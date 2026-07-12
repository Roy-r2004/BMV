"""Runtime-correctness guards for generated preview apps.

These are pure plumbing (make the AI's app actually render when served under a
sub-path with Tailwind) — NOT UI/content shaping. Build success alone can't
catch these because a missing basename or Tailwind import still compiles fine.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path, PurePosixPath

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


def _seeded_list_export(name: str, brand_name: str) -> str:
    """3–6 realistic rows so pages never render empty lists from auto-exports."""
    brand = brand_name or "Brand"
    label = re.sub(r"([A-Z])", r" \1", name).strip() or name
    rows = []
    for i in range(1, 5):
        rows.append(
            {
                "id": f"{name.lower()}-{i}",
                "name": f"{label} {i}",
                "title": f"{label} {i}",
                "label": f"{label} {i}",
                "status": ["Open", "In progress", "Done", "Scheduled"][i % 4],
                "detail": f"Sample {brand} record for demo lists",
                "amount": 40 + i * 12,
                "count": 3 + i,
            }
        )
    return json.dumps(rows, ensure_ascii=False)


def _design_system_dict(primary: str, secondary: str, font: str) -> dict:
    primary = primary or "#6366f1"
    secondary = secondary or primary
    font_token = (font or "Inter").split(",")[0].strip().strip('"').strip("'") or "Inter"
    font_class = re.sub(r"[^a-z0-9]+", "", font_token.lower()) or "sans"
    slug = re.sub(r"[^a-z0-9]+", "+", font_token.lower())
    return {
        "primary_color": primary,
        "secondary_color": secondary,
        "accent": primary,
        "text_color": "#0f172a",
        "muted_text_color": "#475569",
        "background_color": "#fafafa",
        "font_family": font_class,
        "font_import_url": f"https://fonts.googleapis.com/css2?family={slug}:wght@400;500;600;700&display=swap",
        "section_spacing": "4rem",
        "border_radius": "1rem",
        "card_style": "shadow (rgba(0,0,0,0.05))",
    }


def _default_export_value(
    name: str,
    architect: dict,
    plan: dict,
    images: dict,
    brand_name: str,
    primary: str = "#6366f1",
    secondary: str = "#0d9488",
    font: str = "Inter",
) -> str:
    low = name.lower()
    if low == "images":
        return json.dumps(images or {}, ensure_ascii=False)
    if low == "brand":
        return json.dumps({"name": brand_name or "Brand", "tagline": ""}, ensure_ascii=False)
    if low in ("brand_name", "brandname", "owner_name", "ownername"):
        return json.dumps(brand_name or "Brand", ensure_ascii=False)
    if low in ("design_system", "designsystem"):
        return json.dumps(_design_system_dict(primary, secondary, font), ensure_ascii=False)
    if low == "navigation":
        return json.dumps(_nav_from_architect(architect), ensure_ascii=False)
    if low == "roles":
        return json.dumps(_roles_from(architect, plan), ensure_ascii=False)
    # Never default to [] — empty arrays compile but show blank UIs.
    return _seeded_list_export(name, brand_name or "Brand")


_EMPTY_ARRAY_EXPORT_RE = re.compile(
    r"export\s+const\s+([A-Za-z_$][\w$]*)\s*=\s*\[\s*\]\s*;",
)


def enrich_empty_mock_exports(workspace, brand_name: str) -> list[str]:
    """Replace `export const X = []` with seeded rows for any mock export."""
    mock_path = "src/data/mock.ts"
    mock = read_file(workspace, mock_path)
    if not mock.strip():
        return []
    filled: list[str] = []

    def _repl(m: re.Match) -> str:
        name = m.group(1)
        if name.lower() in ("roles", "navigation", "images", "brand"):
            return m.group(0)
        filled.append(name)
        return f"export const {name} = {_seeded_list_export(name, brand_name)};"

    updated = _EMPTY_ARRAY_EXPORT_RE.sub(_repl, mock)
    if updated != mock:
        write_file(workspace, mock_path, updated)
    return filled


_BRAND_EXPORT_RE = re.compile(r"export\s+const\s+brand\s*=\s*\{", re.MULTILINE)


def _brand_object_span(mock: str) -> tuple[int, int] | None:
    """Return (body_start, close_brace_index) for `export const brand = { ... }`."""
    m = _BRAND_EXPORT_RE.search(mock)
    if not m:
        return None
    start = m.end()
    depth = 1
    i = start
    while i < len(mock) and depth:
        ch = mock[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    if depth != 0:
        return None
    return start, i - 1


def _brand_completeness_patch(
    brand_name: str,
    primary: str,
    secondary: str,
    font: str,
) -> str:
    """TS snippet merged into brand so pages that expect design_system don't white-screen."""
    name = brand_name or "Brand"
    services = [
        {
            "name": f"{name} Signature",
            "title": f"{name} Signature",
            "description": "Flagship service with clear results and a calm, premium feel.",
            "image": "",
            "badge": "Popular",
            "price": 280,
            "duration": "60 min",
        },
        {
            "name": "AI-guided consult",
            "title": "AI-guided consult",
            "description": "Personalized recommendations from your goals — then book in minutes.",
            "image": "",
            "badge": "AI",
            "price": 0,
            "duration": "15 min",
        },
        {
            "name": "Member aftercare",
            "title": "Member aftercare",
            "description": "Recovery tips and check-ins so results last and WhatsApp stays quiet.",
            "image": "",
            "price": 0,
            "duration": "Ongoing",
        },
    ]
    testimonials = [
        {
            "name": "Maya R.",
            "quote": f"Finally a {name} experience that feels personal — the AI consult nailed what I needed.",
            "text": f"Finally a {name} experience that feels personal — the AI consult nailed what I needed.",
            "role": "Client",
            "rating": 5,
        },
        {
            "name": "Jordan K.",
            "quote": "Booking and aftercare in one place. No more chasing answers on chat.",
            "text": "Booking and aftercare in one place. No more chasing answers on chat.",
            "role": "Member",
            "rating": 5,
        },
        {
            "name": "Sam T.",
            "quote": "The owner hub's no-show risk view alone paid for itself in a week.",
            "text": "The owner hub's no-show risk view alone paid for itself in a week.",
            "role": "Owner",
            "rating": 5,
        },
    ]
    design = _design_system_dict(primary, secondary, font)
    return (
        f"design_system: {json.dumps(design, ensure_ascii=False)},\n"
        f"  services: {json.dumps(services, ensure_ascii=False)},\n"
        f"  testimonials: {json.dumps(testimonials, ensure_ascii=False)},\n"
        f"  social_proof: {json.dumps(f'Trusted by over 2,400 delighted {name} clients.', ensure_ascii=False)}"
    )


def ensure_brand_shape(
    workspace,
    brand_name: str,
    primary: str,
    secondary: str,
    font: str,
) -> bool:
    """Guarantee `brand.design_system` (+ services/testimonials) so home pages don't crash white.

    AI pages often read `brand.design_system.primary_color` and `brand.services.map(...)`.
    Mock synthesis frequently ships a flat brand `{ name, accent }` — that throws at runtime
    and the iframe stays blank until someone hand-patches mock.ts.

    Detection MUST inspect the brand object body only: top-level `export const design_system`
    / path strings like `/owner/services` must not count as completeness.
    """
    mock_path = "src/data/mock.ts"
    mock = read_file(workspace, mock_path)
    if not mock.strip():
        return False
    span = _brand_object_span(mock)
    if not span:
        return False
    body_start, close_at = span
    body = mock[body_start:close_at]

    needs_ds = "design_system" not in body or "primary_color" not in body
    needs_services = not re.search(r"\bservices\s*:", body)
    needs_testimonials = not re.search(r"\btestimonials\s*:", body)
    needs_proof = "social_proof" not in body
    if not (needs_ds or needs_services or needs_testimonials or needs_proof):
        return False

    patch = _brand_completeness_patch(brand_name, primary, secondary, font)
    before = mock[:close_at].rstrip()
    if before.endswith(","):
        injection = f"\n  {patch},\n"
    else:
        injection = f",\n  {patch},\n"
    updated = mock[:close_at] + injection + mock[close_at:]
    write_file(workspace, mock_path, updated)
    return True


_TYPED_MOCK_EXPORT_RE = re.compile(
    r"export\s+const\s+(brand_name|brandName|owner_name|ownerName|design_system|designSystem)\s*=\s*",
    re.MULTILINE,
)


def repair_typed_mock_exports(
    workspace,
    brand_name: str,
    primary: str,
    secondary: str,
    font: str,
) -> list[str]:
    """Replace auto-seeded array stubs for brand_name / design_system with real shapes.

    `ensure_mock_exports` used to fill unknown imports with list rows. Pages treat
    `design_system.primary_color` and `brand_name` as object/string — arrays white-screen.
    """
    mock_path = "src/data/mock.ts"
    mock = read_file(workspace, mock_path)
    if not mock.strip():
        return []

    replaced: list[str] = []
    ds_value = _default_export_value(
        "design_system", {}, {}, {}, brand_name, primary, secondary, font
    )
    name_value = json.dumps(brand_name or "Brand", ensure_ascii=False)

    def _export_value_end(src: str, start: int) -> int:
        i = start
        while i < len(src) and src[i] in " \t\n\r":
            i += 1
        if i >= len(src):
            return start
        if src[i] in "\"'":
            quote = src[i]
            i += 1
            while i < len(src):
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == quote:
                    i += 1
                    break
                i += 1
        elif src[i] in "[{":
            open_ch = src[i]
            close_ch = "]" if open_ch == "[" else "}"
            depth = 0
            in_str: str | None = None
            while i < len(src):
                ch = src[i]
                if in_str:
                    if ch == "\\":
                        i += 1
                    elif ch == in_str:
                        in_str = None
                elif ch in "\"'`":
                    in_str = ch
                elif ch == open_ch:
                    depth += 1
                elif ch == close_ch:
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
        else:
            while i < len(src) and src[i] not in ";\n":
                i += 1
        while i < len(src) and src[i] in " \t":
            i += 1
        if i < len(src) and src[i] == ";":
            i += 1
        return i

    # Walk matches right-to-left so offsets stay valid.
    matches = list(_TYPED_MOCK_EXPORT_RE.finditer(mock))
    for m in reversed(matches):
        name = m.group(1)
        val_start = m.end()
        val_end = _export_value_end(mock, val_start)
        current = mock[val_start:val_end].strip().rstrip(";").strip()
        low = name.lower().replace("_", "")
        if low in ("brandname", "ownername"):
            if current.startswith("[") or not (current.startswith('"') or current.startswith("'")):
                mock = mock[:val_start] + f"{name_value};" + mock[val_end:]
                replaced.append(name)
        elif low == "designsystem":
            if current.startswith("[") or "primary_color" not in current:
                mock = mock[:val_start] + f"{ds_value};" + mock[val_end:]
                replaced.append(name)

    if replaced:
        write_file(workspace, mock_path, mock)
    return replaced


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


# Matches a single-line `key: '...'` or bare `'...',` string value — the only
# shape AI-written mock/data files reliably use for narrative copy.
_STRING_LINE_RE = re.compile(r"^(\s*(?:[\w.\[\]\"]+\s*:\s*)?)'(.*)'(\s*[,;]?\s*)$")


def fix_unescaped_apostrophes(content: str) -> tuple[str, bool]:
    """Escape stray apostrophes (contractions/possessives) inside single-quoted
    string literals — e.g. `'the station's over-portioning'` breaks the JS
    parser because the AI wrote natural-language text without escaping `'`.

    Only touches single-line `key: '...'` / `'...'` value lines so normal code
    (JSX, regex, multi-line templates) is never at risk of being rewritten.
    """
    changed = False
    out_lines = []
    for line in content.splitlines():
        m = _STRING_LINE_RE.match(line)
        if m:
            prefix, body, suffix = m.group(1), m.group(2), m.group(3)
            if re.search(r"(?<!\\)'", body):
                fixed_body = re.sub(r"(?<!\\)'", r"\\'", body)
                line = f"{prefix}'{fixed_body}'{suffix}"
                changed = True
        out_lines.append(line)
    return ("\n".join(out_lines), changed)


def _import_prefix_for_page(rel: str) -> str:
    """Relative prefix from a page file back to `src/` (e.g. `../../` for `src/pages/owner/X.tsx`)."""
    norm = rel.replace("\\", "/")
    if "src/pages/" not in norm:
        return "../"
    tail = norm.split("src/pages/", 1)[1]
    depth = tail.count("/")
    return "../" * (depth + 1)


def fix_nested_import_paths(workspace) -> list[str]:
    """Correct `../components` → `../../components` (etc.) in nested page folders."""
    fixed: list[str] = []
    for rel in list_source_files(workspace):
        if not rel.endswith((".tsx", ".ts")):
            continue
        norm = rel.replace("\\", "/")
        if "/pages/" not in norm:
            continue
        correct = _import_prefix_for_page(norm)
        content = read_file(workspace, rel)
        updated = content
        for target in ("components/", "data/", "lib/", "layouts/"):
            for shallow_len in range(1, 6):
                shallow = "../" * shallow_len
                if shallow == correct:
                    break
                for quote in ("'", '"'):
                    wrong = f"from {quote}{shallow}{target}"
                    right = f"from {quote}{correct}{target}"
                    if wrong in updated:
                        updated = updated.replace(wrong, right)
        if updated != content:
            write_file(workspace, rel, updated)
            fixed.append(rel)
    return fixed


_UI_KIT_IMPORT_LINE_RE = re.compile(
    r"""(^\s*import\s+(?:type\s+)?[\s\S]*?\s+from\s+)(['"])([^'"]+)(\2\s*;?\s*$)""",
    re.MULTILINE,
)


def _normalize_ui_kit_specifier(spec: str) -> str | None:
    """Return an `@/ui...` alias for specifiers that clearly target `src/ui`."""
    norm = spec.replace("\\", "/")
    if norm.startswith("@/ui"):
        return None
    match = re.fullmatch(r"(?:\./|\.\./)+(?:src/)?ui(?P<suffix>(?:/[^'\"\\]+)?)", norm)
    if not match:
        match = re.fullmatch(r"/?src/ui(?P<suffix>(?:/[^'\"\\]+)?)", norm)
    if not match:
        return None
    suffix = match.group("suffix") or ""
    if suffix in {"/index", "/index.ts", "/index.tsx", "/index.js", "/index.jsx"}:
        suffix = ""
    return f"@/ui{suffix}"


def normalize_ui_kit_imports(workspace) -> list[str]:
    """Rewrite clearly-relative `src/ui` imports to the `@/ui` alias."""
    fixed: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")):
            continue
        content = read_file(workspace, rel)

        def _replace(match: re.Match[str]) -> str:
            alias = _normalize_ui_kit_specifier(match.group(3))
            if not alias:
                return match.group(0)
            return f"{match.group(1)}{match.group(2)}{alias}{match.group(4)}"

        updated = _UI_KIT_IMPORT_LINE_RE.sub(_replace, content)
        if updated != content:
            write_file(workspace, rel, updated)
            fixed.append(norm)
    return fixed


def find_truncated_pages(workspace) -> list[str]:
    """Return page source paths that look cut off mid-generation."""
    out: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if "/pages/" not in norm or not norm.endswith((".tsx", ".ts")):
            continue
        if looks_truncated_source(read_file(workspace, rel)):
            out.append(rel)
    return out


_EMPTY_ARRAY_STATE_RE = re.compile(
    r"const\s*\[\s*(\w+)\s*,\s*set\w+\s*\]\s*=\s*useState\s*(?:<[^(]*>)?\s*\(\s*\[\s*\]\s*\)"
)
_MOCK_IMPORT_ANY_RE = re.compile(
    r"^\s*import\s+[^;\n]*from\s*['\"][^'\"]*data/mock['\"]", re.MULTILINE
)


def _empty_seed_state_vars(content: str) -> list[str]:
    """`useState([])` variable names in `content` that are later `.map()`'d in
    render — i.e. they drive visible list content rather than being
    incidental UI state (a `showModal`/`editingItem` boolean, or a
    multi-select `selectedIds` array that's legitimately meant to start
    empty). Exposed separately from `find_empty_seed_pages` so callers can
    name the specific violating variable in a regeneration instruction.
    """
    return [
        var for var in _EMPTY_ARRAY_STATE_RE.findall(content)
        if re.search(rf"\b{re.escape(var)}\??\.map\(", content)
    ]


def find_empty_seed_pages(workspace) -> list[str]:
    """Pages whose primary rendered list starts empty with nothing to seed it.

    A generated CRUD/list page sometimes initializes its main content as
    `useState([])` and never populates it — no mock import, no inline seed
    data — so the live page renders an empty "No items found" state instead
    of a realistic demo. This isn't a compile error (an empty array is
    syntactically valid), so the build-error fix-loop never catches it —
    this is a content-realism guard, not a correctness guard. It only
    detects; the caller (pipeline.py) handles regeneration with a reinforced
    instruction rather than this module trying to synthesize fake seed data
    itself — guessing the wrong shape would trade an empty list for a new
    runtime bug.

    Signal used: a `useState([])` variable that IS `.map()`'d in render
    (drives visible content) AND the file has zero `data/mock` imports at
    all (no chance it's actually seeded from mock data under another name).
    Both conditions are required together — either alone produces false
    positives (plenty of legitimately-empty state like `selectedIds` starts
    as `useState([])` and is never meant to render a list; plenty of pages
    import mock data under names that don't obviously pair with a specific
    `.map()`'d variable).
    """
    out: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if "/pages/" not in norm or not norm.endswith((".tsx", ".ts")):
            continue
        content = read_file(workspace, rel)
        if _MOCK_IMPORT_ANY_RE.search(content):
            continue
        if _empty_seed_state_vars(content):
            out.append(rel)
    return out


_ALLOWED_NPM_IMPORTS = {
    "react",
    "react-dom",
    "react-router-dom",
    "react/jsx-runtime",
    "framer-motion",
    "@radix-ui/react-dialog",
    "@radix-ui/react-dropdown-menu",
    "@radix-ui/react-tabs",
    "@radix-ui/react-select",
    "@radix-ui/react-switch",
    "@radix-ui/react-tooltip",
    "@radix-ui/react-slot",
    "lucide-react",
    "recharts",
    "clsx",
    "tailwind-merge",
    "date-fns",
    "sonner",
}
# Packages we cannot install in preview apps — rewrite imports to local stubs
# instead of deleting them (deleting left Transition/Dialog undefined → white screen).
_STUBBED_NPM_IMPORTS = {
    "@headlessui/react": "src/components/UiHeadless",
    "@headlessui/react/dist": "src/components/UiHeadless",
}
_IMPORT_FROM_RE = re.compile(
    r"""^\s*import\s+(?:type\s+)?(?:[\s\S]*?)\s+from\s+['"]([^'"]+)['"]\s*;?\s*$""",
    re.MULTILINE,
)
_HEADLESS_SYMBOLS = (
    "Transition",
    "Dialog",
    "Menu",
    "Disclosure",
    "Listbox",
    "Combobox",
    "Popover",
    "Tab",
    "Switch",
    "RadioGroup",
    "Portal",
)


def _npm_package_name(spec: str) -> str:
    if spec.startswith("@"):
        parts = spec.split("/")
        return "/".join(parts[:2]) if len(parts) >= 2 else spec
    return spec.split("/")[0]


def _rel_to_stub(from_file: str, stub_abs: str = "src/components/UiHeadless") -> str:
    """Relative import path from a source file to the UiHeadless stub (no extension)."""
    start = PurePosixPath(from_file.replace("\\", "/")).parent
    target = PurePosixPath(stub_abs)
    rel = PurePosixPath(os.path.relpath(str(target), str(start))).as_posix()
    if not rel.startswith("."):
        rel = "./" + rel
    return rel


def ensure_ui_headless_file(workspace) -> bool:
    """Copy UiHeadless.tsx from the preview template into the workspace."""
    source = settings.PREVIEW_TEMPLATE_DIR / "src" / "components" / "UiHeadless.tsx"
    dest = Path(workspace) / "src" / "components" / "UiHeadless.tsx"
    if not source.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = source.read_text(encoding="utf-8")
    if dest.is_file() and dest.read_text(encoding="utf-8") == text:
        return False
    dest.write_text(text, encoding="utf-8")
    return True


def strip_forbidden_npm_imports(workspace) -> list[str]:
    """Rewrite stubbable illegal imports; strip the rest.

    Models often import @headlessui/react / framer-motion. Deleting those lines
    used to leave `<Transition>` / `<Dialog>` unbound → runtime white screen
    even though `vite build` succeeded. Stubbable packages are rewritten to
    `src/components/UiHeadless`; unknown packages are still stripped.
    """
    ensure_ui_headless_file(workspace)
    touched: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")):
            continue
        if norm.startswith("src/data/") or norm.endswith("UiHeadless.tsx"):
            continue
        content = read_file(workspace, rel)
        updated = content
        changed = False
        for m in list(_IMPORT_FROM_RE.finditer(content)):
            src = m.group(1)
            if (
                src.startswith(".")
                or src.startswith("/")
                or src.startswith("http")
                or src.startswith("@/")
                or src.startswith("~/")
            ):
                continue
            pkg = _npm_package_name(src)
            if pkg in _ALLOWED_NPM_IMPORTS or src in _ALLOWED_NPM_IMPORTS:
                continue
            # Exact or package-level stub match
            stub_target = _STUBBED_NPM_IMPORTS.get(src) or _STUBBED_NPM_IMPORTS.get(pkg)
            if stub_target:
                rel_imp = _rel_to_stub(norm, stub_target)
                old = m.group(0)
                new = re.sub(
                    r"""from\s+['"][^'"]+['"]""",
                    f"from '{rel_imp}'",
                    old,
                )
                if new != old and old in updated:
                    updated = updated.replace(old, new, 1)
                    changed = True
                continue
            # Unknown forbidden package — strip the import line
            old = m.group(0)
            if old in updated:
                updated = updated.replace(old, "/* removed forbidden import */\n", 1)
                changed = True
        if changed and updated != content:
            write_file(workspace, norm, updated)
            print(f"    npm imports rewritten/stripped in {norm}", flush=True)
            touched.append(norm)
    return touched


def ensure_headless_stub_imports(workspace) -> list[str]:
    """Inject UiHeadless imports when Headless UI symbols are used unbound.

    Covers the case where a prior build already stripped the headless import
    (comment left behind) and the page still references the symbols.
    """
    ensure_ui_headless_file(workspace)
    fixed: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")):
            continue
        if norm.startswith("src/data/") or norm.endswith("UiHeadless.tsx"):
            continue
        content = read_file(workspace, rel)
        needed: list[str] = []
        for sym in _HEADLESS_SYMBOLS:
            # JSX tag or compound API (Dialog.Panel) — not prose like "Member Portal."
            used = bool(
                re.search(rf"<{sym}\b", content)
                or re.search(rf"\b{sym}\.[A-Za-z]", content)
                or (sym == "motion" and re.search(r"\bmotion\.[a-z]", content))
                or (sym == "useAnimation" and re.search(r"\buseAnimation\s*\(", content))
            )
            if not used:
                continue
            imported = bool(
                re.search(
                    rf"import\s+[^;]*\b{sym}\b[^;]*from\s+['\"][^'\"]+['\"]",
                    content,
                )
            )
            if not imported:
                needed.append(sym)
        if not needed:
            continue
        # Deduplicate while preserving order
        ordered: list[str] = []
        for s in needed:
            if s not in ordered:
                ordered.append(s)
        rel_imp = _rel_to_stub(norm)
        inject = f"import {{ {', '.join(ordered)} }} from '{rel_imp}';\n"
        # Prefer after the last import; else top of file
        last_imp = None
        for m in re.finditer(r"^(?:import\s.+?;|/\* removed forbidden import \*/)\s*$", content, re.MULTILINE):
            last_imp = m
        if last_imp:
            at = last_imp.end()
            if not content[at:].startswith("\n"):
                inject = "\n" + inject
            updated = content[:at] + "\n" + inject + content[at:].lstrip("\n")
        else:
            updated = inject + content
        write_file(workspace, norm, updated)
        fixed.append(norm)
        print(f"    injected UiHeadless imports in {norm}: {', '.join(ordered)}", flush=True)
    return fixed


_ROUTER_SYMBOLS = ("Link", "NavLink", "Outlet", "Navigate", "useNavigate", "useLocation", "useParams")


def ensure_react_default_import(workspace) -> list[str]:
    """Add `import React` when files use runtime `React.*` (e.g. cloneElement).

    Vite's automatic JSX runtime does not inject a React binding, so
    `React.cloneElement` / `React.FC` value usage crashes with a blank page
    (`React is not defined`) even though `vite build` succeeds.
    """
    fixed: list[str] = []
    react_use = re.compile(r"\bReact\.")
    has_default = re.compile(r"import\s+React\b|import\s*\*\s*as\s+React\b")
    named_only = re.compile(r"import\s*\{([^}]*)\}\s*from\s*['\"]react['\"]\s*;?")
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")):
            continue
        content = read_file(workspace, rel)
        if not react_use.search(content) or has_default.search(content):
            continue
        m = named_only.search(content)
        if m:
            new_imp = f"import React, {{ {m.group(1).strip()} }} from 'react';"
            content = content[: m.start()] + new_imp + content[m.end() :]
        else:
            content = "import React from 'react';\n" + content
        write_file(workspace, rel, content)
        fixed.append(norm)
        print(f"    added React import in {norm}", flush=True)
    return fixed


def ensure_react_router_imports(workspace) -> list[str]:
    """Add missing react-router-dom named imports when JSX/hooks use them.

    Models often use `<Link>` in layouts/footers without importing it — that
    builds fine under Vite (no typecheck in `vite build`) then crashes at
    runtime with a blank white screen (`Link is not defined`).
    """
    fixed: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")):
            continue
        content = read_file(workspace, rel)
        needed: list[str] = []
        for sym in _ROUTER_SYMBOLS:
            used = bool(re.search(rf"<\s*{sym}[\s/>]", content)) or bool(
                re.search(rf"\b{sym}\s*\(", content)
            )
            if not used:
                continue
            if re.search(
                rf"import\s*{{[^}}]*\b{sym}\b[^}}]*}}\s*from\s*['\"]react-router-dom['\"]",
                content,
            ):
                continue
            needed.append(sym)
        if not needed:
            continue
        m = re.search(
            r"import\s*\{([^}]*)\}\s*from\s*['\"]react-router-dom['\"]\s*;?",
            content,
        )
        if m:
            existing = {p.strip() for p in m.group(1).split(",") if p.strip()}
            merged = sorted(existing | set(needed))
            new_imp = "import { " + ", ".join(merged) + " } from 'react-router-dom';"
            content = content[: m.start()] + new_imp + content[m.end() :]
        else:
            content = "import { " + ", ".join(needed) + " } from 'react-router-dom';\n" + content
        write_file(workspace, rel, content)
        fixed.append(norm)
        print(f"    added react-router imports in {norm}: {', '.join(needed)}", flush=True)
    return fixed


def apply_workspace_guards(
    workspace,
    architect: dict,
    plan: dict,
    images: dict,
    brand_name: str,
    primary: str,
    secondary: str,
    font: str,
    template_renderer: TemplateRenderer,
) -> list[str]:
    """Run every deterministic build guard. Safe to call before every `vite build`."""
    from app.application.preview_app.assemble import write_app_tsx, write_index_css

    actions: list[str] = []
    for fn, label in (
        (lambda: sanitize_workspace_sources(workspace), "fences stripped"),
        (lambda: sanitize_data_files(workspace), "quotes escaped"),
        (lambda: fix_nested_import_paths(workspace), "import paths fixed"),
        (lambda: normalize_ui_kit_imports(workspace), "ui kit imports normalized"),
        (lambda: strip_forbidden_npm_imports(workspace), "forbidden npm imports stripped"),
        (lambda: ensure_headless_stub_imports(workspace), "headless stubs imported"),
        (lambda: ensure_react_default_import(workspace), "React imports fixed"),
        (lambda: ensure_react_router_imports(workspace), "react-router imports fixed"),
    ):
        try:
            result = fn()
            if result:
                actions.extend(result if isinstance(result, list) else [label])
        except Exception as e:
            print(f"    guard {label} skipped: {e}", flush=True)
    try:
        if ensure_ui_icons(workspace):
            actions.append("src/components/UiIcons.tsx")
    except Exception as e:
        print(f"    ui icons guard skipped: {e}", flush=True)
    try:
        actions.extend(ensure_ui_icon_coverage(workspace))
    except Exception as e:
        print(f"    ui icon coverage guard skipped: {e}", flush=True)
    try:
        added = ensure_mock_exports(workspace, architect, plan, images, brand_name)
        actions.extend(added)
    except Exception as e:
        print(f"    mock exports guard skipped: {e}", flush=True)
    try:
        filled = enrich_empty_mock_exports(workspace, brand_name)
        if filled:
            actions.extend([f"mock:{n}" for n in filled])
            print(f"    filled empty mock exports: {', '.join(filled)}", flush=True)
    except Exception as e:
        print(f"    empty mock enrich skipped: {e}", flush=True)
    try:
        repaired = repair_typed_mock_exports(workspace, brand_name, primary, secondary, font)
        if repaired:
            actions.extend([f"mock-typed:{n}" for n in repaired])
            print(f"    repaired typed mock exports: {', '.join(repaired)}", flush=True)
    except Exception as e:
        print(f"    typed mock repair skipped: {e}", flush=True)
    try:
        if ensure_brand_shape(workspace, brand_name, primary, secondary, font):
            actions.append("src/data/mock.ts (brand shape)")
            print("    brand.design_system + services/testimonials ensured", flush=True)
    except Exception as e:
        print(f"    brand shape guard skipped: {e}", flush=True)
    try:
        src_main = settings.PREVIEW_TEMPLATE_DIR / "src" / "main.tsx"
        dst_main = Path(workspace) / "src" / "main.tsx"
        if src_main.is_file():
            text = src_main.read_text(encoding="utf-8")
            if "PreviewErrorBoundary" in text and (
                not dst_main.is_file() or "PreviewErrorBoundary" not in dst_main.read_text(encoding="utf-8")
            ):
                dst_main.write_text(text, encoding="utf-8")
                actions.append("src/main.tsx (error boundary)")
    except Exception as e:
        print(f"    main.tsx sync skipped: {e}", flush=True)
    try:
        write_index_css(workspace, primary, secondary, font, template_renderer)
        write_app_tsx(workspace, architect, template_renderer)
    except Exception as e:
        print(f"    assemble skipped: {e}", flush=True)
    try:
        actions.extend(ensure_runtime_correctness(
            workspace, architect, plan, primary, secondary, font, template_renderer,
        ))
    except Exception as e:
        print(f"    runtime correctness skipped: {e}", flush=True)
    return actions


def sanitize_data_files(workspace) -> list[str]:
    """Run `fix_unescaped_apostrophes` over every `src/data/*.ts(x)` file.

    Called before *every* build attempt (not just once) so this guard applies
    even to content written later by the fix-loop or critic-refine passes.
    """
    fixed: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.startswith("src/data/") or not norm.endswith((".ts", ".tsx")):
            continue
        raw = read_file(workspace, rel)
        new_content, changed = fix_unescaped_apostrophes(raw)
        if changed:
            write_file(workspace, rel, new_content)
            fixed.append(rel)
    return fixed


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
    # Note: brand_name / design_system get correct shapes via _default_export_value;
    # repair_typed_mock_exports also rewrites any older array stubs before build.
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


_UI_ICON_USAGE_RE = re.compile(
    r"<UiIcon\b[^>]*\bname\s*=\s*(?:\{\s*)?['\"]([a-zA-Z0-9_-]+)['\"]"
)
_ICON_MAP_DECL_RE = re.compile(r"\bconst\s+(\w+)\s*(?::[^=]+)?=\s*\{")
_ICON_MAP_KEY_RE = re.compile(
    r"(?:^|[,{\n])\s*(?:'([^']+)'|\"([^\"]+)\"|([A-Za-z_$][\w$-]*))\s*:"
)


def _collect_ui_icon_usages(workspace) -> set[str]:
    """Every literal icon name referenced via `<UiIcon name="...">` across the
    app (excluding the icon-set file itself, which defines names rather than
    using them). Dynamic names (`name={item.icon}`) can't be resolved
    statically and are intentionally skipped — this only catches the common
    case of a page hardcoding an icon key that the icon set never defines.
    """
    names: set[str] = set()
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if norm.endswith("components/uiicons.tsx") or not norm.endswith((".tsx", ".ts")):
            continue
        for m in _UI_ICON_USAGE_RE.finditer(read_file(workspace, rel)):
            names.add(m.group(1).strip().lower())
    return names


def _find_icon_map(content: str) -> tuple[int, int] | None:
    """Locate the icon-name -> JSX map inside a generated UiIcons.tsx.

    Doesn't assume the AI kept the static template's `icons` variable name —
    scans every top-level `const X = { ... }` object literal (brace/string
    aware, since JSX values contain their own braces) and returns the body
    span of the first one that actually contains SVG markup, which
    disambiguates it from unrelated objects like a shared `stroke` props
    object. Returns None if no such map can be found.
    """
    for m in _ICON_MAP_DECL_RE.finditer(content):
        start = m.end()
        depth = 1
        i = start
        in_str: str | None = None
        while i < len(content) and depth > 0:
            ch = content[i]
            if in_str:
                if ch == "\\":
                    i += 1
                elif ch == in_str:
                    in_str = None
            elif ch in ("'", '"', "`"):
                in_str = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            i += 1
        end = i - 1
        if end <= start:
            continue
        if "<svg" in content[start:end]:
            return start, end
    return None


def _icon_map_keys(body: str) -> set[str]:
    keys: set[str] = set()
    for km in _ICON_MAP_KEY_RE.finditer(body):
        key = km.group(1) or km.group(2) or km.group(3)
        if key:
            keys.add(key.strip().lower())
    return keys


def ensure_ui_icon_coverage(workspace) -> list[str]:
    """Guarantee every `<UiIcon name="...">` usage has a matching entry in the
    generated UiIcons.tsx icon map.

    AI-authored icon sets sometimes omit keys that pages actually reference
    (e.g. a page uses `name="dashboard"` but the generated set only defines
    `gauge`) — the lookup then silently renders nothing for that slot: the
    build still passes, the icon is just blank space. This appends a generic
    fallback shape for any missing key (reusing the file's own stroke-prop
    styling when detectable) so every reference renders SOMETHING instead of
    empty space. Purely additive — never touches or removes existing icons.
    """
    target = "src/components/UiIcons.tsx"
    content = read_file(workspace, target)
    if not content.strip():
        return []

    used = _collect_ui_icon_usages(workspace)
    if not used:
        return []

    found = _find_icon_map(content)
    if not found:
        return []
    body_start, body_end = found
    defined = _icon_map_keys(content[body_start:body_end])

    missing = sorted(n for n in used if n and n not in defined and n != "default")
    if not missing:
        return []

    stroke_match = re.search(r"\{\.\.\.(\w+)\}", content)
    stroke_attrs = (
        f"{{...{stroke_match.group(1)}}}" if stroke_match else
        'fill="none" stroke="currentColor" strokeWidth={1.75} '
        'strokeLinecap="round" strokeLinejoin="round"'
    )
    additions = "".join(
        f"  '{key}': (\n"
        f"    <svg viewBox=\"0 0 24 24\" {stroke_attrs}>\n"
        f"      <circle cx=\"12\" cy=\"12\" r=\"8\" />\n"
        f"    </svg>\n"
        f"  ),\n"
        for key in missing
    )
    # `content[:body_end]` ends wherever the last existing entry's value ends
    # — if the AI didn't write a trailing comma after it (valid JS either
    # way, but ours needs one before splicing in more entries), gluing
    # `additions` on directly would concatenate two expressions with no
    # separator (`)\n  'x': (` — invalid object-literal syntax). Detect that
    # and insert the missing comma ourselves rather than assuming it's there.
    head = content[:body_end]
    head_trimmed = head.rstrip()
    if head_trimmed and not head_trimmed.endswith((",", "{")):
        head = head_trimmed + ",\n"
    updated = head + additions + content[body_end:]
    write_file(workspace, target, updated)
    return [f"UiIcons.tsx (+{len(missing)} icon key{'s' if len(missing) != 1 else ''}: {', '.join(missing)})"]


def ensure_ui_icons(workspace) -> bool:
    """Ensure UiIcons exists and exports a default (pages use `import UiIcon from ...`)."""
    target = "src/components/UiIcons.tsx"
    content = read_file(workspace, target).strip()
    changed = False
    if not content:
        source = settings.PREVIEW_TEMPLATE_DIR / "src" / "components" / "UiIcons.tsx"
        if not source.is_file():
            return False
        content = source.read_text(encoding="utf-8")
        changed = True
    if "export default UiIcon" not in content and "export function UiIcon" in content:
        content = content.rstrip() + "\n\nexport default UiIcon;\n"
        changed = True
    # Pages sometimes do `import { UiIcon }` — expose a named export too.
    if "export default UiIcon" in content and "export { UiIcon }" not in content:
        content = content.rstrip() + "\nexport { UiIcon };\n"
        changed = True
    if changed:
        write_file(workspace, target, content)
    return changed


_NAMED_UIICON_IMPORT_RE = re.compile(
    r"""import\s*\{\s*UiIcon\s*\}\s*from\s*(['"][^'"]*UiIcons['"])\s*;?""",
    re.MULTILINE,
)


def normalize_ui_icon_imports(workspace) -> list[str]:
    """Rewrite `import { UiIcon } from '...UiIcons'` → default import."""
    fixed: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")):
            continue
        content = read_file(workspace, rel)
        new_content, n = _NAMED_UIICON_IMPORT_RE.subn(
            r"import UiIcon from \1;",
            content,
        )
        if n:
            write_file(workspace, rel, new_content)
            fixed.append(norm)
    return fixed


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
        fixed.extend(normalize_ui_icon_imports(workspace))
    except Exception as e:
        print(f"    ui icon import normalize skipped: {e}", flush=True)
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
