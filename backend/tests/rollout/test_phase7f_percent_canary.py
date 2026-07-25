"""Phase 7F percent serving + live canary lifecycle tests (provider doubles only)."""
from __future__ import annotations

import hashlib
import importlib
import inspect
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from app.application.rollout.authorization import trusted_actor_from_admin
from app.application.rollout.canary_auth_cache import invalidate_canary_auth_cache
from app.application.rollout.canary_service import (
    BudgetTracker,
    CanaryService,
    CanaryServiceError,
    FixtureCanaryProvider,
)
from app.application.rollout.percent_serve import (
    build_targeting_diagnostic,
    evaluate_serve_eligibility,
)
from app.application.rollout.serving_resolve import SERVING_FALLBACK_AUDIT_TIMEOUT_SECONDS
from app.application.rollout.targeting import FROZEN_STICKY_VECTORS, compute_sticky_bucket
from app.core import config as config_module
from app.domain.models.rollout import PreviewServingPointerVersionRecord
from app.domain.schemas.canary import (
    CanaryApprovalBody,
    CanaryExecuteBody,
    CanaryRequestBody,
    CanaryReviewBody,
)
from app.domain.schemas.rollout import TrustedRolloutActor
from app.infrastructure.db.phase7f_migrations import (
    PHASE7F_SCHEMA_VERSION,
    migrate_phase7f_percent_canary,
    phase7f_schema_version,
)
from tests.rollout.helpers import (
    dispose,
    enable_test_only_mode,
    import_rollout_models,
    make_phase7f_engine,
    make_session,
)


def _admin(actor_id: str) -> TrustedRolloutActor:
    return trusted_actor_from_admin(actor_id=actor_id, is_admin=True)


def _enable_7f(
    monkeypatch,
    *,
    percent="0",
    percent_serve=False,
    canary=True,
    allowlist="1",
    requires_canary=True,
    breaker=False,
) -> None:
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_ENABLED", "true")
    monkeypatch.setenv("V2_PHASE7_PROMOTE_ENABLED", "true")
    monkeypatch.setenv("V2_PHASE7_SHADOW_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_CIRCUIT_BREAKER_ENABLED", "true" if breaker else "false")
    monkeypatch.setenv("V2_PHASE7_AUTO_ROLLBACK_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_OPS_DASHBOARD_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_OPS_ALERTS_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_PERCENT", percent)
    monkeypatch.setenv("V2_PHASE7_REQUEST_ALLOWLIST", allowlist)
    monkeypatch.setenv("V2_PHASE7_POLICY_REVISION", "2026-07-25.1")
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_SALT", "2026-07-25.1")
    monkeypatch.setenv(
        "V2_PHASE7_PERCENT_SERVE_ENABLED", "true" if percent_serve else "false"
    )
    monkeypatch.setenv(
        "V2_PHASE7_PERCENT_REQUIRES_CANARY", "true" if requires_canary else "false"
    )
    monkeypatch.setenv(
        "V2_PHASE7_LIVE_CANARY_ENABLED", "true" if canary else "false"
    )
    monkeypatch.setenv("V2_PHASE7_LIVE_CANARY_PROVIDERS_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_CANARY_SIMULATION_ENABLED", "false")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("V2_PHASE7_CANARY_MAX_CALLS", "12")
    monkeypatch.setenv("V2_PHASE7_CANARY_MAX_INPUT_TOKENS", "1000")
    monkeypatch.setenv("V2_PHASE7_CANARY_MAX_OUTPUT_TOKENS", "1000")
    monkeypatch.setenv("V2_PHASE7_CANARY_MAX_COST_USD", "1.0")
    monkeypatch.setenv("V2_PHASE7_CANARY_MAX_WALL_SECONDS", "120")
    monkeypatch.setenv("V2_PHASE7_CANARY_MAX_RETRIES", "1")
    monkeypatch.setenv("V2_PHASE7_CANARY_PER_CALL_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("V2_PHASE7_CANARY_APPROVAL_TTL_SECONDS", "3600")
    importlib.reload(config_module)
    invalidate_canary_auth_cache()


def _seed_pointer(db, request_id: int = 1, version: int = 2) -> None:
    db.add(
        PreviewServingPointerVersionRecord(
            request_id=request_id,
            pointer_version=version,
            target_kind="v2_candidate",
            candidate_revision_id=7,
            legacy_preview_relpath=None,
            effective_tier=2,
            summary_sha256="a" * 64,
            candidate_manifest_sha256="b" * 64,
            previous_pointer_version=None,
            pointer_action="promote",
            decision_id=None,
            actor_id="admin:seed",
            policy_revision=config_module.settings.V2_PHASE7_POLICY_REVISION,
            created_at=datetime.utcnow(),
            is_current=True,
            pointer_sha256=hashlib.sha256(
                f"ptr:{request_id}:{version}".encode()
            ).hexdigest(),
        )
    )
    db.commit()


def _run_canary_lifecycle(db, *, idem_suffix: str = "1"):
    """Fixture-injected lifecycle — never percent-authorizing."""
    svc = CanaryService(db, provider_factory=FixtureCanaryProvider)
    req = svc.request_canary(
        _admin("admin:requester"),
        1,
        CanaryRequestBody(
            reason="canary test",
            ticket_ref="T-7F-1",
            max_calls=2,
            max_input_tokens=500,
            max_output_tokens=500,
            max_cost_usd=0.5,
            idempotency_key=f"canary-req-{idem_suffix}",
        ),
    )
    svc.approve_canary(
        _admin("admin:approver"),
        req.approval_id,
        CanaryApprovalBody(reason="approve", ticket_ref="T-7F-1"),
    )
    execution = svc.execute_canary(
        _admin("admin:executor"),
        req.approval_id,
        CanaryExecuteBody(
            reason="execute",
            ticket_ref="T-7F-1",
            idempotency_key=f"canary-exec-{idem_suffix}",
        ),
    )
    reviewed = svc.review_execution(
        _admin("admin:reviewer"),
        execution.execution_id,
        CanaryReviewBody(accept=True, reason="looks good", ticket_ref="T-7F-1"),
    )
    return req, execution, reviewed, svc


def _run_live_canary_lifecycle(db, monkeypatch, *, idem_suffix: str = "live"):
    """Live construction path with a provider double (not FixtureCanaryProvider)."""

    class LiveProviderDouble:
        def complete(self, *, prompt: str, max_tokens: int) -> dict:
            _ = prompt
            return {
                "input_tokens": 32,
                "output_tokens": min(64, max_tokens),
                "cost_usd": 0.001,
                "text": "live-double-ok",
            }

    monkeypatch.setenv("V2_PHASE7_LIVE_CANARY_ENABLED", "true")
    monkeypatch.setenv("V2_PHASE7_LIVE_CANARY_PROVIDERS_ENABLED", "true")
    monkeypatch.setenv("V2_PHASE7_CANARY_SIMULATION_ENABLED", "false")
    importlib.reload(config_module)
    assert config_module.settings.V2_PHASE7_LIVE_CANARY_PROVIDERS_ENABLED is True
    monkeypatch.setattr(
        "app.infrastructure.ai_providers.factory.get_ai_provider",
        lambda: LiveProviderDouble(),
    )
    svc = CanaryService(db)
    req = svc.request_canary(
        _admin("admin:requester"),
        1,
        CanaryRequestBody(
            reason="live canary",
            ticket_ref="T-7F-LIVE",
            idempotency_key=f"canary-live-req-{idem_suffix}",
        ),
    )
    svc.approve_canary(
        _admin("admin:approver"),
        req.approval_id,
        CanaryApprovalBody(reason="approve", ticket_ref="T-7F-LIVE"),
    )
    execution = svc.execute_canary(
        _admin("admin:executor"),
        req.approval_id,
        CanaryExecuteBody(
            reason="execute",
            ticket_ref="T-7F-LIVE",
            idempotency_key=f"canary-live-exec-{idem_suffix}",
        ),
    )
    reviewed = svc.review_execution(
        _admin("admin:reviewer"),
        execution.execution_id,
        CanaryReviewBody(accept=True, reason="live ok", ticket_ref="T-7F-LIVE"),
    )
    return req, execution, reviewed, svc


def test_migration_phase7f_version() -> None:
    enable_test_only_mode()
    engine, root = make_phase7f_engine()
    assert phase7f_schema_version(engine) == PHASE7F_SCHEMA_VERSION
    migrate_phase7f_percent_canary(engine)  # idempotent
    assert phase7f_schema_version(engine) == PHASE7F_SCHEMA_VERSION
    dispose(engine, root)


def test_preview_apps_unchanged() -> None:
    from app.api.v1.routers import preview_apps

    source = inspect.getsource(preview_apps)
    assert "canary_service" not in source
    assert "percent_serve" not in source
    assert "PromotionService" not in source
    assert "get_dist_dir" in source


def test_flags_off_legacy_identical(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("V2_PHASE7_ROLLOUT_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_PROMOTE_ENABLED", "false")
    monkeypatch.setenv("V2_PHASE7_PERCENT_SERVE_ENABLED", "false")
    importlib.reload(config_module)
    from app.application.preview_app import workspace as workspace_mod

    importlib.reload(workspace_mod)
    apps = tmp_path / "apps"
    monkeypatch.setattr(workspace_mod.settings, "PREVIEW_APPS_DIR", apps)
    assert workspace_mod.get_dist_dir(9) == workspace_mod._legacy_get_dist_dir(9)


def test_sticky_vectors_identical_to_7a() -> None:
    for salt, request_id, first8, bucket in FROZEN_STICKY_VECTORS:
        result = compute_sticky_bucket(
            salt=salt, request_id=request_id, rollout_percent=100
        )
        assert result.digest_first8_hex == first8
        assert result.bucket == bucket


def test_cohort_monotonicity() -> None:
    salt = "2026-07-25.1"
    for request_id in ("1", "42", "100", "999", "23104"):
        low = compute_sticky_bucket(salt=salt, request_id=request_id, rollout_percent=25)
        high = compute_sticky_bucket(salt=salt, request_id=request_id, rollout_percent=50)
        if low.percent_eligible:
            assert high.percent_eligible


def test_percent_zero_no_percentage_serving(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch, percent="0", percent_serve=True, requires_canary=False)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()
    _seed_pointer(db, request_id=42)
    elig = evaluate_serve_eligibility(db, 42)
    assert elig.mode == "legacy"
    assert elig.reason == "percent_serve_disabled"
    dispose(engine, root)


def test_percent_without_reviewed_canary_fails_closed(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch, percent="100", percent_serve=True, requires_canary=True)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()
    _seed_pointer(db, request_id=42)
    elig = evaluate_serve_eligibility(db, 42)
    assert elig.mode == "legacy"
    assert elig.reason == "percent_blocked_missing_canary"
    dispose(engine, root)


def test_allowlist_path_at_percent_zero(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch, percent="0", percent_serve=False)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()
    _seed_pointer(db, request_id=1)
    elig = evaluate_serve_eligibility(db, 1)
    assert elig.mode == "pointer"
    assert elig.reason == "allowlisted"
    dispose(engine, root)


def test_canary_lifecycle_sod_and_no_pointer_mutation(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch, canary=True)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()
    _seed_pointer(db, request_id=1, version=3)
    before = (
        db.query(PreviewServingPointerVersionRecord)
        .filter(PreviewServingPointerVersionRecord.is_current.is_(True))
        .one()
        .pointer_version
    )
    _req, execution, reviewed, svc = _run_canary_lifecycle(db)
    assert execution.result_status == "completed"
    assert execution.pointer_version_before == before
    assert execution.pointer_version_after == before
    assert execution.no_serving_mutation is True
    assert reviewed.reviewed_accepted is False
    assert reviewed.reviewed_fixture_only is True
    assert reviewed.provenance.execution_mode == "fixture"
    assert reviewed.provenance.percent_authorization_eligible is False
    assert svc.provider_was_constructed() is True
    after = (
        db.query(PreviewServingPointerVersionRecord)
        .filter(PreviewServingPointerVersionRecord.is_current.is_(True))
        .one()
        .pointer_version
    )
    assert after == before
    dispose(engine, root)


def test_sod_rejects_dual_role(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()
    svc = CanaryService(db, provider_factory=FixtureCanaryProvider)
    req = svc.request_canary(
        _admin("admin:same"),
        1,
        CanaryRequestBody(reason="r", ticket_ref="T1"),
    )
    with pytest.raises(CanaryServiceError) as exc:
        svc.approve_canary(
            _admin("admin:same"),
            req.approval_id,
            CanaryApprovalBody(reason="a", ticket_ref="T1"),
        )
    assert exc.value.reason == "sod_requester_approver"
    dispose(engine, root)


def test_expired_approval_rejected_before_provider(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()

    svc = CanaryService(db, provider_factory=FixtureCanaryProvider)
    req = svc.request_canary(
        _admin("admin:requester"),
        1,
        CanaryRequestBody(reason="r", ticket_ref="T1"),
    )
    svc.approve_canary(
        _admin("admin:approver"),
        req.approval_id,
        CanaryApprovalBody(reason="a", ticket_ref="T1"),
    )
    import app.application.rollout.canary_service as canary_mod

    real_dt = canary_mod.datetime

    class _FutureClock:
        @staticmethod
        def utcnow():
            return real_dt.utcnow() + timedelta(hours=3)

        @staticmethod
        def fromisoformat(value: str):
            return real_dt.fromisoformat(value)

    monkeypatch.setattr(canary_mod, "datetime", _FutureClock)
    svc2 = CanaryService(db, provider_factory=FixtureCanaryProvider)
    with pytest.raises(CanaryServiceError) as exc:
        svc2.execute_canary(
            _admin("admin:executor"),
            req.approval_id,
            CanaryExecuteBody(
                reason="x", ticket_ref="T1", idempotency_key="exp-1"
            ),
        )
    assert exc.value.reason == "approval_expired"
    assert svc2.provider_was_constructed() is False
    dispose(engine, root)


def test_single_use_and_idempotent_execute(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()
    svc = CanaryService(db, provider_factory=FixtureCanaryProvider)
    req = svc.request_canary(
        _admin("admin:requester"),
        1,
        CanaryRequestBody(reason="r", ticket_ref="T1"),
    )
    svc.approve_canary(
        _admin("admin:approver"),
        req.approval_id,
        CanaryApprovalBody(reason="a", ticket_ref="T1"),
    )
    first = svc.execute_canary(
        _admin("admin:executor"),
        req.approval_id,
        CanaryExecuteBody(reason="e", ticket_ref="T1", idempotency_key="idem-x"),
    )
    replay = svc.execute_canary(
        _admin("admin:executor"),
        req.approval_id,
        CanaryExecuteBody(reason="e", ticket_ref="T1", idempotency_key="idem-x"),
    )
    assert replay.execution_id == first.execution_id
    with pytest.raises(CanaryServiceError) as exc:
        svc.execute_canary(
            _admin("admin:executor"),
            req.approval_id,
            CanaryExecuteBody(reason="e2", ticket_ref="T1", idempotency_key="idem-y"),
        )
    assert exc.value.reason == "approval_already_used"
    dispose(engine, root)


def test_budget_overrun_stops_calls(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()

    class CountingProvider:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, *, prompt: str, max_tokens: int) -> dict:
            self.calls += 1
            return {
                "input_tokens": 100,
                "output_tokens": 100,
                "cost_usd": 0.01,
                "text": "x",
            }

    class HungryRunner:
        def run(self, *, provider, budget: BudgetTracker, request_id, approval):
            budget.check_before_call()
            r1 = provider.complete(prompt="a", max_tokens=10)
            budget.record_call(
                input_tokens=r1["input_tokens"],
                output_tokens=r1["output_tokens"],
                cost_usd=r1["cost_usd"],
            )
            budget.check_before_call()
            r2 = provider.complete(prompt="b", max_tokens=10)
            budget.record_call(
                input_tokens=r2["input_tokens"],
                output_tokens=r2["output_tokens"],
                cost_usd=r2["cost_usd"],
            )
            # Third call should trip max_calls=2
            budget.check_before_call()
            return type("R", (), {
                "candidate_revision_id": 7,
                "effective_tier": 2,
                "phase4_status": "candidate_runtime_validated",
                "phase5_status": "candidate_visual_accepted",
                "comparison_artifact_sha256": "c" * 64,
                "status": "completed",
                "failure_reason": None,
            })()

    provider = CountingProvider()
    svc = CanaryService(
        db, provider_factory=lambda: provider, runner=HungryRunner()
    )
    req = svc.request_canary(
        _admin("admin:requester"),
        1,
        CanaryRequestBody(
            reason="r",
            ticket_ref="T1",
            max_calls=2,
            max_input_tokens=1000,
            max_output_tokens=1000,
            max_cost_usd=1.0,
        ),
    )
    svc.approve_canary(
        _admin("admin:approver"),
        req.approval_id,
        CanaryApprovalBody(reason="a", ticket_ref="T1"),
    )
    execution = svc.execute_canary(
        _admin("admin:executor"),
        req.approval_id,
        CanaryExecuteBody(reason="e", ticket_ref="T1", idempotency_key="bud-1"),
    )
    assert execution.result_status == "aborted"
    assert execution.failure_reason == "budget_exceeded_calls"
    assert provider.calls == 2
    dispose(engine, root)


def test_percent_serve_with_reviewed_canary(monkeypatch, tmp_path) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch, percent="100", percent_serve=True, canary=True)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()
    cand = tmp_path / "candidates" / "req-1" / "rev-7" / "dist"
    cand.mkdir(parents=True)
    (cand / "index.html").write_text("<html/>", encoding="utf-8")
    monkeypatch.setattr(
        config_module.settings, "PREVIEW_CANDIDATES_DIR", tmp_path / "candidates"
    )
    # request 42 is not allowlisted; bucket under 100% with salt
    _seed_pointer(db, request_id=42)
    _req, execution, reviewed, _svc = _run_live_canary_lifecycle(db, monkeypatch)
    assert reviewed.reviewed_accepted is True
    assert execution.provenance.execution_mode == "live"
    assert execution.provenance.percent_authorization_eligible is True
    invalidate_canary_auth_cache()
    elig = evaluate_serve_eligibility(db, 42)
    assert elig.mode == "pointer"
    assert elig.reason == "percent_eligible"
    dispose(engine, root)


def test_stale_policy_canary_fails_closed(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch, percent="100", percent_serve=True)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()
    _seed_pointer(db, request_id=42)
    _run_live_canary_lifecycle(db, monkeypatch)
    monkeypatch.setenv("V2_PHASE7_POLICY_REVISION", "2026-07-25.2")
    importlib.reload(config_module)
    invalidate_canary_auth_cache()
    elig = evaluate_serve_eligibility(db, 42)
    assert elig.mode == "legacy"
    assert elig.reason == "percent_blocked_stale_canary"
    dispose(engine, root)


def test_percent_miss_uses_legacy(monkeypatch, tmp_path) -> None:
    enable_test_only_mode()
    # bucket for request 42 with salt 2026-07-25.1 is 89 — miss at 1%
    _enable_7f(monkeypatch, percent="1", percent_serve=True, requires_canary=False)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()
    _seed_pointer(db, request_id=42)
    elig = evaluate_serve_eligibility(db, 42)
    assert elig.mode == "legacy"
    assert elig.reason == "percent_miss"
    sticky = compute_sticky_bucket(
        salt="2026-07-25.1", request_id=42, rollout_percent=1
    )
    assert sticky.percent_eligible is False
    dispose(engine, root)


def test_breaker_open_blocks_canary_execute(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch, breaker=True)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()
    from app.application.rollout.breaker_service import BreakerService

    bs = BreakerService(db)
    bs.ensure_default_policy()
    bs.manual_open(
        actor=_admin("admin:breaker"),
        reason="freeze",
        ticket_ref="T-BR",
        run_auto_rollback=False,
    )
    db.commit()
    svc = CanaryService(db, provider_factory=FixtureCanaryProvider)
    req = svc.request_canary(
        _admin("admin:requester"),
        1,
        CanaryRequestBody(reason="r", ticket_ref="T1"),
    )
    svc.approve_canary(
        _admin("admin:approver"),
        req.approval_id,
        CanaryApprovalBody(reason="a", ticket_ref="T1"),
    )
    svc2 = CanaryService(db, provider_factory=FixtureCanaryProvider)
    with pytest.raises(CanaryServiceError) as exc:
        svc2.execute_canary(
            _admin("admin:executor"),
            req.approval_id,
            CanaryExecuteBody(reason="e", ticket_ref="T1", idempotency_key="br-1"),
        )
    assert exc.value.reason == "breaker_not_closed"
    assert svc2.provider_was_constructed() is False
    dispose(engine, root)


def test_targeting_diagnostic_redacted(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()
    view = build_targeting_diagnostic(db, 1)
    dumped = view.model_dump()
    blob = str(dumped).lower()
    assert "password" not in blob
    assert "secret" not in blob
    assert "openrouter" not in blob
    assert "api_key" not in blob
    assert view.request_id == 1
    assert "serve_reason" in dumped
    dispose(engine, root)


def test_no_percentage_mutation_endpoint() -> None:
    from app.api.v1.routers import rollout_diagnostics as rd

    source = Path(rd.__file__).read_text(encoding="utf-8")
    assert "mutate_rollout_percent" not in source
    assert '"/percent"' not in source
    assert "requests/{request_id}/canaries" in source
    assert "canary-executions/{execution_id}/review" in source
    assert "targeting/{request_id}" in source


def test_serving_audit_timeout_bound() -> None:
    assert SERVING_FALLBACK_AUDIT_TIMEOUT_SECONDS == 0.25


def test_no_auto_promote_from_canary(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()
    count_before = db.query(PreviewServingPointerVersionRecord).count()
    _run_canary_lifecycle(db)
    count_after = db.query(PreviewServingPointerVersionRecord).count()
    assert count_after == count_before  # no new pointer rows
    dispose(engine, root)


def test_fixture_cannot_authorize_percent_serving(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch, percent="100", percent_serve=True)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()
    _seed_pointer(db, request_id=42)
    _req, execution, reviewed, _svc = _run_canary_lifecycle(db, idem_suffix="fx1")
    assert reviewed.reviewed_fixture_only is True
    assert reviewed.reviewed_accepted is False
    assert execution.provenance.percent_authorization_eligible is False
    invalidate_canary_auth_cache()
    elig = evaluate_serve_eligibility(db, 42)
    assert elig.mode == "legacy"
    assert elig.reason == "fixture_canary_not_eligible"
    diag = build_targeting_diagnostic(db, 42)
    assert diag.serve_reason == "fixture_canary_not_eligible"
    assert diag.canary_gate_reason == "fixture_canary_not_eligible"
    dispose(engine, root)


def test_live_providers_disabled_rejects_before_construction(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()
    svc = CanaryService(db)  # no injection, no simulation
    req = svc.request_canary(
        _admin("admin:requester"),
        1,
        CanaryRequestBody(reason="r", ticket_ref="T1"),
    )
    svc.approve_canary(
        _admin("admin:approver"),
        req.approval_id,
        CanaryApprovalBody(reason="a", ticket_ref="T1"),
    )
    svc2 = CanaryService(db)
    with pytest.raises(CanaryServiceError) as exc:
        svc2.execute_canary(
            _admin("admin:executor"),
            req.approval_id,
            CanaryExecuteBody(reason="e", ticket_ref="T1", idempotency_key="no-live"),
        )
    assert exc.value.reason == "live_providers_disabled"
    assert svc2.provider_was_constructed() is False
    dispose(engine, root)


def test_production_execute_does_not_silent_fixture(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()
    src = Path(
        importlib.import_module("app.application.rollout.canary_service").__file__
    ).read_text(encoding="utf-8")
    # Ordinary path must raise, not fall through to FixtureCanaryProvider()
    assert 'raise CanaryServiceError("live_providers_disabled"' in src
    svc = CanaryService(db)
    req = svc.request_canary(
        _admin("admin:requester"),
        1,
        CanaryRequestBody(reason="r", ticket_ref="T1"),
    )
    svc.approve_canary(
        _admin("admin:approver"),
        req.approval_id,
        CanaryApprovalBody(reason="a", ticket_ref="T1"),
    )
    with pytest.raises(CanaryServiceError) as exc:
        svc.execute_canary(
            _admin("admin:executor"),
            req.approval_id,
            CanaryExecuteBody(reason="e", ticket_ref="T1", idempotency_key="silent"),
        )
    assert exc.value.reason == "live_providers_disabled"
    dispose(engine, root)


def test_client_cannot_spoof_live_provenance(monkeypatch) -> None:
    from app.application.rollout.authorization import (
        RolloutAuthorizationError,
        reject_client_supplied_roles,
    )

    with pytest.raises(RolloutAuthorizationError):
        reject_client_supplied_roles({"provider_was_live": True})
    with pytest.raises(RolloutAuthorizationError):
        reject_client_supplied_roles({"execution_mode": "live"})
    with pytest.raises(RolloutAuthorizationError):
        reject_client_supplied_roles({"percent_authorization_eligible": True})


def test_promotion_rejects_fixture_canary_evidence(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()
    _req, execution, _reviewed, _svc = _run_canary_lifecycle(db, idem_suffix="promo")
    from app.application.rollout.promotion_service import (
        PromotionService,
        PromotionServiceError,
    )

    svc = PromotionService(db)
    with pytest.raises(PromotionServiceError) as exc:
        svc._verify_canary_evidence(
            request_id=1,
            canary_execution_id=execution.execution_id,
            candidate_revision_id=7,
            effective_tier_summary_id=1,
        )
    assert exc.value.reason == "canary_fixture_not_eligible"
    dispose(engine, root)


def test_cache_separates_fixture_and_live(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch, percent="100", percent_serve=True)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()
    _seed_pointer(db, request_id=42)
    _run_canary_lifecycle(db, idem_suffix="cache-fx")
    invalidate_canary_auth_cache()
    from app.application.rollout.percent_serve import canary_authorization

    fx = canary_authorization(db)
    assert fx.valid is False
    assert fx.reason == "fixture_canary_not_eligible"
    fx_key = fx.cache_key
    _run_live_canary_lifecycle(db, monkeypatch, idem_suffix="cache-live")
    invalidate_canary_auth_cache()
    live = canary_authorization(db)
    assert live.valid is True
    assert live.execution_mode == "live"
    assert live.cache_key != fx_key
    dispose(engine, root)


def test_live_provenance_is_server_derived(monkeypatch) -> None:
    enable_test_only_mode()
    _enable_7f(monkeypatch)
    engine, root = make_phase7f_engine()
    db = make_session(engine)
    import_rollout_models()
    _req, execution, reviewed, _svc = _run_live_canary_lifecycle(
        db, monkeypatch, idem_suffix="prov"
    )
    assert execution.provenance.execution_mode == "live"
    assert execution.provenance.provider_was_live is True
    assert execution.provenance.simulation_only is False
    assert execution.provenance.network_access_expected is True
    assert execution.provenance.percent_authorization_eligible is True
    assert reviewed.reviewed_accepted is True
    assert reviewed.reviewed_fixture_only is False
    dispose(engine, root)


KNOWN_PREEXISTING_FAILURES = (
    "test_pottery_picks_craft_studio_pack",
    "test_enriched_industry_packs_carry_seed_items",
    "test_production_callsites_render_with_strict_undefined",
)


def test_known_preexisting_failures_documented() -> None:
    assert len(KNOWN_PREEXISTING_FAILURES) == 3
