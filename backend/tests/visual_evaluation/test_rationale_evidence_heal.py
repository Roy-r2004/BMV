"""Heal AI visual rationales so strict evidence-link checks can pass."""
from __future__ import annotations

from app.application.visual_evaluation.scoring import (
    _anchor_score_band,
    _heal_assessment,
    _link_citations,
)
from app.domain.schemas.visual_evaluation import VisualDimensionAssessment


def test_link_citations_appends_missing_evidence_ids() -> None:
    text = _link_citations(
        "The booking pages look usable.",
        ("EVIDENCE-1", "/book/start"),
    )
    assert "EVIDENCE-1" in text
    assert "/book/start" in text


def test_anchor_score_band_injects_required_tokens() -> None:
    text = _anchor_score_band("Looks good overall.", 85)
    assert "strong" in text.casefold() or "professional" in text.casefold()


def test_heal_assessment_makes_rationale_evidence_linked() -> None:
    item = VisualDimensionAssessment(
        dimension="business_specificity",
        score=82,
        confidence=0.7,
        evidence_ids=("EVIDENCE-HOME",),
        affected_routes=("/book/start",),
        affected_viewports=("desktop",),
        rationale="The product feels generic without naming the flow.",
        failure_severity="minor",
        deterministic_support=False,
    )
    healed = _heal_assessment(item)
    assert "EVIDENCE-HOME" in healed.rationale
    assert "/book/start" in healed.rationale
