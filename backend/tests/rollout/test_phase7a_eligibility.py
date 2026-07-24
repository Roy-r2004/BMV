"""Advisory eligibility recomputation and hash stability."""
from __future__ import annotations

from app.application.rollout.eligibility import (
    EligibilityInputs,
    compute_promotion_eligibility,
    eligibility_authorizes_write,
)
from app.application.rollout.policy import build_policy_view
from app.domain.schemas.rollout import TrustedRolloutActor


def _policy(**overrides):
    base = dict(
        policy_revision="2026-07-25.1",
        master_enabled=True,
        shadow_enabled=True,
        promote_enabled=True,
        rollout_percent=100,
        allowlist=(),
        rollout_salt="2026-07-25.1",
        created_actor_id="admin",
        created_actor_role="rollout_admin",
    )
    base.update(overrides)
    return build_policy_view(**base)


def _actor(*roles):
    return TrustedRolloutActor(
        actor_id="op-1",
        roles=tuple(roles),
        auth_source="session",
    )


def test_eligibility_advisory_only_and_deterministic() -> None:
    inputs = EligibilityInputs(
        request_id=1,
        candidate_revision_id=7,
        requested_tier=1,
        effective_tier_summary_id=None,
        highest_accepted_tier=1,
        phase4_status="candidate_runtime_validated",
        phase5_status="candidate_visual_accepted",
        lineage_ok=True,
        manifest_ok=True,
        policy=_policy(),
        circuit_breaker_state="closed",
        actor=_actor("rollout_operator"),
        requester_actor_id="op-1",
        approver_actor_id="ap-2",
    )
    a = compute_promotion_eligibility(inputs)
    b = compute_promotion_eligibility(inputs)
    assert a.eligibility_sha256 == b.eligibility_sha256
    assert a.advisory_only is True
    assert eligibility_authorizes_write(a) is False
    assert a.eligible_for_promote is True


def test_eligibility_recomputes_current_policy() -> None:
    actor = _actor("rollout_operator")
    base = EligibilityInputs(
        request_id=1,
        candidate_revision_id=7,
        requested_tier=1,
        effective_tier_summary_id=None,
        highest_accepted_tier=1,
        phase4_status="candidate_runtime_validated",
        phase5_status="candidate_visual_accepted",
        lineage_ok=True,
        manifest_ok=True,
        policy=_policy(master_enabled=True, promote_enabled=True),
        circuit_breaker_state="closed",
        actor=actor,
        requester_actor_id="op-1",
        approver_actor_id="ap-2",
    )
    enabled = compute_promotion_eligibility(base)
    disabled = compute_promotion_eligibility(
        EligibilityInputs(
            **{
                **base.__dict__,
                "policy": _policy(master_enabled=False, promote_enabled=True),
            }
        )
    )
    assert enabled.eligible_for_promote is True
    assert disabled.eligible_for_promote is False
    assert "master_disabled" in disabled.rejection_reasons
    assert enabled.eligibility_sha256 != disabled.eligibility_sha256


def test_breaker_open_and_unauthorized() -> None:
    result = compute_promotion_eligibility(
        EligibilityInputs(
            request_id=1,
            candidate_revision_id=7,
            requested_tier=1,
            effective_tier_summary_id=None,
            highest_accepted_tier=1,
            phase4_status="candidate_runtime_validated",
            phase5_status="candidate_visual_accepted",
            lineage_ok=True,
            manifest_ok=True,
            policy=_policy(),
            circuit_breaker_state="open",
            actor=_actor("rollout_viewer"),
            requester_actor_id="v1",
            approver_actor_id="ap-2",
        )
    )
    assert result.eligible_for_promote is False
    assert "circuit_breaker_open" in result.rejection_reasons
    assert "actor_unauthorized" in result.rejection_reasons
