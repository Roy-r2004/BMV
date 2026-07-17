"""Preview safety — Runtime."""
from __future__ import annotations

import re
from pathlib import Path

from app.application.preview_app.safety.ui_icons import (
    ensure_ui_icons,
    normalize_ui_icon_imports,
)
from app.application.preview_app.theme import sanitize_theme_inputs
from app.application.preview_app.workspace import list_source_files, read_file, write_file
from app.core.config import settings
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.infrastructure.logging import get_logger

guard_log = get_logger("SafetyGuards")

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

    brand, accent, font_family = sanitize_theme_inputs(primary, secondary, font)
    catalogue_tokens = {
        "--color-background": f"color-mix(in srgb, {brand} 4%, white)",
        "--color-foreground": f"color-mix(in srgb, {brand} 32%, black)",
        "--color-muted": f"color-mix(in srgb, {brand} 30%, #64748b)",
        "--color-card": "white",
        "--color-border-subtle": f"color-mix(in srgb, {brand} 16%, #e2e8f0)",
        "--color-brand": brand,
        "--color-brand-dark": accent,
        "--color-accent": accent,
        "--color-ring": brand,
        "--color-chart": accent,
        "--font-sans": font_family,
        "--font-display": font_family,
        "--radius-ui": "0.75rem",
        "--shadow-ui": f"0 24px 50px -36px color-mix(in srgb, {brand} 35%, transparent)",
        "--glow-atmosphere": f"color-mix(in srgb, {brand} 12%, transparent)",
        "--treatment-light": brand,
    }
    missing_tokens = {
        token: value for token, value in catalogue_tokens.items() if token not in css
    }
    if missing_tokens:
        declarations = "".join(
            f"  {token}: {value};\n" for token, value in missing_tokens.items()
        )
        theme_block = f"\n@theme {{\n{declarations}}}\n"
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

    # 1b) registerPreviewNavigate so absolute in-app <a href="/..."> clicks stay mounted
    if "registerPreviewNavigate" not in app:
        if "setupPreviewBridge" in app:
            app = app.replace(
                "import { notifyParent, setupPreviewBridge }",
                "import { notifyParent, registerPreviewNavigate, setupPreviewBridge }",
            )
            app = app.replace(
                "import { notifyParent,setupPreviewBridge }",
                "import { notifyParent, registerPreviewNavigate, setupPreviewBridge }",
            )
            if "registerPreviewNavigate" not in app and "from './lib/preview-bridge'" in app:
                app = re.sub(
                    r"import\s*\{([^}]+)\}\s*from\s*['\"]\./lib/preview-bridge['\"]",
                    lambda m: (
                        m.group(0)
                        if "registerPreviewNavigate" in m.group(1)
                        else (
                            "import { "
                            + ", ".join(
                                sorted(
                                    {
                                        *(p.strip() for p in m.group(1).split(",") if p.strip()),
                                        "registerPreviewNavigate",
                                    }
                                )
                            )
                            + " } from './lib/preview-bridge'"
                        )
                    ),
                    app,
                    count=1,
                )
            if "registerPreviewNavigate((path)" not in app and "setupPreviewBridge(" in app:
                app = app.replace(
                    "setupPreviewBridge(",
                    "registerPreviewNavigate((path) => navigate(path));\n    setupPreviewBridge(",
                    1,
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
        guard_log.warning("ui icons guard skipped: %s", e)
    try:
        fixed.extend(normalize_ui_icon_imports(workspace))
    except Exception as e:
        guard_log.warning("ui icon import normalize skipped: %s", e)
    try:
        if _ensure_tailwind_css(workspace, primary, secondary, font):
            fixed.append("src/index.css (tailwind/theme)")
    except Exception as e:
        guard_log.warning("tailwind guard skipped: %s", e)
    try:
        if _ensure_router(workspace, architect, plan, template_renderer):
            fixed.append("src/App.tsx (basename/index route)")
    except Exception as e:
        guard_log.warning("router guard skipped: %s", e)
    return fixed
