"""Isolated staging and immutable workspace lifecycle for Phase 3B."""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

from app.application.appspec.source import canonical_json
from app.application.candidate_generation.cache import (
    canonical_sha256,
    sha256_text,
)
from app.application.candidate_generation.deterministic import (
    CandidateSourceFile,
)
from app.application.candidate_generation.policy import (
    CANDIDATE_DETERMINISTIC_REVISION,
)
from app.core.config import settings


_SAFE_RELATIVE = re.compile(r"^[A-Za-z0-9_./-]+$")
_STAGE_PROGRESS_ORDER = {
    "business_components": 1,
    "pages": 2,
}
_STAGE_STATUS_PROGRESS = {
    "in_flight": 1,
    "parsed_output": 2,
    "completed": 3,
}


@dataclass(frozen=True)
class CandidateWorkspace:
    request_id: int
    revision_uuid: str
    staging_path: Path
    final_path: Path
    resumed: bool
    resume_state: dict | None = None
    resume_invalid_reason: str | None = None


def candidate_root() -> Path:
    return settings.PREVIEW_CANDIDATES_DIR


def _safe_target(root: Path, relpath: str) -> Path:
    normalized = str(relpath).replace("\\", "/")
    parts = tuple(part for part in normalized.split("/") if part not in {"", "."})
    if (
        not normalized
        or not _SAFE_RELATIVE.fullmatch(normalized)
        or normalized.startswith("/")
        or Path(normalized).is_absolute()
        or PureWindowsPath(normalized).is_absolute()
        or ".." in parts
    ):
        raise ValueError(f"Unsafe candidate path: {relpath!r}")
    resolved_root = root.resolve(strict=False)
    target = resolved_root.joinpath(*parts)
    try:
        target.parent.resolve(strict=False).relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Candidate path escapes staging: {relpath!r}") from exc
    if target.is_symlink():
        raise ValueError(f"Candidate path targets a symlink: {relpath!r}")
    return target


def write_sources(
    workspace: CandidateWorkspace,
    sources: tuple[CandidateSourceFile, ...],
) -> None:
    for item in sources:
        target = _safe_target(workspace.staging_path, item.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = _safe_target(workspace.staging_path, item.path)
        target.write_text(item.source, encoding="utf-8", newline="\n")


def read_source(workspace: CandidateWorkspace, relpath: str) -> str:
    target = _safe_target(workspace.staging_path, relpath)
    if not target.is_file():
        return ""
    return target.read_text(encoding="utf-8")


def source_file_manifest(root: Path) -> list[dict]:
    result = []
    for path in sorted(
        item
        for item in root.rglob("*")
        if item.is_file() and item.name != ".attempt.json"
    ):
        relpath = str(path.relative_to(root)).replace("\\", "/")
        payload = path.read_bytes()
        result.append(
            {
                "path": relpath,
                "sha256": sha256_text(payload.decode("utf-8")),
                "byte_count": len(payload),
            }
        )
    return result


def file_manifest_sha256(root: Path) -> str:
    return canonical_sha256(source_file_manifest(root))


def _attempt_metadata_path(staging_path: Path) -> Path:
    return staging_path / ".attempt.json"


def _write_attempt_metadata(
    workspace: CandidateWorkspace,
    *,
    upstream_sha256: str,
    completed_artifacts: dict[str, str] | None = None,
    policy_revision: str | None = None,
    completed_stage_state: dict | None = None,
    candidate_call_ledger: dict | None = None,
    candidate_provider_attempts: list[dict] | None = None,
) -> None:
    existing: dict = {}
    metadata_path = _attempt_metadata_path(workspace.staging_path)
    if metadata_path.exists():
        try:
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    payload = {
        "request_id": workspace.request_id,
        "revision_uuid": workspace.revision_uuid,
        "upstream_sha256": upstream_sha256,
        "policy_revision": (
            policy_revision or settings.V2_CANDIDATE_POLICY_REVISION
        ),
        # Deterministic foundation/data/routes builder fingerprint. When this
        # changes, prior staging ledgers must not resume — AI cache keys depend
        # on parent data hashes and a spent call budget cannot regenerate.
        "deterministic_revision": CANDIDATE_DETERMINISTIC_REVISION,
        "checkpointed_at_utc": datetime.now(timezone.utc).isoformat(),
        "completed_artifacts": completed_artifacts
        if completed_artifacts is not None
        else (existing.get("completed_artifacts") or {}),
        "completed_stage_state": completed_stage_state
        if completed_stage_state is not None
        else (existing.get("completed_stage_state") or {}),
        "candidate_call_ledger": candidate_call_ledger
        if candidate_call_ledger is not None
        else (existing.get("candidate_call_ledger") or {}),
        "candidate_provider_attempts": candidate_provider_attempts
        if candidate_provider_attempts is not None
        else list(existing.get("candidate_provider_attempts") or []),
    }
    temp_path = metadata_path.with_name(
        f"{metadata_path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, metadata_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def checkpoint_workspace(
    workspace: CandidateWorkspace,
    *,
    upstream_sha256: str,
    completed_artifacts: dict[str, str],
    policy_revision: str | None = None,
    completed_stage_state: dict | None = None,
    candidate_call_ledger: dict | None = None,
    candidate_provider_attempts: list[dict] | None = None,
) -> None:
    _write_attempt_metadata(
        workspace,
        upstream_sha256=upstream_sha256,
        completed_artifacts=completed_artifacts,
        policy_revision=policy_revision,
        completed_stage_state=completed_stage_state,
        candidate_call_ledger=candidate_call_ledger,
        candidate_provider_attempts=candidate_provider_attempts,
    )


def _verified_resume(
    staging_path: Path,
    *,
    request_id: int,
    upstream_sha256: str,
    policy_revision: str | None = None,
) -> CandidateWorkspace | None:
    metadata_path = _attempt_metadata_path(staging_path)
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        revision_uuid = str(payload["revision_uuid"])
        uuid.UUID(revision_uuid)
    except Exception:
        return CandidateWorkspace(
            request_id=request_id,
            revision_uuid=staging_path.name,
            staging_path=staging_path,
            final_path=(
                candidate_root() / str(request_id) / "revisions" / staging_path.name
            ),
            resumed=True,
            resume_state=None,
            resume_invalid_reason="attempt_checkpoint_unreadable",
        )
    if (
        payload.get("request_id") != request_id
        or payload.get("upstream_sha256") != upstream_sha256
        or payload.get("policy_revision")
        != (policy_revision or settings.V2_CANDIDATE_POLICY_REVISION)
        or str(payload.get("deterministic_revision") or "")
        != CANDIDATE_DETERMINISTIC_REVISION
    ):
        return None
    invalid_reason: str | None = None
    for relpath, expected_sha in (payload.get("completed_artifacts") or {}).items():
        target = _safe_target(staging_path, relpath)
        if not target.is_file() or sha256_text(
            target.read_text(encoding="utf-8")
        ) != expected_sha:
            invalid_reason = f"completed_artifact_mismatch:{relpath}"
            break
    completed_stage_state = payload.get("completed_stage_state") or {}
    paid_claim = any(
        isinstance(item, dict)
        and str(item.get("status") or "")
        in {"in_flight", "parsed_output", "completed"}
        for item in completed_stage_state.values()
    )
    if invalid_reason and not paid_claim:
        return None
    return CandidateWorkspace(
        request_id=request_id,
        revision_uuid=revision_uuid,
        staging_path=staging_path,
        final_path=(
            candidate_root() / str(request_id) / "revisions" / revision_uuid
        ),
        resumed=True,
        resume_state=payload,
        resume_invalid_reason=invalid_reason,
    )


def _parse_resume_timestamp(payload: dict) -> float:
    raw = str(
        payload.get("checkpointed_at_utc")
        or payload.get("updated_at_utc")
        or ""
    ).strip()
    if not raw:
        return 0.0
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _resume_stage_progress(payload: dict) -> tuple[int, int]:
    completed_stage_state = payload.get("completed_stage_state") or {}
    best_stage = 0
    completed_count = 0
    for stage_name, stage_payload in completed_stage_state.items():
        if not isinstance(stage_payload, dict):
            continue
        stage_score = _STAGE_PROGRESS_ORDER.get(str(stage_name), 0)
        status_score = _STAGE_STATUS_PROGRESS.get(
            str(stage_payload.get("status") or ""),
            0,
        )
        best_stage = max(best_stage, (stage_score * 10) + status_score)
        if status_score >= _STAGE_STATUS_PROGRESS["completed"]:
            completed_count += 1
    return best_stage, completed_count


def _resume_rank(candidate: CandidateWorkspace) -> tuple[float, tuple[int, int], int]:
    payload = dict(candidate.resume_state or {})
    return (
        _parse_resume_timestamp(payload),
        _resume_stage_progress(payload),
        len(list(payload.get("candidate_provider_attempts") or [])),
    )


def _has_in_flight_resume_state(candidate: CandidateWorkspace) -> bool:
    payload = dict(candidate.resume_state or {})
    completed_stage_state = payload.get("completed_stage_state") or {}
    return any(
        isinstance(item, dict) and str(item.get("status") or "") == "in_flight"
        for item in completed_stage_state.values()
    )


def _with_resume_invalid_reason(
    candidate: CandidateWorkspace,
    reason: str,
) -> CandidateWorkspace:
    return CandidateWorkspace(
        request_id=candidate.request_id,
        revision_uuid=candidate.revision_uuid,
        staging_path=candidate.staging_path,
        final_path=candidate.final_path,
        resumed=candidate.resumed,
        resume_state=candidate.resume_state,
        resume_invalid_reason=reason,
    )


def open_candidate_workspace(
    *,
    request_id: int,
    upstream_sha256: str,
    policy_revision: str | None = None,
) -> CandidateWorkspace:
    request_root = candidate_root() / str(request_id)
    staging_root = request_root / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    resumable_workspaces: list[CandidateWorkspace] = []
    for staging_path in sorted(staging_root.iterdir()):
        if not staging_path.is_dir():
            continue
        resumed = _verified_resume(
            staging_path,
            request_id=request_id,
            upstream_sha256=upstream_sha256,
            policy_revision=policy_revision,
        )
        if resumed is not None:
            resumable_workspaces.append(resumed)
    if resumable_workspaces:
        ranked = sorted(
            resumable_workspaces,
            key=_resume_rank,
            reverse=True,
        )
        best = ranked[0]
        best_rank = _resume_rank(best)
        tied = [item for item in ranked if _resume_rank(item) == best_rank]
        if len(tied) > 1:
            return _with_resume_invalid_reason(
                tied[0],
                "ambiguous_resume_checkpoint",
            )
        return best
    revision_uuid = str(uuid.uuid4())
    staging_path = staging_root / revision_uuid
    staging_path.mkdir(parents=False, exist_ok=False)
    workspace = CandidateWorkspace(
        request_id=request_id,
        revision_uuid=revision_uuid,
        staging_path=staging_path,
        final_path=request_root / "revisions" / revision_uuid,
        resumed=False,
        resume_state=None,
        resume_invalid_reason=None,
    )
    _write_attempt_metadata(
        workspace,
        upstream_sha256=upstream_sha256,
        policy_revision=policy_revision,
    )
    return workspace


def freeze_candidate_workspace(workspace: CandidateWorkspace) -> Path:
    metadata = _attempt_metadata_path(workspace.staging_path)
    if metadata.exists():
        metadata.unlink()
    workspace.final_path.parent.mkdir(parents=True, exist_ok=True)
    if workspace.final_path.exists():
        raise FileExistsError(
            f"Candidate revision already frozen: {workspace.revision_uuid}"
        )
    os.replace(workspace.staging_path, workspace.final_path)
    return workspace.final_path


def quarantine_invalid_staging(workspace: CandidateWorkspace) -> Path:
    request_root = candidate_root() / str(workspace.request_id)
    quarantine = request_root / ".abandoned" / workspace.revision_uuid
    quarantine.parent.mkdir(parents=True, exist_ok=True)
    if quarantine.exists():
        quarantine = quarantine.with_name(
            f"{workspace.revision_uuid}-{uuid.uuid4().hex[:8]}"
        )
    shutil.move(str(workspace.staging_path), str(quarantine))
    return quarantine


def workspace_relpath(path: Path) -> str:
    resolved_root = candidate_root().resolve(strict=False)
    return str(path.resolve(strict=False).relative_to(resolved_root)).replace(
        "\\",
        "/",
    )


__all__ = [
    "CandidateWorkspace",
    "candidate_root",
    "checkpoint_workspace",
    "file_manifest_sha256",
    "freeze_candidate_workspace",
    "open_candidate_workspace",
    "quarantine_invalid_staging",
    "read_source",
    "source_file_manifest",
    "workspace_relpath",
    "write_sources",
]
