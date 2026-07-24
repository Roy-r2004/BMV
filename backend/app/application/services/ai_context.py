"""Context for attributing AI usage to the active request / stage."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator

_ai_request_id: ContextVar[int | None] = ContextVar("ai_request_id", default=None)
_ai_purpose: ContextVar[str | None] = ContextVar("ai_purpose", default=None)
_ai_stage_capture: ContextVar["AIStageTelemetryCapture | None"] = ContextVar(
    "ai_stage_capture",
    default=None,
)


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


__all__ = [
    "AIStageTelemetryCapture",
    "ai_run_scope",
    "capture_ai_stage_telemetry",
    "get_ai_purpose",
    "get_ai_request_id",
    "observe_ai_transport_retry",
    "observe_ai_usage",
    "set_ai_purpose",
]
