"""app/engine/partner/charter.py - the engagement charter: fourteen id lists
assembled by query, played back item by item, and approved by the client
(design 6.6, spec section 2).

The charter is not a document the partner writes. It is fourteen queries over
the registry, and every line of it is an entity id the client can trace back to
the turn or the document it came from. That is what makes per-item confirmation
possible: each item is shown with its own locator quote, and the client may
confirm it, correct it or reject it.

The laws this module lives by:

  * The fourteen lists come from `CharterPayload`'s own fields, walked
    mechanically. A section cannot be added, dropped or reordered here without
    changing the frozen contract.
  * Approving the charter CONFIRMS exactly the client-attributed PROPOSED
    entities the charter lists, and nothing else. "Client-attributed" is not a
    judgement made here: it is `may_advance(e, CONFIRMED, Actor.CLIENT)` over
    the authority table, so a consultant judgement the charter happens to list
    is never promoted by a client's signature (MF2.2). A verdict naming an
    entity the charter does not list is refused outright.
  * A correction supersedes and RE-proposes: the corrected row is PROPOSED
    again, by the CLIENT, citing the turn the correction was made in, so it
    comes back in the next reply's playback for confirmation. A correction is
    never a confirmation of itself.
  * The whole confirmation is one batch through `apply_all`: if any item is
    refused (a corrected client fact whose new wording is not in the turn, for
    instance) nothing is written and the charter is not approved. A charter
    approved over a correction that did not land would not be the charter the
    client read.
  * Approving the charter is what makes a decision CENTRAL. Nothing else in the
    engine names the central decision, and any other live CENTRAL decision is
    visibly demoted to SUBORDINATE in the same batch, so `central_decision()`
    can never see two.
  * An amendment is a new CHARTER row citing the one it amends (`amends`). The
    previous charter is not edited and not retired: it is what the client
    approved, and it stays queryable as such.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Iterable, Mapping, Sequence

from app.engine.authority import may_advance
from app.engine.methods.contract import METHODS, MethodRegistry, select_methods
from app.engine.partner.hypothesis import central_decision_for_charter
from app.engine.partner.questions import open_issues
from app.engine.registry import EngagementRegistry
from app.engine.types import (
    TERMINAL_STATUSES, Actor, Add, AnalysisPayload, AnalysisState, Authority, CharterPayload,
    Confidence, DecisionRole, Entity, EntityDelta, FillStrategy, Kind, Provenance,
    RelationToCentralDecision, Relevance, SetStatus, Status, Supersede, make_entity,
)
from app.engine.work_products.plan import plan_work_products

__all__ = [
    "AMENDMENT_LABEL",
    "CHARTER_SECTIONS",
    "CORRECT",
    "CONFIRM",
    "CharterItem",
    "CharterOutcome",
    "CharterProposal",
    "OUT_OF_SCOPE_LABEL",
    "REJECT",
    "VERDICTS",
    "amend",
    "assemble",
    "confirm",
    "items",
    "listed_ids",
    "live_proposal",
    "plan_analyses",
    "playback",
    "propose",
    "understanding",
]

# An ISSUE the partner put out of scope carries this label AND cites the entity
# that says why. An exclusion with no recorded reason is not an exclusion the
# client can review, so it stays in scope: the fail-safe direction is to keep
# working on something, never to silently stop.
OUT_OF_SCOPE_LABEL = "out_of_scope"

# The label an amended charter carries, so a reader can see at a glance that
# this row is a revision rather than the original mandate.
AMENDMENT_LABEL = "charter_amendment"

CONFIRM = "confirm"
CORRECT = "correct"
REJECT = "reject"
VERDICTS: frozenset[str] = frozenset({CONFIRM, CORRECT, REJECT})

# `proposed_work_products` holds work-product DECLARATION ids, not entity ids:
# a preliminary plan (design 6.6) promises what the evidence supports today and
# deliberately writes no WORK_PRODUCT rows. `amends` holds a charter id, which
# the playback shows as the amended charter, not as an item to confirm.
_NON_ENTITY_FIELDS: frozenset[str] = frozenset({"proposed_work_products", "amends"})

# The fourteen sections, in the order the contract declares them.
CHARTER_SECTIONS: tuple[str, ...] = tuple(
    f.name for f in fields(CharterPayload) if f.name not in _NON_ENTITY_FIELDS) + ("proposed_work_products",)
assert len(CHARTER_SECTIONS) == 14, "the charter is fourteen lists (spec section 2)"

_TEXT_ATTRS = ("text", "statement", "name", "question")


def _text_of(e: Entity) -> str:
    for attr in _TEXT_ATTRS:
        v = getattr(e.payload, attr, None)
        if isinstance(v, str) and v:
            return v
    return e.id


def _live(view, kind: Kind | None = None) -> list[Entity]:
    return [e for e in view.query(kind) if e.status not in TERMINAL_STATUSES]


def _ids(entities: Iterable[Entity]) -> tuple[str, ...]:
    return tuple(e.id for e in entities)


# ---------------------------------------------------------------------------
# 1. The fourteen queries
# ---------------------------------------------------------------------------

def _top_level_issues(view) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Top-level issue nodes split into scope and exclusions. An excluded node
    must carry both the label and a cited rationale entity; the ones that do
    not are still in scope."""
    scope: list[str] = []
    exclusions: list[str] = []
    for i in _live(view, Kind.ISSUE):
        if i.payload.parent_id:
            continue
        if OUT_OF_SCOPE_LABEL in i.labels and i.provenance.derived_from:
            exclusions.append(i.id)
        else:
            scope.append(i.id)
    return tuple(scope), tuple(exclusions)


def assemble(view, *, planned_analyses: Sequence[str] = (), proposed_work_products: Sequence[str] = (),
             amends: str | None = None, central_decision: str | None = None) -> CharterPayload:
    """The charter as fourteen id lists, every one of them a registry query.

    `planned_analyses` and `proposed_work_products` are passed in because they
    are produced by writing (ANALYSIS rows) and by planning (a preliminary
    work-product pass) rather than by reading; everything else is read here.

    `central_decision` overrides the query for one case only: an amendment
    proposes a DIFFERENT central decision, and naming it is the whole point of
    the amendment. It becomes CENTRAL when the client approves the amendment
    and not before, so the override changes what is proposed, never what is.
    """
    scope, exclusions = _top_level_issues(view)
    central = view.get(central_decision or "") if central_decision else central_decision_for_charter(view)
    owners = _live(view, Kind.DECISION_OWNER)
    situation = _ids(_live(view, Kind.BUSINESS_CONTEXT)) + tuple(
        f.id for f in _live(view, Kind.FACT) if f.relation == RelationToCentralDecision.DEFINES)
    evidence_required = tuple(
        q.id for q in view.query(Kind.QUESTION, status=Status.OPEN)
        if q.payload.strategy == FillStrategy.REQUEST_DOCUMENT)
    return CharterPayload(
        situation=situation,
        central_decision=central.id if central is not None else None,
        decision_owner=owners[0].id if owners else None,
        objectives=_ids(_live(view, Kind.OBJECTIVE)),
        scope=scope,
        exclusions=exclusions,
        constraints=_ids(_live(view, Kind.CONSTRAINT)),
        evidence_available=_ids(_live(view, Kind.EVIDENCE_SOURCE)),
        evidence_required=evidence_required,
        # The key questions ARE the top-level issue nodes (design 6.6): the
        # engagement's questions and its scope are one structure seen twice.
        key_questions=scope,
        initial_hypotheses=_ids(_live(view, Kind.HYPOTHESIS)),
        planned_analyses=tuple(planned_analyses),
        proposed_work_products=tuple(proposed_work_products),
        open_decisions=_ids(view.query(Kind.DECISION_REQUIRED, status=Status.OPEN)),
        amends=amends,
    )


def listed_ids(payload: CharterPayload) -> tuple[tuple[str, str], ...]:
    """(section, entity id) for every entity the charter names, walked over the
    contract's own fields so the fourteen lists cannot drift out of step with
    the payload. Declaration ids and the amended charter id are not entities
    and are not walked."""
    out: list[tuple[str, str]] = []
    for f in fields(payload):
        if f.name in _NON_ENTITY_FIELDS:
            continue
        value = getattr(payload, f.name)
        if value is None:
            continue
        if isinstance(value, str):
            out.append((f.name, value))
            continue
        for eid in value:
            out.append((f.name, eid))
    return tuple(out)


# ---------------------------------------------------------------------------
# 2. Playback: what the client is shown, item by item
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CharterItem:
    """One line of the charter as the client sees it: the entity's own words,
    the locator they were taken from, and whether this is theirs to confirm."""
    entity_id: str
    kind: Kind
    text: str
    locator: str | None
    authority: Authority
    status: Status
    confirmable: bool
    section: str = ""


def _client_may_confirm(e: Entity) -> bool:
    """Client-attributed and still open to confirmation. The authority table
    decides, never a list of kinds written here: an entity whose owner is the
    client (a preference) or whose owner is the client's own recollection is
    theirs to confirm, and a consultant judgement never is (MF2.2)."""
    return e.status == Status.PROPOSED and may_advance(e, Status.CONFIRMED, Actor.CLIENT)


def playback(view, entities: Iterable[Entity], *, section: str = "") -> tuple[CharterItem, ...]:
    """Entities as playback items. Used for the charter's per-item list and for
    the reply's `understanding` block, which is the same act on a different
    set: everything the engine believes the client said, in their words, with
    the locator, for correction."""
    return tuple(CharterItem(entity_id=e.id, kind=e.kind, text=_text_of(e),
                             locator=e.provenance.source_locator, authority=e.authority,
                             status=e.status, confirmable=_client_may_confirm(e), section=section)
                 for e in entities)


def items(view, charter: Entity) -> tuple[CharterItem, ...]:
    """Every entity the charter names, in section order, first section wins for
    an id that appears twice (scope and key questions are the same nodes)."""
    out: list[CharterItem] = []
    seen: set[str] = set()
    for section, eid in listed_ids(charter.payload):
        if eid in seen:
            continue
        e = view.get(eid)
        if e is None:
            continue
        seen.add(eid)
        out.extend(playback(view, (e,), section=section))
    return tuple(out)


def understanding(view) -> tuple[CharterItem, ...]:
    """Every live PROPOSED entity the client may confirm, with its locator: the
    reply's correction surface (design 6.2 step 8). Nothing is inferred from
    silence - an item stays PROPOSED until the client says otherwise."""
    return playback(view, [e for e in _live(view) if _client_may_confirm(e)])


# ---------------------------------------------------------------------------
# 3. Proposing
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CharterProposal:
    """What one proposal pass produced. `refusals` carries what could not be
    assembled (a work-product planner that raised, for instance) in the words
    of the failure: an empty promise is shown as an empty promise."""
    charter: Entity
    items: tuple[CharterItem, ...] = ()
    planned_analyses: tuple[Entity, ...] = ()
    work_products: tuple[str, ...] = ()
    amends: str | None = None
    reproposed: bool = False
    refusals: tuple[str, ...] = ()


def _planned_already(view, method_id: str, issue_id: str) -> bool:
    for a in _live(view, Kind.ANALYSIS):
        p = a.payload
        if p.method_id == method_id and issue_id in p.issue_ids and p.state == AnalysisState.PLANNED:
            return True
    return False


def plan_analyses(registry: EngagementRegistry, *, actor_ref: str,
                  methods: MethodRegistry = METHODS) -> list[Entity]:
    """Every method the open issue nodes select, recorded as ANALYSIS(PLANNED).

    The charter promises analyses by row, not by prose, so what was promised
    and what ran are the same kind of thing and can be compared. Re-proposing a
    charter never duplicates a promise it already made.
    """
    for s in select_methods(open_issues(registry), registry, methods):
        if _planned_already(registry, s.method_id, s.issue_id):
            continue
        spec = methods.get(s.method_id).spec
        registry.apply(Add(make_entity(
            kind=Kind.ANALYSIS, engagement_id=registry.engagement_id,
            payload=AnalysisPayload(method_id=spec.id, method_version=spec.version,
                                    issue_ids=(s.issue_id,), state=AnalysisState.PLANNED),
            provenance=Provenance(actor=Actor.PARTNER, actor_ref=actor_ref, derived_from=(s.issue_id,)),
            confidence=Confidence(None), relevance=Relevance(None, 0.0),
            relation=RelationToCentralDecision.INFORMS, status=Status.PROPOSED)))
    return [a for a in _live(registry, Kind.ANALYSIS) if a.payload.state == AnalysisState.PLANNED]


def live_proposal(view) -> Entity | None:
    """The charter currently on the table, if any."""
    proposed = view.query(Kind.CHARTER, status=Status.PROPOSED)
    return proposed[-1] if proposed else None


def _preliminary_products(view, bounds: Mapping[str, Any] | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The deliverables the evidence supports today. A planner failure costs
    the promise, never the charter: the reason is recorded and the client sees
    an empty list rather than a crashed turn."""
    try:
        plan = plan_work_products(view, preliminary=True, bounds=bounds)
    except Exception as exc:
        return (), (f"work products could not be planned: {exc}",)
    return tuple(v.product_id for v in plan.planned), ()


def propose(registry: EngagementRegistry, *, turn_number: int = 0, amends: str | None = None,
            bounds: Mapping[str, Any] | None = None, central_decision: str | None = None,
            methods: MethodRegistry = METHODS) -> CharterProposal:
    """Assemble and write a CHARTER, PROPOSED by the partner.

    A charter whose fourteen lists are identical to the one already on the
    table is not re-written: a re-proposal with the same content is not new
    information, and a fresh row every turn would bury the one the client is
    reading. An amendment always writes, because `amends` makes it different.
    """
    actor_ref = f"partner:turn:{turn_number}" if turn_number else "partner:charter"
    analyses = plan_analyses(registry, actor_ref=actor_ref, methods=methods)
    products, refusals = _preliminary_products(registry, bounds)
    payload = assemble(registry, planned_analyses=tuple(a.id for a in analyses),
                       proposed_work_products=products, amends=amends,
                       central_decision=central_decision)
    standing = live_proposal(registry)
    if standing is not None and standing.payload == payload:
        return CharterProposal(charter=standing, items=items(registry, standing),
                               planned_analyses=tuple(analyses), work_products=products,
                               amends=amends, reproposed=True, refusals=refusals)
    derived = tuple(dict.fromkeys(eid for _, eid in listed_ids(payload) if registry.get(eid) is not None))
    labels = (AMENDMENT_LABEL,) if amends else ()
    charter = registry.apply(Add(make_entity(
        kind=Kind.CHARTER, engagement_id=registry.engagement_id, payload=payload,
        provenance=Provenance(actor=Actor.PARTNER, actor_ref=actor_ref, derived_from=derived),
        confidence=Confidence(None), relevance=Relevance(payload.central_decision, 0.0),
        relation=RelationToCentralDecision.DEFINES, status=Status.PROPOSED, labels=labels)))
    return CharterProposal(charter=charter, items=items(registry, charter),
                           planned_analyses=tuple(analyses), work_products=products,
                           amends=amends, refusals=refusals)


def amend(registry: EngagementRegistry, previous_charter_id: str, *, turn_number: int = 0,
          bounds: Mapping[str, Any] | None = None, central_decision: str | None = None,
          methods: MethodRegistry = METHODS) -> CharterProposal:
    """Propose a charter that amends an approved one (design 6.7). The previous
    charter is untouched: it is what the client approved, and the amendment
    says so by citing it."""
    return propose(registry, turn_number=turn_number, amends=previous_charter_id,
                   bounds=bounds, central_decision=central_decision, methods=methods)


# ---------------------------------------------------------------------------
# 4. Confirming, item by item
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CharterOutcome:
    """What one confirmation did. `refused` is non-empty exactly when nothing
    was written: the batch is one decision."""
    charter: Entity
    approved: bool = False
    confirmed: tuple[str, ...] = ()
    corrected: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()
    central_decision: str | None = None
    refused: tuple[str, ...] = ()


def _rebuilt(e: Entity, *, payload: Any, actor: Actor, actor_ref: str,
             derived_from: tuple[str, ...] | None = None, status: Status = Status.PROPOSED) -> Entity:
    """A replacement row for a supersession, through the one constructor that
    derives authority and info type (I7): a corrected payload may change what
    kind of information the row holds, and the owner must move with it."""
    return make_entity(
        kind=e.kind, engagement_id=e.engagement_id, payload=payload,
        provenance=Provenance(actor=actor, actor_ref=actor_ref,
                              derived_from=e.provenance.derived_from if derived_from is None else derived_from,
                              source_locator=e.provenance.source_locator),
        confidence=e.confidence, relevance=e.relevance, relation=e.relation, status=status,
        entity_id=e.id, labels=e.labels)


def confirm(registry: EngagementRegistry, charter_id: str, *,
            verdicts: Mapping[str, str] | None = None,
            corrections: Mapping[str, Any] | None = None,
            turn_number: int = 0, turn_id: str | None = None) -> CharterOutcome:
    """The client's answer to the charter, applied as one batch.

    Every listed client-attributed PROPOSED item is CONFIRMED unless the client
    said otherwise for that item: they were shown each one with its locator
    before signing, so approval is an act, not silence. `correct` supersedes
    and re-proposes; `reject` retires. Anything the registry refuses refuses
    the whole confirmation - a charter approved over a correction that did not
    land would not be the charter the client read.
    """
    verdicts = dict(verdicts or {})
    corrections = dict(corrections or {})
    charter = registry.get(charter_id)
    if charter is None or charter.kind != Kind.CHARTER:
        return CharterOutcome(charter=charter, refused=(f"{charter_id} is not a charter",))
    if charter.status == Status.APPROVED:
        return CharterOutcome(charter=charter, approved=True,
                              refused=(f"{charter_id} is already approved",))
    if charter.status in TERMINAL_STATUSES:
        return CharterOutcome(charter=charter, refused=(f"{charter_id} is {charter.status.value}",))

    shown = items(registry, charter)
    listed = {i.entity_id: i for i in shown}
    actor_ref = f"client:turn:{turn_number}" if turn_number else "client:charter"
    by_client = Provenance(actor=Actor.CLIENT, actor_ref=actor_ref,
                           derived_from=(turn_id,) if turn_id else ())

    refused: list[str] = []
    for eid, verdict in verdicts.items():
        if verdict not in VERDICTS:
            refused.append(f"{eid}: {verdict!r} is not one of {sorted(VERDICTS)}")
        elif eid not in listed:
            # The law the mutation "confirm promotes unlisted entities" breaks:
            # a signature on this charter reaches exactly what this charter
            # showed, and nothing the client never saw.
            refused.append(f"{eid} is not listed on {charter.id}")
    central_id = charter.payload.central_decision
    if central_id is not None and verdicts.get(central_id) == REJECT:
        refused.append(f"{central_id} is the charter's central decision and cannot be rejected; amend instead")
    if refused:
        return CharterOutcome(charter=charter, refused=tuple(refused))

    deltas: list[EntityDelta] = []
    confirmed: list[str] = []
    corrected: list[str] = []
    rejected: list[str] = []
    replaced: dict[str, Any] = {}
    for item in shown:
        verdict = verdicts.get(item.entity_id, CONFIRM)
        entity = registry.get(item.entity_id)
        if entity is None:                                # pragma: no cover - defensive
            continue
        if verdict == REJECT:
            deltas.append(SetStatus(entity.id, Status.REJECTED, by_client))
            rejected.append(entity.id)
        elif verdict == CORRECT:
            payload = corrections.get(entity.id)
            if payload is None:
                refused.append(f"{entity.id}: a correction needs the corrected payload")
                continue
            replaced[entity.id] = payload
            corrected.append(entity.id)
        elif item.confirmable:
            deltas.append(SetStatus(entity.id, Status.CONFIRMED, by_client))
            confirmed.append(entity.id)
        # An item the client may not confirm (a consultant judgement the
        # charter lists) is left exactly as it is: approving the charter is
        # approving the plan, not adopting the consultant's conclusions.
    if refused:
        return CharterOutcome(charter=charter, refused=tuple(refused))

    # The central decision becomes CENTRAL here and only here, carrying its
    # correction if it had one, so one supersession says both things at once.
    for other in _live(registry, Kind.DECISION):
        if other.payload.role == DecisionRole.CENTRAL and other.id != central_id:
            demoted = _rebuilt(other, payload=_with_role(other.payload, DecisionRole.SUBORDINATE),
                               actor=Actor.CLIENT, actor_ref=actor_ref)
            deltas.append(Supersede(other.id, demoted))
    central_entity = registry.get(central_id or "")
    if central_entity is not None and central_entity.kind == Kind.DECISION:
        payload = _with_role(replaced.pop(central_entity.id, central_entity.payload),
                             DecisionRole.CENTRAL)
        # A row that would say exactly what the current row says is not written:
        # a re-confirmed charter must not fill the lineage with restatements.
        if payload != central_entity.payload:
            deltas.append(Supersede(central_entity.id, _rebuilt(
                central_entity, payload=payload, actor=Actor.CLIENT, actor_ref=actor_ref,
                derived_from=_cited(central_entity, turn_id))))

    for eid, payload in replaced.items():
        old = registry.get(eid)
        if old is None:                                   # pragma: no cover - defensive
            continue
        deltas.append(Supersede(eid, _rebuilt(old, payload=payload, actor=Actor.CLIENT,
                                              actor_ref=actor_ref, derived_from=_cited(old, turn_id))))

    deltas.append(SetStatus(charter.id, Status.APPROVED, by_client))
    try:
        registry.apply_all(deltas)
    except Exception as exc:
        # One decision: the correction that was refused takes the approval with
        # it, and the client is told which law refused it.
        return CharterOutcome(charter=registry.get(charter.id), refused=(str(exc),))
    return CharterOutcome(charter=registry.get(charter.id), approved=True,
                          confirmed=tuple(confirmed), corrected=tuple(corrected),
                          rejected=tuple(rejected), central_decision=central_id)


def _with_role(payload: Any, role: DecisionRole) -> Any:
    from dataclasses import replace as _replace

    return _replace(payload, role=role)


def _cited(e: Entity, turn_id: str | None) -> tuple[str, ...]:
    """What a client-corrected row rests on: what it already cited plus the
    turn the correction was made in. A corrected client fact needs that turn
    on the record or I2 refuses it - its new wording must be the client's own
    words, verbatim, from a turn the registry holds."""
    if turn_id is None:
        return e.provenance.derived_from
    return tuple(dict.fromkeys(e.provenance.derived_from + (turn_id,)))
