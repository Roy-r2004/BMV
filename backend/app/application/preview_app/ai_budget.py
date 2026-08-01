"""Request-scoped aggregate model-call budget for preview generation."""
from __future__ import annotations

import logging
import inspect
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import wraps

from app.domain.interfaces.ai_provider import AIProvider


logger = logging.getLogger(__name__)


@dataclass
class AICallBudget:
    request_key: str
    max_calls: int
    used: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _logged_exhaustion: bool = field(default=False, repr=False)

    @property
    def exhausted(self) -> bool:
        with self._lock:
            return self.used >= self.max_calls

    def acquire(self, *, modality: str) -> bool:
        with self._lock:
            if self.used >= self.max_calls:
                if not self._logged_exhaustion:
                    logger.warning(
                        "Preview AI call budget exhausted request=%s used=%s max=%s modality=%s",
                        self.request_key,
                        self.used,
                        self.max_calls,
                        modality,
                    )
                    self._logged_exhaustion = True
                return False
            self.used += 1
            return True


class BudgetedAIProvider:
    def __init__(
        self,
        provider: AIProvider,
        budget: AICallBudget,
        release,
    ) -> None:
        self.provider = provider
        self.budget = budget
        self._release = release
        self._closed = False
        self._close_lock = threading.Lock()

    def _refuse(self, modality: str) -> str:
        """Record the exhaustion, then return the empty string callers expect.

        The defect worth fixing here is that exhaustion was **silent**: `""` is
        indistinguishable from a model that answered with nothing, so a budget
        that ran out surfaced as a stub or a fallback slot several stages
        downstream of the cause, and a page composed from `""` still passes
        `tsc` and still builds.

        The roadmap asks for a raise instead. That is deliberately **deferred to
        Phase 2**, and the reason is in its own justification: a raise matters
        when "the content asks are load-bearing", which is true after the
        content flip and not before. Today every caller already has a
        deterministic fallback — `generate_file`, `synthesize_mock_data`, the
        critic and the chat-scaffold path each have a test pinning that they
        preserve existing source on exhaustion. Raising would convert those
        proven degradations into an exception out of `generate_preview_app`,
        which the orchestrator answers with a whole-generation retry costing
        180 s of runway. That trades a working fallback for a worse outcome.

        So: keep the return, remove the silence. `record_degradation` makes the
        exhaustion machine-readable, which is what "not silent" actually
        requires — a reader, not an exception.
        """
        from app.application.services.request_deadline import record_degradation

        record_degradation("ai_budget", f"exhausted_{modality}")
        return ""

    def ask_chat(self, model: str, messages: list[dict], **kwargs) -> str:
        if not self.budget.acquire(modality="chat"):
            return self._refuse("chat")
        return self.provider.ask_chat(model, messages, **kwargs)

    def ask_vision(self, model: str, prompt: str, image_path: str) -> str:
        if not self.budget.acquire(modality="vision"):
            return self._refuse("vision")
        return self.provider.ask_vision(model, prompt, image_path)

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        self._release()

    def __enter__(self) -> BudgetedAIProvider:
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()


@dataclass
class _BudgetRegistryEntry:
    budget: AICallBudget
    holders: int = 0


@dataclass
class _OperationRegistryEntry:
    lock: threading.RLock = field(default_factory=threading.RLock)
    holders: int = 0


_budget_registry: dict[str, _BudgetRegistryEntry] = {}
_budget_registry_lock = threading.RLock()
_operation_registry: dict[str, _OperationRegistryEntry] = {}
_operation_registry_lock = threading.RLock()


def active_budget_registry_size() -> int:
    with _budget_registry_lock:
        return len(_budget_registry)


def active_operation_registry_size() -> int:
    with _operation_registry_lock:
        return len(_operation_registry)


def budget_ai_provider(
    provider: AIProvider,
    *,
    request_key: object,
    max_calls: int,
) -> BudgetedAIProvider:
    """Acquire one holder of a request-keyed aggregate budget."""
    normalized_key = str(request_key)
    if isinstance(provider, BudgetedAIProvider):
        provider = provider.provider
    with _budget_registry_lock:
        entry = _budget_registry.get(normalized_key)
        if entry is None:
            entry = _BudgetRegistryEntry(
                budget=AICallBudget(normalized_key, max(1, int(max_calls)))
            )
            _budget_registry[normalized_key] = entry
        else:
            # A re-entry cannot enlarge/reset the cap selected by the first holder.
            entry.budget.max_calls = min(entry.budget.max_calls, max(1, int(max_calls)))
        entry.holders += 1

    released = False
    release_lock = threading.Lock()

    def _release() -> None:
        nonlocal released
        with release_lock:
            if released:
                return
            released = True
        with _budget_registry_lock:
            current = _budget_registry.get(normalized_key)
            if current is not entry:
                return
            current.holders -= 1
            if current.holders <= 0:
                _budget_registry.pop(normalized_key, None)

    return BudgetedAIProvider(provider, entry.budget, _release)


@contextmanager
def request_operation_lock(request_key: object):
    """Serialize mutating orchestration for one request while isolating others."""
    normalized_key = str(request_key)
    with _operation_registry_lock:
        entry = _operation_registry.get(normalized_key)
        if entry is None:
            entry = _OperationRegistryEntry()
            _operation_registry[normalized_key] = entry
        entry.holders += 1
    entry.lock.acquire()
    try:
        yield
    finally:
        entry.lock.release()
        with _operation_registry_lock:
            current = _operation_registry.get(normalized_key)
            if current is entry:
                current.holders -= 1
                if current.holders <= 0:
                    _operation_registry.pop(normalized_key, None)


def request_mutation_boundary(func):
    """Share budget, serialize mutation, and clean workspace tracking on exit."""
    signature = inspect.signature(func)

    @wraps(func)
    def _wrapped(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        request_id = bound.arguments["request_id"]
        provider = bound.arguments["ai_provider"]
        from app.application.preview_app.fallback import clear_stubbed_paths
        from app.application.preview_app.workspace import get_workspace
        from app.core.config import settings

        leased_provider = budget_ai_provider(
            provider,
            request_key=request_id,
            max_calls=settings.PREVIEW_MAX_AI_CALLS,
        )
        bound.arguments["ai_provider"] = leased_provider
        try:
            with request_operation_lock(request_id):
                return func(*bound.args, **bound.kwargs)
        finally:
            # The wrapped function has returned only after metadata persistence.
            try:
                module = sys.modules.get(func.__module__)
                workspace_resolver = getattr(module, "get_workspace", get_workspace)
                clear_stubbed_paths(workspace_resolver(request_id))
            finally:
                leased_provider.close()

    return _wrapped
