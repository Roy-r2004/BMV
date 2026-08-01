"""Shared ownership rules for template-provided preview UI files."""
from __future__ import annotations

import posixpath
import re
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


def _pascal_token(token: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "", token or "")
    if not token:
        return ""
    return token[0].upper() + token[1:]


def canonicalize_page_component_path(path: str) -> str:
    """Force page files into PascalCase `*Page.tsx` under src/pages/.

    Prevents Linux-only duplicates like Homepage.tsx + HomePage.tsx when the
    architect and scaffold disagree on casing.
    """
    canonical = canonical_workspace_path(path)
    if not canonical.startswith("src/pages/") or not canonical.lower().endswith((".tsx", ".jsx")):
        return canonical
    parts = canonical.split("/")
    filename = parts[-1]
    stem, ext = filename.rsplit(".", 1)
    ext = ext.lower()
    # Drop trailing Page/page so we can re-attach a canonical suffix.
    core = re.sub(r"(?i)page$", "", stem)
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", core)
    tokens = re.findall(r"[A-Za-z0-9]+", spaced)
    pascal = "".join(_pascal_token(tok) for tok in tokens) or "Page"
    if not pascal.lower().endswith("page"):
        pascal = f"{pascal}Page"
    elif pascal.endswith("page"):
        pascal = pascal[:-4] + "Page"
    # Keep area folders lowercase-stable (owner/admin/member/staff/…).
    # PascalCasing them (owner → Owner) breaks Linux Docker volumes and App imports.
    dirs = parts[:-1]
    normalized_dirs: list[str] = []
    for idx, part in enumerate(dirs):
        if idx <= 1:  # src / pages
            normalized_dirs.append(part)
            continue
        normalized_dirs.append(part.lower())
    return "/".join([*normalized_dirs, f"{pascal}.{ext}"])


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
    return canonicalize_page_component_path(canonical)


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


#: Files the *generator* owns outright. Not template-owned — `App.tsx` is
#: written from scratch by `assemble.write_app_tsx` on every run, and
#: `index.css` from `codegen/index_css.j2` — but equally not something an AI
#: repair may edit. Two writers disagreed about this and it cost request 67 its
#: whole storefront: `codegen/fix_agent` refused `App.tsx` via its own private
#: basename list while `quality_repair.RepairAPI` checked only
#: `is_template_owned_path`, which covers `src/ui/**` and two files. So the gate's
#: repair model was handed `App.tsx`, deleted
#: `<Route path="/collection" element={<CollectionPage />} />` to clear a
#: dead-link finding, and left 14 links across 7 pages falling through
#: `path="*"` to the home page.
_GENERATOR_OWNED_BASENAMES = frozenset(
    {"app.tsx", "index.css", "package.json", "package-lock.json", "main.tsx"}
)


def is_generator_owned_path(path: str, workspace=None) -> bool:
    """True for files only the pipeline may write. Deliberately architect-free.

    `is_template_owned_path` yields when a workspace has no catalogue routes;
    these files are the pipeline's on every run, so this rule has no such door.
    """
    norm = canonical_workspace_path(path, workspace).lower()
    if norm == ".." or norm.startswith("../") or norm.startswith("/"):
        return False
    return norm.rsplit("/", 1)[-1] in _GENERATOR_OWNED_BASENAMES


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
