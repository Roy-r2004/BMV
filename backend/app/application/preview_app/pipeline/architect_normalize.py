"""Architect normalization and plan-to-file mapping."""
from __future__ import annotations

import json
import re

from app.application.preview_app.text_utils import _bounded_json
from app.application.preview_app.protected_paths import (
    is_template_owned_path,
    safe_generated_route_path,
    safe_source_path,
)
from app.application.ui_catalogue import (
    compact_skeleton_contract,
    infer_page_contract,
    infer_section_slots,
)

def _sort_gen_order(files: list[dict]) -> list[dict]:
    """Generate foundational files first so later files can import them."""
    kind_order = {"theme": 0, "data": 1, "component": 2, "layout": 3, "page": 4, "router": 5}
    return sorted(files, key=lambda f: (kind_order.get(f.get("kind", ""), 4), f.get("path", "")))

def _prioritize_for_file_cap(files: list[dict]) -> list[dict]:
    """Keep pages first when slicing to PREVIEW_MAX_FILES so routes aren't dropped."""
    pages = [f for f in files if (f.get("kind") or "") == "page"]
    rest = [f for f in files if (f.get("kind") or "") != "page"]
    return pages + rest

def _attach_plan_sections(files: list[dict], plan: dict, architect: dict | None = None) -> list[dict]:
    """Feed each page's plan spec (sections + features) into its codegen instructions."""
    page_specs: dict[tuple[str, str], dict] = {}
    pages_by_id: dict[str, list[dict]] = {}
    path_to_page: dict[str, dict] = {}
    for role in plan.get("roles", []):
        for page in role.get("pages", []):
            pid = page.get("id", "")
            if pid:
                enriched = {**page, "role_id": role.get("id"), "role_label": role.get("label")}
                key = (str(role.get("id") or ""), str(pid))
                page_specs[key] = enriched
                pages_by_id.setdefault(str(pid), []).append(enriched)
    if architect:
        for rt in architect.get("routes") or []:
            pid = str(rt.get("page_id") or "")
            role_id = str(rt.get("role_id") or "")
            cf = (rt.get("component_file") or "").replace("\\", "/")
            if cf:
                page = page_specs.get((role_id, pid)) or {}
                if not page and len(pages_by_id.get(pid, [])) == 1:
                    page = pages_by_id[pid][0]
                path_to_page[cf.lower()] = {
                    **page,
                    **rt,
                    "role_id": rt.get("role_id") or page.get("role_id"),
                    "role_label": page.get("role_label"),
                }

    out: list[dict] = []
    for f in files:
        spec = dict(f)
        fpath = (spec.get("path") or "").replace("\\", "/").lower()
        page = path_to_page.get(fpath)
        if not page:
            for pid, matches in pages_by_id.items():
                if len(matches) != 1:
                    continue
                path = fpath.replace("-", "").replace("_", "")
                if pid and pid.replace("-", "").replace("_", "") in path:
                    page = matches[0]
                    break
        if page:
            sections = page.get("sections") or []
            sec_text = _bounded_json(sections[:20], 4000)
            inferred = infer_page_contract(page)
            skeleton_id = inferred["skeleton_id"]
            section_slots = infer_section_slots(page, skeleton_id)
            slot_briefs: dict[str, list] = {slot: [] for slot in section_slots}
            contextual_briefs: list = []
            for section in sections[:20]:
                section_name = (
                    section.get("name") or section.get("id") or section.get("title") or ""
                    if isinstance(section, dict)
                    else str(section)
                )
                normalized_name = re.sub(r"[^a-z0-9]+", "", str(section_name).lower())
                matched_slot = next(
                    (
                        slot for slot in section_slots
                        if re.sub(r"[^a-z0-9]+", "", slot.lower()) in normalized_name
                        or normalized_name in re.sub(r"[^a-z0-9]+", "", slot.lower())
                    ),
                    None,
                )
                if matched_slot:
                    slot_briefs[matched_slot].append(section)
                else:
                    contextual_briefs.append(section)
            mapped_sections_text = _bounded_json(
                {
                    "assigned_slots": [
                        {
                            "slot": slot,
                            "plan_briefs": slot_briefs[slot],
                            "required_without_legacy_name_match": not bool(slot_briefs[slot]),
                        }
                        for slot in section_slots
                    ],
                    "contextual_legacy_briefs": contextual_briefs,
                },
                4000,
            )
            skeleton_contract = compact_skeleton_contract(skeleton_id, section_slots)
            contract_text = json.dumps(
                skeleton_contract,
                ensure_ascii=False,
                separators=(", ", ": "),
            )
            app_spec_contract = page.get("app_spec_contract") or {}
            behavior_contract_text = (
                _bounded_json(app_spec_contract, 9000)
                if app_spec_contract
                else ""
            )
            spec["instructions"] = (
                f"{spec.get('instructions', '')}\n\n"
                f"Role: {page.get('role_label') or page.get('role_id', '')}\n"
                f"Page: {page.get('title')} — {page.get('purpose', '')}\n"
                "Assigned skeleton slots are authoritative: implement every assigned slot, "
                "including required skeleton slots without a direct legacy section-name match. "
                "Use the legacy plan sections as content briefs mapped into those slots; they "
                "do not restrict or remove required slots.\n"
                f"Mapped slot briefs:\n{mapped_sections_text}\n"
                f"Original legacy section briefs (context only):\n{sec_text}\n"
                f"Features to showcase: {', '.join(page.get('features_to_showcase', []))}\n"
                f"Sample data notes: {page.get('sample_data_notes', '')}\n"
                f"Skeleton/slot contract (use only these catalogue components and props):\n"
                f"{contract_text}"
                + (
                    "\nCanonical AppSpec behavior contract (preserve every state, action, "
                    "transition, evidence item, acceptance outcome, and data-appspec hook):\n"
                    f"{behavior_contract_text}"
                    if behavior_contract_text
                    else ""
                )
            )
        out.append(spec)
    return out

def _files_from_plan(architect: dict) -> list[dict]:
    """Derive only AI-owned route pages and explicit shared components."""
    files: list[dict] = []
    for route in architect.get("routes", []):
        comp = route.get("component_file")
        if comp:
            files.append({
                "path": comp,
                "kind": "page",
                "instructions": route.get("purpose", route.get("title", "")),
            })
    for comp in architect.get("shared_components") or []:
        if comp.get("path"):
            files.append({
                "path": comp["path"],
                "kind": comp.get("kind", "component"),
                "instructions": comp.get("instructions", ""),
            })
    return files

_CHROME_DEFAULTS: dict[str, tuple[str, str]] = {
    "src/components/Nav.tsx": (
        "component",
        "Public top nav bar for this brand — typography, spacing, button shape and "
        "color usage should feel specific to this business, not generic.",
    ),
    "src/layouts/PublicLayout.tsx": (
        "layout",
        "Public site shell (header + main + footer) wrapping every public page. "
        "Footer copy and structure should suit this business.",
    ),
    "src/layouts/AdminLayout.tsx": (
        "layout",
        "Admin dashboard shell (sidebar + header) wrapping every admin page. Never "
        "hardcode a business type in labels (e.g. do not assume 'Studio').",
    ),
    "src/components/UiIcons.tsx": (
        "component",
        "A small bespoke icon set (10-14 icons) matching this brand's visual style "
        "(stroke width, corner rounding), covering the icon keys pages already use.",
    ),
}

_LEGACY_CHROME_PATHS = {
    "src/components/nav.tsx",
    "src/layouts/publiclayout.tsx",
    "src/layouts/adminlayout.tsx",
    "src/components/uiicons.tsx",
}

def _normalize_architect(architect: dict, plan: dict) -> dict:
    plan_pages: dict[tuple[str, str], dict] = {}
    pages_by_id: dict[str, list[dict]] = {}
    for role in plan.get("roles") or []:
        for page in role.get("pages") or []:
            if page.get("id"):
                role_id = str(role.get("id") or "")
                page_id = str(page["id"])
                plan_pages[(role_id, page_id)] = page
                pages_by_id.setdefault(page_id, []).append(page)

    for route_index, route in enumerate(architect.get("routes") or []):
        component_file = safe_generated_route_path(
            route.get("component_file", ""),
            architect,
        )
        if not component_file:
            raw_name = str(
                route.get("page_id")
                or route.get("title")
                or f"route-{route_index + 1}"
            )
            stem = "".join(
                part[:1].upper() + part[1:]
                for part in re.findall(r"[A-Za-z0-9]+", raw_name)
            ) or f"Route{route_index + 1}"
            component_file = f"src/pages/{stem}Page.tsx"
        route["component_file"] = component_file
        page_id = str(route.get("page_id") or "")
        role_id = str(route.get("role_id") or "")
        page = plan_pages.get((role_id, page_id)) or {}
        if not page and len(pages_by_id.get(page_id, [])) == 1:
            page = pages_by_id[page_id][0]
        source = {**page, **route}
        inferred = infer_page_contract(source)
        route["surface"] = inferred["surface"]
        route["skeleton_id"] = inferred["skeleton_id"]
        route["section_slots"] = infer_section_slots(
            source,
            inferred["skeleton_id"],
        )
        from app.application.preview_app.product_face import normalize_page_intent

        route["page_intent"] = normalize_page_intent(
            page.get("page_intent") or route.get("page_intent"),
            path=str(route.get("path") or ""),
            skeleton_id=str(route.get("skeleton_id") or ""),
            surface=str(route.get("surface") or ""),
        )

    files = architect.get("files_to_generate") or []
    if not files:
        files = _files_from_plan(architect)
    safe_files: list[dict] = []
    for file_spec in files:
        safe_path = safe_source_path(file_spec.get("path", ""))
        if not safe_path or is_template_owned_path(safe_path, architect):
            continue
        safe_files.append({**file_spec, "path": safe_path})
    files = safe_files
    catalogue_routes = any(route.get("skeleton_id") for route in architect.get("routes") or [])
    if catalogue_routes:
        files = [
            file_spec
            for file_spec in files
            if (file_spec.get("path") or "").replace("\\", "/").lower()
            not in _LEGACY_CHROME_PATHS
        ]

    existing_paths = {(f.get("path") or "").lower().replace("\\", "/") for f in files}
    for comp in architect.get("shared_components") or []:
        safe_path = safe_source_path(comp.get("path", ""))
        cp = (safe_path or "").lower()
        if (
            cp
            and cp not in existing_paths
            and not is_template_owned_path(cp, architect)
            and not (catalogue_routes and cp in _LEGACY_CHROME_PATHS)
        ):
            files.append({
                "path": safe_path,
                "kind": comp.get("kind", "component"),
                "instructions": comp.get("instructions", ""),
            })
            existing_paths.add(cp)

    if not catalogue_routes:
        for path, (kind, instr) in _CHROME_DEFAULTS.items():
            norm = path.lower()
            if norm not in existing_paths and not is_template_owned_path(path, architect):
                files.append({"path": path, "kind": kind, "instructions": instr})
                existing_paths.add(norm)

    # Guarantee every route has a matching file entry — no page ever skipped
    for route in architect.get("routes", []):
        comp = route.get("component_file")
        if not comp:
            continue
        norm = comp.lower().replace("\\", "/")
        if norm not in existing_paths:
            files.append({
                "path": comp,
                "kind": "page",
                "instructions": (
                    f"{route.get('title', '')} — {route.get('purpose', '')}. "
                    f"Features visible: {', '.join(route.get('features', []))}"
                ),
            })
            existing_paths.add(norm)

    architect["files_to_generate"] = _attach_plan_sections(files, plan, architect)

    if not architect.get("roles"):
        architect["roles"] = [
            {
                "id": r.get("id"),
                "label": r.get("label"),
                "defaultPath": r.get("defaultPath", "/"),
                "icon": r.get("icon", "users"),
            }
            for r in plan.get("roles", [])
        ]
    return architect

def _plan_for_persistence(plan: dict) -> dict:
    """Remove embedded AppSpec slices; generated_pages stores provenance only."""

    persisted = json.loads(json.dumps(plan))
    for role in persisted.get("roles") or []:
        for page in role.get("pages") or []:
            page.pop("app_spec_contract", None)
    return persisted
