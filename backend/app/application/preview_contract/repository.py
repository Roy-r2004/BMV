"""Persistence for immutable v2 customer-source and strategy artifacts."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.application.appspec.repository import load_json_object
from app.application.appspec.source import canonical_json, source_sha256
from app.domain.models.app_spec import AppSpecRevision
from app.domain.models.preview_contract import (
    CustomerSourceArtifact,
    PRODUCT_STRATEGY_STATUS_ACCEPTED,
    PreviewTierArtifactRecord,
    ProductStrategyRevision,
)
from app.domain.schemas.customer_source import CustomerSourceSnapshotV2
from app.domain.schemas.preview_tier import (
    PreviewTierArtifact,
    TierValidationReport,
)
from app.domain.schemas.product_strategy import ProductStrategy


@dataclass(frozen=True)
class PreviewContractInputs:
    source: CustomerSourceArtifact
    strategy: ProductStrategyRevision


@dataclass(frozen=True)
class PersistedTierSet:
    tier_1: PreviewTierArtifactRecord
    tier_2: PreviewTierArtifactRecord
    tier_3: PreviewTierArtifactRecord
    reused: bool


class PartialTierSetError(ValueError):
    """Some, but not all, cumulative artifacts already exist."""


class TierPolicyRevisionMismatch(ValueError):
    """Persisted artifacts were selected under another policy revision."""


def strategy_sha256(strategy: ProductStrategy) -> str:
    payload = strategy.model_dump(mode="json")
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def tier_artifact_sha256(artifact: PreviewTierArtifact) -> str:
    payload = artifact.model_dump(mode="json")
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def tier_artifact_ref(row: PreviewTierArtifactRecord) -> dict[str, object]:
    return {
        "id": row.id,
        "tier": row.tier,
        "sha256": row.artifact_sha256,
        "selection_policy_revision": row.selection_policy_revision,
    }


class PreviewContractRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _next_strategy_revision(self, request_id: int) -> int:
        current = (
            self.db.query(func.max(ProductStrategyRevision.revision))
            .filter(ProductStrategyRevision.request_id == request_id)
            .scalar()
        )
        return int(current or 0) + 1

    def stage_inputs(
        self,
        *,
        source: CustomerSourceSnapshotV2,
        strategy: ProductStrategy,
    ) -> PreviewContractInputs:
        """Flush source + strategy in one transaction without committing.

        The caller owns the outer transaction. Any failure while staging the
        second artifact rolls back both newly inserted rows.
        """

        source_payload = source.model_dump(mode="json")
        source_digest = source_sha256(source_payload)
        if strategy.source_sha256 != source_digest:
            raise ValueError(
                "ProductStrategy source_sha256 must match the immutable source."
            )
        request_id = source.request_id
        source_json = canonical_json(source_payload)
        strategy_json = canonical_json(strategy.model_dump(mode="json"))
        strategy_digest = strategy_sha256(strategy)

        try:
            source_row = (
                self.db.query(CustomerSourceArtifact)
                .filter(
                    CustomerSourceArtifact.request_id == request_id,
                    CustomerSourceArtifact.sha256 == source_digest,
                )
                .first()
            )
            if source_row is None:
                source_row = CustomerSourceArtifact(
                    request_id=request_id,
                    schema_version=source.source_schema_version,
                    snapshot_json=source_json,
                    sha256=source_digest,
                )
                self.db.add(source_row)
                self.db.flush()
            elif source_row.snapshot_json != source_json:
                raise ValueError(
                    "Customer source hash collision detected; refusing overwrite."
                )

            strategy_row = (
                self.db.query(ProductStrategyRevision)
                .filter(
                    ProductStrategyRevision.request_id == request_id,
                    ProductStrategyRevision.source_artifact_id == source_row.id,
                    ProductStrategyRevision.strategy_sha256 == strategy_digest,
                )
                .first()
            )
            if strategy_row is None:
                strategy_row = ProductStrategyRevision(
                    request_id=request_id,
                    revision=self._next_strategy_revision(request_id),
                    source_artifact_id=source_row.id,
                    source_sha256=source_digest,
                    schema_version=strategy.schema_version,
                    origin=strategy.origin,
                    status=PRODUCT_STRATEGY_STATUS_ACCEPTED,
                    strategy_json=strategy_json,
                    strategy_sha256=strategy_digest,
                    deterministic_validation_json=canonical_json(
                        {
                            "passed": True,
                            "schema": "ProductStrategy",
                            "schema_version": strategy.schema_version,
                            "source_sha256_matches": True,
                        }
                    ),
                    validation_passed=True,
                    generation_metadata_json=canonical_json(
                        {
                            "projection": "deterministic",
                            "provider_calls": 0,
                        }
                    ),
                )
                self.db.add(strategy_row)
                self.db.flush()
            elif strategy_row.strategy_json != strategy_json:
                raise ValueError(
                    "ProductStrategy hash collision detected; refusing overwrite."
                )
        except Exception:
            self.db.rollback()
            raise

        return PreviewContractInputs(source=source_row, strategy=strategy_row)

    def list_tiers(self, app_spec_revision_id: int) -> list[PreviewTierArtifactRecord]:
        return (
            self.db.query(PreviewTierArtifactRecord)
            .filter(
                PreviewTierArtifactRecord.app_spec_revision_id
                == app_spec_revision_id
            )
            .order_by(PreviewTierArtifactRecord.tier.asc())
            .all()
        )

    def _validate_tier_foreign_references(
        self,
        tiers: tuple[PreviewTierArtifact, PreviewTierArtifact, PreviewTierArtifact],
    ) -> tuple[CustomerSourceArtifact, ProductStrategyRevision, AppSpecRevision]:
        first = tiers[0]
        source = (
            self.db.query(CustomerSourceArtifact)
            .filter(CustomerSourceArtifact.id == first.customer_source_ref.id)
            .first()
        )
        strategy = (
            self.db.query(ProductStrategyRevision)
            .filter(ProductStrategyRevision.id == first.product_strategy_ref.id)
            .first()
        )
        app_spec = (
            self.db.query(AppSpecRevision)
            .filter(AppSpecRevision.id == first.app_spec_ref.id)
            .first()
        )
        if source is None or strategy is None or app_spec is None:
            raise ValueError("Tier references must resolve to persisted artifacts.")
        if any(
            row.request_id != first.request_id
            for row in (source, strategy, app_spec)
        ):
            raise ValueError("Tier references must belong to the same request.")
        if (
            source.sha256 != first.customer_source_ref.sha256
            or strategy.strategy_sha256 != first.product_strategy_ref.sha256
            or strategy.revision != first.product_strategy_ref.revision
            or app_spec.source_sha256 != source.sha256
            or app_spec.app_spec_sha256 != first.app_spec_ref.sha256
            or app_spec.revision != first.app_spec_ref.revision
            or app_spec.schema_version != first.app_spec_ref.schema_version
        ):
            raise ValueError("Tier reference hashes or revisions do not match.")
        if strategy.source_artifact_id != source.id:
            raise ValueError("ProductStrategy does not reference the tier source.")
        app_spec_metadata = load_json_object(
            app_spec.generation_metadata_json
        )
        if (
            app_spec_metadata.get("customer_source_artifact_id") != source.id
            or app_spec_metadata.get("product_strategy_revision_id")
            != strategy.id
            or app_spec_metadata.get("product_strategy_sha256")
            != strategy.strategy_sha256
        ):
            raise ValueError(
                "AppSpec provenance does not reference the tier source and "
                "strategy."
            )
        for tier in tiers[1:]:
            if (
                tier.request_id != first.request_id
                or tier.customer_source_ref != first.customer_source_ref
                or tier.product_strategy_ref != first.product_strategy_ref
                or tier.app_spec_ref != first.app_spec_ref
            ):
                raise ValueError("All tiers must reference one canonical contract.")
        return source, strategy, app_spec

    def stage_tiers(
        self,
        *,
        tiers: tuple[
            PreviewTierArtifact,
            PreviewTierArtifact,
            PreviewTierArtifact,
        ],
        validation: TierValidationReport,
    ) -> PersistedTierSet:
        """Stage all three immutable rows or roll back the transaction."""

        if [tier.tier for tier in tiers] != [1, 2, 3]:
            raise ValueError("Tier persistence requires ordered Tier 1, 2, and 3.")
        if not validation.passed:
            raise ValueError("Invalid tiers cannot be persisted.")
        source, strategy, app_spec = self._validate_tier_foreign_references(tiers)
        policy_revision = tiers[0].selection_policy_revision
        if any(
            tier.selection_policy_revision != policy_revision for tier in tiers
        ):
            raise ValueError("All tiers must use one selection-policy revision.")

        existing = self.list_tiers(app_spec.id)
        if existing:
            if len(existing) != 3 or [row.tier for row in existing] != [1, 2, 3]:
                raise PartialTierSetError(
                    "A partial existing tier set cannot be reused or repaired."
                )
            if any(
                row.selection_policy_revision != policy_revision
                for row in existing
            ):
                raise TierPolicyRevisionMismatch(
                    "Existing tiers use a different selection-policy revision."
                )
            expected_parent_ids = [None, existing[0].id, existing[1].id]
            validation_payload = validation.model_dump(mode="json")
            for row, artifact, parent_id in zip(
                existing,
                tiers,
                expected_parent_ids,
            ):
                expected_json = canonical_json(artifact.model_dump(mode="json"))
                if (
                    row.parent_tier_artifact_id != parent_id
                    or row.artifact_json != expected_json
                    or row.artifact_sha256 != tier_artifact_sha256(artifact)
                    or not row.validation_passed
                    or load_json_object(row.validation_json)
                    != validation_payload
                ):
                    raise ValueError(
                        "Existing tiers do not exactly match the deterministic "
                        "artifacts and cannot be silently reused."
                    )
            return PersistedTierSet(*existing, reused=True)

        rows: list[PreviewTierArtifactRecord] = []
        validation_json = canonical_json(validation.model_dump(mode="json"))
        try:
            parent_id: int | None = None
            for artifact in tiers:
                artifact_json = canonical_json(
                    artifact.model_dump(mode="json")
                )
                row = PreviewTierArtifactRecord(
                    request_id=artifact.request_id,
                    tier=artifact.tier,
                    schema_version=artifact.tier_schema_version,
                    selection_policy_revision=policy_revision,
                    source_artifact_id=source.id,
                    product_strategy_revision_id=strategy.id,
                    app_spec_revision_id=app_spec.id,
                    parent_tier_artifact_id=parent_id,
                    artifact_json=artifact_json,
                    artifact_sha256=tier_artifact_sha256(artifact),
                    validation_json=validation_json,
                    validation_passed=True,
                )
                self.db.add(row)
                self.db.flush()
                rows.append(row)
                parent_id = row.id
        except Exception:
            self.db.rollback()
            raise
        return PersistedTierSet(*rows, reused=False)


__all__ = [
    "PreviewContractInputs",
    "PreviewContractRepository",
    "PartialTierSetError",
    "PersistedTierSet",
    "TierPolicyRevisionMismatch",
    "strategy_sha256",
    "tier_artifact_ref",
    "tier_artifact_sha256",
]
