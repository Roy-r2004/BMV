"""Isolated, resumable Phase 4 validation workspaces."""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

from app.application.appspec.source import canonical_json
from app.application.candidate_generation.cache import canonical_sha256
from app.application.runtime_validation.cache import sha256_file
from app.core.config import settings


_SAFE_RELATIVE = re.compile(r"^[A-Za-z0-9_./-]+$")


@dataclass(frozen=True)
class RuntimeValidationWorkspace:
    request_id: int
    candidate_revision_uuid: str
    attempt_uuid: str
    staging_path: Path
    candidate_path: Path
    final_path: Path
    resumed: bool


def validation_root() -> Path:
    return settings.PREVIEW_VALIDATIONS_DIR


def _safe_relative_path(root: Path, relpath: str) -> Path:
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
        raise ValueError(f"Unsafe runtime-validation path: {relpath!r}")
    resolved_root = root.resolve(strict=False)
    target = resolved_root.joinpath(*parts)
    try:
        target.resolve(strict=False).relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("Runtime-validation path escapes its root") from exc
    return target


def source_manifest(
    source_root: Path,
    expected_manifest: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    expected_paths = tuple(str(item["path"]) for item in expected_manifest)
    if len(expected_paths) != len(set(expected_paths)):
        raise ValueError("Candidate manifest repeats paths")
    actual_files = tuple(
        sorted(
            str(path.relative_to(source_root)).replace("\\", "/")
            for path in source_root.rglob("*")
            if path.is_file()
        )
    )
    if actual_files != tuple(sorted(expected_paths)):
        raise ValueError("Frozen candidate files differ from its manifest")
    rows: list[dict[str, Any]] = []
    expected_by_path = {
        str(item["path"]): item for item in expected_manifest
    }
    for relpath in sorted(expected_paths):
        target = _safe_relative_path(source_root, relpath)
        if target.is_symlink():
            raise ValueError("Frozen candidate contains a symbolic link")
        payload = target.read_bytes()
        digest = sha256_file(target)
        expected = expected_by_path[relpath]
        if (
            digest != expected.get("sha256")
            or len(payload) != expected.get("byte_count")
        ):
            raise ValueError("Frozen candidate file hash is invalid")
        rows.append(
            {
                "path": relpath,
                "sha256": digest,
                "byte_count": len(payload),
            }
        )
    return tuple(rows)


def source_manifest_sha256(
    source_root: Path,
    expected_manifest: tuple[dict[str, Any], ...],
) -> str:
    return canonical_sha256(source_manifest(source_root, expected_manifest))


def _metadata_path(path: Path) -> Path:
    return path / ".runtime-attempt.json"


def _write_metadata(
    workspace: RuntimeValidationWorkspace,
    *,
    cache_identity: str,
    source_candidate_sha256: str,
) -> None:
    _metadata_path(workspace.staging_path).write_text(
        canonical_json(
            {
                "request_id": workspace.request_id,
                "candidate_revision_uuid": (
                    workspace.candidate_revision_uuid
                ),
                "attempt_uuid": workspace.attempt_uuid,
                "cache_identity": cache_identity,
                "source_candidate_sha256": source_candidate_sha256,
                "runtime_policy_revision": (
                    settings.V2_RUNTIME_POLICY_REVISION
                ),
            }
        ),
        encoding="utf-8",
        newline="\n",
    )


def open_validation_workspace(
    *,
    request_id: int,
    candidate_revision_uuid: str,
    attempt_uuid: str,
    cache_identity: str,
    source_candidate_sha256: str,
    source_path: Path,
    expected_manifest: tuple[dict[str, Any], ...],
    resume_relpath: str | None = None,
) -> RuntimeValidationWorkspace:
    uuid.UUID(attempt_uuid)
    root = validation_root()
    request_root = (
        root
        / str(request_id)
        / candidate_revision_uuid
    )
    final_path = request_root / "attempts" / attempt_uuid
    if resume_relpath:
        staging = _safe_relative_path(root, resume_relpath)
        metadata_path = _metadata_path(staging)
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError("Runtime attempt metadata is invalid") from exc
        if metadata != {
            "request_id": request_id,
            "candidate_revision_uuid": candidate_revision_uuid,
            "attempt_uuid": attempt_uuid,
            "cache_identity": cache_identity,
            "source_candidate_sha256": source_candidate_sha256,
            "runtime_policy_revision": settings.V2_RUNTIME_POLICY_REVISION,
        }:
            raise ValueError("Runtime attempt resume provenance changed")
        candidate_path = staging / "candidate"
        source_manifest_sha256(candidate_path, expected_manifest)
        return RuntimeValidationWorkspace(
            request_id=request_id,
            candidate_revision_uuid=candidate_revision_uuid,
            attempt_uuid=attempt_uuid,
            staging_path=staging,
            candidate_path=candidate_path,
            final_path=final_path,
            resumed=True,
        )
    staging = request_root / ".staging" / attempt_uuid
    staging.mkdir(parents=True, exist_ok=False)
    candidate_path = staging / "candidate"
    shutil.copytree(source_path, candidate_path, copy_function=shutil.copy2)
    for item in expected_manifest:
        relpath = str(item["path"])
        source_file = _safe_relative_path(source_path, relpath)
        copied_file = _safe_relative_path(candidate_path, relpath)
        if os.path.samefile(source_file, copied_file):
            raise ValueError("Mutable hardlink detected in validation copy")
    copied_hash = source_manifest_sha256(candidate_path, expected_manifest)
    if copied_hash != source_candidate_sha256:
        raise ValueError("Validation copy differs from frozen candidate")
    workspace = RuntimeValidationWorkspace(
        request_id=request_id,
        candidate_revision_uuid=candidate_revision_uuid,
        attempt_uuid=attempt_uuid,
        staging_path=staging,
        candidate_path=candidate_path,
        final_path=final_path,
        resumed=False,
    )
    _write_metadata(
        workspace,
        cache_identity=cache_identity,
        source_candidate_sha256=source_candidate_sha256,
    )
    return workspace


def create_derived_repair_workspace(
    workspace: RuntimeValidationWorkspace,
    *,
    repair_uuid: str,
) -> Path:
    uuid.UUID(repair_uuid)
    # Keep the derived path short enough for Windows CreateProcess cwd limits.
    target = workspace.staging_path / f"repair-{repair_uuid[:8]}"
    shutil.copytree(
        workspace.candidate_path,
        target,
        copy_function=shutil.copy2,
        ignore=shutil.ignore_patterns("dist", "node_modules"),
    )
    return target


def apply_deterministic_repair(candidate_path: Path, repair_code: str) -> str:
    allowed = {
        "route_fallback_configuration",
        "asset_path_normalization",
        "manifest_wiring",
        "deterministic_test_hook_wiring",
        "recognized_build_configuration",
    }
    if repair_code not in allowed:
        raise ValueError("Repair code is outside the Phase 4 allowlist")
    config = candidate_path / "vite.config.ts"
    source = config.read_text(encoding="utf-8")
    changed = source
    changed_paths: list[str] = []
    if repair_code in {
        "route_fallback_configuration",
        "recognized_build_configuration",
    } and "appType:" not in changed:
        changed = changed.replace(
            "export default defineConfig({",
            "export default defineConfig({\n  appType: 'spa',",
            1,
        )
    elif repair_code == "asset_path_normalization":
        changed = changed.replace("base: '/'", "base: './'")
        index = candidate_path / "index.html"
        index_source = index.read_text(encoding="utf-8")
        index_changed = "\n".join(
            line
            for line in index_source.splitlines()
            if not (
                'rel="preconnect"' in line
                and ("http://" in line or "https://" in line)
            )
        ) + "\n"
        if index_changed != index_source:
            index.write_text(
                index_changed,
                encoding="utf-8",
                newline="\n",
            )
            changed_paths.append("index.html")
    elif repair_code == "manifest_wiring":
        # Phase 4 owns its dist identity manifest; source wiring is untouched.
        return "dist_identity_manifest"
    elif repair_code == "deterministic_test_hook_wiring":
        raise ValueError(
            "Test-hook wiring requires a unique canonical target"
        )
    if changed != source:
        config.write_text(changed, encoding="utf-8", newline="\n")
        changed_paths.append("vite.config.ts")
    if not changed_paths:
        raise ValueError("Deterministic repair had no recognized target")
    return ",".join(changed_paths)


def freeze_validation_workspace(
    workspace: RuntimeValidationWorkspace,
) -> Path:
    metadata = _metadata_path(workspace.staging_path)
    if metadata.exists():
        metadata.unlink()
    workspace.final_path.parent.mkdir(parents=True, exist_ok=True)
    if workspace.final_path.exists():
        raise FileExistsError("Validation attempt is already frozen")
    os.replace(workspace.staging_path, workspace.final_path)
    return workspace.final_path


def workspace_relpath(path: Path) -> str:
    return str(
        path.resolve(strict=False).relative_to(
            validation_root().resolve(strict=False)
        )
    ).replace("\\", "/")


__all__ = [
    "RuntimeValidationWorkspace",
    "apply_deterministic_repair",
    "create_derived_repair_workspace",
    "freeze_validation_workspace",
    "open_validation_workspace",
    "source_manifest",
    "source_manifest_sha256",
    "validation_root",
    "workspace_relpath",
]
