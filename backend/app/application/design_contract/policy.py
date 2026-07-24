"""Stage-specific Phase 2 routing, budgets, and fail-closed model policy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.application.appspec.policy import ModelFamilyPolicyError, model_family
from app.core.config import settings


DesignStage = Literal[
    "product_strategy_v2",
    "information_architecture",
    "design_dna",
]


@dataclass(frozen=True)
class DesignStagePolicy:
    stage: DesignStage
    model: str
    model_family: str
    prompt_revision: str
    max_tokens: int
    temperature: float
    max_attempts: int
    timeout_seconds: int
    use_vision: bool = False


def _known_model(model: str, *, stage: DesignStage) -> str:
    family = model_family(model)
    if family is None:
        raise ModelFamilyPolicyError(
            f"Unknown model family for {stage}: {model!r}; "
            "Phase 2 fails closed before provider calls."
        )
    return family


def resolve_design_stage_policy(
    stage: DesignStage,
    *,
    use_vision: bool = False,
) -> DesignStagePolicy:
    if stage == "product_strategy_v2":
        model = settings.V2_PRODUCT_STRATEGY_MODEL
        prompt_revision = settings.V2_PRODUCT_STRATEGY_PROMPT_REVISION
        max_tokens = settings.V2_PRODUCT_STRATEGY_MAX_TOKENS
        temperature = 0.2
        timeout_seconds = settings.V2_PRODUCT_STRATEGY_TIMEOUT_SECONDS
    elif stage == "information_architecture":
        model = settings.V2_INFORMATION_ARCHITECTURE_MODEL
        prompt_revision = settings.V2_INFORMATION_ARCHITECTURE_PROMPT_REVISION
        max_tokens = settings.V2_INFORMATION_ARCHITECTURE_MAX_TOKENS
        temperature = 0.1
        timeout_seconds = settings.V2_INFORMATION_ARCHITECTURE_TIMEOUT_SECONDS
    elif stage == "design_dna":
        model = (
            settings.V2_DESIGN_DNA_VISION_MODEL
            if use_vision
            else settings.V2_DESIGN_DNA_MODEL
        )
        prompt_revision = settings.V2_DESIGN_DNA_PROMPT_REVISION
        max_tokens = settings.V2_DESIGN_DNA_MAX_TOKENS
        temperature = 0.3
        timeout_seconds = settings.V2_DESIGN_DNA_TIMEOUT_SECONDS
    else:
        raise ValueError(f"Unknown design stage: {stage!r}")
    return DesignStagePolicy(
        stage=stage,
        model=model,
        model_family=_known_model(model, stage=stage),
        prompt_revision=prompt_revision,
        max_tokens=max_tokens,
        temperature=temperature,
        max_attempts=settings.V2_DESIGN_STAGE_MAX_ATTEMPTS,
        timeout_seconds=timeout_seconds,
        use_vision=use_vision,
    )


__all__ = [
    "DesignStage",
    "DesignStagePolicy",
    "resolve_design_stage_policy",
]
