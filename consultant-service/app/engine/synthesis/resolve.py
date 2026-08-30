"""app/engine/synthesis/resolve.py - who settles a conflict, and on what basis.

Three things live here, in the order the engine reaches them (design 9.4):

1. `advise()` - the recommended resolution, from DECLARED PRECEDENCE ONLY.
   Two sources of one current-state fact are ordered by CURRENT_STATE_PRECEDENCE
   and by nothing else: not by recency, not by which specialist wrote it, not
   by confidence. Equal rank recommends nobody and names the CLIENT as the
   authority that must designate one; an analysis disagreement recommends
   nobody either, because precedence orders records, not judgements.

2. `auto_resolve()` - the only resolution the engine performs by itself, and
   it is visible. It happens when the winner's authority is VERIFIED_RECORD
   (with the winning source's record class confirmed by the client, MF2.3, and
   a STRICTLY higher rank) or DETERMINISTIC_ENGINE (arithmetic that recomputes
   exactly). The conflict is superseded into RESOLVED by `document:EVI-n` or
   `calculator`, and the loser is superseded carrying the label
   SUPERSEDED_BY_RECORD - the one path I2 admits for retiring a client fact -
   so the loser stays queryable and says who retired it. A rank difference
   whose record class the client has NOT confirmed resolves nothing: it opens
   an OFFHAND provenance question ("what kind of record is this?") and leaves
   the conflict OPEN with authority CLIENT. A model's guess about what a
   document is must never be able to retire what the client said.

3. `resolve()` - every other resolution, by a human. The authority act is the
   conflict's transition to RESOLVED, which I1 checks against
   MAY_CONFIRM[authority_required]; this module refuses the same act first, and
   turns a refusal at the registry door into the same exception, so the API
   answers 403/409 and never a 500. Resolving never deletes:
   each unchosen conclusion is REJECTED, with the resolution named in the row
   that rejected it, and stays addressable by get()/lineage(). The rejections
   and the resolution are ONE batch (apply_all), so a refusal leaves nothing
   half-applied.

`emit_decisions_required()` closes the loop the client sees: an open material
conflict nobody can settle inside the engine becomes a DECISION_REQUIRED
naming its conclusions, which is also what L12 looks for behind an objective
the facts show infeasible.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from app.engine.authority import MAY_CONFIRM, may_advance, precedence_rank
from app.engine.registry import SUPERSEDED_BY_RECORD, Calculator, EngagementRegistry
from app.engine.types import (
    CURRENT_STATE_PRECEDENCE, TERMINAL_STATUSES, Actor, Add, AsksFor, Authority, Confidence, ConflictKind,
    DecisionRequiredPayload, EffortClass, Entity, FactBasis, FillStrategy, Kind, Provenance, QuestionPayload,
    RecordClass, RegistryError, SetStatus, Status, Supersede, make_entity,
)

# Which authority a conflict names is a function of what kind of conflict it
# is, and (for judgements) of whether it is material. Every ConflictKind is in
# exactly one class; the assert below is the law that a new kind must declare
# where it belongs rather than silently inherit CLIENT.
CLIENT_DESIGNATES: frozenset[ConflictKind] = frozenset({
    ConflictKind.OBJECTIVE_VS_FEASIBILITY, ConflictKind.ASSUMPTION_VS_EVIDENCE,
})
PRECEDENCE_ORDERS: frozenset[ConflictKind] = frozenset({
    ConflictKind.VALUE, ConflictKind.DEFINITION, ConflictKind.CLIENT_VS_RECORD,
})
JUDGEMENT_DISAGREEMENT: frozenset[ConflictKind] = frozenset({ConflictKind.SPECIALIST_DISAGREEMENT})
assert CLIENT_DESIGNATES | PRECEDENCE_ORDERS | JUDGEMENT_DISAGREEMENT == set(ConflictKind), \
    "every conflict kind declares which authority resolves it"

# Names, never literals, at every comparison and in every recorded actor_ref
# (the whitelist AST law, design 18.2, sees no string inside a branch test).
_PRECEDENCE_NAME = "CURRENT_STATE_PRECEDENCE"
_RECOMPUTE_BASIS = "recomputed exactly by the calculator"
_DOCUMENT_REF = "document"
_CALCULATOR_REF = "calculator"
_RESOLUTION_REF = "resolution"
_PROVENANCE_REF = "synthesis:provenance"
_DECISION_REF = "synthesis:decision_required"


class ResolutionRefused(Exception):
    """The act is not this actor's to perform, or the conflict is not open, or
    the choice is not one of the recorded conclusions. Raised before anything
    is written; the API maps it to 403/409."""


@dataclass(frozen=True)
class ResolutionAdvice:
    """What precedence says about one conflict, recomputed from the live
    registry every time it is asked. Nothing here is read from the stored
    payload: a record class confirmed since the conflict was written must
    change the answer (MF2.3/MF2.4)."""
    winner_id: str | None
    basis: str | None
    authority: Authority
    automatic: bool = False
    winning_source_id: str | None = None      # the confirmed record that wins
    unconfirmed_source_id: str | None = None  # the record that would win, if the client said what it is


def _record_source(registry: EngagementRegistry, fact: Entity) -> Entity | None:
    """The EVIDENCE_SOURCE a fact was read from: the row that knows what the
    document IS and whether the client confirmed that classification."""
    for sid in fact.provenance.derived_from:
        e = registry.get(sid)
        if e is not None and e.kind is Kind.EVIDENCE_SOURCE:
            return e
    return None


def _precedence_advice(registry: EngagementRegistry, conclusion_ids: tuple[str, ...],
                       calc: Calculator | None) -> ResolutionAdvice:
    facts = [registry.get(i) for i in conclusion_ids]
    if any(f is None or f.kind is not Kind.FACT for f in facts):
        return ResolutionAdvice(None, None, Authority.CLIENT)

    # Arithmetic first: a calculated fact that recomputes exactly is not one
    # opinion among several, it is the arithmetic of facts already registered
    # (L7 is equality, not closeness). Without a calculator nothing is claimed.
    calculated = [f for f in facts if f.payload.basis is FactBasis.CALCULATED]
    if len(calculated) == 1 and calc is not None and calc.recompute(calculated[0], registry) is True:
        return ResolutionAdvice(calculated[0].id, _RECOMPUTE_BASIS, Authority.DETERMINISTIC_ENGINE, automatic=True)

    ranks = [(f, precedence_rank(f, registry)) for f in facts]
    if any(r is None for _f, r in ranks):
        # An unranked source (a calculated or external fact, an unknown record
        # class) is not weaker or stronger: it is unordered, and the client
        # designates. Absence of a rank is never read as the bottom rank.
        return ResolutionAdvice(None, None, Authority.CLIENT)
    best = min(r for _f, r in ranks)
    winners = [f for f, r in ranks if r == best]
    if len(winners) != 1:
        # Equal rank never resolves automatically (design 5.4): two management
        # reports disagreeing is a question for the client, not a coin toss.
        return ResolutionAdvice(None, None, Authority.CLIENT)
    winner = winners[0]
    losers = ", ".join(CURRENT_STATE_PRECEDENCE[r] for f, r in ranks if f.id != winner.id)
    basis = f"{_PRECEDENCE_NAME}: {CURRENT_STATE_PRECEDENCE[best]} > {losers}"

    source = _record_source(registry, winner)
    confirmed = source is not None and source.payload.record_class_confirmed_by_client is True
    if winner.authority is Authority.VERIFIED_RECORD and confirmed:
        return ResolutionAdvice(winner.id, basis, Authority.VERIFIED_RECORD, automatic=True,
                                winning_source_id=source.id)
    unconfirmed = source.id if winner.authority is Authority.VERIFIED_RECORD and source is not None else None
    return ResolutionAdvice(winner.id, basis, Authority.CLIENT, unconfirmed_source_id=unconfirmed)


def advise(registry: EngagementRegistry, conflict_kind: ConflictKind, conclusion_ids: tuple[str, ...],
           *, material: bool, calc: Calculator | None = None) -> ResolutionAdvice:
    """The recommended resolution and the authority that must settle it."""
    if conflict_kind in CLIENT_DESIGNATES:
        # An objective the arithmetic refutes, or an assumption the evidence
        # contradicts, is the client's to change: the engine states the
        # arithmetic, it does not choose the objective.
        return ResolutionAdvice(None, None, Authority.CLIENT)
    if conflict_kind in PRECEDENCE_ORDERS:
        return _precedence_advice(registry, conclusion_ids, calc)
    # Judgements: precedence orders records, not conclusions. A material
    # disagreement belongs to the decision owner; an immaterial one the
    # consultant closes. Removing the materiality half is the mutation
    # "let CONSULTANT resolve a material trade-off".
    return ResolutionAdvice(None, None, Authority.DECISION_OWNER if material else Authority.CONSULTANT)


def _resolved_row(conflict: Entity, chosen: str | None, actor: Actor, actor_ref: str,
                  basis: str | None, rationale: str) -> Entity:
    """The conflict's next version: RESOLVED, with who chose what and why on
    the row itself. I1 re-checks the transition at the registry door."""
    return replace(
        conflict, status=Status.RESOLVED,
        payload=replace(conflict.payload, recommended_resolution=chosen, recommendation_basis=basis,
                        resolution_chosen=chosen, resolution_by=actor_ref, resolution_rationale=rationale),
        provenance=replace(conflict.provenance, actor=actor, actor_ref=actor_ref),
    )


def _retire_by_record(loser: Entity, winner_id: str, actor: Actor, actor_ref: str) -> Supersede:
    """The loser's next version: same words, same measure, plus the label that
    says a record retired it. Written at PROPOSED because a confirmation is
    the client's act and a record cannot make one on their behalf - the row
    stays queryable, and stops counting as a confirmed support (L2)."""
    return Supersede(loser.id, replace(
        loser, status=Status.PROPOSED,
        labels=tuple(dict.fromkeys(loser.labels + (SUPERSEDED_BY_RECORD,))),
        provenance=replace(loser.provenance, actor=actor, actor_ref=actor_ref,
                           derived_from=tuple(dict.fromkeys(loser.provenance.derived_from + (winner_id,)))),
    ))


def _resolve_visibly(registry: EngagementRegistry, conflict: Entity, advice: ResolutionAdvice) -> Entity | None:
    winner = registry.get(advice.winner_id) if advice.winner_id else None
    basis = advice.basis
    # An automatic resolution always says on what basis it acted; without one
    # there is nothing visible to record, so nothing is resolved.
    if winner is None or basis is None:
        return None
    if advice.winning_source_id is not None:
        actor, actor_ref = Actor.DOCUMENT, f"{_DOCUMENT_REF}:{advice.winning_source_id}"
    else:
        actor, actor_ref = Actor.CALCULATOR, _CALCULATOR_REF
    deltas: list = []
    for c in conflict.payload.conclusions:
        loser = registry.get(c.entity_id)
        if loser is None or loser.id == winner.id or loser.status in TERMINAL_STATUSES:
            continue
        deltas.append(_retire_by_record(loser, winner.id, actor, actor_ref))
    deltas.append(Supersede(conflict.id, _resolved_row(conflict, winner.id, actor, actor_ref, basis, basis)))
    try:
        registry.apply_all(deltas)
    except RegistryError:
        # The registry refused to retire a loser (I2: only the client, or a
        # record carrying the label, supersedes a client fact). Failing closed
        # IS the answer: apply_all rolled the batch back, the conflict stays
        # OPEN and a human resolves it.
        return None
    return registry.get(conflict.id)


def _provenance_question(registry: EngagementRegistry, conflict: Entity, advice: ResolutionAdvice) -> Entity | None:
    """A rank difference the client never confirmed asks what the document is,
    at OFFHAND effort (they know), instead of letting the classification a
    model proposed retire what the client said (MF2.3)."""
    source = registry.get(advice.unconfirmed_source_id) if advice.unconfirmed_source_id else None
    if source is None:
        return None
    ref = f"{_PROVENANCE_REF}:{source.id}"
    if any(q.provenance.actor_ref == ref for q in registry.live(Kind.QUESTION)):
        return None
    classes = ", ".join(rc.value.replace("_", " ") for rc in RecordClass if rc is not RecordClass.UNKNOWN)
    payload = QuestionPayload(
        text=f'What kind of record is "{source.payload.name}" - {classes}?',
        asks_for=(AsksFor(Kind.EVIDENCE_SOURCE, {"record_class_confirmed_by_client": True}),),
        why=f"it carries a value that disagrees with {conflict.payload.subject_id}",
        effort=EffortClass.OFFHAND, strategy=FillStrategy.ASK_CLIENT,
        material=registry.is_material(conflict),
    )
    question = make_entity(
        kind=Kind.QUESTION, engagement_id=registry.engagement_id, payload=payload,
        provenance=Provenance(actor=Actor.PARTNER, actor_ref=ref,
                              derived_from=(conflict.id, source.id) + ((advice.winner_id,) if advice.winner_id else ())),
        confidence=Confidence(None), relevance=conflict.relevance, relation=conflict.relation, status=Status.OPEN)
    return registry.apply(Add(question))


def auto_resolve(registry: EngagementRegistry, *, calc: Calculator | None = None) -> list[Entity]:
    """Every open conflict the engine may settle alone, settled visibly; every
    one it may not, left open - with the provenance question that would let it
    decide next round."""
    out: list[Entity] = []
    for conflict in registry.query(Kind.CONFLICT, status=Status.OPEN):
        ids = tuple(c.entity_id for c in conflict.payload.conclusions)
        advice = advise(registry, conflict.payload.kind, ids,
                        material=registry.is_material(conflict), calc=calc)
        if advice.automatic and advice.winner_id is not None:
            resolved = _resolve_visibly(registry, conflict, advice)
            if resolved is not None:
                out.append(resolved)
        elif advice.unconfirmed_source_id is not None:
            _provenance_question(registry, conflict, advice)
    return out


def _already_asked(registry: EngagementRegistry, conflict: Entity, asked: set[str]) -> bool:
    """Has this disagreement already been put to its owner?

    Usually the test is the conflict's own id. An infeasible objective is the
    exception: whoever finds it asks about it, and a CALCULATION method
    (methods/builtin/financial_model.py, FM3) writes its DECISION_REQUIRED
    citing the OBJECTIVE rather than the conflict - which is exactly the row
    `infeasible_objectives_without_decision()` counts as asked behind L12. A
    second one written here would put the client one question twice, and L12
    would see two decisions for one objective. The test made here is the test
    L12 makes, so the two cannot drift apart.
    """
    if conflict.id in asked:
        return True
    if conflict.payload.kind is not ConflictKind.OBJECTIVE_VS_FEASIBILITY:
        # Only the objective conflict is asked about by an id other than its
        # own; matching any shared conclusion generally would silence a second
        # genuine disagreement over the same fact.
        return False
    for c in conflict.payload.conclusions:
        entity = registry.get(c.entity_id)
        if entity is not None and entity.kind is Kind.OBJECTIVE and entity.id in asked:
            return True
    return False


def emit_decisions_required(registry: EngagementRegistry) -> list[Entity]:
    """An open material conflict is put to its owner as a DECISION_REQUIRED
    that names the conflict and every conclusion in `derived_from` - which is
    what `infeasible_objectives_without_decision()` reads behind L12."""
    asked: set[str] = set()
    for d in registry.live(Kind.DECISION_REQUIRED):
        # derived_from AND options, the same two places L12 reads, so a
        # decision written by a method counts as asked here too.
        asked.update(d.provenance.derived_from)
        asked.update(d.payload.options)
    out: list[Entity] = []
    for conflict in registry.query(Kind.CONFLICT, status=Status.OPEN):
        if _already_asked(registry, conflict, asked) or not registry.is_material(conflict):
            continue
        conclusions = conflict.payload.conclusions
        options = tuple(c.entity_id for c in conclusions)
        alternatives = " | ".join(f"{c.entity_id}: {c.statement}" for c in conclusions)
        central = registry.central_decision()
        payload = DecisionRequiredPayload(
            text=f"Which conclusion stands for {conflict.payload.subject_id}? {alternatives}",
            from_authority=conflict.payload.authority_required,
            decision_id=central.id if central is not None else None,
            options=options,
        )
        entity = make_entity(
            kind=Kind.DECISION_REQUIRED, engagement_id=registry.engagement_id, payload=payload,
            provenance=Provenance(actor=Actor.PARTNER, actor_ref=f"{_DECISION_REF}:{conflict.id}",
                                  derived_from=(conflict.id,) + options),
            confidence=Confidence(None), relevance=conflict.relevance, relation=conflict.relation,
            status=Status.OPEN)
        out.append(registry.apply(Add(entity)))
    return out


def _rejector(loser: Entity, conflict_id: str, actor: Actor, actor_ref: str) -> Provenance:
    """Who records the loser's retirement. The authority act is the conflict's
    RESOLVED transition; the loser's REJECTED row is that act's recorded
    consequence, written in the resolver's name when may_advance admits them
    and otherwise by the PARTNER, who keeps the process record. Never by an
    actor may_advance would refuse: apply_all would then roll the whole
    resolution back, which is the right outcome, not a half-applied one."""
    ref = f"{_RESOLUTION_REF}:{conflict_id}:{actor_ref}"
    if may_advance(loser, Status.REJECTED, actor):
        return Provenance(actor=actor, actor_ref=ref)
    return Provenance(actor=Actor.PARTNER, actor_ref=ref)


def resolve(registry: EngagementRegistry, conflict_id: str, *, chosen_entity_id: str | None,
            actor: Actor, actor_ref: str, rationale: str, on_behalf_of: str | None = None) -> Entity:
    """Settle a conflict by hand. Refuses before writing anything when the
    actor is not one MAY_CONFIRM[authority_required] admits, when the conflict
    is not open, when the choice is not one of the recorded conclusions, or
    when a decision owner's delegation is claimed rather than recorded - and
    refuses in the same currency when the registry itself declines the batch,
    so the only two outcomes are a settled conflict or an untouched one."""
    conflict = registry.get(conflict_id)
    if conflict is None or conflict.kind is not Kind.CONFLICT:
        raise ResolutionRefused(f"{conflict_id} is not a conflict")
    if conflict.status is not Status.OPEN:
        raise ResolutionRefused(f"{conflict_id} is {conflict.status.value}; only an open conflict is resolved")
    if not rationale:
        raise ResolutionRefused("a resolution records why it went the way it did")
    required = conflict.payload.authority_required
    if actor not in MAY_CONFIRM[required]:
        raise ResolutionRefused(
            f"{conflict_id} is resolved by {required.value}; {actor.value} may not settle it")
    if actor is Actor.DECISION_OWNER:
        # Delegation is recorded, never assumed (design 5.3): the acting party
        # names the DECISION_OWNER row they act for, and it must exist.
        owner = registry.get(on_behalf_of) if on_behalf_of else None
        if owner is None or owner.kind is not Kind.DECISION_OWNER or owner.status in TERMINAL_STATUSES:
            raise ResolutionRefused("a decision owner acts on behalf of a recorded DECISION_OWNER")
    ids = tuple(c.entity_id for c in conflict.payload.conclusions)
    if chosen_entity_id is not None and chosen_entity_id not in ids:
        raise ResolutionRefused(f"{chosen_entity_id} is not one of this conflict's conclusions {ids}")

    deltas: list = []
    for entity_id in ids:
        if entity_id == chosen_entity_id:
            continue
        loser = registry.get(entity_id)
        if loser is None or loser.status in TERMINAL_STATUSES:
            continue
        # Never deleted: REJECTED, still addressable by get() and lineage(),
        # and the row names the resolution that rejected it.
        deltas.append(SetStatus(loser.id, Status.REJECTED, _rejector(loser, conflict_id, actor, actor_ref)))
    deltas.append(Supersede(conflict_id, _resolved_row(
        conflict, chosen_entity_id, actor, actor_ref, conflict.payload.recommendation_basis, rationale)))
    try:
        registry.apply_all(deltas)
    except RegistryError as e:
        # The rejections and the resolution are ONE batch, so a law refused at
        # the registry door leaves nothing half-applied: no conflict marked
        # RESOLVED above a conclusion still live. The caller is told in this
        # module's own currency (the API answers 403/409, never a 500), and the
        # conflict is still open for someone who may settle it.
        raise ResolutionRefused(f"{conflict_id} was not settled: {e}") from e
    return registry.get(conflict_id)


__all__ = [
    "CLIENT_DESIGNATES", "JUDGEMENT_DISAGREEMENT", "PRECEDENCE_ORDERS", "ResolutionAdvice",
    "ResolutionRefused", "advise", "auto_resolve", "emit_decisions_required", "resolve",
]
