"""Product Face Contract — brief/LLM owns copy + page_intent; packs gap-fill only."""
from __future__ import annotations

import copy
import re
from typing import Any

from app.application.preview_app.industry_templates.seed import (
    early_brand_placeholder_item_titles,
    early_brand_placeholder_strings,
    early_brand_trust_labels,
    normalize_mock_seed,
)

PAGE_INTENTS = frozenset(
    {
        "home",
        "listing",
        "detail",
        "booking",
        "confirm",
        "ops",
        "ai",
        "utility",
    }
)

_PUBLIC_SEED_KEYS = (
    "hero",
    "services",
    "features",
    "process",
    "testimonials",
    "credentials",
    "trustLabels",
    "treatments",
    "items",
    "showcaseHeading",
    "featuresHeading",
    "processHeading",
    "credentialsHeading",
    "testimonialsHeading",
    "cta",
    "footer",
    "nav_cta",
    "tone",
)

_OPS_SEED_KEYS = (
    "hero",
    "kpis",
    "items",
    "activity",
    "risk",
    "tableRows",
    "table",
    "tone",
)


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


def _item_title(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(
            entry.get("title") or entry.get("name") or entry.get("label") or ""
        ).strip()
    if isinstance(entry, str):
        return entry.strip()
    return ""


def _is_early_brand_placeholder_str(value: str) -> bool:
    """True for Brand-bearing sticky defaults (safe exact scrub / fillable)."""
    text = value.strip()
    if not text:
        return False
    if text == "Brand":
        return True
    # Only Brand-bearing leaves — shared generics ("Explore now", "Choose") may
    # appear in real pack/LLM copy and must not be wiped as fillable empty.
    return text in early_brand_placeholder_strings() and "Brand" in text


def _collect_string_leaves(value: Any, out: set[str]) -> None:
    if isinstance(value, str):
        text = value.strip()
        if text:
            out.add(text)
        return
    if isinstance(value, list):
        for entry in value:
            _collect_string_leaves(entry, out)
        return
    if isinstance(value, dict):
        for entry in value.values():
            _collect_string_leaves(entry, out)


def _entry_is_early_placeholder(entry: Any) -> bool:
    """True for Brand-default list rows (exact string match / known early titles)."""
    if isinstance(entry, str):
        return _is_early_brand_placeholder_str(entry)
    if not isinstance(entry, dict):
        return False
    title = _item_title(entry)
    # Per-item early titles + any Brand-bearing default title — drop even if
    # description was hand-edited mush ("placeholder").
    if title in early_brand_placeholder_item_titles() and (
        "Brand" in title or title in {"Everyday essential", "Guest favorite"}
    ):
        return True
    leaves: set[str] = set()
    _collect_string_leaves(entry, leaves)
    if not leaves:
        return True
    placeholders = early_brand_placeholder_strings()
    return all(leaf in placeholders for leaf in leaves)


def _string_list_is_early_trust_defaults(value: list[Any]) -> bool:
    """True when every non-empty string is an exact Brand-default trustLabel.

    Covers full mixed Brand+Brand-less defaults and Brand-less orphan subsets
    left after a Brand-bearing member was already scrubbed.
    """
    if not value or not all(isinstance(entry, str) for entry in value):
        return False
    texts = [entry.strip() for entry in value if entry.strip()]
    if not texts:
        return True
    labels = early_brand_trust_labels()
    return all(text in labels for text in texts)


def _scrub_early_trust_string_list(value: list[Any]) -> list[Any]:
    """Drop Brand-default trustLabels (full, co-resident, or orphan subset).

    Real pack strings outside the Brand trust set survive; lone shared CTAs are
    unaffected (not trustDefaults). Dict-item lists use the mixed-entry path.
    """
    texts = [str(entry).strip() for entry in value if isinstance(entry, str)]
    non_empty = [text for text in texts if text]
    if not non_empty:
        return []
    labels = early_brand_trust_labels()
    if all(text in labels for text in non_empty):
        return []
    # Mixed list: drop Brand-bearing + co-resident Brand-less trustDefaults only
    # when a Brand-bearing early member is present in the same list.
    has_brand_bearing = any(_is_early_brand_placeholder_str(text) for text in non_empty)
    if has_brand_bearing:
        return [text for text in non_empty if text not in labels]
    return list(non_empty)


def _list_is_early_default_items(value: list[Any]) -> bool:
    """True when every item is an early Brand-default placeholder entry."""
    if not value:
        return True
    if all(isinstance(entry, str) for entry in value):
        return _string_list_is_early_trust_defaults(value)
    return all(_entry_is_early_placeholder(entry) for entry in value)


def _is_fillable_empty(value: Any) -> bool:
    """Empty for gap-fill/lift, including Brand-templated normalize defaults."""
    if _is_empty(value):
        return True
    if isinstance(value, str) and _is_early_brand_placeholder_str(value):
        return True
    if isinstance(value, list) and _list_is_early_default_items(value):
        return True
    return False


def _scrub_early_placeholders(value: Any) -> Any:
    """Clear Brand-templated normalize defaults so brand-bound normalize can fill."""
    if isinstance(value, str):
        return "" if _is_early_brand_placeholder_str(value) else value
    if isinstance(value, list):
        if value and all(isinstance(entry, str) for entry in value):
            return _scrub_early_trust_string_list(value)
        scrubbed: list[Any] = []
        for entry in value:
            if _entry_is_early_placeholder(entry):
                continue
            if isinstance(entry, dict):
                scrubbed.append(_scrub_early_placeholders(entry))
            else:
                scrubbed.append(entry)
        return scrubbed
    if isinstance(value, dict):
        return {k: _scrub_early_placeholders(v) for k, v in value.items()}
    return value


def _write_back_scrubbed_public_seed(
    face: dict[str, Any],
    seed: dict[str, Any],
) -> dict[str, Any]:
    """Sync rematerialized public keys onto face after early-default scrub.

    Only keys already on ``public_seed`` whose scrub left them fillable —
    covers sticky Brand-less orphan lists. Never invents into truly empty keys
    or clobbers pack/LLM copy that scrub preserved.
    """
    public = dict(face.get("public_seed") or {})
    if not public:
        return face
    scrubbed = _scrub_early_placeholders(copy.deepcopy(public))
    if not isinstance(scrubbed, dict):
        scrubbed = {}
    updated_public = dict(public)
    changed = False
    for key in list(public.keys()):
        if key not in _PUBLIC_SEED_KEYS:
            continue
        orig = public.get(key)
        # Truly empty — do not invent normalize defaults onto the face.
        if _is_empty(orig):
            continue
        if not _is_fillable_empty(scrubbed.get(key)):
            continue
        rematerialized = seed.get(key)
        if _is_fillable_empty(rematerialized):
            continue
        updated_public[key] = copy.deepcopy(rematerialized)
        changed = True
    if not changed:
        return face
    out = dict(face)
    out["public_seed"] = updated_public
    return out


def _deep_gap_fill(base: dict[str, Any], filler: dict[str, Any]) -> dict[str, Any]:
    """Copy filler keys into base only where base is missing/empty. Never overwrite."""
    out = dict(base or {})
    for key, fval in (filler or {}).items():
        if key not in out or _is_fillable_empty(out.get(key)):
            if isinstance(fval, dict):
                out[key] = _deep_gap_fill({}, fval)
            else:
                out[key] = copy.deepcopy(fval)
        elif isinstance(out.get(key), dict) and isinstance(fval, dict):
            out[key] = _deep_gap_fill(dict(out[key]), fval)
    return out


def normalize_page_intent(raw: Any, *, path: str = "", skeleton_id: str = "", surface: str = "") -> str:
    """Normalize or infer a closed page_intent."""
    text = str(raw or "").strip().lower()
    aliases = {
        "homepage": "home",
        "landing": "home",
        "catalog": "listing",
        "catalogue": "listing",
        "directory": "listing",
        "schedule": "listing",
        "list": "listing",
        "service": "listing",
        "services": "listing",
        "book": "booking",
        "reservation": "booking",
        "confirmation": "confirm",
        "success": "confirm",
        "dashboard": "ops",
        "admin": "ops",
        "workspace": "ops",
        "desk": "ops",
        "ai-features": "ai",
        "ai_hub": "ai",
    }
    if text in PAGE_INTENTS:
        return text
    if text in aliases:
        return aliases[text]

    path_l = (path or "").rstrip("/").lower() or "/"
    sk = (skeleton_id or "").lower()
    surf = (surface or "").lower()

    if path_l == "/ai-features" or "aifeature" in path_l:
        return "ai"
    if surf == "ops" or sk.startswith("ops"):
        return "ops"
    if sk == "public-home" or path_l in {"/", "/home"}:
        return "home"
    if sk == "public-booking" or re.search(r"/(book|booking|reserve)", path_l):
        return "booking"
    if sk in {"public-utility"} or re.search(
        r"/(cart|checkout|login|account|track)", path_l
    ):
        return "utility"
    if re.search(r"/(confirm|success|thank)", path_l):
        return "confirm"
    if sk == "public-detail" or re.search(r"/:\w+|/\d+$", path_l):
        return "detail"
    if sk in {"public-service", "public-catalog"}:
        return "listing"
    return "utility"


def infer_intent_from_page(page: dict[str, Any]) -> str:
    return normalize_page_intent(
        page.get("page_intent") or page.get("page_type"),
        path=str(page.get("path") or ""),
        skeleton_id=str(page.get("skeleton_id") or ""),
        surface=str(page.get("surface") or ""),
    )


def _routes_from_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    seen: set[str] = set()

    for rt in plan.get("routes") or []:
        if not isinstance(rt, dict) or not rt.get("path"):
            continue
        path = str(rt["path"])
        if path in seen:
            continue
        seen.add(path)
        intent = normalize_page_intent(
            rt.get("page_intent"),
            path=path,
            skeleton_id=str(rt.get("skeleton_id") or ""),
            surface=str(rt.get("surface") or ""),
        )
        routes.append(
            {
                "path": path,
                "title": str(rt.get("title") or path),
                "role_id": str(rt.get("role_id") or ""),
                "page_intent": intent,
                "skeleton_id": str(rt.get("skeleton_id") or ""),
                "surface": str(rt.get("surface") or ("ops" if intent == "ops" else "public")),
            }
        )

    for role in plan.get("roles") or []:
        if not isinstance(role, dict):
            continue
        rid = str(role.get("id") or "")
        for page in role.get("pages") or []:
            if not isinstance(page, dict):
                continue
            path = str(page.get("path") or "").strip()
            if not path:
                # Pages often lack path until architect — skip path-less here.
                continue
            if path in seen:
                continue
            seen.add(path)
            intent = infer_intent_from_page(page)
            routes.append(
                {
                    "path": path,
                    "title": str(page.get("title") or path),
                    "role_id": rid,
                    "page_intent": intent,
                    "skeleton_id": str(page.get("skeleton_id") or ""),
                    "surface": str(page.get("surface") or ""),
                }
            )
    return routes


def _roles_from_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for role in plan.get("roles") or []:
        if not isinstance(role, dict) or not role.get("id"):
            continue
        out.append(
            {
                "id": str(role["id"]),
                "label": str(role.get("label") or role["id"]),
                "tagline": str(role.get("tagline") or ""),
                "defaultPath": str(role.get("defaultPath") or role.get("default_path") or ""),
                "icon": str(role.get("icon") or "users"),
            }
        )
    return out


def _slice_seed(raw: dict[str, Any] | None, keys: tuple[str, ...]) -> dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    out: dict[str, Any] = {}
    for k in keys:
        if k not in src or _is_fillable_empty(src.get(k)):
            continue
        val = _scrub_early_placeholders(copy.deepcopy(src[k]))
        if _is_fillable_empty(val):
            continue
        out[k] = val
    return out


_ITEM_ALIAS_KEYS = (
    "products",
    "dishes",
    "treatments",
    "classes",
    "services",
    "offerings",
)


def _collapse_pack_aliases(pack_seed: dict[str, Any] | None) -> dict[str, Any]:
    """Map pack-only keys (classes/products/…) into contract keys — no Brand defaults."""
    raw = copy.deepcopy(pack_seed) if isinstance(pack_seed, dict) else {}
    if _is_fillable_empty(raw.get("items")):
        for key in _ITEM_ALIAS_KEYS:
            if not _is_fillable_empty(raw.get(key)):
                raw["items"] = copy.deepcopy(raw[key])
                break
    if _is_fillable_empty(raw.get("process")) and not _is_fillable_empty(raw.get("steps")):
        raw["process"] = copy.deepcopy(raw["steps"])
    return raw


def extract_product_face(plan: dict[str, Any] | None) -> dict[str, Any]:
    """Build a normalized product_face from plan + any existing face/seeds."""
    plan = plan or {}
    existing = plan.get("product_face") if isinstance(plan.get("product_face"), dict) else {}

    roles = list(existing.get("roles") or []) or _roles_from_plan(plan)
    routes = list(existing.get("routes") or []) or _routes_from_plan(plan)
    # Stamp intents on existing routes.
    normalized_routes: list[dict[str, Any]] = []
    for rt in routes:
        if not isinstance(rt, dict):
            continue
        path = str(rt.get("path") or "")
        if not path:
            continue
        intent = normalize_page_intent(
            rt.get("page_intent"),
            path=path,
            skeleton_id=str(rt.get("skeleton_id") or ""),
            surface=str(rt.get("surface") or ""),
        )
        normalized_routes.append({**rt, "path": path, "page_intent": intent})

    # Also stamp page_intent onto plan role pages for downstream architect.
    public_seed = dict(existing.get("public_seed") or {})
    ops_seed = dict(existing.get("ops_seed") or {})

    # Promote plan-level seeds if present (LLM may emit these).
    if isinstance(plan.get("public_seed"), dict):
        public_seed = _deep_gap_fill(public_seed, plan["public_seed"])
    if isinstance(plan.get("ops_seed"), dict):
        ops_seed = _deep_gap_fill(ops_seed, plan["ops_seed"])

    # Lift from mock_seed without treating pack overwrite as authority later.
    mock = plan.get("mock_seed") if isinstance(plan.get("mock_seed"), dict) else {}
    if mock:
        public_seed = _deep_gap_fill(
            public_seed, _slice_seed(_collapse_pack_aliases(mock), _PUBLIC_SEED_KEYS)
        )
        if isinstance(mock.get("opsHero"), dict) and _is_fillable_empty(ops_seed.get("hero")):
            scrubbed_ops_hero = _scrub_early_placeholders(copy.deepcopy(mock["opsHero"]))
            if not _is_fillable_empty(scrubbed_ops_hero):
                ops_seed["hero"] = scrubbed_ops_hero
        ops_seed = _deep_gap_fill(
            ops_seed,
            {
                k: mock[k]
                for k in ("kpis", "activity", "risk", "tableRows", "table")
                if k in mock and not _is_fillable_empty(mock.get(k))
            },
        )
        if mock.get("opsItems") and _is_fillable_empty(ops_seed.get("items")):
            scrubbed_ops_items = _scrub_early_placeholders(copy.deepcopy(mock["opsItems"]))
            if not _is_fillable_empty(scrubbed_ops_items):
                ops_seed["items"] = scrubbed_ops_items

    return {
        "version": 1,
        "roles": roles,
        "routes": normalized_routes,
        "public_seed": public_seed,
        "ops_seed": ops_seed,
    }


def gap_fill_public_seed_from_pack(
    face: dict[str, Any],
    pack_seed: dict[str, Any] | None,
    *,
    brand_name: str | None = None,
) -> dict[str, Any]:
    """Fill empty public_seed fields from a pack mock_seed. Never overwrite.

    Slices the raw pack only (alias collapse, no Brand defaults) — branded
    ``normalize_mock_seed`` runs once in ``materialize_mock_seed``.
    ``brand_name`` kept for call-site compat.
    """
    updated = dict(face or {})
    public = dict(updated.get("public_seed") or {})
    raw = _collapse_pack_aliases(pack_seed if isinstance(pack_seed, dict) else {})
    filler = _slice_seed(raw, _PUBLIC_SEED_KEYS)
    updated["public_seed"] = _deep_gap_fill(public, filler)
    return updated


def gap_fill_ops_seed_from_pack(
    face: dict[str, Any],
    pack_seed: dict[str, Any] | None,
    *,
    brand_name: str | None = None,
) -> dict[str, Any]:
    """Fill empty ops_seed fields from an ops pack. Never overwrite.

    Slices the raw pack only (alias collapse, no Brand defaults) — branded
    ``normalize_mock_seed`` runs once in ``materialize_mock_seed``.
    ``brand_name`` kept for call-site compat.
    """
    updated = dict(face or {})
    ops = dict(updated.get("ops_seed") or {})
    raw = _collapse_pack_aliases(pack_seed if isinstance(pack_seed, dict) else {})
    filler = _slice_seed(raw, _OPS_SEED_KEYS)
    # Pack hero → ops hero only when empty.
    if raw.get("hero") and _is_fillable_empty(ops.get("hero")):
        scrubbed_hero = _scrub_early_placeholders(copy.deepcopy(raw["hero"]))
        if not _is_fillable_empty(scrubbed_hero):
            filler["hero"] = scrubbed_hero
    updated["ops_seed"] = _deep_gap_fill(ops, filler)
    return updated


def materialize_mock_seed(
    face: dict[str, Any] | None,
    *,
    brand_name: str | None = None,
    fill_defaults: bool = True,
) -> dict[str, Any]:
    """Flatten product_face into scaffold mock_seed (public + opsHero/kpis)."""
    face = face or {}
    public = dict(face.get("public_seed") or {})
    ops = dict(face.get("ops_seed") or {})
    if fill_defaults:
        scrubbed = _scrub_early_placeholders(public)
        if not isinstance(scrubbed, dict):
            scrubbed = {}
        seed = normalize_mock_seed(scrubbed, brand_name=brand_name)
    else:
        # Pass-through merge only — no Brand / pack defaults before gap-fill.
        seed = copy.deepcopy(public)
    if ops.get("hero"):
        seed["opsHero"] = copy.deepcopy(ops["hero"])
    for key in ("kpis", "activity", "risk", "tableRows", "table"):
        if ops.get(key):
            seed[key] = copy.deepcopy(ops[key])
    if ops.get("items"):
        seed["opsItems"] = copy.deepcopy(ops["items"])
    if ops.get("tone"):
        seed["opsTone"] = ops["tone"]
    return seed


def stamp_page_intents_on_plan(
    plan: dict[str, Any] | None,
    *,
    brand_name: str | None = None,
    fill_defaults: bool = True,
) -> dict[str, Any]:
    """Write page_intent onto role pages and routes from product_face / inference."""
    updated = dict(plan or {})
    face = extract_product_face(updated)
    intent_by_path = {
        str(rt["path"]): rt["page_intent"]
        for rt in face.get("routes") or []
        if rt.get("path")
    }

    roles = []
    for role in updated.get("roles") or []:
        if not isinstance(role, dict):
            continue
        role = dict(role)
        pages = []
        for page in role.get("pages") or []:
            if not isinstance(page, dict):
                continue
            page = dict(page)
            path = str(page.get("path") or "")
            page["page_intent"] = (
                intent_by_path.get(path)
                or infer_intent_from_page(page)
            )
            pages.append(page)
        role["pages"] = pages
        roles.append(role)
    updated["roles"] = roles

    routes = []
    for rt in updated.get("routes") or []:
        if not isinstance(rt, dict):
            continue
        rt = dict(rt)
        path = str(rt.get("path") or "")
        rt["page_intent"] = intent_by_path.get(path) or normalize_page_intent(
            rt.get("page_intent"),
            path=path,
            skeleton_id=str(rt.get("skeleton_id") or ""),
            surface=str(rt.get("surface") or ""),
        )
        routes.append(rt)
    if routes:
        updated["routes"] = routes

    updated["product_face"] = face
    updated["mock_seed"] = materialize_mock_seed(
        face, brand_name=brand_name, fill_defaults=fill_defaults
    )
    if fill_defaults:
        updated["product_face"] = _write_back_scrubbed_public_seed(
            updated["product_face"], updated["mock_seed"]
        )
    return updated


def ensure_product_face_on_plan(
    plan: dict[str, Any] | None,
    *,
    brand_name: str | None = None,
    fill_defaults: bool = True,
) -> dict[str, Any]:
    """Normalize product_face, stamp intents, materialize mock_seed."""
    return stamp_page_intents_on_plan(
        plan, brand_name=brand_name, fill_defaults=fill_defaults
    )


def face_is_thin(face: dict[str, Any] | None) -> bool:
    """True when packs are allowed to contribute substantive seed."""
    face = face or {}
    public = face.get("public_seed") or {}
    ops = face.get("ops_seed") or {}
    has_public = bool(public.get("hero") or public.get("features") or public.get("services"))
    has_ops = bool(ops.get("hero") or ops.get("kpis") or ops.get("items"))
    return not (has_public or has_ops)
