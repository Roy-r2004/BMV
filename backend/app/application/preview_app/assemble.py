"""Deterministic assembly of routing + theme for generated preview apps.

App.tsx (router) and index.css (Tailwind theme) are pure plumbing, not design.
Generating them from the architect plan + design system (instead of asking the
LLM) removes the biggest source of build failures (basename, RouteBridge exports,
Tailwind removal, page import-name drift). The LLM still authors every page and
all mock data — the actual UI/content.
"""
from __future__ import annotations

import re

from app.domain.interfaces.template_renderer import TemplateRenderer
from app.application.preview_app.workspace import list_source_files, read_file, write_file


def _ident(stem: str) -> str:
    s = re.sub(r"[^0-9A-Za-z_]", "", stem)
    if not s or s[0].isdigit():
        s = "Page" + s
    return s


def _pages_index(workspace) -> dict[str, str]:
    idx: dict[str, str] = {}
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if "/pages/" in norm and norm.endswith((".tsx", ".jsx")):
            stem = norm.split("/")[-1].rsplit(".", 1)[0]
            idx[stem.lower()] = norm
    return idx


def write_index_css(workspace, primary: str, secondary: str, font: str, template_renderer: TemplateRenderer) -> None:
    font_family = f'"{font}", system-ui, sans-serif' if font else "system-ui, sans-serif"
    css = template_renderer.render(
        "codegen/index_css.j2",
        primary=primary or "#6366f1",
        secondary=secondary or primary or "#4f46e5",
        font_family=font_family,
    )
    write_file(workspace, "src/index.css", css)


def _layout_for(route: dict) -> str:
    if route.get("layout") == "admin":
        return "admin"
    return "admin" if (route.get("path") or "").startswith("/admin") else "public"


def write_app_tsx(workspace, architect: dict, template_renderer: TemplateRenderer) -> list[str]:
    routes = architect.get("routes") or []
    pages = _pages_index(workspace)

    resolved: list[tuple[str, str, str]] = []  # (path, component, layout)
    imports: dict[str, str] = {}  # component -> import path (no extension)

    def _register(rel: str) -> str:
        stem = rel.split("/")[-1].rsplit(".", 1)[0]
        comp = _ident(stem)
        imp = "./" + rel[len("src/"):].rsplit(".", 1)[0] if rel.startswith("src/") else "./" + rel
        imports[comp] = imp
        return comp

    for rt in routes:
        path = rt.get("path")
        if not path:
            continue
        cf = rt.get("component_file") or ""
        rel = None
        if cf and read_file(workspace, cf):
            rel = cf.replace("\\", "/")
        elif cf:
            stem = cf.split("/")[-1].rsplit(".", 1)[0].lower()
            rel = pages.get(stem)
        if not rel:
            continue
        resolved.append((path, _register(rel), _layout_for(rt)))

    # Fallback: no routes resolved -> route every page file we found.
    if not resolved:
        for stem_l, rel in pages.items():
            comp = _register(rel)
            resolved.append(("/" + stem_l, comp, "admin" if "admin" in stem_l else "public"))

    # Dedupe by path (first wins).
    seen: set[str] = set()
    uniq: list[tuple[str, str, str]] = []
    for path, comp, layout in resolved:
        if path in seen:
            continue
        seen.add(path)
        uniq.append((path, comp, layout))
    resolved = uniq

    # Every app needs a marketing landing page — wire Home/HomePage if architect omitted it.
    public_paths = [p for p, _, l in resolved if l == "public"]
    has_landing = any(p in ("/", "/home") for p in public_paths)
    if not has_landing:
        for key in ("homepage", "home"):
            rel = pages.get(key)
            if rel:
                comp = _register(rel)
                resolved.insert(0, ("/", comp, "public"))
                break

    public = [(p, c) for p, c, l in resolved if l == "public"]
    admin = [(p, c) for p, c, l in resolved if l == "admin"]
    has_root = any(p == "/" for p, _, _ in resolved)
    first_path = (public[0][0] if public else resolved[0][0]) if resolved else "/"

    import_lines = "\n".join(f"import {c} from '{imp}';" for c, imp in imports.items())

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
    return [p for p, _, _ in resolved]
