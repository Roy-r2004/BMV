"""AppSpec coverage review must tolerate LLM-invented extra keys."""
from __future__ import annotations

from app.application.appspec.coverage import AppSpecCoverageReview


def test_coverage_review_ignores_llm_extra_fields() -> None:
    """Models often add assumption_ids etc.; that must not fail closed."""
    payload = {
        "verdict": "pass",
        "score": 92,
        "summary": "Goals covered.",
        "goal_coverage": [
            {
                "source_path": "customer_input.desired_outcome",
                "source_excerpt": "Sell paintings online",
                "covered": True,
                "requirement_ids": ["req-gallery"],
                "evidence_ids": ["ev-gallery"],
                "acceptance_test_ids": ["test-gallery"],
                "notes": "",
                # Invented by the model — previously blew up request 15.
                "assumption_ids": ["ASSUMPTION-SINGLE-ADMIN"],
            }
        ],
        "omissions": [],
        "contradictions": [],
        "unsupported_additions": [
            {
                "code": "extra",
                "severity": "minor",
                "message": "ok",
                "invented_key": True,
            }
        ],
        "mislabeled_assumptions": [],
        "open_question_gaps": [],
        "also_invented_top_level": {"nope": True},
    }
    review = AppSpecCoverageReview.model_validate(payload)
    assert review.verdict == "pass"
    assert review.goal_coverage[0].requirement_ids == ["req-gallery"]
    dumped = review.model_dump()
    assert "assumption_ids" not in dumped["goal_coverage"][0]
    assert "also_invented_top_level" not in dumped
