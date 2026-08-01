"""The repair model chains, resolved to distinct ids.

Roadmap §1.2. `FIX_MODEL` defaults to `PREVIEW_APP_MODEL` and `QUALITY_FIX_MODEL`
defaults to `FIX_MODEL` (`config.py:300-312`), so on request 67 the gate repair's
four-name chain resolved to
`('z-ai/glm-5.2', 'z-ai/glm-5.2', 'google/gemini-2.5-flash', 'google/gemini-2.5-flash')`
— the same model asked twice in a row, twice. Every duplicate is a full timeout
paid for an answer already known.

Phase 1 DoD: *zero consecutive asks to the same resolved model id.*
"""
from __future__ import annotations

from pathlib import Path

import pytest

import app.application.preview_app.codegen.fix_agent as fa
from app.application.preview_app.quality_repair import request_quality_repair_plan
from app.core.config import settings


class _Issue:
    code = "dead_internal_link"
    message = "link to /nowhere"
    path = "src/pages/Home.tsx"


class _Recorder:
    """Answers nothing, so the whole chain is walked and every ask is visible."""

    def __init__(self, fail: set[str] | None = None) -> None:
        self.asked: list[str] = []
        self.fail = fail or set()
        self.answer = ""

    def ask_chat(self, model, _messages, **_kw):
        self.asked.append(model)
        if model in self.fail:
            raise RuntimeError("Provider output was truncated.")
        return self.answer


@pytest.fixture(autouse=True)
def _clean_failed_models(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(fa, "_FAILED_FIX_MODELS", set())


def _ws(tmp_path: Path) -> Path:
    (tmp_path / "src" / "pages").mkdir(parents=True)
    (tmp_path / "src" / "pages" / "Home.tsx").write_text("export default () => null\n")
    return tmp_path


def _set_request_67_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "QUALITY_FIX_MODEL", "z-ai/glm-5.2")
    monkeypatch.setattr(settings, "FIX_MODEL", "z-ai/glm-5.2")
    monkeypatch.setattr(settings, "PREVIEW_APP_MODEL", "google/gemini-2.5-flash")
    monkeypatch.setattr(settings, "TEXT_MODEL", "google/gemini-2.5-flash")


def test_a_failing_model_is_not_re_asked_under_its_other_setting_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Request 67's exact configuration, and where the wasted timeout came from.

    `QUALITY_FIX_MODEL` times out; the next entry is `FIX_MODEL`, which resolves
    to the same id, so the loop paid the identical timeout again before reaching
    a different provider.
    """
    _set_request_67_models(monkeypatch)
    ai = _Recorder(fail={"z-ai/glm-5.2"})
    ai.answer = '{"strategy": "ops", "ops": [{"op": "replace", "path": "src/pages/Home.tsx"}]}'

    request_quality_repair_plan(_ws(tmp_path), {"routes": []}, [_Issue()], ai)

    assert ai.asked == ["z-ai/glm-5.2", "google/gemini-2.5-flash"], ai.asked


def test_no_two_consecutive_asks_go_to_the_same_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Phase 1 DoD line, over the worst case: every model down, both attempts.

    Before dedupe this was eight asks to two providers, in pairs.
    """
    _set_request_67_models(monkeypatch)
    ai = _Recorder(fail={"z-ai/glm-5.2", "google/gemini-2.5-flash"})

    request_quality_repair_plan(_ws(tmp_path), {"routes": []}, [_Issue()], ai)

    assert len(ai.asked) == 4, ai.asked
    assert all(a != b for a, b in zip(ai.asked, ai.asked[1:])), ai.asked


def test_the_fix_agent_chain_is_deduplicated_too(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "FIX_MODEL", "z-ai/glm-5.2")
    monkeypatch.setattr(settings, "PREVIEW_APP_MODEL", "z-ai/glm-5.2")
    monkeypatch.setattr(settings, "TEXT_MODEL", "google/gemini-2.5-flash")
    ai = _Recorder()

    fa._ask_fix_model(ai, "prompt")

    assert ai.asked == ["z-ai/glm-5.2", "google/gemini-2.5-flash"], ai.asked


def test_a_model_that_fails_mid_loop_is_not_asked_later_in_the_same_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failed set was read once, when the list was built, and never again.

    A concurrent run recording a failure while this loop is walking the chain had
    no effect: the already-built list still asked the dead model.
    """
    monkeypatch.setattr(settings, "FIX_MODEL", "a/model")
    monkeypatch.setattr(settings, "PREVIEW_APP_MODEL", "b/model")
    monkeypatch.setattr(settings, "TEXT_MODEL", "c/model")

    asked: list[str] = []

    class _ConcurrentOutage:
        def ask_chat(self, model, _messages, **_kw):
            asked.append(model)
            if model == "a/model":
                # Another run discovers b/model is down while we are mid-chain.
                fa._FAILED_FIX_MODELS.add("b/model")
                return ""
            return '{"files": []}'

    assert fa._ask_fix_model(_ConcurrentOutage(), "prompt")

    assert asked == ["a/model", "c/model"], asked


def test_candidates_report_exhaustion_rather_than_returning_nothing() -> None:
    """An outage can end. An empty chain would disable repair for the worker's life."""
    fa._FAILED_FIX_MODELS.update({"a/model", "b/model"})

    candidates, exhausted = fa.fix_model_candidates(["a/model", "b/model", "a/model"])

    assert exhausted is True
    assert candidates == ["a/model", "b/model"]


def test_candidates_drop_empty_settings_and_preserve_order() -> None:
    candidates, exhausted = fa.fix_model_candidates(["", "b/model", None, "a/model", "b/model"])

    assert exhausted is False
    assert candidates == ["b/model", "a/model"]
