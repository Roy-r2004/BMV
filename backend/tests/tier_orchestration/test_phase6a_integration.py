from __future__ import annotations

import json
from typing import Any

import pytest

from app.application.tier_orchestration.service import orchestrate_v2_tier_2
from app.application.tier_orchestration.validation import (
    Tier2GenerationContractError,
)
from app.core.config import settings
from app.domain.models import (
    CandidateBaselineComparisonRecord,
    CandidateEffectiveTierSummaryRecord,
    CandidateJourneyResultRecord,
    CandidateLowerTierPreservationAuditRecord,
    CandidateRevisionRecord,
    CandidateRouteResultRecord,
    CandidateTierExtensionManifestRecord,
    CandidateTierGenerationResultRecord,
    CandidateTierOrchestrationAttemptRecord,
    CandidateTierValidationResultRecord,
    CandidateTierVisualOutcomeRecord,
)
from app.domain.schemas.preview_candidate import CandidateValidationIssue
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from tests.runtime_validation.helpers import (
    isolated_runtime_paths,
    prepare_runtime_candidate,
    run_phase4,
)
from tests.tier_orchestration.helpers import Tier2FixtureAI
from tests.visual_evaluation.helpers import (
    PreparedVisual,
    VisualFixtureAI,
    run_phase5,
)


def _accepted_tier_one(request_id: int):
    runtime = prepare_runtime_candidate(request_id=request_id)
    phase4 = run_phase4(runtime)
    prepared = PreparedVisual(runtime=runtime, phase4_result=phase4)
    phase5 = run_phase5(prepared, VisualFixtureAI(score=85))
    assert phase5["preview_contract"]["status"] == "candidate_visual_accepted"
    return runtime, phase5


class _InvalidGenerationAI(Tier2FixtureAI):
    def ask_chat(
        self,
        model: str,
        messages: list[dict],
        max_tokens=None,
        temperature=None,
    ) -> str:
        content = messages[0]["content"]
        prompt = (
            content
            if isinstance(content, str)
            else next(
                item["text"]
                for item in content
                if item["type"] == "text"
            )
        )
        if "Tier 2 inputs:" in prompt:
            self.calls.append(("invalid_tier_2_generation", model))
            return "{}"
        return super().ask_chat(
            model,
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )


def _run_tier_2(runtime, phase5, ai):
    return orchestrate_v2_tier_2(
        runtime.prepared.db,
        runtime.prepared.req.id,
        ai,
        JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        req=runtime.prepared.req,
        phase5_result=phase5,
    )


def test_tier_2_happy_path_uses_four_calls_and_seven_records(
    isolated_runtime_paths,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "V2_TIER2_GENERATION_ENABLED", True)
    monkeypatch.setattr(settings, "V2_VISUAL_EVALUATION_ENABLED", True)
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")
    runtime, phase5 = _accepted_tier_one(22001)
    request_bundle_before = runtime.prepared.req.generated_pages
    accepted_manifest = runtime.candidate_path.joinpath(
        "src/App.tsx"
    ).read_bytes()
    ai = Tier2FixtureAI(score=85)
    result = _run_tier_2(runtime, phase5, ai)
    assert result["preview_contract"]["status"] == "tier_2_accepted", (
        json.dumps(
            result["preview_contract"]["tier_2_visual_outcome"],
            indent=2,
        )
    )
    summary = result["preview_contract"]["effective_tier_summary"]
    assert summary["telemetry"]["provider_call_count"] == 4
    assert summary["telemetry"]["output_tokens"] == 200
    assert summary["telemetry"]["cost_usd"] == pytest.approx(0.02)
    assert 0 < summary["telemetry"]["latency_ms"] <= 2_400_000
    assert summary["highest_accepted_tier"] == 2
    assert summary["tier_3_invoked"] is False
    assert summary["serving_pointer_changed"] is False
    assert summary["promoted"] is False
    assert result["preview_contract"]["tier_2_generation_result"][
        "component_batch_call_count"
    ] == 1
    assert result["preview_contract"]["tier_2_generation_result"][
        "page_batch_call_count"
    ] == 1
    assert result["preview_contract"]["tier_2_generation_result"][
        "full_product_regeneration"
    ] is False
    assert result["preview_contract"]["tier_2_validation_result"][
        "complete_phase4_reused"
    ] is True
    assert result["preview_contract"]["tier_2_validation_result"][
        "tier_1_journeys_rerun"
    ] is True
    assert result["preview_contract"]["tier_2_visual_outcome"][
        "tier_1_regression_checked"
    ] is True
    assert runtime.candidate_path.joinpath(
        "src/App.tsx"
    ).read_bytes() == accepted_manifest
    db = runtime.prepared.db
    assert db.query(CandidateTierOrchestrationAttemptRecord).count() == 1
    assert db.query(CandidateTierExtensionManifestRecord).count() == 1
    assert db.query(CandidateLowerTierPreservationAuditRecord).count() == 1
    assert db.query(CandidateTierGenerationResultRecord).count() == 1
    assert db.query(CandidateTierValidationResultRecord).count() == 1
    assert db.query(CandidateTierVisualOutcomeRecord).count() == 1
    assert db.query(CandidateEffectiveTierSummaryRecord).count() == 1
    assert (
        db.query(CandidateRevisionRecord)
        .filter(CandidateRevisionRecord.target_tier == 2)
        .count()
        == 1
    )
    derived = (
        db.query(CandidateRevisionRecord)
        .filter(CandidateRevisionRecord.target_tier == 2)
        .one()
    )
    assert (
        db.query(CandidateRouteResultRecord)
        .filter(
            CandidateRouteResultRecord.candidate_revision_id == derived.id
        )
        .count()
        == 6
    )
    assert (
        db.query(CandidateJourneyResultRecord)
        .filter(
            CandidateJourneyResultRecord.candidate_revision_id == derived.id
        )
        .count()
        >= 1
    )
    phase6_visual = db.query(CandidateTierVisualOutcomeRecord).one()
    baseline = db.get(
        CandidateBaselineComparisonRecord,
        phase6_visual.baseline_comparison_id,
    )
    assert baseline is not None and baseline.mode == "blind_pair"
    db.refresh(runtime.prepared.req)
    assert runtime.prepared.req.generated_pages == request_bundle_before
    audit = json.loads(
        db.query(CandidateLowerTierPreservationAuditRecord)
        .one()
        .audit_json
    )
    assert audit["entries"]
    assert all(
        item["original_sha256"] and item["final_sha256"]
        for item in audit["entries"]
    )
    assert all(
        item["original_sha256"] == item["final_sha256"]
        for item in audit["entries"]
        if item["classification"] == "immutable"
    )
    assert all(
        item["edit_authority"] in {"none", "ai", "deterministic"}
        and item["justification"]
        for item in audit["entries"]
    )
    canonical_contract = next(
        item
        for item in audit["entries"]
        if item["path"] == "src/generated/canonical-contracts.ts"
    )
    assert canonical_contract["classification"] == "immutable"
    assert canonical_contract["edit_authority"] == "none"


def test_tier_2_full_cache_hit_makes_zero_calls(
    isolated_runtime_paths,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "V2_TIER2_GENERATION_ENABLED", True)
    monkeypatch.setattr(settings, "V2_VISUAL_EVALUATION_ENABLED", True)
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")
    runtime, phase5 = _accepted_tier_one(22002)
    first = Tier2FixtureAI(score=85)
    result = _run_tier_2(runtime, phase5, first)
    assert result["preview_contract"]["status"] == "tier_2_accepted"
    second = Tier2FixtureAI(score=85)
    cached = _run_tier_2(runtime, phase5, second)
    assert cached["preview_contract"]["status"] == "tier_2_accepted"
    assert cached["preview_contract"]["tier_2_cache_hit"] is True
    assert second.calls == []
    derived = (
        runtime.prepared.db.query(CandidateRevisionRecord)
        .filter(CandidateRevisionRecord.target_tier == 2)
        .one()
    )
    derived_app = settings.PREVIEW_CANDIDATES_DIR.joinpath(
        derived.workspace_relpath,
        "src",
        "App.tsx",
    )
    derived_app.write_text(
        derived_app.read_text(encoding="utf-8") + "\n// tampered\n",
        encoding="utf-8",
    )
    third = Tier2FixtureAI(score=85)
    with pytest.raises(
        Tier2GenerationContractError,
        match="workspace was modified",
    ):
        _run_tier_2(runtime, phase5, third)
    assert third.calls == []


def test_narrow_page_static_repair_is_bounded_and_reruns_full_gate(
    isolated_runtime_paths,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "V2_TIER2_GENERATION_ENABLED", True)
    monkeypatch.setattr(settings, "V2_VISUAL_EVALUATION_ENABLED", True)
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")
    runtime, phase5 = _accepted_tier_one(22006)
    from app.application.tier_orchestration import generation

    original_validator = generation.validate_candidate_workspace
    invocations = 0

    def fail_first_static_gate(*args, **kwargs):
        nonlocal invocations
        invocations += 1
        report = original_validator(*args, **kwargs)
        if invocations != 1:
            return report
        return report.model_copy(
            update={
                "passed": False,
                "issues": (
                    CandidateValidationIssue(
                        code="synthetic_page_diagnostic",
                        path="src/pages/PAGE-POLICY.tsx",
                        related_ids=("PAGE-POLICY",),
                        message="Synthetic page-only static diagnostic.",
                    ),
                ),
            }
        )

    monkeypatch.setattr(
        generation,
        "validate_candidate_workspace",
        fail_first_static_gate,
    )
    ai = Tier2FixtureAI(score=85)
    result = _run_tier_2(runtime, phase5, ai)
    summary = result["preview_contract"]["effective_tier_summary"]
    assert result["preview_contract"]["status"] == "tier_2_accepted"
    assert summary["telemetry"]["provider_call_count"] == 5
    assert summary["telemetry"]["generation_call_count"] == 3
    assert invocations == 2
    assert [
        item for item in ai.calls
        if item[0] == "tier_2_pages_static_repair"
    ]


def test_generation_failure_freezes_diagnostics_and_falls_back_to_tier_one(
    isolated_runtime_paths,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "V2_TIER2_GENERATION_ENABLED", True)
    monkeypatch.setattr(settings, "V2_VISUAL_EVALUATION_ENABLED", True)
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")
    runtime, phase5 = _accepted_tier_one(22003)
    accepted_bytes = runtime.candidate_path.joinpath(
        "src/App.tsx"
    ).read_bytes()
    result = _run_tier_2(runtime, phase5, _InvalidGenerationAI(score=85))
    summary = result["preview_contract"]["effective_tier_summary"]
    assert result["preview_contract"]["status"] == (
        "tier_2_failed_serving_tier_1"
    )
    assert summary["failure_stage"] == "tier_2_generation"
    assert summary["highest_accepted_tier"] == 1
    assert summary["last_accepted_candidate_revision_id"] == (
        summary["accepted_tier_1_revision_id"]
    )
    assert summary["derived_candidate_revision_id"] is None
    assert runtime.candidate_path.joinpath(
        "src/App.tsx"
    ).read_bytes() == accepted_bytes


def test_phase4_failure_preserves_tier_one_and_never_becomes_effective(
    isolated_runtime_paths,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "V2_TIER2_GENERATION_ENABLED", True)
    monkeypatch.setattr(settings, "V2_VISUAL_EVALUATION_ENABLED", True)
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")
    runtime, phase5 = _accepted_tier_one(22004)
    accepted_bytes = runtime.candidate_path.joinpath(
        "src/App.tsx"
    ).read_bytes()

    def rejected_phase4(*_args, **_kwargs) -> dict[str, Any]:
        return {
            "preview_contract": {
                "status": "candidate_runtime_failed",
                "runtime_validation_summary": {"id": None},
            }
        }

    monkeypatch.setattr(
        "app.application.tier_orchestration.service."
        "validate_v2_candidate_runtime",
        rejected_phase4,
    )
    result = _run_tier_2(runtime, phase5, Tier2FixtureAI(score=85))
    summary = result["preview_contract"]["effective_tier_summary"]
    assert summary["failure_stage"] == "phase4_runtime_validation"
    assert summary["highest_accepted_tier"] == 1
    assert summary["derived_candidate_revision_id"] is not None
    assert summary["last_accepted_candidate_revision_id"] == (
        summary["accepted_tier_1_revision_id"]
    )
    assert summary["phase5_visual_summary_id"] is None
    assert runtime.candidate_path.joinpath(
        "src/App.tsx"
    ).read_bytes() == accepted_bytes


def test_phase5_rejection_preserves_tier_one_and_records_fallback(
    isolated_runtime_paths,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "V2_TIER2_GENERATION_ENABLED", True)
    monkeypatch.setattr(settings, "V2_VISUAL_EVALUATION_ENABLED", True)
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")
    runtime, phase5 = _accepted_tier_one(22005)
    accepted_bytes = runtime.candidate_path.joinpath(
        "src/App.tsx"
    ).read_bytes()

    def rejected_phase5(*_args, **_kwargs) -> dict[str, Any]:
        return {
            "preview_contract": {
                "status": "candidate_visual_rejected",
                "visual_evaluation_summary": {"id": None},
                "visual_evaluation": {
                    "provider_call_count": 0,
                    "completion_tokens": 0,
                    "cost_usd": 0.0,
                },
            }
        }

    monkeypatch.setattr(
        "app.application.tier_orchestration.service."
        "evaluate_v2_candidate_visuals",
        rejected_phase5,
    )
    result = _run_tier_2(runtime, phase5, Tier2FixtureAI(score=85))
    summary = result["preview_contract"]["effective_tier_summary"]
    assert summary["failure_stage"] == "phase5_visual_evaluation"
    assert summary["highest_accepted_tier"] == 1
    assert summary["last_accepted_candidate_revision_id"] == (
        summary["accepted_tier_1_revision_id"]
    )
    assert summary["phase5_visual_summary_id"] is None
    assert runtime.candidate_path.joinpath(
        "src/App.tsx"
    ).read_bytes() == accepted_bytes
