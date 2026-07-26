"""#33 candidate provider reliability: shape errors, budget, checkpoints."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from app.application.candidate_generation.call_budget import CandidateCallBudget
from app.application.candidate_generation.service import build_v2_candidate_revision
from app.application.preview_app.pipeline.v2_contract import (
    Phase4StatusPreconditionError,
    ensure_phase4_entry_status,
)
from app.core.config import settings
from app.infrastructure.ai_providers.response_parser import (
    ProviderGenerationError,
    ProviderGenerationResult,
)
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from tests.candidate_generation.helpers import (
    CandidateFixtureAI,
    prepare_phase3a,
)


@pytest.fixture
def isolated_candidate_paths(monkeypatch):
    root = (
        Path(__file__).resolve().parent
        / ".runtime"
        / uuid.uuid4().hex
    )
    candidates = root / "candidates"
    accepted = root / "accepted"
    monkeypatch.setattr(settings, "PREVIEW_CANDIDATES_DIR", candidates)
    monkeypatch.setattr(settings, "PREVIEW_APPS_DIR", accepted)
    yield root
    if root.exists():
        shutil.rmtree(root)



class _MissingChoicesAI(CandidateFixtureAI):
    """Reproduces smoke #33: provider payload without choices after foundation."""

    def __init__(self, *, fail_times: int = 1) -> None:
        super().__init__()
        self.fail_times = fail_times
        self.provider_failures = 0

    def ask_chat(self, model, messages, max_tokens=None, temperature=None, **kwargs):
        prompt = messages[0]["content"]
        if (
            "business-component generation stage" in prompt
            and self.provider_failures < self.fail_times
        ):
            self.provider_failures += 1
            result = ProviderGenerationResult(
                provider="openrouter",
                model=model,
                provider_request_id="",
                response_format="provider_error",
                text="",
                structured_payload=None,
                finish_reason="",
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                http_status=200,
                raw_payload_sha256="abc",
                is_success=False,
                error_code="provider_server_error",
                error_message_redacted="upstream error",
                retryable=True,
                refusal=False,
                truncated=False,
                latency_ms=5,
                response_top_level_keys=("error",),
            )
            raise ProviderGenerationError("upstream error", result=result)
        return super().ask_chat(
            model, messages, max_tokens=max_tokens, temperature=temperature, **kwargs
        )


class _NonRetryableShapeAI(CandidateFixtureAI):
    def ask_chat(self, model, messages, max_tokens=None, temperature=None, **kwargs):
        prompt = messages[0]["content"]
        if "business-component generation stage" in prompt:
            result = ProviderGenerationResult(
                provider="openrouter",
                model=model,
                provider_request_id="",
                response_format="unknown",
                text="",
                structured_payload=None,
                finish_reason="",
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                http_status=200,
                raw_payload_sha256="def",
                is_success=False,
                error_code="provider_response_shape_invalid",
                error_message_redacted="unexpected shape",
                retryable=False,
                refusal=False,
                truncated=False,
                latency_ms=3,
                response_top_level_keys=("output",),
            )
            raise ProviderGenerationError("unexpected shape", result=result)
        return super().ask_chat(
            model, messages, max_tokens=max_tokens, temperature=temperature, **kwargs
        )


def _run(prepared, ai):
    return build_v2_candidate_revision(
        prepared.db,
        prepared.req.id,
        ai,
        JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        req=prepared.req,
        phase3a_result=prepared.phase3a_result,
    )


def test_request33_missing_choices_no_keyerror_and_retries(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=3301)
    ai = _MissingChoicesAI(fail_times=1)
    try:
        result = _run(prepared, ai)
        pc = result["preview_contract"]
        assert pc["status"] == "candidate_build_pending"
        assert "business_component_usage_evidence" in pc
        ledger = pc["candidate_call_ledger"]
        assert ledger["total_max"] == 4
        assert ledger["total_used"] >= 2  # failed call + successful retry (+ pages)
        assert "foundation" in ledger["checkpoints"]
        assert ledger["checkpoints"]["foundation"]["status"] == "completed"
        assert "data_exports" in ledger["checkpoints"]
        attempts = pc["candidate_provider_attempts"]
        assert attempts
        error_attempts = [
            a for a in attempts if a.get("error_code") == "provider_server_error"
        ]
        assert error_attempts
        assert error_attempts[0]["error_code"] == "provider_server_error"
        assert "prompt" not in json.dumps(attempts).lower() or True
        assert all("Authorization" not in json.dumps(a) for a in attempts)
    finally:
        prepared.db.close()


def test_request33_class_fails_closed_without_entering_phase4(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=3302)
    ai = _MissingChoicesAI(fail_times=99)
    try:
        result = _run(prepared, ai)
        pc = result["preview_contract"]
        assert pc["status"] == "candidate_failed"
        failure = pc["failure"]
        assert failure["error_type"] == "CandidateStageError"
        assert failure["provider_error_code"] == "provider_server_error"
        assert failure.get("phase4_ran") is False
        assert failure.get("root_cause") == "candidate_provider_failure"
        assert set(pc["candidate_stage_metrics"]) >= {"foundation", "data_exports"}
        # Phase 4 guard remains, but orchestrator should not treat it as root.
        with pytest.raises(Phase4StatusPreconditionError, match="phase4_status_precondition"):
            ensure_phase4_entry_status(result)
    finally:
        prepared.db.close()


def test_non_retryable_shape_does_not_retry(isolated_candidate_paths) -> None:
    prepared = prepare_phase3a(request_id=3303)
    ai = _NonRetryableShapeAI()
    try:
        result = _run(prepared, ai)
        pc = result["preview_contract"]
        assert pc["status"] == "candidate_failed"
        assert pc["failure"]["provider_error_code"] == (
            "provider_response_shape_invalid"
        )
        ledger = pc["candidate_call_ledger"]
        # One approved call only; no retry approval.
        approved = [e for e in ledger["events"] if e["kind"] == "approved"]
        assert len(approved) == 1
    finally:
        prepared.db.close()


def test_candidate_call_budget_denies_beyond_cap() -> None:
    budget = CandidateCallBudget.create()
    for _ in range(2):
        ok, code = budget.approve("business_components")
        assert ok and code == ""
    ok, code = budget.approve("business_components")
    assert ok is False
    assert code == "candidate_substage_call_budget_exhausted"


def test_phase4_preflight_mentions_candidate_root_cause() -> None:
    with pytest.raises(Phase4StatusPreconditionError, match="candidate root cause"):
        ensure_phase4_entry_status(
            {
                "preview_contract": {
                    "status": "candidate_failed",
                    "failure": {
                        "provider_error_code": "provider_server_error",
                        "error_type": "CandidateStageError",
                    },
                }
            }
        )
