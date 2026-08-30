"""C11 quantified methods: market_competitor, market_sizing, scenario,
option_evaluation, cost_benefit and financial_model.

Each test names the law it pins. The four mutations the work breakdown
requires are caught here:

  allow a coined fraction          -> test_a_rate_fact_is_never_a_scenario_fraction
                                      test_the_validator_refuses_a_calculated_fact_that_scaled_a_rate_fact
  average scorings                 -> test_two_scorings_of_one_pair_become_a_conflict_never_an_average
  let the consultant's weights rank-> test_consultant_weights_list_the_options_and_never_rank_them
  confirm an uncited external fact -> test_an_external_fact_without_a_locator_is_refused_and_asked_for
                                      test_the_validator_refuses_an_external_fact_written_confirmed

Every method output is put through the real EngagementRegistry wherever the
test is about what gets recorded: a delta a method builds but the registry
would refuse is not a result.
"""
from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal

import pytest

from app.engine import types as T
from app.engine.calc.arith import DecimalCalculator
from app.engine.llm import FakeProvider
from app.engine.methods.contract import METHODS, MethodContext, MethodResult

import app.engine.methods.builtin  # noqa: F401  (registration by import)
from app.engine.methods.builtin import financial_model as FM
from app.engine.methods.builtin import market_competitor as MC
from app.engine.methods.builtin import market_sizing as MS
from app.engine.methods.builtin import option_evaluation as OE
from app.engine.methods.builtin import scenario as SC

K = T.Kind
AS_OF = "2025-12-31"


# ---------------------------------------------------------------------------
# builders: rows the registry assigns ids to, so a test can hold several of a
# kind (the shared conftest entity always occupies <PREFIX>-1)
# ---------------------------------------------------------------------------

def build(reg, kind, payload, *, actor=T.Actor.PARTNER, status=T.Status.PROPOSED, derived_from=("EVI-1",),
          locator=None, decision="DEC-1", weight=0.5, relation=T.RelationToCentralDecision.INFORMS):
    """An entity the registry has NOT seen: used where the law under test is a
    validator, which must judge a row the registry would refuse at the door."""
    return T.make_entity(
        kind=kind, engagement_id=reg.engagement_id, payload=payload,
        provenance=T.Provenance(actor=actor, actor_ref=f"{actor.value}:test", derived_from=tuple(derived_from),
                                source_locator=locator),
        confidence=T.Confidence(None), relevance=T.Relevance(decision, weight),
        relation=relation, status=status)


def add(reg, kind, payload, **kw):
    return reg.apply(T.Add(build(reg, kind, payload, **kw)))


def money(value, *, currency="EUR", period="FY25", period_basis="year", as_of=AS_OF, scope=None, definition=None):
    return T.Quantity(Decimal(value), currency, T.UnitFamily.MONEY,
                      T.Dimensions(currency=currency, period=period, period_basis=period_basis,
                                   as_of=as_of, scope=scope, definition=definition))


def count(value, unit="units", *, as_of=AS_OF):
    return T.Quantity(Decimal(value), unit, T.UnitFamily.COUNT, T.Dimensions(as_of=as_of))


def fraction(value, *, as_of=AS_OF):
    return T.Quantity(Decimal(value), "%", T.UnitFamily.RATE, T.Dimensions(as_of=as_of))


def fact(reg, statement, quantity=None, *, basis=T.FactBasis.DOCUMENT_EXTRACTED, measure_id=None,
         derived_from=("EVI-1",)):
    return add(reg, K.FACT, T.FactPayload(statement=statement, basis=basis, measure_id=measure_id,
                                          quantity=quantity), derived_from=derived_from)


def seeded(registry):
    """One turn, one central decision, one context row, one measure and one
    issue node: the frame every method here runs inside."""
    reg = registry()
    add(reg, K.EVIDENCE_SOURCE,
        T.EvidenceSourcePayload(name="turn 1", source_kind=T.SourceKind.CONVERSATION_TURN,
                                record_class=T.RecordClass.UNKNOWN, text="the client said things",
                                received_at="2026-01-01T00:00:00+00:00"),
        derived_from=())                                                        # EVI-1
    add(reg, K.DECISION, T.DecisionPayload(statement="which path", role=T.DecisionRole.CENTRAL))   # DEC-1
    add(reg, K.BUSINESS_CONTEXT, T.BusinessContextPayload(text="a business", aspect="what_it_does"))  # BCX-1
    add(reg, K.MEASURE, T.MeasurePayload(name="run cost", unit_family=T.UnitFamily.MONEY))         # MEA-1
    add(reg, K.ISSUE, T.IssuePayload(text="how much?", interrogative=T.Interrogative.HOW_MUCH,
                                     target_kind=K.COST, quantified=True))                          # ISS-1
    return reg


def ctx_for(reg, method_id, provider=None, **settings):
    return MethodContext(registry=reg, provider=provider or FakeProvider(), calc=DecimalCalculator(reg),
                         actor=T.Actor.METHOD, actor_ref=f"method:{method_id}@1", issue_ids=("ISS-1",),
                         settings=settings)


def run(reg, method_id, provider=None, **settings):
    return METHODS.get(method_id).run(ctx_for(reg, method_id, provider, **settings))


def added(result, kind):
    return [d.entity for d in result.deltas if isinstance(d, T.Add) and d.entity.kind == kind]


def superseded(result, kind):
    return [d.entity for d in result.deltas if isinstance(d, T.Supersede) and d.entity.kind == kind]


def calculated(result):
    return [e for e in added(result, K.FACT) if e.payload.basis is T.FactBasis.CALCULATED]


def sheet(*outputs, questions=()):
    return json.dumps({"outputs": list(outputs), "questions": list(questions)})


def output(kind="fact", text="an external claim", fields=None, derived_from=("BCX-1",), quantity_from=None):
    return {"kind": kind, "text": text, "fields": dict(fields or {}),
            "quantity_from": quantity_from, "derived_from": list(derived_from)}


def provider_for(method_id, *bodies):
    return FakeProvider(script={f"method_{method_id}": list(bodies)})


# ===========================================================================
# the six specs
# ===========================================================================

def test_calculation_and_deterministic_methods_declare_no_model_calls():
    # M1 at the level of this component: a method that claims exactness never
    # asks a model for its numbers.
    for method_id in ("cost_benefit", "financial_model", "scenario", "option_evaluation"):
        spec = METHODS.get(method_id).spec
        assert spec.execution in T.FREE_EXECUTION and spec.max_model_calls == 0


def test_research_methods_run_under_an_assignment_and_declare_their_budget():
    for method_id in ("market_competitor", "market_sizing"):
        spec = METHODS.get(method_id).spec
        assert spec.execution is T.ExecutionType.RESEARCH
        assert spec.execution in T.ASSIGNMENT_EXECUTION and spec.max_model_calls == 3


def test_the_declared_shapes_are_the_ones_the_design_table_states():
    shapes = {mid: {(s.interrogative, s.target_kind, s.quantified) for s in METHODS.get(mid).spec.applicability}
              for mid in ("market_competitor", "market_sizing", "scenario", "option_evaluation",
                          "cost_benefit", "financial_model")}
    I = T.Interrogative
    assert shapes["market_competitor"] == {(I.WHAT, K.FACT, False)}
    assert shapes["market_sizing"] == {(I.HOW_MUCH, K.BENEFIT, True), (I.HOW_MUCH, K.EXPECTED_OUTCOME, True)}
    assert shapes["scenario"] == {(I.WHETHER, K.EXPECTED_OUTCOME, True), (I.HOW_MUCH, K.EXPECTED_OUTCOME, True)}
    assert shapes["option_evaluation"] == {(I.WHICH, K.DECISION, False)}
    assert shapes["cost_benefit"] == {(I.HOW_MUCH, K.COST, True), (I.HOW_MUCH, K.BENEFIT, True)}
    assert shapes["financial_model"] == {(I.HOW_MUCH, K.COST, True), (I.HOW_MUCH, K.BENEFIT, True),
                                         (I.HOW_MUCH, K.EXPECTED_OUTCOME, True), (I.WHETHER, K.OBJECTIVE, True)}


def test_no_engagement_type_or_client_vocabulary_in_any_module():
    # Universality is a property of the type system: a method that named an
    # engagement type would be a capability pack (spec section 3).
    import inspect
    # engagement types only, and no client name is written here either: a
    # negative control that spells one out would put the vocabulary it forbids
    # into the repository (spec section 8).
    banned = ("acquisition", "market_entry", "cost_reduction", "turnaround",
              "restructuring", "product_launch", "if engagement")
    for module in (MC, MS, SC, OE, FM):
        source = inspect.getsource(module).lower()
        for word in banned:
            assert word not in source, f"{module.__name__} names {word!r}"


# ===========================================================================
# financial_model
# ===========================================================================

def test_financial_model_refuses_incomparable_inputs_and_opens_a_pin_question(registry):
    reg = seeded(registry)
    fact(reg, "run cost is 900", money("900"), measure_id="MEA-1")
    # The second figure's currency was never pinned. Absence is a typed hole:
    # nothing is totalled and the exact dimension is asked for (FM1).
    fact(reg, "another run cost", T.Quantity(Decimal("1200"), "EUR", T.UnitFamily.MONEY,
                                             T.Dimensions(currency=None, period="FY25",
                                                          period_basis="year", as_of=AS_OF)),
         measure_id="MEA-1")
    result = run(reg, "financial_model")
    assert calculated(result) == []
    assert len(result.questions) == 1
    assert "currency" in result.questions[0].text
    assert result.questions[0].strategy is T.FillStrategy.ASK_CLIENT


def test_financial_model_totals_the_registered_figures_with_a_recomputable_formula(registry):
    reg = seeded(registry)
    a = fact(reg, "run cost is 900", money("900"), measure_id="MEA-1")
    b = fact(reg, "run cost is 1200", money("1200"), measure_id="MEA-1")
    result = run(reg, "financial_model")
    rows = calculated(result)
    assert len(rows) == 1
    assert rows[0].payload.formula == f"{a.id} + {b.id}"
    assert rows[0].payload.inputs == (a.id, b.id)
    assert rows[0].payload.quantity.value == Decimal("2100.00")
    stored = reg.apply(T.Add(rows[0]))
    # L7's demand, at the source: the stored row recomputes exactly.
    assert DecimalCalculator(reg).recompute(stored, reg) is True


def test_an_infeasible_objective_is_amended_with_a_conflict_and_a_decision_required(registry):
    reg = seeded(registry)
    fact(reg, "run cost is 900", money("900"), measure_id="MEA-1")
    fact(reg, "run cost is 1200", money("1200"), measure_id="MEA-1")
    objective = add(reg, K.OBJECTIVE, T.ObjectivePayload(text="save 9000", measure_id="MEA-1",
                                                         target=money("9000")))
    result = run(reg, "financial_model")
    reg.apply_all(result.deltas)

    amended = reg.get(objective.id)
    assert amended.payload.feasibility is T.Feasibility.INFEASIBLE_ON_FACTS
    assert FM.FEASIBILITY_TESTED in amended.labels
    # the original is still there, visibly retired: lineage is the row history
    assert [r.status for r in reg.lineage(objective.id)][:2] == [T.Status.PROPOSED, T.Status.SUPERSEDED]

    conflicts = reg.query(K.CONFLICT, status=T.Status.OPEN)
    assert len(conflicts) == 1
    assert conflicts[0].payload.kind is T.ConflictKind.OBJECTIVE_VS_FEASIBILITY
    assert conflicts[0].payload.authority_required is T.Authority.CLIENT
    # the conflict shows both sides, each with its own evidence
    assert {c.entity_id for c in conflicts[0].payload.conclusions} >= {objective.id}
    assert reg.is_material(conflicts[0]) is True
    # L12: an infeasible objective that was put to the client is not a finding
    assert reg.infeasible_objectives_without_decision() == []
    assert reg.query(K.DECISION_REQUIRED)[0].payload.from_authority is T.Authority.CLIENT
    # and the shortfall itself exists as arithmetic, not as prose
    assert any(f.payload.formula for f in reg.calculated_facts())


def test_a_confirmed_objective_returns_to_proposed_when_the_arithmetic_amends_it(registry):
    # FM4: the engine may state what the arithmetic shows; it may not keep the
    # client's confirmation on a statement the client has not seen.
    reg = seeded(registry)
    fact(reg, "run cost is 900", money("900"), measure_id="MEA-1")
    fact(reg, "run cost is 1200", money("1200"), measure_id="MEA-1")
    objective = add(reg, K.OBJECTIVE, T.ObjectivePayload(text="save 9000", measure_id="MEA-1",
                                                         target=money("9000")),
                    actor=T.Actor.CLIENT, status=T.Status.CONFIRMED)
    assert objective.status is T.Status.CONFIRMED
    result = run(reg, "financial_model")
    reg.apply_all(result.deltas)
    assert reg.get(objective.id).status is T.Status.PROPOSED


def test_a_reachable_target_is_marked_feasible_and_puts_nothing_to_the_client(registry):
    reg = seeded(registry)
    fact(reg, "run cost is 900", money("900"), measure_id="MEA-1")
    fact(reg, "run cost is 1200", money("1200"), measure_id="MEA-1")
    objective = add(reg, K.OBJECTIVE, T.ObjectivePayload(text="save 500", measure_id="MEA-1",
                                                         target=money("500")))
    result = run(reg, "financial_model")
    reg.apply_all(result.deltas)
    assert reg.get(objective.id).payload.feasibility is T.Feasibility.FEASIBLE
    assert reg.query(K.CONFLICT) == [] and reg.query(K.DECISION_REQUIRED) == []


def test_no_feasibility_verdict_when_the_target_is_not_one_kind_of_thing(registry):
    # A target in heads against figures in euros is not infeasible; it is
    # untestable. The refusal is recorded and the objective is left alone.
    reg = seeded(registry)
    fact(reg, "run cost is 900", money("900"), measure_id="MEA-1")
    fact(reg, "run cost is 1200", money("1200"), measure_id="MEA-1")
    objective = add(reg, K.OBJECTIVE, T.ObjectivePayload(text="reach 40 heads", measure_id="MEA-1",
                                                         target=count("40", "heads")))
    result = run(reg, "financial_model")
    assert superseded(result, K.OBJECTIVE) == []
    assert added(result, K.CONFLICT) == []
    assert [f.law for f in result.findings] == ["M.financial_model.refused_comparison"]
    assert result.findings[0].blocks_final is False
    reg.apply_all(result.deltas)
    assert reg.get(objective.id).payload.feasibility is T.Feasibility.UNTESTED


def test_an_objective_on_a_measure_with_no_figures_stays_untested(registry):
    # Absent evidence is not evidence of infeasibility.
    reg = seeded(registry)
    objective = add(reg, K.OBJECTIVE, T.ObjectivePayload(text="save 9000", measure_id="MEA-1",
                                                         target=money("9000")))
    result = run(reg, "financial_model")
    assert result.deltas == () and result.findings == ()
    assert reg.get(objective.id).payload.feasibility is T.Feasibility.UNTESTED


def test_financial_model_does_not_total_its_own_totals(registry):
    reg = seeded(registry)
    fact(reg, "run cost is 900", money("900"), measure_id="MEA-1")
    fact(reg, "run cost is 1200", money("1200"), measure_id="MEA-1")
    reg.apply_all(run(reg, "financial_model").deltas)
    second = run(reg, "financial_model")
    assert calculated(second) == []


# ===========================================================================
# scenario
# ===========================================================================

def approved(reg, statement="a 10% uplift", value="0.10"):
    return add(reg, K.ASSUMPTION, T.AssumptionPayload(statement=statement, quantity=fraction(value),
                                                      approval=T.ApprovalState.APPROVED))


def test_a_scenario_multiplies_a_registered_figure_by_an_approved_assumption(registry):
    reg = seeded(registry)
    base = fact(reg, "revenue is 1200", money("1200"), measure_id="MEA-1")
    assumption = approved(reg)
    result = run(reg, "scenario")
    rows = calculated(result)
    assert len(rows) == 1
    assert rows[0].payload.formula == f"{base.id} * {assumption.id}"
    assert rows[0].payload.quantity.value == Decimal("120.00")
    outcomes = added(result, K.EXPECTED_OUTCOME)
    assert len(outcomes) == 1 and outcomes[0].payload.basis == "calculated"
    # the outcome states the calculated figure; it carries none of its own
    assert outcomes[0].payload.quantity == rows[0].payload.quantity
    assert outcomes[0].payload.supports == rows[0].payload.inputs
    reg.apply_all(result.deltas)


def test_a_rate_fact_is_never_a_scenario_fraction(registry):
    # SC1 (mutation: allow a coined fraction). A fraction that lives on a FACT
    # has nobody to approve it; multiplying by it would look agreed when it is
    # not. With no assumption registered there is simply no scenario.
    reg = seeded(registry)
    fact(reg, "revenue is 1200", money("1200"), measure_id="MEA-1")
    rate_fact = fact(reg, "uplift is 10%", fraction("0.10"))
    assert SC.fraction_carriers(reg) == []
    result = run(reg, "scenario")
    assert result.deltas == ()
    # and it stays out even when a lawful assumption exists beside it
    assumption = approved(reg)
    rows = calculated(run(reg, "scenario"))
    assert len(rows) == 1
    assert rate_fact.id not in rows[0].payload.inputs
    assert rows[0].payload.inputs[-1] == assumption.id


def test_the_validator_refuses_a_calculated_fact_that_scaled_a_rate_fact(registry):
    # The same law, checked on a finished result: a later edit to the guard
    # alone does not get a coined fraction past the spec's validators.
    reg = seeded(registry)
    base = fact(reg, "revenue is 1200", money("1200"), measure_id="MEA-1")
    rate_fact = fact(reg, "uplift is 10%", fraction("0.10"))
    doctored = build(reg, K.FACT, T.FactPayload(
        statement="scaled", basis=T.FactBasis.CALCULATED, quantity=money("120"),
        formula=f"{base.id} * {rate_fact.id}", inputs=(base.id, rate_fact.id)))
    findings = SC.fraction_from_assumption(reg, MethodResult(deltas=(T.Add(doctored),)))
    assert [f.law for f in findings] == ["M.scenario.coined_fraction"]
    assert findings[0].entity_ids == (rate_fact.id,)
    # the negative control: the same shape with an assumption is clean
    assumption = approved(reg)
    clean = replace(doctored, payload=replace(doctored.payload, formula=f"{base.id} * {assumption.id}",
                                              inputs=(base.id, assumption.id)))
    assert SC.fraction_from_assumption(reg, MethodResult(deltas=(T.Add(clean),))) == []


def test_an_unapproved_assumption_is_asked_about_not_computed(registry):
    # SC2: the calculator refuses a share nobody with authority stated, and
    # the refusal becomes a question for the client, who owns assumptions.
    reg = seeded(registry)
    fact(reg, "revenue is 1200", money("1200"), measure_id="MEA-1")
    unapproved = add(reg, K.ASSUMPTION, T.AssumptionPayload(statement="a 10% uplift", quantity=fraction("0.10"),
                                                            approval=T.ApprovalState.UNAPPROVED))
    result = run(reg, "scenario")
    assert calculated(result) == []
    assert [f.law for f in result.findings] == ["M.scenario.refused_product"]
    assert len(result.questions) == 1 and unapproved.id in result.questions[0].text
    assert result.questions[0].asks_for == (T.AsksFor(K.ASSUMPTION),)


def test_a_scenario_over_unpinned_dimensions_asks_rather_than_computes(registry):
    reg = seeded(registry)
    add(reg, K.FACT, T.FactPayload(statement="revenue", basis=T.FactBasis.DOCUMENT_EXTRACTED,
                                   quantity=T.Quantity(Decimal("1200"), "EUR", T.UnitFamily.MONEY,
                                                       T.Dimensions(currency=None, as_of=AS_OF))))
    approved(reg)
    result = run(reg, "scenario")
    assert calculated(result) == []
    assert len(result.questions) == 1 and "currency" in result.questions[0].text


def test_the_scenario_count_is_bounded_by_the_declared_fanout_setting(registry):
    # SC3: dynamic, not hardcoded. How many scenarios exist is a property of
    # the engagement; the bound is a declared setting, read at run time.
    reg = seeded(registry)
    for i in range(3):
        fact(reg, f"revenue {i}", money(str(1000 + i)), measure_id="MEA-1")
    approved(reg, "uplift a", "0.10")
    approved(reg, "uplift b", "0.20")
    assert len(calculated(run(reg, "scenario", MAX_FANOUT=2))) == 2
    assert len(calculated(run(reg, "scenario", MAX_FANOUT=5))) == 5
    assert len(calculated(run(reg, "scenario"))) == T.BOUNDS["MAX_FANOUT"]


def test_a_scenario_is_not_rescaled_by_its_own_assumption_next_round(registry):
    reg = seeded(registry)
    fact(reg, "revenue is 1200", money("1200"), measure_id="MEA-1")
    approved(reg)
    reg.apply_all(run(reg, "scenario").deltas)
    assert calculated(run(reg, "scenario")) == []


# ===========================================================================
# option_evaluation
# ===========================================================================

def options_and_criteria(reg, *, weight=0.2, weight_set_by=T.Authority.CLIENT, second_weight=0.8):
    """Two options and two criteria. Both options are evidenced on the first
    criterion, only the second option on the second, so a lawful ranking
    reorders them and an unlawful one leaves registration order visible."""
    one = add(reg, K.OPTION, T.OptionPayload(text="stay", decision_id="DEC-1", evidence=("EVI-1",)))
    two = add(reg, K.OPTION, T.OptionPayload(text="move", decision_id="DEC-1", evidence=("EVI-1",)))
    c1 = add(reg, K.EVALUATION_CRITERION, T.EvaluationCriterionPayload(
        text="run cost", decision_id="DEC-1", weight=weight, weight_set_by=weight_set_by))
    c2 = add(reg, K.EVALUATION_CRITERION, T.EvaluationCriterionPayload(
        text="fit", decision_id="DEC-1", weight=second_weight, weight_set_by=weight_set_by))
    fact(reg, "stay costs 900", money("900"), measure_id="MEA-1", derived_from=(one.id, c1.id))
    fact(reg, "move costs 1200", money("1200"), measure_id="MEA-1", derived_from=(two.id, c1.id))
    fact(reg, "move fits 5", money("5"), derived_from=(two.id, c2.id))
    return one, two, c1, c2


def test_two_scorings_of_one_pair_become_a_conflict_never_an_average(registry):
    # O1 (mutation: average scorings). Two records give one option two scores
    # on one criterion. The mean of 900 and 1200 is a number neither record
    # states, so no score is written and the disagreement is registered.
    reg = seeded(registry)
    one, two, c1, _c2 = options_and_criteria(reg)
    fact(reg, "stay costs 1200 in the other system", money("1200"), measure_id="MEA-1",
         derived_from=(one.id, c1.id))
    result = run(reg, "option_evaluation")

    conflicts = added(result, K.CONFLICT)
    assert len(conflicts) == 1
    payload = conflicts[0].payload
    assert payload.kind is T.ConflictKind.VALUE and payload.subject_id == c1.id
    assert len(payload.conclusions) == 2
    assert all(c.evidence for c in payload.conclusions)
    scored = {(s.option_id, s.criterion_id): s.score for t in added(result, K.TRADE_OFF) for s in t.payload.scores}
    assert (one.id, c1.id) not in scored
    assert Decimal("1050") not in set(scored.values())
    reg.apply_all(result.deltas)


def test_client_weights_rank_the_options_by_the_coverage_they_are_evidenced_on(registry):
    reg = seeded(registry)
    one, two, _c1, _c2 = options_and_criteria(reg, weight_set_by=T.Authority.CLIENT)
    trade_offs = added(run(reg, "option_evaluation"), K.TRADE_OFF)
    assert len(trade_offs) == 1
    assert OE.RANKED_LABEL in trade_offs[0].labels
    assert trade_offs[0].payload.option_ids == (two.id, one.id)


def test_consultant_weights_list_the_options_and_never_rank_them(registry):
    # O3 (mutation: let the consultant's weights rank). A consultant who both
    # weights the criteria and orders the options has made the client's
    # decision for them.
    reg = seeded(registry)
    one, two, c1, c2 = options_and_criteria(reg, weight_set_by=T.Authority.CONSULTANT)
    result = run(reg, "option_evaluation")
    trade_off = added(result, K.TRADE_OFF)[0]
    assert OE.LISTED_LABEL in trade_off.labels and OE.RANKED_LABEL not in trade_off.labels
    assert trade_off.payload.option_ids == (one.id, two.id)          # registration order, not coverage
    weights_asked = [q for q in result.questions if c1.id in q.text and c2.id in q.text]
    assert len(weights_asked) == 1 and weights_asked[0].asks_for == (T.AsksFor(K.EVALUATION_CRITERION),)


def test_an_unweighted_criterion_produces_a_listing_not_a_ranking(registry):
    reg = seeded(registry)
    one, two, _c1, _c2 = options_and_criteria(reg, weight=None, second_weight=None)
    trade_off = added(run(reg, "option_evaluation"), K.TRADE_OFF)[0]
    assert OE.LISTED_LABEL in trade_off.labels
    assert trade_off.payload.option_ids == (one.id, two.id)


def test_the_ranking_validator_refuses_a_ranked_label_without_client_weights(registry):
    reg = seeded(registry)
    _one, _two, _c1, _c2 = options_and_criteria(reg, weight_set_by=T.Authority.CONSULTANT)
    listed = added(run(reg, "option_evaluation"), K.TRADE_OFF)[0]
    relabelled = replace(listed, labels=(OE.RANKED_LABEL,))
    findings = OE.ranking_only_on_client_weights(reg, MethodResult(deltas=(T.Add(relabelled),)))
    assert [f.law for f in findings] == ["M.option_evaluation.ranked_without_client_weights"]
    assert OE.ranking_only_on_client_weights(reg, MethodResult(deltas=(T.Add(listed),))) == []


def test_a_material_trade_off_is_put_to_the_decision_owner(registry):
    # O4: a trade-off on the central decision that the options do not resolve
    # the same way is the owner's to make.
    reg = seeded(registry)
    one, two, _c1, _c2 = options_and_criteria(reg)
    result = run(reg, "option_evaluation")
    trade_off = added(result, K.TRADE_OFF)[0]
    assert trade_off.payload.material is True
    # a material trade-off is owned by the decision owner, derived, not chosen
    assert trade_off.info_type is T.InfoType.MATERIAL_TRADE_OFF
    assert trade_off.authority is T.Authority.DECISION_OWNER
    required = added(result, K.DECISION_REQUIRED)
    assert len(required) == 1
    assert required[0].payload.from_authority is T.Authority.DECISION_OWNER
    assert set(required[0].payload.options) == {one.id, two.id}
    assert required[0].status is T.Status.OPEN
    reg.apply_all(result.deltas)


def test_the_validator_fails_a_material_trade_off_that_was_never_put(registry):
    reg = seeded(registry)
    options_and_criteria(reg)
    result = run(reg, "option_evaluation")
    material = MethodResult(deltas=tuple(d for d in result.deltas
                                         if not (isinstance(d, T.Add) and d.entity.kind is K.DECISION_REQUIRED)))
    assert result.deltas != material.deltas
    findings = OE.material_trade_off_reaches_the_owner(reg, material)
    assert [f.law for f in findings] == ["M.option_evaluation.material_trade_off_not_put"]
    assert OE.material_trade_off_reaches_the_owner(reg, result) == []


def test_every_score_cites_the_rows_it_was_read_from(registry):
    reg = seeded(registry)
    options_and_criteria(reg)
    result = run(reg, "option_evaluation")
    trade_off = added(result, K.TRADE_OFF)[0]
    assert trade_off.payload.scores
    for score in trade_off.payload.scores:
        assert score.evidence and all(reg.get(i) is not None for i in score.evidence)
    stripped = replace(trade_off, payload=replace(
        trade_off.payload, scores=tuple(replace(s, evidence=()) for s in trade_off.payload.scores)))
    findings = OE.score_cites_evidence(reg, MethodResult(deltas=(T.Add(stripped),)))
    assert findings and {f.law for f in findings} == {"M.option_evaluation.uncited_score"}


def test_an_option_with_no_evidenced_score_is_asked_about_not_scored(registry):
    # O2: no evidence, no score. The gap is a question, never a placeholder.
    reg = seeded(registry)
    one, _two, _c1, c2 = options_and_criteria(reg)
    result = run(reg, "option_evaluation")
    asked = [q for q in result.questions if one.id in q.text and c2.id in q.text]
    assert len(asked) == 1
    scored = {(s.option_id, s.criterion_id) for t in added(result, K.TRADE_OFF) for s in t.payload.scores}
    assert (one.id, c2.id) not in scored


def test_one_option_is_not_a_choice(registry):
    reg = seeded(registry)
    add(reg, K.OPTION, T.OptionPayload(text="stay", decision_id="DEC-1", evidence=("EVI-1",)))
    add(reg, K.EVALUATION_CRITERION, T.EvaluationCriterionPayload(text="cost", decision_id="DEC-1", weight=1.0,
                                                                  weight_set_by=T.Authority.CLIENT))
    assert run(reg, "option_evaluation").deltas == ()


def test_rerunning_the_evaluation_is_the_same_conclusion_not_a_second_one(registry):
    reg = seeded(registry)
    options_and_criteria(reg)
    reg.apply_all(run(reg, "option_evaluation").deltas)
    assert added(run(reg, "option_evaluation"), K.TRADE_OFF) == []


# ===========================================================================
# market_competitor
# ===========================================================================

def test_a_cited_external_fact_is_written_proposed_with_its_locator(registry):
    reg = seeded(registry)
    body = sheet(output(fields={"citation": "Statista 2026, table 4", "topic": "market size"}))
    result = run(reg, "market_competitor", provider_for("market_competitor", body))
    facts = added(result, K.FACT)
    assert len(facts) == 1
    written = facts[0]
    assert written.payload.basis is T.FactBasis.EXTERNAL_SOURCED
    assert written.provenance.source_locator == "Statista 2026, table 4"
    assert written.provenance.model_call_id
    # R2: authority is derived, and only a cited source may confirm it
    assert written.authority is T.Authority.CITED_SOURCE and written.status is T.Status.PROPOSED
    stored = reg.apply(T.Add(written))
    assert stored.status is T.Status.PROPOSED
    assert MC.external_fact_validator("market_competitor")(reg, result) == []


def test_an_external_fact_without_a_locator_is_refused_and_asked_for(registry):
    # R1 (mutation: confirm an uncited external fact). A claim with no source
    # names nothing that could confirm or refute it.
    reg = seeded(registry)
    body = sheet(output(text="competitors are consolidating", fields={}),
                 output(text="the market grew", fields={"citation": "   "}))
    result = run(reg, "market_competitor", provider_for("market_competitor", body))
    assert added(result, K.FACT) == []
    assert [f.law for f in result.findings] == ["M.market_competitor.uncited_external_fact"] * 2
    assert len(result.questions) == 2
    assert all(q.strategy is T.FillStrategy.REQUEST_DOCUMENT for q in result.questions)
    assert "competitors are consolidating" in result.questions[0].text


def test_the_validator_refuses_an_external_fact_written_confirmed(registry):
    reg = seeded(registry)
    body = sheet(output(fields={"citation": "Statista 2026, table 4"}))
    result = run(reg, "market_competitor", provider_for("market_competitor", body))
    written = added(result, K.FACT)[0]
    confirmed = replace(written, status=T.Status.CONFIRMED)
    findings = MC.external_fact_validator("market_competitor")(reg, MethodResult(deltas=(T.Add(confirmed),)))
    assert [f.law for f in findings] == ["M.market_competitor.external_fact_not_proposed"]
    uncited = replace(written, provenance=replace(written.provenance, source_locator=""))
    findings = MC.external_fact_validator("market_competitor")(reg, MethodResult(deltas=(T.Add(uncited),)))
    assert [f.law for f in findings] == ["M.market_competitor.external_fact_without_locator"]


def test_a_market_fact_carries_no_number_of_its_own(registry):
    # R3: a figure enters only by copying a registered input by id.
    reg = seeded(registry)
    known = fact(reg, "we serve 40 clients", count("40", "clients"))
    body = sheet(output(text="the addressable base is larger", fields={"citation": "p.9"},
                        derived_from=["BCX-1", known.id], quantity_from=known.id),
                 output(text="the market is 900bn", fields={"citation": "p.10"},
                        quantity_from="FCT-999"))
    result = run(reg, "market_competitor", provider_for("market_competitor", body))
    facts = added(result, K.FACT)
    assert facts[0].payload.quantity == known.payload.quantity
    assert facts[1].payload.quantity is None
    assert any(f.law == "M.market_competitor.coined_quantity" for f in result.findings)


def test_a_model_failure_yields_a_finding_and_no_deltas(registry):
    reg = seeded(registry)
    provider = FakeProvider(script={"method_market_competitor": [RuntimeError("provider down")] * 2})
    result = run(reg, "market_competitor", provider)
    assert result.deltas == () and result.questions == ()
    assert [f.law for f in result.findings] == ["M.market_competitor.model_failure"]


# ===========================================================================
# market_sizing
# ===========================================================================

def test_the_model_names_the_chain_and_the_calculator_produces_the_number(registry):
    # MS1/MS2: the model chooses ids, the calculator chooses the number.
    reg = seeded(registry)
    price = fact(reg, "price is 900", money("900"), measure_id="MEA-1")
    volume = fact(reg, "40 units", count("40"))
    body = sheet(output(text="the opportunity", fields={"basis": "calculated"},
                        derived_from=[price.id, volume.id]))
    result = run(reg, "market_sizing", provider_for("market_sizing", body))
    rows = calculated(result)
    assert len(rows) == 1
    assert rows[0].payload.formula == f"{price.id} * {volume.id}"
    assert rows[0].payload.quantity.value == Decimal("36000.00")
    assert rows[0].payload.quantity.unit_family is T.UnitFamily.MONEY
    # S2: a research method proposes; the arithmetic is confirmed after admission
    assert rows[0].status is T.Status.PROPOSED
    stored = reg.apply(T.Add(rows[0]))
    assert DecimalCalculator(reg).recompute(stored, reg) is True


def test_a_sizing_chain_of_one_is_refused(registry):
    # MS3: one registered figure under a second id is the same figure twice.
    reg = seeded(registry)
    price = fact(reg, "price is 900", money("900"), measure_id="MEA-1")
    body = sheet(output(fields={"basis": "calculated"}, derived_from=[price.id]))
    result = run(reg, "market_sizing", provider_for("market_sizing", body))
    assert result.deltas == ()
    assert [f.law for f in result.findings] == ["M.market_sizing.short_chain"]


def test_a_refused_chain_is_recorded_and_asked_for_never_estimated(registry):
    reg = seeded(registry)
    price = fact(reg, "price is 900", money("900"), measure_id="MEA-1")
    guessed = fact(reg, "10% of them", fraction("0.10"), basis=T.FactBasis.INFERRED)
    body = sheet(output(fields={"basis": "calculated"}, derived_from=[price.id, guessed.id]))
    result = run(reg, "market_sizing", provider_for("market_sizing", body))
    assert result.deltas == ()
    assert [f.law for f in result.findings] == ["M.market_sizing.refused_chain"]
    assert len(result.questions) == 1


def test_market_sizing_holds_external_claims_to_the_same_citation_law(registry):
    reg = seeded(registry)
    fact(reg, "price is 900", money("900"), measure_id="MEA-1")
    body = sheet(output(text="the market is growing", fields={"basis": "external_sourced"}),
                 output(text="the market is 900bn", fields={"basis": "external_sourced", "citation": "p.3"}),
                 output(text="something else", fields={"basis": "guesswork"}))
    result = run(reg, "market_sizing", provider_for("market_sizing", body))
    facts = added(result, K.FACT)
    assert [f.provenance.source_locator for f in facts] == ["p.3"]
    assert {f.law for f in result.findings} == {"M.market_sizing.uncited_external_fact",
                                                "M.market_sizing.unknown_basis"}


# ===========================================================================
# cost_benefit
# ===========================================================================

def test_cost_benefit_totals_costs_and_benefits_side_by_side_with_lineage(registry):
    reg = seeded(registry)
    fact(reg, "a money fact", money("900"), measure_id="MEA-1")
    c1 = add(reg, K.COST, T.CostPayload(text="licences", basis="quote", quantity=money("900")))
    c2 = add(reg, K.COST, T.CostPayload(text="services", basis="quote", quantity=money("1200")))
    b1 = add(reg, K.BENEFIT, T.BenefitPayload(text="savings", basis="quote", quantity=money("3000")))
    result = run(reg, "cost_benefit")
    rows = calculated(result)
    assert [r.payload.formula for r in rows] == [f"{c1.id} + {c2.id}", b1.id]
    assert [r.payload.quantity.value for r in rows] == [Decimal("2100.00"), Decimal("3000.00")]
    totals = added(result, K.COST) + added(result, K.BENEFIT)
    assert [t.payload.quantity for t in totals] == [r.payload.quantity for r in rows]
    assert all(t.payload.basis == "calculated" and t.payload.for_ids for t in totals)
    reg.apply_all(result.deltas)


def test_cost_benefit_asks_to_pin_a_dimension_instead_of_totalling_across_it(registry):
    reg = seeded(registry)
    fact(reg, "a money fact", money("900"), measure_id="MEA-1")
    add(reg, K.COST, T.CostPayload(text="licences", basis="quote", quantity=money("900")))
    # the second figure states no period basis at all: an unknown dimension,
    # which is a question, not a defect and not a default
    add(reg, K.COST, T.CostPayload(text="services", basis="quote", quantity=money("1200", period_basis=None)))
    result = run(reg, "cost_benefit")
    assert calculated(result) == []
    assert len(result.questions) == 1 and "period_basis" in result.questions[0].text


def test_a_calculated_fact_without_a_formula_is_flagged_as_a_coined_number(registry):
    from app.engine.methods.builtin.cost_benefit import calculated_traceable
    reg = seeded(registry)
    coined = build(reg, K.FACT, T.FactPayload(statement="2100", basis=T.FactBasis.CALCULATED,
                                              quantity=money("2100")))
    findings = calculated_traceable(reg, MethodResult(deltas=(T.Add(coined),)))
    assert [f.law for f in findings] == ["M.calc.untraceable_quantity"]


@pytest.mark.parametrize("method_id", ["cost_benefit", "financial_model", "scenario", "option_evaluation",
                                        "market_competitor", "market_sizing"])
def test_every_method_declares_validators_and_limitations(method_id):
    spec = METHODS.get(method_id).spec
    assert spec.validators and spec.limitations
    assert spec.answers and spec.applicability
