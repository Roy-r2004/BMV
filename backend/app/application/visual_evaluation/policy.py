"""Dedicated Phase 5 model capabilities, routing, and bounded policy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.application.appspec.policy import ModelFamilyPolicyError, model_family
from app.core.config import settings
from app.domain.schemas.visual_evaluation import (
    ModelCapabilityResolution,
    ScoreBandPolicy,
    VisualAcceptancePolicy,
    VisualEvaluationLimits,
    VisualStageRouting,
)


VisualStage = Literal[
    "critic",
    "reviewer",
    "refinement",
    "technical_repair",
]


@dataclass(frozen=True)
class _Capability:
    family: str
    multimodal: bool
    max_images: int
    max_image_bytes: int
    max_aggregate_image_bytes: int


# This registry describes the exact OpenAI-compatible content-parts format
# used by OpenRouterAIProvider. It is intentionally local and allowlisted:
# Phase 5 never guesses capabilities from a model name or calls a provider
# discovery endpoint at runtime.
_OPENROUTER_CAPABILITIES = {
    "openai/gpt-4o": _Capability(
        family="openai",
        multimodal=True,
        max_images=20,
        max_image_bytes=20 * 1024 * 1024,
        max_aggregate_image_bytes=50 * 1024 * 1024,
    ),
    "google/gemini-2.5-flash": _Capability(
        family="google",
        multimodal=True,
        max_images=32,
        max_image_bytes=7 * 1024 * 1024,
        max_aggregate_image_bytes=20 * 1024 * 1024,
    ),
    "meta-llama/llama-3.2-11b-vision-instruct": _Capability(
        family="meta-llama",
        multimodal=True,
        max_images=8,
        max_image_bytes=5 * 1024 * 1024,
        max_aggregate_image_bytes=16 * 1024 * 1024,
    ),
    "deepseek/deepseek-v4-pro": _Capability(
        family="deepseek",
        multimodal=False,
        max_images=0,
        max_image_bytes=0,
        max_aggregate_image_bytes=0,
    ),
}


def resolve_model_capability(
    model: str,
    *,
    require_multimodal: bool,
) -> ModelCapabilityResolution:
    if settings.AI_PROVIDER != "openrouter":
        raise ModelFamilyPolicyError(
            "Phase 5 supports only the registered OpenRouter multimodal "
            "message format; provider capability is unknown."
        )
    capability = _OPENROUTER_CAPABILITIES.get(model)
    family = model_family(model)
    if capability is None or family is None or family != capability.family:
        raise ModelFamilyPolicyError(
            f"Unknown Phase 5 capability for model {model!r}; "
            "failing closed before provider calls."
        )
    if require_multimodal and not capability.multimodal:
        raise ModelFamilyPolicyError(
            f"Phase 5 model {model!r} is not registered for multimodal chat."
        )
    return ModelCapabilityResolution(
        provider="openrouter",
        model=model,
        family=family,
        capability=(
            "multimodal_chat" if capability.multimodal else "text_chat"
        ),
        message_format=(
            "openai_content_parts"
            if capability.multimodal
            else "openai_text_messages"
        ),
        max_images=capability.max_images,
        max_image_bytes=capability.max_image_bytes,
        max_aggregate_image_bytes=(
            capability.max_aggregate_image_bytes
        ),
    )


def _stage_values(stage: VisualStage) -> tuple[str, str, int, float, int, bool]:
    if stage == "critic":
        return (
            settings.V2_VISUAL_CRITIC_MODEL,
            settings.V2_VISUAL_CRITIC_PROMPT_REVISION,
            settings.V2_VISUAL_CRITIC_MAX_TOKENS,
            0.2,
            settings.V2_VISUAL_CRITIC_TIMEOUT_SECONDS,
            True,
        )
    if stage == "reviewer":
        return (
            settings.V2_VISUAL_REVIEWER_MODEL,
            settings.V2_VISUAL_REVIEWER_PROMPT_REVISION,
            settings.V2_VISUAL_REVIEWER_MAX_TOKENS,
            0.1,
            settings.V2_VISUAL_REVIEWER_TIMEOUT_SECONDS,
            True,
        )
    if stage == "refinement":
        return (
            settings.V2_VISUAL_REFINEMENT_MODEL,
            settings.V2_VISUAL_REFINEMENT_PROMPT_REVISION,
            settings.V2_VISUAL_REFINEMENT_MAX_TOKENS,
            0.2,
            settings.V2_VISUAL_REFINEMENT_TIMEOUT_SECONDS,
            True,
        )
    if stage == "technical_repair":
        return (
            settings.V2_VISUAL_TECHNICAL_REPAIR_MODEL,
            settings.V2_VISUAL_TECHNICAL_REPAIR_PROMPT_REVISION,
            settings.V2_VISUAL_TECHNICAL_REPAIR_MAX_TOKENS,
            0.0,
            settings.V2_VISUAL_TECHNICAL_REPAIR_TIMEOUT_SECONDS,
            False,
        )
    raise ValueError(f"Unknown Phase 5 stage: {stage!r}")


def resolve_visual_routing() -> tuple[VisualStageRouting, ...]:
    if settings.V2_VISUAL_POLICY_REVISION != "2026-07-24.1":
        raise ValueError("Configured Phase 5 policy revision is unsupported")
    routes = []
    for stage in (
        "critic",
        "reviewer",
        "refinement",
        "technical_repair",
    ):
        model, prompt_revision, max_tokens, temperature, timeout, vision = (
            _stage_values(stage)
        )
        routes.append(
            VisualStageRouting(
                stage=stage,
                capability=resolve_model_capability(
                    model,
                    require_multimodal=vision,
                ),
                prompt_revision=prompt_revision,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_seconds=timeout,
            )
        )
    critic, reviewer = routes[:2]
    if critic.capability.family == reviewer.capability.family:
        raise ModelFamilyPolicyError(
            "Phase 5 critic and reviewer must use different model families."
        )
    return tuple(routes)


def visual_limits() -> VisualEvaluationLimits:
    return VisualEvaluationLimits(
        phase_timeout_seconds=settings.V2_VISUAL_PHASE_TIMEOUT_SECONDS,
        max_calls=settings.V2_VISUAL_MAX_CALLS,
        max_output_tokens=settings.V2_VISUAL_MAX_OUTPUT_TOKENS,
        max_cost_usd=settings.V2_VISUAL_MAX_COST_USD,
        max_refinement_files=8,
        max_refinement_pages=4,
        max_refinement_batches=1,
        max_technical_repairs=1,
    )


def acceptance_policy() -> VisualAcceptancePolicy:
    return VisualAcceptancePolicy()


def score_band_policy() -> ScoreBandPolicy:
    return ScoreBandPolicy()


__all__ = [
    "VisualStage",
    "acceptance_policy",
    "resolve_model_capability",
    "resolve_visual_routing",
    "score_band_policy",
    "visual_limits",
]
