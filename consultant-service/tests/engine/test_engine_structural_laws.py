"""C24 - seven structural laws over what the engine PRODUCES.

Every other suite in tests/engine asks whether a component obeys its own
contract. These seven ask the question the owner asked of the finished
engagement: is this a piece of consulting, or a pile of rows? Each law is one
test, each names the mutation it exists to catch, and each carries a NEGATIVE
CONTROL - the same checking function run over a hand-built engagement that is
sound - so a law that fails cannot be dismissed as a check nothing could pass.

The laws:

  S1 termination at the condition, not the wall. A loop stops because its
     stopping condition was met, never because I9 refused the row it was about
     to write. Counted on the WRITE PATH (rows offered to `_add`), because
     refusal is invisible in a count of survivors: `apply_all` rolls a refused
     batch back whole, so the live count lands BELOW the ceiling that refused
     it, and the pre-selection guard (`saturated_kinds`) therefore never fires.
     The cap and the guard defeat each other, and only the offered count sees
     it.
       mutation: raise MAX_ENTITIES_PER_ANALYSIS_KIND and the live counts stay
       inside it while generation runs away exactly as before.

  S2 every case concludes, or says why. A conclusion is a live RECOMMENDATION;
     a reason is a typed blocker - an OPEN QUESTION, a DECISION_REQUIRED or a
     CONFLICT - that names the central decision in a typed field AND names the
     evidence that would settle it. Silence is neither, and neither is a row
     that merely mentions the decision in its lineage.
       mutation: exempt an engagement from concluding because it ran few
       methods (a run-count floor), which is what let one case conclude
       nothing and pass; or accept a blocker that names the decision and not
       the missing evidence, which is what let every case pass this branch on
       questions about something else.

  S3 one coherent recommendation per decision. Two live recommendations on one
     decision may not be mutually exclusive.
       mutation: dedupe recommendations by the id they cite rather than by the
       choice they make, which cannot see that three routes to one gap are one
       choice.

  S4 a recommendation selects AND explains. It names the live OPTION it
     selects, cites a criterion the choice was judged on, and cites the
     comparison in which that option beat a named rival.
       mutation: drop the comparison and keep the citation - advice that names
       a route and never says what it was weighed against.

  S5 traces but does not copy. A recommendation's statement may not contain,
     nor be contained by, the claim of any FACT or MEASURE in the registry.
       mutation: prefix or suffix a copied claim ("Take the route: <fact>") and
       call the frame authorship; equality alone does not see it, containment
       does. Comparison is exact - normalise whitespace, fold case, compare
       substrings. No similarity measure is imported by this module.

  S6 the gate blocks. A contradictory pair of recommendations on one decision,
     and a recommendation asserting specificity its support closure does not
     carry, must stop a release. Tested through `release_status(run_laws(...))`
     - the door itself - not through a benchmark assertion.
       mutation: leave the check in the benchmark only, where a release never
       reads it.

  S7 the starvation mutations are caught. Six named edits that make the engine
     produce LESS while every existing test stays green:
       (a) analysis ends after one tier              -> test_s7a_*
       (b) the capability gate drops PARTIAL         -> test_s7b_*
       (c) the capability gate drops PRESENT_UNUSED  -> test_s7c_*
       (d) attempted methods hold a node's slots     -> test_s7d_*
       (e) synthesis_blockers returns () always      -> test_s7e_*
       (f) make_buy_partner requires two OPTIONs     -> test_s7f_*

Written as tests only. No production module is edited by this file; where a
mutation must be exercised it is applied with monkeypatch and reverted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping

import pytest

from app.engine import types as T
from app.engine.benchmark import cases as C
from app.engine.benchmark import harness as H
from app.engine.benchmark.oracle import structural_oracle
from app.engine.gates.laws import ArtifactRef, run_laws
from app.engine.gates.release import STATUS_DRAFT, release_status
from app.engine.llm import FakeProvider
from app.engine.methods.contract import (
    METHODS,
    EvidenceRequirement,
    InputSpec,
    MethodContext,
    MethodRegistry,
    MethodResult,
    MethodSpec,
    QuestionShape,
    input_state,
)
from app.engine.partner import state as S
from app.engine.registry import EngagementRegistry
from app.engine.types import (
    ANALYSIS_KINDS,
    BOUNDS,
    TERMINAL_STATUSES,
    Actor,
    Add,
    Authority,
    CapabilityClass,
    CapabilityPayload,
    Confidence,
    DecisionPayload,
    DecisionRole,
    Dimensions,
    EffortClass,
    Entity,
    EvaluationCriterionPayload,
    EvidenceSourcePayload,
    FactBasis,
    FactPayload,
    FillStrategy,
    GapState,
    Kind,
    MeasurePayload,
    OptionPayload,
    Provenance,
    Quantity,
    QuestionPayload,
    RecommendationPayload,
    RelationToCentralDecision,
    Relevance,
    Score,
    SourceKind,
    Status,
    TradeOffPayload,
    UnitFamily,
    make_entity,
)

import app.engine.methods.builtin  # noqa: F401  - registration by import

from tests.engine.conftest import FIXED_CLOCK


# ===========================================================================
# 0. The benchmark, run once, with the registry WRITE PATH instrumented
# ===========================================================================

@dataclass
class Run:
    """One engagement as the laws read it: the registry it ended with, and -
    the thing no query can recover afterwards - how many rows of each kind
    were OFFERED to the registry, including the ones it refused."""
    case_id: str
    registry: Any
    methods: tuple[str, ...]
    phase: str
    generated: Mapping[str, int] = field(default_factory=dict)
    refused_by_capacity: Mapping[str, int] = field(default_factory=dict)


@pytest.fixture(scope="module")
def runs():
    """Every benchmark case, once, with `_add` counted.

    Module-scoped for the same reason tests/engine/test_engine_benchmarks_fake.py
    scopes its bundles: fifteen engagements are the unit under test, and the
    runs are deterministic, so running them again per law would say nothing
    new.
    """
    generated: dict[str, int] = {}
    refused: dict[str, int] = {}
    original = EngagementRegistry._add

    def counting_add(self, e):
        generated[e.kind.name] = generated.get(e.kind.name, 0) + 1
        try:
            return original(self, e)
        except T.RegistryError as exc:
            if getattr(exc, "invariant", None) == "I9":
                refused[e.kind.name] = refused.get(e.kind.name, 0) + 1
            raise

    EngagementRegistry._add = counting_add
    try:
        out: dict[str, Run] = {}
        for case in C.load_all():
            generated.clear()
            refused.clear()
            bundle = H.run_case(case, FakeProvider(oracle=structural_oracle))
            out[case.id] = Run(case_id=case.id, registry=bundle.registry,
                               methods=tuple(bundle.methods), phase=bundle.phase,
                               generated=dict(generated), refused_by_capacity=dict(refused))
        return out
    finally:
        EngagementRegistry._add = original


# ===========================================================================
# 1. Shared reading. Every law IS one of these functions, and every law's
#    negative control runs the SAME function on a hand-built engagement.
# ===========================================================================

def live(view, kind: Kind) -> list[Entity]:
    return [e for e in view.query(kind) if e.status not in TERMINAL_STATUSES]


def normalised(text: str) -> str:
    """Whitespace collapsed, case folded. Exact comparison only - there is no
    similarity measure anywhere in this file, and S5 is the reason."""
    return " ".join(str(text or "").split()).casefold()


def defensible_ceiling() -> int:
    """The ceiling the engine can defend FROM THE BOUNDS IT ALREADY PUBLISHES:
    every round of the analysis (MAX_ANALYSIS_ROUNDS), running flat out
    (MAX_SPECIALISTS_PER_ROUND), opening every branch it is allowed
    (MAX_FANOUT). Not a target - the point past which an engagement has stopped
    analysing a decision and started enumerating the registry.

    Derived rather than declared for one reason: MAX_ENTITIES_PER_ANALYSIS_KIND
    is the value S1's own named mutation moves, so a law that read only that
    value moved its goalposts and its measuring stick together.
    """
    return (int(BOUNDS["MAX_ANALYSIS_ROUNDS"]) * int(BOUNDS["MAX_SPECIALISTS_PER_ROUND"])
            * int(BOUNDS["MAX_FANOUT"]))


def ceiling() -> int:
    """The ceiling S1 judges against: the declared bound, LIMITED BY the default
    the other bounds defend.

    Never a literal - the bound is the operator's to set and a test that spelled
    it out would pin the wrong thing - but never the declared value alone
    either. Read as the declared value alone, S1 was satisfied by its own named
    mutation: raise MAX_ENTITIES_PER_ANALYSIS_KIND, and the ceiling the law
    measures against rises with the ceiling the engine generates against, every
    count goes legal, and generation runs away exactly as before. The operator
    may argue this bound DOWN as far as they like; arguing it up is an argument
    against MAX_ANALYSIS_ROUNDS, MAX_SPECIALISTS_PER_ROUND and MAX_FANOUT, and
    has to be made there.
    """
    return min(int(BOUNDS["MAX_ENTITIES_PER_ANALYSIS_KIND"]), defensible_ceiling())


# -- S1 ---------------------------------------------------------------------

def capacity_breaches(generated: Mapping[str, int], refused: Mapping[str, int],
                      bound: int) -> list[str]:
    """S1: rows OFFERED of an analysis kind stay inside the declared bound, and
    no row is ever refused for capacity.

    Both halves are one law. A loop that stops when its stopping condition is
    met never offers the (bound + 1)th row; a loop that runs until the door
    refuses it offers thousands and lands under the bound only because the
    refusal rolled its batch back.
    """
    out: list[str] = []
    for name, count in sorted(generated.items()):
        if Kind[name] in ANALYSIS_KINDS and count > bound:
            out.append(f"{count} {name} rows generated, over the bound of {bound}")
    for name, count in sorted(refused.items()):
        out.append(f"{count} {name} rows refused by capacity (I9)")
    return out


# -- S2 ---------------------------------------------------------------------

def central(view) -> Entity | None:
    for d in live(view, Kind.DECISION):
        if d.payload.role is DecisionRole.CENTRAL:
            return d
    return None


def names_decision(e: Entity, decision_id: str) -> bool:
    """Whether a row is recorded AGAINST this decision, by a TYPED field its own
    kind carries.

    `derived_from` was read here too, and dropping it is half of the repair
    below. Lineage says a row was written after the decision, which nearly
    every row in an engagement was; it does not say the row is why the decision
    is unanswered. Kept as a separate function because two kinds of row file
    themselves under two different fields, which is a spelling question and not
    a question about what the row means.
    """
    payload = e.payload
    for attr in ("decision_id", "subject_id"):
        if getattr(payload, attr, None) == decision_id:
            return True
    return e.relevance.decision_id == decision_id


def typed_blockers(view, decision_id: str) -> list[str]:
    """The rows that say WHY no conclusion is possible - and say what would make
    one possible.

    A blocker carries both halves, each in a typed field. WHICH decision is
    unanswered: `names_decision`, which reads the fields a row files itself
    under. WHAT WOULD ANSWER IT: an OPEN QUESTION's `asks_for` names the kind
    of evidence being asked for; a DECISION_REQUIRED or a CONFLICT earns the
    same standing by citing such a question, so the blocker and the ask are one
    record rather than two rows that happen to coexist.

    The second half is the repair. Without it this branch accepted ANY open
    question that mentioned the decision anywhere, lineage included - and
    lineage is a link nearly every row carries - so an engagement holding a
    hundred open questions about anything at all was reported as having said
    why it could not conclude. `lineage_only_blockers` below is that clause,
    kept as the ghost this one is measured against, and
    `test_s2_a_blocker_names_the_evidence_that_would_settle_the_decision`
    is the fixture the ghost accepts and this refuses.
    """
    asked = [q.id for q in view.query(Kind.QUESTION, status=Status.OPEN)
             if q.payload.asks_for and names_decision(q, decision_id)]
    out: list[str] = list(asked)
    for kind in (Kind.DECISION_REQUIRED, Kind.CONFLICT):
        for e in live(view, kind):
            if names_decision(e, decision_id) and set(e.provenance.derived_from) & set(asked):
                out.append(e.id)
    return out


def lineage_only_blockers(view, decision_id: str) -> list[str]:
    """S2's blocker clause AS IT STOOD, before the repair above: any open
    question, decision-required or conflict that MENTIONS the decision - by a
    typed field or merely by a link in `derived_from` - and nothing about what
    would settle it.

    No law calls this. It exists so the repair can be shown to have changed
    something: a predicate that refuses everything is not a repair, and the
    proof is a fixture this accepts and `typed_blockers` refuses.
    """
    def mentions(e: Entity) -> bool:
        return names_decision(e, decision_id) or decision_id in e.provenance.derived_from

    out: list[str] = [q.id for q in view.query(Kind.QUESTION, status=Status.OPEN) if mentions(q)]
    for kind in (Kind.DECISION_REQUIRED, Kind.CONFLICT):
        out.extend(e.id for e in live(view, kind) if mentions(e))
    return out


def unconcluded(view) -> list[str]:
    """S2: the engagement concludes, or it records the reason it cannot. No
    exemption by run count - a short engagement that concluded nothing and said
    nothing is exactly the case this law is for."""
    decision = central(view)
    if decision is None:
        return ["no live CENTRAL decision: there is nothing this engagement could conclude about"]
    if live(view, Kind.RECOMMENDATION):
        return []
    if typed_blockers(view, decision.id):
        return []
    return [f"no live RECOMMENDATION and no typed blocker recorded against {decision.id}"]


# -- S3 ---------------------------------------------------------------------

def option_subjects(option: Entity) -> frozenset[str]:
    """What a route is a route TO: the ids it was written for. Two routes to
    one subject are two answers to one question."""
    return frozenset(option.payload.evidence) | frozenset(option.provenance.derived_from)


def mutually_exclusive(view, first: Entity, second: Entity) -> str:
    """Whether two recommendations cannot both be taken, read structurally and
    never from wording.

    Two ways one registry says so:
      - the routes they select answer the same subject by different mechanisms
        (make / buy / partner on one capability gap: choosing one is declining
        the others);
      - a live TRADE_OFF lists both routes together, which is the engagement's
        own record that they are alternatives.
    """
    a_id, b_id = first.payload.option_id, second.payload.option_id
    if not a_id or not b_id or a_id == b_id:
        return ""
    options = {o.id: o for o in live(view, Kind.OPTION)}
    a, b = options.get(a_id), options.get(b_id)
    if a is None or b is None:
        return ""
    if (a.payload.mechanism and b.payload.mechanism
            and a.payload.mechanism != b.payload.mechanism
            and option_subjects(a) & option_subjects(b)):
        return (f"{first.id} takes {a_id} ({a.payload.mechanism}) and {second.id} takes "
                f"{b_id} ({b.payload.mechanism}) for the same subject")
    for t in live(view, Kind.TRADE_OFF):
        ids = set(t.payload.option_ids)
        if a_id in ids and b_id in ids:
            return f"{first.id} and {second.id} take two routes {t.id} weighs against each other"
    return ""


def incoherent(view) -> list[str]:
    """S3: for each live DECISION, no two live recommendations on it are
    mutually exclusive. Either exactly one stands, or the several that stand
    are compatible - the alternatives belong under one recommendation as
    OPTIONs, not beside it as rival advice."""
    out: list[str] = []
    for decision in live(view, Kind.DECISION):
        on_it = [r for r in live(view, Kind.RECOMMENDATION)
                 if r.payload.decision_id == decision.id]
        for i in range(len(on_it)):
            for j in range(i + 1, len(on_it)):
                why = mutually_exclusive(view, on_it[i], on_it[j])
                if why:
                    out.append(f"{decision.id}: {why}")
    return out


# -- S4 ---------------------------------------------------------------------

def discriminates(trade_off: Entity, option_id: str) -> bool:
    """Whether a comparison actually separates this route from the others in
    it. A trade-off that scores nothing and records neither what is given up
    nor what is gained is a pairing, not a comparison."""
    payload = trade_off.payload
    if any(s.option_id == option_id for s in payload.scores):
        return True
    return bool((payload.gives_up or "").strip() or (payload.gains or "").strip())


def unselective(view) -> list[str]:
    """S4: a recommendation names the route it selects, the standard it was
    judged against, and the comparison in which that route beat a named rival.

    The third clause is the one that separates advice from an emission. A
    recommendation that cites its option and its criteria and NO comparison has
    said "take this" without ever saying "rather than that" - and the registry
    holds nothing that could be asked what it was weighed against.
    """
    out: list[str] = []
    options = {o.id: o for o in live(view, Kind.OPTION)}
    criteria = {c.id: c for c in live(view, Kind.EVALUATION_CRITERION)}
    trade_offs = {t.id: t for t in live(view, Kind.TRADE_OFF)}
    for r in live(view, Kind.RECOMMENDATION):
        decision_id = r.payload.decision_id
        cited = set(r.provenance.derived_from) | set(r.payload.supports)
        option_id = r.payload.option_id
        option = options.get(option_id or "")
        if option is None:
            out.append(f"{r.id} names no live OPTION")
            continue
        if option.payload.decision_id != decision_id:
            out.append(f"{r.id} selects {option_id}, which is a route for "
                       f"{option.payload.decision_id}, not for {decision_id}")
            continue
        if not any(i in criteria and criteria[i].payload.decision_id == decision_id
                   for i in cited):
            out.append(f"{r.id} cites no EVALUATION_CRITERION for {decision_id}")
            continue
        compared = False
        for i in cited:
            t = trade_offs.get(i)
            if t is None or t.payload.decision_id != decision_id:
                continue
            ids = set(t.payload.option_ids)
            rivals = {o for o in ids if o in options and o != option_id}
            if option_id in ids and rivals and discriminates(t, option_id):
                compared = True
                break
        if not compared:
            out.append(f"{r.id} records no comparison in which {option_id} beat a named rival")
    return out


# -- S5 ---------------------------------------------------------------------

def claims(view) -> list[tuple[str, str]]:
    """(id, claim) for every live FACT and MEASURE.

    A FACT's `statement` and a MEASURE's `definition` are the fields that carry
    a claim; a measure's NAME is a label for a column and not something anyone
    asserts. The distinction is by FIELD, not by length: a law that skipped
    short text would be a similarity measure with extra steps, and a law that
    compared column labels would be unsatisfiable rather than strict.
    """
    out: list[tuple[str, str]] = []
    for f in live(view, Kind.FACT):
        text = normalised(f.payload.statement)
        if text:
            out.append((f.id, text))
    for m in live(view, Kind.MEASURE):
        text = normalised(getattr(m.payload, "definition", "") or "")
        if text:
            out.append((m.id, text))
    return out


def copied(view) -> list[str]:
    """S5: a recommendation traces to evidence, and does not repeat it.

    Containment both ways. Equality alone is defeated by a frame - "Take the
    route: <the fact>" is not equal to the fact and is not authorship either -
    and the reverse direction catches a statement so terse a claim swallows it.
    """
    out: list[str] = []
    texts = claims(view)
    for r in live(view, Kind.RECOMMENDATION):
        if not r.payload.supports:
            out.append(f"{r.id} rests on nothing: it cites no supports")
            continue
        statement = normalised(r.payload.statement)
        if not statement:
            out.append(f"{r.id} says nothing")
            continue
        for entity_id, claim in texts:
            if claim in statement:
                out.append(f"{r.id} contains the claim of {entity_id} verbatim")
                break
            if statement in claim:
                out.append(f"{r.id} is contained in the claim of {entity_id}")
                break
    return out


# ===========================================================================
# 2. One hand-built engagement that every law above passes.
#    This is the negative control shared by S1-S6: without it a law that fails
#    proves only that something is impossible.
# ===========================================================================

CLIENT_SENTENCE = "we move 4200 parcels a week out of the northern depots"
TURN_TEXT = f"Good morning. {CLIENT_SENTENCE}. We must decide before the peak season."


def row(kind, payload, *, eid, actor=Actor.PARTNER, status=Status.PROPOSED, derived=(),
        decision_id="DEC-1", weight=0.5, relation=RelationToCentralDecision.INFORMS) -> Entity:
    return make_entity(
        kind=kind, engagement_id="E-1", payload=payload,
        provenance=Provenance(actor=actor, actor_ref=f"{actor.value}:1",
                              derived_from=tuple(derived), source_locator=None,
                              recorded_at=FIXED_CLOCK),
        confidence=Confidence(None), relevance=Relevance(decision_id, weight),
        relation=relation, status=status, entity_id=eid)


def sound_rows() -> list[Entity]:
    """An engagement that concluded: one decision, one capability gap, two
    routes to it, a criterion the client weighted, a comparison that scores
    both routes, and ONE recommendation that selects the winner and words
    itself out of the relation between the rows rather than out of any one of
    them."""
    return [
        row(Kind.EVIDENCE_SOURCE, EvidenceSourcePayload(
            name="opening conversation", source_kind=SourceKind.CONVERSATION_TURN,
            text=TURN_TEXT, received_at=FIXED_CLOCK), eid="EVI-1"),
        row(Kind.MEASURE, MeasurePayload(name="weekly parcel volume", unit_family=UnitFamily.COUNT,
                                         definition="parcels leaving the depots in a week",
                                         confirmed_by_client=True),
            eid="MEA-1", actor=Actor.CLIENT),
        row(Kind.DECISION, DecisionPayload(statement="whether to consolidate the depots",
                                           role=DecisionRole.CENTRAL), eid="DEC-1"),
        row(Kind.FACT, FactPayload(
            statement=CLIENT_SENTENCE, basis=FactBasis.CLIENT_STATED, measure_id="MEA-1",
            quantity=Quantity(Decimal("4200"), "parcels", UnitFamily.COUNT,
                              Dimensions(currency=None, period="2026-01", period_basis="week",
                                         scope="the northern depots", as_of="2026-01-31",
                                         definition=None), 0),
            topic="volume"),
            eid="FCT-1", actor=Actor.CLIENT, status=Status.CONFIRMED, derived=("EVI-1",)),
        row(Kind.CAPABILITY, CapabilityPayload(text="a single northern sortation line",
                                               capability_class=CapabilityClass.PROCESS,
                                               gap=GapState.MISSING, evidence=("FCT-1",)),
            eid="CAP-1", derived=("FCT-1",)),
        row(Kind.OPTION, OptionPayload(text="run the sortation line in house", decision_id="DEC-1",
                                       mechanism="make", evidence=("CAP-1",)),
            eid="OPT-1", derived=("CAP-1",), relation=RelationToCentralDecision.RESOLVES),
        row(Kind.OPTION, OptionPayload(text="buy sortation as a service", decision_id="DEC-1",
                                       mechanism="buy", evidence=("CAP-1",)),
            eid="OPT-2", derived=("CAP-1",), relation=RelationToCentralDecision.RESOLVES),
        row(Kind.EVALUATION_CRITERION, EvaluationCriterionPayload(
            text="peak week throughput", decision_id="DEC-1", weight=0.7,
            weight_set_by=Authority.CLIENT), eid="CRI-1", derived=("DEC-1",)),
        row(Kind.TRADE_OFF, TradeOffPayload(
            decision_id="DEC-1", option_ids=("OPT-1", "OPT-2"),
            gives_up="a supplier relationship the client already has",
            gains="control of the peak week roster",
            scores=(Score("OPT-1", "CRI-1", Decimal("0.8"), ("FCT-1",)),
                    Score("OPT-2", "CRI-1", Decimal("0.4"), ("FCT-1",)))),
            eid="TRD-1", derived=("CAP-1", "OPT-1", "OPT-2"),
            relation=RelationToCentralDecision.RESOLVES),
        row(Kind.RECOMMENDATION, RecommendationPayload(
            statement="Run the sortation line in house rather than buying it as a service: it "
                      "leads on peak week throughput, and gives up a supplier relationship the "
                      "client already has.",
            decision_id="DEC-1", option_id="OPT-1", supports=("FCT-1",)),
            eid="REC-1", derived=("OPT-1", "DEC-1", "CRI-1", "TRD-1", "FCT-1"),
            relation=RelationToCentralDecision.RESOLVES),
    ]


def silent_rows() -> list[Entity]:
    """The same engagement with its advice taken away: two routes on the table,
    a capability gap found, and nothing concluded about the decision. Routes are
    the question laid out, not an answer to it, which is why this is the fixture
    both S2 and Law E of `test_engine_analysis_quality.py` are measured on."""
    return [r for r in sound_rows() if r.kind is not Kind.RECOMMENDATION]


def settling_question(eid: str = "QST-1") -> Entity:
    """The record a consultant who cannot conclude leaves: an open question
    filed against the decision it blocks (`Relevance.decision_id`, which `row`
    sets from its `decision_id` argument) and naming in `asks_for` the KIND of
    evidence that would settle it."""
    return row(Kind.QUESTION, QuestionPayload(
        text="Which of your records gives the peak week volume per depot?",
        asks_for=(T.AsksFor(Kind.FACT),), material=True,
        why="the routes cannot be compared until the peak week volume is known",
        effort=EffortClass.LOOKUP, strategy=FillStrategy.ASK_CLIENT),
        eid=eid, status=Status.OPEN, derived=("DEC-1",))


def declared_rows() -> list[Entity]:
    """The engagement that concluded nothing and said what would settle it. A
    recorded reason is itself a conclusion about the engagement, so every law
    that asks for a conclusion must accept this one."""
    return silent_rows() + [settling_question()]


def build(rows=None) -> EngagementRegistry:
    return EngagementRegistry.from_rows("E-1", list(sound_rows() if rows is None else rows),
                                        clock=lambda: FIXED_CLOCK)


@pytest.fixture
def sound():
    return build()


# ===========================================================================
# S1 - termination at the condition, not the wall
# ===========================================================================

def test_s1_production_stops_at_its_condition_not_at_the_registry_door(runs):
    """S1. Every analysis kind an engagement generates stays inside
    MAX_ENTITIES_PER_ANALYSIS_KIND, and no row is ever refused for capacity.

    Counted on the write path because the survivors cannot show it: I9 refuses
    the row, `apply_all` rolls the whole batch back, and the live count comes to
    rest BELOW the ceiling that refused it - which is also why `saturated_kinds`
    never fires and the pre-selection guard never stops the producer. Cap and
    guard defeat each other; the offered count is the only place the defeat is
    visible.

    mutation caught: raise the ceiling, or widen what ANALYSIS_KINDS excludes.
    Live counts go legal, the refusals stop, and generation runs away exactly as
    before - this test still fails, on the generated count, because `ceiling()`
    is the declared bound LIMITED BY the three bounds it is derived from and
    `ANALYSIS_KINDS` is pinned by name below. Both halves were open until then:
    the law read the same value its mutation moves, so goalposts and measuring
    stick moved together and the mutation this docstring names survived it.
    """
    # NEGATIVE CONTROL: a run that stopped when it was finished.
    assert capacity_breaches({"OPTION": 3, "CAPABILITY": 1, "FACT": 10_000}, {}, ceiling()) == [], \
        "a run inside the bound with no refusal breaches nothing - and evidence is not rationed"

    breaches = {r.case_id: capacity_breaches(r.generated, r.refused_by_capacity, ceiling())
                for r in runs.values()}
    offending = {case: why for case, why in breaches.items() if why}
    assert offending == {}, (
        "production ran until the registry door refused it:\n"
        + "\n".join(f"  {case}: {'; '.join(why)}" for case, why in sorted(offending.items())))


def test_s1_the_ceiling_this_law_reads_cannot_be_raised_by_its_own_mutation():
    """S1, the half that was missing. The bound S1 measures against is declared
    in one place and read by the engine and by this law alike, so "raise
    MAX_ENTITIES_PER_ANALYSIS_KIND" - the mutation S1's docstring names - moved
    the law and the engine by the same amount and was caught by neither.

    Three statements close it:

      - the DECLARED bound is inside the default the other bounds defend, so the
        table cannot grant the engine room the rest of the table does not;
      - the LIVE ceiling the registry actually rations by is inside it too - I9
        reads the operator setting and this law read the table, so the two could
        part in silence;
      - and `ceiling()` returns the smaller of the two whatever either says, so
        even the run in which one of the above is the thing being fixed is
        judged with a stick that did not move.

    mutation caught: BOUNDS["MAX_ENTITIES_PER_ANALYSIS_KIND"] = 100_000, or the
    same value installed on Settings. Both went green everywhere before this.
    """
    declared = int(BOUNDS["MAX_ENTITIES_PER_ANALYSIS_KIND"])
    default = defensible_ceiling()
    assert declared <= default, (
        f"the declared bound is {declared}, above the {default} that MAX_ANALYSIS_ROUNDS x "
        f"MAX_SPECIALISTS_PER_ROUND x MAX_FANOUT can defend; a larger ceiling is not this "
        f"bound's to grant")

    from app.engine.registry import EngagementRegistry

    live_ceiling = int(EngagementRegistry("E-pin", clock=lambda: FIXED_CLOCK)._capacity())
    assert live_ceiling <= default, (
        f"the engine rations by {live_ceiling}, above the defensible {default}; I9 reads the "
        f"operator setting, so the room the table refuses can still be taken there")

    assert ceiling() <= default, "the stick S1 measures with moved"


def test_s1_the_kinds_the_ceiling_applies_to_are_pinned_by_name():
    """S1's OTHER named mutation: "widen what ANALYSIS_KINDS excludes".

    `capacity_breaches` counts only the kinds in ANALYSIS_KINDS, and so do I9
    and `saturated_kinds`. Drop OPTION from that tuple and all three go blind to
    routes at once: the registry stops refusing them, the pre-selection guard
    stops seeing the producer fill up, and S1 stops counting them on the write
    path. Nothing else in the suite reads the membership, so the narrowing is
    invisible - the shape of a starvation mutation, except that this one causes
    a runaway.

    Pinned as a SET OF NAMES: a reordering is not a defect, a deletion cannot be
    spelled as one, and an addition has to be made deliberately here. The
    positive half - only conclusions are rationed - is stated too, so the pin
    cannot be satisfied by adding FACT to the tuple and calling it fixed.
    """
    rationed = {
        "CAPABILITY", "OPTION", "EVALUATION_CRITERION", "TRADE_OFF", "RECOMMENDATION",
        "PROCESS_STEP", "WORKSTREAM", "INITIATIVE", "ACTION", "HYPOTHESIS", "RISK", "CONTROL",
    }
    declared = {k.name for k in ANALYSIS_KINDS}
    gone = sorted(rationed - declared) or "-"
    added = sorted(declared - rationed) or "-"
    assert declared == rationed, (
        f"the kinds the engine rations have changed; no longer rationed: {gone}; "
        f"newly rationed: {added}")
    assert len(ANALYSIS_KINDS) == len(set(ANALYSIS_KINDS)), "a kind is rationed twice"

    # Evidence the client handed over is not the engine's to ration, and the
    # records it is audited by are not conclusions.
    for kind in (Kind.FACT, Kind.EVIDENCE_SOURCE, Kind.QUESTION, Kind.ANALYSIS,
                 Kind.DECISION, Kind.MEASURE, Kind.CHARTER):
        assert kind not in ANALYSIS_KINDS, f"{kind.name} is not a conclusion the engine emits"

    # And the pin is not decorative: this is the function S1 counts with, so a
    # kind removed from the tuple stops being counted by it.
    assert capacity_breaches({"OPTION": ceiling() + 1}, {}, ceiling()) != [], (
        "OPTION over the bound is a breach while OPTION is rationed")


# ===========================================================================
# S2 - every case concludes, or says why
# ===========================================================================

def test_s2_every_case_concludes_or_records_why_it_cannot(runs):
    """S2. Every engagement holds a live RECOMMENDATION, or a typed blocker - an
    OPEN QUESTION, a DECISION_REQUIRED, a CONFLICT - that is filed against the
    central decision AND names the evidence that would settle it. No exemption
    by run count.

    An engagement that concluded nothing and recorded no reason has not declined
    to advise; it has said nothing, and been graded as though silence were
    caution. An engagement that named the decision and not the missing evidence
    has said only that something is unanswered, which is the state the reader
    was already in.

    mutation caught: exempt an engagement below a run-count floor. The floor
    reads a number about the ENGINE (how much work it did) to excuse a hole in
    what the CLIENT got, and those are not the same question. And the mutation
    this law was itself repaired against: accept a blocker for MENTIONING the
    decision, `derived_from` included - proved separately, in the test below.
    """
    # NEGATIVE CONTROL: an engagement that concluded.
    assert unconcluded(build()) == []
    # ... and one that concluded nothing but said why, in one typed row.
    assert unconcluded(build(declared_rows())) == [], \
        "a recorded reason is itself a conclusion about the engagement"

    silence = {r.case_id: unconcluded(r.registry) for r in runs.values()}
    offending = {case: why for case, why in silence.items() if why}
    assert offending == {}, (
        "an engagement reached synthesis and said nothing:\n"
        + "\n".join(f"  {case}: {'; '.join(why)}" for case, why in sorted(offending.items())))


def test_s2_a_blocker_names_the_evidence_that_would_settle_the_decision(runs):
    """S2's second branch, and the proof that repairing it changed something.

    `typed_blockers` used to accept any OPEN QUESTION, DECISION_REQUIRED or
    CONFLICT that MENTIONED the decision, and `names_decision` counted a
    mention in `derived_from` - a link nearly every row in an engagement
    carries. So an engagement could hold a hundred open questions about
    anything at all, conclude nothing, and be reported by S2 as having said why.
    `lineage_only_blockers` is that clause, kept verbatim; the law above is the
    repair.

    The fixture separates them. It is an engagement that concluded nothing and
    holds ONE open question, about who signs the leases - nothing to do with
    the choice - which happens to cite the decision in its lineage. The ghost
    accepts it and S2 fell silent. The repaired predicate does not, because
    nothing on that row says it is why THIS decision is unanswered.

    The population half is what stops the fixture being dismissed as contrived:
    across the benchmark the repair must actually REFUSE rows the ghost
    accepted (or nothing was repaired), while every engagement still records a
    blocker that names what it is waiting for (or the repair is a law nothing
    can pass, which is the other way to make a law vacuous).

    mutation caught: widen `names_decision` back to `derived_from`, or drop the
    `asks_for` clause. Either restores a blocker that says a decision is
    unanswered without saying what would answer it.
    """
    unrelated = row(Kind.QUESTION, QuestionPayload(
        text="Who signs off the depot lease renewals?",
        asks_for=(T.AsksFor(Kind.DECISION_OWNER),),
        why="the lease owner is not recorded",
        effort=EffortClass.OFFHAND, strategy=FillStrategy.ASK_CLIENT),
        # decision_id=None is not a contrivance: `Relevance.decision_id` is
        # documented as "the DECISION this bears on (None == not yet
        # attached)", and the lineage link is the only thing tying this
        # question to DEC-1 - which is exactly what the old clause read.
        eid="QST-1", status=Status.OPEN, derived=("DEC-1",), decision_id=None, weight=0.0)
    view = build(silent_rows() + [unrelated])

    assert lineage_only_blockers(view, "DEC-1") == ["QST-1"], \
        "the clause S2 used to read accepts a question that names the decision in its lineage"
    assert typed_blockers(view, "DEC-1") == [], \
        "the repaired clause refuses it: nothing on that row says what would settle DEC-1"
    assert unconcluded(view), \
        "so S2 now reports the engagement as having concluded nothing and said nothing"

    # The other half of the repair, on its own fixture: a question filed
    # against the decision by its own typed field, asking for NOTHING. It says
    # the decision is unanswered - which the reader knew - and does not say
    # what would answer it.
    unasked = row(Kind.QUESTION, QuestionPayload(
        text="Is the peak week volume per depot known?", decision_id="DEC-1",
        why="the routes cannot be compared until it is",
        effort=EffortClass.OFFHAND, strategy=FillStrategy.ASK_CLIENT),
        eid="QST-1", status=Status.OPEN, derived=("DEC-1",))
    silent_ask = build(silent_rows() + [unasked])
    assert lineage_only_blockers(silent_ask, "DEC-1") == ["QST-1"], \
        "the clause S2 used to read accepts a question that asks for nothing"
    assert typed_blockers(silent_ask, "DEC-1") == [], \
        "the repaired clause refuses it: `asks_for` is where the missing evidence is named"
    assert unconcluded(silent_ask), "so S2 reports it too"

    # NEGATIVE CONTROL: the same engagement with a question filed against the
    # decision it blocks, naming the kind of evidence that would settle it. The
    # repair is strict, not unsatisfiable.
    declared = build(declared_rows())
    assert typed_blockers(declared, "DEC-1") == ["QST-1"]
    assert unconcluded(declared) == []

    refused: dict[str, list[str]] = {}
    silent: dict[str, str] = {}
    for r in runs.values():
        decision = central(r.registry)
        if decision is None:
            continue
        ghost = set(lineage_only_blockers(r.registry, decision.id))
        kept = set(typed_blockers(r.registry, decision.id))
        if ghost - kept:
            refused[r.case_id] = sorted(ghost - kept)
        if ghost and not kept:
            opens = list(r.registry.query(Kind.QUESTION, status=Status.OPEN))
            silent[r.case_id] = (
                f"{len(ghost)} row(s) mention {decision.id} and none of them names what would "
                f"settle it; {len(opens)} open question(s) in the engagement")
    assert silent == {}, (
        "S2's second branch is satisfied by rows that say a decision is unanswered without "
        "saying what would answer it:\n"
        + "\n".join(f"  {case}: {why}" for case, why in sorted(silent.items())))
    assert refused, (
        "the repair refused nothing anywhere in the benchmark: every row the old clause accepted "
        "is accepted by the new one, so the two predicates are the same law under two names")


# ===========================================================================
# S3 - one coherent recommendation per decision
# ===========================================================================

def test_s3_no_two_recommendations_on_one_decision_exclude_each_other(runs):
    """S3. For each live DECISION, the live recommendations on it are not
    mutually exclusive: either exactly one stands, or the several that stand can
    all be taken.

    Three routes to one capability gap are one choice with three answers. Set
    beside each other as recommendations they are not advice at all - the reader
    is handed the decision back, dressed as a conclusion.

    mutation caught: dedupe recommendations by the id each cites (the action,
    the option) instead of by the choice each makes. Citation-keyed dedup cannot
    see that make, buy and partner on one gap are the same choice, which is how
    one decision came to carry seventy-two recommendations.
    """
    # NEGATIVE CONTROL 1: one recommendation, the alternatives under it as
    # OPTIONs.
    assert incoherent(build()) == []
    # NEGATIVE CONTROL 2: two recommendations on one decision that are NOT
    # rivals - different subjects, no mechanism clash, no trade-off pairing
    # them. The law is about exclusivity, not about a count.
    both = list(sound_rows())
    both.append(row(Kind.CAPABILITY, CapabilityPayload(
        text="a night shift roster", capability_class=CapabilityClass.PEOPLE_AND_ORGANISATION,
        gap=GapState.MISSING, evidence=("FCT-1",)), eid="CAP-2", derived=("FCT-1",)))
    both.append(row(Kind.OPTION, OptionPayload(
        text="staff a night shift", decision_id="DEC-1", mechanism="make", evidence=("CAP-2",)),
        eid="OPT-3", derived=("CAP-2",), relation=RelationToCentralDecision.RESOLVES))
    both.append(row(Kind.RECOMMENDATION, RecommendationPayload(
        statement="Staff a night shift alongside the in-house line.", decision_id="DEC-1",
        option_id="OPT-3", supports=("FCT-1",)), eid="REC-2",
        derived=("OPT-3", "DEC-1", "CRI-1", "FCT-1"),
        relation=RelationToCentralDecision.RESOLVES))
    assert incoherent(build(both)) == [], \
        "two compatible recommendations on one decision are two pieces of advice, not a clash"

    clashes = {r.case_id: incoherent(r.registry) for r in runs.values()}
    offending = {case: why for case, why in clashes.items() if why}
    assert offending == {}, (
        "one decision carries recommendations that exclude each other:\n"
        + "\n".join(f"  {case}: {len(why)} contradictory pair(s), e.g. {why[0]}"
                    for case, why in sorted(offending.items())))


# ===========================================================================
# S4 - a recommendation selects and explains
# ===========================================================================

def test_s4_every_recommendation_selects_a_route_and_says_what_it_beat(runs):
    """S4. Every live RECOMMENDATION names the live OPTION it selects for its
    own decision, cites an EVALUATION_CRITERION for that decision, and cites the
    TRADE_OFF in which that option was weighed against at least one other live
    route - a trade-off that actually discriminates (a score for the chosen
    route, or a recorded gives-up / gains).

    "Why this one" is a relation between rows. It cannot be copied off any
    single row, which is exactly why it is the test of whether the engine
    concluded or emitted.

    mutation caught: keep the option and the criteria, drop the comparison. The
    advice still names a route and cites a standard, can no longer say what it
    was weighed against, and no query of the registry could recover it.
    """
    # NEGATIVE CONTROL: a recommendation that selects, cites its criterion, and
    # cites the scored comparison it won.
    assert unselective(build()) == []

    thin = {r.case_id: unselective(r.registry) for r in runs.values()}
    offending = {case: why for case, why in thin.items() if why}
    assert offending == {}, (
        "advice that selected without comparing:\n"
        + "\n".join(f"  {case}: {len(why)} of "
                    f"{len(live(runs[case].registry, Kind.RECOMMENDATION))} recommendations, "
                    f"e.g. {why[0]}"
                    for case, why in sorted(offending.items())))


# ===========================================================================
# S5 - traces but does not copy
# ===========================================================================

def test_s5_a_recommendation_traces_to_evidence_and_never_repeats_it(runs):
    """S5. Every live RECOMMENDATION rests on supports, and its statement
    neither contains nor is contained by the claim of any live FACT or MEASURE.

    The engine polices invention (`coined_figures` fails text that departs from
    its source) and has never policed copying, so the safest possible output -
    repeating the evidence - scored highest under every check that existed.

    mutation caught: bolt a frame onto a copied claim. "Take the route: Stand up
    Reported NPS is 46. with the organisation's own people and systems" is not
    EQUAL to any fact, and is not authored either; containment sees the borrowed
    sentence sitting inside the frame. Comparison is exact - whitespace
    normalised, case folded, substring - and never a ratio.
    """
    # NEGATIVE CONTROL: a composed statement drawing on the same evidence that
    # repeats none of it.
    assert copied(build()) == []

    plagiarism = {r.case_id: copied(r.registry) for r in runs.values()}
    offending = {case: why for case, why in plagiarism.items() if why}
    assert offending == {}, (
        "advice that repeats its own evidence:\n"
        + "\n".join(f"  {case}: {len(why)} of "
                    f"{len(live(runs[case].registry, Kind.RECOMMENDATION))} recommendations, "
                    f"e.g. {why[0]}"
                    for case, why in sorted(offending.items())))


def test_s5_reads_no_similarity_measure():
    """S5's comparison is exact. A ratio would let a rewording of a copied claim
    through, and would turn the law into an opinion about how close is too
    close. Pinned as source, because an import added later would pass every
    other test in this file."""
    import pathlib

    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    for name in ("dif" "flib", "Sequence" "Matcher", "rapid" "fuzz", "Leven" "shtein"):
        assert name not in source, f"{name} is a similarity measure; S5 compares exactly"


# ===========================================================================
# S6 - the gate blocks
# ===========================================================================

def contradictory_rows() -> list[Entity]:
    """The sound engagement plus a second recommendation that takes the route
    the first one declined. Both live, both on DEC-1, both selecting a route the
    same TRADE_OFF weighs against the other."""
    rows = list(sound_rows())
    rows.append(row(Kind.RECOMMENDATION, RecommendationPayload(
        statement="Buy sortation as a service rather than running it in house: it leads on the "
                  "supplier relationship already in place.",
        decision_id="DEC-1", option_id="OPT-2", supports=("FCT-1",)),
        eid="REC-2", derived=("OPT-2", "DEC-1", "CRI-1", "TRD-1", "FCT-1"),
        relation=RelationToCentralDecision.RESOLVES))
    return rows


def overspecific_rows() -> list[Entity]:
    """The sound engagement with its recommendation replaced by one that asserts
    a figure and a scope its support closure does not carry. FCT-1 establishes
    4200 parcels a week out of the northern depots; nothing in the closure
    establishes 15 per cent, and nothing establishes the southern depots."""
    rows = [r for r in sound_rows() if r.id != "REC-1"]
    rows.append(row(Kind.RECOMMENDATION, RecommendationPayload(
        statement="Run the sortation line in house: it cuts handling cost by 15 per cent across "
                  "the southern depots.",
        decision_id="DEC-1", option_id="OPT-1", supports=("FCT-1",)),
        eid="REC-1", derived=("OPT-1", "DEC-1", "CRI-1", "TRD-1", "FCT-1"),
        relation=RelationToCentralDecision.RESOLVES))
    return rows


def gate_status(view, artifacts: tuple[ArtifactRef, ...] = ()) -> dict:
    return release_status(run_laws(view, artifacts))


def test_s6_the_gate_passes_a_sound_engagement(sound):
    """NEGATIVE CONTROL for both S6 laws, and the thing that makes them mean
    something: the same door, on the same shape of engagement, opens."""
    assert run_laws(sound, ()) == []
    assert gate_status(sound)["status"] != STATUS_DRAFT


def test_s6_the_gate_refuses_a_contradictory_pair_of_recommendations():
    """S6a. Two recommendations on one decision that exclude each other must
    BLOCK release, at the gate - `release_status(run_laws(...))` - and not only
    in a benchmark assertion a release never reads.

    A contradiction is the one defect a reader is guaranteed to find, because
    both halves are printed on the same page. It is also the defect a registry
    can prove without reading a word: the trade-off names both routes.

    mutation caught: state the check in the benchmark only. The suite goes
    green, the benchmark reports it, and the door still opens.
    """
    view = build(contradictory_rows())
    assert incoherent(view), "the fixture really does hold a contradictory pair"
    verdict = gate_status(view)
    assert verdict["status"] == STATUS_DRAFT, (
        "the gate released an engagement advising two routes that exclude each other; "
        f"reasons were {verdict['reasons']}")
    assert any("REC-1" in reason and "REC-2" in reason for reason in verdict["reasons"]), \
        f"no blocking finding names the contradictory pair: {verdict['reasons']}"


def test_s6_the_gate_refuses_specificity_the_support_closure_does_not_carry():
    """S6b. A recommendation asserting more than its supports establish must
    BLOCK release, at the gate.

    The statement here claims a 15 per cent cut across the southern depots. Its
    whole support closure is one confirmed fact about 4200 parcels a week out of
    the NORTHERN depots. Nothing was misquoted and no number miscopied - the
    advice simply says more than it can show, which is the failure a client
    discovers after acting on it.

    Read at the registry, with no artifact: L11 reads figures off a rendered
    page, so a claim that never reaches a page is invisible to it, and a
    recommendation is a claim whether or not anything has been printed yet.

    mutation caught: rely on L11 and the printed page. Nothing on the page is
    wrong until the page exists.
    """
    view = build(overspecific_rows())
    verdict = gate_status(view)
    assert verdict["status"] == STATUS_DRAFT, (
        "the gate released advice asserting a figure and a scope its evidence does not carry; "
        f"reasons were {verdict['reasons']}")
    assert any("REC-1" in reason for reason in verdict["reasons"]), \
        f"no blocking finding names the over-specific recommendation: {verdict['reasons']}"


# ===========================================================================
# S7 - the six starvation mutations
#
# Each pair of tests states the law and then applies its mutation with
# monkeypatch, so the law is never merely an assertion nobody can break. No
# production module is edited.
# ===========================================================================

SHAPE_FIRST = QuestionShape(T.Interrogative.WHAT, Kind.FACT)
SHAPE_SECOND = QuestionShape(T.Interrogative.WHICH, Kind.CAPABILITY, comparative=True)


def method_spec(mid: str, shape: QuestionShape, *, needs: tuple[InputSpec, ...],
                writes: tuple[Kind, ...], cost: int = 1) -> MethodSpec:
    return MethodSpec(
        id=mid, version=1, applicability=(shape,), answers=(shape.interrogative,),
        required_inputs=needs, optional_inputs=(),
        execution=T.ExecutionType.DETERMINISTIC, output_kinds=writes, output_schema=None,
        evidence=EvidenceRequirement(), limitations=(), validators=(),
        cost_class=cost, max_model_calls=0)


class Inert:
    """A method that writes nothing. Selection, not execution, is what these six
    tests are about, and a writer would change the registry under them."""

    def __init__(self, spec: MethodSpec):
        self.spec = spec

    def run(self, ctx: MethodContext) -> MethodResult:      # pragma: no cover - never run here
        return MethodResult()


def library(*specs: MethodSpec) -> MethodRegistry:
    reg = MethodRegistry()
    for spec in specs:
        reg.register(Inert(spec))
    return reg


def tiered_registry(registry_factory) -> Any:
    """A registry mid-engagement: a central decision, a fact, an issue node the
    second-tier method takes on, and an OPEN question that has asked the client
    for the very kind that method is missing."""
    reg = registry_factory("E-1")
    reg.apply(Add(row(Kind.DECISION, DecisionPayload(
        statement="which sortation route", role=DecisionRole.CENTRAL), eid="DEC-1")))
    reg.apply(Add(row(Kind.FACT, FactPayload(statement=CLIENT_SENTENCE,
                                             basis=FactBasis.INFERRED),
                      eid="FCT-1", derived=("DEC-1",))))
    reg.apply(Add(row(Kind.ISSUE, T.IssuePayload(
        text="which route closes the gap", interrogative=SHAPE_SECOND.interrogative,
        target_kind=SHAPE_SECOND.target_kind, comparative=True, decisive_for=("DEC-1",)),
        eid="ISS-1", relation=RelationToCentralDecision.DEFINES)))
    reg.apply(Add(row(Kind.QUESTION, QuestionPayload(
        text="Which capabilities does the depot already have?",
        asks_for=(T.AsksFor(Kind.CAPABILITY),), issue_ids=("ISS-1",),
        why="the routes cannot be enumerated until the gaps are known",
        effort=EffortClass.LOOKUP, strategy=FillStrategy.ASK_CLIENT),
        eid="QST-1", status=Status.OPEN, derived=("ISS-1",))))
    return reg


def second_tier_methods() -> set[str]:
    """The methods a first pass CANNOT satisfy: those requiring a kind the
    engine concludes rather than one the client hands over. Read off
    ANALYSIS_KINDS and the library's own declarations, never off a list of
    method names written here."""
    return {m.spec.id for m in METHODS.all()
            if any(i.kind in ANALYSIS_KINDS and i.min_count >= 1
                   for i in m.spec.required_inputs)}


def test_s7a_analysis_does_not_end_after_one_tier(registry, runs):
    """S7(a) - mutation: `outstanding_inputs` returns [], or the second term of
    `synthesis_blockers` is dropped.

    "Nothing runnable at this instant" is not "analysis is complete". A method
    whose inputs are another method's outputs, or an answer the client has been
    asked for and not yet given, is unsatisfied on every first pass - and
    PHASE_TRANSITIONS offers no way back from SYNTHESIS, so answering on the
    first term alone ends every engagement after one tier of the dependency
    graph.

    Two halves. The guard must hold the door on a registry that is waiting; and
    the engagements must actually have gone through it - every case must have
    run at least one method whose required inputs are an ANALYSIS kind, which is
    something no client can hand over and only an earlier method can write.
    """
    methods = library(
        method_spec("tier2", SHAPE_SECOND,
                    needs=(InputSpec("capabilities", Kind.CAPABILITY, min_count=1,
                                     why_needed="the gap a route would close"),),
                    writes=(Kind.OPTION,)))
    reg = tiered_registry(registry)

    assert S.runnable_selections(reg, methods=methods) == [], "nothing is runnable at this instant"
    assert S.outstanding_inputs(reg, methods=methods), "but something is still expected to arrive"
    assert S.synthesis_blockers(reg, rounds_used=0, methods=methods), \
        "so analysis stays open for the tier that has not run"

    # NEGATIVE CONTROL: once the awaited kind lands and the method has been
    # attempted, nothing is left and SYNTHESIS is reachable. The guard refuses a
    # first pass, not every pass.
    reg.apply(Add(row(Kind.CAPABILITY, CapabilityPayload(
        text="a single northern sortation line", capability_class=CapabilityClass.PROCESS,
        gap=GapState.MISSING, evidence=("FCT-1",)), eid="CAP-1", derived=("FCT-1",))))
    reg.apply(Add(row(Kind.ANALYSIS, T.AnalysisPayload(
        method_id="tier2", method_version=1, issue_ids=("ISS-1",),
        state=T.AnalysisState.DONE), eid="ANA-1", derived=("ISS-1",))))
    assert S.synthesis_blockers(reg, rounds_used=0, methods=methods) == ()

    tier = second_tier_methods()
    assert tier, "the library declares methods that consume what an analysis concludes"
    stalled = {r.case_id: sorted(set(r.methods)) for r in runs.values()
               if not (set(r.methods) & tier)}
    assert stalled == {}, (
        "analysis ended after one tier: no method consuming an analysis kind ever ran:\n"
        + "\n".join(f"  {case}: ran {ran}" for case, ran in sorted(stalled.items())))


def test_s7a_the_mutation_is_what_ends_it(registry, monkeypatch):
    """S7(a), the mutation applied. With `outstanding_inputs` returning nothing,
    the guard above falls silent and SYNTHESIS opens on a registry whose second
    tier has not run."""
    methods = library(
        method_spec("tier2", SHAPE_SECOND,
                    needs=(InputSpec("capabilities", Kind.CAPABILITY, min_count=1,
                                     why_needed="the gap a route would close"),),
                    writes=(Kind.OPTION,)))
    reg = tiered_registry(registry)
    assert S.synthesis_blockers(reg, rounds_used=0, methods=methods), "held before the mutation"

    monkeypatch.setattr(S, "outstanding_inputs", lambda *a, **k: [])
    assert S.synthesis_blockers(reg, rounds_used=0, methods=methods) == (), \
        "the mutation must actually silence the guard, or this pin proves nothing"


# -- (b) and (c): the capability gate --------------------------------------

def make_buy_context(reg) -> MethodContext:
    return MethodContext(registry=reg, provider=None, calc=None, actor=Actor.METHOD,
                         actor_ref="method:make_buy_partner@1", issue_ids=("ISS-1",), settings={})


def gap_registry(registry_factory) -> Any:
    """One central decision and one capability in each gap state the engine
    declares. Nothing else, so the routes written are a function of the gate
    alone."""
    reg = registry_factory("E-1")
    reg.apply(Add(row(Kind.DECISION, DecisionPayload(
        statement="which sortation route", role=DecisionRole.CENTRAL), eid="DEC-1")))
    reg.apply(Add(row(Kind.FACT, FactPayload(statement=CLIENT_SENTENCE,
                                             basis=FactBasis.INFERRED),
                      eid="FCT-1", derived=("DEC-1",))))
    for n, gap in enumerate(GapState, start=1):
        reg.apply(Add(row(Kind.CAPABILITY, CapabilityPayload(
            text=f"the {gap.value} capability", capability_class=CapabilityClass.PROCESS,
            gap=gap, evidence=("FCT-1",)), eid=f"CAP-{n}", derived=("FCT-1",))))
    return reg


def routes_written(reg) -> dict[str, set[str]]:
    """capability id -> the mechanisms make_buy_partner put on the table for it,
    from one run of the real method."""
    from app.engine.methods.builtin.make_buy_partner import MakeBuyPartner

    result = MakeBuyPartner().run(make_buy_context(reg))
    out: dict[str, set[str]] = {}
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not Kind.OPTION:
            continue
        for cap_id in e.payload.evidence:
            out.setdefault(cap_id, set()).add(e.payload.mechanism)
    return out


def open_gaps(reg) -> list[str]:
    return [c.id for c in live(reg, Kind.CAPABILITY) if c.payload.gap is not GapState.PRESENT]


def test_s7b_every_open_gap_gets_every_route(registry):
    """S7(b) - mutation: narrow the capability gate to GapState.MISSING, so a
    PARTIAL gap is never sourced.

    A capability the client half has is still a capability whose provider is in
    question - that is what PARTIAL MEANS. Narrowing the gate starves the only
    producer of OPTION in the library, and with no route on the table there is
    nothing a recommendation could select. Nothing else in the suite would
    notice: the method still runs, still writes rows, still passes every
    validator it declares.

    The law: every capability whose gap is not PRESENT gets the whole closed
    answer set. The gate is stated once, as "not PRESENT", and read off the enum
    rather than off a list of gap names written here.
    """
    reg = gap_registry(registry)
    written = routes_written(reg)
    mechanisms = {m for routes in written.values() for m in routes}
    assert len(mechanisms) >= 2, "the closed answer set has more than one route in it"

    for cap_id in open_gaps(reg):
        assert written.get(cap_id) == mechanisms, \
            f"{cap_id} is an open gap and did not get every route: {written.get(cap_id)}"

    # NEGATIVE CONTROL: a capability that is PRESENT is not a gap and gets
    # nothing. The law is about open gaps, not about every row of the kind.
    present = [c.id for c in live(reg, Kind.CAPABILITY) if c.payload.gap is GapState.PRESENT]
    assert present, "the fixture holds a capability that is not a gap"
    for cap_id in present:
        assert cap_id not in written, f"{cap_id} is PRESENT and needs no sourcing route"


def test_s7b_the_narrowing_to_missing_is_caught(registry, monkeypatch):
    """S7(b), the mutation applied: the gate reads `gap is MISSING`."""
    import app.engine.methods.builtin.make_buy_partner as MBP

    reg = gap_registry(registry)
    before = routes_written(reg)
    partial = [c.id for c in live(reg, Kind.CAPABILITY) if c.payload.gap is GapState.PARTIAL]
    assert partial and all(before.get(i) for i in partial), "PARTIAL is sourced before the mutation"

    original = MBP.live

    def narrowed(view, kind):
        rows = original(view, kind)
        if kind is Kind.CAPABILITY:
            return [c for c in rows if c.payload.gap is GapState.MISSING]
        return rows

    monkeypatch.setattr(MBP, "live", narrowed)
    after = routes_written(reg)
    assert all(not after.get(i) for i in partial), \
        "the mutation must actually starve PARTIAL, or this pin proves nothing"


def test_s7c_the_narrowing_that_drops_present_unused_is_caught(registry, monkeypatch):
    """S7(c) - mutation: the capability gate excludes PRESENT_UNUSED as well as
    PRESENT, on the reading that a capability the client HAS is not a gap.

    It is a gap. PRESENT_UNUSED is the state for a capability that exists and is
    not used, and how it comes to be used - in house, bought, or with a partner
    - is precisely the sourcing question. This is a second narrowing because it
    is a second argument, and either one alone silently removes a class of gap
    from the only producer of OPTION.
    """
    import app.engine.methods.builtin.make_buy_partner as MBP

    reg = gap_registry(registry)
    unused = [c.id for c in live(reg, Kind.CAPABILITY) if c.payload.gap is GapState.PRESENT_UNUSED]
    assert unused, "the fixture holds a PRESENT_UNUSED capability"

    before = routes_written(reg)
    assert all(before.get(i) for i in unused), \
        "a capability that exists and is not used is still a gap the routes answer"

    original = MBP.live

    def narrowed(view, kind):
        rows = original(view, kind)
        if kind is Kind.CAPABILITY:
            return [c for c in rows
                    if c.payload.gap not in (GapState.PRESENT, GapState.PRESENT_UNUSED)]
        return rows

    monkeypatch.setattr(MBP, "live", narrowed)
    after = routes_written(reg)
    assert all(not after.get(i) for i in unused), \
        "the mutation must actually starve PRESENT_UNUSED, or this pin proves nothing"


# -- (d) and (e): the node's slots, and the guard ---------------------------

def slotted_registry(registry_factory) -> Any:
    reg = registry_factory("E-1")
    reg.apply(Add(row(Kind.DECISION, DecisionPayload(
        statement="which sortation route", role=DecisionRole.CENTRAL), eid="DEC-1")))
    reg.apply(Add(row(Kind.FACT, FactPayload(statement=CLIENT_SENTENCE,
                                             basis=FactBasis.INFERRED),
                      eid="FCT-1", derived=("DEC-1",))))
    reg.apply(Add(row(Kind.ISSUE, T.IssuePayload(
        text="what the current state is", interrogative=SHAPE_FIRST.interrogative,
        target_kind=SHAPE_FIRST.target_kind, decisive_for=("DEC-1",)),
        eid="ISS-1", relation=RelationToCentralDecision.DEFINES)))
    return reg


def three_matching_methods() -> MethodRegistry:
    needs = (InputSpec("facts", Kind.FACT, min_count=1, why_needed="a fact to work from"),)
    return library(*(method_spec(mid, SHAPE_FIRST, needs=needs, writes=(Kind.CAPABILITY,),
                                 cost=cost)
                     for mid, cost in (("m_a", 1), ("m_b", 2), ("m_c", 3))))


def record_attempts(reg, method_ids, start: int) -> int:
    for n, method_id in enumerate(sorted(method_ids), start=start):
        reg.apply(Add(row(Kind.ANALYSIS, T.AnalysisPayload(
            method_id=method_id, method_version=1, issue_ids=("ISS-1",),
            state=T.AnalysisState.DONE), eid=f"ANA-{n}", derived=("ISS-1",))))
    return start + len(list(method_ids))


def test_s7d_an_attempted_method_releases_the_node_slot_it_held(registry):
    """S7(d) - mutation: drop the `exclude` predicate from `select_methods`, so
    a method that has already run on a node keeps one of that node's
    MAX_METHODS_PER_ISSUE slots for the rest of the engagement.

    Three methods match this node and the node has two slots. If the two that
    ran first keep them, the third can never be reached however satisfiable it
    becomes - and a method whose inputs the first two just wrote is head-of-line
    blocked by the very run that made it selectable. That is starvation with no
    error anywhere: every round reports work done.
    """
    methods = three_matching_methods()
    reg = slotted_registry(registry)
    per_issue = int(BOUNDS["MAX_METHODS_PER_ISSUE"])

    first = {s.method_id for s in S.open_selections(reg, methods=methods)}
    assert len(first) == per_issue, f"the node offers exactly its {per_issue} slots"

    nxt = record_attempts(reg, first, 1)

    after = {s.method_id for s in S.open_selections(reg, methods=methods)}
    assert after - first, f"the slots stayed with the methods that already ran: {sorted(after)}"
    assert not (after & first), \
        f"a method already attempted on the node is offered again: {sorted(after & first)}"

    # NEGATIVE CONTROL: releasing the slot is not the same as forgetting the
    # run. Once every matching method has been attempted the node offers
    # nothing, rather than cycling forever.
    record_attempts(reg, after, nxt)
    assert S.open_selections(reg, methods=methods) == []


def test_s7d_holding_the_slot_forever_is_caught(registry, monkeypatch):
    """S7(d), the mutation applied: `attempted` always answers False, which is
    what dropping the exclude predicate amounts to where selection reads it."""
    methods = three_matching_methods()
    reg = slotted_registry(registry)
    first = {s.method_id for s in S.open_selections(reg, methods=methods)}
    record_attempts(reg, first, 1)

    monkeypatch.setattr(S, "attempted", lambda view, method_id, issue_id: False)
    after = {s.method_id for s in S.open_selections(reg, methods=methods)}
    assert after == first, \
        "the mutation must actually re-offer the attempted methods, or this pin proves nothing"


def test_s7e_synthesis_is_earned_and_not_only_timed_out(registry, runs):
    """S7(e) - mutation: `synthesis_blockers` returns () unconditionally.

    Two halves, and the second is the one that matters.

    The guard itself must refuse: on a registry with runnable work left and the
    round ceiling not reached, SYNTHESIS is not open and `advance` says so.

    And the engagements must be EARNING it. MAX_ANALYSIS_ROUNDS is the
    unconditional escape, checked FIRST, so an engagement that always hits the
    ceiling reaches SYNTHESIS by timing out - and a `synthesis_blockers` that
    returned () unconditionally would be indistinguishable from the real one on
    every such run. A guard nothing can tell apart from its own mutation is not
    a guard; it is a formality the round budget renders moot.
    """
    methods = three_matching_methods()
    reg = slotted_registry(registry)
    assert S.runnable_selections(reg, methods=methods), "work is runnable"
    assert S.synthesis_blockers(reg, rounds_used=0, methods=methods), "so synthesis is not open"

    state = S.EngagementState(registry=reg, phase=T.Phase.ANALYSIS)
    with pytest.raises(S.PhaseError):
        S.advance(state, T.Phase.SYNTHESIS, rounds_used=0, methods=methods)
    assert state.phase is T.Phase.ANALYSIS

    # NEGATIVE CONTROL: with the work done, the same guard opens the door. The
    # node releases its slots as each method is attempted, so this takes as many
    # passes as the node has matching methods - which is the interleave working,
    # not a workaround.
    nxt = 1
    while (left := {s.method_id for s in S.open_selections(reg, methods=methods)}):
        nxt = record_attempts(reg, left, nxt)
    assert S.synthesis_blockers(reg, rounds_used=0, methods=methods) == ()
    assert S.advance(S.EngagementState(registry=reg, phase=T.Phase.ANALYSIS),
                     T.Phase.SYNTHESIS, rounds_used=0, methods=methods) is T.Phase.SYNTHESIS

    timed_out = {r.case_id: len(S.runnable_selections(r.registry))
                 for r in runs.values() if S.runnable_selections(r.registry)}
    assert timed_out == {}, (
        "synthesis was entered with work still runnable, so the round ceiling - not the guard - "
        "ended analysis, and a `synthesis_blockers` that always returned () would have behaved "
        "identically:\n"
        + "\n".join(f"  {case}: {n} selection(s) still runnable at synthesis"
                    for case, n in sorted(timed_out.items())))


def test_s7e_the_unconditional_guard_is_caught(registry, monkeypatch):
    """S7(e), the mutation applied: with the guard silenced, SYNTHESIS opens on
    an engagement with work still runnable."""
    methods = three_matching_methods()
    reg = slotted_registry(registry)
    state = S.EngagementState(registry=reg, phase=T.Phase.ANALYSIS)
    with pytest.raises(S.PhaseError):
        S.advance(state, T.Phase.SYNTHESIS, rounds_used=0, methods=methods)

    monkeypatch.setitem(S._GUARDS, T.Phase.SYNTHESIS, lambda *a, **k: ())
    assert S.advance(state, T.Phase.SYNTHESIS, rounds_used=0, methods=methods) is T.Phase.SYNTHESIS, \
        "the mutation must actually open the door, or this pin proves nothing"


# -- (f): the sole producer of a kind may not require it --------------------

def sole_producer_cycles(methods: MethodRegistry) -> list[str]:
    """Every method that REQUIRES a kind nothing but itself writes. Such a
    method waits forever for its own output and never runs, and the kind is
    never written by anything."""
    producers: dict[Kind, set[str]] = {}
    for m in methods.all():
        for kind in m.spec.output_kinds:
            producers.setdefault(kind, set()).add(m.spec.id)
    out: list[str] = []
    for m in methods.all():
        for inp in m.spec.required_inputs:
            if inp.min_count >= 1 and producers.get(inp.kind, set()) == {m.spec.id}:
                out.append(f"{m.spec.id} requires {inp.kind.value}, "
                           f"which only {m.spec.id} writes")
    return out


def test_s7f_no_method_waits_for_a_kind_only_it_writes(registry):
    """S7(f) - mutation: make OPTION a required input of `make_buy_partner`
    again, with min_count 2.

    make_buy_partner is the only method in the library that writes an OPTION.
    Requiring two of them makes the sole producer of a kind wait for that kind:
    it never becomes runnable, no engagement ever holds a route, and therefore
    nothing a recommendation could select. The suite stays green throughout - a
    method that never runs breaks no validator.

    Stated over the whole library rather than about one method, so a second
    method acquiring the same cycle is caught by the same law, and pinned
    behaviourally as well: on a registry holding capability gaps and NO option,
    the sole producer of OPTION must be runnable.
    """
    cycles = sole_producer_cycles(METHODS)
    assert cycles == [], "\n".join(cycles)

    from app.engine.methods.builtin.make_buy_partner import MakeBuyPartner

    reg = gap_registry(registry)
    assert live(reg, Kind.OPTION) == [], "the registry holds no route yet"
    state = input_state(MakeBuyPartner.spec, reg)
    assert not state.missing, (
        "the only producer of OPTION cannot run on a registry that holds no OPTION: "
        f"missing {[i.kind.value for i in state.missing]}")
    assert routes_written(reg), "and it does write routes when it runs"

    # NEGATIVE CONTROL: the law is about a SOLE producer, not about a method
    # consuming what an earlier method writes. A two-method chain is legitimate,
    # and this check passes it.
    chain = library(
        method_spec("writes_options", SHAPE_FIRST,
                    needs=(InputSpec("facts", Kind.FACT, min_count=1, why_needed="evidence"),),
                    writes=(Kind.OPTION,)),
        method_spec("reads_options", SHAPE_SECOND,
                    needs=(InputSpec("options", Kind.OPTION, min_count=2, why_needed="routes"),),
                    writes=(Kind.RECOMMENDATION,)))
    assert sole_producer_cycles(chain) == []


def test_s7f_requiring_its_own_output_is_caught():
    """S7(f), the mutation applied: the library law sees the cycle the moment a
    method requires the kind only it writes."""
    mutated = library(
        method_spec("make_buy_partner", SHAPE_SECOND,
                    needs=(InputSpec("capabilities", Kind.CAPABILITY, min_count=1,
                                     why_needed="the gap"),
                           InputSpec("options", Kind.OPTION, min_count=2,
                                     why_needed="the routes already on the table")),
                    writes=(Kind.OPTION, Kind.TRADE_OFF)))
    assert sole_producer_cycles(mutated) == [
        "make_buy_partner requires option, which only make_buy_partner writes"], \
        "the mutation must actually be visible, or this pin proves nothing"
