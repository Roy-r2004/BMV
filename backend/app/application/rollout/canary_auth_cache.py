"""Bounded process-local cache for percent-serve canary authorization."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class CanaryAuthSnapshot:
    valid: bool
    reason: str
    execution_id: int | None
    execution_sha256: str | None
    policy_identity_sha256: str
    cache_key: str
    execution_mode: str | None = None
    percent_authorization_eligible: bool = False


_lock = threading.Lock()
_cache: dict[str, CanaryAuthSnapshot] = {}


def invalidate_canary_auth_cache() -> None:
    with _lock:
        _cache.clear()


def get_cached_canary_auth(cache_key: str) -> CanaryAuthSnapshot | None:
    with _lock:
        return _cache.get(cache_key)


def put_cached_canary_auth(snapshot: CanaryAuthSnapshot) -> None:
    with _lock:
        # Bound: keep only latest few keys (policy identities).
        if len(_cache) >= 8 and snapshot.cache_key not in _cache:
            oldest = next(iter(_cache))
            _cache.pop(oldest, None)
        _cache[snapshot.cache_key] = snapshot


def resolve_canary_auth(
    db: Session,
    *,
    cache_key: str,
    loader: Callable[[Session], CanaryAuthSnapshot],
) -> CanaryAuthSnapshot:
    hit = get_cached_canary_auth(cache_key)
    if hit is not None:
        return hit
    snap = loader(db)
    # Store under both lookup key and the snapshot's authoritative key so
    # fixture vs live evidence cannot collide.
    put_cached_canary_auth(snap)
    if snap.cache_key != cache_key:
        with _lock:
            _cache[cache_key] = snap
    return snap


__all__ = [
    "CanaryAuthSnapshot",
    "get_cached_canary_auth",
    "invalidate_canary_auth_cache",
    "put_cached_canary_auth",
    "resolve_canary_auth",
]
