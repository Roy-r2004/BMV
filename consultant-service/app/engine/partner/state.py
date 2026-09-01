"""app/engine/partner/state.py - the phase machine and the registry queries
that guard it (design 6.1).

`EngagementState` is the whole of the engine's mutable state: the registry, the
phase pointer, the turn counter and the bounds. There is deliberately nothing
else - no cached hypothesis, no stored summary, no per-engagement flags - so
the only way to learn what an engagement believes is to query its rows.

The laws this module lives by:

  * A phase change happens only along `PHASE_TRANSITIONS`. The table is the
    contract's, not this module's, so a new phase edge is a contract change
    with a schema version, never a line added here.
  * ANALYSIS is unreachable without a CHARTER the CLIENT approved, whose
    `central_decision` is a live DECISION with `role=CENTRAL` and whose
    `decision_owner` is a live DECISION_OWNER. This is the guard that keeps
    paid analysis behind the client's own sign-off; removing it is the
    mutation `test_analysis_is_unreachable_without_an_approved_charter` kills.
    (Only `Actor.CLIENT` can carry a CHARTER to APPROVED - `APPROVAL_OWNER` in
    authority.py - so a charter that IS approved was approved by the client;
    the guard reads the status and lets the registry own the actor law.)
  * SYNTHESIS is reachable once nothing is left to run or the round ceiling is
    reached. "Left to run" is a query - a selection whose inputs the registry
    satisfies and which has not already been attempted on that node - so the
    loop and the guard can never disagree about whether analysis is finished.
  * A refused transition raises `PhaseError` carrying every reason. A guard
    that silently declined would leave the engagement sitting in a phase
    nobody chose, which is exactly how work gets done without a mandate.
  * No bound is a literal here: every ceiling comes from Settings (ENGINE_*)
    or a BOUNDS mapping, so an operator moves it without a code change.
  * `settings_bounds()` is exactly the BOUNDS names and nothing else. It is the
    operator's side of what a method reads, so a per-call binding (a database
    session a callable closes over, the account a run is billed to) is not
    added here: the analysis round merges those over this mapping in loop.py.
    Returning one from here would make a caller's value indistinguishable from
    a ceiling an operator set, and no operator would see it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from app.engine.methods.contract import (
    METHODS, MethodRegistry, Selection, input_fingerprint, productive, select_methods,
)
from app.engine.partner.questions import open_issues
from app.engine.registry import EngagementRegistry
from app.engine.types import (
    ANALYSIS_KINDS, BOUNDS, PHASE_TRANSITIONS, TERMINAL_STATUSES, AnalysisState, DecisionRole,
    Entity, Kind, Phase, Status,
)

__all__ = [
    "ATTEMPTED_STATES",
    "EngagementState",
    "PhaseError",
    "advance",
    "analysis_blockers",
    "approved_charter",
    "attempted",
    "attempted_predicate",
    "can_transition",
    "granted_slots",
    "methods_run",
    "open_selections",
    "outstanding_inputs",
    "runnable_selections",
    "saturated_kinds",
    "synthesis_blockers",
    "transition_blockers",
]


class PhaseError(RuntimeError):
    """A phase change the machine refuses, with every reason it refused for.

    The reasons are what the client (or the API) is told: "not yet, and here is
    what is missing" is an answer; a silent no is not.
    """

    def __init__(self, current: Phase, target: Phase, reasons: Iterable[str]):
        self.current = current
        self.target = target
        self.reasons = tuple(reasons)
        detail = "; ".join(self.reasons) if self.reasons else "not a declared transition"
        super().__init__(f"{current.value} -> {target.value} refused: {detail}")


# ---------------------------------------------------------------------------
# 1. State
# ---------------------------------------------------------------------------

def _live_settings() -> Any:
    """The live Settings object, or the frozen defaults when app.config is not
    importable. A bounds lookup must never be the reason a turn cannot run."""
    try:
        from app.config import settings

        return settings
    except Exception:                                    # pragma: no cover - defensive
        return BOUNDS


def _bound(bounds: Any, name: str):
    """A bound comes from Settings (ENGINE_*) or a mapping of BOUNDS names; the
    frozen default is the last resort so a bound can never be a literal in this
    module (dynamic-not-hardcoded)."""
    if isinstance(bounds, Mapping):
        return bounds.get(name, BOUNDS[name])
    return getattr(bounds, f"ENGINE_{name}", BOUNDS[name])


@dataclass
class EngagementState:
    """(registry, phase, turn_n, bounds) and nothing else (design 6.1).

    The phase pointer is mutable because it is a pointer, not a record: every
    phase change that matters is already a row (a CHARTER approved, an ANALYSIS
    done, a QUESTION opened), and the pointer is recomputable from them.
    """
    registry: EngagementRegistry
    phase: Phase = Phase.OPENING
    turn_n: int = 0
    bounds: Any = field(default_factory=_live_settings)

    def bound(self, name: str):
        return _bound(self.bounds, name)

    def settings_bounds(self) -> Mapping[str, Any]:
        """Every BOUNDS name with this state's value, and no other key - what
        MethodContext and Assignment budgets read.

        Derived from the frozen name table by construction, so a bound the
        engine reads cannot exist without a setting an operator can move, and
        nothing that is not a bound can arrive through here. The seam a costed
        method needs (the r30 commissioning callable and the account it runs
        under) is bound per call by the thread that owns the session and merged
        over this mapping in `loop._method_settings`; the two stay separable
        because this one is derived and that one is given.
        """
        return {name: self.bound(name) for name in BOUNDS}


# ---------------------------------------------------------------------------
# 2. The queries the guards are made of
# ---------------------------------------------------------------------------

def approved_charter(view) -> Entity | None:
    """The charter the client approved, latest first-written wins ties.

    An amendment is a NEW charter row citing the one it amends; until the
    client approves it the previous charter still stands, which is why this
    reads the approved ones rather than the newest one.
    """
    approved = view.query(Kind.CHARTER, status=Status.APPROVED)
    return approved[-1] if approved else None


def analysis_blockers(view, *, rounds_used: int = 0, bounds: Any = None,
                      methods: MethodRegistry = METHODS) -> tuple[str, ...]:
    """Why ANALYSIS is not reachable, or () when it is (design 6.1).

    Three registry facts, in the order a client would hear them. The first is
    the mandate itself: without it the other two are questions about a document
    that does not exist, so the check stops there.
    """
    charter = approved_charter(view)
    if charter is None:
        return ("no CHARTER approved by the client",)
    reasons: list[str] = []
    central = view.get(charter.payload.central_decision or "")
    if central is None or central.kind != Kind.DECISION or central.status in TERMINAL_STATUSES \
            or central.payload.role != DecisionRole.CENTRAL:
        reasons.append(f"{charter.id} names no live central DECISION")
    owner = view.get(charter.payload.decision_owner or "")
    if owner is None or owner.kind != Kind.DECISION_OWNER or owner.status in TERMINAL_STATUSES:
        reasons.append(f"{charter.id} names no live DECISION_OWNER")
    return tuple(reasons)


# An analysis that ran and an analysis that was refused are both attempts. A
# blocked or rejected assignment re-run on the same inputs would spend the
# client's budget to be refused again, so it counts as done with.
ATTEMPTED_STATES: frozenset[AnalysisState] = frozenset({AnalysisState.DONE, AnalysisState.BLOCKED})


def attempted(view, method_id: str, issue_id: str) -> bool:
    """Whether this method has already been run on this issue node. Read from
    ANALYSIS rows, so a free run, a specialist run and a reloaded engagement
    all answer the same way."""
    for a in view.query(Kind.ANALYSIS):
        if a.status in TERMINAL_STATUSES:
            continue
        p = a.payload
        if p.method_id == method_id and issue_id in p.issue_ids and p.state in ATTEMPTED_STATES:
            return True
    return False


def _runs_of(view, method_id: str) -> list[Any]:
    """Every recorded attempt at this method, anywhere in the engagement."""
    return [a.payload for a in view.query(Kind.ANALYSIS)
            if a.status not in TERMINAL_STATUSES and a.payload.method_id == method_id
            and a.payload.state in ATTEMPTED_STATES]


def exhausted_methods(view) -> frozenset[str]:
    """The methods a run of which kept nothing.

    A method that generated candidates and refused every one of them, or that
    left the registry exactly as it found it, has told the engagement something
    real: there is nothing here for it to do. Offering it again spends a
    selection slot - and, where it is model-assisted, another model call - on
    an outcome already observed. `issue_tree` ran up to five times an
    engagement on this tree, kept nodes on the first run and refused all of its
    output on every run after, every one of them costing a call; four other
    methods did the same.

    Engagement-wide and not per node, because the observation is about the
    method against this register, not about the node it was pointed at: the
    second node is shown the same rows and the same refusals follow.
    """
    return frozenset(p.method_id for p in
                     (a.payload for a in view.query(Kind.ANALYSIS)
                      if a.status not in TERMINAL_STATUSES and a.payload.state in ATTEMPTED_STATES)
                     if not productive(p))


def spent_or_repeated(view, spec) -> bool:
    """Whether offering this method again could tell the engagement anything.

    Three readings of the same register, all of them from counts and typed
    fields and none from a case:

      * a run of it kept nothing, so it has nothing here to do
        (`exhausted_methods`);
      * it has already been shown exactly this window, so it would conclude
        what it concluded then (`shown_before`);
      * it says itself, from the register, that it has nothing left to
        conclude (`MethodSpec.pending`).

    Read in TWO places on purpose. `open_selections` reads it when the round's
    list is built, and the loop reads it again immediately before each
    selection runs - because a round runs several selections and the earlier
    ones are new information. A list built once and trusted all round is how
    five runs of one method got made in a single pass, four of them refusing
    everything they generated.
    """
    if spec.id in exhausted_methods(view):
        return True
    if shown_before(view, spec.id, input_fingerprint(spec, view)):
        return True
    return spec.pending is not None and not spec.pending(view)


def shown_before(view, method_id: str, fingerprint: str) -> bool:
    """Whether this method has already been shown exactly these inputs.

    The honest form of "already done". `attempted` asks about a NODE, which is
    a question about the tree; this asks about the EVIDENCE, which is what the
    method actually reads. A method run again over an unchanged window
    concludes what it concluded before and has all of it refused as a
    restatement - a call spent to learn what the registry already held. A
    window that has changed is a different question and the method is offered
    it.
    """
    if not fingerprint:
        return False
    return any(p.input_fingerprint == fingerprint for p in _runs_of(view, method_id))


def saturated_kinds(view, *, bounds: Any = None) -> frozenset[Kind]:
    """The analysis kinds this engagement already holds its fill of.

    MAX_ENTITIES_PER_ANALYSIS_KIND is the ceiling, and it is derived from the
    bounds the engine already publishes: every round running flat out, opening
    every branch it is allowed. The other bounds cap how much WORK may run;
    none of them capped what the work leaves behind, which is how an engagement
    came to hold six hundred routes to a single decision. Divergence counted
    over distinct sets is cheap when production is unbounded, so a ceiling here
    is what makes the distinctness assertions mean anything.

    Only what an ANALYSIS concludes is rationed (ANALYSIS_KINDS). The evidence
    the client handed over is not the engine's to ration, and the process
    records it keeps - questions, analysis rows - are how the engagement is
    audited.
    """
    ceiling = int(_bound(bounds if bounds is not None else _live_settings(),
                         "MAX_ENTITIES_PER_ANALYSIS_KIND"))
    return frozenset(k for k in ANALYSIS_KINDS if len(view.live(k)) >= ceiling)


def methods_run(view) -> frozenset[str]:
    """Every method this engagement has already attempted ANYWHERE, by id.

    `attempted` answers about one node; this answers about the engagement, and
    it is what a scarce round budget is spent by. Read from the same ANALYSIS
    rows and the same ATTEMPTED_STATES, so the two can never disagree about
    what "already done" means.
    """
    return frozenset(a.payload.method_id for a in view.query(Kind.ANALYSIS)
                     if a.status not in TERMINAL_STATUSES
                     and a.payload.state in ATTEMPTED_STATES)


def granted_slots(view, selections: Iterable[Selection], *, ceiling: int) -> frozenset[tuple[str, str]]:
    """Which of a round's assignment-bound selections get the round's
    specialist slots, as (issue_id, method_id) keys.

    MAX_SPECIALISTS_PER_ROUND is a real budget - a specialist costs the client
    money - so some fully-fed work does not run this round. WHICH work is
    dropped was previously decided by nothing: the loop took selections in
    issue order and stopped counting, so the budget went to whichever nodes the
    tree happened to list first, and a method that only ever matched later
    nodes was crowded out of every round of the engagement. On a large tree
    that is the whole of the difference between an engagement that reaches the
    delivery half of the library and one that does not, decided by list order.

    The rule is breadth before depth: a method the engagement has not run yet
    goes ahead of one it has. A budget is a reason to do a different thing next,
    not to do the same thing again, and this is the only place the loop knows
    that the round is scarce. Beneath that the existing rank decides, and the
    node id breaks the last tie, so the choice is total and deterministic.
    """
    already = methods_run(view)
    ordered = sorted(selections,
                     key=lambda s: (s.method_id in already, s.rank_key, s.issue_id, s.method_id))
    return frozenset((s.issue_id, s.method_id) for s in ordered[:max(0, int(ceiling))])


def attempted_predicate(view) -> Callable[[str, str], bool]:
    """`attempted` in the shape `select_methods` takes its `exclude` in.

    Selection has to know what has already run or the node's ceiling
    (MAX_METHODS_PER_ISSUE) is held forever by the methods that ran first, and
    a method whose inputs those runs just wrote could never be reached. It is
    handed in as a predicate rather than queried inside `select_methods` so
    that function still reads nothing but enums and booleans - the scramble
    law (design 18.6) is about what steers selection, and a boolean keyed on
    two ids steers nothing a rewording could change.
    """
    def _excluded(issue_id: str, method_id: str) -> bool:
        return attempted(view, method_id, issue_id)
    return _excluded


def open_selections(view, *, bounds: Any = None, methods: MethodRegistry = METHODS) -> list[Selection]:
    """Every selection analysis has not already attempted, satisfied or not.

    One list, read by the loop (which runs the satisfied ones) and by the
    SYNTHESIS guard (which also asks whether an unsatisfied one could still
    become satisfied), so the two can never disagree about what is left.
    """
    full = saturated_kinds(view, bounds=bounds)
    spent = exhausted_methods(view)

    def _excluded(issue_id: str, method_id: str) -> bool:
        if attempted(view, method_id, issue_id):
            return True
        spec = methods.get(method_id).spec
        # A method a run of which kept nothing, or which has already been shown
        # this window, or which says it has nothing left to conclude, is not
        # offered again. The set is precomputed once for the cheap half.
        if method_id in spent or spent_or_repeated(view, spec):
            return True
        # A method ANY of whose CONCLUSIONS the engagement already holds its
        # fill of is not offered again. Only the analysis kinds are counted -
        # almost every method may also write a QUESTION, and a kind that is
        # never rationed would make this test true of nothing.
        #
        # ANY, not ALL. A method writes its kinds together, in one batch that
        # the registry admits or rolls back whole, so a method that would write
        # one row of a saturated kind alongside twenty of an unsaturated one
        # cannot write the twenty: I9 refuses the one and the batch goes back.
        # Requiring EVERY kind to be full therefore kept offering a method that
        # could no longer land anything, round after round, and the guard and
        # the ceiling defeated each other - the ceiling refused the batch, the
        # rollback put the live count back BELOW the ceiling, and the guard
        # looked and saw room. A method that concludes nothing saturated stays
        # selectable.
        concludes = [k for k in spec.output_kinds if k in ANALYSIS_KINDS]
        return any(k in full for k in concludes)

    return select_methods(open_issues(view), view, methods,
                          max_per_issue=_bound(bounds if bounds is not None else _live_settings(),
                                               "MAX_METHODS_PER_ISSUE"),
                          exclude=_excluded)


def runnable_selections(view, *, bounds: Any = None,
                        methods: MethodRegistry = METHODS) -> list[Selection]:
    """What analysis could do right now: a selection over the open issue nodes
    whose required inputs the registry already satisfies and which has not
    already been attempted on that node. The loop runs exactly this list, and
    the SYNTHESIS guard reads exactly this list, so "nothing left to run" means
    the same thing to both."""
    return [s for s in open_selections(view, bounds=bounds, methods=methods) if not s.inputs.missing]


def outstanding_inputs(view, *, bounds: Any = None,
                       methods: MethodRegistry = METHODS) -> list[str]:
    """The selections that are not runnable yet but something is still
    expected to fill: a required input this registry does not satisfy, whose
    kind either a runnable selection writes or an OPEN question has already
    asked the client for.

    This is the second half of "is analysis finished". `runnable_selections`
    only ever asks what is satisfied AT THIS INSTANT, and answering SYNTHESIS
    on that alone ends analysis after one tier: the methods that feed the
    delivery half of the library are unsatisfied on the first pass by
    construction, the answers that would feed them arrive on later turns, and
    PHASE_TRANSITIONS offers no way back from SYNTHESIS. This is the term that
    lets the design-6.7 interleave run more than once.

    Both halves are things that are actually coming. A kind whose only writers
    are themselves blocked is not about to arrive - make_buy_partner needing
    an OPTION it is the only writer of was a cycle of exactly that shape - and
    an unasked kind is not either; waiting for one would hold an engagement
    open on a promise nothing can keep. A question the client answered, even
    with "I do not know", is no longer OPEN (`ingest.open_questions` never
    re-asks it), so the second half empties as the conversation proceeds and
    MAX_ANALYSIS_ROUNDS remains the unconditional escape above both.
    """
    pending = open_selections(view, bounds=bounds, methods=methods)
    if not pending:
        return []
    coming: set[Kind] = set()
    for s in pending:
        if not s.inputs.missing:
            coming.update(methods.get(s.method_id).spec.output_kinds)
    for q in view.query(Kind.QUESTION, status=Status.OPEN):
        coming.update(a.kind for a in q.payload.asks_for)
    out: list[str] = []
    for s in pending:
        for inp in s.inputs.missing:
            if inp.kind in coming:
                out.append(f"{s.method_id} on {s.issue_id} waits for {inp.kind.value}")
                break
    return out


def synthesis_blockers(view, *, rounds_used: int = 0, bounds: Any = None,
                       methods: MethodRegistry = METHODS) -> tuple[str, ...]:
    """SYNTHESIS is reachable when nothing is left to run AND nothing left to
    run is waiting on a kind that is still coming - or when the round ceiling
    is reached.

    The second term is what makes the interleave of design 6.7 possible.
    "Nothing runnable at this instant" is not "analysis is complete": a method
    whose inputs are the outputs of a method that has not run yet, or of an
    answer the client has been asked for and not yet given, is unsatisfied on
    every first pass - and because PHASE_TRANSITIONS offers no way back from
    SYNTHESIS, answering on the first term alone ends every engagement after
    one tier of the dependency graph.

    MAX_ANALYSIS_ROUNDS stays the unconditional escape, checked first: an
    engagement whose methods keep producing work must still be able to
    deliver, and that ceiling is where it is said.
    """
    if int(rounds_used) >= int(_bound(bounds if bounds is not None else _live_settings(),
                                      "MAX_ANALYSIS_ROUNDS")):
        return ()
    left = runnable_selections(view, bounds=bounds, methods=methods)
    if left:
        return (f"{len(left)} selection(s) still runnable",)
    waiting = outstanding_inputs(view, bounds=bounds, methods=methods)
    if waiting:
        return tuple(sorted(waiting))
    return ()


# Only the phases whose entry is a registry fact carry a guard; the rest are
# reachable whenever the transition table admits them.
_GUARDS = {
    Phase.ANALYSIS: analysis_blockers,
    Phase.SYNTHESIS: synthesis_blockers,
}


# ---------------------------------------------------------------------------
# 3. The machine
# ---------------------------------------------------------------------------

def can_transition(current: Phase, target: Phase) -> bool:
    """Table lookup only. The guards are a separate question, asked second, so
    "not a declared edge" and "declared but not yet earned" never blur."""
    return target in PHASE_TRANSITIONS.get(current, frozenset())


def transition_blockers(view, target: Phase, *, rounds_used: int = 0, bounds: Any = None,
                        methods: MethodRegistry = METHODS) -> tuple[str, ...]:
    guard = _GUARDS.get(target)
    if guard is None:
        return ()
    return guard(view, rounds_used=rounds_used, bounds=bounds, methods=methods)


def advance(state: EngagementState, target: Phase, *, rounds_used: int = 0,
            methods: MethodRegistry = METHODS) -> Phase:
    """Move the engagement to `target`, or raise PhaseError saying why not.

    Both halves are enforced: the edge must be declared in PHASE_TRANSITIONS
    and the target's guard must find nothing missing. Re-entering the phase the
    engagement is already in is a no-op rather than an error - a turn that ends
    where it began has not broken any law.
    """
    if target == state.phase:
        return state.phase
    if not can_transition(state.phase, target):
        raise PhaseError(state.phase, target, ())
    reasons = transition_blockers(state.registry, target, rounds_used=rounds_used,
                                  bounds=state.bounds, methods=methods)
    if reasons:
        raise PhaseError(state.phase, target, reasons)
    state.phase = target
    return state.phase
