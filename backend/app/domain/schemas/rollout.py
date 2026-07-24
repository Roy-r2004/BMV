"""Strict Phase 7A rollout control-plane contracts.

Phase 7A defines schemas and advisory computation only. Eligibility never
authorizes writes. Applied promotions and pointer mutations are forbidden on
production application services.
"""
from __future__ import annotations

from typing import Annotated, Literal, Tuple

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StringConstraints, field_validator, model_validator

from app.domain.schemas.design_contract import Sha256, StrictDesignModel


ROLLOUT_SCHEMA_VERSION = "1.0"
PHASE7A_POLICY_REVISION_DEFAULT = "2026-07-25.1"

RolloutRole = Literal[
    "rollout_viewer",
    "rollout_operator",
    "rollout_approver",
    "rollout_admin",
]
DecisionType = Literal["promote", "rollback", "reject", "request"]
DecisionStatus = Literal[
    "requested",
    "rejected",
    "cancelled",
    "test_only_simulated",
    "applied",
]
PointerTargetKind = Literal["legacy_v1", "v2_candidate", "unset", "rollback"]
PointerAction = Literal["initialize", "promote", "rollback"]
BreakerState = Literal["closed", "open", "half_open", "disabled"]
CanaryApprovalStatus = Literal["approved", "consumed", "expired", "revoked"]
MetricClass = Literal[
    "generation_failure",
    "visual_rejection",
    "operator_rejection",
    "promotion_write_failure",
    "serving_health_failure",
    "runtime_validation_failure",
]

NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=256),
]


class CircuitBreakerPolicyContract(StrictDesignModel):
    """Persisted breaker policy — never executed in Phase 7A."""

    schema_version: str = Field(default=ROLLOUT_SCHEMA_VERSION, pattern=r"^1\.0$")
    window_type: Literal["sliding"] = "sliding"
    window_seconds: StrictInt = Field(default=900, ge=1)
    min_samples: StrictInt = Field(default=20, ge=1)
    serving_health_failure_threshold: StrictFloat = Field(default=0.05, ge=0.0, le=1.0)
    promotion_write_failure_threshold: StrictFloat = Field(default=0.10, ge=0.0, le=1.0)
    consecutive_serving_health_failures: StrictInt = Field(default=3, ge=1)
    p95_serving_latency_seconds: StrictFloat = Field(default=5.0, ge=0.0)
    open_duration_seconds: StrictInt = Field(default=600, ge=1)
    half_open_probes: StrictInt = Field(default=2, ge=1)
    cost_spike_multiplier: StrictFloat = Field(default=3.0, ge=1.0)
    metric_classes: Tuple[MetricClass, ...] = (
        "generation_failure",
        "visual_rejection",
        "operator_rejection",
        "promotion_write_failure",
        "serving_health_failure",
        "runtime_validation_failure",
    )
    scope: Literal["request", "global"] = "global"


class ServingHealthCheckContract(StrictDesignModel):
    schema_version: str = Field(default=ROLLOUT_SCHEMA_VERSION, pattern=r"^1\.0$")
    pointer_resolves: StrictBool = True
    manifest_exists_and_hashes: StrictBool = True
    dist_exists: StrictBool = True
    index_html_resolves: StrictBool = True
    health_route_http_200: StrictBool = False
    no_severe_console_errors: StrictBool = False
    primary_journey_smoke: StrictBool = False
    latency_below_threshold: StrictBool = True
    visual_score_drift_advisory: StrictBool = True


class TrustedRolloutActor(StrictDesignModel):
    """Actor identity from trusted server auth — never from request JSON roles."""

    actor_id: NonEmptyText
    roles: Tuple[RolloutRole, ...] = Field(min_length=1)
    auth_source: Literal[
        "session",
        "admin_header",
        "service_principal",
        "test_fixture",
    ]

    @field_validator("roles")
    @classmethod
    def _unique_roles(cls, value: Tuple[RolloutRole, ...]) -> Tuple[RolloutRole, ...]:
        if len(value) != len(set(value)):
            raise ValueError("roles must be unique")
        return value


class SeparationOfDutiesResult(StrictDesignModel):
    requester_actor_id: NonEmptyText
    approver_actor_id: NonEmptyText | None = None
    same_actor: StrictBool
    dual_role_allowed: StrictBool
    ticket_ref: str | None = None
    satisfied: StrictBool
    reasons: Tuple[str, ...] = ()


class StickyBucketResult(StrictDesignModel):
    salt: NonEmptyText
    request_id: NonEmptyText
    digest_first8_hex: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{16}$")]
    bucket: StrictInt = Field(ge=0, le=99)
    rollout_percent: StrictInt = Field(ge=0, le=100)
    percent_eligible: StrictBool


class RolloutPolicyView(StrictDesignModel):
    schema_version: str = Field(default=ROLLOUT_SCHEMA_VERSION, pattern=r"^1\.0$")
    policy_revision: NonEmptyText
    master_enabled: StrictBool
    shadow_enabled: StrictBool
    promote_enabled: StrictBool
    rollout_percent: StrictInt = Field(ge=0, le=100)
    allowlist: Tuple[StrictInt, ...] = ()
    allowlist_sha256: Sha256
    circuit_breaker_policy: CircuitBreakerPolicyContract
    circuit_breaker_policy_sha256: Sha256
    rollout_salt: NonEmptyText
    configuration_sha256: Sha256
    created_actor_id: NonEmptyText
    created_actor_role: RolloutRole


class ServingPointerView(StrictDesignModel):
    """Read-only serving pointer resolution — not wired into production serve."""

    schema_version: str = Field(default=ROLLOUT_SCHEMA_VERSION, pattern=r"^1\.0$")
    request_id: StrictInt = Field(ge=1)
    pointer_version: StrictInt | None = Field(default=None, ge=1)
    target_kind: PointerTargetKind
    candidate_revision_id: StrictInt | None = Field(default=None, ge=1)
    legacy_preview_relpath: str | None = None
    effective_tier: StrictInt | None = Field(default=None, ge=1, le=3)
    effective_summary_id: StrictInt | None = Field(default=None, ge=1)
    summary_sha256: Sha256 | None = None
    candidate_manifest_sha256: Sha256 | None = None
    previous_pointer_version: StrictInt | None = Field(default=None, ge=1)
    created_at: str | None = None
    is_current: StrictBool = False
    pointer_action: PointerAction | None = None


class PromotionEligibilityResult(StrictDesignModel):
    """Advisory-only eligibility. Never authorizes or triggers a write."""

    schema_version: str = Field(default=ROLLOUT_SCHEMA_VERSION, pattern=r"^1\.0$")
    request_id: StrictInt = Field(ge=1)
    candidate_revision_id: StrictInt | None = Field(default=None, ge=1)
    requested_tier: StrictInt = Field(ge=1, le=3)
    effective_tier_summary_id: StrictInt | None = Field(default=None, ge=1)
    highest_accepted_tier: StrictInt = Field(ge=0, le=3)
    phase4_status: NonEmptyText
    phase5_status: NonEmptyText
    lineage_ok: StrictBool
    manifest_ok: StrictBool
    policy_revision: NonEmptyText
    master_enabled: StrictBool
    shadow_enabled: StrictBool
    promote_enabled: StrictBool
    allowlisted: StrictBool
    sticky_bucket: StrictInt = Field(ge=0, le=99)
    rollout_percent: StrictInt = Field(ge=0, le=100)
    percent_eligible: StrictBool
    circuit_breaker_state: BreakerState
    actor_id: NonEmptyText
    actor_roles: Tuple[RolloutRole, ...]
    actor_authorized: StrictBool
    separation_of_duties: SeparationOfDutiesResult
    eligible_for_shadow: StrictBool
    eligible_for_promote: StrictBool
    advisory_only: StrictBool = True
    rejection_reasons: Tuple[str, ...] = ()
    eligibility_sha256: Sha256

    @model_validator(mode="after")
    def _advisory_never_write_token(self) -> "PromotionEligibilityResult":
        if not self.advisory_only:
            raise ValueError("Phase 7A eligibility must remain advisory_only=true")
        return self


class LiveCanaryApprovalContract(StrictDesignModel):
    """Canary approval schema only — Phase 7A never constructs providers."""

    schema_version: str = Field(default=ROLLOUT_SCHEMA_VERSION, pattern=r"^1\.0$")
    approval_uuid: NonEmptyText
    request_id: StrictInt = Field(ge=1)
    provider_model_allowlist: Tuple[NonEmptyText, ...]
    max_calls: StrictInt = Field(ge=1)
    max_output_tokens: StrictInt = Field(ge=1)
    max_cost_usd: StrictFloat = Field(gt=0.0)
    max_wall_seconds: StrictInt = Field(ge=1)
    expires_at: NonEmptyText
    approver_id: NonEmptyText
    ticket_ref: NonEmptyText
    policy_revision: NonEmptyText
    status: CanaryApprovalStatus
    single_use: StrictBool = True
    approval_sha256: Sha256


class CanaryApprovalStatusEvent(StrictDesignModel):
    """Append-only status lineage — never mutate approved → consumed in place."""

    schema_version: str = Field(default=ROLLOUT_SCHEMA_VERSION, pattern=r"^1\.0$")
    approval_uuid: NonEmptyText
    status: CanaryApprovalStatus
    actor_id: NonEmptyText
    reason: NonEmptyText
    created_at: NonEmptyText
    event_sha256: Sha256


__all__ = [
    "PHASE7A_POLICY_REVISION_DEFAULT",
    "ROLLOUT_SCHEMA_VERSION",
    "BreakerState",
    "CanaryApprovalStatus",
    "CanaryApprovalStatusEvent",
    "CircuitBreakerPolicyContract",
    "DecisionStatus",
    "DecisionType",
    "LiveCanaryApprovalContract",
    "MetricClass",
    "PointerAction",
    "PointerTargetKind",
    "PromotionEligibilityResult",
    "RolloutPolicyView",
    "RolloutRole",
    "SeparationOfDutiesResult",
    "ServingHealthCheckContract",
    "ServingPointerView",
    "StickyBucketResult",
    "TrustedRolloutActor",
]
