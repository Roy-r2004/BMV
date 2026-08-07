"""Provider-error-cut streams must never be fragment-extracted into candidates.

Session 19, requests 118-121: gemini-2.5-flash returned HTTP 200 bodies with
``finish_reason=error`` and 0 output tokens — partial streams of 1k-34k chars.
The parser's fragment strategies (balanced scan, repair) found small complete
objects inside the partial text, returned them ``ok=True``, and the pipeline
minted revisions off them and failed the requests as spec rejections. Four
funded runs were burned by transport failures adjudicated as model answers.

The rule these tests pin: on ``finish_reason=error``, only a complete direct
parse may pass. Everything else fails as ``app_spec_authoring_json_truncated``
(retryable), so the authoring loop re-asks the provider instead of judging
the cut.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.appspec.builder import (
    build_app_spec_candidate,
)
from app.domain.appspec.authoring_parser import (
    AUTHORING_JSON_TRUNCATED,
    parse_appspec_authoring_output,
)


# The request-118 shape: prose/preamble containing one small complete object,
# then the real document begins and is cut mid-stream by the provider error.
# Without the gate, the balanced scan (or the repair pass) extracts the small
# object and returns ok=True.
_ERROR_CUT_BODY = (
    'Here is a quick sketch first: {"fragment": true, "note": "not the spec"}\n'
    'Now the full AppSpec:\n'
    '{"schema_version": "1", "product_intent": {"summary": "booking"}, '
    '"pages": [{"id": "PAGE-HOME", "title": "Home", "sections": ['
)

_COMPLETE_BODY = json.dumps(
    {
        "schema_version": "1",
        "product_intent": {"summary": "booking"},
        "pages": [],
    }
)


class _StubRenderer:
    def render(self, *_args: Any, **_kwargs: Any) -> str:
        return "AUTHORING_PROMPT"


class _MetaAI:
    """Fake provider whose completion meta mirrors the real openrouter shape."""

    def __init__(self, turns: list[tuple[str, str]]) -> None:
        # Each turn is (finish_reason, body).
        self.turns = list(turns)
        self.calls: list[dict[str, Any]] = []
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
        finish_reason, body = self.turns.pop(0)
        self.calls.append({"model": model, "messages": messages})
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


def test_error_cut_stream_is_never_fragment_extracted() -> None:
    result = parse_appspec_authoring_output(_ERROR_CUT_BODY, finish_reason="error")
    assert not result.ok
    assert result.error_code == AUTHORING_JSON_TRUNCATED
    assert result.strategy == "provider_error"
    assert result.parser_error == "provider_error_cut_stream"
    assert result.diagnostics.get("truncated") is True


def test_error_cut_stream_without_gate_would_have_extracted() -> None:
    # The same body parses "fine" when the stream was not error-cut — this is
    # the fragment the gate exists to refuse, so the fixture provably reaches
    # the extraction path it guards.
    result = parse_appspec_authoring_output(_ERROR_CUT_BODY, finish_reason=None)
    assert result.ok
    assert result.payload == {"fragment": True, "note": "not the spec"}


def test_error_finish_with_complete_direct_object_still_parses() -> None:
    # A complete top-level object that arrived before the error flag is the
    # model's whole answer; refusing it would turn a harmless late error into
    # a wasted re-ask.
    result = parse_appspec_authoring_output(_COMPLETE_BODY, finish_reason="error")
    assert result.ok
    assert result.strategy == "direct"
    assert result.payload["schema_version"] == "1"


def test_builder_reasks_provider_after_error_cut_stream() -> None:
    ai = _MetaAI([("error", _ERROR_CUT_BODY), ("stop", _COMPLETE_BODY)])
    candidate = build_app_spec_candidate(
        source_snapshot={"business_name": "Test"},
        derived_context={},
        ai_provider=ai,
        template_renderer=_StubRenderer(),
        model="google/gemini-2.5-flash",
    )
    assert candidate.payload["schema_version"] == "1"
    assert len(ai.calls) == 2
    diagnostics = candidate.authoring_diagnostics or {}
    assert diagnostics.get("malformed_retry_used") is True
