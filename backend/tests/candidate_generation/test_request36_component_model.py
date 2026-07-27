"""Request #36: business_components needs Gemini (≥1M), not DeepSeek 32k."""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path

import pytest

from app.application.appspec.policy import ModelFamilyPolicyError
from app.application.candidate_generation.builder import (
    CandidateStageError,
    build_ai_batch,
)
from app.application.candidate_generation.call_budget import CandidateCallBudget
from app.application.candidate_generation.policy import (
    repair_policy,
    resolve_candidate_stage_policy,
)
from app.application.candidate_generation.service import build_v2_candidate_revision
from app.application.preview_app.pipeline.v2_contract import (
    Phase4StatusPreconditionError,
    ensure_phase4_entry_status,
)
from app.core.config import candidate_model_configuration, settings
from app.infrastructure.ai_providers.model_capabilities import (
    APPROVED_CANDIDATE_COMPONENT_MODEL,
    APPROVED_CANDIDATE_PAGE_MODEL,
    CAPABILITY_PROFILE_REVISION,
    CONTEXT_RESERVE_TOKENS,
    MINIMUM_VALID_OUTPUT_TOKENS,
    clamp_max_tokens,
    estimate_prompt_tokens,
    resolve_model_capability,
)
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from tests.candidate_generation.helpers import (
    CandidateFixtureAI,
    prepare_phase3a,
)


# Production smoke #36 component prompt estimate (failed under DeepSeek 32k).
REQUEST36_COMPONENT_ESTIMATE = 33_139
# Lean-prompt regression ceiling: stay far below Gemini 1M; do not re-bloat.
REQUEST36_COMPONENT_PROMPT_CEILING = 120_000


@pytest.fixture
def isolated_settings(monkeypatch):
    monkeypatch.setattr(
        settings,
        "V2_CANDIDATE_COMPONENT_MODEL",
        APPROVED_CANDIDATE_COMPONENT_MODEL,
    )
    monkeypatch.setattr(
        settings, "V2_CANDIDATE_PAGE_MODEL", APPROVED_CANDIDATE_PAGE_MODEL
    )
    monkeypatch.setattr(settings, "V2_CANDIDATE_COMPONENT_FALLBACK_MODEL", "")
    monkeypatch.setattr(settings, "V2_CANDIDATE_MAX_CALLS", 4)
    monkeypatch.setattr(settings, "PREVIEW_APP_MODEL", "deepseek/deepseek-chat")


@pytest.fixture
def isolated_candidate_paths(monkeypatch):
    root = Path(__file__).resolve().parent / ".runtime" / uuid.uuid4().hex
    candidates = root / "candidates"
    accepted = root / "accepted"
    monkeypatch.setattr(settings, "PREVIEW_CANDIDATES_DIR", candidates)
    monkeypatch.setattr(settings, "PREVIEW_APPS_DIR", accepted)
    yield root
    if root.exists():
        shutil.rmtree(root)


def test_components_and_pages_use_gemini_not_preview_app_model(
    isolated_settings,
) -> None:
    components = resolve_candidate_stage_policy("business_components")
    pages = resolve_candidate_stage_policy("pages")
    assert components.model == "google/gemini-2.5-flash"
    assert pages.model == "google/gemini-2.5-flash"
    assert components.model != settings.PREVIEW_APP_MODEL
    assert pages.model != settings.PREVIEW_APP_MODEL
    assert settings.PREVIEW_APP_MODEL == "deepseek/deepseek-chat"
    for model in (components.model, pages.model):
        cap = resolve_model_capability(model)
        assert cap.context_window == 1_048_576
        assert cap.revision == CAPABILITY_PROFILE_REVISION
        assert cap.supports_json_text_mode is True


def test_request36_component_estimate_fails_under_deepseek() -> None:
    estimated = REQUEST36_COMPONENT_ESTIMATE
    deepseek = resolve_model_capability("deepseek/deepseek-chat")
    assert deepseek.context_window == 32_768
    assert estimated >= deepseek.context_window
    clamped = clamp_max_tokens(
        requested_max_tokens=24_000,
        estimated_input_tokens=estimated,
        context_window=deepseek.context_window,
    )
    assert clamped == 0


def test_request36_component_estimate_passes_under_gemini() -> None:
    estimated = REQUEST36_COMPONENT_ESTIMATE
    gemini = resolve_model_capability(APPROVED_CANDIDATE_COMPONENT_MODEL)
    assert gemini.context_window == 1_048_576
    assert estimated < gemini.context_window
    clamped = clamp_max_tokens(
        requested_max_tokens=24_000,
        estimated_input_tokens=estimated,
        context_window=gemini.context_window,
    )
    assert clamped == 24_000
    assert clamped >= MINIMUM_VALID_OUTPUT_TOKENS


def test_pages_requested_clamped_output_remains_32000(isolated_settings) -> None:
    pages = resolve_candidate_stage_policy("pages")
    assert pages.max_tokens == 32_000
    gemini = resolve_model_capability(pages.model)
    clamped = clamp_max_tokens(
        requested_max_tokens=pages.max_tokens,
        estimated_input_tokens=33_232,
        context_window=gemini.context_window,
    )
    assert clamped == 32_000


def test_missing_component_model_fails_closed(monkeypatch, isolated_settings) -> None:
    monkeypatch.setattr(settings, "V2_CANDIDATE_COMPONENT_MODEL", "")
    with pytest.raises(ModelFamilyPolicyError) as exc:
        resolve_candidate_stage_policy("business_components")
    assert "candidate_component_model_not_configured" in str(exc.value)


def test_unknown_component_model_fails_closed_without_deepseek_fallback(
    monkeypatch, isolated_settings
) -> None:
    monkeypatch.setattr(
        settings,
        "V2_CANDIDATE_COMPONENT_MODEL",
        "google/unprofiled-component-model",
    )
    monkeypatch.setattr(
        settings, "V2_CANDIDATE_COMPONENT_FALLBACK_MODEL", "deepseek/deepseek-chat"
    )
    policy = resolve_candidate_stage_policy("business_components")
    assert policy.model == "google/unprofiled-component-model"

    class _NoCallAI:
        name = "openrouter"

        def ask_chat(self, *args, **kwargs):
            raise AssertionError("must not call provider for unknown component model")

    class _Renderer:
        def render(self, template, **values):
            return "x" * (REQUEST36_COMPONENT_ESTIMATE * 3)

    budget = CandidateCallBudget.create()
    remaining_before = budget.remaining_total()
    assert remaining_before == 4

    with pytest.raises(CandidateStageError) as exc:
        build_ai_batch(
            request_id=3601,
            policy=policy,
            prompt_template="ignored",
            prompt_values={},
            ai_provider=_NoCallAI(),
            template_renderer=_Renderer(),
            phase_deadline=time.monotonic() + 60,
            call_budget=budget,
            candidate_revision_uuid="rev-unknown-components",
        )
    assert exc.value.provider_error_code == (
        "candidate_component_model_capability_unknown"
    )
    assert budget.remaining_total() == remaining_before
    attempts = budget.attempts_snapshot()
    assert attempts
    assert attempts[-1]["model"] == "google/unprofiled-component-model"
    assert attempts[-1]["approval_decision"] == "denied_preflight"
    assert "selected_fallback" not in (
        attempts[-1].get("fallback_model_decision") or ""
    )


def test_deepseek_component_preflight_fails_before_provider_approval(
    monkeypatch, isolated_settings
) -> None:
    monkeypatch.setattr(
        settings, "V2_CANDIDATE_COMPONENT_MODEL", "deepseek/deepseek-chat"
    )
    policy = resolve_candidate_stage_policy("business_components")
    assert policy.model == "deepseek/deepseek-chat"

    class _NoCallAI:
        name = "openrouter"

        def ask_chat(self, *args, **kwargs):
            raise AssertionError("DeepSeek #36 preflight must not call provider")

    class _Renderer:
        def render(self, template, **values):
            return "x" * (REQUEST36_COMPONENT_ESTIMATE * 3)

    budget = CandidateCallBudget.create()
    with pytest.raises(CandidateStageError) as exc:
        build_ai_batch(
            request_id=3602,
            policy=policy,
            prompt_template="ignored",
            prompt_values={},
            ai_provider=_NoCallAI(),
            template_renderer=_Renderer(),
            phase_deadline=time.monotonic() + 60,
            call_budget=budget,
            candidate_revision_uuid="rev-deepseek-36",
        )
    assert exc.value.provider_error_code == "provider_context_length_exceeded"
    assert budget.snapshot()["total_used"] == 0
    attempt = budget.attempts_snapshot()[-1]
    assert attempt["model"] == "deepseek/deepseek-chat"
    assert attempt["context_window"] == 32_768
    assert attempt["estimated_input_tokens"] == REQUEST36_COMPONENT_ESTIMATE
    assert attempt["requested_output_tokens"] == 24_000
    assert attempt["clamped_output_tokens"] == 0
    assert attempt["approval_decision"] == "denied_preflight"


def test_call_caps_unchanged_total_4_components_2_pages_2(
    isolated_settings,
) -> None:
    budget = CandidateCallBudget.create()
    assert budget.total_max == 4
    snap = budget.snapshot()
    assert snap["substage_caps"]["business_components"] == 2
    assert snap["substage_caps"]["pages"] == 2
    for _ in range(2):
        assert budget.approve("business_components")[0]
    ok, code = budget.approve("business_components")
    assert ok is False
    assert code == "candidate_substage_call_budget_exhausted"


def test_component_repair_policy_remains_bounded_glm(
    isolated_settings,
) -> None:
    repair = repair_policy()
    assert repair.model == settings.V2_CANDIDATE_REPAIR_MODEL
    assert repair.max_tokens == settings.V2_CANDIDATE_REPAIR_MAX_TOKENS
    # Repair is a separate stage policy; call budget still caps components at 2.
    budget = CandidateCallBudget.create()
    assert budget.approve("business_components")[0]
    assert budget.approve("business_components")[0]
    ok, code = budget.approve("business_components")
    assert ok is False
    assert code == "candidate_substage_call_budget_exhausted"


def test_successful_component_preflight_diagnostics_persist(
    monkeypatch, isolated_settings
) -> None:
    policy = resolve_candidate_stage_policy("business_components")
    calls: list[str] = []

    class _SuccessfulAI:
        name = "openrouter"

        def ask_chat(self, model, messages, max_tokens=None, **kwargs):
            calls.append(model)
            return json.dumps(
                {
                    "schema_version": "1.0",
                    "batch_kind": "business_components",
                    "files": [
                        {
                            "path": (
                                "src/components/business/CompBookComponent.tsx"
                            ),
                            "file_kind": "business_component",
                            "owner_contract_ids": ["book"],
                            "source": (
                                "export default function CompBookComponent()"
                                " { return <div>Book</div>; }"
                            ),
                        }
                    ],
                }
            )

    class _Renderer:
        def render(self, template, **values):
            return "x" * (REQUEST36_COMPONENT_ESTIMATE * 3)

    budget = CandidateCallBudget.create()
    build_ai_batch(
        request_id=3603,
        policy=policy,
        prompt_template="ignored",
        prompt_values={},
        ai_provider=_SuccessfulAI(),
        template_renderer=_Renderer(),
        phase_deadline=time.monotonic() + 60,
        call_budget=budget,
        candidate_revision_uuid="rev-components-preflight-ok",
    )
    assert calls == ["google/gemini-2.5-flash"]
    assert budget.snapshot()["substage_used"]["business_components"] == 1
    assert budget.snapshot()["total_used"] == 1
    preflight = next(
        item
        for item in budget.attempts_snapshot()
        if item["typed_result"] == "preflight_passed"
    )
    assert preflight["model"] == "google/gemini-2.5-flash"
    assert preflight["capability_profile_revision"] == CAPABILITY_PROFILE_REVISION
    assert preflight["context_window"] == 1_048_576
    assert preflight["estimated_input_tokens"] == REQUEST36_COMPONENT_ESTIMATE
    assert (
        preflight["requested_output_tokens"]
        == settings.V2_CANDIDATE_COMPONENT_MAX_TOKENS
    )
    assert preflight["clamped_output_tokens"] == 24_000
    assert preflight["minimum_output_allowance"] == MINIMUM_VALID_OUTPUT_TOKENS
    assert preflight["context_reserve"] == CONTEXT_RESERVE_TOKENS
    assert preflight["request_shape_hash"]
    assert preflight["approval_decision"] == "approved_preflight"
    assert preflight["calls_remaining"] == 4


def test_trusted_diagnostics_expose_component_and_pages_models(
    isolated_settings,
) -> None:
    payload = candidate_model_configuration(settings)
    assert payload["component"]["effective_model"] == "google/gemini-2.5-flash"
    assert payload["component"]["context_window"] == 1_048_576
    assert (
        payload["component"]["capability_profile_revision"]
        == CAPABILITY_PROFILE_REVISION
    )
    assert payload["pages"]["effective_model"] == "google/gemini-2.5-flash"
    assert payload["pages"]["context_window"] == 1_048_576
    assert payload["preview_app_model"] == "deepseek/deepseek-chat"
    assert payload["component"]["inherits_preview_app_model"] is False
    assert payload["pages"]["inherits_preview_app_model"] is False


def test_request36_after_gemini_reaches_pages_and_build_pending(
    isolated_candidate_paths,
    isolated_settings,
) -> None:
    prepared = prepare_phase3a(request_id=3604, page_count=5)
    captured_components: list[str] = []
    models_used: list[str] = []

    class _CaptureAI(CandidateFixtureAI):
        def ask_chat(self, model, messages, max_tokens=None, temperature=None, **kwargs):
            models_used.append(model)
            prompt = messages[0]["content"]
            if "business-component generation stage" in prompt:
                captured_components.append(prompt)
                assert "omitted_sections" in prompt
                assert '"canonical_app_spec":' not in prompt
                assert '"product_strategy_v2":' not in prompt
                assert '"information_architecture":' not in prompt
                estimated = estimate_prompt_tokens(prompt)
                assert estimated < REQUEST36_COMPONENT_PROMPT_CEILING
                assert estimated < resolve_model_capability(model).context_window
            return super().ask_chat(
                model,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )

    try:
        result = build_v2_candidate_revision(
            prepared.db,
            prepared.req.id,
            _CaptureAI(),
            JinjaTemplateRenderer(settings.TEMPLATES_DIR),
            req=prepared.req,
            phase3a_result=prepared.phase3a_result,
        )
        pc = result["preview_contract"]
        assert pc["status"] == "candidate_build_pending"
        assert captured_components, "business_components prompt was not captured"
        assert "google/gemini-2.5-flash" in models_used
        totals = pc["candidate_totals"]
        assert totals["provider_call_count"] <= 4
        stages = pc["candidate_stage_metrics"]
        assert stages["business_components"]["provider_call_count"] <= 2
        assert stages["pages"]["provider_call_count"] <= 2
        assert stages["business_components"]["effective_model"].startswith(
            "google/gemini-2.5-flash"
        )
        assert stages["pages"]["effective_model"].startswith(
            "google/gemini-2.5-flash"
        )
        ensure_phase4_entry_status(result)
    finally:
        prepared.db.close()


def test_request36_deepseek_blocks_pages_and_phase4(
    isolated_candidate_paths,
    monkeypatch,
    isolated_settings,
) -> None:
    monkeypatch.setattr(
        settings, "V2_CANDIDATE_COMPONENT_MODEL", "deepseek/deepseek-chat"
    )

    class _HugeComponentAI(CandidateFixtureAI):
        def ask_chat(self, model, messages, max_tokens=None, temperature=None, **kwargs):
            raise AssertionError("provider must not be reached after preflight fail")

    # Force oversized component prompt estimate via monkeypatched renderer path:
    # use real pipeline but inject estimate by making component model DeepSeek
    # and substituting build_ai_batch renderer through a tiny custom path is hard;
    # instead exercise build_ai_batch + ensure full pipeline fails before pages
    # when components preflight fails with the #36-sized estimate.
    from app.application.candidate_generation import builder as builder_mod
    from app.application.candidate_generation import service as service_mod

    real_build = builder_mod.build_ai_batch

    def _wrap_build_ai_batch(*, policy, template_renderer, **kwargs):
        if policy.stage == "business_components":

            class _HugeRenderer:
                def render(self, template, **values):
                    return "x" * (REQUEST36_COMPONENT_ESTIMATE * 3)

            return real_build(
                policy=policy,
                template_renderer=_HugeRenderer(),
                **kwargs,
            )
        return real_build(
            policy=policy,
            template_renderer=template_renderer,
            **kwargs,
        )

    monkeypatch.setattr(service_mod, "build_ai_batch", _wrap_build_ai_batch)
    prepared = prepare_phase3a(request_id=3605, page_count=5)
    ai = _HugeComponentAI()
    try:
        result = build_v2_candidate_revision(
            prepared.db,
            prepared.req.id,
            ai,
            JinjaTemplateRenderer(settings.TEMPLATES_DIR),
            req=prepared.req,
            phase3a_result=prepared.phase3a_result,
        )
        pc = result["preview_contract"]
        assert pc["status"] == "candidate_failed"
        failure = pc.get("failure") or {}
        assert failure.get("provider_error_code") == (
            "provider_context_length_exceeded"
        )
        assert failure.get("phase4_ran") is False
        assert failure.get("stage") == "business_components"
        assert ai.calls == []
        with pytest.raises(Phase4StatusPreconditionError):
            ensure_phase4_entry_status(result)
    finally:
        prepared.db.close()


def test_component_estimate_token_helper_matches_fixture_size() -> None:
    prompt = "x" * (REQUEST36_COMPONENT_ESTIMATE * 3)
    assert estimate_prompt_tokens(prompt) == REQUEST36_COMPONENT_ESTIMATE


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
