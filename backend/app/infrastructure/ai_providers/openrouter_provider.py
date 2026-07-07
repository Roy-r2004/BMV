"""OpenRouter AI provider — hosted inference via the OpenRouter chat API."""
from __future__ import annotations

import base64
import mimetypes

import requests

from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider

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

    @property
    def name(self) -> str:
        return "openrouter"

    def _headers(self) -> dict:
        if not self._api_key:
            raise ValueError("OPENROUTER_API_KEY is not set.")
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://buildmyversion.ai",
            "X-Title": self._app_name,
        }

    @staticmethod
    def _is_claude(model: str) -> bool:
        return any(model.startswith(prefix) for prefix in _CLAUDE_MODEL_PREFIXES)

    def _chat_completion(
        self,
        model: str,
        messages: list,
        timeout: int = 300,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        payload: dict = {"model": model, "messages": messages, "stream": False}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        response = requests.post(
            f"{self._base_url}/chat/completions",
            headers=self._headers(),
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def ask_chat(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        # Claude code-gen: low temperature for precise, rule-following output.
        if temperature is None and self._is_claude(model):
            temperature = 0.3
        return self._chat_completion(model, messages, max_tokens=max_tokens, temperature=temperature)

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
        return self._chat_completion(model, messages)

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            response = requests.get(f"{self._base_url}/models", headers=self._headers(), timeout=10)
            return response.status_code == 200
        except Exception:
            return False
