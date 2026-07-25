"""Strict Phase 7D circuit-breaker and auto-rollback contracts."""
from __future__ import annotations

from typing import Annotated, Literal, Tuple

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StringConstraints

from app.domain.schemas.design_contract import Sha256, StrictDesignModel
from app.domain.schemas.rollout import BreakerState


BREAKER_SCHEMA_VERSION = "1.0"
GLOBAL_BREAKER_SCOPE_KEY = "global:preview-generator-v2"
SYSTEM_BREAKER_ACTOR_ID = "system:phase7-breaker"

NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=256),
]

BreakerMetricClass = Literal[
    "promotion_write_success",
    "promotion_write_failure",
    "serving_health_success",
    "serving_health_failure",
    "serving_latency",
    "generation_failure",
    "runtime_validation_failure",
    "visual_rejection",
    "operator_rejection",
]

SampleOutcome = Literal["success", "failure", "observed"]


class BreakerManualOpenBody(StrictDesignModel):
    reason: NonEmptyText
    ticket_ref: NonEmptyText
    run_auto_rollback: StrictBool = False


class BreakerManualCloseBody(StrictDesignModel):
    reason: NonEmptyText
    ticket_ref: NonEmptyText


class BreakerDisableBody(StrictDesignModel):
    reason: NonEmptyText
    ticket_ref: NonEmptyText


class BreakerEvaluateBody(StrictDesignModel):
    reason: NonEmptyText | None = None
    run_auto_rollback_if_opened: StrictBool = True


class BreakerAutoRollbackRunBody(StrictDesignModel):
    open_state_id: StrictInt = Field(ge=1)
    reason: NonEmptyText | None = None


class BreakerMetricSnapshot(StrictDesignModel):
    window_seconds: StrictInt = Field(ge=1)
    min_samples: StrictInt = Field(ge=1)
    promotion_write_samples: StrictInt = Field(ge=0)
    promotion_write_failures: StrictInt = Field(ge=0)
    promotion_write_failure_rate: StrictFloat = Field(ge=0.0, le=1.0)
    serving_health_samples: StrictInt = Field(ge=0)
    serving_health_failures: StrictInt = Field(ge=0)
    serving_health_failure_rate: StrictFloat = Field(ge=0.0, le=1.0)
    consecutive_serving_health_failures: StrictInt = Field(ge=0)
    latency_samples: StrictInt = Field(ge=0)
    p95_serving_latency_seconds: StrictFloat | None = None
    p95_enabled: StrictBool = False
    trip_reasons: Tuple[str, ...] = ()
    snapshot_sha256: Sha256


class BreakerEvaluationResult(StrictDesignModel):
    schema_version: str = Field(default=BREAKER_SCHEMA_VERSION, pattern=r"^1\.0$")
    scope_key: NonEmptyText = GLOBAL_BREAKER_SCOPE_KEY
    current_state: BreakerState
    next_state: BreakerState
    transitioned: StrictBool
    policy_revision: NonEmptyText
    metric_snapshot: BreakerMetricSnapshot
    evaluation_sha256: Sha256
    open_state_id: StrictInt | None = Field(default=None, ge=1)
    half_open_probes_passed: StrictInt = Field(default=0, ge=0)
    rejection_reasons: Tuple[str, ...] = ()


class BreakerStateView(StrictDesignModel):
    schema_version: str = Field(default=BREAKER_SCHEMA_VERSION, pattern=r"^1\.0$")
    state_id: StrictInt = Field(ge=1)
    scope_key: NonEmptyText
    state: BreakerState
    metric_class: NonEmptyText
    reason: NonEmptyText
    policy_revision: NonEmptyText
    policy_id: StrictInt = Field(ge=1)
    created_at: NonEmptyText
    state_sha256: Sha256
    is_current: StrictBool = True


class BreakerMetricSampleView(StrictDesignModel):
    sample_id: StrictInt = Field(ge=1)
    event_at: NonEmptyText
    metric_class: BreakerMetricClass
    outcome: SampleOutcome
    request_id: StrictInt | None = Field(default=None, ge=1)
    decision_id: StrictInt | None = Field(default=None, ge=1)
    pointer_version: StrictInt | None = Field(default=None, ge=1)
    duration_ms: StrictFloat | None = None
    policy_revision: NonEmptyText
    source_event_hash: Sha256
    sample_sha256: Sha256


class AutoRollbackResultView(StrictDesignModel):
    open_state_id: StrictInt = Field(ge=1)
    request_id: StrictInt = Field(ge=1)
    decision_id: StrictInt | None = Field(default=None, ge=1)
    status: Literal[
        "applied",
        "skipped",
        "failed",
        "already_processed",
    ]
    reason: NonEmptyText
    resulting_pointer_version: StrictInt | None = Field(default=None, ge=1)
    target_pointer_version: StrictInt | None = Field(default=None, ge=1)
    idempotency_key: NonEmptyText | None = None


__all__ = [
    "BREAKER_SCHEMA_VERSION",
    "GLOBAL_BREAKER_SCOPE_KEY",
    "SYSTEM_BREAKER_ACTOR_ID",
    "AutoRollbackResultView",
    "BreakerAutoRollbackRunBody",
    "BreakerDisableBody",
    "BreakerEvaluateBody",
    "BreakerEvaluationResult",
    "BreakerManualCloseBody",
    "BreakerManualOpenBody",
    "BreakerMetricClass",
    "BreakerMetricSampleView",
    "BreakerMetricSnapshot",
    "BreakerStateView",
    "SampleOutcome",
]
