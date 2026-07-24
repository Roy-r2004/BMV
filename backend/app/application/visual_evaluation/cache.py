"""Canonical Phase 5 cache keys with complete policy/model provenance."""
from __future__ import annotations

from app.application.candidate_generation.cache import canonical_sha256
from app.domain.schemas.visual_evaluation import (
    ScoreBandPolicy,
    VisualAcceptancePolicy,
    VisualEvaluationLimits,
    VisualEvaluationRefs,
    VisualEvidenceBundle,
    VisualStageRouting,
)


def evaluation_cache_key(
    *,
    refs: VisualEvaluationRefs,
    bundle: VisualEvidenceBundle,
    routing: tuple[VisualStageRouting, ...],
    limits: VisualEvaluationLimits,
    score_bands: ScoreBandPolicy,
    acceptance: VisualAcceptancePolicy,
    baseline_identity: str | None,
) -> str:
    return canonical_sha256(
        {
            "stage": "visual_evaluation",
            "refs": refs.model_dump(mode="json"),
            "ordered_screenshot_hashes": bundle.ordered_screenshot_hashes,
            "grouping_manifest": [
                item.model_dump(mode="json")
                for item in bundle.grouping_manifest
            ],
            "capture_policy_revision": bundle.capture_policy_revision,
            "image_bundle_policy_revision": (
                bundle.image_bundle_policy_revision
            ),
            "routing": [item.model_dump(mode="json") for item in routing],
            "limits": limits.model_dump(mode="json"),
            "score_bands": score_bands.model_dump(mode="json"),
            "acceptance": acceptance.model_dump(mode="json"),
            "baseline_identity": baseline_identity,
        }
    )


def artifact_cache_key(stage: str, payload: object) -> str:
    return canonical_sha256({"stage": stage, "payload": payload})


__all__ = ["artifact_cache_key", "evaluation_cache_key"]
