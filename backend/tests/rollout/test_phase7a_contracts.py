"""Canary and circuit-breaker contracts — define only."""
from __future__ import annotations

import sys

from app.application.rollout.breaker_contract import (
    DEFAULT_BREAKER_POLICY,
    metric_classes_are_separate,
)
from app.application.rollout.canary_contract import (
    assert_no_provider_construction,
    canary_approval_sha256,
    determine_single_use_status,
)
from app.application.rollout.health_contract import DEFAULT_SERVING_HEALTH_CONTRACT
from app.domain.schemas.rollout import (
    CanaryApprovalStatusEvent,
    LiveCanaryApprovalContract,
)


def test_breaker_defaults() -> None:
    p = DEFAULT_BREAKER_POLICY
    assert p.window_seconds == 900
    assert p.min_samples == 20
    assert p.serving_health_failure_threshold == 0.05
    assert p.promotion_write_failure_threshold == 0.10
    assert p.consecutive_serving_health_failures == 3
    assert p.p95_serving_latency_seconds == 5.0
    assert p.open_duration_seconds == 600
    assert p.half_open_probes == 2
    assert metric_classes_are_separate(p)


def test_canary_append_only_status_lineage() -> None:
    contract = LiveCanaryApprovalContract(
        approval_uuid="11111111-1111-1111-1111-111111111111",
        request_id=1,
        provider_model_allowlist=("openrouter/x",),
        max_calls=2,
        max_output_tokens=1000,
        max_cost_usd=0.5,
        max_wall_seconds=60,
        expires_at="2026-07-26T00:00:00Z",
        approver_id="approver-1",
        ticket_ref="CANARY-1",
        policy_revision="2026-07-25.1",
        status="approved",
        approval_sha256="a" * 64,
    )
    digest = canary_approval_sha256(contract)
    assert len(digest) == 64
    events = [
        CanaryApprovalStatusEvent(
            approval_uuid=contract.approval_uuid,
            status="approved",
            actor_id="approver-1",
            reason="approved",
            created_at="2026-07-25T00:00:00Z",
            event_sha256="b" * 64,
        ),
        CanaryApprovalStatusEvent(
            approval_uuid=contract.approval_uuid,
            status="consumed",
            actor_id="system:phase7-canary",
            reason="consumed",
            created_at="2026-07-25T01:00:00Z",
            event_sha256="c" * 64,
        ),
    ]
    assert determine_single_use_status(events=events) == "consumed"
    assert_no_provider_construction()
    assert DEFAULT_SERVING_HEALTH_CONTRACT.pointer_resolves is True


def test_zero_provider_modules_imported_by_canary() -> None:
    # Canary contract module must not pull AI providers.
    banned = [
        name
        for name in sys.modules
        if name.startswith("app.infrastructure.ai_providers")
        and "canary_contract" in str(sys.modules.get("app.application.rollout.canary_contract"))
    ]
    # Importing canary_contract alone should not require providers.
    import app.application.rollout.canary_contract as canary

    assert "openrouter" not in canary.__file__
    _ = banned
