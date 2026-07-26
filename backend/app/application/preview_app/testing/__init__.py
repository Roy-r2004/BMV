"""Test-only Preview Generator v2 diagnostics.

This package must never be enabled in production configuration.
"""

from app.application.preview_app.testing.failure_injection import (
    FailureInjectionPlan,
    FailureInjectionUnavailable,
    clear_failure_injection,
    consume_failure_injection,
    failure_injection_enabled,
    install_failure_injection,
    list_injectable_stages,
)

__all__ = [
    "FailureInjectionPlan",
    "FailureInjectionUnavailable",
    "clear_failure_injection",
    "consume_failure_injection",
    "failure_injection_enabled",
    "install_failure_injection",
    "list_injectable_stages",
]
