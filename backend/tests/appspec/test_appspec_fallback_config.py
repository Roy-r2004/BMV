from __future__ import annotations

import json

import pytest
from fastapi.responses import JSONResponse

from app.api.v1.routers.admin import configuration_safety
from app.api.v1.routers.health import health_ready
from app.core.config import (
    RuntimeConfigurationError,
    Settings,
    _parse_strict_bool,
    appspec_fallback_configuration,
    assert_safe_runtime_configuration,
    settings,
)


@pytest.mark.parametrize(
    ("raw", "expected", "valid"),
    [
        (None, False, True),
        ("false", False, True),
        ("False", False, True),
        ("FALSE", False, True),
        ("0", False, True),
        ("no", False, True),
        ("true", True, True),
        ("True", True, True),
        ("TRUE", True, True),
        ("1", True, True),
        ("yes", True, True),
        ("", False, True),
        ("definitely", False, False),
    ],
)
def test_strict_boolean_parser(
    raw: str | None,
    expected: bool,
    valid: bool,
) -> None:
    assert _parse_strict_bool(raw, default=False) == (expected, valid)


@pytest.mark.parametrize(
    ("raw", "expected", "valid"),
    [
        (None, False, True),
        ("false", False, True),
        ("False", False, True),
        ("FALSE", False, True),
        ("0", False, True),
        ("no", False, True),
        ("true", True, True),
        ("True", True, True),
        ("TRUE", True, True),
        ("1", True, True),
        ("yes", True, True),
        ("", False, True),
        ("malformed", False, False),
    ],
)
def test_actual_settings_loader_boolean_matrix(
    monkeypatch: pytest.MonkeyPatch,
    raw: str | None,
    expected: bool,
    valid: bool,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    if raw is None:
        monkeypatch.delenv("APPSPEC_FALLBACK_ENABLED", raising=False)
    else:
        monkeypatch.setenv("APPSPEC_FALLBACK_ENABLED", raw)

    config = Settings()

    assert config.APPSPEC_FALLBACK_ENABLED is expected
    assert config.APPSPEC_FALLBACK_CONFIG_VALID is valid


def test_source_default_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APPSPEC_FALLBACK_ENABLED", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("ENV", raising=False)

    config = Settings()

    assert config.APPSPEC_FALLBACK_ENABLED is False
    assert config.APPSPEC_FALLBACK_SAFETY_CODE == "ok"


def test_explicit_true_allowed_only_outside_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("APPSPEC_FALLBACK_ENABLED", "true")
    development = Settings()
    assert development.APPSPEC_FALLBACK_ENABLED is True
    assert_safe_runtime_configuration(development)

    monkeypatch.setenv("APP_ENV", "production")
    production = Settings()
    assert production.APPSPEC_FALLBACK_ENABLED is True
    assert production.APPSPEC_FALLBACK_SAFETY_CODE == (
        "unsafe_appspec_fallback_enabled"
    )
    with pytest.raises(
        RuntimeConfigurationError,
        match="unsafe_appspec_fallback_enabled",
    ):
        assert_safe_runtime_configuration(production)


def test_malformed_value_fails_safety_without_enabling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APPSPEC_FALLBACK_ENABLED", "not-a-boolean")

    config = Settings()

    assert config.APPSPEC_FALLBACK_ENABLED is False
    assert config.APPSPEC_FALLBACK_CONFIG_VALID is False
    with pytest.raises(
        RuntimeConfigurationError,
        match="invalid_appspec_fallback_boolean",
    ):
        assert_safe_runtime_configuration(config)


def test_readiness_fails_with_precise_configuration_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", True)
    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_CONFIG_VALID", True)
    monkeypatch.setattr(
        settings,
        "APPSPEC_FALLBACK_SAFETY_CODE",
        "unsafe_appspec_fallback_enabled",
    )
    monkeypatch.setattr(
        settings,
        "APP_ENVIRONMENT_CLASSIFICATION",
        "production",
    )

    response = health_ready()

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    payload = json.loads(response.body)
    assert payload == {
        "status": "not_ready",
        "ready": False,
        "configuration_error": "unsafe_appspec_fallback_enabled",
    }


def test_trusted_admin_diagnostics_are_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_CONFIG_VALID", True)
    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_SAFETY_CODE", "ok")
    monkeypatch.setattr(
        settings,
        "APPSPEC_FALLBACK_CONFIG_SOURCE",
        "source_default",
    )
    monkeypatch.setattr(
        settings,
        "APP_ENVIRONMENT_CLASSIFICATION",
        "production",
    )

    payload = configuration_safety(True)
    serialized = json.dumps(payload)

    assert payload["appspec_fallback"] == {
        "appspec_fallback_enabled": False,
        "configuration_source": "source_default",
        "environment_classification": "production",
        "configuration_valid": True,
        "safety_assertion": "passed",
        "safety_code": "ok",
    }
    assert "candidate_models" in payload
    assert "effective_model" in payload["candidate_models"]["component"]
    assert "effective_model" in payload["candidate_models"]["pages"]
    assert "context_window" in payload["candidate_models"]["component"]
    assert "capability_profile_revision" in payload["candidate_models"][
        "component"
    ]
    assert all(
        enabled is False
        for enabled in payload["related_fallbacks"].values()
    )
    assert "password" not in serialized.lower()
    assert "authorization" not in serialized.lower()
    assert "prompt" not in serialized.lower()
