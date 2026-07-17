"""Chat-driven refinement of a generated preview workspace.

Split from the former monolithic ``chat_refinement.py`` into focused modules:

- ``appspec_context``: canonical AppSpec contract resolution + projections
- ``intent``: chat-message intent detection (full redesign, file ranking)
- ``workspace_patch``: apply one AI payload onto workspace files/routes
- ``chat_rebuild``: ``refine_preview_app_from_chat`` orchestration
"""
from __future__ import annotations

from app.application.preview_app.pipeline.architect_normalize import _plan_for_persistence

from .appspec_context import (
    AppSpecRefinementContext,
    _app_spec_ref_is_enforced,
    _load_app_spec_refinement_context,
    _merge_app_spec_refinement_enrichment,
)
from .chat_rebuild import refine_log, refine_preview_app_from_chat
from .intent import _FULL_REDESIGN_RE, _is_full_redesign_request, _rank_refinement_files
from .workspace_patch import (
    _apply_chat_file_updates,
    _architect_from_generated,
    _catalogue_fallback_paths,
    _merge_chat_routes,
    _request_chat_refinement_payload,
)

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
]
