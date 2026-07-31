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

from app.infrastructure.logging import get_logger

retry_log = get_logger("AIRetry")

T = TypeVar("T")

_RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

#: After the socket is closed under it, how long to let the worker surface its own
#: error before we stop waiting on a thread that may never return.
_CANCEL_GRACE_SECONDS = 15.0


def _run_with_heartbeat(
    fn: Callable[[], T],
    heartbeat_interval: float,
    on_heartbeat: Callable[[float], None],
    hard_deadline: float | None = None,
    on_deadline: Callable[[], None] | None = None,
) -> T:
    """Run `fn` on a worker thread, calling `on_heartbeat(elapsed_seconds)` on the
    calling thread every `heartbeat_interval` seconds while it's still running.

    `fn`'s own timeout is a *socket inactivity* timeout, not a ceiling: any byte
    within the window resets it, so a model that trickles output holds the
    connection indefinitely. Request 45 sat on one repair call for fourteen
    minutes with `timeout=120` set. `hard_deadline` is the total wall-clock cap;
    when it passes, `on_deadline` (the provider's `cancel_inflight`) closes the
    socket under the worker and this raises `requests.Timeout`.
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
    aborted = False
    while thread.is_alive():
        thread.join(timeout=heartbeat_interval)
        if not thread.is_alive():
            break
        elapsed = time.monotonic() - start
        if hard_deadline is not None and elapsed >= hard_deadline and not aborted:
            aborted = True
            retry_log.warning(
                "hard deadline hit after %.0fs (cap %.0fs) — cancelling the in-flight call",
                elapsed,
                hard_deadline,
            )
            if on_deadline is not None:
                try:
                    on_deadline()
                except Exception:
                    pass
            # The socket is closed; give the worker a moment to surface its own
            # error, then stop waiting on a thread that may never return.
            thread.join(timeout=_CANCEL_GRACE_SECONDS)
            if thread.is_alive():
                raise requests.exceptions.Timeout(
                    f"call exceeded its {hard_deadline:.0f}s wall-clock budget"
                )
            break
        try:
            on_heartbeat(elapsed)
        except Exception:
            pass  # heartbeat logging must never break the actual call
    if "error" in box:
        raise box["error"]
    if "result" not in box:
        raise requests.exceptions.Timeout("call was cancelled before returning a result")
    return box["result"]  # type: ignore[return-value]


def call_with_retry(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 20.0,
    heartbeat_interval: float | None = None,
    on_heartbeat: Callable[[float], None] | None = None,
    hard_deadline: float | None = None,
    on_deadline: Callable[[], None] | None = None,
) -> T:
    """Call `fn`, retrying on transient network/API errors with exponential backoff.

    If `heartbeat_interval`/`on_heartbeat` are given, `on_heartbeat(elapsed)` is
    called periodically while a single attempt is still in flight, so a slow
    call is visibly "still waiting" in the logs instead of looking identical
    to a stuck one until it finally times out.

    `hard_deadline` caps a single attempt's total wall clock, which the socket
    timeout cannot — see `_run_with_heartbeat`.
    """
    def _attempt() -> T:
        if heartbeat_interval and on_heartbeat:
            return _run_with_heartbeat(
                fn, heartbeat_interval, on_heartbeat, hard_deadline, on_deadline
            )
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
            from app.application.services.ai_context import (
                observe_ai_transport_retry,
            )

            observe_ai_transport_retry()
            retry_log.warning("HTTP %s on attempt %s/%s, retrying", status, attempt, attempts)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exc = e
            if attempt == attempts:
                raise
            from app.application.services.ai_context import (
                observe_ai_transport_retry,
            )

            observe_ai_transport_retry()
            retry_log.warning("%s on attempt %s/%s, retrying", type(e).__name__, attempt, attempts)
        time.sleep(min(base_delay * (2 ** (attempt - 1)), max_delay))
    if last_exc:
        raise last_exc
    raise RuntimeError("call_with_retry: unreachable")
