"""Append-only Phase 3B candidate artifacts and immutable revisions."""
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


class CandidateArtifactRecord(Base):
    __tablename__ = "candidate_artifacts"
    __table_args__ = (
        CheckConstraint(
            "artifact_kind IN "
            "('foundation','data_exports','business_components','pages',"
            "'routes','validation')",
            name="ck_candidate_artifact_kind",
        ),
        UniqueConstraint(
            "request_id",
            "artifact_kind",
            "cache_key",
            name="uq_candidate_artifact_request_kind_cache",
        ),
        Index(
            "ix_candidate_artifact_request_kind_created",
            "request_id",
            "artifact_kind",
            "created_at",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(
        Integer,
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    artifact_kind = Column(String(40), nullable=False, index=True)
    schema_version = Column(String(32), nullable=False)
    policy_revision = Column(String(64), nullable=False)
    prompt_revision = Column(String(64), nullable=False)
    effective_model = Column(String(240), nullable=False)
    provider = Column(String(80), nullable=False)
    model_family = Column(String(80), nullable=False)
    parent_artifact_id = Column(
        Integer,
        ForeignKey("candidate_artifacts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    cache_key = Column(String(64), nullable=False, index=True)
    upstream_manifest_sha256 = Column(String(64), nullable=False, index=True)
    artifact_json = Column(Text, nullable=False)
    artifact_sha256 = Column(String(64), nullable=False, index=True)
    validation_json = Column(Text, nullable=False, default="{}")
    validation_passed = Column(Boolean, nullable=False, default=False)
    cacheable = Column(Boolean, nullable=False, default=True)
    provider_call_count = Column(Integer, nullable=False, default=0)
    repair_call_count = Column(Integer, nullable=False, default=0)
    repair_reason = Column(Text, nullable=True)
    transport_retry_count = Column(Integer, nullable=False, default=0)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CandidateRevisionRecord(Base):
    __tablename__ = "candidate_revisions"
    __table_args__ = (
        CheckConstraint(
            "target_tier = 1",
            name="ck_candidate_revision_target_tier",
        ),
        CheckConstraint(
            "status IN "
            "('candidate_generated','candidate_contract_failed',"
            "'candidate_build_pending','candidate_failed')",
            name="ck_candidate_revision_status",
        ),
        UniqueConstraint(
            "request_id",
            "revision",
            name="uq_candidate_revision_request_revision",
        ),
        UniqueConstraint(
            "revision_uuid",
            name="uq_candidate_revision_uuid",
        ),
        Index(
            "ix_candidate_revision_request_created",
            "request_id",
            "created_at",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    revision_uuid = Column(String(36), nullable=False, index=True)
    request_id = Column(
        Integer,
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision = Column(Integer, nullable=False)
    target_tier = Column(Integer, nullable=False, default=1)
    status = Column(String(48), nullable=False)
    generator_version = Column(String(48), nullable=False)
    policy_revision = Column(String(64), nullable=False)
    upstream_manifest_json = Column(Text, nullable=False)
    upstream_manifest_sha256 = Column(String(64), nullable=False, index=True)
    dependency_lock_sha256 = Column(String(64), nullable=False)
    model_manifest_json = Column(Text, nullable=False)
    workspace_relpath = Column(String(500), nullable=True, unique=True)
    file_manifest_json = Column(Text, nullable=False, default="[]")
    file_manifest_sha256 = Column(String(64), nullable=True)
    foundation_artifact_id = Column(
        Integer,
        ForeignKey("candidate_artifacts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    data_artifact_id = Column(
        Integer,
        ForeignKey("candidate_artifacts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    component_artifact_id = Column(
        Integer,
        ForeignKey("candidate_artifacts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    page_artifact_id = Column(
        Integer,
        ForeignKey("candidate_artifacts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    route_artifact_id = Column(
        Integer,
        ForeignKey("candidate_artifacts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    validation_artifact_id = Column(
        Integer,
        ForeignKey("candidate_artifacts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    failure_json = Column(Text, nullable=False, default="{}")
    provider_call_count = Column(Integer, nullable=False, default=0)
    repair_call_count = Column(Integer, nullable=False, default=0)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


__all__ = ["CandidateArtifactRecord", "CandidateRevisionRecord"]
