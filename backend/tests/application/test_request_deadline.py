"""The request-scoped wall-clock deadline (roadmap Phase 1.1 / 1.3).

Every case here is named for something a measured run actually did. The
numbers come from the Phase 0.6 census over requests 66-71.
"""
from __future__ import annotations

import time

import pytest
import requests

from app.application.preview_app.ai_budget import budget_ai_provider
from app.application.services import request_deadline as rd
from app.infrastructure.ai_providers.retry import call_with_retry


class _StubAI:
    def __init__(self) -> None:
        self.calls = 0

    def ask_chat(self, model, messages, **kwargs) -> str:
        self.calls += 1
        return "ok"

    def ask_vision(self, model, prompt, image_path) -> str:
        self.calls += 1
        return "ok"


def test_a_retry_inherits_the_deadline_instead_of_minting_a_fresh_one() -> None:
    """`orchestrator` calls `generate_preview_app` twice on failure.

    If the inner call stamped its own deadline, the cap would bound one attempt
    and a failing run could spend 124 + 540 + 540. The scope is re-entrant for
    the same request on purpose.
    """
    with rd.request_deadline_scope(42, total_seconds=300) as outer:
        with rd.request_deadline_scope(42, total_seconds=999) as inner:
            assert inner is outer, "a nested scope for the same request must not re-arm"
            assert inner.total_seconds == 300

        # A *different* request is a different budget.
        with rd.request_deadline_scope(43, total_seconds=100) as other:
            assert other is not outer
            assert other.total_seconds == 100

        assert rd.current_deadline() is outer, "the outer scope must be restored"


def test_the_deadline_is_monotonic_not_wall_clock() -> None:
    """An NTP step or a container suspend must not hand a run more budget."""
    with rd.request_deadline_scope(1, total_seconds=60) as deadline:
        assert deadline.started_at <= time.monotonic()
        # `deadline_at` is derived from the monotonic start, never from a
        # datetime; a naive implementation reading the wall clock would drift.
        assert deadline.deadline_at == deadline.started_at + 60


def test_an_ask_never_outlives_the_request_that_owns_it() -> None:
    """One repair call was held open for 1,040 s.

    `timeout=120` x `_WALL_CLOCK_BUDGET_FACTOR=2.5` x `attempts=2` is 600 s for
    one ask, and the caller then failed over and paid it again.
    """
    # No deadline armed: the flat ceiling still applies.
    assert rd.ask_budget_seconds() == rd.DEFAULT_ASK_CEILING_SECONDS
    assert rd.ask_budget_seconds(9999) == rd.DEFAULT_ASK_CEILING_SECONDS
    assert rd.ask_budget_seconds(30) == 30

    with rd.request_deadline_scope(2, total_seconds=45):
        # The request has less left than the ask ceiling, so the request wins.
        assert rd.ask_budget_seconds() <= 45
        assert rd.ask_budget_seconds(9999) <= 45

    with rd.request_deadline_scope(3, total_seconds=10_000):
        # Plenty of request time, so the ask ceiling binds.
        assert rd.ask_budget_seconds() == rd.DEFAULT_ASK_CEILING_SECONDS


def test_an_expired_request_grants_zero_ask_time_not_a_token_second() -> None:
    """Zero means *do not call*, and the distinction is not cosmetic.

    This asserted `>= 1.0` when it was written, on the reasoning that a socket
    timeout must never be zero or negative. Request 72 proved that wrong in
    the worst way: past the deadline every ask got a 1 s budget,
    `_run_with_heartbeat` only checked its cap once per 20 s heartbeat, so each
    doomed call waited 20 s, failed, retried, and failed over. AppSpec spent
    **29 minutes past an expired deadline** making calls that could not succeed.

    Zero makes `call_with_retry` refuse before the first attempt — an immediate
    clean failure the caller's deterministic fallback already handles.
    """
    with rd.request_deadline_scope(4, total_seconds=-5) as deadline:
        assert deadline.expired()
        assert deadline.ask_budget() == 0.0
        assert rd.ask_budget_seconds() == 0.0

    # Unarmed callers are unaffected — they still get the flat ceiling.
    assert rd.ask_budget_seconds() == rd.DEFAULT_ASK_CEILING_SECONDS


def test_a_short_ask_budget_is_honoured_within_it_not_a_heartbeat_later() -> None:
    """The deadline's resolution used to be the heartbeat interval.

    `_run_with_heartbeat` joined for the full `heartbeat_interval` and only
    then compared elapsed against `hard_deadline`, so a 1 s cap under a 20 s
    heartbeat took 20 s to fire. That is the mechanism behind request 72.
    """
    def _never_returns():
        time.sleep(30)
        return "unreachable"

    started = time.monotonic()
    with pytest.raises(requests.exceptions.Timeout):
        call_with_retry(
            _never_returns,
            attempts=1,
            heartbeat_interval=20.0,     # far longer than the cap below
            on_heartbeat=lambda _elapsed: None,
            hard_deadline=1.0,
            on_deadline=lambda: None,
        )
    elapsed = time.monotonic() - started
    assert elapsed < 19.0, (
        f"a 1s cap took {elapsed:.1f}s — the deadline is still only checked once "
        "per heartbeat"
    )


def test_an_elective_stage_is_skipped_past_the_deadline_and_a_mandatory_one_degrades() -> None:
    """The degradation contract, which is the whole reason this is not a kill switch.

    Two of three observed runs already shipped nothing; a deadline that simply
    aborts trades a slow preview for no preview.
    """
    with rd.request_deadline_scope(5, total_seconds=-1) as deadline:
        assert rd.should_skip_elective("visual_critic") is True
        assert rd.should_skip_elective("codegen") is False, (
            "codegen is mandatory — it degrades, it does not vanish"
        )
        assert rd.claim_model_time("codegen") is False
        assert rd.claim_model_time("visual_critic") is False

        reasons = {(d["stage"], d["reason"]) for d in deadline.degradations()}
        assert ("visual_critic", "skipped_past_deadline") in reasons
        assert ("codegen", "deterministic_fallback_past_deadline") in reasons, (
            "a mandatory stage that fell back must not be recorded as skipped"
        )


def test_nothing_is_skipped_while_time_remains() -> None:
    with rd.request_deadline_scope(6, total_seconds=600) as deadline:
        assert rd.should_skip_elective("visual_critic") is False
        assert rd.claim_model_time("codegen") is True
        assert deadline.degradations() == []


def test_a_degradation_is_recorded_once_per_reason_not_once_per_loop() -> None:
    """A stage that degrades inside a loop must not bury the others."""
    with rd.request_deadline_scope(7, total_seconds=-1) as deadline:
        for _ in range(50):
            rd.record_degradation("quality_repair", "skipped_past_deadline")
        rd.record_degradation("quality_repair", "a_different_reason")
        assert len(deadline.degradations()) == 2
        assert deadline.degraded_stages() == ["quality_repair"]


def test_a_run_that_degraded_does_not_look_like_one_that_did_not() -> None:
    """The property the whole contract rests on."""
    with rd.request_deadline_scope(8, total_seconds=600) as clean:
        assert clean.degradations() == []
    with rd.request_deadline_scope(9, total_seconds=-1) as degraded:
        rd.should_skip_elective("refine")
        assert degraded.degradations() != []
        assert "refine" in degraded.degraded_stages()


def test_a_retry_is_refused_when_there_is_no_runway_for_it() -> None:
    """`orchestrator` retries the whole generation once on any exception."""
    with rd.request_deadline_scope(10, total_seconds=600):
        assert rd.has_retry_runway() is True
    with rd.request_deadline_scope(11, total_seconds=rd.MIN_RETRY_RUNWAY_SECONDS - 30):
        assert rd.has_retry_runway() is False
    # Unarmed (tests, CLI, chat refinement) must not be blocked.
    assert rd.has_retry_runway() is True


def test_budget_exhaustion_is_recorded_rather_than_silent() -> None:
    """`""` is indistinguishable from a model that answered with nothing.

    The return value is deliberately unchanged — see `BudgetedAIProvider._refuse`
    for why the raise is deferred to Phase 2 — so the *record* is what makes
    exhaustion visible.
    """
    underlying = _StubAI()
    with rd.request_deadline_scope(12, total_seconds=600) as deadline:
        wrapped = budget_ai_provider(underlying, request_key="deadline-budget", max_calls=1)
        try:
            assert wrapped.ask_chat("m", [{"role": "user", "content": "a"}]) == "ok"
            assert wrapped.ask_chat("m", [{"role": "user", "content": "b"}]) == ""
            assert wrapped.ask_vision("m", "p", "x.png") == ""
        finally:
            wrapped.close()
        assert underlying.calls == 1
        reasons = {(d["stage"], d["reason"]) for d in deadline.degradations()}
        assert ("ai_budget", "exhausted_chat") in reasons
        assert ("ai_budget", "exhausted_vision") in reasons


def test_the_ask_budget_bounds_every_attempt_and_every_backoff_together() -> None:
    """`hard_deadline` only ever capped a *single* attempt.

    So `attempts=2` doubled it, and the backoff between them was free time
    beside the budget rather than part of it.
    """
    attempts_started = 0

    def _always_times_out():
        nonlocal attempts_started
        attempts_started += 1
        time.sleep(0.25)
        raise requests.exceptions.Timeout("simulated")

    started = time.monotonic()
    with pytest.raises(requests.exceptions.Timeout):
        call_with_retry(
            _always_times_out,
            attempts=8,
            base_delay=10.0,   # would sleep 10s+ between attempts, unbudgeted
            max_delay=20.0,
            ask_budget=1.0,
        )
    elapsed = time.monotonic() - started

    assert elapsed < 5.0, (
        f"the ask ran {elapsed:.1f}s against a 1.0s budget — backoff is not being clamped"
    )
    assert attempts_started < 8, "an attempt that cannot finish in the budget must not start"


def test_no_ask_budget_leaves_the_old_behaviour_untouched() -> None:
    """Unarmed callers — CLI, tests, chat refinement — must not change."""
    calls = 0

    def _flaky():
        nonlocal calls
        calls += 1
        if calls < 2:
            raise requests.exceptions.ConnectionError("transient")
        return "done"

    assert call_with_retry(_flaky, attempts=3, base_delay=0.01) == "done"
    assert calls == 2
