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
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from app.engine.methods.contract import METHODS, MethodRegistry, Selection, select_methods
from app.engine.partner.questions import open_issues
from app.engine.registry import EngagementRegistry
from app.engine.types import (
    BOUNDS, PHASE_TRANSITIONS, TERMINAL_STATUSES, AnalysisState, DecisionRole, Entity, Kind, Phase,
    Status,
)

__all__ = [
    "ATTEMPTED_STATES",
    "EngagementState",
    "PhaseError",
    "advance",
    "analysis_blockers",
    "approved_charter",
    "attempted",
    "can_transition",
    "runnable_selections",
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
        """Every BOUNDS name with this state's value - what MethodContext and
        Assignment budgets read. Derived from the frozen name table, so a bound
        the engine reads cannot exist without a setting an operator can move."""
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


def runnable_selections(view, *, methods: MethodRegistry = METHODS) -> list[Selection]:
    """What analysis could still do: a selection over the open issue nodes
    whose required inputs the registry already satisfies and which has not
    already been attempted on that node. The loop runs exactly this list, and
    the SYNTHESIS guard reads exactly this list, so "nothing left to run" means
    the same thing to both."""
    return [s for s in select_methods(open_issues(view), view, methods)
            if not s.inputs.missing and not attempted(view, s.method_id, s.issue_id)]


def synthesis_blockers(view, *, rounds_used: int = 0, bounds: Any = None,
                       methods: MethodRegistry = METHODS) -> tuple[str, ...]:
    """SYNTHESIS is reachable when no selection is runnable, or when the round
    ceiling is reached - an engagement whose methods keep producing work must
    still be able to deliver, and MAX_ANALYSIS_ROUNDS is where that is said."""
    if int(rounds_used) >= int(_bound(bounds if bounds is not None else _live_settings(),
                                      "MAX_ANALYSIS_ROUNDS")):
        return ()
    left = runnable_selections(view, methods=methods)
    if left:
        return (f"{len(left)} selection(s) still runnable",)
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
