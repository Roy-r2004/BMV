"""Idempotency and process-local concurrency for Phase 7B."""
from __future__ import annotations

import importlib
import threading

import pytest

from app.application.rollout.shadow_concurrency import (
    SHADOW_GATE,
    ShadowConcurrencyError,
    ShadowConcurrencyGate,
)
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


def _op():
    return TrustedRolloutActor(
        actor_id="op", roles=("rollout_operator",), auth_source="test_fixture"
    )


def test_idempotent_post_returns_same_terminal(monkeypatch) -> None:
    enable_test_only_mode()
    _enable(monkeypatch)
    engine, root = make_rollout_engine()
    db = make_session(engine)
    monkeypatch.setattr(
        "app.application.rollout.shadow_service.locate_latest_accepted_lineage",
        lambda *_a, **_k: None,
    )
    svc = ShadowService(db)
    body = ShadowStartRequest(
        reason="idem",
        mode="regenerate_fixture",
        idempotency_key="same-key",
    )
    first = svc.start_shadow(actor=_op(), request_id=1, body=body)
    db.commit()
    second = svc.start_shadow(actor=_op(), request_id=1, body=body)
    assert first.evaluation_id == second.evaluation_id
    assert first.shadow_attempt_uuid == second.shadow_attempt_uuid
    db.close()
    dispose(engine, root)


def test_idempotency_conflict_on_different_mode(monkeypatch) -> None:
    enable_test_only_mode()
    _enable(monkeypatch)
    engine, root = make_rollout_engine()
    db = make_session(engine)
    svc = ShadowService(db)
    svc.start_shadow(
        actor=_op(),
        request_id=1,
        body=ShadowStartRequest(
            reason="a",
            mode="regenerate_fixture",
            idempotency_key="conflict-key",
        ),
    )
    db.commit()
    # Insert a pending-only conflict: create pending with different mode via
    # second call with same key but different mode after clearing terminal link
    # by using a fresh pending row manually is hard; service checks pending.mode.
    # Simulate by starting with reuse after fixture under same key — pending
    # already has terminal, so find_idempotent returns terminal; force conflict
    # by inserting pending-only with key.
    from datetime import datetime

    from app.domain.models.rollout import PreviewShadowEvaluationRecord

    pending = PreviewShadowEvaluationRecord(
        request_id=1,
        served_target_kind="none",
        served_pointer_version=None,
        comparison_policy_revision="2026-07-25.1",
        telemetry_json='{"schema_version":"1.0","mode":"reuse_accepted","started_at":"t","wall_ms":0,"provider_calls":0,"output_tokens":0,"estimated_cost_usd":0.0,"cache_hit_lineage":false,"cache_hit_pointer":false,"cache_hit_comparison":false,"phase4_status":"p","phase5_status":"p","highest_accepted_tier":0,"served_target_kind":"unset","compare_enabled":true,"compare_status":"skipped","eligibility_sha256":"'
        + ("c" * 64)
        + '","rejection_reasons":[],"no_serving_mutation":true,"synthetic_fixture_telemetry":false}',
        telemetry_sha256="d" * 64,
        result_status="pending",
        no_serving_mutation=True,
        created_at=datetime.utcnow(),
        evaluation_sha256="e" * 64,
        shadow_attempt_uuid="11111111-1111-1111-1111-111111111111",
        mode="reuse_accepted",
        idempotency_key="conflict-key-2",
        eligibility_sha256="c" * 64,
    )
    db.add(pending)
    db.commit()
    with pytest.raises(ShadowExecutionError, match="idempotency_key_conflict"):
        svc.start_shadow(
            actor=_op(),
            request_id=1,
            body=ShadowStartRequest(
                reason="b",
                mode="regenerate_fixture",
                idempotency_key="conflict-key-2",
            ),
        )
    db.close()
    dispose(engine, root)


def test_concurrency_gate_serializes_same_request() -> None:
    gate = ShadowConcurrencyGate(max_concurrency=1)
    entered = threading.Event()
    release = threading.Event()
    errors: list[Exception] = []

    def worker():
        try:
            with gate.acquire(7):
                entered.set()
                release.wait(timeout=2)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=worker)
    t1.start()
    assert entered.wait(timeout=1)
    with pytest.raises(ShadowConcurrencyError):
        with gate.acquire(7):
            pass
    with pytest.raises(ShadowConcurrencyError):
        with gate.acquire(8):
            pass
    release.set()
    t1.join(timeout=2)
    assert errors == []
    # Gate recovers
    with gate.acquire(7):
        pass
    _ = SHADOW_GATE
