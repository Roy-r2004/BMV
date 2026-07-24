"""Cache identity and invalidation utilities for Phase 7A.

Eligibility is never durably cached as a write-authorization token.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RolloutCacheKeys:
    sticky_bucket: tuple[str, str]
    serving_pointer: tuple[int, int | None]
    policy_configuration: str

    @staticmethod
    def for_sticky(salt: str, request_id: str) -> tuple[str, str]:
        return (salt, request_id)

    @staticmethod
    def for_pointer(request_id: int, pointer_version: int | None) -> tuple[int, int | None]:
        return (request_id, pointer_version)

    @staticmethod
    def for_policy(configuration_sha256: str) -> str:
        return configuration_sha256


@dataclass
class RolloutCacheInvalidation:
    """Tracks which cache namespaces must be dropped after events."""

    sticky_salts: set[str] = field(default_factory=set)
    pointer_request_ids: set[int] = field(default_factory=set)
    policy_configuration_hashes: set[str] = field(default_factory=set)

    def on_policy_changed(self, *, salt: str, configuration_sha256: str) -> None:
        self.sticky_salts.add(salt)
        self.policy_configuration_hashes.add(configuration_sha256)

    def on_pointer_changed(self, *, request_id: int) -> None:
        self.pointer_request_ids.add(request_id)


class ProcessMemo:
    """Short-lived process memo — never authorizes promotion writes."""

    def __init__(self) -> None:
        self._sticky: dict[tuple[str, str], object] = {}
        self._pointer: dict[tuple[int, int | None], object] = {}

    def get_sticky(self, key: tuple[str, str]):
        return self._sticky.get(key)

    def set_sticky(self, key: tuple[str, str], value: object) -> None:
        self._sticky[key] = value

    def get_pointer(self, key: tuple[int, int | None]):
        return self._pointer.get(key)

    def set_pointer(self, key: tuple[int, int | None], value: object) -> None:
        self._pointer[key] = value

    def invalidate(self, events: RolloutCacheInvalidation) -> None:
        if events.sticky_salts:
            self._sticky = {
                k: v for k, v in self._sticky.items() if k[0] not in events.sticky_salts
            }
        if events.pointer_request_ids:
            self._pointer = {
                k: v
                for k, v in self._pointer.items()
                if k[0] not in events.pointer_request_ids
            }


__all__ = [
    "ProcessMemo",
    "RolloutCacheInvalidation",
    "RolloutCacheKeys",
]
