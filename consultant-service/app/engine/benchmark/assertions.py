"""app/engine/benchmark/assertions.py - what a bundle, and a set of bundles,
must satisfy (design 17.4).

Every check returns a list of failure strings rather than raising: a benchmark
that stopped at the first failure would report one defect per run, and the point
of running fifteen cases is to see all of them at once. The test files turn the
lists into assertions.

Two families:

  * DIVERGENCE, over the ten core bundles. The claim is that one engine reacting
    to different inputs produces different work - different questions, different
    central decisions, differently shaped issue trees, different methods,
    different assignments, different evidence asked for, different deliverables.
    Under the fake this is a regression net rather than proof of usefulness (the
    oracle cannot judge prose); what it does prove is that nothing in the
    deterministic core is a per-case script, because the oracle cannot tell one
    case from another.
  * ADVERSARIAL, one per named check in a case's `<id>.keys.json`. Each states a
    law the engine must not break when the material is hostile: evidence that
    is missing, documents that disagree, an objective the arithmetic refutes,
    two specialists who disagree, a matter that needs a licence, a request that
    is a symptom of something else.
  * THE CHARTER, over the same core bundles. Divergence proves the ten
    engagements differ; it cannot tell whether the charter that started each
    one was the RANKING's answer or the ask-floor's. `charter_failures` reads
    the mechanism itself (design 6.4/6.6): the charter names the top of the
    deterministic ranking, that top clears CHARTER_MIN_WEIGHT and
    CHARTER_MIN_MARGIN, and the analysis the charter unlocks actually ran. A
    build whose relevance links were all empty would pass every divergence
    check above with the ranking dead and every charter opened by ASK_FLOOR.

Where a law's full path is not reachable in this build, the check says so in its
own words and exercises the law directly on a probe registry instead of
pretending the run covered it. Every such place is named in `BLOCKED_CLAIMS`,
which a test pins: when the engine gains what the claim needs, that test fails
and the claim moves back into the live checks. A silent skip would leave a law
untested and nothing would say so.
"""
from __future__ import annotations

from decimal import Decimal
from itertools import combinations
from typing import Any, Callable, Mapping, Sequence

from app.engine.benchmark.cases import ADVERSARIAL_CHECKS, LoadedCase
from app.engine.benchmark.harness import Bundle
from app.engine.calc.arith import DecimalCalculator
from app.engine.gates import laws as laws_mod
from app.engine.gates.release import STATUS_DRAFT
from app.engine.partner.hypothesis import PARTNER_INFERRED, maybe_reframe, ranked_candidates
from app.engine.partner.state import approved_charter
from app.engine.partner.ingest import TURN_ACTOR_PREFIX
from app.engine.registry import EngagementRegistry, IncomparableInputs, ScopedView
from app.engine.synthesis.conflicts import detect_conflicts
from app.engine.synthesis.resolve import emit_decisions_required
from app.engine.types import (
    BOUNDS, Actor, Add, AnalysisState, Authority, Confidence, ConflictKind, DecisionPayload, DecisionRole,
    Dimensions, Entity, FactBasis, FactPayload, Feasibility, HypothesisPayload, Interrogative,
    IssuePayload, Kind, MeasurePayload, ObjectivePayload, Provenance, Quantity, Relevance,
    RelationToCentralDecision, SetStatus, SourceKind, Status, UnitFamily, make_entity,
)
from app.engine.types import EvidenceSourcePayload

__all__ = [
    "ADVERSARIAL",
    "BLOCKED_CLAIMS",
    "adversarial_failures",
    "bound",
    "charter_failures",
    "divergence_failures",
    "revealed_failures",
]


def bound(name: str, overrides: Mapping[str, Any] | None = None) -> Any:
    """A named bound's live value: the caller's mapping, else the ENGINE_<name>
    setting, else the frozen default. Never a literal at the point of use."""
    if overrides is not None and name in overrides:
        return overrides[name]
    try:
        from app.config import settings
        value = getattr(settings, f"ENGINE_{name}", None)
        if value is not None:
            return value
    except Exception:                                     # pragma: no cover - settings optional
        pass
    return BOUNDS[name]


# The claims design 17.4 makes that this build cannot yet make. Each names what
# is missing, so the gap is a recorded fact rather than a quiet omission, and
# `test_engine_benchmarks_fake.py` pins the list.
BLOCKED_CLAIMS: Mapping[str, str] = {
    "deliverable_sets_reach_the_bound": (
        "MIN_DISTINCT_DELIVERABLE_SETS distinct product-id sets across the core cases; the ten core "
        "bundles produce two. The old reason - an empty specialist evidence window - is retired: "
        "Assignment.from_selection now puts the assigned node and its ancestors in the permitted set, "
        "and the model-assisted methods run - issue_tree grafts 6-12 nodes, capability_gap and root_cause "
        "reach ANALYSIS state done, as do the deterministic current_state, kpi_design and financial_model. "
        "What is left is a method library whose option-and-delivery half is starved at its root: no run "
        "writes a CAPABILITY, OPTION, EVALUATION_CRITERION or ACTION row, so make_buy_partner (the only "
        "OPTION writer) sits at options 0/2 and capabilities 0/1, option_evaluation and prioritization are "
        "selected and then blocked on those same empty kinds, and operating_model and roadmap match no "
        "open node's shape at all. The product predicates that would vary the set therefore never hold. "
        "The live check below still requires the sets not to be all identical."),
    "section_signatures_reach_the_bound": (
        "MIN_DISTINCT_SECTION_SIGNATURES distinct section signatures; the ten core bundles produce two. "
        "Same cause: sections are planned per product from the same counts, and the product set cannot "
        "vary until something writes the option-and-delivery kinds above."),
    "recommendations_are_distinct": (
        "recommendation statements pairwise distinct. No RECOMMENDATION is written in a fake run, and "
        "the cause is not a blocked method: NOTHING in this build creates one. No MethodSpec names "
        "Kind.RECOMMENDATION in its output_kinds, and synthesis only ever SUPERSEDES a recommendation "
        "that already exists (synthesis/regulated.py routes a licensed one; recommend.py checks and "
        "approves one). The registry, the gate (L2/L3) and the products all read RECOMMENDATION rows, "
        "so the reading half of the law is exercised on probe registries; the writing half has no "
        "producer to exercise."),
    "workstreams_are_distinct": (
        "workstream name sets pairwise distinct; every core bundle carries an empty set. A WORKSTREAM "
        "is written by operating_model, roadmap and the r30 adapter. None is reachable here: "
        "operating_model requires capabilities 2 and matches no open node's shape, roadmap requires "
        "workstreams 1 and actions 1 - inputs of the same starved chain - and the r30 adapter is not "
        "selected by shape in any core case. Same root cause as the deliverable sets."),
    "central_decision_is_not_the_opening_statement": (
        "the central decision differs from the client's opening words. The old reason - that hypothesis "
        "weights come only from methods, none of which runs before the charter - is retired: ingestion "
        "now writes the relevance link at birth and every core engagement is ranked (weight 1.0, over "
        "CHARTER_MIN_WEIGHT and CHARTER_MIN_MARGIN), which is what `charter_failures` asserts live. What "
        "blocks the claim is that there is only ever ONE candidate to rank. The structural oracle "
        "returns no new_candidates by design - a case-blind rule cannot word a rival decision without "
        "reading the case - so no PARTNER_INFERRED row exists, and maybe_reframe returns None at its "
        "first gate. Two further gates stand behind that one: an inferred candidate accrues no weight, "
        "because a statement bears on the decision it was STATED under and no client statement is made "
        "under a candidate the partner invented afterwards; and the reframe additionally needs a "
        "HYPOTHESIS from an ISSUE under the stated request to a cause under the inferred one, while the "
        "first ISSUE is the root the charter itself opens - after discovery has ended. The "
        "symptom-vs-problem law is exercised on a probe by `adv_symptom_not_problem` instead."),
}


# =============================================================================
# 1. Divergence over the core bundles
# =============================================================================

def _pairs(bundles: Sequence[Bundle]):
    return combinations(sorted(bundles, key=lambda b: b.case_id), 2)


def _jaccard(a: frozenset, b: frozenset) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def divergence_failures(bundles: Sequence[Bundle],
                        bounds: Mapping[str, Any] | None = None) -> list[str]:
    """Every way in which the core bundles are NOT different enough."""
    out: list[str] = []
    if len(bundles) < 2:
        return [f"divergence needs at least two bundles, got {len(bundles)}"]

    # D1: two engagements do not ask the same questions. Structural gaps are
    # exempt on phrasing (design 17.4): the seven structural inputs are the
    # same holes in every engagement, so only questions a tree produced count.
    for a, b in _pairs(bundles):
        overlap = _jaccard(a.question_texts(), b.question_texts())
        if overlap >= 0.5:
            out.append(f"D1 questions: {a.case_id} and {b.case_id} overlap {overlap:.2f} (>= 0.5)")

    # D2: no question is asked of nearly everybody. One question in most
    # engagements is a script, however varied the rest of the batch is.
    seen: dict[str, int] = {}
    for b in bundles:
        for text in b.question_texts():
            seen[text] = seen.get(text, 0) + 1
    ceiling = 0.6 * len(bundles)
    for text, n in sorted(seen.items()):
        if n > ceiling:
            out.append(f"D2 questions: {n}/{len(bundles)} cases ask {text[:70]!r}")

    # D3-D7: the structural account of the engagement.
    for a, b in _pairs(bundles):
        if a.central_decision == b.central_decision:
            out.append(f"D3 central decision: {a.case_id} and {b.case_id} name the same decision")
        if a.issue_hash == b.issue_hash:
            out.append(f"D4 issue tree: {a.case_id} and {b.case_id} have the same structure")

    for label, key, code in (
        ("method multisets", lambda x: x.methods, "D5"),
        ("evidence requests", lambda x: x.evidence_requests, "D6"),
        ("assignments", lambda x: x.assignments, "D7"),
        ("deliverable sets", lambda x: tuple(sorted(x.deliverable_set())), "D8"),
        ("section signatures", lambda x: x.section_signature(), "D9"),
        ("routed regulated domains", lambda x: x.regulated_domains, "D10"),
    ):
        distinct = {key(b) for b in bundles}
        if len(distinct) < 2:
            out.append(f"{code} {label}: all {len(bundles)} cases produced the same one")
    return out


def charter_failures(bundles: Sequence[Bundle],
                     bounds: Mapping[str, Any] | None = None) -> list[str]:
    """Every way in which a core engagement did NOT start from the ranking.

    Design 6.4 makes the central decision a weight the registry computed from
    relevance links; design 6.6 also lets ASK_FLOOR open a charter when nothing
    left to ask could move it. Both are lawful, and only the second one needs
    no evidence at all - so a build whose relevance links were empty would
    still reach a charter, still diverge, and still pass every check above,
    with the ranking dead underneath. This is the check that would notice.

    Four claims per bundle: the client approved a charter; it names the top of
    the deterministic ranking; that top clears CHARTER_MIN_WEIGHT and
    CHARTER_MIN_MARGIN ON THE DISCOVERY EVIDENCE ALONE; and at least one method
    reached `done`, because a charter that unlocks nothing is a charter nothing
    rests on.

    The ranking is recomputed over a ScopedView of the candidate decisions plus
    the rows ingestion wrote (actor_ref TURN_ACTOR_PREFIX), never over the
    finished registry. That is not a nicety: a method attaches relevance to
    everything it writes, the root ISSUE alone carries weight 1.0 on the
    central decision, and all of that lands AFTER the charter. Scored on the
    final rows, a build whose discovery wrote no link at all would still show a
    confident ranking - the check would pass on evidence that did not exist
    when the charter was decided. The arithmetic is `ranked_candidates` itself,
    not a copy of it; only the rows it may see are narrowed.
    """
    floor = float(bound("CHARTER_MIN_WEIGHT", bounds))
    margin = float(bound("CHARTER_MIN_MARGIN", bounds))
    out: list[str] = []
    for b in bundles:
        view = b.registry
        if view is None:                                   # pragma: no cover - defensive
            out.append(f"{b.case_id}: no registry rode along with the bundle")
            continue
        charter = approved_charter(view)
        if charter is None:
            out.append(f"{b.case_id}: no charter was approved")
            continue
        discovery = ScopedView(view, [
            e.id for e in view.query()
            if e.kind is Kind.DECISION or e.provenance.actor_ref.startswith(TURN_ACTOR_PREFIX)])
        ranked = ranked_candidates(discovery)
        if not ranked:
            out.append(f"{b.case_id}: a charter was approved with no candidate decision")
            continue
        top, top_w = ranked[0]
        second_w = ranked[1][1] if len(ranked) > 1 else 0.0
        named = charter.payload.central_decision
        if named != top.id:
            out.append(f"{b.case_id}: the charter names {named} but discovery ranked {top.id} top")
        if top_w < floor or (top_w - second_w) < margin:
            out.append(f"{b.case_id}: the charter was not reached by the ranking - the discovery "
                       f"evidence gives {top.id} weight {top_w:.3f} (floor {floor}) and margin "
                       f"{top_w - second_w:.3f} (floor {margin}); only ASK_FLOOR could have opened it")
        if not any(a.payload.state is AnalysisState.DONE for a in view.query(Kind.ANALYSIS)):
            out.append(f"{b.case_id}: the charter was approved but no analysis reached done")
    return out


def revealed_failures(bundles: Sequence[Bundle], cases: Sequence[LoadedCase],
                      bounds: Mapping[str, Any] | None = None) -> list[str]:
    """The guard against vacuous divergence (design 17.4): bundles can differ in
    every listed way and still both have missed everything that mattered. A core
    case must surface at least MIN_REVEALED_CHANGERS of the dossier items its
    author marked as changing the recommendation."""
    floor = int(bound("MIN_REVEALED_CHANGERS", bounds))
    by_id = {c.id: c for c in cases}
    out: list[str] = []
    for b in bundles:
        case = by_id.get(b.case_id)
        available = len(case.changing_indexes()) if case is not None else 0
        if b.revealed_changers < min(floor, available):
            out.append(f"{b.case_id}: {b.revealed_changers} changing dossier items surfaced, "
                       f"floor {floor} (the case offers {available})")
    return out


# =============================================================================
# 2. Small builders for the probes
# =============================================================================

def _entity(registry: EngagementRegistry, kind: Kind, payload: Any, *, actor: Actor = Actor.PARTNER,
            status: Status = Status.PROPOSED, relation: RelationToCentralDecision,
            decision_id: str | None = None, weight: float = 0.0,
            derived_from: Sequence[str] = ()) -> Entity:
    return registry.apply(Add(make_entity(
        kind=kind, engagement_id=registry.engagement_id, payload=payload,
        provenance=Provenance(actor=actor, actor_ref=f"{actor.value}:probe",
                              derived_from=tuple(derived_from)),
        confidence=Confidence(None), relevance=Relevance(decision_id, weight),
        relation=relation, status=status)))


def _money(value: str, currency: str = "EUR") -> Quantity:
    """A fully pinned figure. Every dimension a comparison needs is stated,
    because an unpinned one is a QUESTION and not a conflict (design 9.2) - and
    a probe that left one unpinned would be testing the pin path while claiming
    to test the conflict path."""
    return Quantity(Decimal(value), currency, UnitFamily.MONEY,
                    Dimensions(currency=currency, period="FY26", period_basis="year",
                               as_of="2026-01-01"))


def _probe(name: str) -> EngagementRegistry:
    return EngagementRegistry(f"PROBE-{name}", clock=lambda: "2026-01-01T00:00:00+00:00")


def _turn(registry: EngagementRegistry, *statements: str) -> Entity:
    """The conversation turn a client fact must cite (I2). Its text is the
    statements themselves, so a probe fact is a verbatim span of the turn the
    way a real one is - the registry refuses anything else, and a probe that
    dodged that would be testing a registry nobody runs."""
    text = "\n".join(statements)
    source = _entity(registry, Kind.EVIDENCE_SOURCE,
                     EvidenceSourcePayload(name="probe turn", source_kind=SourceKind.CONVERSATION_TURN,
                                           text=text, received_at="2026-01-01T00:00:00+00:00"),
                     actor=Actor.CLIENT, relation=RelationToCentralDecision.INFORMS)
    registry.register_source_text(source.id, text)
    return source


def _confirm(registry: EngagementRegistry, entity: Entity) -> Entity:
    return registry.apply(SetStatus(entity.id, Status.CONFIRMED,
                                    Provenance(actor=Actor.CLIENT, actor_ref="client:probe")))


# =============================================================================
# 3. The adversarial checks
# =============================================================================

def adv_missing_evidence(bundle: Bundle, case: LoadedCase) -> list[str]:
    """Nothing is stated on evidence that does not exist.

    Three registry claims: every quantity a product could print traces to a
    non-inferred row; every recommendation carries what it is conditional on;
    and while a material question is open the release is DRAFT, blocked by L5.
    """
    out: list[str] = []
    view = bundle.registry
    inferred: set[str] = set()
    for fact in view.live(Kind.FACT):
        if getattr(fact.payload, "quantity", None) is None:
            continue
        if fact.payload.basis is FactBasis.INFERRED:
            inferred.add(fact.id)
            # An inference may be PROPOSED - that is what a restatement is -
            # but it is never something the client confirmed, and confirming
            # one would launder an inference into evidence.
            if fact.status in (Status.CONFIRMED, Status.APPROVED):
                out.append(f"{fact.id}: an inferred figure carries a confirmation")
        if fact.payload.basis is FactBasis.CALCULATED and not fact.payload.inputs:
            out.append(f"{fact.id}: a calculated figure with no inputs (I8)")
    for rec in view.live(Kind.RECOMMENDATION):
        if not rec.payload.conditional_on and not rec.payload.supports:
            out.append(f"{rec.id}: a recommendation resting on nothing and conditional on nothing")
        if rec.payload.supports and set(rec.payload.supports) <= inferred:
            out.append(f"{rec.id}: every support is an inference and nothing is conditional on it")
    for outcome in view.live(Kind.EXPECTED_OUTCOME):
        if outcome.payload.supports and set(outcome.payload.supports) <= inferred:
            out.append(f"{outcome.id}: an expected outcome resting only on inference")
    open_material = view.open_material_questions()
    if open_material and bundle.release_status != STATUS_DRAFT:
        out.append("a material question is open and the release is not DRAFT")
    if open_material and not any(f.startswith("L5") for f in bundle.blocking_findings):
        out.append(f"{len(open_material)} material questions open but L5 raised no blocking finding")
    return out


def adv_contradictory_documents(bundle: Bundle, case: LoadedCase) -> list[str]:
    """Documents that disagree are never blended.

    The engine must show the disagreement somewhere - a CONFLICT, or an open
    question about the source or the unpinned dimension that makes two figures
    incomparable - and the calculator must refuse to produce a number from two
    values that disagree. The refusal is exercised directly: under the fake the
    two sides rarely land on one MEASURE (the oracle names a measure from the
    words before the figure), and a law nothing reached is a law nothing tested.
    """
    out: list[str] = []
    view = bundle.registry
    documents = case.contradicting_documents()
    if documents:
        raised = (len(view.live(Kind.CONFLICT))
                  + len([q for q in view.live(Kind.QUESTION) if q.status is Status.OPEN]))
        if raised < len(documents):
            out.append(f"{len(documents)} contradicting documents but only {raised} conflicts or open "
                       "questions: a contradiction was absorbed silently")

    # Nothing averages (design 1, consequence 2).
    calc = DecimalCalculator(view)
    probe = _probe("blend")
    measure = _entity(probe, Kind.MEASURE, MeasurePayload(name="one measure", unit_family=UnitFamily.MONEY,
                                                          confirmed_by_client=True),
                      relation=RelationToCentralDecision.DEFINES)
    turn = _turn(probe, "one side", "the other side")
    low = _entity(probe, Kind.FACT, FactPayload(statement="one side", basis=FactBasis.CLIENT_STATED,
                                                measure_id=measure.id, quantity=_money("100")),
                  actor=Actor.CLIENT, relation=RelationToCentralDecision.EVIDENCES,
                  derived_from=(turn.id,))
    high = _entity(probe, Kind.FACT, FactPayload(statement="the other side", basis=FactBasis.CLIENT_STATED,
                                                 measure_id=measure.id, quantity=_money("140")),
                   actor=Actor.CLIENT, relation=RelationToCentralDecision.EVIDENCES,
                   derived_from=(turn.id,))
    try:
        result = DecimalCalculator(probe).total([low, high])
    except IncomparableInputs:
        result = None
    if result is not None and getattr(result, "quantity", None) is not None:
        value = result.quantity.value
        if value == Decimal("120"):
            out.append("the calculator averaged two conflicting values instead of refusing")
    conflicts = detect_conflicts(probe, calc=calc)
    if not any(c.payload.kind is ConflictKind.VALUE for c in conflicts):
        out.append("two live facts with different values on one confirmed measure raised no VALUE conflict")
    return out


def adv_impossible_objective(bundle: Bundle, case: LoadedCase) -> list[str]:
    """An objective the arithmetic refutes is said out loud.

    The probe is the run's own shape in miniature: a confirmed baseline, a
    target above it and a calculated projection that does not reach it. The
    engine must raise OBJECTIVE_VS_FEASIBILITY and put a decision to the client;
    a plan that quietly claimed the target was met is the failure this exists
    to catch.
    """
    out: list[str] = []
    probe = _probe("infeasible")
    measure = _entity(probe, Kind.MEASURE, MeasurePayload(name="the measure the objective names",
                                                          unit_family=UnitFamily.MONEY,
                                                          confirmed_by_client=True),
                      relation=RelationToCentralDecision.DEFINES)
    decision = _entity(probe, Kind.DECISION, DecisionPayload(statement="what to do", role=DecisionRole.CENTRAL),
                       relation=RelationToCentralDecision.DEFINES)
    turn = _turn(probe, "today")
    baseline = _entity(probe, Kind.FACT,
                       FactPayload(statement="today", basis=FactBasis.CLIENT_STATED, measure_id=measure.id,
                                   quantity=_money("100")),
                       actor=Actor.CLIENT, relation=RelationToCentralDecision.EVIDENCES,
                       decision_id=decision.id, weight=1.0, derived_from=(turn.id,))
    _confirm(probe, baseline)
    _entity(probe, Kind.FACT,
            FactPayload(statement="what the plan reaches", basis=FactBasis.CALCULATED, measure_id=measure.id,
                        quantity=_money("110"), formula="baseline + effect", inputs=(baseline.id,)),
            actor=Actor.CALCULATOR, relation=RelationToCentralDecision.EVIDENCES,
            derived_from=(baseline.id,))
    _entity(probe, Kind.OBJECTIVE,
            ObjectivePayload(text="reach the target", measure_id=measure.id, target=_money("200"),
                             feasibility=Feasibility.UNTESTED),
            actor=Actor.CLIENT, relation=RelationToCentralDecision.DEFINES, decision_id=decision.id, weight=1.0)

    conflicts = detect_conflicts(probe)
    if not any(c.payload.kind is ConflictKind.OBJECTIVE_VS_FEASIBILITY for c in conflicts):
        out.append("an objective the arithmetic cannot reach raised no OBJECTIVE_VS_FEASIBILITY conflict")
    # The decision may already have been written by the conflict query itself;
    # `emit_decisions_required` then adds nothing, which is right (a question
    # is put once). What matters is that one stands, whoever wrote it.
    emit_decisions_required(probe)
    required = probe.live(Kind.DECISION_REQUIRED)
    if not any(d.payload.from_authority is Authority.CLIENT for d in required):
        out.append("an infeasible objective put no decision to the client")
    for outcome in bundle.registry.live(Kind.EXPECTED_OUTCOME):
        if outcome.payload.basis == FactBasis.INFERRED.value:
            out.append(f"{outcome.id}: an expected outcome asserted on inference alone")
    return out


def adv_specialist_disagreement(bundle: Bundle, case: LoadedCase) -> list[str]:
    """Two specialists on one issue disagree, and neither conclusion vanishes.

    Scripted, as the design says: two HYPOTHESIS rows on one issue with opposite
    verdicts. The engine must raise CONFLICT(SPECIALIST_DISAGREEMENT), keep both
    rows live, and block FINAL through L1 while it is open and material.
    """
    out: list[str] = []
    probe = _probe("disagree")
    decision = _entity(probe, Kind.DECISION, DecisionPayload(statement="the decision", role=DecisionRole.CENTRAL),
                       relation=RelationToCentralDecision.DEFINES)
    issue = _entity(probe, Kind.ISSUE,
                    IssuePayload(text="the issue both were assigned", interrogative=Interrogative.WHY,
                                 target_kind=Kind.FACT, causal=True, decisive_for=(decision.id,)),
                    relation=RelationToCentralDecision.DEFINES, decision_id=decision.id, weight=1.0)
    first = _entity(probe, Kind.HYPOTHESIS,
                    HypothesisPayload(text="the first specialist's conclusion", issue_id=issue.id,
                                      verdict="supported"),
                    actor=Actor.SPECIALIST, relation=RelationToCentralDecision.EVIDENCES,
                    decision_id=decision.id, weight=0.5, derived_from=(issue.id,))
    second = _entity(probe, Kind.HYPOTHESIS,
                     HypothesisPayload(text="the second specialist's conclusion", issue_id=issue.id,
                                       verdict="refuted"),
                     actor=Actor.SPECIALIST, relation=RelationToCentralDecision.EVIDENCES,
                     decision_id=decision.id, weight=0.5, derived_from=(issue.id,))
    conflicts = detect_conflicts(probe)
    if not any(c.payload.kind is ConflictKind.SPECIALIST_DISAGREEMENT for c in conflicts):
        out.append("two specialists contradicting each other on one issue raised no conflict")
    live = {e.id for e in probe.live(Kind.HYPOTHESIS)}
    for row in (first, second):
        if row.id not in live:
            out.append(f"{row.id}: a specialist conclusion disappeared instead of being kept visible")
    for conflict in conflicts:
        if conflict.payload.kind is not ConflictKind.SPECIALIST_DISAGREEMENT:
            continue
        if conflict.payload.authority_required is None:
            out.append(f"{conflict.id}: a disagreement nobody is named to resolve")
        findings = laws_mod.law_material_open_conflict(probe, ())
        if probe.is_material(conflict) and not findings:
            out.append(f"{conflict.id}: material and open, and L1 raised nothing")
    return out


def adv_regulated(bundle: Bundle, case: LoadedCase) -> list[str]:
    """Every matter the case says needs a licence is routed, and nothing the
    engine writes states the licensed answer itself."""
    out: list[str] = []
    annotated = {d.value for d in case.regulated_domains()}
    routed = set(bundle.regulated_domains)
    missing = sorted(annotated - routed)
    if missing:
        out.append(f"annotated regulated domains never routed: {missing}")
    view = bundle.registry
    for matter in view.query(Kind.REGULATED_MATTER):
        if matter.status is not Status.ROUTED:
            out.append(f"{matter.id}: a regulated matter that was not routed")
            continue
        if not matter.payload.adviser_class:
            out.append(f"{matter.id}: routed to nobody in particular")
        if not matter.payload.withheld_interpretation:
            out.append(f"{matter.id}: nothing recorded as withheld (S11)")
    touched = {t for m in view.query(Kind.REGULATED_MATTER) for t in m.payload.touches}
    for rec in view.live(Kind.RECOMMENDATION):
        if rec.id in touched and rec.payload.licensed_interpretation is not True:
            out.append(f"{rec.id}: touches a regulated matter and is not flagged as licensed")
        if rec.payload.licensed_interpretation is True and rec.status in (Status.APPROVED, Status.CONFIRMED):
            out.append(f"{rec.id}: licensed interpretation carried an approval")
    if annotated and not view.query(Kind.REGULATED_MATTER):
        out.append("the case states regulated matters and the registry holds none")
    return out


def adv_symptom_not_problem(bundle: Bundle, case: LoadedCase) -> list[str]:
    """A request that is a symptom is reframed, and only with the client.

    Two halves. Over the run: no decision was quietly substituted - if a stated
    request carries `symptom_of`, a scope DECISION_REQUIRED for the CLIENT
    exists. On a probe: when an inferred candidate outweighs the stated request
    by SYMPTOM_MARGIN and a HYPOTHESIS links an issue under the request to a
    cause under the candidate, the rule fires; and when the margin is not met it
    does not. The probe is how this law is reached at all - see BLOCKED_CLAIMS.
    """
    out: list[str] = []
    view = bundle.registry
    for decision in view.live(Kind.DECISION):
        if decision.payload.symptom_of is None:
            continue
        scope = [d for d in view.live(Kind.DECISION_REQUIRED)
                 if d.payload.from_authority is Authority.CLIENT]
        if not scope:
            out.append(f"{decision.id}: marked a symptom with no scope decision put to the client")

    fired, refused = _reframe_probe()
    if fired is None:
        out.append("the symptom rule did not fire when an inferred candidate outweighed the request")
    if refused is not None:
        out.append("the symptom rule fired on a margin the bound does not admit")
    return out


def _reframe_registry(weight: float) -> tuple[EngagementRegistry, Any]:
    """A registry where an inferred candidate carries `weight` of the evidence
    and the stated request carries the rest, with the causal chain the rule
    requires."""
    probe = _probe(f"reframe-{weight}")
    stated = _entity(probe, Kind.DECISION,
                     DecisionPayload(statement="what the client asked for", role=DecisionRole.STATED_REQUEST),
                     actor=Actor.CLIENT, relation=RelationToCentralDecision.DEFINES)
    inferred = _entity(probe, Kind.DECISION,
                       DecisionPayload(statement="what the evidence points at", role=DecisionRole.SUBORDINATE,
                                       origin=PARTNER_INFERRED),
                       relation=RelationToCentralDecision.DEFINES)
    issue = _entity(probe, Kind.ISSUE,
                    IssuePayload(text="under the request", interrogative=Interrogative.WHY,
                                 target_kind=Kind.FACT, causal=True, decisive_for=(stated.id,)),
                    relation=RelationToCentralDecision.DEFINES, decision_id=stated.id, weight=1.0 - weight)
    turn = _turn(probe, "under the inferred decision")
    cause = _entity(probe, Kind.FACT,
                    FactPayload(statement="under the inferred decision", basis=FactBasis.CLIENT_STATED),
                    actor=Actor.CLIENT, relation=RelationToCentralDecision.DEFINES,
                    decision_id=inferred.id, weight=weight, derived_from=(turn.id,))
    _entity(probe, Kind.HYPOTHESIS,
            HypothesisPayload(text="the request follows from the cause", issue_id=issue.id,
                              causes=(cause.id,)),
            relation=RelationToCentralDecision.EVIDENCES, derived_from=(issue.id, cause.id))
    return probe, stated


def _reframe_probe() -> tuple[Any, Any]:
    """(what fired above the margin, what wrongly fired below it)."""
    margin = float(bound("SYMPTOM_MARGIN"))
    wide, _ = _reframe_registry(0.5 + margin)
    fired = maybe_reframe(wide, BOUNDS)
    narrow, _ = _reframe_registry(0.5 + margin / 4.0)
    refused = maybe_reframe(narrow, BOUNDS)
    return fired, refused


# The registry of adversarial checks. Asserted total against the closed name
# list the case loader validates against, so a name in a keys file with no
# implementation and an implementation nothing names both fail loudly.
ADVERSARIAL: Mapping[str, Callable[[Bundle, LoadedCase], list[str]]] = {
    "missing_evidence": adv_missing_evidence,
    "contradictory_documents": adv_contradictory_documents,
    "impossible_objective": adv_impossible_objective,
    "specialist_disagreement": adv_specialist_disagreement,
    "regulated": adv_regulated,
    "symptom_not_problem": adv_symptom_not_problem,
}
assert set(ADVERSARIAL) == set(ADVERSARIAL_CHECKS), \
    "every adversarial check a keys file may name has an implementation, and no other"


def adversarial_failures(bundle: Bundle, case: LoadedCase) -> list[str]:
    """Run the checks this case's annotations name."""
    out: list[str] = []
    for name in case.keys.checks:
        for failure in ADVERSARIAL[name](bundle, case):
            out.append(f"{case.id}/{name}: {failure}")
    return out
