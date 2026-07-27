"""Deterministic assembly of routing + theme for generated preview apps."""
from __future__ import annotations

import json
import re

from app.domain.interfaces.template_renderer import TemplateRenderer
from app.application.ui_catalogue import (
    compact_skeleton_contract,
    infer_page_contract,
    infer_section_slots,
)
from app.application.preview_app.text_utils import _bounded_json
from app.application.preview_app.workspace import list_source_files, read_file, write_file
from app.application.preview_app.theme import sanitize_theme_inputs
from app.application.preview_app.protected_paths import safe_generated_route_path


def _ident(stem: str) -> str:
    """Build a React component identifier (must be PascalCase for JSX)."""
    s = re.sub(r"[^0-9A-Za-z_]", "", stem)
    if not s or s[0].isdigit():
        s = "Page" + s
    # Lowercase-first names (e.g. src_pages_admin_DropsPage_tsx) render as
    # unknown HTML tags in JSX and produce blank routes.
    if s[0].islower():
        s = s[0].upper() + s[1:]
    return s


def _collision_component_name(rel: str, stem: str) -> str:
    """Prefer AdminDropsPage over path-slug aliases when stems collide."""
    parts = rel.replace("\\", "/").split("/")
    parent = parts[-2] if len(parts) >= 2 else ""
    if parent and parent.lower() not in {"pages", "src", "."}:
        return _ident(f"{parent}_{stem}")
    return _ident(f"Alt_{stem}")


def _stem(rel: str) -> str:
    return rel.split("/")[-1].rsplit(".", 1)[0].lower()


def _pages_catalog(workspace) -> list[str]:
    return sorted(
        rel.replace("\\", "/")
        for rel in list_source_files(workspace)
        if "/pages/" in rel.replace("\\", "/") and rel.endswith((".tsx", ".jsx"))
    )


def architect_from_stored(generated_pages: dict, plan: dict | None = None) -> dict:
    """Rebuild architect dict from persisted preview_app metadata (no LLM call)."""
    pa = generated_pages.get("preview_app") or {}
    stored_routes = pa.get("routes") or []
    roles = pa.get("roles") or []
    plan_pages: dict[tuple[str, str], dict] = {}
    pages_by_id: dict[str, list[dict]] = {}
    for role in (plan or {}).get("roles", []):
        for page in role.get("pages", []):
            if not page.get("id"):
                continue
            role_id = str(role.get("id") or "")
            page_id = str(page["id"])
            enriched = {**page, "role_id": role_id, "role_label": role.get("label")}
            plan_pages[(role_id, page_id)] = enriched
            pages_by_id.setdefault(page_id, []).append(enriched)
    routes: list[dict] = []
    files: list[dict] = []
    for stored_route in stored_routes:
        rt = dict(stored_route)
        raw_component_file = rt.get("component_file")
        if raw_component_file:
            safe_component_file = safe_generated_route_path(
                raw_component_file,
                {"routes": stored_routes},
            )
            if safe_component_file:
                rt["component_file"] = safe_component_file
            else:
                rt.pop("component_file", None)
        page_id = str(rt.get("page_id") or "")
        role_id = str(rt.get("role_id") or "")
        page = plan_pages.get((role_id, page_id)) or {}
        if not page and len(pages_by_id.get(page_id, [])) == 1:
            page = pages_by_id[page_id][0]
        is_catalogue_route = bool(rt.get("skeleton_id"))
        if is_catalogue_route:
            inferred = infer_page_contract({**page, **rt})
            rt["surface"] = rt.get("surface") or inferred["surface"]
            rt["section_slots"] = infer_section_slots(
                {**page, **rt},
                rt["skeleton_id"],
            )
        routes.append(rt)
        cf = rt.get("component_file")
        if not cf:
            continue
        sections = page.get("sections") or []
        instruction_payload = {
            "title": rt.get("title") or page.get("title") or "",
            "purpose": rt.get("purpose") or page.get("purpose") or "",
            "role_id": rt.get("role_id") or page.get("role_id") or "",
            "sections": sections[:10],
        }
        if is_catalogue_route:
            slots = rt["section_slots"]
            instruction_payload["catalogue_contract"] = compact_skeleton_contract(
                rt["skeleton_id"],
                slots,
            )
        files.append({
            "path": cf,
            "kind": "page",
            "instructions": _bounded_json(instruction_payload, 8000),
        })
    return {
        "routes": routes,
        "roles": roles,
        "design_direction": pa.get("design_direction") or "",
        "files_to_generate": files,
    }


def _layout_for(route: dict) -> str:
    if route.get("layout") == "admin":
        return "admin"
    if route.get("layout") == "public":
        return "public"
    path = route.get("path") or ""
    if path.startswith("/admin") or "/admin/" in path:
        return "admin"
    if path.startswith("/owner") or "/owner/" in path:
        return "admin"
    return "public"


def _route_owns_shell(route: dict) -> bool:
    """Catalogue pages and the AI hub own their shell (no Public/AdminLayout wrap)."""
    if route.get("owns_shell"):
        return True
    if route.get("skeleton_id"):
        return True
    page_type = str(route.get("page_type") or "").casefold()
    path = str(route.get("path") or "").rstrip("/").lower()
    component = str(route.get("component_file") or "").replace("\\", "/").lower()
    return (
        page_type == "ai_hub"
        or path == "/ai-features"
        or component.endswith("aifeaturespage.tsx")
    )


def _pin_ai_features_nav(items: list[dict], routes: list[dict]) -> list[dict]:
    """Ensure /ai-features appears in ops sidebars, not only public chrome."""
    if any(str(it.get("path") or "") == "/ai-features" for it in items):
        return items
    has_hub = any(
        isinstance(rt, dict)
        and (
            str(rt.get("path") or "") == "/ai-features"
            or str(rt.get("page_type") or "").casefold() == "ai_hub"
            or str(rt.get("component_file") or "")
            .replace("\\", "/")
            .endswith("AiFeaturesPage.tsx")
        )
        for rt in routes
    )
    if not has_hub:
        return items
    hub = {
        "id": "ai-features",
        "path": "/ai-features",
        "href": "/ai-features",
        "label": "AI features",
    }
    if not items:
        return [hub]
    # Keep Desk/home first when present.
    insert_at = 1 if str(items[0].get("path") or "") in {"/", "/home", "/desk"} else 0
    return items[:insert_at] + [hub] + items[insert_at:]


def _score_page_for_route(rel: str, route: dict) -> int:
    path = (route.get("path") or "").lower()
    role_id = (route.get("role_id") or "").lower()
    page_id = (route.get("page_id") or "").lower().replace("-", "")
    title = (route.get("title") or "").lower()
    cf = (route.get("component_file") or "").replace("\\", "/").lower()
    norm = rel.replace("\\", "/").lower()
    stem = _stem(rel)
    score = 0

    if cf and norm == cf:
        score += 2000
    elif cf and norm.endswith("/" + cf.split("/")[-1]):
        score += 1500

    if page_id and page_id in stem.replace("page", ""):
        score += 400
    for word in re.findall(r"[a-z]{4,}", title):
        if word in stem:
            score += 80

    for part in [p for p in path.split("/") if p]:
        if part in stem or part.rstrip("s") in stem:
            score += 120
        if part in norm:
            score += 40

    if role_id == "admin" and "/admin/" in norm:
        score += 200
    if role_id == "owner" and "/owner/" in norm:
        score += 200
    if role_id == "public" and "/admin/" not in norm and "/owner/" not in norm:
        score += 100

    if "admin" in path and "admindashboard" in stem:
        score += 300
    if "admin" in path and stem in ("dashboardpage", "dashboard"):
        score -= 500
    if "owner" in path and stem == "dashboardpage" and "/owner/" not in norm:
        score -= 100
    if "inventory" in path and "inventory" in stem:
        score += 400
    if "pipeline" in path or "leads" in path:
        if "pipeline" in stem or "leads" in stem:
            score += 400
    if "assistant" in path and "assistant" in stem:
        score += 400
    if "workflow" in path and "workflow" in stem:
        score += 400
    if "features" in path and "features" in stem:
        score += 400
    if "about" in path and "about" in stem:
        score += 400
    if "demo" in path and "demo" in stem:
        score += 400

    return score


def _resolve_page(
    workspace,
    route: dict,
    catalog: list[str],
    used_files: set[str],
) -> str | None:
    cf = (route.get("component_file") or "").replace("\\", "/")
    if cf and read_file(workspace, cf).strip():
        return cf if cf not in used_files else None

    ranked = sorted(
        (( _score_page_for_route(rel, route), rel) for rel in catalog if rel not in used_files),
        reverse=True,
    )
    if ranked and ranked[0][0] >= 200:
        return ranked[0][1]
    return None


def find_missing_route_pages(workspace, architect: dict) -> list[dict]:
    """Routes whose component_file is missing or empty on disk."""
    missing: list[dict] = []
    for rt in architect.get("routes") or []:
        cf = (rt.get("component_file") or "").replace("\\", "/")
        if not cf:
            # Still need a file — invent a path from route title/path so codegen can fill it.
            title = (rt.get("title") or rt.get("path") or "Page").strip()
            stem = re.sub(r"[^A-Za-z0-9]+", "", title) or "Page"
            if not stem.endswith("Page"):
                stem = f"{stem}Page"
            role = (rt.get("role_id") or "").lower()
            folder = "src/pages/admin" if role in ("owner", "admin", "staff", "manager") else "src/pages"
            cf = f"{folder}/{stem}.tsx"
            rt["component_file"] = cf
        if not read_file(workspace, cf).strip():
            missing.append({
                "path": cf,
                "kind": "page",
                "instructions": (
                    f"{rt.get('title', '')} — {rt.get('purpose', '')}. "
                    f"Role: {rt.get('role_id', '')}. "
                    f"Features: {', '.join(rt.get('features') or [])}. "
                    "This page MUST look completely different from other roles — unique layout and data."
                ),
                "_route": rt,
            })
    return missing


def find_unresolved_routes(workspace, architect: dict) -> list[dict]:
    """Routes that would be dropped from App.tsx because no page file resolves."""
    catalog = _pages_catalog(workspace)
    used: set[str] = set()
    unresolved: list[dict] = []
    for rt in architect.get("routes") or []:
        if not rt.get("path"):
            continue
        rel = _resolve_page(workspace, rt, catalog, used)
        if not rel:
            unresolved.append(rt)
        else:
            used.add(rel)
    return unresolved


def _nav_label(route: dict) -> str:
    """Short chrome label — never dump full page titles into sidebar/nav."""
    path = str(route.get("path") or "")
    title = str(route.get("title") or "").strip()
    title = re.sub(r"^(Manage|Welcome to|My Forge Flow)\s+", "", title, flags=re.I).strip()
    if title and len(title) <= 24 and ":" not in path:
        return title
    seg = [p for p in path.split("/") if p and not p.startswith(":")]
    if not seg:
        return "Home"
    token = seg[-1].replace("-", " ").replace("_", " ")
    return token.title()


def _nav_items_for(routes: list[dict], predicate) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for rt in routes:
        path = rt.get("path")
        if not path or not predicate(rt):
            continue
        if ":" in path or "{" in path:
            continue
        # Keep transactional booking steps out of persistent chrome.
        if re.match(
            r"^/(book|booking|payment|confirmation|checkout|cart|login|register|signup)\b",
            path,
            re.I,
        ):
            continue
        segments = [s for s in path.strip("/").split("/") if s]
        # Public chrome: listings + hubs only — not /classes/intro-to-wheel clutter.
        if (
            len(segments) >= 2
            and not path.startswith(("/admin", "/owner", "/member", "/ops"))
            and segments[0]
            in {
                "classes",
                "services",
                "products",
                "treatments",
                "stylists",
                "workshops",
                "schedule",
                "sessions",
            }
        ):
            continue
        if path in seen:
            continue
        seen.add(path)
        label = _nav_label(rt)
        if path == "/ai-features":
            label = "AI features"
        items.append({
            "id": path.strip("/").replace("/", "-") or "home",
            "path": path,
            "href": path,
            "label": label,
        })
    # Pin the AI hub near the top of public chrome so it's never buried.
    ai_idx = next((i for i, it in enumerate(items) if it.get("path") == "/ai-features"), -1)
    if ai_idx > 1:
        items.insert(1, items.pop(ai_idx))
    # Cap public chrome so generated detail sprawl never overwhelms the demo.
    if items and all(not str(it.get("path") or "").startswith(("/admin", "/owner")) for it in items):
        priority = ("/", "/home", "/ai-features", "/classes", "/services", "/schedule", "/ai-advisor", "/contact")
        ranked = sorted(
            items,
            key=lambda it: (
                priority.index(it["path"]) if it.get("path") in priority else 50,
                str(it.get("label") or ""),
            ),
        )
        items = ranked[:7]
    return items


def sync_mock_roles_navigation(workspace, architect: dict) -> bool:
    mock_path = "src/data/mock.ts"
    mock = read_file(workspace, mock_path)
    if not mock.strip():
        return False

    routes = architect.get("routes") or []
    roles_src = architect.get("roles") or []

    roles_data = []
    for ar in roles_src:
        rid = ar.get("id")
        if not rid:
            continue
        default = ar.get("defaultPath")
        if not default:
            for rt in routes:
                if rt.get("role_id") == rid and rt.get("path"):
                    default = rt["path"]
                    break
        roles_data.append({
            "id": rid,
            "label": ar.get("label") or rid,
            "defaultPath": default or "/",
            "icon": ar.get("icon") or "users",
        })

    public_nav = _nav_items_for(routes, lambda rt: _layout_for(rt) == "public")
    admin_nav = _pin_ai_features_nav(
        _nav_items_for(
            routes,
            lambda rt: _layout_for(rt) == "admin"
            or str(rt.get("surface") or "").lower() == "ops"
            or str(rt.get("skeleton_id") or "").startswith("ops"),
        ),
        routes,
    )
    # Ops-first previews: also surface AI hub in public nav for deep links.
    public_nav = _pin_ai_features_nav(public_nav, routes)
    navigation_data = {"public": public_nav, "admin": admin_nav}
    for role in roles_src:
        role_id = role.get("id")
        if not role_id:
            continue
        role_nav = _pin_ai_features_nav(
            _nav_items_for(
                routes,
                lambda rt, rid=role_id: rt.get("role_id") == rid,
            ),
            routes,
        )
        # Ops products often stamp one role_id on every route. Role switchers
        # still need a full sidebar — fall back to admin chrome so pages open.
        if len(role_nav) < 2 and admin_nav:
            role_nav = list(admin_nav)
        navigation_data[role_id] = role_nav

    roles_json = json.dumps(roles_data, indent=2, ensure_ascii=False)
    nav_json = json.dumps(navigation_data, indent=2, ensure_ascii=False)

    updated = mock
    if re.search(r"export const roles\s*=", mock):
        updated = re.sub(
            r"export const roles\s*=\s*\[[\s\S]*?\];",
            f"export const roles = {roles_json};",
            updated,
            count=1,
        )
    if re.search(r"export const navigation\s*=", updated):
        updated = re.sub(
            r"export const navigation\s*=\s*\{[\s\S]*?\};",
            f"export const navigation = {nav_json};",
            updated,
            count=1,
        )
    # Keep common aliases pointed at the same admin chrome list.
    alias = (
        "\nexport const navItemsAdmin = navigation.admin;\n"
        "export const adminNavItems = navigation.admin;\n"
    )
    if "export const navItemsAdmin" not in updated:
        updated = updated.rstrip() + alias
    else:
        updated = re.sub(
            r"export const navItemsAdmin\s*=\s*[^;]+;",
            "export const navItemsAdmin = navigation.admin;",
            updated,
            count=1,
        )
        if "export const adminNavItems" in updated:
            updated = re.sub(
                r"export const adminNavItems\s*=\s*[^;]+;",
                "export const adminNavItems = navigation.admin;",
                updated,
                count=1,
            )
        else:
            updated = updated.rstrip() + "\nexport const adminNavItems = navigation.admin;\n"
    if updated != mock:
        write_file(workspace, mock_path, updated)
        return True
    return False


def write_plumbing_mock(
    workspace,
    architect: dict,
    images: dict,
    brand_name: str,
    primary: str,
    secondary: str,
    design_system: dict | None = None,
    mock_seed: dict | None = None,
) -> None:
    """Minimal mock.ts so layouts/router work before pages exist."""
    from app.application.preview_app.brand_brief import resolve_preview_brand_name
    from app.application.preview_app.industry_templates.seed import normalize_mock_seed

    resolved_brand = resolve_preview_brand_name(brand_name=brand_name, fallback=True) or "Brand"

    routes = architect.get("routes") or []
    roles_src = architect.get("roles") or []
    roles_data = []
    for ar in roles_src:
        rid = ar.get("id")
        if not rid:
            continue
        default = ar.get("defaultPath") or "/"
        for rt in routes:
            if rt.get("role_id") == rid and rt.get("path"):
                default = rt["path"]
                break
        roles_data.append({
            "id": rid,
            "label": ar.get("label") or rid,
            "defaultPath": default,
            "icon": ar.get("icon") or "users",
        })
    public_nav = _pin_ai_features_nav(
        [
            {"path": rt["path"], "href": rt["path"], "label": rt.get("title") or rt["path"]}
            for rt in routes
            if rt.get("path") and _layout_for(rt) == "public"
        ],
        routes,
    )
    admin_nav = _pin_ai_features_nav(
        [
            {"path": rt["path"], "href": rt["path"], "label": rt.get("title") or rt["path"]}
            for rt in routes
            if rt.get("path") and _layout_for(rt) == "admin"
        ],
        routes,
    )
    img = images or {}
    brand_payload: dict = {
        "name": resolved_brand,
        "tagline": "",
    }
    if design_system:
        brand_payload["design_system"] = design_system
    seed_payload = normalize_mock_seed(
        mock_seed
        if isinstance(mock_seed, dict)
        else (architect.get("mock_seed") if isinstance(architect.get("mock_seed"), dict) else None),
        brand_name=resolved_brand,
    )
    ai_features = architect.get("ai_features") if isinstance(architect.get("ai_features"), list) else []
    content = (
        f"export const brand = {json.dumps(brand_payload, ensure_ascii=False)};\n\n"
        f"export const images = {json.dumps(img, indent=2, ensure_ascii=False)};\n\n"
        f"export const roles = {json.dumps(roles_data, indent=2, ensure_ascii=False)};\n\n"
        f"export const navigation = {json.dumps({'public': public_nav, 'admin': admin_nav}, indent=2, ensure_ascii=False)};\n\n"
        f"export const seed = {json.dumps(seed_payload, indent=2, ensure_ascii=False)};\n\n"
        f"export const aiFeatures = {json.dumps(ai_features, indent=2, ensure_ascii=False)} as const;\n"
    )
    write_file(workspace, "src/data/mock.ts", content)


def write_recipe_id(workspace, recipe: dict | None = None) -> None:
    from app.application.preview_app.design_recipes import get_recipe

    resolved = recipe or get_recipe(None)
    recipe_id = resolved.get("id") or "warm-service"
    write_file(
        workspace,
        "src/lib/recipe-id.ts",
        f'export const RECIPE_ID = "{recipe_id}" as const;\n',
    )


def write_index_css(
    workspace,
    primary: str,
    secondary: str,
    font: str,
    template_renderer: TemplateRenderer,
    recipe: dict | None = None,
    design_system: dict | None = None,
) -> None:
    from app.application.preview_app.design_recipes import get_recipe, recipe_font_import_css

    primary, secondary, font_family = sanitize_theme_inputs(primary, secondary, font)
    resolved = dict(recipe or get_recipe(None))
    tokens = dict(resolved.get("tokens") or {})
    fonts = dict(resolved.get("fonts") or {})
    ds = design_system or {}
    # Per-request overlay (and brand brief) win over recipe kit defaults.
    overrides = ds.get("token_overrides")
    if isinstance(overrides, dict):
        tokens.update({k: v for k, v in overrides.items() if v is not None})
    if ds.get("font_sans"):
        fonts["sans"] = ds["font_sans"]
    if ds.get("font_display"):
        fonts["display"] = ds["font_display"]
    if ds.get("font_import"):
        fonts["import"] = ds["font_import"]
    if ds.get("font_sans") or ds.get("font_display") or ds.get("font_import"):
        resolved["fonts"] = fonts
    if ds.get("font_family"):
        font_family = str(ds["font_family"])
    if ds.get("brand_locked"):
        if ds.get("primary_color"):
            primary = str(ds["primary_color"])
        if ds.get("secondary_color"):
            secondary = str(ds["secondary_color"])
    font_import = (
        f'@import url("https://fonts.googleapis.com/css2?family={fonts.get("import")}&display=swap");'
        if fonts.get("import")
        else recipe_font_import_css(resolved)
    )
    css = template_renderer.render(
        "codegen/index_css.j2",
        primary=primary,
        secondary=secondary,
        font_family=font_family,
        font_sans=fonts.get("sans") or font_family,
        font_display=fonts.get("display") or fonts.get("sans") or font_family,
        font_import=font_import,
        radius_ui=tokens.get("radius_ui") or "0.75rem",
        bg_mix=tokens.get("bg_mix") or "4%",
        fg_mix=tokens.get("fg_mix") or "32%",
        muted_mix=tokens.get("muted_mix") or "30%",
        border_mix=tokens.get("border_mix") or "16%",
        shadow_ui=tokens.get("shadow") or "0 24px 50px -36px",
        shadow_alpha=tokens.get("shadow_alpha") or "35%",
        glow=tokens.get("glow") or "12%",
        card_color=tokens.get("card") or "white",
        atmosphere=tokens.get("atmosphere")
        or "radial-gradient(120% 80% at 0% 0%, color-mix(in srgb, var(--color-brand) 10%, transparent), transparent 50%)",
        recipe_id=resolved.get("id") or "warm-service",
    )
    write_file(workspace, "src/index.css", css)
    write_recipe_id(workspace, resolved)


def write_app_tsx(workspace, architect: dict, template_renderer: TemplateRenderer) -> list[str]:
    routes = architect.get("routes") or []
    catalog = _pages_catalog(workspace)

    resolved: list[tuple[str, str, str, str, bool]] = []  # path, component, layout, file, catalogue
    imports: dict[str, str] = {}
    used_files: set[str] = set()
    used_components: dict[str, str] = {}  # component -> path (detect duplicates)

    def _register(rel: str) -> str:
        stem = rel.split("/")[-1].rsplit(".", 1)[0]
        comp = _ident(stem)
        imp = "./" + rel[len("src/"):].rsplit(".", 1)[0] if rel.startswith("src/") else "./" + rel.rsplit(".", 1)[0]
        if comp in imports and imports[comp] != imp:
            comp = _collision_component_name(rel, stem)
        imports[comp] = imp
        return comp

    for rt in routes:
        path = rt.get("path")
        if not path:
            continue
        rel = _resolve_page(workspace, rt, catalog, used_files)
        if not rel:
            continue
        comp = _register(rel)
        if comp in used_components and used_components[comp] != path:
            stem = rel.split("/")[-1].rsplit(".", 1)[0]
            role = str(rt.get("role_id") or "role")
            comp = _ident(f"{role}_{stem}")
            imp = "./" + rel[len("src/"):].rsplit(".", 1)[0] if rel.startswith("src/") else "./" + rel.rsplit(".", 1)[0]
            imports[comp] = imp
        used_files.add(rel)
        used_components[comp] = path
        resolved.append((path, comp, _layout_for(rt), rel, _route_owns_shell(rt)))

    if not resolved and catalog:
        for rel in catalog:
            stem = _stem(rel)
            layout = "admin" if "/admin/" in rel or "/owner/" in rel else "public"
            path = f"/{stem.replace('page', '')}" if layout == "public" else f"/admin/{stem.replace('page', '')}"
            comp = _register(rel)
            resolved.append((path, comp, layout, rel, False))

    seen_paths: set[str] = set()
    uniq: list[tuple[str, str, str, str, bool]] = []
    for item in resolved:
        if item[0] in seen_paths:
            continue
        seen_paths.add(item[0])
        uniq.append(item)
    resolved = uniq

    public_paths = [p for p, _, l, _, _ in resolved if l == "public"]
    if not any(p in ("/", "/home") for p in public_paths):
        for rel in catalog:
            if _stem(rel) in ("homepage", "home") and rel not in used_files:
                comp = _register(rel)
                resolved.insert(0, ("/", comp, "public", rel, False))
                break

    sync_mock_roles_navigation(workspace, architect)

    catalogue = [(p, c) for p, c, _, _, owns_shell in resolved if owns_shell]
    public = [(p, c) for p, c, l, _, owns_shell in resolved if l == "public" and not owns_shell]
    admin = [(p, c) for p, c, l, _, owns_shell in resolved if l == "admin" and not owns_shell]
    has_root = any(p == "/" for p, _, _, _, _ in resolved)
    first_path = (public[0][0] if public else resolved[0][0]) if resolved else "/"

    import_lines = "\n".join(f"import {c} from '{imp}';" for c, imp in sorted(imports.items()))

    def _routes_block(items: list[tuple[str, str]]) -> str:
        lines: list[str] = []
        registered: set[str] = set()
        all_paths = {p.rstrip("/") or "/" for p, _ in items}
        for path, comp in items:
            lines.append(f'          <Route path="{path}" element={{<{comp} />}} />')
            registered.add(path)
            # Advisor cards invent /ai-advisor/skill-assessment etc. Keep those
            # URLs on the same page so "sub steps" don't fall through to Home.
            leaf = path.rstrip("/").rsplit("/", 1)[-1].lower()
            if re.search(r"ai[-_]?advisor|ai[-_]?stylist|ai[-_]?chat", leaf) and not path.endswith("/*"):
                splat = f"{path.rstrip('/')}/*"
                if splat not in registered:
                    lines.append(
                        f'          <Route path="{splat}" element={{<{comp} />}} />'
                    )
                    registered.add(splat)
            # Seed cards often link /gallery/<slug> while App only registered
            # /gallery/v2 (or similar). If the parent listing exists, accept
            # any sibling slug on the same detail component.
            if not path.endswith(("/*", "/:id", "/:slug")) and "/" in path.rstrip("/"):
                parent = path.rstrip("/").rsplit("/", 1)[0]
                parent_key = parent.rstrip("/") or "/"
                detailish = bool(
                    re.search(
                        r"(detail|artwork|item|piece|product|dish|class|service|provider|doctor|v\d+)",
                        f"{leaf} {comp}",
                        re.I,
                    )
                    or parent_key in all_paths
                )
                if detailish and parent_key not in ("", "/"):
                    for alias in (f"{parent}/:id", f"{parent}/:slug"):
                        if alias not in registered:
                            lines.append(
                                f'          <Route path="{alias}" element={{<{comp} />}} />'
                            )
                            registered.add(alias)
            # Booking aliases — scaffolds historically emitted /book-appointment.
            if leaf in {"book", "booking"} and path.rstrip("/") in {"/book", "/booking"}:
                for alias in ("/book-appointment", "/book-appointments"):
                    if alias not in registered:
                        lines.append(
                            f'          <Route path="{alias}" element={{<{comp} />}} />'
                        )
                        registered.add(alias)
        # Catalogue cards link /gallery/<slug> even when detail was planned as
        # /artwork (or similar). Wire listing/:id onto the detail component.
        listing_re = re.compile(
            r"^/(gallery|collection|collections|shop|catalog|catalogue|products|works|menu)(/|$)",
            re.I,
        )
        detail_comps = [
            (p, c)
            for p, c in items
            if re.search(r"(detail|artwork|item|piece|product)", f"{p} {c}", re.I)
            and not listing_re.match(p.rstrip("/") + "/")
        ]
        if detail_comps:
            detail_comp = detail_comps[0][1]
            for p, _ in items:
                if not listing_re.match((p.rstrip("/") or "/") + "/"):
                    continue
                base = p.rstrip("/") or ""
                if not base:
                    continue
                for alias in (f"{base}/:id", f"{base}/:slug"):
                    if alias not in registered:
                        lines.append(
                            f'          <Route path="{alias}" element={{<{detail_comp} />}} />'
                        )
                        registered.add(alias)
        return "\n".join(lines)

    blocks: list[str] = []
    if not has_root and first_path != "/":
        blocks.append(f'        <Route path="/" element={{<Navigate to="{first_path}" replace />}} />')
    if catalogue:
        blocks.append(_routes_block(catalogue))
    if public:
        blocks.append(
            "        <Route element={<PublicLayout />}>\n"
            + _routes_block(public)
            + "\n        </Route>"
        )
    if admin:
        blocks.append(
            "        <Route element={<AdminLayout />}>\n"
            + _routes_block(admin)
            + "\n        </Route>"
        )
    blocks.append('        <Route path="*" element={<Navigate to="/" replace />} />')
    routes_jsx = "\n".join(blocks)

    app = template_renderer.render(
        "codegen/app_tsx.j2",
        import_lines=import_lines,
        layout_import_lines="\n".join(
            line
            for enabled, line in (
                (bool(public), "import PublicLayout from './layouts/PublicLayout';"),
                (bool(admin), "import AdminLayout from './layouts/AdminLayout';"),
            )
            if enabled
        ),
        first_path=first_path,
        routes_jsx=routes_jsx,
    )
    write_file(workspace, "src/App.tsx", app)
    return [p for p, _, _, _, _ in resolved]
