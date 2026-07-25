"""Bounded stage deadlines for Phase 3A AI stages."""
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class StageDeadline:
    """One monotonic deadline created at stage start."""

    stage: str
    started_at: float
    deadline_at: float
    wall_seconds: float

    @classmethod
    def start(cls, stage: str, wall_seconds: float) -> "StageDeadline":
        started = time.monotonic()
        wall = max(0.0, float(wall_seconds))
        return cls(
            stage=stage,
            started_at=started,
            deadline_at=started + wall,
            wall_seconds=wall,
        )

    def remaining(self, *, now: float | None = None) -> float:
        current = time.monotonic() if now is None else now
        return max(0.0, self.deadline_at - current)

    def elapsed(self, *, now: float | None = None) -> float:
        current = time.monotonic() if now is None else now
        return max(0.0, current - self.started_at)

    def exhausted(self, *, now: float | None = None) -> bool:
        return self.remaining(now=now) <= 0.0

    def call_timeout(
        self,
        *,
        per_call_timeout: float,
        min_call_budget: float,
        now: float | None = None,
    ) -> float | None:
        """Return bounded call timeout, or None when unsafe to start a call."""

        remaining = self.remaining(now=now)
        if remaining < max(0.0, float(min_call_budget)):
            return None
        timeout = min(float(per_call_timeout), remaining)
        if timeout < max(0.0, float(min_call_budget)):
            return None
        return timeout


__all__ = ["StageDeadline"]
