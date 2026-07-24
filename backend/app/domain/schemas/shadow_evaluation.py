"""Strict Phase 7B shadow evaluation contracts."""
from __future__ import annotations

from typing import Annotated, Literal, Tuple

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StringConstraints, model_validator

from app.domain.schemas.design_contract import Sha256, StrictDesignModel
from app.domain.schemas.rollout import BreakerState, PointerTargetKind, RolloutRole


SHADOW_SCHEMA_VERSION = "1.0"
SHADOW_COMPARISON_POLICY_REVISION = "2026-07-25.1"

ShadowMode = Literal["reuse_accepted", "regenerate_fixture", "regenerate_live"]
ShadowResultStatus = Literal["pending", "completed", "failed"]
CompareStatus = Literal["skipped", "completed", "failed", "absolute_only"]
NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=256),
]


class ShadowStartRequest(StrictDesignModel):
    """Admin POST body — never carries actor roles or authorization scopes."""

    mode: ShadowMode | None = None
    reason: NonEmptyText
    ticket_ref: str | None = Field(default=None, max_length=256)
    idempotency_key: NonEmptyText | None = None

    @model_validator(mode="after")
    def _no_auth_fields(self) -> "ShadowStartRequest":
        # Extra fields already forbidden by StrictDesignModel.
        return self


class ShadowTelemetry(StrictDesignModel):
    schema_version: str = Field(default=SHADOW_SCHEMA_VERSION, pattern=r"^1\.0$")
    mode: ShadowMode
    started_at: NonEmptyText
    completed_at: NonEmptyText | None = None
    wall_ms: StrictInt = Field(ge=0)
    provider_calls: StrictInt = Field(ge=0)
    output_tokens: StrictInt = Field(ge=0)
    estimated_cost_usd: StrictFloat = Field(ge=0.0)
    cache_hit_lineage: StrictBool = False
    cache_hit_pointer: StrictBool = False
    cache_hit_comparison: StrictBool = False
    phase4_status: NonEmptyText
    phase5_status: NonEmptyText
    highest_accepted_tier: StrictInt = Field(ge=0, le=3)
    served_target_kind: PointerTargetKind
    served_pointer_version: StrictInt | None = Field(default=None, ge=1)
    candidate_manifest_sha256: Sha256 | None = None
    effective_summary_sha256: Sha256 | None = None
    compare_enabled: StrictBool
    compare_status: CompareStatus
    eligibility_sha256: Sha256
    failure_stage: str | None = None
    rejection_reasons: Tuple[str, ...] = ()
    no_serving_mutation: StrictBool = True
    pointer_version_before: StrictInt | None = Field(default=None, ge=1)
    pointer_version_after: StrictInt | None = Field(default=None, ge=1)
    synthetic_fixture_telemetry: StrictBool = False

    @model_validator(mode="after")
    def _invariants(self) -> "ShadowTelemetry":
        if not self.no_serving_mutation:
            raise ValueError("shadow telemetry requires no_serving_mutation=true")
        if (
            self.pointer_version_before is not None
            and self.pointer_version_after is not None
            and self.pointer_version_before != self.pointer_version_after
        ):
            raise ValueError("pointer_version_after must equal pointer_version_before")
        return self


class ShadowEligibilityResult(StrictDesignModel):
    """Advisory shadow authorization — never authorizes promotion."""

    schema_version: str = Field(default=SHADOW_SCHEMA_VERSION, pattern=r"^1\.0$")
    request_id: StrictInt = Field(ge=1)
    actor_id: NonEmptyText
    actor_roles: Tuple[RolloutRole, ...]
    policy_revision: NonEmptyText
    allowlisted: StrictBool
    sticky_bucket: StrictInt = Field(ge=0, le=99)
    rollout_percent: StrictInt = Field(ge=0, le=100)
    percent_eligible: StrictBool
    selected_mode: ShadowMode
    accepted_lineage_available: StrictBool
    served_target_kind: PointerTargetKind
    served_pointer_version: StrictInt | None = Field(default=None, ge=1)
    configuration_valid: StrictBool
    master_enabled: StrictBool
    shadow_enabled: StrictBool
    circuit_breaker_state: BreakerState
    actor_authorized: StrictBool
    eligible_for_shadow: StrictBool
    advisory_only: StrictBool = True
    cannot_authorize_promotion: StrictBool = True
    rejection_reasons: Tuple[str, ...] = ()
    eligibility_sha256: Sha256

    @model_validator(mode="after")
    def _advisory(self) -> "ShadowEligibilityResult":
        if not self.advisory_only or not self.cannot_authorize_promotion:
            raise ValueError("shadow eligibility must remain advisory and non-promoting")
        return self


class ShadowComparisonArtifact(StrictDesignModel):
    schema_version: str = Field(default=SHADOW_SCHEMA_VERSION, pattern=r"^1\.0$")
    comparison_policy_revision: NonEmptyText
    served_target_kind: PointerTargetKind
    served_pointer_version: StrictInt | None = Field(default=None, ge=1)
    v2_candidate_revision_id: StrictInt | None = Field(default=None, ge=1)
    v2_effective_summary_id: StrictInt | None = Field(default=None, ge=1)
    served_target_hash: Sha256 | None = None
    candidate_manifest_sha256: Sha256 | None = None
    effective_summary_sha256: Sha256 | None = None
    served_route_count: StrictInt | None = Field(default=None, ge=0)
    candidate_route_count: StrictInt | None = Field(default=None, ge=0)
    route_coverage_delta: StrictInt | None = None
    dist_exists: StrictBool
    entry_file_exists: StrictBool
    phase4_status: NonEmptyText
    phase5_status: NonEmptyText
    highest_accepted_tier: StrictInt = Field(ge=0, le=3)
    time_to_ready_delta_ms: StrictInt | None = None
    shadow_wall_ms: StrictInt = Field(ge=0)
    provider_calls: StrictInt = Field(ge=0)
    output_tokens: StrictInt = Field(ge=0)
    estimated_cost_usd: StrictFloat = Field(ge=0.0)
    limitations: Tuple[str, ...] = ()
    absolute_only: StrictBool = False
    visual_superiority_claimed: StrictBool = False
    promotion_recommended: StrictBool = False
    result: Literal["completed", "failed", "skipped", "absolute_only"]
    artifact_sha256: Sha256

    @model_validator(mode="after")
    def _no_promo_claim(self) -> "ShadowComparisonArtifact":
        if self.visual_superiority_claimed:
            raise ValueError("comparison must not claim visual superiority")
        if self.promotion_recommended:
            raise ValueError("comparison must not recommend promotion")
        return self


class ShadowEvaluationView(StrictDesignModel):
    schema_version: str = Field(default=SHADOW_SCHEMA_VERSION, pattern=r"^1\.0$")
    evaluation_id: StrictInt = Field(ge=1)
    request_id: StrictInt = Field(ge=1)
    shadow_attempt_uuid: NonEmptyText
    terminal_of_evaluation_id: StrictInt | None = Field(default=None, ge=1)
    result_status: ShadowResultStatus
    mode: ShadowMode
    served_target_kind: PointerTargetKind
    served_pointer_version: StrictInt | None = Field(default=None, ge=1)
    v2_candidate_revision_id: StrictInt | None = Field(default=None, ge=1)
    v2_effective_summary_id: StrictInt | None = Field(default=None, ge=1)
    comparison_policy_revision: NonEmptyText
    comparison_artifact_sha256: Sha256 | None = None
    telemetry: ShadowTelemetry
    telemetry_sha256: Sha256
    evaluation_sha256: Sha256
    no_serving_mutation: StrictBool = True
    idempotency_key: str | None = None
    created_at: NonEmptyText


__all__ = [
    "SHADOW_COMPARISON_POLICY_REVISION",
    "SHADOW_SCHEMA_VERSION",
    "CompareStatus",
    "ShadowComparisonArtifact",
    "ShadowEligibilityResult",
    "ShadowEvaluationView",
    "ShadowMode",
    "ShadowResultStatus",
    "ShadowStartRequest",
    "ShadowTelemetry",
]
