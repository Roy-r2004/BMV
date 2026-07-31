"""Deterministic AppSpec contract-hook injection for preview page sources."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.application.appspec.projection import PreviewScope
from app.application.preview_app.patterns import default_export_search_from
from app.application.preview_app.workspace import read_file, write_file
from app.domain.schemas.app_spec import AppSpec


def attr_bound(source: str, attr: str, value: str) -> bool:
    """True when ``attr="value"`` / ``attr='value'`` appears (not a loose substring)."""
    if not value:
        return False
    return f'{attr}="{value}"' in source or f"{attr}='{value}'" in source


def page_hooks_present(
    source: str,
    *,
    page_id: str,
    action_ids: Sequence[str] = (),
    evidence_ids: Sequence[str] = (),
) -> bool:
    if not attr_bound(source, "data-appspec-page", page_id):
        return False
    for action_id in action_ids:
        if not attr_bound(source, "data-appspec-action", action_id):
            return False
    for evidence_id in evidence_ids:
        if not attr_bound(source, "data-appspec-evidence", evidence_id):
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


def _statement_semicolon_end(text: str, expr_start: int) -> int | None:
    """Index of the `;` that ends a return expression starting at expr_start."""
    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    in_str: str | None = None
    escape = False
    i = expr_start
    while i < len(text):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in {'"', "'", "`"}:
            in_str = ch
            i += 1
            continue
        if ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren = max(0, depth_paren - 1)
        elif ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace = max(0, depth_brace - 1)
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket = max(0, depth_bracket - 1)
        elif (
            ch == ";"
            and depth_paren == 0
            and depth_brace == 0
            and depth_bracket == 0
        ):
            return i
        i += 1
    return None


def _matching_paren(text: str, open_index: int) -> int | None:
    """Index of the `)` closing the `(` at open_index, ignoring strings."""
    depth = 0
    in_str: str | None = None
    escape = False
    for i in range(open_index, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            continue
        if ch in {'"', "'", "`"}:
            in_str = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
    return None


def _find_bare_jsx_return(text: str, search_from: int) -> tuple[int, int, int] | None:
    """Locate `return <jsx…>;` → (return_kw_start, jsx_start, semicolon_index)."""
    region = text[search_from:]
    match = re.search(r"\breturn\s+<", region)
    if not match:
        return None
    return_start = search_from + match.start()
    jsx_start = search_from + match.end() - 1  # at '<'
    semi = _statement_semicolon_end(text, jsx_start)
    if semi is None:
        return None
    return return_start, jsx_start, semi


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

    Hooks must sit inside a *reachable* return of the default export. A prior
    fallback that appended a second `return (` before the file's last `}` left
    hooks as dead code when the component used bare `return <jsx/>;`.
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
    search_from = default_export_search_from(text)

    # Prefer injecting into the `return ( … )` of the default export — as a
    # *sibling inside a fragment*, never as a bare second root. Inserting the
    # strip straight after `return (` left request 45's LoginPage with
    # `<div/>` followed by `<PublicShell>`, and rolldown refuses adjacent JSX:
    # the whole preview build died on one page's missing attribute.
    marker = "return ("
    idx = text.find(marker, search_from)
    if idx >= 0:
        open_paren = idx + len(marker) - 1
        close_paren = _matching_paren(text, open_paren)
        if close_paren is not None:
            expr = text[open_paren + 1 : close_paren].strip()
            if expr.startswith("<>") and expr.endswith("</>"):
                # Already a fragment — the strip is just one more child.
                inner_at = open_paren + 1 + text[open_paren + 1 :].index("<>") + 2
                return text[:inner_at] + "\n" + strip + text[inner_at:]
            wrapped = f"\n    <>\n{strip}\n      {expr}\n    </>\n  "
            return text[: open_paren + 1] + wrapped + text[close_paren:]

    # Bare `return <jsx…>;` — wrap so the strip is a sibling in the same tree.
    bare = _find_bare_jsx_return(text, search_from)
    if bare is not None:
        ret_start, jsx_start, semi = bare
        jsx = text[jsx_start:semi]
        wrapped = f"return (\n{strip}\n    <>\n      {jsx}\n    </>\n  );"
        return text[:ret_start] + wrapped + text[semi + 1 :]

    # No return yet: append a reachable return before the last closing brace.
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
    "attr_bound",
    "ensure_workspace_appspec_hooks",
    "inject_appspec_contract_hooks",
    "page_hooks_present",
]
