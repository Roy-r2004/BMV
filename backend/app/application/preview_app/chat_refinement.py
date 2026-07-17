"""Backward-compatible shim — chat refinement now lives in ``preview_app/refinement/``.

The implementation was split into ``preview_app/refinement/`` (AppSpec context,
intent detection, workspace patching, and the main rebuild flow). This module
re-exports the public names so existing imports keep working:

- ``from app.application.preview_app.chat_refinement import <name>``
- ``from app.application.preview_app import chat_refinement``

Some tests monkeypatch individual collaborators (e.g. ``get_request``,
``run_build``) as attributes on this module. Those names are re-imported here
for attribute compatibility, but tests that need the patch to actually affect
``refine_preview_app_from_chat`` must patch the collaborator on
``app.application.preview_app.refinement.chat_rebuild`` instead, since that is
where the function's own module globals live.
"""
from __future__ import annotations

from app.application.preview_app.refinement import (
    AppSpecRefinementContext,
    _FULL_REDESIGN_RE,
    _app_spec_ref_is_enforced,
    _apply_chat_file_updates,
    _architect_from_generated,
    _catalogue_fallback_paths,
    _is_full_redesign_request,
    _load_app_spec_refinement_context,
    _merge_app_spec_refinement_enrichment,
    _merge_chat_routes,
    _plan_for_persistence,
    _rank_refinement_files,
    _request_chat_refinement_payload,
    refine_log,
    refine_preview_app_from_chat,
)

# Re-imported (not just referenced) for backward-compatible attribute access —
# some tests save/restore these as attributes of this module.
from app.application.pipelines._shared import business_info, get_request
from app.application.preview_app.build import run_build
from app.application.preview_app.safety.orchestrator import apply_workspace_guards
from app.application.preview_app.workspace import get_dist_dir, get_workspace
from app.application.services.industry_images import get_images_for_industry
from app.application.services.progress import emit as _emit
from app.core.config import settings

__all__ = [
    "AppSpecRefinementContext",
    "_FULL_REDESIGN_RE",
    "_app_spec_ref_is_enforced",
    "_apply_chat_file_updates",
    "_architect_from_generated",
    "_catalogue_fallback_paths",
    "_is_full_redesign_request",
    "_load_app_spec_refinement_context",
    "_merge_app_spec_refinement_enrichment",
    "_merge_chat_routes",
    "_plan_for_persistence",
    "_rank_refinement_files",
    "_request_chat_refinement_payload",
    "refine_log",
    "refine_preview_app_from_chat",
    "business_info",
    "get_request",
    "run_build",
    "apply_workspace_guards",
    "get_dist_dir",
    "get_workspace",
    "get_images_for_industry",
    "_emit",
    "settings",
]
