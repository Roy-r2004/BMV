"""Deterministic, test-only failure injection for Preview Generator v2.

Safety invariants
-----------------
* Impossible to enable when APP_ENV/ENVIRONMENT/ENV is production/prod.
* Impossible to enable unless PYTEST_CURRENT_TEST is set or
  BMV_FAILURE_INJECTION=1 is set in a non-production process.
* No HTTP/API surface installs plans — callers must be in-process tests.
* Plans are process-local and cleared explicitly between tests.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Any, Literal


FailureMode = Literal[
    "provider_timeout",
    "provider_invalid_json",
    "provider_partial_output",
    "provider_429",
    "provider_500",
    "provider_cancellation",
    "schema_validation",
    "db_persistence",
    "filesystem_write",
    "missing_generated_file",
    "invalid_import",
    "vite_build_failure",
    "playwright_startup_failure",
    "browser_timeout",
    "screenshot_failure",
    "accessibility_failure",
    "visual_model_timeout",
    "visual_rejection",
    "migration_failure",
    "process_restart",
]

INJECTABLE_STAGES: tuple[str, ...] = (
    "appspec",
    "tier_selection",
    "tier1_closure_heal",
    "product_strategy_v2",
    "information_architecture",
    "design_dna",
    "page_purpose_contract",
    "business_component_plan",
    "content_data_plan",
    "interaction_contract",
    "component_dependency_graph",
    "candidate_business_components",
    "candidate_pages",
    "candidate_validation",
    "runtime_build",
    "runtime_browser",
    "runtime_accessibility",
    "runtime_screenshot",
    "visual_critic",
    "visual_reviewer",
    "visual_refinement",
    "tier2_generation",
    "tier3_generation",
    "expanded_preview_publish",
    "migration_startup",
)


class FailureInjectionUnavailable(RuntimeError):
    """Raised when failure injection is requested outside a safe test context."""


@dataclass(frozen=True)
class FailureInjectionPlan:
    stage: str
    mode: FailureMode
    message: str = "Injected failure"
    after_attempts: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.stage not in INJECTABLE_STAGES:
            raise ValueError(f"Unknown injectable stage: {self.stage!r}")
        if self.after_attempts < 0:
            raise ValueError("after_attempts must be >= 0")


_LOCK = threading.Lock()
_PLAN: FailureInjectionPlan | None = None
_ATTEMPTS: dict[str, int] = {}
_AUDIT: list[dict[str, Any]] = []


def _app_env() -> str:
    return (
        os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or os.getenv("ENV") or ""
    ).strip().lower()


def failure_injection_enabled() -> bool:
    if _app_env() in {"production", "prod"}:
        return False
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True
    return os.getenv("BMV_FAILURE_INJECTION", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def list_injectable_stages() -> tuple[str, ...]:
    return INJECTABLE_STAGES


def install_failure_injection(plan: FailureInjectionPlan) -> None:
    if not failure_injection_enabled():
        raise FailureInjectionUnavailable(
            "Failure injection is disabled outside non-production tests."
        )
    with _LOCK:
        global _PLAN
        _PLAN = plan
        _ATTEMPTS.clear()
        _AUDIT.append(
            {
                "event": "install",
                "stage": plan.stage,
                "mode": plan.mode,
                "after_attempts": plan.after_attempts,
                "message": plan.message,
                "metadata": dict(plan.metadata),
            }
        )


def clear_failure_injection() -> None:
    with _LOCK:
        global _PLAN
        _PLAN = None
        _ATTEMPTS.clear()
        _AUDIT.append({"event": "clear"})


def audit_log() -> tuple[dict[str, Any], ...]:
    with _LOCK:
        return tuple(_AUDIT)


def consume_failure_injection(stage: str) -> FailureInjectionPlan | None:
    """Return a matching plan once its attempt threshold is reached.

    Safe no-op when injection is disabled or no plan is installed.
    """

    if not failure_injection_enabled():
        return None
    with _LOCK:
        global _PLAN
        plan = _PLAN
        if plan is None or plan.stage != stage:
            return None
        current = _ATTEMPTS.get(stage, 0)
        _ATTEMPTS[stage] = current + 1
        _AUDIT.append(
            {
                "event": "attempt",
                "stage": stage,
                "attempt": current + 1,
                "mode": plan.mode,
            }
        )
        if current < plan.after_attempts:
            return None
        _AUDIT.append(
            {
                "event": "fire",
                "stage": stage,
                "attempt": current + 1,
                "mode": plan.mode,
                "message": plan.message,
            }
        )
        # One-shot unless metadata asks to keep.
        if not plan.metadata.get("sticky"):
            _PLAN = None
        return plan


def raise_if_injected(stage: str, *, error_factory=None) -> None:
    """Convenience helper for tests/harness probes."""

    plan = consume_failure_injection(stage)
    if plan is None:
        return
    if error_factory is not None:
        raise error_factory(plan)
    raise RuntimeError(f"[{plan.stage}:{plan.mode}] {plan.message}")


__all__ = [
    "FailureInjectionPlan",
    "FailureInjectionUnavailable",
    "FailureMode",
    "INJECTABLE_STAGES",
    "audit_log",
    "clear_failure_injection",
    "consume_failure_injection",
    "failure_injection_enabled",
    "install_failure_injection",
    "list_injectable_stages",
    "raise_if_injected",
]
