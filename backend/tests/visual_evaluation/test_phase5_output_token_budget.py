"""Phase 5 output-token ceiling counts completion tokens only."""
from __future__ import annotations

import time

from app.application.visual_evaluation import service as phase5_service
from app.application.visual_evaluation.policy import visual_limits
from app.domain.schemas.visual_evaluation import VisualCallMetrics


def _metric(*, prompt: int, completion: int) -> VisualCallMetrics:
    return VisualCallMetrics(
        stage="critic",
        group_index=0,
        model="openai/gpt-4o",
        provider="fixture",
        family="openai",
        capability="multimodal_chat",
        prompt_revision="2026-07-24.1",
        temperature=0.2,
        max_tokens=12000,
        cache_hit=False,
        provider_call_count=1,
        transport_retry_count=0,
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        cost_usd=0.0,
        latency_ms=1,
    )


def test_output_token_ceiling_ignores_prompt_heavy_vision_input() -> None:
    phase5_service._budget_guard(
        (_metric(prompt=90000, completion=5000),),
        limits=visual_limits(),
        deadline=time.monotonic() + 10,
    )


def test_output_token_ceiling_trips_on_completion_tokens() -> None:
    import pytest

    with pytest.raises(Exception, match="output-token ceiling"):
        phase5_service._budget_guard(
            (_metric(prompt=100, completion=42001),),
            limits=visual_limits(),
            deadline=time.monotonic() + 10,
        )
