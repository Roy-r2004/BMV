"""Architect agent — routes, chrome contracts, prompt context."""
from __future__ import annotations

import json

from app.application.prompts import PromptTemplate
from app.application.preview_app.text_utils import _bounded_json, _parse_json
from app.application.ui_catalogue import compact_catalogue_plan_contract, compact_skeleton_contract, infer_section_slots
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer

def call_architect(
    full_context: str,
    plan: dict,
    manifest: dict,
    images: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> dict:
    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_ARCHITECT,
        full_context=full_context[:12000],
        plan_json=json.dumps(plan, ensure_ascii=False, indent=2)[:14000],
        manifest_json=json.dumps(manifest, ensure_ascii=False, indent=2),
        images_json=json.dumps(images, ensure_ascii=False, indent=2),
        catalogue_contract_json=_bounded_json(compact_catalogue_plan_contract(), 8000),
    )
    for model in (settings.ARCHITECT_MODEL, settings.PREVIEW_APP_MODEL, settings.TEXT_MODEL):
        try:
            raw = ai_provider.ask_chat(model, [{"role": "user", "content": prompt}], max_tokens=14000)
            return _parse_json(raw)
        except Exception:
            continue
    raise ValueError("Architect agent failed to produce valid JSON")

_COLOR_CONSTRAINT = (
    " COLORS: the only theme color tokens that exist are `brand` and `brand-dark` "
    "(text-brand, bg-brand, bg-brand-dark, border-brand, bg-brand/10, etc.) plus "
    "Tailwind's built-in defaults (slate, gray, white, black, and so on). NEVER invent "
    "a new color family name (no bg-navy-800, text-primary-600, bg-cream-50, etc.) — "
    "those classes do not exist in this build's CSS and will silently render as no "
    "color at all. Vary the LOOK using shade/opacity of brand + slate/gray, spacing, "
    "typography, and shape — not by inventing color tokens that were never defined."
)

_CHROME_CONTRACTS: dict[str, str] = {
    "src/components/nav.tsx": (
        "This is the shared top navigation bar, rendered once by PublicLayout on every "
        "public page. Keep the exact signature: "
        "`export default function Nav({ brandName = 'Brand', items = [], cta }: Props)` "
        "with Props = { brandName?: string; items?: {path,label}[]; cta?: {path,label} }. "
        "Redesign the visual style (spacing, typography, button shape) to fit THIS "
        "brand specifically — do not default to a generic indigo/slate look. "
        "It must feel like a real storefront nav the customer trusts: sticky/clean, "
        "brand name as text logo, clear active-ready links, strong CTA — never 'Demo' "
        "or pitch wording in labels."
        + _COLOR_CONSTRAINT
    ),
    "src/layouts/publiclayout.tsx": (
        "This wraps EVERY public page — it must keep rendering <Outlet /> for page content, "
        "keep importing `brand, navigation` from '../data/mock', and keep rendering "
        "<Nav /> from '../components/Nav'. You control the footer content/structure and "
        "overall shell styling — make it specific to this business, not a generic template. "
        "CRITICAL: do NOT wrap <Outlet /> in heavy vertical padding that kills full-bleed "
        "heroes — let pages own their spacing. Footer must feel real (hours, address, "
        "phone-style contact lines from brand context) — not a one-line copyright stub."
        + _COLOR_CONSTRAINT
    ),
    "src/layouts/adminlayout.tsx": (
        "This wraps EVERY admin page — it must keep rendering <Outlet /> for page content and "
        "keep importing `brand, navigation` from '../data/mock'. NEVER hardcode a business "
        "type in any label (do not assume 'Studio', 'Restaurant', 'Clinic', etc.) — use "
        "`brand.name` and neutral wording like 'Admin' or 'Dashboard'. You control the "
        "sidebar/header styling — make it specific to this business. Feel like a real ops "
        "console: sidebar with clear sections, subtle active state, compact header with "
        "today's date or 'Live' status — not a marketing shell."
        + _COLOR_CONSTRAINT
    ),
    "src/components/uiicons.tsx": (
        "This is the shared icon set used everywhere via `<UiIcon name=\"...\" />`. Keep "
        "exporting a default `UiIcon` component that accepts a `name` prop and supports at "
        "least these keys: clipboard, chart, target, clock, users, zap, shield, bell, "
        "calendar, check, search, cart, brain, coffee, arrowRight. Design a bespoke stroke "
        "style (weight, corner rounding) that fits this brand rather than a generic outline "
        "set — but every icon must share the same stroke weight/rounding as each other. "
        "Unknown names must fall back to a simple circle/dot SVG — never crash."
        + _COLOR_CONSTRAINT
    ),
}

def _route_for_file(file_path: str, architect: dict) -> dict:
    norm = (file_path or "").replace("\\", "/").lower()
    for route in architect.get("routes") or []:
        component_file = (route.get("component_file") or "").replace("\\", "/").lower()
        if component_file == norm:
            return route
    return {}

def _catalogue_routes_context(architect: dict) -> str:
    routes = []
    for route in architect.get("routes") or []:
        skeleton_id = route.get("skeleton_id")
        if not skeleton_id:
            continue
        slots = infer_section_slots(route, skeleton_id)
        routes.append({
            "path": route.get("path"),
            "component_file": route.get("component_file"),
            "surface": route.get("surface"),
            "skeleton_id": skeleton_id,
            "contract": compact_skeleton_contract(skeleton_id, slots),
        })
    return _bounded_json(routes, 10000)

def _architect_prompt_context(architect: dict) -> str:
    """Serialize bounded architecture context without repeated file instructions."""
    context = {
        key: architect.get(key)
        for key in ("app_name", "design_direction")
        if architect.get(key) is not None
    }
    context["roles"] = [
        {
            key: role.get(key)
            for key in ("id", "label", "defaultPath", "route_prefix", "icon")
            if role.get(key) is not None
        }
        for role in architect.get("roles") or []
    ]
    context["routes"] = [
        {
            key: route.get(key)
            for key in (
                "path",
                "page_id",
                "role_id",
                "title",
                "component_file",
                "layout",
                "surface",
                "skeleton_id",
            )
            if route.get(key) is not None
        }
        for route in architect.get("routes") or []
    ]
    context["shared_components"] = [
        {
            key: component.get(key)
            for key in ("path", "kind")
            if component.get(key) is not None
        }
        for component in architect.get("shared_components") or []
    ]
    return _bounded_json(context, 8000)
