"""Executing an Assignment: scoped view, budgeted provider, all-or-nothing
admission (design section 8, contracts.py section 12).

Two doors lead into a method, and only two:

  run()       every RESEARCH / MODEL_ASSISTED method and every tied selection.
              The method runs as Actor.SPECIALIST behind a ScopedView, its
              model calls are counted against the assignment's Budget, and
              every delta it returns is checked under S1-S6 *before any of
              them is applied*.
  run_free()  the loop's only direct-execution door: DETERMINISTIC and
              CALCULATION methods, untied, as Actor.METHOD. It refuses
              anything else, which is the mechanical form of MF1.2 -- there is
              no code path that runs a research method without an assignment.

Why admission is all-or-nothing. A specialist's result is one argument, not a
bag of independent rows: if one delta reaches outside the assignment, the
reasoning that produced the rest reached outside too. Admitting the "good"
part of a result that broke a rule would leave conclusions in the registry
whose basis was never scoped, and no reader could tell which ones. So the
runner checks every delta first, and on any violation writes nothing at all,
records the outcome and the rule on the assignment row, and returns a Finding.

Validators are the runner's to run, not the method's to remember. Every
Validator the method declared on its MethodSpec is called as v(view, result)
on the admitted result and its findings are attached to the ANALYSIS: a
declared law that nothing calls is a comment, and the point of putting the
laws on the spec was that they bite on every run of that method however the
Assignment reached the runner.

What the runner never does: reconcile. Two specialists that disagree leave two
PROPOSED entities of one kind on one subject, and synthesis turns that into a
CONFLICT(SPECIALIST_DISAGREEMENT). A runner that merged them would be the one
place in the engine where a disagreement could disappear silently.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from typing import Any, Iterable, Mapping, Sequence

from app.engine.methods.contract import (
    METHODS, MethodContext, MethodRegistry, MethodResult, Selection, input_fingerprint,
    question_lineage, question_relevance, run_record,
)
from app.engine.registry import Calculator, EngagementRegistry, ScopedView
from app.engine.specialists.assignment import (
    ADMISSION_RULES, Assignment, DECISION_OWNED_KINDS, default_budget, resolve_bounds,
)
from app.engine.types import (
    ASSIGNMENT_EXECUTION,
    Actor,
    Add,
    AnalysisPayload,
    AnalysisState,
    ApprovalState,
    Confidence,
    Entity,
    EntityDelta,
    FactBasis,
    Finding,
    Kind,
    Provenance,
    Quantity,
    RegistryError,
    Relevance,
    RelationToCentralDecision,
    SetStatus,
    Severity,
    Status,
    Supersede,
    make_entity,
)

# A fact whose basis asserts the client said it, or that a document says it,
# is a fact about the outside world. A specialist reads the world through its
# permitted evidence and never becomes a source for it (S3).
_SOURCE_BASES: frozenset[FactBasis] = frozenset(
    {FactBasis.CLIENT_STATED, FactBasis.DOCUMENT_VERIFIED, FactBasis.DOCUMENT_EXTRACTED})


class BudgetExceeded(Exception):
    """The assignment ran out of what it was funded for. It is an exception
    and not a truncation on purpose: half an analysis presented as a whole one
    is the failure mode this class exists to prevent."""

    def __init__(self, what: str, spent: int, limit: int):
        super().__init__(f"{what}: {spent} exceeds the assignment's budget of {limit}")
        self.what = what
        self.spent = spent
        self.limit = limit


class AssignmentRequired(Exception):
    """A method that may only run under an Assignment was handed to the direct
    door (MF1.2)."""


class BudgetedProvider:
    """The provider a specialist sees. Counts calls and reserved tokens against
    the assignment's Budget and raises before the call that would exceed it, so
    the ceiling is enforced where the money is spent rather than checked
    afterwards. Tokens are charged at the call's own max_tokens reservation:
    what a provider reports back varies, what the call asked for does not, and
    a budget that only counted returned usage would let a cassette or a fake
    run for free."""

    def __init__(self, inner, budget, *, method_id: str):
        self._inner = inner
        self.budget = budget
        # The ledger purpose this assignment's calls belong to. The call's own
        # purpose is left alone: rewriting it would silently re-key every
        # scripted fake and recorded cassette keyed on the method's purpose.
        self.purpose = f"engine:specialist:{method_id}"
        self.calls = 0
        self.reserved = 0
        self.tokens_used = 0
        self.call_ids: list[str] = []

    def complete(self, call):
        if self.calls + 1 > self.budget.max_model_calls:
            raise BudgetExceeded("model calls", self.calls + 1, self.budget.max_model_calls)
        want = self.reserved + int(getattr(call, "max_tokens", 0) or 0)
        if want > self.budget.max_tokens:
            raise BudgetExceeded("tokens", want, self.budget.max_tokens)
        response = self._inner.complete(call)
        self.calls += 1
        self.reserved = want
        usage = getattr(response, "usage", None) or {}
        self.tokens_used += int(usage.get("prompt_tokens", 0) or 0) + int(usage.get("completion_tokens", 0) or 0)
        if getattr(response, "call_id", None):
            self.call_ids.append(response.call_id)
        return response


@dataclass(frozen=True)
class RunOutcome:
    """What one assignment did. `outcome` mirrors the value stored on the
    SPECIALIST_ASSIGNMENT row, so the registry and the caller can never tell
    different stories about the same run."""
    assignment_id: str
    outcome: str                                  # "done" | "blocked" | "rejected"
    written: tuple[Entity, ...] = ()
    findings: tuple[Finding, ...] = ()
    rejection_rule: str | None = None
    analysis_id: str | None = None
    model_calls: int = 0


# =============================================================================
# admission (S1-S6)
# =============================================================================

def _written_entities(deltas: Iterable[EntityDelta]) -> list[Entity]:
    """Every row a result would create: an Add's entity and a Supersede's
    replacement. A supersession writes a row too, so it faces the same rules
    an Add does -- otherwise S2 and S3 would be evadable by rewriting instead
    of adding."""
    out: list[Entity] = []
    for d in deltas:
        if isinstance(d, (Add, Supersede)):
            out.append(d.entity)
    return out


def _quantities(payload: Any, _seen: set[int] | None = None) -> list[Quantity]:
    """Every Quantity anywhere in a payload, including inside nested frozen
    dataclasses and tuples: S6 must see the number wherever the payload chose
    to put it, not only in a field called `quantity`."""
    seen = _seen if _seen is not None else set()
    if id(payload) in seen:
        return []
    seen.add(id(payload))
    out: list[Quantity] = []
    if isinstance(payload, Quantity):
        return [payload]
    if is_dataclass(payload) and not isinstance(payload, type):
        for f in fields(payload):
            out.extend(_quantities(getattr(payload, f.name), seen))
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            out.extend(_quantities(item, seen))
    return out


def _is_calculated_fact(e: Entity) -> bool:
    """A CalcResult as the registry stores arithmetic: the formula over entity
    ids and the input ids that reproduce it exactly (I8, and what L7
    recomputes)."""
    return (e.kind == Kind.FACT and e.payload.basis == FactBasis.CALCULATED
            and bool(e.payload.formula) and bool(e.payload.inputs))


def _own_rows(registry: EngagementRegistry, *, actor_ref: str, calc_ref: str,
              assignment_id: str) -> set[str]:
    """Every row already in the registry that this assignment wrote, by id.

    Two writers sign one assignment's work, not one. The specialist signs its
    own conclusions (actor_ref "specialist:<id>"); the deterministic
    calculator signs the arithmetic a method runs inside the assignment
    (calculated_fact signs "calc:<method_id>", because arithmetic is owned by
    the deterministic engine and never by the analyst who asked for it). A
    RESEARCH method that sizes something writes exactly that row, so an
    actor_ref comparison knowing only about the specialist would treat the
    assignment's own calculation as a foreign record and refuse the run.

    The calculator's ref alone would be too wide: "calc:<method_id>" is the
    same string for every assignment of that method, and S1 exists precisely
    so one role cannot edit another's record. So a calculator row counts as
    this assignment's only when this assignment's own ANALYSIS listed it as an
    output -- the registry's record of which run produced it."""
    own = {e.id for e in registry.rows() if e.provenance.actor_ref == actor_ref}
    if not assignment_id:
        return own
    for analysis in registry.query(Kind.ANALYSIS):
        if getattr(analysis.payload, "assignment_id", None) != assignment_id:
            continue
        for out_id in analysis.payload.outputs:
            row = registry.get(out_id)
            if row is not None and row.provenance.actor_ref == calc_ref:
                own.add(out_id)
    return own


def _quantity_matches(q: Quantity, other: Quantity) -> bool:
    """A copy is the same number in the same unit with the same dimensions
    pinned the same way. A quantity that agrees on the value but re-pins a
    dimension is a new claim about scope or period, not a copy."""
    return (q.value == other.value and q.unit == other.unit
            and q.unit_family == other.unit_family and q.dimensions == other.dimensions)


def admission_violations(assignment: Assignment, result: MethodResult, registry: EngagementRegistry,
                         *, actor_ref: str, permitted: frozenset[str],
                         issue: Entity | None = None,
                         assignment_id: str = "") -> list[tuple[str, str, str]]:
    """Every rule broken by any delta, as (rule, where, why). The caller
    refuses the whole result on the first entry; the whole list is returned so
    the record says everything that was wrong with it, not only the first
    thing noticed."""
    out: list[tuple[str, str, str]] = []
    rows = _written_entities(result.deltas)
    # Rows already in the registry that this assignment wrote -- its own, and
    # the calculator's on its behalf. S1 reads this set alone: retiring or
    # re-statusing a row is lawful only against it.
    own = _own_rows(registry, actor_ref=actor_ref, calc_ref=f"calc:{assignment.method_id}",
                    assignment_id=assignment_id)
    # Ids this assignment may cite: rows named in this batch, plus everything
    # it already owns. Wider than `own` on purpose -- a Supersede's
    # replacement carries the id it replaces, and citing a row is not editing
    # it, so S5 must not borrow S1's set.
    created = {e.id for e in rows if e.id} | own
    targeted = set(issue.payload.decisive_for) if issue is not None else set()
    forbidden = set(assignment.forbidden_decisions)
    # Every number ctx.calc produced in this same result: the aggregate rows a
    # calculation method writes carry the CalcResult's own quantity.
    calc_quantities = [q for row in rows if _is_calculated_fact(row) for q in _quantities(row.payload)]

    for d in result.deltas:
        # S1 -- a specialist may retire or re-status only its own conclusions.
        # Anything else is one role editing another's record, which is how a
        # client fact or a partner's decision would quietly change hands.
        if isinstance(d, (Supersede, SetStatus)):
            target_id = d.old_id if isinstance(d, Supersede) else d.entity_id
            if registry.get(target_id) is None or target_id not in own:
                out.append(("S1", target_id, ADMISSION_RULES["S1"]))

    for e in rows:
        where = e.id or e.kind.value
        # S2 -- everything a specialist writes is PROPOSED. A specialist's
        # conclusion is a proposal to the engagement, never a settled fact.
        # The one exception is the deterministic engine's own row: a
        # calculated FACT written by the CALCULATOR is CONFIRMED because
        # recompute() reproduces it exactly and MAY_CONFIRM says arithmetic is
        # the calculator's to confirm -- and L7 re-verifies it at the gate.
        #
        # PROPOSED is admitted for that same row too. A RESEARCH method whose
        # calculation step runs inside an assignment proposes its arithmetic
        # rather than confirming it, and the actor that owns arithmetic re-runs
        # the formula afterwards: the same figure, the same formula, one
        # authority later. Admitting the weaker of the two statuses can let
        # nothing through that the stronger one did not already.
        actor = e.provenance.actor
        calc_row = (actor == Actor.CALCULATOR and _is_calculated_fact(e)
                    and e.status in (Status.PROPOSED, Status.CONFIRMED))
        if not calc_row and not (actor == Actor.SPECIALIST and e.status == Status.PROPOSED):
            out.append(("S2", where, ADMISSION_RULES["S2"]))

        # S3 -- a specialist is never a source. Client recollections and
        # document records enter through ingestion, where the verbatim and the
        # hash are checked (I2); a specialist writing one would manufacture
        # evidence for its own conclusion.
        #
        # A calculated FACT is the admitted case, not an exception tolerated:
        # the formula over entity ids and the input ids are on the row, so
        # recompute() reproduces it exactly and nobody has to trust the
        # producer -- that is how a RESEARCH method registers a size it did
        # not type. It is admitted only when they are actually there:
        # basis=calculated makes the row's info_type ARITHMETIC, owned by the
        # deterministic engine, so a row claiming it with no formula and no
        # inputs is a coined figure wearing the calculator's authority.
        if e.kind == Kind.FACT and e.payload.basis in _SOURCE_BASES:
            out.append(("S3", where, ADMISSION_RULES["S3"]))
        elif e.kind == Kind.FACT and e.payload.basis == FactBasis.CALCULATED and not _is_calculated_fact(e):
            out.append(("S3", where, ADMISSION_RULES["S3"] + " (calculated with no formula or no inputs)"))

        # S4 -- the specialist answers its node; it does not settle decisions
        # it was not given. Options for a forbidden decision are refused too
        # unless this node was built to be decisive for it.
        if (e.kind in DECISION_OWNED_KINDS and e.payload.decision_id in forbidden
                and not (e.kind == Kind.OPTION and e.payload.decision_id in targeted)):
            out.append(("S4", where, ADMISSION_RULES["S4"]))

        # S5 -- cite only what you could read. The window is the scope: a
        # citation outside permitted evidence means the conclusion rests on
        # something the assignment never granted (and ScopedView returned
        # nothing for), so the lineage would be a fiction.
        for cited in e.provenance.derived_from:
            if cited not in permitted and cited not in created:
                out.append(("S5", where, f"{ADMISSION_RULES['S5']} ({cited} is neither)"))
        if e.kind == Kind.ASSUMPTION:
            grant = assignment.grant_for(e)
            if grant is None:
                out.append(("S5", where, f"{ADMISSION_RULES['S5']} (no grant admits this assumption)"))
            # An assumption a specialist approved for itself would be an
            # invented number wearing a confirmed label; only the client
            # approves an assumption (APPROVAL_OWNER).
            if e.payload.approval != ApprovalState.UNAPPROVED or e.status == Status.APPROVED:
                out.append(("S5", where, f"{ADMISSION_RULES['S5']} (the assumption is not unapproved)"))

        # S6 -- no coined numbers. Every quantity is either arithmetic the
        # calculator did (formula + inputs, recomputable) or the same number
        # already in permitted evidence, copied from the entity it cites.
        # An ASSUMPTION under a grant is the one place a number may be stated
        # without either: that is what an assumption IS, and it is visibly
        # unapproved until the client approves it.
        if e.kind == Kind.ASSUMPTION and assignment.grant_for(e) is not None:
            continue
        if _is_calculated_fact(e):
            continue
        for q in _quantities(e.payload):
            if any(_quantity_matches(q, other) for other in calc_quantities):
                continue                                  # a CalcResult this same result produced
            sources: list[Quantity] = []
            for cited in e.provenance.derived_from:
                if cited not in permitted and cited not in created:
                    continue
                src = registry.get(cited)
                if src is not None:
                    sources.extend(_quantities(src.payload))
            if not any(_quantity_matches(q, other) for other in sources):
                out.append(("S6", where, f"{ADMISSION_RULES['S6']} ({q.value} {q.unit} is neither)"))
    return out


# =============================================================================
# running
# =============================================================================

def declared_validators(assignment: Assignment, spec) -> list:
    """Every Validator that must judge this result: the ones the Assignment
    was issued with, and the ones the method declared on its own MethodSpec.

    Usually the same objects -- Assignment.from_selection copies
    spec.validators -- and deduplicated by identity so a validator is not run
    twice. The union is the law: an Assignment built any other way (rebuilt
    from a persisted row, or assembled by a caller filling the fields itself)
    would otherwise run a method with every one of its declared laws switched
    off, and nothing in the record would say so. A validator the runner does
    not call is a comment.
    """
    out: list = []
    seen: set[int] = set()
    for v in tuple(assignment.validation) + tuple(getattr(spec, "validators", ())):
        if id(v) in seen:
            continue
        seen.add(id(v))
        out.append(v)
    return out


def _finding(rule: str, where: str, why: str, *, assignment_id: str) -> Finding:
    return Finding(law=f"SPE.admission.{rule}", where=where, issue=why,
                   fix="the whole result is refused; re-issue the assignment with the evidence or the grant it needs",
                   severity=Severity.HIGH, entity_ids=(assignment_id,), blocks_final=False)


def _persist_assignment(assignment: Assignment, registry: EngagementRegistry, methods: MethodRegistry,
                        issue: Entity | None) -> str:
    """The assignment row is written before the method runs: what a specialist
    was allowed to do is on the record whatever the run then does, including
    when it is refused."""
    if assignment.id and registry.get(assignment.id) is not None:
        return assignment.id
    cites = tuple(i for i in (assignment.issue_id,) if i and registry.get(i) is not None)
    row = make_entity(
        kind=Kind.SPECIALIST_ASSIGNMENT, engagement_id=registry.engagement_id,
        payload=assignment.as_payload(methods),
        provenance=Provenance(actor=Actor.PARTNER, actor_ref="partner:assignment", derived_from=cites),
        confidence=Confidence(None), relevance=Relevance(None, 0.0),
        relation=RelationToCentralDecision.INFORMS, status=Status.PROPOSED,
        entity_id=assignment.id or "")
    return registry.apply(Add(row)).id


def _record_outcome(registry: EngagementRegistry, assignment_id: str, outcome: str,
                    rejection_rule: str | None) -> None:
    """The verdict lands on the assignment row itself. A refused run that left
    no trace would be indistinguishable from a run that never happened."""
    row = registry.get(assignment_id)
    if row is None:
        return
    payload = replace(row.payload, outcome=outcome, rejection_rule=rejection_rule)
    new = replace(row, payload=payload,
                  provenance=replace(row.provenance, actor=Actor.SYSTEM, actor_ref="system:specialist_runner"))
    registry.apply(Supersede(assignment_id, new))


def _analysis(registry: EngagementRegistry, assignment: Assignment, assignment_id: str, spec, *,
              actor_ref: str, state: AnalysisState, outputs: Sequence[str] = (),
              blocked_on: Sequence[str] = (), fingerprint: str = "",
              record: Mapping[str, int] | None = None) -> Entity:
    """The specialist's own ANALYSIS row, carrying the same account of the run
    the free path records: what it kept, what it generated and refused, what it
    asked, what it spent, and the digest of what it was shown. The selector
    reads both kinds of row through one predicate, so a method cannot be
    rationed on the free path and unrationed under an assignment."""
    counted = dict(record or {})
    payload = AnalysisPayload(
        method_id=spec.id, method_version=spec.version, issue_ids=tuple(i for i in (assignment.issue_id,) if i),
        state=state, inputs=assignment.permitted_evidence, outputs=tuple(outputs),
        assignment_id=assignment_id, blocked_on=tuple(blocked_on), input_fingerprint=fingerprint,
        kept=int(counted.get("kept", 0)), discarded=int(counted.get("discarded", 0)),
        asked=int(counted.get("asked", 0)), model_calls=int(counted.get("model_calls", 0)))
    entity = make_entity(
        kind=Kind.ANALYSIS, engagement_id=registry.engagement_id, payload=payload,
        provenance=Provenance(actor=Actor.SPECIALIST, actor_ref=actor_ref, derived_from=(assignment_id,)),
        confidence=Confidence(None), relevance=Relevance(None, 0.0),
        relation=RelationToCentralDecision.INFORMS, status=Status.PROPOSED)
    return registry.apply(Add(entity))


def _question_entities(registry: EngagementRegistry, result: MethodResult, *, actor_ref: str,
                       assignment_id: str) -> list[Add]:
    """A specialist's questions are written with its outputs. A question the
    runner dropped would be a typed hole the engagement never learns about --
    the one thing absence of evidence must never become."""
    out: list[Add] = []
    for q in result.questions:
        out.append(Add(make_entity(
            kind=Kind.QUESTION, engagement_id=registry.engagement_id, payload=q,
            provenance=Provenance(actor=Actor.SPECIALIST, actor_ref=actor_ref,
                                  derived_from=question_lineage(registry, assignment_id, q)),
            confidence=Confidence(None), relevance=question_relevance(registry, q),
            relation=RelationToCentralDecision.INFORMS, status=Status.OPEN)))
    return out


def run(assignment: Assignment, registry: EngagementRegistry, provider, calc: Calculator, *,
        methods: MethodRegistry = METHODS, settings_bounds: Mapping[str, Any] | None = None) -> RunOutcome:
    """Execute one Assignment. Nothing of the result is written unless all of
    it is admitted (S1-S6), and nothing is truncated to fit a budget: an
    assignment that runs out is blocked, and says so."""
    method = methods.get(assignment.method_id)
    spec = method.spec
    issue = registry.get(assignment.issue_id) if assignment.issue_id else None
    assignment_id = _persist_assignment(assignment, registry, methods, issue)
    actor_ref = f"specialist:{assignment_id}"

    view = ScopedView(registry, assignment.permitted_evidence)
    # Taken before the run and against the REGISTRY rather than the scoped
    # view: the selector that reads it back sees the whole register, and a
    # digest taken through one assignment's window could not be compared with
    # one taken through another's.
    fingerprint = input_fingerprint(spec, registry)
    budgeted = BudgetedProvider(provider, assignment.budget, method_id=spec.id)
    ctx = MethodContext(registry=view, provider=budgeted, calc=calc, actor=Actor.SPECIALIST,
                        actor_ref=actor_ref, issue_ids=tuple(i for i in (assignment.issue_id,) if i),
                        assignment_id=assignment_id, settings=resolve_bounds(settings_bounds))

    def blocked(reason: str, detail: str) -> RunOutcome:
        _record_outcome(registry, assignment_id, "blocked", None)
        analysis = _analysis(registry, assignment, assignment_id, spec, actor_ref=actor_ref,
                             state=AnalysisState.BLOCKED, blocked_on=(reason,),
                             fingerprint=fingerprint)
        finding = Finding(law=f"SPE.budget.{reason}", where=assignment_id, issue=detail,
                          fix="re-issue the assignment with a larger budget, or narrow the question",
                          severity=Severity.HIGH, entity_ids=(assignment_id,), blocks_final=False)
        return RunOutcome(assignment_id, "blocked", (), (finding,), None, analysis.id, budgeted.calls)

    try:
        result = method.run(ctx)
    except BudgetExceeded as exc:
        return blocked("exhausted", str(exc))

    # A result larger than the assignment funded is blocked whole, never
    # trimmed to fit: a truncated analysis reads as a complete one.
    if len(result.deltas) > assignment.budget.max_deltas:
        return blocked("deltas", f"{len(result.deltas)} deltas exceed the assignment's budget of "
                                 f"{assignment.budget.max_deltas}")

    violations = admission_violations(assignment, result, registry, actor_ref=actor_ref,
                                      permitted=view.permitted, issue=issue,
                                      assignment_id=assignment_id)
    if violations:
        rule = min(v[0] for v in violations)          # S1 before S2 before S3...
        findings = tuple(_finding(r, w, why, assignment_id=assignment_id) for r, w, why in violations)
        _record_outcome(registry, assignment_id, "rejected", rule)
        analysis = _analysis(registry, assignment, assignment_id, spec, actor_ref=actor_ref,
                             state=AnalysisState.BLOCKED, blocked_on=(rule,),
                             fingerprint=fingerprint, record=run_record(result))
        return RunOutcome(assignment_id, "rejected", (), findings, rule, analysis.id, budgeted.calls)

    deltas = list(result.deltas) + _question_entities(registry, result, actor_ref=actor_ref,
                                                      assignment_id=assignment_id)
    try:
        written = registry.apply_all(deltas)
    except RegistryError as exc:
        # Admission passed but a registry invariant refused the batch: the
        # batch rolled back whole (apply_all), so the outcome is the same
        # refusal, recorded under the invariant that caught it.
        _record_outcome(registry, assignment_id, "rejected", exc.invariant)
        analysis = _analysis(registry, assignment, assignment_id, spec, actor_ref=actor_ref,
                             state=AnalysisState.BLOCKED, blocked_on=(exc.invariant,),
                             fingerprint=fingerprint, record=run_record(result))
        finding = Finding(law=f"SPE.admission.{exc.invariant}", where=assignment_id, issue=str(exc),
                          fix="the whole result is refused; nothing of it is written",
                          severity=Severity.HIGH, entity_ids=(assignment_id,), blocks_final=False)
        return RunOutcome(assignment_id, "rejected", (), (finding,), exc.invariant, analysis.id, budgeted.calls)

    # Validators judge the admitted result against the window it was allowed to
    # see. Their findings are recorded against the ANALYSIS, not used to delete
    # rows: a flawed conclusion stays visible with its flaw named.
    findings = list(result.findings)
    for validator in declared_validators(assignment, spec):
        try:
            findings.extend(validator(view, result))
        except Exception as exc:                       # pragma: no cover - defensive
            # A validator that raised judged nothing. The rows are already
            # written, so crashing here would leave an assignment with no
            # recorded outcome; the failure is recorded as a finding instead,
            # naming the law that did not get to run.
            findings.append(Finding(
                law=f"SPE.validator.{getattr(validator, '__name__', 'validator')}",
                where=assignment_id, issue=f"the declared validator raised: {exc}",
                fix="fix the validator; until it runs, this method's declared law is unchecked",
                severity=Severity.HIGH, entity_ids=(assignment_id,), blocks_final=False))
    analysis = _analysis(registry, assignment, assignment_id, spec, actor_ref=actor_ref,
                         state=AnalysisState.DONE, outputs=[e.id for e in written],
                         fingerprint=fingerprint, record=run_record(result))
    findings = [replace(f, entity_ids=tuple(dict.fromkeys(f.entity_ids + (analysis.id,)))) for f in findings]
    _record_outcome(registry, assignment_id, "done", None)
    return RunOutcome(assignment_id, "done", tuple(written), tuple(findings), None, analysis.id, budgeted.calls)


def run_free(selection: Selection, ctx: MethodContext, *, methods: MethodRegistry = METHODS) -> MethodResult:
    """The loop's one direct-execution door (MF1.2). It refuses:

      - a RESEARCH or MODEL_ASSISTED method, which may only run under an
        Assignment: those are the executions that reach outside the registry
        or ask a model to word a conclusion, and both need a frozen scope;
      - a tied selection, however cheap, because two methods that ranked equal
        must both run as assignments so their disagreement surfaces as a
        CONFLICT instead of one being silently preferred - unless the method
        writes a kind S4 refuses a specialist on a decision the assignment
        does not target (DECISION_OWNED_KINDS), in which case an assignment
        would reject its whole result on a rule about specialists and the tie
        is broken by running it here instead. Both tied methods still run, so
        neither is silently preferred, and their disagreement still reaches
        `detect_conflicts` as two rows about one subject;
      - a context claiming to be a specialist, which would run scoped work
        without a scope.

    Removing any one of these is the mutation that lets a research method run
    unscoped, and no benchmark case would show an Assignment at all.

    And it METERS the result. `default_budget` is the same production budget an
    Assignment is funded with, applied to the same rule an assignment applies:
    a result larger than the run was funded for is blocked WHOLE, never trimmed
    to fit, because a truncated analysis reads as a complete one. The free path
    was the hole in that law - it is where DETERMINISTIC and CALCULATION
    methods run, which is most of the library's writers, and nothing counted
    what they wrote. A method whose output grew with the size of the register
    rather than with the question it was asked could therefore offer the
    registry hundreds of rows in one batch and be stopped only by the ceiling
    at the door, which rolls the batch back and hides the whole event in a live
    count that lands BELOW the ceiling that refused it.
    """
    spec = methods.get(selection.method_id).spec
    if spec.execution in ASSIGNMENT_EXECUTION:
        raise AssignmentRequired(
            f"{spec.id} is {spec.execution.value}: it runs only under an Assignment (ASSIGNMENT_EXECUTION)")
    if selection.tied and not any(k in DECISION_OWNED_KINDS for k in spec.output_kinds):
        raise AssignmentRequired(
            f"{spec.id} tied with another method: tied selections both run as assignments so the disagreement is visible")
    if ctx.actor != Actor.METHOD:
        raise AssignmentRequired(f"a direct run is the METHOD's own; {ctx.actor.value} runs under an Assignment")
    result = methods.get(selection.method_id).run(ctx)
    # `ctx.settings` carries every BOUNDS name when the loop built it, and a
    # caller may hand a method a narrower mapping; a bounds lookup must never
    # be the reason a run is refused, so a mapping that does not carry the
    # ceilings falls back to the operator's live ones (`resolve_bounds(None)`).
    bounds = ctx.settings if all(n in ctx.settings for n in ("MAX_FANOUT", "MAX_ANALYSIS_ROUNDS")) else None
    funded = default_budget(spec, bounds).max_deltas
    if len(result.deltas) > funded:
        raise BudgetExceeded("deltas", len(result.deltas), funded)
    return result


__all__ = [
    "AssignmentRequired", "BudgetExceeded", "BudgetedProvider", "RunOutcome",
    "admission_violations", "declared_validators", "run", "run_free",
]
