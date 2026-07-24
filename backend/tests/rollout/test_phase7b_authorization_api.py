"""Phase 7B RBAC, client payload rejection, and route surface."""
from __future__ import annotations

import importlib
import inspect

import pytest
from fastapi.routing import APIRoute

from app.api.v1.api_router import api_router
from app.api.v1.routers import preview_apps
from app.application.rollout.authorization import (
    RolloutAuthorizationError,
    reject_client_supplied_roles,
)
from app.application.rollout.shadow_lineage import AcceptedLineage
from app.application.rollout.shadow_service import ShadowExecutionError, ShadowService
from app.core import config as config_module
from app.domain.schemas.rollout import TrustedRolloutActor
from app.domain.schemas.shadow_evaluation import ShadowStartRequest
from tests.rollout.helpers import dispose, enable_test_only_mode, make_rollout_engine, make_session


def _enable(monkeypatch) -> None:
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_ENABLED", "true")
    monkeypatch.setenv("V2_PHASE7_SHADOW_ENABLED", "true")
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_PERCENT", "100")
    importlib.reload(config_module)


def test_operator_admin_can_start_viewer_approver_cannot(monkeypatch) -> None:
    enable_test_only_mode()
    _enable(monkeypatch)
    engine, root = make_rollout_engine()
    db = make_session(engine)
    monkeypatch.setattr(
        "app.application.rollout.shadow_service.locate_latest_accepted_lineage",
        lambda *_a, **_k: AcceptedLineage(
            candidate_revision_id=7,
            effective_summary_id=1,
            effective_summary_sha256="a" * 64,
            candidate_manifest_sha256="b" * 64,
            phase4_status="candidate_runtime_validated",
            phase5_status="candidate_visual_accepted",
            highest_accepted_tier=2,
            lineage_sha256="a" * 64,
            candidate_routes=None,
        ),
    )
    svc = ShadowService(db)
    for role in ("rollout_operator", "rollout_admin"):
        view = svc.start_shadow(
            actor=TrustedRolloutActor(
                actor_id=role, roles=(role,), auth_source="test_fixture"
            ),
            request_id=1,
            body=ShadowStartRequest(
                reason="ok", mode="regenerate_fixture", idempotency_key=f"k-{role}"
            ),
        )
        assert view.result_status == "completed"
    for role in ("rollout_viewer", "rollout_approver"):
        with pytest.raises(RolloutAuthorizationError):
            svc.start_shadow(
                actor=TrustedRolloutActor(
                    actor_id=role, roles=(role,), auth_source="test_fixture"
                ),
                request_id=1,
                body=ShadowStartRequest(reason="nope", mode="regenerate_fixture"),
            )
    db.close()
    dispose(engine, root)


def test_client_supplied_roles_rejected() -> None:
    with pytest.raises(RolloutAuthorizationError):
        reject_client_supplied_roles({"actor_id": "x"})
    with pytest.raises(RolloutAuthorizationError):
        reject_client_supplied_roles({"roles": ["rollout_admin"]})
    with pytest.raises(RolloutAuthorizationError):
        reject_client_supplied_roles({"provider": "openrouter"})


def test_api_routes_shadow_only_no_promote() -> None:
    routes = [r for r in api_router.routes if isinstance(r, APIRoute)]
    shadow_posts = [
        r
        for r in routes
        if "shadow-evaluations" in r.path and "POST" in (r.methods or set())
    ]
    assert shadow_posts
    for route in routes:
        path = route.path.lower()
        methods = set(route.methods or [])
        if any(m in methods for m in ("POST", "PUT", "PATCH", "DELETE")):
            assert "promote" not in path
            assert "rollback" not in path
            assert "pointer-swap" not in path
            assert "canary" not in path or "GET" in methods


def test_preview_apps_unchanged_and_no_shadow_import() -> None:
    source = inspect.getsource(preview_apps)
    assert "shadow" not in source.lower()
    assert "resolve_serving_pointer" not in source
    assert "get_dist_dir" in source


def test_allowlist_and_percent_targeting(monkeypatch) -> None:
    enable_test_only_mode()
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_ENABLED", "true")
    monkeypatch.setenv("V2_PHASE7_SHADOW_ENABLED", "true")
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_PERCENT", "0")
    monkeypatch.setenv("V2_PHASE7_REQUEST_ALLOWLIST", "1")
    importlib.reload(config_module)
    engine, root = make_rollout_engine()
    db = make_session(engine)
    monkeypatch.setattr(
        "app.application.rollout.shadow_service.locate_latest_accepted_lineage",
        lambda *_a, **_k: None,
    )
    svc = ShadowService(db)
    ok = svc.start_shadow(
        actor=TrustedRolloutActor(
            actor_id="op", roles=("rollout_operator",), auth_source="test_fixture"
        ),
        request_id=1,
        body=ShadowStartRequest(reason="allowlisted", mode="regenerate_fixture"),
    )
    assert ok.result_status == "completed"
    denied = svc.start_shadow(
        actor=TrustedRolloutActor(
            actor_id="op", roles=("rollout_operator",), auth_source="test_fixture"
        ),
        request_id=42,
        body=ShadowStartRequest(reason="not-allowlisted", mode="regenerate_fixture"),
    )
    assert denied.result_status == "failed"
    assert "outside_allowlist_and_percent" in denied.telemetry.rejection_reasons
    db.close()
    dispose(engine, root)
