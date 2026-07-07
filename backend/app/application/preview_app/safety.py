"""Runtime-correctness guards for generated preview apps.

These are pure plumbing (make the AI's app actually render when served under a
sub-path with Tailwind) — NOT UI/content shaping. Build success alone can't
catch these because a missing basename or Tailwind import still compiles fine.
"""
from __future__ import annotations

import json
import re

from app.core.config import settings
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.application.preview_app.workspace import list_source_files, read_file, write_file

_MOCK_IMPORT_RE = re.compile(
    r"import\s+(?:type\s+)?\{([^}]*)\}\s*from\s*['\"][^'\"]*data/mock['\"]"
)


def _first_route_path(architect: dict, plan: dict) -> str:
    for rt in architect.get("routes", []):
        p = rt.get("path")
        if p and p != "/":
            return p
    for r in plan.get("roles", []):
        dp = r.get("defaultPath")
        if dp and dp != "/":
            return dp
        for pg in r.get("pages", []):
            pp = pg.get("path")
            if pp and pp != "/":
                return pp
    return "/"


def _ensure_tailwind_css(workspace, primary: str, secondary: str, font: str) -> bool:
    css = read_file(workspace, "src/index.css")
    changed = False

    if '@import "tailwindcss"' not in css and "@import 'tailwindcss'" not in css:
        css = '@import "tailwindcss";\n\n' + css
        changed = True

    # Pages use bg-brand/text-brand -> the @theme must define --color-brand.
    if "--color-brand" not in css:
        font_family = f'"{font}", system-ui, sans-serif' if font else "system-ui, sans-serif"
        theme_block = (
            "\n@theme {\n"
            f"  --color-brand: {primary};\n"
            f"  --color-brand-dark: {secondary or primary};\n"
            f"  --font-sans: {font_family};\n"
            "}\n"
        )
        # insert after the tailwind import line
        lines = css.splitlines()
        insert_at = 0
        for i, ln in enumerate(lines):
            if "tailwindcss" in ln:
                insert_at = i + 1
                break
        lines.insert(insert_at, theme_block)
        css = "\n".join(lines)
        changed = True

    if changed:
        write_file(workspace, "src/index.css", css)
    return changed


def _ensure_router(workspace, architect: dict, plan: dict, template_renderer: TemplateRenderer) -> bool:
    app = read_file(workspace, "src/App.tsx")
    if not app or "<BrowserRouter" not in app:
        return False
    changed = False

    # 1) basename so routes resolve under the served sub-path
    if "basename" not in app:
        app = re.sub(
            r"<BrowserRouter(\s|>)",
            lambda m: "<BrowserRouter basename={import.meta.env.BASE_URL}"
            + ("" if m.group(1) == ">" else " ")
            + (">" if m.group(1) == ">" else ""),
            app,
            count=1,
        )
        changed = True

    # 2) ensure a root ("/") route exists so the served root renders something
    if 'path="/"' not in app and "path='/'" not in app:
        target = _first_route_path(architect, plan)
        if "Navigate" not in app:
            app = re.sub(
                r"from ['\"]react-router-dom['\"]",
                lambda m: m.group(0),
                app,
                count=1,
            )
            app = re.sub(
                r"(import\s*\{)([^}]*)(\}\s*from\s*['\"]react-router-dom['\"])",
                lambda m: f"{m.group(1)}{m.group(2)}, Navigate{m.group(3)}",
                app,
                count=1,
            )
        redirect = template_renderer.render("codegen/route_redirect_snippet.j2", target=target)
        app = re.sub(r"(<Routes>\s*)", lambda m: m.group(1) + "\n        " + redirect + "\n", app, count=1)
        changed = True

    if changed:
        write_file(workspace, "src/App.tsx", app)
    return changed


def _collect_mock_imports(workspace) -> set[str]:
    names: set[str] = set()
    for rel in list_source_files(workspace):
        if rel.endswith("data/mock.ts"):
            continue
        for m in _MOCK_IMPORT_RE.finditer(read_file(workspace, rel)):
            for part in m.group(1).split(","):
                n = part.strip().split(" as ")[0].strip()
                if n and n != "type":
                    names.add(n)
    return names


def _mock_exported_names(mock: str) -> set[str]:
    names = set(
        re.findall(r"export\s+(?:const|let|var|function|class)\s+([A-Za-z0-9_]+)", mock)
    )
    for m in re.finditer(r"export\s*\{([^}]*)\}", mock):
        for part in m.group(1).split(","):
            n = part.strip().split(" as ")[-1].strip()
            if n:
                names.add(n)
    return names


def _nav_from_architect(architect: dict) -> dict:
    public, admin = [], []
    for rt in architect.get("routes", []):
        path = rt.get("path")
        if not path or path == "/":
            continue
        item = {"path": path, "label": rt.get("title") or path.strip("/").replace("-", " ").title()}
        if (rt.get("layout") == "admin") or path.startswith("/admin"):
            admin.append(item)
        else:
            public.append(item)
    return {"public": public, "admin": admin}


def _roles_from(architect: dict, plan: dict) -> list:
    src = architect.get("roles") or plan.get("roles") or []
    return [
        {
            "id": r.get("id"),
            "label": r.get("label"),
            "defaultPath": r.get("defaultPath", "/"),
            "icon": r.get("icon", "users"),
        }
        for r in src
        if r.get("id")
    ]


def _default_export_value(name: str, architect: dict, plan: dict, images: dict, brand_name: str) -> str:
    low = name.lower()
    if low == "images":
        return json.dumps(images or {}, ensure_ascii=False)
    if low == "brand":
        return json.dumps({"name": brand_name or "Brand", "tagline": ""}, ensure_ascii=False)
    if low == "navigation":
        return json.dumps(_nav_from_architect(architect), ensure_ascii=False)
    if low == "roles":
        return json.dumps(_roles_from(architect, plan), ensure_ascii=False)
    # Unknown symbols: default to an empty array (safe for .map / iteration).
    return "[]"


_MOCK_SELF_IMPORT_RE = re.compile(
    r"^\s*import\s+[^;\n]*from\s*['\"][^'\"]*(?:/)?mock['\"]\s*;?\s*$", re.MULTILINE
)


def looks_truncated_source(content: str) -> bool:
    """Heuristic: reject AI file writes cut off mid-line (common token-limit failure)."""
    stripped = content.rstrip()
    if len(stripped) < 20:
        return True
    last = stripped.splitlines()[-1].rstrip()
    if not last:
        return False
    if stripped.endswith(("}", ");", "};", "/>", ">", '"""', "'''")):
        return False
    if last.count('"') % 2 == 1 or last.count("'") % 2 == 1:
        return True
    if re.search(r'className="[^"]*$', last):
        return True
    if re.search(r"<\w+[^>]*$", last):
        return True
    return False


def sanitize_workspace_sources(workspace) -> list[str]:
    """Strip markdown fences/prose accidentally pasted into source files."""
    from app.application.preview_app.codegen import _strip_fences

    cleaned: list[str] = []
    for rel in list_source_files(workspace):
        if not rel.endswith((".tsx", ".ts", ".css")):
            continue
        raw = read_file(workspace, rel)
        fixed = _strip_fences(raw)
        if fixed != raw.strip():
            write_file(workspace, rel, fixed)
            cleaned.append(rel)
    return cleaned


def _clean_mock(mock: str) -> str:
    """Remove any self-import lines (mock.ts importing from itself -> redeclare)."""
    return _MOCK_SELF_IMPORT_RE.sub("", mock)


def ensure_mock_exports(
    workspace, architect: dict, plan: dict, images: dict, brand_name: str
) -> list[str]:
    """Guarantee every symbol the pages import from mock.ts actually exists.

    Only APPENDS missing exports (never removes the AI's rich data). Pure
    build-correctness — prevents MISSING_EXPORT failures and fix-loop thrashing.
    """
    mock = read_file(workspace, "src/data/mock.ts")
    cleaned = _clean_mock(mock)
    if cleaned != mock:
        mock = cleaned
        write_file(workspace, "src/data/mock.ts", mock)
    needed = _collect_mock_imports(workspace)
    if not needed:
        return []
    have = _mock_exported_names(mock)
    missing = [n for n in sorted(needed) if n not in have]
    if not missing:
        return []
    additions = "\n".join(
        f"export const {n} = {_default_export_value(n, architect, plan, images, brand_name)};"
        for n in missing
    )
    mock = mock.rstrip() + "\n\n// build-correctness guard: auto-added missing exports\n" + additions + "\n"
    write_file(workspace, "src/data/mock.ts", mock)
    return missing


_NAV_IMPORT_RE = re.compile(r"^\s*import\s+Nav\s+from\s+['\"][^'\"]+['\"]\s*;?\s*\n", re.MULTILINE)
_NAV_JSX_RE = re.compile(r"<Nav\b[^>]*/>\s*", re.DOTALL)


def cleanup_page_shells(workspace) -> list[str]:
    """Remove duplicate Nav from pages — PublicLayout already renders it."""
    cleaned: list[str] = []
    for rel in list_source_files(workspace):
        if "/pages/" not in rel.replace("\\", "/"):
            continue
        content = read_file(workspace, rel)
        updated = _NAV_IMPORT_RE.sub("", content)
        updated = _NAV_JSX_RE.sub("", updated)
        if updated != content:
            write_file(workspace, rel, updated)
            cleaned.append(rel)
    return cleaned


def ensure_ui_icons(workspace) -> bool:
    """Copy UiIcons scaffold from preview template if the workspace is missing it."""
    target = "src/components/UiIcons.tsx"
    if read_file(workspace, target).strip():
        return False
    source = settings.PREVIEW_TEMPLATE_DIR / "src" / "components" / "UiIcons.tsx"
    if not source.is_file():
        return False
    write_file(workspace, target, source.read_text(encoding="utf-8"))
    return True


def ensure_runtime_correctness(
    workspace,
    architect: dict,
    plan: dict,
    primary: str,
    secondary: str,
    font: str,
    template_renderer: TemplateRenderer,
) -> list[str]:
    fixed: list[str] = []
    try:
        if ensure_ui_icons(workspace):
            fixed.append("src/components/UiIcons.tsx")
    except Exception as e:
        print(f"    ui icons guard skipped: {e}", flush=True)
    try:
        if _ensure_tailwind_css(workspace, primary, secondary, font):
            fixed.append("src/index.css (tailwind/theme)")
    except Exception as e:
        print(f"    tailwind guard skipped: {e}", flush=True)
    try:
        if _ensure_router(workspace, architect, plan, template_renderer):
            fixed.append("src/App.tsx (basename/index route)")
    except Exception as e:
        print(f"    router guard skipped: {e}", flush=True)
    return fixed
