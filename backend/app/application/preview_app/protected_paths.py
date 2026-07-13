"""Shared ownership rules for template-provided preview UI files."""
from __future__ import annotations

import posixpath
from pathlib import Path
from pathlib import PureWindowsPath


def has_catalogue_routes(architect: dict | None) -> bool:
    architect = architect or {}
    return bool(architect.get("_catalogue_workspace")) or any(
        route.get("skeleton_id") for route in architect.get("routes") or []
    )


def canonical_workspace_path(path: str, workspace=None) -> str:
    """Lexically normalize a source path without following filesystem links."""
    raw = str(path or "").replace("\\", "/")
    if workspace is not None:
        base = str(Path(workspace).absolute()).replace("\\", "/").rstrip("/")
        if raw.lower() == base.lower():
            raw = ""
        elif raw.lower().startswith(base.lower() + "/"):
            raw = raw[len(base) + 1 :]
    normalized = posixpath.normpath(raw)
    return "" if normalized == "." else normalized


def safe_source_path(path: str, workspace=None) -> str | None:
    """Return a canonical src-relative path, or None for absolute/traversal input."""
    raw = str(path or "")
    normalized_raw = raw.replace("\\", "/")
    raw_parts = tuple(
        part for part in normalized_raw.split("/") if part not in {"", "."}
    )
    if (
        Path(raw).is_absolute()
        or PureWindowsPath(raw).is_absolute()
        or normalized_raw.startswith("/")
        or ".." in raw_parts
    ):
        return None
    canonical = canonical_workspace_path(raw)
    if (
        not canonical.startswith("src/")
        or canonical == "src"
        or canonical == ".."
        or canonical.startswith("../")
        or "/../" in f"/{canonical}/"
    ):
        return None
    if workspace is not None:
        root = Path(workspace).resolve()
        candidate = root.joinpath(*canonical.split("/"))
        try:
            candidate.resolve(strict=False).relative_to(root / "src")
        except ValueError:
            return None
    return canonical


def safe_generated_route_path(
    path: str,
    architect: dict | None,
    workspace=None,
) -> str | None:
    """Canonicalize an AI route component path into the approved page scope."""
    canonical = safe_source_path(path, workspace)
    if not canonical or not canonical.startswith("src/pages/"):
        return None
    if is_template_owned_path(canonical, architect, workspace):
        return None
    return canonical


def is_template_owned_path(path: str, architect: dict | None, workspace=None) -> bool:
    """Catalogue workspaces may read, but never generate or rewrite, these files."""
    if not has_catalogue_routes(architect):
        return False
    norm = canonical_workspace_path(path, workspace).lower()
    if norm == ".." or norm.startswith("../") or norm.startswith("/"):
        return False
    return (
        norm.startswith("src/ui/")
        or norm == "src/components/uiicons.tsx"
        or norm == "src/lib/preview-bridge.ts"
    )


def snapshot_template_owned_files(workspace, architect: dict | None) -> dict[str, str]:
    if not has_catalogue_routes(architect):
        return {}
    from app.application.preview_app.workspace import list_source_files, read_file

    return {
        path: read_file(workspace, path)
        for path in list_source_files(workspace)
        if is_template_owned_path(path, architect)
    }


def restore_template_owned_files(
    workspace,
    architect: dict | None,
    snapshot: dict[str, str],
) -> None:
    if not has_catalogue_routes(architect):
        return
    from app.application.preview_app.workspace import list_source_files, write_file

    current = {
        path
        for path in list_source_files(workspace)
        if is_template_owned_path(path, architect)
    }
    for path in current - set(snapshot):
        try:
            (Path(workspace) / path).unlink()
        except OSError:
            pass
    for path, content in snapshot.items():
        write_file(workspace, path, content)
