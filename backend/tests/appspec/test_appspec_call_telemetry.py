"""Every AppSpec model call must be scoped, so its cost can be attributed.

`admin_ops._record_usage` derives a row's `stage` from the active `ai_call`
scope and falls back to `purpose`; with no scope it hardcodes `writer=None` and
`attempt=1` (`admin_ops.py:330-332`). AppSpec was the only AI-calling stage in
the pipeline with no scope anywhere — codegen, fix_agent, design_critic, vision,
refine, seed, architect and quality_repair all have one.

The cost of that was not theoretical. Over trios 2-5, `appspec` wrote **49
`ai_usage_events` rows across 12 runs, every one with `writer = NULL` and
`attempt = 1`**, which meant:

* the stage that spends 147 s per run — roughly half the whole budget, and the
  subject of a pending owner decision on bounding it — could not be broken down
  into authoring vs coverage vs repair;
* its re-asks were invisible. `build_app_spec_candidate` retries a malformed
  authoring response `APPSPEC_AUTHORING_MALFORMED_RETRY_MAX` times and every one
  of those was recorded as `attempt = 1`;
* the Phase 1 DoD row *"no ask > 120 s inclusive of failovers"* groups logical
  asks by `(request_id, stage, writer)` with `attempt` not resetting — so for
  appspec that grouping had nothing to group on, and the row was evaluated on
  data that structurally could not show an appspec failover.

These tests assert the scope is live at the moment the provider is called, which
is the only place it can be observed without a database.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.application.appspec.builder import build_app_spec_candidate
from app.application.appspec.coverage import review_app_spec_coverage
from app.application.appspec.fallback import build_fallback_app_spec
from app.application.services.ai_context import current_ai_call

_VALID = '{"schema_version":"1","product_intent":{"summary":"ok"}}'


class _StubRenderer:
    def render(self, *_args: Any, **_kwargs: Any) -> str:
        return "prompt"


class _ScopeRecordingAI:
    """Records the `ai_call` scope that was active during each ask."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.scopes: list[tuple[str | None, str | None, int]] = []

    def ask_chat(self, _model: str, _messages: list[dict], **_kwargs: Any) -> str:
        call = current_ai_call()
        self.scopes.append(
            (call.stage, call.writer, call.attempt) if call else (None, None, 0)
        )
        return self._responses.pop(0) if self._responses else _VALID


def test_authoring_calls_are_scoped_with_a_writer() -> None:
    ai = _ScopeRecordingAI([_VALID])

    build_app_spec_candidate(
        source_snapshot={"brief": "x"},
        derived_context={},
        ai_provider=ai,
        template_renderer=_StubRenderer(),
        model="google/gemini-2.5-flash",
        max_tokens=512,
    )

    assert ai.scopes == [("appspec", "authoring", 1)]


def test_authoring_reasks_carry_their_real_attempt_number() -> None:
    """The retry loop must not report every attempt as attempt 1.

    Two of the four captured payloads in `tests/fixtures/model_json/` are
    structurally complete and merely under-escaped, so before session 6 the
    authoring parser rejected them and this loop re-asked a 28k-token call for
    output already in hand. That spend has to be visible as a re-ask.
    """
    ai = _ScopeRecordingAI(["not json at all", _VALID])

    build_app_spec_candidate(
        source_snapshot={"brief": "x"},
        derived_context={},
        ai_provider=ai,
        template_renderer=_StubRenderer(),
        model="google/gemini-2.5-flash",
        max_tokens=512,
    )

    assert ai.scopes == [("appspec", "authoring", 1), ("appspec", "authoring", 2)]
    # Distinguishable from a first attempt, which is the whole point.
    assert len({attempt for _, _, attempt in ai.scopes}) == 2


def test_coverage_review_is_scoped_separately_from_authoring() -> None:
    """Authoring and review are different spends with different fixes."""
    review = (
        '{"verdict":"pass","score":100,"summary":"ok","goal_coverage":[],'
        '"omissions":[],"contradictions":[],"unsupported_additions":[],'
        '"mislabeled_assumptions":[],"open_question_gaps":[]}'
    )
    ai = _ScopeRecordingAI([review])

    # The fallback builder is the cheapest source of a schema-valid AppSpec;
    # this test is about the scope, not about the spec's contents.
    spec = build_fallback_app_spec({"customer_input": {"business_name": "Acme"}})

    review_app_spec_coverage(
        source_snapshot={"brief": "x"},
        app_spec=spec,
        ai_provider=ai,
        template_renderer=_StubRenderer(),
        model="google/gemini-2.5-flash",
        max_tokens=512,
    )

    assert ai.scopes == [("appspec", "coverage_review", 1)]


@pytest.mark.parametrize(
    "module_path",
    [
        "app.application.appspec.builder",
        "app.application.appspec.coverage",
        # schema_repair no longer asks a model directly — session 20 routed its
        # ask through builder's `_candidate_ask_with_transport_reask`, which
        # carries the scope (and the transport re-ask) for every candidate ask.
    ],
)
def test_every_appspec_module_that_asks_a_model_imports_the_scope(module_path: str) -> None:
    """A guard against the next unscoped call site being added silently.

    Deliberately a static check on the module rather than a behavioural one:
    `schema_repair` needs a validation failure to reach its ask, and a test that
    elaborate would pin its setup rather than the instrumentation.
    """
    import importlib

    module = importlib.import_module(module_path)
    source = __import__("inspect").getsource(module)

    assert "ai_call(" in source, f"{module_path} calls a model outside any ai_call scope"
    for line_number, line in enumerate(source.splitlines(), 1):
        if ".ask_chat(" in line and "def ask_chat" not in line:
            assert 'ai_call("appspec"' in source, (
                f"{module_path}:{line_number} asks a model; the module has no appspec scope"
            )
