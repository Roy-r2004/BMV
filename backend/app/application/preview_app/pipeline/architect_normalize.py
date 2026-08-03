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
    infer_page_contract,
    infer_section_slots,
    skeleton_contract_for_prompt,
)
from app.infrastructure.logging import get_logger

route_log = get_logger("RouteTable")

_PARAM_SEGMENT_RE = re.compile(r"^:[A-Za-z_][A-Za-z0-9_]*$")
_BRACED_PARAM_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

# Paths that must survive normalization whatever the signature says.
_PINNED_PATHS = frozenset({"/", "/ai-features"})

# Synonym vocabularies for one public concept. Two single-segment public routes
# whose tokens live in the same tuple describe the same face; the earliest token
# present in the table becomes the canonical path.
_CONCEPT_SYNONYMS: tuple[tuple[str, ...], ...] = (
    (
        "gallery",
        "collection",
        "collections",
        "works",
        "work",
        "portfolio",
        "pieces",
        "artworks",
        "catalog",
        "catalogue",
    ),
    ("shop", "store", "products", "menu"),
    ("services", "service", "treatments", "offerings", "packages"),
    ("team", "doctors", "providers", "practitioners", "staff", "people"),
    ("about", "about-us", "story", "our-story"),
    ("contact", "contact-us", "enquire", "inquire"),
    ("classes", "workshops", "sessions", "schedule"),
    ("blog", "journal", "news", "press"),
)

_CONCEPT_RANK: dict[str, tuple[int, int]] = {
    token: (group_index, token_index)
    for group_index, group in enumerate(_CONCEPT_SYNONYMS)
    for token_index, token in enumerate(group)
}


def _canonical_route_path(path: str) -> str:
    """`{id}` → `:id`, and drop dynamic segments React Router cannot bind.

    A param name repeated inside one path silently loses its first binding, and
    a dynamic segment directly after another one is a detail-of-detail route the
    generator never produces a page for.
    """
    raw = _BRACED_PARAM_RE.sub(r":\1", str(path or "").strip())
    kept: list[str] = []
    seen_params: set[str] = set()
    for segment in (s for s in raw.split("/") if s):
        if not _PARAM_SEGMENT_RE.match(segment):
            kept.append(segment)
            continue
        name = segment[1:]
        if name in seen_params or (kept and _PARAM_SEGMENT_RE.match(kept[-1])):
            continue
        seen_params.add(name)
        kept.append(segment)
    return "/" + "/".join(kept) if kept else "/"


def _path_shape(path: str) -> str:
    """Path with every param name replaced — two shapes that match are ambiguous."""
    return "/".join(
        "*" if _PARAM_SEGMENT_RE.match(segment) else segment
        for segment in path.split("/")
    )


def _concept_token(path: str) -> str | None:
    """Canonical concept for a single-segment public path, else None."""
    segments = [s for s in path.split("/") if s]
    if len(segments) != 1 or _PARAM_SEGMENT_RE.match(segments[0]):
        return None
    token = segments[0].lower()
    rank = _CONCEPT_RANK.get(token)
    return _CONCEPT_SYNONYMS[rank[0]][0] if rank else None


def _route_signature(route: dict) -> tuple:
    """What a route renders — same signature means the same page twice."""
    return (
        str(route.get("surface") or ""),
        str(route.get("skeleton_id") or ""),
        str(route.get("page_intent") or ""),
        tuple(str(slot) for slot in route.get("section_slots") or ()),
        str(
            route.get("data_source")
            or route.get("collection")
            or route.get("entity")
            or ""
        ).lower(),
    )


def _rewrite_path_prefix(path: str, old_base: str, new_base: str) -> str:
    if path == old_base:
        return new_base
    if path.startswith(f"{old_base}/"):
        return new_base + path[len(old_base) :]
    return path


def _dominant_param_name(paths: list[str]) -> str:
    counts: dict[str, int] = {}
    for path in paths:
        for segment in path.split("/"):
            if _PARAM_SEGMENT_RE.match(segment):
                counts[segment[1:]] = counts.get(segment[1:], 0) + 1
    if not counts:
        return "id"
    return max(sorted(counts), key=lambda name: counts[name])


def _collapse_synonym_concepts(routes: list[dict]) -> dict[str, str]:
    """Map synonym concept bases onto one canonical base (`/works` → `/gallery`)."""
    groups: dict[tuple, list[tuple[int, str]]] = {}
    for index, route in enumerate(routes):
        path = str(route.get("path") or "")
        concept = _concept_token(path)
        if not concept:
            continue
        groups.setdefault((concept, *_route_signature(route)), []).append((index, path))
    rebase: dict[str, str] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        winner = min(
            members,
            key=lambda m: (_CONCEPT_RANK[m[1].strip("/").lower()], m[0]),
        )[1]
        for _, path in members:
            if path != winner:
                rebase[path] = winner
    return rebase


def _shadowed_dynamic_paths(routes: list[dict]) -> set[str]:
    """Trailing-param routes that duplicate a page already reachable literally."""
    paths = [str(route.get("path") or "") for route in routes]
    literal_children: dict[str, int] = {}
    for path in paths:
        segments = [s for s in path.split("/") if s]
        if not segments or _PARAM_SEGMENT_RE.match(segments[-1]):
            continue
        parent = "/" + "/".join(segments[:-1])
        literal_children[parent] = literal_children.get(parent, 0) + 1
    component_use: dict[str, int] = {}
    for route in routes:
        component = str(route.get("component_file") or "").lower()
        if component:
            component_use[component] = component_use.get(component, 0) + 1
    shadowed: set[str] = set()
    for route, path in zip(routes, paths):
        segments = [s for s in path.split("/") if s]
        if len(segments) != 2 or not _PARAM_SEGMENT_RE.match(segments[-1]):
            continue
        parent = f"/{segments[0]}"
        component = str(route.get("component_file") or "").lower()
        if literal_children.get(parent, 0) and component_use.get(component, 0) > 1:
            shadowed.add(path)
    return shadowed


def _resolve_remap_chains(remap: dict[str, str], live_paths: set[str]) -> dict[str, str]:
    """Follow `a→b→c` so no removed path is redirected at another removed path."""
    resolved: dict[str, str] = {}
    for old in remap:
        target = old
        for _ in range(len(remap) + 1):
            if target in live_paths:
                break
            nxt = remap.get(target)
            if nxt is None or nxt == target:
                break
            target = nxt
        resolved[old] = target if target in live_paths else "/"
    return {old: new for old, new in resolved.items() if old != new}


def _normalize_route_table(architect: dict) -> dict[str, str]:
    """Collapse duplicate/malformed routes in place; return the old→new path map.

    Runs after the per-route enrichment loop because the dedup signature needs
    `surface`/`skeleton_id`/`page_intent`.
    """
    routes = architect.get("routes") or []
    if len(routes) < 2:
        return {}
    remap: dict[str, str] = {}
    for route in routes:
        original = str(route.get("path") or "")
        canonical = _canonical_route_path(original)
        if canonical != original:
            remap[original] = canonical
        route["path"] = canonical

    for old_base, new_base in _collapse_synonym_concepts(routes).items():
        for route in routes:
            rewritten = _rewrite_path_prefix(str(route["path"]), old_base, new_base)
            if rewritten != route["path"]:
                remap[str(route["path"])] = rewritten
                route["path"] = rewritten

    dominant = _dominant_param_name([str(r["path"]) for r in routes])
    component_use: dict[str, int] = {}
    for route in routes:
        component = str(route.get("component_file") or "").lower()
        if component:
            component_use[component] = component_use.get(component, 0) + 1
    by_shape: dict[str, list[tuple[int, dict]]] = {}
    for index, route in enumerate(routes):
        by_shape.setdefault(_path_shape(str(route["path"])), []).append((index, route))
    kept: list[dict] = []
    for shape_members in by_shape.values():
        winner_index, winner = min(
            shape_members,
            key=lambda m: (
                component_use.get(str(m[1].get("component_file") or "").lower(), 0),
                0 if f":{dominant}" in str(m[1]["path"]) else 1,
                m[0],
            ),
        )
        for index, route in shape_members:
            if index != winner_index:
                remap[str(route["path"])] = str(winner["path"])
        kept.append(winner)

    shadowed = _shadowed_dynamic_paths(kept)
    survivors = [
        route
        for route in kept
        if str(route["path"]) in _PINNED_PATHS or str(route["path"]) not in shadowed
    ]
    if not survivors:
        survivors = kept
    # Literals declared before params so no dynamic segment can shadow a sibling.
    survivors.sort(
        key=lambda route: sum(
            1
            for segment in str(route["path"]).split("/")
            if _PARAM_SEGMENT_RE.match(segment)
        )
    )
    kept_paths = {str(route["path"]) for route in survivors}
    component_home = {
        str(route.get("component_file") or "").lower(): str(route["path"])
        for route in survivors
    }
    for route in kept:
        path = str(route["path"])
        if path in kept_paths:
            continue
        parent = "/" + "/".join([s for s in path.split("/") if s][:-1])
        remap[path] = (
            component_home.get(str(route.get("component_file") or "").lower())
            or (parent if parent in kept_paths else "/")
        )
    architect["routes"] = survivors
    remap = _resolve_remap_chains(remap, kept_paths)
    if remap:
        route_log.info(
            "route table normalized: %s → %s routes (%s)",
            len(routes),
            len(survivors),
            ", ".join(f"{old}→{new}" for old, new in sorted(remap.items())),
        )
    return remap


def _remap_role_default_paths(architect: dict, remap: dict[str, str]) -> None:
    """No role may open on a path the route table no longer declares."""
    if not remap:
        return
    paths = {str(route.get("path") or "") for route in architect.get("routes") or []}
    for role in architect.get("roles") or []:
        default = str(role.get("defaultPath") or "")
        if not default or default in paths:
            continue
        target = remap.get(default) or _canonical_route_path(default)
        role["defaultPath"] = target if target in paths else "/"


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
            # Compact separators, like every other prompt site: the spaced
            # form this used to emit cost ~350-420 chars a file that the
            # budget in `skeleton_contract_for_prompt` never counted, and
            # nothing bounded the result at all.
            skeleton_contract = skeleton_contract_for_prompt(skeleton_id, section_slots)
            contract_text = json.dumps(
                skeleton_contract,
                ensure_ascii=False,
                separators=(",", ":"),
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

    try:
        route_remap = _normalize_route_table(architect)
    except Exception as exc:
        route_log.warning("route table normalization skipped: %s", exc)
        route_remap = {}

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
    _remap_role_default_paths(architect, route_remap)
    return architect

def _plan_for_persistence(plan: dict) -> dict:
    """Remove embedded AppSpec slices; generated_pages stores provenance only."""

    persisted = json.loads(json.dumps(plan))
    for role in persisted.get("roles") or []:
        for page in role.get("pages") or []:
            page.pop("app_spec_contract", None)
    return persisted
