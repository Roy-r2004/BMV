"""Safety and behavior tests for the test-only failure injection harness."""
from __future__ import annotations

import os

import pytest

from app.application.preview_app.testing.failure_injection import (
    FailureInjectionPlan,
    FailureInjectionUnavailable,
    audit_log,
    clear_failure_injection,
    consume_failure_injection,
    failure_injection_enabled,
    install_failure_injection,
    list_injectable_stages,
    raise_if_injected,
)


@pytest.fixture(autouse=True)
def _reset_injection():
    clear_failure_injection()
    yield
    clear_failure_injection()


def test_injection_enabled_under_pytest() -> None:
    assert os.getenv("PYTEST_CURRENT_TEST")
    assert failure_injection_enabled() is True


def test_production_env_disables_injection(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    assert failure_injection_enabled() is False
    with pytest.raises(FailureInjectionUnavailable):
        install_failure_injection(
            FailureInjectionPlan(
                stage="business_component_plan",
                mode="provider_timeout",
            )
        )


def test_unknown_stage_rejected() -> None:
    with pytest.raises(ValueError):
        FailureInjectionPlan(stage="not_a_stage", mode="provider_timeout")


def test_one_shot_consume_and_audit() -> None:
    install_failure_injection(
        FailureInjectionPlan(
            stage="candidate_pages",
            mode="provider_invalid_json",
            message="boom",
            after_attempts=1,
        )
    )
    assert consume_failure_injection("candidate_pages") is None
    fired = consume_failure_injection("candidate_pages")
    assert fired is not None
    assert fired.mode == "provider_invalid_json"
    assert consume_failure_injection("candidate_pages") is None
    events = [item["event"] for item in audit_log()]
    assert "install" in events
    assert "fire" in events


def test_raise_if_injected_helper() -> None:
    install_failure_injection(
        FailureInjectionPlan(
            stage="runtime_build",
            mode="vite_build_failure",
            message="vite failed",
        )
    )
    with pytest.raises(RuntimeError, match="vite_build_failure"):
        raise_if_injected("runtime_build")


def test_injectable_stage_catalog_covers_pipeline() -> None:
    stages = set(list_injectable_stages())
    for required in (
        "appspec",
        "business_component_plan",
        "candidate_pages",
        "runtime_build",
        "visual_critic",
        "tier2_generation",
        "migration_startup",
    ):
        assert required in stages
