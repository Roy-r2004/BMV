"""Load and verify the complete accepted Phase 3A contract."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.application.appspec.repository import load_json_object
from app.application.composition_contract.cache import (
    composition_artifact_sha256,
)
from app.application.composition_contract.context import (
    CompositionContext,
    load_composition_context,
)
from app.application.composition_contract.repository import (
    CompositionContractRepository,
    composition_artifact_ref,
)
from app.domain.models import CompositionContractArtifactRecord
from app.domain.schemas.business_component_plan import BusinessComponentPlan
from app.domain.schemas.component_dependency_graph import (
    ComponentDependencyGraph,
)
from app.domain.schemas.content_data_plan import ContentDataPlan
from app.domain.schemas.interaction_contract import InteractionContract
from app.domain.schemas.page_purpose_contract import PagePurposeContract
from app.domain.schemas.preview_candidate import CandidateUpstreamRefs


@dataclass(frozen=True)
class CandidateContext:
    composition: CompositionContext
    refs: CandidateUpstreamRefs
    page_purpose: PagePurposeContract
    business_components: BusinessComponentPlan
    content_data: ContentDataPlan
    interactions: InteractionContract
    dependency_graph: ComponentDependencyGraph
    rows: tuple[
        CompositionContractArtifactRecord,
        CompositionContractArtifactRecord,
        CompositionContractArtifactRecord,
        CompositionContractArtifactRecord,
        CompositionContractArtifactRecord,
    ]


_KINDS_AND_SCHEMAS = (
    ("page_purpose_contract", PagePurposeContract),
    ("business_component_plan", BusinessComponentPlan),
    ("content_data_plan", ContentDataPlan),
    ("interaction_contract", InteractionContract),
    ("component_dependency_graph", ComponentDependencyGraph),
)


def load_candidate_context(
    db: Session,
    *,
    request_id: int,
    phase3a_result: dict[str, Any],
) -> CandidateContext:
    summary = dict(phase3a_result.get("preview_contract") or {})
    if summary.get("status") != "composition_contract_ready":
        raise ValueError("Phase 3B requires composition_contract_ready.")
    ref_map = summary.get("composition_artifact_refs") or {}
    rows = tuple(
        db.get(
            CompositionContractArtifactRecord,
            (ref_map.get(kind) or {}).get("id"),
        )
        for kind, _schema in _KINDS_AND_SCHEMAS
    )
    if any(row is None for row in rows):
        raise ValueError("Phase 3A candidate references do not resolve.")
    typed_rows = tuple(rows)
    if any(
        row.request_id != request_id or row.artifact_kind != kind
        for row, (kind, _schema) in zip(typed_rows, _KINDS_AND_SCHEMAS)
    ):
        raise ValueError("Phase 3A candidate references are cross-request.")
    if (
        typed_rows[0].parent_artifact_id is not None
        or any(
            row.parent_artifact_id != typed_rows[index - 1].id
            for index, row in enumerate(typed_rows[1:], start=1)
        )
    ):
        raise ValueError("Phase 3A artifact parent chain is invalid.")

    artifacts = tuple(
        schema.model_validate(load_json_object(row.artifact_json))
        for row, (_kind, schema) in zip(typed_rows, _KINDS_AND_SCHEMAS)
    )
    for row, artifact, (kind, _schema) in zip(
        typed_rows,
        artifacts,
        _KINDS_AND_SCHEMAS,
    ):
        ref = ref_map[kind]
        if (
            not row.validation_passed
            or row.artifact_sha256 != ref.get("sha256")
            or row.schema_version != ref.get("schema_version")
            or composition_artifact_sha256(artifact)
            != row.artifact_sha256
        ):
            raise ValueError("Phase 3A artifact provenance is corrupt.")

    phase2_summary = dict(summary)
    phase2_summary["status"] = "design_contract_ready"
    composition = load_composition_context(
        db,
        request_id=request_id,
        phase2_result={"preview_contract": phase2_summary},
    )
    page, components, content, interactions, graph = artifacts
    if not (
        page.contract_refs
        == components.contract_refs
        == content.contract_refs
        == interactions.contract_refs
        == graph.contract_refs
        == composition.refs
    ):
        raise ValueError("Phase 3A artifacts do not share canonical refs.")
    refs = CandidateUpstreamRefs(
        request_id=request_id,
        target_tier=1,
        composition_contract_refs=composition.refs,
        page_purpose_ref=composition_artifact_ref(typed_rows[0]),
        business_component_plan_ref=composition_artifact_ref(typed_rows[1]),
        content_data_plan_ref=composition_artifact_ref(typed_rows[2]),
        interaction_contract_ref=composition_artifact_ref(typed_rows[3]),
        component_dependency_graph_ref=composition_artifact_ref(
            typed_rows[4]
        ),
    )
    repository = CompositionContractRepository(db)
    for row in typed_rows:
        repository.validate_cached_row_refs(row, refs=composition.refs)
    return CandidateContext(
        composition=composition,
        refs=refs,
        page_purpose=page,
        business_components=components,
        content_data=content,
        interactions=interactions,
        dependency_graph=graph,
        rows=typed_rows,
    )


__all__ = ["CandidateContext", "load_candidate_context"]
