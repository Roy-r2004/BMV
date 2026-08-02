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

    # `fn` runs off the calling thread, so it starts with an empty context unless
    # one is handed to it — and anything `fn` does that reads the request id or
    # the active stage would silently see the defaults.
    from app.application.services.ai_context import propagated_context

    thread = threading.Thread(target=propagated_context().run, args=(_target,), daemon=True)
    start = time.monotonic()
    thread.start()
    aborted = False
    while thread.is_alive():
        # Wake for whichever comes first: the next heartbeat, or the deadline.
        # This used to join for the full heartbeat interval and only then look
        # at `hard_deadline`, so the deadline's resolution was the heartbeat —
        # 20 s. A caller passing a 1 s cap still waited 20 s. Request 72 spent
        # 29 minutes that way: every ask past the request deadline got a tiny
        # budget, waited a full heartbeat regardless, failed, and failed over.
        wait = heartbeat_interval
        if hard_deadline is not None and not aborted:
            wait = min(wait, max(0.05, hard_deadline - (time.monotonic() - start)))
        thread.join(timeout=wait)
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
    ask_budget: float | None = None,
) -> T:
    """Call `fn`, retrying on transient network/API errors with exponential backoff.

    If `heartbeat_interval`/`on_heartbeat` are given, `on_heartbeat(elapsed)` is
    called periodically while a single attempt is still in flight, so a slow
    call is visibly "still waiting" in the logs instead of looking identical
    to a stuck one until it finally times out.

    `hard_deadline` caps a **single attempt's** total wall clock, which the
    socket timeout cannot — see `_run_with_heartbeat`.

    `ask_budget` caps the **whole ask**: every attempt plus every backoff sleep
    between them. Without it the two interact badly — `timeout=120` x
    `_WALL_CLOCK_BUDGET_FACTOR=2.5` x `attempts=2` is 600 s for one logical ask,
    and the caller then fails over to the next model and pays it again. Measured
    over requests 66-71, `z-ai/glm-5.2` is 6 % of calls and 37 % of the seconds
    at p95 233 s each; that tail is what a 540 s request deadline cannot absorb.

    An attempt that cannot finish inside what is left is not started, because
    starting it guarantees the budget is blown *and* nothing is returned.
    """
    started = time.monotonic()

    def _remaining() -> float | None:
        if ask_budget is None:
            return None
        return ask_budget - (time.monotonic() - started)

    def _attempt() -> T:
        attempt_cap = hard_deadline
        left = _remaining()
        if left is not None:
            attempt_cap = left if attempt_cap is None else min(attempt_cap, left)
        if heartbeat_interval and on_heartbeat:
            return _run_with_heartbeat(
                fn, heartbeat_interval, on_heartbeat, attempt_cap, on_deadline
            )
        return fn()

    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        left = _remaining()
        if left is not None and left <= 0:
            retry_log.warning(
                "ask budget of %.0fs exhausted before attempt %s/%s", ask_budget, attempt, attempts
            )
            break
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
        # Backoff is part of the ask, not free time beside it. At a 20 % 429 rate
        # over ~17 calls this is 30-70 s of pure sleep, and sleeping past the
        # budget spends it without ever making the next request.
        delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
        left = _remaining()
        if left is not None:
            delay = min(delay, max(0.0, left))
        if delay > 0:
            time.sleep(delay)
    if last_exc:
        raise last_exc
    raise requests.exceptions.Timeout(
        f"ask exceeded its {ask_budget:.0f}s budget before any attempt completed"
        if ask_budget is not None
        else "call_with_retry: no attempt completed"
    )
