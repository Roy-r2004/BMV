"""Trusted RBAC and separation-of-duties for Phase 7A."""
from __future__ import annotations

import pytest

from app.application.rollout.authorization import (
    FORBIDDEN_PHASE7A_ACTIONS,
    RolloutAuthorizationError,
    actor_has_permission,
    evaluate_separation_of_duties,
    reject_client_supplied_roles,
    require_permission,
    trusted_actor_from_admin,
)
from app.domain.schemas.rollout import TrustedRolloutActor


def test_role_permissions_matrix() -> None:
    viewer = TrustedRolloutActor(
        actor_id="v1", roles=("rollout_viewer",), auth_source="session"
    )
    operator = TrustedRolloutActor(
        actor_id="o1", roles=("rollout_operator",), auth_source="session"
    )
    approver = TrustedRolloutActor(
        actor_id="a1", roles=("rollout_approver",), auth_source="session"
    )
    admin = TrustedRolloutActor(
        actor_id="ad1", roles=("rollout_admin",), auth_source="admin_header"
    )
    assert actor_has_permission(viewer, "read_diagnostics")
    assert not actor_has_permission(viewer, "compute_promotion_eligibility")
    assert actor_has_permission(operator, "compute_promotion_eligibility")
    assert actor_has_permission(operator, "request_promotion")
    assert not actor_has_permission(operator, "apply_promotion")
    assert actor_has_permission(approver, "review_eligibility")
    assert actor_has_permission(approver, "approve_promotion")
    assert not actor_has_permission(approver, "apply_promotion")
    assert actor_has_permission(admin, "create_rollout_policy_version")
    assert actor_has_permission(admin, "apply_promotion")
    assert actor_has_permission(admin, "apply_rollback")
    for action in FORBIDDEN_PHASE7A_ACTIONS:
        assert not actor_has_permission(admin, action)


def test_client_payload_roles_rejected() -> None:
    with pytest.raises(RolloutAuthorizationError):
        reject_client_supplied_roles({"actor_role": "rollout_admin"})
    with pytest.raises(RolloutAuthorizationError):
        reject_client_supplied_roles({"roles": ["rollout_admin"]})
    reject_client_supplied_roles({"request_id": 1})


def test_separation_of_duties() -> None:
    ok = evaluate_separation_of_duties(
        requester_actor_id="alice",
        approver_actor_id="bob",
    )
    assert ok.satisfied is True
    same = evaluate_separation_of_duties(
        requester_actor_id="alice",
        approver_actor_id="alice",
        dual_role_allowed=False,
    )
    assert same.satisfied is False
    emergency = evaluate_separation_of_duties(
        requester_actor_id="alice",
        approver_actor_id="alice",
        dual_role_allowed=True,
        ticket_ref="INC-1",
        reason="emergency dual-role approved",
    )
    assert emergency.satisfied is True
    emergency_missing_reason = evaluate_separation_of_duties(
        requester_actor_id="alice",
        approver_actor_id="alice",
        dual_role_allowed=True,
        ticket_ref="INC-1",
    )
    assert emergency_missing_reason.satisfied is False


def test_trusted_actor_from_admin() -> None:
    actor = trusted_actor_from_admin(actor_id="admin@x", is_admin=True)
    assert "rollout_admin" in actor.roles
    require_permission(actor, "read_diagnostics")
