"""Workspace management for generated preview apps."""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from pathlib import PureWindowsPath

from app.core.config import settings
from app.infrastructure.logging import get_logger

ws_log = get_logger("Workspace")

_SKIP_COPY = {"node_modules", "dist", ".git"}


class UnauthorizedPageWrite(RuntimeError):
    """A module outside the allowlist tried to write a page or a render artifact."""


#: Roadmap DoD 8. Paths only an allowlisted module may write.
#:
#: `src/render/**` does not exist yet — Phase 2 creates it — and the guard is
#: armed for it deliberately. The point of DoD 8 is that Phase 2 *opens* with the
#: guarantee rather than trying to establish it after twenty modules have already
#: learned to write there.
_GUARDED_WRITE_RE = re.compile(r"^src/(?:pages/.+\.(?:tsx|jsx)|render/.+)$")

#: Every module that may write a guarded path. **Derived, not designed.**
#:
#: This is not a statement that 26 modules *should* be able to write pages. It is
#: the measurement that they can, and Phase 2's whole thesis is that exactly one
#: should. Pinning it now means the number can only go down on purpose: 2.4-2.5
#: is measured by how much of this list disappears.
#:
#: Two sources, because one was not safe on its own:
#:
#: * `observed` — caught writing a guarded path by running the suite with
#:   `BMV_AUDIT_PAGE_WRITES=1`. 13 modules.
#: * `static` — calls the write seam with a *computed* path. These iterate
#:   `list_source_files` and rewrite whatever they find, which includes pages;
#:   the suite's fixtures just never put a page in front of them. Enforcing on
#:   the observed set alone would have raised in production on the first
#:   generation whose workspace differs from a test fixture.
#:
#: A `static` entry is therefore also a **test-coverage gap**: nothing proves
#: whether it writes pages or not. Confirming or removing each one is cheap
#: Phase 2 work and shrinks the list honestly.
#:
#: To change this: run the audit, do not hand-edit. A module added without a
#: reason in the commit message is the failure the guard exists to prevent.
_PAGE_WRITERS: frozenset[str] = frozenset(
    {
        "app.application.preview_app.workspace",
        "app.application.appspec.hooks",  # static
        "app.application.preview_app.ai_feature_surfaces",  # static
        "app.application.preview_app.assemble",  # static
        "app.application.preview_app.asset_integrity",  # observed
        "app.application.preview_app.chrome_nav",  # static
        "app.application.preview_app.codegen.critic",  # observed
        "app.application.preview_app.codegen.fix_agent",  # observed
        "app.application.preview_app.codegen.generate",  # observed
        "app.application.preview_app.codegen.mock",  # static
        "app.application.preview_app.fallback",  # observed
        "app.application.preview_app.pipeline.build_phase",  # static
        "app.application.preview_app.pipeline.visual_critic",  # observed
        "app.application.preview_app.protected_paths",  # static
        "app.application.preview_app.quality_gate",  # observed
        "app.application.preview_app.quality_repair",  # observed
        "app.application.preview_app.refinement.chat_rebuild",  # observed
        "app.application.preview_app.refinement.workspace_patch",  # observed
        "app.application.preview_app.safety.brand_contract",  # static
        "app.application.preview_app.safety.catalogue_guards",  # observed
        "app.application.preview_app.safety.copy_hygiene",  # static
        "app.application.preview_app.safety.imports",  # observed
        "app.application.preview_app.safety.mock_data",  # static
        "app.application.preview_app.safety.pages",  # observed
        "app.application.preview_app.safety.seed_keys",  # static
        "app.application.preview_app.safety.source_sanitize",  # static
        "app.application.preview_app.safety.ui_icons",  # static
    }
)

#: Test modules write page fixtures directly. Allowed, and stated rather than
#: left to look like an accident: production has no `tests.` module, so the
#: guarantee this guard makes about the pipeline is unaffected. Without it the
#: only alternative is routing fixture setup through a production writer, which
#: would make the census lie.
_TEST_MODULE_PREFIX = "tests."


def _page_write_origin() -> str:
    """The nearest calling module outside this one.

    Frame-walking rather than `inspect.stack()`, which builds a full FrameInfo
    (source lookup included) for every level and costs milliseconds. Guarded
    writes number in the dozens per generation, so this has to be cheap enough
    to leave on in production — a guard that only runs in tests guarantees
    nothing about the pipeline.
    """
    frame = sys._getframe(1)
    while frame is not None:
        name = frame.f_globals.get("__name__", "")
        if name and name != __name__:
            return name
        frame = frame.f_back
    return "<unknown>"


def _check_page_write_allowed(rel_path: str) -> None:
    """Enforce DoD 8 at the seam every page write already passes through."""
    if not _GUARDED_WRITE_RE.match(rel_path):
        return
    origin = _page_write_origin()
    if os.getenv("BMV_AUDIT_PAGE_WRITES"):
        # Census mode: record, never block. This is how `_PAGE_WRITERS` is built.
        print(f"PAGE_WRITE_ORIGIN\t{origin}\t{rel_path}", flush=True)
        return
    if origin in _PAGE_WRITERS or origin.startswith(_TEST_MODULE_PREFIX):
        return
    raise UnauthorizedPageWrite(
        f"{origin} may not write {rel_path}: not in the DoD 8 allowlist. "
        "If this is a legitimate new writer, add it to `_PAGE_WRITERS` with a "
        "reason — do not widen the pattern."
    )


def get_workspace(request_id: int) -> Path:
    return settings.PREVIEW_APPS_DIR / str(request_id)


def _legacy_get_dist_dir(request_id: int) -> Path:
    """Pre-Phase-7 dist resolution — exact historical behavior."""
    return get_workspace(request_id) / "dist"


def get_dist_dir(request_id: int) -> Path:
    """Resolve preview dist; Option A flag-gated pointer adapter (Phase 7C).

    When Phase 7 rollout/promote flags are off, returns the exact legacy path.
    When enabled, uses read-only serving resolution with approved fallbacks.
    Never imports promotion writers or apply transactions on this path.
    """
    from app.core import config as app_config

    cfg = app_config.settings
    if not (
        cfg.V2_PHASE7_ROLLOUT_ENABLED
        and cfg.V2_PHASE7_PROMOTE_ENABLED
        and cfg.V2_PHASE7_CONFIG_VALID
    ):
        return _legacy_get_dist_dir(request_id)
    from app.application.rollout.serving_resolve import resolve_dist_for_serving

    return resolve_dist_for_serving(
        request_id,
        legacy_get_dist_dir=_legacy_get_dist_dir,
    )


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


def write_file(workspace: Path, rel_path: str, content: str) -> str:
    """Write generated source only, rejecting absolute, traversal, and symlink escapes.

    Returns the path actually written, which is **not always `rel_path`**: page
    files under `src/pages/` are canonicalized (`Dashboard.tsx` ->
    `DashboardPage.tsx`) and the pre-canonical file is deleted. A caller that
    keeps `rel_path` afterwards is holding a path to a file that no longer
    exists. Record the return value instead.
    """
    return write_trusted_contained_file(workspace, rel_path, content)


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
) -> str:
    """Write trusted source bytes/text while replacing only the final symlink entry.

    Returns the canonical workspace-relative path that was written. See
    `write_file` for why that is not always the path you passed in.
    """
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

    # After canonicalization, so the guard judges the path actually written.
    _check_page_write_allowed(normalized)

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
    # `normalized`, not `rel_path`: for a non-page write `rel_path` is still
    # whatever the caller passed (back-slashes, `./`), and callers compare this
    # against `list_source_files`, which is forward-slashed and lexically
    # normalized. Returning the raw form would trade one wrong path for another.
    return normalized


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
