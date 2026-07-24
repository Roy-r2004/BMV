"""Persistence for immutable v2 customer-source and strategy artifacts."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.application.appspec.source import canonical_json, source_sha256
from app.domain.models.preview_contract import (
    CustomerSourceArtifact,
    PRODUCT_STRATEGY_STATUS_ACCEPTED,
    ProductStrategyRevision,
)
from app.domain.schemas.customer_source import CustomerSourceSnapshotV2
from app.domain.schemas.product_strategy import ProductStrategy


@dataclass(frozen=True)
class PreviewContractInputs:
    source: CustomerSourceArtifact
    strategy: ProductStrategyRevision


def strategy_sha256(strategy: ProductStrategy) -> str:
    payload = strategy.model_dump(mode="json")
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


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


__all__ = [
    "PreviewContractInputs",
    "PreviewContractRepository",
    "strategy_sha256",
]
