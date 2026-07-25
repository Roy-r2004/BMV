"""Hard budget model for business_component_plan reliability."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class BusinessComponentPlanBudgets:
    stage_wall_seconds: float
    max_provider_calls: int
    per_call_timeout_seconds: float
    max_validation_retries: int
    max_input_tokens: int
    max_output_tokens: int
    max_deterministic_repair: int
    max_ai_repair: int
    min_call_budget_seconds: float
    recovery_model: str


def resolve_business_component_plan_budgets() -> BusinessComponentPlanBudgets:
    # Legacy V2_BUSINESS_COMPONENT_TIMEOUT_SECONDS remains the stage wall so
    # existing env/tests keep controlling the total deadline.
    stage_wall = float(settings.V2_BUSINESS_COMPONENT_TIMEOUT_SECONDS)
    per_call = float(
        getattr(
            settings,
            "V2_BUSINESS_COMPONENT_PER_CALL_TIMEOUT_SECONDS",
            min(180, stage_wall),
        )
    )
    max_calls = int(
        getattr(settings, "V2_BUSINESS_COMPONENT_MAX_PROVIDER_CALLS", 2)
    )
    max_retries = int(
        getattr(settings, "V2_BUSINESS_COMPONENT_MAX_RETRIES", 1)
    )
    max_input = int(
        getattr(settings, "V2_BUSINESS_COMPONENT_MAX_INPUT_TOKENS", 24000)
    )
    max_output = int(settings.V2_BUSINESS_COMPONENT_MAX_TOKENS)
    max_det_repair = int(
        getattr(
            settings,
            "V2_BUSINESS_COMPONENT_MAX_DETERMINISTIC_REPAIR",
            1,
        )
    )
    max_ai_repair = int(
        getattr(settings, "V2_BUSINESS_COMPONENT_MAX_AI_REPAIR", 1)
    )
    min_call = float(
        getattr(
            settings,
            "V2_BUSINESS_COMPONENT_MIN_CALL_BUDGET_SECONDS",
            15.0,
        )
    )
    recovery_model = str(
        getattr(
            settings,
            "V2_BUSINESS_COMPONENT_RECOVERY_MODEL",
            "",
        )
        or settings.V2_BUSINESS_COMPONENT_MODEL
    ).strip()
    # Nested budgets cannot exceed the stage wall.
    stage_wall = max(0.0, stage_wall)
    per_call = max(0.01, min(per_call, stage_wall if stage_wall > 0 else per_call))
    max_calls = max(1, min(max_calls, 2))
    max_retries = max(0, min(max_retries, max_calls - 1))
    max_ai_repair = max(0, min(max_ai_repair, max_retries))
    max_det_repair = max(0, min(max_det_repair, 1))
    min_call = max(0.001, min(min_call, per_call))
    return BusinessComponentPlanBudgets(
        stage_wall_seconds=min(900.0, stage_wall),
        max_provider_calls=max_calls,
        per_call_timeout_seconds=per_call,
        max_validation_retries=max_retries,
        max_input_tokens=min(48000, max(1000, max_input)),
        max_output_tokens=min(16000, max(500, max_output)),
        max_deterministic_repair=max_det_repair,
        max_ai_repair=max_ai_repair,
        min_call_budget_seconds=min_call,
        recovery_model=recovery_model,
    )


__all__ = [
    "BusinessComponentPlanBudgets",
    "resolve_business_component_plan_budgets",
]
