"""Workspace management for generated preview apps."""
from __future__ import annotations

import shutil
from pathlib import Path
from pathlib import PureWindowsPath

from app.core.config import settings
from app.infrastructure.logging import get_logger

ws_log = get_logger("Workspace")

_SKIP_COPY = {"node_modules", "dist", ".git"}


def get_workspace(request_id: int) -> Path:
    return settings.PREVIEW_APPS_DIR / str(request_id)


def get_dist_dir(request_id: int) -> Path:
    return get_workspace(request_id) / "dist"


def prepare_workspace(request_id: int) -> Path:
    """Copy template into an isolated workspace (fresh each generation)."""
    workspace = get_workspace(request_id)
    tpl = settings.PREVIEW_TEMPLATE_DIR
    ws_log.info("prepare_workspace id=%s template=%s exists=%s", request_id, tpl, tpl.is_dir())
    if workspace.exists():
        ws_log.debug("removing old workspace %s", workspace)
        shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True, exist_ok=True)

    if not tpl.is_dir():
        raise FileNotFoundError(
            f"Preview template not found: {tpl}. "
            "Deploy must include preview-template/ (see render.yaml / backend/preview-template)."
        )

    copied = 0
    for item in tpl.iterdir():
        if item.name in _SKIP_COPY:
            continue
        dest = workspace / item.name
        if item.is_dir():
            shutil.copytree(item, dest, ignore=shutil.ignore_patterns(*_SKIP_COPY))
        else:
            shutil.copy2(item, dest)
        copied += 1
    ws_log.info("workspace ready at %s (%s top-level items)", workspace, copied)
    return workspace


def _safe_workspace_target(
    workspace: Path,
    rel_path: str,
    *,
    source_only: bool,
    replace_target_symlink: bool = False,
) -> Path:
    raw = str(rel_path or "")
    normalized = raw.replace("\\", "/")
    parts = tuple(part for part in normalized.split("/") if part not in {"", "."})
    if (
        not raw
        or Path(raw).is_absolute()
        or PureWindowsPath(raw).is_absolute()
        or normalized.startswith("/")
        or ".." in parts
    ):
        raise ValueError(f"Unsafe workspace path: {rel_path}")
    if source_only and (not parts or parts[0] != "src" or len(parts) < 2):
        raise ValueError(f"Generated source writes must stay under src/: {rel_path}")

    root = Path(workspace).resolve()
    target = root.joinpath(*parts)
    allowed_root = root / "src" if source_only else root
    resolved_parent = target.parent.resolve(strict=False)
    try:
        resolved_parent.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError(f"Workspace parent escapes allowed root: {rel_path}") from exc
    if target.is_symlink():
        if not replace_target_symlink:
            raise ValueError(f"Workspace path targets a symlink: {rel_path}")
        target.unlink()
    elif target.exists():
        try:
            target.resolve().relative_to(allowed_root)
        except ValueError as exc:
            raise ValueError(f"Workspace path escapes allowed root: {rel_path}") from exc
    return target


def write_file(workspace: Path, rel_path: str, content: str) -> None:
    """Write generated source only, rejecting absolute, traversal, and symlink escapes."""
    write_trusted_contained_file(workspace, rel_path, content)


def write_trusted_workspace_file(workspace: Path, rel_path: str, content: str) -> None:
    """Explicit trusted API for repository-root workspace files such as package.json."""
    target = _safe_workspace_target(
        workspace,
        rel_path,
        source_only=False,
        replace_target_symlink=True,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target = _safe_workspace_target(
        workspace,
        rel_path,
        source_only=False,
        replace_target_symlink=True,
    )
    target.write_text(content, encoding="utf-8")


def write_trusted_contained_file(
    workspace: Path,
    rel_path: str,
    content: str | bytes,
) -> None:
    """Write trusted source bytes/text while replacing only the final symlink entry."""
    from app.application.preview_app.protected_paths import (
        canonicalize_page_component_path,
        canonical_workspace_path,
    )

    original = canonical_workspace_path(rel_path)
    normalized = original
    if normalized.startswith("src/pages/") and normalized.lower().endswith((".tsx", ".jsx")):
        normalized = canonicalize_page_component_path(normalized)
        # Drop case-variant siblings (Homepage.tsx vs HomePage.tsx) so Vite
        # never bundles two copies of the same route on case-sensitive FS.
        parent = (Path(workspace) / normalized).parent
        if parent.is_dir():
            want_name = Path(normalized).name
            want_lower = want_name.lower()
            for sibling in parent.iterdir():
                if (
                    sibling.is_file()
                    and sibling.name.lower() == want_lower
                    and sibling.name != want_name
                ):
                    try:
                        sibling.unlink()
                    except OSError:
                        pass
        rel_path = normalized

    target = _safe_workspace_target(
        workspace,
        rel_path,
        source_only=True,
        replace_target_symlink=True,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    # Re-check after mkdir to close a missing-parent path gap.
    target = _safe_workspace_target(
        workspace,
        rel_path,
        source_only=True,
        replace_target_symlink=True,
    )
    if isinstance(content, bytes):
        target.write_bytes(content)
    else:
        target.write_text(content, encoding="utf-8")

    # Canonical rename (Dashboard.tsx → DashboardPage.tsx) must not leave the
    # pre-canonical file behind — import guards would "fix" a duplicate copy.
    if original != normalized:
        old_path = Path(workspace).joinpath(*original.split("/"))
        try:
            if old_path.is_file() and old_path.resolve() != target.resolve():
                old_path.unlink()
        except OSError:
            pass


def read_file(workspace: Path, rel_path: str) -> str:
    target = _safe_workspace_target(workspace, rel_path, source_only=True)
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
