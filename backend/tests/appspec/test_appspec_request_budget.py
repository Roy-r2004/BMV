"""AppSpec's ceiling is per request, and it will not spend the pipeline's runway.

Measured on the first funded trio (requests 92, 93, 94): 7, 6 and 10 AI calls
against a configured `APPSPEC_MAX_CALLS = 6`, and not one budget-exhausted line
in the container log. The ceiling was held on the provider instance, and the
stage is entered **twice** a generation — `orchestrator` defines the contract
and `preview_app.pipeline.appspec_gate` confirms it. Each entry minted a fresh
budget, so the configured number bounded nothing.

The second entry is meant to be free: `ensure_approved_app_spec` returns
`reused=True, calls_used=0` when a revision with the same source digest is
already accepted. It re-authors from scratch instead whenever nothing was
accepted, which on those three runs was always — all 18 revisions are
`rejected`, so the confirming pass repeated the whole authoring chain. Requests
92 and 94 each spent about half of the stage's AI time doing the work twice,
finished appspec with 91 s and 136 s of a 540 s budget left, and stored no
`preview_app` at all.

So there are two different bounds here and only one of them protects the
artifact. A call budget bounds how often the stage asks. Only the runway
reservation stops it eating the time `architect` and `codegen` have yet to
spend — which is the failure that produced an empty record twice in one trio.
"""
from __future__ import annotations

import pytest

from app.application.appspec.generation import (
    AppSpecCallBudgetExceeded,
    _StageLimitedAIProvider,
)
from app.application.services import request_deadline as rd


class _CountingAI:
    def __init__(self) -> None:
        self.calls = 0

    def ask_chat(self, *_args, **_kwargs) -> str:
        self.calls += 1
        return "{}"

    def ask_vision(self, *_args, **_kwargs) -> str:
        self.calls += 1
        return "{}"


def _spend(provider: _StageLimitedAIProvider, attempts: int) -> int:
    """Ask until the budget refuses. Returns the number of asks that landed."""

    landed = 0
    for _ in range(attempts):
        try:
            provider.ask_chat("model", [])
        except AppSpecCallBudgetExceeded:
            break
        landed += 1
    return landed


def test_a_second_entry_into_appspec_continues_the_budget_it_does_not_reset_it() -> None:
    ai = _CountingAI()
    with rd.request_deadline_scope(92, total_seconds=10_000):
        first = _StageLimitedAIProvider(ai, 3)
        second = _StageLimitedAIProvider(ai, 3)

        landed = _spend(first, 3) + _spend(second, 3)

    # Per instance this is 6 — which is exactly how 92/93/94 made 7, 6 and 10
    # calls against a configured 6.
    assert landed == 3
    assert ai.calls == 3


def test_the_request_wide_tally_survives_a_provider_that_never_asked() -> None:
    """The tally is the deadline's, so a fresh instance inherits the spend."""

    ai = _CountingAI()
    with rd.request_deadline_scope(93, total_seconds=10_000) as deadline:
        _spend(_StageLimitedAIProvider(ai, 2), 2)
        assert deadline.stage_calls_used("appspec") == 2

        fresh = _StageLimitedAIProvider(ai, 2)
        assert _spend(fresh, 2) == 0
        # The refusal is recorded on the run, not just raised at the caller.
        assert any(
            entry["stage"] == "appspec"
            and entry["reason"] == "call_budget_exhausted"
            for entry in deadline.degradations()
        )


def test_appspec_will_not_start_a_call_that_leaves_the_pipeline_no_runway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bound that decides whether a run has a preview at all.

    Sized to the corpus: across requests 77-94 the five runs that reached
    `ready` needed 284.6 s to 504.9 s after their last appspec call. Request 92
    left 91 s and stored nothing.
    """

    from app.core import config as config_mod

    monkeypatch.setattr(
        config_mod.settings, "APPSPEC_DOWNSTREAM_RESERVE_SECONDS", 280.0, raising=False
    )
    ai = _CountingAI()

    # 200 s left: more than enough for one ask, and less than the pipeline
    # behind it has ever shipped on.
    with rd.request_deadline_scope(94, total_seconds=200) as deadline:
        provider = _StageLimitedAIProvider(ai, 8)
        with pytest.raises(AppSpecCallBudgetExceeded) as excinfo:
            provider.ask_chat("model", [])

        assert ai.calls == 0
        assert "runway" in str(excinfo.value)
        assert any(
            entry["stage"] == "appspec"
            and entry["reason"] == "stopped_low_downstream_runway"
            for entry in deadline.degradations()
        )
        # Refusing on runway must not silently eat the call budget too — the
        # two degrade for different reasons and are counted separately.
        assert deadline.stage_calls_used("appspec") == 0


def test_a_run_with_runway_to_spare_is_not_bounded_by_the_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guards the other direction: request 83 shipped with appspec ending at
    306 s, and a reservation fitted too high would have refused its last call."""

    from app.core import config as config_mod

    monkeypatch.setattr(
        config_mod.settings, "APPSPEC_DOWNSTREAM_RESERVE_SECONDS", 280.0, raising=False
    )
    ai = _CountingAI()
    with rd.request_deadline_scope(83, total_seconds=285):
        assert _spend(_StageLimitedAIProvider(ai, 8), 4) == 4


def test_both_ceilings_are_sized_to_the_corpus_not_to_a_round_number() -> None:
    """Each number here would have changed a real run's outcome.

    `APPSPEC_MAX_CALLS` is now spent per request rather than per entry, so the
    old 6 is a different and much tighter bound than it was. Request 87's
    AppSpec was accepted on its **7th** call; a request-wide 6 refuses that call
    and loses the only accepted contract in that run.

    The reservation is bounded on both sides. Below ~235 s no run in requests
    77-94 ever completed the pipeline; above 284.6 s it starts refusing calls
    that shipped runs made — that is request 83, which reached `ready` with its
    last appspec call ending at 306 s.
    """

    from app.core.config import settings

    assert settings.APPSPEC_MAX_CALLS >= 7
    assert 235.0 <= settings.APPSPEC_DOWNSTREAM_RESERVE_SECONDS <= 284.0


def test_without_an_armed_deadline_the_ceiling_stays_per_instance() -> None:
    """Admin re-runs and tests have no request clock; nothing may depend on one."""

    ai = _CountingAI()
    assert rd.current_deadline() is None
    assert _spend(_StageLimitedAIProvider(ai, 2), 5) == 2
    assert _spend(_StageLimitedAIProvider(ai, 2), 5) == 2


class _RaisingAI:
    """Errors N times, then answers — request 143's error-cut authoring shape."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def ask_chat(self, *_args, **_kwargs) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("provider stream cut")
        return "{}"


def test_an_errored_call_is_refunded_not_spent() -> None:
    """R6: an errored $0 call must not consume the budget an ANSWER needs.

    143's authoring attempt 1 was error-cut and still spent a unit of
    `APPSPEC_MAX_CALLS`; with a budget of 2, two cuts would have left the
    stage unable to hear a single answer."""

    ai = _RaisingAI(failures=2)
    with rd.request_deadline_scope(143, total_seconds=10_000) as deadline:
        provider = _StageLimitedAIProvider(ai, 2)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                provider.ask_chat("model", [])
        # Both errored asks refunded — the full budget is still there.
        assert deadline.stage_calls_used("appspec") == 0
        assert provider.calls_used == 0
        # The answered asks then spend it for real, and the ceiling holds.
        assert _spend(provider, 5) == 2
        assert deadline.stage_calls_used("appspec") == 2


def test_answered_asks_are_never_refunded() -> None:
    """The refund pairs ONLY with a raise — a returned answer spends for good,
    or the ceiling stops bounding anything."""

    ai = _CountingAI()
    with rd.request_deadline_scope(146, total_seconds=10_000) as deadline:
        provider = _StageLimitedAIProvider(ai, 3)
        assert _spend(provider, 10) == 3
        assert deadline.stage_calls_used("appspec") == 3

    ai2 = _CountingAI()
    assert rd.current_deadline() is None
    provider2 = _StageLimitedAIProvider(ai2, 2)
    assert _spend(provider2, 6) == 2
    assert provider2.calls_used == 2


def test_the_refund_never_goes_below_zero() -> None:
    with rd.request_deadline_scope(147, total_seconds=10_000) as deadline:
        deadline.refund_stage_call("appspec")
        assert deadline.stage_calls_used("appspec") == 0
