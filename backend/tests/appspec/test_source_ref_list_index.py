"""AppSpec source refs may address list items (ai_features.0.description)."""
from __future__ import annotations

from app.application.appspec.generation import _resolve_source_ref, _source_reference_issues


class _Req:
    def __init__(self, rid: str, refs: list[str]) -> None:
        self.id = rid
        self.source_refs = refs


class _Spec:
    def __init__(self, requirements: list[_Req]) -> None:
        self.requirements = requirements


def test_resolve_source_ref_supports_list_indices() -> None:
    snapshot = {
        "customer_input": {
            "ai_features": [
                {
                    "id": "ai-class-advisor",
                    "name": "AI Class Advisor",
                    "description": "Recommends pottery classes.",
                }
            ]
        }
    }
    assert (
        _resolve_source_ref(snapshot, "customer_input.ai_features.0.description")
        == "Recommends pottery classes."
    )
    assert _resolve_source_ref(snapshot, "customer_input.ai_features.1.description") is None
    assert _resolve_source_ref(snapshot, "customer_input.ai_features") == snapshot[
        "customer_input"
    ]["ai_features"]


def test_coverage_requires_repair_accepts_ai_feature_indexed_source_paths() -> None:
    from app.application.appspec.coverage import (
        AppSpecCoverageReview,
        coverage_requires_repair,
    )

    snapshot = {
        "customer_input": {
            "desired_outcome": "Book classes online",
            "ai_features": [
                {"description": "Recommends pottery classes."},
            ],
        }
    }
    review = AppSpecCoverageReview.model_validate(
        {
            "verdict": "pass",
            "score": 100,
            "summary": "ok",
            "goal_coverage": [
                {
                    "source_path": "customer_input.ai_features.0.description",
                    "source_excerpt": "Recommends pottery classes.",
                    "covered": True,
                    "requirement_ids": [],
                    "evidence_ids": [],
                    "acceptance_test_ids": [],
                    "notes": "",
                }
            ],
            "omissions": [],
            "contradictions": [],
            "unsupported_additions": [],
            "mislabeled_assumptions": [],
            "open_question_gaps": [],
        }
    )
    assert (
        coverage_requires_repair(review, app_spec=None, source_snapshot=snapshot)
        is False
    )


def test_source_reference_issues_accepts_ai_feature_indexed_refs() -> None:
    snapshot = {
        "customer_input": {
            "ai_features": [
                {"description": "Recommends pottery classes."},
                {"description": "Answers studio FAQs."},
            ]
        }
    }
    spec = _Spec(
        [
            _Req("REQ-AI-1", ["customer_input.ai_features.0.description"]),
            _Req("REQ-AI-2", ["customer_input.ai_features.1.description"]),
        ]
    )
    assert _source_reference_issues(spec, snapshot) == []  # type: ignore[arg-type]
