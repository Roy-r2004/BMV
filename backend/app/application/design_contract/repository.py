"""Immutable persistence and exact cache lookup for Phase 2 artifacts."""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.application.appspec.repository import load_json_object
from app.application.appspec.source import canonical_json
from app.application.design_contract.cache import artifact_sha256
from app.domain.models.app_spec import AppSpecRevision
from app.domain.models.design_contract import DesignContractArtifactRecord
from app.domain.models.preview_contract import (
    CustomerSourceArtifact,
    PreviewTierArtifactRecord,
    ProductStrategyRevision,
)
from app.domain.schemas.design_contract import (
    DESIGN_CONTRACT_POLICY_REVISION,
    DesignArtifactRef,
    DesignContractRefs,
    DesignStageMetrics,
    DesignValidationReport,
)


@dataclass(frozen=True)
class PersistedDesignArtifact:
    row: DesignContractArtifactRecord
    reused: bool


def design_artifact_ref(
    row: DesignContractArtifactRecord,
) -> DesignArtifactRef:
    return DesignArtifactRef(
        id=row.id,
        artifact_kind=row.artifact_kind,
        schema_version=row.schema_version,
        sha256=row.artifact_sha256,
    )


def cache_hit_metrics(
    row: DesignContractArtifactRecord,
    *,
    latency_ms: int,
) -> DesignStageMetrics:
    return DesignStageMetrics(
        stage=row.artifact_kind,
        effective_model=row.effective_model,
        provider=row.provider,
        model_family=row.model_family,
        prompt_revision=row.prompt_revision,
        cache_hit=True,
        provider_call_count=0,
        validation_retry_count=0,
        validation_retry_reasons=(),
        transport_retry_count=0,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        cost_usd=0.0,
        latency_ms=max(0, latency_ms),
    )


class DesignContractRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_cache(
        self,
        *,
        request_id: int,
        artifact_kind: str,
        cache_key: str,
    ) -> DesignContractArtifactRecord | None:
        return (
            self.db.query(DesignContractArtifactRecord)
            .filter(
                DesignContractArtifactRecord.request_id == request_id,
                DesignContractArtifactRecord.artifact_kind == artifact_kind,
                DesignContractArtifactRecord.cache_key == cache_key,
            )
            .first()
        )

    def _validate_contract_refs(
        self,
        refs: DesignContractRefs,
    ) -> tuple[
        CustomerSourceArtifact,
        ProductStrategyRevision,
        AppSpecRevision,
        tuple[
            PreviewTierArtifactRecord,
            PreviewTierArtifactRecord,
            PreviewTierArtifactRecord,
        ],
    ]:
        source = self.db.get(
            CustomerSourceArtifact,
            refs.customer_source_ref.id,
        )
        seed = self.db.get(
            ProductStrategyRevision,
            refs.product_strategy_seed_ref.id,
        )
        app_spec = self.db.get(AppSpecRevision, refs.app_spec_ref.id)
        tier_rows = tuple(
            self.db.get(PreviewTierArtifactRecord, ref.id)
            for ref in refs.tier_refs
        )
        if (
            source is None
            or seed is None
            or app_spec is None
            or any(row is None for row in tier_rows)
        ):
            raise ValueError("Design contract references must resolve.")
        typed_tiers = tuple(tier_rows)
        if any(
            row.request_id != refs.request_id
            for row in (source, seed, app_spec, *typed_tiers)
        ):
            raise ValueError(
                "Design contract references must belong to one request."
            )
        if (
            source.sha256 != refs.customer_source_ref.sha256
            or seed.strategy_sha256
            != refs.product_strategy_seed_ref.sha256
            or seed.revision != refs.product_strategy_seed_ref.revision
            or app_spec.app_spec_sha256 != refs.app_spec_ref.sha256
            or app_spec.revision != refs.app_spec_ref.revision
            or app_spec.schema_version != refs.app_spec_ref.schema_version
        ):
            raise ValueError("Design contract reference hashes do not match.")
        for ref, row in zip(refs.tier_refs, typed_tiers):
            if (
                row.tier != ref.tier
                or row.artifact_sha256 != ref.sha256
                or row.selection_policy_revision
                != ref.selection_policy_revision
                or row.app_spec_revision_id != app_spec.id
            ):
                raise ValueError("Design tier reference does not match storage.")
        return source, seed, app_spec, typed_tiers

    def stage_artifact(
        self,
        *,
        artifact_kind: str,
        artifact: BaseModel,
        refs: DesignContractRefs,
        cache_key: str,
        prompt_revision: str,
        metrics: DesignStageMetrics,
        validation: DesignValidationReport,
        parent_artifact_id: int | None,
    ) -> PersistedDesignArtifact:
        if metrics.stage != artifact_kind:
            raise ValueError("Stage metrics must match artifact kind.")
        if metrics.cache_hit:
            raise ValueError("Cache-hit metrics cannot create artifacts.")
        if not validation.passed:
            raise ValueError("Invalid design artifacts cannot be persisted.")
        _, _, _, tier_rows = self._validate_contract_refs(refs)
        parent = (
            self.db.get(DesignContractArtifactRecord, parent_artifact_id)
            if parent_artifact_id is not None
            else None
        )
        if parent_artifact_id is not None and (
            parent is None or parent.request_id != refs.request_id
        ):
            raise ValueError("Design artifact parent must belong to the request.")
        expected_parent_kind = {
            "product_strategy_v2": None,
            "information_architecture": "product_strategy_v2",
            "design_dna": "information_architecture",
        }[artifact_kind]
        if (
            expected_parent_kind is None
            and parent is not None
        ) or (
            expected_parent_kind is not None
            and (
                parent is None
                or parent.artifact_kind != expected_parent_kind
            )
        ):
            raise ValueError("Design artifact parent chain is invalid.")

        payload = artifact.model_dump(mode="json")
        artifact_json = canonical_json(payload)
        digest = artifact_sha256(artifact)
        validation_json = canonical_json(validation.model_dump(mode="json"))
        existing = self.find_cache(
            request_id=refs.request_id,
            artifact_kind=artifact_kind,
            cache_key=cache_key,
        )
        if existing is not None:
            if (
                existing.parent_artifact_id != parent_artifact_id
                or existing.artifact_json != artifact_json
                or existing.artifact_sha256 != digest
                or not existing.validation_passed
                or load_json_object(existing.validation_json)
                != validation.model_dump(mode="json")
            ):
                raise ValueError(
                    "Existing design cache row does not exactly match."
                )
            return PersistedDesignArtifact(existing, reused=True)

        row = DesignContractArtifactRecord(
            request_id=refs.request_id,
            artifact_kind=artifact_kind,
            schema_version=str(payload.get("schema_version") or ""),
            policy_revision=DESIGN_CONTRACT_POLICY_REVISION,
            prompt_revision=prompt_revision,
            effective_model=metrics.effective_model,
            provider=metrics.provider,
            model_family=metrics.model_family,
            source_artifact_id=refs.customer_source_ref.id,
            product_strategy_seed_id=refs.product_strategy_seed_ref.id,
            app_spec_revision_id=refs.app_spec_ref.id,
            tier_1_artifact_id=tier_rows[0].id,
            tier_2_artifact_id=tier_rows[1].id,
            tier_3_artifact_id=tier_rows[2].id,
            parent_artifact_id=parent_artifact_id,
            cache_key=cache_key,
            artifact_json=artifact_json,
            artifact_sha256=digest,
            validation_json=validation_json,
            validation_passed=True,
            provider_call_count=metrics.provider_call_count,
            validation_retry_count=metrics.validation_retry_count,
            validation_retry_reasons_json=canonical_json(
                list(metrics.validation_retry_reasons)
            ),
            transport_retry_count=metrics.transport_retry_count,
            prompt_tokens=metrics.prompt_tokens,
            completion_tokens=metrics.completion_tokens,
            total_tokens=metrics.total_tokens,
            cost_usd=metrics.cost_usd,
            latency_ms=metrics.latency_ms,
        )
        self.db.add(row)
        self.db.flush()
        return PersistedDesignArtifact(row, reused=False)

    def validate_cached_row_refs(
        self,
        row: DesignContractArtifactRecord,
        *,
        refs: DesignContractRefs,
    ) -> None:
        _, _, _, tier_rows = self._validate_contract_refs(refs)
        if (
            row.request_id != refs.request_id
            or row.source_artifact_id != refs.customer_source_ref.id
            or row.product_strategy_seed_id
            != refs.product_strategy_seed_ref.id
            or row.app_spec_revision_id != refs.app_spec_ref.id
            or row.tier_1_artifact_id != tier_rows[0].id
            or row.tier_2_artifact_id != tier_rows[1].id
            or row.tier_3_artifact_id != tier_rows[2].id
        ):
            raise ValueError("Cached design artifact references are corrupt.")

    def load_artifact_json(
        self,
        row: DesignContractArtifactRecord,
    ) -> dict:
        payload = load_json_object(row.artifact_json)
        if not payload:
            raise ValueError("Cached design artifact JSON is invalid.")
        return payload


__all__ = [
    "DesignContractRepository",
    "PersistedDesignArtifact",
    "cache_hit_metrics",
    "design_artifact_ref",
]
