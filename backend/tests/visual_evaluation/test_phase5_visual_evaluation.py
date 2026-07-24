from __future__ import annotations

import pytest

from app.domain.models import (
    CandidateBaselineComparisonRecord,
    CandidateRefinementGenerationRecord,
    CandidateRefinementPlanRecord,
    CandidateRevisionRecord,
    CandidateValidationSummaryRecord,
    CandidateVisualEvaluationAttemptRecord,
    CandidateVisualEvidenceBundleRecord,
    CandidateVisualHardGateResultRecord,
    CandidateVisualReviewerDecisionRecord,
    CandidateVisualScorecardRecord,
    CandidateVisualSummaryRecord,
)
from app.application.runtime_validation.workspace import source_manifest_sha256
from app.application.visual_evaluation.repository import (
    VisualEvaluationRepository,
)
from app.core.config import settings

from tests.runtime_validation.helpers import isolated_runtime_paths
from tests.visual_evaluation.helpers import (
    VisualFixtureAI,
    prepared_visual,
    run_phase5,
)


def test_accepted_original_uses_exactly_two_calls(prepared_visual) -> None:
    ai = VisualFixtureAI(score=85)
    result = run_phase5(prepared_visual, ai)
    assert (
        result["preview_contract"]["status"] == "candidate_visual_accepted"
    ), result["preview_contract"]["visual_evaluation"]["diagnostics"]
    assert result["preview_contract"]["visual_evaluation"][
        "provider_call_count"
    ] == 2
    assert [model for model, _prompt in ai.calls] == [
        "openai/gpt-4o",
        "google/gemini-2.5-flash",
    ]
    assert prepared_visual.db.query(
        CandidateVisualEvaluationAttemptRecord
    ).count() == 1
    assert prepared_visual.db.query(
        CandidateVisualEvidenceBundleRecord
    ).count() == 1
    assert prepared_visual.db.query(
        CandidateVisualHardGateResultRecord
    ).count() == 1
    assert prepared_visual.db.query(CandidateVisualScorecardRecord).count() == 2
    assert prepared_visual.db.query(
        CandidateVisualReviewerDecisionRecord
    ).count() == 2
    assert prepared_visual.db.query(
        CandidateBaselineComparisonRecord
    ).count() == 1
    assert prepared_visual.db.query(CandidateVisualSummaryRecord).count() == 1


def test_full_cache_hit_and_prompt_invalidation(
    prepared_visual,
    monkeypatch,
) -> None:
    first_ai = VisualFixtureAI(score=85)
    first = run_phase5(prepared_visual, first_ai)
    assert first["preview_contract"]["status"] == "candidate_visual_accepted"
    second_ai = VisualFixtureAI(score=85)
    second = run_phase5(prepared_visual, second_ai)
    assert second["preview_contract"]["status"] == "candidate_visual_accepted"
    assert second["preview_contract"]["visual_evaluation"][
        "provider_call_count"
    ] == 0
    assert second["preview_contract"]["visual_evaluation"]["cache_hit"] is True
    assert second_ai.calls == []
    monkeypatch.setattr(
        settings,
        "V2_VISUAL_CRITIC_PROMPT_REVISION",
        "2026-07-24.2",
    )
    third_ai = VisualFixtureAI(score=85)
    third = run_phase5(prepared_visual, third_ai)
    assert third["preview_contract"]["status"] == "candidate_visual_accepted"
    assert len(third_ai.calls) == 2
    assert prepared_visual.db.query(CandidateVisualSummaryRecord).count() == 2


def test_repairable_candidate_uses_one_bounded_refinement(
    prepared_visual,
) -> None:
    ai = VisualFixtureAI(score=65, repairable=True)
    original_sha = source_manifest_sha256(
        prepared_visual.runtime.candidate_path,
        tuple(
            __import__("json").loads(
                prepared_visual.runtime.revision.file_manifest_json
            )
        ),
    )
    result = run_phase5(prepared_visual, ai)
    assert result["preview_contract"]["status"] == "candidate_visual_accepted"
    assert result["preview_contract"]["visual_evaluation"][
        "provider_call_count"
    ] == 5
    assert len(ai.calls) == 5
    assert prepared_visual.db.query(CandidateRevisionRecord).count() == 2
    assert prepared_visual.db.query(CandidateValidationSummaryRecord).count() == 2
    assert prepared_visual.db.query(
        CandidateRefinementPlanRecord
    ).count() == 2
    assert prepared_visual.db.query(
        CandidateRefinementGenerationRecord
    ).count() == 1
    assert prepared_visual.db.query(CandidateVisualSummaryRecord).count() == 2
    assert source_manifest_sha256(
        prepared_visual.runtime.candidate_path,
        tuple(
            __import__("json").loads(
                prepared_visual.runtime.revision.file_manifest_json
            )
        ),
    ) == original_sha
    assert not settings.PREVIEW_APPS_DIR.exists()
    repeat_ai = VisualFixtureAI(score=65, repairable=True)
    repeat = run_phase5(prepared_visual, repeat_ai)
    assert repeat_ai.calls == []
    assert repeat["preview_contract"]["status"] == "candidate_visual_accepted"
    assert prepared_visual.db.query(CandidateRevisionRecord).count() == 2


def test_rejected_not_repairable_makes_no_refinement_call(
    prepared_visual,
) -> None:
    ai = VisualFixtureAI(score=65, repairable=False)
    result = run_phase5(prepared_visual, ai)
    assert result["preview_contract"]["status"] == "candidate_visual_rejected"
    assert result["preview_contract"]["visual_evaluation_summary"][
        "repairability"
    ] == "rejected_not_repairable"
    assert len(ai.calls) == 2
    assert prepared_visual.db.query(
        CandidateRefinementGenerationRecord
    ).count() == 0


def test_terminal_transaction_rolls_back_completely(
    prepared_visual,
    monkeypatch,
) -> None:
    original = VisualEvaluationRepository.persist_terminal

    def fail_after_staging(self, **kwargs):
        original(self, **kwargs)
        raise RuntimeError("synthetic incomplete transaction")

    monkeypatch.setattr(
        VisualEvaluationRepository,
        "persist_terminal",
        fail_after_staging,
    )
    with pytest.raises(RuntimeError, match="synthetic incomplete"):
        run_phase5(prepared_visual, VisualFixtureAI(score=85))
    assert prepared_visual.db.query(
        CandidateVisualEvaluationAttemptRecord
    ).count() == 0
    assert prepared_visual.db.query(CandidateVisualSummaryRecord).count() == 0


def test_invalid_model_output_has_no_schema_retry(prepared_visual) -> None:
    class InvalidAI(VisualFixtureAI):
        def ask_chat(self, model, messages, max_tokens=None, temperature=None):
            self.calls.append((model, "invalid"))
            return "{}"

    ai = InvalidAI()
    with pytest.raises(Exception, match="invalid structured output"):
        run_phase5(prepared_visual, ai)
    assert len(ai.calls) == 1


def test_one_source_only_technical_repair_is_bounded(
    prepared_visual,
) -> None:
    ai = VisualFixtureAI(
        score=65,
        repairable=True,
        technical_repair=True,
    )
    result = run_phase5(prepared_visual, ai)
    assert result["preview_contract"]["status"] == "candidate_visual_accepted"
    assert len(ai.calls) == 6
    generation = prepared_visual.db.query(
        CandidateRefinementGenerationRecord
    ).one()
    assert generation.technical_repair_call_count == 1
    assert prepared_visual.db.query(CandidateRevisionRecord).count() == 2


def test_invalid_refinement_records_terminal_failure(prepared_visual) -> None:
    class InvalidRefinementAI(VisualFixtureAI):
        def ask_chat(self, model, messages, max_tokens=None, temperature=None):
            prompt = __import__(
                "tests.visual_evaluation.helpers",
                fromlist=["_prompt"],
            )._prompt(messages)
            if "screenshot-aware source refiner" in prompt:
                self.calls.append((model, prompt))
                return "{}"
            return super().ask_chat(
                model,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )

    ai = InvalidRefinementAI(score=65, repairable=True)
    result = run_phase5(prepared_visual, ai)
    assert (
        result["preview_contract"]["status"]
        == "candidate_refinement_failed"
    )
    assert len(ai.calls) == 3
    assert prepared_visual.db.query(CandidateRevisionRecord).count() == 1
    assert prepared_visual.db.query(CandidateVisualSummaryRecord).count() == 2
