"""Preview safety — Source Sanitize."""
from __future__ import annotations

import re

from app.application.preview_app.patterns import (
    _EMPTY_ARRAY_STATE_RE,
    _MOCK_IMPORT_ANY_RE,
)
from app.application.preview_app.source_quality import (
    fix_unescaped_apostrophes,
    looks_truncated_source,
)
from app.application.preview_app.text_utils import _strip_fences
from app.application.preview_app.workspace import (
    list_source_files,
    read_file,
    write_file,
)
from app.infrastructure.logging import get_logger

guard_log = get_logger("SafetyGuards")

def sanitize_workspace_sources(workspace) -> list[str]:
    """Strip markdown fences/prose accidentally pasted into source files."""
    cleaned: list[str] = []
    for rel in list_source_files(workspace):
        if not rel.endswith((".tsx", ".ts", ".css")):
            continue
        raw = read_file(workspace, rel)
        fixed = _strip_fences(raw)
        if fixed != raw.strip():
            write_file(workspace, rel, fixed)
            cleaned.append(rel)
    return cleaned

def _import_prefix_for_page(rel: str) -> str:
    """Relative prefix from a page file back to `src/` (e.g. `../../` for `src/pages/owner/X.tsx`)."""
    norm = rel.replace("\\", "/")
    if "src/pages/" not in norm:
        return "../"
    tail = norm.split("src/pages/", 1)[1]
    depth = tail.count("/")
    return "../" * (depth + 1)

def fix_nested_import_paths(workspace) -> list[str]:
    """Correct `../components` → `../../components` (etc.) in nested page folders."""
    fixed: list[str] = []
    for rel in list_source_files(workspace):
        if not rel.endswith((".tsx", ".ts")):
            continue
        norm = rel.replace("\\", "/")
        if "/pages/" not in norm:
            continue
        correct = _import_prefix_for_page(norm)
        content = read_file(workspace, rel)
        updated = content
        for target in ("components/", "data/", "lib/", "layouts/"):
            for shallow_len in range(1, 6):
                shallow = "../" * shallow_len
                if shallow == correct:
                    break
                for quote in ("'", '"'):
                    wrong = f"from {quote}{shallow}{target}"
                    right = f"from {quote}{correct}{target}"
                    if wrong in updated:
                        updated = updated.replace(wrong, right)
        if updated != content:
            write_file(workspace, rel, updated)
            fixed.append(rel)
    return fixed

def find_truncated_pages(workspace) -> list[str]:
    """Return page source paths that look cut off mid-generation."""
    out: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if "/pages/" not in norm or not norm.endswith((".tsx", ".ts")):
            continue
        if looks_truncated_source(read_file(workspace, rel)):
            out.append(rel)
    return out

def _empty_seed_state_vars(content: str) -> list[str]:
    """`useState([])` variable names in `content` that are later `.map()`'d in
    render — i.e. they drive visible list content rather than being
    incidental UI state (a `showModal`/`editingItem` boolean, or a
    multi-select `selectedIds` array that's legitimately meant to start
    empty). Exposed separately from `find_empty_seed_pages` so callers can
    name the specific violating variable in a regeneration instruction.
    """
    return [
        var for var in _EMPTY_ARRAY_STATE_RE.findall(content)
        if re.search(rf"\b{re.escape(var)}\??\.map\(", content)
    ]

def find_empty_seed_pages(workspace) -> list[str]:
    """Pages whose primary rendered list starts empty with nothing to seed it.

    A generated CRUD/list page sometimes initializes its main content as
    `useState([])` and never populates it — no mock import, no inline seed
    data — so the live page renders an empty "No items found" state instead
    of a realistic demo. This isn't a compile error (an empty array is
    syntactically valid), so the build-error fix-loop never catches it —
    this is a content-realism guard, not a correctness guard. It only
    detects; the caller (pipeline.py) handles regeneration with a reinforced
    instruction rather than this module trying to synthesize fake seed data
    itself — guessing the wrong shape would trade an empty list for a new
    runtime bug.

    Signal used: a `useState([])` variable that IS `.map()`'d in render
    (drives visible content) AND the file has zero `data/mock` imports at
    all (no chance it's actually seeded from mock data under another name).
    Both conditions are required together — either alone produces false
    positives (plenty of legitimately-empty state like `selectedIds` starts
    as `useState([])` and is never meant to render a list; plenty of pages
    import mock data under names that don't obviously pair with a specific
    `.map()`'d variable).
    """
    out: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if "/pages/" not in norm or not norm.endswith((".tsx", ".ts")):
            continue
        content = read_file(workspace, rel)
        if _MOCK_IMPORT_ANY_RE.search(content):
            continue
        if _empty_seed_state_vars(content):
            out.append(rel)
    return out
