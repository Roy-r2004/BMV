from __future__ import annotations

import pytest

from app.application.candidate_generation.context import load_candidate_context
from app.application.tier_orchestration.projection import (
    build_tier_2_extension_contracts,
    project_tier_2_delta,
)
from app.application.tier_orchestration.validation import (
    Tier2GenerationContractError,
    validate_delta_batch,
)
from app.domain.schemas.preview_candidate import (
    GeneratedCandidateBatch,
    GeneratedCandidateFile,
)
from tests.candidate_generation.helpers import prepare_phase3a


def _contracts(request_id: int = 21001):
    prepared = prepare_phase3a(request_id=request_id)
    inherited = load_candidate_context(
        prepared.db,
        request_id=prepared.req.id,
        phase3a_result=prepared.phase3a_result,
    )
    projection = project_tier_2_delta(
        inherited.composition,
        accepted_tier_1_revision_id=1,
        accepted_tier_1_manifest_sha256="a" * 64,
        accepted_tier_1_visual_summary_id=1,
    )
    contracts, refs = build_tier_2_extension_contracts(
        inherited.composition,
        inherited_page_purpose=inherited.page_purpose,
        inherited_components=inherited.business_components,
        inherited_content_data=inherited.content_data,
        projection=projection,
        artifact_record_id=1,
    )
    return inherited, projection, contracts, refs


def test_tier_2_delta_is_deterministic_and_canonical() -> None:
    inherited, first, contracts, refs = _contracts()
    second = project_tier_2_delta(
        inherited.composition,
        accepted_tier_1_revision_id=1,
        accepted_tier_1_manifest_sha256="a" * 64,
        accepted_tier_1_visual_summary_id=1,
    )
    assert first == second
    assert first.delta.requirement_ids == ("REQ-POLICY",)
    assert first.delta.page_ids == ("PAGE-POLICY",)
    assert first.delta.action_ids == ()
    assert first.delta.journey_ids == ()
    assert refs.target_tier == 2
    assert contracts.page_purpose.contract_refs.target_tier == 2


def test_extension_is_cumulative_without_reauthoring_tier_one() -> None:
    inherited, projection, contracts, _refs = _contracts(21002)
    lower_pages = {
        item.page_id: item for item in inherited.page_purpose.pages
    }
    upper_pages = {
        item.page_id: item for item in contracts.page_purpose.pages
    }
    assert {
        page_id: upper_pages[page_id] for page_id in lower_pages
    } == lower_pages
    assert tuple(
        item.component_id
        for item in contracts.business_components.components[
            : len(inherited.business_components.components)
        ]
    ) == tuple(
        item.component_id
        for item in inherited.business_components.components
    )
    assert set(projection.tier_1_references.page_ids).issubset(
        projection.tier_2_references.page_ids
    )
    assert len(contracts.page_purpose.pages) == 2
    assert contracts.page_purpose.pages[-1].journey_ids == ()


def test_extension_graph_is_closed_and_acyclic() -> None:
    _inherited, _projection, contracts, _refs = _contracts(21003)
    graph = contracts.dependency_graph
    node_ids = {item.node_id for item in graph.nodes}
    assert set(graph.topological_order) == node_ids
    assert len(graph.topological_order) == len(node_ids)
    assert all(
        item.prerequisite_node_id in node_ids
        and item.dependent_node_id in node_ids
        for item in graph.edges
    )
    assert any(
        item.contract_id == "PAGE-POLICY" and item.kind == "route"
        for item in graph.nodes
    )


def test_ai_batch_cannot_edit_deterministic_or_out_of_delta_paths() -> None:
    _inherited, projection, contracts, _refs = _contracts(21004)
    component_id = next(
        item.component_id
        for item in contracts.business_components.components
        if item.component_id.startswith("COMP-T2-")
    )
    batch = GeneratedCandidateBatch(
        batch_kind="business_components",
        files=(
            GeneratedCandidateFile(
                path="src/App.tsx",
                file_kind="business_component",
                owner_contract_ids=(component_id,),
                source="export const App = () => null;",
            ),
        ),
    )
    with pytest.raises(
        Tier2GenerationContractError,
        match="escaped its deterministic delta",
    ) as captured:
        validate_delta_batch(
            batch,
            projection=projection,
            new_component_ids=(component_id,),
            allowed_ai_edit_paths=(),
            existing_paths=("src/App.tsx",),
        )
    assert "wrong_namespace:src/App.tsx" in captured.value.diagnostics
    assert "immutable_edit:src/App.tsx" in captured.value.diagnostics


def test_ai_batch_requires_exact_delta_ownership() -> None:
    _inherited, projection, contracts, _refs = _contracts(21005)
    component_id = next(
        item.component_id
        for item in contracts.business_components.components
        if item.component_id.startswith("COMP-T2-")
    )
    batch = GeneratedCandidateBatch(
        batch_kind="business_components",
        files=(
            GeneratedCandidateFile(
                path="src/components/business/Unrelated.tsx",
                file_kind="business_component",
                owner_contract_ids=("COMP-UNRELATED",),
                source="export const Unrelated = () => null;",
            ),
        ),
    )
    with pytest.raises(Tier2GenerationContractError) as captured:
        validate_delta_batch(
            batch,
            projection=projection,
            new_component_ids=(component_id,),
            allowed_ai_edit_paths=(),
            existing_paths=(),
        )
    assert any(
        item.startswith("out_of_delta_owner:")
        for item in captured.value.diagnostics
    )
    assert f"owner_file_cardinality:{component_id}:0" in (
        captured.value.diagnostics
    )
