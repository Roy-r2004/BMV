from __future__ import annotations

import json

import pytest
from sqlalchemy import text

import app.application.tier_orchestration.tier3_service as tier3_service_module
from app.application.candidate_generation.workspace import source_file_manifest
from app.application.tier_orchestration.service import orchestrate_v2_tier_2
from app.application.tier_orchestration.tier3_service import (
    Tier3OrchestrationError,
    orchestrate_v2_tier_3,
)
from app.core.config import settings
from app.domain.models import (
    CandidateEffectiveTierSummaryRecord,
    CandidateRevisionRecord,
    CandidateRouteResultRecord,
    CandidateTierOrchestrationAttemptRecord,
    CandidateVisualHardGateResultRecord,
    CandidateVisualSummaryRecord,
)
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from tests.runtime_validation.helpers import isolated_runtime_paths
from tests.tier_orchestration.helpers import Tier2FixtureAI, Tier3FixtureAI
from tests.tier_orchestration.test_phase6a_integration import (
    _accepted_tier_one,
)


def test_tier_3_happy_path_is_cumulative_and_terminal(
    isolated_runtime_paths,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "V2_TIER2_GENERATION_ENABLED", True)
    monkeypatch.setattr(settings, "V2_TIER3_GENERATION_ENABLED", True)
    monkeypatch.setattr(settings, "V2_VISUAL_EVALUATION_ENABLED", True)
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")
    runtime, phase5 = _accepted_tier_one(23104)
    renderer = JinjaTemplateRenderer(settings.TEMPLATES_DIR)
    phase6a = orchestrate_v2_tier_2(
        runtime.prepared.db,
        runtime.prepared.req.id,
        Tier2FixtureAI(score=85),
        renderer,
        req=runtime.prepared.req,
        phase5_result=phase5,
    )
    assert phase6a["preview_contract"]["status"] == "tier_2_accepted"
    tier3_ai = Tier3FixtureAI(score=85)
    result = orchestrate_v2_tier_3(
        runtime.prepared.db,
        runtime.prepared.req.id,
        tier3_ai,
        renderer,
        req=runtime.prepared.req,
        phase6a_result=phase6a,
    )
    if result["preview_contract"]["status"] != "tier_3_accepted":
        visual_id = result["preview_contract"]["effective_tier_summary"][
            "phase5_visual_summary_id"
        ]
        visual = runtime.prepared.db.get(
            CandidateVisualSummaryRecord,
            visual_id,
        )
        hard_gate = (
            runtime.prepared.db.query(
                CandidateVisualHardGateResultRecord
            )
            .filter(
                CandidateVisualHardGateResultRecord.visual_attempt_id
                == visual.visual_attempt_id
            )
            .one()
            if visual
            else None
        )
        raise AssertionError(
            json.dumps(
                {
                    "preview_status": result["preview_contract"]["status"],
                    "failure_stage": result["preview_contract"][
                        "effective_tier_summary"
                    ]["failure_stage"],
                    "fallback_reason": result["preview_contract"][
                        "effective_tier_summary"
                    ]["fallback_reason"],
                    "visual_status": visual.status if visual else None,
                    "hard_gate": (
                        json.loads(hard_gate.artifact_json)
                        if hard_gate
                        else None
                    ),
                    "acceptance": (
                        json.loads(visual.deterministic_acceptance_json)
                        if visual
                        else None
                    ),
                },
                indent=2,
            )
        )
    summary = result["preview_contract"]["effective_tier_summary"]
    assert summary["highest_accepted_tier"] == 3
    assert summary["serving_pointer_changed"] is False
    assert summary["promoted"] is False
    assert summary["phase_7_invoked"] is False
    assert summary["visual_call_plan"]["screenshot_count"] == 39
    assert summary["visual_call_plan"]["mandatory_calls"] > 4
    assert summary["telemetry"]["generation_call_count"] == 2
    assert summary["telemetry"]["visual_call_count"] == 6
    assert summary["telemetry"]["provider_call_count"] == 8
    assert summary["telemetry"]["phase6_provider_call_count"] == 12
    assert len(tier3_ai.calls) == 8
    db = runtime.prepared.db
    tier3 = (
        db.query(CandidateRevisionRecord)
        .filter(CandidateRevisionRecord.target_tier == 3)
        .one()
    )
    assert (
        db.query(CandidateRouteResultRecord)
        .filter(CandidateRouteResultRecord.candidate_revision_id == tier3.id)
        .count()
        == 39
    )
    assert (
        db.query(CandidateEffectiveTierSummaryRecord)
        .filter(CandidateEffectiveTierSummaryRecord.target_tier == 3)
        .count()
        == 1
    )
    cached_ai = Tier3FixtureAI(score=85)
    cached = orchestrate_v2_tier_3(
        db,
        runtime.prepared.req.id,
        cached_ai,
        renderer,
        req=runtime.prepared.req,
        phase6a_result=phase6a,
    )
    assert cached["preview_contract"]["tier_3_cache_hit"] is True
    assert cached_ai.calls == []

    tier2_summary = phase6a["preview_contract"]["effective_tier_summary"]
    accepted_tier2 = db.get(
        CandidateRevisionRecord,
        tier2_summary["derived_candidate_revision_id"],
    )
    accepted_workspace = (
        settings.PREVIEW_CANDIDATES_DIR
        / accepted_tier2.workspace_relpath
    )
    accepted_bytes = source_file_manifest(accepted_workspace)
    original_build = tier3_service_module.build_tier_3_candidate
    original_phase4 = tier3_service_module.validate_v2_candidate_runtime
    original_phase5 = tier3_service_module.evaluate_v2_candidate_visuals

    monkeypatch.setattr(
        settings,
        "V2_TIER3_GENERATION_POLICY_REVISION",
        "phase6b-fixture-generation-failure",
    )

    def fail_generation(*_args, **_kwargs):
        raise RuntimeError("synthetic Tier 3 generation failure")

    monkeypatch.setattr(
        tier3_service_module,
        "build_tier_3_candidate",
        fail_generation,
    )
    generation_ai = Tier3FixtureAI(score=85)
    generation_failure = orchestrate_v2_tier_3(
        db,
        runtime.prepared.req.id,
        generation_ai,
        renderer,
        req=runtime.prepared.req,
        phase6a_result=phase6a,
    )
    generation_summary = generation_failure["preview_contract"][
        "effective_tier_summary"
    ]
    assert generation_summary["status"] == "tier_3_failed_serving_tier_2"
    assert generation_summary["failure_stage"] == "tier_3_generation"
    assert generation_summary["highest_accepted_tier"] == 2
    assert generation_ai.calls == []
    assert source_file_manifest(accepted_workspace) == accepted_bytes
    monkeypatch.setattr(
        tier3_service_module,
        "build_tier_3_candidate",
        original_build,
    )

    def rejected_phase4(*_args, **kwargs):
        candidate = kwargs["phase3b_result"]["preview_contract"][
            "candidate_revision"
        ]
        return {
            "preview_contract": {
                "status": "candidate_runtime_rejected",
                "candidate_revision": candidate,
            }
        }

    monkeypatch.setattr(
        settings,
        "V2_TIER3_GENERATION_POLICY_REVISION",
        "phase6b-fixture-phase4-failure",
    )
    monkeypatch.setattr(
        tier3_service_module,
        "validate_v2_candidate_runtime",
        rejected_phase4,
    )
    phase4_ai = Tier3FixtureAI(score=85)
    phase4_failure = orchestrate_v2_tier_3(
        db,
        runtime.prepared.req.id,
        phase4_ai,
        renderer,
        req=runtime.prepared.req,
        phase6a_result=phase6a,
    )
    phase4_failure_summary = phase4_failure["preview_contract"][
        "effective_tier_summary"
    ]
    assert phase4_failure_summary["failure_stage"] == (
        "phase4_runtime_validation"
    )
    assert phase4_failure_summary["highest_accepted_tier"] == 2
    assert [item[0] for item in phase4_ai.calls] == [
        "tier_3_components",
        "tier_3_pages",
    ]
    assert source_file_manifest(accepted_workspace) == accepted_bytes

    def accepted_phase4(*_args, **kwargs):
        candidate = kwargs["phase3b_result"]["preview_contract"][
            "candidate_revision"
        ]
        return {
            "preview_contract": {
                "status": "candidate_runtime_validated",
                "candidate_revision": candidate,
                "runtime_validation_summary": {
                    "id": None,
                    "sha256": None,
                },
            }
        }

    def rejected_phase5(*_args, **_kwargs):
        return {
            "preview_contract": {
                "status": "candidate_visual_rejected",
                "visual_evaluation_summary": {
                    "id": None,
                    "sha256": None,
                },
            }
        }

    monkeypatch.setattr(
        settings,
        "V2_TIER3_GENERATION_POLICY_REVISION",
        "phase6b-fixture-phase5-failure",
    )
    monkeypatch.setattr(
        tier3_service_module,
        "validate_v2_candidate_runtime",
        accepted_phase4,
    )
    monkeypatch.setattr(
        tier3_service_module,
        "evaluate_v2_candidate_visuals",
        rejected_phase5,
    )
    phase5_ai = Tier3FixtureAI(score=85)
    phase5_failure = orchestrate_v2_tier_3(
        db,
        runtime.prepared.req.id,
        phase5_ai,
        renderer,
        req=runtime.prepared.req,
        phase6a_result=phase6a,
    )
    phase5_failure_summary = phase5_failure["preview_contract"][
        "effective_tier_summary"
    ]
    assert phase5_failure_summary["failure_stage"] == (
        "phase5_visual_evaluation"
    )
    assert phase5_failure_summary["highest_accepted_tier"] == 2
    assert [item[0] for item in phase5_ai.calls] == [
        "tier_3_components",
        "tier_3_pages",
    ]
    assert source_file_manifest(accepted_workspace) == accepted_bytes
    monkeypatch.setattr(
        tier3_service_module,
        "validate_v2_candidate_runtime",
        original_phase4,
    )
    monkeypatch.setattr(
        tier3_service_module,
        "evaluate_v2_candidate_visuals",
        original_phase5,
    )

    attempt = db.get(
        CandidateTierOrchestrationAttemptRecord,
        tier2_summary["orchestration_attempt_id"],
    )
    db.execute(
        text(
            "UPDATE candidate_tier_orchestration_attempts "
            "SET accepted_manifest_sha256=:corrupt WHERE id=:attempt_id"
        ),
        {"corrupt": "0" * 64, "attempt_id": attempt.id},
    )
    db.commit()
    invalid_ai = Tier3FixtureAI(score=85)
    with pytest.raises(
        Tier3OrchestrationError,
        match="lineage|candidate",
    ):
        orchestrate_v2_tier_3(
            db,
            runtime.prepared.req.id,
            invalid_ai,
            renderer,
            req=runtime.prepared.req,
            phase6a_result=phase6a,
        )
    assert invalid_ai.calls == []
