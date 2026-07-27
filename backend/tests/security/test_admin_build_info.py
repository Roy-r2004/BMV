from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import deps
from app.api.deps import verify_admin
from app.api.v1.routers.admin import build_info
from app.api.v1.routers.health import health, health_live, health_ready
from app.application.services.runtime_metadata import production_build_info


def _settings(**overrides):
    values = {
        "APP_VERSION": "1.0.0",
        "V2_CANDIDATE_COMPONENT_MODEL": "google/gemini-2.5-flash",
        "V2_CANDIDATE_PAGE_MODEL": "google/gemini-2.5-flash",
        "V2_CANDIDATE_REPAIR_MODEL": "z-ai/glm-5.2",
        "V2_CANDIDATE_REPAIR_TIMEOUT_SECONDS": 300,
        "V2_CANDIDATE_MAX_CALLS": 4,
        "V2_DESIGN_DNA_MAX_TOKENS": 8000,
        "V2_DESIGN_STAGE_MAX_ATTEMPTS": 4,
        "V2_DESIGN_DNA_TIMEOUT_SECONDS": 300,
        "V2_DESIGN_CONTRACT_TIMEOUT_SECONDS": 1200,
        "APPSPEC_FALLBACK_ENABLED": False,
        "APPSPEC_FALLBACK_CONFIG_VALID": True,
        "APPSPEC_FALLBACK_SAFETY_CODE": "ok",
        "APPSPEC_FALLBACK_CONFIG_SOURCE": "environment",
        "APP_ENVIRONMENT_CLASSIFICATION": "production",
        "V2_PHASE7_ROLLOUT_ENABLED": False,
        "V2_PHASE7_LIVE_CANARY_ENABLED": False,
        "V2_PHASE7_PERCENT_SERVE_ENABLED": False,
        "V2_PHASE7_PROMOTE_ENABLED": False,
        "V2_PHASE7_SHADOW_ENABLED": False,
        "V2_PHASE7_AUTO_ROLLBACK_ENABLED": False,
        "ADMIN_PASSWORD": "must-not-leak",
        "OPENROUTER_API_KEY": "must-not-leak",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_build_info_returns_only_approved_non_secret_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_GIT_REVISION", "a" * 40)
    monkeypatch.setenv("APP_BUILD_TIMESTAMP", "2026-07-27T12:00:00Z")
    payload = production_build_info(
        _settings(),
        process_started_at="2026-07-27T12:05:00Z",
    )

    assert payload["revision"] == "a" * 40
    assert payload["revision_verified"] is True
    assert payload["candidate_caps"] == {
        "total": 4,
        "components": 2,
        "pages": 2,
    }
    assert payload["generated_data_api_policy_revision"] == (
        "2026-07-27.generated-data-api.1"
    )
    serialized = json.dumps(payload).lower()
    for forbidden in ("must-not-leak", "admin_password", "openrouter_api_key"):
        assert forbidden not in serialized


def test_build_info_marks_missing_revision_as_unverified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APP_GIT_REVISION", raising=False)
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.delenv("COMMIT_SHA", raising=False)
    payload = production_build_info(_settings())

    assert payload["revision"] is None
    assert payload["revision_verified"] is False


def test_configuration_fingerprint_changes_only_for_approved_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_GIT_REVISION", "b" * 40)
    baseline = production_build_info(_settings())
    changed = production_build_info(
        _settings(V2_CANDIDATE_REPAIR_TIMEOUT_SECONDS=299)
    )
    secret_changed = production_build_info(
        _settings(ADMIN_PASSWORD="different-secret")
    )

    assert baseline["configuration_fingerprint"] != changed[
        "configuration_fingerprint"
    ]
    assert baseline["configuration_fingerprint"] == secret_changed[
        "configuration_fingerprint"
    ]


def test_build_info_endpoint_is_admin_guarded_and_returns_metadata() -> None:
    parameters = inspect.signature(build_info).parameters
    assert "_" in parameters

    payload = build_info(True)

    assert "configuration_fingerprint" in payload
    assert "generated_data_api_policy_revision" in payload


def test_verify_admin_rejects_non_admin_bearer_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deps,
        "get_user_by_token",
        lambda _db, _token: SimpleNamespace(is_admin=False),
    )

    with pytest.raises(HTTPException) as exc:
        verify_admin(
            db=object(),
            x_admin_password=None,
            authorization="Bearer non-admin-token",
        )

    assert exc.value.status_code == 401


def test_verify_admin_accepts_admin_bearer_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deps,
        "get_user_by_token",
        lambda _db, _token: SimpleNamespace(is_admin=True),
    )

    assert (
        verify_admin(
            db=object(),
            x_admin_password=None,
            authorization="Bearer admin-token",
        )
        is True
    )


def test_public_health_endpoints_expose_no_build_or_configuration_metadata() -> None:
    assert health() == {"status": "ok"}
    assert health_live() == {"status": "ok", "live": True}
    ready_result = health_ready()
    readiness = (
        ready_result
        if isinstance(ready_result, dict)
        else json.loads(ready_result.body)
    )
    assert {
        "revision",
        "image_digest",
        "configuration_fingerprint",
        "candidate_models",
        "generated_data_api_policy_revision",
    }.isdisjoint(readiness)
