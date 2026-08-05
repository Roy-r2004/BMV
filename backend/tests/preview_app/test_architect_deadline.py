"""The architect must name the deadline when it is the deadline that stopped it.

Request 74, one of three runs started 60 s apart on 2026-08-02: at t=540.4 s
`call_architect` started and raised 9 ms later with "Architect agent failed to
produce valid JSON". No model was asked anything — past the deadline every ask
budget is zero, so all three failover links refuse before the first byte. The
orchestrator logged the JSON message, decided the failure was transient, and
went looking for retry runway it did not have. The run stored no `preview_app`
at all.

What it must not do is end blaming a model that was never called.

**Updated 2026-08-05 (session 13).** When this file was written `architect` was
MANDATORY *and had no deterministic path*, so the sentence here read "the run
still ends here". It no longer does: `plan_phase` now falls back to the resolved
kind's blueprint in shadow mode (1.12, piece a), pinned by
`test_mandatory_stage_deterministic_paths.py`. `call_architect` itself is
unchanged and still raises — which is what these tests cover, and why they still
pass unaltered.
"""
from __future__ import annotations

import pytest

from app.application.preview_app.codegen import architect as architect_mod
from app.application.services import request_deadline as rd
from app.application.services.request_deadline import RequestDeadlineExceeded


class _Renderer:
    def render(self, *_args, **_kwargs) -> str:
        return "prompt"


class _CountingAI:
    def __init__(self) -> None:
        self.calls = 0

    def ask_chat(self, *_args, **_kwargs) -> str:
        self.calls += 1
        return ""


def test_the_architect_blames_the_deadline_not_the_model_when_out_of_time() -> None:
    ai = _CountingAI()
    with rd.request_deadline_scope(74, total_seconds=-1) as deadline:
        with pytest.raises(RequestDeadlineExceeded) as excinfo:
            architect_mod.call_architect(
                "context", {}, {}, {}, ai, _Renderer(),
            )

    assert excinfo.value.stage == "architect"
    assert "valid JSON" not in str(excinfo.value), (
        "the failure still names a parsing problem that never happened"
    )
    assert ai.calls == 0, (
        f"{ai.calls} model call(s) attempted past the deadline — the failover "
        "chain is being burned on asks that are refused before the first byte"
    )
    assert ("architect", "no_model_time_remaining") in {
        (d["stage"], d["reason"]) for d in deadline.degradations()
    }, "an architect that died on the clock left no record saying so"


def test_the_architect_is_untouched_while_the_request_has_time() -> None:
    """The guard must not change the in-budget path — that is the normal case."""

    class _GoodAI:
        def ask_chat(self, *_args, **_kwargs) -> str:
            return '{"routes": [{"path": "/"}]}'

    with rd.request_deadline_scope(78, total_seconds=600):
        result = architect_mod.call_architect(
            "context", {}, {}, {}, _GoodAI(), _Renderer(),
        )
    assert result == {"routes": [{"path": "/"}]}


def test_an_unarmed_caller_still_gets_the_old_json_failure() -> None:
    """CLI and chat-refinement callers have no deadline; nothing changes for them."""
    with pytest.raises(ValueError, match="valid JSON"):
        architect_mod.call_architect(
            "context", {}, {}, {}, _CountingAI(), _Renderer(),
        )


def test_the_architect_chain_asks_each_resolved_model_once(monkeypatch) -> None:
    """Phase 1 DoD: *zero consecutive asks to the same resolved model id.*

    Marked done and pinned by `test_fix_model_chain.py` — but that test pins the
    repair chains. The architect's was never deduped, and in this environment
    all three of its setting names resolve to `google/gemini-2.5-flash`.
    Requests 74, 75 and 76 each wrote consecutive same-model rows; request 74's
    architect wrote three, one model, all unusable, for one logical failure.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "ARCHITECT_MODEL", "same/model", raising=False)
    monkeypatch.setattr(settings, "PREVIEW_APP_MODEL", "same/model", raising=False)
    monkeypatch.setattr(settings, "TEXT_MODEL", "other/model", raising=False)

    asked: list[str] = []

    class _RecordingAI:
        def ask_chat(self, model, *_args, **_kwargs) -> str:
            asked.append(model)
            return "not json"

    with pytest.raises(ValueError):
        architect_mod.call_architect(
            "context", {}, {}, {}, _RecordingAI(), _Renderer(),
        )

    assert asked == ["same/model", "other/model"], (
        f"asked {asked} — a resolved model id is being asked twice in a row"
    )
    assert len(asked) == len(set(asked))
