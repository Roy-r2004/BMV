"""Phase 7B shadow execution: modes, lineage, telemetry, pointer invariance."""
from __future__ import annotations

import importlib

import pytest
from sqlalchemy import text

from app.application.rollout.shadow_lineage import AcceptedLineage
from app.application.rollout.shadow_service import ShadowExecutionError, ShadowService
from app.core import config as config_module
from app.domain.schemas.rollout import TrustedRolloutActor
from app.domain.schemas.shadow_evaluation import ShadowStartRequest
from tests.rollout.helpers import dispose, enable_test_only_mode, make_rollout_engine, make_session


def _enable_shadow(monkeypatch) -> None:
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_ENABLED", "true")
    monkeypatch.setenv("V2_PHASE7_SHADOW_ENABLED", "true")
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_PERCENT", "100")
    monkeypatch.setenv("V2_PHASE7_SHADOW_LIVE_PROVIDERS_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_SHADOW_MODE", "reuse_accepted")
    importlib.reload(config_module)


def _operator() -> TrustedRolloutActor:
    return TrustedRolloutActor(
        actor_id="op-1",
        roles=("rollout_operator",),
        auth_source="test_fixture",
    )


def _lineage() -> AcceptedLineage:
    return AcceptedLineage(
        candidate_revision_id=7,
        effective_summary_id=1,
        effective_summary_sha256="a" * 64,
        candidate_manifest_sha256="b" * 64,
        phase4_status="candidate_runtime_validated",
        phase5_status="candidate_visual_accepted",
        highest_accepted_tier=2,
        lineage_sha256="a" * 64,
        candidate_routes=None,
    )


def test_flags_off_writes_no_shadow_row(monkeypatch) -> None:
    enable_test_only_mode()
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_SHADOW_ENABLED", "false")
    importlib.reload(config_module)
    engine, root = make_rollout_engine()
    db = make_session(engine)
    svc = ShadowService(db)
    with pytest.raises(ShadowExecutionError, match="flags_off"):
        svc.start_shadow(
            actor=_operator(),
            request_id=1,
            body=ShadowStartRequest(reason="test"),
        )
    assert (
        db.execute(text("SELECT COUNT(*) FROM preview_shadow_evaluations")).scalar()
        == 0
    )
    db.close()
    dispose(engine, root)


def test_reuse_accepted_zero_providers_and_lineage(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_shadow(monkeypatch)
    engine, root = make_rollout_engine()
    db = make_session(engine)
    monkeypatch.setattr(
        "app.application.rollout.shadow_service.locate_latest_accepted_lineage",
        lambda _db, _rid: _lineage(),
    )
    svc = ShadowService(db)
    view = svc.start_shadow(
        actor=_operator(),
        request_id=1,
        body=ShadowStartRequest(reason="reuse", mode="reuse_accepted"),
    )
    db.commit()
    assert view.result_status == "completed"
    assert view.telemetry.provider_calls == 0
    assert view.telemetry.synthetic_fixture_telemetry is False
    assert view.telemetry.no_serving_mutation is True
    assert (
        view.telemetry.pointer_version_before
        == view.telemetry.pointer_version_after
    )
    rows = db.execute(
        text(
            "SELECT result_status, terminal_of_evaluation_id, shadow_attempt_uuid "
            "FROM preview_shadow_evaluations ORDER BY id"
        )
    ).all()
    assert len(rows) == 2
    assert rows[0][0] == "pending"
    assert rows[0][1] is None
    assert rows[1][0] == "completed"
    assert rows[1][1] == 1
    assert rows[0][2] == rows[1][2]
    # Pending immutable
    pending_tel = db.execute(
        text("SELECT telemetry_sha256 FROM preview_shadow_evaluations WHERE id=1")
    ).scalar()
    db.execute(
        text(
            "SELECT telemetry_sha256 FROM preview_shadow_evaluations WHERE id=1"
        )
    )
    assert pending_tel
    db.close()
    dispose(engine, root)


def test_regenerate_fixture_synthetic_telemetry(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_shadow(monkeypatch)
    engine, root = make_rollout_engine()
    db = make_session(engine)
    monkeypatch.setattr(
        "app.application.rollout.shadow_service.locate_latest_accepted_lineage",
        lambda *_a, **_k: None,
    )
    svc = ShadowService(db)
    view = svc.start_shadow(
        actor=_operator(),
        request_id=1,
        body=ShadowStartRequest(reason="fixture", mode="regenerate_fixture"),
    )
    db.commit()
    assert view.result_status == "completed"
    assert view.telemetry.synthetic_fixture_telemetry is True
    assert view.telemetry.provider_calls == 1
    assert view.telemetry.estimated_cost_usd == 0.0
    db.close()
    dispose(engine, root)


def test_regenerate_live_fails_before_providers(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_shadow(monkeypatch)
    engine, root = make_rollout_engine()
    db = make_session(engine)
    svc = ShadowService(db)
    with pytest.raises(ShadowExecutionError, match="regenerate_live_not_approved"):
        svc.start_shadow(
            actor=_operator(),
            request_id=1,
            body=ShadowStartRequest(reason="live", mode="regenerate_live"),
        )
    assert (
        db.execute(text("SELECT COUNT(*) FROM preview_shadow_evaluations")).scalar()
        == 0
    )
    db.close()
    dispose(engine, root)


def test_missing_lineage_failed_terminal_no_serving_mutation(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_shadow(monkeypatch)
    engine, root = make_rollout_engine()
    db = make_session(engine)
    monkeypatch.setattr(
        "app.application.rollout.shadow_service.locate_latest_accepted_lineage",
        lambda _db, _rid: None,
    )
    svc = ShadowService(db)
    view = svc.start_shadow(
        actor=_operator(),
        request_id=1,
        body=ShadowStartRequest(reason="no-lineage", mode="reuse_accepted"),
    )
    db.commit()
    assert view.result_status == "failed"
    assert "accepted_lineage_unavailable" in view.telemetry.rejection_reasons
    assert view.telemetry.pointer_version_before == view.telemetry.pointer_version_after
    db.close()
    dispose(engine, root)


def test_direct_sql_mutation_still_rejected(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_shadow(monkeypatch)
    engine, root = make_rollout_engine()
    db = make_session(engine)
    monkeypatch.setattr(
        "app.application.rollout.shadow_service.locate_latest_accepted_lineage",
        lambda _db, _rid: _lineage(),
    )
    ShadowService(db).start_shadow(
        actor=_operator(),
        request_id=1,
        body=ShadowStartRequest(reason="x", mode="reuse_accepted"),
    )
    db.commit()
    with engine.connect() as conn:
        with pytest.raises(Exception):
            with conn.begin():
                conn.execute(
                    text(
                        "UPDATE preview_shadow_evaluations SET result_status='failed'"
                    )
                )
    db.close()
    dispose(engine, root)
