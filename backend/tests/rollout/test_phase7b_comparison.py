"""Deterministic comparison artifact hashing and absolute-only behavior."""
from __future__ import annotations

from app.application.rollout.shadow_compare import ComparisonInputs, build_comparison_artifact


def test_deterministic_comparison_hash_and_absolute_only() -> None:
    inputs = ComparisonInputs(
        served_target_kind="unset",
        served_pointer_version=None,
        v2_candidate_revision_id=7,
        v2_effective_summary_id=1,
        served_target_hash=None,
        candidate_manifest_sha256="b" * 64,
        effective_summary_sha256="a" * 64,
        served_routes=None,
        candidate_routes=None,
        dist_exists=False,
        entry_file_exists=False,
        phase4_status="candidate_runtime_validated",
        phase5_status="candidate_visual_accepted",
        highest_accepted_tier=2,
        time_to_ready_delta_ms=None,
        shadow_wall_ms=12,
        provider_calls=0,
        output_tokens=0,
        estimated_cost_usd=0.0,
    )
    a = build_comparison_artifact(inputs)
    b = build_comparison_artifact(inputs)
    assert a.artifact_sha256 == b.artifact_sha256
    assert a.absolute_only is True
    assert "route_mapping_incomplete" in a.limitations
    assert a.visual_superiority_claimed is False
    assert a.promotion_recommended is False


def test_route_coverage_when_complete() -> None:
    artifact = build_comparison_artifact(
        ComparisonInputs(
            served_target_kind="legacy_v1",
            served_pointer_version=1,
            v2_candidate_revision_id=7,
            v2_effective_summary_id=1,
            served_target_hash="c" * 64,
            candidate_manifest_sha256="b" * 64,
            effective_summary_sha256="a" * 64,
            served_routes=("/a", "/b"),
            candidate_routes=("/a", "/b", "/c"),
            dist_exists=True,
            entry_file_exists=True,
            phase4_status="candidate_runtime_validated",
            phase5_status="candidate_visual_accepted",
            highest_accepted_tier=2,
            time_to_ready_delta_ms=100,
            shadow_wall_ms=20,
            provider_calls=0,
            output_tokens=0,
            estimated_cost_usd=0.0,
        )
    )
    assert artifact.absolute_only is False
    assert artifact.route_coverage_delta == 1
    assert artifact.result == "completed"
