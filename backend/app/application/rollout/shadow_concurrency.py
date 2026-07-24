"""Process-local shadow concurrency gate (max 1 for Phase 7B)."""
from __future__ import annotations

import threading
from contextlib import contextmanager


class ShadowConcurrencyError(RuntimeError):
    """Raised when the process-local shadow concurrency limit is exceeded."""


class ShadowConcurrencyGate:
    def __init__(self, *, max_concurrency: int = 1) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        self._max = max_concurrency
        self._sem = threading.BoundedSemaphore(max_concurrency)
        self._lock = threading.Lock()
        self._active_requests: set[int] = set()

    @contextmanager
    def acquire(self, request_id: int):
        with self._lock:
            if request_id in self._active_requests:
                raise ShadowConcurrencyError(
                    f"shadow already in progress for request_id={request_id}"
                )
        if not self._sem.acquire(blocking=False):
            raise ShadowConcurrencyError("shadow concurrency limit reached")
        with self._lock:
            self._active_requests.add(request_id)
        try:
            yield
        finally:
            with self._lock:
                self._active_requests.discard(request_id)
            self._sem.release()


SHADOW_GATE = ShadowConcurrencyGate(max_concurrency=1)


__all__ = ["SHADOW_GATE", "ShadowConcurrencyError", "ShadowConcurrencyGate"]
