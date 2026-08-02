"""End to end: a writer that got a 200 and could not use it says so.

The unit-level split lives in `tests/application/test_ai_call_telemetry.py`.
This file drives the real writers through a provider that records usage the way
the real one does, and asserts what actually lands in the row — because the
defect was never in the primitive, it was in nobody calling it.

Request 67's fix agent: three calls, two recorded `success = true`, zero applied
file operations. Request 68's quality repair: 882.2 s, seven calls, zero applied
operations. Both looked healthy in every query anyone ran.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

from app.application.preview_app.codegen.architect import call_architect  # noqa: E402
from app.application.services import admin_ops  # noqa: E402


class _RecordingProvider:
    """Answers from a script, and records usage exactly where the real one does.

    `record_usage` is called on the calling thread after the transport resolves,
    with `success = True` for any 200 — which is the whole point.
    """

    name = "openrouter"

    def __init__(self, answers: list[str], latency_ms: int = 20_000) -> None:
        self._answers = list(answers)
        self._latency_ms = latency_ms
        self.models_asked: list[str] = []

    def ask_chat(self, model: str, _messages, **_kwargs) -> str:
        self.models_asked.append(model)
        answer = self._answers.pop(0) if self._answers else ""
        admin_ops.record_usage(
            provider="openrouter",
            model=model,
            purpose="pipeline",
            success=True,
            latency_ms=self._latency_ms,
            finish_reason="stop",
            output_chars=len(answer),
        )
        return answer

    def ask_vision(self, model: str, _prompt: str, _image: str) -> str:
        return self.ask_chat(model, [])


@pytest.fixture(autouse=True)
def distinct_architect_models(monkeypatch):
    """Give the architect chain three genuinely different model ids.

    Without this the fixture contradicts the test names below. `ARCHITECT_MODEL`,
    `PREVIEW_APP_MODEL` and `TEXT_MODEL` all default to `google/gemini-2.5-flash`
    in this environment *and in production* — so "each failover link ... with its
    own model" was asserting `[m, m, m] == [m, m, m]`, which holds for any m.
    The chain now dedupes by resolved id (roadmap 1.2, which had only ever been
    applied to the repair chains), so a collapsed chain is one link, not three.

    These tests are about telemetry granularity — one row per link actually
    asked, with its own model, attempt and latency. Three distinct ids is the
    setup that exercises that; the collapse itself is pinned separately by
    `test_architect_deadline.py::test_the_architect_chain_asks_each_resolved_model_once`.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "ARCHITECT_MODEL", "vendor/model-a", raising=False)
    monkeypatch.setattr(settings, "PREVIEW_APP_MODEL", "vendor/model-b", raising=False)
    monkeypatch.setattr(settings, "TEXT_MODEL", "vendor/model-c", raising=False)


@pytest.fixture()
def rows(monkeypatch) -> list[dict]:
    captured: list[dict] = []
    monkeypatch.setattr(admin_ops, "flush_usage_rows", captured.extend)
    return captured


class _Renderer:
    def render(self, _template: str, **_kwargs) -> str:
        return "architect prompt"


def _architect(provider) -> dict:
    return call_architect("ctx", {}, {}, {}, provider, _Renderer())


def test_the_architect_link_that_returned_prose_is_not_a_success(rows) -> None:
    """Model one answers with an apology; model two answers with the routes.

    Both are HTTP 200. Only one of them moved the pipeline forward, and the
    first one still cost 20 s.
    """

    provider = _RecordingProvider(
        ["I'm sorry, I can't help with that.", json.dumps({"routes": [{"path": "/"}]})]
    )

    result = _architect(provider)

    assert result == {"routes": [{"path": "/"}]}
    assert len(rows) == 2
    assert [row["success"] for row in rows] == [True, True]
    assert [row["usable"] for row in rows] == [False, True]
    assert rows[0]["unusable_reason"] == "unparseable"
    assert rows[0]["stage"] == "architect"
    assert rows[0]["attempt"] == 1 and rows[1]["attempt"] == 2


def test_each_failover_link_is_its_own_row_with_its_own_model(rows) -> None:
    """Collapsing the chain into one row is how a model that always returns
    unparseable JSON keeps looking free."""

    provider = _RecordingProvider(["nope", "still nope", json.dumps({"routes": []})])

    _architect(provider)

    assert len(rows) == 3
    assert [row["model"] for row in rows] == provider.models_asked
    assert [row["writer"] for row in rows] == [
        f"architect:{model}" for model in provider.models_asked
    ]


def test_a_chain_that_never_parses_records_three_unusable_rows_and_raises(
    rows,
) -> None:
    provider = _RecordingProvider(["a", "b", "c"])

    with pytest.raises(ValueError, match="failed to produce valid JSON"):
        _architect(provider)

    assert len(rows) == 3
    assert all(row["success"] is True for row in rows)
    assert all(row["usable"] is False for row in rows)
    assert sum(row["latency_ms"] for row in rows) == 60_000


def test_the_wasted_wall_clock_is_readable_straight_off_the_rows(rows) -> None:
    """The number the census needs: seconds spent on 200s that bought nothing."""

    from app.application.services.ai_call_census import CallRecord, wasted_seconds

    provider = _RecordingProvider(["nope", json.dumps({"routes": []})], latency_ms=90_000)
    _architect(provider)

    records = [
        CallRecord(
            request_id=67,
            stage=row["stage"],
            model=row["model"],
            latency_ms=row["latency_ms"],
            success=row["success"],
            usable=row["usable"],
        )
        for row in rows
    ]
    dead_calls, dead_seconds = wasted_seconds(records)

    assert dead_calls == 1
    assert dead_seconds == pytest.approx(90.0)


def test_a_repair_plan_that_does_not_parse_is_recorded_unusable_with_zero_ops(
    rows, tmp_path
) -> None:
    """Request 68's shape: the plan never parsed, so nothing was applied."""

    from app.application.preview_app.quality_repair import run_ai_quality_repair

    workspace = tmp_path / "ws"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "App.tsx").write_text("export default function App() {}")

    provider = _RecordingProvider(["not json at all", "still not json"], latency_ms=300_000)

    touched = run_ai_quality_repair(workspace, {"routes": []}, ["broken_nav"], provider)

    assert touched == []
    assert len(rows) == 2
    assert all(row["success"] is True for row in rows), "both were HTTP 200"
    assert all(row["usable"] is False for row in rows)
    assert all(row["ops_applied"] == 0 for row in rows)
    assert all(row["stage"] == "quality_repair" for row in rows)
    assert sum(row["latency_ms"] for row in rows) == 600_000


def test_a_repair_round_with_no_issues_makes_no_call_at_all(rows, tmp_path) -> None:
    from app.application.preview_app.quality_repair import run_ai_quality_repair

    workspace = tmp_path / "ws"
    (workspace / "src").mkdir(parents=True)

    assert run_ai_quality_repair(workspace, {"routes": []}, [], _RecordingProvider([])) == []
    assert rows == []
