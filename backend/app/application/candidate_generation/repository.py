"""Append-only Phase 3B artifact cache and revision persistence."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.application.appspec.repository import load_json_object
from app.application.appspec.source import canonical_json
from app.application.candidate_generation.cache import (
    candidate_upstream_sha256,
    canonical_sha256,
)
from app.domain.models import (
    CandidateArtifactRecord,
    CandidateRevisionRecord,
    Request,
)
from app.domain.schemas.preview_candidate import (
    CANDIDATE_GENERATOR_VERSION,
    CANDIDATE_POLICY_REVISION,
    CandidateStageMetrics,
    CandidateStatus,
    CandidateUpstreamRefs,
)


ArtifactT = TypeVar("ArtifactT", bound=BaseModel)


@dataclass(frozen=True)
class ResolvedCandidateArtifact:
    artifact: BaseModel
    row: CandidateArtifactRecord
    metrics: CandidateStageMetrics


def candidate_cache_hit_metrics(
    row: CandidateArtifactRecord,
    *,
    latency_ms: int,
) -> CandidateStageMetrics:
    return CandidateStageMetrics(
        stage=row.artifact_kind,
        effective_model=row.effective_model,
        provider=row.provider,
        model_family=row.model_family,
        prompt_revision=row.prompt_revision,
        cache_hit=True,
        provider_call_count=0,
        repair_call_count=0,
        repair_reason=None,
        transport_retry_count=0,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        cost_usd=0.0,
        latency_ms=max(0, latency_ms),
    )


class CandidateRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_cache(
        self,
        *,
        request_id: int,
        artifact_kind: str,
        cache_key: str,
    ) -> CandidateArtifactRecord | None:
        return (
            self.db.query(CandidateArtifactRecord)
            .filter(
                CandidateArtifactRecord.request_id == request_id,
                CandidateArtifactRecord.artifact_kind == artifact_kind,
                CandidateArtifactRecord.cache_key == cache_key,
                CandidateArtifactRecord.cacheable.is_(True),
            )
            .first()
        )

    def load_cached(
        self,
        row: CandidateArtifactRecord,
        *,
        schema: type[ArtifactT],
        request_id: int,
        provenance_sha256: str,
        parent_artifact_id: int | None,
    ) -> ArtifactT:
        if (
            row.request_id != request_id
            or row.upstream_manifest_sha256 != provenance_sha256
            or row.parent_artifact_id != parent_artifact_id
            or not row.validation_passed
        ):
            raise ValueError("Candidate cache provenance is invalid.")
        artifact = schema.model_validate(load_json_object(row.artifact_json))
        if canonical_sha256(artifact) != row.artifact_sha256:
            raise ValueError(
                f"Candidate cache artifact hash is corrupt: "
                f"{row.artifact_kind}."
            )
        return artifact

    def stage_artifact(
        self,
        *,
        artifact: BaseModel,
        refs: CandidateUpstreamRefs,
        provenance_sha256: str,
        cache_key: str,
        metrics: CandidateStageMetrics,
        parent_artifact_id: int | None,
        validation: dict[str, Any],
        validation_passed: bool,
        cacheable: bool = True,
    ) -> CandidateArtifactRecord:
        expected_parent_kind = {
            "foundation": None,
            "data_exports": "foundation",
            "business_components": "data_exports",
            "pages": "business_components",
            "routes": "pages",
            "validation": "routes",
        }[metrics.stage]
        parent = (
            self.db.get(CandidateArtifactRecord, parent_artifact_id)
            if parent_artifact_id is not None
            else None
        )
        if (
            expected_parent_kind is None
            and parent is not None
        ) or (
            expected_parent_kind is not None
            and (
                parent is None
                or parent.request_id != refs.request_id
                or parent.artifact_kind != expected_parent_kind
            )
        ):
            raise ValueError("Candidate artifact parent chain is invalid.")
        payload = artifact.model_dump(mode="json")
        artifact_json = canonical_json(payload)
        digest = canonical_sha256(payload)
        existing = self.find_cache(
            request_id=refs.request_id,
            artifact_kind=metrics.stage,
            cache_key=cache_key,
        )
        if existing is not None:
            if (
                existing.parent_artifact_id != parent_artifact_id
                or existing.artifact_json != artifact_json
                or existing.artifact_sha256 != digest
                or existing.validation_passed != validation_passed
                or load_json_object(existing.validation_json) != validation
            ):
                raise ValueError(
                    "Existing candidate cache does not exactly match."
                )
            return existing
        row = CandidateArtifactRecord(
            request_id=refs.request_id,
            artifact_kind=metrics.stage,
            schema_version=str(payload.get("schema_version") or ""),
            policy_revision=CANDIDATE_POLICY_REVISION,
            prompt_revision=metrics.prompt_revision,
            effective_model=metrics.effective_model,
            provider=metrics.provider,
            model_family=metrics.model_family,
            parent_artifact_id=parent_artifact_id,
            cache_key=cache_key,
            upstream_manifest_sha256=provenance_sha256,
            artifact_json=artifact_json,
            artifact_sha256=digest,
            validation_json=canonical_json(validation),
            validation_passed=validation_passed,
            cacheable=cacheable,
            provider_call_count=metrics.provider_call_count,
            repair_call_count=metrics.repair_call_count,
            repair_reason=metrics.repair_reason,
            transport_retry_count=metrics.transport_retry_count,
            prompt_tokens=metrics.prompt_tokens,
            completion_tokens=metrics.completion_tokens,
            total_tokens=metrics.total_tokens,
            cost_usd=metrics.cost_usd,
            latency_ms=metrics.latency_ms,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def persist_revision(
        self,
        *,
        req: Request,
        revision_uuid: str,
        status: CandidateStatus,
        refs: CandidateUpstreamRefs,
        dependency_lock_sha256: str,
        model_manifest: dict[str, Any],
        workspace_relpath: str | None,
        file_manifest: list[dict],
        artifact_rows: tuple[CandidateArtifactRecord | None, ...],
        failure: dict[str, Any],
        metrics: tuple[CandidateStageMetrics, ...],
        summary_base: dict[str, Any],
    ) -> tuple[CandidateRevisionRecord, dict[str, Any]]:
        revision = int(
            self.db.query(func.max(CandidateRevisionRecord.revision))
            .filter(CandidateRevisionRecord.request_id == req.id)
            .scalar()
            or 0
        ) + 1
        file_digest = (
            canonical_sha256(file_manifest) if file_manifest else None
        )
        total_calls = sum(item.provider_call_count for item in metrics)
        total_repairs = sum(item.repair_call_count for item in metrics)
        row = CandidateRevisionRecord(
            revision_uuid=revision_uuid,
            request_id=req.id,
            revision=revision,
            target_tier=1,
            status=status,
            generator_version=CANDIDATE_GENERATOR_VERSION,
            policy_revision=CANDIDATE_POLICY_REVISION,
            upstream_manifest_json=canonical_json(
                refs.model_dump(mode="json")
            ),
            upstream_manifest_sha256=candidate_upstream_sha256(refs),
            dependency_lock_sha256=dependency_lock_sha256,
            model_manifest_json=canonical_json(model_manifest),
            workspace_relpath=workspace_relpath,
            file_manifest_json=canonical_json(file_manifest),
            file_manifest_sha256=file_digest,
            foundation_artifact_id=(
                artifact_rows[0].id if artifact_rows[0] else None
            ),
            data_artifact_id=(
                artifact_rows[1].id if artifact_rows[1] else None
            ),
            component_artifact_id=(
                artifact_rows[2].id if artifact_rows[2] else None
            ),
            page_artifact_id=(
                artifact_rows[3].id if artifact_rows[3] else None
            ),
            route_artifact_id=(
                artifact_rows[4].id if artifact_rows[4] else None
            ),
            validation_artifact_id=(
                artifact_rows[5].id if artifact_rows[5] else None
            ),
            failure_json=canonical_json(failure),
            provider_call_count=total_calls,
            repair_call_count=total_repairs,
            prompt_tokens=sum(item.prompt_tokens for item in metrics),
            completion_tokens=sum(item.completion_tokens for item in metrics),
            total_tokens=sum(item.total_tokens for item in metrics),
            cost_usd=sum(item.cost_usd for item in metrics),
            latency_ms=sum(item.latency_ms for item in metrics),
            completed_at=datetime.utcnow(),
        )
        self.db.add(row)
        self.db.flush()
        summary = {
            **summary_base,
            "status": status,
            "candidate_revision": {
                "id": row.id,
                "revision_uuid": row.revision_uuid,
                "revision": row.revision,
                "target_tier": row.target_tier,
                "workspace_relpath": row.workspace_relpath,
                "file_manifest_sha256": row.file_manifest_sha256,
            },
            "candidate_stage_metrics": {
                item.stage: item.model_dump(mode="json") for item in metrics
            },
            "candidate_totals": {
                "provider_call_count": total_calls,
                "repair_call_count": total_repairs,
                "prompt_tokens": row.prompt_tokens,
                "completion_tokens": row.completion_tokens,
                "total_tokens": row.total_tokens,
                "cost_usd": row.cost_usd,
                "latency_ms": row.latency_ms,
            },
            "failure": failure,
        }
        bundle: dict[str, Any] = {}
        if req.generated_pages:
            try:
                loaded = json.loads(req.generated_pages)
                if isinstance(loaded, dict):
                    bundle = loaded
            except Exception:
                pass
        bundle["preview_contract"] = summary
        req.generated_pages = json.dumps(bundle, ensure_ascii=False)
        return row, summary


__all__ = [
    "CandidateRepository",
    "ResolvedCandidateArtifact",
    "candidate_cache_hit_metrics",
]
