"""app/engine/llm.py - the single LLM boundary of the universal engine (design 15).

`ModelProvider.complete(ModelCall) -> ModelResponse` is the one seam between the
deterministic core and a language model. Three providers implement it:

  OpenRouterProvider  the only place under app/engine that imports app.ai.provider
                      (an AST test pins that); every call, success or failure, is
                      ledgered as an AiUsageEvent row and, through a store callback,
                      an engagement_model_calls row. This module has no ORM import
                      of its own: the ledger goes through _shared.log_usage and the
                      callback the persistence component provides.
  FakeProvider        deterministic, scripted per purpose (contracts section 9).
  RecordingProvider   record/replay cassettes keyed by ModelCall.prompt_hash(),
                      which folds purpose, schema_version and messages together,
                      so bumping a schema_version invalidates every recording made
                      against the old shape (S10) instead of replaying stale text.

`structured_call()` turns free text into a validated pydantic object: the JSON is
pulled out with the r30 extractors, validated with the caller's schema, retried
ONCE with the validation errors appended to the conversation, and otherwise
raised as StructuredFailure. It never fills a field in: a missing or malformed
answer becomes a QUESTION or a blocked ANALYSIS upstream, never a default that
would later print as if the model had said it (spec section 7, "unknown
information remains unknown").
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping, Protocol, Sequence

from app.pipeline._shared import extract_json_from_text, extract_json_objects

logger = logging.getLogger("consultant.engine.llm")

# The declared surface. app/engine/methods/contract.py imports ModelProvider
# under TYPE_CHECKING by this exact name; listing it here makes the export a
# promise rather than an accident of the file, so a rename breaks a test
# instead of silently turning MethodContext.provider into an unresolved string.
__all__ = [
    "ModelCall",
    "ModelResponse",
    "ModelProvider",
    "StructuredFailure",
    "FakeProvider",
    "OpenRouterProvider",
    "RecordingProvider",
    "structured_call",
    "ModelCallRecord",
    "RecordCallback",
]

# Values from an OpenRouter body that the ledger keeps. Anything else in
# `usage` is provider-specific noise that must not reach a typed row.
_USAGE_KEYS = ("prompt_tokens", "completion_tokens", "cost")


# =============================================================================
# 1. The contract (contracts.py section 9, verbatim)
# =============================================================================

@dataclass(frozen=True)
class ModelCall:
    purpose: str
    messages: tuple[Mapping[str, str], ...]
    model: str | None = None
    max_tokens: int = 4000
    budgets: tuple[int, ...] = ()           # escalating max_tokens on finish_reason == "length"
    schema: type | None = None
    schema_version: int = 1                 # S10 graft: bumps invalidate recorded cassettes
    engagement_id: str | None = None
    temperature: float | None = None

    def prompt_hash(self) -> str:
        body = json.dumps([dict(m) for m in self.messages], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(f"{self.purpose}|{self.schema_version}|{body}".encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ModelResponse:
    text: str | None
    finish_reason: str | None
    usage: Mapping[str, Any]
    call_id: str
    error: str | None = None


class ModelProvider(Protocol):
    def complete(self, call: ModelCall) -> ModelResponse: ...


class StructuredFailure(Exception):
    """structured_call() could not obtain schema-valid output after its one
    retry. Callers open a QUESTION or mark the ANALYSIS blocked; they never
    default a decision-carrying field."""


class FakeProvider:
    """Deterministic provider for tests and fake-mode benchmarks.

    script: purpose -> list of responses, each a str, an Exception (raised, to
    simulate an outage) or a callable(ModelCall) -> str. When a purpose's script
    is exhausted or absent, `oracle` (a case-agnostic callable, e.g. the
    structural oracle in app/engine/benchmark/oracle.py) answers; with no oracle
    the response is an empty JSON object, which every consumer treats as a real
    'nothing found' answer, never as a default.
    """

    def __init__(self, script: Mapping[str, Sequence[Any]] | None = None,
                 oracle: Callable[[ModelCall], str] | None = None):
        self._script = {k: list(v) for k, v in (script or {}).items()}
        self._oracle = oracle
        self.calls: list[ModelCall] = []
        self._n = 0

    def complete(self, call: ModelCall) -> ModelResponse:
        self.calls.append(call)
        self._n += 1
        call_id = f"{call.prompt_hash()[:16]}-{self._n}"
        queue = self._script.get(call.purpose)
        if queue:
            item = queue.pop(0)
            if isinstance(item, Exception):
                return ModelResponse(None, None, {}, call_id, error=str(item))
            text = item(call) if callable(item) else str(item)
        elif self._oracle is not None:
            text = self._oracle(call)
        else:
            text = "{}"
        return ModelResponse(text, "stop", {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}, call_id)


# =============================================================================
# 2. The real provider and its ledger
# =============================================================================

# What the persistence component receives per call, in the shape of an
# engagement_model_calls row. A plain dict keeps this module free of the ORM;
# the callback that turns it into a row lives in app/engine/persistence/store.py.
ModelCallRecord = dict[str, Any]
RecordCallback = Callable[[ModelCallRecord], None]


def _sha256(text: str | None) -> str | None:
    return None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean_usage(usage: Mapping[str, Any] | None) -> dict[str, Any]:
    usage = usage or {}
    return {k: usage.get(k) for k in _USAGE_KEYS if usage.get(k) is not None}


class OpenRouterProvider:
    """The one path from the engine to a paid model.

    Every call produces exactly one AiUsageEvent row (success or failure) and
    one engagement_model_calls record. The ledger counts calls, not attempts:
    `chat` already retries transient upstream conditions once internally and
    reports only the exhausted outcome, so a loud failure lands here as a
    success=False row rather than as quietly parsed truncated JSON (the
    in-200 upstream error detection in app/ai/provider.py is inherited).

    session_factory: a zero-arg callable returning a SQLAlchemy Session
    (app.database.SessionLocal by default; injected in tests). record_call: the
    persistence callback for the model-call ledger; None until the store wires
    it, in which case the AiUsageEvent row is still written - the cost ledger
    never depends on a component that may not have landed.
    """

    def __init__(self, *, session_factory: Callable[[], Any] | None = None,
                 record_call: RecordCallback | None = None,
                 default_model: str | None = None, timeout: float = 90.0):
        self._session_factory = session_factory
        self._record_call = record_call
        self._default_model = default_model
        self._timeout = timeout
        self._n = 0

    def _model(self, call: ModelCall) -> str:
        if call.model:
            return call.model
        if self._default_model:
            return self._default_model
        from app.config import settings
        return settings.ANALYSIS_MODEL

    def _session(self):
        if self._session_factory is not None:
            return self._session_factory()
        from app.database import SessionLocal
        return SessionLocal()

    def _ledger(self, call: ModelCall, model: str, *, usage: Mapping[str, Any] | None,
                success: bool, error: str | None, call_id: str, response_text: str | None,
                finish_reason: str | None) -> None:
        from app.pipeline._shared import log_usage

        screen = f"engagement:{call.engagement_id}" if call.engagement_id else None
        db = self._session()
        try:
            log_usage(
                db, None, provider="openrouter", model=model, purpose=f"engine:{call.purpose}",
                usage=dict(usage or {}), success=success, error=error, screen=screen,
            )
        finally:
            db.close()
        if self._record_call is not None:
            usage = usage or {}
            self._record_call({
                "call_id": call_id,
                "engagement_id": call.engagement_id,
                "purpose": call.purpose,
                "model": model,
                "schema_version": call.schema_version,
                "prompt_hash": call.prompt_hash(),
                "response_hash": _sha256(response_text),
                "max_tokens": call.max_tokens,
                "finish_reason": finish_reason,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "cost_usd": usage.get("cost"),
                "success": success,
                "error": error,
            })

    def complete(self, call: ModelCall) -> ModelResponse:
        # The only import of app.ai.provider under app/engine (design 15; pinned
        # by an AST test). Kept inside the method so importing this module in a
        # test never touches settings or httpx.
        from app.ai import provider as _provider

        self._n += 1
        call_id = f"{call.prompt_hash()[:16]}-{self._n}"
        model = self._model(call)
        messages = [dict(m) for m in call.messages]
        try:
            body = _provider.chat(model, messages, max_tokens=call.max_tokens,
                                  timeout=self._timeout, retries=1)
        except _provider.AiProviderError as exc:
            # A failed call is still a call: without this row an outage looks
            # like zero spend and zero attempts, and the engagement's blocked
            # analyses cannot be traced to the model that refused them.
            error = str(exc)[:500]
            self._ledger(call, model, usage=None, success=False, error=error, call_id=call_id,
                         response_text=None, finish_reason=None)
            return ModelResponse(None, None, {}, call_id, error=error)

        choice = (body.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content")
        finish_reason = choice.get("finish_reason")
        usage = _clean_usage(body.get("usage"))
        self._ledger(call, model, usage=usage, success=True, error=None, call_id=call_id,
                     response_text=text, finish_reason=finish_reason)
        return ModelResponse(text, finish_reason, usage, call_id)


# =============================================================================
# 3. Record / replay
# =============================================================================

def _cassette_key(call: ModelCall) -> str:
    """The replay key. prompt_hash() covers purpose, schema_version and the
    messages, so a recording is only ever replayed against the exact prompt
    AND the exact output shape it was made for: a bumped schema_version is a
    miss, never a stale answer validated against a new schema (S10)."""
    return call.prompt_hash()


class RecordingProvider:
    """Wraps a real provider and writes what it said to a JSON cassette; replays
    it afterwards without spend.

    A key holds a LIST of responses in call order, because one prompt can be
    issued more than once in a run (an escalated budget re-issues the same
    messages), and a replay must return the same sequence. A miss with no inner
    provider is an error response, which the engine treats like any outage -
    it never fabricates text.
    """

    def __init__(self, inner: ModelProvider | None, path: str):
        self._inner = inner
        self._path = path
        self._entries: dict[str, list[dict[str, Any]]] = {}
        self._cursor: dict[str, int] = {}
        self._n = 0
        self.hits = 0
        self.misses = 0
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            self._entries = {k: list(v) for k, v in (data.get("entries") or {}).items()}

    def _save(self) -> None:
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump({"entries": self._entries}, fh, indent=1, sort_keys=True, ensure_ascii=False)

    def complete(self, call: ModelCall) -> ModelResponse:
        self._n += 1
        call_id = f"{call.prompt_hash()[:16]}-{self._n}"
        key = _cassette_key(call)
        recorded = self._entries.get(key) or []
        index = self._cursor.get(key, 0)
        if index < len(recorded):
            self._cursor[key] = index + 1
            self.hits += 1
            entry = recorded[index]
            return ModelResponse(entry.get("text"), entry.get("finish_reason"), dict(entry.get("usage") or {}),
                                 call_id, error=entry.get("error"))
        self.misses += 1
        if self._inner is None:
            return ModelResponse(None, None, {}, call_id,
                                 error=f"cassette miss for purpose={call.purpose} schema_version={call.schema_version}")
        response = self._inner.complete(call)
        self._entries.setdefault(key, []).append({
            "text": response.text, "finish_reason": response.finish_reason,
            "usage": dict(response.usage), "error": response.error,
        })
        self._cursor[key] = len(self._entries[key])
        self._save()
        return response


# =============================================================================
# 4. Structured output
# =============================================================================

def _parse_json(text: str) -> dict:
    """The r30 extractor first (fenced or bare object), the salvage scanner as
    a fallback so a response whose outer wrapper is cut off still yields its
    first well-formed object; anything else is a ValueError for the retry."""
    try:
        return extract_json_from_text(text)
    except (ValueError, json.JSONDecodeError):
        objects = extract_json_objects(text)
        if objects:
            return objects[0]
        raise ValueError(f"No JSON object found in model response: {text[:200]}")


def _validate(schema: type, data: Any) -> Any:
    """Schema validation raises; it never constructs. A field the model did not
    return stays absent and is reported to the model on the retry - filling it
    from a default would print as a finding the model never made."""
    return schema.model_validate(data)


def _budgets(call: ModelCall) -> tuple[int, ...]:
    # The first budget is the call's own; the escalation ladder follows in
    # ascending order and only ever raises the cap (decompose.TECH_SPEC_BUDGETS).
    ladder = [call.max_tokens] + [b for b in sorted(call.budgets) if b > call.max_tokens]
    return tuple(ladder)


def _complete_with_budgets(provider: ModelProvider, call: ModelCall) -> tuple[ModelResponse, ModelCall]:
    """One logical completion: when the model reports it was cut off by the
    cap (finish_reason == "length"), re-issue with the next budget rather than
    parse the wreckage. Returns the last response and the call that produced it."""
    response: ModelResponse | None = None
    issued = call
    for budget in _budgets(call):
        issued = replace(call, max_tokens=budget)
        response = provider.complete(issued)
        if response.error is not None or response.finish_reason != "length":
            break
    assert response is not None
    return response, issued


def structured_call(provider: ModelProvider, call: ModelCall, schema: type | None = None) -> tuple[Any, ModelResponse]:
    """Obtain a schema-valid object from the model, or raise StructuredFailure.

    Steps: complete (escalating budgets on truncation) -> extract JSON ->
    schema.model_validate -> on failure, ONE retry whose conversation carries
    the model's own reply and the validation errors -> StructuredFailure.
    A provider error is a StructuredFailure immediately: there is no text to
    repair, and retrying an outage is the provider's job, not this function's.
    Returns (instance, last ModelResponse) so the caller can cite call_id in
    Provenance.model_call_id.
    """
    schema = schema or call.schema
    if schema is None:
        raise ValueError("structured_call needs a schema (call.schema or the schema argument)")
    current = call
    last_errors: str | None = None
    for attempt in range(2):
        response, issued = _complete_with_budgets(provider, current)
        if response.error is not None or response.text is None:
            raise StructuredFailure(f"{call.purpose}: provider error: {response.error or 'empty response'}")
        try:
            data = _parse_json(response.text)
            return _validate(schema, data), response
        except Exception as exc:  # ValueError, pydantic.ValidationError, TypeError from a non-object
            last_errors = str(exc)[:2000]
            if attempt == 0:
                logger.warning("structured_call retry: purpose=%s %s", call.purpose, last_errors[:200])
                current = replace(
                    issued,
                    messages=tuple(issued.messages) + (
                        {"role": "assistant", "content": response.text},
                        {"role": "user", "content": (
                            "Your previous reply did not validate. Errors:\n" + last_errors
                            + "\nReturn the corrected JSON object only, with every required field.")},
                    ),
                )
    raise StructuredFailure(f"{call.purpose}: no schema-valid output after one retry: {last_errors}")
