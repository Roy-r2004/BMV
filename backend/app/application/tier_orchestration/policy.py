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
from app.application.candidate_generation.cache import canonical_sha256
from app.application.visual_evaluation.policy import resolve_visual_routing
from app.domain.schemas.tier_orchestration import (
    Tier2Budget,
    Tier3Budget,
    Tier3VisualCallPlan,
    Tier3VisualGroupPlan,
    Tier3VisualImagePlan,
)


class Tier2BudgetError(RuntimeError):
    """Mandatory Tier 2 path cannot start within configured controls."""


class Tier3BudgetError(RuntimeError):
    """Mandatory Tier 3 path cannot start within configured controls."""


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


def tier_3_generation_policy(stage: str) -> CandidateStagePolicy:
    if stage == "business_components":
        model = settings.V2_TIER3_COMPONENT_MODEL
        return CandidateStagePolicy(
            stage="business_components",
            model=model,
            model_family=_family(model, "Tier 3 business_components"),
            prompt_revision=settings.V2_TIER3_COMPONENT_PROMPT_REVISION,
            max_tokens=settings.V2_CANDIDATE_COMPONENT_MAX_TOKENS,
            temperature=0.25,
            timeout_seconds=settings.V2_CANDIDATE_COMPONENT_TIMEOUT_SECONDS,
            ai_authored=True,
        )
    if stage == "pages":
        model = settings.V2_TIER3_PAGE_MODEL
        return CandidateStagePolicy(
            stage="pages",
            model=model,
            model_family=_family(model, "Tier 3 pages"),
            prompt_revision=settings.V2_TIER3_PAGE_PROMPT_REVISION,
            max_tokens=settings.V2_CANDIDATE_PAGE_MAX_TOKENS,
            temperature=0.25,
            timeout_seconds=settings.V2_CANDIDATE_PAGE_TIMEOUT_SECONDS,
            ai_authored=True,
        )
    raise ValueError(f"Unknown Tier 3 generation stage: {stage}")


def tier_3_static_repair_policy() -> CandidateStagePolicy:
    model = settings.V2_TIER3_REPAIR_MODEL
    return CandidateStagePolicy(
        stage="validation",
        model=model,
        model_family=_family(model, "Tier 3 static_repair"),
        prompt_revision=settings.V2_CANDIDATE_REPAIR_PROMPT_REVISION,
        max_tokens=settings.V2_CANDIDATE_REPAIR_MAX_TOKENS,
        temperature=0.0,
        timeout_seconds=settings.V2_CANDIDATE_REPAIR_TIMEOUT_SECONDS,
        ai_authored=True,
    )


def build_tier_3_visual_call_plan(
    *,
    available_pages: tuple[tuple[str, str], ...],
    selected_page_ids: tuple[str, ...],
    matched_tier_2_page_ids: tuple[str, ...],
    screenshot_bytes: dict[tuple[str, str], int] | None = None,
    excluded_page_reasons: tuple[str, ...] = (),
) -> Tier3VisualCallPlan:
    """Resolve provider-aware Phase 5 groups before the first Tier 3 call."""

    routing = resolve_visual_routing()
    critic = routing[0].capability
    reviewer = routing[1].capability
    route_by_page = dict(available_pages)
    if (
        not selected_page_ids
        or len(selected_page_ids) != len(set(selected_page_ids))
        or not set(selected_page_ids).issubset(route_by_page)
    ):
        raise Tier3BudgetError("Tier 3 visual scope is invalid")
    matched = set(matched_tier_2_page_ids)
    byte_map = screenshot_bytes or {}
    observed = tuple(value for value in byte_map.values() if value > 0)
    default_bytes = max(1, max(observed, default=512 * 1024))
    images: list[Tier3VisualImagePlan] = []
    for page_id in selected_page_ids:
        for viewport in ("mobile", "tablet", "desktop"):
            planned_bytes = int(
                byte_map.get((page_id, viewport), default_bytes)
            )
            if planned_bytes <= 0:
                raise Tier3BudgetError(
                    "Tier 3 visual byte plan contains a non-positive image"
                )
            images.append(
                Tier3VisualImagePlan(
                    ordinal=len(images),
                    page_id=page_id,
                    route=route_by_page[page_id],
                    viewport=viewport,
                    comparison_mode=(
                        "matched_tier_2"
                        if page_id in matched
                        else "candidate_only"
                    ),
                    planned_bytes=planned_bytes,
                )
            )

    by_page = {
        page_id: tuple(
            item.ordinal for item in images if item.page_id == page_id
        )
        for page_id in selected_page_ids
    }
    groups: list[Tier3VisualGroupPlan] = []
    common: list[tuple[tuple[int, ...], int, int, int, int]] = []
    pending: list[int] = []
    critic_count = critic_bytes = reviewer_count = reviewer_bytes = 0
    pending_has_matched = False
    fallback_page = next(
        (item for item in selected_page_ids if item in matched),
        None,
    )
    if fallback_page is None:
        raise Tier3BudgetError(
            "Tier 3 visual scope needs a matched Tier 2 route"
        )
    fallback_ordinals = by_page[fallback_page]
    fallback_comparison_count = len(fallback_ordinals) * 2
    fallback_comparison_bytes = sum(
        images[index].planned_bytes for index in fallback_ordinals
    ) * 2

    def flush_common() -> None:
        nonlocal pending
        nonlocal critic_count, critic_bytes, reviewer_count, reviewer_bytes
        nonlocal pending_has_matched
        if pending:
            effective_reviewer_count = reviewer_count
            effective_reviewer_bytes = reviewer_bytes
            if not pending_has_matched:
                effective_reviewer_count += fallback_comparison_count
                effective_reviewer_bytes += fallback_comparison_bytes
            if (
                effective_reviewer_count > reviewer.max_images
                or effective_reviewer_bytes
                > reviewer.max_aggregate_image_bytes
            ):
                raise Tier3BudgetError(
                    "Tier 3 fallback comparison exceeds reviewer capability"
                )
            common.append(
                (
                    tuple(pending),
                    critic_count,
                    critic_bytes,
                    effective_reviewer_count,
                    effective_reviewer_bytes,
                )
            )
        pending = []
        critic_count = critic_bytes = reviewer_count = reviewer_bytes = 0
        pending_has_matched = False

    for page_id in selected_page_ids:
        ordinals = by_page[page_id]
        candidate_bytes = sum(
            images[index].planned_bytes for index in ordinals
        )
        reviewer_multiplier = 2 if page_id in matched else 1
        next_critic_count = len(ordinals)
        next_reviewer_count = len(ordinals) * reviewer_multiplier
        next_critic_bytes = candidate_bytes
        next_reviewer_bytes = candidate_bytes * reviewer_multiplier
        if (
            next_critic_count > critic.max_images
            or next_reviewer_count > reviewer.max_images
            or next_critic_bytes > critic.max_aggregate_image_bytes
            or next_reviewer_bytes
            > reviewer.max_aggregate_image_bytes
            or any(
                images[index].planned_bytes
                > min(
                    critic.max_image_bytes,
                    reviewer.max_image_bytes,
                )
                for index in ordinals
            )
        ):
            raise Tier3BudgetError(
                f"Tier 3 route {page_id} exceeds visual capabilities"
            )
        next_has_matched = pending_has_matched or page_id in matched
        prospective_reviewer_count = (
            reviewer_count + next_reviewer_count
        )
        prospective_reviewer_bytes = (
            reviewer_bytes + next_reviewer_bytes
        )
        if not next_has_matched:
            prospective_reviewer_count += fallback_comparison_count
            prospective_reviewer_bytes += fallback_comparison_bytes
        if pending and (
            critic_count + next_critic_count > critic.max_images
            or prospective_reviewer_count > reviewer.max_images
            or critic_bytes + next_critic_bytes
            > critic.max_aggregate_image_bytes
            or prospective_reviewer_bytes
            > reviewer.max_aggregate_image_bytes
        ):
            flush_common()
        pending.extend(ordinals)
        critic_count += next_critic_count
        critic_bytes += next_critic_bytes
        reviewer_count += next_reviewer_count
        reviewer_bytes += next_reviewer_bytes
        pending_has_matched = pending_has_matched or page_id in matched
    flush_common()
    for actor in ("critic", "reviewer"):
        for index, (
            ordinals,
            c_count,
            c_bytes,
            r_count,
            r_bytes,
        ) in enumerate(common):
            candidate_count = len(ordinals)
            provider_count = c_count if actor == "critic" else r_count
            provider_bytes = c_bytes if actor == "critic" else r_bytes
            groups.append(
                Tier3VisualGroupPlan(
                    actor=actor,
                    group_index=index,
                    candidate_image_ordinals=ordinals,
                    comparison_image_count=(
                        provider_count - candidate_count
                    ),
                    total_provider_images=provider_count,
                    total_provider_bytes=provider_bytes,
                )
            )
    critic_calls = sum(1 for item in groups if item.actor == "critic")
    reviewer_calls = sum(1 for item in groups if item.actor == "reviewer")
    mandatory_calls = 2 + critic_calls + reviewer_calls
    if mandatory_calls > settings.V2_TIER3_MAX_CALLS:
        raise Tier3BudgetError(
            "Tier 3 provider grouping exceeds its hard call ceiling"
        )
    payload = {
        "pages": available_pages,
        "selected": selected_page_ids,
        "excluded": excluded_page_reasons,
        "images": [item.model_dump(mode="json") for item in images],
        "groups": [item.model_dump(mode="json") for item in groups],
        "routing": [
            routing[0].model_dump(mode="json"),
            routing[1].model_dump(mode="json"),
        ],
    }
    return Tier3VisualCallPlan(
        available_page_ids=tuple(item[0] for item in available_pages),
        selected_page_ids=selected_page_ids,
        excluded_page_reasons=excluded_page_reasons,
        images=tuple(images),
        groups=tuple(groups),
        screenshot_count=len(images),
        total_planned_bytes=sum(item.planned_bytes for item in images),
        critic_group_calls=critic_calls,
        reviewer_group_calls=reviewer_calls,
        aggregation_calls=0,
        mandatory_calls=mandatory_calls,
        optional_call_reserve=max(
            0,
            settings.V2_TIER3_MAX_CALLS - mandatory_calls,
        ),
        critic_model=critic.model,
        reviewer_model=reviewer.model,
        critic_max_images=critic.max_images,
        reviewer_max_images=reviewer.max_images,
        critic_max_image_bytes=critic.max_image_bytes,
        reviewer_max_image_bytes=reviewer.max_image_bytes,
        grouping_sha256=canonical_sha256(payload),
    )


def tier_3_budget(plan: Tier3VisualCallPlan) -> Tier3Budget:
    return Tier3Budget(
        max_calls=settings.V2_TIER3_MAX_CALLS,
        max_output_tokens=settings.V2_TIER3_MAX_OUTPUT_TOKENS,
        max_cost_usd=settings.V2_TIER3_MAX_COST_USD,
        max_wall_seconds=settings.V2_TIER3_MAX_WALL_SECONDS,
        mandatory_calls=plan.mandatory_calls,
        optional_call_reserve=plan.optional_call_reserve,
    )


def preflight_tier_3_budget(
    db: Session,
    *,
    request_id: int,
    ai_provider,
    plan: Tier3VisualCallPlan,
    phase6a_calls: int,
    phase6a_output_tokens: int,
    phase6a_cost_usd: float,
    phase6a_latency_ms: int,
) -> Tier3Budget:
    """Fail before generation unless the exact mandatory path fits."""

    budget = tier_3_budget(plan)
    component = tier_3_generation_policy("business_components")
    page = tier_3_generation_policy("pages")
    tier_3_static_repair_policy()
    mandatory_tokens = (
        component.max_tokens
        + page.max_tokens
        + plan.critic_group_calls
        * settings.V2_VISUAL_CRITIC_MAX_TOKENS
        + plan.reviewer_group_calls
        * settings.V2_VISUAL_REVIEWER_MAX_TOKENS
    )
    mandatory_wall = (
        component.timeout_seconds
        + page.timeout_seconds
        + settings.V2_RUNTIME_PHASE_TIMEOUT_SECONDS
        + plan.critic_group_calls
        * settings.V2_VISUAL_CRITIC_TIMEOUT_SECONDS
        + plan.reviewer_group_calls
        * settings.V2_VISUAL_REVIEWER_TIMEOUT_SECONDS
    )
    if (
        plan.mandatory_calls > budget.max_calls
        or mandatory_tokens > budget.max_output_tokens
        or mandatory_wall > budget.max_wall_seconds
        or phase6a_calls + plan.mandatory_calls
        > budget.aggregate_phase6_max_calls
        or phase6a_output_tokens + mandatory_tokens
        > budget.aggregate_phase6_max_output_tokens
        or phase6a_cost_usd + budget.max_cost_usd
        > budget.aggregate_phase6_max_cost_usd
        or phase6a_latency_ms + mandatory_wall * 1000
        > budget.aggregate_phase6_max_wall_seconds * 1000
    ):
        raise Tier3BudgetError(
            "Tier 3 mandatory path exceeds Phase 6 hard ceilings"
        )
    if isinstance(ai_provider, BudgetedAIProvider):
        remaining = ai_provider.budget.max_calls - ai_provider.budget.used
        if remaining < plan.mandatory_calls:
            raise Tier3BudgetError(
                "Request-wide call budget cannot afford Tier 3"
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
            raise Tier3BudgetError(
                "Request cost budget cannot afford Tier 3"
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
                raise Tier3BudgetError(
                    "Daily cost budget cannot afford Tier 3"
                )
    return budget


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
    "Tier3BudgetError",
    "build_tier_3_visual_call_plan",
    "preflight_tier_2_budget",
    "tier_2_budget",
    "tier_2_generation_policy",
    "tier_2_static_repair_policy",
    "preflight_tier_3_budget",
    "tier_3_budget",
    "tier_3_generation_policy",
    "tier_3_static_repair_policy",
]
