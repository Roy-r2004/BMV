"""Collect named imports from `data/mock` across a preview workspace.

Neutral helper — used by codegen mock synthesis and safety mock guards.
"""
from __future__ import annotations

from app.application.preview_app.patterns import _MOCK_IMPORT_RE
from app.application.preview_app.workspace import list_source_files, read_file


def collect_mock_imports(workspace) -> set[str]:
    names: set[str] = set()
    for rel in list_source_files(workspace):
        if rel.endswith("data/mock.ts"):
            continue
        for m in _MOCK_IMPORT_RE.finditer(read_file(workspace, rel)):
            for part in m.group(1).split(","):
                n = part.strip().split(" as ")[0].strip()
                if n and n != "type":
                    names.add(n)
    return names


# Back-compat for existing call sites.
_collect_mock_imports = collect_mock_imports
