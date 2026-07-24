"""Append-only Phase 4 runtime-validation records."""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.infrastructure.db.base import Base


class CandidateRuntimeValidationAttemptRecord(Base):
    __tablename__ = "candidate_runtime_validation_attempts"
    __table_args__ = (
        UniqueConstraint("attempt_uuid", name="uq_runtime_attempt_uuid"),
        Index(
            "ix_runtime_attempt_candidate_created",
            "candidate_revision_id",
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
    candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_sequence = Column(Integer, nullable=False)
    cache_identity = Column(String(64), nullable=False, index=True)
    candidate_manifest_sha256 = Column(String(64), nullable=False, index=True)
    dependency_lock_sha256 = Column(String(64), nullable=False)
    source_candidate_sha256_before = Column(String(64), nullable=False)
    runtime_policy_revision = Column(String(64), nullable=False)
    tool_versions_json = Column(Text, nullable=False)
    tool_versions_sha256 = Column(String(64), nullable=False)
    limits_json = Column(Text, nullable=False)
    limits_sha256 = Column(String(64), nullable=False)
    workspace_relpath = Column(String(500), nullable=False)
    resumed_from_attempt_id = Column(
        Integer,
        ForeignKey("candidate_runtime_validation_attempts.id"),
        nullable=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CandidateBuildAttemptRecord(Base):
    __tablename__ = "candidate_build_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('build_passed','build_failed')",
            name="ck_candidate_build_attempt_status",
        ),
        Index(
            "ix_candidate_build_cache_created",
            "build_cache_key",
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
    candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    runtime_attempt_id = Column(
        Integer,
        ForeignKey(
            "candidate_runtime_validation_attempts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    attempt_sequence = Column(Integer, nullable=False)
    parent_build_attempt_id = Column(
        Integer,
        ForeignKey("candidate_build_attempts.id"),
        nullable=True,
    )
    status = Column(String(32), nullable=False)
    build_cache_key = Column(String(64), nullable=False, index=True)
    dist_cache_key = Column(String(64), nullable=False, index=True)
    build_hash = Column(String(64), nullable=False, index=True)
    dist_manifest_sha256 = Column(String(64), nullable=False)
    workspace_relpath = Column(String(500), nullable=False)
    result_json = Column(Text, nullable=False)
    result_sha256 = Column(String(64), nullable=False)
    passed = Column(Boolean, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CandidateRouteResultRecord(Base):
    __tablename__ = "candidate_route_results"
    __table_args__ = (
        UniqueConstraint(
            "runtime_attempt_id",
            "page_id",
            "viewport",
            name="uq_candidate_route_attempt_page_viewport",
        ),
        Index(
            "ix_candidate_route_cache_created",
            "cache_key",
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
    candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    runtime_attempt_id = Column(
        Integer,
        ForeignKey(
            "candidate_runtime_validation_attempts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    build_attempt_id = Column(
        Integer,
        ForeignKey("candidate_build_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_id = Column(String(120), nullable=False)
    route = Column(String(300), nullable=False)
    viewport = Column(String(24), nullable=False)
    cache_key = Column(String(64), nullable=False, index=True)
    passed = Column(Boolean, nullable=False)
    result_json = Column(Text, nullable=False)
    result_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CandidateJourneyResultRecord(Base):
    __tablename__ = "candidate_journey_results"
    __table_args__ = (
        UniqueConstraint(
            "runtime_attempt_id",
            "journey_id",
            "action_id",
            name="uq_candidate_journey_attempt_action",
        ),
        Index(
            "ix_candidate_journey_cache_created",
            "cache_key",
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
    candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    runtime_attempt_id = Column(
        Integer,
        ForeignKey(
            "candidate_runtime_validation_attempts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    build_attempt_id = Column(
        Integer,
        ForeignKey("candidate_build_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    journey_id = Column(String(120), nullable=False)
    action_id = Column(String(120), nullable=False)
    cache_key = Column(String(64), nullable=False, index=True)
    passed = Column(Boolean, nullable=False)
    result_json = Column(Text, nullable=False)
    result_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CandidateAccessibilityFindingRecord(Base):
    __tablename__ = "candidate_accessibility_findings"
    __table_args__ = (
        UniqueConstraint(
            "runtime_attempt_id",
            "page_id",
            "viewport",
            name="uq_candidate_accessibility_attempt_route",
        ),
        Index(
            "ix_candidate_accessibility_cache_created",
            "cache_key",
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
    candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    runtime_attempt_id = Column(
        Integer,
        ForeignKey(
            "candidate_runtime_validation_attempts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    build_attempt_id = Column(
        Integer,
        ForeignKey("candidate_build_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_id = Column(String(120), nullable=False)
    route = Column(String(300), nullable=False)
    viewport = Column(String(24), nullable=False)
    scanner_name = Column(String(120), nullable=False)
    scanner_policy_revision = Column(String(64), nullable=False)
    cache_key = Column(String(64), nullable=False, index=True)
    passed = Column(Boolean, nullable=False)
    result_json = Column(Text, nullable=False)
    result_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CandidateScreenshotRecord(Base):
    __tablename__ = "candidate_screenshots"
    __table_args__ = (
        UniqueConstraint(
            "runtime_attempt_id",
            "page_id",
            "viewport",
            name="uq_candidate_screenshot_attempt_route",
        ),
        Index(
            "ix_candidate_screenshot_cache_created",
            "cache_key",
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
    candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    runtime_attempt_id = Column(
        Integer,
        ForeignKey(
            "candidate_runtime_validation_attempts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    build_attempt_id = Column(
        Integer,
        ForeignKey("candidate_build_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_id = Column(String(120), nullable=False)
    route = Column(String(300), nullable=False)
    viewport = Column(String(24), nullable=False)
    cache_key = Column(String(64), nullable=False, index=True)
    relative_path = Column(String(500), nullable=False)
    screenshot_sha256 = Column(String(64), nullable=False)
    evidence_json = Column(Text, nullable=False)
    evidence_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CandidateValidationSummaryRecord(Base):
    __tablename__ = "candidate_validation_summaries"
    __table_args__ = (
        CheckConstraint(
            "status IN "
            "('candidate_runtime_validated','candidate_build_failed',"
            "'candidate_runtime_failed')",
            name="ck_candidate_validation_summary_status",
        ),
        UniqueConstraint(
            "runtime_attempt_id",
            name="uq_candidate_validation_summary_attempt",
        ),
        Index(
            "ix_candidate_validation_summary_candidate_created",
            "candidate_revision_id",
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
    candidate_revision_id = Column(
        Integer,
        ForeignKey("candidate_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    runtime_attempt_id = Column(
        Integer,
        ForeignKey(
            "candidate_runtime_validation_attempts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    build_attempt_id = Column(
        Integer,
        ForeignKey("candidate_build_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(String(48), nullable=False, index=True)
    candidate_manifest_sha256 = Column(String(64), nullable=False)
    build_hash = Column(String(64), nullable=False)
    source_candidate_sha256_before = Column(String(64), nullable=False)
    source_candidate_sha256_after = Column(String(64), nullable=False)
    summary_json = Column(Text, nullable=False)
    summary_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


__all__ = [
    "CandidateAccessibilityFindingRecord",
    "CandidateBuildAttemptRecord",
    "CandidateJourneyResultRecord",
    "CandidateRouteResultRecord",
    "CandidateRuntimeValidationAttemptRecord",
    "CandidateScreenshotRecord",
    "CandidateValidationSummaryRecord",
]
