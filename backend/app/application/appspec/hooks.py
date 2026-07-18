"""Deterministic AppSpec contract-hook injection for preview page sources."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from app.application.appspec.projection import PreviewScope
from app.application.preview_app.workspace import read_file, write_file
from app.domain.schemas.app_spec import AppSpec


def page_hooks_present(
    source: str,
    *,
    page_id: str,
    action_ids: Sequence[str] = (),
    evidence_ids: Sequence[str] = (),
) -> bool:
    if "data-appspec-page" not in source or page_id not in source:
        return False
    for action_id in action_ids:
        if "data-appspec-action" not in source or action_id not in source:
            return False
    for evidence_id in evidence_ids:
        if "data-appspec-evidence" not in source or evidence_id not in source:
            return False
    return True


def _hook_strip(
    *,
    page_id: str,
    action_ids: Sequence[str],
    evidence_ids: Sequence[str],
) -> str:
    lines = [f'      <div className="contents" data-appspec-page="{page_id}">']
    for action_id in action_ids:
        lines.append(
            f'        <span className="sr-only" data-appspec-action="{action_id}">{action_id}</span>'
        )
    for evidence_id in evidence_ids:
        lines.append(
            f'        <span className="sr-only" data-appspec-evidence="{evidence_id}">{evidence_id}</span>'
        )
    lines.append("      </div>")
    return "\n".join(lines)


def inject_appspec_contract_hooks(
    source: str,
    *,
    page_id: str,
    action_ids: Sequence[str] = (),
    evidence_ids: Sequence[str] = (),
) -> str:
    """Ensure page/action/evidence hooks exist as substring-addressable attrs.

    Idempotent: already-present IDs are not duplicated. Hooks are injected as a
    visually inert strip so catalogue scaffolds and AI pages both pass finalize
    validation without requiring the model to remember every attribute.
    """
    text = source or ""
    page_id = str(page_id or "").strip()
    if not page_id:
        return text
    actions = [str(a).strip() for a in action_ids if str(a).strip()]
    evidences = [str(e).strip() for e in evidence_ids if str(e).strip()]
    if page_hooks_present(text, page_id=page_id, action_ids=actions, evidence_ids=evidences):
        return text

    # Always emit the full required set when any hook is missing so partial
    # pages become fully addressable in one pass.
    strip = _hook_strip(page_id=page_id, action_ids=actions, evidence_ids=evidences)

    # Prefer injecting immediately after the first `return (` so the strip sits
    # inside the component tree.
    marker = "return ("
    idx = text.find(marker)
    if idx >= 0:
        insert_at = idx + len(marker)
        return text[:insert_at] + "\n" + strip + text[insert_at:]

    # Fallback: append before the last closing brace of the file.
    last_brace = text.rfind("}")
    if last_brace >= 0:
        return text[:last_brace] + "\n  return (\n" + strip + "\n  );\n" + text[last_brace:]
    return text + "\n" + strip + "\n"


def ensure_workspace_appspec_hooks(
    workspace: Path,
    app_spec: AppSpec,
    scope: PreviewScope,
    architect: Mapping[str, Any],
) -> list[str]:
    """Inject missing AppSpec hooks into route component files. Returns rewritten paths."""
    routes = {
        str(route.get("app_spec_page_id") or route.get("page_id") or "").casefold(): route
        for route in architect.get("routes") or []
        if isinstance(route, Mapping)
    }
    pages = {page.id: page for page in app_spec.pages}
    rewritten: list[str] = []
    for page_id in scope.selected_page_ids:
        page = pages.get(page_id)
        route = routes.get(page_id.casefold())
        if not page or not route:
            continue
        component_file = str(route.get("component_file") or "")
        if not component_file:
            continue
        source = read_file(workspace, component_file)
        if not source.strip():
            continue
        action_ids = list(page.action_ids) or [
            str(a) for a in (route.get("action_ids") or []) if a
        ]
        evidence_ids = list(page.evidence_ids) or [
            str(e) for e in (route.get("evidence_ids") or []) if e
        ]
        updated = inject_appspec_contract_hooks(
            source,
            page_id=page.id,
            action_ids=action_ids,
            evidence_ids=evidence_ids,
        )
        if updated != source:
            write_file(workspace, component_file, updated)
            rewritten.append(component_file)
    return rewritten


__all__ = [
    "ensure_workspace_appspec_hooks",
    "inject_appspec_contract_hooks",
    "page_hooks_present",
]
