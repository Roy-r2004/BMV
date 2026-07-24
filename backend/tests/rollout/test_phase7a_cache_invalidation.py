"""Cache key identity and invalidation rules."""
from __future__ import annotations

from app.application.rollout.cache import (
    ProcessMemo,
    RolloutCacheInvalidation,
    RolloutCacheKeys,
)
from app.application.rollout.targeting import compute_sticky_bucket


def test_cache_keys_and_invalidation() -> None:
    sticky_key = RolloutCacheKeys.for_sticky("2026-07-25.1", "1")
    pointer_key = RolloutCacheKeys.for_pointer(1, 2)
    policy_key = RolloutCacheKeys.for_policy("a" * 64)
    memo = ProcessMemo()
    memo.set_sticky(sticky_key, compute_sticky_bucket(
        salt="2026-07-25.1", request_id=1, rollout_percent=50
    ))
    memo.set_pointer(pointer_key, {"v": 2})
    events = RolloutCacheInvalidation()
    events.on_policy_changed(salt="2026-07-25.1", configuration_sha256=policy_key)
    events.on_pointer_changed(request_id=1)
    memo.invalidate(events)
    assert memo.get_sticky(sticky_key) is None
    assert memo.get_pointer(pointer_key) is None
