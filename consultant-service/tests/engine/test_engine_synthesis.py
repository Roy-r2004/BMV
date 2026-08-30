"""C14 synthesis: app/engine/synthesis/{conflicts,resolve,recommend}.py --
what the engagement does with two conclusions that cannot both stand
(design 9.1-9.5; spec section 7: conflicts fail closed).

Laws pinned here, each with the mutation that kills it:

  * equal rank never resolves automatically; the client designates
                            (mutation: auto-resolve equal ranks)
  * a rank difference resolves automatically ONLY when the client confirmed
    what the winning document IS; otherwise the conflict stays open and an
    OFFHAND provenance question is asked
                            (mutation: auto-resolve on an unconfirmed record class)
  * a material judgement disagreement belongs to the decision owner
                            (mutation: let CONSULTANT resolve a material trade-off)
  * resolving never deletes: the unchosen conclusion is REJECTED and stays
    queryable in get()/lineage()
                            (mutation: delete the loser row)
  * materiality is recomputed from the live support graph every round, so a
    conflict written before the recommendation that rests on it becomes
    material once that recommendation exists
                            (mutation: read the stored material flag)

plus: facts join on measure_id and on nothing else (two different wordings on
one confirmed measure reconcile, with no similarity import anywhere in the
package); an objective the arithmetic refutes becomes INFEASIBLE_ON_FACTS and
reaches the client as a DECISION_REQUIRED (L12); an unpinned dimension is a
question and never a conflict; an unsupported recommendation is never
approved; detection is idempotent.

And the three seams other components read this module through (section 9):

  * C11 methods: a CALCULATION method reaches the feasibility verdict first
    for the measures it totals, amending the objective and asking the client
    itself. Query 3 says nothing that record already says
                            (mutation: drop the already-refuted guard)
                            (mutation: ask the client a second time)
  * C13 specialists: two PROPOSED entities of one kind on one subject from two
    assignments ARE the SPECIALIST_DISAGREEMENT input - the runner never
    reconciles them, and neither does this module
  * C8 questions: a conflict becomes a client question on exactly two
    structural fields, status OPEN and authority_required CLIENT
"""
from __future__ import annotations

import pathlib
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.engine import types as T
from app.engine.registry import SUPERSEDED_BY_RECORD, RegistryError
from app.engine.synthesis.conflicts import UNTESTED_VERDICT, detect_conflicts, reevaluate_materiality
from app.engine.synthesis.recommend import (
    UNSUPPORTED_RECOMMENDATION_LAW, UnsupportedRecommendation, approve_recommendation, conditional_on,
    refresh_conditional_on, support_findings,
)
from app.engine.synthesis.resolve import (
    ResolutionRefused, advise, emit_decisions_required, resolve,
)

K, S, A = T.Kind, T.Status, T.Actor
CK, AU = T.ConflictKind, T.Authority

TURN = "we run with 40 heads today; the finance pack said 41 heads last quarter"
PAYROLL = "Headcount as at 2025-12-31: 45 heads on the payroll export"
BOARD = "The board pack records 47 heads as at 2025-12-31"
OPERATIONS = "Operations review: 48 heads as at 2025-12-31"

NOW = T.Dimensions(currency=None, period="FY25", period_basis="point_in_time", scope="group",
                   as_of="2025-12-31", definition="heads")
LATER = replace(NOW, period="FY26", as_of="2026-12-31")


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------

def qty(value: str, dims: T.Dimensions = NOW) -> T.Quantity:
    return T.Quantity(Decimal(value), "heads", T.UnitFamily.COUNT, dims, precision=0)


def add(reg, kind, payload, *, actor=A.PARTNER, ref=None, derived=(), locator=None, status=S.PROPOSED,
        relation=T.RelationToCentralDecision.INFORMS, weight=0.5, decision_id=None):
    entity = T.make_entity(
        kind=kind, engagement_id=reg.engagement_id, payload=payload,
        provenance=T.Provenance(actor=actor, actor_ref=ref or f"{actor.value}:1",
                                derived_from=tuple(derived), source_locator=locator),
        confidence=T.Confidence(None), relevance=T.Relevance(decision_id, weight, ""),
        relation=relation, status=status)
    return reg.apply(T.Add(entity))


def advance(reg, entity, status, actor, ref=None):
    return reg.apply(T.SetStatus(entity.id, status, T.Provenance(actor=actor, actor_ref=ref or f"{actor.value}:1")))


@pytest.fixture
def world(registry):
    """One engagement: a conversation turn, one confirmed MEASURE every fact
    joins on, and a central decision for relevance."""
    reg = registry("E-1")
    turn = add(reg, K.EVIDENCE_SOURCE, T.EvidenceSourcePayload(
        name="turn 1", source_kind=T.SourceKind.CONVERSATION_TURN, text=TURN))
    measure = add(reg, K.MEASURE, T.MeasurePayload(
        name="headcount", unit_family=T.UnitFamily.COUNT, definition="heads", confirmed_by_client=True))
    decision = add(reg, K.DECISION, T.DecisionPayload(
        statement="how many people to run the workshop with", role=T.DecisionRole.CENTRAL))
    return SimpleNamespace(reg=reg, turn=turn, measure=measure, decision=decision)


def source(w, name, text, record_class=T.RecordClass.UNKNOWN, confirmed=False):
    return add(w.reg, K.EVIDENCE_SOURCE, T.EvidenceSourcePayload(
        name=name, source_kind=T.SourceKind.DOCUMENT, record_class=record_class,
        record_class_confirmed_by_client=confirmed, text=text))


def client_fact(w, statement, value, *, confirm=True, dims=NOW, topic="what the client remembers",
                relation=T.RelationToCentralDecision.INFORMS, measure=None):
    f = add(w.reg, K.FACT, T.FactPayload(statement=statement, basis=T.FactBasis.CLIENT_STATED,
                                         measure_id=(measure or w.measure).id, quantity=qty(value, dims),
                                         topic=topic),
            derived=(w.turn.id,), relation=relation, decision_id=w.decision.id)
    return advance(w.reg, f, S.CONFIRMED, A.CLIENT) if confirm else f


def record_fact(w, src, value, record_class, locator, *, confirm=False, dims=NOW,
                relation=T.RelationToCentralDecision.INFORMS, measure=None):
    f = add(w.reg, K.FACT, T.FactPayload(statement=locator, basis=T.FactBasis.DOCUMENT_VERIFIED,
                                         measure_id=(measure or w.measure).id, quantity=qty(value, dims),
                                         record_class=record_class, topic="what the record says"),
            ref=f"doc:{src.id}", derived=(src.id,), locator=locator, relation=relation,
            decision_id=w.decision.id)
    return advance(w.reg, f, S.CONFIRMED, A.DOCUMENT) if confirm else f


def calculated_fact(w, value, inputs, *, dims=NOW):
    return add(w.reg, K.FACT, T.FactPayload(
        statement="headcount after the plan", basis=T.FactBasis.CALCULATED, measure_id=w.measure.id,
        quantity=qty(value, dims), formula=" - ".join(i.id for i in inputs) if len(inputs) > 1 else f"{inputs[0].id} * 0.875",
        inputs=tuple(i.id for i in inputs)), actor=A.CALCULATOR, ref="calculator", decision_id=w.decision.id)


def tradeoff(w, score, *, relation=T.RelationToCentralDecision.DEFINES, material=True):
    return add(w.reg, K.TRADE_OFF, T.TradeOffPayload(
        decision_id=w.decision.id, option_ids=("OPT-1", "OPT-2"), gives_up="speed", gains="cost",
        scores=(T.Score("OPT-1", "CRI-1", Decimal(score), ("FCT-1",)),), material=material),
        actor=A.METHOD, ref="method:option_evaluation@1", relation=relation, decision_id=w.decision.id)


def conflicts_of(reg):
    return reg.query(K.CONFLICT)


def only_conflict(reg):
    rows = conflicts_of(reg)
    assert len(rows) == 1, [c.payload.kind for c in rows]
    return rows[0]


class Recomputes:
    """The calculator boundary as far as advise() uses it: does this stored
    calculation still recompute, exactly (L7)?"""

    def __init__(self, verdict: bool):
        self.verdict = verdict

    def recompute(self, calculated, registry) -> bool:
        return self.verdict


# ---------------------------------------------------------------------------
# 1. detection joins on the measure, and on nothing else
# ---------------------------------------------------------------------------

def test_two_wordings_on_one_measure_reconcile_without_similarity(world):
    """MF1.6: the join is measure_id. Two facts whose statements and topics
    differ are one disagreement, and no similarity decided that."""
    a = client_fact(world, "40 heads", "40", topic="headcount today")
    b = client_fact(world, "41 heads", "41", topic="what the finance pack said")

    detect_conflicts(world.reg)

    conflict = only_conflict(world.reg)
    assert conflict.payload.kind is CK.VALUE
    assert conflict.payload.subject_id == world.measure.id
    assert {c.entity_id for c in conflict.payload.conclusions} == {a.id, b.id}
    assert conflict.status is S.OPEN


def test_no_similarity_library_is_imported_by_synthesis():
    """Broad regex, similarity and prose replacement are prohibited (spec
    section 7): the join above cannot quietly become a text comparison."""
    package = pathlib.Path(__file__).resolve().parents[2] / "app" / "engine" / "synthesis"
    for path in sorted(package.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "difflib" not in text, path.name
        assert "rapidfuzz" not in text, path.name


def test_an_unpinned_dimension_is_a_question_not_a_conflict(world):
    """Absence is not evidence of a defect: a fact whose as_of nobody pinned
    disagrees with nothing."""
    client_fact(world, "40 heads", "40")
    payroll = source(world, "payroll export", PAYROLL, T.RecordClass.SYSTEM_OF_RECORD, confirmed=True)
    record_fact(world, payroll, "45", T.RecordClass.SYSTEM_OF_RECORD, "45 heads",
                dims=replace(NOW, as_of=None))

    detect_conflicts(world.reg)

    assert conflicts_of(world.reg) == []


def test_detection_is_idempotent(world):
    client_fact(world, "40 heads", "40")
    client_fact(world, "41 heads", "41")

    detect_conflicts(world.reg)
    again = detect_conflicts(world.reg)

    assert again == []
    assert len(conflicts_of(world.reg)) == 1


# ---------------------------------------------------------------------------
# 2. precedence: equal rank never resolves itself
# ---------------------------------------------------------------------------

def test_same_rank_sources_stay_open_and_recommend_nobody(world):
    """MUTATION 'auto-resolve equal ranks': two management reports of equal
    rank must not pick a winner, whatever their record classes say."""
    board = source(world, "board pack", BOARD, T.RecordClass.MANAGEMENT_REPORT, confirmed=True)
    operations = source(world, "operations review", OPERATIONS, T.RecordClass.MANAGEMENT_REPORT, confirmed=True)
    a = record_fact(world, board, "47", T.RecordClass.MANAGEMENT_REPORT, "47 heads", confirm=True)
    b = record_fact(world, operations, "48", T.RecordClass.MANAGEMENT_REPORT, "48 heads", confirm=True)

    detect_conflicts(world.reg)

    conflict = only_conflict(world.reg)
    assert conflict.status is S.OPEN
    assert conflict.payload.authority_required is AU.CLIENT
    assert conflict.payload.recommended_resolution is None
    for f in (a, b):
        assert SUPERSEDED_BY_RECORD not in world.reg.get(f.id).labels
        assert world.reg.get(f.id).status is S.CONFIRMED


# ---------------------------------------------------------------------------
# 3. a confirmed record class, and only a confirmed one, resolves visibly
# ---------------------------------------------------------------------------

def test_confirmed_record_supersedes_the_client_statement_visibly(world):
    payroll = source(world, "payroll export", PAYROLL, T.RecordClass.SYSTEM_OF_RECORD, confirmed=True)
    said = client_fact(world, "40 heads", "40")
    recorded = record_fact(world, payroll, "45", T.RecordClass.SYSTEM_OF_RECORD, "45 heads", confirm=True)

    detect_conflicts(world.reg)

    conflict = only_conflict(world.reg)
    assert conflict.payload.kind is CK.CLIENT_VS_RECORD
    assert conflict.status is S.RESOLVED
    assert conflict.payload.resolution_chosen == recorded.id
    assert conflict.payload.resolution_by == f"document:{payroll.id}"
    assert conflict.payload.recommendation_basis and "CURRENT_STATE_PRECEDENCE" in conflict.payload.recommendation_basis

    loser = world.reg.get(said.id)
    assert loser is not None, "resolving never deletes"
    assert SUPERSEDED_BY_RECORD in loser.labels
    assert loser.payload.statement == "40 heads", "the client's words are never restated"
    assert loser.status is S.PROPOSED, "a record cannot confirm on the client's behalf"
    assert any(row.status is S.SUPERSEDED for row in world.reg.lineage(said.id))
    assert world.reg.get(recorded.id).status is S.CONFIRMED


def test_unconfirmed_record_class_leaves_the_conflict_open_and_asks_what_the_document_is(world):
    """MUTATION 'auto-resolve on an unconfirmed record class' (MF2.3): a record
    class the client never confirmed is a model's guess, and a guess must not
    retire what the client said."""
    payroll = source(world, "payroll export", PAYROLL, T.RecordClass.SYSTEM_OF_RECORD, confirmed=False)
    said = client_fact(world, "40 heads", "40")
    recorded = record_fact(world, payroll, "45", T.RecordClass.SYSTEM_OF_RECORD, "45 heads", confirm=True)

    detect_conflicts(world.reg)

    conflict = only_conflict(world.reg)
    assert conflict.status is S.OPEN
    assert conflict.payload.authority_required is AU.CLIENT
    assert conflict.payload.recommended_resolution == recorded.id, "precedence still recommends; it just cannot act"

    loser = world.reg.get(said.id)
    assert SUPERSEDED_BY_RECORD not in loser.labels
    assert loser.status is S.CONFIRMED

    questions = world.reg.query(K.QUESTION, status=S.OPEN)
    assert len(questions) == 1
    question = questions[0]
    assert question.payload.effort is T.EffortClass.OFFHAND
    assert question.payload.asks_for[0].kind is K.EVIDENCE_SOURCE
    assert payroll.id in question.provenance.derived_from
    assert payroll.payload.name in question.payload.text

    detect_conflicts(world.reg)
    assert len(world.reg.query(K.QUESTION, status=S.OPEN)) == 1, "one provenance question per source"


def test_arithmetic_that_recomputes_resolves_itself(world):
    payroll = source(world, "payroll export", PAYROLL, T.RecordClass.SYSTEM_OF_RECORD, confirmed=True)
    recorded = record_fact(world, payroll, "45", T.RecordClass.SYSTEM_OF_RECORD, "45 heads", confirm=True)
    computed = calculated_fact(world, "44", (recorded,))

    detect_conflicts(world.reg, calc=Recomputes(True))

    conflict = only_conflict(world.reg)
    assert conflict.status is S.RESOLVED
    assert conflict.payload.resolution_chosen == computed.id
    assert conflict.payload.resolution_by == "calculator"
    assert SUPERSEDED_BY_RECORD in world.reg.get(recorded.id).labels


def test_arithmetic_that_does_not_recompute_resolves_nothing(world):
    payroll = source(world, "payroll export", PAYROLL, T.RecordClass.SYSTEM_OF_RECORD, confirmed=True)
    recorded = record_fact(world, payroll, "45", T.RecordClass.SYSTEM_OF_RECORD, "45 heads", confirm=True)
    calculated_fact(world, "44", (recorded,))

    detect_conflicts(world.reg, calc=Recomputes(False))

    conflict = only_conflict(world.reg)
    assert conflict.status is S.OPEN
    assert conflict.payload.authority_required is AU.CLIENT
    assert conflict.payload.recommended_resolution is None


# ---------------------------------------------------------------------------
# 4. judgements: who may settle a disagreement, and what happens to the loser
# ---------------------------------------------------------------------------

def _disagreeing_tradeoffs(world):
    return tradeoff(world, "3"), tradeoff(world, "5")


def test_a_material_trade_off_is_the_decision_owners_to_settle(world):
    """MUTATION 'let CONSULTANT resolve a material trade-off': a disagreement
    that defines the central decision is not the consultant's to close."""
    _disagreeing_tradeoffs(world)

    detect_conflicts(world.reg)

    conflict = only_conflict(world.reg)
    assert conflict.payload.kind is CK.SPECIALIST_DISAGREEMENT
    assert conflict.payload.material is True
    assert conflict.payload.authority_required is AU.DECISION_OWNER

    with pytest.raises(ResolutionRefused):
        resolve(world.reg, conflict.id, chosen_entity_id=None, actor=A.PARTNER,
                actor_ref="partner:1", rationale="the partner prefers the cheaper one")
    assert world.reg.get(conflict.id).status is S.OPEN


def test_an_immaterial_disagreement_is_the_consultants(world):
    """The negative control for the same law: nothing rests on these, so the
    consultant closes them."""
    tradeoff(world, "3", relation=T.RelationToCentralDecision.INFORMS, material=False)
    tradeoff(world, "5", relation=T.RelationToCentralDecision.INFORMS, material=False)

    detect_conflicts(world.reg)

    conflict = only_conflict(world.reg)
    assert conflict.payload.material is False
    assert conflict.payload.authority_required is AU.CONSULTANT
    assert advise(world.reg, conflict.payload.kind, (), material=False).authority is AU.CONSULTANT


def test_resolving_rejects_the_loser_and_never_deletes_it(world):
    """MUTATION 'delete the loser row': the unchosen conclusion is REJECTED
    with the resolution named on the row, and stays queryable."""
    owner = add(world.reg, K.DECISION_OWNER, T.DecisionOwnerPayload(name="the owner", role="managing director"))
    kept, dropped = _disagreeing_tradeoffs(world)
    detect_conflicts(world.reg)
    conflict = only_conflict(world.reg)

    with pytest.raises(ResolutionRefused):
        resolve(world.reg, conflict.id, chosen_entity_id=kept.id, actor=A.DECISION_OWNER,
                actor_ref="client:turn:3", rationale="the owner decided")

    resolved = resolve(world.reg, conflict.id, chosen_entity_id=kept.id, actor=A.DECISION_OWNER,
                       actor_ref="client:turn:3", rationale="the owner decided on the cost score",
                       on_behalf_of=owner.id)

    assert resolved.status is S.RESOLVED
    assert resolved.payload.resolution_chosen == kept.id
    assert resolved.payload.resolution_rationale == "the owner decided on the cost score"
    loser = world.reg.get(dropped.id)
    assert loser is not None and loser.status is S.REJECTED
    assert conflict.id in (loser.confirmed_by or "")
    assert len(world.reg.lineage(dropped.id)) >= 2
    assert world.reg.get(kept.id).status is S.PROPOSED


def test_a_resolution_refuses_an_unrecorded_choice_a_closed_conflict_and_a_silent_rationale(world):
    owner = add(world.reg, K.DECISION_OWNER, T.DecisionOwnerPayload(name="the owner", role="managing director"))
    kept, _dropped = _disagreeing_tradeoffs(world)
    detect_conflicts(world.reg)
    conflict = only_conflict(world.reg)

    with pytest.raises(ResolutionRefused):
        resolve(world.reg, conflict.id, chosen_entity_id=world.measure.id, actor=A.DECISION_OWNER,
                actor_ref="client:turn:3", rationale="not a conclusion", on_behalf_of=owner.id)
    with pytest.raises(ResolutionRefused):
        resolve(world.reg, conflict.id, chosen_entity_id=kept.id, actor=A.DECISION_OWNER,
                actor_ref="client:turn:3", rationale="", on_behalf_of=owner.id)

    resolve(world.reg, conflict.id, chosen_entity_id=kept.id, actor=A.DECISION_OWNER,
            actor_ref="client:turn:3", rationale="settled", on_behalf_of=owner.id)
    with pytest.raises(ResolutionRefused):
        resolve(world.reg, conflict.id, chosen_entity_id=kept.id, actor=A.DECISION_OWNER,
                actor_ref="client:turn:4", rationale="again", on_behalf_of=owner.id)


def test_the_arithmetic_never_retires_what_the_client_said(world):
    """MUTATION 'let the calculator retire a client fact as a record': I2 admits
    exactly one automatic path over a client statement -- a DOCUMENT carrying
    the label. A calculation is not that path, so the batch is refused, the
    conflict stays OPEN, and the client is the one who settles it."""
    said = client_fact(world, "40 heads", "40")
    computed = calculated_fact(world, "35", (said,))

    detect_conflicts(world.reg, calc=Recomputes(True))

    conflict = only_conflict(world.reg)
    assert conflict.status is S.OPEN, "a calculation may not close this one alone"
    loser = world.reg.get(said.id)
    assert loser.status is S.CONFIRMED and SUPERSEDED_BY_RECORD not in loser.labels
    assert world.reg.get(computed.id).status is S.PROPOSED
    assert len(world.reg.lineage(said.id)) == 2, "nothing was half-applied"
    assert conflict.payload.recommended_resolution == computed.id, "it still says what it would have chosen"


def test_a_resolution_the_registry_refuses_leaves_the_conflict_untouched(world):
    """MUTATION 'let the registry error escape': the rejections and the
    resolution are one batch. When a law refuses one of them the whole act is
    refused -- in this module's own currency, so the API answers 403/409 and
    never a 500 -- and no conflict is left RESOLVED above a live conclusion."""
    board = source(world, "board pack", BOARD, T.RecordClass.MANAGEMENT_REPORT, confirmed=True)
    operations = source(world, "operations review", OPERATIONS, T.RecordClass.MANAGEMENT_REPORT, confirmed=True)
    # Authored by a specialist: no actor this resolution may write in -- neither
    # the client nor the partner -- may reject them (may_advance, REJECTED).
    a = add(world.reg, K.FACT, T.FactPayload(
        statement="47 heads", basis=T.FactBasis.DOCUMENT_VERIFIED, measure_id=world.measure.id,
        quantity=qty("47"), record_class=T.RecordClass.MANAGEMENT_REPORT),
        actor=A.SPECIALIST, ref="specialist:1", derived=(board.id,), locator="47 heads")
    b = add(world.reg, K.FACT, T.FactPayload(
        statement="48 heads", basis=T.FactBasis.DOCUMENT_VERIFIED, measure_id=world.measure.id,
        quantity=qty("48"), record_class=T.RecordClass.MANAGEMENT_REPORT),
        actor=A.SPECIALIST, ref="specialist:1", derived=(operations.id,), locator="48 heads")

    detect_conflicts(world.reg)
    conflict = only_conflict(world.reg)
    assert conflict.payload.authority_required is AU.CLIENT

    with pytest.raises(ResolutionRefused):
        resolve(world.reg, conflict.id, chosen_entity_id=a.id, actor=A.CLIENT,
                actor_ref="client:turn:2", rationale="the board pack is the one we plan on")

    assert world.reg.get(conflict.id).status is S.OPEN
    assert world.reg.get(b.id).status is S.PROPOSED, "no conclusion was rejected by a refused act"
    assert len(world.reg.lineage(conflict.id)) == 1


def test_an_open_material_conflict_reaches_its_owner_as_a_decision_required(world):
    _disagreeing_tradeoffs(world)

    detect_conflicts(world.reg)

    conflict = only_conflict(world.reg)
    required = world.reg.query(K.DECISION_REQUIRED, status=S.OPEN)
    assert len(required) == 1
    assert required[0].payload.from_authority is AU.DECISION_OWNER
    assert conflict.id in required[0].provenance.derived_from
    assert set(required[0].payload.options) == {c.entity_id for c in conflict.payload.conclusions}
    emit_decisions_required(world.reg)
    assert len(world.reg.query(K.DECISION_REQUIRED, status=S.OPEN)) == 1, "asked once"


# ---------------------------------------------------------------------------
# 5. an objective the arithmetic refutes
# ---------------------------------------------------------------------------

def _objective(world, target_value):
    return add(world.reg, K.OBJECTIVE, T.ObjectivePayload(
        text="run the workshop with fewer people", measure_id=world.measure.id, target=qty(target_value, LATER)),
        actor=A.CLIENT, ref="client:turn:1", status=S.CONFIRMED, decision_id=world.decision.id)


def test_an_impossible_objective_is_marked_infeasible_and_put_to_the_client(world):
    baseline = client_fact(world, "40 heads", "40")
    objective = _objective(world, "20")
    calculated_fact(world, "35", (baseline,), dims=LATER)

    detect_conflicts(world.reg)

    current = world.reg.get(objective.id)
    assert current.payload.feasibility is T.Feasibility.INFEASIBLE_ON_FACTS
    assert current.payload.text == "run the workshop with fewer people"
    assert current.status is S.PROPOSED, "only the client confirms their own objective"

    conflict = only_conflict(world.reg)
    assert conflict.payload.kind is CK.OBJECTIVE_VS_FEASIBILITY
    assert conflict.payload.material is True
    assert conflict.payload.authority_required is AU.CLIENT
    assert world.reg.infeasible_objectives_without_decision() == [], "L12: the client was asked"


def test_a_reachable_objective_is_left_alone(world):
    baseline = client_fact(world, "40 heads", "40")
    objective = _objective(world, "36")
    calculated_fact(world, "35", (baseline,), dims=LATER)

    detect_conflicts(world.reg)

    assert world.reg.get(objective.id).payload.feasibility is T.Feasibility.UNTESTED
    assert conflicts_of(world.reg) == []


# ---------------------------------------------------------------------------
# 6. an assumption the evidence contradicts
# ---------------------------------------------------------------------------

def test_an_assumption_a_confirmed_fact_contradicts_becomes_a_conflict(world):
    fact = client_fact(world, "40 heads", "40")
    assumption = add(world.reg, K.ASSUMPTION, T.AssumptionPayload(
        statement="we assume 30 heads", rationale="planning figure", quantity=qty("30")),
        actor=A.METHOD, ref="method:scenario@1", derived=(world.measure.id,), decision_id=world.decision.id)

    detect_conflicts(world.reg)

    conflict = only_conflict(world.reg)
    assert conflict.payload.kind is CK.ASSUMPTION_VS_EVIDENCE
    assert conflict.payload.authority_required is AU.CLIENT
    assert {c.entity_id for c in conflict.payload.conclusions} == {assumption.id, fact.id}


# ---------------------------------------------------------------------------
# 7. materiality is recomputed, never remembered
# ---------------------------------------------------------------------------

def test_a_conflict_becomes_material_when_a_recommendation_rests_on_it(world):
    """MUTATION 'read the stored material flag' (MF2.4): the flag written when
    nothing rested on the conflict would wave it through forever."""
    a = client_fact(world, "40 heads", "40")
    client_fact(world, "41 heads", "41")
    detect_conflicts(world.reg)
    conflict = only_conflict(world.reg)
    assert conflict.payload.material is False

    add(world.reg, K.RECOMMENDATION, T.RecommendationPayload(
        statement="run with the smaller team", decision_id=world.decision.id, supports=(a.id,)),
        decision_id=world.decision.id)

    changed = reevaluate_materiality(world.reg)

    assert [c.id for c in changed] == [conflict.id]
    current = world.reg.get(conflict.id)
    assert current.payload.material is True
    assert current.payload.authority_required is AU.CLIENT
    assert len(world.reg.lineage(conflict.id)) >= 2, "a changed flag is visible in lineage"
    assert [c.id for c in reevaluate_materiality(world.reg)] == [], "no churn once it agrees"
    assert world.reg.open_material_conflicts() == [current], "L1 now sees it"


# ---------------------------------------------------------------------------
# 8. recommendations: supported, and conditional while a question is open
# ---------------------------------------------------------------------------

def test_an_unsupported_recommendation_is_never_approved(world):
    rec = add(world.reg, K.RECOMMENDATION, T.RecommendationPayload(
        statement="run with the smaller team", decision_id=world.decision.id), decision_id=world.decision.id)

    findings = support_findings(world.reg)
    assert [f.law for f in findings] == [UNSUPPORTED_RECOMMENDATION_LAW]
    assert findings[0].blocks_final is True
    with pytest.raises(UnsupportedRecommendation):
        approve_recommendation(world.reg, rec.id, actor=A.CLIENT, actor_ref="client:turn:2")
    with pytest.raises(RegistryError):
        world.reg.apply(T.SetStatus(rec.id, S.APPROVED, T.Provenance(actor=A.CLIENT, actor_ref="client:turn:2")))
    assert world.reg.get(rec.id).status is S.PROPOSED


def test_a_supported_recommendation_is_approved_by_the_client(world):
    fact = client_fact(world, "40 heads", "40")
    rec = add(world.reg, K.RECOMMENDATION, T.RecommendationPayload(
        statement="run with the smaller team", decision_id=world.decision.id, supports=(fact.id,)),
        decision_id=world.decision.id)

    approved = approve_recommendation(world.reg, rec.id, actor=A.CLIENT, actor_ref="client:turn:2")

    assert approved.status is S.APPROVED
    assert support_findings(world.reg) == []


def test_conditional_on_tracks_the_open_material_questions_a_support_rests_on(world):
    fact = client_fact(world, "40 heads", "40")
    rec = add(world.reg, K.RECOMMENDATION, T.RecommendationPayload(
        statement="run with the smaller team", decision_id=world.decision.id, supports=(fact.id,)),
        decision_id=world.decision.id)
    question = add(world.reg, K.QUESTION, T.QuestionPayload(
        text="is that headcount permanent staff only?", material=True), derived=(fact.id,), status=S.OPEN)

    assert conditional_on(world.reg, world.reg.get(rec.id)) == (question.id,)
    changed = refresh_conditional_on(world.reg)
    assert [e.id for e in changed] == [rec.id]
    assert world.reg.get(rec.id).payload.conditional_on == (question.id,)

    advance(world.reg, question, S.RESOLVED, A.CLIENT, "client:turn:2")
    refresh_conditional_on(world.reg)

    assert world.reg.get(rec.id).payload.conditional_on == ()
    assert len(world.reg.lineage(rec.id)) >= 3, "becoming and ceasing to be conditional are both visible"
    assert refresh_conditional_on(world.reg) == []


# ---------------------------------------------------------------------------
# 9. the seams: what C11, C13 and C8 read this module through
# ---------------------------------------------------------------------------

def _amend_infeasible(world, objective, projection):
    """The objective as a CALCULATION method leaves it (financial_model, FM3):
    amended by the calculator, back at PROPOSED, citing the arithmetic."""
    return world.reg.apply(T.Supersede(objective.id, replace(
        world.reg.get(objective.id), status=S.PROPOSED,
        payload=replace(objective.payload, feasibility=T.Feasibility.INFEASIBLE_ON_FACTS),
        provenance=replace(objective.provenance, actor=A.CALCULATOR, actor_ref="calc:financial_model",
                           derived_from=objective.provenance.derived_from + (projection.id,)))))


def _method_already_refuted(world, objective, projection):
    """The whole record a CALCULATION method leaves behind: the amended
    objective, a CONFLICT keyed on the OBJECTIVE's own id, and the
    DECISION_REQUIRED citing the objective - the row L12 counts as asked."""
    amended = _amend_infeasible(world, objective, projection)
    conflict = add(world.reg, K.CONFLICT, T.ConflictPayload(
        kind=CK.OBJECTIVE_VS_FEASIBILITY, subject_id=objective.id,
        conclusions=(T.ConflictConclusion(entity_id=objective.id,
                                          statement="the objective targets 20 heads",
                                          evidence=(objective.id,)),
                     T.ConflictConclusion(entity_id=projection.id,
                                          statement="the registered figures give 35 heads",
                                          evidence=(projection.id,))),
        relation_to_central_decision=T.RelationToCentralDecision.CONSTRAINS,
        authority_required=AU.CLIENT),
        actor=A.METHOD, ref="method:financial_model@1", derived=(objective.id, projection.id),
        status=S.OPEN, relation=T.RelationToCentralDecision.CONSTRAINS, decision_id=world.decision.id)
    # The objective is named as the OPTION and the arithmetic as the lineage,
    # which is one of the two shapes L12 counts as asked. Reading only
    # derived_from here would call this objective unasked and ask it again.
    add(world.reg, K.DECISION_REQUIRED, T.DecisionRequiredPayload(
        text="change the target, change the scope, or accept the shortfall",
        from_authority=AU.CLIENT, decision_id=world.decision.id, options=(objective.id,)),
        actor=A.METHOD, ref="method:financial_model@1", derived=(projection.id,),
        status=S.OPEN, relation=T.RelationToCentralDecision.CONSTRAINS, decision_id=world.decision.id)
    return amended, conflict


def test_an_objective_a_method_already_refuted_is_not_refuted_twice(world):
    """MUTATION 'drop the already-refuted guard' and MUTATION 'ask the client a
    second time' (C11): the method keys its conflict on the OBJECTIVE and its
    decision on the objective too, while query 3 keys on the MEASURE - so
    neither the fingerprint nor the conflict id can see that it was already
    said. Without the guard the client is put one question twice under two
    subjects and L12 counts two decisions for one objective."""
    baseline = client_fact(world, "40 heads", "40")
    objective = _objective(world, "20")
    projection = calculated_fact(world, "35", (baseline,), dims=LATER)
    _amended, theirs = _method_already_refuted(world, objective, projection)

    written = detect_conflicts(world.reg)

    assert written == [], "the verdict was already recorded, by whoever found it"
    assert [c.id for c in conflicts_of(world.reg)] == [theirs.id]
    assert len(world.reg.query(K.DECISION_REQUIRED, status=S.OPEN)) == 1, "asked once"
    assert world.reg.infeasible_objectives_without_decision() == [], "L12 still satisfied"
    assert world.reg.get(objective.id).payload.feasibility is T.Feasibility.INFEASIBLE_ON_FACTS
    amenders = [r.provenance.actor_ref for r in world.reg.lineage(objective.id)]
    assert "calculator" not in amenders, "query 3 did not amend an objective a method had amended"
    assert amenders.count("calc:financial_model") == 1


def test_an_amended_objective_no_conflict_records_is_still_refuted_here(world):
    """The negative control for the same guard: both halves are required. A
    feasibility flag with no conflict behind it is a verdict nobody was told,
    and skipping on the flag alone would bury it."""
    baseline = client_fact(world, "40 heads", "40")
    objective = _objective(world, "20")
    projection = calculated_fact(world, "35", (baseline,), dims=LATER)
    _amend_infeasible(world, objective, projection)

    detect_conflicts(world.reg)

    conflict = only_conflict(world.reg)
    assert conflict.payload.kind is CK.OBJECTIVE_VS_FEASIBILITY
    assert conflict.payload.subject_id == world.measure.id, "our subject is the measure"
    assert world.reg.infeasible_objectives_without_decision() == [], "and now the client has been asked"


def test_one_objective_already_asked_about_does_not_silence_the_next(world):
    """The guard is per objective, never per kind: a second target on the same
    measure is still held against the same arithmetic."""
    baseline = client_fact(world, "40 heads", "40")
    first = _objective(world, "20")
    projection = calculated_fact(world, "35", (baseline,), dims=LATER)
    _method_already_refuted(world, first, projection)
    second = _objective(world, "22")

    detect_conflicts(world.reg)

    assert {c.payload.subject_id for c in conflicts_of(world.reg)} == {first.id, world.measure.id}
    assert world.reg.get(second.id).payload.feasibility is T.Feasibility.INFEASIBLE_ON_FACTS
    assert len(world.reg.query(K.DECISION_REQUIRED, status=S.OPEN)) == 2, "one question per objective"


def _specialist_hypothesis(world, issue, verdict, assignment):
    """One specialist's PROPOSED conclusion, under its assignment's actor_ref,
    exactly as specialists/runner.py writes it."""
    return add(world.reg, K.HYPOTHESIS, T.HypothesisPayload(
        text=f"the workshop is people-bound ({verdict})", issue_id=issue.id, verdict=verdict),
        actor=A.SPECIALIST, ref=f"specialist:{assignment}", derived=(issue.id,), status=S.PROPOSED,
        relation=T.RelationToCentralDecision.CONSTRAINS, decision_id=world.decision.id)


def _issue(world):
    return add(world.reg, K.ISSUE, T.IssuePayload(
        text="is the workshop people-bound?", interrogative=T.Interrogative.WHETHER, target_kind=K.FACT))


def test_two_assignments_disagreeing_on_one_issue_are_a_conflict_never_a_merge(world):
    """C13: the runner deliberately never reconciles, so two PROPOSED entities
    of one kind on one subject from two assignments arrive here intact. This
    module records the disagreement and leaves both conclusions standing -
    nothing averages the verdicts, prefers the later assignment, or drops the
    quieter one."""
    issue = _issue(world)
    supported = _specialist_hypothesis(world, issue, "supported", "ASG-1")
    refuted = _specialist_hypothesis(world, issue, "refuted", "ASG-2")

    detect_conflicts(world.reg)

    conflict = only_conflict(world.reg)
    assert conflict.payload.kind is CK.SPECIALIST_DISAGREEMENT
    assert conflict.payload.subject_id == issue.id
    assert {c.entity_id for c in conflict.payload.conclusions} == {supported.id, refuted.id}
    assert conflict.payload.recommended_resolution is None, "precedence orders records, not judgements"
    assert conflict.payload.authority_required is AU.DECISION_OWNER
    for written in (supported, refuted):
        current = world.reg.get(written.id)
        assert current.status is S.PROPOSED, "both conclusions still stand"
        assert current.payload.verdict == written.payload.verdict, "neither verdict was rewritten"
        assert current.provenance.actor_ref == written.provenance.actor_ref, "each still names its assignment"


def test_an_untested_verdict_is_not_a_disagreement(world):
    """The negative control: a specialist that has not concluded contradicts
    nobody, so an assignment still running is never put to a decision owner."""
    issue = _issue(world)
    _specialist_hypothesis(world, issue, "supported", "ASG-1")
    _specialist_hypothesis(world, issue, UNTESTED_VERDICT, "ASG-2")

    detect_conflicts(world.reg)

    assert conflicts_of(world.reg) == []


def test_a_conflict_is_a_client_question_only_while_open_and_the_clients_to_settle(world):
    """C8 selects the conflicts it turns into client questions on exactly two
    structural fields - status OPEN and authority_required CLIENT - and on no
    prose. Both halves are pinned here: an open judgement the consultant may
    close is not selected, and neither is the client's own conflict once it is
    settled, though it still names the client."""
    board = source(world, "board pack", BOARD, T.RecordClass.MANAGEMENT_REPORT, confirmed=True)
    operations = source(world, "operations review", OPERATIONS, T.RecordClass.MANAGEMENT_REPORT, confirmed=True)
    a = record_fact(world, board, "47", T.RecordClass.MANAGEMENT_REPORT, "47 heads", confirm=True)
    record_fact(world, operations, "48", T.RecordClass.MANAGEMENT_REPORT, "48 heads", confirm=True)
    tradeoff(world, "3", relation=T.RelationToCentralDecision.INFORMS, material=False)
    tradeoff(world, "5", relation=T.RelationToCentralDecision.INFORMS, material=False)

    detect_conflicts(world.reg)

    by_kind = {c.payload.kind: c for c in conflicts_of(world.reg)}
    assert set(by_kind) == {CK.VALUE, CK.SPECIALIST_DISAGREEMENT}
    selected = world.reg.query(K.CONFLICT, status=S.OPEN, where={"authority_required": AU.CLIENT})
    assert [c.id for c in selected] == [by_kind[CK.VALUE].id]
    judgement = by_kind[CK.SPECIALIST_DISAGREEMENT]
    assert judgement.status is S.OPEN and judgement.payload.authority_required is AU.CONSULTANT

    resolve(world.reg, by_kind[CK.VALUE].id, chosen_entity_id=a.id, actor=A.CLIENT,
            actor_ref="client:turn:3", rationale="the board pack is the one we plan on")

    settled = world.reg.get(by_kind[CK.VALUE].id)
    assert settled.status is S.RESOLVED and settled.payload.authority_required is AU.CLIENT
    assert world.reg.query(K.CONFLICT, status=S.OPEN, where={"authority_required": AU.CLIENT}) == []
