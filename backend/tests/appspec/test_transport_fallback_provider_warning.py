"""R7: the transport fallback's cross-provider invariant is asserted, not remembered.

The fallback's whole value is provider independence (runs 136/137: a
provider-side storm cuts the primary and its bounded re-ask alike). Until now
"keep it cross-provider" lived in a `.env` comment. Startup now WARNS — never
crashes — when `APPSPEC_TRANSPORT_FALLBACK_MODEL` shares a provider prefix
with `APPSPEC_MODEL` or `APPSPEC_REPAIR_MODEL`.
"""
from __future__ import annotations

import logging

import pytest

from app.core.config import (
    Settings,
    _model_provider_prefix,
    assert_safe_runtime_configuration,
    warn_same_provider_transport_fallback,
)


def _config(
    monkeypatch: pytest.MonkeyPatch,
    *,
    primary: str,
    repair: str,
    fallback: str,
    coverage: str = "google/gemini-2.5-flash",
) -> Settings:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("APPSPEC_MODEL", primary)
    monkeypatch.setenv("APPSPEC_REPAIR_MODEL", repair)
    monkeypatch.setenv("APPSPEC_COVERAGE_MODEL", coverage)
    monkeypatch.setenv("APPSPEC_TRANSPORT_FALLBACK_MODEL", fallback)
    return Settings()


@pytest.mark.parametrize(
    ("model", "prefix"),
    [
        ("google/gemini-2.5-flash", "google"),
        ("anthropic/claude-haiku-4.5", "anthropic"),
        ("Anthropic/claude-haiku-4.5", "anthropic"),
        ("z-ai/glm-5.2:nitro", "z-ai"),
        ("gemini-2.5-flash", None),
        ("", None),
        ("/claude-haiku-4.5", None),
    ],
)
def test_provider_prefix_parses_the_openrouter_head(
    model: str, prefix: str | None
) -> None:
    assert _model_provider_prefix(model) == prefix


def test_cross_provider_fallback_stays_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(
        monkeypatch,
        primary="google/gemini-2.5-flash",
        repair="google/gemini-2.5-flash",
        fallback="anthropic/claude-haiku-4.5",
    )
    assert warn_same_provider_transport_fallback(config) == []


def test_same_provider_as_primary_warns_and_names_the_slot(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = _config(
        monkeypatch,
        primary="anthropic/claude-opus-5",
        repair="google/gemini-2.5-flash",
        fallback="anthropic/claude-haiku-4.5",
    )
    with caplog.at_level(logging.WARNING, logger="bmv.Config"):
        offenders = warn_same_provider_transport_fallback(config)
    assert offenders == ["APPSPEC_MODEL"]
    assert any(
        "APPSPEC_TRANSPORT_FALLBACK_MODEL" in record.getMessage()
        and "APPSPEC_MODEL" in record.getMessage()
        for record in caplog.records
    )


def test_same_provider_as_both_slots_lists_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(
        monkeypatch,
        primary="anthropic/claude-opus-5",
        repair="anthropic/claude-sonnet-5",
        fallback="anthropic/claude-haiku-4.5",
    )
    assert warn_same_provider_transport_fallback(config) == [
        "APPSPEC_MODEL",
        "APPSPEC_REPAIR_MODEL",
    ]


def test_same_provider_as_coverage_slot_warns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The coverage reviewer joined the rung's riders (session 24): a fallback
    # sharing its provider dies in the same storm that cut both coverage asks.
    config = _config(
        monkeypatch,
        primary="google/gemini-2.5-flash",
        repair="google/gemini-2.5-flash",
        coverage="anthropic/claude-opus-5",
        fallback="anthropic/claude-haiku-4.5",
    )
    assert warn_same_provider_transport_fallback(config) == [
        "APPSPEC_COVERAGE_MODEL"
    ]


def test_provider_match_is_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(
        monkeypatch,
        primary="Anthropic/claude-opus-5",
        repair="google/gemini-2.5-flash",
        fallback="anthropic/claude-haiku-4.5",
    )
    assert warn_same_provider_transport_fallback(config) == ["APPSPEC_MODEL"]


def test_unclassifiable_fallback_never_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(
        monkeypatch,
        primary="anthropic/claude-opus-5",
        repair="anthropic/claude-opus-5",
        fallback="claude-haiku-4.5",
    )
    assert warn_same_provider_transport_fallback(config) == []


def test_startup_assertion_warns_but_never_crashes_on_same_provider(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = _config(
        monkeypatch,
        primary="anthropic/claude-opus-5",
        repair="anthropic/claude-sonnet-5",
        fallback="anthropic/claude-haiku-4.5",
    )
    with caplog.at_level(logging.WARNING, logger="bmv.Config"):
        assert_safe_runtime_configuration(config)  # must not raise
    assert any(
        "shares provider" in record.getMessage() for record in caplog.records
    )
