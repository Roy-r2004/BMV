"""Context for attributing AI usage to the active request / stage."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_ai_request_id: ContextVar[int | None] = ContextVar("ai_request_id", default=None)
_ai_purpose: ContextVar[str | None] = ContextVar("ai_purpose", default=None)


def get_ai_request_id() -> int | None:
    return _ai_request_id.get()


def get_ai_purpose() -> str | None:
    return _ai_purpose.get()


def set_ai_purpose(purpose: str | None) -> None:
    _ai_purpose.set((purpose or "")[:80] or None)


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
