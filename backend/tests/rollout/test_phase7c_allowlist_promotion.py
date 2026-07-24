"""Phase 7C allowlist promotion, rollback, serving adapter, and gates."""
from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest
from sqlalchemy import text

from app.api.v1.routers import preview_apps
from app.application.preview_app import workspace as workspace_mod
from app.application.rollout.authorization import RolloutAuthorizationError
from app.application.rollout.promotion_service import (
    PromotionService,
    PromotionServiceError,
)
from app.application.rollout.serving_resolve import resolve_dist_for_serving
from app.core import config as config_module
from app.domain.models.rollout import (
    PreviewPromotionDecisionStatusEventRecord,
    PreviewRolloutAuditEventRecord,
    PreviewServingPointerVersionRecord,
)
from app.domain.schemas.promotion import (
    DecisionApprovalBody,
    DecisionApplyBody,
    PromotionRequestBody,
    RollbackRequestBody,
)
from app.domain.schemas.rollout import TrustedRolloutActor
from app.infrastructure.db.phase7c_migrations import (
    PHASE7C_SCHEMA_VERSION,
    migrate_phase7c_promotion,
    phase7c_schema_version,
)
from tests.rollout.helpers import (
    dispose,
    enable_test_only_mode,
    make_phase7c_engine,
    make_rollout_engine,
    make_session,
)


def _enable_7c(monkeypatch, *, allowlist="1", percent="0") -> None:
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_ENABLED", "true")
    monkeypatch.setenv("V2_PHASE7_PROMOTE_ENABLED", "true")
    monkeypatch.setenv("V2_PHASE7_SHADOW_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_PERCENT", percent)
    monkeypatch.setenv("V2_PHASE7_REQUEST_ALLOWLIST", allowlist)
    monkeypatch.setenv("V2_PHASE7_ALLOW_ADMIN_DUAL_ROLE", "false")
    importlib.reload(config_module)


def _actors():
    return (
        TrustedRolloutActor(
            actor_id="op-1",
            roles=("rollout_operator",),
            auth_source="test_fixture",
        ),
        TrustedRolloutActor(
            actor_id="ap-1",
            roles=("rollout_approver",),
            auth_source="test_fixture",
        ),
        TrustedRolloutActor(
            actor_id="ad-1",
            roles=("rollout_admin",),
            auth_source="test_fixture",
        ),
    )


def _seed_candidate_dist(tmp_path: Path, monkeypatch) -> None:
    cand_root = tmp_path / "candidates"
    apps_root = tmp_path / "apps"
    dist = cand_root / "req-1" / "rev-7" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html>v2</html>", encoding="utf-8")
    legacy = apps_root / "1" / "dist"
    legacy.mkdir(parents=True)
    (legacy / "index.html").write_text("<html>v1</html>", encoding="utf-8")
    monkeypatch.setattr(config_module.settings, "PREVIEW_CANDIDATES_DIR", cand_root)
    monkeypatch.setattr(config_module.settings, "PREVIEW_APPS_DIR", apps_root)
    monkeypatch.setattr(workspace_mod.settings, "PREVIEW_CANDIDATES_DIR", cand_root)
    monkeypatch.setattr(workspace_mod.settings, "PREVIEW_APPS_DIR", apps_root)


def _request_approve_apply(db, monkeypatch, tmp_path, *, expected=None):
    _seed_candidate_dist(tmp_path, monkeypatch)
    op, ap, ad = _actors()
    svc = PromotionService(db)
    req = svc.request_promotion(
        actor=op,
        request_id=1,
        body=PromotionRequestBody(
            candidate_revision_id=7,
            effective_tier_summary_id=1,
            expected_pointer_version=expected,
            reason="promote allowlisted",
            ticket_ref="T-1",
            idempotency_key="promo-1",
        ),
    )
    svc.approve_promotion(
        actor=ap,
        decision_id=req.decision_id,
        body=DecisionApprovalBody(reason="approved", ticket_ref="T-1"),
    )
    result = svc.apply_promotion(
        actor=ad,
        decision_id=req.decision_id,
        body=DecisionApplyBody(
            expected_pointer_version=expected,
            reason="apply now",
            ticket_ref="T-1",
            idempotency_key="apply-1",
        ),
    )
    return result, svc


def test_preview_apps_unchanged_option_a_adapter(monkeypatch) -> None:
    source = inspect.getsource(preview_apps)
    assert "promotion_service" not in source
    assert "apply_pointer_swap" not in source
    assert "PromotionService" not in source
    ws_src = inspect.getsource(workspace_mod.get_dist_dir)
    assert "resolve_dist_for_serving" in ws_src
    assert "_legacy_get_dist_dir" in inspect.getsource(workspace_mod)


def test_flags_off_exact_legacy_get_dist_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_PROMOTE_ENABLED", "false")
    importlib.reload(config_module)
    importlib.reload(workspace_mod)
    apps = tmp_path / "apps"
    monkeypatch.setattr(workspace_mod.settings, "PREVIEW_APPS_DIR", apps)
    expected = apps / "9" / "dist"
    assert workspace_mod.get_dist_dir(9) == expected
    assert workspace_mod.get_dist_dir(9) == workspace_mod._legacy_get_dist_dir(9)


def test_migration_preserves_history_and_version() -> None:
    enable_test_only_mode()
    engine, root = make_rollout_engine(phase7c=False)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO preview_promotion_decisions ("
                "request_id, decision_type, decision_status, lineage_sha256, "
                "actor_id, actor_role, reason, policy_revision, eligibility_sha256, "
                "requested_at, decision_sha256) VALUES ("
                "1, 'promote', 'requested', :l, 'a', 'rollout_operator', 'x', 'p', "
                ":e, CURRENT_TIMESTAMP, :d)"
            ),
            {"l": "c" * 64, "e": "d" * 64, "d": "e" * 64},
        )
        before = conn.execute(
            text("SELECT COUNT(*) FROM preview_promotion_decisions")
        ).scalar()
    migrate_phase7c_promotion(engine)
    assert phase7c_schema_version(engine) == PHASE7C_SCHEMA_VERSION
    with engine.begin() as conn:
        after = conn.execute(
            text("SELECT COUNT(*) FROM preview_promotion_decisions")
        ).scalar()
        cols = {
            row[1]
            for row in conn.execute(
                text("PRAGMA table_info(preview_promotion_decisions)")
            )
        }
    assert before == after == 1
    assert "expected_pointer_version" in cols
    dispose(engine, root)


def test_allowlist_promotion_lifecycle(monkeypatch, tmp_path) -> None:
    enable_test_only_mode()
    _enable_7c(monkeypatch)
    engine, root = make_phase7c_engine()
    db = make_session(engine)
    result, _svc = _request_approve_apply(db, monkeypatch, tmp_path, expected=None)
    assert result.pointer.target_kind == "v2_candidate"
    assert result.pointer.pointer_version == 2  # legacy init + promote
    assert result.decision.latest_status == "applied"
    current = (
        db.query(PreviewServingPointerVersionRecord)
        .filter(PreviewServingPointerVersionRecord.is_current.is_(True))
        .all()
    )
    assert len(current) == 1
    hist = (
        db.query(PreviewServingPointerVersionRecord)
        .filter(PreviewServingPointerVersionRecord.request_id == 1)
        .order_by(PreviewServingPointerVersionRecord.pointer_version)
        .all()
    )
    assert hist[0].target_kind == "legacy_v1"
    assert hist[0].pointer_action == "initialize"
    assert hist[1].previous_pointer_version == 1
    db.close()
    dispose(engine, root)


def test_percent_nonzero_rejects_apply(monkeypatch, tmp_path) -> None:
    enable_test_only_mode()
    _enable_7c(monkeypatch, percent="0")
    engine, root = make_phase7c_engine()
    db = make_session(engine)
    _seed_candidate_dist(tmp_path, monkeypatch)
    op, ap, ad = _actors()
    svc = PromotionService(db)
    req = svc.request_promotion(
        actor=op,
        request_id=1,
        body=PromotionRequestBody(
            candidate_revision_id=7,
            effective_tier_summary_id=1,
            reason="r",
            ticket_ref="T",
        ),
    )
    svc.approve_promotion(
        actor=ap,
        decision_id=req.decision_id,
        body=DecisionApprovalBody(reason="ok"),
    )
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_PERCENT", "5")
    importlib.reload(config_module)
    with pytest.raises(PromotionServiceError, match="rollout_percent_nonzero"):
        svc.apply_promotion(
            actor=ad,
            decision_id=req.decision_id,
            body=DecisionApplyBody(expected_pointer_version=None, reason="x"),
        )
    db.close()
    dispose(engine, root)


def test_non_allowlisted_rejects(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7c(monkeypatch, allowlist="99")
    engine, root = make_phase7c_engine()
    db = make_session(engine)
    op, _, _ = _actors()
    with pytest.raises(PromotionServiceError, match="not_allowlisted"):
        PromotionService(db).request_promotion(
            actor=op,
            request_id=1,
            body=PromotionRequestBody(
                candidate_revision_id=7,
                effective_tier_summary_id=1,
                reason="r",
                ticket_ref="T",
            ),
        )
    db.close()
    dispose(engine, root)


def test_rbac_operator_approver_cannot_apply(monkeypatch, tmp_path) -> None:
    enable_test_only_mode()
    _enable_7c(monkeypatch)
    engine, root = make_phase7c_engine()
    db = make_session(engine)
    _seed_candidate_dist(tmp_path, monkeypatch)
    op, ap, _ad = _actors()
    svc = PromotionService(db)
    req = svc.request_promotion(
        actor=op,
        request_id=1,
        body=PromotionRequestBody(
            candidate_revision_id=7,
            effective_tier_summary_id=1,
            reason="r",
            ticket_ref="T",
        ),
    )
    with pytest.raises(RolloutAuthorizationError):
        svc.approve_promotion(
            actor=op,
            decision_id=req.decision_id,
            body=DecisionApprovalBody(reason="no"),
        )
    svc.approve_promotion(
        actor=ap,
        decision_id=req.decision_id,
        body=DecisionApprovalBody(reason="ok"),
    )
    with pytest.raises(RolloutAuthorizationError):
        svc.apply_promotion(
            actor=op,
            decision_id=req.decision_id,
            body=DecisionApplyBody(expected_pointer_version=None, reason="x"),
        )
    with pytest.raises(RolloutAuthorizationError):
        svc.apply_promotion(
            actor=ap,
            decision_id=req.decision_id,
            body=DecisionApplyBody(expected_pointer_version=None, reason="x"),
        )
    db.close()
    dispose(engine, root)


def test_sod_requester_approver_must_differ(monkeypatch, tmp_path) -> None:
    enable_test_only_mode()
    _enable_7c(monkeypatch)
    engine, root = make_phase7c_engine()
    db = make_session(engine)
    _seed_candidate_dist(tmp_path, monkeypatch)
    admin = TrustedRolloutActor(
        actor_id="same",
        roles=("rollout_admin",),
        auth_source="test_fixture",
    )
    svc = PromotionService(db)
    req = svc.request_promotion(
        actor=admin,
        request_id=1,
        body=PromotionRequestBody(
            candidate_revision_id=7,
            effective_tier_summary_id=1,
            reason="r",
            ticket_ref="T",
        ),
    )
    with pytest.raises(PromotionServiceError, match="same_actor_denied"):
        svc.approve_promotion(
            actor=admin,
            decision_id=req.decision_id,
            body=DecisionApprovalBody(reason="self"),
        )
    db.close()
    dispose(engine, root)


def test_emergency_dual_role_requires_flag_reason_ticket(monkeypatch, tmp_path) -> None:
    enable_test_only_mode()
    _enable_7c(monkeypatch)
    monkeypatch.setenv("V2_PHASE7_ALLOW_ADMIN_DUAL_ROLE", "true")
    importlib.reload(config_module)
    engine, root = make_phase7c_engine()
    db = make_session(engine)
    _seed_candidate_dist(tmp_path, monkeypatch)
    admin = TrustedRolloutActor(
        actor_id="same",
        roles=("rollout_admin",),
        auth_source="test_fixture",
    )
    svc = PromotionService(db)
    req = svc.request_promotion(
        actor=admin,
        request_id=1,
        body=PromotionRequestBody(
            candidate_revision_id=7,
            effective_tier_summary_id=1,
            reason="r",
            ticket_ref="T-EM",
        ),
    )
    with pytest.raises(Exception):
        DecisionApprovalBody(reason="", ticket_ref="T-EM")
    monkeypatch.setenv("V2_PHASE7_ALLOW_ADMIN_DUAL_ROLE", "false")
    importlib.reload(config_module)
    with pytest.raises(PromotionServiceError, match="same_actor_denied"):
        svc.approve_promotion(
            actor=admin,
            decision_id=req.decision_id,
            body=DecisionApprovalBody(reason="no flag", ticket_ref="T-EM"),
        )
    monkeypatch.setenv("V2_PHASE7_ALLOW_ADMIN_DUAL_ROLE", "true")
    importlib.reload(config_module)
    approved = svc.approve_promotion(
        actor=admin,
        decision_id=req.decision_id,
        body=DecisionApprovalBody(reason="emergency approve", ticket_ref="T-EM"),
    )
    assert approved.latest_status == "approved"
    db.close()
    dispose(engine, root)


def test_stale_pointer_and_atomic_failure(monkeypatch, tmp_path) -> None:
    enable_test_only_mode()
    _enable_7c(monkeypatch)
    engine, root = make_phase7c_engine()
    db = make_session(engine)
    result, svc = _request_approve_apply(db, monkeypatch, tmp_path, expected=None)
    db.commit()
    op, ap, ad = _actors()
    req2 = svc.request_promotion(
        actor=op,
        request_id=1,
        body=PromotionRequestBody(
            candidate_revision_id=7,
            effective_tier_summary_id=1,
            expected_pointer_version=result.pointer.pointer_version,
            reason="second",
            ticket_ref="T-2",
            idempotency_key="promo-2",
        ),
    )
    svc.approve_promotion(
        actor=ap,
        decision_id=req2.decision_id,
        body=DecisionApprovalBody(reason="ok"),
    )
    with pytest.raises(PromotionServiceError):
        svc.apply_promotion(
            actor=ad,
            decision_id=req2.decision_id,
            body=DecisionApplyBody(expected_pointer_version=999, reason="stale"),
        )
    db.rollback()
    currents = (
        db.query(PreviewServingPointerVersionRecord)
        .filter(
            PreviewServingPointerVersionRecord.request_id == 1,
            PreviewServingPointerVersionRecord.is_current.is_(True),
        )
        .all()
    )
    assert len(currents) == 1
    assert currents[0].pointer_version == result.pointer.pointer_version
    db.close()
    dispose(engine, root)


def test_idempotent_request_approve_apply(monkeypatch, tmp_path) -> None:
    enable_test_only_mode()
    _enable_7c(monkeypatch)
    engine, root = make_phase7c_engine()
    db = make_session(engine)
    _seed_candidate_dist(tmp_path, monkeypatch)
    op, ap, ad = _actors()
    svc = PromotionService(db)
    body = PromotionRequestBody(
        candidate_revision_id=7,
        effective_tier_summary_id=1,
        reason="r",
        ticket_ref="T",
        idempotency_key="idem-req",
    )
    a = svc.request_promotion(actor=op, request_id=1, body=body)
    b = svc.request_promotion(actor=op, request_id=1, body=body)
    assert a.decision_id == b.decision_id
    with pytest.raises(PromotionServiceError, match="idempotency_key_conflict"):
        svc.request_promotion(
            actor=op,
            request_id=1,
            body=PromotionRequestBody(
                candidate_revision_id=7,
                effective_tier_summary_id=1,
                reason="different",
                ticket_ref="T",
                idempotency_key="idem-req",
            ),
        )
    svc.approve_promotion(
        actor=ap,
        decision_id=a.decision_id,
        body=DecisionApprovalBody(reason="ok", idempotency_key="idem-ap"),
    )
    svc.approve_promotion(
        actor=ap,
        decision_id=a.decision_id,
        body=DecisionApprovalBody(reason="ok", idempotency_key="idem-ap"),
    )
    applied = svc.apply_promotion(
        actor=ad,
        decision_id=a.decision_id,
        body=DecisionApplyBody(
            expected_pointer_version=None,
            reason="go",
            idempotency_key="idem-apply",
        ),
    )
    replay = svc.apply_promotion(
        actor=ad,
        decision_id=a.decision_id,
        body=DecisionApplyBody(
            expected_pointer_version=None,
            reason="go",
            idempotency_key="idem-apply",
        ),
    )
    assert applied.pointer.pointer_version == replay.pointer.pointer_version
    versions = (
        db.query(PreviewServingPointerVersionRecord)
        .filter(
            PreviewServingPointerVersionRecord.request_id == 1,
            PreviewServingPointerVersionRecord.pointer_action == "promote",
        )
        .count()
    )
    assert versions == 1
    db.close()
    dispose(engine, root)


def test_rollback_immediate_and_explicit(monkeypatch, tmp_path) -> None:
    enable_test_only_mode()
    _enable_7c(monkeypatch)
    engine, root = make_phase7c_engine()
    db = make_session(engine)
    first, svc = _request_approve_apply(db, monkeypatch, tmp_path, expected=None)
    op, ap, ad = _actors()
    req2 = svc.request_promotion(
        actor=op,
        request_id=1,
        body=PromotionRequestBody(
            candidate_revision_id=7,
            effective_tier_summary_id=1,
            expected_pointer_version=first.pointer.pointer_version,
            reason="tier bump",
            ticket_ref="T-3",
            idempotency_key="promo-3",
        ),
    )
    svc.approve_promotion(
        actor=ap,
        decision_id=req2.decision_id,
        body=DecisionApprovalBody(reason="ok"),
    )
    second = svc.apply_promotion(
        actor=ad,
        decision_id=req2.decision_id,
        body=DecisionApplyBody(
            expected_pointer_version=first.pointer.pointer_version,
            reason="apply2",
        ),
    )
    rb = svc.request_rollback(
        actor=op,
        request_id=1,
        body=RollbackRequestBody(
            expected_pointer_version=second.pointer.pointer_version,
            reason="rollback",
            ticket_ref="RB-1",
        ),
    )
    svc.approve_rollback(
        actor=ap,
        decision_id=rb.decision_id,
        body=DecisionApprovalBody(reason="ok"),
    )
    rolled = svc.apply_rollback(
        actor=ad,
        decision_id=rb.decision_id,
        body=DecisionApplyBody(
            expected_pointer_version=second.pointer.pointer_version,
            reason="apply rb",
        ),
    )
    assert rolled.pointer.pointer_action == "rollback"
    assert rolled.decision.latest_status == "applied"
    rb2 = svc.request_rollback(
        actor=op,
        request_id=1,
        body=RollbackRequestBody(
            expected_pointer_version=rolled.pointer.pointer_version,
            target_pointer_version=1,
            reason="to legacy",
            ticket_ref="RB-2",
            idempotency_key="rb-explicit",
        ),
    )
    svc.approve_rollback(
        actor=ap,
        decision_id=rb2.decision_id,
        body=DecisionApprovalBody(reason="ok"),
    )
    explicit = svc.apply_rollback(
        actor=ad,
        decision_id=rb2.decision_id,
        body=DecisionApplyBody(
            expected_pointer_version=rolled.pointer.pointer_version,
            reason="apply explicit",
        ),
    )
    assert explicit.pointer.target_kind in ("legacy_v1", "rollback")
    db.close()
    dispose(engine, root)


def test_unhealthy_v2_falls_back_to_legacy_pointer(monkeypatch, tmp_path) -> None:
    enable_test_only_mode()
    _enable_7c(monkeypatch)
    engine, root = make_phase7c_engine()
    db = make_session(engine)
    result, _svc = _request_approve_apply(db, monkeypatch, tmp_path, expected=None)
    db.commit()
    cand = config_module.settings.PREVIEW_CANDIDATES_DIR / "req-1" / "rev-7" / "dist"
    for child in cand.iterdir():
        child.unlink()
    cand.rmdir()
    monkeypatch.setattr(
        "app.application.rollout.serving_resolve.SessionLocal",
        lambda: make_session(engine),
    )
    resolved = resolve_dist_for_serving(
        1, legacy_get_dist_dir=workspace_mod._legacy_get_dist_dir
    )
    assert resolved == workspace_mod._legacy_get_dist_dir(1)
    cur = (
        db.query(PreviewServingPointerVersionRecord)
        .filter(PreviewServingPointerVersionRecord.is_current.is_(True))
        .one()
    )
    assert cur.pointer_version == result.pointer.pointer_version
    audits = (
        db.query(PreviewRolloutAuditEventRecord)
        .filter(PreviewRolloutAuditEventRecord.event_type == "serving_fallback")
        .count()
    )
    assert audits >= 1
    db.close()
    dispose(engine, root)


def _pointer_fingerprint(db) -> str:
    rows = (
        db.query(PreviewServingPointerVersionRecord)
        .filter(PreviewServingPointerVersionRecord.request_id == 1)
        .order_by(PreviewServingPointerVersionRecord.pointer_version)
        .all()
    )
    parts = [
        f"{r.pointer_version}:{r.target_kind}:{r.pointer_action}:"
        f"{int(r.is_current)}:{r.pointer_sha256}:{r.candidate_revision_id}:"
        f"{r.legacy_preview_relpath}:{r.previous_pointer_version}"
        for r in rows
    ]
    return "|".join(parts)


def test_audit_failure_does_not_block_fallback(monkeypatch, tmp_path) -> None:
    enable_test_only_mode()
    _enable_7c(monkeypatch)
    engine, root = make_phase7c_engine()
    db = make_session(engine)
    _request_approve_apply(db, monkeypatch, tmp_path, expected=None)
    db.commit()
    before = _pointer_fingerprint(db)
    cand = config_module.settings.PREVIEW_CANDIDATES_DIR / "req-1" / "rev-7" / "dist"
    (cand / "index.html").unlink()
    import app.application.rollout.serving_resolve as sr

    monkeypatch.setattr(sr, "SessionLocal", lambda: make_session(engine))

    def boom(**_k):
        raise RuntimeError("audit repository exception")

    monkeypatch.setattr(sr, "_persist_serving_fallback_audit", boom)
    out = resolve_dist_for_serving(
        1, legacy_get_dist_dir=workspace_mod._legacy_get_dist_dir
    )
    assert out == workspace_mod._legacy_get_dist_dir(1)
    db.expire_all()
    assert _pointer_fingerprint(db) == before
    db.close()
    dispose(engine, root)


def test_audit_timeout_does_not_block_fallback(monkeypatch, tmp_path) -> None:
    import time

    enable_test_only_mode()
    _enable_7c(monkeypatch)
    engine, root = make_phase7c_engine()
    db = make_session(engine)
    _request_approve_apply(db, monkeypatch, tmp_path, expected=None)
    db.commit()
    before = _pointer_fingerprint(db)
    cand = config_module.settings.PREVIEW_CANDIDATES_DIR / "req-1" / "rev-7" / "dist"
    (cand / "index.html").unlink()
    import app.application.rollout.serving_resolve as sr

    monkeypatch.setattr(sr, "SessionLocal", lambda: make_session(engine))
    monkeypatch.setattr(sr, "SERVING_FALLBACK_AUDIT_TIMEOUT_SECONDS", 0.05)

    def slow(**_k):
        time.sleep(1.0)

    monkeypatch.setattr(sr, "_persist_serving_fallback_audit", slow)
    out = resolve_dist_for_serving(
        1, legacy_get_dist_dir=workspace_mod._legacy_get_dist_dir
    )
    assert out == workspace_mod._legacy_get_dist_dir(1)
    db.expire_all()
    assert _pointer_fingerprint(db) == before
    db.close()
    dispose(engine, root)


def test_flags_off_no_phase7_db_or_audit(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_PROMOTE_ENABLED", "false")
    importlib.reload(config_module)
    importlib.reload(workspace_mod)
    apps = tmp_path / "apps"
    monkeypatch.setattr(workspace_mod.settings, "PREVIEW_APPS_DIR", apps)
    import app.application.rollout.serving_resolve as sr

    def forbid_session():
        raise AssertionError("flags-off must not open Phase 7 SessionLocal")

    monkeypatch.setattr(sr, "SessionLocal", forbid_session)
    assert workspace_mod.get_dist_dir(9) == apps / "9" / "dist"


def test_serving_adapter_does_not_import_promotion_executors() -> None:
    import ast

    path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "application"
        / "rollout"
        / "serving_resolve.py"
    )
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
            imports.update(f"{node.module}.{a.name}" for a in node.names)
    joined = " ".join(sorted(imports))
    assert "promotion_service" not in joined
    assert "apply_transaction" not in joined
    assert "PromotionService" not in source
    assert "apply_pointer_swap_transaction" not in source
    preview_src = inspect.getsource(
        __import__("app.api.v1.routers.preview_apps", fromlist=["preview_apps"])
    )
    assert "promotion_service" not in preview_src
    assert "serving_resolve" not in preview_src


def test_no_provider_percent_canary_breaker_actions(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7c(monkeypatch)
    src = Path(__file__).resolve().parents[2] / "app" / "application" / "rollout"
    promo = (src / "promotion_service.py").read_text(encoding="utf-8")
    apply_txn = (src / "apply_transaction.py").read_text(encoding="utf-8")
    serve = (src / "serving_resolve.py").read_text(encoding="utf-8")
    for blob in (promo, apply_txn, serve):
        assert "OpenAI" not in blob
        assert "openrouter" not in blob.lower()
        assert "trip_circuit" not in blob
        assert "consume_canary" not in blob
        assert "auto_rollback" not in blob
        assert "percentage_serve" not in blob


def test_health_precheck_rejects_before_mutation(monkeypatch, tmp_path) -> None:
    enable_test_only_mode()
    _enable_7c(monkeypatch)
    engine, root = make_phase7c_engine()
    db = make_session(engine)
    apps = tmp_path / "apps"
    apps.mkdir()
    cand = tmp_path / "c"
    monkeypatch.setattr(config_module.settings, "PREVIEW_APPS_DIR", apps)
    monkeypatch.setattr(config_module.settings, "PREVIEW_CANDIDATES_DIR", cand)
    monkeypatch.setattr(workspace_mod.settings, "PREVIEW_APPS_DIR", apps)
    monkeypatch.setattr(workspace_mod.settings, "PREVIEW_CANDIDATES_DIR", cand)
    op, ap, ad = _actors()
    svc = PromotionService(db)
    req = svc.request_promotion(
        actor=op,
        request_id=1,
        body=PromotionRequestBody(
            candidate_revision_id=7,
            effective_tier_summary_id=1,
            reason="r",
            ticket_ref="T",
        ),
    )
    svc.approve_promotion(
        actor=ap,
        decision_id=req.decision_id,
        body=DecisionApprovalBody(reason="ok"),
    )
    with pytest.raises(PromotionServiceError):
        svc.apply_promotion(
            actor=ad,
            decision_id=req.decision_id,
            body=DecisionApplyBody(expected_pointer_version=None, reason="x"),
        )
    assert (
        db.query(PreviewServingPointerVersionRecord)
        .filter(PreviewServingPointerVersionRecord.is_current.is_(True))
        .count()
    ) == 0
    assert (
        db.query(PreviewPromotionDecisionStatusEventRecord)
        .filter(PreviewPromotionDecisionStatusEventRecord.status == "applied")
        .count()
    ) == 0
    db.close()
    dispose(engine, root)


def test_immutable_status_history(monkeypatch, tmp_path) -> None:
    enable_test_only_mode()
    _enable_7c(monkeypatch)
    engine, root = make_phase7c_engine()
    db = make_session(engine)
    result, _ = _request_approve_apply(db, monkeypatch, tmp_path, expected=None)
    events = (
        db.query(PreviewPromotionDecisionStatusEventRecord)
        .filter(
            PreviewPromotionDecisionStatusEventRecord.decision_id
            == result.decision.decision_id
        )
        .order_by(PreviewPromotionDecisionStatusEventRecord.id)
        .all()
    )
    assert [e.status for e in events] == ["requested", "approved", "applied"]
    with pytest.raises(Exception):
        events[0].status = "cancelled"
        db.commit()
    db.rollback()
    db.close()
    dispose(engine, root)
