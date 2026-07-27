"""Request #43 AppSpec authoring parser + structured-output regression."""
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
    APPSPEC_AUTHORING_MALFORMED_RETRY_MAX,
    AppSpecBuildError,
    _COMPACT_JSON_RETRY_INSTRUCTION,
    _structured_output_request,
    build_app_spec_candidate,
    parse_app_spec_candidate,
)
from app.core.config import settings
from app.domain.appspec.authoring_parser import (
    AUTHORING_JSON_SYNTAX_INVALID,
    AUTHORING_JSON_TRUNCATED,
    AUTHORING_NO_JSON_OBJECT,
    AUTHORING_RESPONSE_FIELD_MISSING,
    parse_appspec_authoring_output,
)
from app.domain.appspec.validation import validate_app_spec
from app.infrastructure.ai_providers.model_capabilities import resolve_model_capability
from app.shared.json_utils import extract_json_from_text

RAW_DIR = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "app_spec"
    / "request43_authoring_raw"
)
DIAG_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "app_spec"
    / "request43_authoring_diagnostics.json"
)


def _read_raw(name: str) -> str:
    return (RAW_DIR / name).read_text(encoding="utf-8")


class _StubRenderer:
    def render(self, *_args: Any, **_kwargs: Any) -> str:
        return "AUTHORING_PROMPT_SCHEMA_PLACEHOLDER"


class _RecordingAI:
    def __init__(
        self, responses: list[str], *, accept_response_format: bool = True
    ) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.accept_response_format = accept_response_format
        self._last_completion_meta: dict[str, Any] | None = None

    @property
    def name(self) -> str:
        return "test"

    def ask_chat(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> str:
        if "response_format" in kwargs and not self.accept_response_format:
            raise TypeError(
                "ask_chat() got an unexpected keyword argument 'response_format'"
            )
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": kwargs.get("response_format"),
            }
        )
        text = self.responses.pop(0)
        self._last_completion_meta = {
            "provider": "test",
            "model": model,
            "finish_reason": "stop",
            "input_tokens": 10,
            "output_tokens": 20,
            "total_tokens": 30,
            "truncated": False,
            "text_chars": len(text),
            "response_field": "choices[0].message.content",
            "response_format_requested": kwargs.get("response_format"),
        }
        return text

    def last_completion_meta(self) -> dict[str, Any] | None:
        return dict(self._last_completion_meta or {})

    def ask_vision(self, *_a: Any, **_k: Any) -> str:
        raise NotImplementedError

    def is_available(self) -> bool:
        return True


# --- canonical parser -----------------------------------------------------


def test_direct_valid_json() -> None:
    result = parse_appspec_authoring_output(_read_raw("direct_valid.json"))
    assert result.ok
    assert result.strategy == "direct"
    assert result.payload["schema_version"] == "1"


def test_fenced_valid_json() -> None:
    result = parse_appspec_authoring_output(_read_raw("fenced_valid.json.txt"))
    assert result.ok
    assert result.strategy == "markdown_fence"
    assert result.payload["product_intent"]["summary"] == "x"


def test_prose_before_and_after_valid_json() -> None:
    result = parse_appspec_authoring_output(_read_raw("prose_wrapped_valid.txt"))
    assert result.ok
    assert result.strategy == "balanced_scan"
    assert result.payload["product_intent"]["summary"] == "booking"


def test_braces_inside_json_strings() -> None:
    result = parse_appspec_authoring_output(_read_raw("braces_in_strings.txt"))
    assert result.ok
    assert "{curly}" in result.payload["note"]


def test_escaped_quotes_and_backslashes() -> None:
    result = parse_appspec_authoring_output(_read_raw("braces_in_strings.txt"))
    assert result.ok
    assert '"quotes"' in result.payload["note"]
    assert "\\paths" in result.payload["note"]


def test_nested_objects_and_arrays() -> None:
    result = parse_appspec_authoring_output(_read_raw("nested_valid.txt"))
    assert result.ok
    assert result.payload["a"]["b"][1]["c"] is True


def test_multiple_objects_first_object_policy() -> None:
    result = parse_appspec_authoring_output(_read_raw("multiple_objects.txt"))
    assert result.ok
    assert result.payload["product_intent"]["summary"] == "first"


def test_truncated_object() -> None:
    result = parse_appspec_authoring_output(_read_raw("truncated_object.txt"))
    assert not result.ok
    assert result.error_code == AUTHORING_JSON_TRUNCATED
    assert result.public_message.startswith(
        "AppSpec model output was not valid JSON"
    )


def test_invalid_json_syntax() -> None:
    result = parse_appspec_authoring_output(_read_raw("invalid_syntax.txt"))
    assert not result.ok
    assert result.error_code == AUTHORING_JSON_SYNTAX_INVALID


def test_prose_only_response() -> None:
    result = parse_appspec_authoring_output(
        _read_raw("request43_class_f_prose_only.txt")
    )
    assert not result.ok
    assert result.error_code == AUTHORING_NO_JSON_OBJECT


def test_missing_provider_content_field() -> None:
    result = parse_appspec_authoring_output(
        None,
        response_field_present=False,
    )
    assert not result.ok
    assert result.error_code == AUTHORING_RESPONSE_FIELD_MISSING


def test_public_errors_remain_sanitized() -> None:
    secretish = 'SECRET_TOKEN=abc\n{"broken":'
    result = parse_appspec_authoring_output(secretish)
    assert not result.ok
    assert "SECRET_TOKEN" not in result.public_message
    assert "abc" not in result.public_message


# --- request #43 regression -----------------------------------------------


def test_request43_diagnostics_document_unrecovered_shared_output() -> None:
    diag = json.loads(DIAG_PATH.read_text(encoding="utf-8"))
    assert diag["request_id"] == 43
    assert len(diag["attempts"]) == 3
    sha = diag["shared_raw_response_sha256"]
    assert (
        sha
        == "d2cbc22bd09ff1e0c7ff82081ab56a9669e5d83bbe9e9b52ae935c76adc731d5"
    )
    for attempt in diag["attempts"]:
        assert attempt["raw_response_sha256"] == sha
        assert attempt["json_extraction"]["ok"] is False
        assert "No valid JSON object" in attempt["json_extraction"]["error"]
        assert attempt["finish_reason"] is None


def test_request43_historical_class_f_fails_old_and_new_parser() -> None:
    raw = _read_raw("request43_class_f_prose_only.txt")
    with pytest.raises(ValueError, match="No valid JSON object|No JSON object"):
        extract_json_from_text(raw)
    result = parse_appspec_authoring_output(raw)
    assert result.error_code == AUTHORING_NO_JSON_OBJECT


def test_request43_production_shaped_structured_response_passes_validation() -> None:
    raw = _read_raw("production_shaped_valid_booking.json")
    parsed = parse_appspec_authoring_output(raw)
    assert parsed.ok
    assert parsed.strategy == "direct"
    spec = parse_app_spec_candidate(parsed.payload)
    report = validate_app_spec(spec)
    assert report.is_valid, [issue.code for issue in report.issues]


# --- provider capability / adapter ----------------------------------------


def test_structured_output_supported_provider_requests_json_object() -> None:
    model = "google/gemini-2.5-flash"
    profile = resolve_model_capability(model)
    assert profile.known is True
    assert profile.supports_json_object is True
    assert profile.supports_json_schema is False
    request, diag = _structured_output_request(model)
    assert request == {"type": "json_object"}
    assert diag["structured_output_mode_requested"] == "json_object"
    assert diag["structured_output_mode_supported"] is True


def test_structured_output_unsupported_provider_skips_response_format() -> None:
    model = "unknown/vendor-model-xyz"
    profile = resolve_model_capability(model)
    assert profile.known is False
    assert profile.supports_json_object is False
    request, diag = _structured_output_request(model)
    assert request is None
    assert diag["structured_output_mode_requested"] is None
    assert diag["structured_output_mode_supported"] is False


def test_unsupported_response_format_parameter_is_not_sent() -> None:
    ai = _RecordingAI(
        ['{"schema_version":"1","product_intent":{"summary":"ok"}}'],
        accept_response_format=True,
    )
    build_app_spec_candidate(
        source_snapshot={"brief": "x"},
        derived_context={},
        ai_provider=ai,
        template_renderer=_StubRenderer(),
        model="unknown/vendor-model-xyz",
        max_tokens=512,
    )
    assert ai.calls[0]["response_format"] is None


def test_supported_model_sends_json_object_response_format() -> None:
    ai = _RecordingAI(
        ['{"schema_version":"1","product_intent":{"summary":"ok"}}'],
    )
    build_app_spec_candidate(
        source_snapshot={"brief": "x"},
        derived_context={},
        ai_provider=ai,
        template_renderer=_StubRenderer(),
        model="google/gemini-2.5-flash",
        max_tokens=512,
    )
    assert ai.calls[0]["response_format"] == {"type": "json_object"}


def test_compact_retry_instruction_on_malformed_json() -> None:
    ai = _RecordingAI(
        [
            "Sorry, I cannot emit JSON for this brief.",
            '{"schema_version":"1","product_intent":{"summary":"retry-ok"}}',
        ]
    )
    candidate = build_app_spec_candidate(
        source_snapshot={"brief": "x"},
        derived_context={},
        ai_provider=ai,
        template_renderer=_StubRenderer(),
        model="google/gemini-2.5-flash",
        max_tokens=512,
    )
    assert candidate.payload["product_intent"]["summary"] == "retry-ok"
    assert len(ai.calls) == 2
    retry_messages = ai.calls[1]["messages"]
    assert any(
        msg.get("content") == _COMPACT_JSON_RETRY_INSTRUCTION
        for msg in retry_messages
    )
    assert "Sorry, I cannot emit JSON" not in json.dumps(retry_messages)
    assert "No prose" in _COMPACT_JSON_RETRY_INSTRUCTION
    assert "No markdown" in _COMPACT_JSON_RETRY_INSTRUCTION
    assert "No code fences" in _COMPACT_JSON_RETRY_INSTRUCTION


def test_maximum_attempt_count_unchanged() -> None:
    assert APPSPEC_AUTHORING_MALFORMED_RETRY_MAX == 1
    assert settings.APPSPEC_MAX_CALLS >= 2
    ai = _RecordingAI(
        [
            "prose only attempt one",
            "prose only attempt two",
            "should-not-be-called",
        ]
    )
    with pytest.raises(AppSpecBuildError) as exc_info:
        build_app_spec_candidate(
            source_snapshot={"brief": "x"},
            derived_context={},
            ai_provider=ai,
            template_renderer=_StubRenderer(),
            model="google/gemini-2.5-flash",
            max_tokens=512,
        )
    assert len(ai.calls) == 1 + APPSPEC_AUTHORING_MALFORMED_RETRY_MAX
    assert exc_info.value.typed_error == AUTHORING_NO_JSON_OBJECT


def test_fallback_remains_disabled() -> None:
    assert settings.APPSPEC_FALLBACK_ENABLED is False


def test_parser_does_not_invent_appspec_fields() -> None:
    result = parse_appspec_authoring_output('{"schema_version":"1"}')
    assert result.ok
    assert set(result.payload.keys()) == {"schema_version"}


def test_truncated_object_never_closed_heuristically() -> None:
    raw = '{"schema_version":"1","pages":[{"id":"PAGE-1"'
    result = parse_appspec_authoring_output(raw)
    assert result.error_code == AUTHORING_JSON_TRUNCATED
    assert result.payload is None
