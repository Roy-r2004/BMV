"""Trusted commercial Expanded Preview RBAC (separate from Phase 7 rollout)."""
from __future__ import annotations

from typing import Iterable

from app.domain.schemas.expanded_preview import CommercialRole, TrustedCommercialActor

COMMERCIAL_PERMISSIONS: dict[CommercialRole, frozenset[str]] = {
    "expanded_preview_viewer": frozenset({"read_queue", "read_detail"}),
    "expanded_preview_operator": frozenset(
        {
            "read_queue",
            "read_detail",
            "approve",
            "reject",
            "start_generation",
            "review",
        }
    ),
    "expanded_preview_admin": frozenset(
        {
            "read_queue",
            "read_detail",
            "approve",
            "reject",
            "start_generation",
            "review",
            "publish",
        }
    ),
}


class CommercialAuthorizationError(PermissionError):
    """Trusted-context commercial authorization failure."""


def actor_has_permission(actor: TrustedCommercialActor, permission: str) -> bool:
    for role in actor.roles:
        if permission in COMMERCIAL_PERMISSIONS.get(role, frozenset()):
            return True
    return False


def require_permission(actor: TrustedCommercialActor, permission: str) -> None:
    if not actor_has_permission(actor, permission):
        raise CommercialAuthorizationError(
            f"actor {actor.actor_id} lacks permission {permission}"
        )


def reject_client_supplied_roles(payload: dict) -> None:
    banned = (
        "actor_id",
        "actor_role",
        "actor_roles",
        "roles",
        "commercial_role",
        "authorization_scope",
        "approval_status",
        "generation_permissions",
        "target_candidate_revision",
        "publish_authority",
        "pricing_authority",
        "serving_target",
        "pointer_version",
        "provider",
        "model",
    )
    for key in banned:
        if key in payload:
            raise CommercialAuthorizationError(
                f"client payload must not supply authorization field {key!r}"
            )


def trusted_actor_from_admin(
    *,
    actor_id: str,
    is_admin: bool,
    extra_roles: Iterable[CommercialRole] = (),
) -> TrustedCommercialActor:
    roles: list[CommercialRole] = []
    if is_admin:
        # Authenticated product admins receive full commercial capability.
        # Distinct actor_ids still provide audit separation of duties.
        roles.append("expanded_preview_admin")
        roles.append("expanded_preview_operator")
        roles.append("expanded_preview_viewer")
    roles.extend(extra_roles)
    if not roles:
        raise CommercialAuthorizationError("no trusted commercial roles for actor")
    seen: set[str] = set()
    unique: list[CommercialRole] = []
    for role in roles:
        if role not in seen:
            seen.add(role)
            unique.append(role)
    return TrustedCommercialActor(
        actor_id=actor_id,
        roles=tuple(unique),
        auth_source="admin_header" if is_admin else "session",
    )


__all__ = [
    "COMMERCIAL_PERMISSIONS",
    "CommercialAuthorizationError",
    "actor_has_permission",
    "reject_client_supplied_roles",
    "require_permission",
    "trusted_actor_from_admin",
]
