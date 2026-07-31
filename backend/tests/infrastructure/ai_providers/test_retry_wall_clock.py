"""A stalled AI call must not hold a pipeline stage open indefinitely.

`requests`' `timeout=` is a socket-inactivity timeout: any byte within the window
resets it. Request 45 sat on one typecheck-repair call for fourteen minutes with
`timeout=120` set, heartbeating "still waiting" the whole way, because the model
was trickling output. The socket timeout can't express "this attempt has had
long enough" — only a wall-clock deadline can.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402
import requests  # noqa: E402

from app.infrastructure.ai_providers import retry as retry_mod  # noqa: E402
from app.infrastructure.ai_providers.retry import call_with_retry  # noqa: E402


def test_closing_the_socket_surfaces_the_workers_own_error() -> None:
    """The normal path: `cancel_inflight` closes the socket and the read fails."""
    released = threading.Event()
    cancelled = threading.Event()

    def _dies_when_cancelled():
        released.wait(timeout=30)
        raise requests.exceptions.ConnectionError("socket closed under us")

    def _cancel() -> None:
        cancelled.set()
        released.set()

    started = time.monotonic()
    with pytest.raises(requests.exceptions.ConnectionError):
        call_with_retry(
            _dies_when_cancelled,
            attempts=1,
            base_delay=0,
            heartbeat_interval=0.05,
            on_heartbeat=lambda _elapsed: None,
            hard_deadline=0.2,
            on_deadline=_cancel,
        )
    elapsed = time.monotonic() - started

    assert cancelled.is_set(), "the provider's cancel hook must be called"
    assert elapsed < 5, f"the deadline did not stop the wait (took {elapsed:.1f}s)"


def test_a_worker_that_ignores_the_cancel_is_abandoned(monkeypatch) -> None:
    """Request 45's fourteen minutes: nothing must be able to wait forever."""
    monkeypatch.setattr(retry_mod, "_CANCEL_GRACE_SECONDS", 0.1)
    cancelled = threading.Event()

    def _unstoppable():
        time.sleep(30)
        return "never read"

    started = time.monotonic()
    with pytest.raises(requests.exceptions.Timeout):
        call_with_retry(
            _unstoppable,
            attempts=1,
            base_delay=0,
            heartbeat_interval=0.05,
            on_heartbeat=lambda _elapsed: None,
            hard_deadline=0.2,
            on_deadline=cancelled.set,
        )
    elapsed = time.monotonic() - started

    assert cancelled.is_set()
    assert elapsed < 5, f"the wait outlived its budget ({elapsed:.1f}s)"


def test_a_call_that_finishes_in_time_is_untouched() -> None:
    calls: list[float] = []

    def _fast():
        calls.append(time.monotonic())
        return "ok"

    result = call_with_retry(
        _fast,
        attempts=1,
        base_delay=0,
        heartbeat_interval=0.05,
        on_heartbeat=lambda _elapsed: None,
        hard_deadline=5,
        on_deadline=lambda: pytest.fail("cancel must not fire on a healthy call"),
    )

    assert result == "ok"
    assert len(calls) == 1


def test_no_deadline_keeps_the_previous_behaviour() -> None:
    def _slow_but_fine():
        time.sleep(0.15)
        return "done"

    assert (
        call_with_retry(
            _slow_but_fine,
            attempts=1,
            base_delay=0,
            heartbeat_interval=0.05,
            on_heartbeat=lambda _elapsed: None,
        )
        == "done"
    )


def test_the_provider_passes_a_budget_and_its_own_cancel_hook() -> None:
    """The wiring, not the mechanism: a deadline nobody passes is no deadline."""
    source = (
        BACKEND_DIR
        / "app" / "infrastructure" / "ai_providers" / "openrouter_provider.py"
    ).read_text(encoding="utf-8")

    assert "hard_deadline=timeout * _WALL_CLOCK_BUDGET_FACTOR" in source
    assert "on_deadline=self.cancel_inflight" in source


def main() -> None:
    test_closing_the_socket_surfaces_the_workers_own_error()
    test_a_call_that_finishes_in_time_is_untouched()
    test_no_deadline_keeps_the_previous_behaviour()
    test_the_provider_passes_a_budget_and_its_own_cancel_hook()
    print("retry wall-clock tests passed (4 tests; 1 needs pytest's monkeypatch)")


if __name__ == "__main__":
    main()
