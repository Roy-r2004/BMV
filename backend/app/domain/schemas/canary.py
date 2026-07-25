"""Strict Phase 7F live-canary and percentage-targeting contracts."""
from __future__ import annotations

from typing import Annotated, Literal, Tuple

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StringConstraints

from app.domain.schemas.design_contract import Sha256, StrictDesignModel
from app.domain.schemas.rollout import BreakerState


CANARY_SCHEMA_VERSION = "1.0"
NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=512),
]

CanaryLifecycleStatus = Literal[
    "requested",
    "approved",
    "executed",
    "completed",
    "failed",
    "aborted",
    "reviewed_accepted",
    "reviewed_rejected",
    "reviewed_fixture_only",
    "consumed",
]
CanaryExecutionResultStatus = Literal["running", "completed", "failed", "aborted"]
CanaryExecutionMode = Literal["fixture", "live"]
ServePathReason = Literal[
    "gates_invalid",
    "allowlisted",
    "percent_eligible",
    "percent_miss",
    "percent_blocked_missing_canary",
    "percent_blocked_stale_canary",
    "percent_blocked_breaker_state",
    "percent_serve_disabled",
    "fixture_canary_not_eligible",
    "no_current_pointer",
    "legacy_default",
]


class CanaryRequestBody(StrictDesignModel):
    reason: NonEmptyText
    ticket_ref: NonEmptyText
    max_calls: StrictInt | None = Field(default=None, ge=1, le=12)
    max_input_tokens: StrictInt | None = Field(default=None, ge=1)
    max_output_tokens: StrictInt | None = Field(default=None, ge=1)
    max_cost_usd: StrictFloat | None = Field(default=None, gt=0.0)
    max_wall_seconds: StrictInt | None = Field(default=None, ge=1, le=1200)
    max_retries: StrictInt | None = Field(default=None, ge=0, le=1)
    per_call_timeout_seconds: StrictInt | None = Field(default=None, ge=1, le=600)
    idempotency_key: NonEmptyText | None = None


class CanaryApprovalBody(StrictDesignModel):
    reason: NonEmptyText
    ticket_ref: NonEmptyText
    idempotency_key: NonEmptyText | None = None


class CanaryExecuteBody(StrictDesignModel):
    reason: NonEmptyText
    ticket_ref: NonEmptyText | None = None
    idempotency_key: NonEmptyText


class CanaryReviewBody(StrictDesignModel):
    accept: StrictBool
    reason: NonEmptyText
    ticket_ref: NonEmptyText
    idempotency_key: NonEmptyText | None = None


class CanaryLifecycleEventView(StrictDesignModel):
    status: CanaryLifecycleStatus
    actor_id: NonEmptyText
    reason: NonEmptyText
    ticket_ref: NonEmptyText | None = None
    created_at: NonEmptyText
    event_sha256: Sha256


class CanaryApprovalView(StrictDesignModel):
    schema_version: str = Field(default=CANARY_SCHEMA_VERSION, pattern=r"^1\.0$")
    approval_id: StrictInt = Field(ge=1)
    approval_uuid: NonEmptyText
    request_id: StrictInt = Field(ge=1)
    requester_id: NonEmptyText
    approver_id: NonEmptyText | None = None
    ticket_ref: NonEmptyText
    reason: NonEmptyText
    policy_revision: NonEmptyText
    rollout_salt: NonEmptyText
    provider_manifest_sha256: Sha256
    generation_policy_sha256: Sha256
    prompt_policy_sha256: Sha256
    runtime_policy_sha256: Sha256
    comparison_policy_revision: NonEmptyText
    budget_policy_sha256: Sha256
    policy_identity_sha256: Sha256
    max_calls: StrictInt = Field(ge=1)
    max_input_tokens: StrictInt = Field(ge=1)
    max_output_tokens: StrictInt = Field(ge=1)
    max_cost_usd: StrictFloat = Field(gt=0.0)
    max_wall_seconds: StrictInt = Field(ge=1)
    max_retries: StrictInt = Field(ge=0)
    per_call_timeout_seconds: StrictInt = Field(ge=1)
    expires_at: NonEmptyText
    latest_status: CanaryLifecycleStatus
    approval_sha256: Sha256
    lifecycle: Tuple[CanaryLifecycleEventView, ...] = ()


class CanaryExecutionProvenanceView(StrictDesignModel):
    execution_mode: CanaryExecutionMode
    provider_was_live: StrictBool
    provider_family: NonEmptyText | None = None
    provider_model: NonEmptyText | None = None
    provider_manifest_sha256: Sha256
    provider_factory_revision: NonEmptyText | None = None
    network_access_expected: StrictBool
    execution_environment: NonEmptyText | None = None
    simulation_only: StrictBool
    percent_authorization_eligible: StrictBool


class CanaryExecutionView(StrictDesignModel):
    schema_version: str = Field(default=CANARY_SCHEMA_VERSION, pattern=r"^1\.0$")
    execution_id: StrictInt = Field(ge=1)
    execution_uuid: NonEmptyText
    approval_id: StrictInt = Field(ge=1)
    request_id: StrictInt = Field(ge=1)
    started_at: NonEmptyText
    completed_at: NonEmptyText | None = None
    provider_manifest_sha256: Sha256
    generation_policy_sha256: Sha256
    prompt_policy_sha256: Sha256
    candidate_revision_id: StrictInt | None = Field(default=None, ge=1)
    effective_tier: StrictInt | None = Field(default=None, ge=0)
    phase4_status: NonEmptyText | None = None
    phase5_status: NonEmptyText | None = None
    provider_calls: StrictInt = Field(ge=0)
    input_tokens: StrictInt = Field(ge=0)
    output_tokens: StrictInt = Field(ge=0)
    estimated_cost_usd: StrictFloat = Field(ge=0.0)
    wall_seconds: StrictFloat = Field(ge=0.0)
    retries: StrictInt = Field(ge=0)
    comparison_artifact_sha256: Sha256 | None = None
    telemetry_sha256: Sha256
    result_status: CanaryExecutionResultStatus
    failure_reason: NonEmptyText | None = None
    no_serving_mutation: StrictBool = True
    pointer_version_before: StrictInt | None = Field(default=None, ge=1)
    pointer_version_after: StrictInt | None = Field(default=None, ge=1)
    policy_identity_sha256: Sha256
    execution_sha256: Sha256
    reviewed_accepted: StrictBool = False
    reviewed_fixture_only: StrictBool = False
    provenance: CanaryExecutionProvenanceView


class TargetingDiagnosticView(StrictDesignModel):
    schema_version: str = Field(default=CANARY_SCHEMA_VERSION, pattern=r"^1\.0$")
    request_id: StrictInt = Field(ge=1)
    normalized_request_id: NonEmptyText
    sticky_bucket: StrictInt = Field(ge=0, le=99)
    configured_percent: StrictInt = Field(ge=0, le=100)
    allowlisted: StrictBool
    percent_serve_enabled: StrictBool
    percent_eligible: StrictBool
    canary_gate_valid: StrictBool
    canary_gate_reason: NonEmptyText | None = None
    current_pointer_available: StrictBool
    breaker_state: BreakerState
    serve_pointer: StrictBool
    serve_legacy: StrictBool
    serve_reason: ServePathReason
    diagnostic_sha256: Sha256


__all__ = [
    "CANARY_SCHEMA_VERSION",
    "CanaryApprovalBody",
    "CanaryApprovalView",
    "CanaryExecuteBody",
    "CanaryExecutionMode",
    "CanaryExecutionProvenanceView",
    "CanaryExecutionView",
    "CanaryLifecycleEventView",
    "CanaryLifecycleStatus",
    "CanaryRequestBody",
    "CanaryReviewBody",
    "ServePathReason",
    "TargetingDiagnosticView",
]
