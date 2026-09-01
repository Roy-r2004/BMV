"""C26 - the evidence a choice follows, and the choice following it.

`recommendation.SETTLING_KINDS` is (COST, BENEFIT) and, until the two methods
under test here existed, nothing in the library wrote either: measured over the
fifteen benchmark engagements, zero COST rows and zero BENEFIT rows. A
comparison the register says nothing about cannot be settled by evidence, so
the engine produced a constant - `make` in every engagement while the selection
walked registration order, and a decline in every engagement once that order
was taken away. Neither is a judgement.

These tests are about the three things that had to become true for it to be
one, and each names the mutation it catches:

  route_dependency   what the register says about the way through a route runs
                     - one-sided, or nothing at all - and never a magnitude it
                     does not hold.
  objective_stake    what settling the decision is worth, in figures copied from
                     the aims the engagement registered, and a hole where the
                     level is not registered.
  recommendation     the choice reading those rows, the decline naming what
                     would settle THIS choice, and the standing advice being
                     revisable rather than frozen.

Every law is run through the real EngagementRegistry wherever the test is about
what gets recorded: a delta a method builds but the registry would refuse is
not a result.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from app.engine import types as T
from app.engine.calc.arith import DecimalCalculator
from app.engine.registry import EngagementRegistry
from app.engine.methods.contract import METHODS, MethodContext, MethodResult

import app.engine.methods.builtin  # noqa: F401  (registration by import)
from app.engine.methods.builtin import objective_stake as OS
from app.engine.methods.builtin import recommendation as REC
from app.engine.methods.builtin import route_dependency as RD

K = T.Kind
CC = T.CapabilityClass
GAP = T.GapState
FIXED_CLOCK = "2026-01-01T00:00:00+00:00"


# ===========================================================================
# 0. Hand-built engagements. Ids are explicit so a law can name a row.
# ===========================================================================

def row(kind, payload, *, eid, actor=T.Actor.PARTNER, status=T.Status.PROPOSED, derived=(),
        decision_id="DEC-1", weight=0.5, relation=T.RelationToCentralDecision.INFORMS) -> T.Entity:
    return T.make_entity(
        kind=kind, engagement_id="E-1", payload=payload,
        provenance=T.Provenance(actor=actor, actor_ref=f"{actor.value}:1", derived_from=tuple(derived),
                                source_locator=None, recorded_at=FIXED_CLOCK),
        confidence=T.Confidence(None), relevance=T.Relevance(decision_id, weight),
        relation=relation, status=status, entity_id=eid)


def build(rows) -> EngagementRegistry:
    return EngagementRegistry.from_rows("E-1", list(rows), clock=lambda: FIXED_CLOCK)


def ctx_for(reg, method_id: str, issue_ids=()) -> MethodContext:
    return MethodContext(registry=reg, provider=None, calc=DecimalCalculator(reg),
                         actor=T.Actor.METHOD, actor_ref=f"method:{method_id}@1",
                         issue_ids=tuple(issue_ids), settings={})


def run(reg, method_id: str, issue_ids=()) -> MethodResult:
    return METHODS.get(method_id).run(ctx_for(reg, method_id, issue_ids))


def added(result: MethodResult, kind: T.Kind):
    return [d.entity for d in result.deltas if isinstance(d, T.Add) and d.entity.kind is kind]


def cap(eid: str, capability_class: CC, gap: GAP, text: str, *, evidence=("FCT-1",)) -> T.Entity:
    return row(K.CAPABILITY, T.CapabilityPayload(text=text, capability_class=capability_class,
                                                 gap=gap, evidence=evidence),
               eid=eid, derived=evidence)


CANNERY = "we run two lines and a third stands idle four days a week"


def sourcing_rows(*channels: T.Entity, subject_gap: GAP = GAP.MISSING) -> list[T.Entity]:
    """One decision, one measure, one confirmed fact, one capability gap, the
    make and buy routes to it and the comparison that weighs them - plus
    whatever the caller puts in the CHANNELS those routes run through.

    Deliberately WITHOUT anything that bears on one route rather than the
    other, except through the channel capabilities: that is the one thing the
    tests below vary, so nothing else can be what moved the answer.
    """
    return [
        row(K.DECISION, T.DecisionPayload(statement="whether to can in house",
                                          role=T.DecisionRole.CENTRAL), eid="DEC-1"),
        row(K.MEASURE, T.MeasurePayload(name="line hours a week", unit_family=T.UnitFamily.TIME,
                                        definition="hours the canning lines run in a week"),
            eid="MEA-1", actor=T.Actor.CLIENT, derived=("DEC-1",)),
        row(K.FACT, T.FactPayload(statement=CANNERY, basis=T.FactBasis.CLIENT_STATED,
                                  measure_id="MEA-1"),
            eid="FCT-1", actor=T.Actor.CLIENT, status=T.Status.CONFIRMED,
            derived=("DEC-1", "MEA-1")),
        cap("CAP-1", CC.PROCESS, subject_gap, "a third canning line in service"),
        row(K.OPTION, T.OptionPayload(text="Stand up a third canning line in service with the "
                                           "organisation's own people and systems",
                                      decision_id="DEC-1", mechanism="make", evidence=("CAP-1",)),
            eid="OPT-1", derived=("CAP-1",), relation=T.RelationToCentralDecision.RESOLVES),
        row(K.OPTION, T.OptionPayload(text="Obtain a third canning line in service as a supplied "
                                           "product or service",
                                      decision_id="DEC-1", mechanism="buy", evidence=("CAP-1",)),
            eid="OPT-2", derived=("CAP-1",), relation=T.RelationToCentralDecision.RESOLVES),
        row(K.EVALUATION_CRITERION, T.EvaluationCriterionPayload(
            text="cases filled per shift", decision_id="DEC-1", weight=0.6,
            weight_set_by=T.Authority.CLIENT), eid="CRI-1", derived=("DEC-1",)),
        row(K.TRADE_OFF, T.TradeOffPayload(decision_id="DEC-1", option_ids=("OPT-1", "OPT-2"),
                                           gives_up="", gains="", scores=()),
            eid="TRD-1", derived=("CAP-1", "OPT-1", "OPT-2"),
            relation=T.RelationToCentralDecision.RESOLVES),
    ] + list(channels)


# The two channels the catalogue declares for the two routes on the table, each
# said one way in one fixture and the other way in its mirror. Nothing else
# differs between them, which is what makes the pair a differential.
def own_side_short() -> list[T.Entity]:
    return [cap("CAP-2", CC.PEOPLE_AND_ORGANISATION, GAP.MISSING, "a trained second-shift crew"),
            cap("CAP-3", CC.SOFTWARE_SYSTEM, GAP.MISSING, "a line scheduling system")]


def own_side_held() -> list[T.Entity]:
    return [cap("CAP-2", CC.PEOPLE_AND_ORGANISATION, GAP.PRESENT, "a trained second-shift crew"),
            cap("CAP-3", CC.SOFTWARE_SYSTEM, GAP.PRESENT_UNUSED, "a line scheduling system")]


def bought_side_short() -> list[T.Entity]:
    return [cap("CAP-4", CC.EXTERNAL_RELATIONSHIP, GAP.MISSING, "a co-packer under contract"),
            cap("CAP-5", CC.COMMERCIAL, GAP.PARTIAL, "a purchasing function that lets contracts")]


def bought_side_held() -> list[T.Entity]:
    return [cap("CAP-4", CC.EXTERNAL_RELATIONSHIP, GAP.PRESENT, "a co-packer under contract"),
            cap("CAP-5", CC.COMMERCIAL, GAP.PRESENT_UNUSED, "a purchasing function that lets contracts")]


def evidenced(reg: EngagementRegistry) -> EngagementRegistry:
    """The registry after `route_dependency` has said what it has to say. The
    real method, run as the engine runs it, and its output put through the real
    registry: a delta the door would refuse is not evidence."""
    reg.apply_all(list(run(reg, "route_dependency").deltas))
    return reg


# ===========================================================================
# 1. route_dependency - RD1/RD2: a one-sided register writes a one-sided row
# ===========================================================================

def test_a_wholly_short_channel_costs_its_route_and_a_wholly_held_one_gains_its_route():
    """RD1 and RD2 together, on one register. The make route's channels are
    every-one-missing and the buy route's are every-one-in-place, so the cost
    lands on OPT-1 alone and the benefit on OPT-2 alone.

    `for_ids` carries exactly one route on every row: that is what makes the
    row able to tell one route from another, and it is checked here rather than
    left to the validator, because a row naming both would separate nothing
    while looking exactly like evidence.

    mutation caught: write the row for a channel where ANY capability is
    missing rather than where every one of them is. CAP-5 is PARTIAL in the
    mirror fixture and PRESENT_UNUSED here, so a per-row reading writes a cost
    against both routes and the comparison goes back to saying nothing.
    """
    reg = build(sourcing_rows(*own_side_short(), *bought_side_held()))
    result = run(reg, "route_dependency")

    costs = added(result, K.COST)
    benefits = added(result, K.BENEFIT)
    assert costs and benefits, "a register that answers one way about both channels writes both rows"
    assert {c.payload.for_ids for c in costs} == {("OPT-1",)}
    assert {b.payload.for_ids for b in benefits} == {("OPT-2",)}
    # every row rests on the route it names and on the capability rows it read
    for c in costs:
        cited = set(c.provenance.derived_from)
        assert "OPT-1" in cited
        assert cited & {"CAP-2", "CAP-3"}, "the channel capabilities are cited, not summarised"
    assert reg.apply_all(list(result.deltas)), "the registry admits every row the method wrote"


def test_the_answer_mirrors_when_the_register_mirrors():
    """RD3 stated as a differential, which is the only form that cannot be
    satisfied by a constant. Two registers alike in every row but which channel
    the organisation is short of must not produce the same rows: whichever
    reading of a capability register an engine holds, applying it to a register
    and to that register's mirror image gives the two answers, not one twice.

    mutation caught: read the mechanism and prefer a route. Any fixed
    preference gives the same route in both halves of this pair.
    """
    left = build(sourcing_rows(*own_side_short(), *bought_side_held()))
    right = build(sourcing_rows(*own_side_held(), *bought_side_short()))

    def sides(reg):
        result = run(reg, "route_dependency")
        return ({c.payload.for_ids[0] for c in added(result, K.COST)},
                {b.payload.for_ids[0] for b in added(result, K.BENEFIT)})

    assert sides(left) == ({"OPT-1"}, {"OPT-2"})
    assert sides(right) == ({"OPT-2"}, {"OPT-1"})


def test_a_channel_the_register_answers_both_ways_writes_nothing_and_is_asked_about():
    """RD3: one capability of the class in place and one missing says nothing
    one-sided, so no row is written for that channel - and the hole is
    recorded, naming the route, the channel and the measure the route stands
    on, so the answer has somewhere to land (RD4).

    mutation caught: fall back to the majority, or to the first capability in
    id order. Either turns "the register does not say" into a verdict the
    register never gave.
    """
    mixed = [cap("CAP-2", CC.PEOPLE_AND_ORGANISATION, GAP.PRESENT, "a trained second-shift crew"),
             cap("CAP-3", CC.PEOPLE_AND_ORGANISATION, GAP.MISSING, "a maintenance fitter on shift")]
    reg = build(sourcing_rows(*mixed))
    result = run(reg, "route_dependency")

    assert added(result, K.COST) == [] and added(result, K.BENEFIT) == []
    asks = [q for q in result.questions if "OPT-1" in (q.about_ids or ())]
    assert asks, "the hole is recorded against the route it is in"
    ask = asks[0]
    assert "people and organisation" in ask.text
    assert "MEA-1" in ask.text, "the ask names the measure this route is counted on"
    assert ask.decision_id == "DEC-1" and {a.kind for a in ask.asks_for} == {K.COST, K.BENEFIT}


def test_the_gap_a_route_exists_to_close_is_not_also_a_cost_of_taking_it():
    """RD5. The subject capability is PEOPLE_AND_ORGANISATION and MISSING, and
    it is the very gap both routes were written to close. Reading it as a
    channel would cost the make route for the problem it was proposed to
    solve - and would do it in every engagement whose gap happens to be of a
    class some route runs through, which is a bias no register put there.

    mutation caught: drop the `own` exclusion in `readings`.
    """
    reg = build([r for r in sourcing_rows() if r.id != "CAP-1"]
                + [cap("CAP-1", CC.PEOPLE_AND_ORGANISATION, GAP.MISSING, "a trained second-shift crew")])
    verdicts = {(r.option_id, r.channel) for r in RD.readings(reg) if r.verdict is not RD.UNREGISTERED}
    assert verdicts == set(), "the only capability registered is the routes' own subject"
    assert added(run(reg, "route_dependency"), K.COST) == []


def test_a_second_run_writes_nothing_and_the_method_says_so_first():
    """Idempotence, read by citation and never by wording. `pending` and `run`
    must agree: a method whose `pending` still said yes would be offered a slot
    to write nothing, and one whose `pending` said no while the run had rows
    left would drop them.

    mutation caught: compare the rows by text. The wording is rebuilt from the
    register each run, so a text comparison passes here and fails the moment
    anything renames a capability.
    """
    reg = evidenced(build(sourcing_rows(*own_side_short(), *bought_side_held())))
    assert RD.pending(reg) is True, "the asks are still to be made"
    reg.apply_all([T.Add(T.make_entity(
        kind=K.QUESTION, engagement_id="E-1", payload=q,
        provenance=T.Provenance(actor=T.Actor.METHOD, actor_ref="method:route_dependency@1",
                                derived_from=("DEC-1",), recorded_at=FIXED_CLOCK),
        confidence=T.Confidence(None), relevance=T.Relevance(q.decision_id, 0.5),
        relation=T.RelationToCentralDecision.INFORMS, status=T.Status.OPEN))
        for q in run(reg, "route_dependency").questions])

    second = run(reg, "route_dependency")
    assert second.deltas == () and second.questions == ()
    assert RD.pending(reg) is False


def test_a_route_the_sourcing_catalogue_does_not_name_has_no_channel():
    """A route written by something other than the sourcing catalogue declares
    no channel, and this method does not invent one for it. Guessing would put
    a cost on a route whose meaning the engine does not know.

    mutation caught: default an unknown mechanism to any class.
    """
    rows = [r for r in sourcing_rows(*own_side_short()) if r.id != "OPT-1"]
    rows.append(row(K.OPTION, T.OptionPayload(text="Lease the line for one season",
                                              decision_id="DEC-1", mechanism="lease",
                                              evidence=("CAP-1",)),
                    eid="OPT-1", derived=("CAP-1",),
                    relation=T.RelationToCentralDecision.RESOLVES))
    reg = build(rows)
    assert {r.option_id for r in RD.readings(reg)} == {"OPT-2"}


def test_the_validators_refuse_a_row_that_names_every_route_or_carries_a_figure():
    """RD1/RD4 re-checked on a finished result, which is where a law about
    OUTPUT belongs: the producer's own care is not the law.

    mutation caught: widen `for_ids` to the whole comparison (a row bearing on
    everything separates nothing), or copy a capability's evidence quantity
    onto the cost as though the state of a thing were the price of changing it.
    """
    reg = build(sourcing_rows(*own_side_short(), *bought_side_held()))
    every_route = T.Add(row(K.COST, T.CostPayload(text="both routes", basis="unknown",
                                                  for_ids=("OPT-1", "OPT-2")),
                            eid="COS-9", derived=("OPT-1", "OPT-2")))
    findings = RD._v_every_row_names_one_route(reg, MethodResult(deltas=(every_route,)))
    assert [f.law for f in findings] == ["M.route_dependency.bears_on_no_single_route"]

    priced = T.Add(row(K.COST, T.CostPayload(
        text="a figure the register never held", basis="unknown", for_ids=("OPT-1",),
        quantity=T.Quantity(Decimal("40"), "hours", T.UnitFamily.TIME, T.Dimensions())),
        eid="COS-8", derived=("OPT-1",)))
    findings = RD._v_no_coined_magnitude(reg, MethodResult(deltas=(priced,)))
    assert [f.law for f in findings] == ["M.route_dependency.coined_magnitude"]
    # and the method's own output passes both, on the register that produced it
    result = run(reg, "route_dependency")
    assert RD._v_every_row_names_one_route(reg, result) == []
    assert RD._v_no_coined_magnitude(reg, result) == []


def test_no_row_this_method_writes_carries_a_magnitude():
    """RD4 on the real output. The capability register holds the STATE of a
    thing, never the price of changing it, so a figure here could only have
    been invented - and the gap is recorded instead.

    mutation caught: copy the quantity of the FACT the capability was read
    from onto the cost. It is a registered figure, which is what makes the
    mutation plausible, and it is a figure about something else.
    """
    reg = build(sourcing_rows(*own_side_short(), *bought_side_held()))
    result = run(reg, "route_dependency")
    rows = added(result, K.COST) + added(result, K.BENEFIT)
    assert rows and all(r.payload.quantity is None for r in rows)
    assert all(r.payload.basis == "unknown" for r in rows)


# ===========================================================================
# 2. objective_stake - the figure is copied, and the hole is recorded
# ===========================================================================

def aim_rows(*, target=True, measure=True) -> list[T.Entity]:
    """The sourcing engagement plus one registered aim, with and without the
    level it is set at."""
    quantity = T.Quantity(Decimal("120"), "hours", T.UnitFamily.TIME,
                          T.Dimensions(period="FY26", period_basis="week", as_of="2026-01-01"))
    payload = T.ObjectivePayload(text="run the canning lines 120 hours a week",
                                 priority=1, measure_id="MEA-1" if measure else None,
                                 target=quantity if target else None)
    return sourcing_rows(*own_side_short()) + [
        row(K.OBJECTIVE, payload, eid="OBJ-1", actor=T.Actor.CLIENT, derived=("DEC-1", "MEA-1"),
            relation=T.RelationToCentralDecision.DEFINES),
    ]


def test_the_stake_carries_the_aim_s_own_registered_target_and_no_figure_of_its_own():
    """OS1. The BENEFIT's quantity is the OBJECTIVE's target, the same object,
    cited to the row it came from - so every figure on the page is one somebody
    in the engagement put there.

    mutation caught: rebase, rescale or round the target on the way through.
    The comparison is on the Quantity itself, which carries unit, dimensions
    and precision, so an adjusted figure is a different object.
    """
    reg = build(aim_rows())
    result = run(reg, "objective_stake")
    stakes = added(result, K.BENEFIT)
    assert len(stakes) == 1
    stake = stakes[0]
    assert stake.payload.quantity == reg.get("OBJ-1").payload.target
    assert "OBJ-1" in stake.provenance.derived_from and "MEA-1" in stake.provenance.derived_from
    assert stake.payload.basis == "client_fact", "the client's own aim is a client fact"
    assert OS._v_every_figure_is_registered(reg, result) == []
    assert reg.apply_all(list(result.deltas))


def test_the_validator_refuses_a_figure_no_cited_row_carries():
    """OS1's negative control, and the mutation the law exists for: a figure
    that looks registered because the row beside it is. Doubling the target is
    the cheapest possible invention and nothing else in the engine would see
    it - the row cites a real objective and a real measure."""
    reg = build(aim_rows())
    doubled = T.Add(row(K.BENEFIT, T.BenefitPayload(
        text="twice the aim", basis="client_fact", for_ids=("OPT-1",),
        quantity=T.Quantity(Decimal("240"), "hours", T.UnitFamily.TIME,
                            T.Dimensions(period="FY26", period_basis="week", as_of="2026-01-01"))),
        eid="BEN-9", derived=("OBJ-1", "MEA-1")))
    findings = OS._v_every_figure_is_registered(reg, MethodResult(deltas=(doubled,)))
    assert [f.law for f in findings] == ["M.objective_stake.uncopied_figure"]


def test_an_aim_with_no_level_is_asked_about_and_never_filled_in():
    """OS3. An engagement that has not said what it is aiming at has not aimed
    low; it has not said. The ask names the aim and the measure it is counted
    on, so one figure answers it.

    mutation caught: default the target to the level already recorded, or to
    the target of another aim.
    """
    # A figure IS registered on the aim's own measure - which is what makes the
    # defaulting mutation plausible, and what makes refusing it a law rather
    # than an accident of a thin fixture.
    reg = build(aim_rows(target=False) + [
        row(K.FACT, T.FactPayload(statement="the lines ran 80 hours last week",
                                  basis=T.FactBasis.DOCUMENT_VERIFIED, measure_id="MEA-1",
                                  quantity=T.Quantity(Decimal("80"), "hours", T.UnitFamily.TIME,
                                                      T.Dimensions(period_basis="week"))),
            eid="FCT-2", actor=T.Actor.CLIENT, status=T.Status.CONFIRMED, derived=("MEA-1",))])
    result = run(reg, "objective_stake")
    assert added(result, K.BENEFIT) == [], "where a thing stands is not what it is aimed at"
    assert len(result.questions) == 1
    ask = result.questions[0]
    assert "OBJ-1" in ask.about_ids and "MEA-1" in ask.about_ids
    assert ask.decision_id == "DEC-1"
    assert [a.kind for a in ask.asks_for] == [K.FACT]


def test_an_aim_on_no_measure_is_asked_which_measure_and_writes_nothing():
    """OS3, the other hole: a level with nothing to count it on cannot be
    joined to anything the engagement holds, so it is asked rather than
    assumed onto the nearest measure."""
    reg = build(aim_rows(measure=False))
    result = run(reg, "objective_stake")
    assert added(result, K.BENEFIT) == []
    assert [a.kind for a in result.questions[0].asks_for] == [K.MEASURE]


def test_the_distance_to_the_aim_is_a_calculated_fact_with_a_formula_that_reproduces_it():
    """OS2. Where the register holds a figure on the aim's own measure, the
    distance between them is arithmetic and goes through ctx.calc: a CALCULATED
    fact carrying the formula over entity ids and the inputs, which L7
    recomputes exactly.

    mutation caught: divide by hand and store the result. A typed number has no
    formula and nothing can reproduce it.
    """
    level = T.Quantity(Decimal("80"), "hours", T.UnitFamily.TIME,
                       T.Dimensions(period="FY26", period_basis="week", as_of="2026-01-01"))
    rows = aim_rows() + [
        row(K.FACT, T.FactPayload(statement="the lines ran 80 hours last week",
                                  basis=T.FactBasis.DOCUMENT_VERIFIED, measure_id="MEA-1",
                                  quantity=level),
            eid="FCT-2", actor=T.Actor.CLIENT, status=T.Status.CONFIRMED, derived=("MEA-1",)),
    ]
    reg = build(rows)
    result = run(reg, "objective_stake")
    calculated = [f for f in added(result, K.FACT) if f.payload.basis is T.FactBasis.CALCULATED]
    assert len(calculated) == 1
    fact = calculated[0]
    assert fact.payload.formula == "FCT-2 / OBJ-1"
    assert set(fact.payload.inputs) == {"FCT-2", "OBJ-1"}
    assert fact.payload.quantity.value == Decimal("0.67")
    written = reg.apply_all(list(result.deltas))
    stored = [e for e in written if e.kind is K.FACT and e.payload.basis is T.FactBasis.CALCULATED][0]
    assert DecimalCalculator(reg).recompute(stored, reg), "the formula reproduces the figure"


def test_the_stake_bears_on_every_route_and_therefore_separates_none_of_them():
    """OS4. What the decision is worth is what ANY route to it is for, so the
    row names them all - and `points_to` passes over a row that names them all,
    because a benefit every route carries is not a reason to take any of them.

    mutation caught: attach the stake to one route. It would be an invented
    preference wearing the client's own target as evidence, and the whole
    comparison would turn on it.
    """
    reg = build(aim_rows())
    reg.apply_all(list(run(reg, "objective_stake").deltas))
    stake = [b for b in reg.live(K.BENEFIT)][0]
    assert set(stake.payload.for_ids) == {"OPT-1", "OPT-2"}
    assert REC.points_to(reg, ["OPT-1", "OPT-2"]) == (None, ())
    assert REC.separates(reg, ["OPT-1", "OPT-2"]) is False


# ===========================================================================
# 3. The choice reading the evidence, end to end
# ===========================================================================

def advised(reg: EngagementRegistry) -> tuple[str | None, str | None]:
    """(option id, mechanism) this registry's own producer advises, after the
    evidence producer has run. Both real methods, run as the engine runs them,
    with the registry between them."""
    reg = evidenced(reg)
    reg.apply_all(list(run(reg, "recommendation").deltas))
    for r in sorted(reg.live(K.RECOMMENDATION), key=lambda e: e.id):
        option = reg.get(r.payload.option_id or "")
        return r.payload.option_id, (option.payload.mechanism if option else None)
    return None, None


def test_the_advice_follows_the_evidence_the_producer_wrote():
    """The whole chain, and the law the two methods exist for: the register
    says which way through is open to this organisation, and the choice follows
    it. Mirror the register and the advice mirrors.

    This is T1's differential run through the real producer rather than through
    hand-written COST and BENEFIT rows - which is what makes it evidence that
    the engine chooses, and not only that it could if somebody wrote the rows.

    mutation caught: select `option_ids[0]`, or any other fixed position in a
    registration order. It gives OPT-1 in both halves.
    """
    left = advised(build(sourcing_rows(*own_side_short(), *bought_side_held())))
    right = advised(build(sourcing_rows(*own_side_held(), *bought_side_short())))
    assert left == ("OPT-2", "buy")
    assert right == ("OPT-1", "make")


def test_a_register_that_says_nothing_about_the_channels_advises_nothing():
    """The other half of the same law, and the reason the first half is not a
    tautology: the producer writes rows only where the register is one-sided,
    so an engagement it says nothing about is still declined. A method that
    always wrote a row would make every choice decidable and none of them
    evidenced."""
    reg = evidenced(build(sourcing_rows()))
    assert reg.live(K.COST) == [] and reg.live(K.BENEFIT) == []
    result = run(reg, "recommendation")
    assert added(result, K.RECOMMENDATION) == []
    assert added(result, K.DECISION_REQUIRED)


# ===========================================================================
# 4. The decline says what would settle THIS choice
# ===========================================================================

def decline_text(reg: EngagementRegistry) -> str:
    blockers = added(run(reg, "recommendation"), K.DECISION_REQUIRED)
    assert blockers, "an engagement that cannot advise records why"
    return blockers[0].payload.text


def test_the_decline_names_the_routes_and_the_measure_and_not_a_count_of_routes():
    """R7. The blocker a reader finds where the advice would have been has to
    say which choice is open and what to send. "nothing tells the 27 route(s)
    apart" was one sentence shared by fifteen engagements, differing by an
    integer: it names no route, no measure and no kind of evidence, and a
    reader cannot act on it.

    mutation caught: render the reason from counts. The assertion below is that
    the ids and the measure are IN the sentence, which a count cannot satisfy.
    """
    text = decline_text(build(sourcing_rows()))
    assert "OPT-1" in text and "OPT-2" in text
    assert "MEA-1" in text and "line hours a week" in text
    assert "cost" in text and "benefit" in text


def test_two_engagements_that_cannot_advise_do_not_get_the_same_sentence():
    """The same law as a differential, because "names the routes" is satisfiable
    by a template with the ids substituted in. Two engagements whose routes and
    measures differ must get different sentences; an engine whose decline is a
    script gives one sentence twice.

    mutation caught: drop the measure clause and keep the ids. The two
    sentences below would still differ - so the assertion is on the MEASURE
    text as well, which no id substitution reaches.
    """
    first = decline_text(build(sourcing_rows()))
    other = [r for r in sourcing_rows() if r.id != "MEA-1"]
    other.append(row(K.MEASURE, T.MeasurePayload(name="pallets shipped a day",
                                                 unit_family=T.UnitFamily.COUNT,
                                                 definition="pallets leaving the yard in a day"),
                     eid="MEA-1", actor=T.Actor.CLIENT, derived=("DEC-1",)))
    second = decline_text(build(other))
    assert first != second
    assert "line hours a week" in first and "pallets shipped a day" in second


def test_a_register_that_points_two_ways_is_not_reported_as_unevidenced():
    """R7's truthfulness clause. Four impasses, four different fixes: no route,
    no comparison, nothing separating them, and rows that separate them and
    disagree. Collapsing the last into "no registered route traces to a
    confirmed fact" told the reader to go and find evidence for routes that
    were perfectly well evidenced and merely pointed both ways.

    mutation caught: report `UNEVIDENCED` for every failure to select.
    """
    reg = build(sourcing_rows(*own_side_short(), *bought_side_short()))
    reg = evidenced(reg)
    ids = ["OPT-1", "OPT-2"]
    assert REC.separates(reg, ids) is True, "each route carries a cost of its own"
    assert REC.points_to(reg, ids) == (None, ()), "and they point at each other"

    options = {o.id: o for o in reg.live(K.OPTION)}
    reason, comparison, details = REC.impasse(
        reg, options, REC.widest_comparison(reg, "DEC-1", options))
    assert reason == REC.POINTS_TWO_WAYS and comparison.id == "TRD-1"
    assert details, "the rows that disagree are named"

    text = decline_text(reg)
    assert "points more than one way" in text
    assert all(i in text for i in details)
    assert "no confirmed fact" not in text


def test_an_engagement_with_no_comparison_says_so_and_names_its_routes():
    """The first two impasses, which are about the shape of the register rather
    than about its content, and which must stay distinguishable from the other
    two."""
    no_comparison = build([r for r in sourcing_rows() if r.id != "TRD-1"])
    assert "never weighed against one another" in decline_text(no_comparison)
    no_routes = build([r for r in sourcing_rows() if not r.id.startswith("OPT")
                       and r.id != "TRD-1"])
    assert "no route is registered" in decline_text(no_routes)


# ===========================================================================
# 5. Advice is revisable, and the deadlock is not silent
# ===========================================================================

def standing_advice(option_id: str) -> T.Entity:
    return row(K.RECOMMENDATION, T.RecommendationPayload(
        statement="Stand the line up in house rather than buying it in.",
        decision_id="DEC-1", option_id=option_id, supports=("FCT-1",)),
        eid="REC-1", derived=(option_id, "DEC-1", "TRD-1", "CRI-1", "FCT-1"),
        relation=T.RelationToCentralDecision.RESOLVES)


def test_evidence_that_moves_the_register_supersedes_the_standing_advice():
    """R9. The advice stood on the evidence it had; the register now points the
    other way, so the row is superseded in place - same id, the other route,
    citing what changed its mind. Never a second row: two live recommendations
    on one decision hand the reader the decision back."""
    reg = build(sourcing_rows(*own_side_short(), *bought_side_held()) + [standing_advice("OPT-1")])
    reg = evidenced(reg)
    result = run(reg, "recommendation")
    supersedes = [d for d in result.deltas if isinstance(d, T.Supersede)]
    assert len(supersedes) == 1 and supersedes[0].old_id == "REC-1"
    revised = supersedes[0].entity
    assert revised.payload.option_id == "OPT-2"
    moved = {c.id for c in reg.live(K.COST)} | {b.id for b in reg.live(K.BENEFIT)}
    assert moved & set(revised.provenance.derived_from), "the revision cites what changed it"
    assert added(result, K.RECOMMENDATION) == []


def test_an_unchanged_register_draws_no_revision():
    """R9's negative control, and the one that keeps the law from asking for
    churn. Nothing has arrived, so nothing is written - not the revision, not
    the contest, not a restatement of the advice that stands."""
    reg = build(sourcing_rows() + [standing_advice("OPT-1")])
    assert run(reg, "recommendation").deltas == ()
    assert REC.pending(reg) is False


def test_advice_the_register_no_longer_bears_out_is_recorded_as_contested():
    """R9's other half, and the silent deadlock it ends. Evidence arrives that
    bears on both routes and points both ways: the register now points at no
    route at all, so there is nothing to revise the advice INTO - and the old
    code's single early return meant nothing was written, the recommendation
    went on standing, and no row in the registry said it was out of date.

    The advice is not rewritten: it still says what it said, on the evidence it
    said it on. What is recorded is that the choice is back with its owner,
    which rows put it there, and what would settle it.

    mutation caught: `if option is None: return MethodResult()`.
    """
    reg = build(sourcing_rows(*own_side_short(), *bought_side_short()) + [standing_advice("OPT-1")])
    reg = evidenced(reg)
    assert REC.points_to(reg, ["OPT-1", "OPT-2"]) == (None, ())
    assert REC.pending(reg) is True

    result = run(reg, "recommendation")
    assert [d for d in result.deltas if isinstance(d, T.Supersede)] == []
    blockers = added(result, K.DECISION_REQUIRED)
    assert len(blockers) == 1
    text = blockers[0].payload.text
    assert "REC-1" in text and "OPT-1" in text and "does not bear it out" in text
    assert "MEA-1" in text, "and it says what would settle it, on this engagement's measure"

    # written once: a second run over the same register adds nothing.
    reg.apply_all(list(result.deltas))
    assert run(reg, "recommendation").deltas == ()
    assert REC.pending(reg) is False


def test_a_contest_is_read_from_the_ids_the_advice_cites_and_never_from_a_count():
    """The contest is read by CITATION. A recommendation that already rests on
    a row has not been contested by it, and the rows it does not cite are
    exactly the ones that are new to it.

    Both halves are needed. Advice that cites everything must draw no contest,
    or the blocker is raised again every round for ever; and advice that cites
    ONE of four must be contested by the other three and not by the one - which
    is what a count cannot tell, because four rows against one citation and
    four rows against four citations differ only in which ids they are.

    mutation caught: `rows if len(rows) > len(cited & set(rows)) else ()`.
    """
    reg = evidenced(build(sourcing_rows(*own_side_short(), *bought_side_short())))
    bearing = tuple(sorted({c.id for c in reg.live(K.COST)}))
    assert len(bearing) == 4, "each route runs through two channels and is short of both"

    def contests(cites):
        base = standing_advice("OPT-1")
        aware = replace(base, provenance=replace(base.provenance,
                                                 derived_from=base.provenance.derived_from + tuple(cites)))
        scratch = build(list(reg.query()) + [aware])
        return REC.contesting_rows(scratch, scratch.get("REC-1"), scratch.get("TRD-1"),
                                   {o.id: o for o in scratch.live(K.OPTION)})

    assert contests(bearing) == (), "advice that rests on every row is not contested by them"
    one = bearing[:1]
    assert contests(one) == bearing[1:], "the rows it does not cite are the new ones"
    assert one[0] not in contests(one), "and the one it cites is not among them"


# ===========================================================================
# 6. R11 - a decline is not recorded a round before the evidence
# ===========================================================================

def issue_node(eid: str = "ISS-1", *, interrogative=T.Interrogative.WHICH,
               target=K.DECISION, comparative=True) -> T.Entity:
    return row(K.ISSUE, T.IssuePayload(text="which way", interrogative=interrogative,
                                       target_kind=target, comparative=comparative,
                                       decisive_for=("DEC-1",)),
               eid=eid, derived=("DEC-1",), status=T.Status.OPEN)


def test_the_advice_waits_while_a_producer_of_settling_evidence_still_has_a_node():
    """R11. A node is offered to a method once, so a decline recorded before
    the producer of the evidence has run is also the last word the engine gets:
    over the fifteen benchmark engagements `recommendation` ran immediately
    before `route_dependency` in fourteen of them, declined in every one, and
    the register it declined over went on to point at a route in nine.

    So `pending` says "not yet" while a registered producer of a settling kind
    is unattempted, satisfiable and has a live node of a shape it declares -
    and no ANALYSIS row is written, which is what leaves the node open.

    mutation caught: return True unconditionally when nothing is advised.
    """
    reg = build(sourcing_rows() + [issue_node()])
    assert "route_dependency" in REC.settling_producers(reg)
    assert REC.pending(reg) is False, "the evidence is still coming"

    # The RUN never waits: a method that has been run and says nothing has been
    # silent, and R7 is exactly the refusal to be silent.
    result = run(reg, "recommendation", issue_ids=("ISS-1",))
    assert added(result, K.DECISION_REQUIRED), "a direct run still records the reason"


def test_the_wait_ends_when_the_producer_has_run():
    """The bound that makes R11 a wait and not a deadlock: once the producer
    has been attempted, the engagement holds what it is going to hold and the
    decline is true."""
    reg = build(sourcing_rows() + [issue_node()])
    reg.apply_all([T.Add(row(K.ANALYSIS, T.AnalysisPayload(
        method_id="route_dependency", method_version=1, issue_ids=("ISS-1",),
        state=T.AnalysisState.DONE), eid="ANA-1", derived=("ISS-1",)))])
    assert "route_dependency" not in REC.settling_producers(reg)
    assert REC.pending(reg) is True


def test_the_wait_ends_when_no_open_node_could_host_the_producer():
    """The other bound, and the one that stops an engagement waiting for ever
    for a method it will never select: a producer whose declared shapes match
    no live issue node has no node to run on, and is not coming.

    mutation caught: drop the shape clause from `settling_producers`. Then an
    engagement whose tree never asked a comparative question would hold its
    advice back for ever and reach synthesis with nothing recorded at all.
    """
    reg = build(sourcing_rows() + [issue_node(interrogative=T.Interrogative.WHO,
                                              target=K.STAKEHOLDER, comparative=False)])
    assert REC.settling_producers(reg) == ()
    assert REC.pending(reg) is True


def test_the_wait_never_holds_back_a_choice_the_register_can_already_settle():
    """Evidence that would settle a choice already settled does not stop the
    engine settling it. The wait is about a DECLINE being premature, never
    about an advice being early."""
    reg = evidenced(build(sourcing_rows(*own_side_short(), *bought_side_held()) + [issue_node()]))
    assert REC.pending(reg) is True
    assert added(run(reg, "recommendation"), K.RECOMMENDATION)


# ===========================================================================
# 7. The two methods are methods
# ===========================================================================

@pytest.mark.parametrize("method_id", ["route_dependency", "objective_stake"])
def test_the_new_producers_are_ordinary_methods(method_id):
    """Registered by import, declared shapes, declared inputs, an execution
    type, validators, limitations and a `pending` - and registering them took
    no orchestrator change."""
    spec = METHODS.get(method_id).spec
    assert spec.execution in T.FREE_EXECUTION and spec.max_model_calls == 0
    assert spec.applicability and spec.answers and spec.validators and spec.limitations
    assert spec.pending is not None
    assert all(s.interrogative in spec.answers for s in spec.applicability)


def test_the_settling_kinds_now_have_producers():
    """The defect these tests are about, stated as a law: every kind the
    selection reads as able to settle a choice has a producer in the library.
    A kind nothing writes is a branch nothing can reach."""
    for kind in REC.SETTLING_KINDS:
        assert METHODS.producers_of(kind), f"{kind.value} has no producer in the library"
    assert "route_dependency" in {m.spec.id for m in METHODS.producers_of(K.COST)}
    assert "objective_stake" in {m.spec.id for m in METHODS.producers_of(K.BENEFIT)}


def test_no_engagement_type_or_client_vocabulary_in_either_module():
    """Universality is a property of the type system: a method that named an
    engagement type would be a capability pack (spec section 3)."""
    import inspect
    banned = ("acquisition", "market_entry", "cost_reduction", "turnaround",
              "restructuring", "product_launch", "if engagement")
    for module in (RD, OS):
        source = inspect.getsource(module).lower()
        for word in banned:
            assert word not in source, f"{module.__name__} names {word!r}"
