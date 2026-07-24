"""Phase 7A configuration parsing and fail-closed validation."""
from __future__ import annotations

import importlib

from app.core import config as config_module


def _reload_settings(monkeypatch, **env):
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    importlib.reload(config_module)
    return config_module.settings


def test_phase7_defaults_fail_closed(monkeypatch) -> None:
    settings = _reload_settings(
        monkeypatch,
        V2_PHASE7_ROLLOUT_ENABLED=None,
        V2_PHASE7_SHADOW_ENABLED=None,
        V2_PHASE7_PROMOTE_ENABLED=None,
        V2_PHASE7_ROLLOUT_PERCENT=None,
        V2_PHASE7_REQUEST_ALLOWLIST=None,
    )
    assert settings.V2_PHASE7_ROLLOUT_ENABLED is False
    assert settings.V2_PHASE7_SHADOW_ENABLED is False
    assert settings.V2_PHASE7_PROMOTE_ENABLED is False
    assert settings.V2_PHASE7_ROLLOUT_PERCENT == 0
    assert settings.V2_PHASE7_REQUEST_ALLOWLIST == ()
    assert settings.V2_PHASE7_CONFIG_VALID is True


def test_malformed_percent_fail_closed(monkeypatch) -> None:
    settings = _reload_settings(
        monkeypatch,
        V2_PHASE7_ROLLOUT_PERCENT="abc",
        V2_PHASE7_ROLLOUT_ENABLED="true",
    )
    assert settings.V2_PHASE7_CONFIG_VALID is False
    assert settings.V2_PHASE7_ROLLOUT_ENABLED is False
    assert settings.V2_PHASE7_ROLLOUT_PERCENT == 0


def test_malformed_allowlist_fail_closed(monkeypatch) -> None:
    settings = _reload_settings(
        monkeypatch,
        V2_PHASE7_REQUEST_ALLOWLIST="1,nope,3",
        V2_PHASE7_ROLLOUT_ENABLED="true",
    )
    assert settings.V2_PHASE7_CONFIG_VALID is False
    assert settings.V2_PHASE7_ROLLOUT_ENABLED is False
    assert settings.V2_PHASE7_REQUEST_ALLOWLIST == ()


def test_allowlist_normalized_unique_sorted(monkeypatch) -> None:
    settings = _reload_settings(
        monkeypatch,
        V2_PHASE7_REQUEST_ALLOWLIST="3,1,1,2",
    )
    assert settings.V2_PHASE7_REQUEST_ALLOWLIST == (1, 2, 3)
