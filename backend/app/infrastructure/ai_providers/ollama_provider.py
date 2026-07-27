"""Ollama AI provider — local inference via the Ollama HTTP API."""
from __future__ import annotations

import base64
import threading
import time

import requests

from app.application.services.admin_ops import ai_is_allowed, record_usage
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.infrastructure.ai_providers.response_parser import (
    ProviderGenerationError,
    parse_json_body,
    parse_ollama_chat_response,
    raise_if_unsuccessful,
)
from app.infrastructure.ai_providers.retry import call_with_retry
from app.infrastructure.logging import get_logger

retry_log = get_logger("AIRetry")


class OllamaAIProvider(AIProvider):
    """Implements `AIProvider` against a local Ollama server."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url or settings.OLLAMA_URL
        self._lock = threading.Lock()
        self._active_response: requests.Response | None = None
        self._active_session: requests.Session | None = None

    @property
    def name(self) -> str:
        return "ollama"

    def cancel_inflight(self) -> None:
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

    def _guard(self, model: str, purpose: str) -> None:
        allowed, reason = ai_is_allowed(purpose)
        if not allowed:
            record_usage(
                provider="ollama",
                model=model,
                purpose=purpose,
                success=False,
                error=reason,
            )
            raise RuntimeError(reason)

    def _chat(
        self,
        model: str,
        messages: list[dict],
        *,
        purpose: str,
        max_tokens: int | None = None,
        timeout: int = 240,
        transport_attempts: int = 2,
    ) -> str:
        self._guard(model, purpose)
        payload: dict = {"model": model, "stream": False, "messages": messages}
        if max_tokens is not None:
            payload["options"] = {"num_predict": max_tokens}

        def _do_request() -> tuple[int, object | None, str]:
            session = requests.Session()
            with self._lock:
                self._active_session = session
            try:
                response = session.post(
                    f"{self._base_url}/api/chat",
                    json=payload,
                    timeout=timeout,
                )
                with self._lock:
                    self._active_response = response
                raw_text = response.text or ""
                body, _malformed = parse_json_body(raw_text)
                return response.status_code, body, raw_text
            finally:
                with self._lock:
                    self._active_response = None
                    self._active_session = None
                session.close()

        def _heartbeat(elapsed: float) -> None:
            retry_log.debug("still waiting on ollama/%s (%.0fs elapsed)", model, elapsed)

        started = time.monotonic()
        try:
            status, body, raw_text = call_with_retry(
                _do_request,
                attempts=max(1, int(transport_attempts)),
                base_delay=3,
                heartbeat_interval=20,
                on_heartbeat=_heartbeat,
            )
            latency = int((time.monotonic() - started) * 1000)
            parsed = parse_ollama_chat_response(
                provider="ollama",
                model=model,
                http_status=int(status),
                body=body,
                raw_text=raw_text,
                latency_ms=latency,
            )
            if not parsed.is_success:
                record_usage(
                    provider="ollama",
                    model=model,
                    purpose=purpose,
                    prompt_tokens=parsed.input_tokens,
                    completion_tokens=parsed.output_tokens,
                    cost_usd=0.0,
                    success=False,
                    error=parsed.error_code or parsed.error_message_redacted,
                    latency_ms=latency,
                )
                raise_if_unsuccessful(parsed)
            record_usage(
                provider="ollama",
                model=model,
                purpose=purpose,
                prompt_tokens=parsed.input_tokens,
                completion_tokens=parsed.output_tokens,
                cost_usd=0.0,
                success=True,
                latency_ms=latency,
            )
            return parsed.text
        except ProviderGenerationError:
            raise
        except Exception as exc:
            latency = int((time.monotonic() - started) * 1000)
            record_usage(
                provider="ollama",
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
    ) -> str:
        # Ollama AppSpec path keeps prompt-only JSON; ignore unsupported
        # response_format rather than sending an invalid option.
        _ = response_format
        timeout = 240 if timeout_seconds is None else max(1, int(timeout_seconds))
        attempts = 2 if transport_attempts is None else max(1, int(transport_attempts))
        return self._chat(
            model,
            messages,
            purpose="pipeline",
            max_tokens=max_tokens,
            timeout=timeout,
            transport_attempts=attempts,
        )

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
        timeout = 240 if timeout_seconds is None else max(1, int(timeout_seconds))
        attempts = 2 if transport_attempts is None else max(1, int(transport_attempts))
        return self._chat(
            model,
            messages,
            purpose=purpose,
            max_tokens=max_tokens,
            timeout=timeout,
            transport_attempts=attempts,
        )

    def ask_vision(self, model: str, prompt: str, image_path: str) -> str:
        purpose = "vision"
        self._guard(model, purpose)
        with open(image_path, "rb") as file:
            image_base64 = base64.b64encode(file.read()).decode("utf-8")

        def _do_request() -> tuple[int, object | None, str]:
            response = requests.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "messages": [
                        {"role": "user", "content": prompt, "images": [image_base64]}
                    ],
                },
                timeout=240,
            )
            raw_text = response.text or ""
            body, _malformed = parse_json_body(raw_text)
            return response.status_code, body, raw_text

        started = time.monotonic()
        try:
            status, body, raw_text = call_with_retry(
                _do_request, attempts=2, base_delay=3
            )
            latency = int((time.monotonic() - started) * 1000)
            parsed = parse_ollama_chat_response(
                provider="ollama",
                model=model,
                http_status=int(status),
                body=body,
                raw_text=raw_text,
                latency_ms=latency,
            )
            if not parsed.is_success:
                record_usage(
                    provider="ollama",
                    model=model,
                    purpose=purpose,
                    cost_usd=0.0,
                    success=False,
                    error=parsed.error_code or parsed.error_message_redacted,
                    latency_ms=latency,
                )
                raise_if_unsuccessful(parsed)
            record_usage(
                provider="ollama",
                model=model,
                purpose=purpose,
                cost_usd=0.0,
                success=True,
                latency_ms=latency,
            )
            return parsed.text
        except ProviderGenerationError:
            raise
        except Exception as exc:
            latency = int((time.monotonic() - started) * 1000)
            record_usage(
                provider="ollama",
                model=model,
                purpose=purpose,
                success=False,
                error=str(exc)[:2000],
                latency_ms=latency,
            )
            raise

    def is_available(self) -> bool:
        try:
            response = requests.get(f"{self._base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def installed_models(self) -> list[str]:
        response = requests.get(f"{self._base_url}/api/tags", timeout=5)
        response.raise_for_status()
        payload = response.json()
        return [m.get("name", "") for m in payload.get("models", []) if m.get("name")]
