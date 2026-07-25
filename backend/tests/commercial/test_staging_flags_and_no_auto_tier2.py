"""Staging hard-gate parsing and no automatic Tier 2 after Tier 1."""
from __future__ import annotations

import inspect

import pytest

from app.application.preview_app.pipeline import v2_contract
from app.core import config as config_module


def test_staging_hard_gates_parse(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_PERCENT", "0")
    monkeypatch.setenv("V2_PHASE7_PERCENT_SERVE_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_LIVE_CANARY_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_LIVE_CANARY_PROVIDERS_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_AUTO_ROLLBACK_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_PROMOTE_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_SHADOW_LIVE_PROVIDERS_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_CANARY_SIMULATION_ENABLED", "false")
    monkeypatch.setenv("V2_TIER2_GENERATION_ENABLED", "true")
    monkeypatch.setenv("V2_TIER3_GENERATION_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_ENABLED", "true")
    settings = config_module.Settings()
    assert settings.V2_PHASE7_ROLLOUT_PERCENT == 0
    assert settings.V2_PHASE7_PERCENT_SERVE_ENABLED is False
    assert settings.V2_PHASE7_LIVE_CANARY_ENABLED is False
    assert settings.V2_PHASE7_LIVE_CANARY_PROVIDERS_ENABLED is False
    assert settings.V2_PHASE7_AUTO_ROLLBACK_ENABLED is False
    assert settings.V2_PHASE7_PROMOTE_ENABLED is False
    assert settings.V2_PHASE7_SHADOW_LIVE_PROVIDERS_ENABLED is False
    assert settings.V2_PHASE7_CANARY_SIMULATION_ENABLED is False
    assert settings.V2_TIER2_GENERATION_ENABLED is True
    assert settings.V2_TIER3_GENERATION_ENABLED is False


def test_tier2_flag_does_not_auto_run_in_v2_contract(monkeypatch):
    monkeypatch.setattr(
        "app.application.preview_app.pipeline.v2_contract.settings.V2_TIER2_GENERATION_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "app.application.preview_app.pipeline.v2_contract.settings.V2_RUNTIME_VALIDATION_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "app.application.preview_app.pipeline.v2_contract.settings.V2_VISUAL_EVALUATION_ENABLED",
        True,
    )
    source = inspect.getsource(v2_contract.run_v2_contract_boundary)
    assert "orchestrate_v2_tier_2" not in source
    assert "orchestrate_v2_tier_3" not in source
    assert "Commercial gate" in source or "never auto-start" in source


def test_v2_contract_returns_phase5_without_tier2(monkeypatch):
    calls = {"tier2": 0}

    class _Settings:
        V2_RUNTIME_VALIDATION_ENABLED = True
        V2_VISUAL_EVALUATION_ENABLED = True

    monkeypatch.setattr(v2_contract, "settings", _Settings())
    monkeypatch.setattr(
        v2_contract,
        "build_v2_app_spec_contract",
        lambda *a, **k: {"preview_contract": {"status": "appspec_ready"}},
    )
    monkeypatch.setattr(
        v2_contract,
        "build_v2_design_contract",
        lambda *a, **k: {"preview_contract": {"status": "design_ready"}},
    )
    monkeypatch.setattr(
        v2_contract,
        "build_v2_composition_contract",
        lambda *a, **k: {"preview_contract": {"status": "composition_contract_ready"}},
    )
    monkeypatch.setattr(
        v2_contract,
        "build_v2_candidate_revision",
        lambda *a, **k: {"preview_contract": {"status": "candidate_build_pending"}},
    )
    monkeypatch.setattr(
        v2_contract,
        "validate_v2_candidate_runtime",
        lambda *a, **k: {
            "preview_contract": {"status": "candidate_runtime_validated"}
        },
    )
    phase5 = {"preview_contract": {"status": "candidate_visual_accepted"}}
    monkeypatch.setattr(
        v2_contract,
        "evaluate_v2_candidate_visuals",
        lambda *a, **k: phase5,
    )

    # Ensure any accidental import of orchestrate would fail the test if called
    import app.application.tier_orchestration.service as tier_svc

    monkeypatch.setattr(
        tier_svc,
        "orchestrate_v2_tier_2",
        lambda *a, **k: calls.__setitem__("tier2", calls["tier2"] + 1) or phase5,
    )

    result = v2_contract.run_v2_contract_boundary(
        db=None,
        request_id=1,
        ai_provider=None,
        template_renderer=None,
        req=object(),
        app_spec_revision_id=1,
    )
    assert result is phase5
    assert calls["tier2"] == 0
