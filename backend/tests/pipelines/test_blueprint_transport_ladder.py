"""R1's last naked ask gets its ladder (owner-ruled, session 24).

The ask-site survey: `blueprint` was the only MANDATORY single ask with no
retry and no floor — everything downstream reads the blueprint, so one
transport cut was a dead run. The ladder is the house shape: classify first
(retryable provider raise or empty-cut body = transport; refusal propagates
untouched; a non-empty answer is accepted as-is — the blueprint has no
quality judge and quality never takes a model fallback), one bounded
same-model re-ask, ONE ask on the cross-provider slot, then fail closed
exactly as before the ladder existed. Every ask is its own telemetry row.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.pipelines.blueprint import (
    _ask_blueprint_with_transport_ladder,
)
from app.application.services.ai_context import current_ai_call
from app.core.config import settings
from app.infrastructure.ai_providers.response_parser import (
    ProviderGenerationError,
    ProviderGenerationResult,
)


def _provider_error(*, retryable: bool) -> ProviderGenerationError:
    result = ProviderGenerationResult(
        provider="openrouter",
        model="google/gemini-3-flash-preview",
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
        error_message_redacted="cut",
        retryable=retryable,
        refusal=not retryable,
        truncated=False,
        latency_ms=8,
    )
    return ProviderGenerationError("stream cut in transit", result=result)


class _WeatherAI:
    """"RAISE"/"REFUSE"/"" simulate the failure classes; text is healthy."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.models: list[str] = []
        self.attempts: list[int | None] = []

    def ask_chat(self, model, messages, **_kwargs):
        self.models.append(model)
        call = current_ai_call()
        self.attempts.append(call.attempt if call else None)
        item = self.responses.pop(0)
        if item == "RAISE":
            raise _provider_error(retryable=True)
        if item == "REFUSE":
            raise _provider_error(retryable=False)
        return item


def test_healthy_first_ask_is_the_only_ask(monkeypatch) -> None:
    ai = _WeatherAI(["A complete blueprint."])
    assert _ask_blueprint_with_transport_ladder(ai, "P") == "A complete blueprint."
    assert ai.attempts == [1]
    assert ai.models == [settings.TEXT_MODEL]


def test_one_cut_gets_one_same_model_reask(monkeypatch) -> None:
    ai = _WeatherAI(["RAISE", "A complete blueprint."])
    assert _ask_blueprint_with_transport_ladder(ai, "P") == "A complete blueprint."
    assert ai.attempts == [1, 2]
    assert ai.models == [settings.TEXT_MODEL, settings.TEXT_MODEL]


def test_two_cuts_take_the_cross_provider_rung(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "BLUEPRINT_TRANSPORT_FALLBACK_MODEL",
        "anthropic/claude-haiku-4.5",
    )
    ai = _WeatherAI(["RAISE", "", "A complete blueprint."])
    assert _ask_blueprint_with_transport_ladder(ai, "P") == "A complete blueprint."
    assert ai.attempts == [1, 2, 3]
    assert ai.models[-1] == "anthropic/claude-haiku-4.5"


def test_three_cuts_fail_closed_and_bounded(monkeypatch) -> None:
    ai = _WeatherAI(["RAISE", "RAISE", "RAISE", "never-asked"])
    with pytest.raises(ProviderGenerationError):
        _ask_blueprint_with_transport_ladder(ai, "P")
    assert len(ai.models) == 3  # the ladder is bounded — no fourth ask


def test_refusal_class_never_retries(monkeypatch) -> None:
    ai = _WeatherAI(["REFUSE", "never-asked"])
    with pytest.raises(ProviderGenerationError):
        _ask_blueprint_with_transport_ladder(ai, "P")
    assert len(ai.models) == 1


def test_empty_body_is_the_transport_class(monkeypatch) -> None:
    ai = _WeatherAI(["", "A complete blueprint."])
    assert _ask_blueprint_with_transport_ladder(ai, "P") == "A complete blueprint."
    assert ai.attempts == [1, 2]


def test_nonempty_answer_is_never_re_asked(monkeypatch) -> None:
    """The blueprint has no quality judge — a strange but non-empty answer is
    accepted as-is; quality never takes a model fallback."""

    ai = _WeatherAI(["?", "never-asked"])
    assert _ask_blueprint_with_transport_ladder(ai, "P") == "?"
    assert len(ai.models) == 1


def test_generate_mvp_blueprint_survives_a_cut_via_the_ladder(monkeypatch) -> None:
    """End-to-end through the real stage function: attempt 1 cut, attempt 2
    lands — the run that used to die keeps its blueprint. Catches the
    unwired-ladder mutation the helper-level tests cannot see."""

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.application.pipelines.blueprint import generate_mvp_blueprint
    from app.domain.models.request import Request
    from app.infrastructure.db.base import Base
    from app.infrastructure.templating.renderer import JinjaTemplateRenderer

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    req = Request(
        business_name="Ladder Fixture Co",
        industry="Personal Care",
        business_description="Small booking studio",
        project_type="new",
        email="fixture@example.invalid",
        status="new",
    )
    session.add(req)
    session.commit()
    session.refresh(req)

    ai = _WeatherAI(["RAISE", "A blueprint without extractable fields.", "{}"])
    try:
        generate_mvp_blueprint(
            session,
            req.id,
            ai,
            JinjaTemplateRenderer(str(BACKEND_DIR / "app" / "templates")),
        )
        session.refresh(req)
        assert req.mvp_blueprint == "A blueprint without extractable fields."
        assert ai.attempts[:2] == [1, 2]
    finally:
        session.close()


def test_same_provider_blueprint_fallback_warns(monkeypatch) -> None:
    from app.core.config import Settings, warn_same_provider_blueprint_fallback

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("TEXT_MODEL", "anthropic/claude-opus-5")
    monkeypatch.setenv(
        "BLUEPRINT_TRANSPORT_FALLBACK_MODEL", "anthropic/claude-haiku-4.5"
    )
    assert warn_same_provider_blueprint_fallback(Settings()) == ["TEXT_MODEL"]

    monkeypatch.setenv("TEXT_MODEL", "google/gemini-3-flash-preview")
    assert warn_same_provider_blueprint_fallback(Settings()) == []
