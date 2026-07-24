"""Deterministic advisory filesystem/manifest comparison for Phase 7B."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Sequence

from app.domain.schemas.shadow_evaluation import (
    SHADOW_COMPARISON_POLICY_REVISION,
    ShadowComparisonArtifact,
)


@dataclass(frozen=True)
class ComparisonInputs:
    served_target_kind: str
    served_pointer_version: int | None
    v2_candidate_revision_id: int | None
    v2_effective_summary_id: int | None
    served_target_hash: str | None
    candidate_manifest_sha256: str | None
    effective_summary_sha256: str | None
    served_routes: Sequence[str] | None
    candidate_routes: Sequence[str] | None
    dist_exists: bool
    entry_file_exists: bool
    phase4_status: str
    phase5_status: str
    highest_accepted_tier: int
    time_to_ready_delta_ms: int | None
    shadow_wall_ms: int
    provider_calls: int
    output_tokens: int
    estimated_cost_usd: float


def build_comparison_artifact(inputs: ComparisonInputs) -> ShadowComparisonArtifact:
    limitations: list[str] = []
    absolute_only = False
    served_count = None if inputs.served_routes is None else len(inputs.served_routes)
    cand_count = None if inputs.candidate_routes is None else len(inputs.candidate_routes)
    coverage_delta = None
    if inputs.served_routes is None or inputs.candidate_routes is None:
        limitations.append("route_mapping_incomplete")
        absolute_only = True
    else:
        coverage_delta = len(set(inputs.candidate_routes) - set(inputs.served_routes))
    if inputs.time_to_ready_delta_ms is None:
        limitations.append("time_to_ready_not_comparable")
    if inputs.served_target_hash is None:
        limitations.append("served_target_hash_unavailable")

    payload = {
        "schema_version": "1.0",
        "comparison_policy_revision": SHADOW_COMPARISON_POLICY_REVISION,
        "served_target_kind": inputs.served_target_kind,
        "served_pointer_version": inputs.served_pointer_version,
        "v2_candidate_revision_id": inputs.v2_candidate_revision_id,
        "v2_effective_summary_id": inputs.v2_effective_summary_id,
        "served_target_hash": inputs.served_target_hash,
        "candidate_manifest_sha256": inputs.candidate_manifest_sha256,
        "effective_summary_sha256": inputs.effective_summary_sha256,
        "served_route_count": served_count,
        "candidate_route_count": cand_count,
        "route_coverage_delta": coverage_delta,
        "dist_exists": inputs.dist_exists,
        "entry_file_exists": inputs.entry_file_exists,
        "phase4_status": inputs.phase4_status,
        "phase5_status": inputs.phase5_status,
        "highest_accepted_tier": inputs.highest_accepted_tier,
        "time_to_ready_delta_ms": inputs.time_to_ready_delta_ms,
        "shadow_wall_ms": inputs.shadow_wall_ms,
        "provider_calls": inputs.provider_calls,
        "output_tokens": inputs.output_tokens,
        "estimated_cost_usd": inputs.estimated_cost_usd,
        "limitations": limitations,
        "absolute_only": absolute_only,
        "visual_superiority_claimed": False,
        "promotion_recommended": False,
        "result": "absolute_only" if absolute_only else "completed",
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ShadowComparisonArtifact(
        comparison_policy_revision=SHADOW_COMPARISON_POLICY_REVISION,
        served_target_kind=inputs.served_target_kind,  # type: ignore[arg-type]
        served_pointer_version=inputs.served_pointer_version,
        v2_candidate_revision_id=inputs.v2_candidate_revision_id,
        v2_effective_summary_id=inputs.v2_effective_summary_id,
        served_target_hash=inputs.served_target_hash,
        candidate_manifest_sha256=inputs.candidate_manifest_sha256,
        effective_summary_sha256=inputs.effective_summary_sha256,
        served_route_count=served_count,
        candidate_route_count=cand_count,
        route_coverage_delta=coverage_delta,
        dist_exists=inputs.dist_exists,
        entry_file_exists=inputs.entry_file_exists,
        phase4_status=inputs.phase4_status,
        phase5_status=inputs.phase5_status,
        highest_accepted_tier=inputs.highest_accepted_tier,
        time_to_ready_delta_ms=inputs.time_to_ready_delta_ms,
        shadow_wall_ms=inputs.shadow_wall_ms,
        provider_calls=inputs.provider_calls,
        output_tokens=inputs.output_tokens,
        estimated_cost_usd=inputs.estimated_cost_usd,
        limitations=tuple(limitations),
        absolute_only=absolute_only,
        visual_superiority_claimed=False,
        promotion_recommended=False,
        result="absolute_only" if absolute_only else "completed",
        artifact_sha256=digest,
    )


__all__ = ["ComparisonInputs", "build_comparison_artifact"]
