"""Persisted immutable source and strategy artifacts for preview generator v2."""
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


PRODUCT_STRATEGY_STATUS_ACCEPTED = "accepted"


class CustomerSourceArtifact(Base):
    __tablename__ = "customer_source_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "request_id",
            "sha256",
            name="uq_customer_source_request_sha",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(
        Integer,
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    schema_version = Column(String(32), nullable=False)
    snapshot_json = Column(Text, nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ProductStrategyRevision(Base):
    __tablename__ = "product_strategy_revisions"
    __table_args__ = (
        UniqueConstraint(
            "request_id",
            "revision",
            name="uq_product_strategy_request_revision",
        ),
        UniqueConstraint(
            "request_id",
            "source_artifact_id",
            "strategy_sha256",
            name="uq_product_strategy_request_source_sha",
        ),
        Index(
            "ix_product_strategy_request_status_revision",
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
    source_artifact_id = Column(
        Integer,
        ForeignKey("customer_source_artifacts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_sha256 = Column(String(64), nullable=False, index=True)
    schema_version = Column(String(32), nullable=False)
    origin = Column(String(64), nullable=False)
    status = Column(
        String(24),
        nullable=False,
        default=PRODUCT_STRATEGY_STATUS_ACCEPTED,
        index=True,
    )
    strategy_json = Column(Text, nullable=False)
    strategy_sha256 = Column(String(64), nullable=False, index=True)
    deterministic_validation_json = Column(Text, nullable=False)
    validation_passed = Column(Boolean, nullable=False, default=False)
    generation_metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    validated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PreviewTierArtifactRecord(Base):
    __tablename__ = "preview_tier_artifacts"
    __table_args__ = (
        CheckConstraint("tier >= 1 AND tier <= 3", name="ck_preview_tier_range"),
        UniqueConstraint(
            "app_spec_revision_id",
            "tier",
            name="uq_preview_tier_app_spec_tier",
        ),
        Index(
            "ix_preview_tier_request_app_spec_tier",
            "request_id",
            "app_spec_revision_id",
            "tier",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(
        Integer,
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tier = Column(Integer, nullable=False)
    schema_version = Column(String(32), nullable=False)
    selection_policy_revision = Column(String(64), nullable=False)
    source_artifact_id = Column(
        Integer,
        ForeignKey("customer_source_artifacts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    product_strategy_revision_id = Column(
        Integer,
        ForeignKey("product_strategy_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    app_spec_revision_id = Column(
        Integer,
        ForeignKey("app_spec_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    parent_tier_artifact_id = Column(
        Integer,
        ForeignKey("preview_tier_artifacts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    artifact_json = Column(Text, nullable=False)
    artifact_sha256 = Column(String(64), nullable=False, index=True)
    validation_json = Column(Text, nullable=False)
    validation_passed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


__all__ = [
    "CustomerSourceArtifact",
    "PRODUCT_STRATEGY_STATUS_ACCEPTED",
    "PreviewTierArtifactRecord",
    "ProductStrategyRevision",
]
