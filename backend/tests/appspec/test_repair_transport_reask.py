"""The repair-path asks re-ask an error-cut stream instead of judging it.

Session 19, run 123: a schema_repair stream error-cut at 349 chars bypassed the
provider-error gate — its call site never threaded ``finish_reason`` into the
parser — and the extracted fragment consumed the only schema-repair attempt.
Run 128 proved the authoring loop's re-ask handles the same weather. Session
20 routes every candidate-shaped ask (repair, schema_repair) through one
bounded helper, and the coverage review — which parses leniently enough to
adjudicate a fragment of a cut stream, request 118's exact shape — refuses
``finish_reason=error`` outright so generation.py's existing one-shot retry is
its bounded re-ask.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.appspec.builder import (
    AppSpecBuildError,
    repair_app_spec_candidate,
)
from app.application.appspec.coverage import (
    AppSpecCoverageError,
    review_app_spec_coverage,
)
from app.application.appspec.fallback import build_fallback_app_spec
from app.application.appspec.schema_repair import repair_app_spec_schema_candidate
from app.application.services.ai_context import current_ai_call
from app.core.config import settings
from app.infrastructure.ai_providers.response_parser import (
    ProviderGenerationError,
    ProviderGenerationResult,
)

# The run-123 shape: an error-cut body whose prefix carries one small complete
# object — the fragment the extractors would adjudicate without the gate.
_ERROR_CUT_BODY = (
    'Sketch: {"fragment": true}\n'
    'Full spec: {"schema_version": "1", "product_intent": {"summary": "cut'
)

_COMPLETE_BODY = json.dumps(
    {"schema_version": "1", "product_intent": {"summary": "repaired"}, "pages": []}
)

_COVERAGE_BODY = json.dumps(
    {
        "verdict": "pass",
        "score": 95,
        "minimum_score": 80,
        "omissions": [],
        "distortions": [],
        "summary": "covers the brief",
    }
)


def _empty_cut_error() -> ProviderGenerationError:
    result = ProviderGenerationResult(
        provider="openrouter",
        model="google/gemini-2.5-flash",
        provider_request_id="req-x",
        response_format="unknown",
        text="",
        structured_payload=None,
        finish_reason="error",
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        http_status=200,
        raw_payload_sha256="0" * 64,
        is_success=False,
        error_code="provider_empty_response",
        error_message_redacted="provider returned an empty error-cut stream",
        retryable=True,
        refusal=False,
        truncated=False,
        latency_ms=8,
    )
    error = ProviderGenerationError("empty error-cut stream", result=result)
    assert error.retryable  # the fixture must be the retryable transport shape
    return error


class _StubRenderer:
    def render(self, *_args: Any, **_kwargs: Any) -> str:
        return "REPAIR_PROMPT"


class _MetaAI:
    """Turns are (finish_reason, body) or an exception instance to raise."""

    def __init__(self, turns: list[Any]) -> None:
        self.turns = list(turns)
        self.calls = 0
        self.scopes: list[tuple[str | None, int | None]] = []
        self._last_completion_meta: dict[str, Any] | None = None

    @property
    def name(self) -> str:
        return "test"

    def ask_chat(self, model: str, _messages: list[dict], **_kwargs: Any) -> str:
        self.calls += 1
        scope = current_ai_call()
        self.scopes.append(
            (getattr(scope, "writer", None), getattr(scope, "attempt", None))
        )
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            self._last_completion_meta = None
            raise turn
        finish_reason, body = turn
        errored = finish_reason == "error"
        self._last_completion_meta = {
            "provider": "test",
            "model": model,
            "finish_reason": finish_reason,
            "input_tokens": 0 if errored else 10,
            "output_tokens": 0 if errored else 20,
            "total_tokens": 0 if errored else 30,
            "truncated": False,
            "text_chars": len(body),
            "response_field": "choices[0].message.content",
        }
        return body

    def last_completion_meta(self) -> dict[str, Any] | None:
        return dict(self._last_completion_meta or {})

    def is_available(self) -> bool:
        return True


def _repair(ai: _MetaAI):
    return repair_app_spec_candidate(
        source_snapshot={"business_name": "Test"},
        derived_context={},
        candidate={"schema_version": "1"},
        deterministic_report={"issues": []},
        ai_provider=ai,
        template_renderer=_StubRenderer(),
        model="google/gemini-2.5-flash",
        max_tokens=2000,
    )


def test_repair_reasks_after_an_error_cut_stream() -> None:
    ai = _MetaAI([("error", _ERROR_CUT_BODY), ("stop", _COMPLETE_BODY)])
    candidate = _repair(ai)
    assert ai.calls == 2
    assert candidate.payload["product_intent"]["summary"] == "repaired"
    assert (candidate.authoring_diagnostics or {}).get("transport_reask_used") is True
    # The re-ask bumps the ai_call attempt — the rows in ai_usage_events must
    # stay distinguishable (the exact reason writer/attempt scoping exists).
    assert ai.scopes == [("repair", 1), ("repair", 2)]


def test_non_retryable_provider_error_propagates() -> None:
    error = _empty_cut_error()
    error.retryable = False
    ai = _MetaAI([error, ("stop", _COMPLETE_BODY)])
    with pytest.raises(ProviderGenerationError):
        _repair(ai)
    assert ai.calls == 1  # a refusal-class failure is not transport; no re-ask


def test_repair_reasks_after_an_empty_cut_raise() -> None:
    ai = _MetaAI([_empty_cut_error(), ("stop", _COMPLETE_BODY)])
    candidate = _repair(ai)
    assert ai.calls == 2
    assert candidate.payload["product_intent"]["summary"] == "repaired"


def test_repair_never_retries_model_malformation() -> None:
    ai = _MetaAI([("stop", "this is not json at all")])
    with pytest.raises(AppSpecBuildError):
        _repair(ai)
    assert ai.calls == 1  # the model answered; re-asking is the authoring loop's call


def test_repair_fails_closed_after_two_cuts(monkeypatch: pytest.MonkeyPatch) -> None:
    # Session 21: two cuts now reach the cross-provider fallback rung first
    # (tests/appspec/test_transport_model_fallback.py). With the fallback
    # unconfigured, the original contract holds: two asks, then fail closed.
    monkeypatch.setattr(settings, "APPSPEC_TRANSPORT_FALLBACK_MODEL", "")
    ai = _MetaAI([("error", _ERROR_CUT_BODY), ("error", _ERROR_CUT_BODY)])
    with pytest.raises(AppSpecBuildError) as excinfo:
        _repair(ai)
    assert ai.calls == 2
    assert excinfo.value.typed_error == "app_spec_authoring_json_truncated"


def test_schema_repair_gate_fires_and_reasks() -> None:
    # Run 123's exact failure: without finish_reason threading, the first
    # turn's fragment would have BECOME the repaired candidate.
    ai = _MetaAI([("error", _ERROR_CUT_BODY), ("stop", _COMPLETE_BODY)])
    repaired = repair_app_spec_schema_candidate(
        candidate={"schema_version": "1", "pages": []},
        schema_issue={"code": "app_spec_schema_parse_failed", "issues": []},
        ai_provider=ai,
        template_renderer=_StubRenderer(),
        model="google/gemini-2.5-flash",
        max_tokens=2000,
    )
    assert ai.calls == 2
    assert repaired.payload["product_intent"]["summary"] == "repaired"
    assert repaired.payload != {"fragment": True}
    assert repaired.repair_type == "ai_schema_repair"


def test_coverage_refuses_an_error_cut_review() -> None:
    spec = build_fallback_app_spec({"customer_input": {"business_name": "Acme"}})
    ai = _MetaAI([("error", _COVERAGE_BODY)])  # cut stream, extractable body
    with pytest.raises(AppSpecCoverageError):
        review_app_spec_coverage(
            source_snapshot={"brief": "x"},
            app_spec=spec,
            ai_provider=ai,
            template_renderer=_StubRenderer(),
            model="google/gemini-2.5-flash",
            max_tokens=512,
        )


def test_coverage_still_parses_a_healthy_review() -> None:
    spec = build_fallback_app_spec({"customer_input": {"business_name": "Acme"}})
    ai = _MetaAI([("stop", _COVERAGE_BODY)])
    review = review_app_spec_coverage(
        source_snapshot={"brief": "x"},
        app_spec=spec,
        ai_provider=ai,
        template_renderer=_StubRenderer(),
        model="google/gemini-2.5-flash",
        max_tokens=512,
    )
    assert review.verdict == "pass"
