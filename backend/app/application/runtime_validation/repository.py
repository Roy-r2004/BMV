"""Append-only Phase 4 persistence and strict cache loading."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.application.appspec.repository import load_json_object
from app.application.appspec.source import canonical_json
from app.application.runtime_validation.cache import artifact_sha256
from app.application.runtime_validation.cache import sha256_file
from app.application.runtime_validation.workspace import validation_root
from app.domain.models import (
    CandidateAccessibilityFindingRecord,
    CandidateBuildAttemptRecord,
    CandidateJourneyResultRecord,
    CandidateRevisionRecord,
    CandidateRouteResultRecord,
    CandidateRuntimeValidationAttemptRecord,
    CandidateScreenshotRecord,
    CandidateValidationSummaryRecord,
    Request,
)
from app.domain.schemas.runtime_validation import (
    AccessibilityRouteResult,
    BuildValidationResult,
    JourneyValidationResult,
    RouteViewportResult,
    RuntimeLimits,
    RuntimeToolVersions,
    RuntimeValidationRefs,
    RuntimeValidationSummary,
    ScreenshotEvidence,
)


ArtifactT = TypeVar("ArtifactT", bound=BaseModel)


@dataclass(frozen=True)
class PersistedBuild:
    row: CandidateBuildAttemptRecord
    result: BuildValidationResult


def _validated_payload(
    row: Any,
    *,
    json_field: str,
    sha_field: str,
    schema: type[ArtifactT],
) -> ArtifactT:
    payload = load_json_object(getattr(row, json_field))
    artifact = schema.model_validate(payload)
    if artifact_sha256(artifact) != getattr(row, sha_field):
        raise ValueError("Runtime cache artifact hash is corrupt")
    return artifact


class RuntimeValidationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def latest_summary(
        self,
        candidate_revision_id: int,
    ) -> CandidateValidationSummaryRecord | None:
        return (
            self.db.query(CandidateValidationSummaryRecord)
            .filter(
                CandidateValidationSummaryRecord.candidate_revision_id
                == candidate_revision_id
            )
            .order_by(CandidateValidationSummaryRecord.id.desc())
            .first()
        )

    def find_resumable_attempt(
        self,
        *,
        candidate_revision_id: int,
        cache_identity: str,
    ) -> CandidateRuntimeValidationAttemptRecord | None:
        summarized = (
            self.db.query(CandidateValidationSummaryRecord.runtime_attempt_id)
        )
        return (
            self.db.query(CandidateRuntimeValidationAttemptRecord)
            .filter(
                CandidateRuntimeValidationAttemptRecord.candidate_revision_id
                == candidate_revision_id,
                CandidateRuntimeValidationAttemptRecord.cache_identity
                == cache_identity,
                ~CandidateRuntimeValidationAttemptRecord.id.in_(summarized),
            )
            .order_by(CandidateRuntimeValidationAttemptRecord.id.desc())
            .first()
        )

    def create_attempt(
        self,
        *,
        attempt_uuid: str,
        refs: RuntimeValidationRefs,
        cache_identity: str,
        source_candidate_sha256_before: str,
        tools: RuntimeToolVersions,
        limits: RuntimeLimits,
        workspace_relpath: str,
        resumed_from_attempt_id: int | None = None,
    ) -> CandidateRuntimeValidationAttemptRecord:
        candidate = self.db.get(
            CandidateRevisionRecord,
            refs.candidate_revision_id,
        )
        if (
            candidate is None
            or candidate.request_id != refs.request_id
            or candidate.revision_uuid != refs.candidate_revision_uuid
            or candidate.file_manifest_sha256
            != refs.candidate_manifest_sha256
            or candidate.dependency_lock_sha256
            != refs.dependency_lock_sha256
            or candidate.status != "candidate_build_pending"
        ):
            raise ValueError("Runtime attempt candidate reference is invalid")
        sequence = int(
            self.db.query(
                func.max(
                    CandidateRuntimeValidationAttemptRecord.attempt_sequence
                )
            )
            .filter(
                CandidateRuntimeValidationAttemptRecord.candidate_revision_id
                == candidate.id
            )
            .scalar()
            or 0
        ) + 1
        tools_json = canonical_json(tools.model_dump(mode="json"))
        limits_json = canonical_json(limits.model_dump(mode="json"))
        row = CandidateRuntimeValidationAttemptRecord(
            attempt_uuid=attempt_uuid,
            request_id=refs.request_id,
            candidate_revision_id=refs.candidate_revision_id,
            attempt_sequence=sequence,
            cache_identity=cache_identity,
            candidate_manifest_sha256=refs.candidate_manifest_sha256,
            dependency_lock_sha256=refs.dependency_lock_sha256,
            source_candidate_sha256_before=(
                source_candidate_sha256_before
            ),
            runtime_policy_revision=refs.runtime_policy_revision,
            tool_versions_json=tools_json,
            tool_versions_sha256=artifact_sha256(tools),
            limits_json=limits_json,
            limits_sha256=artifact_sha256(limits),
            workspace_relpath=workspace_relpath,
            resumed_from_attempt_id=resumed_from_attempt_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def validate_attempt(
        self,
        row: CandidateRuntimeValidationAttemptRecord,
        *,
        refs: RuntimeValidationRefs,
        cache_identity: str,
        source_candidate_sha256_before: str,
        tools: RuntimeToolVersions,
        limits: RuntimeLimits,
    ) -> None:
        if (
            row.request_id != refs.request_id
            or row.candidate_revision_id != refs.candidate_revision_id
            or row.cache_identity != cache_identity
            or row.candidate_manifest_sha256
            != refs.candidate_manifest_sha256
            or row.dependency_lock_sha256
            != refs.dependency_lock_sha256
            or row.source_candidate_sha256_before
            != source_candidate_sha256_before
            or row.runtime_policy_revision != refs.runtime_policy_revision
            or row.tool_versions_sha256 != artifact_sha256(tools)
            or row.limits_sha256 != artifact_sha256(limits)
            or RuntimeToolVersions.model_validate(
                load_json_object(row.tool_versions_json)
            )
            != tools
            or RuntimeLimits.model_validate(
                load_json_object(row.limits_json)
            )
            != limits
        ):
            raise ValueError("Resumable runtime attempt provenance changed")

    def persist_build(
        self,
        *,
        attempt: CandidateRuntimeValidationAttemptRecord,
        result: BuildValidationResult,
        workspace_relpath: str,
        parent_build_attempt_id: int | None = None,
    ) -> PersistedBuild:
        existing = (
            self.db.query(CandidateBuildAttemptRecord)
            .filter(
                CandidateBuildAttemptRecord.runtime_attempt_id == attempt.id,
                CandidateBuildAttemptRecord.attempt_sequence
                == result.deterministic_repair_count,
            )
            .first()
        )
        payload = canonical_json(result.model_dump(mode="json"))
        digest = artifact_sha256(result)
        if existing is not None:
            if (
                existing.result_sha256 != digest
                or existing.result_json != payload
                or existing.workspace_relpath != workspace_relpath
            ):
                raise ValueError("Existing build attempt is inconsistent")
            return PersistedBuild(existing, result)
        row = CandidateBuildAttemptRecord(
            request_id=attempt.request_id,
            candidate_revision_id=attempt.candidate_revision_id,
            runtime_attempt_id=attempt.id,
            attempt_sequence=result.deterministic_repair_count,
            parent_build_attempt_id=parent_build_attempt_id,
            status="build_passed" if result.passed else "build_failed",
            build_cache_key=result.build_cache_key,
            dist_cache_key=result.dist_cache_key,
            build_hash=result.build_hash,
            dist_manifest_sha256=result.dist_manifest_sha256,
            workspace_relpath=workspace_relpath,
            result_json=payload,
            result_sha256=digest,
            passed=result.passed,
        )
        self.db.add(row)
        self.db.flush()
        return PersistedBuild(row, result)

    def find_build_cache(
        self,
        *,
        candidate_revision_id: int,
        build_cache_key: str,
        dist_cache_key: str,
    ) -> PersistedBuild | None:
        row = (
            self.db.query(CandidateBuildAttemptRecord)
            .filter(
                CandidateBuildAttemptRecord.candidate_revision_id
                == candidate_revision_id,
                CandidateBuildAttemptRecord.build_cache_key
                == build_cache_key,
                CandidateBuildAttemptRecord.dist_cache_key == dist_cache_key,
                CandidateBuildAttemptRecord.passed.is_(True),
            )
            .order_by(CandidateBuildAttemptRecord.id.desc())
            .first()
        )
        if row is None:
            return None
        result = _validated_payload(
            row,
            json_field="result_json",
            sha_field="result_sha256",
            schema=BuildValidationResult,
        )
        if not result.passed or not result.dist_validation_passed:
            raise ValueError("Passing build cache is invalid")
        return PersistedBuild(row, result)

    def _cache_group(
        self,
        *,
        model: Any,
        schema: type[ArtifactT],
        json_field: str,
        sha_field: str,
        candidate_revision_id: int,
        cache_key: str,
    ) -> tuple[ArtifactT, ...]:
        latest = (
            self.db.query(model)
            .filter(
                model.candidate_revision_id == candidate_revision_id,
                model.cache_key == cache_key,
                model.passed.is_(True),
            )
            .order_by(model.id.desc())
            .first()
        )
        if latest is None:
            return ()
        rows = (
            self.db.query(model)
            .filter(
                model.candidate_revision_id == candidate_revision_id,
                model.cache_key == cache_key,
                model.passed.is_(True),
                model.runtime_attempt_id == latest.runtime_attempt_id,
            )
            .order_by(model.id)
            .all()
        )
        return tuple(
            _validated_payload(
                row,
                json_field=json_field,
                sha_field=sha_field,
                schema=schema,
            )
            for row in rows
        )

    def route_cache(
        self,
        candidate_revision_id: int,
        cache_key: str,
    ) -> tuple[RouteViewportResult, ...]:
        return self._cache_group(
            model=CandidateRouteResultRecord,
            schema=RouteViewportResult,
            json_field="result_json",
            sha_field="result_sha256",
            candidate_revision_id=candidate_revision_id,
            cache_key=cache_key,
        )

    def journey_cache(
        self,
        candidate_revision_id: int,
        cache_key: str,
    ) -> tuple[JourneyValidationResult, ...]:
        return self._cache_group(
            model=CandidateJourneyResultRecord,
            schema=JourneyValidationResult,
            json_field="result_json",
            sha_field="result_sha256",
            candidate_revision_id=candidate_revision_id,
            cache_key=cache_key,
        )

    def accessibility_cache(
        self,
        candidate_revision_id: int,
        cache_key: str,
    ) -> tuple[AccessibilityRouteResult, ...]:
        return self._cache_group(
            model=CandidateAccessibilityFindingRecord,
            schema=AccessibilityRouteResult,
            json_field="result_json",
            sha_field="result_sha256",
            candidate_revision_id=candidate_revision_id,
            cache_key=cache_key,
        )

    def screenshot_cache(
        self,
        candidate_revision_id: int,
        cache_key: str,
    ) -> tuple[tuple[CandidateScreenshotRecord, ScreenshotEvidence], ...]:
        latest = (
            self.db.query(CandidateScreenshotRecord)
            .filter(
                CandidateScreenshotRecord.candidate_revision_id
                == candidate_revision_id,
                CandidateScreenshotRecord.cache_key == cache_key,
            )
            .order_by(CandidateScreenshotRecord.id.desc())
            .first()
        )
        if latest is None:
            return ()
        rows = (
            self.db.query(CandidateScreenshotRecord)
            .filter(
                CandidateScreenshotRecord.candidate_revision_id
                == candidate_revision_id,
                CandidateScreenshotRecord.cache_key == cache_key,
                CandidateScreenshotRecord.runtime_attempt_id
                == latest.runtime_attempt_id,
            )
            .order_by(CandidateScreenshotRecord.id)
            .all()
        )
        return tuple(
            (
                row,
                _validated_payload(
                    row,
                    json_field="evidence_json",
                    sha_field="evidence_sha256",
                    schema=ScreenshotEvidence,
                ),
            )
            for row in rows
        )

    def persist_terminal(
        self,
        *,
        req: Request,
        attempt: CandidateRuntimeValidationAttemptRecord,
        build: CandidateBuildAttemptRecord,
        routes: tuple[RouteViewportResult, ...],
        journeys: tuple[JourneyValidationResult, ...],
        accessibility: tuple[AccessibilityRouteResult, ...],
        screenshots: tuple[ScreenshotEvidence, ...],
        summary: RuntimeValidationSummary,
    ) -> CandidateValidationSummaryRecord:
        if (
            req.id != attempt.request_id
            or summary.refs.request_id != req.id
            or summary.refs.candidate_revision_id
            != attempt.candidate_revision_id
            or build.runtime_attempt_id != attempt.id
            or summary.attempt_uuid != attempt.attempt_uuid
        ):
            raise ValueError("Runtime final-summary references are invalid")
        if self.db.query(CandidateValidationSummaryRecord).filter(
            CandidateValidationSummaryRecord.runtime_attempt_id == attempt.id
        ).first():
            raise ValueError("Runtime attempt already has a summary")
        result_artifacts = (
            *routes,
            *journeys,
            *accessibility,
            *screenshots,
        )
        if any(
            item.refs != summary.refs
            or item.build_hash != build.build_hash
            for item in result_artifacts
        ):
            raise ValueError("Runtime result references are inconsistent")
        if summary.status == "candidate_runtime_validated":
            route_keys = {(item.page_id, item.viewport) for item in routes}
            accessibility_keys = {
                (item.page_id, item.viewport) for item in accessibility
            }
            screenshot_keys = {
                (item.page_id, item.viewport) for item in screenshots
            }
            if (
                not build.passed
                or len(routes) != summary.expected_route_viewport_count
                or route_keys != accessibility_keys
                or route_keys != screenshot_keys
                or len(journeys) != summary.expected_journey_count
                or not all(item.passed for item in routes)
                or not all(item.passed for item in journeys)
                or not all(item.passed for item in accessibility)
                or len(route_keys) != len(routes)
                or tuple(artifact_sha256(item) for item in routes)
                != summary.route_result_hashes
                or tuple(artifact_sha256(item) for item in journeys)
                != summary.journey_result_hashes
                or tuple(
                    artifact_sha256(item) for item in accessibility
                )
                != summary.accessibility_result_hashes
                or tuple(item.sha256 for item in screenshots)
                != summary.screenshot_hashes
            ):
                raise ValueError(
                    "Incomplete result set cannot become runtime validated"
                )
            evidence_root = validation_root().resolve(strict=False)
            for item in screenshots:
                target = (
                    evidence_root / item.relative_path
                ).resolve(strict=False)
                try:
                    target.relative_to(evidence_root)
                except ValueError as exc:
                    raise ValueError(
                        "Screenshot evidence escapes validation root"
                    ) from exc
                if (
                    not target.is_file()
                    or target.stat().st_size != item.byte_count
                    or sha256_file(target) != item.sha256
                ):
                    raise ValueError(
                        "Screenshot evidence is missing or corrupt"
                    )
        for item in routes:
            payload = canonical_json(item.model_dump(mode="json"))
            self.db.add(
                CandidateRouteResultRecord(
                    request_id=req.id,
                    candidate_revision_id=attempt.candidate_revision_id,
                    runtime_attempt_id=attempt.id,
                    build_attempt_id=build.id,
                    page_id=item.page_id,
                    route=item.route,
                    viewport=item.viewport,
                    cache_key=item.cache_key,
                    passed=item.passed,
                    result_json=payload,
                    result_sha256=artifact_sha256(item),
                )
            )
        for item in journeys:
            payload = canonical_json(item.model_dump(mode="json"))
            self.db.add(
                CandidateJourneyResultRecord(
                    request_id=req.id,
                    candidate_revision_id=attempt.candidate_revision_id,
                    runtime_attempt_id=attempt.id,
                    build_attempt_id=build.id,
                    journey_id=item.journey_id,
                    action_id=item.action_id,
                    cache_key=item.cache_key,
                    passed=item.passed,
                    result_json=payload,
                    result_sha256=artifact_sha256(item),
                )
            )
        for item in accessibility:
            payload = canonical_json(item.model_dump(mode="json"))
            self.db.add(
                CandidateAccessibilityFindingRecord(
                    request_id=req.id,
                    candidate_revision_id=attempt.candidate_revision_id,
                    runtime_attempt_id=attempt.id,
                    build_attempt_id=build.id,
                    page_id=item.page_id,
                    route=item.route,
                    viewport=item.viewport,
                    scanner_name=item.scanner_name,
                    scanner_policy_revision=item.scanner_policy_revision,
                    cache_key=item.cache_key,
                    passed=item.passed,
                    result_json=payload,
                    result_sha256=artifact_sha256(item),
                )
            )
        for item in screenshots:
            payload = canonical_json(item.model_dump(mode="json"))
            self.db.add(
                CandidateScreenshotRecord(
                    request_id=req.id,
                    candidate_revision_id=attempt.candidate_revision_id,
                    runtime_attempt_id=attempt.id,
                    build_attempt_id=build.id,
                    page_id=item.page_id,
                    route=item.route,
                    viewport=item.viewport,
                    cache_key=item.cache_key,
                    relative_path=item.relative_path,
                    screenshot_sha256=item.sha256,
                    evidence_json=payload,
                    evidence_sha256=artifact_sha256(item),
                )
            )
        summary_json = canonical_json(summary.model_dump(mode="json"))
        row = CandidateValidationSummaryRecord(
            request_id=req.id,
            candidate_revision_id=attempt.candidate_revision_id,
            runtime_attempt_id=attempt.id,
            build_attempt_id=build.id,
            status=summary.status,
            candidate_manifest_sha256=(
                summary.refs.candidate_manifest_sha256
            ),
            build_hash=build.build_hash,
            source_candidate_sha256_before=(
                summary.source_candidate_sha256_before
            ),
            source_candidate_sha256_after=(
                summary.source_candidate_sha256_after
            ),
            summary_json=summary_json,
            summary_sha256=artifact_sha256(summary),
        )
        self.db.add(row)
        bundle: dict[str, Any] = {}
        if req.generated_pages:
            try:
                loaded = json.loads(req.generated_pages)
                if isinstance(loaded, dict):
                    bundle = loaded
            except Exception:
                pass
        preview = dict(bundle.get("preview_contract") or {})
        preview.update(
            {
                "status": summary.status,
                "runtime_validation_summary": {
                    "id": None,
                    "attempt_uuid": summary.attempt_uuid,
                    "sha256": row.summary_sha256,
                },
            }
        )
        bundle["preview_contract"] = preview
        req.generated_pages = json.dumps(bundle, ensure_ascii=False)
        self.db.flush()
        preview["runtime_validation_summary"]["id"] = row.id
        bundle["preview_contract"] = preview
        req.generated_pages = json.dumps(bundle, ensure_ascii=False)
        return row


__all__ = [
    "PersistedBuild",
    "RuntimeValidationRepository",
]
