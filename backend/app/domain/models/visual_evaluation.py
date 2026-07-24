"""Append-only Phase 5 visual evaluation and refinement records."""
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
)

from app.infrastructure.db.base import Base


class CandidateVisualEvaluationAttemptRecord(Base):
    __tablename__ = "candidate_visual_evaluation_attempts"
    __table_args__ = (
        UniqueConstraint("attempt_uuid", name="uq_visual_attempt_uuid"),
        Index(
            "ix_visual_attempt_candidate_created",
            "candidate_revision_id",
            "created_at",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    attempt_uuid = Column(String(36), nullable=False, index=True)
    request_id = Column(Integer, ForeignKey("requests.id"), nullable=False, index=True)
    candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id"),
        nullable=False,
        index=True,
    )
    runtime_summary_id = Column(
        Integer,
        ForeignKey("candidate_validation_summaries.id"),
        nullable=False,
        index=True,
    )
    parent_attempt_id = Column(
        Integer,
        ForeignKey("candidate_visual_evaluation_attempts.id"),
        nullable=True,
    )
    subject = Column(String(16), nullable=False)
    evaluation_cache_key = Column(String(64), nullable=False, index=True)
    refs_json = Column(Text, nullable=False)
    refs_sha256 = Column(String(64), nullable=False)
    routing_json = Column(Text, nullable=False)
    routing_sha256 = Column(String(64), nullable=False)
    limits_json = Column(Text, nullable=False)
    limits_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class _VisualArtifactColumns:
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("requests.id"), nullable=False, index=True)
    candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id"),
        nullable=False,
        index=True,
    )
    visual_attempt_id = Column(
        Integer,
        ForeignKey("candidate_visual_evaluation_attempts.id"),
        nullable=False,
        index=True,
    )
    cache_key = Column(String(64), nullable=False, index=True)
    artifact_json = Column(Text, nullable=False)
    artifact_sha256 = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CandidateVisualEvidenceBundleRecord(_VisualArtifactColumns, Base):
    __tablename__ = "candidate_visual_evidence_bundles"
    grouping_manifest_sha256 = Column(String(64), nullable=False)
    screenshot_set_sha256 = Column(String(64), nullable=False, index=True)


class CandidateVisualHardGateResultRecord(_VisualArtifactColumns, Base):
    __tablename__ = "candidate_visual_hard_gate_results"
    passed = Column(Boolean, nullable=False)


class CandidateVisualScorecardRecord(_VisualArtifactColumns, Base):
    __tablename__ = "candidate_visual_scorecards"
    actor = Column(String(24), nullable=False)
    subject = Column(String(16), nullable=False)
    group_index = Column(Integer, nullable=True)
    effective_model = Column(String(240), nullable=False)
    provider = Column(String(80), nullable=False)
    model_family = Column(String(80), nullable=False)
    model_capability = Column(String(80), nullable=False)
    prompt_revision = Column(String(64), nullable=False)
    parameters_json = Column(Text, nullable=False)
    score_band_policy_revision = Column(String(64), nullable=False)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Integer, nullable=False, default=0)


class CandidateVisualFindingRecord(Base):
    __tablename__ = "candidate_visual_findings"
    __table_args__ = (
        UniqueConstraint(
            "visual_attempt_id",
            "finding_id",
            name="uq_visual_finding_attempt_id",
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("requests.id"), nullable=False, index=True)
    candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id"),
        nullable=False,
        index=True,
    )
    visual_attempt_id = Column(
        Integer,
        ForeignKey("candidate_visual_evaluation_attempts.id"),
        nullable=False,
        index=True,
    )
    finding_id = Column(String(120), nullable=False)
    source = Column(String(24), nullable=False)
    severity = Column(String(24), nullable=False)
    finding_json = Column(Text, nullable=False)
    finding_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CandidateVisualReviewerDecisionRecord(_VisualArtifactColumns, Base):
    __tablename__ = "candidate_visual_reviewer_decisions"
    recommendation = Column(String(16), nullable=False)
    effective_model = Column(String(240), nullable=False)
    provider = Column(String(80), nullable=False)
    model_family = Column(String(80), nullable=False)
    model_capability = Column(String(80), nullable=False)
    prompt_revision = Column(String(64), nullable=False)
    parameters_json = Column(Text, nullable=False)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Integer, nullable=False, default=0)


class CandidateBaselineComparisonRecord(_VisualArtifactColumns, Base):
    __tablename__ = "candidate_baseline_comparisons"
    mode = Column(String(24), nullable=False)
    baseline_identity_sha256 = Column(String(64), nullable=True)


class CandidateRefinementPlanRecord(_VisualArtifactColumns, Base):
    __tablename__ = "candidate_refinement_plans"
    repairability = Column(String(40), nullable=False)


class CandidateRefinementGenerationRecord(_VisualArtifactColumns, Base):
    __tablename__ = "candidate_refinement_generations"
    original_candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id"),
        nullable=False,
    )
    derived_candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id"),
        nullable=False,
    )
    refinement_model = Column(String(240), nullable=False)
    refinement_output_json = Column(Text, nullable=False)
    refinement_output_sha256 = Column(String(64), nullable=False)
    technical_repair_model = Column(String(240), nullable=True)
    technical_repair_output_json = Column(Text, nullable=True)
    technical_repair_output_sha256 = Column(String(64), nullable=True)
    refinement_call_count = Column(Integer, nullable=False, default=1)
    technical_repair_call_count = Column(Integer, nullable=False, default=0)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Integer, nullable=False, default=0)


class CandidateVisualSummaryRecord(_VisualArtifactColumns, Base):
    __tablename__ = "candidate_visual_summaries"
    __table_args__ = (
        CheckConstraint(
            "status IN "
            "('candidate_visual_accepted','candidate_visual_rejected',"
            "'candidate_refinement_failed')",
            name="ck_candidate_visual_summary_status",
        ),
        UniqueConstraint(
            "visual_attempt_id",
            name="uq_candidate_visual_summary_attempt",
        ),
    )
    status = Column(String(48), nullable=False, index=True)
    repairability = Column(String(40), nullable=False)
    acceptance_policy_revision = Column(String(64), nullable=False)
    score_band_policy_revision = Column(String(64), nullable=False)
    deterministic_acceptance_json = Column(Text, nullable=False)
    provider_call_count = Column(Integer, nullable=False, default=0)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Integer, nullable=False, default=0)


__all__ = [
    "CandidateBaselineComparisonRecord",
    "CandidateRefinementGenerationRecord",
    "CandidateRefinementPlanRecord",
    "CandidateVisualEvaluationAttemptRecord",
    "CandidateVisualEvidenceBundleRecord",
    "CandidateVisualFindingRecord",
    "CandidateVisualHardGateResultRecord",
    "CandidateVisualReviewerDecisionRecord",
    "CandidateVisualScorecardRecord",
    "CandidateVisualSummaryRecord",
]
