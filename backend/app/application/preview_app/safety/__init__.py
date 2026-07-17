"""Workspace safety guards for preview apps — public API only."""
from app.application.preview_app.safety.brand_contract import ensure_brand_shape
from app.application.preview_app.safety.imports import (
    normalize_ui_kit_imports,
    strip_forbidden_npm_imports,
)
from app.application.preview_app.safety.mock_data import ensure_mock_exports
from app.application.preview_app.safety.orchestrator import apply_workspace_guards
from app.application.preview_app.safety.pages import cleanup_page_shells
from app.application.preview_app.safety.runtime import ensure_runtime_correctness
from app.application.preview_app.safety.source_sanitize import (
    find_empty_seed_pages,
    find_truncated_pages,
    fix_unescaped_apostrophes,
    looks_truncated_source,
)
from app.application.preview_app.safety.ui_icons import (
    ensure_named_ui_icon_exports,
    ensure_ui_icon_coverage,
    ensure_ui_icons,
    normalize_ui_icon_imports,
)

__all__ = [
    "apply_workspace_guards",
    "cleanup_page_shells",
    "ensure_brand_shape",
    "ensure_mock_exports",
    "ensure_named_ui_icon_exports",
    "ensure_runtime_correctness",
    "ensure_ui_icon_coverage",
    "ensure_ui_icons",
    "find_empty_seed_pages",
    "find_truncated_pages",
    "fix_unescaped_apostrophes",
    "looks_truncated_source",
    "normalize_ui_icon_imports",
    "normalize_ui_kit_imports",
    "strip_forbidden_npm_imports",
]
