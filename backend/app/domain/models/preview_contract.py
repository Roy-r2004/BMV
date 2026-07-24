"""Persisted immutable source and strategy artifacts for preview generator v2."""
from datetime import datetime

from sqlalchemy import (
    Boolean,
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


__all__ = [
    "CustomerSourceArtifact",
    "PRODUCT_STRATEGY_STATUS_ACCEPTED",
    "ProductStrategyRevision",
]
