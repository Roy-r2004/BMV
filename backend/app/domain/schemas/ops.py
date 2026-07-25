"""Strict Phase 7E ops dashboard and alert contracts."""
from __future__ import annotations

from typing import Annotated, Any, Literal, Tuple

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StringConstraints

from app.domain.schemas.breaker import BreakerMetricSnapshot, GLOBAL_BREAKER_SCOPE_KEY
from app.domain.schemas.design_contract import Sha256, StrictDesignModel
from app.domain.schemas.rollout import BreakerState


OPS_SCHEMA_VERSION = "1.0"

NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=256),
]

AlertClass = Literal[
    "breaker_opened",
    "breaker_half_open",
    "breaker_closed",
    "promote_error_budget_burn",
    "serving_health_budget_burn",
    "promotion_write_failure_burst",
    "auto_rollback_failed",
    "auto_rollback_skipped_unhealthy_no_predecessor",
    "history_mutation_denied",
    "phase7_config_invalid",
    "alert_storm_suppressed",
]

AlertSeverity = Literal["info", "medium", "high", "critical"]
AlertStatus = Literal["recorded", "acknowledged", "suppressed"]


class AlertAckBody(StrictDesignModel):
    reason: NonEmptyText
    ticket_ref: NonEmptyText | None = None
    idempotency_key: NonEmptyText | None = None


class OpsFlagsView(StrictDesignModel):
    rollout_enabled: StrictBool
    shadow_enabled: StrictBool
    promote_enabled: StrictBool
    circuit_breaker_enabled: StrictBool
    auto_rollback_enabled: StrictBool
    ops_dashboard_enabled: StrictBool
    ops_alerts_enabled: StrictBool
    config_valid: StrictBool
    rollout_percent: StrictInt = Field(ge=0, le=100)
    allowlist_size: StrictInt = Field(ge=0)


class OpsOverviewView(StrictDesignModel):
    schema_version: str = Field(default=OPS_SCHEMA_VERSION, pattern=r"^1\.0$")
    disabled: StrictBool = False
    scope_key: NonEmptyText = GLOBAL_BREAKER_SCOPE_KEY
    breaker_state: BreakerState | None = None
    breaker_state_id: StrictInt | None = Field(default=None, ge=1)
    policy_revision: NonEmptyText | None = None
    breaker_state_age_seconds: StrictFloat | None = None
    flags: OpsFlagsView
    promotion_applied_count: StrictInt = Field(default=0, ge=0)
    rollback_applied_count: StrictInt = Field(default=0, ge=0)
    auto_rollback_applied_count: StrictInt = Field(default=0, ge=0)
    auto_rollback_failed_count: StrictInt = Field(default=0, ge=0)
    auto_rollback_skipped_count: StrictInt = Field(default=0, ge=0)
    shadow_evaluation_count: StrictInt = Field(default=0, ge=0)
    serving_fallback_count: StrictInt = Field(default=0, ge=0)
    serving_health_failure_count: StrictInt = Field(default=0, ge=0)
    lookback_seconds: StrictInt = Field(ge=1)
    overview_sha256: Sha256


class OpsBreakerBudgetView(StrictDesignModel):
    schema_version: str = Field(default=OPS_SCHEMA_VERSION, pattern=r"^1\.0$")
    disabled: StrictBool = False
    scope_key: NonEmptyText = GLOBAL_BREAKER_SCOPE_KEY
    breaker_state: BreakerState | None = None
    policy_revision: NonEmptyText | None = None
    thresholds: dict[str, Any] = Field(default_factory=dict)
    metric_snapshot: BreakerMetricSnapshot | None = None
    half_open_countdown_seconds: StrictFloat | None = None
    budget_sha256: Sha256


class OpsRequestDrilldownView(StrictDesignModel):
    schema_version: str = Field(default=OPS_SCHEMA_VERSION, pattern=r"^1\.0$")
    request_id: StrictInt = Field(ge=1)
    current_pointer: dict[str, Any] | None = None
    pointer_history: Tuple[dict[str, Any], ...] = ()
    decisions: Tuple[dict[str, Any], ...] = ()
    shadow_evaluations: Tuple[dict[str, Any], ...] = ()
    auto_rollback_claims: Tuple[dict[str, Any], ...] = ()
    fallback_audits: Tuple[dict[str, Any], ...] = ()
    drilldown_sha256: Sha256


class AlertStatusEventView(StrictDesignModel):
    status_event_id: StrictInt = Field(ge=1)
    alert_id: StrictInt = Field(ge=1)
    status: AlertStatus
    actor_id: NonEmptyText
    reason: NonEmptyText
    ticket_ref: NonEmptyText | None = None
    created_at: NonEmptyText
    event_sha256: Sha256


class AlertView(StrictDesignModel):
    schema_version: str = Field(default=OPS_SCHEMA_VERSION, pattern=r"^1\.0$")
    alert_id: StrictInt = Field(ge=1)
    alert_class: AlertClass
    severity: AlertSeverity
    scope_key: NonEmptyText
    source_event_type: NonEmptyText
    source_event_id: NonEmptyText
    source_sha256: Sha256
    policy_revision: NonEmptyText
    payload: dict[str, Any]
    payload_sha256: Sha256
    dedupe_key: NonEmptyText
    created_at: NonEmptyText
    alert_sha256: Sha256
    latest_status: AlertStatus
    status_events: Tuple[AlertStatusEventView, ...] = ()


class RunbookActionView(StrictDesignModel):
    recommendation: NonEmptyText
    method: NonEmptyText
    path: NonEmptyText
    required_role: NonEmptyText


class OpsRunbookView(StrictDesignModel):
    schema_version: str = Field(default=OPS_SCHEMA_VERSION, pattern=r"^1\.0$")
    disabled: StrictBool = False
    breaker_state: BreakerState | None = None
    actions: Tuple[RunbookActionView, ...] = ()
    notes: Tuple[str, ...] = ()
    runbook_sha256: Sha256


__all__ = [
    "OPS_SCHEMA_VERSION",
    "AlertAckBody",
    "AlertClass",
    "AlertSeverity",
    "AlertStatus",
    "AlertStatusEventView",
    "AlertView",
    "OpsBreakerBudgetView",
    "OpsFlagsView",
    "OpsOverviewView",
    "OpsRequestDrilldownView",
    "OpsRunbookView",
    "RunbookActionView",
]
