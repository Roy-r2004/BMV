from __future__ import annotations

import pytest

from app.application.tier_orchestration.service import (
    Tier2OrchestrationError,
    orchestrate_v2_tier_2,
)
from app.core.config import settings
from tests.candidate_generation.helpers import prepare_phase3a


def test_flag_false_returns_exact_phase5_object(monkeypatch) -> None:
    monkeypatch.setattr(settings, "V2_TIER2_GENERATION_ENABLED", False)
    phase5 = {"preview_contract": {"status": "candidate_visual_accepted"}}
    assert (
        orchestrate_v2_tier_2(
            None,
            1,
            None,
            None,
            req=None,
            phase5_result=phase5,
        )
        is phase5
    )


def test_tier_2_requires_accepted_tier_1_visual_status(monkeypatch) -> None:
    prepared = prepare_phase3a(request_id=21010)
    monkeypatch.setattr(settings, "V2_TIER2_GENERATION_ENABLED", True)
    with pytest.raises(Tier2OrchestrationError, match="requires accepted"):
        orchestrate_v2_tier_2(
            prepared.db,
            prepared.req.id,
            object(),
            object(),
            req=prepared.req,
            phase5_result={
                "preview_contract": {
                    "status": "candidate_visual_rejected"
                }
            },
        )
