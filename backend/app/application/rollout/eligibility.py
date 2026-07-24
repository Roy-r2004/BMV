"""Deterministic, advisory-only promotion eligibility for Phase 7A."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.application.rollout.authorization import (
    actor_has_permission,
    evaluate_separation_of_duties,
)
from app.application.rollout.targeting import compute_sticky_bucket
from app.domain.schemas.rollout import (
    BreakerState,
    PromotionEligibilityResult,
    RolloutPolicyView,
    SeparationOfDutiesResult,
    TrustedRolloutActor,
)


@dataclass(frozen=True)
class EligibilityInputs:
    request_id: int
    candidate_revision_id: int | None
    requested_tier: int
    effective_tier_summary_id: int | None
    highest_accepted_tier: int
    phase4_status: str
    phase5_status: str
    lineage_ok: bool
    manifest_ok: bool
    policy: RolloutPolicyView
    circuit_breaker_state: BreakerState
    actor: TrustedRolloutActor
    requester_actor_id: str | None = None
    approver_actor_id: str | None = None
    dual_role_allowed: bool = False
    ticket_ref: str | None = None


def _hash_eligibility(payload: dict) -> str:
    material = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def compute_promotion_eligibility(inputs: EligibilityInputs) -> PromotionEligibilityResult:
    """Recompute eligibility from current state. Never persists a write token."""
    policy = inputs.policy
    sticky = compute_sticky_bucket(
        salt=policy.rollout_salt,
        request_id=inputs.request_id,
        rollout_percent=policy.rollout_percent,
    )
    allowlisted = inputs.request_id in set(policy.allowlist)
    percent_eligible = sticky.percent_eligible or allowlisted

    sod = evaluate_separation_of_duties(
        requester_actor_id=inputs.requester_actor_id or inputs.actor.actor_id,
        approver_actor_id=inputs.approver_actor_id,
        dual_role_allowed=inputs.dual_role_allowed,
        ticket_ref=inputs.ticket_ref,
    )

    reasons: list[str] = []
    if not policy.master_enabled:
        reasons.append("master_disabled")
    if not inputs.lineage_ok:
        reasons.append("lineage_invalid")
    if not inputs.manifest_ok:
        reasons.append("manifest_invalid")
    if inputs.phase4_status != "candidate_runtime_validated":
        reasons.append("phase4_not_validated")
    if inputs.phase5_status != "candidate_visual_accepted":
        reasons.append("phase5_not_accepted")
    if inputs.requested_tier > inputs.highest_accepted_tier:
        reasons.append("requested_tier_above_accepted")
    if not percent_eligible:
        reasons.append("outside_allowlist_and_percent")
    if inputs.circuit_breaker_state == "open":
        reasons.append("circuit_breaker_open")

    actor_authorized_shadow = actor_has_permission(
        inputs.actor, "compute_shadow_eligibility"
    )
    actor_authorized_promote = actor_has_permission(
        inputs.actor, "compute_promotion_eligibility"
    )
    if not actor_authorized_promote and not actor_authorized_shadow:
        reasons.append("actor_unauthorized")

    eligible_for_shadow = (
        policy.master_enabled
        and policy.shadow_enabled
        and actor_authorized_shadow
        and "master_disabled" not in reasons
        and "actor_unauthorized" not in reasons
    )
    # Promote eligibility is advisory only — never authorizes a write in 7A.
    eligible_for_promote = (
        policy.master_enabled
        and policy.promote_enabled
        and actor_authorized_promote
        and sod.satisfied
        and not reasons
    )
    if policy.promote_enabled and not sod.satisfied:
        reasons.append("separation_of_duties_unsatisfied")
        eligible_for_promote = False
    if not policy.promote_enabled:
        reasons.append("promote_disabled")
        eligible_for_promote = False

    # Recompute clean reason list for hash stability (ordered unique).
    uniq_reasons = tuple(dict.fromkeys(reasons))

    base = {
        "schema_version": "1.0",
        "request_id": inputs.request_id,
        "candidate_revision_id": inputs.candidate_revision_id,
        "requested_tier": inputs.requested_tier,
        "effective_tier_summary_id": inputs.effective_tier_summary_id,
        "highest_accepted_tier": inputs.highest_accepted_tier,
        "phase4_status": inputs.phase4_status,
        "phase5_status": inputs.phase5_status,
        "lineage_ok": inputs.lineage_ok,
        "manifest_ok": inputs.manifest_ok,
        "policy_revision": policy.policy_revision,
        "configuration_sha256": policy.configuration_sha256,
        "master_enabled": policy.master_enabled,
        "shadow_enabled": policy.shadow_enabled,
        "promote_enabled": policy.promote_enabled,
        "allowlisted": allowlisted,
        "sticky_bucket": sticky.bucket,
        "rollout_percent": policy.rollout_percent,
        "percent_eligible": sticky.percent_eligible,
        "circuit_breaker_state": inputs.circuit_breaker_state,
        "actor_id": inputs.actor.actor_id,
        "actor_roles": list(inputs.actor.roles),
        "actor_authorized": actor_authorized_promote or actor_authorized_shadow,
        "separation_of_duties": sod.model_dump(mode="json"),
        "eligible_for_shadow": eligible_for_shadow,
        "eligible_for_promote": eligible_for_promote,
        "advisory_only": True,
        "rejection_reasons": list(uniq_reasons),
    }
    digest = _hash_eligibility(base)

    return PromotionEligibilityResult(
        request_id=inputs.request_id,
        candidate_revision_id=inputs.candidate_revision_id,
        requested_tier=inputs.requested_tier,
        effective_tier_summary_id=inputs.effective_tier_summary_id,
        highest_accepted_tier=inputs.highest_accepted_tier,
        phase4_status=inputs.phase4_status,
        phase5_status=inputs.phase5_status,
        lineage_ok=inputs.lineage_ok,
        manifest_ok=inputs.manifest_ok,
        policy_revision=policy.policy_revision,
        master_enabled=policy.master_enabled,
        shadow_enabled=policy.shadow_enabled,
        promote_enabled=policy.promote_enabled,
        allowlisted=allowlisted,
        sticky_bucket=sticky.bucket,
        rollout_percent=policy.rollout_percent,
        percent_eligible=sticky.percent_eligible,
        circuit_breaker_state=inputs.circuit_breaker_state,
        actor_id=inputs.actor.actor_id,
        actor_roles=inputs.actor.roles,
        actor_authorized=actor_authorized_promote or actor_authorized_shadow,
        separation_of_duties=sod,
        eligible_for_shadow=eligible_for_shadow,
        eligible_for_promote=eligible_for_promote,
        advisory_only=True,
        rejection_reasons=uniq_reasons,
        eligibility_sha256=digest,
    )


def eligibility_authorizes_write(_result: PromotionEligibilityResult) -> bool:
    """Phase 7A invariant: eligibility never authorizes writes."""
    return False


__all__ = [
    "EligibilityInputs",
    "compute_promotion_eligibility",
    "eligibility_authorizes_write",
    "evaluate_separation_of_duties",
    "SeparationOfDutiesResult",
]
