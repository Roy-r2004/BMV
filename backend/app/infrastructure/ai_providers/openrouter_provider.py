"""OpenRouter AI provider — hosted inference via the OpenRouter chat API."""
from __future__ import annotations

import base64
import mimetypes
import threading
import time

import requests

from app.application.services.admin_ops import (
    ai_is_allowed,
    record_usage,
)
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.infrastructure.ai_providers.response_parser import (
    ChatMessageEnvelope,
    ProviderGenerationError,
    parse_json_body,
    parse_openai_compatible_chat_response,
    raise_if_unsuccessful,
    retryable_for_status,
)
from app.infrastructure.ai_providers.retry import call_with_retry
from app.infrastructure.logging import get_logger

retry_log = get_logger("AIRetry")


def _response_field_for(envelope: ChatMessageEnvelope) -> str:
    """Name the field the assistant answer actually arrived in."""

    if envelope.tool_calls:
        return "choices[0].message.tool_calls"
    if envelope.has_parsed:
        return "choices[0].message.parsed"
    if envelope.content_kind == "parts":
        return "choices[0].message.content[]"
    return "choices[0].message.content"


def _openrouter_http_exchange(
    *,
    provider_self: "OpenRouterAIProvider",
    session: requests.Session,
    url: str,
    headers: dict,
    payload: dict,
    timeout: int,
) -> tuple[int, object | None, str]:
    response = session.post(
        url,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    with provider_self._lock:
        provider_self._active_response = response
    if retryable_for_status(response.status_code):
        # Preserve transport-level retries owned by call_with_retry.
        raise requests.HTTPError(
            f"{response.status_code} Server Error for url: {url}",
            response=response,
        )
    raw_text = response.text or ""
    body, _malformed = parse_json_body(raw_text)
    return response.status_code, body, raw_text


def _result_from_transport_error(
    *,
    model: str,
    exc: Exception,
    latency_ms: int,
) -> None:
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        parsed = parse_openai_compatible_chat_response(
            provider="openrouter",
            model=model,
            http_status=408,
            body=None,
            raw_text="",
            latency_ms=latency_ms,
        )
        raise_if_unsuccessful(parsed)
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        raw_text = exc.response.text or ""
        body, _ = parse_json_body(raw_text)
        parsed = parse_openai_compatible_chat_response(
            provider="openrouter",
            model=model,
            http_status=int(exc.response.status_code),
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
        )
        raise_if_unsuccessful(parsed)
    raise exc

_CLAUDE_MODEL_PREFIXES = (
    "anthropic/claude",
    "anthropic/claude-sonnet",
    "anthropic/claude-opus",
    "anthropic/claude-haiku",
)

#: A single attempt may take this many times its socket timeout before it is
#: cancelled. Slow-but-working generations must survive; a call that has stopped
#: making progress must not hold a pipeline stage open indefinitely.
_WALL_CLOCK_BUDGET_FACTOR = 2.5


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
        self._last_completion_meta: dict | None = None
        self._last_response_envelope: ChatMessageEnvelope | None = None

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
        response_format: dict | None = None,
        tools: list[dict] | None = None,
        tool_choice: dict | str | None = None,
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
        if isinstance(response_format, dict) and response_format:
            payload["response_format"] = response_format
        # Tool parameters are only ever sent when the caller proved support via
        # the capability profile; an unsupported model never sees them.
        if isinstance(tools, list) and tools:
            payload["tools"] = tools
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice

        def _do_request() -> tuple[int, object | None, str]:
            session = requests.Session()
            with self._lock:
                self._active_session = session
            try:
                status, body, raw_text = _openrouter_http_exchange(
                    provider_self=self,
                    session=session,
                    url=f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    payload=payload,
                    timeout=timeout,
                )
                return status, body, raw_text
            finally:
                with self._lock:
                    self._active_response = None
                    self._active_session = None
                session.close()

        def _heartbeat(elapsed: float) -> None:
            retry_log.debug("still waiting on %s (%.0fs elapsed)", model, elapsed)

        started = time.monotonic()
        try:
            try:
                status, body, raw_text = call_with_retry(
                    _do_request,
                    attempts=max(1, int(transport_attempts)),
                    base_delay=3,
                    heartbeat_interval=20,
                    on_heartbeat=_heartbeat,
                    # `timeout` only fires on socket inactivity. A model that
                    # trickles bytes never trips it: request 45 held one repair
                    # call open for fourteen minutes. Cap an attempt's total wall
                    # clock generously — a long generation is legitimate, a
                    # quarter of an hour on one call is not.
                    hard_deadline=timeout * _WALL_CLOCK_BUDGET_FACTOR,
                    on_deadline=self.cancel_inflight,
                )
            except (requests.HTTPError, requests.Timeout, requests.ConnectionError) as exc:
                latency = int((time.monotonic() - started) * 1000)
                try:
                    _result_from_transport_error(
                        model=model, exc=exc, latency_ms=latency
                    )
                except ProviderGenerationError as typed:
                    record_usage(
                        provider="openrouter",
                        model=model,
                        purpose=purpose,
                        prompt_tokens=typed.result.input_tokens,
                        completion_tokens=typed.result.output_tokens,
                        total_tokens=typed.result.total_tokens,
                        cost_usd=typed.result.cost_usd,
                        success=False,
                        error=typed.error_code,
                        latency_ms=latency,
                    )
                    raise
                record_usage(
                    provider="openrouter",
                    model=model,
                    purpose=purpose,
                    success=False,
                    error=str(exc)[:2000],
                    latency_ms=latency,
                )
                raise

            latency = int((time.monotonic() - started) * 1000)
            parsed = parse_openai_compatible_chat_response(
                provider="openrouter",
                model=model,
                http_status=int(status),
                body=body,
                raw_text=raw_text,
                latency_ms=latency,
            )
            with self._lock:
                self._last_response_envelope = parsed.envelope
            if not parsed.is_success:
                record_usage(
                    provider="openrouter",
                    model=model,
                    purpose=purpose,
                    prompt_tokens=parsed.input_tokens,
                    completion_tokens=parsed.output_tokens,
                    total_tokens=parsed.total_tokens,
                    cost_usd=parsed.cost_usd,
                    success=False,
                    error=parsed.error_code or parsed.error_message_redacted,
                    latency_ms=latency,
                )
                raise_if_unsuccessful(parsed)

            record_usage(
                provider="openrouter",
                model=model,
                purpose=purpose,
                prompt_tokens=parsed.input_tokens,
                completion_tokens=parsed.output_tokens,
                total_tokens=parsed.total_tokens,
                cost_usd=parsed.cost_usd,
                success=True,
                latency_ms=latency,
            )
            with self._lock:
                self._last_response_envelope = parsed.envelope
                self._last_completion_meta = {
                    "provider": "openrouter",
                    "model": model,
                    "finish_reason": parsed.finish_reason,
                    "input_tokens": parsed.input_tokens,
                    "output_tokens": parsed.output_tokens,
                    "total_tokens": parsed.total_tokens,
                    "truncated": bool(parsed.truncated),
                    "response_format_requested": (
                        dict(response_format) if response_format else None
                    ),
                    "tools_requested": [
                        str(
                            (item.get("function") or {}).get("name")
                            if isinstance(item, dict)
                            else ""
                        )
                        for item in (tools or [])
                    ],
                    "text_chars": len(parsed.text or ""),
                    "response_field": _response_field_for(parsed.envelope),
                    "envelope": parsed.envelope.to_diagnostics(),
                }
            return parsed.text
        except ProviderGenerationError:
            raise
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
        response_format: dict | None = None,
        tools: list[dict] | None = None,
        tool_choice: dict | str | None = None,
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
            response_format=response_format,
            tools=tools,
            tool_choice=tool_choice,
        )

    def last_completion_meta(self) -> dict | None:
        with self._lock:
            return dict(self._last_completion_meta) if self._last_completion_meta else None

    def last_response_envelope(self) -> ChatMessageEnvelope | None:
        """The structural envelope of the most recent chat completion.

        Kept out of ``last_completion_meta`` so that dict stays JSON-safe.
        """

        with self._lock:
            return self._last_response_envelope

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
