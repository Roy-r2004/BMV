"""app/engine/synthesis/conflicts.py - two conclusions that cannot both stand.

Conflicts fail closed (spec section 7): nothing here averages two numbers,
picks the newer one, or drops the quieter conclusion. Each of the four
detection queries below turns a disagreement into a typed CONFLICT row that
names both conclusions, the authority that must settle it and what precedence
recommends - and then L1 keeps the release DRAFT while a material one is open.

The four queries (design 9.1):

1. Facts. Grouped by `measure_id` (MF1.6) and handed to calc.reconcile, which
   joins on the measure and NOTHING else: no statement, no topic, no
   similarity. VALUE, DEFINITION or CLIENT_VS_RECORD comes back typed; a
   reconciliation that names no ConflictKind is a question about a dimension,
   which the gaps pass owns, not a defect.
2. Analyses. Two live PROPOSED conclusions of one kind on one subject whose
   payloads cannot both hold: hypothesis verdicts that contradict on one
   issue, two scorings of one (option, criterion), two recommendations naming
   different options for one decision. Two specialists disagreeing is a
   CONFLICT, never a merge (design 8.6).
3. Objectives vs arithmetic. A target the registered facts cannot reach:
   direction comes from the confirmed current-state fact the target moves
   away from, so nothing has to be told which way is "better". The objective
   is superseded with feasibility=INFEASIBLE_ON_FACTS and the conflict goes to
   the CLIENT, who owns the objective. This query is not the only producer of
   that verdict - a CALCULATION method that totals a measure records the same
   one on the objective's own id - so it says nothing a feasibility conflict
   already says about an objective already amended.
4. Assumptions vs evidence. An assumption whose quantity a CONFIRMED fact on
   the same measure contradicts.

`detect_conflicts()` is the whole round pass the partner loop calls: detect,
then resolve visibly what may be resolved, then put what may not in front of
its owner, then refresh which recommendations are conditional.
`reevaluate_materiality()` is the other half of MF2.4: materiality is
recomputed from the live support graph every round and a changed flag is a
Supersede, so a conflict written before the recommendation that rests on it
becomes material the moment that recommendation exists. The stored flag is a
rendering snapshot; the gate (L1) never reads it.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from itertools import combinations
from typing import Callable, Mapping, Sequence

from app.engine.calc import COMPARABLE, comparable, format_quantity, reconcile
from app.engine.calc.units import canonical_unit
from app.engine.registry import SUPERSEDED_BY_RECORD, Calculator, EngagementRegistry
from app.engine.synthesis.recommend import refresh_conditional_on
from app.engine.synthesis.resolve import advise, auto_resolve, emit_decisions_required
from app.engine.types import (
    SENSITIVITY, Actor, Add, Authority, Confidence, ConflictConclusion, ConflictKind, ConflictPayload,
    Dimensions, Entity, FactBasis, Feasibility, HypothesisPayload, Kind, Provenance, Quantity, Relevance,
    RelationToCentralDecision, Status, Supersede, make_entity,
)

SYNTHESIS_ACTOR_REF = "synthesis"
_CALCULATOR_REF = "calculator"

# HypothesisPayload.verdict is a plain str whose declared default is the
# undecided one; read from the contract rather than restated, so the two
# cannot drift and so the whitelist AST law (design 18.2) sees a Name at
# every comparison instead of a string constant.
UNTESTED_VERDICT: str = HypothesisPayload.__dataclass_fields__["verdict"].default

# Payload fields a conclusion's wording may be read from, in order. Display
# only: which entities are compared is decided by kind, measure and subject
# id, never by these.
_QUANTITY_FIELDS: tuple[str, ...] = ("quantity", "target")
_WORDING_FIELDS: tuple[str, ...] = ("statement", "text", "name")

# The two dimensions that say WHEN a value is true. A baseline and a target
# differ in these and in nothing else; everything else is what is measured.
_TIME_DIMENSIONS: frozenset[str] = frozenset({"period", "as_of"})

# The subject two conclusions of one kind must share to be about one thing.
_ANALYSIS_SUBJECT: Mapping[Kind, str] = {
    Kind.HYPOTHESIS: "issue_id",
    Kind.RECOMMENDATION: "decision_id",
    Kind.TRADE_OFF: "decision_id",
}


# ---------------------------------------------------------------------------
# reading entities (display and structure; never selection on prose)
# ---------------------------------------------------------------------------

def _quantity(entity: Entity) -> Quantity | None:
    for name in _QUANTITY_FIELDS:
        q = getattr(entity.payload, name, None)
        if q is not None:
            return q
    return None


def _wording(entity: Entity) -> str:
    """What the conclusion says, for the conflict record and the brief. A
    number speaks for itself; a scoring speaks as its scores; otherwise the
    entity's own words."""
    q = _quantity(entity)
    if q is not None:
        return format_quantity(q)
    scores = getattr(entity.payload, "scores", ())
    if scores:
        return "; ".join(f"{s.option_id}/{s.criterion_id}={s.score}" for s in scores)
    for name in _WORDING_FIELDS:
        value = getattr(entity.payload, name, None)
        if value:
            return str(value)
    return entity.id


def _measure_of(registry: EngagementRegistry, entity: Entity) -> str | None:
    """The MEASURE an entity is attached to: its own `measure_id` when the
    payload declares one, otherwise the MEASURE it cites. A structural join
    on entity ids - the only join reconciliation is allowed (MF1.6)."""
    declared = getattr(entity.payload, "measure_id", None)
    if declared is not None:
        return declared
    for i in entity.provenance.derived_from:
        cited = registry.get(i)
        if cited is not None and cited.kind is Kind.MEASURE:
            return i
    return None


def _relation(entities: Sequence[Entity]) -> RelationToCentralDecision:
    """The conflict inherits the most decisive relation of its conclusions.
    SENSITIVITY (types.py) declares that order; nothing here ranks relations
    by hand."""
    best = RelationToCentralDecision.UNKNOWN
    for e in entities:
        if SENSITIVITY[e.relation] > SENSITIVITY[best]:
            best = e.relation
    return best


def _cited_kind(registry: EngagementRegistry, entity: Entity, kind: Kind) -> tuple[str, ...]:
    cited = ((i, registry.get(i)) for i in entity.provenance.derived_from)
    return tuple(i for i, e in cited if e is not None and e.kind is kind)


def _conclusion(registry: EngagementRegistry, entity: Entity) -> ConflictConclusion:
    assumptions = _cited_kind(registry, entity, Kind.ASSUMPTION)
    wording = _wording(entity)
    return ConflictConclusion(
        entity_id=entity.id, statement=wording, evidence=entity.provenance.derived_from,
        assumptions=assumptions, consequence=f"planning would rest on {entity.id} ({wording})")


# ---------------------------------------------------------------------------
# writing a conflict (once per disagreement, materiality computed live)
# ---------------------------------------------------------------------------

def _fingerprint(kind: ConflictKind, subject_id: str,
                 conclusions: Sequence[ConflictConclusion]) -> tuple:
    """One disagreement is recorded once. The wording is part of the key, so a
    conclusion that changed its value raises a fresh conflict rather than
    hiding behind the resolved one."""
    return (kind, subject_id, tuple(sorted((c.entity_id, c.statement) for c in conclusions)))


def _recorded(registry: EngagementRegistry) -> set[tuple]:
    return {_fingerprint(c.payload.kind, c.payload.subject_id, c.payload.conclusions)
            for c in registry.query(Kind.CONFLICT)}


def _draft(registry: EngagementRegistry, payload: ConflictPayload, entities: Sequence[Entity],
           relation: RelationToCentralDecision) -> Entity:
    central = registry.central_decision()
    decision_id = central.id if central is not None else next(
        (e.relevance.decision_id for e in entities if e.relevance.decision_id is not None), None)
    weight = max([e.relevance.weight for e in entities] or [0.0])
    return make_entity(
        kind=Kind.CONFLICT, engagement_id=registry.engagement_id, payload=payload,
        provenance=Provenance(actor=Actor.PARTNER, actor_ref=SYNTHESIS_ACTOR_REF,
                              derived_from=tuple(e.id for e in entities)),
        confidence=Confidence(None), relevance=Relevance(decision_id, weight, SYNTHESIS_ACTOR_REF),
        relation=relation, status=Status.OPEN)


def _write(registry: EngagementRegistry, seen: set[tuple], *, kind: ConflictKind, subject_id: str,
           entities: Sequence[Entity], calc: Calculator | None) -> Entity | None:
    conclusions = tuple(_conclusion(registry, e) for e in entities)
    key = _fingerprint(kind, subject_id, conclusions)
    if key in seen:
        return None
    relation = _relation(entities)
    draft = ConflictPayload(kind=kind, subject_id=subject_id, conclusions=conclusions,
                            relation_to_central_decision=relation, authority_required=Authority.CLIENT)
    # Materiality and the recommended resolution are computed from the live
    # registry, on the row as it would be written -- never carried over from a
    # producer's claim (MF2.4, MF2.3).
    material = registry.is_material(_draft(registry, draft, entities, relation))
    advice = advise(registry, kind, tuple(c.entity_id for c in conclusions), material=material, calc=calc)
    payload = replace(draft, material=material, authority_required=advice.authority,
                      recommended_resolution=advice.winner_id, recommendation_basis=advice.basis)
    seen.add(key)
    return registry.apply(Add(_draft(registry, payload, entities, relation)))


# ---------------------------------------------------------------------------
# 1. facts on one measure
# ---------------------------------------------------------------------------

def _fact_conflicts(registry: EngagementRegistry, seen: set[tuple], calc: Calculator | None) -> list[Entity]:
    out: list[Entity] = []
    for measure_id, facts in registry.facts_by_measure().items():
        # A fact a record has already retired is not re-litigated against
        # every new arrival: it lost, visibly, and its label says so.
        live = sorted((f for f in facts if SUPERSEDED_BY_RECORD not in f.labels), key=lambda f: f.id)
        for a, b in combinations(live, 2):
            outcome = reconcile(a, b)
            if outcome.conflict_kind is None:
                # question / distinct / same: a dimension to pin or two
                # different populations, both of which the gaps pass owns.
                continue
            written = _write(registry, seen, kind=outcome.conflict_kind, subject_id=measure_id,
                             entities=(a, b), calc=calc)
            if written is not None:
                out.append(written)
    return out


# ---------------------------------------------------------------------------
# 2. two live conclusions on one subject
# ---------------------------------------------------------------------------

def _verdicts_contradict(a: Entity, b: Entity) -> bool:
    verdicts = (a.payload.verdict, b.payload.verdict)
    return verdicts[0] != verdicts[1] and UNTESTED_VERDICT not in verdicts


def _options_differ(a: Entity, b: Entity) -> bool:
    chosen = (a.payload.option_id, b.payload.option_id)
    return None not in chosen and chosen[0] != chosen[1]


def _scores_differ(a: Entity, b: Entity) -> bool:
    """Two scorings of one (option, criterion) that are not the identical
    Decimal disagree. There is no tolerance to hide a difference in and
    nothing averages them (design 9.4)."""
    scored = {(s.option_id, s.criterion_id): s.score for s in a.payload.scores}
    return any(scored.get((s.option_id, s.criterion_id), s.score) != s.score for s in b.payload.scores)


_INCOMPATIBLE: Mapping[Kind, Callable[[Entity, Entity], bool]] = {
    Kind.HYPOTHESIS: _verdicts_contradict,
    Kind.RECOMMENDATION: _options_differ,
    Kind.TRADE_OFF: _scores_differ,
}


def _analysis_conflicts(registry: EngagementRegistry, seen: set[tuple], calc: Calculator | None) -> list[Entity]:
    out: list[Entity] = []
    for kind, subject_field in _ANALYSIS_SUBJECT.items():
        incompatible = _INCOMPATIBLE[kind]
        proposed = sorted(registry.query(kind, status=Status.PROPOSED), key=lambda e: e.id)
        for a, b in combinations(proposed, 2):
            subject = getattr(a.payload, subject_field, None)
            if subject is None or subject != getattr(b.payload, subject_field, None):
                continue
            if not incompatible(a, b):
                continue
            written = _write(registry, seen, kind=ConflictKind.SPECIALIST_DISAGREEMENT, subject_id=subject,
                             entities=(a, b), calc=calc)
            if written is not None:
                out.append(written)
    return out


# ---------------------------------------------------------------------------
# 3. an objective the arithmetic refutes
# ---------------------------------------------------------------------------

def _same_population(a: Quantity, b: Quantity) -> bool:
    """Do two quantities measure the same thing, at possibly different times?
    Same family, same unit and every dimension but the two that say WHEN."""
    if a.unit_family is not b.unit_family or canonical_unit(a.unit) != canonical_unit(b.unit):
        return False
    return all(getattr(a.dimensions, n) == getattr(b.dimensions, n)
               for n in Dimensions.DIMENSION_NAMES if n not in _TIME_DIMENSIONS)


def _direction(target: Quantity, baseline: Quantity) -> Decimal | None:
    """Which way the target points: away from today's confirmed value. The
    baseline must measure the same thing in the same unit but NOT at the same
    moment - a value pinned to the target's own date would not be a baseline.
    None when it measures something else, or when the target is already today."""
    if not _same_population(target, baseline):
        return None
    gap = target.value - baseline.value
    return None if gap == 0 else gap


def _reaches(target: Quantity, projection: Quantity, gap: Decimal) -> bool | None:
    """Does the arithmetic get to the target, moving the way `gap` points?
    None when the two are not comparable: a dimension to pin is a question for
    the client, never a defect the engine declares."""
    if comparable(target, projection) != COMPARABLE:
        return None
    if gap > 0:
        return projection.value >= target.value
    return projection.value <= target.value


def _objectives_already_refuted(registry: EngagementRegistry) -> frozenset[str]:
    """Every objective an OBJECTIVE_VS_FEASIBILITY conflict already names.

    A CALCULATION method that totals a measure
    (methods/builtin/financial_model.py, FM3) reaches this verdict first for
    the objectives it can total: it amends the objective, opens the conflict
    on the OBJECTIVE's own id, and asks the client in the same result. Our
    subject here is the MEASURE, so _fingerprint() cannot recognise that row,
    and without this the client would be put one question twice under two
    subjects. Every version counts, RESOLVED ones included: a settled
    disagreement is recorded, not re-opened by the next round.
    """
    named: set[str] = set()
    for conflict in registry.query(Kind.CONFLICT):
        if conflict.payload.kind is not ConflictKind.OBJECTIVE_VS_FEASIBILITY:
            continue
        named.add(conflict.payload.subject_id)
        named.update(c.entity_id for c in conflict.payload.conclusions)
    return frozenset(named)


def _objective_conflicts(registry: EngagementRegistry, seen: set[tuple], calc: Calculator | None) -> list[Entity]:
    out: list[Entity] = []
    already_refuted = _objectives_already_refuted(registry)
    for objective in sorted(registry.live(Kind.OBJECTIVE), key=lambda e: e.id):
        # Both halves are required, and neither alone is the record. An
        # amendment with no conflict is a verdict nobody was told; a conflict
        # over a target since changed is not today's arithmetic. An objective
        # that is BOTH amended INFEASIBLE_ON_FACTS and already named by a
        # feasibility conflict has had this said once, and once is enough.
        if (objective.payload.feasibility is Feasibility.INFEASIBLE_ON_FACTS
                and objective.id in already_refuted):
            continue
        target = objective.payload.target
        measure_id = _measure_of(registry, objective)
        if target is None or measure_id is None:
            continue
        facts = sorted(registry.facts_by_measure().get(measure_id, []), key=lambda f: f.id)
        # Today's confirmed value sets the direction; the arithmetic says how
        # far the plan gets. Neither is guessed and neither is a default.
        gap, baseline, projection = None, None, None
        for f in facts:
            q = _quantity(f)
            if f.status is not Status.CONFIRMED or q is None or f.payload.basis is FactBasis.CALCULATED:
                continue
            gap = _direction(target, q)
            if gap is not None:
                baseline = f
                break
        if gap is None or baseline is None:
            continue
        for f in facts:
            q = _quantity(f)
            if f.payload.basis is not FactBasis.CALCULATED or q is None:
                continue
            if _reaches(target, q, gap) is False:
                projection = f
                break
        if projection is None:
            continue
        if objective.payload.feasibility is not Feasibility.INFEASIBLE_ON_FACTS:
            # The arithmetic, not an opinion, records the verdict; and it
            # records it as a PROPOSAL, because only the client confirms their
            # own objective (I1). The words of the objective are untouched.
            objective = registry.apply(Supersede(objective.id, replace(
                objective, status=Status.PROPOSED,
                payload=replace(objective.payload, feasibility=Feasibility.INFEASIBLE_ON_FACTS),
                provenance=replace(objective.provenance, actor=Actor.CALCULATOR, actor_ref=_CALCULATOR_REF,
                                   derived_from=tuple(dict.fromkeys(
                                       objective.provenance.derived_from + (baseline.id, projection.id)))))))
        written = _write(registry, seen, kind=ConflictKind.OBJECTIVE_VS_FEASIBILITY, subject_id=measure_id,
                         entities=(objective, projection), calc=calc)
        if written is not None:
            out.append(written)
    return out


# ---------------------------------------------------------------------------
# 4. an assumption the evidence contradicts
# ---------------------------------------------------------------------------

def _assumption_conflicts(registry: EngagementRegistry, seen: set[tuple], calc: Calculator | None) -> list[Entity]:
    out: list[Entity] = []
    for assumption in sorted(registry.live(Kind.ASSUMPTION), key=lambda e: e.id):
        assumed = _quantity(assumption)
        measure_id = _measure_of(registry, assumption)
        if assumed is None or measure_id is None:
            continue
        for fact in sorted(registry.facts_by_measure().get(measure_id, []), key=lambda f: f.id):
            known = _quantity(fact)
            if fact.status is not Status.CONFIRMED or known is None:
                continue
            if comparable(assumed, known) != COMPARABLE or assumed.value == known.value:
                continue
            written = _write(registry, seen, kind=ConflictKind.ASSUMPTION_VS_EVIDENCE, subject_id=measure_id,
                             entities=(assumption, fact), calc=calc)
            if written is not None:
                out.append(written)
    return out


# ---------------------------------------------------------------------------
# the round pass
# ---------------------------------------------------------------------------

def detect_conflicts(registry: EngagementRegistry, *, calc: Calculator | None = None) -> list[Entity]:
    """The synthesis pass of one analysis round: detect every disagreement,
    settle visibly the ones declared precedence settles alone, put the rest to
    their owner as DECISION_REQUIRED, and refresh which recommendations are
    conditional. Returns the conflicts written this pass."""
    seen = _recorded(registry)
    written: list[Entity] = []
    written += _fact_conflicts(registry, seen, calc)
    written += _analysis_conflicts(registry, seen, calc)
    written += _objective_conflicts(registry, seen, calc)
    written += _assumption_conflicts(registry, seen, calc)
    auto_resolve(registry, calc=calc)
    emit_decisions_required(registry)
    refresh_conditional_on(registry)
    return written


def reevaluate_materiality(registry: EngagementRegistry, *, calc: Calculator | None = None) -> list[Entity]:
    """Recompute materiality for every open conflict from the LIVE support
    graph and supersede the ones whose flag changed (MF2.4). A conflict
    written before the recommendation that rests on it is immaterial when it
    is written and material once that recommendation exists; reading the
    stored flag here would wave it through forever."""
    out: list[Entity] = []
    for conflict in registry.query(Kind.CONFLICT, status=Status.OPEN):
        material = registry.is_material(conflict)
        if material == conflict.payload.material:
            continue
        # The authority moves with the flag for a judgement disagreement: what
        # a consultant may close while it touches nothing, only the decision
        # owner may close once a recommendation rests on it.
        advice = advise(registry, conflict.payload.kind,
                        tuple(c.entity_id for c in conflict.payload.conclusions),
                        material=material, calc=calc)
        entity = replace(
            conflict,
            payload=replace(conflict.payload, material=material, authority_required=advice.authority,
                            recommended_resolution=advice.winner_id, recommendation_basis=advice.basis),
            provenance=replace(conflict.provenance, actor=Actor.PARTNER, actor_ref=SYNTHESIS_ACTOR_REF))
        out.append(registry.apply(Supersede(conflict.id, entity)))
    return out


__all__ = [
    "SYNTHESIS_ACTOR_REF", "UNTESTED_VERDICT", "detect_conflicts", "reevaluate_materiality",
]
