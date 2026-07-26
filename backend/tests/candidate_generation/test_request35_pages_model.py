"""Request #35: pages stage needs an explicit ≥64k model (no DeepSeek 32k inherit)."""
from __future__ import annotations

import json
import time

import pytest

from app.application.appspec.policy import ModelFamilyPolicyError
from app.application.candidate_generation.builder import (
    CandidateStageError,
    build_ai_batch,
)
from app.application.candidate_generation.call_budget import CandidateCallBudget
from app.application.candidate_generation.policy import (
    resolve_candidate_stage_policy,
)
from app.application.preview_app.pipeline.v2_contract import (
    Phase4StatusPreconditionError,
    ensure_phase4_entry_status,
)
from app.core.config import settings
from app.infrastructure.ai_providers.model_capabilities import (
    APPROVED_CANDIDATE_PAGE_MODEL,
    CAPABILITY_PROFILE_REVISION,
    CONTEXT_RESERVE_TOKENS,
    MINIMUM_VALID_OUTPUT_TOKENS,
    clamp_max_tokens,
    estimate_prompt_tokens,
    resolve_model_capability,
)


REQUEST35_PAGES_ESTIMATE = 33_232


@pytest.fixture
def isolated_settings(monkeypatch):
    monkeypatch.setattr(
        settings, "V2_CANDIDATE_COMPONENT_MODEL", "deepseek/deepseek-chat"
    )
    monkeypatch.setattr(
        settings, "V2_CANDIDATE_PAGE_MODEL", APPROVED_CANDIDATE_PAGE_MODEL
    )
    monkeypatch.setattr(settings, "V2_CANDIDATE_COMPONENT_FALLBACK_MODEL", "")
    monkeypatch.setattr(settings, "V2_CANDIDATE_MAX_CALLS", 4)


def test_components_and_pages_models_are_split(isolated_settings) -> None:
    components = resolve_candidate_stage_policy("business_components")
    pages = resolve_candidate_stage_policy("pages")
    assert components.model == "deepseek/deepseek-chat"
    assert pages.model == "google/gemini-2.5-flash"
    assert pages.model != components.model
    assert resolve_model_capability(components.model).context_window == 32_768
    assert resolve_model_capability(pages.model).context_window == 1_048_576
    assert resolve_model_capability(pages.model).revision == (
        CAPABILITY_PROFILE_REVISION
    )


def test_request35_pages_prompt_fails_under_32768() -> None:
    estimated = REQUEST35_PAGES_ESTIMATE
    deepseek = resolve_model_capability("deepseek/deepseek-chat")
    assert deepseek.context_window == 32_768
    assert estimated >= deepseek.context_window
    clamped = clamp_max_tokens(
        requested_max_tokens=32_000,
        estimated_input_tokens=estimated,
        context_window=deepseek.context_window,
    )
    assert clamped == 0


def test_request35_pages_prompt_passes_under_64k_plus_profile() -> None:
    estimated = REQUEST35_PAGES_ESTIMATE
    pages = resolve_model_capability(APPROVED_CANDIDATE_PAGE_MODEL)
    assert pages.context_window >= 64_000
    assert estimated < pages.context_window
    clamped = clamp_max_tokens(
        requested_max_tokens=32_000,
        estimated_input_tokens=estimated,
        context_window=pages.context_window,
    )
    assert clamped >= MINIMUM_VALID_OUTPUT_TOKENS
    # Remaining room after reserve for the #35-sized pages prompt.
    expected = min(
        32_000,
        pages.context_window - estimated - CONTEXT_RESERVE_TOKENS,
    )
    assert clamped == expected
    assert expected == 32_000  # 1M window leaves full requested output


def test_missing_pages_model_fails_closed(monkeypatch, isolated_settings) -> None:
    monkeypatch.setattr(settings, "V2_CANDIDATE_PAGE_MODEL", "")
    with pytest.raises(ModelFamilyPolicyError) as exc:
        resolve_candidate_stage_policy("pages")
    assert "candidate_page_model_not_configured" in str(exc.value)


def test_unknown_pages_model_fails_closed_without_component_fallback(
    monkeypatch, isolated_settings
) -> None:
    monkeypatch.setattr(
        settings, "V2_CANDIDATE_PAGE_MODEL", "google/unprofiled-pages-model"
    )
    # Known family so policy resolves; capability profile is missing.
    policy = resolve_candidate_stage_policy("pages")
    assert policy.model == "google/unprofiled-pages-model"

    class _NoCallAI:
        name = "openrouter"

        def ask_chat(self, *args, **kwargs):
            raise AssertionError("must not call provider for unknown pages model")

    class _Renderer:
        def render(self, template, **values):
            return "x" * (REQUEST35_PAGES_ESTIMATE * 3)

    budget = CandidateCallBudget.create()
    # Simulate components already spent 2/2; pages still has budget.
    assert budget.approve("business_components")[0]
    assert budget.approve("business_components")[0]
    remaining_before = budget.remaining_total()
    assert remaining_before == 2

    with pytest.raises(CandidateStageError) as exc:
        build_ai_batch(
            request_id=3501,
            policy=policy,
            prompt_template="ignored",
            prompt_values={},
            ai_provider=_NoCallAI(),
            template_renderer=_Renderer(),
            phase_deadline=time.monotonic() + 60,
            call_budget=budget,
            candidate_revision_uuid="rev-unknown-pages",
        )
    assert exc.value.provider_error_code == (
        "candidate_page_model_capability_unknown"
    )
    assert budget.remaining_total() == remaining_before
    attempts = budget.attempts_snapshot()
    assert attempts
    assert attempts[-1]["model"] == "google/unprofiled-pages-model"
    assert attempts[-1]["approval_decision"] == "denied_preflight"
    assert attempts[-1]["fallback_model_decision"] == "primary_only"


def test_pages_do_not_silently_fall_back_to_component_model(
    monkeypatch, isolated_settings
) -> None:
    monkeypatch.setattr(
        settings, "V2_CANDIDATE_COMPONENT_FALLBACK_MODEL", "google/gemini-2.5-flash"
    )
    monkeypatch.setattr(
        settings, "V2_CANDIDATE_PAGE_MODEL", "deepseek/deepseek-chat"
    )
    policy = resolve_candidate_stage_policy("pages")
    assert policy.model == "deepseek/deepseek-chat"

    class _NoCallAI:
        name = "openrouter"

        def ask_chat(self, *args, **kwargs):
            raise AssertionError("pages must fail preflight, not call provider")

    class _Renderer:
        def render(self, template, **values):
            return "x" * (REQUEST35_PAGES_ESTIMATE * 3)

    budget = CandidateCallBudget.create()
    with pytest.raises(CandidateStageError) as exc:
        build_ai_batch(
            request_id=3502,
            policy=policy,
            prompt_template="ignored",
            prompt_values={},
            ai_provider=_NoCallAI(),
            template_renderer=_Renderer(),
            phase_deadline=time.monotonic() + 60,
            call_budget=budget,
            candidate_revision_uuid="rev-no-silent-fallback",
        )
    assert exc.value.provider_error_code == "provider_context_length_exceeded"
    attempt = budget.attempts_snapshot()[-1]
    assert attempt["model"] == "deepseek/deepseek-chat"
    assert "selected_fallback" not in (attempt.get("fallback_model_decision") or "")


def test_call_caps_unchanged_total_4_pages_2(isolated_settings) -> None:
    budget = CandidateCallBudget.create()
    assert budget.total_max == 4
    snap = budget.snapshot()
    assert snap["substage_caps"]["business_components"] == 2
    assert snap["substage_caps"]["pages"] == 2
    for _ in range(2):
        assert budget.approve("pages")[0]
    ok, code = budget.approve("pages")
    assert ok is False
    assert code == "candidate_substage_call_budget_exhausted"


def test_successful_pages_preflight_diagnostics_persist(
    monkeypatch, isolated_settings
) -> None:
    policy = resolve_candidate_stage_policy("pages")
    calls: list[str] = []

    class _SuccessfulAI:
        name = "openrouter"

        def ask_chat(self, model, messages, max_tokens=None, **kwargs):
            calls.append(model)
            return json.dumps(
                {
                    "schema_version": "1.0",
                    "batch_kind": "pages",
                    "files": [
                        {
                            "path": "src/pages/HomePage.tsx",
                            "file_kind": "page",
                            "owner_contract_ids": ["home"],
                            "source": "export default function HomePage() { return <div>Home</div>; }",
                        }
                    ],
                }
            )

    class _Renderer:
        def render(self, template, **values):
            # ~33_232 tokens like request #35 pages estimate
            return "x" * (REQUEST35_PAGES_ESTIMATE * 3)

    budget = CandidateCallBudget.create()
    build_ai_batch(
        request_id=3503,
        policy=policy,
        prompt_template="ignored",
        prompt_values={},
        ai_provider=_SuccessfulAI(),
        template_renderer=_Renderer(),
        phase_deadline=time.monotonic() + 60,
        call_budget=budget,
        candidate_revision_uuid="rev-pages-preflight-ok",
    )
    assert calls == ["google/gemini-2.5-flash"]
    assert budget.snapshot()["substage_used"]["pages"] == 1
    assert budget.snapshot()["total_used"] == 1
    preflight = next(
        item
        for item in budget.attempts_snapshot()
        if item["typed_result"] == "preflight_passed"
    )
    assert preflight["model"] == "google/gemini-2.5-flash"
    assert preflight["capability_profile_revision"] == CAPABILITY_PROFILE_REVISION
    assert preflight["context_window"] == 1_048_576
    assert preflight["estimated_input_tokens"] == REQUEST35_PAGES_ESTIMATE
    assert preflight["requested_output_tokens"] == settings.V2_CANDIDATE_PAGE_MAX_TOKENS
    assert preflight["clamped_output_tokens"] >= MINIMUM_VALID_OUTPUT_TOKENS
    assert preflight["minimum_output_allowance"] == MINIMUM_VALID_OUTPUT_TOKENS
    assert preflight["context_reserve"] == CONTEXT_RESERVE_TOKENS
    assert preflight["request_shape_hash"]
    assert preflight["approval_decision"] == "approved_preflight"
    assert preflight["calls_remaining"] == 4  # preflight does not consume budget


def test_phase4_remains_blocked_until_candidate_build_pending() -> None:
    with pytest.raises(Phase4StatusPreconditionError):
        ensure_phase4_entry_status(
            {
                "preview_contract": {
                    "status": "candidate_failed",
                    "failure": {
                        "provider_error_code": "provider_context_length_exceeded",
                        "error_type": "CandidateStageError",
                    },
                }
            }
        )


def test_pages_estimate_token_helper_matches_fixture_size() -> None:
    prompt = "x" * (REQUEST35_PAGES_ESTIMATE * 3)
    assert estimate_prompt_tokens(prompt) == REQUEST35_PAGES_ESTIMATE
