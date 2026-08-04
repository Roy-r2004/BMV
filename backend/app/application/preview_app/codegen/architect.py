"""Architect agent — routes, chrome contracts, prompt context."""
from __future__ import annotations

import json

from app.application.prompts import PromptTemplate
from app.application.preview_app.text_utils import _bounded_json, _parse_json
from app.application.services.ai_context import UNUSABLE_UNPARSEABLE, ai_call
from app.application.services.request_deadline import require_model_time
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
    # Past the deadline every ask budget is zero, so all three links below are
    # refused before the first byte and the loop falls out in ~9 ms — then
    # blames the model for invalid JSON that no model was ever asked to
    # produce. Request 74 died exactly that way: the log said "Architect agent
    # failed to produce valid JSON", the orchestrator read that as transient and
    # went looking for retry runway, and the actual cause (a 540 s budget
    # already spent, 390 s of it inside `appspec`) appeared nowhere in the
    # failure. `architect` is MANDATORY and has no deterministic path, so this
    # still ends the run — but it must end it naming the deadline.
    require_model_time("architect")

    # Roadmap 1.2 deduped the *repair* chains and its test pins those; this one
    # was left resolving three setting names against one id. On requests 74-76
    # `ARCHITECT_MODEL`, `PREVIEW_APP_MODEL` and `TEXT_MODEL` are all
    # `google/gemini-2.5-flash`, so "fail over twice" meant asking the same
    # model three times — request 74 wrote three `architect` rows, one model,
    # all unusable. A model that just returned unparseable JSON does not parse
    # when asked again a millisecond later; it costs another full ask.
    chain = list(
        dict.fromkeys(
            m
            for m in (
                settings.ARCHITECT_MODEL,
                settings.PREVIEW_APP_MODEL,
                settings.TEXT_MODEL,
            )
            if m
        )
    )

    for attempt, model in enumerate(chain, start=1):
        # Each failover link is its own logical ask. Collapsing the chain into
        # one row is how a model that reliably returns unparseable JSON keeps
        # looking free — the row that mattered was the one after it.
        with ai_call("architect", writer=f"architect:{model}", attempt=attempt) as call:
            try:
                raw = ai_provider.ask_chat(model, [{"role": "user", "content": prompt}], max_tokens=14000)
                parsed = _parse_json(raw)
                call.mark_usable()
                return parsed
            except Exception:
                call.unusable(UNUSABLE_UNPARSEABLE)
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

#: Every catalogue component definition and prop shape is stated **once** per
#: run under these keys; a route then names the components it may use.
_LIBRARY_KEY = "component_library"
_PROP_SHAPES_KEY = "prop_shapes"

#: The fix agent's route block budget, unchanged. What changed is what happens
#: when a run does not fit inside it.
_ROUTES_CONTEXT_BUDGET = 10000

#: Least to most degraded. Each level drops the cheapest thing whose loss the
#: repair path can most afford, and `detail_level` says which one was sent.
#:
#: Measured on request 93's real 9 catalogue routes, with the library already
#: hoisted: library 6,019 chars, prop shapes 2,206, routes 10,597 — 18,869
#: against a 10,000 budget. So the hoist alone (45k+ before it) is a 2.4x
#: reduction and still not enough, and the block has to be able to shed weight
#: rather than vanish.
_DETAIL_FULL = "full"
_DETAIL_NO_PROP_SHAPES = "no_prop_shapes"
_DETAIL_NAMES_ONLY = "allowed_names_only"
_DETAIL_SKELETON_IDS_ONLY = "skeleton_ids_only"
_DETAIL_LEVELS = (
    _DETAIL_FULL,
    _DETAIL_NO_PROP_SHAPES,
    _DETAIL_NAMES_ONLY,
    _DETAIL_SKELETON_IDS_ONLY,
)


def _routes_context_payload(
    routes: list[dict],
    library: dict[str, dict],
    prop_shapes: dict[str, str],
    level: str,
) -> dict:
    """One rung of the degradation ladder."""

    if level == _DETAIL_SKELETON_IDS_ONLY:
        trimmed = []
        for route in routes:
            contract = route["contract"]
            trimmed.append({
                **{k: v for k, v in route.items() if k != "contract"},
                "section_slots": contract.get("section_slots") or [],
                "shell_component": contract.get("shell_component"),
            })
        return {"detail_level": level, "routes": trimmed}

    if level == _DETAIL_NAMES_ONLY:
        trimmed = []
        for route in routes:
            contract = route["contract"]
            trimmed.append({
                **{k: v for k, v in route.items() if k != "contract"},
                "section_slots": contract.get("section_slots") or [],
                "shell_component": contract.get("shell_component"),
                "slot_components": contract.get("slot_components") or {},
                "allowed_components": contract.get("allowed_components") or [],
            })
        return {"detail_level": level, "routes": trimmed}

    payload: dict = {
        "detail_level": level,
        _LIBRARY_KEY: [library[name] for name in sorted(library)],
        "routes": routes,
    }
    if level == _DETAIL_FULL:
        payload[_PROP_SHAPES_KEY] = prop_shapes
    return payload


def _catalogue_routes_context(architect: dict) -> str:
    """The catalogue contract for every route, with the allow-list stated once.

    This block goes to the **fix agent** and to `chat_rebuild` — not to the
    architect, despite living in this file and despite four write-ups
    (including two of mine) saying otherwise. `_route_for_file` above is the
    architect's; this one takes the *completed* architect dict and its only
    callers are `fix_agent` (`:482`, `:530`) and `chat_rebuild` (`:245`).

    It used to serialize one **full** `compact_skeleton_contract` per route
    into a 10,000-char budget. The component definitions and prop shapes are
    the bulk of that and they repeat verbatim for every route sharing a
    skeleton, so measured offline: 1 route = 5,004 chars, 2 routes = each
    component list clipped to 12 entries, **3 routes = the whole block
    collapsed to `{"truncated": true, "preview": …}`**. Confirmed live on
    request 93's real 9-route list, where the fix agent then ran twice for
    147.8 s of AI against a route block it could not read — the repair path,
    which is the consumer that most needs each page's contract.

    Hoisting the library changes what the model sees. It is the same
    information, said once: each route keeps its skeleton, slots and shell,
    and names its allowed components instead of restating their definitions.
    """

    library: dict[str, dict] = {}
    prop_shapes: dict[str, str] = {}
    routes = []
    for route in architect.get("routes") or []:
        skeleton_id = route.get("skeleton_id")
        if not skeleton_id:
            continue
        slots = infer_section_slots(route, skeleton_id)
        contract = dict(compact_skeleton_contract(skeleton_id, slots))
        allowed: list[str] = []
        for component in contract.pop("components", None) or []:
            name = str(component.get("name") or "")
            if not name:
                continue
            library.setdefault(name, component)
            allowed.append(name)
        for key, members in (contract.pop(_PROP_SHAPES_KEY, None) or {}).items():
            prop_shapes.setdefault(str(key), members)
        # Order is the catalogue's, not alphabetical: `compact_skeleton_contract`
        # leads with this page's own shell, nav and slot components, and that
        # ordering is what `skeleton_contract_for_prompt` drops from the tail of.
        contract["allowed_components"] = allowed
        routes.append({
            "path": route.get("path"),
            "component_file": route.get("component_file"),
            "surface": route.get("surface"),
            "skeleton_id": skeleton_id,
            "contract": contract,
        })
    if not routes:
        # `[]` and `{"routes": []}` read the same to a model, and the empty
        # case is what a run with no catalogue routes has always sent.
        return _bounded_json([], _ROUTES_CONTEXT_BUDGET)

    # Degrade by dropping, never by collapsing. `_bounded_json` past its budget
    # replaces the WHOLE block with `{"truncated": true, "preview": …}`, which
    # is what the fix agent got on requests 86, 87, 88, 91 and 93 — every
    # archived run with more than two catalogue routes. Knowing which page maps
    # to which skeleton and slots, with no component definitions, beats knowing
    # nothing; it is the same rule `_budgeted_prop_shapes` already follows one
    # layer down ("a shape that does not fit is dropped, never truncated").
    for level in _DETAIL_LEVELS:
        payload = _routes_context_payload(routes, library, prop_shapes, level)
        rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(rendered) <= _ROUTES_CONTEXT_BUDGET:
            return rendered
    # Past the last rung the route list itself is the overflow; clip it rather
    # than send a preview of one, and say how many were dropped.
    kept = list(routes)
    while kept:
        kept = kept[:-1]
        payload = _routes_context_payload(
            kept, library, prop_shapes, _DETAIL_SKELETON_IDS_ONLY
        )
        payload["routes_omitted"] = len(routes) - len(kept)
        rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(rendered) <= _ROUTES_CONTEXT_BUDGET:
            return rendered
    return _bounded_json([], _ROUTES_CONTEXT_BUDGET)

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
