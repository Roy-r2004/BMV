"""Strict baseline eligibility and deterministic blind A/B labeling."""
from __future__ import annotations

from app.application.candidate_generation.cache import canonical_sha256
from app.application.visual_evaluation.context import VisualEvaluationContext
from app.domain.schemas.visual_evaluation import CandidateBaselineComparison


def blind_label_order(
    identity_one: str,
    identity_two: str,
    *,
    attempt_hash: str,
) -> tuple[str, str]:
    ranked = sorted(
        (identity_one, identity_two),
        key=lambda value: canonical_sha256(
            {"attempt_hash": attempt_hash, "identity": value}
        ),
    )
    return ranked[0], ranked[1]


def resolve_baseline(
    context: VisualEvaluationContext,
    *,
    attempt_hash: str,
) -> CandidateBaselineComparison:
    # Phase 5 cannot infer that an arbitrary legacy PREVIEW_APPS_DIR directory
    # is accepted, immutable, or captured under Phase 4. A future promotion
    # phase may persist a verified accepted-candidate pointer; until then this
    # truthful absolute-only artifact prevents a false improvement claim.
    return CandidateBaselineComparison(
        mode="absolute_only",
        reason=(
            "No accepted preview with a same-policy Phase 4 validation "
            "summary and exact/unique semantic route match exists."
        ),
        attempt_hash=attempt_hash,
    )


__all__ = ["blind_label_order", "resolve_baseline"]
