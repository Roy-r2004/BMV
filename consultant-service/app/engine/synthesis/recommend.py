"""app/engine/synthesis/recommend.py - what a recommendation is allowed to be.

Spec section 7: every recommendation traces to evidence, an approved
assumption or a calculation. Two mechanisms, both queries over the live
support graph and never over prose:

- `support_findings()` lists every live recommendation that does not yet
  trace, one Finding per reason, reusing the registry's own
  `unsupported_recommendations()` so the gate (L2) and the approval path
  cannot drift apart. Nothing is waved through: no rule proves an unsupported
  recommendation sound, so it stays listed (the fallthrough spirit of
  app/pipeline/adjudicate.py:743).

- `refresh_conditional_on()` recomputes, each round, the OPEN material
  questions a recommendation's supports rest on, and supersedes the row when
  that list changes, so lineage shows when a recommendation became (or
  stopped being) conditional. The link is structural: a question raised FROM
  something in the support closure, or answered by something in it. An
  APPROVED recommendation is never rewritten here - it is the decision
  owner's row (APPROVAL_OWNER), and the engine records around it rather than
  editing it; the open question still blocks release through L5.

`approve_recommendation()` is the approval path: it refuses an unsupported
recommendation before writing, and the registry refuses it again at the door
(I3). Approving is not confirming (MF2.2): only DECISION_OWNER or CLIENT may
do it, which `may_advance` enforces through APPROVAL_OWNER.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from app.engine.registry import EngagementRegistry
from app.engine.types import (
    TERMINAL_STATUSES, Actor, Add, Authority, Confidence, DecisionRequiredPayload, Entity, Finding,
    Kind, Provenance, Severity, SetStatus, Status, Supersede, make_entity,
)

# gates/laws.py owns the LawId enum (contracts section 14); the id is spelled
# here so a finding raised at synthesis and one raised at the gate carry the
# same law name.
UNSUPPORTED_RECOMMENDATION_LAW = "L2.unsupported_recommendation"

_CONDITIONAL_REF = "synthesis:conditional_on"
_LICENSED_REF = "synthesis:licensed_advice"


class UnsupportedRecommendation(Exception):
    """Refused before writing: a recommendation that does not trace to a
    confirmed fact, an approved assumption or a calculation is never approved."""


def support_findings(registry: EngagementRegistry) -> list[Finding]:
    """One HIGH finding per live recommendation that does not trace, naming
    the support that is missing, superseded or not yet confirmed."""
    return [
        Finding(law=UNSUPPORTED_RECOMMENDATION_LAW, where=rec.id, issue=reason,
                fix="cite a confirmed fact, an approved assumption or a calculation, or withdraw it",
                severity=Severity.HIGH, entity_ids=(rec.id,), blocks_final=True)
        for rec, reason in registry.unsupported_recommendations()
    ]


def _closure(registry: EngagementRegistry, ids: Iterable[str]) -> set[str]:
    """Everything one recommendation rests on, transitively through
    `derived_from` and calculation `inputs` - the same walk
    EngagementRegistry.support_closure() makes over every recommendation at
    once, scoped here to one."""
    out: set[str] = set()
    frontier = list(ids)
    while frontier:
        i = frontier.pop()
        if i in out:
            continue
        out.add(i)
        e = registry.get(i)
        if e is not None:
            frontier.extend(e.provenance.derived_from)
            frontier.extend(getattr(e.payload, "inputs", ()) or ())
    return out


def conditional_on(registry: EngagementRegistry, recommendation: Entity) -> tuple[str, ...]:
    """The OPEN material questions this recommendation's supports depend on:
    a question raised from something in the closure, or one whose recorded
    answers are in it. Ordered by question id so the tuple is stable and a
    re-run supersedes nothing."""
    closure = _closure(registry, recommendation.payload.supports)
    hits = [
        q.id for q in registry.open_material_questions()
        if closure & (set(q.provenance.derived_from) | set(q.payload.answer_entity_ids))
    ]
    return tuple(sorted(set(hits)))


def refresh_conditional_on(registry: EngagementRegistry) -> list[Entity]:
    """Recompute `conditional_on` for every live, unapproved recommendation;
    supersede the ones whose list changed. A changed list is a Supersede so
    the change is visible in lineage, exactly as a changed materiality flag is."""
    out: list[Entity] = []
    for rec in registry.live(Kind.RECOMMENDATION):
        if rec.status is Status.APPROVED:
            continue
        wanted = conditional_on(registry, rec)
        if wanted == tuple(rec.payload.conditional_on):
            continue
        entity = replace(
            rec, payload=replace(rec.payload, conditional_on=wanted),
            provenance=replace(rec.provenance, actor=Actor.PARTNER, actor_ref=_CONDITIONAL_REF,
                               derived_from=tuple(dict.fromkeys(rec.provenance.derived_from + wanted))))
        out.append(registry.apply(Supersede(rec.id, entity)))
    return out


def withdraw_licensed_advice(registry: EngagementRegistry) -> list[Entity]:
    """Retire every recommendation the regulated screen flagged, and put the
    matter to the adviser it was routed to instead (L4's own fix).

    The screen identifies and routes; it does not decide what the engagement
    then says, which is why this act is here and not there. A recommendation
    carrying `licensed_interpretation` is advice a licensed professional must
    give, so leaving it LIVE means the engine is still giving it - the
    condition L4 reports as blocking and the failure design 9.6 calls the
    dangerous direction. The row is WITHDRAWN by the SYSTEM that wrote the
    flagged row (I1 admits a withdrawal by the row's own actor), and what it
    asked becomes a DECISION_REQUIRED from the QUALIFIED_PROFESSIONAL, citing
    the matters. Nothing is deleted and nothing is paraphrased: the withheld
    wording is on the REGULATED_MATTER, and the lineage says who withheld it.
    """
    out: list[Entity] = []
    for rec in registry.licensed_recommendations():
        matters = [m for m in registry.query(Kind.REGULATED_MATTER)
                   if rec.id in m.payload.touches and m.status not in TERMINAL_STATUSES]
        if not matters:
            # The flag is on the row but no matter names it: the record does
            # not say what licence is needed, so the engine has nothing to put
            # to an adviser. Left for L4 to report rather than guessed at.
            continue
        advisers = ", ".join(dict.fromkeys(m.payload.adviser_class for m in matters))
        matter_ids = tuple(m.id for m in matters)
        payload = DecisionRequiredPayload(
            text=(f"{rec.payload.statement} - this is advice a {advisers} must give; the "
                  f"engagement recorded the matter and did not state it"),
            from_authority=Authority.QUALIFIED_PROFESSIONAL,
            decision_id=rec.payload.decision_id,
            options=matter_ids)
        asked = registry.apply(Add(make_entity(
            kind=Kind.DECISION_REQUIRED, engagement_id=registry.engagement_id, payload=payload,
            provenance=Provenance(actor=Actor.SYSTEM, actor_ref=_LICENSED_REF,
                                  derived_from=(rec.id,) + matter_ids),
            confidence=Confidence(None), relevance=rec.relevance, relation=rec.relation,
            status=Status.OPEN)))
        registry.apply(SetStatus(rec.id, Status.WITHDRAWN,
                                 by=Provenance(actor=rec.provenance.actor,
                                               actor_ref=_LICENSED_REF,
                                               derived_from=(asked.id,))))
        out.append(asked)
    return out


def approve_recommendation(registry: EngagementRegistry, recommendation_id: str, *,
                           actor: Actor, actor_ref: str) -> Entity:
    """Approve a recommendation. Refuses an unsupported one here, and the
    registry refuses it again (I3) and checks the actor against
    APPROVAL_OWNER (I1): approving is the decision owner's or the client's act."""
    rec = registry.get(recommendation_id)
    if rec is None or rec.kind is not Kind.RECOMMENDATION:
        raise UnsupportedRecommendation(f"{recommendation_id} is not a recommendation")
    if rec.status in TERMINAL_STATUSES:
        raise UnsupportedRecommendation(f"{recommendation_id} is {rec.status.value}")
    reasons = [why for r, why in registry.unsupported_recommendations() if r.id == rec.id]
    if reasons:
        raise UnsupportedRecommendation(f"{recommendation_id} does not trace to evidence: {'; '.join(reasons)}")
    return registry.apply(SetStatus(rec.id, Status.APPROVED, Provenance(actor=actor, actor_ref=actor_ref)))


__all__ = [
    "UNSUPPORTED_RECOMMENDATION_LAW", "UnsupportedRecommendation", "approve_recommendation",
    "conditional_on", "refresh_conditional_on", "support_findings", "withdraw_licensed_advice",
]
