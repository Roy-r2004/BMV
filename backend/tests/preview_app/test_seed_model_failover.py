"""The seed asks a second model when the first one does not answer.

`mock_synthesize` was the one content-critical stage in the pipeline with no
failover: one hardcoded `attempt=1`, one model, and a silent deterministic
fallback to the plumbing mock when it failed. Measured over the 57 stored `seed`
asks in `ai_usage_events`:

    google/gemini-2.5-flash   requests 72-98    19 of 23 usable   mean 27.0 s
    deepseek/deepseek-v4-pro  requests 101+      4 of 31 usable   mean 66.1 s
    the last two trios (146-161)                 1 of 11 usable

Ten of those eleven are `provider_timeout` with `output_chars = 0`, six riding
the 120 s ask cap to the millisecond. Nothing looked broken because the failure
mode is a quiet fallback — which is how a hardware store shipped "Member
aftercare", "Follow-up visit" and `client_names: [… "Client 7", "Client 8"]`.

These tests pin the contract, not the models: which ids are in the chain is
settings, and the order is deliberately the owner's call.

`_valid_synthesized_mock_source` is stubbed throughout. The real one shells out
to `node` with the template's bundled `typescript.js` and returns False when
either is absent, so a test that used it would be testing the container's
node_modules rather than the failover.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.codegen import mock as mock_module


class _ChainAI:
    """Answers per model id: an Exception is raised, a string is returned."""

    def __init__(self, answers: dict[str, object]) -> None:
        self.answers = answers
        self.asked: list[str] = []

    def ask_chat(self, model, _messages, **_kwargs):
        self.asked.append(model)
        answer = self.answers.get(model, "")
        if isinstance(answer, Exception):
            raise answer
        return answer

    def ask_vision(self, *_a, **_k):  # pragma: no cover - unused here
        raise AssertionError("the seed never asks vision")


@pytest.fixture
def accept_everything(monkeypatch):
    monkeypatch.setattr(
        mock_module, "_valid_synthesized_mock_source", lambda content, _needed: bool(content)
    )


@pytest.fixture
def three_models(monkeypatch):
    monkeypatch.setattr(mock_module.settings, "PREVIEW_APP_MODEL", "primary/one")
    monkeypatch.setattr(mock_module.settings, "TEXT_MODEL", "second/two")
    monkeypatch.setattr(mock_module.settings, "ARCHITECT_MODEL", "third/three")


def test_a_timeout_on_the_primary_falls_over_to_the_next_model(
    accept_everything, three_models
):
    """Request 148's exact shape: the primary times out, and today that was the end."""

    ai = _ChainAI({
        "primary/one": TimeoutError("provider_timeout"),
        "second/two": "export const brand = {};",
    })

    assert mock_module._synthesize_mock_source(ai, "prompt", ["brand"]) == (
        "export const brand = {};"
    )
    assert ai.asked == ["primary/one", "second/two"]


def test_the_first_model_answering_ends_the_chain(accept_everything, three_models):
    ai = _ChainAI({"primary/one": "export const brand = {};"})

    assert mock_module._synthesize_mock_source(ai, "prompt", ["brand"]) is not None
    assert ai.asked == ["primary/one"], "a healthy primary must not cost a second ask"


def test_output_the_validator_rejects_falls_over_too(monkeypatch, three_models):
    """A rejection is not a transport failure, and it is still worth another model."""

    monkeypatch.setattr(
        mock_module,
        "_valid_synthesized_mock_source",
        lambda content, _needed: content.startswith("export"),
    )
    ai = _ChainAI({
        "primary/one": "I'm sorry, I can't help with that.",
        "second/two": "export const brand = {};",
    })

    assert mock_module._synthesize_mock_source(ai, "prompt", ["brand"]) == (
        "export const brand = {};"
    )
    assert ai.asked == ["primary/one", "second/two"]


def test_the_chain_is_deduped_so_one_model_is_never_asked_twice(
    accept_everything, monkeypatch
):
    """`call_architect`'s lesson: request 74 asked one model three times."""

    for name in ("PREVIEW_APP_MODEL", "TEXT_MODEL", "ARCHITECT_MODEL"):
        monkeypatch.setattr(mock_module.settings, name, "only/one")
    ai = _ChainAI({"only/one": TimeoutError("provider_timeout")})

    assert mock_module._synthesize_mock_source(ai, "prompt", ["brand"]) is None
    assert ai.asked == ["only/one"]


def test_every_model_failing_keeps_the_plumbing_mock(accept_everything, three_models):
    ai = _ChainAI({
        "primary/one": TimeoutError("provider_timeout"),
        "second/two": TimeoutError("provider_timeout"),
        "third/three": TimeoutError("provider_timeout"),
    })

    assert mock_module._synthesize_mock_source(ai, "prompt", ["brand"]) is None
    assert ai.asked == ["primary/one", "second/two", "third/three"]


def test_a_failover_link_is_not_started_without_time_to_finish(
    accept_everything, three_models, monkeypatch
):
    """The floor is the point: the one ask that ever succeeded took 63.9 s.

    Past the deadline `ask_budget_seconds()` is 0.0, so this is also what stops
    the chain from spending a budget the request has already lost.
    """

    monkeypatch.setattr(
        "app.application.services.request_deadline.ask_budget_seconds",
        lambda *_a, **_k: mock_module._SEED_FAILOVER_FLOOR_SECONDS - 0.1,
    )
    ai = _ChainAI({
        "primary/one": TimeoutError("provider_timeout"),
        "second/two": "export const brand = {};",
    })

    assert mock_module._synthesize_mock_source(ai, "prompt", ["brand"]) is None
    assert ai.asked == ["primary/one"], "a link too short to finish must not start"


def test_enough_time_lets_the_failover_run(accept_everything, three_models, monkeypatch):
    monkeypatch.setattr(
        "app.application.services.request_deadline.ask_budget_seconds",
        lambda *_a, **_k: mock_module._SEED_FAILOVER_FLOOR_SECONDS,
    )
    ai = _ChainAI({
        "primary/one": TimeoutError("provider_timeout"),
        "second/two": "export const brand = {};",
    })

    assert mock_module._synthesize_mock_source(ai, "prompt", ["brand"]) is not None
    assert ai.asked == ["primary/one", "second/two"]


def test_each_link_is_its_own_numbered_ask(accept_everything, three_models, monkeypatch):
    """One row per model, numbered — a chain collapsed into one row hides the cost."""

    seen: list[tuple[str, str, int]] = []
    real_ai_call = mock_module.ai_call

    def _spy(stage=None, *, writer=None, attempt=1, **kwargs):
        seen.append((stage, writer, attempt))
        return real_ai_call(stage, writer=writer, attempt=attempt, **kwargs)

    monkeypatch.setattr(mock_module, "ai_call", _spy)
    ai = _ChainAI({
        "primary/one": TimeoutError("provider_timeout"),
        "second/two": "export const brand = {};",
    })

    mock_module._synthesize_mock_source(ai, "prompt", ["brand"])

    assert seen == [("seed", "mock_synthesize", 1), ("seed", "mock_synthesize", 2)]


def test_a_dead_chain_records_a_degradation(accept_everything, three_models, monkeypatch):
    recorded: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.application.services.request_deadline.record_degradation",
        lambda stage, reason: recorded.append((stage, reason)),
    )
    ai = _ChainAI({m: TimeoutError("t") for m in ("primary/one", "second/two", "third/three")})

    assert mock_module._synthesize_mock_source(ai, "prompt", ["brand"]) is None
    assert ("codegen", "mock_synthesis_failed_plumbing_mock_kept") in recorded


def test_a_chain_that_only_wrote_junk_is_not_a_provider_failure(
    monkeypatch, three_models
):
    """Reached and rejected is a different fact from never answered.

    `test_a_rejected_mock_is_still_a_rejection_and_not_a_degradation` pins this
    from the outside; it is repeated here because the failover loop is where the
    two now meet, and a chain makes it easy to conflate them.
    """

    monkeypatch.setattr(
        mock_module, "_valid_synthesized_mock_source", lambda *_a: False
    )
    recorded: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.application.services.request_deadline.record_degradation",
        lambda stage, reason: recorded.append((stage, reason)),
    )
    ai = _ChainAI({m: "junk" for m in ("primary/one", "second/two", "third/three")})

    assert mock_module._synthesize_mock_source(ai, "prompt", ["brand"]) is None
    assert ai.asked == ["primary/one", "second/two", "third/three"]
    assert recorded == [], "every model answered — nothing was degraded"


def test_running_out_of_time_says_so_separately(accept_everything, three_models, monkeypatch):
    """Out of time and out of models are different failures and read differently."""

    recorded: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.application.services.request_deadline.record_degradation",
        lambda stage, reason: recorded.append((stage, reason)),
    )
    monkeypatch.setattr(
        "app.application.services.request_deadline.ask_budget_seconds",
        lambda *_a, **_k: 0.0,
    )
    ai = _ChainAI({"primary/one": TimeoutError("provider_timeout")})

    assert mock_module._synthesize_mock_source(ai, "prompt", ["brand"]) is None
    # Exactly one marker, and only this one. Out of time is a decision about the
    # request, not about each unasked model: a loop that kept going would stamp
    # it once per remaining link and then add a provider-failure marker on top,
    # so a reader could not tell one dead run from three.
    assert recorded == [("codegen", "mock_synthesis_failover_out_of_time")]
