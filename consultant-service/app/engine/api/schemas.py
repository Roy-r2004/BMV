"""What the client may send, and what the engagement says back (design 16.2).

Two laws live in this module rather than in the router, because they are
properties of the vocabulary rather than of any one endpoint:

S1  An actor class is a closed literal. `acting_as` cannot name an actor the
    type system does not have, so a body can never invent an authority; the
    router still refuses the classes the caller's credential does not support
    (design 5.3 - the credential decides, the body only asks).
S2  Nothing here stores a summary. `entity_out` serialises one row through
    `Entity.to_json` (the same encoder persistence uses, so what the API
    shows and what the database holds cannot diverge), and the live summary
    is read from the registry on every response. A cached picture of an
    engagement is a picture the next row makes false with nothing saying so.
"""
from __future__ import annotations

from typing import Any, Literal, Sequence

from pydantic import BaseModel, Field

# The three classes a caller may ask to act as. CLIENT is the default because
# the signed-in owner is the client; the other two are claims the router has
# to see a credential (or a recorded DECISION_OWNER row) for.
ActingAs = Literal["client", "decision_owner", "qualified_professional"]

# One item's verdict on the charter (design 6.6): confirm what is right,
# correct what is not, reject what does not belong. Silence is not a verdict.
Verdict = Literal["confirm", "correct", "reject"]


class ActorClaim(BaseModel):
    """The delegation a body may claim. `on_behalf_of` is the DECISION_OWNER
    entity id the caller acts for and `adviser` the qualified professional's
    identity string: both end up in `Provenance.actor_ref`, so delegation is
    a recorded fact and never an assumption (design 5.3)."""

    acting_as: ActingAs = "client"
    on_behalf_of: str | None = None
    adviser: str | None = None


class ResolveRequest(ActorClaim):
    """Settling a CONFLICT or a DECISION_REQUIRED. `chosen_entity_id` is None
    when the caller settles it without picking one of the conclusions."""

    chosen_entity_id: str | None = None
    rationale: str = ""


class ApprovalRequest(ActorClaim):
    """Approving or rejecting an ASSUMPTION."""

    rationale: str = ""


class CharterItemVerdict(BaseModel):
    entity_id: str
    verdict: Verdict
    # The client's own words for a correction. Required by the router for
    # `correct`, because a correction with no text is not a correction.
    text: str | None = None


class CharterConfirmRequest(BaseModel):
    charter_id: str
    items: list[CharterItemVerdict] = Field(default_factory=list)


class AnswerItem(BaseModel):
    question_id: str
    text: str = ""
    # "I do not know" is an answer (design 6.5): it is recorded on the
    # question so the gap becomes RECORD_UNKNOWN and is never re-asked.
    unknown: bool = False


class AnswersRequest(BaseModel):
    answers: list[AnswerItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Serialisers. Functions, not response_models: a registry row is a typed union
# of 41 payloads, and a pydantic mirror of it would be a second schema to keep
# in step with types.py.
# ---------------------------------------------------------------------------

def entity_out(e: Any) -> dict:
    """One row exactly as the registry holds it. `Entity.to_json` is the same
    encoder the store writes rows with, so the API cannot show a shape the
    database does not hold."""
    return e.to_json()


def entities_out(entities: Sequence[Any]) -> list[dict]:
    return [entity_out(e) for e in entities]


def item_out(item: Any) -> dict:
    """One charter/playback line: the entity's own words, the locator they
    came from, and whether this one is the client's to confirm."""
    return {
        "entity_id": item.entity_id,
        "kind": item.kind.value,
        "text": item.text,
        "locator": item.locator,
        "authority": item.authority.value,
        "status": item.status.value,
        "confirmable": item.confirmable,
        "section": item.section,
    }


def reply_out(reply: Any) -> dict:
    """The PartnerReply the client reads. `live_summary` is a property on the
    reply and is read here, once, at serialisation time (S2)."""
    charter = reply.charter
    reframe = reply.reframe
    return {
        "phase": reply.phase.value,
        "turn_n": reply.turn_n,
        "turn_id": reply.turn_id,
        "understanding": [item_out(i) for i in reply.understanding],
        "reframe": None if reframe is None else {
            "stated_id": reframe.stated_id,
            "inferred_id": reframe.inferred_id,
            "hypothesis_ids": list(reframe.hypothesis_ids),
            "decision_required_id": reframe.decision_required_id,
        },
        "questions": entities_out(reply.questions),
        "evidence_requests": entities_out(reply.evidence_requests),
        "charter": None if charter is None else {
            "charter_id": charter.charter.id,
            "items": [item_out(i) for i in charter.items],
            "planned_analyses": [a.id for a in charter.planned_analyses],
            "work_products": list(charter.work_products),
            "amends": charter.amends,
            "refusals": list(charter.refusals),
        },
        "regulated": entities_out(reply.regulated),
        "ran": [{"method_id": m, "issue_id": i} for m, i in reply.ran],
        "refusals": list(reply.refusals),
        "live_summary": reply.live_summary,
    }


def analysis_out(run: Any) -> dict:
    """What one background analysis pass did, in ids."""
    return {
        "phase": run.phase.value,
        "rounds": run.rounds,
        "ran": [{"method_id": m, "issue_id": i} for m, i in run.ran],
        "assignments": list(run.assignments),
        "conflicts": list(run.conflicts),
        "paused_on": list(run.paused_on),
        "amendment": None if run.amendment is None else run.amendment.id,
        "findings": [f.as_dict() for f in run.findings],
        "refusals": list(run.refusals),
    }


def progress_out(row: Any, *, elapsed_s: int) -> dict:
    """requests.get_progress's shape (app/routers/requests.py:302), with the
    engine's own name for the flag: an engagement WORKS, a request GENERATES.
    `elapsed_s` is computed on the server because created_at is a naive
    utcnow() a browser would read as local time."""
    return {
        "review_status": row.review_status,
        "client_name": row.client_name,
        "title": row.title,
        "phase": row.phase,
        "stage": row.stage,
        "label": row.stage_label,
        "pct": row.progress_pct,
        "detail": row.progress_detail,
        "is_working": bool(row.is_working),
        "is_failed": bool(row.is_failed),
        "status": row.status,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "elapsed_s": elapsed_s,
    }


def card_out(row: Any) -> dict:
    """One line of /mine or /review-queue."""
    return {
        "id": row.public_id,
        "public_id": row.public_id,
        "client_name": row.client_name,
        "title": row.title,
        "phase": row.phase,
        "status": row.status,
        "is_working": bool(row.is_working),
        "review_status": row.review_status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


__all__ = [
    "ActingAs", "ActorClaim", "AnswerItem", "AnswersRequest", "ApprovalRequest",
    "CharterConfirmRequest", "CharterItemVerdict", "ResolveRequest", "Verdict",
    "analysis_out", "card_out", "entities_out", "entity_out", "item_out", "progress_out",
    "reply_out",
]
