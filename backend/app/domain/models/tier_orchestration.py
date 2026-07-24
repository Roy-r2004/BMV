"""Append-only Phase 6A Tier 2 orchestration records.

These rows link existing Phase 3B/4/5 artifacts; they never duplicate build,
browser, screenshot, critic, or refinement internals.
"""
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
)
from sqlalchemy.orm import Session

from app.infrastructure.db.base import Base


class _TierLineageColumns:
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(
        Integer,
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    accepted_tier_1_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    accepted_tier_1_visual_summary_id = Column(
        Integer,
        ForeignKey("candidate_visual_summaries.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    target_tier = Column(Integer, nullable=False, default=2)
    tier_closure_sha256 = Column(String(64), nullable=False, index=True)
    delta_sha256 = Column(String(64), nullable=False, index=True)
    generation_policy_revision = Column(String(64), nullable=False)
    orchestration_attempt_id = Column(
        Integer,
        ForeignKey(
            "candidate_tier_orchestration_attempts.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CandidateTierOrchestrationAttemptRecord(Base):
    __tablename__ = "candidate_tier_orchestration_attempts"
    __table_args__ = (
        CheckConstraint("target_tier = 2", name="ck_tier_attempt_target"),
        CheckConstraint(
            "status IN ('started','succeeded','failed')",
            name="ck_tier_attempt_status",
        ),
        UniqueConstraint("attempt_uuid", name="uq_tier_attempt_uuid"),
        UniqueConstraint(
            "request_id",
            "resume_identity_sha256",
            name="uq_tier_attempt_resume_identity",
        ),
        Index(
            "ix_tier_attempt_request_created",
            "request_id",
            "created_at",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    attempt_uuid = Column(String(36), nullable=False, index=True)
    request_id = Column(
        Integer,
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    accepted_tier_1_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    accepted_tier_1_visual_summary_id = Column(
        Integer,
        ForeignKey("candidate_visual_summaries.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    target_tier = Column(Integer, nullable=False, default=2)
    tier_closure_sha256 = Column(String(64), nullable=False, index=True)
    delta_sha256 = Column(String(64), nullable=False, index=True)
    generation_policy_revision = Column(String(64), nullable=False)
    resume_identity_sha256 = Column(String(64), nullable=False, index=True)
    accepted_manifest_sha256 = Column(String(64), nullable=False)
    upstream_refs_json = Column(Text, nullable=False)
    upstream_refs_sha256 = Column(String(64), nullable=False)
    budget_json = Column(Text, nullable=False)
    budget_sha256 = Column(String(64), nullable=False)
    staging_workspace_relpath = Column(String(500), nullable=True)
    status = Column(String(16), nullable=False, default="started")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CandidateTierExtensionManifestRecord(_TierLineageColumns, Base):
    __tablename__ = "candidate_tier_extension_manifests"
    __table_args__ = (
        CheckConstraint("target_tier = 2", name="ck_tier_manifest_target"),
        UniqueConstraint(
            "orchestration_attempt_id",
            name="uq_tier_manifest_attempt",
        ),
    )
    manifest_json = Column(Text, nullable=False)
    manifest_sha256 = Column(String(64), nullable=False, index=True)
    page_purpose_sha256 = Column(String(64), nullable=False)
    business_component_plan_sha256 = Column(String(64), nullable=False)
    content_data_plan_sha256 = Column(String(64), nullable=False)
    interaction_contract_sha256 = Column(String(64), nullable=False)
    dependency_graph_sha256 = Column(String(64), nullable=False)


class CandidateLowerTierPreservationAuditRecord(_TierLineageColumns, Base):
    __tablename__ = "candidate_lower_tier_preservation_audits"
    __table_args__ = (
        CheckConstraint("target_tier = 2", name="ck_tier_audit_target"),
        UniqueConstraint(
            "orchestration_attempt_id",
            name="uq_tier_audit_attempt",
        ),
    )
    tier_extension_manifest_id = Column(
        Integer,
        ForeignKey("candidate_tier_extension_manifests.id", ondelete="RESTRICT"),
        nullable=False,
    )
    audit_json = Column(Text, nullable=False)
    audit_sha256 = Column(String(64), nullable=False, index=True)
    passed = Column(Boolean, nullable=False)


class CandidateTierGenerationResultRecord(_TierLineageColumns, Base):
    __tablename__ = "candidate_tier_generation_results"
    __table_args__ = (
        CheckConstraint("target_tier = 2", name="ck_tier_generation_target"),
        UniqueConstraint(
            "orchestration_attempt_id",
            name="uq_tier_generation_attempt",
        ),
    )
    preservation_audit_id = Column(
        Integer,
        ForeignKey(
            "candidate_lower_tier_preservation_audits.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    derived_candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    result_json = Column(Text, nullable=False)
    result_sha256 = Column(String(64), nullable=False, index=True)
    passed = Column(Boolean, nullable=False)
    provider_call_count = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Integer, nullable=False, default=0)


class CandidateTierValidationResultRecord(_TierLineageColumns, Base):
    __tablename__ = "candidate_tier_validation_results"
    __table_args__ = (
        CheckConstraint("target_tier = 2", name="ck_tier_validation_target"),
        UniqueConstraint(
            "orchestration_attempt_id",
            name="uq_tier_validation_attempt",
        ),
    )
    preservation_audit_id = Column(
        Integer,
        ForeignKey(
            "candidate_lower_tier_preservation_audits.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    derived_candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    phase4_validation_summary_id = Column(
        Integer,
        ForeignKey("candidate_validation_summaries.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    result_json = Column(Text, nullable=False)
    result_sha256 = Column(String(64), nullable=False)
    passed = Column(Boolean, nullable=False)


class CandidateTierVisualOutcomeRecord(_TierLineageColumns, Base):
    __tablename__ = "candidate_tier_visual_outcomes"
    __table_args__ = (
        CheckConstraint("target_tier = 2", name="ck_tier_visual_target"),
        UniqueConstraint(
            "orchestration_attempt_id",
            name="uq_tier_visual_attempt",
        ),
    )
    preservation_audit_id = Column(
        Integer,
        ForeignKey(
            "candidate_lower_tier_preservation_audits.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    derived_candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id", ondelete="RESTRICT"),
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
        index=True,
    )
    baseline_comparison_id = Column(
        Integer,
        ForeignKey("candidate_baseline_comparisons.id", ondelete="RESTRICT"),
        nullable=True,
    )
    outcome_json = Column(Text, nullable=False)
    outcome_sha256 = Column(String(64), nullable=False)
    passed = Column(Boolean, nullable=False)


class CandidateEffectiveTierSummaryRecord(_TierLineageColumns, Base):
    __tablename__ = "candidate_effective_tier_summaries"
    __table_args__ = (
        CheckConstraint("target_tier = 2", name="ck_effective_tier_target"),
        CheckConstraint(
            "status IN "
            "('tier_2_accepted','tier_2_failed_serving_tier_1')",
            name="ck_effective_tier_status",
        ),
        CheckConstraint(
            "highest_accepted_tier IN (1, 2)",
            name="ck_highest_accepted_tier",
        ),
        UniqueConstraint(
            "orchestration_attempt_id",
            name="uq_effective_tier_attempt",
        ),
        Index(
            "ix_effective_tier_request_created",
            "request_id",
            "created_at",
        ),
    )
    tier_extension_manifest_id = Column(
        Integer,
        ForeignKey("candidate_tier_extension_manifests.id", ondelete="RESTRICT"),
        nullable=False,
    )
    preservation_audit_id = Column(
        Integer,
        ForeignKey(
            "candidate_lower_tier_preservation_audits.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    tier_generation_result_id = Column(
        Integer,
        ForeignKey("candidate_tier_generation_results.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tier_validation_result_id = Column(
        Integer,
        ForeignKey("candidate_tier_validation_results.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tier_visual_outcome_id = Column(
        Integer,
        ForeignKey("candidate_tier_visual_outcomes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    derived_candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id", ondelete="RESTRICT"),
        nullable=True,
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
    status = Column(String(48), nullable=False, index=True)
    highest_accepted_tier = Column(Integer, nullable=False)
    last_accepted_candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    summary_json = Column(Text, nullable=False)
    summary_sha256 = Column(String(64), nullable=False, index=True)


_APPEND_ONLY_TYPES = (
    CandidateTierOrchestrationAttemptRecord,
    CandidateTierExtensionManifestRecord,
    CandidateLowerTierPreservationAuditRecord,
    CandidateTierGenerationResultRecord,
    CandidateTierValidationResultRecord,
    CandidateTierVisualOutcomeRecord,
    CandidateEffectiveTierSummaryRecord,
)


@event.listens_for(Session, "before_flush")
def _protect_tier_orchestration_history(session, _flush_context, _instances):
    if any(isinstance(row, _APPEND_ONLY_TYPES) for row in session.dirty):
        raise ValueError("Phase 6 orchestration history is append-only")
    if any(isinstance(row, _APPEND_ONLY_TYPES) for row in session.deleted):
        raise ValueError("Phase 6 orchestration history is append-only")


__all__ = [
    "CandidateEffectiveTierSummaryRecord",
    "CandidateLowerTierPreservationAuditRecord",
    "CandidateTierExtensionManifestRecord",
    "CandidateTierGenerationResultRecord",
    "CandidateTierOrchestrationAttemptRecord",
    "CandidateTierValidationResultRecord",
    "CandidateTierVisualOutcomeRecord",
]
