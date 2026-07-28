"""Driver evidence helpers for accepted five-page booking shapes."""
from __future__ import annotations

from types import SimpleNamespace

from app.infrastructure.ai_providers.model_capabilities import (
    CAPABILITY_PROFILE_REVISION,
)
from scripts.cli.preview_v2_production_readiness import (
    CLASSIC_FIVE_PAGE_BOOKING_ROUTES,
    WIZARD_FIVE_PAGE_BOOKING_ROUTES,
    _booking_journey_proof_ok,
    _semantic_page_set_ok,
    _synthetic_cache_hit_preflight,
)


def test_semantic_page_set_accepts_classic_and_wizard() -> None:
    assert _semantic_page_set_ok(CLASSIC_FIVE_PAGE_BOOKING_ROUTES)
    assert _semantic_page_set_ok(WIZARD_FIVE_PAGE_BOOKING_ROUTES)
    assert not _semantic_page_set_ok({"PAGE-HOME": "/", "PAGE-OTHER": "/x"})


def test_booking_journey_proof_recognizes_wizard_evidence_ids() -> None:
    rows = [SimpleNamespace(passed=True, journey_id="JOURNEY-CUSTOMER-BOOKING")]
    payloads = [
        {
            "steps": [
                {"canonical_id": "ACTION-CHOOSE-SERVICE"},
                {"canonical_id": "EVIDENCE-CALENDAR-VIEW"},
                {"canonical_id": "EVIDENCE-CUSTOMER-FORM"},
                {"canonical_id": "EVIDENCE-CONFIRMATION-MESSAGE"},
            ]
        }
    ]
    assert _booking_journey_proof_ok(rows, payloads)


def test_synthetic_cache_hit_preflight_for_gemini() -> None:
    payload = _synthetic_cache_hit_preflight(
        model_manifest={
            "business_components": {
                "model": "google/gemini-2.5-flash",
                "max_tokens": 24000,
            }
        },
        stage_name="business_components",
    )
    assert payload["approval_decision"] == "approved_preflight"
    assert payload["context_window"] == 1_048_576
    assert payload["capability_profile_revision"] == CAPABILITY_PROFILE_REVISION
