"""R1 at the highest-volume ask site: slot_fill's cross-provider transport rung.

1.12(b) proved the shape: with the page writer unroutable, every page shipped
its bare scaffold to the quality gate — an honest failure that one ask on a
different provider's model can turn into a judged page. The rung mirrors
appspec's (`3f7f7f9`): it fires ONLY on the transport class, asks the
cross-provider `PREVIEW_APP_TRANSPORT_FALLBACK_MODEL` exactly once under a
distinct telemetry attempt, and its answer faces the identical syntactic and
contract judge as the primary's. Refusal-class raises, unconfigured or
same-model fallbacks, and low runway all keep failing closed to the scaffold.

This file also pins R2's other half on the LIVE path: the contract retry's
translation (`_SLOT_FILL_RETRY_GUIDANCE["catalogue-contract"]`) must reach the
actual attempt-2 prompt — the old pin called `_slot_fill_retry_prompt`
directly, a path the production loop never takes for contract rejections.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app import codegen
from app.application.preview_app.catalogue_contract import (
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.codegen.generate import (
    _MAX_SLOT_FILL_ATTEMPTS,
    _SLOT_FILL_RETRY_GUIDANCE,
    CONTRACT_REJECTION,
    _is_transport_failure,
)
from app.application.preview_app.fallback import clear_stubbed_paths, consume_stubbed_paths
from app.application.services.ai_context import (
    UNUSABLE_REJECTED,
    ai_call,
    current_ai_call,
)
from app.application.services.request_deadline import (
    DEFAULT_ASK_CEILING_SECONDS,
    RESERVE_SECONDS,
    request_deadline_scope,
)
from app.core.config import (
    settings,
    warn_same_provider_preview_app_fallback,
)
from app.infrastructure.ai_providers.response_parser import (
    ProviderGenerationError,
    ProviderGenerationResult,
)
from app.infrastructure.templating.renderer import JinjaTemplateRenderer

TEMPLATES_DIR = REPO_ROOT / "backend" / "app" / "templates"
PAGE = "src/pages/HomePage.tsx"
SCAFFOLD_MARKER = "deterministic catalogue contract scaffold"

_PRIMARY = "deepseek/deepseek-v4-pro"
_FALLBACK = "anthropic/claude-haiku-4.5"

_CONTRACT_INVALID = (
    "import { PublicShell } from '@/ui';\n"
    "export default function HomePage() { "
    'return <PublicShell brandName="Wrong"><main>complete invalid page</main>'
    "</PublicShell>; }\n"
)


def _provider_error(*, retryable: bool, model: str = _PRIMARY) -> ProviderGenerationError:
    result = ProviderGenerationResult(
        provider="openrouter",
        model=model,
        provider_request_id="req-x",
        response_format="unknown",
        text="",
        structured_payload=None,
        finish_reason="error",
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        http_status=200 if retryable else 403,
        raw_payload_sha256="0" * 64,
        is_success=False,
        error_code="provider_empty_response" if retryable else "provider_refusal",
        error_message_redacted="scripted provider failure",
        retryable=retryable,
        refusal=not retryable,
        truncated=False,
        latency_ms=8,
    )
    error = ProviderGenerationError("scripted provider failure", result=result)
    assert error.retryable is retryable  # the fixture must be the filed shape
    return error


def _route() -> dict:
    return {
        "path": "/",
        "page_id": "home",
        "role_id": "customer",
        "component_file": PAGE,
        "surface": "public",
        "skeleton_id": "public-home",
        "section_slots": [
            "hero",
            "features",
            "showcase",
            "process",
            "testimonials",
            "cta",
            "footer",
        ],
    }


def _accepted_fill(sentinel: str) -> str:
    return minimal_catalogue_page_scaffold(PAGE, _route(), brand_name=sentinel).replace(
        f"// {SCAFFOLD_MARKER}", "// AI-authored business page"
    )


class _ScriptedAI:
    """Turns are answer strings or exceptions to raise.

    Records the MODEL of every ask beside the (writer, attempt) scope — the
    rung assertions in this file are about which model was asked when. Files a
    usage row on answered turns the way a real provider does, so adjudication
    is observable through a flush.
    """

    def __init__(self, turns: list) -> None:
        self.turns = list(turns)
        self.models: list[str] = []
        self.scopes: list[tuple[str | None, int | None]] = []
        self.prompts: list[str] = []

    @property
    def name(self) -> str:
        return "test"

    def ask_chat(self, model: str, messages: list[dict], **_kwargs) -> str:
        self.models.append(model)
        scope = current_ai_call()
        self.scopes.append(
            (getattr(scope, "writer", None), getattr(scope, "attempt", None))
        )
        self.prompts.append(messages[-1]["content"])
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        if scope is not None:
            scope.record({"success": True, "usable": True})
        return turn


@pytest.fixture()
def models_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PREVIEW_APP_MODEL", _PRIMARY)
    monkeypatch.setattr(settings, "PREVIEW_APP_TRANSPORT_FALLBACK_MODEL", _FALLBACK)


def _generate(ai: _ScriptedAI, workspace: Path) -> str:
    return codegen.generate_file(
        workspace,
        {"path": PAGE, "kind": "page", "instructions": "home"},
        "business context",
        {"routes": [_route()]},
        {"roles": []},
        {},
        {},
        ai,
        JinjaTemplateRenderer(TEMPLATES_DIR),
    )


# --- the predicate ------------------------------------------------------------


def test_the_predicate_is_the_transport_class_and_nothing_else() -> None:
    assert _is_transport_failure(_provider_error(retryable=True))
    assert not _is_transport_failure(_provider_error(retryable=False))
    assert not _is_transport_failure(RuntimeError("weather-shaped string"))


# --- the rung fires -----------------------------------------------------------


def test_transport_cut_gets_one_cross_provider_ask_and_the_fill_ships(
    models_pinned: None,
) -> None:
    ai = _ScriptedAI(
        [_provider_error(retryable=True), _accepted_fill("FALLBACK_SENTINEL")]
    )
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        content = _generate(ai, workspace)
        assert "FALLBACK_SENTINEL" in content
        assert SCAFFOLD_MARKER not in content
        assert consume_stubbed_paths(workspace) == []
    assert ai.models == [_PRIMARY, _FALLBACK]
    assert ai.scopes == [
        ("slot_fill", 1),
        ("slot_fill", _MAX_SLOT_FILL_ATTEMPTS + 1),
    ]


def test_transport_on_the_retry_attempt_hands_the_corrective_prompt_to_the_rung(
    models_pinned: None,
) -> None:
    """Attempt 2's corrective context is not thrown away when attempt 2 is cut."""
    ai = _ScriptedAI(
        [
            _CONTRACT_INVALID,
            _provider_error(retryable=True),
            _accepted_fill("RUNG_AFTER_RETRY_SENTINEL"),
        ]
    )
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        content = _generate(ai, workspace)
        assert "RUNG_AFTER_RETRY_SENTINEL" in content
    assert ai.models == [_PRIMARY, _PRIMARY, _FALLBACK]
    assert [attempt for _, attempt in ai.scopes] == [1, 2, 3]
    assert "CATALOGUE CONTRACT RETRY" in ai.prompts[-1], (
        "the rung dropped the corrective context the retry attempt carried"
    )


def test_the_fallback_fill_faces_the_same_judge(models_pinned: None) -> None:
    """A fallback answer the contract judge rejects is a scaffold, not a ship."""
    captured: list[dict] = []
    ai = _ScriptedAI([_provider_error(retryable=True), _CONTRACT_INVALID])
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        with ai_call("test-root", flush=captured.extend):
            content = _generate(ai, workspace)
        assert SCAFFOLD_MARKER in content
        assert consume_stubbed_paths(workspace) == [PAGE]
    rows = [row for row in captured if row.get("writer") == "slot_fill"]
    assert [row["attempt"] for row in rows] == [_MAX_SLOT_FILL_ATTEMPTS + 1]
    assert rows[0]["usable"] is False
    assert rows[0]["unusable_reason"] == UNUSABLE_REJECTED


def test_a_parse_broken_fallback_fill_is_judged_not_shipped(
    models_pinned: None,
) -> None:
    """The judge is the ONLY defense for a fill enforce would keep.

    A contract-invalid fill is doubly defended — the post-loop enforce replaces
    it even if the rung's own verdict is ignored, which is exactly how the
    first sweep's 'ships unjudged' mutation survived. A fill that PARSES wrong
    but keeps its face walks past enforce, so only the rung's judge stands
    between it and the workspace.
    """
    from app.application.preview_app.catalogue_contract import (
        enforce_catalogue_page_contract,
    )
    from app.application.preview_app.source_quality import tsx_parse_error

    broken = (
        _accepted_fill("BROKEN_PARSE_SENTINEL")
        + "\nconst dangling = <div><span></div></span>;\n"
    )
    # The fixture must bind: judged unusable, yet kept by enforce.
    assert tsx_parse_error(broken), "the fixture no longer breaks the TSX parse"
    _, replaced = enforce_catalogue_page_contract(
        PAGE, broken, {"routes": [_route()]}, brand_name="Brand"
    )
    assert not replaced, (
        "enforce discards this fixture — it no longer isolates the rung's judge"
    )

    ai = _ScriptedAI([_provider_error(retryable=True), broken])
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        content = _generate(ai, workspace)
        assert SCAFFOLD_MARKER in content
        assert "BROKEN_PARSE_SENTINEL" not in content
        assert consume_stubbed_paths(workspace) == [PAGE]
    assert ai.models == [_PRIMARY, _FALLBACK]


# --- the rung never fires on the model's own answer or refusal ----------------


def test_a_refusal_class_raise_keeps_failing_closed(models_pinned: None) -> None:
    ai = _ScriptedAI(
        [_provider_error(retryable=False), _accepted_fill("NEVER_ASKED_SENTINEL")]
    )
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        content = _generate(ai, workspace)
        assert SCAFFOLD_MARKER in content
        assert "NEVER_ASKED_SENTINEL" not in content
    assert ai.models == [_PRIMARY], "a refusal-class raise reached the fallback rung"


def test_two_judged_rejections_never_reach_the_rung(models_pinned: None) -> None:
    """Rejected answers are the model's own — the rung is for weather only."""
    ai = _ScriptedAI(
        [
            _CONTRACT_INVALID,
            _CONTRACT_INVALID,
            _accepted_fill("NEVER_ASKED_SENTINEL"),
        ]
    )
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        content = _generate(ai, workspace)
        assert SCAFFOLD_MARKER in content
    assert ai.models == [_PRIMARY, _PRIMARY], (
        "a judged rejection was treated as weather"
    )


# --- the rung is one ask, then closed -----------------------------------------


def test_a_cut_fallback_keeps_the_scaffold_without_raising(
    models_pinned: None,
) -> None:
    ai = _ScriptedAI(
        [
            _provider_error(retryable=True),
            _provider_error(retryable=True, model=_FALLBACK),
            _accepted_fill("NEVER_ASKED_SENTINEL"),
        ]
    )
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        content = _generate(ai, workspace)
        assert SCAFFOLD_MARKER in content
        assert consume_stubbed_paths(workspace) == [PAGE]
    assert ai.models == [_PRIMARY, _FALLBACK], "the rung is bounded at one ask"


# --- configuration guards -----------------------------------------------------


def test_unconfigured_fallback_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PREVIEW_APP_MODEL", _PRIMARY)
    monkeypatch.setattr(settings, "PREVIEW_APP_TRANSPORT_FALLBACK_MODEL", "")
    ai = _ScriptedAI([_provider_error(retryable=True), _accepted_fill("X")])
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        content = _generate(ai, workspace)
        assert SCAFFOLD_MARKER in content
    assert ai.models == [_PRIMARY]


def test_same_model_fallback_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PREVIEW_APP_MODEL", _PRIMARY)
    monkeypatch.setattr(settings, "PREVIEW_APP_TRANSPORT_FALLBACK_MODEL", _PRIMARY)
    ai = _ScriptedAI([_provider_error(retryable=True), _accepted_fill("X")])
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        content = _generate(ai, workspace)
        assert SCAFFOLD_MARKER in content
    assert ai.models == [_PRIMARY], "a same-model fallback rides the same storm"


def test_the_default_fallback_slot_is_cross_provider_from_the_page_writer() -> None:
    # The shipped defaults must satisfy R7's invariant out of the box.
    assert settings.PREVIEW_APP_TRANSPORT_FALLBACK_MODEL
    assert warn_same_provider_preview_app_fallback(settings) == []


def test_the_config_warning_names_a_same_provider_page_writer_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PREVIEW_APP_MODEL", "anthropic/claude-opus-5")
    monkeypatch.setattr(
        settings, "PREVIEW_APP_TRANSPORT_FALLBACK_MODEL", _FALLBACK
    )
    assert warn_same_provider_preview_app_fallback(settings) == ["PREVIEW_APP_MODEL"]


def test_startup_asserts_the_page_writer_invariant_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    from app.core.config import assert_safe_runtime_configuration

    monkeypatch.setattr(settings, "PREVIEW_APP_MODEL", "anthropic/claude-opus-5")
    monkeypatch.setattr(
        settings, "PREVIEW_APP_TRANSPORT_FALLBACK_MODEL", _FALLBACK
    )
    with caplog.at_level(logging.WARNING, logger="bmv.Config"):
        assert_safe_runtime_configuration(settings)  # must not raise
    assert any(
        "PREVIEW_APP_TRANSPORT_FALLBACK_MODEL" in record.getMessage()
        for record in caplog.records
    ), "startup never checked the page-writer fallback pair"


# --- the cost bound -----------------------------------------------------------


def test_the_rung_is_skipped_without_runway_and_says_so(
    models_pinned: None,
) -> None:
    ai = _ScriptedAI(
        [_provider_error(retryable=True), _accepted_fill("UNREACHABLE_SENTINEL")]
    )
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        with request_deadline_scope(
            "slotfill-transport-runway",
            total_seconds=DEFAULT_ASK_CEILING_SECONDS + RESERVE_SECONDS - 10.0,
        ) as deadline:
            content = _generate(ai, workspace)
            reasons = [entry["reason"] for entry in deadline.degradations()]
        assert SCAFFOLD_MARKER in content
        assert "UNREACHABLE_SENTINEL" not in content
    assert ai.models == [_PRIMARY]
    assert "slot_fill_transport_fallback_skipped_low_runway" in reasons, (
        "the skipped rung was silent; a run that could not afford its fallback "
        "must not look like a run whose fallback was never needed"
    )


# --- R2 on the live path ------------------------------------------------------


def test_the_live_contract_retry_carries_the_translation(models_pinned: None) -> None:
    """Request 107's lesson, pinned where production actually walks.

    The raw validator strings alone reproduced the violation byte-identically;
    the translation into edits existed but only `_slot_fill_retry_prompt` read
    it — a function the loop never calls for contract rejections. The live
    attempt-2 prompt must now carry errors AND their translation.
    """
    ai = _ScriptedAI([_CONTRACT_INVALID, _accepted_fill("TRANSLATED_SENTINEL")])
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        content = _generate(ai, workspace)
        assert "TRANSLATED_SENTINEL" in content
    retry_prompt = ai.prompts[-1]
    assert "CATALOGUE CONTRACT RETRY" in retry_prompt
    assert "How to repair: " in retry_prompt
    # The whole translation, not a word of it — a gutted guidance dict must fail
    # this, which per-word asserts cannot guarantee.
    assert _SLOT_FILL_RETRY_GUIDANCE[CONTRACT_REJECTION] in retry_prompt
