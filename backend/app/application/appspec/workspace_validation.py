"""Deterministic source-level checks for an AppSpec-driven preview workspace."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from app.application.appspec.hooks import attr_bound
from app.application.appspec.projection import PreviewScope
from app.application.preview_app.workspace import read_file
from app.domain.schemas.app_spec import AppSpec


def validate_app_spec_workspace(
    workspace: Path,
    app_spec: AppSpec,
    scope: PreviewScope,
    architect: Mapping[str, Any],
) -> list[str]:
    """Return missing canonical page/action/evidence instrumentation.

    These hooks do not prove the interaction by themselves; they make every
    declared contract target addressable by the later browser journey gate and
    prevent an apparently polished page from silently dropping an action.
    """

    routes = {
        str(route.get("app_spec_page_id") or route.get("page_id") or "").casefold(): route
        for route in architect.get("routes") or []
        if isinstance(route, Mapping)
    }
    pages = {page.id: page for page in app_spec.pages}
    issues: list[str] = []
    for page_id in scope.selected_page_ids:
        page = pages[page_id]
        route = routes.get(page_id.casefold())
        if not route:
            issues.append(f"{page_id}: canonical route is missing")
            continue
        component_file = str(route.get("component_file") or "")
        if not component_file:
            issues.append(f"{page_id}: component_file is missing")
            continue
        source = read_file(workspace, component_file)
        if not source.strip():
            issues.append(f"{page_id}: component source is empty")
            continue
        # Require attribute bindings (attr="id"), not a loose id substring that
        # can appear in copy/comments while the hook itself is missing.
        if not attr_bound(source, "data-appspec-page", page_id):
            issues.append(f"{page_id}: data-appspec-page hook is missing")
        for action_id in page.action_ids:
            if not attr_bound(source, "data-appspec-action", action_id):
                issues.append(f"{page_id}: action hook {action_id} is missing")
        for evidence_id in page.evidence_ids:
            if not attr_bound(source, "data-appspec-evidence", evidence_id):
                issues.append(f"{page_id}: evidence hook {evidence_id} is missing")
    return issues


__all__ = ["validate_app_spec_workspace"]
