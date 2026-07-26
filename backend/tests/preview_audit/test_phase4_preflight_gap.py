"""Phase 4 orchestration preflight for smoke #25-class status mismatches."""
from __future__ import annotations

import pytest

from app.application.preview_app.pipeline.v2_contract import (
    Phase4StatusPreconditionError,
    ensure_phase4_entry_status,
)
from app.application.preview_app.testing.failure_injection import (
    FailureInjectionPlan,
    clear_failure_injection,
    install_failure_injection,
    raise_if_injected,
)


@pytest.fixture(autouse=True)
def _reset():
    clear_failure_injection()
    yield
    clear_failure_injection()


def test_orchestrator_preflight_rejects_non_pending_phase3b_status() -> None:
    with pytest.raises(
        Phase4StatusPreconditionError,
        match="phase4_status_precondition",
    ):
        ensure_phase4_entry_status(
            {
                "preview_contract": {
                    "status": "candidate_contract_failed",
                }
            }
        )


def test_orchestrator_preflight_allows_build_pending() -> None:
    ensure_phase4_entry_status(
        {"preview_contract": {"status": "candidate_build_pending"}}
    )


def test_runtime_build_injection_is_wired_for_pipeline_probes() -> None:
    install_failure_injection(
        FailureInjectionPlan(
            stage="runtime_build",
            mode="schema_validation",
            message="Phase 4 requires candidate_build_pending",
        )
    )
    with pytest.raises(RuntimeError, match="candidate_build_pending"):
        raise_if_injected("runtime_build")
