"""Phase 6A model routing and aggregate limits."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.application.appspec.policy import ModelFamilyPolicyError, model_family
from app.application.candidate_generation.policy import CandidateStagePolicy
from app.application.preview_app.ai_budget import BudgetedAIProvider
from app.core.config import settings
from app.domain.models import AdminSettings, AiUsageEvent
from app.domain.schemas.tier_orchestration import Tier2Budget


class Tier2BudgetError(RuntimeError):
    """Mandatory Tier 2 path cannot start within configured controls."""


def _family(model: str, stage: str) -> str:
    family = model_family(model)
    if family is None:
        raise ModelFamilyPolicyError(
            f"Unknown model family for Tier 2 {stage}: {model!r}"
        )
    return family


def tier_2_generation_policy(stage: str) -> CandidateStagePolicy:
    if stage == "business_components":
        model = settings.V2_TIER2_COMPONENT_MODEL
        return CandidateStagePolicy(
            stage="business_components",
            model=model,
            model_family=_family(model, stage),
            prompt_revision=settings.V2_TIER2_COMPONENT_PROMPT_REVISION,
            max_tokens=settings.V2_CANDIDATE_COMPONENT_MAX_TOKENS,
            temperature=0.25,
            timeout_seconds=settings.V2_CANDIDATE_COMPONENT_TIMEOUT_SECONDS,
            ai_authored=True,
        )
    if stage == "pages":
        model = settings.V2_TIER2_PAGE_MODEL
        return CandidateStagePolicy(
            stage="pages",
            model=model,
            model_family=_family(model, stage),
            prompt_revision=settings.V2_TIER2_PAGE_PROMPT_REVISION,
            max_tokens=settings.V2_CANDIDATE_PAGE_MAX_TOKENS,
            temperature=0.25,
            timeout_seconds=settings.V2_CANDIDATE_PAGE_TIMEOUT_SECONDS,
            ai_authored=True,
        )
    raise ValueError(f"Unknown Tier 2 generation stage: {stage}")


def tier_2_static_repair_policy() -> CandidateStagePolicy:
    model = settings.V2_TIER2_REPAIR_MODEL
    return CandidateStagePolicy(
        stage="validation",
        model=model,
        model_family=_family(model, "static_repair"),
        prompt_revision=settings.V2_CANDIDATE_REPAIR_PROMPT_REVISION,
        max_tokens=settings.V2_CANDIDATE_REPAIR_MAX_TOKENS,
        temperature=0.0,
        timeout_seconds=settings.V2_CANDIDATE_REPAIR_TIMEOUT_SECONDS,
        ai_authored=True,
    )


def tier_2_budget() -> Tier2Budget:
    return Tier2Budget(
        max_calls=settings.V2_TIER2_MAX_CALLS,
        max_output_tokens=settings.V2_TIER2_MAX_OUTPUT_TOKENS,
        max_cost_usd=settings.V2_TIER2_MAX_COST_USD,
        max_wall_seconds=settings.V2_TIER2_MAX_WALL_SECONDS,
    )


def preflight_tier_2_budget(
    db: Session,
    *,
    request_id: int,
    ai_provider,
) -> Tier2Budget:
    """Validate mandatory 2 generation + 2 visual calls before any provider."""

    budget = tier_2_budget()
    component = tier_2_generation_policy("business_components")
    page = tier_2_generation_policy("pages")
    tier_2_static_repair_policy()
    mandatory_tokens = (
        component.max_tokens
        + page.max_tokens
        + settings.V2_VISUAL_CRITIC_MAX_TOKENS
        + settings.V2_VISUAL_REVIEWER_MAX_TOKENS
    )
    mandatory_wall_seconds = (
        component.timeout_seconds
        + page.timeout_seconds
        + settings.V2_RUNTIME_PHASE_TIMEOUT_SECONDS
        + settings.V2_VISUAL_CRITIC_TIMEOUT_SECONDS
        + settings.V2_VISUAL_REVIEWER_TIMEOUT_SECONDS
    )
    if (
        budget.max_calls < 4
        or budget.max_output_tokens < mandatory_tokens
        or budget.max_wall_seconds < mandatory_wall_seconds
    ):
        raise Tier2BudgetError(
            "Tier 2 aggregate limits cannot afford the mandatory path"
        )
    if isinstance(ai_provider, BudgetedAIProvider):
        remaining_calls = (
            ai_provider.budget.max_calls - ai_provider.budget.used
        )
        if remaining_calls < 4:
            raise Tier2BudgetError(
                "Request-wide call budget cannot afford Tier 2"
            )
    admin = db.get(AdminSettings, 1)
    if admin is not None:
        request_spend = float(
            db.query(func.coalesce(func.sum(AiUsageEvent.cost_usd), 0.0))
            .filter(AiUsageEvent.request_id == request_id)
            .scalar()
            or 0.0
        )
        if (
            admin.request_budget_usd is not None
            and float(admin.request_budget_usd) - request_spend
            < budget.max_cost_usd
        ):
            raise Tier2BudgetError(
                "Request cost budget cannot afford Tier 2's mandatory path"
            )
        if admin.daily_budget_usd is not None:
            start = datetime.utcnow().replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            daily_spend = float(
                db.query(func.coalesce(func.sum(AiUsageEvent.cost_usd), 0.0))
                .filter(AiUsageEvent.created_at >= start)
                .scalar()
                or 0.0
            )
            if (
                float(admin.daily_budget_usd) - daily_spend
                < budget.max_cost_usd
            ):
                raise Tier2BudgetError(
                    "Daily cost budget cannot afford Tier 2's mandatory path"
                )
    return budget


__all__ = [
    "Tier2BudgetError",
    "preflight_tier_2_budget",
    "tier_2_budget",
    "tier_2_generation_policy",
    "tier_2_static_repair_policy",
]
