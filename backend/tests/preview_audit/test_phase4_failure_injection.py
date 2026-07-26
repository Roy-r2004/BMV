"""Focused Phase 4 failure-injection coverage for wired runtime stages."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.application.preview_app.testing.failure_injection import (
    FailureInjectionPlan,
    clear_failure_injection,
    install_failure_injection,
)
from app.application.runtime_validation.accessibility import (
    run_baseline_accessibility_scan,
)
from app.application.runtime_validation.browser import run_browser_validation
from app.application.runtime_validation.build import run_build_validation
from app.application.runtime_validation.policy import runtime_limits
from app.domain.schemas.runtime_validation import (
    RuntimeToolVersions,
    RuntimeValidationRefs,
)


@pytest.fixture(autouse=True)
def _reset():
    clear_failure_injection()
    yield
    clear_failure_injection()


def _refs() -> RuntimeValidationRefs:
    return RuntimeValidationRefs(
        request_id=1,
        candidate_revision_id=1,
        candidate_revision_uuid="00000000-0000-4000-8000-000000000001",
        candidate_manifest_sha256="1" * 64,
        dependency_lock_sha256="2" * 64,
        candidate_generator_version="v2-phase3b",
        candidate_policy_revision="2026-07-24.1",
    )


def _tools() -> RuntimeToolVersions:
    return RuntimeToolVersions(
        node="v22",
        typescript="5.8.3",
        vite="8.1.3",
        playwright="1.61.0",
        browser_name="chromium",
        browser_version="chromium-1228",
    )


def test_runtime_build_injection_stops_before_prebuild() -> None:
    install_failure_injection(
        FailureInjectionPlan(
            stage="runtime_build",
            mode="vite_build_failure",
            message="injected runtime_build",
        )
    )
    with pytest.raises(RuntimeError, match="injected runtime_build"):
        run_build_validation(
            refs=_refs(),
            candidate_path=Path("."),
            frozen_source_path=Path("."),
            expected_manifest=(),
            source_sha_before="1" * 64,
            limits=runtime_limits(),
            tools=_tools(),
        )


def test_runtime_browser_injection_stops_before_playwright() -> None:
    install_failure_injection(
        FailureInjectionPlan(
            stage="runtime_browser",
            mode="playwright_startup_failure",
            message="injected runtime_browser",
        )
    )
    context = SimpleNamespace(
        contracts=SimpleNamespace(
            page_purpose=SimpleNamespace(pages=()),
            interactions=SimpleNamespace(interactions=()),
        )
    )
    with pytest.raises(RuntimeError, match="injected runtime_browser"):
        run_browser_validation(
            context=context,  # type: ignore[arg-type]
            base_url="http://127.0.0.1:1",
            build_hash="3" * 64,
            evidence_root=Path("."),
            evidence_relbase="evidence",
            limits=runtime_limits(),
            cache_browser_version="chromium-1228",
        )


def test_runtime_accessibility_injection_stops_before_scan() -> None:
    install_failure_injection(
        FailureInjectionPlan(
            stage="runtime_accessibility",
            mode="accessibility_failure",
            message="injected runtime_accessibility",
        )
    )
    with pytest.raises(RuntimeError, match="injected runtime_accessibility"):
        run_baseline_accessibility_scan(
            page=None,
            refs=_refs(),
            cache_key="4" * 64,
            build_hash="3" * 64,
            page_id="PAGE-ONE",
            route="/",
            viewport="desktop",
        )
