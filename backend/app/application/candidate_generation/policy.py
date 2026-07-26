"""Phase 3B model routing and hard performance policy."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.appspec.policy import (
    ModelFamilyPolicyError,
    model_family,
)
from app.core.config import settings
from app.domain.schemas.preview_candidate import CandidateArtifactKind


@dataclass(frozen=True)
class CandidateStagePolicy:
    stage: CandidateArtifactKind
    model: str
    model_family: str
    prompt_revision: str
    max_tokens: int
    temperature: float
    timeout_seconds: int
    ai_authored: bool


def _known_model(model: str, *, stage: str) -> str:
    family = model_family(model)
    if family is None:
        raise ModelFamilyPolicyError(
            f"Unknown model family for {stage}: {model!r}; "
            "Phase 3B fails closed before provider calls."
        )
    return family


def resolve_candidate_stage_policy(
    stage: CandidateArtifactKind,
) -> CandidateStagePolicy:
    if stage == "business_components":
        model = settings.V2_CANDIDATE_COMPONENT_MODEL
        return CandidateStagePolicy(
            stage=stage,
            model=model,
            model_family=_known_model(model, stage=stage),
            prompt_revision=settings.V2_CANDIDATE_COMPONENT_PROMPT_REVISION,
            max_tokens=settings.V2_CANDIDATE_COMPONENT_MAX_TOKENS,
            temperature=0.25,
            timeout_seconds=settings.V2_CANDIDATE_COMPONENT_TIMEOUT_SECONDS,
            ai_authored=True,
        )
    if stage == "pages":
        model = str(settings.V2_CANDIDATE_PAGE_MODEL or "").strip()
        if not model:
            raise ModelFamilyPolicyError(
                "candidate_page_model_not_configured: "
                "V2_CANDIDATE_PAGE_MODEL is missing or empty; "
                "pages stage fails closed before provider calls."
            )
        return CandidateStagePolicy(
            stage=stage,
            model=model,
            model_family=_known_model(model, stage=stage),
            prompt_revision=settings.V2_CANDIDATE_PAGE_PROMPT_REVISION,
            max_tokens=settings.V2_CANDIDATE_PAGE_MAX_TOKENS,
            temperature=0.25,
            timeout_seconds=settings.V2_CANDIDATE_PAGE_TIMEOUT_SECONDS,
            ai_authored=True,
        )
    if stage in {"foundation", "data_exports", "routes", "validation"}:
        return CandidateStagePolicy(
            stage=stage,
            model="deterministic",
            model_family="deterministic",
            prompt_revision=CANDIDATE_DETERMINISTIC_REVISION,
            max_tokens=0,
            temperature=0.0,
            timeout_seconds=0,
            ai_authored=False,
        )
    raise ValueError(f"Unknown candidate stage: {stage!r}")


CANDIDATE_DETERMINISTIC_REVISION = "2026-07-24.1"


def repair_policy() -> CandidateStagePolicy:
    model = settings.V2_CANDIDATE_REPAIR_MODEL
    return CandidateStagePolicy(
        stage="validation",
        model=model,
        model_family=_known_model(model, stage="candidate_repair"),
        prompt_revision=settings.V2_CANDIDATE_REPAIR_PROMPT_REVISION,
        max_tokens=settings.V2_CANDIDATE_REPAIR_MAX_TOKENS,
        temperature=0.0,
        timeout_seconds=settings.V2_CANDIDATE_REPAIR_TIMEOUT_SECONDS,
        ai_authored=True,
    )


__all__ = [
    "CANDIDATE_DETERMINISTIC_REVISION",
    "CandidateStagePolicy",
    "repair_policy",
    "resolve_candidate_stage_policy",
]
