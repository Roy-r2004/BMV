"""Phase 3A stage routing, provenance, and fail-closed model policy."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.appspec.policy import ModelFamilyPolicyError, model_family
from app.core.config import settings
from app.domain.schemas.composition_contract import CompositionArtifactKind


@dataclass(frozen=True)
class CompositionStagePolicy:
    stage: CompositionArtifactKind
    model: str
    model_family: str
    prompt_revision: str
    max_tokens: int
    temperature: float
    max_attempts: int
    timeout_seconds: int
    ai_authored: bool


def _known_model(
    model: str,
    *,
    stage: CompositionArtifactKind,
) -> str:
    family = model_family(model)
    if family is None:
        raise ModelFamilyPolicyError(
            f"Unknown model family for {stage}: {model!r}; "
            "Phase 3A fails closed before provider calls."
        )
    return family


def resolve_composition_stage_policy(
    stage: CompositionArtifactKind,
) -> CompositionStagePolicy:
    if stage == "business_component_plan":
        model = settings.V2_BUSINESS_COMPONENT_MODEL
        return CompositionStagePolicy(
            stage=stage,
            model=model,
            model_family=_known_model(model, stage=stage),
            prompt_revision=(
                settings.V2_BUSINESS_COMPONENT_PROMPT_REVISION
            ),
            max_tokens=settings.V2_BUSINESS_COMPONENT_MAX_TOKENS,
            temperature=0.2,
            max_attempts=settings.V2_COMPOSITION_AI_STAGE_MAX_ATTEMPTS,
            timeout_seconds=(
                settings.V2_BUSINESS_COMPONENT_TIMEOUT_SECONDS
            ),
            ai_authored=True,
        )
    if stage == "content_data_plan":
        model = settings.V2_CONTENT_DATA_MODEL
        return CompositionStagePolicy(
            stage=stage,
            model=model,
            model_family=_known_model(model, stage=stage),
            prompt_revision=settings.V2_CONTENT_DATA_PROMPT_REVISION,
            max_tokens=settings.V2_CONTENT_DATA_MAX_TOKENS,
            temperature=0.1,
            max_attempts=settings.V2_COMPOSITION_AI_STAGE_MAX_ATTEMPTS,
            timeout_seconds=settings.V2_CONTENT_DATA_TIMEOUT_SECONDS,
            ai_authored=True,
        )
    if stage in {
        "page_purpose_contract",
        "interaction_contract",
        "component_dependency_graph",
    }:
        return CompositionStagePolicy(
            stage=stage,
            model="deterministic",
            model_family="deterministic",
            prompt_revision="deterministic",
            max_tokens=0,
            temperature=0.0,
            max_attempts=1,
            timeout_seconds=0,
            ai_authored=False,
        )
    raise ValueError(f"Unknown composition stage: {stage!r}")


__all__ = [
    "CompositionStagePolicy",
    "resolve_composition_stage_policy",
]
