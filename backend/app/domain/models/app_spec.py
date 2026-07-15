"""Persisted, revisioned canonical AppSpec artifacts.

AppSpec revisions deliberately live outside ``Request.generated_pages``.  The
latter is a mutable preview bundle, while an accepted AppSpec is the immutable
product contract and must remain auditable after preview regeneration/refine.
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from app.infrastructure.db.base import Base


APP_SPEC_STATUS_ACCEPTED = "accepted"
APP_SPEC_STATUS_REJECTED = "rejected"


class AppSpecRevision(Base):
    """One immutable AppSpec generation/validation attempt for a request."""

    __tablename__ = "app_spec_revisions"
    __table_args__ = (
        UniqueConstraint(
            "request_id",
            "revision",
            name="uq_app_spec_request_revision",
        ),
        Index(
            "ix_app_spec_request_status_revision",
            "request_id",
            "status",
            "revision",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(
        Integer,
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision = Column(Integer, nullable=False)

    schema_version = Column(String(32), nullable=False)
    status = Column(String(24), nullable=False, default=APP_SPEC_STATUS_REJECTED, index=True)

    # Source and AppSpec are canonical JSON strings.  Keeping the exact bytes
    # used for hashing makes provenance stable across SQLite and Postgres.
    source_snapshot_json = Column(Text, nullable=False)
    source_sha256 = Column(String(64), nullable=False, index=True)
    app_spec_json = Column(Text, nullable=False)
    app_spec_sha256 = Column(String(64), nullable=False, index=True)

    deterministic_validation_json = Column(Text, nullable=False)
    validation_passed = Column(Boolean, nullable=False, default=False)
    semantic_coverage_json = Column(Text, nullable=False)
    coverage_passed = Column(Boolean, nullable=False, default=False)
    coverage_score = Column(Integer, nullable=True)

    generation_metadata_json = Column(Text, nullable=False, default="{}")
    parent_revision_id = Column(
        Integer,
        ForeignKey("app_spec_revisions.id"),
        nullable=True,
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    validated_at = Column(DateTime, nullable=True)
