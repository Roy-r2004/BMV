"""OpenRouter AI provider — hosted inference via the OpenRouter chat API."""
from __future__ import annotations

import base64
import mimetypes
import threading
import time

import requests

from app.application.services.admin_ops import (
    ai_is_allowed,
    parse_openrouter_usage,
    record_usage,
)
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.infrastructure.ai_providers.retry import call_with_retry
from app.infrastructure.logging import get_logger

retry_log = get_logger("AIRetry")

_CLAUDE_MODEL_PREFIXES = (
    "anthropic/claude",
    "anthropic/claude-sonnet",
    "anthropic/claude-opus",
    "anthropic/claude-haiku",
)


class OpenRouterAIProvider(AIProvider):
    """Implements `AIProvider` against the OpenRouter API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        app_name: str | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.OPENROUTER_API_KEY
        self._base_url = base_url or settings.OPENROUTER_BASE_URL
        self._app_name = app_name or settings.OPENROUTER_APP_NAME
        self._lock = threading.Lock()
        self._active_response: requests.Response | None = None
        self._active_session: requests.Session | None = None

    @property
    def name(self) -> str:
        return "openrouter"

    def cancel_inflight(self) -> None:
        """Best-effort cancel of the in-flight HTTP request."""

        with self._lock:
            response = self._active_response
            session = self._active_session
            self._active_response = None
            self._active_session = None
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        if session is not None:
            try:
                session.close()
            except Exception:
                pass

    def _headers(self) -> dict:
        if not self._api_key:
            raise ValueError("OPENROUTER_API_KEY is not set.")
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.OPENROUTER_SITE_URL or "https://buildmyversion.ai",
            "X-Title": self._app_name,
        }

    @staticmethod
    def _is_claude(model: str) -> bool:
        return any(model.startswith(prefix) for prefix in _CLAUDE_MODEL_PREFIXES)

    def _chat_completion(
        self,
        model: str,
        messages: list,
        timeout: int = 120,
        max_tokens: int | None = None,
        temperature: float | None = None,
        purpose: str = "pipeline",
        transport_attempts: int = 2,
    ) -> str:
        allowed, reason = ai_is_allowed(purpose)
        if not allowed:
            record_usage(
                provider="openrouter",
                model=model,
                purpose=purpose,
                success=False,
                error=reason,
            )
            raise RuntimeError(reason)

        payload: dict = {"model": model, "messages": messages, "stream": False}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature

        def _do_request() -> dict:
            session = requests.Session()
            with self._lock:
                self._active_session = session
            try:
                response = session.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                    timeout=timeout,
                )
                with self._lock:
                    self._active_response = response
                response.raise_for_status()
                return response.json()
            finally:
                with self._lock:
                    self._active_response = None
                    self._active_session = None
                session.close()

        def _heartbeat(elapsed: float) -> None:
            retry_log.debug("still waiting on %s (%.0fs elapsed)", model, elapsed)

        started = time.monotonic()
        try:
            data = call_with_retry(
                _do_request,
                attempts=max(1, int(transport_attempts)),
                base_delay=3,
                heartbeat_interval=20,
                on_heartbeat=_heartbeat,
            )
            latency = int((time.monotonic() - started) * 1000)
            prompt, completion, total, cost = parse_openrouter_usage(data)
            record_usage(
                provider="openrouter",
                model=model,
                purpose=purpose,
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=total,
                cost_usd=cost,
                success=True,
                latency_ms=latency,
            )
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            latency = int((time.monotonic() - started) * 1000)
            record_usage(
                provider="openrouter",
                model=model,
                purpose=purpose,
                success=False,
                error=str(exc)[:2000],
                latency_ms=latency,
            )
            raise

    def ask_chat(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int | None = None,
        temperature: float | None = None,
        *,
        timeout_seconds: float | None = None,
        transport_attempts: int | None = None,
    ) -> str:
        if temperature is None and self._is_claude(model):
            temperature = 0.3
        timeout = 120 if timeout_seconds is None else max(1, int(timeout_seconds))
        attempts = 2 if transport_attempts is None else max(1, int(transport_attempts))
        return self._chat_completion(
            model,
            messages,
            timeout=timeout,
            max_tokens=max_tokens,
            temperature=temperature,
            purpose="pipeline",
            transport_attempts=attempts,
        )

    def ask_vision(self, model: str, prompt: str, image_path: str) -> str:
        mime, _ = mimetypes.guess_type(image_path)
        mime = mime or "image/jpeg"
        with open(image_path, "rb") as file:
            image_b64 = base64.b64encode(file.read()).decode("utf-8")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                ],
            }
        ]
        return self._chat_completion(model, messages, purpose="vision")

    def ask_chat_purposed(
        self,
        model: str,
        messages: list[dict],
        *,
        purpose: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout_seconds: float | None = None,
        transport_attempts: int | None = None,
    ) -> str:
        timeout = 120 if timeout_seconds is None else max(1, int(timeout_seconds))
        attempts = 2 if transport_attempts is None else max(1, int(transport_attempts))
        return self._chat_completion(
            model,
            messages,
            timeout=timeout,
            max_tokens=max_tokens,
            temperature=temperature,
            purpose=purpose,
            transport_attempts=attempts,
        )

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            response = requests.get(f"{self._base_url}/models", headers=self._headers(), timeout=10)
            return response.status_code == 200
        except Exception:
            return False
