"""Phase 7E ops dashboard and alert persistence focused tests."""
from __future__ import annotations

import importlib
import inspect
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from app.application.rollout.authorization import RolloutAuthorizationError
from app.application.rollout.breaker_metrics import append_metric_sample
from app.application.rollout.breaker_service import BreakerService
from app.application.rollout.metric_snapshot import (
    compute_breaker_metric_snapshot_from_rows,
)
from app.application.rollout.ops_alerts import (
    ALERT_SCAN_CAP,
    OpsAlertError,
    OpsAlertService,
    record_alert,
    scan_and_persist_alerts,
)
from app.application.rollout.ops_service import OpsService, OpsServiceError
from app.core import config as config_module
from app.domain.models.rollout import (
    PreviewBreakerMetricSampleRecord,
    PreviewCircuitBreakerStateRecord,
    PreviewRolloutAlertEventRecord,
    PreviewRolloutAlertStatusEventRecord,
    PreviewRolloutAuditEventRecord,
    PreviewServingPointerVersionRecord,
)
from app.domain.schemas.breaker import GLOBAL_BREAKER_SCOPE_KEY
from app.domain.schemas.ops import AlertAckBody
from app.domain.schemas.rollout import CircuitBreakerPolicyContract, TrustedRolloutActor
from app.infrastructure.db.phase7e_migrations import (
    PHASE7E_SCHEMA_VERSION,
    migrate_phase7e_ops,
    phase7e_schema_version,
)
from tests.rollout.helpers import (
    dispose,
    enable_test_only_mode,
    make_phase7e_engine,
    make_session,
)


def _enable_7e(
    monkeypatch,
    *,
    dashboard=True,
    alerts=True,
    allowlist="1",
    percent="0",
) -> None:
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_ENABLED", "true")
    monkeypatch.setenv("V2_PHASE7_PROMOTE_ENABLED", "true")
    monkeypatch.setenv("V2_PHASE7_SHADOW_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_CIRCUIT_BREAKER_ENABLED", "true")
    monkeypatch.setenv("V2_PHASE7_AUTO_ROLLBACK_ENABLED", "false")
    monkeypatch.setenv(
        "V2_PHASE7_OPS_DASHBOARD_ENABLED", "true" if dashboard else "false"
    )
    monkeypatch.setenv("V2_PHASE7_OPS_ALERTS_ENABLED", "true" if alerts else "false")
    monkeypatch.setenv("V2_PHASE7_OPS_ALERT_LOOKBACK_SECONDS", "3600")
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_PERCENT", percent)
    monkeypatch.setenv("V2_PHASE7_REQUEST_ALLOWLIST", allowlist)
    importlib.reload(config_module)


def _admin() -> TrustedRolloutActor:
    return TrustedRolloutActor(
        actor_id="ad-1", roles=("rollout_admin",), auth_source="test_fixture"
    )


def _viewer() -> TrustedRolloutActor:
    return TrustedRolloutActor(
        actor_id="v-1", roles=("rollout_viewer",), auth_source="test_fixture"
    )


def _operator() -> TrustedRolloutActor:
    return TrustedRolloutActor(
        actor_id="op-1", roles=("rollout_operator",), auth_source="test_fixture"
    )


def _patch_policy(monkeypatch, **kwargs) -> None:
    monkeypatch.setattr(
        "app.application.rollout.breaker_service.DEFAULT_BREAKER_POLICY",
        CircuitBreakerPolicyContract(min_samples=5, scope="global", **kwargs),
    )


def test_migration_phase7e() -> None:
    enable_test_only_mode()
    engine, root = make_phase7e_engine()
    try:
        assert phase7e_schema_version(engine) == PHASE7E_SCHEMA_VERSION
        with engine.connect() as conn:
            names = set(conn.execute(text("SELECT name FROM sqlite_master")).scalars())
            assert "preview_rollout_alert_events" in names
            assert "preview_rollout_alert_status_events" in names
        migrate_phase7e_ops(engine)
    finally:
        dispose(engine, root)


def test_flags_off_disabled_payloads_no_alert_writes(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7e(monkeypatch, dashboard=False, alerts=False)
    engine, root = make_phase7e_engine()
    db = make_session(engine)
    try:
        ov = OpsService(db).overview(actor=_admin())
        assert ov.disabled is True
        bud = OpsService(db).breaker_budget(actor=_admin())
        assert bud.disabled is True
        assert scan_and_persist_alerts(db) == 0
        assert db.query(PreviewRolloutAlertEventRecord).count() == 0
    finally:
        db.close()
        dispose(engine, root)


def test_alerts_off_allows_dashboard_no_inserts(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7e(monkeypatch, dashboard=True, alerts=False)
    engine, root = make_phase7e_engine()
    db = make_session(engine)
    try:
        ov = OpsService(db).overview(actor=_admin())
        assert ov.disabled is False
        assert scan_and_persist_alerts(db) == 0
        assert db.query(PreviewRolloutAlertEventRecord).count() == 0
    finally:
        db.close()
        dispose(engine, root)


def test_invalid_config_fails_closed(monkeypatch) -> None:
    enable_test_only_mode()
    monkeypatch.setenv("V2_PHASE7_OPS_ALERT_LOOKBACK_SECONDS", "nope")
    monkeypatch.setenv("V2_PHASE7_OPS_DASHBOARD_ENABLED", "true")
    monkeypatch.setenv("V2_PHASE7_OPS_ALERTS_ENABLED", "true")
    importlib.reload(config_module)
    assert config_module.settings.V2_PHASE7_CONFIG_VALID is False
    assert config_module.settings.V2_PHASE7_OPS_DASHBOARD_ENABLED is False
    assert config_module.settings.V2_PHASE7_OPS_ALERTS_ENABLED is False


def test_overview_hash_stable(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7e(monkeypatch, alerts=False)
    engine, root = make_phase7e_engine()
    db = make_session(engine)
    try:
        a = OpsService(db).overview(actor=_admin())
        b = OpsService(db).overview(actor=_admin())
        assert a.overview_sha256 == b.overview_sha256
        assert a.disabled is False
        assert a.flags.rollout_percent == 0
    finally:
        db.close()
        dispose(engine, root)


def test_budget_matches_phase7d_math(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7e(monkeypatch, alerts=False)
    _patch_policy(monkeypatch)
    engine, root = make_phase7e_engine()
    db = make_session(engine)
    try:
        rev = config_module.settings.V2_PHASE7_POLICY_REVISION
        for i in range(4):
            append_metric_sample(
                db,
                metric_class="promotion_write_success",
                outcome="success",
                policy_revision=rev,
                source_event_hash=f"ok-{i}".ljust(64, "0")[:64],
                source_event_id=f"ok:{i}",
            )
        append_metric_sample(
            db,
            metric_class="promotion_write_failure",
            outcome="failure",
            policy_revision=rev,
            source_event_hash="fail-0".ljust(64, "0")[:64],
            source_event_id="fail:0",
        )
        svc = BreakerService(db)
        policy = CircuitBreakerPolicyContract(min_samples=5, scope="global")
        d7 = svc._compute_snapshot(policy)
        samples = db.query(PreviewBreakerMetricSampleRecord).order_by(
            PreviewBreakerMetricSampleRecord.id.asc()
        ).all()
        shared = compute_breaker_metric_snapshot_from_rows(policy, samples)
        assert d7.snapshot_sha256 == shared.snapshot_sha256
        budget = OpsService(db).breaker_budget(actor=_admin())
        assert budget.metric_snapshot is not None
        assert budget.metric_snapshot.snapshot_sha256 == d7.snapshot_sha256
        again = OpsService(db).breaker_budget(actor=_admin())
        assert budget.budget_sha256 == again.budget_sha256
    finally:
        db.close()
        dispose(engine, root)


def test_allowlist_only_drilldown_no_leak(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7e(monkeypatch, allowlist="1", alerts=False)
    engine, root = make_phase7e_engine()
    db = make_session(engine)
    try:
        db.add(
            PreviewServingPointerVersionRecord(
                request_id=1,
                pointer_version=1,
                target_kind="legacy_v1",
                candidate_revision_id=None,
                legacy_preview_relpath="1/dist",
                effective_tier=None,
                summary_sha256=None,
                candidate_manifest_sha256=None,
                previous_pointer_version=None,
                pointer_action="initialize",
                decision_id=None,
                actor_id="ad-1",
                policy_revision=config_module.settings.V2_PHASE7_POLICY_REVISION,
                created_at=datetime.utcnow(),
                is_current=True,
                pointer_sha256="a" * 64,
            )
        )
        db.flush()
        ok = OpsService(db).request_drilldown(actor=_admin(), request_id=1)
        assert ok.request_id == 1
        assert ok.current_pointer is not None
        with pytest.raises(OpsServiceError, match="not_found"):
            OpsService(db).request_drilldown(actor=_admin(), request_id=42)
    finally:
        db.close()
        dispose(engine, root)


def test_alert_generation_classes_and_dedupe(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7e(monkeypatch)
    _patch_policy(monkeypatch)
    engine, root = make_phase7e_engine()
    db = make_session(engine)
    try:
        BreakerService(db).manual_open(
            actor=_admin(), reason="trip", ticket_ref="T", run_auto_rollback=False
        )
        n1 = scan_and_persist_alerts(db)
        assert n1 >= 1
        classes = {
            a.alert_class for a in db.query(PreviewRolloutAlertEventRecord).all()
        }
        assert "breaker_opened" in classes
        n2 = scan_and_persist_alerts(db)
        assert n2 == 0  # dedupe
        assert db.query(PreviewRolloutAlertEventRecord).count() == len(classes)

        # Budget burn
        rev = config_module.settings.V2_PHASE7_POLICY_REVISION
        for i in range(4):
            append_metric_sample(
                db,
                metric_class="serving_health_success",
                outcome="success",
                policy_revision=rev,
                source_event_hash=f"hs-{i}".ljust(64, "0")[:64],
                source_event_id=f"hs:{i}",
            )
        append_metric_sample(
            db,
            metric_class="serving_health_failure",
            outcome="failure",
            policy_revision=rev,
            source_event_hash="hf-0".ljust(64, "0")[:64],
            source_event_id="hf:0",
        )
        scan_and_persist_alerts(db)
        classes = {
            a.alert_class for a in db.query(PreviewRolloutAlertEventRecord).all()
        }
        assert "serving_health_budget_burn" in classes

        db.add(
            PreviewRolloutAuditEventRecord(
                request_id=1,
                event_type="history_mutation_denied",
                actor_id="system",
                actor_role="rollout_admin",
                policy_revision=rev,
                reason="append_only",
                metadata_json="{}",
                metadata_sha256="b" * 64,
                created_at=datetime.utcnow(),
                event_sha256="c" * 64,
            )
        )
        db.flush()
        scan_and_persist_alerts(db)
        classes = {
            a.alert_class for a in db.query(PreviewRolloutAlertEventRecord).all()
        }
        assert "history_mutation_denied" in classes
    finally:
        db.close()
        dispose(engine, root)


def test_alert_storm_cap(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7e(monkeypatch)
    engine, root = make_phase7e_engine()
    db = make_session(engine)
    try:
        # Seed many unique breaker state opens via direct rows
        policy = BreakerService(db).ensure_default_policy(actor_id="ad-1")
        for i in range(ALERT_SCAN_CAP + 5):
            db.add(
                PreviewCircuitBreakerStateRecord(
                    policy_id=policy.id,
                    scope_key=GLOBAL_BREAKER_SCOPE_KEY,
                    state="open",
                    metric_class="operator_rejection",
                    reason=f"storm-{i}",
                    created_at=datetime.utcnow() - timedelta(seconds=i),
                    state_sha256=f"{i:064d}"[:64],
                )
            )
        db.flush()
        scan_and_persist_alerts(db)
        opened = (
            db.query(PreviewRolloutAlertEventRecord)
            .filter(PreviewRolloutAlertEventRecord.alert_class == "breaker_opened")
            .count()
        )
        assert opened <= ALERT_SCAN_CAP
        storm = (
            db.query(PreviewRolloutAlertEventRecord)
            .filter(
                PreviewRolloutAlertEventRecord.alert_class == "alert_storm_suppressed"
            )
            .count()
        )
        assert storm >= 1
    finally:
        db.close()
        dispose(engine, root)


def test_ack_admin_only_idempotent_conflict(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7e(monkeypatch)
    engine, root = make_phase7e_engine()
    db = make_session(engine)
    try:
        row = record_alert(
            db,
            alert_class="breaker_opened",
            severity="high",
            scope_key=GLOBAL_BREAKER_SCOPE_KEY,
            source_event_type="test",
            source_event_id="ack-1",
            source_sha256="d" * 64,
            policy_revision=config_module.settings.V2_PHASE7_POLICY_REVISION,
            payload={"k": 1},
        )
        assert row is not None
        svc = OpsAlertService(db)
        with pytest.raises(RolloutAuthorizationError):
            svc.acknowledge(
                actor=_viewer(),
                alert_id=row.id,
                body=AlertAckBody(reason="nope"),
            )
        with pytest.raises(RolloutAuthorizationError):
            svc.acknowledge(
                actor=_operator(),
                alert_id=row.id,
                body=AlertAckBody(reason="nope"),
            )
        v1 = svc.acknowledge(
            actor=_admin(),
            alert_id=row.id,
            body=AlertAckBody(reason="acked", ticket_ref="T-1"),
        )
        assert v1.latest_status == "acknowledged"
        v2 = svc.acknowledge(
            actor=_admin(),
            alert_id=row.id,
            body=AlertAckBody(reason="acked", ticket_ref="T-1"),
        )
        assert v2.latest_status == "acknowledged"
        assert len(v2.status_events) == len(v1.status_events)
        with pytest.raises(OpsAlertError, match="ack_payload_conflict"):
            svc.acknowledge(
                actor=_admin(),
                alert_id=row.id,
                body=AlertAckBody(reason="different", ticket_ref="T-1"),
            )
        # Append-only: alert row unchanged; status events only grow on first ack
        assert db.query(PreviewRolloutAlertStatusEventRecord).filter(
            PreviewRolloutAlertStatusEventRecord.alert_id == row.id
        ).count() >= 2
        dirty = db.query(PreviewRolloutAlertEventRecord).filter(
            PreviewRolloutAlertEventRecord.id == row.id
        ).one()
        with pytest.raises(ValueError, match="append-only"):
            dirty.severity = "info"
            db.flush()
    finally:
        db.rollback()
        db.close()
        dispose(engine, root)


def test_runbook_deep_links_no_evaluate_wrapper(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7e(monkeypatch, alerts=False)
    engine, root = make_phase7e_engine()
    db = make_session(engine)
    try:
        BreakerService(db).manual_open(
            actor=_admin(), reason="o", ticket_ref="T", run_auto_rollback=False
        )
        rb = OpsService(db).runbook(actor=_admin())
        paths = {a.path for a in rb.actions}
        assert "/api/admin/rollout/breaker/evaluate" in paths
        assert all("/ops/breaker/evaluate" not in p for p in paths)
        again = OpsService(db).runbook(actor=_admin())
        assert rb.runbook_sha256 == again.runbook_sha256
    finally:
        db.close()
        dispose(engine, root)


def test_boundary_no_pointer_swap_no_providers(monkeypatch) -> None:
    for mod in (
        "app.application.rollout.ops_service",
        "app.application.rollout.ops_alerts",
    ):
        src = inspect.getsource(importlib.import_module(mod)).lower()
        assert "apply_pointer_swap_transaction" not in src
        assert "manual_open" not in src
        assert "manual_close" not in src
        assert "openai" not in src
        assert "playwright" not in src
        assert "consume_canary" not in src
        # Phase 7F may import percent_serve for read-only canary-gate alerts.
        assert "apply_pointer_swap" not in src
        # May mention AutoRollbackService only as read of claims table — ensure
        # no write service import
        assert "from app.application.rollout.auto_rollback" not in src
    sr = inspect.getsource(
        importlib.import_module("app.application.rollout.serving_resolve")
    )
    assert "ops_service" not in sr
    assert "ops_alerts" not in sr
    apps = Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "routers" / "preview_apps.py"
    # Unchanged presence of get_dist_dir only — hash vs git checked separately
    text = apps.read_text(encoding="utf-8")
    assert "OpsService" not in text
    assert "ops_alerts" not in text


def test_phase7_config_invalid_alert(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7e(monkeypatch)
    engine, root = make_phase7e_engine()
    db = make_session(engine)
    try:
        monkeypatch.setattr(config_module.settings, "V2_PHASE7_CONFIG_VALID", False)
        monkeypatch.setattr(config_module.settings, "V2_PHASE7_OPS_ALERTS_ENABLED", True)
        n = scan_and_persist_alerts(db)
        assert n >= 1
        assert (
            db.query(PreviewRolloutAlertEventRecord)
            .filter(
                PreviewRolloutAlertEventRecord.alert_class == "phase7_config_invalid"
            )
            .count()
            == 1
        )
    finally:
        db.close()
        dispose(engine, root)


def test_known_preexisting_failures_documented() -> None:
    doc = Path(__file__).resolve().parents[3] / "docs" / "architecture" / (
        "PREVIEW_GENERATOR_V2_PHASE7E_DASHBOARDS_ALERTS.md"
    )
    text = doc.read_text(encoding="utf-8")
    assert "test_pottery_picks_craft_studio_pack" in text
    assert "test_enriched_industry_packs_carry_seed_items" in text
    assert "test_production_callsites_render_with_strict_undefined" in text
