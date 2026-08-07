"""A transport storm alone can no longer kill an appspec ask.

Session 20, runs 136/137: real specs whose repair chains were double
error-cut — `_candidate_ask_with_transport_reask` fired its bounded same-model
re-ask live on both, and the weather beat it, because a provider-side storm
cuts the primary and its re-ask alike. Session 21 adds the last rung: when the
bounded re-ask is ALSO transport-cut, ask the cross-provider
``APPSPEC_TRANSPORT_FALLBACK_MODEL`` exactly once before failing closed.
Authoring, repair and schema_repair all take it; the fallback fires ONLY on
the transport class — model-authored malformation raises exactly as before,
and a malformed answer FROM the fallback model raises honestly (the
deterministic validator still gates quality either way).
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
    build_app_spec_candidate,
    repair_app_spec_candidate,
)
from app.application.appspec.schema_repair import repair_app_spec_schema_candidate
from app.application.services.ai_context import current_ai_call
from app.core.config import settings
from app.infrastructure.ai_providers.response_parser import (
    ProviderGenerationError,
    ProviderGenerationResult,
)

_PRIMARY = "google/gemini-2.5-flash"
_FALLBACK = "anthropic/claude-haiku-4.5"

# The run-123/136/137 shape: an error-cut body whose prefix carries one small
# complete object — the fragment the extractors would adjudicate without the
# provider-error gate.
_ERROR_CUT_BODY = (
    'Sketch: {"fragment": true}\n'
    'Full spec: {"schema_version": "1", "product_intent": {"summary": "cut'
)

_COMPLETE_BODY = json.dumps(
    {"schema_version": "1", "product_intent": {"summary": "rescued"}, "pages": []}
)


def _empty_cut_error() -> ProviderGenerationError:
    result = ProviderGenerationResult(
        provider="openrouter",
        model=_PRIMARY,
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
        return "ASK_PROMPT"


class _ModelAI:
    """Turns are (finish_reason, body) or an exception to raise.

    Records the MODEL of every ask beside the (writer, attempt) scope — the
    fallback assertions in this file are about which model was asked when.
    """

    def __init__(self, turns: list[Any]) -> None:
        self.turns = list(turns)
        self.models: list[str] = []
        self.scopes: list[tuple[str | None, int | None]] = []
        self._last_completion_meta: dict[str, Any] | None = None

    @property
    def name(self) -> str:
        return "test"

    def ask_chat(self, model: str, _messages: list[dict], **_kwargs: Any) -> str:
        self.models.append(model)
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


@pytest.fixture()
def fallback_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "APPSPEC_TRANSPORT_FALLBACK_MODEL", _FALLBACK)


def _repair(ai: _ModelAI):
    return repair_app_spec_candidate(
        source_snapshot={"business_name": "Test"},
        derived_context={},
        candidate={"schema_version": "1"},
        deterministic_report={"issues": []},
        ai_provider=ai,
        template_renderer=_StubRenderer(),
        model=_PRIMARY,
        max_tokens=2000,
    )


def _author(ai: _ModelAI):
    return build_app_spec_candidate(
        source_snapshot={"business_name": "Test"},
        derived_context={},
        ai_provider=ai,
        template_renderer=_StubRenderer(),
        model=_PRIMARY,
        max_tokens=2000,
    )


# --- the fallback fires: a double-cut chain gets one cross-provider ask ---


def test_repair_double_cut_falls_back_to_the_other_provider(
    fallback_configured: None,
) -> None:
    ai = _ModelAI(
        [("error", _ERROR_CUT_BODY), ("error", _ERROR_CUT_BODY), ("stop", _COMPLETE_BODY)]
    )
    candidate = _repair(ai)
    assert ai.models == [_PRIMARY, _PRIMARY, _FALLBACK]
    # Attempt numbering stays distinct in ai_usage_events: the fallback row is
    # attempt 3 under the same writer, on the other provider's model.
    assert ai.scopes == [("repair", 1), ("repair", 2), ("repair", 3)]
    assert candidate.payload["product_intent"]["summary"] == "rescued"
    diagnostics = candidate.authoring_diagnostics or {}
    assert diagnostics.get("transport_fallback_used") is True
    assert diagnostics.get("transport_fallback_model") == _FALLBACK


def test_schema_repair_double_cut_falls_back(fallback_configured: None) -> None:
    ai = _ModelAI(
        [_empty_cut_error(), ("error", _ERROR_CUT_BODY), ("stop", _COMPLETE_BODY)]
    )
    repaired = repair_app_spec_schema_candidate(
        candidate={"schema_version": "1", "pages": []},
        schema_issue={"code": "app_spec_schema_parse_failed", "issues": []},
        ai_provider=ai,
        template_renderer=_StubRenderer(),
        model=_PRIMARY,
        max_tokens=2000,
    )
    assert ai.models == [_PRIMARY, _PRIMARY, _FALLBACK]
    assert repaired.payload["product_intent"]["summary"] == "rescued"
    assert repaired.repair_type == "ai_schema_repair"


def test_authoring_double_cut_falls_back(fallback_configured: None) -> None:
    # One raise-shape cut and one body-shape cut: both transport signals.
    ai = _ModelAI(
        [_empty_cut_error(), ("error", _ERROR_CUT_BODY), ("stop", _COMPLETE_BODY)]
    )
    candidate = _author(ai)
    assert ai.models == [_PRIMARY, _PRIMARY, _FALLBACK]
    assert ai.scopes == [("authoring", 1), ("authoring", 2), ("authoring", 3)]
    assert candidate.payload["product_intent"]["summary"] == "rescued"
    diagnostics = candidate.authoring_diagnostics or {}
    assert diagnostics.get("transport_fallback_used") is True
    assert diagnostics.get("transport_fallback_model") == _FALLBACK


def test_authoring_empty_cut_raise_no_longer_kills_the_run(
    fallback_configured: None,
) -> None:
    # Before session 21 the retryable empty-cut raise escaped the authoring
    # loop with zero retries. Now it is transport: re-ask, then fallback.
    ai = _ModelAI([_empty_cut_error(), ("stop", _COMPLETE_BODY)])
    candidate = _author(ai)
    assert ai.models == [_PRIMARY, _PRIMARY]  # healthy re-ask; no fallback needed
    assert candidate.payload["product_intent"]["summary"] == "rescued"


# --- the fallback NEVER fires on the model's own answer ---


def test_authoring_malformation_never_falls_back(fallback_configured: None) -> None:
    # Third healthy turn provable: had the fallback fired, this would succeed.
    ai = _ModelAI(
        [("stop", "not json at all"), ("stop", "still not json"), ("stop", _COMPLETE_BODY)]
    )
    with pytest.raises(AppSpecBuildError):
        _author(ai)
    assert ai.models == [_PRIMARY, _PRIMARY]
    assert _FALLBACK not in ai.models


def test_repair_malformation_never_falls_back(fallback_configured: None) -> None:
    ai = _ModelAI([("stop", "not json at all"), ("stop", _COMPLETE_BODY)])
    with pytest.raises(AppSpecBuildError):
        _repair(ai)
    assert ai.models == [_PRIMARY]
    assert _FALLBACK not in ai.models


def test_authoring_non_retryable_raise_never_falls_back(
    fallback_configured: None,
) -> None:
    error = _empty_cut_error()
    error.retryable = False
    ai = _ModelAI([error, ("stop", _COMPLETE_BODY)])
    with pytest.raises(ProviderGenerationError):
        _author(ai)
    assert ai.models == [_PRIMARY]  # refusal-class: no re-ask, no fallback


def test_single_cut_with_healthy_reask_never_falls_back(
    fallback_configured: None,
) -> None:
    ai = _ModelAI([("error", _ERROR_CUT_BODY), ("stop", _COMPLETE_BODY)])
    candidate = _repair(ai)
    assert ai.models == [_PRIMARY, _PRIMARY]
    assert candidate.payload["product_intent"]["summary"] == "rescued"


# --- the fallback is one ask, judged honestly, then closed ---


def test_fallback_cut_fails_closed_with_no_fourth_ask(
    fallback_configured: None,
) -> None:
    ai = _ModelAI(
        [
            ("error", _ERROR_CUT_BODY),
            ("error", _ERROR_CUT_BODY),
            ("error", _ERROR_CUT_BODY),
        ]
    )
    with pytest.raises(AppSpecBuildError) as excinfo:
        _repair(ai)
    assert ai.models == [_PRIMARY, _PRIMARY, _FALLBACK]
    assert excinfo.value.typed_error == "app_spec_authoring_json_truncated"
    extraction = dict(excinfo.value.json_extraction or {})
    assert extraction.get("transport_fallback_model") == _FALLBACK


def test_fallback_malformation_raises_honestly(fallback_configured: None) -> None:
    # A wrong fallback answer is the model's answer: the validator gates it,
    # nothing re-asks it. This trades a certain dead run for a judged candidate.
    ai = _ModelAI(
        [
            ("error", _ERROR_CUT_BODY),
            ("error", _ERROR_CUT_BODY),
            ("stop", "not json at all"),
        ]
    )
    with pytest.raises(AppSpecBuildError):
        _author(ai)
    assert ai.models == [_PRIMARY, _PRIMARY, _FALLBACK]


# --- configuration guards ---


def test_fallback_pointed_at_the_primary_model_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A same-model "fallback" would ride the same storm — fail closed instead.
    monkeypatch.setattr(settings, "APPSPEC_TRANSPORT_FALLBACK_MODEL", _PRIMARY)
    ai = _ModelAI(
        [("error", _ERROR_CUT_BODY), ("error", _ERROR_CUT_BODY), ("stop", _COMPLETE_BODY)]
    )
    with pytest.raises(AppSpecBuildError):
        _repair(ai)
    assert ai.models == [_PRIMARY, _PRIMARY]


def test_fallback_unconfigured_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "APPSPEC_TRANSPORT_FALLBACK_MODEL", "")
    ai = _ModelAI(
        [("error", _ERROR_CUT_BODY), ("error", _ERROR_CUT_BODY), ("stop", _COMPLETE_BODY)]
    )
    with pytest.raises(AppSpecBuildError):
        _author(ai)
    assert ai.models == [_PRIMARY, _PRIMARY]


def test_default_configuration_is_cross_provider() -> None:
    # The shipped default must dodge the storm by construction.
    assert settings.APPSPEC_TRANSPORT_FALLBACK_MODEL.startswith("anthropic/")
