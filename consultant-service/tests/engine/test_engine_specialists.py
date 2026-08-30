"""C13 specialists: the assignment, the scoped window, the budget and the six
admission rules.

Every test names the law it pins. The mutations the work breakdown requires
are noted at the test that catches them: delete each of S1-S6 (six), make
rejection per-delta instead of all-or-nothing, and let the runner CONFIRM what
a specialist wrote.

The methods here are scripted stand-ins registered in a private
MethodRegistry, never in METHODS: what a specialist may do must be provable
without any builtin method existing, and a test that registered into the
global registry would leak into every other engine test file.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from app.engine import types as T
from app.engine.methods.contract import (
    EvidenceRequirement,
    InputSpec,
    InputState,
    MethodRegistry,
    MethodResult,
    MethodSpec,
    QuestionShape,
    Selection,
    new_entity,
)
from app.engine.specialists import (
    ADMISSION_RULES,
    Assignment,
    AssignmentRequired,
    BudgetExceeded,
    BudgetedProvider,
    run,
    run_free,
)
from app.engine.specialists.assignment import default_budget

from conftest import sample_payload

K = T.Kind
Add, Supersede, SetStatus = T.Add, T.Supersede, T.SetStatus

TURN_TEXT = "we have 40 people"


# ---------------------------------------------------------------------------
# a small engagement: two facts on one turn, a central and a subordinate
# decision, a confirmed objective and the issue node the specialist answers
# ---------------------------------------------------------------------------

def _entity(kind, payload, *, actor=T.Actor.PARTNER, actor_ref=None, derived=("EVI-1",),
            status=T.Status.PROPOSED, eid=""):
    return T.make_entity(
        kind=kind, engagement_id="E-1", payload=payload,
        provenance=T.Provenance(actor=actor, actor_ref=actor_ref or f"{actor.value}:1",
                                derived_from=derived, source_locator=TURN_TEXT),
        confidence=T.Confidence(None), relevance=T.Relevance(None, 0.0),
        relation=T.RelationToCentralDecision.INFORMS, status=status, entity_id=eid)


@pytest.fixture
def world(registry):
    reg = registry()
    reg.apply(Add(_entity(K.EVIDENCE_SOURCE, sample_payload(K.EVIDENCE_SOURCE), derived=(), eid="EVI-1")))
    reg.apply(Add(_entity(K.FACT, sample_payload(K.FACT), eid="FCT-1")))
    reg.apply(Add(_entity(K.FACT, replace(sample_payload(K.FACT), quantity=None, measure_id=None), eid="FCT-2")))
    reg.apply(Add(_entity(K.DECISION, sample_payload(K.DECISION), eid="DEC-1")))
    reg.apply(Add(_entity(K.DECISION, replace(sample_payload(K.DECISION), role=T.DecisionRole.SUBORDINATE),
                          eid="DEC-2")))
    reg.apply(Add(_entity(K.OBJECTIVE, sample_payload(K.OBJECTIVE), actor=T.Actor.CLIENT,
                          status=T.Status.CONFIRMED, eid="OBJ-1")))
    reg.apply(Add(_entity(K.ISSUE, replace(sample_payload(K.ISSUE), decisive_for=("DEC-2",)), eid="ISS-1")))
    return reg


def make_methods(run_fn, *, method_id="scripted", execution=T.ExecutionType.MODEL_ASSISTED,
                 output_kinds=(K.HYPOTHESIS,), max_model_calls=1, validators=()):
    """A scripted method in its own registry. `run_fn(ctx) -> MethodResult`."""
    spec = MethodSpec(
        id=method_id, version=1,
        applicability=(QuestionShape(T.Interrogative.HOW_MUCH, K.COST, quantified=True),),
        answers=(T.Interrogative.HOW_MUCH,),
        required_inputs=(InputSpec("facts", K.FACT),), optional_inputs=(),
        execution=execution, output_kinds=output_kinds, output_schema=None,
        evidence=EvidenceRequirement(), limitations=(), validators=validators,
        cost_class=1, max_model_calls=max_model_calls)

    class _Scripted:
        pass

    _Scripted.spec = spec
    _Scripted.run = lambda self, ctx: run_fn(ctx)
    registry = MethodRegistry()
    registry.register(_Scripted())
    return registry


def assign(methods, reg, *, method_id="scripted", budget=None):
    selection = Selection("ISS-1", method_id, InputState((), ()), rank_key=())
    return Assignment.from_selection(reg.get("ISS-1"), selection, reg, methods=methods, budget=budget)


def hypothesis(ctx, text="the cause is the handover", cites=("FCT-1",)):
    return Add(new_entity(ctx, K.HYPOTHESIS,
                          T.HypothesisPayload(text=text, issue_id="ISS-1", causes=cites),
                          derived_from=cites, relation=T.RelationToCentralDecision.INFORMS,
                          confidence=T.Confidence(None), decision_id=None, weight=0.0))


class _NullProvider:
    def complete(self, call):                        # pragma: no cover - only the budget tests call it
        raise AssertionError("this scripted method makes no model call")


class _NullCalc:
    pass


def written_kinds(reg, kind):
    return [e for e in reg.query(kind) if e.status not in T.TERMINAL_STATUSES]


# ---------------------------------------------------------------------------
# the assignment
# ---------------------------------------------------------------------------

def test_permitted_evidence_is_the_inputs_and_their_closure(world):
    """The scope is derived, never declared: what the method's own InputSpecs
    match, plus what those entities rest on."""
    methods = make_methods(lambda ctx: MethodResult())
    a = assign(methods, world)
    assert a.permitted_evidence == ("EVI-1", "FCT-1", "FCT-2")   # EVI-1 only via the closure
    assert a.issue_id == "ISS-1" and a.method_id == "scripted"


def test_forbidden_decisions_are_every_live_decision_but_the_subordinate_one(world):
    """A specialist answers its node. The central decision is never its to
    take; the subordinate decision the node is decisive_for is."""
    methods = make_methods(lambda ctx: MethodResult())
    a = assign(methods, world)
    assert a.forbidden_decisions == ("DEC-1",)


def test_budget_is_derived_from_the_method_and_the_bounds(world):
    """Dynamic, not hardcoded: model calls are what the method declared, and
    the delta ceiling moves with ENGINE_MAX_FANOUT / MAX_ANALYSIS_ROUNDS."""
    methods = make_methods(lambda ctx: MethodResult(), max_model_calls=2,
                           output_kinds=(K.HYPOTHESIS, K.QUESTION))
    spec = methods.get("scripted").spec
    bounds = {"MAX_FANOUT": 5, "MAX_ANALYSIS_ROUNDS": 3}
    b = default_budget(spec, bounds)
    assert b.max_model_calls == 2
    assert b.max_deltas == 5 * 3 * 2
    free = make_methods(lambda ctx: MethodResult(), execution=T.ExecutionType.DETERMINISTIC, max_model_calls=0)
    assert default_budget(free.get("scripted").spec, bounds).max_model_calls == 0


def test_assignment_row_records_the_scope_it_was_issued_under(world):
    """The assignment is on the record before the method runs: what a
    specialist was allowed to do survives whatever the run then does."""
    methods = make_methods(lambda ctx: MethodResult(deltas=(hypothesis(ctx),)))
    outcome = run(assign(methods, world), world, _NullProvider(), _NullCalc(), methods=methods)
    row = world.get(outcome.assignment_id)
    assert row.kind is K.SPECIALIST_ASSIGNMENT
    assert row.payload.permitted_evidence == ("EVI-1", "FCT-1", "FCT-2")
    assert row.payload.outcome == "done" and row.payload.rejection_rule is None


# ---------------------------------------------------------------------------
# the window
# ---------------------------------------------------------------------------

def test_specialist_reading_outside_permitted_evidence_gets_nothing(world):
    """ScopedView is the scope: a specialist cannot read what it was not
    given, which is why it cannot cite it either (S5)."""
    seen = {}

    def script(ctx):
        seen["decisions"] = ctx.registry.query(K.DECISION)
        seen["issue"] = ctx.registry.get("ISS-1")
        seen["facts"] = [f.id for f in ctx.registry.query(K.FACT)]
        seen["objective"] = ctx.registry.get("OBJ-1")
        seen["central"] = ctx.registry.central_decision()
        return MethodResult(deltas=(hypothesis(ctx),))

    methods = make_methods(script)
    run(assign(methods, world), world, _NullProvider(), _NullCalc(), methods=methods)
    assert seen["decisions"] == [] and seen["issue"] is None and seen["central"] is None
    assert seen["facts"] == ["FCT-1", "FCT-2"]
    # The confirmed client preference is in the window whatever the assignment
    # listed: objectives are the frame every analysis works inside.
    assert seen["objective"] is not None and seen["objective"].id == "OBJ-1"


# ---------------------------------------------------------------------------
# the clean negative control
# ---------------------------------------------------------------------------

def test_a_clean_result_is_admitted_unchanged_and_stays_proposed(world):
    """Mutation partner for "let the runner CONFIRM outputs": a specialist's
    conclusion is a proposal to the engagement, never a settled fact."""
    methods = make_methods(lambda ctx: MethodResult(deltas=(hypothesis(ctx),)))
    outcome = run(assign(methods, world), world, _NullProvider(), _NullCalc(), methods=methods)
    assert outcome.outcome == "done" and outcome.rejection_rule is None
    assert [e.kind for e in outcome.written] == [K.HYPOTHESIS]
    row = outcome.written[0]
    assert row.status is T.Status.PROPOSED
    assert row.provenance.actor is T.Actor.SPECIALIST
    assert row.provenance.actor_ref == f"specialist:{outcome.assignment_id}"
    assert row.payload.text == "the cause is the handover"           # admitted unchanged
    analysis = world.get(outcome.analysis_id)
    assert analysis.payload.state is T.AnalysisState.DONE and analysis.payload.outputs == (row.id,)


def test_questions_a_specialist_raises_are_written_not_dropped(world):
    """A typed hole the runner dropped is the one thing absence of evidence
    must never become."""
    question = T.QuestionPayload(text="pin the period basis on FCT-1", asks_for=(T.AsksFor(K.FACT),),
                                 issue_ids=("ISS-1",), why="the total needs it",
                                 effort=T.EffortClass.OFFHAND, strategy=T.FillStrategy.ASK_CLIENT)
    methods = make_methods(lambda ctx: MethodResult(deltas=(hypothesis(ctx),), questions=(question,)))
    outcome = run(assign(methods, world), world, _NullProvider(), _NullCalc(), methods=methods)
    asked = [q for q in outcome.written if q.kind is K.QUESTION]
    assert len(asked) == 1 and asked[0].status is T.Status.OPEN


# ---------------------------------------------------------------------------
# S1 - S6, one test each. Deleting the rule its name carries makes it fail.
# ---------------------------------------------------------------------------

def _rejected(world, run_fn, rule, *, output_kinds=(K.HYPOTHESIS,)):
    methods = make_methods(run_fn, output_kinds=output_kinds)
    outcome = run(assign(methods, world), world, _NullProvider(), _NullCalc(), methods=methods)
    assert outcome.outcome == "rejected", f"expected {rule} to refuse the result"
    assert outcome.rejection_rule == rule
    assert outcome.written == ()
    assert any(f.law == f"SPE.admission.{rule}" for f in outcome.findings)
    assert world.get(outcome.assignment_id).payload.rejection_rule == rule
    return outcome


def test_s1_a_specialist_may_not_restatus_what_it_did_not_create(world):
    """S1. Confirming a client fact for itself is how a specialist would
    manufacture the support its own conclusion needs."""
    def script(ctx):
        return MethodResult(deltas=(SetStatus("FCT-1", T.Status.CONFIRMED,
                                              T.Provenance(actor=T.Actor.SPECIALIST, actor_ref=ctx.actor_ref)),))

    _rejected(world, script, "S1")
    assert world.get("FCT-1").status is T.Status.PROPOSED


def test_s1_covers_superseding_someone_elses_row(world):
    """The same rule, the other delta: a supersession of a row this assignment
    did not write is still one role editing another's record."""
    def script(ctx):
        old = ctx.registry.get("FCT-1")
        new = replace(old, payload=replace(old.payload, statement=TURN_TEXT, topic="rewritten"),
                      provenance=replace(old.provenance, actor=T.Actor.SPECIALIST, actor_ref=ctx.actor_ref))
        return MethodResult(deltas=(Supersede("FCT-1", new),))

    _rejected(world, script, "S1")


def test_s2_every_add_is_proposed(world):
    """S2. Also the mutation partner for "let the runner CONFIRM outputs":
    with S2 gone the CONFIRMED row is admitted."""
    def script(ctx):
        good = hypothesis(ctx)
        return MethodResult(deltas=(Add(replace(good.entity, status=T.Status.CONFIRMED)),))

    _rejected(world, script, "S2")


def test_s2_admits_the_calculators_own_confirmed_arithmetic(world):
    """The one exception, and why it is not a hole: arithmetic is owned by the
    deterministic engine, the calculator is its only confirmer, and L7
    recomputes it exactly at the gate."""
    def script(ctx):
        payload = T.FactPayload(statement="FCT-1 * 2", basis=T.FactBasis.CALCULATED, measure_id=None,
                                quantity=T.Quantity(Decimal("80"), "heads", T.UnitFamily.COUNT),
                                formula="FCT-1 * 2", inputs=("FCT-1",))
        entity = T.make_entity(
            kind=K.FACT, engagement_id="E-1", payload=payload,
            provenance=T.Provenance(actor=T.Actor.CALCULATOR, actor_ref="calc:scripted", derived_from=("FCT-1",)),
            confidence=T.Confidence(1.0, "computed"), relevance=T.Relevance(None, 0.0),
            relation=T.RelationToCentralDecision.INFORMS, status=T.Status.CONFIRMED)
        return MethodResult(deltas=(Add(entity),))

    methods = make_methods(script, output_kinds=(K.FACT,))
    outcome = run(assign(methods, world), world, _NullProvider(), _NullCalc(), methods=methods)
    assert outcome.outcome == "done"
    assert outcome.written[0].status is T.Status.CONFIRMED


def test_s3_a_specialist_is_never_a_source(world):
    """S3. Client recollections and document records enter through ingestion,
    where the verbatim and the hash are checked."""
    def script(ctx):
        payload = T.FactPayload(statement="the warehouse ships nightly",
                                basis=T.FactBasis.DOCUMENT_EXTRACTED, measure_id=None, quantity=None)
        return MethodResult(deltas=(Add(new_entity(
            ctx, K.FACT, payload, derived_from=("FCT-1",), relation=T.RelationToCentralDecision.INFORMS,
            confidence=T.Confidence(None), decision_id=None, weight=0.0)),))

    _rejected(world, script, "S3", output_kinds=(K.FACT,))


def test_s4_no_conclusion_on_a_forbidden_decision(world):
    """S4. The engagement's central decision is not a specialist's to settle."""
    def script(ctx):
        payload = T.RecommendationPayload(statement="buy", decision_id="DEC-1", supports=("FCT-1",))
        return MethodResult(deltas=(Add(new_entity(
            ctx, K.RECOMMENDATION, payload, derived_from=("FCT-1",),
            relation=T.RelationToCentralDecision.RESOLVES, confidence=T.Confidence(None),
            decision_id="DEC-1", weight=0.5)),))

    _rejected(world, script, "S4", output_kinds=(K.RECOMMENDATION,))


def test_s4_admits_the_subordinate_decision_the_node_was_built_to_settle(world):
    """The negative control: answering its own node is exactly the job."""
    def script(ctx):
        payload = T.RecommendationPayload(statement="buy", decision_id="DEC-2", supports=("FCT-1",))
        return MethodResult(deltas=(Add(new_entity(
            ctx, K.RECOMMENDATION, payload, derived_from=("FCT-1",),
            relation=T.RelationToCentralDecision.RESOLVES, confidence=T.Confidence(None),
            decision_id="DEC-2", weight=0.5)),))

    methods = make_methods(script, output_kinds=(K.RECOMMENDATION,))
    outcome = run(assign(methods, world), world, _NullProvider(), _NullCalc(), methods=methods)
    assert outcome.outcome == "done"


def test_s4_no_option_for_a_decision_the_node_does_not_target(world):
    def script(ctx):
        payload = T.OptionPayload(text="keep the current supplier", decision_id="DEC-1", evidence=("FCT-1",))
        return MethodResult(deltas=(Add(new_entity(
            ctx, K.OPTION, payload, derived_from=("FCT-1",), relation=T.RelationToCentralDecision.INFORMS,
            confidence=T.Confidence(None), decision_id="DEC-1", weight=0.5)),))

    _rejected(world, script, "S4", output_kinds=(K.OPTION,))


def test_s5_a_citation_outside_the_window_is_a_fiction(world):
    """S5. ScopedView returned nothing for DEC-1, so a conclusion resting on
    it rests on something the specialist never read."""
    def script(ctx):
        return MethodResult(deltas=(hypothesis(ctx, cites=("DEC-1",)),))

    _rejected(world, script, "S5")


def test_s5_an_assumption_needs_a_grant(world):
    """S5. A method that never declared it writes assumptions cannot reach for
    one: the grant is derived from the method's own output kinds."""
    def script(ctx):
        payload = T.AssumptionPayload(statement="volumes grow 10%", rationale="", quantity=None,
                                      approval=T.ApprovalState.UNAPPROVED)
        return MethodResult(deltas=(Add(new_entity(
            ctx, K.ASSUMPTION, payload, derived_from=("FCT-1",), relation=T.RelationToCentralDecision.INFORMS,
            confidence=T.Confidence(None), decision_id=None, weight=0.0)),))

    _rejected(world, script, "S5", output_kinds=(K.HYPOTHESIS,))
    # Declared as an output kind, the same assumption is admitted -- and stays
    # visibly unapproved until the client approves it.
    methods = make_methods(script, output_kinds=(K.ASSUMPTION,))
    outcome = run(assign(methods, world), world, _NullProvider(), _NullCalc(), methods=methods)
    assert outcome.outcome == "done"
    assert outcome.written[0].payload.approval is T.ApprovalState.UNAPPROVED


def test_s5_a_specialist_may_not_approve_its_own_assumption(world):
    def script(ctx):
        payload = T.AssumptionPayload(statement="volumes grow 10%", rationale="", quantity=None,
                                      approval=T.ApprovalState.APPROVED)
        return MethodResult(deltas=(Add(new_entity(
            ctx, K.ASSUMPTION, payload, derived_from=("FCT-1",), relation=T.RelationToCentralDecision.INFORMS,
            confidence=T.Confidence(None), decision_id=None, weight=0.0)),))

    _rejected(world, script, "S5", output_kinds=(K.ASSUMPTION,))


def test_s6_a_coined_quantity_is_refused(world):
    """S6. A number that is neither arithmetic nor a copy is a number with no
    lineage -- exactly what L7's exact recompute exists to catch."""
    def script(ctx):
        payload = T.CostPayload(text="the migration", basis="estimate",
                                quantity=T.Quantity(Decimal("99000"), "EUR", T.UnitFamily.MONEY),
                                for_ids=("FCT-1",))
        return MethodResult(deltas=(Add(new_entity(
            ctx, K.COST, payload, derived_from=("FCT-1",), relation=T.RelationToCentralDecision.INFORMS,
            confidence=T.Confidence(None), decision_id=None, weight=0.0)),))

    _rejected(world, script, "S6", output_kinds=(K.COST,))


def test_s6_admits_a_quantity_copied_from_the_entity_it_cites(world):
    """The negative control: the same number, in the same unit, with the same
    dimensions pinned the same way, from an entity in the window."""
    def script(ctx):
        source = ctx.registry.get("FCT-1")
        payload = T.CostPayload(text="headcount carried forward", basis="client_fact",
                                quantity=source.payload.quantity, for_ids=("FCT-1",))
        return MethodResult(deltas=(Add(new_entity(
            ctx, K.COST, payload, derived_from=("FCT-1",), relation=T.RelationToCentralDecision.INFORMS,
            confidence=T.Confidence(None), decision_id=None, weight=0.0)),))

    methods = make_methods(script, output_kinds=(K.COST,))
    outcome = run(assign(methods, world), world, _NullProvider(), _NullCalc(), methods=methods)
    assert outcome.outcome == "done"


def test_admission_rules_table_covers_every_rule_the_runner_states():
    assert sorted(ADMISSION_RULES) == ["S1", "S2", "S3", "S4", "S5", "S6"]


# ---------------------------------------------------------------------------
# all-or-nothing
# ---------------------------------------------------------------------------

def test_one_bad_delta_among_good_ones_writes_nothing(world):
    """Mutation partner for "make rejection per-delta". A result is one
    argument: if one delta reached outside the assignment, the reasoning that
    produced the rest reached outside too."""
    def script(ctx):
        bad = T.FactPayload(statement=TURN_TEXT, basis=T.FactBasis.CLIENT_STATED, measure_id=None, quantity=None)
        return MethodResult(deltas=(
            hypothesis(ctx, text="first cause"),
            Add(new_entity(ctx, K.FACT, bad, derived_from=("FCT-1",),
                           relation=T.RelationToCentralDecision.INFORMS, confidence=T.Confidence(None),
                           decision_id=None, weight=0.0)),
            hypothesis(ctx, text="second cause"),
        ))

    outcome = _rejected(world, script, "S3", output_kinds=(K.HYPOTHESIS, K.FACT))
    assert written_kinds(world, K.HYPOTHESIS) == []
    assert [f.id for f in written_kinds(world, K.FACT)] == ["FCT-1", "FCT-2"]
    assert outcome.written == ()


def test_two_specialists_disagreeing_leave_two_proposed_entities(world):
    """The runner never reconciles: a merge here would be the one place a
    disagreement could disappear silently. Synthesis makes the CONFLICT."""
    def first(ctx):
        return MethodResult(deltas=(hypothesis(ctx, text="the handover is the cause"),))

    def second(ctx):
        return MethodResult(deltas=(hypothesis(ctx, text="the forecast is the cause"),))

    a = make_methods(first, method_id="first")
    b = make_methods(second, method_id="second")
    out_a = run(assign(a, world, method_id="first"), world, _NullProvider(), _NullCalc(), methods=a)
    out_b = run(assign(b, world, method_id="second"), world, _NullProvider(), _NullCalc(), methods=b)
    assert out_a.outcome == "done" and out_b.outcome == "done"
    live = written_kinds(world, K.HYPOTHESIS)
    assert len(live) == 2
    assert {h.payload.text for h in live} == {"the handover is the cause", "the forecast is the cause"}
    assert {h.status for h in live} == {T.Status.PROPOSED}
    assert out_a.assignment_id != out_b.assignment_id


# ---------------------------------------------------------------------------
# the budget
# ---------------------------------------------------------------------------

def test_budget_exhaustion_blocks_the_assignment_rather_than_truncating(world):
    """Half an analysis presented as a whole one is the failure this refuses.
    The first call's output is discarded with everything else."""
    from app.engine.llm import FakeProvider, ModelCall

    def script(ctx):
        deltas = []
        for n in range(2):
            ctx.provider.complete(ModelCall(purpose="scripted", messages=({"role": "user", "content": "x"},)))
            deltas.append(hypothesis(ctx, text=f"cause {n}"))
        return MethodResult(deltas=tuple(deltas))

    methods = make_methods(script, max_model_calls=2)
    a = assign(methods, world, budget=T.Budget(max_model_calls=1, max_tokens=8000, max_deltas=36))
    outcome = run(a, world, FakeProvider(), _NullCalc(), methods=methods)
    assert outcome.outcome == "blocked" and outcome.written == ()
    assert written_kinds(world, K.HYPOTHESIS) == []
    assert outcome.findings[0].law == "SPE.budget.exhausted"
    assert world.get(outcome.assignment_id).payload.outcome == "blocked"
    assert world.get(outcome.analysis_id).payload.state is T.AnalysisState.BLOCKED


def test_a_result_larger_than_the_budget_is_blocked_whole(world):
    def script(ctx):
        return MethodResult(deltas=(hypothesis(ctx, text="one"), hypothesis(ctx, text="two")))

    methods = make_methods(script)
    a = assign(methods, world, budget=T.Budget(max_model_calls=1, max_tokens=4000, max_deltas=1))
    outcome = run(a, world, _NullProvider(), _NullCalc(), methods=methods)
    assert outcome.outcome == "blocked" and outcome.written == ()
    assert written_kinds(world, K.HYPOTHESIS) == []


def test_budgeted_provider_refuses_the_call_before_it_is_made():
    from app.engine.llm import FakeProvider, ModelCall

    inner = FakeProvider()
    p = BudgetedProvider(inner, T.Budget(max_model_calls=1, max_tokens=8000, max_deltas=4), method_id="scripted")
    call = ModelCall(purpose="scripted", messages=({"role": "user", "content": "x"},))
    p.complete(call)
    with pytest.raises(BudgetExceeded):
        p.complete(call)
    assert len(inner.calls) == 1                     # the refused call never reached the provider
    assert p.purpose == "engine:specialist:scripted"


def test_token_ceiling_is_enforced_on_the_reservation():
    from app.engine.llm import FakeProvider, ModelCall

    p = BudgetedProvider(FakeProvider(), T.Budget(max_model_calls=4, max_tokens=100, max_deltas=4),
                         method_id="scripted")
    with pytest.raises(BudgetExceeded):
        p.complete(ModelCall(purpose="scripted", messages=({"role": "user", "content": "x"},), max_tokens=200))


# ---------------------------------------------------------------------------
# the direct-execution door (MF1.2)
# ---------------------------------------------------------------------------

def _ctx(reg, actor=T.Actor.METHOD):
    from app.engine.methods.contract import MethodContext

    return MethodContext(registry=reg, provider=_NullProvider(), calc=_NullCalc(), actor=actor,
                         actor_ref="method:scripted", issue_ids=("ISS-1",))


def test_a_research_method_run_directly_is_refused(world):
    """MF1.2 made mechanical: there is no code path that runs a RESEARCH or
    MODEL_ASSISTED method without an Assignment."""
    for execution in (T.ExecutionType.RESEARCH, T.ExecutionType.MODEL_ASSISTED):
        methods = make_methods(lambda ctx: MethodResult(), execution=execution, max_model_calls=1)
        with pytest.raises(AssignmentRequired):
            run_free(Selection("ISS-1", "scripted", InputState((), ()), rank_key=()), _ctx(world), methods=methods)


def test_a_tied_selection_is_refused_even_when_free(world):
    """Two methods that ranked equal both run as assignments, so their
    disagreement surfaces as a CONFLICT instead of one being preferred."""
    methods = make_methods(lambda ctx: MethodResult(), execution=T.ExecutionType.DETERMINISTIC, max_model_calls=0)
    selection = Selection("ISS-1", "scripted", InputState((), ()), rank_key=(), tied=True)
    with pytest.raises(AssignmentRequired):
        run_free(selection, _ctx(world), methods=methods)


def test_a_free_untied_method_runs_through_the_direct_door(world):
    """The negative control, and the reason the door exists at all."""
    methods = make_methods(lambda ctx: MethodResult(findings=(T.Finding("M.ok", "x", "y", "z"),)),
                           execution=T.ExecutionType.DETERMINISTIC, max_model_calls=0)
    result = run_free(Selection("ISS-1", "scripted", InputState((), ()), rank_key=()), _ctx(world), methods=methods)
    assert result.findings[0].law == "M.ok"


def test_the_direct_door_refuses_a_specialist_context(world):
    methods = make_methods(lambda ctx: MethodResult(), execution=T.ExecutionType.DETERMINISTIC, max_model_calls=0)
    with pytest.raises(AssignmentRequired):
        run_free(Selection("ISS-1", "scripted", InputState((), ()), rank_key=()),
                 _ctx(world, actor=T.Actor.SPECIALIST), methods=methods)


# ---------------------------------------------------------------------------
# validators
# ---------------------------------------------------------------------------

def _calc_fact(*, status=T.Status.PROPOSED, ref="calc:scripted", formula="FCT-1 * 2",
               inputs=("FCT-1",), quantity=T.Quantity(Decimal("80"), "heads", T.UnitFamily.COUNT)):
    """The row the deterministic calculator writes when a method's arithmetic
    runs inside an assignment: the formula over entity ids, the input ids, and
    the CALCULATOR's own signature -- arithmetic is never signed by the
    analyst who asked for it."""
    payload = T.FactPayload(statement="FCT-1 * 2", basis=T.FactBasis.CALCULATED, measure_id=None,
                            quantity=quantity, formula=formula, inputs=inputs)
    return T.make_entity(
        kind=K.FACT, engagement_id="E-1", payload=payload,
        provenance=T.Provenance(actor=T.Actor.CALCULATOR, actor_ref=ref, derived_from=inputs),
        confidence=T.Confidence(1.0, "computed"), relevance=T.Relevance(None, 0.0),
        relation=T.RelationToCentralDecision.INFORMS, status=status)


def test_validator_findings_attach_to_the_analysis_without_deleting_rows(world):
    """A flawed conclusion stays visible with its flaw named: findings are a
    record, not a delete."""
    def validator(view, result):
        return [T.Finding(law="M.scripted.thin", where="HYP", issue="one cause only",
                          fix="cite a second fact", severity=T.Severity.LOW, blocks_final=False)]

    methods = make_methods(lambda ctx: MethodResult(deltas=(hypothesis(ctx),)), validators=(validator,))
    outcome = run(assign(methods, world), world, _NullProvider(), _NullCalc(), methods=methods)
    assert outcome.outcome == "done" and len(outcome.written) == 1
    finding = [f for f in outcome.findings if f.law == "M.scripted.thin"][0]
    assert outcome.analysis_id in finding.entity_ids



def test_the_runner_runs_the_laws_the_method_declared_not_only_the_ones_it_was_handed(world):
    """A declared validator that nothing calls is a comment. The runner runs
    the union of the Assignment's validators and the MethodSpec's own, so a
    method's laws bite on every run of it however the Assignment reached the
    runner -- rebuilt from a persisted row, or assembled by a caller that
    filled the fields itself.

    Mutation: run() reading only assignment.validation -> this fails.
    """
    def validator(view, result):
        return [T.Finding(law="M.scripted.declared", where="HYP", issue="the method's own law",
                          fix="cite a second fact", severity=T.Severity.LOW, blocks_final=False)]

    methods = make_methods(lambda ctx: MethodResult(deltas=(hypothesis(ctx),)), validators=(validator,))
    handed_none = replace(assign(methods, world), validation=())
    outcome = run(handed_none, world, _NullProvider(), _NullCalc(), methods=methods)
    assert outcome.outcome == "done"
    finding = [f for f in outcome.findings if f.law == "M.scripted.declared"][0]
    assert outcome.analysis_id in finding.entity_ids


def test_a_declared_validator_is_called_once_with_the_scoped_view_and_the_result(world):
    """v(view, result): the window it judges against is the window the
    specialist worked in, so a validator cannot check the conclusion against
    evidence the specialist was never allowed to read. Once, not twice: the
    Assignment carries the same objects the spec declared."""
    seen = []

    def validator(view, result):
        seen.append((view.get("FCT-1"), view.get("DEC-1"), result))
        return []

    methods = make_methods(lambda ctx: MethodResult(deltas=(hypothesis(ctx),)), validators=(validator,))
    a = assign(methods, world)
    assert a.validation == (validator,)                  # from_selection copies the spec's laws
    outcome = run(a, world, _NullProvider(), _NullCalc(), methods=methods)
    assert outcome.outcome == "done"
    assert len(seen) == 1
    in_window, out_of_window, result = seen[0]
    assert in_window is not None and in_window.id == "FCT-1"
    assert out_of_window is None                         # DEC-1 was never in the assignment's scope
    assert [d.entity.kind for d in result.deltas] == [K.HYPOTHESIS]


def test_a_validator_that_raises_is_recorded_rather_than_crashing_a_written_run(world):
    """The rows are already written when validators run, so a raising
    validator must not leave an assignment with no recorded outcome. The law
    that did not get to run is named in a finding instead of vanishing."""
    def validator(view, result):
        raise RuntimeError("the law could not be checked")

    methods = make_methods(lambda ctx: MethodResult(deltas=(hypothesis(ctx),)), validators=(validator,))
    outcome = run(assign(methods, world), world, _NullProvider(), _NullCalc(), methods=methods)
    assert outcome.outcome == "done"
    assert any(f.law == "SPE.validator.validator" and f.severity is T.Severity.HIGH for f in outcome.findings)
    assert world.get(outcome.assignment_id).payload.outcome == "done"


# ---------------------------------------------------------------------------
# the calculator inside an assignment: a research method's own arithmetic
# ---------------------------------------------------------------------------

def test_a_calculated_fact_a_research_method_proposed_is_admitted(world):
    """A RESEARCH method may not say what a number IS: it names the registered
    ids that multiply, the Calculator computes, and the row is written
    PROPOSED under the assignment (the confirming actor recomputes the formula
    afterwards). S2 admits the calculator's row at either status, so the
    weaker one is not the reason a lawful sizing run is refused.

    Mutation: S2 requiring CONFIRMED of the calculator's row -> this fails.
    """
    methods = make_methods(lambda ctx: MethodResult(deltas=(Add(_calc_fact()),)), output_kinds=(K.FACT,))
    outcome = run(assign(methods, world), world, _NullProvider(), _NullCalc(), methods=methods)
    assert outcome.outcome == "done" and outcome.rejection_rule is None
    row = outcome.written[0]
    assert row.status is T.Status.PROPOSED                    # not confirmed by the producer
    assert row.provenance.actor is T.Actor.CALCULATOR
    assert row.payload.formula == "FCT-1 * 2" and row.payload.inputs == ("FCT-1",)


def test_a_specialists_own_row_signed_by_the_calculator_is_still_refused(world):
    """The carve-out is arithmetic, not a signature. A row that claims the
    calculator's name without the formula and the inputs that reproduce it
    would be a conclusion the deterministic engine appears to own."""
    def script(ctx):
        payload = T.HypothesisPayload(text="the cause is the handover", issue_id="ISS-1", causes=("FCT-1",))
        entity = T.make_entity(
            kind=K.HYPOTHESIS, engagement_id="E-1", payload=payload,
            provenance=T.Provenance(actor=T.Actor.CALCULATOR, actor_ref="calc:scripted",
                                    derived_from=("FCT-1",)),
            confidence=T.Confidence(None), relevance=T.Relevance(None, 0.0),
            relation=T.RelationToCentralDecision.INFORMS, status=T.Status.PROPOSED)
        return MethodResult(deltas=(Add(entity),))

    _rejected(world, script, "S2")


def test_a_fact_claiming_calculated_with_no_arithmetic_is_refused(world):
    """S3, the other side of "a specialist is never a source": basis
    calculated makes the row ARITHMETIC, owned by the deterministic engine, so
    claiming it with no formula and no inputs is a coined figure wearing the
    calculator's authority -- and nothing could recompute it."""
    def script(ctx):
        # Signed by the specialist at PROPOSED, so S2 has nothing to say: the
        # only thing wrong with this row is that it claims arithmetic without
        # any.
        payload = T.FactPayload(statement="the market is 4bn", basis=T.FactBasis.CALCULATED,
                                measure_id=None, quantity=None, formula=None, inputs=())
        return MethodResult(deltas=(Add(new_entity(
            ctx, K.FACT, payload, derived_from=("FCT-1",), relation=T.RelationToCentralDecision.INFORMS,
            confidence=T.Confidence(None), decision_id=None, weight=0.0)),))

    _rejected(world, script, "S3", output_kinds=(K.FACT,))


def test_the_assignments_own_calculated_row_is_neither_foreign_nor_uncitable(world):
    """S1 and S5 read one set: the rows this assignment wrote. Two writers
    sign them -- the specialist, and the calculator that did the assignment's
    arithmetic -- so a second run of the same assignment may cite the figure
    it produced and hand it to the actor that confirms arithmetic.

    Mutation: narrowing that set back to the specialist's actor_ref alone ->
    this fails under S1 and S5.
    """
    state = {}

    def script(ctx):
        if "calc_id" not in state:
            return MethodResult(deltas=(Add(_calc_fact()),))
        calc_id = state["calc_id"]
        return MethodResult(deltas=(
            hypothesis(ctx, text="the size explains the gap", cites=(calc_id,)),
            SetStatus(calc_id, T.Status.CONFIRMED,
                      T.Provenance(actor=T.Actor.CALCULATOR, actor_ref="calc:scripted")),
        ))

    methods = make_methods(script, output_kinds=(K.FACT, K.HYPOTHESIS))
    first = run(assign(methods, world), world, _NullProvider(), _NullCalc(), methods=methods)
    assert first.outcome == "done"
    state["calc_id"] = first.written[0].id

    again = replace(assign(methods, world), id=first.assignment_id)
    second = run(again, world, _NullProvider(), _NullCalc(), methods=methods)
    assert second.outcome == "done", second.rejection_rule
    assert second.assignment_id == first.assignment_id
    assert world.get(state["calc_id"]).status is T.Status.CONFIRMED
    assert [h.payload.text for h in written_kinds(world, K.HYPOTHESIS)] == ["the size explains the gap"]


def test_another_assignments_calculated_row_is_still_foreign(world):
    """The narrowing that keeps S1 a law: "calc:<method_id>" is the same
    string for every assignment of one method, so ownership is read from the
    ANALYSIS that recorded the output, not from the signature. Otherwise every
    assignment of a method could retire every other's arithmetic."""
    owner = make_methods(lambda ctx: MethodResult(deltas=(Add(_calc_fact()),)), output_kinds=(K.FACT,))
    first = run(assign(owner, world), world, _NullProvider(), _NullCalc(), methods=owner)
    assert first.outcome == "done"
    calc_id = first.written[0].id

    def intruder(ctx):
        return MethodResult(deltas=(SetStatus(calc_id, T.Status.CONFIRMED,
                                              T.Provenance(actor=T.Actor.CALCULATOR,
                                                           actor_ref="calc:scripted")),))

    _rejected(world, intruder, "S1", output_kinds=(K.FACT,))
    assert world.get(calc_id).status is T.Status.PROPOSED
