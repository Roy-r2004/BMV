from __future__ import annotations

import pytest

import app.application.preview_app.pipeline.v2_contract as boundary_module
from app.application.candidate_generation.context import load_candidate_context
from app.application.tier_orchestration.policy import (
    Tier3BudgetError,
    build_tier_3_visual_call_plan,
)
from app.application.tier_orchestration.projection import (
    build_tier_2_extension_contracts,
    build_tier_3_extension_contracts,
    project_tier_2_delta,
    project_tier_3_delta,
)
from app.application.tier_orchestration.tier3_service import (
    Tier3OrchestrationError,
    orchestrate_v2_tier_3,
)
from app.core.config import settings
from tests.candidate_generation.helpers import prepare_phase3a


def _stub_through_phase5(monkeypatch, phase5):
    monkeypatch.setattr(
        boundary_module,
        "build_v2_app_spec_contract",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        boundary_module,
        "build_v2_design_contract",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        boundary_module,
        "build_v2_composition_contract",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        boundary_module,
        "build_v2_candidate_revision",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        boundary_module,
        "validate_v2_candidate_runtime",
        lambda *_args, **_kwargs: {
            "preview_contract": {
                "status": "candidate_runtime_validated",
            }
        },
    )
    monkeypatch.setattr(
        boundary_module,
        "evaluate_v2_candidate_visuals",
        lambda *_args, **_kwargs: phase5,
    )


def _contracts(request_id: int = 23001):
    prepared = prepare_phase3a(request_id=request_id)
    tier1 = load_candidate_context(
        prepared.db,
        request_id=prepared.req.id,
        phase3a_result=prepared.phase3a_result,
    )
    projection2 = project_tier_2_delta(
        tier1.composition,
        accepted_tier_1_revision_id=1,
        accepted_tier_1_manifest_sha256="a" * 64,
        accepted_tier_1_visual_summary_id=1,
    )
    tier2, _refs2 = build_tier_2_extension_contracts(
        tier1.composition,
        inherited_page_purpose=tier1.page_purpose,
        inherited_components=tier1.business_components,
        inherited_content_data=tier1.content_data,
        projection=projection2,
        artifact_record_id=1,
    )
    projection3 = project_tier_3_delta(
        tier1.composition,
        accepted_tier_1_revision_id=1,
        accepted_tier_1_visual_summary_id=1,
        accepted_tier_2_revision_id=2,
        accepted_tier_2_manifest_sha256="b" * 64,
        accepted_tier_2_visual_summary_id=2,
        accepted_tier_2_effective_summary_id=1,
        accepted_tier_2_effective_summary_sha256="c" * 64,
    )
    tier3, refs3 = build_tier_3_extension_contracts(
        tier1.composition,
        inherited_page_purpose=tier2.page_purpose,
        inherited_components=tier2.business_components,
        inherited_content_data=tier2.content_data,
        projection=projection3,
        artifact_record_id=2,
    )
    return tier1, tier2, projection3, tier3, refs3


def test_tier_3_projection_is_canonical_cumulative_and_complete() -> None:
    tier1, tier2, first, contracts, refs = _contracts()
    second = project_tier_3_delta(
        tier1.composition,
        accepted_tier_1_revision_id=1,
        accepted_tier_1_visual_summary_id=1,
        accepted_tier_2_revision_id=2,
        accepted_tier_2_manifest_sha256="b" * 64,
        accepted_tier_2_visual_summary_id=2,
        accepted_tier_2_effective_summary_id=1,
        accepted_tier_2_effective_summary_sha256="c" * 64,
    )
    assert first == second
    assert refs.target_tier == 3
    assert len(contracts.page_purpose.pages) == 13
    assert tuple(
        item.page_id for item in contracts.page_purpose.pages
    ) == first.tier_3_references.page_ids
    assert set(first.tier_2_references.page_ids).issubset(
        first.tier_3_references.page_ids
    )
    assert contracts.business_components.components[
        : len(tier2.business_components.components)
    ] == tier2.business_components.components


def test_39_screenshots_use_dynamic_groups_not_fixed_four_calls(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")
    pages = tuple(
        (f"PAGE-{index:02d}", f"/page-{index}")
        for index in range(13)
    )
    plan = build_tier_3_visual_call_plan(
        available_pages=pages,
        selected_page_ids=tuple(item[0] for item in pages),
        matched_tier_2_page_ids=(pages[0][0], pages[1][0]),
    )
    assert plan.screenshot_count == 39
    assert plan.critic_group_calls == 3
    assert plan.reviewer_group_calls == 3
    assert plan.mandatory_calls == 8
    assert plan.mandatory_calls != 4


def test_visual_plan_fails_closed_without_matched_tier_2_route(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")
    with pytest.raises(Tier3BudgetError, match="matched Tier 2"):
        build_tier_3_visual_call_plan(
            available_pages=(("PAGE-NEW", "/new"),),
            selected_page_ids=("PAGE-NEW",),
            matched_tier_2_page_ids=(),
        )


def test_tier_3_flag_false_returns_exact_phase6a_object(monkeypatch) -> None:
    monkeypatch.setattr(settings, "V2_TIER3_GENERATION_ENABLED", False)
    phase6a = {"preview_contract": {"status": "tier_2_accepted"}}
    assert (
        orchestrate_v2_tier_3(
            None,
            1,
            None,
            None,
            req=None,
            phase6a_result=phase6a,
        )
        is phase6a
    )


def test_tier_3_requires_all_preceding_flags_before_provider(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "V2_TIER3_GENERATION_ENABLED", True)
    monkeypatch.setattr(settings, "V2_TIER2_GENERATION_ENABLED", False)
    with pytest.raises(Tier3OrchestrationError, match="preceding"):
        orchestrate_v2_tier_3(
            None,
            1,
            object(),
            object(),
            req=None,
            phase6a_result={},
        )


def test_both_tier_flags_false_return_exact_phase5_object(
    monkeypatch,
) -> None:
    phase5 = {
        "preview_contract": {"status": "candidate_visual_accepted"}
    }
    _stub_through_phase5(monkeypatch, phase5)
    monkeypatch.setattr(settings, "V2_RUNTIME_VALIDATION_ENABLED", True)
    monkeypatch.setattr(settings, "V2_VISUAL_EVALUATION_ENABLED", True)
    monkeypatch.setattr(settings, "V2_TIER2_GENERATION_ENABLED", False)
    monkeypatch.setattr(settings, "V2_TIER3_GENERATION_ENABLED", False)
    result = boundary_module.run_v2_contract_boundary(
        None,
        1,
        None,
        None,
        req=None,
        app_spec_revision_id=None,
    )
    assert result is phase5


def test_tier_3_disabled_returns_exact_phase6a_object_in_pipeline(
    monkeypatch,
) -> None:
    phase5 = {
        "preview_contract": {"status": "candidate_visual_accepted"}
    }
    phase6a = {
        "preview_contract": {
            "status": "tier_2_accepted",
            "target_tier": 2,
        }
    }
    _stub_through_phase5(monkeypatch, phase5)
    monkeypatch.setattr(settings, "V2_RUNTIME_VALIDATION_ENABLED", True)
    monkeypatch.setattr(settings, "V2_VISUAL_EVALUATION_ENABLED", True)
    monkeypatch.setattr(settings, "V2_TIER2_GENERATION_ENABLED", True)
    monkeypatch.setattr(settings, "V2_TIER3_GENERATION_ENABLED", False)
    monkeypatch.setattr(
        boundary_module,
        "orchestrate_v2_tier_2",
        lambda *_args, **_kwargs: phase6a,
    )
    result = boundary_module.run_v2_contract_boundary(
        None,
        1,
        None,
        None,
        req=None,
        app_spec_revision_id=None,
    )
    assert result is phase6a
