"""Product Face Contract — brief/LLM owns copy + page_intent; packs gap-fill only."""
from __future__ import annotations

import copy
import re
from typing import Any

from app.application.preview_app.industry_templates.seed import normalize_mock_seed

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


def _deep_gap_fill(base: dict[str, Any], filler: dict[str, Any]) -> dict[str, Any]:
    """Copy filler keys into base only where base is missing/empty. Never overwrite."""
    out = dict(base or {})
    for key, fval in (filler or {}).items():
        if key not in out or _is_empty(out.get(key)):
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
    return {k: copy.deepcopy(src[k]) for k in keys if k in src and not _is_empty(src.get(k))}


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
        public_seed = _deep_gap_fill(public_seed, _slice_seed(mock, _PUBLIC_SEED_KEYS))
        if isinstance(mock.get("opsHero"), dict) and _is_empty(ops_seed.get("hero")):
            ops_seed["hero"] = copy.deepcopy(mock["opsHero"])
        ops_seed = _deep_gap_fill(
            ops_seed,
            {
                k: mock[k]
                for k in ("kpis", "activity", "risk", "tableRows", "table")
                if k in mock and not _is_empty(mock.get(k))
            },
        )
        if mock.get("opsItems") and _is_empty(ops_seed.get("items")):
            ops_seed["items"] = copy.deepcopy(mock["opsItems"])

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
) -> dict[str, Any]:
    """Fill empty public_seed fields from a pack mock_seed. Never overwrite."""
    updated = dict(face or {})
    public = dict(updated.get("public_seed") or {})
    pack = normalize_mock_seed(pack_seed if isinstance(pack_seed, dict) else None)
    filler = _slice_seed(pack, _PUBLIC_SEED_KEYS)
    updated["public_seed"] = _deep_gap_fill(public, filler)
    return updated


def gap_fill_ops_seed_from_pack(
    face: dict[str, Any],
    pack_seed: dict[str, Any] | None,
) -> dict[str, Any]:
    """Fill empty ops_seed fields from an ops pack. Never overwrite."""
    updated = dict(face or {})
    ops = dict(updated.get("ops_seed") or {})
    pack = normalize_mock_seed(pack_seed if isinstance(pack_seed, dict) else None)
    filler = _slice_seed(pack, _OPS_SEED_KEYS)
    # Pack hero → ops hero only when empty.
    if pack.get("hero") and _is_empty(ops.get("hero")):
        filler["hero"] = pack["hero"]
    updated["ops_seed"] = _deep_gap_fill(ops, filler)
    return updated


def materialize_mock_seed(face: dict[str, Any] | None) -> dict[str, Any]:
    """Flatten product_face into scaffold mock_seed (public + opsHero/kpis)."""
    face = face or {}
    public = dict(face.get("public_seed") or {})
    ops = dict(face.get("ops_seed") or {})
    seed = normalize_mock_seed(public)
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


def stamp_page_intents_on_plan(plan: dict[str, Any] | None) -> dict[str, Any]:
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
    updated["mock_seed"] = materialize_mock_seed(face)
    return updated


def ensure_product_face_on_plan(plan: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize product_face, stamp intents, materialize mock_seed."""
    return stamp_page_intents_on_plan(plan)


def face_is_thin(face: dict[str, Any] | None) -> bool:
    """True when packs are allowed to contribute substantive seed."""
    face = face or {}
    public = face.get("public_seed") or {}
    ops = face.get("ops_seed") or {}
    has_public = bool(public.get("hero") or public.get("features") or public.get("services"))
    has_ops = bool(ops.get("hero") or ops.get("kpis") or ops.get("items"))
    return not (has_public or has_ops)
