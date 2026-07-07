"""Workspace management for generated preview apps."""
from __future__ import annotations

import shutil
from pathlib import Path

from app.core.config import settings

_SKIP_COPY = {"node_modules", "dist", ".git"}


def get_workspace(request_id: int) -> Path:
    return settings.PREVIEW_APPS_DIR / str(request_id)


def get_dist_dir(request_id: int) -> Path:
    return get_workspace(request_id) / "dist"


def prepare_workspace(request_id: int) -> Path:
    """Copy template into an isolated workspace (fresh each generation)."""
    workspace = get_workspace(request_id)
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True, exist_ok=True)

    if not settings.PREVIEW_TEMPLATE_DIR.is_dir():
        raise FileNotFoundError(f"Preview template not found: {settings.PREVIEW_TEMPLATE_DIR}")

    for item in settings.PREVIEW_TEMPLATE_DIR.iterdir():
        if item.name in _SKIP_COPY:
            continue
        dest = workspace / item.name
        if item.is_dir():
            shutil.copytree(item, dest, ignore=shutil.ignore_patterns(*_SKIP_COPY))
        else:
            shutil.copy2(item, dest)
    return workspace


def write_file(workspace: Path, rel_path: str, content: str) -> None:
    target = workspace / rel_path.replace("\\", "/")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def read_file(workspace: Path, rel_path: str) -> str:
    target = workspace / rel_path.replace("\\", "/")
    return target.read_text(encoding="utf-8") if target.is_file() else ""


def list_source_files(workspace: Path) -> list[str]:
    src = workspace / "src"
    if not src.is_dir():
        return []
    return sorted(
        str(p.relative_to(workspace)).replace("\\", "/")
        for p in src.rglob("*")
        if p.is_file() and p.suffix in {".tsx", ".ts", ".css"}
    )


def summarize_files(workspace: Path, paths: list[str], max_chars: int = 12000) -> str:
    parts: list[str] = []
    total = 0
    for rel in paths:
        content = read_file(workspace, rel)
        if not content:
            continue
        chunk = f"--- {rel} ({len(content)} chars) ---\n{content[:2000]}\n"
        if total + len(chunk) > max_chars:
            parts.append(f"--- {rel} --- (truncated)")
            break
        parts.append(chunk)
        total += len(chunk)
    return "\n".join(parts) if parts else "(no files yet)"


def snapshot_source(workspace: Path) -> dict[str, str]:
    """Capture current content of every source file, to allow safe rollback."""
    return {p: read_file(workspace, p) for p in list_source_files(workspace)}


def restore_source(workspace: Path, snapshot: dict[str, str]) -> None:
    """Restore source files to a prior snapshot, removing any files added since."""
    for path, content in snapshot.items():
        write_file(workspace, path, content)
    for path in set(list_source_files(workspace)) - set(snapshot.keys()):
        try:
            (workspace / path).unlink()
        except OSError:
            pass


def backup_dist(workspace: Path) -> Path | None:
    """Copy the currently-served build output aside before a risky rebuild."""
    dist = workspace / "dist"
    if not dist.is_dir():
        return None
    backup = workspace / "_dist_backup"
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)
    shutil.copytree(dist, backup)
    return backup


def restore_dist(workspace: Path, backup: Path) -> None:
    """Bring back the last known-good build output."""
    dist = workspace / "dist"
    if dist.exists():
        shutil.rmtree(dist, ignore_errors=True)
    shutil.copytree(backup, dist)


def discard_backup(backup: Path | None) -> None:
    if backup and backup.exists():
        shutil.rmtree(backup, ignore_errors=True)
