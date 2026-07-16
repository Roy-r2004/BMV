"""Runtime-correctness guards for generated preview apps.

These are pure plumbing (make the AI's app actually render when served under a
sub-path with Tailwind) — NOT UI/content shaping. Build success alone can't
catch these because a missing basename or Tailwind import still compiles fine.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import date, timedelta
from pathlib import Path, PurePosixPath

from app.core.config import settings
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.application.preview_app.protected_paths import (
    has_catalogue_routes,
    is_template_owned_path,
    restore_template_owned_files,
    snapshot_template_owned_files,
)
from app.application.preview_app.catalogue_contract import (
    catalogue_route_for_file,
    enforce_catalogue_page_contract,
)
from app.application.preview_app.workspace import (
    list_source_files,
    read_file,
    write_file,
    write_trusted_contained_file,
)
from app.application.preview_app.theme import sanitize_theme_inputs
from app.application.ui_catalogue import load_catalogue

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


# Marker used by auto-seeded list stubs — also detects thin stubs that need
# date/schedule fields so pages calling `new Date(row.date)` don't throw.
_SEEDED_STUB_DETAIL_MARKER = "record for demo lists"
_DATE_FIELD_KEYS = (
    "date",
    "dropOffDate",
    "startDate",
    "scheduledAt",
    "createdAt",
    "timestamp",
)


def _seeded_list_export(name: str, brand_name: str) -> str:
    """3–6 realistic rows so pages never render empty lists from auto-exports.

    Includes ISO date/time fields — generated ops dashboards often call
    `dateFormatter.format(new Date(session.date))` and crash on missing dates
    with RangeError: Invalid time value.
    """
    brand = brand_name or "Brand"
    label = re.sub(r"([A-Z])", r" \1", name).strip() or name
    today = date.today()
    load_types = ("Bisque", "Glaze", "Cone 6", "Raku")
    instructors = ("Maya R.", "Jordan K.", "Sam T.", "Noa B.")
    rows = []
    for i in range(1, 5):
        day = today + timedelta(days=i - 1)
        iso = day.isoformat()
        hh = 9 + (i % 8)
        mm = "00" if i % 2 else "30"
        hhmm = f"{hh:02d}:{mm}"
        hhmmss = f"{hhmm}:00"
        scheduled = f"{iso}T{hhmmss}"
        registered = 4 + i
        capacity = 12
        rows.append(
            {
                "id": f"{name.lower()}-{i}",
                "name": f"{label} {i}",
                "title": f"{label} {i}",
                "label": f"{label} {i}",
                "status": ["Open", "In progress", "Done", "Scheduled"][i % 4],
                "detail": f"Sample {brand} {_SEEDED_STUB_DETAIL_MARKER}",
                "message": f"{label} update {i}",
                "amount": 40 + i * 12,
                "count": 3 + i,
                # Schedule / booking fields (admin dashboards, kiln, classes)
                "date": iso,
                "time": hhmm,
                "startDate": iso,
                "endDate": iso,
                "dropOffDate": iso,
                "dropOffTime": hhmm,
                "pickupDate": (day + timedelta(days=2)).isoformat(),
                "scheduledAt": scheduled,
                "createdAt": scheduled,
                "timestamp": scheduled,
                "instructor": instructors[(i - 1) % len(instructors)],
                "memberName": f"Member {i}",
                "loadType": load_types[(i - 1) % len(load_types)],
                "registered": registered,
                "capacity": capacity,
                "isFull": registered >= capacity,
            }
        )
    return json.dumps(rows, ensure_ascii=False)


def _mock_export_value_end(src: str, start: int) -> int:
    """Return index just past the value (and optional `;`) of an export const."""
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


_LIST_EXPORT_RE = re.compile(
    r"export\s+const\s+([A-Za-z_$][\w$]*)\s*=\s*",
    re.MULTILINE,
)


def enrich_date_starved_mock_exports(workspace, brand_name: str) -> list[str]:
    """Rewrite thin auto-seeded list stubs that lack ISO date fields.

    Older stubs only had id/name/title/status/amount/count. Pages that do
    `new Date(row.date)` then throw RangeError: Invalid time value at runtime.
    """
    mock_path = "src/data/mock.ts"
    mock = read_file(workspace, mock_path)
    if not mock.strip():
        return []

    skip = {
        "roles",
        "navigation",
        "images",
        "brand",
        "design_system",
        "designsystem",
        "manifest",
        "brand_manifest",
        "brandmanifest",
        "brand_name",
        "brandname",
        "owner_name",
        "ownername",
    }
    replaced: list[str] = []
    matches = list(_LIST_EXPORT_RE.finditer(mock))
    for m in reversed(matches):
        name = m.group(1)
        if name.lower().replace("_", "") in skip:
            continue
        val_start = m.end()
        val_end = _mock_export_value_end(mock, val_start)
        current = mock[val_start:val_end].strip().rstrip(";").strip()
        if not current.startswith("["):
            continue
        if _SEEDED_STUB_DETAIL_MARKER not in current:
            continue
        # Already has schedule fields — leave alone (idempotent).
        if any(f'"{k}"' in current or f"'{k}'" in current for k in _DATE_FIELD_KEYS):
            continue
        seeded = _seeded_list_export(name, brand_name)
        mock = mock[:val_start] + seeded + ";" + mock[val_end:]
        replaced.append(name)

    if replaced:
        write_file(workspace, mock_path, mock)
    return list(reversed(replaced))


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
    if low in ("manifest", "brand_manifest", "brandmanifest"):
        # Pages read manifest.brand_name / manifest.accent / manifest.design_system.*
        # — an array stub white-screens the whole route.
        return json.dumps(
            {
                "brand_name": brand_name or "Brand",
                "name": brand_name or "Brand",
                "tagline": "",
                "accent": primary,
                "design_system": _design_system_dict(primary, secondary, font),
            },
            ensure_ascii=False,
        )
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


def _toplevel_string_array(mock: str, name: str) -> list[str] | None:
    """Parse `export const name = ["a", "b"]` if present; else None."""
    m = re.search(
        rf"export\s+const\s+{re.escape(name)}\s*=\s*\[([\s\S]*?)\];",
        mock,
    )
    if not m:
        return None
    vals = re.findall(r"""["']([^"']+)["']""", m.group(1))
    return vals or None


def _default_client_names(brand_name: str) -> list[str]:
    label = (brand_name or "Brand").split()[0]
    return [
        f"Maya {label}",
        "Jordan Cohen",
        "Sam Levi",
        "Noa Ben-David",
        "Alex Mizrahi",
        "Dana Peretz",
    ]


# Usage-driven brand contract (scalable — not field-name hardcoding).
MAX_BRAND_ARRAY_LEN = 12
DEFAULT_DYNAMIC_ARRAY_LEN = 3

# brand.services[2].name  |  brand?.client_names[i]  |  brand.design_system.primary_color
_BRAND_ACCESS_RE = re.compile(
    r"""\bbrand(?P<chain>(?:(?:\s*\?\.\s*|\s*\.\s*)[A-Za-z_][A-Za-z0-9_]*|\s*\[\s*(?:\d+|[A-Za-z_][A-Za-z0-9_]*)\s*\])+)"""
)
_BRAND_CHAIN_PART_RE = re.compile(
    r"""(?:\?\.)\s*([A-Za-z_][A-Za-z0-9_]*)"""
    r"""|\.\s*([A-Za-z_][A-Za-z0-9_]*)"""
    r"""|\[\s*(\d+)\s*\]"""
    r"""|\[\s*([A-Za-z_][A-Za-z0-9_]*)\s*\]"""
)


def _strip_ts_comments_and_strings(src: str) -> str:
    """Replace comments and string/template literal contents with spaces.

    Keeps newlines so line structure stays stable. Conservative — does not
    evaluate code. Used only to avoid matching `brand.foo` inside comments/strings.
    """
    out: list[str] = []
    i = 0
    n = len(src)
    while i < n:
        ch = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            while i < n and src[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if ch == "/" and nxt == "*":
            out.append(" ")
            out.append(" ")
            i += 2
            while i < n - 1 and not (src[i] == "*" and src[i + 1] == "/"):
                out.append("\n" if src[i] == "\n" else " ")
                i += 1
            if i < n - 1:
                out.append(" ")
                out.append(" ")
                i += 2
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            out.append(" ")
            i += 1
            while i < n:
                c = src[i]
                if c == "\\" and i + 1 < n:
                    out.append(" ")
                    out.append(" ")
                    i += 2
                    continue
                if c == quote:
                    out.append(" ")
                    i += 1
                    break
                out.append("\n" if c == "\n" else " ")
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _parse_brand_chain(chain: str) -> tuple:
    """Return segments: strings for props, ints for numeric indexes, '*' for dynamic indexes."""
    parts: list = []
    for m in _BRAND_CHAIN_PART_RE.finditer(chain or ""):
        if m.group(1):
            parts.append(m.group(1))
        elif m.group(2):
            parts.append(m.group(2))
        elif m.group(3):
            parts.append(int(m.group(3)))
        elif m.group(4):
            parts.append("*")
    return tuple(parts)


def normalize_brand_path(parts: tuple) -> str:
    """Normalize a parsed chain to `brand.foo[].bar` form."""
    if not parts:
        return "brand"
    bits = ["brand"]
    for p in parts:
        if isinstance(p, int) or p == "*":
            bits.append("[]")
        else:
            bits.append(str(p))
    # Join: brand + .prop or [] without extra dots before []
    out = bits[0]
    for b in bits[1:]:
        if b == "[]":
            out += "[]"
        else:
            out += f".{b}"
    return out


def collect_brand_property_paths(workspace) -> set[tuple]:
    """Scan TS/TSX for `brand.foo` / `brand.foo[i].bar` usage paths (deduped).

    Ignores matches inside comments and string literals where possible.
    Does not evaluate generated code.
    """
    found: set[tuple] = set()
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts", ".jsx", ".js")):
            continue
        if norm.startswith("src/data/"):
            continue
        raw = read_file(workspace, rel)
        text = _strip_ts_comments_and_strings(raw)
        for m in _BRAND_ACCESS_RE.finditer(text):
            parts = _parse_brand_chain(m.group("chain"))
            if parts and all(
                isinstance(p, (str, int)) or p == "*" for p in parts
            ):
                # Drop unsupported empty / malformed chains
                if isinstance(parts[0], str):
                    found.add(parts)
    return found


# Back-compat alias used by earlier drafts / tests
collect_brand_usage_paths = collect_brand_property_paths


def _brand_scalar_default(field: str, brand_name: str, primary: str) -> object:
    """Small stable schema library — keyed by field *role*, not product field lists."""
    fl = (field or "").lower()
    name = brand_name or "Brand"
    if "color" in fl or fl in {"accent", "primary", "secondary"}:
        return primary or "#6366f1"
    if fl in {"price", "amount", "revenue", "cost", "count", "qty", "quantity"}:
        return 0
    if fl in {"rating", "score", "stars"}:
        return 5
    if fl in {"name", "title", "label", "heading"}:
        return f"{name} item"
    if fl in {"description", "text", "quote", "detail", "summary", "bio"}:
        return f"Sample {field} for {name}."
    if fl in {"image", "img", "url", "href", "link", "path", "src", "photo"}:
        return ""
    if fl in {"badge", "status", "role", "category", "type", "tag"}:
        return "Demo"
    if fl in {"initials"}:
        return "AA"
    if fl in {"duration", "time", "date", "timestamp"} or fl.endswith("_at"):
        return "30 min" if fl == "duration" else "Today"
    if fl in {"email"}:
        return "client@example.com"
    if fl in {"phone"}:
        return "+1 555 0100"
    return f"Sample {field}"


def _infer_brand_requirements(paths: set[tuple]) -> dict[str, dict]:
    """Group usage paths by top-level brand key → array/object requirements."""
    reqs: dict[str, dict] = {}
    for path in paths:
        if not path or not isinstance(path[0], str):
            continue
        top = path[0]
        rest = path[1:]
        req = reqs.setdefault(
            top,
            {"min_len": 0, "item_fields": set(), "object_fields": set(), "is_array": False},
        )
        idx_at = next((i for i, p in enumerate(rest) if p == "*" or isinstance(p, int)), None)
        if idx_at is None:
            for p in rest:
                if isinstance(p, str):
                    req["object_fields"].add(p)
            continue
        req["is_array"] = True
        idx = rest[idx_at]
        if isinstance(idx, int):
            # Cap — never grow to brand.foo[999]
            req["min_len"] = max(req["min_len"], min(idx + 1, MAX_BRAND_ARRAY_LEN))
        else:
            req["min_len"] = max(req["min_len"], DEFAULT_DYNAMIC_ARRAY_LEN)
        for p in rest[idx_at + 1 :]:
            if isinstance(p, str):
                req["item_fields"].add(p)
    for req in reqs.values():
        if req["is_array"]:
            req["min_len"] = min(max(req["min_len"], DEFAULT_DYNAMIC_ARRAY_LEN), MAX_BRAND_ARRAY_LEN)
    return reqs


def _contract_type_label(req: dict) -> str:
    if req["is_array"] and req["item_fields"]:
        fields = ",".join(sorted(req["item_fields"])[:4])
        return f"Array<{{{fields}}}>"
    if req["is_array"]:
        return "string[]"
    if req["object_fields"]:
        fields = ",".join(sorted(req["object_fields"])[:4])
        return f"{{{fields}}}"
    return "unknown"


def _default_brand_top_value(
    key: str,
    req: dict,
    brand_name: str,
    primary: str,
    secondary: str,
    font: str,
    mock: str,
) -> object:
    name = brand_name or "Brand"
    if key in {"design_system", "designSystem"} or (
        req["object_fields"] and not req["is_array"] and "system" in key.lower()
    ):
        base = _design_system_dict(primary, secondary, font) if "design" in key.lower() else {}
        for field in req["object_fields"]:
            if field not in base:
                base[field] = _brand_scalar_default(field, name, primary)
        return base

    if req["is_array"]:
        n = min(req["min_len"], MAX_BRAND_ARRAY_LEN)
        fields = sorted(req["item_fields"])
        if not fields:
            existing = _toplevel_string_array(mock, key)
            if existing:
                vals = list(existing)
                while len(vals) < n:
                    vals.append(f"Client {len(vals) + 1}")
                return vals[:MAX_BRAND_ARRAY_LEN]
            if key.lower() in {"client_names", "clientnames", "customers", "patients"}:
                vals = _default_client_names(name)
                while len(vals) < n:
                    vals.append(f"Client {len(vals) + 1}")
                return vals[:MAX_BRAND_ARRAY_LEN]
            return [f"Item {i + 1}" for i in range(n)]
        return [
            {f: _brand_scalar_default(f, name, primary) for f in fields}
            for _ in range(n)
        ]

    if req["object_fields"]:
        return {
            f: _brand_scalar_default(f, name, primary) for f in sorted(req["object_fields"])
        }
    return name if key in {"name", "brand_name", "owner_name"} else {}


def _brand_has_top_key(body: str, key: str) -> bool:
    return re.search(rf"(?:^|[,{{\s]){re.escape(key)}\s*:", body) is not None


def _find_brand_prop_span(body: str, key: str) -> tuple[int, int] | None:
    """Return [value_start, value_end) for a top-level `key:` inside brand body."""
    m = re.search(rf"(?:^|[,{{\s])({re.escape(key)}\s*:)", body)
    if not m:
        m = re.search(rf"(?:^|\n)\s*({re.escape(key)}\s*:)", body)
    if not m:
        return None
    key_match = re.search(rf"{re.escape(key)}\s*:", body[m.start() :])
    if not key_match:
        return None
    val_start = m.start() + key_match.end()
    while val_start < len(body) and body[val_start] in " \t\n\r":
        val_start += 1
    if val_start >= len(body):
        return None
    j = val_start
    if body[j] in "\"'":
        quote = body[j]
        j += 1
        while j < len(body):
            if body[j] == "\\":
                j += 2
                continue
            if body[j] == quote:
                j += 1
                break
            j += 1
        return val_start, j
    if body[j] in "{[":
        opener = body[j]
        closer = "}" if opener == "{" else "]"
        depth = 1
        j += 1
        in_s = None
        esc = False
        while j < len(body) and depth:
            ch = body[j]
            if in_s:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == in_s:
                    in_s = None
            else:
                if ch in ("'", '"', "`"):
                    in_s = ch
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
            j += 1
        return val_start, j
    while j < len(body) and body[j] not in ",\n}":
        j += 1
    return val_start, j


def _count_array_items(array_src: str) -> int:
    """Count top-level elements in a TS array literal."""
    s = array_src.strip()
    if not s.startswith("["):
        return 0
    # Prefer object-item count when present
    obj_count = 0
    depth = 0
    in_s = None
    esc = False
    for i, ch in enumerate(s):
        if in_s:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == in_s:
                in_s = None
            continue
        if ch in ("'", '"', "`"):
            in_s = ch
            continue
        if ch == "{":
            if depth == 1:  # inside outer [
                obj_count += 1
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
    if obj_count:
        return obj_count
    return len(re.findall(r"""["'][^"']+["']""", s))


def _pad_array_literal(
    array_src: str,
    need: int,
    item_fields: set[str],
    brand_name: str,
    primary: str,
) -> str:
    need = min(need, MAX_BRAND_ARRAY_LEN)
    have = _count_array_items(array_src)
    if have >= need:
        return array_src  # never overwrite / never shrink
    pads = []
    for i in range(have, need):
        if item_fields:
            obj = {f: _brand_scalar_default(f, brand_name, primary) for f in sorted(item_fields)}
            pads.append(json.dumps(obj, ensure_ascii=False))
        else:
            pads.append(json.dumps(f"Item {i + 1}", ensure_ascii=False))
    core = array_src.rstrip()
    if not core.endswith("]"):
        return array_src
    inner = core[:-1].rstrip().rstrip(",")
    addition = (",\n    " if inner.strip() not in {"", "["} else "") + ",\n    ".join(pads)
    return inner + addition + "\n  ]"


def _inject_object_fields(obj_src: str, fields: set[str], brand_name: str, primary: str) -> str:
    """Add missing keys into a TS object literal `{ ... }` — never removes existing keys."""
    if not obj_src.strip().startswith("{"):
        return obj_src
    missing = [f for f in sorted(fields) if not re.search(rf"(?:^|[,{{\s]){re.escape(f)}\s*:", obj_src)]
    if not missing:
        return obj_src
    pieces = [
        f"{f}: {json.dumps(_brand_scalar_default(f, brand_name, primary), ensure_ascii=False)}"
        for f in missing
    ]
    core = obj_src.rstrip()
    if not core.endswith("}"):
        return obj_src
    inner = core[:-1].rstrip().rstrip(",")
    addition = (",\n    " if inner.strip() not in {"", "{"} else "") + ",\n    ".join(pieces)
    return inner + addition + "\n  }"


def ensure_brand_paths(
    mock: str,
    paths: set[tuple] | list[tuple],
    *,
    brand_name: str = "Brand",
    primary: str = "#6366f1",
    secondary: str = "#0d9488",
    font: str = "Inter",
) -> tuple[str, list[str]]:
    """Ensure `brand` in mock.ts satisfies scanned usage paths.

    Returns `(updated_mock, contract_log_lines)`. Never overwrites valid existing
    values — only injects missing keys / pads arrays up to MAX_BRAND_ARRAY_LEN.
    Deterministic. No LLM.
    """
    path_set = set(paths or [])
    if not mock.strip() or not path_set:
        return mock, []

    reqs = _infer_brand_requirements(path_set)
    span = _brand_object_span(mock)
    if not span:
        return mock, []
    body_start, close_at = span
    body = mock[body_start:close_at]
    logs: list[str] = []
    injections: list[str] = []

    for key, req in sorted(reqs.items()):
        type_label = _contract_type_label(req)
        path_label = normalize_brand_path(
            (key, "*", *sorted(req["item_fields"])) if req["is_array"] and req["item_fields"]
            else (key, "*") if req["is_array"]
            else (key, *sorted(req["object_fields"])) if req["object_fields"]
            else (key,)
        )

        if not _brand_has_top_key(body, key):
            value = _default_brand_top_value(
                key, req, brand_name, primary, secondary, font, mock,
            )
            injections.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
            logs.append(f"contract: ensured {path_label} as {type_label}")
            continue

        prop = _find_brand_prop_span(body, key)
        if not prop:
            continue
        val_start, val_end = prop
        current = body[val_start:val_end]

        if req["is_array"] and current.lstrip().startswith("["):
            padded = _pad_array_literal(
                current, req["min_len"], req["item_fields"], brand_name, primary,
            )
            if padded != current:
                body = body[:val_start] + padded + body[val_end:]
                logs.append(
                    f"contract: ensured {path_label} as {type_label} "
                    f"(padded to {min(req['min_len'], MAX_BRAND_ARRAY_LEN)})"
                )
                mock = mock[:body_start] + body + mock[close_at:]
                span = _brand_object_span(mock)
                if not span:
                    break
                body_start, close_at = span
                body = mock[body_start:close_at]
            continue

        if req["object_fields"] and current.lstrip().startswith("{"):
            enriched = _inject_object_fields(
                current, req["object_fields"], brand_name, primary,
            )
            if enriched != current:
                body = body[:val_start] + enriched + body[val_end:]
                logs.append(f"contract: ensured {path_label} as {type_label}")
                mock = mock[:body_start] + body + mock[close_at:]
                span = _brand_object_span(mock)
                if not span:
                    break
                body_start, close_at = span
                body = mock[body_start:close_at]

    if injections:
        patch = ",\n  ".join(injections)
        span = _brand_object_span(mock)
        if span:
            _body_start, close_at = span
            before = mock[:close_at].rstrip()
            if before.endswith(","):
                injection = f"\n  {patch},\n"
            else:
                injection = f",\n  {patch},\n"
            mock = mock[:close_at] + injection + mock[close_at:]

    return mock, logs


def ensure_brand_usage_paths(
    workspace,
    brand_name: str,
    primary: str,
    secondary: str,
    font: str,
) -> list[str]:
    """Workspace wrapper: collect paths → ensure_brand_paths → write mock.ts."""
    paths = collect_brand_property_paths(workspace)
    if not paths:
        return []
    mock_path = "src/data/mock.ts"
    mock = read_file(workspace, mock_path)
    if not mock.strip():
        return []
    updated, logs = ensure_brand_paths(
        mock,
        paths,
        brand_name=brand_name,
        primary=primary,
        secondary=secondary,
        font=font,
    )
    if updated != mock:
        write_file(workspace, mock_path, updated)
    for line in logs:
        print(f"    {line}", flush=True)
    return logs



def _brand_completeness_patch(
    brand_name: str,
    primary: str,
    secondary: str,
    font: str,
    *,
    client_names: list[str] | None = None,
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
        {
            "name": "Follow-up visit",
            "title": "Follow-up visit",
            "description": "Quick check-in to fine-tune results and keep your plan on track.",
            "image": "",
            "badge": "Care",
            "price": 120,
            "duration": "30 min",
        },
    ]
    testimonials = [
        {
            "name": "Maya R.",
            "initials": "MR",
            "quote": f"Finally a {name} experience that feels personal — the AI consult nailed what I needed.",
            "text": f"Finally a {name} experience that feels personal — the AI consult nailed what I needed.",
            "role": "Client",
            "rating": 5,
        },
        {
            "name": "Jordan K.",
            "initials": "JK",
            "quote": "Booking and aftercare in one place. No more chasing answers on chat.",
            "text": "Booking and aftercare in one place. No more chasing answers on chat.",
            "role": "Member",
            "rating": 5,
        },
        {
            "name": "Sam T.",
            "initials": "ST",
            "quote": "The owner hub's no-show risk view alone paid for itself in a week.",
            "text": "The owner hub's no-show risk view alone paid for itself in a week.",
            "role": "Owner",
            "rating": 5,
        },
    ]
    design = _design_system_dict(primary, secondary, font)
    names = client_names or _default_client_names(name)
    return (
        f"design_system: {json.dumps(design, ensure_ascii=False)},\n"
        f"  services: {json.dumps(services, ensure_ascii=False)},\n"
        f"  testimonials: {json.dumps(testimonials, ensure_ascii=False)},\n"
        f"  client_names: {json.dumps(names, ensure_ascii=False)},\n"
        f"  social_proof: {json.dumps(f'Trusted by over 2,400 delighted {name} clients.', ensure_ascii=False)}"
    )


def ensure_brand_shape(
    workspace,
    brand_name: str,
    primary: str,
    secondary: str,
    font: str,
) -> bool:
    """Guarantee missing brand nested fields so home/ops pages don't crash white.

    AI pages often read `brand.design_system.primary_color`, `brand.services[i].name`,
    and `brand.client_names[i]`. Only inject fields that are actually missing —
    re-injecting `services` when it already exists creates duplicate object keys
    (last wins) and can shrink a 4-item AI list to a 3-item stub, crashing on
    `brand.services[3].name`.
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
    needs_client_names = not re.search(r"\bclient_names\s*:", body)
    if not (needs_ds or needs_services or needs_testimonials or needs_proof or needs_client_names):
        return False

    names = _toplevel_string_array(mock, "client_names") or _default_client_names(brand_name)
    testimonial_count = len(re.findall(r"\binitials\s*:|\bquote\s*:|\btext\s*:", body))
    while len(names) < max(8, testimonial_count, 3):
        names.append(f"Client {len(names) + 1}")

    # Build a full patch once, then keep only the missing keys (avoids duplicate-key overwrite).
    full = _brand_completeness_patch(
        brand_name, primary, secondary, font, client_names=names,
    )
    keep: list[str] = []
    if needs_ds:
        keep.append("design_system")
    if needs_services:
        keep.append("services")
    if needs_testimonials:
        keep.append("testimonials")
    if needs_client_names:
        keep.append("client_names")
    if needs_proof:
        keep.append("social_proof")

    pieces: list[str] = []
    for key in keep:
        # Match `key: <value>` through the next top-level key or end.
        m = re.search(
            rf"(?:^|\n)\s*({re.escape(key)}\s*:\s*)([\s\S]*?)(?=(?:\n\s*(?:design_system|services|testimonials|client_names|social_proof)\s*:)|$)",
            "\n" + full,
        )
        if m:
            pieces.append(m.group(1) + m.group(2).rstrip().rstrip(","))
        elif key == "client_names":
            pieces.append(f"client_names: {json.dumps(names, ensure_ascii=False)}")

    if not pieces:
        return False

    patch = ",\n  ".join(pieces)
    before = mock[:close_at].rstrip()
    if before.endswith(","):
        injection = f"\n  {patch},\n"
    else:
        injection = f",\n  {patch},\n"
    updated = mock[:close_at] + injection + mock[close_at:]
    write_file(workspace, mock_path, updated)
    return True


_TYPED_MOCK_EXPORT_RE = re.compile(
    r"export\s+const\s+(brand_name|brandName|owner_name|ownerName|design_system|designSystem|manifest|brandManifest|brand_manifest)\s*=\s*",
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
        elif low in ("manifest", "brandmanifest"):
            # A brand spread alias or an object carrying design_system is fine;
            # only arrays / unrelated shapes get rewritten.
            if current.startswith("[") or (
                "design_system" not in current and "...brand" not in current
            ):
                manifest_value = _default_export_value(
                    "manifest", {}, {}, {}, brand_name, primary, secondary, font
                )
                mock = mock[:val_start] + f"{manifest_value};" + mock[val_end:]
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
}
_CURATED_UI_NPM_IMPORTS = {
    "react",
    "react-dom",
    "react-router-dom",
    "clsx",
    "tailwind-merge",
    "class-variance-authority",
    "recharts",
    "@tanstack/react-table",
    "@radix-ui/react-dialog",
    "@radix-ui/react-select",
    "@radix-ui/react-tabs",
    "@radix-ui/react-tooltip",
    "motion",
    "lucide-react",
    "sonner",
    "date-fns",
}
# Packages we cannot install in preview apps — rewrite imports to local stubs
# instead of deleting them (deleting left Transition/Dialog undefined → white screen).
_STUBBED_NPM_IMPORTS = {
    "@headlessui/react": "src/components/UiHeadless",
    "@headlessui/react/dist": "src/components/UiHeadless",
}
_IMPORT_FROM_RE = re.compile(
    r"""^\s*import\s+(?:type\s+)?(?:[\s\S]*?)\s+from\s+['"]([^'"]+)['"]\s*;?\s*(?://.*)?$""",
    re.MULTILINE,
)
_SIDE_EFFECT_IMPORT_RE = re.compile(
    r"""^\s*import\s+['"]([^'"]+)['"]\s*;?\s*(?://.*)?$""",
    re.MULTILINE,
)
_FORBIDDEN_RUNTIME_IMPORT_LINE_RE = re.compile(
    r"""^[^\S\r\n]*(?:[^\r\n]*\b(?:require|import)\s*\([^\r\n]*"""
    r"""|import\s+[A-Za-z_$][\w$]*\s*=[^\r\n]*)"""
    r"""[^\r\n]*(?:\r?\n|$)""",
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
    text = source.read_text(encoding="utf-8")
    if (
        dest.is_file()
        and not dest.is_symlink()
        and dest.read_text(encoding="utf-8") == text
    ):
        return False
    write_trusted_contained_file(
        workspace,
        "src/components/UiHeadless.tsx",
        text,
    )
    return True


def _safe_workspace_destination(workspace, rel: str) -> Path:
    """Resolve an approved source destination without following escapes/symlink parents."""
    root = Path(workspace).resolve()
    normalized = rel.replace("\\", "/")
    if not (
        normalized.startswith("src/ui/")
        or normalized == "src/components/UiIcons.tsx"
        or normalized == "src/lib/preview-bridge.ts"
        or normalized == "src/lib/app-nav.ts"
        or normalized == "src/lib/recipe-id.ts"
        or normalized == "src/lib/recipe.ts"
    ):
        raise ValueError(f"Refusing non-kit restore path: {rel}")
    target = root.joinpath(*normalized.split("/"))
    parent = target.parent
    existing = parent
    while not existing.exists() and existing != root:
        existing = existing.parent
    if existing.is_symlink():
        raise ValueError(f"Refusing kit restore through symlink: {rel}")
    resolved_parent = existing.resolve()
    try:
        resolved_parent.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Refusing kit restore outside workspace: {rel}") from exc
    return target


def restore_curated_ui_kit(workspace) -> list[str]:
    """Restore the canonical template UI barrel and icon set into a workspace."""
    template_root = settings.PREVIEW_TEMPLATE_DIR.resolve()
    source_ui = template_root / "src" / "ui"
    source_icons = template_root / "src" / "components" / "UiIcons.tsx"
    required_files = (
        source_ui / "catalogue.json",
        source_ui / "registry.ts",
        source_ui / "index.ts",
        source_ui / "compose" / "SkeletonComposer.tsx",
        source_ui / "lib" / "AppLink.tsx",
        source_icons,
    )
    required_dirs = tuple(
        source_ui / name for name in ("core", "public", "ops", "motion", "lib")
    )
    missing = [
        str(path)
        for path in required_files
        if not path.is_file()
    ] + [
        str(path)
        for path in required_dirs
        if not path.is_dir()
    ]
    if missing:
        raise FileNotFoundError(
            "Canonical curated UI kit is incomplete; missing: "
            + ", ".join(missing)
        )

    root = Path(workspace).resolve()
    destination_ui = _safe_workspace_destination(root, "src/ui/index.ts").parent
    destination_icons = _safe_workspace_destination(root, "src/components/UiIcons.tsx")
    changed: list[str] = []

    canonical: dict[str, Path] = {}
    for source in sorted(path for path in source_ui.rglob("*") if path.is_file()):
        rel = "src/ui/" + source.relative_to(source_ui).as_posix()
        canonical[rel] = source

    if destination_ui.exists():
        for current in sorted(
            (path for path in destination_ui.rglob("*") if path.is_file() or path.is_symlink()),
            reverse=True,
        ):
            rel = "src/ui/" + current.relative_to(destination_ui).as_posix()
            if rel not in canonical:
                try:
                    if current.is_dir() and not current.is_symlink():
                        shutil.rmtree(current)
                    else:
                        current.unlink()
                except OSError as exc:
                    raise RuntimeError(
                        f"Failed to remove drifted curated UI path {rel}"
                    ) from exc
                changed.append(rel)

    for rel, source in canonical.items():
        try:
            destination = _safe_workspace_destination(root, rel)
            payload = source.read_bytes()
            if (
                destination.is_symlink()
                or not destination.is_file()
                or destination.read_bytes() != payload
            ):
                write_trusted_contained_file(root, rel, payload)
                changed.append(rel)
        except OSError as exc:
            raise RuntimeError(f"Failed to restore curated UI path {rel}") from exc

    try:
        icon_text = source_icons.read_text(encoding="utf-8")
        if (
            destination_icons.is_symlink()
            or not destination_icons.is_file()
            or destination_icons.read_text(encoding="utf-8") != icon_text
        ):
            write_trusted_contained_file(
                root,
                "src/components/UiIcons.tsx",
                icon_text,
            )
            changed.append("src/components/UiIcons.tsx")
    except OSError as exc:
        raise RuntimeError("Failed to restore curated UI icon set") from exc

    source_bridge = template_root / "src" / "lib" / "preview-bridge.ts"
    if not source_bridge.is_file():
        raise FileNotFoundError(
            f"Canonical preview bridge missing: {source_bridge}"
        )
    try:
        bridge_text = source_bridge.read_text(encoding="utf-8")
        destination_bridge = _safe_workspace_destination(
            root, "src/lib/preview-bridge.ts"
        )
        if (
            destination_bridge.is_symlink()
            or not destination_bridge.is_file()
            or destination_bridge.read_text(encoding="utf-8") != bridge_text
        ):
            write_trusted_contained_file(
                root,
                "src/lib/preview-bridge.ts",
                bridge_text,
            )
            changed.append("src/lib/preview-bridge.ts")
    except OSError as exc:
        raise RuntimeError("Failed to restore preview bridge") from exc

    source_app_nav = template_root / "src" / "lib" / "app-nav.ts"
    if source_app_nav.is_file():
        try:
            app_nav_text = source_app_nav.read_text(encoding="utf-8")
            destination_app_nav = _safe_workspace_destination(
                root, "src/lib/app-nav.ts"
            )
            if (
                destination_app_nav.is_symlink()
                or not destination_app_nav.is_file()
                or destination_app_nav.read_text(encoding="utf-8") != app_nav_text
            ):
                write_trusted_contained_file(
                    root,
                    "src/lib/app-nav.ts",
                    app_nav_text,
                )
                changed.append("src/lib/app-nav.ts")
        except OSError as exc:
            raise RuntimeError("Failed to restore shared app-nav helpers") from exc

    source_recipe_id = template_root / "src" / "lib" / "recipe-id.ts"
    if source_recipe_id.is_file():
        try:
            destination_recipe = _safe_workspace_destination(root, "src/lib/recipe-id.ts")
            if destination_recipe.is_symlink() or not destination_recipe.is_file():
                write_trusted_contained_file(
                    root,
                    "src/lib/recipe-id.ts",
                    source_recipe_id.read_text(encoding="utf-8"),
                )
                changed.append("src/lib/recipe-id.ts")
        except OSError as exc:
            raise RuntimeError("Failed to restore recipe-id bootstrap") from exc

    source_recipe = template_root / "src" / "lib" / "recipe.ts"
    if source_recipe.is_file():
        try:
            recipe_text = source_recipe.read_text(encoding="utf-8")
            destination_recipe_helpers = _safe_workspace_destination(root, "src/lib/recipe.ts")
            if (
                destination_recipe_helpers.is_symlink()
                or not destination_recipe_helpers.is_file()
                or destination_recipe_helpers.read_text(encoding="utf-8") != recipe_text
            ):
                write_trusted_contained_file(root, "src/lib/recipe.ts", recipe_text)
                changed.append("src/lib/recipe.ts")
        except OSError as exc:
            raise RuntimeError("Failed to restore recipe helpers") from exc

    return list(dict.fromkeys(changed))


_STATIC_UI_IMPORT_RE = re.compile(
    r"""^[ \t]*import[ \t]+(?P<clause>[^;'"`]+?)[ \t]+from[ \t]*"""
    r"""(?P<quote>['"])(?P<source>[^'"]+)(?P=quote)[ \t]*;?[ \t]*(?:\r?\n|$)""",
    re.MULTILINE,
)


def _is_ui_kit_source(source: str, from_file: str) -> bool:
    if source == "@/ui" or source.startswith("@/ui/"):
        return True
    component_names = {
        str(item.get("name") or "").lower()
        for item in load_catalogue().get("components") or []
    }
    source_stem = PurePosixPath(source).name.lower()
    if (
        source_stem in component_names
        and (
            source.startswith("@/components/ui/")
            or source.startswith("@/components/")
            or source.startswith("@/ui-components/")
        )
    ):
        return True
    if not source.startswith("."):
        return False
    base = PurePosixPath(from_file.replace("\\", "/")).parent
    joined = PurePosixPath(os.path.normpath(str(base / source)).replace("\\", "/")).as_posix()
    return (
        joined == "src/ui"
        or joined.startswith("src/ui/")
        or (
            source_stem in component_names
            and (
                joined.startswith("src/components/ui/")
                or joined.startswith("src/ui-components/")
            )
        )
    )


def _is_ui_barrel_source(source: str, from_file: str) -> bool:
    if source in {"@/ui", "@/ui/index"}:
        return True
    if not source.startswith("."):
        return False
    base = PurePosixPath(from_file.replace("\\", "/")).parent
    joined = PurePosixPath(os.path.normpath(str(base / source)).replace("\\", "/")).as_posix()
    return joined in {"src/ui", "src/ui/index"}


def _ui_barrel_exports() -> set[str]:
    """Read the canonical barrel's named exports for safe deep-import conversion."""
    source = settings.PREVIEW_TEMPLATE_DIR / "src" / "ui" / "index.ts"
    content = source.read_text(encoding="utf-8") if source.is_file() else ""
    exported: set[str] = {
        str(item.get("name") or "")
        for item in load_catalogue().get("components") or []
        if item.get("name")
    }
    for match in re.finditer(r"export\s*\{([\s\S]*?)\}\s*from\s*['\"]", content):
        for item in match.group(1).split(","):
            token = re.sub(r"^\s*type\s+", "", item.strip())
            if not token:
                continue
            exported_name = re.split(r"\s+as\s+", token)[-1].strip()
            if re.match(r"^[A-Za-z_$][\w$]*$", exported_name):
                exported.add(exported_name)
    return exported


def _split_ui_import_clause(
    clause: str,
    source: str,
    exports: set[str],
    *,
    barrel_source: bool,
) -> tuple[list[str], list[str], bool, bool, str]:
    """Return value/type specs, unsupported/preserve flags, and namespace alias."""
    raw = clause.strip()
    whole_type = raw.startswith("type ")
    if whole_type:
        raw = raw[5:].strip()

    namespace = re.fullmatch(r"\*\s+as\s+([A-Za-z_$][\w$]*)", raw)
    if namespace:
        if barrel_source and not whole_type:
            preserve = source == "@/ui"
            return [], [], False, preserve, "" if preserve else namespace.group(1)
        return [], [], True, False, ""

    default_name = ""
    named_body = ""
    if "{" in raw and "}" in raw:
        before, remainder = raw.split("{", 1)
        named_body = remainder.rsplit("}", 1)[0]
        default_name = before.strip().rstrip(",").strip()
    else:
        default_name = raw

    values: list[str] = []
    types: list[str] = []
    unsupported = False

    if default_name:
        if (
            whole_type
            or not re.match(r"^[A-Za-z_$][\w$]*$", default_name)
        ):
            unsupported = True
        else:
            exported_name = PurePosixPath(source).name.rsplit(".", 1)[0]
            if exported_name in exports:
                spec = (
                    exported_name
                    if default_name == exported_name
                    else f"{exported_name} as {default_name}"
                )
                values.append(spec)
            else:
                unsupported = True

    if named_body:
        for raw_item in named_body.split(","):
            item = raw_item.strip()
            if not item:
                continue
            item_type = whole_type or item.startswith("type ")
            if item.startswith("type "):
                item = item[5:].strip()
            parts = re.split(r"\s+as\s+", item, maxsplit=1)
            imported = parts[0].strip()
            local = parts[1].strip() if len(parts) == 2 else imported
            if (
                imported not in exports
                or not re.match(r"^[A-Za-z_$][\w$]*$", local)
            ):
                unsupported = True
                continue
            spec = imported if imported == local else f"{imported} as {local}"
            (types if item_type else values).append(spec)
    return values, types, unsupported, False, ""


def normalize_ui_kit_imports(workspace) -> list[str]:
    """Collapse representable UI imports to the barrel and remove unsafe deep forms."""
    touched: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")) or norm.startswith("src/ui/"):
            continue
        content = read_file(workspace, norm)
        matches = [
            match
            for match in _STATIC_UI_IMPORT_RE.finditer(content)
            if _is_ui_kit_source(match.group("source"), norm)
        ]
        if not matches:
            continue

        exports = _ui_barrel_exports()
        mergeable: list[tuple[re.Match, list[str], list[str], bool, str]] = []
        for match in matches:
            values, types, unsupported, root_namespace, namespace_alias = _split_ui_import_clause(
                match.group("clause"),
                match.group("source"),
                exports,
                barrel_source=_is_ui_barrel_source(match.group("source"), norm),
            )
            if root_namespace:
                continue
            mergeable.append((match, values, types, unsupported, namespace_alias))
        if not mergeable:
            continue

        value_names: list[str] = []
        type_names: list[str] = []
        namespace_names: list[str] = []
        unsupported = False
        for _match, values, types, invalid, namespace_alias in mergeable:
            unsupported = unsupported or invalid
            if namespace_alias and namespace_alias not in namespace_names:
                namespace_names.append(namespace_alias)
            for name in values:
                if name not in value_names:
                    value_names.append(name)
            for name in types:
                if name not in type_names:
                    type_names.append(name)

        if (
            len(mergeable) == 1
            and mergeable[0][0].group("source") == "@/ui"
            and not unsupported
        ):
            continue

        replacement_lines: list[str] = []
        replacement_lines.extend(
            f"import * as {name} from '@/ui';" for name in namespace_names
        )
        if value_names:
            replacement_lines.append(f"import {{ {', '.join(value_names)} }} from '@/ui';")
        if type_names:
            replacement_lines.append(f"import type {{ {', '.join(type_names)} }} from '@/ui';")
        if unsupported:
            replacement_lines.append("/* removed unsupported deep UI import */")
        replacement = "\n".join(replacement_lines)
        if replacement:
            replacement += "\n"

        pieces: list[str] = []
        cursor = 0
        for index, (match, _values, _types, _invalid, _namespace) in enumerate(mergeable):
            pieces.append(content[cursor:match.start()])
            if index == 0:
                pieces.append(replacement)
            cursor = match.end()
        pieces.append(content[cursor:])
        updated = "".join(pieces)
        write_file(workspace, norm, updated)
        touched.append(norm)
    return touched


def enforce_catalogue_workspace_contracts(
    workspace,
    architect: dict,
    brand_name: str,
) -> list[str]:
    """Replace only invalid assigned catalogue pages with deterministic scaffolds."""
    repaired: list[str] = []
    for rel in list_source_files(workspace):
        route = catalogue_route_for_file(rel, architect)
        if not route.get("skeleton_id"):
            continue
        content = read_file(workspace, rel)
        updated, changed = enforce_catalogue_page_contract(
            rel,
            content,
            architect,
            brand_name=brand_name,
        )
        if changed:
            write_file(workspace, rel, updated)
            repaired.append(rel)
    return repaired


def strip_forbidden_npm_imports(workspace) -> list[str]:
    """Rewrite stubbable illegal imports; strip the rest.

    Models often import @headlessui/react / framer-motion. Deleting those lines
    used to leave `<Transition>` / `<Dialog>` unbound → runtime white screen
    even though `vite build` succeeded. Stubbable packages are rewritten to
    `src/components/UiHeadless`; unknown packages are still stripped.

    Also strips side-effect CSS/JS imports (`import 'pkg/dist/x.css'`) which
    `_IMPORT_FROM_RE` does not match and which otherwise fail Vite resolve.
    """
    ensure_ui_headless_file(workspace)
    touched: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")):
            continue
        if norm.endswith("UiHeadless.tsx"):
            continue
        content = read_file(workspace, rel)
        updated = content
        changed = False

        template_ui = (
            norm.startswith("src/ui/")
            or norm.lower() == "src/components/uiicons.tsx"
        )

        def _should_keep(src: str) -> bool:
            if (
                src.startswith(".")
                or src.startswith("/")
                or src.startswith("@/")
                or src.startswith("~/")
            ):
                return True
            if src.startswith(("http://", "https://")):
                return False
            pkg = _npm_package_name(src)
            if template_ui:
                return pkg in _CURATED_UI_NPM_IMPORTS
            return pkg in _ALLOWED_NPM_IMPORTS or src in _ALLOWED_NPM_IMPORTS

        for m in list(_IMPORT_FROM_RE.finditer(content)):
            src = m.group(1)
            if _should_keep(src):
                continue
            pkg = _npm_package_name(src)
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
            old = m.group(0)
            if old in updated:
                updated = updated.replace(old, "/* removed forbidden import */\n", 1)
                changed = True

        for m in list(_SIDE_EFFECT_IMPORT_RE.finditer(updated)):
            src = m.group(1)
            if _should_keep(src):
                continue
            old = m.group(0)
            if old in updated:
                updated = updated.replace(old, "/* removed forbidden side-effect import */\n", 1)
                changed = True

        if not template_ui:
            scrubbed = _strip_ts_comments_and_strings(updated)
            spans = [
                (match.start(), match.end())
                for match in _FORBIDDEN_RUNTIME_IMPORT_LINE_RE.finditer(scrubbed)
            ]
            for start, end in reversed(spans):
                newline = "\n" if updated[start:end].endswith(("\n", "\r\n")) else ""
                updated = (
                    updated[:start]
                    + "/* removed forbidden runtime import */"
                    + newline
                    + updated[end:]
                )
                changed = True

        if changed and updated != content:
            write_file(workspace, norm, updated)
            print(f"    npm imports rewritten/stripped in {norm}", flush=True)
            touched.append(norm)
    return touched


def ensure_headless_stub_imports(workspace) -> list[str]:
    """Inject UiHeadless imports when Transition/Dialog/motion are used unbound.

    Covers the case where a prior build already stripped the headless import
    (comment left behind) and the page still references the symbols.
    """
    ensure_ui_headless_file(workspace)
    fixed: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")):
            continue
        if (
            norm.startswith("src/data/")
            or norm.startswith("src/ui/")
            or norm.endswith("UiHeadless.tsx")
            or norm.lower() == "src/components/uiicons.tsx"
        ):
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


def rewrite_invented_component_imports(workspace) -> list[str]:
    """Route generated deep UI imports through the curated public barrel."""
    return normalize_ui_kit_imports(workspace)


def sanitize_ui_component_apis(workspace) -> list[str]:
    """Remove a small set of known invented props without reshaping page content."""
    fixed: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith(".tsx") or norm.startswith("src/ui/"):
            continue
        content = read_file(workspace, norm)
        updated = re.sub(r"\s+Icon=\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", "", content)
        updated = re.sub(r'\bsize=(["\'])(?:xs|md|xl)\1', 'size="default"', updated)
        if updated != content:
            write_file(workspace, norm, updated)
            fixed.append(norm)
    return fixed


def unwrap_route_layout_wrappers(workspace, brand_name: str = "Brand") -> list[str]:
    """Replace page-local legacy layout wrappers with their matching kit shell."""
    fixed: list[str] = []
    wrapper_specs = {
        "PublicLayout": ("PublicShell", f'brandName={{{json.dumps(brand_name or "Brand")}}}'),
        "AdminLayout": (
            "OpsShell",
            f'brandName={{{json.dumps(brand_name or "Brand")}}} navItems={{[]}}',
        ),
    }
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if "/pages/" not in norm or not norm.endswith(".tsx"):
            continue
        content = read_file(workspace, norm)
        updated = content
        added_shells: list[str] = []
        for wrapper, (shell, props) in wrapper_specs.items():
            if not re.search(rf"<{wrapper}\b", updated):
                continue
            updated = re.sub(
                rf"^\s*import\s+{wrapper}\s+from\s+['\"][^'\"]+['\"]\s*;?\s*\n",
                "",
                updated,
                flags=re.MULTILINE,
            )
            updated = re.sub(rf"<{wrapper}(?:\s[^>]*)?>", f"<{shell} {props}>", updated)
            updated = updated.replace(f"</{wrapper}>", f"</{shell}>")
            added_shells.append(shell)
        if added_shells:
            existing = re.search(
                r"import\s*\{([^}]*)\}\s*from\s*['\"]@/ui['\"]\s*;?",
                updated,
            )
            if existing:
                names = [part.strip() for part in existing.group(1).split(",") if part.strip()]
                for shell in added_shells:
                    if shell not in names:
                        names.append(shell)
                replacement = "import { " + ", ".join(names) + " } from '@/ui';"
                updated = updated[:existing.start()] + replacement + updated[existing.end():]
            else:
                updated = (
                    "import { " + ", ".join(added_shells) + " } from '@/ui';\n" + updated
                )
        if updated != content:
            write_file(workspace, norm, updated)
            fixed.append(norm)
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
    from app.application.preview_app.design_recipes import get_recipe

    actions: list[str] = []
    catalogue_workspace = has_catalogue_routes(architect)
    if catalogue_workspace:
        actions.extend(restore_curated_ui_kit(workspace))
    protected_snapshot = snapshot_template_owned_files(workspace, architect)
    recipe = get_recipe(
        (plan or {}).get("recipe_id")
        or ((plan or {}).get("design_system") or {}).get("recipe_id")
        or (architect or {}).get("recipe_id")
    )
    for fn, label in (
        (lambda: sanitize_workspace_sources(workspace), "fences stripped"),
        (lambda: sanitize_data_files(workspace), "quotes escaped"),
        (lambda: fix_nested_import_paths(workspace), "import paths fixed"),
        (lambda: normalize_ui_kit_imports(workspace), "UI imports normalized"),
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
    if catalogue_workspace:
        try:
            repaired = enforce_catalogue_workspace_contracts(
                workspace,
                architect,
                brand_name,
            )
            actions.extend(repaired)
        except Exception as e:
            restore_template_owned_files(workspace, architect, protected_snapshot)
            raise RuntimeError(
                f"Catalogue contract enforcement failed before build: {e}"
            ) from e
    if not has_catalogue_routes(architect):
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
            named = ensure_named_ui_icon_exports(workspace)
            if named:
                actions.extend(named)
                print(f"    {named[0]}", flush=True)
        except Exception as e:
            print(f"    named ui icon exports guard skipped: {e}", flush=True)
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
        dated = enrich_date_starved_mock_exports(workspace, brand_name)
        if dated:
            actions.extend([f"mock-dates:{n}" for n in dated])
            print(f"    enriched date-starved mock exports: {', '.join(dated)}", flush=True)
    except Exception as e:
        print(f"    date-starved mock enrich skipped: {e}", flush=True)
    try:
        repaired = repair_typed_mock_exports(workspace, brand_name, primary, secondary, font)
        if repaired:
            actions.extend([f"mock-typed:{n}" for n in repaired])
            print(f"    repaired typed mock exports: {', '.join(repaired)}", flush=True)
    except Exception as e:
        print(f"    typed mock repair skipped: {e}", flush=True)
    try:
        if ensure_brand_shape(workspace, brand_name, primary, secondary, font):
            actions.append("src/data/mock.ts (brand shape fallback)")
            print(
                "    contract: hardcoded fallback ensure_brand_shape "
                "(design_system/services/testimonials/client_names as needed)",
                flush=True,
            )
    except Exception as e:
        print(f"    brand shape guard skipped: {e}", flush=True)
    try:
        usage = ensure_brand_usage_paths(workspace, brand_name, primary, secondary, font)
        if usage:
            actions.extend(usage)
    except Exception as e:
        print(f"    brand usage contract skipped: {e}", flush=True)
    try:
        src_main = settings.PREVIEW_TEMPLATE_DIR / "src" / "main.tsx"
        dst_main = Path(workspace) / "src" / "main.tsx"
        if src_main.is_file():
            text = src_main.read_text(encoding="utf-8")
            if "PreviewErrorBoundary" in text and (
                dst_main.is_symlink()
                or not dst_main.is_file()
                or "PreviewErrorBoundary" not in dst_main.read_text(encoding="utf-8")
            ):
                write_trusted_contained_file(workspace, "src/main.tsx", text)
                actions.append("src/main.tsx (error boundary)")
    except Exception as e:
        print(f"    main.tsx sync skipped: {e}", flush=True)
    try:
        write_index_css(
            workspace,
            primary,
            secondary,
            font,
            template_renderer,
            recipe=recipe,
            design_system=(plan or {}).get("design_system") or {},
        )
        write_app_tsx(workspace, architect, template_renderer)
        # App.tsx can introduce mock imports after the earlier contract pass.
        # Close that deterministic gap in the same guard invocation.
        actions.extend(
            ensure_mock_exports(workspace, architect, plan, images, brand_name)
        )
    except Exception as e:
        print(f"    assemble skipped: {e}", flush=True)
    if catalogue_workspace:
        try:
            from app.application.preview_app.chrome_nav import enforce_shared_chrome_nav

            chrome_fixed = enforce_shared_chrome_nav(workspace, architect)
            if chrome_fixed:
                actions.extend([f"chrome:{path}" for path in chrome_fixed])
                print(
                    f"    shared chrome enforced on {len(chrome_fixed)} page(s)",
                    flush=True,
                )
        except Exception as e:
            print(f"    shared chrome guard skipped: {e}", flush=True)
    try:
        actions.extend(ensure_runtime_correctness(
            workspace, architect, plan, primary, secondary, font, template_renderer,
        ))
    except Exception as e:
        print(f"    runtime correctness skipped: {e}", flush=True)
    restore_template_owned_files(workspace, architect, protected_snapshot)
    return [
        action for action in actions
        if not is_template_owned_path(action.split(" (", 1)[0], architect)
    ]


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


# Never invent mock stubs for UI catalogue / composer APIs — pages must import
# these from '@/ui'. Stubbing them as demo arrays causes runtime PREVIEW ERRORs.
_MOCK_FORBIDDEN_STUB_NAMES = frozenset(
    {
        "SkeletonComposer",
        "getSkeleton",
        "PublicShell",
        "OpsShell",
        "PublicNav",
        "BrandFooter",
        "MarketingHero",
        "FeatureBento",
        "ProductShowcase",
        "ProcessSection",
        "TestimonialRail",
        "CTABand",
        "BookingPanel",
        "PageHeader",
        "StatCard",
        "ChartCard",
        "FilterBar",
        "DataTable",
        "ActivityFeed",
        "RiskQueue",
        "EmptyState",
        "Button",
        "Badge",
        "Input",
        "Select",
        "Dialog",
        "Tabs",
        "LogoMarquee",
        "CredentialStrip",
        "SpotlightCard",
        "ResultRail",
        "AccentBeam",
        "UiIcon",
        "AppLink",
        "toast",
    }
)


_BAD_UI_MOCK_STUB_RE = re.compile(
    r"(?ms)^// build-correctness guard: auto-added missing exports\n"
    r"(?:export const (?:SkeletonComposer|getSkeleton)\s*=\s*\[[^\]]*\]\s*;\n?)+"
)


def _strip_forbidden_mock_stubs(mock: str) -> str:
    """Remove accidental array stubs for UI APIs that belong in '@/ui'."""
    updated = mock
    for name in sorted(_MOCK_FORBIDDEN_STUB_NAMES):
        updated = re.sub(
            rf"(?ms)^export const {re.escape(name)}\s*=\s*\[[^\]]*\]\s*;\s*\n?",
            "",
            updated,
        )
    # Collapse duplicate guard banners left empty after removals.
    updated = re.sub(
        r"(?m)^// build-correctness guard: auto-added missing exports\n(?=\s*(?:// build-correctness guard: auto-added missing exports\n)?\s*$)",
        "",
        updated,
    )
    return updated


def ensure_mock_exports(
    workspace, architect: dict, plan: dict, images: dict, brand_name: str
) -> list[str]:
    """Guarantee every symbol the pages import from mock.ts actually exists.

    Only APPENDS missing exports (never removes the AI's rich data). Pure
    build-correctness — prevents MISSING_EXPORT failures and fix-loop thrashing.
    """
    mock = read_file(workspace, "src/data/mock.ts")
    cleaned = _strip_forbidden_mock_stubs(_clean_mock(mock))
    if cleaned != mock:
        mock = cleaned
        write_file(workspace, "src/data/mock.ts", mock)
    needed = _collect_mock_imports(workspace) - _MOCK_FORBIDDEN_STUB_NAMES
    if not needed:
        return []
    have = _mock_exported_names(mock)
    missing = [n for n in sorted(needed) if n not in have]
    if not missing:
        return []
    brand_span = _brand_object_span(mock)
    brand_body = (
        mock[brand_span[0] : brand_span[1]]
        if brand_span
        else ""
    )

    def _missing_export(name: str) -> str:
        low = name.lower().replace("_", "")
        if low in ("manifest", "brandmanifest") and brand_body:
            # Pages that import `manifest` mean the whole brand manifest —
            # alias it so manifest.services / manifest.design_system just work.
            return f"export const {name} = {{ brand_name: brand.name, ...brand }};"
        if re.search(rf"(?m)^\s*{re.escape(name)}\s*:", brand_body):
            return f"export const {name} = brand.{name};"
        return (
            f"export const {name} = "
            f"{_default_export_value(name, architect, plan, images, brand_name)};"
        )

    additions = "\n".join(
        _missing_export(name)
        for name in missing
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

# `import { CalendarIcon, ClockIcon } from '...UiIcons'` — common AI mistake;
# template only ships default `UiIcon`, so these become MISSING_EXPORT without shims.
_NAMED_ICONS_IMPORT_RE = re.compile(
    r"""import\s*\{([^}]+)\}\s*from\s*['"][^'"]*UiIcons['"]""",
    re.MULTILINE,
)


def _icon_export_to_key(name: str) -> str:
    base = re.sub(r"Icon$", "", name.strip())
    if not base:
        return "default"
    return re.sub(r"(?<!^)(?=[A-Z])", "-", base).lower().replace("_", "-")


def _collect_named_ui_icon_imports(workspace) -> set[str]:
    names: set[str] = set()
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts", ".jsx", ".js")):
            continue
        if norm.endswith("components/UiIcons.tsx"):
            continue
        for m in _NAMED_ICONS_IMPORT_RE.finditer(read_file(workspace, rel)):
            for part in m.group(1).split(","):
                token = part.strip()
                if not token or token.startswith("type ") or token.startswith("typeof "):
                    continue
                ident = token.split()[0]
                if " as " in f" {token} ":
                    # `Foo as Bar` — export name used in file is the alias (Bar)
                    bits = re.split(r"\s+as\s+", token, maxsplit=1)
                    ident = bits[-1].strip().split()[0] if bits else ident
                if ident == "UiIcon":
                    continue
                if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", ident):
                    names.add(ident)
    return names


def ensure_named_ui_icon_exports(workspace) -> list[str]:
    """Add missing named `*Icon` re-exports wrapping default `UiIcon`.

    Prevents Vite MISSING_EXPORT when pages import `{ CalendarIcon }` etc.
    """
    needed = sorted(_collect_named_ui_icon_imports(workspace))
    if not needed:
        return []

    target = "src/components/UiIcons.tsx"
    content = read_file(workspace, target)
    if not content.strip():
        if not ensure_ui_icons(workspace):
            return []
        content = read_file(workspace, target)

    missing = [
        n for n in needed
        if not re.search(rf"export\s+(?:function|const)\s+{re.escape(n)}\b", content)
        and f"export {{ {n}" not in content
        and f"export {{{n}" not in content
    ]
    if not missing:
        return []

    if "function UiIcon" not in content and "UiIcon =" not in content:
        ensure_ui_icons(workspace)
        content = read_file(workspace, target)

    additions = []
    for name in missing:
        key = _icon_export_to_key(name)
        additions.append(
            f"\nexport function {name}({{ className = 'w-5 h-5' }}: {{ className?: string }}) {{\n"
            f"  return <UiIcon name={{'{key}'}} className={{className}} />;\n"
            f"}}\n"
        )
    write_file(workspace, target, content.rstrip() + "\n" + "".join(additions))
    try:
        ensure_ui_icon_coverage(workspace)
    except Exception:
        pass
    return [f"UiIcons.tsx (named exports: {', '.join(missing)})"]


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
