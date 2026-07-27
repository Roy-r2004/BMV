"""VisualEvaluationSummary must allow multimodal total_tokens above 42k."""
from __future__ import annotations

from pydantic.fields import FieldInfo

from app.domain.schemas.visual_evaluation import VisualEvaluationSummary


def _numeric_constraints(field: FieldInfo) -> dict[str, object]:
    out: dict[str, object] = {}
    for item in field.metadata:
        for key in ("ge", "gt", "le", "lt", "multiple_of"):
            if hasattr(item, key):
                value = getattr(item, key)
                if value is not None:
                    out[key] = value
    return out


def test_summary_total_tokens_has_no_output_ceiling() -> None:
    constraints = _numeric_constraints(
        VisualEvaluationSummary.model_fields["total_tokens"]
    )
    assert constraints.get("ge") == 0
    assert "le" not in constraints


def test_summary_completion_tokens_enforce_output_ceiling() -> None:
    constraints = _numeric_constraints(
        VisualEvaluationSummary.model_fields["completion_tokens"]
    )
    assert constraints.get("ge") == 0
    assert constraints.get("le") == 42_000
