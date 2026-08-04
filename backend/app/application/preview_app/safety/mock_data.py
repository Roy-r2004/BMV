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

#: Used when the app declares no public destination of its own. `/` is the one
#: route every generated app serves, and the wording names no artifact type.
_NEUTRAL_CTA = {"label": "See what we offer", "href": "/"}


def scaffold_hero_ctas(architect: dict | None, brand_name: str = "Brand") -> tuple[dict, dict]:
    """The scaffold hero's two CTAs, derived from what this app actually serves.

    They used to be literals: ``{label: 'Explore the collection', href:
    '/gallery'}`` and ``{label: 'Talk to us', href: '/contact#inquire'}``,
    injected whenever the AI's mock synthesis dropped `hero`. A **twelve-table
    Neapolitan trattoria** shipped "Explore the collection" that way, and it is
    verbatim in **7 of 64 archived workspaces** (20, 66, 78, 81, 85, 93, 95)
    across unrelated industries.

    Two things were wrong with the literal and only one of them is vocabulary:

    * *"the collection"* is one industry's word for its artifact, applied to
      every business. A restaurant has a menu and a lodge has rooms.
    * `/gallery` and `/contact#inquire` are **routes the app may not serve**.
      Request 95's secondary CTA was repaired to `/` by the dead-link guard, so
      the scaffold shipped a "Talk to us" button that reloads the home page.

    So the rule is not "suppress gallery for restaurants" — nothing here reads
    an industry, and nothing here may. It is the rule this repo already made
    once for `AiFeaturePanel`'s hardcoded `/ai-features`, dead in 5 of 41
    workspaces (`430453a`): **a scaffold cannot assume a route it did not
    create.** The destination is whichever public route the app declares first
    by `_nav_rank`, and the label is that page's own name — so a business with
    a collection gets one and a business without gets whatever it does have,
    decided identically for both.
    """

    ranked: list[tuple[int, str, str]] = []
    for route in (architect or {}).get("routes") or []:
        path = str(route.get("path") or "").strip()
        if not path.startswith("/") or ":" in path:
            continue
        normalized = path.rstrip("/") or "/"
        if normalized in _NAV_HOME_PATHS:
            continue
        if not _is_public_marketing_nav_path(normalized):
            continue
        label = _nav_label(str(route.get("title") or ""), normalized, brand_name)
        ranked.append((_nav_rank(normalized), normalized, label))
    ranked.sort(key=lambda entry: (entry[0], entry[1]))

    if not ranked:
        return dict(_NEUTRAL_CTA), dict(_NEUTRAL_CTA)
    primary = {"label": ranked[0][2], "href": ranked[0][1]}
    # A second CTA that repeats the first is worse than one that is simply the
    # home page, which is where the dead-link guard sent request 95's anyway.
    secondary = (
        {"label": ranked[1][2], "href": ranked[1][1]} if len(ranked) > 1 else dict(_NEUTRAL_CTA)
    )
    return primary, secondary


def _ts_label(cta: dict, key: str = "label") -> str:
    """One CTA field, escaped for a single-quoted TS literal.

    The labels are route titles now, so they carry whatever the model wrote —
    `Nonna's Menu` would end the string and break the module.
    """

    return str(cta.get(key) or ("/" if key == "href" else "")).replace(
        "\\", "\\\\"
    ).replace("'", "\\'")


def _ts_cta(cta: dict) -> str:
    return f"{{ label: '{_ts_label(cta)}', href: '{_ts_label(cta, key='href')}' }}"


def ensure_seed_scaffold_fields(
    mock: str, brand_name: str = "Brand", architect: dict | None = None
) -> str:
    """Guarantee the scaffold keys under `seed`, one key at a time.

    AI mock synthesis often replaces `seed` with domain-specific data and drops
    hero/cta/footer — HomePage then crashes on `seed.hero.headline`.

    Injecting the whole block whenever `hero` was absent re-declared every other
    key the model *had* written: request 43 shipped six TS1117 duplicate-property
    errors, with the stub first and the real content second (so the right value won
    by accident). Only missing keys are added now — the same lesson as the brand
    `design_system` patch.
    """
    if "export const seed" not in mock:
        return mock

    from app.application.preview_app.safety.seed_keys import _seed_span, _top_level_keys

    span = _seed_span(mock)
    if not span:
        return mock
    body_start, close_at = span
    existing = _top_level_keys(mock[body_start:close_at])

    brand = (brand_name or "Brand").replace("\\", "\\\\").replace("'", "\\'")
    primary_cta, secondary_cta = scaffold_hero_ctas(architect, brand_name)
    blocks: dict[str, str] = {
        "hero": (
            "hero: {\n"
            f"    eyebrow: '{brand}',\n"
            f"    headline: '{brand}',\n"
            f"    subcopy: 'A clear next step from {brand} — warm, specific, and ready when you are.',\n"
            f"    primaryCta: {_ts_cta(primary_cta)},\n"
            f"    secondaryCta: {_ts_cta(secondary_cta)},\n"
            "  }"
        ),
        "items": (
            "items: [\n"
            f"    {{ title: '{brand} signature', description: 'A dependable starting point at {brand}.' }},\n"
            "    { title: 'Everyday essential', description: 'Built for daily use.' },\n"
            f"    {{ title: 'Guest favorite', description: 'The one people come back to {brand} for.' }},\n"
            "  ]"
        ),
        "features": (
            "features: [\n"
            f"    {{ title: 'What {brand} is known for', description: 'Concrete offerings guests can book without guessing.' }},\n"
            "    { title: 'Guided next step', description: 'Every section points toward a clear action.' },\n"
            f"    {{ title: 'Built for return visits', description: 'Details that make {brand} easy to come back to.' }},\n"
            "  ]"
        ),
        "featuresHeading": f"featuresHeading: 'What {brand} offers'",
        "showcaseHeading": f"showcaseHeading: 'From {brand}'",
        # `seed.credentialsHeading` is read by the *home* page's trust strip.
        # A detail page never reads it — its specs strip is written with a
        # literal "Details" heading — so setting this to "Details" only ever
        # degraded the page it was not aimed at.
        "credentialsHeading": f"credentialsHeading: 'Why {brand}'",
        "credentials": (
            "credentials: [\n"
            f"    {{ title: 'Known for', detail: 'Clear work and a straightforward next step at {brand}.' }},\n"
            "    { title: 'Next step', detail: 'Browse, then inquire or book — no dead ends.' },\n"
            "  ]"
        ),
        "trustLabels": (
            "trustLabels: [\n"
            f"    '{brand} quality', 'On schedule', 'Repeat guests', 'Local favorite',\n"
            "  ]"
        ),
        # Both hrefs were `/contact#inquire`, a route no archived workspace
        # declares — the same literal the hero used, and the same defect.
        "cta": (
            "cta: {\n"
            f"    heading: 'Ready for {brand}?',\n"
            f"    description: 'Tell {brand} what you need — clear options, real next steps.',\n"
            f"    primaryLabel: '{_ts_label(primary_cta)}',\n"
            f"    primaryHref: '{_ts_label(primary_cta, key='href')}',\n"
            f"    secondaryLabel: '{_ts_label(secondary_cta)}',\n"
            f"    secondaryHref: '{_ts_label(secondary_cta, key='href')}',\n"
            "  }"
        ),
        "footer": (
            "footer: {\n"
            f"    description: '{brand} — clear choices and a real next step.',\n"
            "  }"
        ),
    }
    missing = [text for key, text in blocks.items() if key not in existing]
    if not missing:
        return mock
    inject = "".join(f"\n  {text}," for text in missing)
    updated, n = re.subn(
        r"(export const seed\s*=\s*\{)",
        lambda m: m.group(1) + inject,
        mock,
        count=1,
    )
    return updated if n else mock


def assert_brand_content_floor(workspace, brand_name: str) -> list[str]:
    """Guarantee brand content is never empty before build (one-shot quality floor).

    Fixes nested `services: []` / `products: []` inside BRAND_MANIFEST and any
    top-level empty list exports. Returns names of exports/fields repaired.
    """
    fixed: list[str] = []
    filled = enrich_empty_mock_exports(workspace, brand_name)
    fixed.extend(filled)

    mock_path = "src/data/mock.ts"
    mock = read_file(workspace, mock_path)
    if not mock.strip():
        return fixed

    services_json = json.dumps(_default_services(brand_name or "Brand"), ensure_ascii=False)
    products_json = json.dumps(_default_products(brand_name or "Brand"), ensure_ascii=False)
    updated = mock

    def _fill_empty_key(src: str, key: str, value_json: str) -> tuple[str, bool]:
        pattern = re.compile(
            rf"({key}\s*:\s*)\[\s*\]",
            re.MULTILINE,
        )
        if not pattern.search(src):
            return src, False
        return pattern.sub(rf"\g<1>{value_json}", src, count=1), True

    for key, value_json, label in (
        ("services", services_json, "BRAND_MANIFEST.services"),
        ("products", products_json, "BRAND_MANIFEST.products"),
    ):
        updated, changed = _fill_empty_key(updated, key, value_json)
        if changed:
            fixed.append(label)

    if updated != mock:
        write_file(workspace, mock_path, updated)
        guard_log.info("brand content floor repaired: %s", ", ".join(fixed))
    return fixed


def ensure_mock_exports(
    workspace, architect: dict, plan: dict, images: dict, brand_name: str
) -> list[str]:
    """Guarantee every symbol the pages import from mock.ts actually exists.

    Only APPENDS missing exports (never removes the AI's rich data). Pure
    build-correctness — prevents MISSING_EXPORT failures and fix-loop thrashing.
    """
    mock = read_file(workspace, "src/data/mock.ts")
    seeded = ensure_seed_scaffold_fields(mock, brand_name=brand_name, architect=architect)
    if seeded != mock:
        mock = seeded
        write_file(workspace, "src/data/mock.ts", mock)
        guard_log.info("seed scaffold keys completed for scaffold pages (brand=%s)", brand_name)
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


_IMAGES_EXPORT_RE = re.compile(
    r"export\s+const\s+images\s*=\s*\{.*?\n\};",
    re.DOTALL,
)
_UNSPLASH_URL_RE = re.compile(
    r"https://images\.unsplash\.com/photo-[A-Za-z0-9_-]+(?:\?[^\s'\"`)]*)?"
)
_DEAD_BOOK_HREFS = (
    "/book-appointment",
    "/book-appointments",
    "/booking-appointment",
)
_BRAND_POISON_RE = re.compile(
    r'brandName=\{(?:"Brand"|\'Brand\'|\{?"Brand"?\}|"Brand")\}'
)
_BRAND_POISON_SIMPLE = 'brandName={"Brand"}'
_BRAND_POISON_SIMPLE_ALT = "brandName={'Brand'}"


def dedupe_object_literal_keys(source: str, export_name: str) -> str:
    """Drop earlier duplicates of a key in a top-level ``export const X = {…};``.

    Last-wins, which is exactly what the JavaScript engine already does — the
    rewrite is behaviour-preserving by construction. What it removes is the
    *diagnostic*: request 66 shipped `item4`…`item8` twice in `images` and
    `tsc` reported five TS1117s, half of that run's ten type errors.

    The duplicates come from the AI that synthesizes `mock.ts`. That writer is
    checked for the exports pages need and for parsing, and TS1117 is neither —
    a duplicate key is perfectly parseable, so nothing downstream objected.
    """
    pattern = re.compile(
        r"(export\s+const\s+" + re.escape(export_name) + r"\s*=\s*\{)(.*?)(\n\};)",
        re.DOTALL,
    )
    match = pattern.search(source)
    if not match:
        return source
    body = match.group(2)
    lines = body.split("\n")
    key_re = re.compile(r"^\s*[\"']?([A-Za-z_$][\w$]*)[\"']?\s*:")
    # Only a flat, one-key-per-line literal is safe to filter this way; a nested
    # object would let a leading `}` line desynchronise the scan.
    if any(ch in body for ch in ("{", "[")):
        return source
    seen_last: dict[str, int] = {}
    for index, line in enumerate(lines):
        found = key_re.match(line)
        if found:
            seen_last[found.group(1)] = index
    kept = [
        line
        for index, line in enumerate(lines)
        if not (m := key_re.match(line)) or seen_last[m.group(1)] == index
    ]
    if len(kept) == len(lines):
        return source
    rebuilt = "\n".join(kept)
    # A dropped final entry can leave the last surviving line with a comma.
    rebuilt = re.sub(r",(\s*)$", r"\1", rebuilt)
    return source[: match.start(2)] + rebuilt + source[match.end(2) :]


def sync_mock_images(workspace, images: dict | None, brand_name: str | None = None) -> list[str]:
    """Force ``export const images`` to the pipeline slot map (stops AI photo-ID 404s).

    Also rewrites stray Unsplash URLs elsewhere in mock.ts / pages that are not in the
    curated/pipeline set — polish often invents ``photo-…`` IDs that 404.
    """
    from app.application.services.industry_images import (
        curated_library_urls,
        curated_photo_ids,
        normalize_image_slot_map,
    )

    slot_map = normalize_image_slot_map(
        {str(k): str(v) for k, v in (images or {}).items() if v}
    )
    if not slot_map:
        return []

    mock_path = "src/data/mock.ts"
    try:
        mock = read_file(workspace, mock_path)
    except Exception:
        return []

    actions: list[str] = []
    images_block = (
        "export const images = "
        + json.dumps(slot_map, indent=2, ensure_ascii=False)
        + ";\n"
    )
    if _IMAGES_EXPORT_RE.search(mock):
        updated = _IMAGES_EXPORT_RE.sub(images_block.rstrip(), mock, count=1)
    elif "export const images" not in mock:
        updated = mock.rstrip() + "\n\n" + images_block
    else:
        updated = mock

    if updated != mock:
        actions.append("images")
        mock = updated

    allowed = set(slot_map.values()) | set(curated_library_urls())
    allowed_ids = set(curated_photo_ids()) | {
        m.group(0)
        for url in allowed
        for m in [re.search(r"photo-[A-Za-z0-9_-]+", url)]
        if m
    }
    fallback_cycle = [slot_map[s] for s in ("card1", "card2", "card3", "hero", "ambient") if s in slot_map]
    if not fallback_cycle:
        fallback_cycle = list(slot_map.values())

    def _replace_url(match: re.Match[str], *, index: list[int]) -> str:
        url = match.group(0)
        pid = re.search(r"photo-[A-Za-z0-9_-]+", url)
        if pid and pid.group(0) in allowed_ids:
            return url
        # Keep non-Unsplash https (e.g. Pexels) untouched.
        if "images.unsplash.com" not in url:
            return url
        replacement = fallback_cycle[index[0] % len(fallback_cycle)]
        index[0] += 1
        return replacement

    idx = [0]
    scrubbed = _UNSPLASH_URL_RE.sub(lambda m: _replace_url(m, index=idx), mock)
    if scrubbed != mock:
        actions.append("unsplash-scrub")
        mock = scrubbed

    # A catalogue card may only name a photograph from the catalogue pool. The
    # mock writer is handed the whole slot map, so once it runs past `item8` it
    # keeps going into `card1`/`card2`/`card3` — the role slots whose photographs
    # show people. Request 70 shipped two of eleven cards as a person at an easel.
    from app.application.preview_app.catalogue_contract.item_source import (
        rebind_catalogue_item_images,
    )

    rebound, count = rebind_catalogue_item_images(mock)
    if count:
        actions.append(f"item-pool:{count}")
        guard_log.info(
            "catalogue photos rebound onto the item pool: %s card(s) named a "
            "layout slot",
            count,
        )
        mock = rebound

    # Dead booking CTAs — map to canonical /book (App.tsx also aliases these paths).
    rewritten = mock
    for dead in _DEAD_BOOK_HREFS:
        if dead in rewritten:
            rewritten = rewritten.replace(dead, "/book")
    if rewritten != mock:
        actions.append("book-href")
        mock = rewritten

    if actions:
        write_file(workspace, mock_path, mock)
        guard_log.info("sync_mock_images: %s", ", ".join(actions))

    # Scrub invented Unsplash + Brand poison across generated pages.
    brand = (brand_name or "").strip() or "Brand"
    brand_js = json.dumps(brand)
    page_actions = 0
    try:
        from app.application.preview_app.workspace import list_source_files

        page_paths = [
            p
            for p in list_source_files(workspace)
            if p.startswith("src/pages/") and p.endswith((".tsx", ".ts", ".jsx", ".js"))
        ]
    except Exception:
        page_paths = []

    for rel in page_paths:
        try:
            text = read_file(workspace, rel)
        except Exception:
            continue
        original = text
        pidx = [0]
        text = _UNSPLASH_URL_RE.sub(lambda m: _replace_url(m, index=pidx), text)
        for dead in _DEAD_BOOK_HREFS:
            if dead in text:
                text = text.replace(dead, "/book")
        if _BRAND_POISON_SIMPLE in text:
            text = text.replace(_BRAND_POISON_SIMPLE, f"brandName={{{brand_js}}}")
        if _BRAND_POISON_SIMPLE_ALT in text:
            text = text.replace(_BRAND_POISON_SIMPLE_ALT, f"brandName={{{brand_js}}}")
        # Also catch JSX string form brandName="Brand"
        text = re.sub(r'brandName="Brand"', f"brandName={{{brand_js}}}", text)
        text = re.sub(r"brandName='Brand'", f"brandName={{{brand_js}}}", text)
        if text != original:
            write_file(workspace, rel, text)
            page_actions += 1

    if page_actions:
        actions.append(f"pages:{page_actions}")
        guard_log.info("sync_mock_images scrubbed %s page file(s)", page_actions)
    return actions


# Nav ranks: primary journey first, contact last. AI hub is ops-only chrome —
# never re-ranked into public marketing nav (assemble public_marketing=True).
_NAV_HOME_PATHS = frozenset({"/", "/home", "/index"})
_NAV_OPS_PATHS = frozenset({"/ai-features"})
_OPS_NAV_PREFIXES = ("/admin", "/owner", "/ops", "/staff", "/member", "/desk", "/account")
_NAV_PRIMARY_TOKENS = frozenset(
    {
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
        "shop",
        "store",
        "products",
        "menu",
        "services",
        "treatments",
        "offerings",
        "packages",
        "classes",
        "workshops",
        "sessions",
        "schedule",
        "pricing",
        "rooms",
        "rentals",
    }
)
_NAV_LAST_TOKENS = frozenset(
    {"contact", "contact-us", "enquire", "inquire", "support", "help"}
)
# Same clean-nav notion quality_gate.nav_clutter enforces on the public list
# (>8 items, >2 deep paths) — assemble._nav_items_for already caps at 7.
_NAV_MAX_ITEMS = 7
_NAV_MAX_DEEP_ITEMS = 2
_NAV_LABEL_NOISE_RE = re.compile(
    r"^(welcome(\s+to)?|manage|my|the)\s+|\s+(page|overview)$", re.I
)


#: Terminal pages — where a form sends you, never where a link takes you.
_TERMINAL_LEAF_RE = re.compile(
    r"^(inquiry|enquiry|order|booking|payment|checkout|contact)?[-_]?"
    r"(confirm|confirmed|confirmation|thank[-_]?you|thanks|success|receipt|complete|completed|sent)$",
    re.I,
)


def _is_public_marketing_nav_path(path: str) -> bool:
    p = (path or "").rstrip("/") or "/"
    if p in _NAV_OPS_PATHS or p.startswith("/ai-"):
        return False
    # Request 66 carried `/inquiry-confirm` in the public nav, so every
    # "Contact" control on the site pointed at a page that says "Inquiry Sent"
    # and has no form on it.
    if _TERMINAL_LEAF_RE.match(p.rsplit("/", 1)[-1]):
        return False
    if any(p == root or p.startswith(f"{root}/") for root in _OPS_NAV_PREFIXES):
        return False
    return True


def _nav_rank(path: str) -> int:
    if path in _NAV_HOME_PATHS:
        return 0
    segments = [s for s in path.strip("/").split("/") if s]
    token = segments[0].lower() if segments else ""
    if token in _NAV_PRIMARY_TOKENS:
        return 1
    if token in _NAV_LAST_TOKENS:
        return 3
    return 2


def _brand_label_variants(brand_name: str) -> list[str]:
    """Every contiguous word run of the brand, longest first."""
    tokens = [token for token in re.split(r"\s+", str(brand_name or "").strip()) if token]
    windows = {
        " ".join(tokens[start:end])
        for start in range(len(tokens))
        for end in range(start + 1, len(tokens) + 1)
    }
    return sorted(windows, key=len, reverse=True)


def _nav_label(raw_label: str, path: str, brand_name: str) -> str:
    """Drop the brand name — the shell already shows it in the wordmark."""
    label = re.sub(r"\s+", " ", str(raw_label or "")).strip()
    for variant in _brand_label_variants(brand_name):
        stripped = re.sub(
            rf"\s*\b{re.escape(variant)}\b\s*", " ", label, flags=re.I
        ).strip(" -–—·|,")
        if stripped and stripped != label:
            label = re.sub(r"\s+", " ", stripped)
            break
    label = _NAV_LABEL_NOISE_RE.sub("", label).strip()
    if not label:
        segments = [s for s in path.strip("/").split("/") if s]
        label = segments[-1].replace("-", " ").replace("_", " ").title() if segments else "Home"
    return label


def _nav_key(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", label.lower())


def _norm_nav_path(path: str) -> str:
    """Compare nav hrefs the way the route table is keyed, not byte-for-byte.

    `live_paths` now comes from `served_route_paths`, which normalises; a nav
    entry written `/contact/` would otherwise read as dead and be dropped.
    """
    from app.application.preview_app.capabilities.journey import _norm

    return _norm(path)


def _normalize_nav_section(
    items: list,
    *,
    brand_name: str,
    live_paths: set[str],
    reorder: bool,
    clutter_cap: bool,
    public_marketing: bool = False,
) -> list[dict]:
    cleaned: list[dict] = []
    seen_paths: set[str] = set()
    seen_labels: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        path = str(item.get("href") or item.get("path") or "").strip()
        if not path.startswith("/") or ":" in path:
            continue
        if public_marketing and not _is_public_marketing_nav_path(path):
            continue
        if live_paths and _norm_nav_path(path) not in live_paths:
            continue
        label = _nav_label(item.get("label") or item.get("name") or "", path, brand_name)
        key = _nav_key(label)
        if path in seen_paths or (key and key in seen_labels):
            continue
        seen_paths.add(path)
        seen_labels.add(key)
        cleaned.append(
            {
                "id": str(item.get("id") or path.strip("/").replace("/", "-") or "home"),
                "path": path,
                "href": path,
                "label": label,
            }
        )
    if reorder:
        cleaned.sort(key=lambda entry: _nav_rank(entry["path"]))
    if not clutter_cap:
        return cleaned
    deep = 0
    capped: list[dict] = []
    for entry in cleaned:
        if entry["path"].count("/") >= 2:
            if deep >= _NAV_MAX_DEEP_ITEMS:
                continue
            deep += 1
        capped.append(entry)
        if len(capped) >= _NAV_MAX_ITEMS:
            break
    return capped


def normalize_mock_navigation(workspace, architect: dict, brand_name: str) -> list[str]:
    """Dedupe nav by destination and label, drop dead links, order the journey.

    `write_plumbing_mock` owns the first write and mock synthesis may replace it,
    so this runs before every build rather than once.
    """
    mock_path = "src/data/mock.ts"
    mock = read_file(workspace, mock_path)
    match = re.search(r"export const navigation\s*=\s*", mock)
    if not match:
        return []
    value_end = _mock_export_value_end(mock, match.end())
    raw_value = mock[match.end() : value_end].rstrip().rstrip(";")
    try:
        navigation = json.loads(raw_value)
    except ValueError:
        return []
    if not isinstance(navigation, dict):
        return []
    # The route table a *visitor* meets, not the one the planner declared. These
    # diverge, and judging the nav against the declared set is how requests 78
    # and 81 shipped nav entries for `/contact` and `/gallery` that no `<Route>`
    # served. `served_route_paths` reads `src/App.tsx` and falls back to the
    # architect only when there is no router yet, so this is strictly better
    # informed and still fail-open.
    from app.application.preview_app.capabilities.journey import served_route_paths

    live_paths = served_route_paths(workspace, architect or {})
    changed: list[str] = []
    normalized: dict[str, list] = {}
    for section, items in navigation.items():
        if not isinstance(items, list):
            normalized[section] = items
            continue
        section_items = _normalize_nav_section(
            items,
            brand_name=brand_name,
            live_paths=live_paths,
            reorder=section != "admin",
            # quality_gate.nav_clutter only measures the public list; an ops
            # sidebar is legitimately all-deep and longer.
            clutter_cap=section == "public",
            public_marketing=section == "public",
        )
        # Never blank out chrome — an empty navbar is worse than a cluttered one.
        normalized[section] = section_items or items
        if normalized[section] != items:
            changed.append(section)
    if not changed:
        return []
    updated = (
        mock[: match.end()]
        + json.dumps(normalized, indent=2, ensure_ascii=False)
        + ";"
        + mock[value_end:]
    )
    write_file(workspace, mock_path, updated)
    guard_log.info("navigation normalized: %s", ", ".join(changed))
    return [f"nav:{section}" for section in changed]
