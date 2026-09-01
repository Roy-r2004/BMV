"""app/engine/partner/hypothesis.py - the engagement hypothesis (design 6.4, 6.6).

Candidate central decisions are DECISION rows: the STATED_REQUEST from turn 1
and partner-inferred alternatives proposed by revise_hypothesis.j2 (which may
only ADD candidates, each citing the entity ids that make it plausible; it
never removes, ranks or chooses one). The ranking is deterministic and is
recomputed from the registry alone on every read:

    score(d)  = sum over live e with e.relevance.decision_id == d of
                e.relevance.weight * conf(e) * REL_MULTIPLIER[e.relation]
    conf(e)   = e.confidence.value, or UNKNOWN_CONFIDENCE_PRIOR when None
    weight(d) = score(d) / sum of scores

so adding evidence flips the ranking with no model call, and the model can
never smuggle a verdict in through a number the registry did not compute.

Symptom vs problem: when an inferred candidate outweighs the stated request
by SYMPTOM_MARGIN and at least one HYPOTHESIS links an issue under the stated
request to a cause under the inferred candidate, the stated DECISION is
superseded with symptom_of set and a DECISION_REQUIRED("confirm revised
scope") opens for the CLIENT. Until the client resolves it, the charter keeps
naming the stated request: a reframe is a scope change, and scope belongs to
the client, never to a weight.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from pydantic import BaseModel, Field

from app.engine import templating
from app.engine.llm import ModelCall, ModelProvider, structured_call
from app.engine.types import (
    BOUNDS, TERMINAL_STATUSES, UNKNOWN_CONFIDENCE_PRIOR, Actor, Add, Authority, Confidence,
    DecisionPayload, DecisionRequiredPayload, DecisionRole, Entity, FactBasis, HypothesisPayload,
    Kind, Provenance, RelationToCentralDecision, Relevance, Status, Supersede, make_entity,
)

# DecisionPayload.origin value for a candidate the partner proposed (the closed
# origin vocabulary is documented on the payload; this is the member this
# module reads and writes).
PARTNER_INFERRED = "partner_inferred"

# The DECISION_REQUIRED the reframe opens. Identified by a label, never by its
# prose: control flow that matched on wording would be a sentence patch.
CONFIRM_SCOPE_TEXT = "confirm revised scope"
SCOPE_CONFIRMATION_LABEL = "scope_confirmation"

# Questions that exist to pin a quantity dimension carry this label (written
# by partner/questions.py). charter_ready reads it structurally; a question
# without the label simply does not block, because absent evidence is not
# evidence of a defect.
PIN_DIMENSION_LABEL = "pin_dimension"

REVISE_PURPOSE = "engine:revise_hypothesis"

# Relation multipliers of the deterministic score (design 6.4). Distinct from
# SENSITIVITY: that table prices a question's relation, this one prices how
# hard a piece of evidence bears on a candidate decision.
REL_MULTIPLIER: Mapping[RelationToCentralDecision, float] = {
    RelationToCentralDecision.DEFINES: 1.0,
    RelationToCentralDecision.RESOLVES: 1.0,
    RelationToCentralDecision.CONSTRAINS: 0.7,
    RelationToCentralDecision.EVIDENCES: 0.7,
    RelationToCentralDecision.INFORMS: 0.3,
}


# ---------------------------------------------------------------------------
# What a statement bears on, and how (design 6.4)
# ---------------------------------------------------------------------------
#
# The score above is only ever as real as the relevance links the registry
# holds, and a link is a consultant judgement about how a piece of evidence
# bears on a candidate decision. That judgement is DERIVED here, from what the
# row IS - its kind, and for a FACT the basis that says where it came from -
# and never asked of the model: a relation or a weight the model returned would
# be the verdict this module exists to keep it away from, and "adding evidence
# flips the ranking with no model call" would become a claim about a prompt.
#
# A kind this table does not name bears on nothing and keeps relation UNKNOWN,
# which REL_MULTIPLIER prices at zero. The omissions are deliberate, not gaps:
# a DECISION is a candidate, not evidence for one (and a candidate never votes,
# for itself or for a rival); an EVIDENCE_SOURCE is a process record of where
# words came from; a QUESTION is a hole, and asking about a decision is not
# evidence for it.
BEARING_BY_KIND: Mapping[Kind, RelationToCentralDecision] = {
    Kind.OBJECTIVE: RelationToCentralDecision.DEFINES,          # what the decision is for
    Kind.DECISION_OWNER: RelationToCentralDecision.DEFINES,     # whose decision it is
    Kind.CONSTRAINT: RelationToCentralDecision.CONSTRAINS,      # what bounds it
    Kind.DEADLINE: RelationToCentralDecision.CONSTRAINS,        # by when it must be taken
    Kind.MEASURE: RelationToCentralDecision.EVIDENCES,          # what it will be judged by
    Kind.BUSINESS_CONTEXT: RelationToCentralDecision.INFORMS,   # the setting it is taken in
    Kind.STAKEHOLDER: RelationToCentralDecision.INFORMS,        # who else it touches
}

# A FACT's bearing is its basis. The client's own words and a quote the
# document demonstrably contains are evidence; a quote verify_quote could NOT
# find in the hashed text only informs, because that is the same distinction
# the promotion test already makes (ingest.verify_quote) and a record the
# document may never have made must not weigh as one it did.
BEARING_BY_FACT_BASIS: Mapping[FactBasis, RelationToCentralDecision] = {
    FactBasis.CLIENT_STATED: RelationToCentralDecision.EVIDENCES,
    FactBasis.DOCUMENT_VERIFIED: RelationToCentralDecision.EVIDENCES,
    FactBasis.EXTERNAL_SOURCED: RelationToCentralDecision.EVIDENCES,
    FactBasis.CALCULATED: RelationToCentralDecision.EVIDENCES,
    FactBasis.DOCUMENT_EXTRACTED: RelationToCentralDecision.INFORMS,
    FactBasis.INFERRED: RelationToCentralDecision.INFORMS,
}

# One statement, one vote. How far a statement moves a candidate is priced by
# its relation (REL_MULTIPLIER) and discounted by its confidence; a second,
# separately chosen number would be a producer grading its own evidence, and
# the ranking would stop being a function of what the rows ARE.
STATEMENT_WEIGHT = 1.0

# Recorded in Relevance.rationale so a link the partner derived is legible in
# lineage as derived, and is never mistaken for one a method computed from
# evidence. The kind it was derived from is appended.
BEARING_RATIONALE = "partner:bearing:kind"

# The envelope of a statement that bears on nothing. Named once so every
# producer writes the same absence, and so "unattached" is a value rather than
# two literals repeated at eight sites.
UNATTACHED: tuple[Relevance, RelationToCentralDecision] = (
    Relevance(None, 0.0), RelationToCentralDecision.UNKNOWN)


def _bound(bounds: Any, name: str):
    """A bound comes from Settings (ENGINE_*) or a mapping of BOUNDS names;
    the frozen default is the last resort so a bound can never be a literal
    in this module (dynamic-not-hardcoded)."""
    if isinstance(bounds, Mapping):
        return bounds.get(name, BOUNDS[name])
    return getattr(bounds, f"ENGINE_{name}")


def _live(view, kind: Kind | None = None) -> list[Entity]:
    # Written against the RegistryView protocol (query + status), not the
    # concrete registry's live(), so a ScopedView serves equally.
    return [e for e in view.query(kind) if e.status not in TERMINAL_STATUSES]


def effective_confidence(e: Entity) -> float:
    """Unknown confidence is not zero confidence: treating None as 0 would let
    absent evidence condemn a candidate (owner constraint). The prior feeds
    the arithmetic only; the stored value stays None."""
    v = e.confidence.value
    return UNKNOWN_CONFIDENCE_PRIOR if v is None else float(v)


def candidate_decisions(view) -> list[Entity]:
    """Live DECISION rows in the running for central: the stated request, an
    already-central decision, and every partner-inferred candidate."""
    out = []
    for d in _live(view, Kind.DECISION):
        p = d.payload
        if p.role in (DecisionRole.CENTRAL, DecisionRole.STATED_REQUEST) or p.origin == PARTNER_INFERRED:
            out.append(d)
    return out


def stated_request(view) -> Entity | None:
    for d in _live(view, Kind.DECISION):
        if d.payload.role == DecisionRole.STATED_REQUEST:
            return d
    return None


def bearing_relation(kind: Kind, payload: Any = None) -> RelationToCentralDecision:
    """How a statement of this kind stands to the decision it was made under.

    A kind (or a fact basis) the tables do not name returns UNKNOWN, which is
    zero in the score. That is absence, not a verdict: nothing here decides
    that a row is irrelevant, only that nothing has been derived for it.
    """
    if kind is Kind.FACT:
        return BEARING_BY_FACT_BASIS.get(getattr(payload, "basis", None),
                                         RelationToCentralDecision.UNKNOWN)
    return BEARING_BY_KIND.get(kind, RelationToCentralDecision.UNKNOWN)


def bearing_decision(view) -> Entity | None:
    """The decision a statement made now bears on: the CENTRAL decision once
    the engagement has one, else the request the client stated.

    Read from the registry alone. No candidate id is ever rendered into an
    extraction prompt, so the model cannot choose which candidate a piece of
    evidence counts for; and no ordering, hash or tie-break picks one, so a
    registry with no stated request attaches nothing rather than guessing.
    """
    central = view.central_decision()
    if central is not None:
        return central
    return stated_request(view)


def bearing(view, kind: Kind, payload: Any = None) -> tuple[Relevance, RelationToCentralDecision]:
    """The (relevance, relation) envelope a statement of this kind is born
    with: what it bears on, and how.

    Both halves or neither. A relation without a decision would arm the gates
    that read relation structurally (charter situation, materiality, question
    sensitivity) on a decision nobody has stated; a decision without a relation
    would score zero anyway. When either is missing the row is born UNATTACHED,
    checked with `is None` and an explicit UNKNOWN comparison so an absent link
    stays absent rather than reading as a weak one.
    """
    relation = bearing_relation(kind, payload)
    if relation is RelationToCentralDecision.UNKNOWN:
        return UNATTACHED
    decision = bearing_decision(view)
    if decision is None:
        return UNATTACHED
    return (Relevance(decision.id, STATEMENT_WEIGHT, f"{BEARING_RATIONALE}:{kind.value}"),
            relation)


def hypothesis_scores(view) -> dict[str, float]:
    """Raw score per candidate id, from the registry alone. A candidate never
    votes for itself; everything else that carries relevance to it does."""
    scores: dict[str, float] = {d.id: 0.0 for d in candidate_decisions(view)}
    for e in _live(view):
        did = e.relevance.decision_id
        if did is None or did not in scores or e.id == did:
            continue
        scores[did] += float(e.relevance.weight) * effective_confidence(e) * REL_MULTIPLIER.get(e.relation, 0.0)
    return scores


def hypothesis_weights(view) -> dict[str, float]:
    """Normalised weights. A registry with no relevant evidence yields all
    zeros: with nothing weighing on any candidate there is no ranking, not a
    uniform default."""
    scores = hypothesis_scores(view)
    total = sum(scores.values())
    if total <= 0.0:
        return {cid: 0.0 for cid in scores}
    return {cid: s / total for cid, s in scores.items()}


def ranked_candidates(view) -> list[tuple[Entity, float]]:
    """Candidates by weight, heaviest first; ties break on id so the order is
    a fact about the registry, never about dict iteration."""
    weights = hypothesis_weights(view)
    cands = candidate_decisions(view)
    return sorted(((d, weights.get(d.id, 0.0)) for d in cands), key=lambda t: (-t[1], t[0].id))


# ---------------------------------------------------------------------------
# revise_hypothesis.j2 - the model may ADD candidates and causal links, only
# ---------------------------------------------------------------------------

class _NewCandidate(BaseModel):
    text: str
    rationale: str = ""
    rationale_ids: list[str] = Field(default_factory=list)


class _CausalLink(BaseModel):
    issue_id: str
    cause_id: str
    support_ids: list[str] = Field(default_factory=list)
    text: str = ""


class HypothesisRevision(BaseModel):
    new_candidates: list[_NewCandidate] = Field(default_factory=list)
    causal_links: list[_CausalLink] = Field(default_factory=list)


_TEXT_ATTRS = ("text", "statement", "name")


def _display_text(e: Entity) -> str | None:
    for attr in _TEXT_ATTRS:
        v = getattr(e.payload, attr, None)
        if v:
            return str(v)
    return None


def revise_hypothesis(registry, provider: ModelProvider, *, model: str | None = None) -> list[Entity]:
    """One model pass over the live registry. Returns the rows it added.

    The function emits Add deltas only - never Supersede, never SetStatus -
    because the model may propose a candidate the client has not seen yet but
    may not retire one; removal is the registry's business, driven by the
    client (design 6.4). A candidate whose rationale cites no registered
    entity is discarded: a decision nothing on the record supports is an
    invention, not an inference. A StructuredFailure propagates; the caller
    (the partner loop) records the blocked step rather than defaulting."""
    cands = candidate_decisions(registry)
    ctx_candidates = [{"id": d.id, "role": d.payload.role.value, "text": d.payload.statement} for d in cands]
    ctx_entities = []
    for e in _live(registry):
        if e.kind == Kind.DECISION:
            continue
        text = _display_text(e)
        if text:
            ctx_entities.append({"id": e.id, "kind": e.kind.value, "text": text})
    prompt = templating.render("revise_hypothesis.j2", candidates=ctx_candidates, entities=ctx_entities)
    call = ModelCall(purpose=REVISE_PURPOSE, messages=({"role": "user", "content": prompt},),
                     model=model, schema=HypothesisRevision, engagement_id=registry.engagement_id)
    parsed, response = structured_call(provider, call)

    known = {e.id for e in _live(registry)}
    existing_texts = {d.payload.statement for d in cands}
    deltas: list[Add] = []
    for c in parsed.new_candidates:
        ids = tuple(dict.fromkeys(c.rationale_ids))
        if not ids or any(i not in known for i in ids) or c.text in existing_texts:
            continue
        existing_texts.add(c.text)
        deltas.append(Add(make_entity(
            kind=Kind.DECISION, engagement_id=registry.engagement_id,
            payload=DecisionPayload(statement=c.text, role=DecisionRole.SUBORDINATE, origin=PARTNER_INFERRED),
            provenance=Provenance(actor=Actor.PARTNER, actor_ref="partner:revise_hypothesis",
                                  derived_from=ids, model_call_id=response.call_id),
            # The model's belief in its own candidate is not a number it may
            # report; unknown stays None in storage and the ranking applies
            # the declared prior at read time.
            confidence=Confidence(None, "model_estimate"),
            relevance=Relevance(None), relation=RelationToCentralDecision.UNKNOWN,
            status=Status.PROPOSED)))
    # The causal links this engagement already holds, as (issue, cause) pairs.
    # A hypothesis is a claim that one thing causes another, so the SAME claim
    # arriving on a later turn is the same hypothesis, not a second one: the
    # model is shown the whole live registry every pass and re-proposes what it
    # proposed before. Without this the row count grows with the number of
    # turns rather than with what was found, and an engagement ends up holding
    # hundreds of copies of a handful of claims - which is production standing
    # in for analysis, and it makes every count over hypotheses meaningless.
    registered = {(h.payload.issue_id, cause)
                  for h in registry.live(Kind.HYPOTHESIS)
                  for cause in (h.payload.causes or ())}
    for link in parsed.causal_links:
        cited = (link.issue_id, link.cause_id, *link.support_ids)
        if not link.support_ids or not link.text.strip() or any(i not in known for i in cited):
            continue
        if (link.issue_id, link.cause_id) in registered:
            continue
        registered.add((link.issue_id, link.cause_id))
        deltas.append(Add(make_entity(
            kind=Kind.HYPOTHESIS, engagement_id=registry.engagement_id,
            payload=HypothesisPayload(text=link.text, issue_id=link.issue_id, causes=(link.cause_id,)),
            provenance=Provenance(actor=Actor.PARTNER, actor_ref="partner:revise_hypothesis",
                                  derived_from=tuple(dict.fromkeys(cited)), model_call_id=response.call_id),
            confidence=Confidence(None, "model_estimate"),
            relevance=Relevance(None), relation=RelationToCentralDecision.INFORMS,
            status=Status.PROPOSED)))
    return registry.apply_all(deltas)


# ---------------------------------------------------------------------------
# Symptom vs problem
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Reframe:
    """What the reply's reframe block renders from: the entities, not prose."""
    stated_id: str
    inferred_id: str
    hypothesis_ids: tuple[str, ...]
    decision_required_id: str


def _under(e: Entity, decision_id: str) -> bool:
    """Whether an entity sits under a decision: its relevance points there, or
    (for issue nodes) the decision is among what it is decisive for."""
    if e.relevance.decision_id == decision_id:
        return True
    return decision_id in tuple(getattr(e.payload, "decisive_for", ()) or ())


def causal_chain(view, stated_id: str, inferred_id: str) -> tuple[str, ...]:
    """Ids of live HYPOTHESIS rows linking an issue under the stated request
    to a cause under the inferred candidate - the evidence that the request
    is a symptom, not merely the lighter candidate."""
    out: list[str] = []
    for h in _live(view, Kind.HYPOTHESIS):
        issue = view.get(h.payload.issue_id)
        if issue is None or not _under(issue, stated_id):
            continue
        for cid in h.payload.causes:
            cause = view.get(cid)
            if cause is not None and _under(cause, inferred_id):
                out.append(h.id)
                break
    return tuple(out)


def _scope_rows(view) -> list[Entity]:
    return [e for e in _live(view, Kind.DECISION_REQUIRED) if SCOPE_CONFIRMATION_LABEL in e.labels]


def open_scope_decision(view) -> Entity | None:
    for e in _scope_rows(view):
        if e.status == Status.OPEN:
            return e
    return None


def maybe_reframe(registry, bounds) -> Reframe | None:
    """Apply the symptom-vs-problem rule once. Returns the Reframe applied, or
    None when the rule does not fire. Idempotent: a stated request already
    marked, or a scope confirmation already put to the client (open or
    resolved), is never reframed again - re-asking would overrule the client.
    """
    stated = stated_request(registry)
    if stated is None or stated.payload.symptom_of is not None:
        return None
    if _scope_rows(registry):
        return None
    weights = hypothesis_weights(registry)
    inferred_cands = [d for d in candidate_decisions(registry)
                      if d.payload.origin == PARTNER_INFERRED and d.id != stated.id]
    if not inferred_cands:
        return None
    inferred = max(inferred_cands, key=lambda d: (weights.get(d.id, 0.0), d.id))
    # The margin is the law: a near-tie reflects which evidence happened to
    # arrive first, not a diagnosis, and reframing on one would churn the
    # engagement's scope every turn.
    gap = weights.get(inferred.id, 0.0) - weights.get(stated.id, 0.0)
    margin = float(_bound(bounds, "SYMPTOM_MARGIN"))
    if gap < margin:
        return None
    # Dominant weight without a causal path is a hint, not a finding: the
    # reframe needs a HYPOTHESIS tying an issue under the stated request to a
    # cause under the inferred candidate (design 6.4), or the "symptom" claim
    # would rest on arithmetic alone.
    chain = causal_chain(registry, stated.id, inferred.id)
    if not chain:
        return None
    replacement = make_entity(
        kind=Kind.DECISION, engagement_id=stated.engagement_id,
        payload=replace(stated.payload, symptom_of=inferred.id),
        provenance=Provenance(actor=Actor.PARTNER, actor_ref="partner:hypothesis",
                              derived_from=tuple(dict.fromkeys(
                                  (*stated.provenance.derived_from, inferred.id, *chain))),
                              source_locator=stated.provenance.source_locator),
        confidence=stated.confidence, relevance=stated.relevance, relation=stated.relation,
        status=stated.status, entity_id=stated.id, labels=stated.labels)
    decision_required = make_entity(
        kind=Kind.DECISION_REQUIRED, engagement_id=stated.engagement_id,
        payload=DecisionRequiredPayload(text=CONFIRM_SCOPE_TEXT, from_authority=Authority.CLIENT,
                                        decision_id=inferred.id, options=(stated.id, inferred.id)),
        provenance=Provenance(actor=Actor.PARTNER, actor_ref="partner:hypothesis",
                              derived_from=tuple(dict.fromkeys((stated.id, inferred.id, *chain)))),
        confidence=Confidence(None), relevance=Relevance(inferred.id, 0.0),
        relation=RelationToCentralDecision.DEFINES, status=Status.OPEN,
        labels=(SCOPE_CONFIRMATION_LABEL,))
    rows = registry.apply_all([Supersede(stated.id, replacement), Add(decision_required)])
    return Reframe(stated_id=stated.id, inferred_id=inferred.id,
                   hypothesis_ids=chain, decision_required_id=rows[1].id)


# ---------------------------------------------------------------------------
# What the charter may name, and when it is ready
# ---------------------------------------------------------------------------

def central_decision_for_charter(view) -> Entity | None:
    """The DECISION the charter names as central right now. While the scope
    confirmation is OPEN the answer is the stated request: naming the
    inferred decision before the client resolved it would be a silent
    substitution of scope (design 6.4)."""
    central = view.central_decision()
    if central is not None:
        return central
    ranked = ranked_candidates(view)
    if not ranked:
        return None
    top = ranked[0][0]
    dr = open_scope_decision(view)
    if dr is not None and dr.payload.decision_id == top.id:
        return stated_request(view)
    return top


def _open_pin_question_on_defining_fact(view) -> bool:
    """An OPEN dimension-pin question on a DEFINES fact blocks the confident
    path: a charter built on a figure whose currency or period is unpinned
    would restate a number nobody has actually stated. Checked structurally
    (label + the cited fact's relation), never by wording."""
    for q in _live(view, Kind.QUESTION):
        if q.status != Status.OPEN or PIN_DIMENSION_LABEL not in q.labels:
            continue
        for sid in q.provenance.derived_from:
            f = view.get(sid)
            if f is not None and f.kind == Kind.FACT and f.relation == RelationToCentralDecision.DEFINES:
                return True
    return False


def charter_ready(view, bounds, *, top_gap_value: float | None = None) -> bool:
    """Design 6.6. Ready when the ranking is confident (top weight and margin
    over the bounds) or the client already chose via a resolved scope
    confirmation - unless an OPEN dimension-pin question on a defining fact
    stands; OR (ASK_FLOOR, S4) when everything left to ask is worth less than
    ASK_FLOOR while a candidate and an owner exist, because holding the
    charter for questions that cannot move it is stalling, not diligence."""
    cands = candidate_decisions(view)
    owners = _live(view, Kind.DECISION_OWNER)
    if not cands or not owners:
        return False
    ranked = ranked_candidates(view)
    top_w = ranked[0][1]
    second_w = ranked[1][1] if len(ranked) > 1 else 0.0
    confident = (top_w >= float(_bound(bounds, "CHARTER_MIN_WEIGHT"))
                 and (top_w - second_w) >= float(_bound(bounds, "CHARTER_MIN_MARGIN")))
    chosen = any(e.status == Status.RESOLVED for e in _scope_rows(view))
    if (confident or chosen) and not _open_pin_question_on_defining_fact(view):
        return True
    if top_gap_value is not None and float(top_gap_value) < float(_bound(bounds, "ASK_FLOOR")):
        return True
    return False


__all__ = [n for n in dir() if not n.startswith("_")]
