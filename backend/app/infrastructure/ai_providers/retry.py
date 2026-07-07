"""Retry helper for AI provider network calls with exponential backoff.

Wraps flaky HTTP calls (timeouts, connection resets, rate limits, 5xx) so a
single transient network blip doesn't kill an entire generation stage. Only
retries errors that look transient — malformed responses / auth errors fail
fast since retrying won't help.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, TypeVar

import requests

T = TypeVar("T")

_RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


def _run_with_heartbeat(
    fn: Callable[[], T],
    heartbeat_interval: float,
    on_heartbeat: Callable[[float], None],
) -> T:
    """Run `fn` on a worker thread, calling `on_heartbeat(elapsed_seconds)` on the
    calling thread every `heartbeat_interval` seconds while it's still running.

    `fn`'s own timeout (e.g. `requests.post(timeout=...)`) still governs the
    max wait — this only adds visibility into "still waiting" vs "stuck",
    which a plain blocking call can't distinguish from the outside.
    """
    box: dict = {}

    def _target() -> None:
        try:
            box["result"] = fn()
        except Exception as e:  # noqa: BLE001 - re-raised on the caller's thread below
            box["error"] = e

    thread = threading.Thread(target=_target, daemon=True)
    start = time.monotonic()
    thread.start()
    while thread.is_alive():
        thread.join(timeout=heartbeat_interval)
        if thread.is_alive():
            try:
                on_heartbeat(time.monotonic() - start)
            except Exception:
                pass  # heartbeat logging must never break the actual call
    if "error" in box:
        raise box["error"]
    return box["result"]  # type: ignore[return-value]


def call_with_retry(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 20.0,
    heartbeat_interval: float | None = None,
    on_heartbeat: Callable[[float], None] | None = None,
) -> T:
    """Call `fn`, retrying on transient network/API errors with exponential backoff.

    If `heartbeat_interval`/`on_heartbeat` are given, `on_heartbeat(elapsed)` is
    called periodically while a single attempt is still in flight, so a slow
    call is visibly "still waiting" in the logs instead of looking identical
    to a stuck one until it finally times out.
    """
    def _attempt() -> T:
        if heartbeat_interval and on_heartbeat:
            return _run_with_heartbeat(fn, heartbeat_interval, on_heartbeat)
        return fn()

    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _attempt()
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            last_exc = e
            if status not in _RETRYABLE_STATUS_CODES or attempt == attempts:
                raise
            print(f"    ...HTTP {status} on attempt {attempt}/{attempts}, retrying", flush=True)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exc = e
            if attempt == attempts:
                raise
            print(f"    ...{type(e).__name__} on attempt {attempt}/{attempts}, retrying", flush=True)
        time.sleep(min(base_delay * (2 ** (attempt - 1)), max_delay))
    if last_exc:
        raise last_exc
    raise RuntimeError("call_with_retry: unreachable")
