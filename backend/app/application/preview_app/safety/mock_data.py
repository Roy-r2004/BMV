"""Preview safety — Mock Data."""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

from app.application.preview_app.mock_imports import collect_mock_imports
from app.application.preview_app.source_quality import fix_unescaped_apostrophes
from app.application.preview_app.patterns import (
    _DATE_FIELD_KEYS,
    _EMPTY_ARRAY_EXPORT_RE,
    _LIST_EXPORT_RE,
    _MOCK_FORBIDDEN_STUB_NAMES,
    _MOCK_SELF_IMPORT_RE,
    _SEEDED_STUB_DETAIL_MARKER,
    _TYPED_MOCK_EXPORT_RE,
    brand_object_span as _brand_object_span,
)
from app.application.preview_app.workspace import list_source_files, read_file, write_file
from app.infrastructure.logging import get_logger

guard_log = get_logger("SafetyGuards")

def _collect_mock_imports(workspace) -> set[str]:
    return collect_mock_imports(workspace)

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


def _default_services(brand_name: str) -> list[dict[str, str]]:
    label = (brand_name or "Brand").strip() or "Brand"
    return [
        {
            "id": "intro-session",
            "name": f"{label} intro session",
            "description": "A welcoming first session for new guests.",
            "duration": "90 min",
            "level": "Beginner Friendly",
            "day": "Thursday",
            "status": "Open",
        },
        {
            "id": "signature-workshop",
            "name": "Signature workshop",
            "description": "The core experience guests book most often.",
            "duration": "2 hours",
            "level": "All Levels",
            "day": "Saturday",
            "status": "Open",
        },
        {
            "id": "advanced-studio",
            "name": "Advanced studio time",
            "description": "Deeper practice with guided feedback.",
            "duration": "3 hours",
            "level": "Intermediate",
            "day": "Wednesday",
            "status": "Full",
        },
    ]


def _default_products(brand_name: str) -> list[dict[str, str]]:
    label = (brand_name or "Brand").strip() or "Brand"
    return [
        {
            "title": f"{label} essential",
            "description": "A dependable pick from the shop floor.",
            "name": f"{label} essential",
        },
        {
            "title": "Studio favorite",
            "description": "The piece guests ask about first.",
            "name": "Studio favorite",
        },
    ]


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
        # Pages read manifest.brand_name / manifest.services / design_system.*
        # — an array stub white-screens the whole route.
        return json.dumps(
            {
                "brand_name": brand_name or "Brand",
                "name": brand_name or "Brand",
                "tagline": "",
                "accent": primary,
                "design_system": _design_system_dict(primary, secondary, font),
                "services": _default_services(brand_name or "Brand"),
                "products": _default_products(brand_name or "Brand"),
            },
            ensure_ascii=False,
        )
    if low == "navigation":
        return json.dumps(_nav_from_architect(architect), ensure_ascii=False)
    if low == "roles":
        return json.dumps(_roles_from(architect, plan), ensure_ascii=False)
    # Never default to [] — empty arrays compile but show blank UIs.
    return _seeded_list_export(name, brand_name or "Brand")

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

def ensure_seed_scaffold_fields(mock: str, brand_name: str = "Brand") -> str:
    """Guarantee seed.hero (and related scaffold keys) exist for catalogue pages.

    AI mock synthesis often replaces `seed` with domain-specific data and drops
    hero/cta/footer — HomePage then crashes on `seed.hero.headline`.
    """
    if "export const seed" not in mock:
        return mock
    # Already has a hero object under seed — leave it alone.
    if re.search(r"export const seed\s*=\s*\{[\s\S]*?\bhero\s*:", mock):
        return mock

    brand = (brand_name or "Brand").replace("\\", "\\\\").replace("'", "\\'")
    inject = (
        "\n  hero: {\n"
        f"    headline: '{brand}',\n"
        "    subcopy: 'A clear next step — polished, branded, and ready to book.',\n"
        "    primaryCta: { label: 'Get started', href: '#details' },\n"
        "    secondaryCta: { label: 'See how it works', href: '#process' },\n"
        "  },\n"
        "  items: [\n"
        "    { title: 'Signature offering', description: 'A dependable starting point.' },\n"
        "    { title: 'Everyday essential', description: 'Built for daily use.' },\n"
        "    { title: 'Member favorite', description: 'The one guests come back for.' },\n"
        "  ],\n"
        "  showcaseHeading: 'Featured experiences',\n"
        "  cta: {\n"
        "    heading: 'Make it unforgettable',\n"
        "    description: 'Book the next chapter — polished, branded, never bland.',\n"
        "    primaryLabel: 'Get started',\n"
        "    primaryHref: '#details',\n"
        "    secondaryLabel: 'Talk to us',\n"
        "    secondaryHref: '#contact',\n"
        "  },\n"
        "  footer: {\n"
        "    description: 'Premium presence from first glance to booked revenue.',\n"
        "  },\n"
    )
    updated, n = re.subn(
        r"(export const seed\s*=\s*\{)",
        r"\1" + inject,
        mock,
        count=1,
    )
    return updated if n else mock


def ensure_mock_exports(
    workspace, architect: dict, plan: dict, images: dict, brand_name: str
) -> list[str]:
    """Guarantee every symbol the pages import from mock.ts actually exists.

    Only APPENDS missing exports (never removes the AI's rich data). Pure
    build-correctness — prevents MISSING_EXPORT failures and fix-loop thrashing.
    """
    mock = read_file(workspace, "src/data/mock.ts")
    seeded = ensure_seed_scaffold_fields(mock, brand_name=brand_name)
    if seeded != mock:
        mock = seeded
        write_file(workspace, "src/data/mock.ts", mock)
        guard_log.info("seed.hero restored for scaffold pages (brand=%s)", brand_name)
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
        if low in ("manifest", "brandmanifest"):
            # Pages call BRAND_MANIFEST.services.filter(...) — a brand spread
            # without services white-screens the route. Prefer a full object.
            return (
                f"export const {name} = "
                f"{_default_export_value(name, architect, plan, images, brand_name)};"
            )
        if brand_body and re.search(rf"(?m)^\s*{re.escape(name)}\s*:", brand_body):
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
