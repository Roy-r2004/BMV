"""Ollama AI provider — local inference via the Ollama HTTP API."""
from __future__ import annotations

import base64

import requests

from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.infrastructure.ai_providers.retry import call_with_retry


class OllamaAIProvider(AIProvider):
    """Implements `AIProvider` against a local Ollama server."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url or settings.OLLAMA_URL

    @property
    def name(self) -> str:
        return "ollama"

    def ask_chat(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        payload: dict = {"model": model, "stream": False, "messages": messages}
        if max_tokens is not None:
            payload["options"] = {"num_predict": max_tokens}

        def _do_request() -> dict:
            # Local/self-hosted inference is often slower per-token than a
            # cloud API, so this keeps more headroom than OpenRouter's 120s —
            # but 600s (worst case ~30min across retries) was excessive for
            # any single call, so it's still cut down.
            response = requests.post(f"{self._base_url}/api/chat", json=payload, timeout=240)
            response.raise_for_status()
            return response.json()

        def _heartbeat(elapsed: float) -> None:
            print(f"    ...still waiting on ollama/{model} ({elapsed:.0f}s elapsed)", flush=True)

        data = call_with_retry(
            _do_request, attempts=2, base_delay=3,
            heartbeat_interval=20, on_heartbeat=_heartbeat,
        )
        return data["message"]["content"]

    def ask_vision(self, model: str, prompt: str, image_path: str) -> str:
        with open(image_path, "rb") as file:
            image_base64 = base64.b64encode(file.read()).decode("utf-8")

        def _do_request() -> dict:
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
            response.raise_for_status()
            return response.json()

        # Was previously unwrapped (no retry) — a single transient blip used
        # to kill the whole screenshot-analysis step outright.
        data = call_with_retry(_do_request, attempts=2, base_delay=3)
        return data["message"]["content"]

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
