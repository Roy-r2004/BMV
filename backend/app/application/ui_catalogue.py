"""Read and resolve the template-owned UI catalogue for preview generation."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from app.core.config import settings


_SKELETON_FIELDS = (
    "id",
    "surface",
    "shell",
    "purpose",
    "requiredSections",
    "optionalSections",
    "recommendedOrder",
    "supportedVariants",
)
_COMPONENT_FIELDS = ("name", "requiredProps", "optionalProps", "variants")
_SHELL_NAVIGATION_COMPONENTS = {
    "PublicShell": ("PublicNav",),
    "OpsShell": (),
}
_SLOT_COMPONENT_DEFAULTS = {
    "shell": None,
    "hero": "MarketingHero",
    "features": "FeatureBento",
    "showcase": "ProductShowcase",
    "process": "ProcessSection",
    "testimonials": "TestimonialRail",
    "cta": "CTABand",
    "footer": "BrandFooter",
    "trust": "LogoMarquee",
    "credentials": "CredentialStrip",
    "spotlight": "SpotlightCard",
    "results": "ResultRail",
    "booking": "BookingPanel",
    "workspace": "Card",
    "summary": "Card",
    "header": "PageHeader",
    "kpis": "StatCard",
    "chart": "ChartCard",
    "filters": "FilterBar",
    "table": "DataTable",
    "activity": "ActivityFeed",
    "risk": "RiskQueue",
    "empty": "EmptyState",
    # Signature product-face slots (accounting / trading)
    "pulse": "CashPulseBar",
    "board": "InvoiceBoard",
    "recon": "ReconSplit",
    "blotter": "BlotterTape",
    "ticker": "DeskTicker",
}


@lru_cache(maxsize=1)
def load_catalogue() -> dict[str, Any]:
    """Load the generated catalogue from the configured preview template."""
    path = settings.PREVIEW_TEMPLATE_DIR / "src" / "ui" / "catalogue.json"
    try:
        with path.open(encoding="utf-8") as handle:
            catalogue = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid UI catalogue JSON at {path}: {exc.msg}") from exc
    if not isinstance(catalogue, dict):
        raise ValueError(f"Invalid UI catalogue at {path}: root must be a JSON object")
    if not isinstance(catalogue.get("components"), list):
        raise ValueError(f"Invalid UI catalogue at {path}: components must be an array")
    if not isinstance(catalogue.get("skeletons"), list):
        raise ValueError(f"Invalid UI catalogue at {path}: skeletons must be an array")
    if not all(isinstance(item, dict) and item.get("name") for item in catalogue["components"]):
        raise ValueError(f"Invalid UI catalogue at {path}: every component must be an object with a name")
    if not all(isinstance(item, dict) and item.get("id") for item in catalogue["skeletons"]):
        raise ValueError(f"Invalid UI catalogue at {path}: every skeleton must be an object with an id")
    return catalogue


def get_skeleton(skeleton_id: str) -> dict[str, Any]:
    """Return one skeleton by its catalogue ID."""
    for skeleton in load_catalogue()["skeletons"]:
        if skeleton.get("id") == skeleton_id:
            return skeleton
    raise ValueError(f"Unknown UI skeleton: {skeleton_id}")


def _search_text(page: dict[str, Any]) -> str:
    values = (
        page.get("id"),
        page.get("title"),
        page.get("page_type"),
        page.get("purpose"),
        page.get("layout"),
        page.get("path"),
        page.get("role_id"),
        page.get("role_label"),
    )
    return " ".join(str(value).lower() for value in values if value)


def _infer_surface(page: dict[str, Any]) -> str:
    explicit = str(page.get("surface") or "").lower()
    if explicit in {"public", "ops"}:
        return explicit

    skeleton_id = str(page.get("skeleton_id") or "")
    if skeleton_id.startswith("ops-"):
        return "ops"
    if skeleton_id.startswith("public-"):
        return "public"

    layout = str(page.get("layout") or "").lower()
    path = str(page.get("path") or "").lower()
    page_type = str(page.get("page_type") or "").lower()
    role = " ".join(
        str(page.get(key) or "").lower() for key in ("role_id", "role_label")
    )
    text = _search_text(page)
    if layout in {"admin", "ops", "dashboard"}:
        return "ops"
    if re.search(r"(^|/)(admin|owner|ops)(/|$)", path):
        return "ops"
    role_tokens = set(re.findall(r"[a-z]+", role))
    if role_tokens & {"public", "customer", "client", "guest", "patient"}:
        return "public"
    if role_tokens & {
        "owner",
        "admin",
        "administrator",
        "ops",
        "operator",
        "operations",
        "staff",
        "manager",
        "trader",
        "portfolio",
        "execution",
        "risk",
        "pm",
    }:
        return "ops"
    if any(
        word in page_type
        for word in (
            "dashboard",
            "operational",
            "record detail",
            "settings",
            "configuration",
            "trading",
            "blotter",
            "desk",
        )
    ):
        return "ops"
    if any(
        word in text
        for word in (
            "dashboard",
            "back office",
            "operations",
            "admin portal",
            "blotter",
            "trading desk",
            "order ticket",
            "hedge fund",
            "invoice",
            "bookkeep",
            "reconcil",
            "workspace",
            "work queue",
        )
    ):
        return "ops"
    # Explicit product-kind lock from planner / product_kind module
    product_kind = str(page.get("product_kind") or "").lower()
    if product_kind in {"saas_workspace", "internal_ops"}:
        return "ops"
    return "public"


def _infer_skeleton_id(page: dict[str, Any], surface: str) -> str:
    explicit = str(page.get("skeleton_id") or "")
    if explicit:
        try:
            skeleton = get_skeleton(explicit)
        except ValueError:
            pass
        else:
            if skeleton.get("surface") == surface:
                return explicit

    path = str(page.get("path") or "").lower().rstrip("/")
    text = _search_text(page)
    if surface == "ops":
        if any(word in text for word in ("setting", "configuration", "preferences")):
            return "ops-settings"
        if any(word in text for word in ("dashboard", "overview", "analytics", "insights")):
            return "ops-dashboard"
        if any(word in text for word in ("detail", "profile", "record")) or (
            path and re.search(r"/(?:\d+|:[^/]+|\[[^\]]+\])$", path)
        ):
            return "ops-detail"
        return "ops-list"

    # Transactional flows first: judged as marketing pages they would be
    # rejected for missing hero/testimonials and fall back to scaffolds.
    if any(
        word in text
        for word in (
            "cart",
            "checkout",
            "order status",
            "track order",
            "order tracking",
            "tracking",
            "wishlist",
            "my orders",
            "order history",
            "account",
            "login",
            "sign in",
            "sign up",
            "register",
        )
    ):
        return "public-utility"
    if any(word in text for word in ("book", "appointment", "reserve", "intake", "schedule")):
        return "public-booking"
    if path == "/" or any(word in text for word in ("home", "landing", "homepage")):
        return "public-home"
    if any(word in text for word in ("detail", "single product", "single service", "treatment detail")):
        return "public-detail"
    if path and re.search(r"/(?:services?|products?|treatments?)/[^/]+$", path):
        return "public-detail"
    if any(
        word in text
        for word in ("catalog", "catalogue", "shop", "store", "browse", "collection", "compare")
    ) or (path and re.search(r"/(?:shop|store|products|catalog)$", path)):
        return "public-catalog"
    return "public-service"


def infer_page_contract(page: dict[str, Any]) -> dict[str, str]:
    """Infer additive catalogue fields for a legacy plan page or route."""
    surface = _infer_surface(page)
    return {
        "surface": surface,
        "skeleton_id": _infer_skeleton_id(page, surface),
    }


def infer_section_slots(page: dict[str, Any], skeleton_id: str) -> list[str]:
    """Return valid slots in skeleton order, completing required content slots."""
    skeleton = get_skeleton(skeleton_id)
    recommended = list(skeleton.get("recommendedOrder") or [])
    required = list(skeleton.get("requiredSections") or [])
    optional = list(skeleton.get("optionalSections") or [])
    allowed_slots = set(required) | set(optional)
    allowed_slots.discard("shell")
    slot_order = recommended + [
        slot for slot in (*required, *optional) if slot not in recommended
    ]
    allowed_components = set(skeleton.get("allowedComponents") or [])
    source = page.get("section_slots")
    if not isinstance(source, list) or not source:
        source = page.get("sections")

    requested: set[str] = set()
    if isinstance(source, list):
        for item in source:
            if isinstance(item, str):
                name = item
            elif isinstance(item, dict):
                name = item.get("slot") or item.get("name") or item.get("id") or ""
            else:
                name = ""
            normalized = str(name).strip()
            if normalized in allowed_slots:
                requested.add(normalized)

    if not requested:
        requested.update(slot for slot in required if slot != "shell")
    else:
        requested.update(slot for slot in required if slot != "shell")

    selected = requested | {slot for slot in required if slot != "shell"}
    for slot in selected:
        component = skeleton.get("shell") if slot == "shell" else _SLOT_COMPONENT_DEFAULTS.get(slot)
        if not component or component not in allowed_components:
            raise ValueError(
                f"Skeleton {skeleton_id} has no valid allowed component default for slot {slot}"
            )
    return [slot for slot in slot_order if slot in selected]


def compact_skeleton_contract(
    skeleton_id: str,
    section_slots: list[str] | None = None,
) -> dict[str, Any]:
    """Return only the chosen skeleton and metadata for its allowed components."""
    catalogue = load_catalogue()
    skeleton = get_skeleton(skeleton_id)
    allowed = set(skeleton.get("allowedComponents") or [])
    slots = infer_section_slots({"section_slots": section_slots or []}, skeleton_id)
    shell_component = str(skeleton.get("shell") or "")
    navigation_components = [
        name
        for name in _SHELL_NAVIGATION_COMPONENTS.get(shell_component, ())
        if name in allowed
    ]
    selected_names: list[str] = [
        name
        for name in (shell_component, *navigation_components)
        if name and name in allowed
    ]
    # Include every skeleton-allowed component so validators/prompts accept
    # Button, Badge, Input, DataTable, etc. — not only shell/slot defaults.
    for name in sorted(allowed):
        if name and name not in selected_names:
            selected_names.append(name)
    slot_components: dict[str, str] = {}
    for slot in slots:
        name = skeleton.get("shell") if slot == "shell" else _SLOT_COMPONENT_DEFAULTS.get(slot)
        if not name or name not in allowed:
            continue
        slot_components[slot] = name
        if name not in selected_names:
            selected_names.append(name)
    components_by_name = {
        component["name"]: component for component in catalogue["components"]
    }
    components = [
        {
            key: components_by_name[name][key]
            for key in _COMPONENT_FIELDS
            if key in components_by_name[name]
        }
        for name in selected_names
        if name in components_by_name
    ]
    skeleton_contract = {
        key: skeleton[key] for key in _SKELETON_FIELDS if key in skeleton
    }
    supported = skeleton_contract.get("supportedVariants")
    if isinstance(supported, dict):
        skeleton_contract["supportedVariants"] = {
            name: variants for name, variants in supported.items() if name in selected_names
        }
    contract: dict[str, Any] = {
        "skeleton": skeleton_contract,
        "shell_component": shell_component,
        "navigation_components": navigation_components,
        "section_slots": slots,
        "slot_components": slot_components,
        "components": components,
    }
    return contract


def compact_catalogue_plan_contract() -> dict[str, Any]:
    """Return skeleton choices and slot rules without injecting the component catalogue."""
    skeleton_fields = (
        "id",
        "surface",
        "shell",
        "purpose",
        "requiredSections",
        "optionalSections",
        "recommendedOrder",
    )
    return {
        "skeletons": [
            {
                key: skeleton[key]
                for key in skeleton_fields
                if key in skeleton
            }
            for skeleton in load_catalogue()["skeletons"]
        ]
    }
