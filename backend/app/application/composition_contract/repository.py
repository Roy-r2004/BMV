"""Immutable Phase 3A persistence and exact cache lookup."""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.application.appspec.repository import load_json_object
from app.application.appspec.source import canonical_json
from app.application.composition_contract.cache import (
    composition_artifact_sha256,
)
from app.application.design_contract.repository import (
    DesignContractRepository,
)
from app.domain.models import (
    AppSpecRevision,
    CompositionContractArtifactRecord,
    CustomerSourceArtifact,
    DesignContractArtifactRecord,
    PreviewTierArtifactRecord,
)
from app.domain.schemas.composition_contract import (
    COMPOSITION_CONTRACT_POLICY_REVISION,
    CompositionArtifactRef,
    CompositionContractRefs,
    CompositionStageMetrics,
    CompositionValidationReport,
)


@dataclass(frozen=True)
class PersistedCompositionArtifact:
    row: CompositionContractArtifactRecord
    reused: bool


def composition_artifact_ref(
    row: CompositionContractArtifactRecord,
) -> CompositionArtifactRef:
    return CompositionArtifactRef(
        id=row.id,
        artifact_kind=row.artifact_kind,
        schema_version=row.schema_version,
        sha256=row.artifact_sha256,
    )


def composition_cache_hit_metrics(
    row: CompositionContractArtifactRecord,
    *,
    latency_ms: int,
) -> CompositionStageMetrics:
    return CompositionStageMetrics(
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


class CompositionContractRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_cache(
        self,
        *,
        request_id: int,
        artifact_kind: str,
        cache_key: str,
    ) -> CompositionContractArtifactRecord | None:
        return (
            self.db.query(CompositionContractArtifactRecord)
            .filter(
                CompositionContractArtifactRecord.request_id == request_id,
                CompositionContractArtifactRecord.artifact_kind
                == artifact_kind,
                CompositionContractArtifactRecord.cache_key == cache_key,
            )
            .first()
        )

    def _validate_refs(
        self,
        refs: CompositionContractRefs,
    ) -> tuple[
        CustomerSourceArtifact,
        AppSpecRevision,
        tuple[
            PreviewTierArtifactRecord,
            PreviewTierArtifactRecord,
            PreviewTierArtifactRecord,
        ],
        tuple[
            DesignContractArtifactRecord,
            DesignContractArtifactRecord,
            DesignContractArtifactRecord,
        ],
    ]:
        design_refs = refs.design_contract_refs
        source = self.db.get(
            CustomerSourceArtifact,
            design_refs.customer_source_ref.id,
        )
        app_spec = self.db.get(
            AppSpecRevision,
            design_refs.app_spec_ref.id,
        )
        tiers = tuple(
            self.db.get(PreviewTierArtifactRecord, ref.id)
            for ref in design_refs.tier_refs
        )
        design_artifact_refs = (
            refs.product_strategy_v2_ref,
            refs.information_architecture_ref,
            refs.design_dna_ref,
        )
        design_rows = tuple(
            self.db.get(DesignContractArtifactRecord, ref.id)
            for ref in design_artifact_refs
        )
        if (
            source is None
            or app_spec is None
            or any(row is None for row in tiers)
            or any(row is None for row in design_rows)
        ):
            raise ValueError("Composition references must resolve.")
        typed_tiers = tuple(tiers)
        typed_design = tuple(design_rows)
        if any(
            row.request_id != refs.request_id
            for row in (
                source,
                app_spec,
                *typed_tiers,
                *typed_design,
            )
        ):
            raise ValueError(
                "Composition references must belong to one request."
            )
        if (
            source.sha256 != design_refs.customer_source_ref.sha256
            or app_spec.app_spec_sha256 != design_refs.app_spec_ref.sha256
        ):
            raise ValueError("Composition canonical hashes do not match.")
        for ref, row in zip(design_refs.tier_refs, typed_tiers):
            if (
                row.tier != ref.tier
                or row.artifact_sha256 != ref.sha256
                or row.selection_policy_revision
                != ref.selection_policy_revision
            ):
                raise ValueError("Composition tier reference is invalid.")
        for ref, row in zip(design_artifact_refs, typed_design):
            if (
                row.artifact_kind != ref.artifact_kind
                or row.schema_version != ref.schema_version
                or row.artifact_sha256 != ref.sha256
                or not row.validation_passed
            ):
                raise ValueError("Phase 2 artifact reference is invalid.")
            DesignContractRepository(self.db).validate_cached_row_refs(
                row,
                refs=design_refs,
            )
        return source, app_spec, typed_tiers, typed_design

    def stage_artifact(
        self,
        *,
        artifact_kind: str,
        artifact: BaseModel,
        refs: CompositionContractRefs,
        cache_key: str,
        metrics: CompositionStageMetrics,
        validation: CompositionValidationReport,
        parent_artifact_id: int | None,
    ) -> PersistedCompositionArtifact:
        if metrics.stage != artifact_kind:
            raise ValueError("Metrics stage must match artifact kind.")
        if metrics.cache_hit:
            raise ValueError("Cache-hit metrics cannot create artifacts.")
        if not validation.passed:
            raise ValueError("Invalid composition artifacts cannot persist.")
        _, _, tier_rows, design_rows = self._validate_refs(refs)
        parent = (
            self.db.get(
                CompositionContractArtifactRecord,
                parent_artifact_id,
            )
            if parent_artifact_id is not None
            else None
        )
        expected_parent = {
            "page_purpose_contract": None,
            "business_component_plan": "page_purpose_contract",
            "content_data_plan": "business_component_plan",
            "interaction_contract": "content_data_plan",
            "component_dependency_graph": "interaction_contract",
        }[artifact_kind]
        if (
            expected_parent is None
            and parent is not None
        ) or (
            expected_parent is not None
            and (
                parent is None
                or parent.request_id != refs.request_id
                or parent.artifact_kind != expected_parent
            )
        ):
            raise ValueError("Composition artifact parent chain is invalid.")
        payload = artifact.model_dump(mode="json")
        artifact_json = canonical_json(payload)
        digest = composition_artifact_sha256(artifact)
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
                    "Existing composition cache does not exactly match."
                )
            return PersistedCompositionArtifact(existing, reused=True)
        row = CompositionContractArtifactRecord(
            request_id=refs.request_id,
            artifact_kind=artifact_kind,
            target_tier=refs.target_tier,
            schema_version=str(payload.get("schema_version") or ""),
            policy_revision=COMPOSITION_CONTRACT_POLICY_REVISION,
            prompt_revision=metrics.prompt_revision,
            effective_model=metrics.effective_model,
            provider=metrics.provider,
            model_family=metrics.model_family,
            source_artifact_id=(
                refs.design_contract_refs.customer_source_ref.id
            ),
            app_spec_revision_id=(
                refs.design_contract_refs.app_spec_ref.id
            ),
            tier_1_artifact_id=tier_rows[0].id,
            tier_2_artifact_id=tier_rows[1].id,
            tier_3_artifact_id=tier_rows[2].id,
            product_strategy_v2_artifact_id=design_rows[0].id,
            information_architecture_artifact_id=design_rows[1].id,
            design_dna_artifact_id=design_rows[2].id,
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
        return PersistedCompositionArtifact(row=row, reused=False)

    def validate_cached_row_refs(
        self,
        row: CompositionContractArtifactRecord,
        *,
        refs: CompositionContractRefs,
    ) -> None:
        _, _, tiers, design_rows = self._validate_refs(refs)
        if (
            row.request_id != refs.request_id
            or row.target_tier != refs.target_tier
            or row.source_artifact_id
            != refs.design_contract_refs.customer_source_ref.id
            or row.app_spec_revision_id
            != refs.design_contract_refs.app_spec_ref.id
            or row.tier_1_artifact_id != tiers[0].id
            or row.tier_2_artifact_id != tiers[1].id
            or row.tier_3_artifact_id != tiers[2].id
            or row.product_strategy_v2_artifact_id != design_rows[0].id
            or row.information_architecture_artifact_id
            != design_rows[1].id
            or row.design_dna_artifact_id != design_rows[2].id
        ):
            raise ValueError("Cached composition references are corrupt.")

    @staticmethod
    def load_artifact_json(
        row: CompositionContractArtifactRecord,
    ) -> dict:
        payload = load_json_object(row.artifact_json)
        if not payload:
            raise ValueError("Cached composition JSON is invalid.")
        return payload


__all__ = [
    "CompositionContractRepository",
    "PersistedCompositionArtifact",
    "composition_artifact_ref",
    "composition_cache_hit_metrics",
]
