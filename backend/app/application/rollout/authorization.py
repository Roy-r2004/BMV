"""Trusted rollout RBAC and separation-of-duties for Phase 7A.

Roles come only from authenticated server context or a dedicated trusted
adapter. Client JSON must never supply actor roles.
"""
from __future__ import annotations

from typing import Iterable

from app.domain.schemas.rollout import (
    RolloutRole,
    SeparationOfDutiesResult,
    TrustedRolloutActor,
)


PHASE7A_PERMISSIONS: dict[RolloutRole, frozenset[str]] = {
    "rollout_viewer": frozenset({"read_diagnostics", "read_breaker"}),
    "rollout_operator": frozenset(
        {
            "read_diagnostics",
            "read_breaker",
            "compute_shadow_eligibility",
            "compute_promotion_eligibility",
            "start_shadow_evaluation",
            "request_promotion",
            "request_rollback",
        }
    ),
    "rollout_approver": frozenset(
        {
            "read_diagnostics",
            "read_breaker",
            "review_eligibility",
            "review_policy_state",
            "approve_promotion",
            "approve_rollback",
        }
    ),
    "rollout_admin": frozenset(
        {
            "read_diagnostics",
            "read_breaker",
            "compute_shadow_eligibility",
            "compute_promotion_eligibility",
            "review_eligibility",
            "review_policy_state",
            "create_rollout_policy_version",
            "start_shadow_evaluation",
            "request_promotion",
            "request_rollback",
            "approve_promotion",
            "approve_rollback",
            "apply_promotion",
            "apply_rollback",
            "evaluate_breaker",
            "open_breaker",
            "close_breaker",
            "disable_breaker",
            "run_auto_rollback",
        }
    ),
}

# Still forbid canary consume / percent serve / live regenerate.
# Breaker open/evaluate/auto-rollback are gated via explicit permissions above.
FORBIDDEN_PHASE7A_ACTIONS = frozenset(
    {
        "consume_canary_approval",
        "start_live_shadow_regenerate",
        "percentage_serve",
    }
)


class RolloutAuthorizationError(PermissionError):
    """Trusted-context authorization failure."""


def actor_has_permission(actor: TrustedRolloutActor, permission: str) -> bool:
    if permission in FORBIDDEN_PHASE7A_ACTIONS:
        return False
    for role in actor.roles:
        if permission in PHASE7A_PERMISSIONS.get(role, frozenset()):
            return True
    return False


def require_permission(actor: TrustedRolloutActor, permission: str) -> None:
    if not actor_has_permission(actor, permission):
        raise RolloutAuthorizationError(
            f"actor {actor.actor_id} lacks permission {permission}"
        )


def reject_client_supplied_roles(payload: dict) -> None:
    """Boundary guard: request JSON must not carry authorization roles."""
    banned = (
        "actor_id",
        "actor_role",
        "actor_roles",
        "roles",
        "rollout_role",
        "authorization_scope",
        "serving_target",
        "current_pointer",
        "pointer_version",
        "eligibility_result",
        "eligibility_sha256",
        "provider",
        "model",
        "provider_model",
        "breaker_override",
    )
    for key in banned:
        if key in payload:
            raise RolloutAuthorizationError(
                f"client payload must not supply authorization field {key!r}"
            )


def evaluate_separation_of_duties(
    *,
    requester_actor_id: str,
    approver_actor_id: str | None,
    apply_actor_id: str | None = None,
    dual_role_allowed: bool = False,
    ticket_ref: str | None = None,
    reason: str | None = None,
    require_approver: bool = True,
) -> SeparationOfDutiesResult:
    requester = requester_actor_id.strip()
    approver = (approver_actor_id or "").strip() or None
    apply_actor = (apply_actor_id or "").strip() or None
    same = bool(approver and approver == requester)
    apply_overlap = bool(
        apply_actor and apply_actor in {requester, *( [approver] if approver else [] )}
    )
    reasons: list[str] = []

    if require_approver and approver is None:
        reasons.append("approver_missing")
    elif same:
        if not dual_role_allowed:
            reasons.append("same_actor_denied")
        else:
            if not (ticket_ref or "").strip():
                reasons.append("emergency_dual_role_requires_ticket")
            if not (reason or "").strip():
                reasons.append("emergency_dual_role_requires_reason")

    if apply_actor and apply_overlap:
        if not dual_role_allowed:
            reasons.append("apply_actor_same_as_earlier_denied")
        else:
            if not (ticket_ref or "").strip():
                reasons.append("emergency_apply_requires_ticket")
            if not (reason or "").strip():
                reasons.append("emergency_apply_requires_reason")

    satisfied = not reasons
    return SeparationOfDutiesResult(
        requester_actor_id=requester,
        approver_actor_id=approver,
        same_actor=same or apply_overlap,
        dual_role_allowed=dual_role_allowed,
        ticket_ref=(ticket_ref or None),
        satisfied=satisfied,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def trusted_actor_from_admin(
    *,
    actor_id: str,
    is_admin: bool,
    extra_roles: Iterable[RolloutRole] = (),
) -> TrustedRolloutActor:
    """Map authenticated admin session to trusted rollout roles."""
    roles: list[RolloutRole] = []
    if is_admin:
        roles.append("rollout_admin")
    roles.extend(extra_roles)
    if not roles:
        raise RolloutAuthorizationError("no trusted rollout roles for actor")
    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[RolloutRole] = []
    for role in roles:
        if role not in seen:
            seen.add(role)
            unique.append(role)
    return TrustedRolloutActor(
        actor_id=actor_id,
        roles=tuple(unique),
        auth_source="admin_header" if is_admin else "session",
    )


__all__ = [
    "FORBIDDEN_PHASE7A_ACTIONS",
    "PHASE7A_PERMISSIONS",
    "RolloutAuthorizationError",
    "actor_has_permission",
    "evaluate_separation_of_duties",
    "reject_client_supplied_roles",
    "require_permission",
    "trusted_actor_from_admin",
]
