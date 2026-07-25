"""Routing and production-service boundary proofs for Phase 7A."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

from app.api.v1.api_router import api_router
from app.application.rollout import repository as repo_mod
from app.application.rollout.service import RolloutControlPlaneService
from tests.rollout import harness as harness_mod


def _all_routes():
    return [r for r in api_router.routes if isinstance(r, APIRoute)]


def test_no_combined_or_unsafe_rollout_write_endpoints() -> None:
    for route in _all_routes():
        path = route.path.lower()
        methods = set(route.methods or [])
        if any(m in methods for m in ("POST", "PUT", "PATCH", "DELETE")):
            assert "pointer-swap" not in path
            # Phase 7D allows /breaker/auto-rollbacks/run only — not a combined
            # promote+rollback write shortcut.
            if "auto-rollback" in path:
                assert "/breaker/auto-rollbacks" in path
            assert "percent" not in path
            assert "canary" not in path
            # Serving pointer remains read-only; writes use promotions/rollbacks.
            if "serving-pointer" in path:
                assert methods == {"GET"}


def test_diagnostic_endpoints_allow_shadow_and_phase7c_writes() -> None:
    rollout_routes = [
        r for r in _all_routes() if "/admin/rollout" in r.path
    ]
    assert rollout_routes, "expected rollout diagnostics"
    allowed_post_suffixes = (
        "/shadow-evaluations",
        "/promotions",
        "/approvals",
        "/apply",
        "/rollbacks",
        "/breaker/evaluate",
        "/breaker/open",
        "/breaker/close",
        "/breaker/disable",
        "/breaker/auto-rollbacks/run",
        "/ops/alerts/",
    )
    for route in rollout_routes:
        methods = set(route.methods or [])
        if "POST" in methods:
            assert any(route.path.endswith(s) or s in route.path for s in allowed_post_suffixes)
            continue
        assert methods == {"GET"}


def test_test_only_harness_unreachable_from_application_routing() -> None:
    assert harness_mod.harness_is_importable_from_routing() is False
    app_root = Path(__file__).resolve().parents[2] / "app"
    offenders: list[str] = []
    for path in app_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if (
            "tests.rollout.harness" in text
            or "Phase7ATestOnlyRolloutHarness" in text
            or "TestOnlyRolloutHarness" in text
        ):
            offenders.append(str(path))
    assert offenders == []


def test_production_service_has_no_write_executor() -> None:
    service = RolloutControlPlaneService
    for name in ("promote", "rollback", "apply_pointer_swap"):
        with pytest.raises(RuntimeError, match="Phase 7A has no"):
            getattr(service(None), name)()  # type: ignore[arg-type]
    assert repo_mod.production_services_cannot_create_applied_decisions() is True
    assert repo_mod.production_services_cannot_mutate_pointers() is True
    # Structural: application/rollout must not import test harness
    source = inspect.getsource(repo_mod)
    assert "Phase7ATestOnlyRolloutHarness" not in source
    assert "PHASE7A_TEST_ONLY_MODE" not in source


def test_preview_apps_source_unchanged_contract() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "api"
        / "v1"
        / "routers"
        / "preview_apps.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert "get_dist_dir" in calls
    assert "resolve_serving_pointer" not in calls
