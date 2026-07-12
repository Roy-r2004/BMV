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
                token = part.strip()
                if not token:
                    continue
                # `import { type Foo }` / `import type { Foo }` residue
                bits = token.split()
                if bits and bits[0] == "type":
                    bits = bits[1:]
                token = " ".join(bits)
                n = token.split(" as ")[0].strip()
                if n and re.match(r"^[A-Za-z_$][\w$]*$", n):
                    names.add(n)
    return names


def scrub_invalid_mock_exports(workspace) -> list[str]:
    """Remove illegal `export const type Foo` / spaced names from mock auto-exports."""
    mock_path = "src/data/mock.ts"
    mock = read_file(workspace, mock_path)
    if not mock.strip():
        return []
    updated, n = re.subn(
        r"^export\s+const\s+type\s+[A-Za-z_$][\w$]*\s*=\s*[\s\S]*?;\s*\n?",
        "",
        mock,
        flags=re.MULTILINE,
    )
    if n:
        write_file(workspace, mock_path, updated)
        print(f"    scrubbed {n} invalid type-export(s) from mock.ts", flush=True)
        return [f"type-export-x{n}"]
    return []


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
    if low in ("ownerdailybriefing",):
        return json.dumps(_default_owner_daily_briefing(brand_name), ensure_ascii=False)
    if low in ("appointmentsoverview",):
        return json.dumps(_default_appointments_overview(), ensure_ascii=False)
    if low in ("newclientsignups",):
        return json.dumps(_default_new_client_signups(), ensure_ascii=False)
    # Never default to [] — empty arrays compile but show blank UIs.
    return _seeded_list_export(name, brand_name or "Brand")


def _default_owner_daily_briefing(brand_name: str) -> dict:
    name = brand_name or "Brand"
    return {
        "highValueClients": [
            f"VIP consult at 10:00 — prepare {name} protocol notes",
            "Returning member booked injectables — confirm consent packet",
            "High LTV client requesting same-day add-on",
        ],
        "specialCases": [
            "Patch-test follow-up mid-afternoon",
            "Sensitivity flag on laser renewal — brief the room early",
            "Aftercare escalation awaiting clinical review",
        ],
    }


def _default_appointments_overview() -> dict:
    return {"confirmed": 12, "pending": 3, "cancelled": 1, "total": 16}


def _default_new_client_signups() -> dict:
    return {"today": 4, "thisWeek": 18, "thisMonth": 42}


def _ts_export_value_end(src: str, start: int) -> int:
    """Return index just past a TS export value (string/array/object/primitive + optional `;`)."""
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


def _replace_named_export(mock: str, name: str, value_src: str) -> tuple[str, bool]:
    """Replace `export const name = ...;` value, or append if missing."""
    pat = re.compile(rf"export\s+const\s+{re.escape(name)}\s*=\s*", re.MULTILINE)
    m = pat.search(mock)
    if not m:
        addition = f"\nexport const {name} = {value_src};\n"
        return mock.rstrip() + addition, True
    end = _ts_export_value_end(mock, m.end())
    return mock[: m.end()] + f"{value_src};" + mock[end:], True


def _pages_reference_prop(workspace, export_name: str, prop: str) -> bool:
    needle = f"{export_name}.{prop}"
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if "/pages/" not in norm or not norm.endswith((".tsx", ".ts")):
            continue
        if needle in read_file(workspace, rel):
            return True
    return False


def repair_ops_mock_object_shapes(workspace, brand_name: str) -> list[str]:
    """Fix mock exports that pages treat as objects but were seeded as arrays.

    Classic crash: `ownerDailyBriefing.highValueClients.map` when the export is a list.
    """
    mock_path = "src/data/mock.ts"
    mock = read_file(workspace, mock_path)
    if not mock.strip():
        return []
    repaired: list[str] = []

    checks: list[tuple[str, list[str], str]] = [
        (
            "ownerDailyBriefing",
            ["highValueClients", "specialCases"],
            json.dumps(_default_owner_daily_briefing(brand_name), ensure_ascii=False),
        ),
        (
            "appointmentsOverview",
            ["confirmed", "pending"],
            json.dumps(_default_appointments_overview(), ensure_ascii=False),
        ),
        (
            "appointmentsToday",
            ["total", "confirmed", "projectedRevenue", "newClientsThisWeek"],
            json.dumps(
                {
                    "total": 18,
                    "confirmed": 14,
                    "pending": 4,
                    "projectedRevenue": "₪18,400",
                    "actualRevenue": "₪12,200",
                    "newClientsThisWeek": 7,
                },
                ensure_ascii=False,
            ),
        ),
        (
            "newClientSignups",
            ["today", "thisWeek"],
            json.dumps(_default_new_client_signups(), ensure_ascii=False),
        ),
    ]
    for export_name, props, value_src in checks:
        if not any(_pages_reference_prop(workspace, export_name, p) for p in props):
            continue
        m = re.search(rf"export\s+const\s+{re.escape(export_name)}\s*=\s*", mock)
        if not m:
            mock, _ = _replace_named_export(mock, export_name, value_src)
            repaired.append(export_name)
            continue
        current = mock[m.end() : _ts_export_value_end(mock, m.end())].strip().rstrip(";").strip()
        needs = current.startswith("[") or not all(p in current for p in props)
        if needs:
            mock, _ = _replace_named_export(mock, export_name, value_src)
            repaired.append(export_name)

    # OpsShell navItems must be an array. AI often emits
    # `adminNavigation = { type: "sidebar", links: [...] }`.
    nav_m = re.search(r"export\s+const\s+adminNavigation\s*=\s*", mock)
    if nav_m:
        end = _ts_export_value_end(mock, nav_m.end())
        current = mock[nav_m.end() : end]
        body = current.strip().rstrip(";").strip()
        if body.startswith("{"):
            links_m = re.search(r"\blinks\s*:\s*(\[[\s\S]*\])\s*,?\s*\}", body)
            if links_m:
                links_src = links_m.group(1)
                # Still rewrite stale paths inside the extracted links
                links_src = re.sub(r'(["\'])/admin/', r"\1/owner/", links_src)
                links_src = re.sub(r'(["\'])/admin(["\'])', r"\1/owner/dashboard\2", links_src)
                links_src = re.sub(r'(["\'])/ops-hub/', r"\1/owner/", links_src)
                links_src = re.sub(r'(["\'])/ops-hub(["\'])', r"\1/owner/dashboard\2", links_src)
                if "href" not in links_src and re.search(r"\bpath\s*:", links_src):
                    links_src = re.sub(
                        r'(path\s*:\s*)(["\'])([^"\']+)\2',
                        r"\1\2\3\2, href: \2\3\2",
                        links_src,
                    )
                mock = mock[: nav_m.end()] + links_src + ";" + mock[end:]
                repaired.append("adminNavigation")
            else:
                body2 = body
                body2 = re.sub(r'(["\'])/admin/', r"\1/owner/", body2)
                body2 = re.sub(r'(["\'])/admin(["\'])', r"\1/owner/dashboard\2", body2)
                body2 = re.sub(r'(["\'])/ops-hub/', r"\1/owner/", body2)
                body2 = re.sub(r'(["\'])/ops-hub(["\'])', r"\1/owner/dashboard\2", body2)
                if body2 != body:
                    mock = mock[: nav_m.end()] + body2 + ";" + mock[end:]
                    repaired.append("adminNavigation")
        elif body.startswith("["):
            body2 = body
            body2 = re.sub(r'(["\'])/admin/', r"\1/owner/", body2)
            body2 = re.sub(r'(["\'])/admin(["\'])', r"\1/owner/dashboard\2", body2)
            body2 = re.sub(r'(["\'])/ops-hub/', r"\1/owner/", body2)
            body2 = re.sub(r'(["\'])/ops-hub(["\'])', r"\1/owner/dashboard\2", body2)
            if "href" not in body2 and re.search(r"\bpath\s*:", body2):
                body2 = re.sub(
                    r'(path\s*:\s*)(["\'])([^"\']+)\2',
                    r"\1\2\3\2, href: \2\3\2",
                    body2,
                )
            elif re.search(r"\bpath\s*:", body2):

                def _add_href(m: re.Match) -> str:
                    full = m.group(0)
                    if "href" in full:
                        return full
                    return re.sub(
                        r'(path\s*:\s*)(["\'])([^"\']+)\2',
                        r"\1\2\3\2, href: \2\3\2",
                        full,
                        count=1,
                    )

                body2 = re.sub(r"\{[^{}]*\bpath\s*:[^{}]*\}", _add_href, body2)
            if body2 != body:
                mock = mock[: nav_m.end()] + body2 + ";" + mock[end:]
                repaired.append("adminNavigation")

    if repaired:
        write_file(workspace, mock_path, mock)
        print(f"    ops mock object shapes repaired: {', '.join(repaired)}", flush=True)
    return repaired


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
    pieces = _brand_missing_field_pieces(
        brand_name,
        primary,
        secondary,
        font,
        needs_ds=True,
        needs_services=True,
        needs_testimonials=True,
        needs_client_names=True,
        needs_proof=True,
    )
    return ",\n  ".join(pieces)


def _default_brand_services(name: str) -> list[dict]:
    return [
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


def _default_brand_testimonials(name: str) -> list[dict]:
    return [
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


def _default_client_names() -> list[str]:
    return [
        "Sofia Chen",
        "Amelia Brooks",
        "Noah Patel",
        "Ava Martinez",
        "Liam Okonkwo",
        "Mia Laurent",
    ]


def _brand_missing_field_pieces(
    brand_name: str,
    primary: str,
    secondary: str,
    font: str,
    *,
    needs_ds: bool,
    needs_services: bool,
    needs_testimonials: bool,
    needs_client_names: bool,
    needs_proof: bool,
) -> list[str]:
    name = brand_name or "Brand"
    pieces: list[str] = []
    if needs_ds:
        pieces.append(
            f"design_system: {json.dumps(_design_system_dict(primary, secondary, font), ensure_ascii=False)}"
        )
    if needs_services:
        pieces.append(f"services: {json.dumps(_default_brand_services(name), ensure_ascii=False)}")
    if needs_testimonials:
        pieces.append(
            f"testimonials: {json.dumps(_default_brand_testimonials(name), ensure_ascii=False)}"
        )
    if needs_client_names:
        pieces.append(f"client_names: {json.dumps(_default_client_names(), ensure_ascii=False)}")
    if needs_proof:
        pieces.append(
            "social_proof: "
            + json.dumps(f"Trusted by over 2,400 delighted {name} clients.", ensure_ascii=False)
        )
    return pieces


def ensure_brand_shape(
    workspace,
    brand_name: str,
    primary: str,
    secondary: str,
    font: str,
) -> bool:
    """Guarantee `brand.design_system` (+ services/testimonials/client_names) so pages don't crash white.

    AI pages often read `brand.design_system.primary_color`, `brand.services.map(...)`,
    and `brand.client_names[0]`. Missing nested keys throw at *module import* time and
    blank the entire SPA (not just that route).

    Detection MUST inspect the brand object body only: top-level `export const design_system`
    / path strings like `/owner/services` must not count as completeness.

    Only missing fields are injected — never re-copy services/testimonials that already exist.
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

    pieces = _brand_missing_field_pieces(
        brand_name,
        primary,
        secondary,
        font,
        needs_ds="design_system" not in body or "primary_color" not in body,
        needs_services=not bool(re.search(r"\bservices\s*:", body)),
        needs_testimonials=not bool(re.search(r"\btestimonials\s*:", body)),
        needs_client_names=not bool(re.search(r"\bclient_names\s*:", body)),
        needs_proof="social_proof" not in body,
    )
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

    # Walk matches right-to-left so offsets stay valid.
    matches = list(_TYPED_MOCK_EXPORT_RE.finditer(mock))
    for m in reversed(matches):
        name = m.group(1)
        val_start = m.end()
        val_end = _ts_export_value_end(mock, val_start)
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
_UI_HEADLESS_MOTION_SYMBOLS = {"motion", "AnimatePresence"}


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


def _rewrite_ui_headless_motion_imports(content: str) -> str:
    """Point pure motion imports at `framer-motion` instead of `UiHeadless`."""

    def _replace(match: re.Match[str]) -> str:
        spec = match.group(3).replace("\\", "/")
        if "UiHeadless" not in spec:
            return match.group(0)
        named = re.match(r"^\s*import\s*(?:type\s+)?\{([^}]*)\}\s+from\s+$", match.group(1))
        if not named:
            return match.group(0)
        symbols = []
        for part in named.group(1).split(","):
            symbol = re.sub(r"\s+as\s+\w+$", "", part.strip())
            symbol = re.sub(r"^type\s+", "", symbol).strip()
            if symbol:
                symbols.append(symbol)
        if not symbols or any(symbol not in _UI_HEADLESS_MOTION_SYMBOLS for symbol in symbols):
            return match.group(0)
        return f"{match.group(1)}{match.group(2)}framer-motion{match.group(4)}"

    return _UI_KIT_IMPORT_LINE_RE.sub(_replace, content)


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
        updated = _rewrite_ui_headless_motion_imports(updated)
        # Models invent `UiIcon` on `@/ui`; the real helper lives in components.
        updated = re.sub(
            r"""(import\s*\{[^}]*\bUiIcon\b[^}]*\}\s*from\s*)(['"])@/ui(?:/index)?\2""",
            r"\1\2@/components/UiIcons\2",
            updated,
        )
        updated = re.sub(
            r"""(import\s+UiIcon\s+from\s*)(['"])@/ui(?:/UiIcon|/index)?\2""",
            r"\1\2@/components/UiIcons\2",
            updated,
        )
        updated = re.sub(
            r"""(import\s+UiIcon\s+from\s*)(['"])@/ui\2""",
            r"\1\2@/components/UiIcons\2",
            updated,
        )
        if updated != content:
            write_file(workspace, rel, updated)
            fixed.append(norm)
    return fixed


def restore_curated_ui_kit(workspace) -> list[str]:
    """Overwrite `src/ui/*` with the curated template kit.

    Codegen sometimes invents incomplete helpers (default-only Checkbox,
    ProgressBar, etc.) that break named imports. Always restore the known-good
    kit before build so pages keep their AI content while the surface API stays
    stable.
    """
    template_ui = settings.PREVIEW_TEMPLATE_DIR / "src" / "ui"
    if not template_ui.is_dir():
        return []
    restored: list[str] = []
    for src in sorted(template_ui.rglob("*")):
        if not src.is_file():
            continue
        rel = ("src/ui/" + src.relative_to(template_ui).as_posix()).replace("\\", "/")
        write_file(workspace, rel, src.read_text(encoding="utf-8"))
        restored.append(rel)
    if restored:
        print(f"    restored curated ui kit ({len(restored)} files)", flush=True)
    return restored


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
    "@radix-ui/react-popover": "src/components/UiHeadless",
}
_IMPORT_FROM_RE = re.compile(
    r"""^\s*import\s+(?:type\s+)?(?:[\s\S]*?)\s+from\s+['"]([^'"]+)['"]\s*;?\s*(?://[^\n]*)?$""",
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
        if norm.startswith("src/data/") or norm.startswith("src/ui/") or norm.endswith("UiHeadless.tsx"):
            continue
        content = read_file(workspace, rel)
        needed: list[str] = []
        for sym in _HEADLESS_SYMBOLS:
            # JSX tag or compound API (Dialog.Panel) — not prose / file paths like Switch.js
            used = bool(
                re.search(rf"<{sym}\b", content)
                or re.search(rf"\b{sym}\.[A-Z]", content)
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


_ALLOWED_BUTTON_VARIANTS = {"primary", "secondary", "ghost", "danger"}
_FORBIDDEN_BUTTON_VARIANTS = {"gradient", "outline", "tertiary", "link", "default", "destructive"}
_UI_COMPONENT_NAMES = {
    "PublicShell", "MarketingHero", "FeatureBento", "CTABand", "OpsShell", "PageHeader",
    "StatCard", "DataTable", "FilterBar", "ChartCard", "EmptyState", "ConfirmDialog",
    "Button", "Card", "Badge", "Input", "Textarea", "TextArea", "Select", "Dialog",
    "Modal", "Tabs", "Checkbox", "Switch", "Tooltip", "SectionHeader", "MultiSelect",
    "Toast",
}


def sanitize_ui_component_apis(workspace) -> list[str]:
    """Rewrite invented Button/StatCard/MarketingHero props to match curated kit contracts."""
    touched: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")):
            continue
        if norm.startswith("src/ui/"):
            continue
        content = read_file(workspace, rel)
        updated = content

        # Button as={Link} / as={...} → drop invalid prop
        updated = re.sub(r"\s+as=\{[^}]+\}", "", updated)
        # asChild on generated pages (curated kit ConfirmDialog may keep it; pages must not)
        if not norm.endswith("ConfirmDialog.tsx"):
            updated = re.sub(r"\s+asChild(?:=\{[^}]*\})?", "", updated)

        for bad in _FORBIDDEN_BUTTON_VARIANTS:
            replacement = "secondary" if bad in ("outline", "tertiary", "link", "default") else "primary"
            updated = re.sub(
                rf'variant=["\']{bad}["\']',
                f'variant="{replacement}"',
                updated,
                flags=re.IGNORECASE,
            )
            updated = re.sub(
                rf'variant=\{{["\']{bad}["\']\}}',
                f'variant="{replacement}"',
                updated,
                flags=re.IGNORECASE,
            )

        # StatCard title= → label= (contract is label/value)
        updated = re.sub(r"<StatCard(\s[^>]*)\btitle=", r"<StatCard\1label=", updated)
        updated = re.sub(r"<StatCard(\s[^>]*)\btitle=\{", r"<StatCard\1label={", updated)
        # Drop unsupported StatCard Icon= prop (balanced braces)
        while True:
            m_icon = re.search(r"\s+Icon=\{", updated)
            if not m_icon:
                break
            start = m_icon.start()
            i = m_icon.end()
            depth = 1
            while i < len(updated) and depth:
                ch = updated[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                i += 1
            updated = updated[:start] + updated[i:]

        # Button size only sm|md
        updated = re.sub(r'size=["\']lg["\']', 'size="md"', updated, flags=re.IGNORECASE)
        updated = re.sub(r'size=["\']large["\']', 'size="md"', updated, flags=re.IGNORECASE)
        updated = re.sub(r"size=\{['\"]lg['\"]\}", 'size="md"', updated, flags=re.IGNORECASE)

        # MarketingHero wrong prop names
        updated = re.sub(r"\bsubheadline=", "subcopy=", updated)
        updated = re.sub(r"\bcta1=", "primaryAction=", updated)
        updated = re.sub(r"\bcta2=", "secondaryAction=", updated)
        # image= on MarketingHero → media= with img wrapper is hard; map prop name at least
        updated = re.sub(r"(<MarketingHero\b[^>]*?)\bimage=", r"\1media=", updated)

        if updated != content:
            write_file(workspace, norm, updated)
            touched.append(norm)
            print(f"    ui API sanitized in {norm}", flush=True)
    return touched


_LAYOUT_IMPORT_RE = re.compile(
    r"""^\s*import\s+(\w+)\s+from\s+['"][^'"]*layouts/(PublicLayout|AdminLayout)(?:\.tsx)?['"]\s*;?\s*\n""",
    re.MULTILINE,
)
_LAYOUT_NAMED_IMPORT_RE = re.compile(
    r"""^\s*import\s+\{\s*(PublicLayout|AdminLayout)\s*\}\s+from\s+['"][^'"]+['"]\s*;?\s*\n""",
    re.MULTILINE,
)


def _ensure_named_or_default_import(content: str, symbol: str, module: str) -> str:
    """Ensure `symbol` is imported from module (named merge or default import)."""
    if re.search(rf"\bimport\s+{re.escape(symbol)}\s+from\s+['\"]{re.escape(module)}['\"]", content):
        return content
    named = re.search(
        rf"""import\s+\{{([^}}]*)}}\s+from\s+['\"]{re.escape(module)}['\"]""",
        content,
    )
    if named:
        if symbol in named.group(1):
            return content
        return (
            content[: named.start(1)]
            + f" {symbol}, "
            + named.group(1)
            + content[named.end(1) :]
        )
    # Prefer default import path for shell components
    default_mod = f"{module}/{symbol}" if module == "@/ui" else module
    if re.search(rf"\bimport\s+{re.escape(symbol)}\s+from\s+['\"]{re.escape(default_mod)}['\"]", content):
        return content
    return f"import {symbol} from '{default_mod}';\n" + content


def _ensure_mock_symbol_import(content: str, symbol: str) -> str:
    if re.search(rf"\b{re.escape(symbol)}\b", content) and re.search(
        r"""from\s+['"](?:@/data/mock|\.\./(?:\.\./)*data/mock)['"]""", content
    ):
        m_imp = re.search(
            r"""import\s+\{([^}]*)\}\s+from\s+['"](?:@/data/mock|\.\./(?:\.\./)*data/mock)['"]""",
            content,
        )
        if m_imp:
            if symbol in m_imp.group(1):
                return content
            return (
                content[: m_imp.start(1)]
                + f" {symbol}, "
                + m_imp.group(1)
                + content[m_imp.end(1) :]
            )
    return f"import {{ {symbol} }} from '@/data/mock';\n" + content


def unwrap_route_layout_wrappers(workspace, brand_name: str = "Brand") -> list[str]:
    """Strip page-level PublicLayout/AdminLayout wrappers.

    Those layouts are thin `<Outlet />` only. Nesting them inside a routed page
    renders an empty Outlet and blanks the screen.
    """
    touched: list[str] = []
    name_lit = json.dumps(brand_name or "Brand", ensure_ascii=False)
    brand_expr = (
        "{(typeof brand !== 'undefined' && (brand as any)?.name) "
        f"|| (typeof brand_name !== 'undefined' ? brand_name : {name_lit})}}"
    )

    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if "/pages/" not in norm or not norm.endswith((".tsx", ".jsx")):
            continue
        content = read_file(workspace, rel)
        if "PublicLayout" not in content and "AdminLayout" not in content:
            continue
        updated = content
        updated = _LAYOUT_IMPORT_RE.sub("", updated)
        updated = _LAYOUT_NAMED_IMPORT_RE.sub("", updated)

        if re.search(r"<PublicLayout\b", updated):
            if re.search(r"<PublicShell\b", updated):
                updated = re.sub(r"<PublicLayout\b[^>]*>", "<>", updated)
                updated = updated.replace("</PublicLayout>", "</>")
            else:
                updated = re.sub(
                    r"<PublicLayout\b[^>]*>",
                    f"<PublicShell brandName={brand_expr}>",
                    updated,
                )
                updated = updated.replace("</PublicLayout>", "</PublicShell>")
                updated = _ensure_named_or_default_import(updated, "PublicShell", "@/ui")

        if re.search(r"<AdminLayout\b", updated):
            if re.search(r"<OpsShell\b", updated):
                updated = re.sub(r"<AdminLayout\b[^>]*>", "<>", updated)
                updated = updated.replace("</AdminLayout>", "</>")
            else:
                updated = re.sub(
                    r"<AdminLayout\b[^>]*>",
                    f"<OpsShell brandName={brand_expr} navItems={{(typeof adminNavigation !== 'undefined' ? adminNavigation : []) as any}}>",
                    updated,
                )
                updated = updated.replace("</AdminLayout>", "</OpsShell>")
                updated = _ensure_named_or_default_import(updated, "OpsShell", "@/ui")
                updated = _ensure_mock_symbol_import(updated, "adminNavigation")

        if updated != content:
            write_file(workspace, norm, updated)
            touched.append(norm)
            print(f"    unwrapped route layout wrappers in {norm}", flush=True)
    return touched


def fix_shell_imports_pointing_at_layouts(workspace) -> list[str]:
    """AI sometimes aliases PublicShell → layouts/PublicLayout (Outlet) — blank pages."""
    touched: list[str] = []
    patterns = (
        (
            re.compile(
                r"""import\s+PublicShell\s+from\s+['"][^'"]*layouts/PublicLayout(?:\.tsx)?['"]\s*;?"""
            ),
            "import PublicShell from '@/ui/PublicShell';",
        ),
        (
            re.compile(
                r"""import\s+OpsShell\s+from\s+['"][^'"]*layouts/AdminLayout(?:\.tsx)?['"]\s*;?"""
            ),
            "import OpsShell from '@/ui/OpsShell';",
        ),
        (
            re.compile(
                r"""import\s+\{\s*PublicShell\s*\}\s+from\s+['"][^'"]*layouts/PublicLayout(?:\.tsx)?['"]\s*;?"""
            ),
            "import PublicShell from '@/ui/PublicShell';",
        ),
        (
            re.compile(
                r"""import\s+\{\s*OpsShell\s*\}\s+from\s+['"][^'"]*layouts/AdminLayout(?:\.tsx)?['"]\s*;?"""
            ),
            "import OpsShell from '@/ui/OpsShell';",
        ),
    )
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")):
            continue
        content = read_file(workspace, rel)
        updated = content
        for pat, repl in patterns:
            updated = pat.sub(repl, updated)
        if updated != content:
            write_file(workspace, norm, updated)
            touched.append(norm)
            print(f"    fixed shell→layout import alias in {norm}", flush=True)
    return touched


_JSX_ATTR_COMMENT_RE = re.compile(
    r"(\s*)\{\/\*[^*]*\*\/\}(?=\s*>)",
    re.MULTILINE,
)


def strip_illegal_jsx_attribute_comments(workspace) -> list[str]:
    """Remove `{/* ... */}` between JSX attributes and the tag's closing `>`."""
    touched: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if "/pages/" not in norm or not norm.endswith((".tsx", ".jsx")):
            continue
        content = read_file(workspace, rel)
        updated = _JSX_ATTR_COMMENT_RE.sub("", content)
        if updated != content:
            write_file(workspace, norm, updated)
            touched.append(norm)
            print(f"    stripped illegal JSX attribute comments in {norm}", flush=True)
    return touched


_NAMED_IMPORT_RE = re.compile(
    r"""^(\s*import\s+)\{([^}]*)\}(\s+from\s+)(['"])([^'"]+)\4(\s*;?\s*(?://[^\n]*)?\n?)$"""
)


def _parse_import_names(inner: str) -> list[str]:
    names: list[str] = []
    for part in inner.split(","):
        token = part.strip()
        if not token:
            continue
        bits = token.split()
        if bits and bits[0] == "type":
            bits = bits[1:]
        token = " ".join(bits).split(" as ")[0].strip()
        if token:
            names.append(token)
    return names


def _rewrite_mixed_uiicons_import(line: str, src: str) -> list[str] | None:
    """Split `import { PublicShell, Button, UiIcon } from '...UiIcons'` into kit + icons."""
    if "UiIcons" not in src:
        return None
    m = _NAMED_IMPORT_RE.match(line if line.endswith("\n") else line + "\n")
    if not m:
        # default import of UiIcons is fine
        return None
    names = _parse_import_names(m.group(2))
    if not names:
        return None
    kit = [n for n in names if n in _UI_COMPONENT_NAMES]
    icons = [n for n in names if n not in _UI_COMPONENT_NAMES]
    if not kit:
        return None
    out: list[str] = []
    out.append(f"import {{ {', '.join(kit)} }} from '@/ui';\n")
    if icons:
        # Keep remaining symbols on UiIcons (usually UiIcon as named — prefer default)
        if icons == ["UiIcon"]:
            out.append(f"import UiIcon from '{src}';\n")
        else:
            out.append(f"import {{ {', '.join(icons)} }} from '{src}';\n")
    return out


def rewrite_invented_component_imports(workspace) -> list[str]:
    """Block invented `@/components/*` (except UiIcons) — rewrite known ui names to `@/ui`.

    Critical old→new migration: AI often does
    `import { PublicShell, Button, Card, UiIcon } from '@/components/UiIcons'`
    which must become `@/ui` + UiIcons default.
    """
    touched: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")):
            continue
        content = read_file(workspace, rel)
        lines: list[str] = []
        changed = False
        for line in content.splitlines(keepends=True):
            m = re.search(r"""from\s+['"]([^'"]+)['"]""", line)
            if not m or "import" not in line:
                lines.append(line)
                continue
            src = m.group(1)

            # Mixed kit symbols imported from UiIcons (the #1 2026 elevation failure mode)
            split = _rewrite_mixed_uiicons_import(line, src)
            if split is not None:
                lines.extend(split)
                changed = True
                continue

            if src.startswith("@/components/") and "UiIcons" not in src and "UiHeadless" not in src:
                base = src.rsplit("/", 1)[-1].replace(".tsx", "").replace(".ts", "")
                if base in _UI_COMPONENT_NAMES:
                    lines.append(line.replace(src, f"@/ui/{base}"))
                    changed = True
                else:
                    lines.append(f"/* removed invented import: {src} */\n")
                    changed = True
                continue
            if "UiHeadless" in src and ("/ui/" in src or src.startswith("@/ui")):
                lines.append(line.replace(src, "@/components/UiHeadless"))
                changed = True
                continue
            if re.search(r"(?:^|/)manifest(?:\.ts)?$", src) and "mock" not in src:
                lines.append(line.replace(src, "@/data/mock"))
                changed = True
                continue
            if re.search(r"(?:^|/)mock-[A-Za-z0-9_-]+$", src) or "/data/mock-" in src:
                lines.append(line.replace(src, "@/data/mock"))
                changed = True
                continue
            if re.search(r"(?:^|[./])assets/[^'\"]+\.(?:png|jpe?g|webp|gif|svg)$", src, re.I):
                lines.append("/* removed invented asset import — use images from @/data/mock */\n")
                changed = True
                continue
            # Invented or nested @/ui/* — map known kit names to `@/ui/{Name}`
            if src.startswith("@/ui/") or re.search(r"(?:\.\./)+ui/", src):
                base = src.rsplit("/", 1)[-1].replace(".tsx", "").replace(".ts", "")
                if base in _UI_COMPONENT_NAMES:
                    target = f"@/ui/{base}"
                    if src.replace("\\", "/") != target and not src.rstrip("/").endswith(
                        f"/ui/{base}"
                    ):
                        lines.append(line.replace(src, target))
                        changed = True
                        continue
                    lines.append(line)
                    continue
                if base and base[0].isupper() and base != "index":
                    lines.append(f"/* removed invented ui import: {src} */\n")
                    changed = True
                    continue
            if (
                re.search(r"(?:\.\./)+components/", src)
                and "UiIcons" not in src
                and "UiHeadless" not in src
                and "/Nav" not in src
            ):
                base = src.rsplit("/", 1)[-1].replace(".tsx", "").replace(".ts", "")
                if base in _UI_COMPONENT_NAMES:
                    lines.append(line.replace(src, f"@/ui/{base}"))
                    changed = True
                elif base and base[0].isupper() and base not in ("Nav",):
                    lines.append(f"/* removed invented import: {src} */\n")
                    changed = True
                else:
                    lines.append(line)
                continue
            lines.append(line)
        if changed:
            write_file(workspace, norm, "".join(lines))
            touched.append(norm)
            print(f"    invented component imports rewritten in {norm}", flush=True)
    return touched


def ensure_shell_required_props(workspace, brand_name: str = "Brand") -> list[str]:
    """Guarantee PublicShell/OpsShell required props so pages don't type/runtime-fail."""
    touched: list[str] = []
    name_lit = json.dumps(brand_name or "Brand", ensure_ascii=False)
    brand_expr = (
        "{(typeof brand !== 'undefined' && (brand as any)?.name) "
        f"|| (typeof brand_name !== 'undefined' ? brand_name : {name_lit})}}"
    )
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if "/pages/" not in norm or not norm.endswith((".tsx", ".jsx")):
            continue
        content = read_file(workspace, rel)
        updated = content

        def _add_brand(m: re.Match) -> str:
            tag = m.group(0)
            if "brandName=" in tag:
                return tag
            return tag[:-1] + f" brandName={brand_expr}>"

        updated = re.sub(r"<PublicShell\b([^>]*?)>", _add_brand, updated)
        # OpsShell needs brandName + navItems
        def _add_ops(m: re.Match) -> str:
            tag = m.group(0)
            out = tag
            if "brandName=" not in out:
                out = out[:-1] + f" brandName={brand_expr}>"
            if "navItems=" not in out:
                out = out[:-1] + " navItems={(typeof adminNavigation !== 'undefined' ? adminNavigation : []) as any}>"
            return out

        updated = re.sub(r"<OpsShell\b([^>]*?)>", _add_ops, updated)
        if updated != content:
            if "adminNavigation" in updated and "adminNavigation" not in content:
                updated = _ensure_mock_symbol_import(updated, "adminNavigation")
            if ("brand" in updated or "brand_name" in updated) and "from '@/data/mock'" not in updated and 'from "@/data/mock"' not in updated:
                if not re.search(r"""from\s+['"].*data/mock['"]""", updated):
                    updated = "import { brand } from '@/data/mock';\n" + updated
            write_file(workspace, norm, updated)
            touched.append(norm)
            print(f"    shell required props ensured in {norm}", flush=True)
    return touched


def rewrite_motion_imports_from_cn(workspace) -> list[str]:
    """AI often imports fadeUp/staggerChildren/pageFade from `@/lib/cn` — move to `@/ui`."""
    motion_names = {"fadeUp", "staggerChildren", "pageFade", "MotionDiv"}
    touched: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")):
            continue
        content = read_file(workspace, rel)
        lines: list[str] = []
        changed = False
        for line in content.splitlines(keepends=True):
            m = _NAMED_IMPORT_RE.match(line if line.endswith("\n") else line + "\n")
            if not m:
                lines.append(line)
                continue
            src = m.group(5)
            if "lib/cn" not in src and src not in ("@/lib/cn", "../lib/cn", "../../lib/cn"):
                lines.append(line)
                continue
            names = _parse_import_names(m.group(2))
            motion = [n for n in names if n in motion_names]
            other = [n for n in names if n not in motion_names]
            if not motion:
                lines.append(line)
                continue
            if other:
                lines.append(f"import {{ {', '.join(other)} }} from '{src}';\n")
            lines.append(f"import {{ {', '.join(motion)} }} from '@/ui';\n")
            changed = True
        if changed:
            write_file(workspace, norm, "".join(lines))
            touched.append(norm)
            print(f"    motion imports rewritten from cn in {norm}", flush=True)
    return touched


def ensure_mock_runtime_contracts(
    workspace,
    brand_name: str,
    primary: str,
    secondary: str,
    font: str,
) -> list[str]:
    """Guarantee manifest + navigation link aliases for runtime safety."""
    mock_path = "src/data/mock.ts"
    mock = read_file(workspace, mock_path)
    if not mock.strip():
        return []
    actions: list[str] = []
    name = brand_name or "Brand"

    if "export const manifest" not in mock:
        mock = (
            mock.rstrip()
            + "\n\n"
            + "export const manifest = {\n"
            + f"  brand_name: {json.dumps(name, ensure_ascii=False)},\n"
            + f"  accent: {json.dumps(primary or '#be185d', ensure_ascii=False)},\n"
            + f"  accent_dark: {json.dumps(secondary or primary or '#9f1239', ensure_ascii=False)},\n"
            + "  accent_light: '#fce7f3',\n"
            + f"  font: {json.dumps(font or 'system-ui', ensure_ascii=False)},\n"
            + "  owner_name: 'Studio Lead',\n"
            + "  client_names: ['Sofia Chen', 'Amelia Brooks', 'Noah Patel', 'Ava Martinez', 'Liam Okonkwo', 'Mia Laurent'],\n"
            + "  services: [] as any[],\n"
            + "  testimonials: [] as any[],\n"
            + "  design_system: {} as Record<string, unknown>,\n"
            + "};\n"
        )
        actions.append("manifest")

    m = re.search(r"export const navigation\s*=\s*(\{[\s\S]*?\n\});", mock)
    if m:
        try:
            nav = json.loads(m.group(1))
        except Exception:
            nav = None
        if isinstance(nav, dict):
            public = nav.get("public") or []
            admin = nav.get("admin") or []
            changed = False
            if "customer" not in nav:
                nav["customer"] = {"links": public}
                changed = True
            if "owner" not in nav:
                nav["owner"] = {"links": admin}
                changed = True
            if changed:
                nav_json = json.dumps(nav, indent=2, ensure_ascii=False)
                mock = mock[: m.start()] + f"export const navigation = {nav_json};" + mock[m.end() :]
                actions.append("navigation aliases")

    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".jsx")) or "/pages/" not in norm:
            continue
        text = read_file(workspace, norm)
        new = text
        new = new.replace(
            "brand.client_names[0]",
            "(brand as any).client_names?.[0] ?? 'Sofia'",
        )
        new = new.replace(
            "M.manifest.brand_name",
            "(M as any).manifest?.brand_name ?? (M as any).brand?.name ?? 'Brand'",
        )
        new = new.replace(
            "navigation.customer.links",
            "(navigation as any).customer?.links ?? (navigation as any).public ?? []",
        )
        new = new.replace(
            "ownerDailyBriefing.highValueClients.map",
            "((ownerDailyBriefing as any)?.highValueClients ?? []).map",
        )
        new = new.replace(
            "ownerDailyBriefing.specialCases.map",
            "((ownerDailyBriefing as any)?.specialCases ?? []).map",
        )
        # Object-shaped overview mocks that auto-seed often fill as arrays
        for expr, safe in (
            (
                "appointmentsToday.total.toString()",
                "String((appointmentsToday as any)?.total ?? 0)",
            ),
            (
                "appointmentsToday.confirmed.toString()",
                "String((appointmentsToday as any)?.confirmed ?? 0)",
            ),
            (
                "appointmentsToday.projectedRevenue.toString()",
                "String((appointmentsToday as any)?.projectedRevenue ?? 0)",
            ),
            (
                "appointmentsToday.actualRevenue.toString()",
                "String((appointmentsToday as any)?.actualRevenue ?? 0)",
            ),
            (
                "appointmentsToday.newClientsThisWeek.toString()",
                "String((appointmentsToday as any)?.newClientsThisWeek ?? 0)",
            ),
        ):
            new = new.replace(expr, safe)
        if new != text:
            write_file(workspace, norm, new)
            actions.append(norm)

    if actions:
        write_file(workspace, mock_path, mock)
        print(f"    mock runtime contracts: {', '.join(actions[:8])}", flush=True)
    return actions


def force_thin_layouts(workspace) -> list[str]:
    """Always restore thin Outlet layouts so pages own PublicShell/OpsShell."""
    fixed: list[str] = []
    for name in ("PublicLayout.tsx", "AdminLayout.tsx"):
        src = settings.PREVIEW_TEMPLATE_DIR / "src" / "layouts" / name
        dst = Path(workspace) / "src" / "layouts" / name
        if not src.is_file():
            continue
        text = src.read_text(encoding="utf-8")
        if not dst.is_file() or dst.read_text(encoding="utf-8") != text:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(text, encoding="utf-8")
            fixed.append(f"src/layouts/{name}")
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
        (lambda: rewrite_invented_component_imports(workspace), "invented component imports rewritten"),
        (lambda: rewrite_motion_imports_from_cn(workspace), "motion imports rewritten"),
        (lambda: sanitize_ui_component_apis(workspace), "ui component APIs sanitized"),
        (lambda: unwrap_route_layout_wrappers(workspace, brand_name), "route layout wrappers unwrapped"),
        (lambda: fix_shell_imports_pointing_at_layouts(workspace), "shell layout aliases fixed"),
        (lambda: ensure_shell_required_props(workspace, brand_name), "shell required props ensured"),
        (lambda: strip_illegal_jsx_attribute_comments(workspace), "jsx attribute comments stripped"),
        (lambda: strip_forbidden_npm_imports(workspace), "forbidden npm imports stripped"),
        (lambda: ensure_headless_stub_imports(workspace), "headless stubs imported"),
        # Restore curated kit AFTER headless injection so kit files are never
        # polluted by UiHeadless symbol heuristics (Switch.js / Dialog.js).
        (lambda: restore_curated_ui_kit(workspace), "ui kit restored"),
        (lambda: force_thin_layouts(workspace), "thin layouts forced"),
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
        scrubbed = scrub_invalid_mock_exports(workspace)
        actions.extend(scrubbed)
    except Exception as e:
        print(f"    invalid mock export scrub skipped: {e}", flush=True)
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
        mock_actions = ensure_mock_runtime_contracts(workspace, brand_name, primary, secondary, font)
        actions.extend(mock_actions)
    except Exception as e:
        print(f"    mock runtime contracts skipped: {e}", flush=True)
    try:
        ops_shapes = repair_ops_mock_object_shapes(workspace, brand_name)
        actions.extend([f"mock-ops:{n}" for n in ops_shapes])
    except Exception as e:
        print(f"    ops mock shape repair skipped: {e}", flush=True)
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
    # Pages sometimes do `import { UiIcon }` — expose a named export too,
    # but only when UiIcon is not already a named export (function/const).
    has_named = bool(
        re.search(r"export\s+(?:async\s+)?function\s+UiIcon\b", content)
        or re.search(r"export\s+const\s+UiIcon\b", content)
        or "export { UiIcon }" in content
    )
    if "export default UiIcon" in content and not has_named:
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
