"""Resolve and verify a frozen Phase 3B candidate and its contracts."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.application.candidate_generation.context import (
    CandidateContext,
    load_candidate_context,
)
from app.application.appspec.source import canonical_json
from app.core.config import settings
from app.domain.models import CandidateRevisionRecord
from app.domain.schemas.runtime_validation import RuntimeValidationRefs


@dataclass(frozen=True)
class RuntimeValidationContext:
    candidate: CandidateRevisionRecord
    candidate_workspace: Path
    candidate_file_manifest: tuple[dict[str, Any], ...]
    contracts: CandidateContext
    refs: RuntimeValidationRefs
    phase3b_summary: dict[str, Any]


def load_runtime_validation_context(
    db: Session,
    *,
    request_id: int,
    phase3b_result: dict[str, Any],
) -> RuntimeValidationContext:
    summary = dict(phase3b_result.get("preview_contract") or {})
    if summary.get("status") != "candidate_build_pending":
        raise ValueError("Phase 4 requires candidate_build_pending")
    revision_ref = summary.get("candidate_revision") or {}
    row = db.get(CandidateRevisionRecord, revision_ref.get("id"))
    if (
        row is None
        or row.request_id != request_id
        or row.status != "candidate_build_pending"
        or row.revision_uuid != revision_ref.get("revision_uuid")
        or row.file_manifest_sha256
        != revision_ref.get("file_manifest_sha256")
        or not row.workspace_relpath
        or not row.file_manifest_sha256
    ):
        raise ValueError("Phase 3B candidate reference is invalid")
    root = settings.PREVIEW_CANDIDATES_DIR.resolve(strict=False)
    workspace = (root / row.workspace_relpath).resolve(strict=False)
    try:
        workspace.relative_to(root)
    except ValueError as exc:
        raise ValueError("Candidate workspace escapes its root") from exc
    if not workspace.is_dir():
        raise ValueError("Frozen candidate workspace is missing")
    loaded_manifest = json.loads(row.file_manifest_json)
    if not isinstance(loaded_manifest, list) or not loaded_manifest:
        raise ValueError("Candidate file manifest is invalid")
    phase3a_summary = dict(summary)
    phase3a_summary["status"] = "composition_contract_ready"
    contracts = load_candidate_context(
        db,
        request_id=request_id,
        phase3a_result={"preview_contract": phase3a_summary},
    )
    if (
        row.target_tier != contracts.refs.target_tier
        or row.upstream_manifest_json
        != canonical_json(contracts.refs.model_dump(mode="json"))
    ):
        raise ValueError("Candidate cumulative contract references changed")
    refs = RuntimeValidationRefs(
        request_id=request_id,
        candidate_revision_id=row.id,
        candidate_revision_uuid=row.revision_uuid,
        candidate_manifest_sha256=row.file_manifest_sha256,
        dependency_lock_sha256=row.dependency_lock_sha256,
        candidate_generator_version=row.generator_version,
        candidate_policy_revision=row.policy_revision,
    )
    return RuntimeValidationContext(
        candidate=row,
        candidate_workspace=workspace,
        candidate_file_manifest=tuple(loaded_manifest),
        contracts=contracts,
        refs=refs,
        phase3b_summary=summary,
    )


__all__ = [
    "RuntimeValidationContext",
    "load_runtime_validation_context",
]
