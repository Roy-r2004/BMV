"""Load and revalidate the immutable Phase 3B/4 inputs to Phase 5."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.application.appspec.repository import load_json_object
from app.application.candidate_generation.cache import canonical_sha256
from app.application.candidate_generation.context import (
    CandidateContext,
    load_candidate_context,
)
from app.application.runtime_validation.cache import artifact_sha256, sha256_file
from app.application.runtime_validation.dist import (
    dist_manifest,
    dist_manifest_sha256,
    read_build_identity,
)
from app.application.runtime_validation.policy import VIEWPORTS
from app.application.runtime_validation.workspace import (
    source_manifest_sha256,
    validation_root,
)
from app.core.config import settings
from app.domain.models import (
    CandidateAccessibilityFindingRecord,
    CandidateBuildAttemptRecord,
    CandidateJourneyResultRecord,
    CandidateRevisionRecord,
    CandidateRouteResultRecord,
    CandidateRuntimeValidationAttemptRecord,
    CandidateScreenshotRecord,
    CandidateValidationSummaryRecord,
)
from app.domain.schemas.runtime_validation import (
    AccessibilityRouteResult,
    BuildValidationResult,
    JourneyValidationResult,
    RouteViewportResult,
    RuntimeValidationSummary,
    ScreenshotEvidence,
)
from app.domain.schemas.visual_evaluation import VisualEvaluationRefs


@dataclass(frozen=True)
class VisualEvaluationContext:
    candidate: CandidateRevisionRecord
    candidate_workspace: Path
    candidate_file_manifest: tuple[dict[str, Any], ...]
    contracts: CandidateContext
    runtime_attempt: CandidateRuntimeValidationAttemptRecord
    runtime_summary_row: CandidateValidationSummaryRecord
    runtime_summary: RuntimeValidationSummary
    build_row: CandidateBuildAttemptRecord
    build_result: BuildValidationResult
    build_workspace: Path
    routes: tuple[RouteViewportResult, ...]
    journeys: tuple[JourneyValidationResult, ...]
    accessibility: tuple[AccessibilityRouteResult, ...]
    screenshots: tuple[ScreenshotEvidence, ...]
    refs: VisualEvaluationRefs
    phase4_summary: dict[str, Any]


def _validated_row(row, *, json_field: str, sha_field: str, schema):
    payload = load_json_object(getattr(row, json_field))
    artifact = schema.model_validate(payload)
    if artifact_sha256(artifact) != getattr(row, sha_field):
        raise ValueError(f"Stored {schema.__name__} hash is corrupt")
    return artifact


def _safe_workspace(root: Path, relpath: str) -> Path:
    resolved_root = root.resolve(strict=False)
    target = (resolved_root / relpath).resolve(strict=False)
    try:
        target.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("Phase 5 input workspace escapes its root") from exc
    if not target.is_dir():
        raise ValueError("Phase 5 input workspace is missing")
    return target


def _verify_build(
    *,
    build_row: CandidateBuildAttemptRecord,
    build: BuildValidationResult,
    workspace: Path,
) -> None:
    dist = workspace / "dist"
    rows = dist_manifest(dist)
    if (
        rows != build.dist_files
        or dist_manifest_sha256(rows) != build.dist_manifest_sha256
        or build_row.dist_manifest_sha256 != build.dist_manifest_sha256
    ):
        raise ValueError("Phase 4 build output hash is stale or corrupt")
    identity = read_build_identity(dist)
    pre_rows = tuple(
        row for row in rows if row.path != "bmv-build-identity.json"
    )
    pre_sha = dist_manifest_sha256(pre_rows)
    expected = canonical_sha256(
        {
            "candidate_manifest_sha256": (
                build.refs.candidate_manifest_sha256
            ),
            "dependency_lock_sha256": build.refs.dependency_lock_sha256,
            "build_cache_key": build.build_cache_key,
            "dist_content_sha256": pre_sha,
        }
    )
    if (
        identity.get("candidate_manifest_sha256")
        != build.refs.candidate_manifest_sha256
        or identity.get("dist_content_sha256") != pre_sha
        or identity.get("build_hash") != expected
        or build.build_hash != expected
        or build_row.build_hash != expected
    ):
        raise ValueError("Phase 4 build hash cannot be reproduced")


def load_visual_evaluation_context(
    db: Session,
    *,
    request_id: int,
    phase4_result: dict[str, Any],
) -> VisualEvaluationContext:
    summary = dict(phase4_result.get("preview_contract") or {})
    if summary.get("status") != "candidate_runtime_validated":
        raise ValueError(
            "Phase 5 requires a complete candidate_runtime_validated result"
        )
    revision_ref = summary.get("candidate_revision") or {}
    runtime_ref = summary.get("runtime_validation_summary") or {}
    candidate = db.get(CandidateRevisionRecord, revision_ref.get("id"))
    runtime_summary_row = db.get(
        CandidateValidationSummaryRecord,
        runtime_ref.get("id"),
    )
    if (
        candidate is None
        or candidate.request_id != request_id
        or candidate.status != "candidate_build_pending"
        or candidate.revision_uuid != revision_ref.get("revision_uuid")
        or candidate.file_manifest_sha256
        != revision_ref.get("file_manifest_sha256")
        or not candidate.workspace_relpath
        or runtime_summary_row is None
        or runtime_summary_row.request_id != request_id
        or runtime_summary_row.candidate_revision_id != candidate.id
        or runtime_summary_row.status != "candidate_runtime_validated"
        or runtime_summary_row.summary_sha256 != runtime_ref.get("sha256")
    ):
        raise ValueError("Phase 5 candidate/runtime references are invalid")
    runtime_attempt = db.get(
        CandidateRuntimeValidationAttemptRecord,
        runtime_summary_row.runtime_attempt_id,
    )
    build_row = db.get(
        CandidateBuildAttemptRecord,
        runtime_summary_row.build_attempt_id,
    )
    if (
        runtime_attempt is None
        or runtime_attempt.request_id != request_id
        or runtime_attempt.candidate_revision_id != candidate.id
        or build_row is None
        or build_row.request_id != request_id
        or build_row.candidate_revision_id != candidate.id
        or build_row.runtime_attempt_id != runtime_attempt.id
        or not build_row.passed
    ):
        raise ValueError("Phase 4 attempt/build chain is invalid")
    runtime_summary = _validated_row(
        runtime_summary_row,
        json_field="summary_json",
        sha_field="summary_sha256",
        schema=RuntimeValidationSummary,
    )
    build_result = _validated_row(
        build_row,
        json_field="result_json",
        sha_field="result_sha256",
        schema=BuildValidationResult,
    )
    if (
        runtime_summary.status != "candidate_runtime_validated"
        or not runtime_summary.all_required_gates_passed
        or runtime_summary.refs.candidate_revision_id != candidate.id
        or build_result.refs != runtime_summary.refs
        or runtime_summary.build_result_sha256 != artifact_sha256(build_result)
        or runtime_summary_row.build_hash != build_result.build_hash
    ):
        raise ValueError("Phase 4 terminal artifacts are inconsistent")

    candidate_workspace = _safe_workspace(
        settings.PREVIEW_CANDIDATES_DIR,
        candidate.workspace_relpath,
    )
    manifest = json.loads(candidate.file_manifest_json)
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("Candidate manifest is invalid")
    source_sha = source_manifest_sha256(
        candidate_workspace,
        tuple(manifest),
    )
    if (
        source_sha != candidate.file_manifest_sha256
        or source_sha != runtime_summary.refs.candidate_manifest_sha256
        or source_sha != runtime_summary.source_candidate_sha256_before
        or source_sha != runtime_summary.source_candidate_sha256_after
    ):
        raise ValueError("Frozen Phase 3B candidate manifest changed")

    build_workspace = _safe_workspace(
        validation_root(),
        build_row.workspace_relpath,
    )
    _verify_build(
        build_row=build_row,
        build=build_result,
        workspace=build_workspace,
    )

    phase3a_summary = dict(summary)
    phase3a_summary["status"] = "composition_contract_ready"
    contracts = load_candidate_context(
        db,
        request_id=request_id,
        phase3a_result={"preview_contract": phase3a_summary},
    )
    expected_keys = tuple(
        (page.page_id, page.route, viewport.name)
        for page in contracts.page_purpose.pages
        for viewport in VIEWPORTS
    )

    def load_matrix(model, schema, json_field, sha_field):
        rows = (
            db.query(model)
            .filter(model.runtime_attempt_id == runtime_attempt.id)
            .all()
        )
        by_key = {
            (row.page_id, row.route, row.viewport): _validated_row(
                row,
                json_field=json_field,
                sha_field=sha_field,
                schema=schema,
            )
            for row in rows
        }
        if set(by_key) != set(expected_keys) or len(rows) != len(expected_keys):
            raise ValueError("Phase 4 route/viewport matrix is incomplete")
        return tuple(by_key[key] for key in expected_keys)

    routes = load_matrix(
        CandidateRouteResultRecord,
        RouteViewportResult,
        "result_json",
        "result_sha256",
    )
    accessibility = load_matrix(
        CandidateAccessibilityFindingRecord,
        AccessibilityRouteResult,
        "result_json",
        "result_sha256",
    )
    screenshots = load_matrix(
        CandidateScreenshotRecord,
        ScreenshotEvidence,
        "evidence_json",
        "evidence_sha256",
    )
    journey_rows = (
        db.query(CandidateJourneyResultRecord)
        .filter(
            CandidateJourneyResultRecord.runtime_attempt_id
            == runtime_attempt.id
        )
        .order_by(CandidateJourneyResultRecord.id)
        .all()
    )
    journeys = tuple(
        _validated_row(
            row,
            json_field="result_json",
            sha_field="result_sha256",
            schema=JourneyValidationResult,
        )
        for row in journey_rows
    )
    artifacts = (*routes, *journeys, *accessibility, *screenshots)
    if (
        not all(item.refs == runtime_summary.refs for item in artifacts)
        or not all(item.build_hash == build_result.build_hash for item in artifacts)
        or not all(item.passed for item in (*routes, *journeys, *accessibility))
        or tuple(artifact_sha256(item) for item in routes)
        != runtime_summary.route_result_hashes
        or tuple(artifact_sha256(item) for item in journeys)
        != runtime_summary.journey_result_hashes
        or tuple(artifact_sha256(item) for item in accessibility)
        != runtime_summary.accessibility_result_hashes
        or tuple(item.sha256 for item in screenshots)
        != runtime_summary.screenshot_hashes
        or len(journeys) != runtime_summary.expected_journey_count
    ):
        raise ValueError("Phase 4 evidence is stale, failing, or cross-request")
    screenshot_set_sha256 = canonical_sha256(
        [
            {
                "page_id": item.page_id,
                "route": item.route,
                "viewport": item.viewport,
                "sha256": item.sha256,
            }
            for item in screenshots
        ]
    )
    rows = contracts.rows
    refs = VisualEvaluationRefs(
        request_id=request_id,
        candidate_revision_id=candidate.id,
        candidate_revision_uuid=candidate.revision_uuid,
        candidate_manifest_sha256=candidate.file_manifest_sha256,
        runtime_attempt_id=runtime_attempt.id,
        runtime_summary_id=runtime_summary_row.id,
        runtime_summary_sha256=runtime_summary_row.summary_sha256,
        build_attempt_id=build_row.id,
        build_hash=build_result.build_hash,
        screenshot_set_sha256=screenshot_set_sha256,
        design_contract_refs=(
            contracts.refs.composition_contract_refs.design_contract_refs
        ),
        page_purpose_sha256=rows[0].artifact_sha256,
        business_component_plan_sha256=rows[1].artifact_sha256,
        content_data_plan_sha256=rows[2].artifact_sha256,
        interaction_contract_sha256=rows[3].artifact_sha256,
        component_dependency_graph_sha256=rows[4].artifact_sha256,
    )
    return VisualEvaluationContext(
        candidate=candidate,
        candidate_workspace=candidate_workspace,
        candidate_file_manifest=tuple(manifest),
        contracts=contracts,
        runtime_attempt=runtime_attempt,
        runtime_summary_row=runtime_summary_row,
        runtime_summary=runtime_summary,
        build_row=build_row,
        build_result=build_result,
        build_workspace=build_workspace,
        routes=routes,
        journeys=journeys,
        accessibility=accessibility,
        screenshots=screenshots,
        refs=refs,
        phase4_summary=summary,
    )


__all__ = ["VisualEvaluationContext", "load_visual_evaluation_context"]
