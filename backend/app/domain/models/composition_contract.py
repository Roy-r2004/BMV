"""Persisted immutable Phase 3A composition-contract artifacts."""
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


class CompositionContractArtifactRecord(Base):
    __tablename__ = "composition_contract_artifacts"
    __table_args__ = (
        CheckConstraint(
            "artifact_kind IN "
            "('page_purpose_contract','business_component_plan',"
            "'content_data_plan','interaction_contract',"
            "'component_dependency_graph')",
            name="ck_composition_contract_artifact_kind",
        ),
        CheckConstraint(
            "target_tier = 1",
            name="ck_composition_contract_target_tier",
        ),
        UniqueConstraint(
            "request_id",
            "artifact_kind",
            "cache_key",
            name="uq_composition_contract_request_kind_cache",
        ),
        Index(
            "ix_composition_contract_request_kind_created",
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
    artifact_kind = Column(String(48), nullable=False, index=True)
    target_tier = Column(Integer, nullable=False, default=1)
    schema_version = Column(String(32), nullable=False)
    policy_revision = Column(String(64), nullable=False)
    prompt_revision = Column(String(64), nullable=False)
    effective_model = Column(String(240), nullable=False)
    provider = Column(String(80), nullable=False)
    model_family = Column(String(80), nullable=False)

    source_artifact_id = Column(
        Integer,
        ForeignKey("customer_source_artifacts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    app_spec_revision_id = Column(
        Integer,
        ForeignKey("app_spec_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    tier_1_artifact_id = Column(
        Integer,
        ForeignKey("preview_tier_artifacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tier_2_artifact_id = Column(
        Integer,
        ForeignKey("preview_tier_artifacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tier_3_artifact_id = Column(
        Integer,
        ForeignKey("preview_tier_artifacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_strategy_v2_artifact_id = Column(
        Integer,
        ForeignKey("design_contract_artifacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    information_architecture_artifact_id = Column(
        Integer,
        ForeignKey("design_contract_artifacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    design_dna_artifact_id = Column(
        Integer,
        ForeignKey("design_contract_artifacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    parent_artifact_id = Column(
        Integer,
        ForeignKey("composition_contract_artifacts.id", ondelete="RESTRICT"),
        nullable=True,
    )

    cache_key = Column(String(64), nullable=False, index=True)
    artifact_json = Column(Text, nullable=False)
    artifact_sha256 = Column(String(64), nullable=False, index=True)
    validation_json = Column(Text, nullable=False)
    validation_passed = Column(Boolean, nullable=False, default=False)

    provider_call_count = Column(Integer, nullable=False, default=0)
    validation_retry_count = Column(Integer, nullable=False, default=0)
    validation_retry_reasons_json = Column(Text, nullable=False, default="[]")
    transport_retry_count = Column(Integer, nullable=False, default=0)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


__all__ = ["CompositionContractArtifactRecord"]
