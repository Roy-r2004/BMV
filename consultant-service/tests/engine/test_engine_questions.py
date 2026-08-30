"""C8 questions: app/engine/partner/questions.py -- the seven typed gap
queries, the value formula and every factor in it, the batch laws (bounds, one
question per issue leaf, zero impact is never asked, a specialist gap is not a
question) and the phrase_questions agenda lock.

Pinned mutations (work breakdown C8):
- drop the division by effort        -> test_effort_divides_the_value
- drop the impact == 0 filter        -> test_zero_impact_gap_is_never_asked
- drop path_impact                   -> test_deep_leaf_scores_under_a_top_level_node
- let model-added questions through  -> test_model_added_question_is_dropped
- drop the one-per-leaf rule         -> test_at_most_one_question_per_issue_leaf
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.engine import types as T
from app.engine.methods.contract import (
    EvidenceRequirement, Gap, InputSpec, MethodRegistry, MethodResult, MethodSpec, QuestionShape,
)
from app.engine.partner import questions as Q
from app.engine.types import Actor, Add, Kind, RelationToCentralDecision, Status

K = Kind
S = Status
EID = "E-1"
DEFINES = RelationToCentralDecision.DEFINES
INFORMS = RelationToCentralDecision.INFORMS
UNRELATED = RelationToCentralDecision.UNRELATED

# The one shape the test methods declare, and the shape every test issue node
# carries: selection is a function of enums only, so one pair suffices.
SHAPE = QuestionShape(T.Interrogative.WHAT, K.FACT)


# ---------------------------------------------------------------------------
# builders: every entity through make_entity, every write through apply()
# ---------------------------------------------------------------------------

def add(reg, kind: Kind, payload, *, actor: Actor = Actor.PARTNER, status: Status = S.PROPOSED,
        relation: RelationToCentralDecision = INFORMS, relevance: T.Relevance | None = None,
        confidence: T.Confidence | None = None, derived=(), labels=()) -> T.Entity:
    return reg.apply(Add(T.make_entity(
        kind=kind, engagement_id=EID, payload=payload,
        provenance=T.Provenance(actor=actor, actor_ref=f"{actor.value}:1", derived_from=tuple(derived)),
        confidence=confidence or T.Confidence(None), relevance=relevance or T.Relevance(None),
        relation=relation, status=status, labels=tuple(labels))))


def scaffold(reg) -> T.Entity:
    """Closes the five structural gaps of an empty registry, so a test that is
    about one gap is not also about turn 1."""
    decision = add(reg, K.DECISION, T.DecisionPayload(statement="which fulfilment path",
                                                      role=T.DecisionRole.STATED_REQUEST))
    add(reg, K.OBJECTIVE, T.ObjectivePayload(text="cut the order cycle time"))
    add(reg, K.DECISION_OWNER, T.DecisionOwnerPayload(name="md", role="managing director"))
    add(reg, K.DEADLINE, T.DeadlinePayload(text="before the season"))
    add(reg, K.EVIDENCE_SOURCE, T.EvidenceSourcePayload(name="ops report",
                                                        source_kind=T.SourceKind.DOCUMENT))
    return decision


def issue(reg, decision_id: str, *, relation=DEFINES, weight: float = 1.0, parent: str | None = None,
          evidence_needed=(), text: str = "what drives the delay") -> T.Entity:
    return add(reg, K.ISSUE,
               T.IssuePayload(text=text, interrogative=SHAPE.interrogative, target_kind=SHAPE.target_kind,
                              parent_id=parent, weight_to_parent=weight, decisive_for=(decision_id,),
                              evidence_needed=tuple(evidence_needed)),
               relation=relation, relevance=T.Relevance(decision_id, 0.5))


def fact(reg, *, statement="the line runs 40 orders a day", conf: float | None = None, quantity=None,
         measure_id: str | None = None, relation=INFORMS, decision_id: str | None = None,
         derived=()) -> T.Entity:
    return add(reg, K.FACT,
               T.FactPayload(statement=statement, basis=T.FactBasis.INFERRED, measure_id=measure_id,
                             quantity=quantity),
               relation=relation, relevance=T.Relevance(decision_id, 0.4),
               confidence=T.Confidence(conf, "verified" if conf is not None else "unknown"),
               derived=derived)


def quantity(*, as_of: str | None = "2026-01-01") -> T.Quantity:
    return T.Quantity(Decimal("40"), "orders", T.UnitFamily.COUNT, T.Dimensions(as_of=as_of))


# ---------------------------------------------------------------------------
# a method registry built per test: C8 must not depend on which builtins exist
# ---------------------------------------------------------------------------

class _TestMethod:
    def __init__(self, spec: MethodSpec) -> None:
        self.spec = spec

    def run(self, ctx) -> MethodResult:      # never called here: C8 only reads specs
        return MethodResult()


def spec(method_id: str, *, inputs=(), execution=T.ExecutionType.DETERMINISTIC,
         outputs=(K.HYPOTHESIS,)) -> MethodSpec:
    return MethodSpec(id=method_id, version=1, applicability=(SHAPE,), answers=(SHAPE.interrogative,),
                      required_inputs=tuple(inputs), optional_inputs=(), execution=execution,
                      output_kinds=tuple(outputs), output_schema=None, evidence=EvidenceRequirement(),
                      limitations=(), validators=())


def methods_with(*specs: MethodSpec) -> MethodRegistry:
    registry = MethodRegistry()
    for s in specs:
        registry.register(_TestMethod(s))
    return registry


FACTS_INPUT = InputSpec("facts", K.FACT, min_count=1, effort=T.EffortClass.OFFHAND,
                        why_needed="without a registered figure there is no current state to analyse")


def one_method(**kwargs) -> MethodRegistry:
    return methods_with(spec("m_facts", inputs=(FACTS_INPUT,), **kwargs))


def sourced(inp: InputSpec, *, issue_id: str = "", decision_ids=(), relation=DEFINES,
            source: str = Q.SOURCE_METHOD_INPUT, subjects=(), gap_id: str = "GAP-under-test") -> Q.SourcedGap:
    """A gap built by hand, so one factor at a time can be moved."""
    return Q.SourcedGap(
        gap=Gap(issue_id=issue_id, method_id="m_facts", input=inp,
                strategy=T.FillStrategy.ASK_CLIENT, decision_ids=tuple(decision_ids)),
        source=source, gap_id=gap_id, subject_ids=tuple(subjects), relation=relation)


def bounds(**overrides) -> dict:
    b = dict(T.BOUNDS)
    b.update(overrides)
    return b


def by_source(scored, source: str):
    return [s for s in scored if s.sourced.source == source]


# ===========================================================================
# 1. gaps(): the seven typed sources, in every engagement
# ===========================================================================

def test_empty_registry_yields_the_structural_gaps(registry):
    """Turn 1 (design 6.5 g): no decision, objective, owner, deadline or
    record. Every one is asked of the client - a specialist spawned before
    there is anything in the registry would have nothing to work from."""
    reg = registry()
    found = Q.sourced_gaps(reg, methods=one_method())
    assert {sg.source for sg in found} == {Q.SOURCE_STRUCTURAL}
    assert {sg.gap.input.kind for sg in found} == {
        K.DECISION, K.OBJECTIVE, K.DECISION_OWNER, K.DEADLINE, K.EVIDENCE_SOURCE}
    assert all(sg.gap.strategy in Q.ASKABLE_STRATEGIES for sg in found)
    # the conversation turn the client is writing is an EVIDENCE_SOURCE too;
    # it must not be what closes the "produce a record" gap
    add(reg, K.EVIDENCE_SOURCE, T.EvidenceSourcePayload(name="turn 1",
                                                        source_kind=T.SourceKind.CONVERSATION_TURN))
    still = {sg.gap.input.kind for sg in Q.sourced_gaps(reg, methods=one_method())}
    assert K.EVIDENCE_SOURCE in still


def test_the_six_registry_gaps_are_found_by_type(registry):
    """(a)-(f) of design 6.5, found by kind, enum and count alone."""
    reg = registry()
    decision = scaffold(reg)
    iss = issue(reg, decision.id, evidence_needed=(T.AsksFor(K.RISK),))
    measure = add(reg, K.MEASURE, T.MeasurePayload(name="daily orders", unit_family=T.UnitFamily.COUNT))
    doc_a = add(reg, K.EVIDENCE_SOURCE, T.EvidenceSourcePayload(name="wms export",
                                                                source_kind=T.SourceKind.DOCUMENT))
    doc_b = add(reg, K.EVIDENCE_SOURCE, T.EvidenceSourcePayload(name="board pack",
                                                                source_kind=T.SourceKind.DOCUMENT))
    fact(reg, measure_id=measure.id, quantity=quantity(), derived=(doc_a.id,), relation=DEFINES)
    fact(reg, measure_id=measure.id, quantity=quantity(), derived=(doc_b.id,), relation=DEFINES,
         statement="the line runs 45 orders a day")
    fact(reg, quantity=quantity(as_of=None), statement="45 people work the floor", relation=DEFINES)
    add(reg, K.CONFLICT,
        T.ConflictPayload(kind=T.ConflictKind.VALUE, subject_id=measure.id,
                          conclusions=(T.ConflictConclusion("FCT-1", "40"),
                                       T.ConflictConclusion("FCT-2", "45")),
                          relation_to_central_decision=DEFINES,
                          authority_required=T.Authority.CLIENT),
        status=S.OPEN)
    add(reg, K.DECISION_REQUIRED,
        T.DecisionRequiredPayload(text="confirm the revised scope", from_authority=T.Authority.CLIENT,
                                  decision_id=decision.id),
        status=S.OPEN)

    # a method that wants more readings than the scene holds, so (a) is a gap
    # here too and all six sources stand in one registry
    hungry = methods_with(spec("m_facts", inputs=(
        InputSpec("facts", K.FACT, min_count=5, why_needed="five readings, not three"),)))
    found = Q.sourced_gaps(reg, methods=hungry)
    assert {sg.source for sg in found} == {
        Q.SOURCE_METHOD_INPUT, Q.SOURCE_EVIDENCE_NEEDED, Q.SOURCE_UNPINNED_DIMENSION,
        Q.SOURCE_RECORD_CLASS, Q.SOURCE_CLIENT_CONFLICT, Q.SOURCE_DECISION_REQUIRED}
    method_gap = [sg for sg in found if sg.source == Q.SOURCE_METHOD_INPUT][0]
    assert method_gap.gap.issue_id == iss.id and method_gap.gap.method_id == "m_facts"
    assert method_gap.gap.decision_ids == (decision.id,)
    pin = [sg for sg in found if sg.source == Q.SOURCE_UNPINNED_DIMENSION][0]
    # the label charter_ready reads structurally (hypothesis.PIN_DIMENSION_LABEL)
    assert Q.PIN_DIMENSION_LABEL in pin.labels
    assert Q.gaps(reg, methods=one_method())        # the typed contract objects themselves


def test_a_satisfied_input_is_not_a_gap(registry):
    reg = registry()
    decision = scaffold(reg)
    issue(reg, decision.id)
    assert by_source(Q.scored_gaps(reg, methods=one_method()), Q.SOURCE_METHOD_INPUT)
    fact(reg, relation=DEFINES)
    assert not by_source(Q.scored_gaps(reg, methods=one_method()), Q.SOURCE_METHOD_INPUT)


# ===========================================================================
# 2. Fill strategies: what the client is never asked for
# ===========================================================================

def test_specialist_gaps_never_become_client_questions(registry):
    """An input a RESEARCH / MODEL_ASSISTED method produces is the product of
    analysis: it becomes an assignment (design 6.7), never a question."""
    reg = registry()
    decision = scaffold(reg)
    issue(reg, decision.id)
    capability_input = InputSpec("capabilities", K.CAPABILITY, min_count=1,
                                 why_needed="the analysis needs the capability picture")
    methods = methods_with(
        spec("m_needs_capability", inputs=(capability_input,)),
        spec("m_makes_capability", execution=T.ExecutionType.MODEL_ASSISTED, outputs=(K.CAPABILITY,)))
    scored = Q.scored_gaps(reg, methods=methods)
    spawn = [s for s in scored if s.gap.input.kind is K.CAPABILITY]
    assert spawn and all(s.gap.strategy is T.FillStrategy.SPAWN_SPECIALIST for s in spawn)
    assert not [s for s in Q.select_questions(scored) if s.gap.input.kind is K.CAPABILITY]
    from app.engine.llm import FakeProvider
    batch = Q.ask(reg, FakeProvider(), turn_number=1, methods=methods)
    assert all(q.payload.asks_for[0].kind is not K.CAPABILITY for q in batch.questions)


def test_a_client_preference_is_never_spawned(registry):
    """No analysis produces the client's objectives: even with a registered
    model-assisted producer, the gap stays the client's to answer."""
    methods = methods_with(spec("m_makes_objectives", execution=T.ExecutionType.MODEL_ASSISTED,
                                outputs=(K.OBJECTIVE,)))
    objective_input = InputSpec("objectives", K.OBJECTIVE, why_needed="what makes one answer better")
    assert Q.gap_strategy(objective_input, methods) is T.FillStrategy.ASK_CLIENT
    # and the same input for a kind analysis does produce is an assignment
    hypothesis_input = InputSpec("hypotheses", K.HYPOTHESIS, why_needed="what we think is going on")
    spawning = methods_with(spec("m_makes_hypotheses", execution=T.ExecutionType.RESEARCH,
                                 outputs=(K.HYPOTHESIS,)))
    assert Q.gap_strategy(hypothesis_input, spawning) is T.FillStrategy.SPAWN_SPECIALIST


def test_dont_know_is_never_re_asked(registry):
    """RECORD_UNKNOWN: the gap survives as a labelled unknown, but it leaves
    the agenda for good."""
    reg = registry()
    decision = scaffold(reg)
    issue(reg, decision.id)
    methods = one_method()
    gap_id = by_source(Q.scored_gaps(reg, methods=methods), Q.SOURCE_METHOD_INPUT)[0].gap_id
    add(reg, K.QUESTION,
        T.QuestionPayload(text="how many orders a day?", unknown=True, strategy=T.FillStrategy.ASK_CLIENT),
        actor=Actor.CLIENT, status=S.RESOLVED, labels=(Q.GAP_LABEL_PREFIX + gap_id,))
    again = by_source(Q.scored_gaps(reg, methods=methods), Q.SOURCE_METHOD_INPUT)[0]
    assert again.gap.strategy is T.FillStrategy.RECORD_UNKNOWN
    assert again.gap_id not in {s.gap_id for s in Q.select_questions(Q.scored_gaps(reg, methods=methods))}


# ===========================================================================
# 3. The value formula: every factor moves it, on its own
# ===========================================================================

def test_impact_rises_with_sensitivity(registry):
    """SENSITIVITY prices the relation the gap's subject bears to the central
    decision: a DEFINES issue outranks one that merely INFORMS."""
    reg = registry()
    decision = scaffold(reg)
    strong = sourced(FACTS_INPUT, decision_ids=(decision.id,), relation=DEFINES)
    weak = sourced(FACTS_INPUT, decision_ids=(decision.id,), relation=INFORMS)
    methods = one_method()
    assert (Q.score_gap(reg, strong, methods=methods).value
            > Q.score_gap(reg, weak, methods=methods).value)


def test_deep_leaf_scores_under_a_top_level_node(registry):
    """path_impact: the answer only reaches the decision through every edge
    above it, so a leaf under a light branch is worth its whole path."""
    reg = registry()
    decision = scaffold(reg)
    top = issue(reg, decision.id, weight=1.0, text="what drives the delay")
    issue(reg, decision.id, parent=top.id, weight=0.2, text="how long is the picking step")
    scored = {s.gap.issue_id: s for s in by_source(Q.scored_gaps(reg, methods=one_method()),
                                                   Q.SOURCE_METHOD_INPUT)}
    leaf_id = [i for i in scored if i != top.id][0]
    assert scored[leaf_id].value < scored[top.id].value
    assert scored[leaf_id].value == pytest.approx(0.2 * scored[top.id].value)


def test_uncertainty_falls_as_the_registry_answers(registry):
    """1 - the best confidence already standing behind an answer: a gap the
    registry half holds is worth less than an empty one."""
    reg = registry()
    decision = scaffold(reg)
    issue(reg, decision.id)
    two_facts = InputSpec("facts", K.FACT, min_count=2, why_needed="two readings, not one")
    methods = methods_with(spec("m_two_facts", inputs=(two_facts,)))
    before = by_source(Q.scored_gaps(reg, methods=methods), Q.SOURCE_METHOD_INPUT)[0]
    assert before.uncertainty == 1.0
    fact(reg, conf=0.95, relation=DEFINES)
    after = by_source(Q.scored_gaps(reg, methods=methods), Q.SOURCE_METHOD_INPUT)[0]
    assert after.uncertainty == pytest.approx(0.05)
    assert after.value < before.value


def test_downstream_rises_with_fan_out(registry):
    """An answer several waiting analyses need is worth more than one that
    unblocks nothing - bounded by MAX_FANOUT, so it never outweighs impact."""
    reg = registry()
    decision = scaffold(reg)
    issue(reg, decision.id)
    gap = sourced(FACTS_INPUT, decision_ids=(decision.id,))
    alone = Q.score_gap(reg, gap, methods=one_method())
    crowded = Q.score_gap(reg, gap, methods=methods_with(
        spec("m_a", inputs=(FACTS_INPUT,)), spec("m_b", inputs=(FACTS_INPUT,)),
        spec("m_c", inputs=(FACTS_INPUT,))))
    assert crowded.fan_out > alone.fan_out
    assert crowded.value > alone.value
    ceiling = Q.downstream_factor(10 ** 6, T.BOUNDS)
    assert ceiling == pytest.approx(2.0)


def test_effort_divides_the_value(registry):
    """EFFORT_WEIGHT divides: a question that costs the client a document must
    earn its place against the ones they can answer offhand. The ratio is the
    contract's own table, exactly."""
    reg = registry()
    decision = scaffold(reg)
    offhand = sourced(InputSpec("facts", K.FACT, effort=T.EffortClass.OFFHAND, why_needed="w"),
                      decision_ids=(decision.id,))
    document = sourced(InputSpec("facts", K.FACT, effort=T.EffortClass.DOCUMENT, why_needed="w"),
                       decision_ids=(decision.id,))
    methods = one_method()
    cheap = Q.score_gap(reg, offhand, methods=methods).value
    dear = Q.score_gap(reg, document, methods=methods).value
    assert cheap > dear
    assert cheap / dear == pytest.approx(
        T.EFFORT_WEIGHT[T.EffortClass.DOCUMENT] / T.EFFORT_WEIGHT[T.EffortClass.OFFHAND])


def test_a_gap_serving_a_heavier_decision_is_worth_more(registry):
    """The decision term is the hypothesis weight, recomputed from the rows:
    evidence that moves the ranking moves the question value with it."""
    reg = registry()
    stated = add(reg, K.DECISION, T.DecisionPayload(statement="fix the delays",
                                                    role=T.DecisionRole.STATED_REQUEST))
    other = add(reg, K.DECISION, T.DecisionPayload(statement="redesign fulfilment",
                                                   role=T.DecisionRole.CENTRAL))
    fact(reg, decision_id=stated.id, conf=0.9, relation=DEFINES)
    fact(reg, decision_id=stated.id, conf=0.9, relation=DEFINES)
    fact(reg, decision_id=other.id, conf=0.1, relation=INFORMS)
    heavy = Q.score_gap(reg, sourced(FACTS_INPUT, decision_ids=(stated.id,)), methods=one_method())
    light = Q.score_gap(reg, sourced(FACTS_INPUT, decision_ids=(other.id,)), methods=one_method())
    assert heavy.value > light.value


# ===========================================================================
# 4. The batch laws
# ===========================================================================

def test_zero_impact_gap_is_never_asked(registry):
    """An issue explicitly related to nothing scores zero: its answer cannot
    change the recommendation, so the turn is not spent on it - even when it
    is the only gap on the table and the minimum is one."""
    reg = registry()
    decision = scaffold(reg)
    issue(reg, decision.id, relation=UNRELATED)
    methods = one_method()
    scored = Q.scored_gaps(reg, methods=methods)
    assert [s.impact for s in scored] == [0.0]          # the gap exists, and is worth nothing
    assert Q.select_questions(scored) == ()
    from app.engine.llm import FakeProvider
    assert Q.ask(reg, FakeProvider(), turn_number=1, methods=methods).questions == ()
    assert Q.top_gap_value(reg, methods=methods) == 0.0


def test_at_most_one_question_per_issue_leaf(registry):
    """S2: one issue leaf gets one question per batch, however many of its
    inputs are missing - the client answers a conversation, not a form."""
    reg = registry()
    decision = scaffold(reg)
    leaf = issue(reg, decision.id)
    methods = methods_with(spec("m_two_inputs", inputs=(
        FACTS_INPUT,
        InputSpec("stakeholders", K.STAKEHOLDER, why_needed="who feels this and who decides it"))))
    scored = Q.scored_gaps(reg, methods=methods)
    assert len([s for s in scored if s.gap.issue_id == leaf.id]) == 2
    chosen = Q.select_questions(scored)
    assert len([s for s in chosen if s.gap.issue_id == leaf.id]) == 1
    assert len(chosen) == 1


def test_bounds_are_respected_and_vary_with_the_value_available(registry):
    """k lies between MIN_ and MAX_QUESTIONS_PER_TURN, and stops early once the
    marginal value falls under MIN_QUESTION_VALUE. No count is written here."""
    reg = registry()
    decision = scaffold(reg)
    for n in range(4):
        issue(reg, decision.id, text=f"issue {n}")
    methods = one_method()
    scored = Q.scored_gaps(reg, methods=methods)
    assert len(scored) == 4
    assert len(Q.select_questions(scored, T.BOUNDS)) == T.BOUNDS["MAX_QUESTIONS_PER_TURN"]
    tighter = bounds(MAX_QUESTIONS_PER_TURN=2)
    assert len(Q.select_questions(scored, tighter)) == 2
    # every gap under the floor: the minimum is still asked, and no more
    floored = bounds(MIN_QUESTION_VALUE=10.0)
    assert len(Q.select_questions(scored, floored)) == floored["MIN_QUESTIONS_PER_TURN"]


def test_fewer_gaps_means_fewer_questions(registry):
    reg = registry()
    decision = scaffold(reg)
    issue(reg, decision.id)
    assert len(Q.select_questions(Q.scored_gaps(reg, methods=one_method()))) == 1


# ===========================================================================
# 5. Asking, and not asking twice
# ===========================================================================

def test_answered_question_disappears_next_turn(registry):
    """The gap is gone once the registry holds the answer: the second turn
    asks something else, or nothing, but never the same thing."""
    from app.engine.llm import FakeProvider
    reg = registry()
    decision = scaffold(reg)
    issue(reg, decision.id)
    methods = one_method()
    first = Q.ask(reg, FakeProvider(), turn_number=1, methods=methods)
    assert len(first.questions) == 1
    asked_gap = first.asked[0].gap_id
    assert first.questions[0].labels == (Q.GAP_LABEL_PREFIX + asked_gap,)
    assert first.questions[0].status is S.OPEN
    fact(reg, conf=0.9, relation=DEFINES)                     # the client answers
    assert asked_gap not in {s.gap_id for s in Q.scored_gaps(reg, methods=methods)}
    second = Q.ask(reg, FakeProvider(), turn_number=2, methods=methods)
    assert second.questions == ()


def test_an_open_question_is_not_asked_again(registry):
    from app.engine.llm import FakeProvider
    reg = registry()
    decision = scaffold(reg)
    issue(reg, decision.id)
    methods = one_method()
    Q.ask(reg, FakeProvider(), turn_number=1, methods=methods)
    again = Q.ask(reg, FakeProvider(), turn_number=2, methods=methods)
    assert again.questions == ()
    assert len(reg.query(K.QUESTION)) == 1


def test_a_written_question_carries_its_typed_ask_and_why(registry):
    from app.engine.llm import FakeProvider
    reg = registry()
    decision = scaffold(reg)
    iss = issue(reg, decision.id)
    batch = Q.ask(reg, FakeProvider(), turn_number=1, methods=one_method())
    q = batch.questions[0]
    assert q.payload.asks_for == (T.AsksFor(K.FACT, {}),)
    assert q.payload.issue_ids == (iss.id,)
    assert q.payload.strategy is T.FillStrategy.ASK_CLIENT
    assert q.payload.effort is T.EffortClass.OFFHAND
    assert q.payload.value == pytest.approx(batch.asked[0].value)
    assert iss.id in q.payload.why and decision.id in q.payload.why
    assert q.provenance.derived_from == (iss.id,)
    assert q.relevance.weight == 0.0            # a question is not evidence for a candidate


# ===========================================================================
# 6. Wording: the model words them, the registry decides them
# ===========================================================================

def scene_with_one_gap(registry):
    reg = registry()
    decision = scaffold(reg)
    issue(reg, decision.id)
    methods = one_method()
    selected = Q.select_questions(Q.scored_gaps(reg, methods=methods))
    return reg, methods, selected


def test_model_added_question_is_dropped(registry):
    """The agenda lock: the model words the gaps it was given and cannot add
    one, because a question mapping to no typed gap has no answer the registry
    could hold."""
    from app.engine.llm import FakeProvider
    reg, methods, selected = scene_with_one_gap(registry)
    real = selected[0].gap_id
    provider = FakeProvider(script={Q.PHRASE_PURPOSE: [json.dumps({"questions": [
        {"gap_id": real, "text": "How many orders a day does the line run?"},
        {"gap_id": "GAP-invented", "text": "Shall we review your pricing while we are at it?"},
        {"gap_id": "", "text": "And who is your auditor?"},
    ]})]})
    worded, call_id = Q.phrase_questions(reg, provider, selected)
    assert set(worded) == {real}
    assert call_id is not None
    batch = Q.ask(reg, FakeProvider(script={Q.PHRASE_PURPOSE: [json.dumps({"questions": [
        {"gap_id": real, "text": "How many orders a day does the line run?"},
        {"gap_id": "GAP-invented", "text": "Shall we review your pricing while we are at it?"},
    ]})]}), turn_number=1, methods=methods)
    assert len(batch.questions) == 1
    assert "pricing" not in batch.questions[0].payload.text


def test_under_the_fake_the_wording_is_why_needed_verbatim(registry):
    """A provider that says nothing costs wording, never the question: the
    engine's own words are the InputSpec's why_needed, so the fake's questions
    are deterministic."""
    from app.engine.llm import FakeProvider
    reg, methods, _ = scene_with_one_gap(registry)
    batch = Q.ask(reg, FakeProvider(), turn_number=1, methods=methods)
    assert batch.questions[0].payload.text == FACTS_INPUT.why_needed
    assert batch.questions[0].provenance.model_call_id is None


def test_a_provider_outage_still_asks_the_question(registry):
    from app.engine.llm import FakeProvider
    reg, methods, _ = scene_with_one_gap(registry)
    provider = FakeProvider(script={Q.PHRASE_PURPOSE: [RuntimeError("provider down")]})
    batch = Q.ask(reg, provider, turn_number=1, methods=methods)
    assert len(batch.questions) == 1
    assert batch.questions[0].payload.text == FACTS_INPUT.why_needed


# ===========================================================================
# 7. Universality: selection reads shapes and counts, never text
# ===========================================================================

def test_scrambling_every_text_field_leaves_the_batch_identical(registry):
    """The same registry with every free-text field replaced yields the same
    gaps, in the same order, at the same values: no engagement vocabulary can
    steer what is asked (M2/P1)."""
    def scene(word: str):
        reg = registry()
        decision = add(reg, K.DECISION, T.DecisionPayload(statement=f"{word} one",
                                                          role=T.DecisionRole.STATED_REQUEST))
        add(reg, K.OBJECTIVE, T.ObjectivePayload(text=f"{word} two"))
        add(reg, K.DECISION_OWNER, T.DecisionOwnerPayload(name=f"{word} three", role=word))
        add(reg, K.DEADLINE, T.DeadlinePayload(text=f"{word} four"))
        add(reg, K.EVIDENCE_SOURCE, T.EvidenceSourcePayload(name=f"{word} five",
                                                            source_kind=T.SourceKind.DOCUMENT))
        issue(reg, decision.id, text=f"{word} six")
        return [(s.sourced.source, round(s.value, 9))
                for s in Q.scored_gaps(reg, methods=one_method())]

    assert scene("alpha") == scene("omega")
