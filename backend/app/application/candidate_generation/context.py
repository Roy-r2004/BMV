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
from app.domain.models import CandidateTierExtensionManifestRecord
from app.domain.schemas.business_component_plan import BusinessComponentPlan
from app.domain.schemas.component_dependency_graph import (
    ComponentDependencyGraph,
)
from app.domain.schemas.content_data_plan import ContentDataPlan
from app.domain.schemas.interaction_contract import InteractionContract
from app.domain.schemas.page_purpose_contract import PagePurposeContract
from app.domain.schemas.preview_candidate import CandidateUpstreamRefs
from app.domain.schemas.tier_orchestration import (
    Tier2ExtensionContracts,
    Tier3ExtensionContracts,
)


@dataclass(frozen=True)
class CandidateContext:
    composition: CompositionContext
    refs: CandidateUpstreamRefs
    page_purpose: PagePurposeContract
    business_components: BusinessComponentPlan
    content_data: ContentDataPlan
    interactions: InteractionContract
    dependency_graph: ComponentDependencyGraph
    rows: tuple[CompositionContractArtifactRecord, ...]


_KINDS_AND_SCHEMAS = (
    ("page_purpose_contract", PagePurposeContract),
    ("business_component_plan", BusinessComponentPlan),
    ("content_data_plan", ContentDataPlan),
    ("interaction_contract", InteractionContract),
    ("component_dependency_graph", ComponentDependencyGraph),
)


def load_tier_2_extension_context(
    db: Session,
    *,
    request_id: int,
    extension_ref: dict[str, Any],
) -> CandidateContext:
    row = db.get(
        CandidateTierExtensionManifestRecord,
        extension_ref.get("id"),
    )
    if (
        row is None
        or row.request_id != request_id
        or row.target_tier != 2
        or row.manifest_sha256 != extension_ref.get("sha256")
    ):
        raise ValueError("Accepted Tier 2 extension reference is invalid")
    contracts = Tier2ExtensionContracts.model_validate(
        load_json_object(row.manifest_json)
    )
    if (
        composition_artifact_sha256(contracts) != row.manifest_sha256
        or contracts.projection.tier_2_closure_sha256
        != row.tier_closure_sha256
        or contracts.projection.delta_sha256 != row.delta_sha256
    ):
        raise ValueError("Accepted Tier 2 extension is corrupt")
    refs = contracts.page_purpose.contract_refs
    design_summary = {
        "status": "design_contract_ready",
        "design_artifact_refs": {
            "product_strategy_v2": (
                refs.product_strategy_v2_ref.model_dump(mode="json")
            ),
            "information_architecture": (
                refs.information_architecture_ref.model_dump(mode="json")
            ),
            "design_dna": refs.design_dna_ref.model_dump(mode="json"),
        },
    }
    composition = load_composition_context(
        db,
        request_id=request_id,
        phase2_result={"preview_contract": design_summary},
    )
    upstream = CandidateUpstreamRefs(
        request_id=request_id,
        target_tier=2,
        composition_contract_refs=refs,
        page_purpose_ref={
            "id": row.orchestration_attempt_id,
            "artifact_kind": "page_purpose_contract",
            "schema_version": contracts.page_purpose.schema_version,
            "sha256": contracts.page_purpose_sha256,
        },
        business_component_plan_ref={
            "id": row.orchestration_attempt_id,
            "artifact_kind": "business_component_plan",
            "schema_version": contracts.business_components.schema_version,
            "sha256": contracts.business_components_sha256,
        },
        content_data_plan_ref={
            "id": row.orchestration_attempt_id,
            "artifact_kind": "content_data_plan",
            "schema_version": contracts.content_data.schema_version,
            "sha256": contracts.content_data_sha256,
        },
        interaction_contract_ref={
            "id": row.orchestration_attempt_id,
            "artifact_kind": "interaction_contract",
            "schema_version": contracts.interactions.schema_version,
            "sha256": contracts.interactions_sha256,
        },
        component_dependency_graph_ref={
            "id": row.orchestration_attempt_id,
            "artifact_kind": "component_dependency_graph",
            "schema_version": contracts.dependency_graph.schema_version,
            "sha256": contracts.dependency_graph_sha256,
        },
    )
    return CandidateContext(
        composition=composition,
        refs=upstream,
        page_purpose=contracts.page_purpose,
        business_components=contracts.business_components,
        content_data=contracts.content_data,
        interactions=contracts.interactions,
        dependency_graph=contracts.dependency_graph,
        rows=(),
    )


def load_candidate_context(
    db: Session,
    *,
    request_id: int,
    phase3a_result: dict[str, Any],
) -> CandidateContext:
    summary = dict(phase3a_result.get("preview_contract") or {})
    if (
        int(summary.get("target_tier") or 1) == 2
        and summary.get("cumulative_extension_context") is True
    ):
        return load_tier_2_extension_context(
            db,
            request_id=request_id,
            extension_ref=summary.get("tier_extension_manifest_ref") or {},
        )
    if (
        int(summary.get("target_tier") or 1) in (2, 3)
        or summary.get("tier_extension_manifest_ref")
    ):
        return _load_tier_candidate_context(
            db,
            request_id=request_id,
            summary=summary,
        )
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


def _load_tier_candidate_context(
    db: Session,
    *,
    request_id: int,
    summary: dict[str, Any],
) -> CandidateContext:
    target_tier = int(summary.get("target_tier") or 2)
    if target_tier not in (2, 3):
        raise ValueError("Cumulative candidate target tier is invalid")
    extension_ref = summary.get("tier_extension_manifest_ref") or {}
    row = db.get(
        CandidateTierExtensionManifestRecord,
        extension_ref.get("id"),
    )
    if (
        row is None
        or row.request_id != request_id
        or row.target_tier != target_tier
        or row.manifest_sha256 != extension_ref.get("sha256")
    ):
        raise ValueError(
            f"Tier {target_tier} extension manifest reference is invalid"
        )
    contract_type = (
        Tier3ExtensionContracts
        if target_tier == 3
        else Tier2ExtensionContracts
    )
    contracts = contract_type.model_validate(load_json_object(row.manifest_json))
    closure_sha = (
        contracts.projection.tier_3_closure_sha256
        if target_tier == 3
        else contracts.projection.tier_2_closure_sha256
    )
    if (
        composition_artifact_sha256(contracts) != row.manifest_sha256
        or contracts.projection.request_id != request_id
        or closure_sha != row.tier_closure_sha256
        or contracts.projection.delta_sha256 != row.delta_sha256
        or contracts.page_purpose_sha256 != row.page_purpose_sha256
        or contracts.business_components_sha256
        != row.business_component_plan_sha256
        or contracts.content_data_sha256 != row.content_data_plan_sha256
        or contracts.interactions_sha256 != row.interaction_contract_sha256
        or contracts.dependency_graph_sha256
        != row.dependency_graph_sha256
    ):
        raise ValueError(
            f"Tier {target_tier} extension manifest provenance is corrupt"
        )

    legacy_summary = dict(summary)
    legacy_summary.pop("tier_extension_manifest_ref", None)
    if target_tier == 3:
        lower_ref = (
            summary.get("accepted_tier_2_extension_manifest_ref") or {}
        )
        lower_row = db.get(
            CandidateTierExtensionManifestRecord,
            lower_ref.get("id"),
        )
        if (
            lower_row is None
            or lower_row.request_id != request_id
            or lower_row.target_tier != 2
            or lower_row.manifest_sha256 != lower_ref.get("sha256")
        ):
            raise ValueError(
                "Accepted Tier 2 extension reference is invalid"
            )
        lower_contracts = Tier2ExtensionContracts.model_validate(
            load_json_object(lower_row.manifest_json)
        )
        lower_refs = lower_contracts.page_purpose.contract_refs
        design_summary = {
            "status": "design_contract_ready",
            "design_artifact_refs": {
                "product_strategy_v2": (
                    lower_refs.product_strategy_v2_ref.model_dump(
                        mode="json"
                    )
                ),
                "information_architecture": (
                    lower_refs.information_architecture_ref.model_dump(
                        mode="json"
                    )
                ),
                "design_dna": lower_refs.design_dna_ref.model_dump(
                    mode="json"
                ),
            },
        }
        composition = load_composition_context(
            db,
            request_id=request_id,
            phase2_result={"preview_contract": design_summary},
        )
        legacy_refs = CandidateUpstreamRefs(
            request_id=request_id,
            target_tier=2,
            composition_contract_refs=lower_refs,
            page_purpose_ref={
                "id": lower_row.orchestration_attempt_id,
                "artifact_kind": "page_purpose_contract",
                "schema_version": lower_contracts.page_purpose.schema_version,
                "sha256": lower_contracts.page_purpose_sha256,
            },
            business_component_plan_ref={
                "id": lower_row.orchestration_attempt_id,
                "artifact_kind": "business_component_plan",
                "schema_version": (
                    lower_contracts.business_components.schema_version
                ),
                "sha256": lower_contracts.business_components_sha256,
            },
            content_data_plan_ref={
                "id": lower_row.orchestration_attempt_id,
                "artifact_kind": "content_data_plan",
                "schema_version": lower_contracts.content_data.schema_version,
                "sha256": lower_contracts.content_data_sha256,
            },
            interaction_contract_ref={
                "id": lower_row.orchestration_attempt_id,
                "artifact_kind": "interaction_contract",
                "schema_version": lower_contracts.interactions.schema_version,
                "sha256": lower_contracts.interactions_sha256,
            },
            component_dependency_graph_ref={
                "id": lower_row.orchestration_attempt_id,
                "artifact_kind": "component_dependency_graph",
                "schema_version": (
                    lower_contracts.dependency_graph.schema_version
                ),
                "sha256": lower_contracts.dependency_graph_sha256,
            },
        )
        legacy = CandidateContext(
            composition=composition,
            refs=legacy_refs,
            page_purpose=lower_contracts.page_purpose,
            business_components=lower_contracts.business_components,
            content_data=lower_contracts.content_data,
            interactions=lower_contracts.interactions,
            dependency_graph=lower_contracts.dependency_graph,
            rows=(),
        )
    else:
        legacy_summary["target_tier"] = 1
        legacy_summary["status"] = "composition_contract_ready"
        legacy = load_candidate_context(
            db,
            request_id=request_id,
            phase3a_result={"preview_contract": legacy_summary},
        )
    cumulative_pages = {
        page.page_id: page for page in contracts.page_purpose.pages
    }
    cumulative_interactions = {
        item.action_id: item for item in contracts.interactions.interactions
    }
    cumulative_page_compositions = {
        item.page_id: item
        for item in contracts.business_components.page_compositions
    }
    cumulative_triggers = {
        item.action_id: item
        for item in contracts.business_components.action_trigger_bindings
    }
    cumulative_component_states = {
        (item.component_id, item.state_id): item
        for item in contracts.business_components.component_state_bindings
    }
    cumulative_collections = {
        item.collection_id: item
        for item in contracts.content_data.data_collections
    }
    cumulative_state_payloads = {
        item.state_id: item
        for item in contracts.content_data.state_payloads
    }
    cumulative_evidence_bindings = {
        item.evidence_id: item
        for item in contracts.content_data.evidence_bindings
    }
    cumulative_action_inputs = {
        item.action_id: item
        for item in contracts.content_data.action_input_bindings
    }
    cumulative_nodes = {
        item.node_id: item for item in contracts.dependency_graph.nodes
    }
    cumulative_edges = {
        (
            item.prerequisite_node_id,
            item.dependent_node_id,
        ): item
        for item in contracts.dependency_graph.edges
    }
    integration_pages = set(
        contracts.projection.lower_tier_integration_page_ids
    )

    def page_preserved(lower_page) -> bool:
        upper_page = cumulative_pages.get(lower_page.page_id)
        if upper_page is None:
            return False
        if lower_page.page_id not in integration_pages:
            return upper_page == lower_page
        reference_fields = (
            "role_ids",
            "requirement_ids",
            "outcome_requirement_ids",
            "capability_ids",
            "state_ids",
            "action_ids",
            "transition_ids",
            "evidence_ids",
            "journey_ids",
            "acceptance_test_ids",
        )
        scalar_fields = (
            "page_id",
            "route",
            "surface",
            "goal",
            "navigation_visibility",
            "deep_link_reason",
            "mobile",
            "immutable",
        )
        return (
            all(
                getattr(upper_page, name) == getattr(lower_page, name)
                for name in scalar_fields
            )
            and all(
                tuple(getattr(upper_page, name))[
                    : len(getattr(lower_page, name))
                ]
                == tuple(getattr(lower_page, name))
                for name in reference_fields
            )
        )

    if (
        any(not page_preserved(page) for page in legacy.page_purpose.pages)
        or contracts.business_components.components[
            : len(legacy.business_components.components)
        ]
        != legacy.business_components.components
        or contracts.content_data.content_items[
            : len(legacy.content_data.content_items)
        ]
        != legacy.content_data.content_items
        or any(
            cumulative_page_compositions.get(item.page_id) is None
            or cumulative_page_compositions[item.page_id]
            .ordered_component_ids[: len(item.ordered_component_ids)]
            != item.ordered_component_ids
            for item in legacy.business_components.page_compositions
        )
        or any(
            cumulative_triggers.get(item.action_id) != item
            for item in legacy.business_components.action_trigger_bindings
        )
        or any(
            cumulative_component_states.get(
                (item.component_id, item.state_id)
            )
            != item
            for item in legacy.business_components.component_state_bindings
        )
        or any(
            cumulative_collections.get(item.collection_id) != item
            for item in legacy.content_data.data_collections
        )
        or contracts.content_data.relationships
        != legacy.content_data.relationships
        or any(
            cumulative_state_payloads.get(item.state_id) != item
            for item in legacy.content_data.state_payloads
        )
        or any(
            cumulative_evidence_bindings.get(item.evidence_id) != item
            for item in legacy.content_data.evidence_bindings
        )
        or any(
            cumulative_action_inputs.get(item.action_id) != item
            for item in legacy.content_data.action_input_bindings
        )
        or tuple(
            cumulative_interactions.get(item.action_id)
            for item in legacy.interactions.interactions
        )
        != legacy.interactions.interactions
        or any(
            cumulative_nodes.get(item.node_id) != item
            for item in legacy.dependency_graph.nodes
        )
        or any(
            (
                item.prerequisite_node_id,
                item.dependent_node_id,
            )
            not in cumulative_edges
            for item in legacy.dependency_graph.edges
        )
    ):
        raise ValueError(
            f"Tier {target_tier} extension changed inherited "
            f"Tier {target_tier - 1} truth"
        )
    refs = CandidateUpstreamRefs(
        request_id=request_id,
        target_tier=target_tier,
        composition_contract_refs=contracts.page_purpose.contract_refs,
        page_purpose_ref={
            "id": row.orchestration_attempt_id,
            "artifact_kind": "page_purpose_contract",
            "schema_version": contracts.page_purpose.schema_version,
            "sha256": contracts.page_purpose_sha256,
        },
        business_component_plan_ref={
            "id": row.orchestration_attempt_id,
            "artifact_kind": "business_component_plan",
            "schema_version": contracts.business_components.schema_version,
            "sha256": contracts.business_components_sha256,
        },
        content_data_plan_ref={
            "id": row.orchestration_attempt_id,
            "artifact_kind": "content_data_plan",
            "schema_version": contracts.content_data.schema_version,
            "sha256": contracts.content_data_sha256,
        },
        interaction_contract_ref={
            "id": row.orchestration_attempt_id,
            "artifact_kind": "interaction_contract",
            "schema_version": contracts.interactions.schema_version,
            "sha256": contracts.interactions_sha256,
        },
        component_dependency_graph_ref={
            "id": row.orchestration_attempt_id,
            "artifact_kind": "component_dependency_graph",
            "schema_version": contracts.dependency_graph.schema_version,
            "sha256": contracts.dependency_graph_sha256,
        },
    )
    return CandidateContext(
        composition=legacy.composition,
        refs=refs,
        page_purpose=contracts.page_purpose,
        business_components=contracts.business_components,
        content_data=contracts.content_data,
        interactions=contracts.interactions,
        dependency_graph=contracts.dependency_graph,
        rows=(),
    )


__all__ = [
    "CandidateContext",
    "load_candidate_context",
    "load_tier_2_extension_context",
]
