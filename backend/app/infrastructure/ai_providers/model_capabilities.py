"""Explicit OpenRouter model capability profiles for candidate generation.

Policy revision: 2026-07-26.candidate-provider.2

Profiles are repository-owned. Do not infer capability from arbitrary failures.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CAPABILITY_PROFILE_REVISION = "2026-07-26.candidate-provider.2"
CONTEXT_RESERVE_TOKENS = 512
MINIMUM_VALID_OUTPUT_TOKENS = 4_000

_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "deepseek/deepseek-chat": 32_768,
    "deepseek/deepseek-v4-pro": 32_768,
    "deepseek/deepseek-chat-v3": 64_000,
    "deepseek/deepseek-v3": 64_000,
    "z-ai/glm-5": 128_000,
    "z-ai/glm-5.2": 128_000,
    "google/gemini-2.5-flash": 1_000_000,
    "google/gemini-2.0-flash": 1_000_000,
    "openai/gpt-4o": 128_000,
    "openai/gpt-4o-mini": 128_000,
    "anthropic/claude-haiku-4.5": 200_000,
    "anthropic/claude-sonnet-4": 200_000,
}


@dataclass(frozen=True)
class ModelCapabilityProfile:
    model: str
    context_window: int
    known: bool = True
    supports_json_text_mode: bool = True
    supports_strict_json_schema: bool = False
    supports_tools: bool = False
    supports_reasoning_params: bool = False
    max_output_tokens_field: str = "max_tokens"
    revision: str = CAPABILITY_PROFILE_REVISION

    def to_diagnostics(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "context_window": self.context_window,
            "known": self.known,
            "supports_json_text_mode": self.supports_json_text_mode,
            "supports_strict_json_schema": self.supports_strict_json_schema,
            "supports_tools": self.supports_tools,
            "supports_reasoning_params": self.supports_reasoning_params,
            "max_output_tokens_field": self.max_output_tokens_field,
            "revision": self.revision,
        }


def resolve_model_capability(model: str) -> ModelCapabilityProfile:
    normalized = str(model or "").strip()
    window = _MODEL_CONTEXT_WINDOWS.get(normalized)
    if window is None:
        return ModelCapabilityProfile(
            model=normalized,
            context_window=0,
            known=False,
        )
    return ModelCapabilityProfile(model=normalized, context_window=window)


def clamp_max_tokens(
    *,
    requested_max_tokens: int,
    estimated_input_tokens: int,
    context_window: int,
    reserve_tokens: int = CONTEXT_RESERVE_TOKENS,
    minimum_output_tokens: int = MINIMUM_VALID_OUTPUT_TOKENS,
) -> int:
    """Fit output budget into remaining context after the prompt."""

    remaining = int(context_window) - int(estimated_input_tokens) - int(reserve_tokens)
    requested = int(requested_max_tokens)
    minimum = int(minimum_output_tokens)
    if remaining < minimum or requested < minimum:
        return 0
    return min(requested, remaining)


def estimate_prompt_tokens(text: str) -> int:
    # Conservative deterministic approximation for mixed prose, JSON, and code.
    return max(1, (len(text or "") + 2) // 3)


__all__ = [
    "CAPABILITY_PROFILE_REVISION",
    "CONTEXT_RESERVE_TOKENS",
    "MINIMUM_VALID_OUTPUT_TOKENS",
    "ModelCapabilityProfile",
    "clamp_max_tokens",
    "estimate_prompt_tokens",
    "resolve_model_capability",
]
