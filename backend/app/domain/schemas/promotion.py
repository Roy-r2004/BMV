"""Strict Phase 7C allowlist promotion / rollback contracts."""
from __future__ import annotations

from typing import Annotated, Literal, Tuple

from pydantic import Field, StrictBool, StrictInt, StringConstraints, model_validator

from app.domain.schemas.design_contract import Sha256, StrictDesignModel
from app.domain.schemas.rollout import (
    BreakerState,
    PointerTargetKind,
    RolloutRole,
    SeparationOfDutiesResult,
    ServingPointerView,
)


PROMOTION_SCHEMA_VERSION = "1.0"
NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=256),
]
DecisionKind = Literal["promote", "rollback"]
LatestDecisionStatus = Literal[
    "requested",
    "approved",
    "rejected",
    "cancelled",
    "applied",
]


class PromotionRequestBody(StrictDesignModel):
    candidate_revision_id: StrictInt = Field(ge=1)
    effective_tier_summary_id: StrictInt = Field(ge=1)
    expected_pointer_version: StrictInt | None = Field(default=None, ge=1)
    reason: NonEmptyText
    ticket_ref: NonEmptyText
    idempotency_key: NonEmptyText | None = None
    # Optional Phase 7F evidence reference — never bypasses SoD/health/apply.
    canary_execution_id: StrictInt | None = Field(default=None, ge=1)


class RollbackRequestBody(StrictDesignModel):
    expected_pointer_version: StrictInt = Field(ge=1)
    target_pointer_version: StrictInt | None = Field(default=None, ge=1)
    reason: NonEmptyText
    ticket_ref: NonEmptyText
    idempotency_key: NonEmptyText | None = None


class DecisionApprovalBody(StrictDesignModel):
    reason: NonEmptyText
    ticket_ref: NonEmptyText | None = None
    idempotency_key: NonEmptyText | None = None


class DecisionApplyBody(StrictDesignModel):
    expected_pointer_version: StrictInt | None = Field(default=None, ge=1)
    reason: NonEmptyText
    ticket_ref: NonEmptyText | None = None
    idempotency_key: NonEmptyText | None = None
    emergency_dual_role: StrictBool = False


class HealthPrecheckResult(StrictDesignModel):
    passed: StrictBool
    decision_exists: StrictBool
    latest_status_approved: StrictBool
    pointer_version_matches: StrictBool
    allowlisted: StrictBool
    rollout_percent_zero: StrictBool
    flags_enabled: StrictBool
    breaker_not_open: StrictBool
    candidate_exists: StrictBool
    manifest_matches: StrictBool
    dist_exists: StrictBool
    entry_exists: StrictBool
    phase4_ok: StrictBool
    phase5_ok: StrictBool
    effective_tier_ok: StrictBool
    reasons: Tuple[str, ...] = ()


class PromotionApplyEligibilityResult(StrictDesignModel):
    schema_version: str = Field(default=PROMOTION_SCHEMA_VERSION, pattern=r"^1\.0$")
    request_id: StrictInt = Field(ge=1)
    decision_id: StrictInt = Field(ge=1)
    decision_type: DecisionKind
    candidate_revision_id: StrictInt | None = Field(default=None, ge=1)
    target_pointer_version: StrictInt | None = Field(default=None, ge=1)
    current_pointer_version: StrictInt | None = Field(default=None, ge=1)
    expected_pointer_version: StrictInt | None = Field(default=None, ge=1)
    latest_decision_status: LatestDecisionStatus
    requester_actor_id: NonEmptyText
    approver_actor_id: NonEmptyText | None = None
    apply_actor_id: NonEmptyText
    separation_of_duties: SeparationOfDutiesResult
    allowlisted: StrictBool
    rollout_percent_zero: StrictBool
    master_enabled: StrictBool
    promote_enabled: StrictBool
    circuit_breaker_state: BreakerState
    phase4_ok: StrictBool
    phase5_ok: StrictBool
    effective_tier_ok: StrictBool
    manifest_ok: StrictBool
    health: HealthPrecheckResult
    eligible_to_apply: StrictBool
    reusable_write_token: StrictBool = False
    rejection_reasons: Tuple[str, ...] = ()
    eligibility_sha256: Sha256

    @model_validator(mode="after")
    def _no_token(self) -> "PromotionApplyEligibilityResult":
        if self.reusable_write_token:
            raise ValueError("apply eligibility must not be a reusable write token")
        return self


class DecisionView(StrictDesignModel):
    schema_version: str = Field(default=PROMOTION_SCHEMA_VERSION, pattern=r"^1\.0$")
    decision_id: StrictInt = Field(ge=1)
    request_id: StrictInt = Field(ge=1)
    decision_type: DecisionKind
    latest_status: LatestDecisionStatus
    candidate_revision_id: StrictInt | None = Field(default=None, ge=1)
    effective_tier_summary_id: StrictInt | None = Field(default=None, ge=1)
    expected_pointer_version: StrictInt | None = Field(default=None, ge=1)
    target_pointer_version: StrictInt | None = Field(default=None, ge=1)
    resulting_pointer_version: StrictInt | None = Field(default=None, ge=1)
    requester_actor_id: NonEmptyText
    reason: NonEmptyText
    ticket_ref: str | None = None
    idempotency_key: str | None = None
    policy_revision: NonEmptyText
    decision_sha256: Sha256
    created_at: NonEmptyText


class ApplyResultView(StrictDesignModel):
    decision: DecisionView
    pointer: ServingPointerView
    eligibility_sha256: Sha256


__all__ = [
    "PROMOTION_SCHEMA_VERSION",
    "ApplyResultView",
    "DecisionApprovalBody",
    "DecisionApplyBody",
    "DecisionKind",
    "DecisionView",
    "HealthPrecheckResult",
    "LatestDecisionStatus",
    "PromotionApplyEligibilityResult",
    "PromotionRequestBody",
    "RollbackRequestBody",
]
