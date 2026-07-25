"""Append-only Phase 7A rollout control-plane persistence models.

Pointer rows allow a narrow `is_current` flip for the future-safe swap
transaction. All other Phase 7 history is insert-only. Status transitions use
append-only event rows rather than in-place mutation.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)  # Float used by canary + breaker metric samples
from sqlalchemy.orm import Session

from app.infrastructure.db.base import Base


class PreviewRolloutPolicyRecord(Base):
    __tablename__ = "preview_rollout_policies"
    __table_args__ = (
        CheckConstraint(
            "rollout_percent >= 0 AND rollout_percent <= 100",
            name="ck_rollout_policy_percent",
        ),
        UniqueConstraint("policy_revision", name="uq_rollout_policy_revision"),
        UniqueConstraint(
            "configuration_sha256",
            name="uq_rollout_policy_configuration_sha256",
        ),
        Index("ix_rollout_policy_created", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    policy_revision = Column(String(64), nullable=False)
    master_enabled = Column(Boolean, nullable=False, default=False)
    shadow_enabled = Column(Boolean, nullable=False, default=False)
    promote_enabled = Column(Boolean, nullable=False, default=False)
    rollout_percent = Column(Integer, nullable=False, default=0)
    allowlist_json = Column(Text, nullable=False)
    allowlist_sha256 = Column(String(64), nullable=False)
    circuit_breaker_policy_json = Column(Text, nullable=False)
    circuit_breaker_policy_sha256 = Column(String(64), nullable=False)
    rollout_salt = Column(String(128), nullable=False)
    configuration_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_actor_id = Column(String(128), nullable=False)
    created_actor_role = Column(String(64), nullable=False)


class PreviewPromotionDecisionRecord(Base):
    __tablename__ = "preview_promotion_decisions"
    __table_args__ = (
        CheckConstraint(
            "decision_type IN ('promote','rollback','reject','request')",
            name="ck_promotion_decision_type",
        ),
        CheckConstraint(
            "decision_status IN ("
            "'requested','rejected','cancelled',"
            "'test_only_simulated','applied')",
            name="ck_promotion_decision_status",
        ),
        UniqueConstraint("decision_sha256", name="uq_promotion_decision_sha256"),
        UniqueConstraint(
            "request_id",
            "idempotency_key",
            name="uq_promotion_decision_idempotency",
        ),
        Index("ix_promotion_decision_request", "request_id", "requested_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(
        Integer,
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision_type = Column(String(32), nullable=False)
    decision_status = Column(String(32), nullable=False)
    candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    effective_tier_summary_id = Column(
        Integer,
        ForeignKey("candidate_effective_tier_summaries.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    phase4_validation_summary_id = Column(
        Integer,
        ForeignKey("candidate_validation_summaries.id", ondelete="RESTRICT"),
        nullable=True,
    )
    phase5_visual_summary_id = Column(
        Integer,
        ForeignKey("candidate_visual_summaries.id", ondelete="RESTRICT"),
        nullable=True,
    )
    lineage_sha256 = Column(String(64), nullable=False)
    candidate_manifest_sha256 = Column(String(64), nullable=True)
    actor_id = Column(String(128), nullable=False)
    actor_role = Column(String(64), nullable=False)
    reason = Column(Text, nullable=False)
    ticket_ref = Column(String(256), nullable=True)
    policy_revision = Column(String(64), nullable=False)
    eligibility_sha256 = Column(String(64), nullable=False)
    idempotency_key = Column(String(128), nullable=True)
    requested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    rejection_reason = Column(Text, nullable=True)
    previous_pointer_version = Column(Integer, nullable=True)
    resulting_pointer_version = Column(Integer, nullable=True)
    decision_sha256 = Column(String(64), nullable=False)
    # Phase 7C additive intent fields (immutable after insert)
    expected_pointer_version = Column(Integer, nullable=True)
    target_pointer_version = Column(Integer, nullable=True)
    idempotency_payload_sha256 = Column(String(64), nullable=True)


class PreviewPromotionDecisionStatusEventRecord(Base):
    """Append-only status lineage for decisions (requested → applied, etc.)."""

    __tablename__ = "preview_promotion_decision_status_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'requested','approved','rejected','cancelled',"
            "'test_only_simulated','applied')",
            name="ck_promotion_decision_event_status",
        ),
        UniqueConstraint("event_sha256", name="uq_promotion_decision_event_sha256"),
        Index(
            "ix_promotion_decision_event_decision",
            "decision_id",
            "created_at",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    decision_id = Column(
        Integer,
        ForeignKey("preview_promotion_decisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status = Column(String(32), nullable=False)
    actor_id = Column(String(128), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    event_sha256 = Column(String(64), nullable=False)


class PreviewServingPointerVersionRecord(Base):
    __tablename__ = "preview_serving_pointer_versions"
    __table_args__ = (
        CheckConstraint(
            "target_kind IN ('legacy_v1','v2_candidate','rollback')",
            name="ck_serving_pointer_target_kind",
        ),
        CheckConstraint(
            "pointer_action IN ('initialize','promote','rollback')",
            name="ck_serving_pointer_action",
        ),
        CheckConstraint(
            "("
            "(target_kind = 'legacy_v1' AND legacy_preview_relpath IS NOT NULL "
            "AND candidate_revision_id IS NULL) OR "
            "(target_kind = 'v2_candidate' AND candidate_revision_id IS NOT NULL) OR "
            "(target_kind = 'rollback')"
            ")",
            name="ck_serving_pointer_target_consistency",
        ),
        UniqueConstraint(
            "request_id",
            "pointer_version",
            name="uq_serving_pointer_request_version",
        ),
        UniqueConstraint("pointer_sha256", name="uq_serving_pointer_sha256"),
        Index("ix_serving_pointer_request_current", "request_id", "is_current"),
    )

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(
        Integer,
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pointer_version = Column(Integer, nullable=False)
    target_kind = Column(String(16), nullable=False)
    candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    legacy_preview_relpath = Column(String(512), nullable=True)
    effective_tier = Column(Integer, nullable=True)
    effective_summary_id = Column(
        Integer,
        ForeignKey("candidate_effective_tier_summaries.id", ondelete="RESTRICT"),
        nullable=True,
    )
    summary_sha256 = Column(String(64), nullable=True)
    candidate_manifest_sha256 = Column(String(64), nullable=True)
    previous_pointer_version = Column(Integer, nullable=True)
    pointer_action = Column(String(32), nullable=False)
    decision_id = Column(
        Integer,
        ForeignKey("preview_promotion_decisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    actor_id = Column(String(128), nullable=False)
    policy_revision = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    is_current = Column(Boolean, nullable=False, default=False)
    pointer_sha256 = Column(String(64), nullable=False)


class PreviewRolloutAuditEventRecord(Base):
    __tablename__ = "preview_rollout_audit_events"
    __table_args__ = (
        UniqueConstraint("event_sha256", name="uq_rollout_audit_event_sha256"),
        Index("ix_rollout_audit_request_created", "request_id", "created_at"),
        Index("ix_rollout_audit_event_type", "event_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(
        Integer,
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    event_type = Column(String(64), nullable=False)
    actor_id = Column(String(128), nullable=False)
    actor_role = Column(String(64), nullable=False)
    policy_revision = Column(String(64), nullable=True)
    decision_id = Column(
        Integer,
        ForeignKey("preview_promotion_decisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    pointer_version_before = Column(Integer, nullable=True)
    pointer_version_after = Column(Integer, nullable=True)
    lineage_sha256 = Column(String(64), nullable=True)
    reason = Column(Text, nullable=True)
    ticket_ref = Column(String(256), nullable=True)
    metadata_json = Column(Text, nullable=False)
    metadata_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    event_sha256 = Column(String(64), nullable=False)


class PreviewShadowEvaluationRecord(Base):
    __tablename__ = "preview_shadow_evaluations"
    __table_args__ = (
        CheckConstraint(
            "served_target_kind IN ('legacy_v1','v2_candidate','none')",
            name="ck_shadow_served_target_kind",
        ),
        CheckConstraint(
            "result_status IN ('pending','completed','failed')",
            name="ck_shadow_result_status",
        ),
        CheckConstraint(
            "no_serving_mutation IN (0, 1)",
            name="ck_shadow_no_serving_mutation",
        ),
        UniqueConstraint("evaluation_sha256", name="uq_shadow_evaluation_sha256"),
        Index("ix_shadow_evaluation_request", "request_id", "created_at"),
        Index("ix_shadow_evaluation_attempt", "shadow_attempt_uuid"),
        Index("ix_shadow_evaluation_idempotency", "request_id", "idempotency_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(
        Integer,
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    served_target_kind = Column(String(16), nullable=False)
    served_pointer_version = Column(Integer, nullable=True)
    v2_candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    v2_effective_summary_id = Column(
        Integer,
        ForeignKey("candidate_effective_tier_summaries.id", ondelete="RESTRICT"),
        nullable=True,
    )
    comparison_policy_revision = Column(String(64), nullable=False)
    telemetry_json = Column(Text, nullable=False)
    telemetry_sha256 = Column(String(64), nullable=False)
    result_status = Column(String(32), nullable=False)
    comparison_artifact_sha256 = Column(String(64), nullable=True)
    no_serving_mutation = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    evaluation_sha256 = Column(String(64), nullable=False)
    # Phase 7B additive lineage / idempotency columns
    shadow_attempt_uuid = Column(String(36), nullable=True, index=True)
    terminal_of_evaluation_id = Column(
        Integer,
        ForeignKey("preview_shadow_evaluations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    mode = Column(String(32), nullable=True)
    idempotency_key = Column(String(128), nullable=True)
    eligibility_sha256 = Column(String(64), nullable=True)


class PreviewLiveCanaryApprovalRecord(Base):
    __tablename__ = "preview_live_canary_approvals"
    __table_args__ = (
        UniqueConstraint("approval_uuid", name="uq_canary_approval_uuid"),
        UniqueConstraint("approval_sha256", name="uq_canary_approval_sha256"),
        Index("ix_canary_approval_request", "request_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    approval_uuid = Column(String(36), nullable=False)
    request_id = Column(
        Integer,
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_model_allowlist_json = Column(Text, nullable=False)
    max_calls = Column(Integer, nullable=False)
    max_output_tokens = Column(Integer, nullable=False)
    max_cost_usd = Column(Float, nullable=False)
    max_wall_seconds = Column(Integer, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    approver_id = Column(String(128), nullable=False)
    ticket_ref = Column(String(256), nullable=False)
    policy_revision = Column(String(64), nullable=False)
    # Initial status only; transitions append to status-event table.
    initial_status = Column(String(32), nullable=False, default="approved")
    approval_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    # Phase 7F additive columns (nullable for pre-7F rows).
    requester_id = Column(String(128), nullable=True)
    reason = Column(Text, nullable=True)
    rollout_salt = Column(String(128), nullable=True)
    provider_manifest_sha256 = Column(String(64), nullable=True)
    generation_policy_sha256 = Column(String(64), nullable=True)
    prompt_policy_sha256 = Column(String(64), nullable=True)
    runtime_policy_sha256 = Column(String(64), nullable=True)
    comparison_policy_revision = Column(String(64), nullable=True)
    budget_policy_sha256 = Column(String(64), nullable=True)
    max_input_tokens = Column(Integer, nullable=True)
    max_retries = Column(Integer, nullable=True)
    per_call_timeout_seconds = Column(Integer, nullable=True)
    policy_identity_sha256 = Column(String(64), nullable=True)
    idempotency_key = Column(String(256), nullable=True)


class PreviewLiveCanaryApprovalStatusEventRecord(Base):
    __tablename__ = "preview_live_canary_approval_status_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('approved','consumed','expired','revoked')",
            name="ck_canary_status_event_status",
        ),
        UniqueConstraint("event_sha256", name="uq_canary_status_event_sha256"),
        Index(
            "ix_canary_status_event_approval",
            "approval_id",
            "created_at",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    approval_id = Column(
        Integer,
        ForeignKey("preview_live_canary_approvals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status = Column(String(32), nullable=False)
    actor_id = Column(String(128), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    event_sha256 = Column(String(64), nullable=False)


class PreviewLiveCanaryLifecycleEventRecord(Base):
    """Phase 7F append-only canary lifecycle (request→approve→execute→review)."""

    __tablename__ = "preview_live_canary_lifecycle_events"
    __table_args__ = (
        UniqueConstraint("event_sha256", name="uq_canary_life_event_sha256"),
        Index("ix_canary_life_approval", "approval_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    approval_id = Column(
        Integer,
        ForeignKey("preview_live_canary_approvals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status = Column(String(32), nullable=False)
    actor_id = Column(String(128), nullable=False)
    reason = Column(Text, nullable=False)
    ticket_ref = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    event_sha256 = Column(String(64), nullable=False)


class PreviewLiveCanaryExecutionRecord(Base):
    __tablename__ = "preview_live_canary_executions"
    __table_args__ = (
        UniqueConstraint("execution_uuid", name="uq_canary_exec_uuid"),
        UniqueConstraint("idempotency_key", name="uq_canary_exec_idem"),
        UniqueConstraint("execution_sha256", name="uq_canary_exec_sha256"),
        Index("ix_canary_exec_request", "request_id", "created_at"),
        Index("ix_canary_exec_approval", "approval_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    execution_uuid = Column(String(36), nullable=False)
    approval_id = Column(
        Integer,
        ForeignKey("preview_live_canary_approvals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    request_id = Column(
        Integer,
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    provider_manifest_sha256 = Column(String(64), nullable=False)
    generation_policy_sha256 = Column(String(64), nullable=False)
    prompt_policy_sha256 = Column(String(64), nullable=False)
    candidate_revision_id = Column(Integer, nullable=True)
    effective_tier = Column(Integer, nullable=True)
    phase4_status = Column(String(64), nullable=True)
    phase5_status = Column(String(64), nullable=True)
    provider_calls = Column(Integer, nullable=False, default=0)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    estimated_cost_usd = Column(Float, nullable=False, default=0.0)
    wall_seconds = Column(Float, nullable=False, default=0.0)
    retries = Column(Integer, nullable=False, default=0)
    budget_json = Column(Text, nullable=False)
    comparison_artifact_sha256 = Column(String(64), nullable=True)
    telemetry_sha256 = Column(String(64), nullable=False)
    result_status = Column(String(32), nullable=False)
    failure_reason = Column(Text, nullable=True)
    no_serving_mutation = Column(Boolean, nullable=False, default=True)
    pointer_version_before = Column(Integer, nullable=True)
    pointer_version_after = Column(Integer, nullable=True)
    policy_identity_sha256 = Column(String(64), nullable=False)
    idempotency_key = Column(String(256), nullable=False)
    execution_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    # Phase 7F.2 server-derived provenance (never client authority).
    execution_mode = Column(String(16), nullable=False, default="fixture")
    provider_was_live = Column(Boolean, nullable=False, default=False)
    provider_family = Column(String(64), nullable=True)
    provider_model = Column(String(128), nullable=True)
    provider_factory_revision = Column(String(64), nullable=True)
    network_access_expected = Column(Boolean, nullable=False, default=False)
    execution_environment = Column(String(64), nullable=True)
    simulation_only = Column(Boolean, nullable=False, default=True)
    percent_authorization_eligible = Column(Boolean, nullable=False, default=False)
    provenance_json = Column(Text, nullable=True)


class PreviewLiveCanaryExecutionStatusEventRecord(Base):
    __tablename__ = "preview_live_canary_execution_status_events"
    __table_args__ = (
        UniqueConstraint("event_sha256", name="uq_canary_exec_status_sha256"),
        Index("ix_canary_exec_status", "execution_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(
        Integer,
        ForeignKey("preview_live_canary_executions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status = Column(String(32), nullable=False)
    actor_id = Column(String(128), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    event_sha256 = Column(String(64), nullable=False)


class PreviewLiveCanaryExecutionClaimRecord(Base):
    """Mutable singleton claim for one global active canary execution."""

    __tablename__ = "preview_live_canary_execution_claims"
    __table_args__ = (
        UniqueConstraint("claim_sha256", name="uq_canary_exec_claim_sha256"),
    )

    id = Column(Integer, primary_key=True)
    execution_id = Column(
        Integer,
        ForeignKey("preview_live_canary_executions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    claimed_at = Column(DateTime, nullable=False)
    released_at = Column(DateTime, nullable=True)
    claim_sha256 = Column(String(64), nullable=False)


class PreviewCircuitBreakerPolicyRecord(Base):
    __tablename__ = "preview_circuit_breaker_policies"
    __table_args__ = (
        UniqueConstraint("policy_sha256", name="uq_breaker_policy_sha256"),
        UniqueConstraint("policy_revision", name="uq_breaker_policy_revision"),
    )

    id = Column(Integer, primary_key=True, index=True)
    policy_revision = Column(String(64), nullable=False)
    policy_json = Column(Text, nullable=False)
    policy_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_actor_id = Column(String(128), nullable=False)


class PreviewCircuitBreakerStateRecord(Base):
    """Append-only breaker state snapshots; current = latest per scope_key."""

    __tablename__ = "preview_circuit_breaker_states"
    __table_args__ = (
        CheckConstraint(
            "state IN ('closed','open','half_open','disabled')",
            name="ck_breaker_state",
        ),
        UniqueConstraint("state_sha256", name="uq_breaker_state_sha256"),
        Index("ix_breaker_state_scope_created", "scope_key", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    policy_id = Column(
        Integer,
        ForeignKey("preview_circuit_breaker_policies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    scope_key = Column(String(128), nullable=False)
    state = Column(String(32), nullable=False)
    metric_class = Column(String(64), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    state_sha256 = Column(String(64), nullable=False)


class PreviewBreakerMetricSampleRecord(Base):
    """Append-only sliding-window metric samples for Phase 7D."""

    __tablename__ = "preview_breaker_metric_samples"
    __table_args__ = (
        UniqueConstraint("sample_sha256", name="uq_breaker_sample_sha256"),
        UniqueConstraint("source_event_hash", name="uq_breaker_sample_source"),
        Index("ix_breaker_sample_event_at", "event_at"),
        Index("ix_breaker_sample_class_event", "metric_class", "event_at"),
        Index("ix_breaker_sample_request_event", "request_id", "event_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    event_at = Column(DateTime, nullable=False, index=True)
    metric_class = Column(String(64), nullable=False)
    outcome = Column(String(32), nullable=False)
    request_id = Column(
        Integer,
        ForeignKey("requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    decision_id = Column(
        Integer,
        ForeignKey("preview_promotion_decisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    pointer_version = Column(Integer, nullable=True)
    duration_ms = Column(Float, nullable=True)
    policy_revision = Column(String(64), nullable=False)
    source_event_id = Column(String(128), nullable=True)
    source_event_hash = Column(String(64), nullable=False)
    metadata_json = Column(Text, nullable=False)
    metadata_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    sample_sha256 = Column(String(64), nullable=False)


class PreviewBreakerAutoRollbackClaimRecord(Base):
    """Idempotency claims for auto-rollback per breaker-open event + request."""

    __tablename__ = "preview_breaker_auto_rollback_claims"
    __table_args__ = (
        UniqueConstraint(
            "open_state_id",
            "request_id",
            name="uq_breaker_auto_rb_open_request",
        ),
        UniqueConstraint("idempotency_key", name="uq_breaker_auto_rb_idem"),
        UniqueConstraint("claim_sha256", name="uq_breaker_auto_rb_claim_sha"),
    )

    id = Column(Integer, primary_key=True, index=True)
    open_state_id = Column(
        Integer,
        ForeignKey("preview_circuit_breaker_states.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    request_id = Column(
        Integer,
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision_id = Column(
        Integer,
        ForeignKey("preview_promotion_decisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    expected_pointer_version = Column(Integer, nullable=False)
    target_pointer_version = Column(Integer, nullable=False)
    idempotency_key = Column(String(256), nullable=False)
    claim_sha256 = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PreviewRolloutAlertEventRecord(Base):
    """Immutable Phase 7E alert event; status lives in append-only status events."""

    __tablename__ = "preview_rollout_alert_events"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_rollout_alert_dedupe"),
        UniqueConstraint("alert_sha256", name="uq_rollout_alert_sha"),
        Index("ix_rollout_alert_class", "alert_class"),
        Index("ix_rollout_alert_severity", "severity"),
        Index("ix_rollout_alert_created", "created_at"),
        Index("ix_rollout_alert_scope", "scope_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    alert_class = Column(String(64), nullable=False)
    severity = Column(String(16), nullable=False)
    scope_key = Column(String(128), nullable=False)
    source_event_type = Column(String(64), nullable=False)
    source_event_id = Column(String(128), nullable=False)
    source_sha256 = Column(String(64), nullable=False)
    policy_revision = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    payload_sha256 = Column(String(64), nullable=False)
    dedupe_key = Column(String(256), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    alert_sha256 = Column(String(64), nullable=False)


class PreviewRolloutAlertStatusEventRecord(Base):
    """Append-only alert status lineage: recorded / acknowledged / suppressed."""

    __tablename__ = "preview_rollout_alert_status_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('recorded','acknowledged','suppressed')",
            name="ck_rollout_alert_status",
        ),
        UniqueConstraint("event_sha256", name="uq_rollout_alert_status_sha"),
        Index("ix_rollout_alert_status_alert", "alert_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(
        Integer,
        ForeignKey("preview_rollout_alert_events.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status = Column(String(32), nullable=False)
    actor_id = Column(String(128), nullable=False)
    reason = Column(Text, nullable=False)
    ticket_ref = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    event_sha256 = Column(String(64), nullable=False)


_STRICT_APPEND_ONLY_TYPES = (
    PreviewRolloutPolicyRecord,
    PreviewPromotionDecisionRecord,
    PreviewPromotionDecisionStatusEventRecord,
    PreviewRolloutAuditEventRecord,
    PreviewShadowEvaluationRecord,
    PreviewLiveCanaryApprovalRecord,
    PreviewLiveCanaryApprovalStatusEventRecord,
    PreviewLiveCanaryLifecycleEventRecord,
    PreviewLiveCanaryExecutionRecord,
    PreviewLiveCanaryExecutionStatusEventRecord,
    PreviewCircuitBreakerPolicyRecord,
    PreviewCircuitBreakerStateRecord,
    PreviewBreakerMetricSampleRecord,
    PreviewBreakerAutoRollbackClaimRecord,
    PreviewRolloutAlertEventRecord,
    PreviewRolloutAlertStatusEventRecord,
)

_POINTER_IMMUTABLE_ATTRS = (
    "request_id",
    "pointer_version",
    "target_kind",
    "candidate_revision_id",
    "legacy_preview_relpath",
    "effective_tier",
    "effective_summary_id",
    "summary_sha256",
    "candidate_manifest_sha256",
    "previous_pointer_version",
    "pointer_action",
    "decision_id",
    "actor_id",
    "policy_revision",
    "created_at",
    "pointer_sha256",
)


@event.listens_for(Session, "before_flush")
def _protect_rollout_history(session, _flush_context, _instances):
    if any(isinstance(row, _STRICT_APPEND_ONLY_TYPES) for row in session.dirty):
        raise ValueError("Phase 7A rollout history is append-only")
    if any(isinstance(row, _STRICT_APPEND_ONLY_TYPES) for row in session.deleted):
        raise ValueError("Phase 7A rollout history is append-only")
    if any(
        isinstance(row, PreviewServingPointerVersionRecord) for row in session.deleted
    ):
        raise ValueError("Phase 7A serving pointer history cannot be deleted")
    for row in session.dirty:
        if not isinstance(row, PreviewServingPointerVersionRecord):
            continue
        for attr in _POINTER_IMMUTABLE_ATTRS:
            hist = getattr(row, "_sa_instance_state").attrs[attr].history
            if hist.has_changes():
                raise ValueError(
                    "Phase 7A serving pointer rows only allow is_current updates"
                )


__all__ = [
    "PreviewBreakerAutoRollbackClaimRecord",
    "PreviewBreakerMetricSampleRecord",
    "PreviewCircuitBreakerPolicyRecord",
    "PreviewCircuitBreakerStateRecord",
    "PreviewLiveCanaryApprovalRecord",
    "PreviewLiveCanaryApprovalStatusEventRecord",
    "PreviewLiveCanaryLifecycleEventRecord",
    "PreviewLiveCanaryExecutionRecord",
    "PreviewLiveCanaryExecutionStatusEventRecord",
    "PreviewLiveCanaryExecutionClaimRecord",
    "PreviewPromotionDecisionRecord",
    "PreviewPromotionDecisionStatusEventRecord",
    "PreviewRolloutAlertEventRecord",
    "PreviewRolloutAlertStatusEventRecord",
    "PreviewRolloutAuditEventRecord",
    "PreviewRolloutPolicyRecord",
    "PreviewServingPointerVersionRecord",
    "PreviewShadowEvaluationRecord",
]
