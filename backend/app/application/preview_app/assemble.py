"""Deterministic assembly of routing + theme for generated preview apps."""
from __future__ import annotations

import json
import re

from app.domain.interfaces.template_renderer import TemplateRenderer
from app.application.preview_app.workspace import list_source_files, read_file, write_file


def _ident(stem: str) -> str:
    s = re.sub(r"[^0-9A-Za-z_]", "", stem)
    if not s or s[0].isdigit():
        s = "Page" + s
    return s


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
    routes = pa.get("routes") or []
    roles = pa.get("roles") or []
    files: list[dict] = []
    for rt in routes:
        cf = rt.get("component_file")
        if not cf:
            continue
        files.append({
            "path": cf,
            "kind": "page",
            "instructions": f"{rt.get('title', '')} — {rt.get('purpose', '')}. Role: {rt.get('role_id', '')}",
        })
    if plan:
        for role in plan.get("roles", []):
            for page in role.get("pages", []):
                for f in files:
                    if page.get("id") and page["id"].replace("-", "") in (f.get("path") or "").lower().replace("-", ""):
                        sections = page.get("sections") or []
                        f["instructions"] += f"\nSections: {json.dumps(sections[:10], ensure_ascii=False)[:2000]}"
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
            continue
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

    public_nav = [
        {"path": rt["path"], "label": rt.get("title") or rt["path"]}
        for rt in routes
        if rt.get("path") and _layout_for(rt) == "public"
    ]
    admin_nav = [
        {"path": rt["path"], "label": rt.get("title") or rt["path"]}
        for rt in routes
        if rt.get("path") and _layout_for(rt) == "admin"
    ]

    roles_json = json.dumps(roles_data, indent=2, ensure_ascii=False)
    nav_json = json.dumps({"public": public_nav, "admin": admin_nav}, indent=2, ensure_ascii=False)

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
) -> None:
    """Minimal mock.ts so layouts/router work before pages exist. No business data."""
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
    public_nav = [
        {"path": rt["path"], "label": rt.get("title") or rt["path"]}
        for rt in routes if rt.get("path") and _layout_for(rt) == "public"
    ]
    admin_nav = [
        {"path": rt["path"], "label": rt.get("title") or rt["path"]}
        for rt in routes if rt.get("path") and _layout_for(rt) == "admin"
    ]
    img = images or {}
    content = (
        f"export const brand = {json.dumps({'name': brand_name or 'Brand', 'tagline': ''}, ensure_ascii=False)};\n\n"
        f"export const images = {json.dumps(img, indent=2, ensure_ascii=False)};\n\n"
        f"export const roles = {json.dumps(roles_data, indent=2, ensure_ascii=False)};\n\n"
        f"export const navigation = {json.dumps({'public': public_nav, 'admin': admin_nav}, indent=2, ensure_ascii=False)};\n"
    )
    write_file(workspace, "src/data/mock.ts", content)


def write_index_css(workspace, primary: str, secondary: str, font: str, template_renderer: TemplateRenderer) -> None:
    font_family = f'"{font}", system-ui, sans-serif' if font else "system-ui, sans-serif"
    css = template_renderer.render(
        "codegen/index_css.j2",
        primary=primary or "#6366f1",
        secondary=secondary or primary or "#4f46e5",
        font_family=font_family,
    )
    write_file(workspace, "src/index.css", css)


def write_app_tsx(workspace, architect: dict, template_renderer: TemplateRenderer) -> list[str]:
    routes = architect.get("routes") or []
    catalog = _pages_catalog(workspace)

    resolved: list[tuple[str, str, str, str]] = []  # path, component, layout, file
    imports: dict[str, str] = {}
    used_files: set[str] = set()
    used_components: dict[str, str] = {}  # component -> path (detect duplicates)

    def _register(rel: str) -> str:
        stem = rel.split("/")[-1].rsplit(".", 1)[0]
        comp = _ident(stem)
        if comp in imports and imports[comp] != "./" + rel[len("src/"):].rsplit(".", 1)[0]:
            comp = _ident(rel.replace("/", "_").replace(".", "_"))
        imp = "./" + rel[len("src/"):].rsplit(".", 1)[0] if rel.startswith("src/") else "./" + rel.rsplit(".", 1)[0]
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
            comp = _ident(f"{rt.get('role_id', 'role')}_{stem}")
            imp = "./" + rel[len("src/"):].rsplit(".", 1)[0] if rel.startswith("src/") else "./" + rel.rsplit(".", 1)[0]
            imports[comp] = imp
        used_files.add(rel)
        used_components[comp] = path
        resolved.append((path, comp, _layout_for(rt), rel))

    if not resolved and catalog:
        for rel in catalog:
            stem = _stem(rel)
            layout = "admin" if "/admin/" in rel or "/owner/" in rel else "public"
            path = f"/{stem.replace('page', '')}" if layout == "public" else f"/admin/{stem.replace('page', '')}"
            comp = _register(rel)
            resolved.append((path, comp, layout, rel))

    seen_paths: set[str] = set()
    uniq: list[tuple[str, str, str, str]] = []
    for item in resolved:
        if item[0] in seen_paths:
            continue
        seen_paths.add(item[0])
        uniq.append(item)
    resolved = uniq

    public_paths = [p for p, _, l, _ in resolved if l == "public"]
    if not any(p in ("/", "/home") for p in public_paths):
        for rel in catalog:
            if _stem(rel) in ("homepage", "home") and rel not in used_files:
                comp = _register(rel)
                resolved.insert(0, ("/", comp, "public", rel))
                break

    sync_mock_roles_navigation(workspace, architect)

    public = [(p, c) for p, c, l, _ in resolved if l == "public"]
    admin = [(p, c) for p, c, l, _ in resolved if l == "admin"]
    has_root = any(p == "/" for p, _, _, _ in resolved)
    first_path = (public[0][0] if public else resolved[0][0]) if resolved else "/"

    import_lines = "\n".join(f"import {c} from '{imp}';" for c, imp in sorted(imports.items()))

    def _routes_block(items: list[tuple[str, str]]) -> str:
        return "\n".join(f'          <Route path="{p}" element={{<{c} />}} />' for p, c in items)

    blocks: list[str] = []
    if not has_root and first_path != "/":
        blocks.append(f'        <Route path="/" element={{<Navigate to="{first_path}" replace />}} />')
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
        first_path=first_path,
        routes_jsx=routes_jsx,
    )
    write_file(workspace, "src/App.tsx", app)
    return [p for p, _, _, _ in resolved]
