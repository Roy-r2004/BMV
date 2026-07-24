"""Shadow-specific advisory eligibility — never authorizes promotion."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.application.rollout.authorization import actor_has_permission
from app.application.rollout.targeting import compute_sticky_bucket
from app.domain.schemas.rollout import (
    BreakerState,
    RolloutPolicyView,
    TrustedRolloutActor,
)
from app.domain.schemas.shadow_evaluation import ShadowEligibilityResult, ShadowMode


@dataclass(frozen=True)
class ShadowEligibilityInputs:
    request_id: int
    actor: TrustedRolloutActor
    policy: RolloutPolicyView
    selected_mode: ShadowMode
    configuration_valid: bool
    master_enabled: bool
    shadow_enabled: bool
    accepted_lineage_available: bool
    served_target_kind: str
    served_pointer_version: int | None
    circuit_breaker_state: BreakerState = "disabled"


def compute_shadow_eligibility(
    inputs: ShadowEligibilityInputs,
) -> ShadowEligibilityResult:
    sticky = compute_sticky_bucket(
        salt=inputs.policy.rollout_salt,
        request_id=inputs.request_id,
        rollout_percent=inputs.policy.rollout_percent,
    )
    allowlisted = inputs.request_id in set(inputs.policy.allowlist)
    percent_eligible = sticky.percent_eligible or allowlisted
    actor_authorized = actor_has_permission(inputs.actor, "start_shadow_evaluation")
    reasons: list[str] = []
    if not inputs.configuration_valid:
        reasons.append("configuration_invalid")
    if not inputs.master_enabled:
        reasons.append("master_disabled")
    if not inputs.shadow_enabled:
        reasons.append("shadow_disabled")
    if not actor_authorized:
        reasons.append("actor_unauthorized")
    if not percent_eligible:
        reasons.append("outside_allowlist_and_percent")
    if inputs.selected_mode == "regenerate_live":
        reasons.append("regenerate_live_not_approved")
    if inputs.selected_mode not in ("reuse_accepted", "regenerate_fixture", "regenerate_live"):
        reasons.append("invalid_mode")
    if (
        inputs.selected_mode == "reuse_accepted"
        and not inputs.accepted_lineage_available
    ):
        # Eligibility can still be computed; execution fails cleanly later.
        reasons.append("accepted_lineage_unavailable")

    eligible = (
        inputs.configuration_valid
        and inputs.master_enabled
        and inputs.shadow_enabled
        and actor_authorized
        and percent_eligible
        and inputs.selected_mode in ("reuse_accepted", "regenerate_fixture")
        and (
            inputs.selected_mode != "reuse_accepted"
            or inputs.accepted_lineage_available
        )
    )
    # Fixture mode may run without accepted lineage (synthetic).
    if inputs.selected_mode == "regenerate_fixture":
        eligible = (
            inputs.configuration_valid
            and inputs.master_enabled
            and inputs.shadow_enabled
            and actor_authorized
            and percent_eligible
        )
        reasons = [r for r in reasons if r != "accepted_lineage_unavailable"]

    payload = {
        "schema_version": "1.0",
        "request_id": inputs.request_id,
        "actor_id": inputs.actor.actor_id,
        "actor_roles": list(inputs.actor.roles),
        "policy_revision": inputs.policy.policy_revision,
        "configuration_sha256": inputs.policy.configuration_sha256,
        "allowlisted": allowlisted,
        "sticky_bucket": sticky.bucket,
        "rollout_percent": inputs.policy.rollout_percent,
        "percent_eligible": sticky.percent_eligible,
        "selected_mode": inputs.selected_mode,
        "accepted_lineage_available": inputs.accepted_lineage_available,
        "served_target_kind": inputs.served_target_kind,
        "served_pointer_version": inputs.served_pointer_version,
        "configuration_valid": inputs.configuration_valid,
        "master_enabled": inputs.master_enabled,
        "shadow_enabled": inputs.shadow_enabled,
        "circuit_breaker_state": inputs.circuit_breaker_state,
        "actor_authorized": actor_authorized,
        "eligible_for_shadow": eligible,
        "advisory_only": True,
        "cannot_authorize_promotion": True,
        "rejection_reasons": list(dict.fromkeys(reasons)),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ShadowEligibilityResult(
        request_id=inputs.request_id,
        actor_id=inputs.actor.actor_id,
        actor_roles=inputs.actor.roles,
        policy_revision=inputs.policy.policy_revision,
        allowlisted=allowlisted,
        sticky_bucket=sticky.bucket,
        rollout_percent=inputs.policy.rollout_percent,
        percent_eligible=sticky.percent_eligible,
        selected_mode=inputs.selected_mode,
        accepted_lineage_available=inputs.accepted_lineage_available,
        served_target_kind=inputs.served_target_kind,  # type: ignore[arg-type]
        served_pointer_version=inputs.served_pointer_version,
        configuration_valid=inputs.configuration_valid,
        master_enabled=inputs.master_enabled,
        shadow_enabled=inputs.shadow_enabled,
        circuit_breaker_state=inputs.circuit_breaker_state,
        actor_authorized=actor_authorized,
        eligible_for_shadow=eligible,
        advisory_only=True,
        cannot_authorize_promotion=True,
        rejection_reasons=tuple(dict.fromkeys(reasons)),
        eligibility_sha256=digest,
    )


def shadow_eligibility_authorizes_promotion(_result: ShadowEligibilityResult) -> bool:
    return False


__all__ = [
    "ShadowEligibilityInputs",
    "compute_shadow_eligibility",
    "shadow_eligibility_authorizes_promotion",
]
