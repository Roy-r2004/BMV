"""Context for attributing AI usage to the active request / stage.

Three things live here.

**Attribution.** `ai_run_scope` binds every AI call made under it to a request id
and a coarse purpose. It is a `ContextVar`, so it follows `await` but *not* a
bare `threading.Thread` or a `ThreadPoolExecutor.submit` — see
`propagated_context()` and its two callers (`preview_app/parallel.py`,
`ai_providers/retry.py`). Before those were wired, 39 of request 67's 58 usage
rows carried `request_id = NULL` and a degraded purpose, because every call the
codegen / critic / vision fan-outs made ran on a pool thread with an empty
context. Per-request queries undercounted by roughly two thirds.

**The call census (Phase 0.6).** `ai_call` wraps *one logical ask plus the parse
that decides whether its output was any use*. Rows recorded inside the scope are
buffered, stamped with `stage` / `writer` / `attempt` / `usable` / `ops_applied`,
and written once at exit — so adjudication costs no extra database round trip.
Scopes nest: an inner scope freezes its own verdict onto its own rows and then
hands them to its parent, and only the outermost scope writes. That is how a
repair writer can say "this ask parsed" at the ask, and "the plan it produced
applied four operations" three function calls later.

**Usable is not 200.** `success` on `ai_usage_events` means the transport
returned something. `usable` means the pipeline could act on it. Request 67
recorded two of its three dead fix-agent calls as `success = true`; they were
200s carrying JSON no extractor could parse. Treating those as successes is what
hid the cost.
"""
from __future__ import annotations

import contextvars
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

_ai_request_id: ContextVar[int | None] = ContextVar("ai_request_id", default=None)
_ai_purpose: ContextVar[str | None] = ContextVar("ai_purpose", default=None)
_ai_stage_capture: ContextVar["AIStageTelemetryCapture | None"] = ContextVar(
    "ai_stage_capture",
    default=None,
)
_ai_call: ContextVar["AICall | None"] = ContextVar("ai_call", default=None)

#: Why a recorded call produced nothing the pipeline could use. `transport` and
#: `truncated` and `empty` are decided by the provider; everything else is the
#: adjudication of whoever had to read the output.
UNUSABLE_TRANSPORT = "transport"
UNUSABLE_EMPTY = "empty"
UNUSABLE_TRUNCATED = "truncated"
UNUSABLE_UNPARSEABLE = "unparseable"
UNUSABLE_REJECTED = "rejected"


@dataclass
class AIStageTelemetryCapture:
    usage_events: list[dict[str, object]] = field(default_factory=list)
    transport_retry_count: int = 0


def get_ai_request_id() -> int | None:
    return _ai_request_id.get()


def get_ai_purpose() -> str | None:
    return _ai_purpose.get()


def set_ai_purpose(purpose: str | None) -> None:
    _ai_purpose.set((purpose or "")[:80] or None)


def observe_ai_usage(payload: dict[str, object]) -> None:
    capture = _ai_stage_capture.get()
    if capture is not None:
        capture.usage_events.append(dict(payload))


def observe_ai_transport_retry() -> None:
    capture = _ai_stage_capture.get()
    if capture is not None:
        capture.transport_retry_count += 1


@contextmanager
def ai_run_scope(request_id: int | None, purpose: str | None = None) -> Iterator[None]:
    """Bind AI calls in this thread/task to a request (and optional purpose)."""
    tok_id = _ai_request_id.set(request_id)
    tok_purpose = _ai_purpose.set((purpose[:80] if purpose else None))
    try:
        yield
    finally:
        _ai_request_id.reset(tok_id)
        _ai_purpose.reset(tok_purpose)


@contextmanager
def capture_ai_stage_telemetry() -> Iterator[AIStageTelemetryCapture]:
    capture = AIStageTelemetryCapture()
    token = _ai_stage_capture.set(capture)
    try:
        yield capture
    finally:
        _ai_stage_capture.reset(token)


def propagated_context() -> contextvars.Context:
    """A fresh copy of the calling context, for handing to a worker thread.

    `ContextVar`s do not cross `threading.Thread` or `Executor.submit`; a worker
    starts with an empty context and every attribution set by `ai_run_scope`
    silently reverts to its default. Each worker needs its *own* copy — a
    `Context` object cannot be entered twice concurrently.
    """

    return contextvars.copy_context()


@dataclass
class AICall:
    """One logical ask: the request, and the verdict on what came back.

    `usable` starts unset. The provider's own signals (transport failure, empty
    body, `finish_reason: length`) decide it for the obvious cases. Everything
    else is presumed usable until the caller that had to read the output says
    otherwise, which it does through `unusable()`.
    """

    stage: str | None = None
    writer: str | None = None
    attempt: int = 1
    usable: bool | None = None
    unusable_reason: str | None = None
    ops_applied: int | None = None
    parent: "AICall | None" = field(default=None, repr=False)
    rows: list[dict[str, Any]] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self.rows.append(payload)

    def mark_usable(self) -> None:
        self.usable = True
        self.unusable_reason = None

    def unusable(self, reason: str = UNUSABLE_UNPARSEABLE) -> None:
        self.usable = False
        self.unusable_reason = (reason or UNUSABLE_UNPARSEABLE)[:80]

    def adjudicate(self, usable: bool, *, reason: str = UNUSABLE_UNPARSEABLE) -> None:
        """Set the verdict from a boolean the caller already computed."""

        if usable:
            self.mark_usable()
        else:
            self.unusable(reason)

    def applied_ops(self, count: int) -> None:
        self.ops_applied = max(0, int(count))

    def freeze(self) -> list[dict[str, Any]]:
        """Stamp this scope's verdict onto its rows and hand them back.

        A row the provider already condemned keeps its own, more specific reason:
        a timeout is not reclassified as "the parser hated it" just because the
        caller then found nothing to parse. The scope's verdict only decides rows
        that arrived looking fine.
        """

        with self._lock:
            rows = list(self.rows)
            self.rows.clear()
        for row in rows:
            if self.stage and not row.get("stage"):
                row["stage"] = self.stage
            if self.writer and not row.get("writer"):
                row["writer"] = self.writer
            if not row.get("attempt"):
                row["attempt"] = self.attempt
            if self.ops_applied is not None and row.get("ops_applied") is None:
                row["ops_applied"] = self.ops_applied
            if row.get("usable") is False:
                continue
            if self.usable is not None:
                row["usable"] = self.usable
                row["unusable_reason"] = None if self.usable else self.unusable_reason
        return rows


def current_ai_call() -> AICall | None:
    return _ai_call.get()


@contextmanager
def ai_call(
    stage: str | None = None,
    *,
    writer: str | None = None,
    attempt: int = 1,
    flush: Callable[[list[dict[str, Any]]], None] | None = None,
) -> Iterator[AICall]:
    """Scope one logical ask so its usability verdict lands on its own rows.

    Nesting bubbles: an inner scope freezes its verdict and hands its rows up, so
    only the outermost scope writes. That lets a repair writer adjudicate each
    ask separately while still attaching `ops_applied`, known only after the plan
    has been applied, to whichever ask produced it.
    """

    parent = _ai_call.get()
    call = AICall(stage=stage, writer=writer, attempt=max(1, int(attempt)), parent=parent)
    token = _ai_call.set(call)
    try:
        yield call
    finally:
        # No `return` in this block. An `ai_call` scope wraps a live model call;
        # returning out of `finally` would swallow whatever the body raised and
        # turn a failed ask into a silent success.
        _ai_call.reset(token)
        _settle(call, parent, flush)


def _settle(
    call: AICall,
    parent: AICall | None,
    flush: Callable[[list[dict[str, Any]]], None] | None,
) -> None:
    rows = call.freeze()
    if not rows:
        return
    if parent is not None:
        with parent._lock:
            parent.rows.extend(rows)
        return
    try:
        (flush or _default_flush)(rows)
    except Exception:  # pragma: no cover - telemetry must never break a run
        pass


def _default_flush(rows: list[dict[str, Any]]) -> None:
    from app.application.services.admin_ops import flush_usage_rows

    flush_usage_rows(rows)


__all__ = [
    "AICall",
    "AIStageTelemetryCapture",
    "UNUSABLE_EMPTY",
    "UNUSABLE_REJECTED",
    "UNUSABLE_TRANSPORT",
    "UNUSABLE_TRUNCATED",
    "UNUSABLE_UNPARSEABLE",
    "ai_call",
    "ai_run_scope",
    "capture_ai_stage_telemetry",
    "current_ai_call",
    "get_ai_purpose",
    "get_ai_request_id",
    "observe_ai_transport_retry",
    "observe_ai_usage",
    "propagated_context",
    "set_ai_purpose",
]
