"""Request #34: context-overflow failure and lean-prompt recovery path."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from app.application.candidate_generation.builder import CandidateStageError
from app.application.candidate_generation.call_budget import (
    CandidateCallBudget,
    CandidateStageCheckpoint,
)
from app.application.candidate_generation.service import build_v2_candidate_revision
from app.application.preview_app.pipeline.v2_contract import (
    Phase4StatusPreconditionError,
    ensure_phase4_entry_status,
)
from app.core.config import settings
from app.infrastructure.ai_providers.response_parser import (
    ProviderGenerationError,
    ProviderGenerationResult,
    parse_openai_compatible_chat_response,
)
from app.infrastructure.ai_providers.model_capabilities import (
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


REQUEST34_ERROR = {
    "object": "error",
    "message": (
        "The sum of prompt length (38049.0), query length (0) "
        "should not exceed max_num_tokens (32768)"
    ),
    "type": "BadRequestError",
    "param": None,
    "code": 400,
}


class _Request34OverflowAI(CandidateFixtureAI):
    """Before lean-prompt fix: provider returns exact #34 error shape."""

    def __init__(self) -> None:
        super().__init__()
        self.component_calls = 0

    def ask_chat(self, model, messages, max_tokens=None, temperature=None, **kwargs):
        prompt = messages[0]["content"]
        if "business-component generation stage" in prompt:
            self.component_calls += 1
            # Simulate old oversized prompt by forcing the provider error path.
            result = parse_openai_compatible_chat_response(
                provider="openrouter",
                model=model,
                http_status=200,
                body={"error": REQUEST34_ERROR},
                raw_text=json.dumps({"error": REQUEST34_ERROR}),
                latency_ms=664,
            )
            raise ProviderGenerationError(
                result.error_message_redacted, result=result
            )
        return super().ask_chat(
            model, messages, max_tokens=max_tokens, temperature=temperature, **kwargs
        )


def test_request34_error_classified_context_overflow() -> None:
    result = parse_openai_compatible_chat_response(
        provider="openrouter",
        model="deepseek/deepseek-chat",
        http_status=200,
        body={"error": REQUEST34_ERROR},
        raw_text=json.dumps({"error": REQUEST34_ERROR}),
    )
    assert result.error_code == "provider_context_length_exceeded"
    assert result.retryable is False
    assert result.response_format == "provider_error"


def test_candidate_model_capabilities_are_explicit_and_unknown_fails_closed() -> None:
    production = resolve_model_capability("deepseek/deepseek-chat")
    pages = resolve_model_capability("google/gemini-2.5-flash")
    unknown = resolve_model_capability("deepseek/unprofiled-candidate-model")

    assert production.context_window == 32_768
    assert production.known is True
    assert pages.context_window == 1_048_576
    assert pages.known is True
    assert pages.supports_json_text_mode is True
    assert unknown.context_window == 0
    assert unknown.known is False
    assert production.revision == CAPABILITY_PROFILE_REVISION
    assert CAPABILITY_PROFILE_REVISION == "2026-07-26.candidate-provider.3"


def test_max_tokens_clamp_rejects_unusable_output_allowance() -> None:
    assert (
        clamp_max_tokens(
            requested_max_tokens=24_000,
            estimated_input_tokens=32_768
            - CONTEXT_RESERVE_TOKENS
            - MINIMUM_VALID_OUTPUT_TOKENS
            + 1,
            context_window=32_768,
        )
        == 0
    )
    assert (
        clamp_max_tokens(
            requested_max_tokens=MINIMUM_VALID_OUTPUT_TOKENS - 1,
            estimated_input_tokens=1_000,
            context_window=32_768,
        )
        == 0
    )
    assert (
        clamp_max_tokens(
            requested_max_tokens=24_000,
            estimated_input_tokens=8_000,
            context_window=32_768,
        )
        >= MINIMUM_VALID_OUTPUT_TOKENS
    )


def test_request34_before_fix_fails_before_pages(
    isolated_candidate_paths,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "V2_CANDIDATE_COMPONENT_FALLBACK_MODEL", "")
    prepared = prepare_phase3a(request_id=3401, page_count=5)
    ai = _Request34OverflowAI()
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
        assert failure.get("provider_error_code") == "provider_context_length_exceeded"
        assert failure.get("phase4_ran") is False
        assert ai.component_calls == 1
        with pytest.raises(Phase4StatusPreconditionError):
            ensure_phase4_entry_status(result)
    finally:
        prepared.db.close()


def test_request34_after_lean_prompt_omits_full_appspec(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=3402, page_count=5)
    captured: list[str] = []

    class _CaptureAI(CandidateFixtureAI):
        def ask_chat(self, model, messages, max_tokens=None, temperature=None, **kwargs):
            prompt = messages[0]["content"]
            if "business-component generation stage" in prompt:
                captured.append(prompt)
                assert "omitted_sections" in prompt
                assert "full_raw_app_spec" in prompt
                assert "design_dna_tokens" in prompt
                # Top-level dumps must be absent; nested contract field names may remain.
                assert '"canonical_app_spec":' not in prompt
                assert '"product_strategy_v2":' not in prompt
                assert '"information_architecture":' not in prompt
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
        assert captured, "business_components prompt was not captured"
        production = resolve_model_capability("deepseek/deepseek-chat")
        estimated = estimate_prompt_tokens(captured[0])
        assert (
            estimated
            + CONTEXT_RESERVE_TOKENS
            + MINIMUM_VALID_OUTPUT_TOKENS
            <= production.context_window
        )
        assert result["preview_contract"]["status"] in {
            "candidate_build_pending",
            "candidate_generated",
            "candidate_contract_failed",
        }
        if result["preview_contract"]["status"] == "candidate_build_pending":
            ensure_phase4_entry_status(result)
    finally:
        prepared.db.close()


def test_context_preflight_does_not_enter_phase4() -> None:
    from app.application.candidate_generation.builder import build_ai_batch
    from app.application.candidate_generation.policy import CandidateStagePolicy

    class _NoCallAI:
        name = "openrouter"

        def ask_chat(self, *args, **kwargs):
            raise AssertionError("provider must not be called on preflight fail")

    class _HugeRenderer:
        def render(self, template, **values):
            return "x" * (40_000 * 4)  # ~40k tokens

    policy = CandidateStagePolicy(
        stage="business_components",
        model="deepseek/deepseek-chat",
        model_family="deepseek",
        prompt_revision="test",
        max_tokens=24000,
        temperature=0.25,
        timeout_seconds=30,
        ai_authored=True,
    )
    budget = CandidateCallBudget.create()
    with pytest.raises(CandidateStageError) as exc:
        build_ai_batch(
            request_id=99,
            policy=policy,
            prompt_template="ignored",
            prompt_values={},
            ai_provider=_NoCallAI(),
            template_renderer=_HugeRenderer(),
            phase_deadline=__import__("time").monotonic() + 60,
            call_budget=budget,
            candidate_revision_uuid="rev-test",
        )
    assert exc.value.provider_error_code == "provider_context_length_exceeded"
    assert budget.remaining_total() == budget.total_max
    assert budget.attempts_snapshot()
    attempt = budget.attempts_snapshot()[0]
    assert attempt["terminal_decision"] == "fail_closed_preflight"
    assert attempt["error_code"] == "provider_context_length_exceeded"
    with pytest.raises(Phase4StatusPreconditionError):
        ensure_phase4_entry_status(
            {
                "preview_contract": {
                    "status": "candidate_failed",
                    "failure": {"provider_error_code": "provider_context_length_exceeded"},
                }
            }
        )


def test_preflight_blocks_below_minimum_output_allowance() -> None:
    from app.application.candidate_generation.builder import build_ai_batch
    from app.application.candidate_generation.policy import CandidateStagePolicy

    class _NoCallAI:
        name = "openrouter"

        def ask_chat(self, *args, **kwargs):
            raise AssertionError("provider must not be called with unusable output budget")

    class _NearlyFullRenderer:
        def render(self, template, **values):
            estimated_tokens = (
                32_768
                - CONTEXT_RESERVE_TOKENS
                - MINIMUM_VALID_OUTPUT_TOKENS
                + 1
            )
            prompt = "x" * (estimated_tokens * 3)
            assert estimate_prompt_tokens(prompt) == estimated_tokens
            return prompt

    policy = CandidateStagePolicy(
        stage="business_components",
        model="deepseek/deepseek-chat",
        model_family="deepseek",
        prompt_revision="test",
        max_tokens=24_000,
        temperature=0.25,
        timeout_seconds=30,
        ai_authored=True,
    )
    budget = CandidateCallBudget.create()
    with pytest.raises(CandidateStageError) as exc:
        build_ai_batch(
            request_id=100,
            policy=policy,
            prompt_template="ignored",
            prompt_values={},
            ai_provider=_NoCallAI(),
            template_renderer=_NearlyFullRenderer(),
            phase_deadline=__import__("time").monotonic() + 60,
            call_budget=budget,
            candidate_revision_uuid="rev-minimum-output",
        )
    assert exc.value.provider_error_code == "provider_context_length_exceeded"
    assert budget.remaining_total() == budget.total_max


def test_unknown_model_capability_blocks_before_provider_call(monkeypatch) -> None:
    from app.application.candidate_generation.builder import build_ai_batch
    from app.application.candidate_generation.policy import CandidateStagePolicy

    class _NoCallAI:
        name = "openrouter"

        def ask_chat(self, *args, **kwargs):
            raise AssertionError("provider must not be called for unknown model")

    class _SmallRenderer:
        def render(self, template, **values):
            return "small prompt"

    policy = CandidateStagePolicy(
        stage="business_components",
        model="deepseek/unprofiled-candidate-model",
        model_family="deepseek",
        prompt_revision="test",
        max_tokens=24_000,
        temperature=0.25,
        timeout_seconds=30,
        ai_authored=True,
    )
    budget = CandidateCallBudget.create()
    monkeypatch.setattr(
        settings,
        "V2_CANDIDATE_COMPONENT_FALLBACK_MODEL",
        "deepseek/deepseek-chat-v3",
    )
    with pytest.raises(CandidateStageError) as exc:
        build_ai_batch(
            request_id=101,
            policy=policy,
            prompt_template="ignored",
            prompt_values={},
            ai_provider=_NoCallAI(),
            template_renderer=_SmallRenderer(),
            phase_deadline=__import__("time").monotonic() + 60,
            call_budget=budget,
            candidate_revision_uuid="rev-unknown-model",
        )
    assert exc.value.provider_error_code == "provider_context_length_exceeded"
    assert budget.remaining_total() == budget.total_max


def test_unset_fallback_keeps_primary_model(monkeypatch) -> None:
    from app.application.candidate_generation.builder import build_ai_batch
    from app.application.candidate_generation.policy import CandidateStagePolicy

    calls: list[str] = []

    class _SuccessfulAI:
        name = "openrouter"

        def ask_chat(self, model, messages, **kwargs):
            calls.append(model)
            return json.dumps(
                {
                    "schema_version": "1.0",
                    "batch_kind": "business_components",
                    "files": [
                        {
                            "path": "src/components/business/Booking.tsx",
                            "file_kind": "business_component",
                            "owner_contract_ids": ["booking"],
                            "source": "export function Booking() { return <div>Booking</div>; }",
                        }
                    ],
                }
            )

    class _SmallRenderer:
        def render(self, template, **values):
            return "small prompt"

    monkeypatch.setattr(settings, "V2_CANDIDATE_COMPONENT_FALLBACK_MODEL", "")
    policy = CandidateStagePolicy(
        stage="business_components",
        model="deepseek/deepseek-chat",
        model_family="deepseek",
        prompt_revision="test",
        max_tokens=24_000,
        temperature=0.25,
        timeout_seconds=30,
        ai_authored=True,
    )
    budget = CandidateCallBudget.create()
    build_ai_batch(
        request_id=102,
        policy=policy,
        prompt_template="ignored",
        prompt_values={},
        ai_provider=_SuccessfulAI(),
        template_renderer=_SmallRenderer(),
        phase_deadline=__import__("time").monotonic() + 60,
        call_budget=budget,
        candidate_revision_uuid="rev-primary-only",
    )
    assert calls == ["deepseek/deepseek-chat"]
    assert budget.snapshot()["total_used"] == 1


def test_larger_profile_fallback_uses_one_call_and_preserves_checkpoints(
    monkeypatch,
) -> None:
    from app.application.candidate_generation.builder import build_ai_batch
    from app.application.candidate_generation.policy import CandidateStagePolicy

    calls: list[tuple[str, int]] = []

    class _SuccessfulAI:
        name = "openrouter"

        def ask_chat(self, model, messages, max_tokens=None, **kwargs):
            calls.append((model, max_tokens))
            return json.dumps(
                {
                    "schema_version": "1.0",
                    "batch_kind": "business_components",
                    "files": [
                        {
                            "path": "src/components/business/Booking.tsx",
                            "file_kind": "business_component",
                            "owner_contract_ids": ["booking"],
                            "source": "export function Booking() { return <div>Booking</div>; }",
                        }
                    ],
                }
            )

    class _PrimaryOverflowRenderer:
        def render(self, template, **values):
            return "x" * (40_000 * 3)

    monkeypatch.setattr(
        settings,
        "V2_CANDIDATE_COMPONENT_FALLBACK_MODEL",
        "deepseek/deepseek-chat-v3",
    )
    policy = CandidateStagePolicy(
        stage="business_components",
        model="deepseek/deepseek-chat",
        model_family="deepseek",
        prompt_revision="test",
        max_tokens=24_000,
        temperature=0.25,
        timeout_seconds=30,
        ai_authored=True,
    )
    budget = CandidateCallBudget.create()
    for stage in ("foundation", "data_exports"):
        budget.record_checkpoint(
            CandidateStageCheckpoint(
                substage=stage,
                input_hash=f"{stage}-input",
                output_hash=f"{stage}-output",
                status="completed",
                idempotency_key=f"rev-fallback:{stage}",
            )
        )

    build_ai_batch(
        request_id=103,
        policy=policy,
        prompt_template="ignored",
        prompt_values={},
        ai_provider=_SuccessfulAI(),
        template_renderer=_PrimaryOverflowRenderer(),
        phase_deadline=__import__("time").monotonic() + 60,
        call_budget=budget,
        candidate_revision_uuid="rev-fallback",
    )

    assert calls == [("deepseek/deepseek-chat-v3", 23_488)]
    snapshot = budget.snapshot()
    assert snapshot["total_used"] == 1
    assert set(snapshot["checkpoints"]) == {"foundation", "data_exports"}
    assert all(
        item["status"] == "completed"
        for item in snapshot["checkpoints"].values()
    )
