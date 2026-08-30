"""Pins for app/engine/llm.py (design 15): the single LLM boundary.

Every real call is ledgered, success or failure; truncation escalates the
budget; invalid structured output is retried exactly once with the errors in
the prompt and then raised, never defaulted; cassettes replay only against the
exact schema_version they were recorded for; and only llm.py imports
app.ai.provider under app/engine.
"""
from __future__ import annotations

import ast
import json
import os

import pytest
from pydantic import BaseModel, ConfigDict

from app.ai import provider as ai_provider
from app.engine import llm as L

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "app", "engine")


class Strict(BaseModel):
    """A schema with a required field: the test for 'never defaults' must use
    a field the model can actually fail to return."""
    model_config = ConfigDict(extra="ignore")
    answer: str
    count: int


def _call(purpose: str = "extract_turn", text: str = "hello", **kw) -> L.ModelCall:
    return L.ModelCall(purpose=purpose, messages=({"role": "user", "content": text},),
                       engagement_id="E-1", model="fake/model", max_tokens=100, **kw)


def _body(text: str, finish_reason: str = "stop") -> dict:
    return {"choices": [{"message": {"content": text}, "finish_reason": finish_reason}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "cost": 0.001, "vendor_extra": 1}}


# ---------------------------------------------------------------------------
# Ledger fixture: the throwaway test database from tests/conftest.py.
# ---------------------------------------------------------------------------

@pytest.fixture
def ledger():
    from app.database import SessionLocal, init_db
    from app.models import AiUsageEvent

    init_db()

    def rows():
        db = SessionLocal()
        try:
            return [(e.purpose, e.success, e.error, e.screen, e.model, e.prompt_tokens, e.cost_usd)
                    for e in db.query(AiUsageEvent).filter(AiUsageEvent.purpose.like("engine:%")).order_by(AiUsageEvent.id)]
        finally:
            db.close()

    return rows


@pytest.fixture
def chat(monkeypatch):
    """Scripted app.ai.provider.chat; records every (model, messages, max_tokens)."""
    calls: list[dict] = []
    script: list = []

    def fake_chat(model, messages, *, max_tokens=2000, timeout=60.0, retries=1):
        calls.append({"model": model, "messages": messages, "max_tokens": max_tokens})
        item = script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(ai_provider, "chat", fake_chat)
    return {"calls": calls, "script": script}


# ---------------------------------------------------------------------------
# OpenRouterProvider and the ledger
# ---------------------------------------------------------------------------

def test_upstream_error_becomes_error_response_and_failed_ledger_row(chat, ledger):
    before = len(ledger())
    chat["script"].append(ai_provider.AiProviderError("OpenRouter 429: busy"))
    records: list[dict] = []
    provider = L.OpenRouterProvider(record_call=records.append)

    response = provider.complete(_call())

    assert response.error is not None and "429" in response.error
    assert response.text is None  # never partial JSON
    rows = ledger()[before:]
    assert len(rows) == 1
    purpose, success, error, screen, model, _, _ = rows[0]
    assert (purpose, success, screen, model) == ("engine:extract_turn", False, "engagement:E-1", "fake/model")
    assert "429" in error
    assert records and records[0]["success"] is False and records[0]["call_id"] == response.call_id


def test_success_ledgers_usage_and_model_call_record(chat, ledger):
    before = len(ledger())
    chat["script"].append(_body('{"answer": "x", "count": 1}'))
    records: list[dict] = []
    provider = L.OpenRouterProvider(record_call=records.append)
    call = _call()

    response = provider.complete(call)

    assert response.text == '{"answer": "x", "count": 1}' and response.finish_reason == "stop"
    assert response.usage == {"prompt_tokens": 3, "completion_tokens": 4, "cost": 0.001}  # vendor noise dropped
    assert response.call_id == call.prompt_hash()[:16] + "-1"
    purpose, success, error, screen, model, prompt_tokens, cost = ledger()[before:][0]
    assert (success, error, prompt_tokens, cost) == (True, None, 3, 0.001)
    rec = records[0]
    assert rec["prompt_hash"] == call.prompt_hash() and rec["schema_version"] == 1
    assert rec["response_hash"] is not None and rec["engagement_id"] == "E-1"


def test_every_call_yields_a_ledger_row_even_when_chat_raises(chat, ledger):
    before = len(ledger())
    chat["script"].extend([
        _body("{}"), ai_provider.AiProviderError("boom"), _body("{}"), ai_provider.AiProviderError("boom"),
    ])
    provider = L.OpenRouterProvider()
    for _ in range(4):
        provider.complete(_call())
    rows = ledger()[before:]
    assert len(rows) == 4
    assert [r[1] for r in rows] == [True, False, True, False]


def test_model_defaults_to_settings_analysis_model(chat, ledger):
    from app.config import settings
    chat["script"].append(_body("{}"))
    L.OpenRouterProvider().complete(L.ModelCall(purpose="p", messages=({"role": "user", "content": "x"},)))
    assert chat["calls"][-1]["model"] == settings.ANALYSIS_MODEL


# ---------------------------------------------------------------------------
# structured_call
# ---------------------------------------------------------------------------

def test_finish_reason_length_uses_next_budget(chat, ledger):
    chat["script"].extend([_body('{"answer": "cut', "length"), _body('{"answer": "ok", "count": 2}')])
    provider = L.OpenRouterProvider()
    call = _call(budgets=(400, 900))

    obj, response = L.structured_call(provider, call, Strict)

    assert obj.count == 2
    assert [c["max_tokens"] for c in chat["calls"]] == [100, 400]


def test_budget_ladder_stops_after_last_budget_and_reports_failure(chat, ledger):
    chat["script"].extend([_body("{", "length"), _body("{", "length"), _body("{", "length")])
    provider = L.OpenRouterProvider()
    with pytest.raises(L.StructuredFailure):
        L.structured_call(provider, _call(budgets=(400,)), Strict)
    # 100 -> 400 for the first attempt; the one retry keeps the budget that was
    # already needed (no budget above 400 exists, so no further escalation)
    assert [c["max_tokens"] for c in chat["calls"]] == [100, 400, 400]


def test_invalid_json_retries_exactly_once_with_errors_in_prompt():
    provider = L.FakeProvider(script={"extract_turn": ['{"answer": "x"}', '{"answer": "x", "count": 5}']})

    obj, _ = L.structured_call(provider, _call(), Strict)

    assert obj.count == 5
    assert len(provider.calls) == 2
    retry = provider.calls[1]
    assert retry.messages[-2] == {"role": "assistant", "content": '{"answer": "x"}'}
    assert "count" in retry.messages[-1]["content"] and "did not validate" in retry.messages[-1]["content"]


def test_still_invalid_after_retry_raises_never_defaults():
    provider = L.FakeProvider(script={"extract_turn": ['{"answer": "x"}', 'not json at all']})
    with pytest.raises(L.StructuredFailure):
        L.structured_call(provider, _call(), Strict)
    assert len(provider.calls) == 2  # exactly one retry, no third attempt


def test_provider_error_is_structured_failure_without_retry():
    provider = L.FakeProvider(script={"extract_turn": [RuntimeError("outage")]})
    with pytest.raises(L.StructuredFailure):
        L.structured_call(provider, _call(), Strict)
    assert len(provider.calls) == 1


def test_json_salvaged_from_prose_and_fences():
    provider = L.FakeProvider(script={"extract_turn": ['Sure:\n```json\n{"answer": "a", "count": 1}\n```']})
    obj, _ = L.structured_call(provider, _call(), Strict)
    assert obj.answer == "a"


# ---------------------------------------------------------------------------
# Cassettes
# ---------------------------------------------------------------------------

def test_cassette_replays_recorded_text_and_bumped_schema_version_misses(tmp_path):
    path = str(tmp_path / "cassette.json")
    inner = L.FakeProvider(script={"extract_turn": ["recorded text"]})
    recorder = L.RecordingProvider(inner, path)
    call = _call(schema_version=1)
    assert recorder.complete(call).text == "recorded text"
    assert recorder.misses == 1

    replay = L.RecordingProvider(None, path)
    hit = replay.complete(call)
    assert hit.text == "recorded text" and hit.error is None
    assert replay.hits == 1

    # A FRESH replay instance: the in-order cursor above has already consumed
    # the one recording, so asking the same instance would miss for the wrong
    # reason and a key that ignored schema_version would go unnoticed.
    fresh = L.RecordingProvider(None, path)
    missed = fresh.complete(L.ModelCall(purpose=call.purpose, messages=call.messages, schema_version=2,
                                        engagement_id="E-1", model="fake/model", max_tokens=100))
    assert missed.error is not None and missed.text is None
    assert fresh.misses == 1 and fresh.hits == 0


def test_cassette_replays_a_repeated_prompt_in_order(tmp_path):
    path = str(tmp_path / "cassette.json")
    inner = L.FakeProvider(script={"p": ["first", "second"]})
    recorder = L.RecordingProvider(inner, path)
    call = L.ModelCall(purpose="p", messages=({"role": "user", "content": "x"},))
    recorder.complete(call)
    recorder.complete(call)
    with open(path, encoding="utf-8") as fh:
        assert len(json.load(fh)["entries"][call.prompt_hash()]) == 2
    replay = L.RecordingProvider(None, path)
    assert [replay.complete(call).text for _ in range(2)] == ["first", "second"]
    assert replay.complete(call).error is not None


# ---------------------------------------------------------------------------
# The AST pin: one boundary
# ---------------------------------------------------------------------------

def _imports_ai_provider(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name.startswith("app.ai") for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.startswith("app.ai") or (mod == "app" and any(a.name == "ai" for a in node.names)):
                return True
    return False


def test_only_llm_imports_app_ai_provider():
    offenders = []
    for root, _, files in os.walk(ENGINE_DIR):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), path)
            if _imports_ai_provider(tree):
                offenders.append(os.path.relpath(path, ENGINE_DIR))
    assert offenders == ["llm.py"]


def test_model_provider_is_exported_under_that_name_for_contract_py():
    # app/engine/methods/contract.py does `from app.engine.llm import ModelProvider`
    # under TYPE_CHECKING. Resolve it the way a type checker would, and pin that
    # the name is a declared export whose protocol still names `complete`, so a
    # rename or a dropped method breaks here rather than in every method file.
    assert "ModelProvider" in L.__all__
    proto = getattr(L, "ModelProvider")
    assert "complete" in getattr(proto, "__protocol_attrs__", set(proto.__dict__))
    with open(os.path.join(ENGINE_DIR, "methods", "contract.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "app.engine.llm"
        for alias in node.names
    }
    assert imported <= set(L.__all__), imported - set(L.__all__)
    # FakeProvider satisfies the protocol structurally: the same seam every
    # method receives in tests and in fake-mode benchmarks.
    assert callable(getattr(L.FakeProvider(), "complete"))


def test_llm_source_is_pure_ascii():
    with open(os.path.join(ENGINE_DIR, "llm.py"), "rb") as fh:
        assert all(b < 128 for b in fh.read())
