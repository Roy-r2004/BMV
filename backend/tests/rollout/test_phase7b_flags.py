"""Phase 7B flag defaults and fail-closed validation."""
from __future__ import annotations

import importlib

from app.core import config as config_module


def _reload(monkeypatch, **env):
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    importlib.reload(config_module)
    return config_module.settings


def test_shadow_flags_default_safe(monkeypatch) -> None:
    s = _reload(
        monkeypatch,
        V2_PHASE7_SHADOW_MODE=None,
        V2_PHASE7_SHADOW_COMPARE_ENABLED=None,
        V2_PHASE7_SHADOW_LIVE_PROVIDERS_ENABLED=None,
        V2_PHASE7_SHADOW_MAX_CONCURRENCY=None,
        V2_PHASE7_SHADOW_MAX_WALL_SECONDS=None,
    )
    assert s.V2_PHASE7_SHADOW_MODE == "reuse_accepted"
    assert s.V2_PHASE7_SHADOW_COMPARE_ENABLED is True
    assert s.V2_PHASE7_SHADOW_LIVE_PROVIDERS_ENABLED is False
    assert s.V2_PHASE7_SHADOW_MAX_CONCURRENCY == 1
    assert s.V2_PHASE7_SHADOW_MAX_WALL_SECONDS == 3600


def test_malformed_shadow_mode_fail_closed(monkeypatch) -> None:
    s = _reload(
        monkeypatch,
        V2_PHASE7_SHADOW_MODE="not-a-mode",
        V2_PHASE7_ROLLOUT_ENABLED="true",
        V2_PHASE7_SHADOW_ENABLED="true",
    )
    assert s.V2_PHASE7_CONFIG_VALID is False
    assert s.V2_PHASE7_SHADOW_ENABLED is False
    assert s.V2_PHASE7_SHADOW_MODE == "reuse_accepted"


def test_live_providers_flag_fail_closed(monkeypatch) -> None:
    s = _reload(
        monkeypatch,
        V2_PHASE7_SHADOW_LIVE_PROVIDERS_ENABLED="true",
        V2_PHASE7_SHADOW_ENABLED="true",
    )
    assert s.V2_PHASE7_CONFIG_VALID is False
    assert s.V2_PHASE7_SHADOW_ENABLED is False
