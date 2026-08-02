"""Smoke test for BmvLogger and WatchBmv.

Converted from a `main()` that pytest never collected (roadmap 0.9). The
original asserted nothing — it made the calls, printed "logging smoke test OK",
and left a human to read the output. The conversion preserved that faithfully,
which meant it could only fail by raising.

These assert what the original was looking at. `WatchBmv`'s "finished in Ns"
line in particular is load-bearing: it is the only per-stage timing the pipeline
emits, and a silent regression in it is invisible until someone tries to profile
a run and finds nothing to read.
"""
from __future__ import annotations

import logging

from app.infrastructure.logging import WatchBmv, configure_logging, get_logger


def test_bmv_logger_and_watch_bmv_smoke(caplog) -> None:
    configure_logging("debug")
    log = get_logger("LoggingSmokeTest")

    with caplog.at_level(logging.DEBUG, logger="bmv.LoggingSmokeTest"):
        log.trace("trace message")
        log.debug("debug message")
        log.info("info message")
        log.warning("warning message")
        with WatchBmv("smoke-section", log):
            sum(range(1000))

    # Every line carries a `timestamp | Owner:lineno | ` prefix, so these are
    # substring checks by necessity, not laziness.
    messages = [record.getMessage() for record in caplog.records]

    def _logged(fragment: str) -> bool:
        return any(fragment in message for message in messages)

    assert _logged("debug message")
    assert _logged("info message")
    assert _logged("warning message")
    # `trace` sits below DEBUG, so `configure_logging("debug")` filters it. That
    # is correct behaviour, and asserting its absence pins the level ordering.
    assert not _logged("trace message"), "trace leaked through a debug-level filter"

    assert _logged("▶ smoke-section started"), f"no WatchBmv start line: {messages}"
    finished = [m for m in messages if "■ smoke-section finished in" in m]
    assert finished, f"no WatchBmv finish line: {messages}"
    assert finished[0].rstrip().endswith("s"), finished[0]


def test_watch_bmv_returns_the_elapsed_time_it_logged() -> None:
    """`stop()` is used for its return value as well as its log line."""
    watch = WatchBmv("measured-section", get_logger("LoggingSmokeTest")).start()
    sum(range(1000))
    elapsed = watch.stop()

    assert elapsed > 0.0
    assert watch.elapsed() >= elapsed


def test_stopping_a_watch_that_never_started_does_not_raise() -> None:
    """It warns and returns 0.0 — a mis-sequenced timer must not fail a run."""
    assert WatchBmv("never-started", get_logger("LoggingSmokeTest")).stop() == 0.0
