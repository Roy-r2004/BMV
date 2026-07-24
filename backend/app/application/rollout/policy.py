"""Rollout policy hashing and view construction for Phase 7A."""
from __future__ import annotations

import hashlib
import json
from typing import Sequence

from app.application.rollout.breaker_contract import (
    DEFAULT_BREAKER_POLICY,
    breaker_policy_canonical_json,
    breaker_policy_sha256,
)
from app.domain.schemas.rollout import (
    CircuitBreakerPolicyContract,
    RolloutPolicyView,
    RolloutRole,
)


def normalize_allowlist(raw: Sequence[int] | str) -> tuple[int, ...]:
    if isinstance(raw, str):
        tokens = [t.strip() for t in raw.split(",") if t.strip()]
        if not tokens:
            return ()
        values: list[int] = []
        for token in tokens:
            if not token.isdigit() or int(token) < 1:
                raise ValueError(f"malformed allowlist token: {token!r}")
            values.append(int(token))
        return tuple(sorted(set(values)))
    values = []
    for item in raw:
        if not isinstance(item, int) or isinstance(item, bool) or item < 1:
            raise ValueError(f"malformed allowlist id: {item!r}")
        values.append(item)
    return tuple(sorted(set(values)))


def allowlist_canonical_json(allowlist: tuple[int, ...]) -> str:
    return json.dumps(list(allowlist), separators=(",", ":"))


def allowlist_sha256(allowlist: tuple[int, ...]) -> str:
    return hashlib.sha256(allowlist_canonical_json(allowlist).encode("utf-8")).hexdigest()


def configuration_sha256(
    *,
    policy_revision: str,
    master_enabled: bool,
    shadow_enabled: bool,
    promote_enabled: bool,
    rollout_percent: int,
    allowlist: tuple[int, ...],
    rollout_salt: str,
    breaker: CircuitBreakerPolicyContract,
) -> str:
    payload = {
        "policy_revision": policy_revision,
        "master_enabled": master_enabled,
        "shadow_enabled": shadow_enabled,
        "promote_enabled": promote_enabled,
        "rollout_percent": rollout_percent,
        "allowlist": list(allowlist),
        "rollout_salt": rollout_salt,
        "circuit_breaker_policy": json.loads(breaker_policy_canonical_json(breaker)),
    }
    material = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def build_policy_view(
    *,
    policy_revision: str,
    master_enabled: bool,
    shadow_enabled: bool,
    promote_enabled: bool,
    rollout_percent: int,
    allowlist: tuple[int, ...],
    rollout_salt: str,
    created_actor_id: str,
    created_actor_role: RolloutRole,
    breaker: CircuitBreakerPolicyContract | None = None,
) -> RolloutPolicyView:
    if rollout_percent < 0 or rollout_percent > 100:
        raise ValueError("rollout_percent must be 0–100")
    policy = breaker or DEFAULT_BREAKER_POLICY
    allow = normalize_allowlist(allowlist)
    return RolloutPolicyView(
        policy_revision=policy_revision,
        master_enabled=master_enabled,
        shadow_enabled=shadow_enabled,
        promote_enabled=promote_enabled,
        rollout_percent=rollout_percent,
        allowlist=allow,
        allowlist_sha256=allowlist_sha256(allow),
        circuit_breaker_policy=policy,
        circuit_breaker_policy_sha256=breaker_policy_sha256(policy),
        rollout_salt=rollout_salt,
        configuration_sha256=configuration_sha256(
            policy_revision=policy_revision,
            master_enabled=master_enabled,
            shadow_enabled=shadow_enabled,
            promote_enabled=promote_enabled,
            rollout_percent=rollout_percent,
            allowlist=allow,
            rollout_salt=rollout_salt,
            breaker=policy,
        ),
        created_actor_id=created_actor_id,
        created_actor_role=created_actor_role,
    )


__all__ = [
    "allowlist_canonical_json",
    "allowlist_sha256",
    "build_policy_view",
    "configuration_sha256",
    "normalize_allowlist",
]
