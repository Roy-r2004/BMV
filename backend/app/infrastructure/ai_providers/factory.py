"""Selects and caches the configured `AIProvider` implementation.

This is the single place that decides Ollama vs OpenRouter, based on
`Settings.AI_PROVIDER`. Everything else in the codebase depends only on the
`AIProvider` Protocol.
"""
from functools import lru_cache

from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.infrastructure.ai_providers.ollama_provider import OllamaAIProvider
from app.infrastructure.ai_providers.openrouter_provider import OpenRouterAIProvider


@lru_cache(maxsize=1)
def get_ai_provider() -> AIProvider:
    if settings.AI_PROVIDER == "openrouter":
        return OpenRouterAIProvider()
    return OllamaAIProvider()


# Thin module-level helpers preserve the old `ask_chat`/`ask_vision` call
# style used throughout the application layer, while routing through the
# factory-selected provider (no behavior change, just indirection).
def ask_chat(
    model: str,
    messages: list,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> str:
    return get_ai_provider().ask_chat(model, messages, max_tokens=max_tokens, temperature=temperature)


def ask_vision(model: str, prompt: str, image_path: str) -> str:
    return get_ai_provider().ask_vision(model, prompt, image_path)


def is_inference_available() -> bool:
    return get_ai_provider().is_available()


def provider_name() -> str:
    return settings.AI_PROVIDER
