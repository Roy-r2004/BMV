"""Isolated staging and immutable workspace lifecycle for Phase 3B."""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from app.application.appspec.source import canonical_json
from app.application.candidate_generation.cache import (
    canonical_sha256,
    sha256_text,
)
from app.application.candidate_generation.deterministic import (
    CandidateSourceFile,
)
from app.core.config import settings


_SAFE_RELATIVE = re.compile(r"^[A-Za-z0-9_./-]+$")


@dataclass(frozen=True)
class CandidateWorkspace:
    request_id: int
    revision_uuid: str
    staging_path: Path
    final_path: Path
    resumed: bool


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
) -> None:
    payload = {
        "request_id": workspace.request_id,
        "revision_uuid": workspace.revision_uuid,
        "upstream_sha256": upstream_sha256,
        "policy_revision": settings.V2_CANDIDATE_POLICY_REVISION,
        "completed_artifacts": completed_artifacts or {},
    }
    _attempt_metadata_path(workspace.staging_path).write_text(
        canonical_json(payload),
        encoding="utf-8",
        newline="\n",
    )


def checkpoint_workspace(
    workspace: CandidateWorkspace,
    *,
    upstream_sha256: str,
    completed_artifacts: dict[str, str],
) -> None:
    _write_attempt_metadata(
        workspace,
        upstream_sha256=upstream_sha256,
        completed_artifacts=completed_artifacts,
    )


def _verified_resume(
    staging_path: Path,
    *,
    request_id: int,
    upstream_sha256: str,
) -> CandidateWorkspace | None:
    metadata_path = _attempt_metadata_path(staging_path)
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        revision_uuid = str(payload["revision_uuid"])
        uuid.UUID(revision_uuid)
    except Exception:
        return None
    if (
        payload.get("request_id") != request_id
        or payload.get("upstream_sha256") != upstream_sha256
        or payload.get("policy_revision")
        != settings.V2_CANDIDATE_POLICY_REVISION
    ):
        return None
    for relpath, expected_sha in (
        payload.get("completed_artifacts") or {}
    ).items():
        target = _safe_target(staging_path, relpath)
        if not target.is_file() or sha256_text(
            target.read_text(encoding="utf-8")
        ) != expected_sha:
            return None
    return CandidateWorkspace(
        request_id=request_id,
        revision_uuid=revision_uuid,
        staging_path=staging_path,
        final_path=(
            candidate_root() / str(request_id) / "revisions" / revision_uuid
        ),
        resumed=True,
    )


def open_candidate_workspace(
    *,
    request_id: int,
    upstream_sha256: str,
) -> CandidateWorkspace:
    request_root = candidate_root() / str(request_id)
    staging_root = request_root / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    for staging_path in sorted(staging_root.iterdir()):
        if not staging_path.is_dir():
            continue
        resumed = _verified_resume(
            staging_path,
            request_id=request_id,
            upstream_sha256=upstream_sha256,
        )
        if resumed is not None:
            return resumed
    revision_uuid = str(uuid.uuid4())
    staging_path = staging_root / revision_uuid
    staging_path.mkdir(parents=False, exist_ok=False)
    workspace = CandidateWorkspace(
        request_id=request_id,
        revision_uuid=revision_uuid,
        staging_path=staging_path,
        final_path=request_root / "revisions" / revision_uuid,
        resumed=False,
    )
    _write_attempt_metadata(
        workspace,
        upstream_sha256=upstream_sha256,
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
