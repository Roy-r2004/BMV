"""Commercial Expanded Preview request lifecycle (append-only history)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Session

from app.infrastructure.db.base import Base

EXPANDED_PREVIEW_STATUSES = (
    "requested",
    "approved",
    "rejected",
    "generation_started",
    "generation_completed",
    "generation_failed",
    "review_accepted",
    "review_rejected",
    "published",
)

OPEN_STATUSES = frozenset(
    {
        "requested",
        "approved",
        "generation_started",
        "generation_completed",
        "review_accepted",
    }
)


class ExpandedPreviewRequestRecord(Base):
    __tablename__ = "expanded_preview_requests"
    __table_args__ = (
        UniqueConstraint(
            "request_id",
            "idempotency_key",
            name="uq_expanded_preview_request_idempotency",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    expanded_preview_uuid = Column(String(36), nullable=False, unique=True, index=True)
    request_id = Column(Integer, ForeignKey("requests.id"), nullable=False, index=True)
    current_status = Column(String(64), nullable=False, index=True)
    customer_reason = Column(Text, nullable=True)
    requested_changes = Column(Text, nullable=True)
    contact_preference = Column(String(128), nullable=True)
    idempotency_key = Column(String(128), nullable=False)
    request_sha256 = Column(String(64), nullable=False)
    actor_id = Column(String(128), nullable=False)
    accepted_tier_1_revision_id = Column(Integer, nullable=True)
    accepted_tier_1_visual_summary_id = Column(Integer, nullable=True)
    tier_2_candidate_revision_id = Column(Integer, nullable=True)
    tier_2_visual_summary_id = Column(Integer, nullable=True)
    published_candidate_revision_id = Column(Integer, nullable=True)
    generation_claim_token = Column(String(64), nullable=True)
    generation_started_at = Column(DateTime, nullable=True)
    generation_finished_at = Column(DateTime, nullable=True)
    generation_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ExpandedPreviewStatusEventRecord(Base):
    __tablename__ = "expanded_preview_status_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    expanded_preview_id = Column(
        Integer,
        ForeignKey("expanded_preview_requests.id"),
        nullable=False,
        index=True,
    )
    from_status = Column(String(64), nullable=True)
    to_status = Column(String(64), nullable=False)
    actor_id = Column(String(128), nullable=False)
    actor_role = Column(String(64), nullable=False)
    reason = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)
    event_sha256 = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ExpandedPreviewGenerationClaimRecord(Base):
    """Singleton-style claim row per expanded preview to prevent concurrent starts."""

    __tablename__ = "expanded_preview_generation_claims"
    __table_args__ = (
        UniqueConstraint(
            "expanded_preview_id",
            name="uq_expanded_preview_generation_claim",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    expanded_preview_id = Column(
        Integer,
        ForeignKey("expanded_preview_requests.id"),
        nullable=False,
    )
    claim_token = Column(String(64), nullable=False, unique=True)
    claimed_by_actor_id = Column(String(128), nullable=False)
    claimed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    heartbeat_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    released_at = Column(DateTime, nullable=True)
    active = Column(Boolean, nullable=False, default=True)


class ExpandedPreviewPublicationRecord(Base):
    __tablename__ = "expanded_preview_publications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    expanded_preview_id = Column(
        Integer,
        ForeignKey("expanded_preview_requests.id"),
        nullable=False,
        index=True,
    )
    request_id = Column(Integer, ForeignKey("requests.id"), nullable=False, index=True)
    candidate_revision_id = Column(Integer, nullable=False)
    publisher_actor_id = Column(String(128), nullable=False)
    publication_sha256 = Column(String(64), nullable=False, unique=True)
    customer_preview_path = Column(String(512), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


def _protect_expanded_preview_history(session: Session, _flush_context, _instances) -> None:
    for obj in session.dirty:
        if isinstance(
            obj,
            (ExpandedPreviewStatusEventRecord, ExpandedPreviewPublicationRecord),
        ):
            raise RuntimeError("expanded preview history rows are append-only")
    for obj in session.deleted:
        if isinstance(
            obj,
            (
                ExpandedPreviewStatusEventRecord,
                ExpandedPreviewPublicationRecord,
                ExpandedPreviewRequestRecord,
            ),
        ):
            raise RuntimeError("expanded preview history rows cannot be deleted")


event.listen(Session, "before_flush", _protect_expanded_preview_history)

__all__ = [
    "EXPANDED_PREVIEW_STATUSES",
    "OPEN_STATUSES",
    "ExpandedPreviewGenerationClaimRecord",
    "ExpandedPreviewPublicationRecord",
    "ExpandedPreviewRequestRecord",
    "ExpandedPreviewStatusEventRecord",
]
