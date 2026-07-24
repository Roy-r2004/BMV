"""Load and verify the complete Phase 2 contract for Phase 3A."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.application.appspec.repository import load_json_object
from app.application.design_contract.cache import artifact_sha256
from app.application.design_contract.repository import (
    DesignContractRepository,
    design_artifact_ref,
)
from app.domain.models import (
    AppSpecRevision,
    CustomerSourceArtifact,
    DesignContractArtifactRecord,
    PreviewTierArtifactRecord,
)
from app.domain.schemas.app_spec import AppSpec
from app.domain.schemas.composition_contract import CompositionContractRefs
from app.domain.schemas.customer_source import CustomerSourceSnapshotV2
from app.domain.schemas.design_dna import DesignDNA
from app.domain.schemas.information_architecture import InformationArchitecture
from app.domain.schemas.preview_tier import PreviewTierArtifact
from app.domain.schemas.product_strategy import ProductStrategyV2


@dataclass(frozen=True)
class CompositionContext:
    refs: CompositionContractRefs
    source: CustomerSourceSnapshotV2
    app_spec: AppSpec
    tiers: tuple[
        PreviewTierArtifact,
        PreviewTierArtifact,
        PreviewTierArtifact,
    ]
    product_strategy_v2: ProductStrategyV2
    information_architecture: InformationArchitecture
    design_dna: DesignDNA
    design_rows: tuple[
        DesignContractArtifactRecord,
        DesignContractArtifactRecord,
        DesignContractArtifactRecord,
    ]

    @property
    def tier_1(self) -> PreviewTierArtifact:
        return self.tiers[0]


def _design_rows(
    db: Session,
    *,
    request_id: int,
    summary: dict[str, Any],
) -> tuple[
    DesignContractArtifactRecord,
    DesignContractArtifactRecord,
    DesignContractArtifactRecord,
]:
    ref_map = summary.get("design_artifact_refs") or {}
    kinds = (
        "product_strategy_v2",
        "information_architecture",
        "design_dna",
    )
    rows = tuple(
        db.get(
            DesignContractArtifactRecord,
            (ref_map.get(kind) or {}).get("id"),
        )
        for kind in kinds
    )
    if any(row is None for row in rows):
        raise ValueError("Phase 2 artifact references do not resolve.")
    typed = tuple(rows)
    if any(
        row.request_id != request_id or row.artifact_kind != kind
        for row, kind in zip(typed, kinds)
    ):
        raise ValueError("Phase 2 artifacts are cross-request or mis-typed.")
    if (
        typed[0].parent_artifact_id is not None
        or typed[1].parent_artifact_id != typed[0].id
        or typed[2].parent_artifact_id != typed[1].id
    ):
        raise ValueError("Phase 2 artifact parent chain is invalid.")
    for row, kind in zip(typed, kinds):
        ref = ref_map[kind]
        if (
            row.artifact_sha256 != ref.get("sha256")
            or row.schema_version != ref.get("schema_version")
            or not row.validation_passed
        ):
            raise ValueError("Phase 2 artifact provenance is inconsistent.")
    return typed


def load_composition_context(
    db: Session,
    *,
    request_id: int,
    phase2_result: dict[str, Any],
) -> CompositionContext:
    summary = dict(phase2_result.get("preview_contract") or {})
    if summary.get("status") != "design_contract_ready":
        raise ValueError("Phase 3A requires design_contract_ready.")
    rows = _design_rows(
        db,
        request_id=request_id,
        summary=summary,
    )
    strategy = ProductStrategyV2.model_validate(
        load_json_object(rows[0].artifact_json)
    )
    ia = InformationArchitecture.model_validate(
        load_json_object(rows[1].artifact_json)
    )
    dna = DesignDNA.model_validate(
        load_json_object(rows[2].artifact_json)
    )
    if (
        artifact_sha256(strategy) != rows[0].artifact_sha256
        or artifact_sha256(ia) != rows[1].artifact_sha256
        or artifact_sha256(dna) != rows[2].artifact_sha256
    ):
        raise ValueError("Phase 2 artifact JSON hash is corrupt.")
    if not (
        strategy.contract_refs
        == ia.contract_refs
        == dna.contract_refs
    ):
        raise ValueError("Phase 2 artifacts do not share canonical refs.")
    refs = CompositionContractRefs(
        request_id=request_id,
        target_tier=1,
        design_contract_refs=strategy.contract_refs,
        product_strategy_v2_ref=design_artifact_ref(rows[0]),
        information_architecture_ref=design_artifact_ref(rows[1]),
        design_dna_ref=design_artifact_ref(rows[2]),
    )
    repository = DesignContractRepository(db)
    for row in rows:
        repository.validate_cached_row_refs(
            row,
            refs=refs.design_contract_refs,
        )

    design_refs = refs.design_contract_refs
    source_row = db.get(
        CustomerSourceArtifact,
        design_refs.customer_source_ref.id,
    )
    app_spec_row = db.get(AppSpecRevision, design_refs.app_spec_ref.id)
    tier_rows = tuple(
        db.get(PreviewTierArtifactRecord, ref.id)
        for ref in design_refs.tier_refs
    )
    if (
        source_row is None
        or app_spec_row is None
        or any(row is None for row in tier_rows)
    ):
        raise ValueError("Canonical Phase 1 references do not resolve.")
    source = CustomerSourceSnapshotV2.model_validate(
        load_json_object(source_row.snapshot_json)
    )
    app_spec = AppSpec.model_validate(
        load_json_object(app_spec_row.app_spec_json)
    )
    tiers = tuple(
        PreviewTierArtifact.model_validate(
            load_json_object(row.artifact_json)
        )
        for row in tier_rows
    )
    if tuple(tier.tier for tier in tiers) != (1, 2, 3):
        raise ValueError("Composition context requires ordered Tier 1/2/3.")
    return CompositionContext(
        refs=refs,
        source=source,
        app_spec=app_spec,
        tiers=tiers,
        product_strategy_v2=strategy,
        information_architecture=ia,
        design_dna=dna,
        design_rows=rows,
    )


__all__ = ["CompositionContext", "load_composition_context"]
