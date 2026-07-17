"""Deterministic workspace repairs used after AI fix-agent attempts.

Lives outside ``codegen`` so the fix agent does not import the ``safety`` package.
"""
from __future__ import annotations

from pathlib import Path

from app.application.preview_app.fallback import scan_and_repair_double_brace_literals
from app.application.preview_app.protected_paths import (
    has_catalogue_routes,
    is_template_owned_path,
    restore_template_owned_files,
    snapshot_template_owned_files,
)
from app.application.preview_app.safety.imports import strip_forbidden_npm_imports
from app.application.preview_app.safety.ui_icons import (
    ensure_named_ui_icon_exports,
    ensure_ui_icon_coverage,
    ensure_ui_icons,
    normalize_ui_icon_imports,
)
from app.infrastructure.logging import get_logger

log = get_logger("BuildRepairs")


def run_deterministic_local_repairs(workspace: Path, architect: dict) -> list[str]:
    repaired: list[str] = []
    protected_snapshot = snapshot_template_owned_files(workspace, architect)
    try:
        try:
            repaired.extend(
                scan_and_repair_double_brace_literals(
                    workspace,
                    architect=architect,
                )
            )
        except ValueError as e:
            log.warning("double-brace deterministic repair failed: %s", e)
        try:
            repaired.extend(strip_forbidden_npm_imports(workspace))
        except Exception as e:
            log.warning("npm-import deterministic repair failed: %s", e)
        if not has_catalogue_routes(architect):
            try:
                if ensure_ui_icons(workspace):
                    repaired.append("src/components/UiIcons.tsx")
                repaired.extend(normalize_ui_icon_imports(workspace))
                repaired.extend(ensure_named_ui_icon_exports(workspace))
                repaired.extend(ensure_ui_icon_coverage(workspace))
            except Exception as e:
                log.warning("icon deterministic repair failed: %s", e)
    finally:
        restore_template_owned_files(workspace, architect, protected_snapshot)
    return list(
        dict.fromkeys(
            path
            for path in repaired
            if not is_template_owned_path(path, architect)
        )
    )
