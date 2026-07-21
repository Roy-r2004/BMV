"""Force internal trading/ops desks to land on ops-dashboard, not marketing SaaS."""
from __future__ import annotations

import copy
import re
from typing import Any

_DESK_HINTS = (
    "hedge",
    "trading",
    "trader",
    "blotter",
    "oms",
    "execution",
    "portfolio manager",
    "risk officer",
    "fund book",
    "institutional",
    "internal desk",
    "internal trading",
    "not a saas",
    "not a retail",
    "not a client",
    "client portal",
)

# Canonical multi-page trading desk — experience plan + architect inject these.
_TRADING_DESK_PAGES: tuple[dict[str, Any], ...] = (
    {
        "id": "trading-desk",
        "title": "Trading Desk",
        "page_type": "trading-desk",
        "path": "/",
        "component_file": "src/pages/TradingDeskPage.tsx",
        "purpose": (
            "Primary fund desk — watchlist KPIs, working blotter, intraday P&L, risk rail."
        ),
        "sections": [
            {
                "name": "Desk KPIs",
                "description": "Open orders, day P&L, gross exposure, fills.",
                "priority": "required",
            },
            {
                "name": "Order blotter",
                "description": "Working/partial/filled orders with symbols and sides.",
                "priority": "required",
            },
            {
                "name": "Risk rail",
                "description": "Limit breaches and concentration alerts.",
                "priority": "required",
            },
        ],
        "features_to_showcase": ["Order blotter", "Positions & P&L", "Risk limits"],
        "layout_notes": "OpsShell floor desk: dense blotter main + activity/risk rail.",
        "sample_data_notes": (
            "AAPL BUY 25k Working; MSFT SELL 12k Partial; Day P&L +1.24M; exposure 62%."
        ),
    },
    {
        "id": "order-ticket",
        "title": "Order Ticket",
        "page_type": "order-ticket",
        "path": "/ticket",
        "component_file": "src/pages/OrderTicketPage.tsx",
        "purpose": "Stage buy/sell tickets with size, limit, TIF, and pre-trade risk checks.",
        "sections": [
            {
                "name": "Ticket form",
                "description": "Symbol, side, qty, limit, account, TIF.",
                "priority": "required",
            },
            {
                "name": "Pre-trade checks",
                "description": "Buying power, concentration, restricted list.",
                "priority": "required",
            },
        ],
        "features_to_showcase": ["Stage order", "Risk check"],
        "layout_notes": "OpsShell form-forward ticket with check results rail.",
        "sample_data_notes": "NVDA BUY 8,000 @ 905.00 DAY; checks: PASS concentration.",
    },
    {
        "id": "order-blotter",
        "title": "Order Blotter",
        "page_type": "order-blotter",
        "path": "/blotter",
        "component_file": "src/pages/OrderBlotterPage.tsx",
        "purpose": "Full working/partial/filled blotter with filters and desk ownership.",
        "sections": [
            {
                "name": "Blotter table",
                "description": "8+ live orders with status chips and fill progress.",
                "priority": "required",
            },
            {
                "name": "Filters",
                "description": "Working / Partial / Filled / Symbol search.",
                "priority": "required",
            },
        ],
        "features_to_showcase": ["Filter blotter", "Cancel/replace"],
        "layout_notes": "OpsShell list: filters + dense DataTable, no marketing chrome.",
        "sample_data_notes": (
            "AAPL BUY 25k Working; MSFT SELL 12k Partial; META BUY 4k Filled."
        ),
    },
    {
        "id": "positions",
        "title": "Positions & P&L",
        "page_type": "positions",
        "path": "/positions",
        "component_file": "src/pages/PositionsPage.tsx",
        "purpose": "Book positions, day/MTD P&L, and sleeve attribution.",
        "sections": [
            {
                "name": "P&L strip",
                "description": "Day, MTD, YTD P&L with deltas.",
                "priority": "required",
            },
            {
                "name": "Positions table",
                "description": "Symbol, qty, avg, mark, unrealized.",
                "priority": "required",
            },
        ],
        "features_to_showcase": ["Mark-to-market", "Sleeve P&L"],
        "layout_notes": "OpsShell with chart + positions grid.",
        "sample_data_notes": "AAPL +420k day; tech sleeve 28% NAV; short book -90k.",
    },
    {
        "id": "risk-limits",
        "title": "Risk Limits",
        "page_type": "risk",
        "path": "/risk",
        "component_file": "src/pages/RiskLimitsPage.tsx",
        "purpose": "Gross/net limits, sector caps, and breach queue for the fund book.",
        "sections": [
            {
                "name": "Limit cards",
                "description": "Gross, net, single-name, sector utilization.",
                "priority": "required",
            },
            {
                "name": "Breach queue",
                "description": "Open breaches with severity and owner.",
                "priority": "required",
            },
        ],
        "features_to_showcase": ["Limit utilization", "Breach triage"],
        "layout_notes": "OpsShell risk console with queue rail.",
        "sample_data_notes": "Gross 62/75%; tech 28% soft breach; single-name NVDA 9%.",
    },
)


def is_internal_desk_brief(*parts: str) -> bool:
    blob = " ".join(str(p or "") for p in parts).lower()
    hits = sum(1 for hint in _DESK_HINTS if hint in blob)
    return hits >= 2


def _ops_dashboard_slots() -> list[str]:
    return ["header", "kpis", "filters", "table", "chart", "activity", "risk"]


def _ops_list_slots() -> list[str]:
    # Must match catalogue ops-list required/optional IDs (no activity/risk).
    return ["header", "filters", "table"]


def _is_ai_hub_route(route: dict[str, Any]) -> bool:
    path = str(route.get("path") or "").rstrip("/").lower()
    page_id = str(
        route.get("page_id") or route.get("app_spec_page_id") or route.get("id") or ""
    ).casefold()
    component = str(route.get("component_file") or "").replace("\\", "/").lower()
    page_type = str(route.get("page_type") or "").casefold()
    return (
        path == "/ai-features"
        or page_id == "page-ai-features"
        or component.endswith("aifeaturespage.tsx")
        or page_type == "ai_hub"
    )


def _desk_page_blueprint(spec: dict[str, Any]) -> dict[str, Any]:
    slots = (
        _ops_dashboard_slots()
        if spec["id"] == "trading-desk"
        else _ops_list_slots()
    )
    return {
        "id": spec["id"],
        "title": spec["title"],
        "page_type": spec["page_type"],
        "surface": "ops",
        "skeleton_id": "ops-dashboard" if spec["id"] == "trading-desk" else "ops-list",
        "section_slots": slots,
        "purpose": spec["purpose"],
        "sections": copy.deepcopy(spec["sections"]),
        "features_to_showcase": list(spec["features_to_showcase"]),
        "layout_notes": spec["layout_notes"],
        "sample_data_notes": spec["sample_data_notes"],
    }


def _ensure_role_desk_pages(role: dict[str, Any]) -> bool:
    """Ensure the role has the full trading desk page set."""

    pages = [p for p in (role.get("pages") or []) if isinstance(p, dict)]
    by_id = {str(p.get("id") or ""): p for p in pages}
    by_title = {str(p.get("title") or "").casefold(): p for p in pages}
    touched = False

    for spec in _TRADING_DESK_PAGES:
        existing = by_id.get(spec["id"]) or by_title.get(str(spec["title"]).casefold())
        if existing is None:
            pages.append(_desk_page_blueprint(spec))
            touched = True
            continue
        # Upgrade thin/marketing pages that match a desk surface.
        skeleton = str(existing.get("skeleton_id") or "")
        surface = str(existing.get("surface") or "")
        if surface == "public" or skeleton.startswith("public"):
            existing.update(_desk_page_blueprint(spec))
            touched = True
        else:
            existing.setdefault("surface", "ops")
            if not existing.get("skeleton_id"):
                existing["skeleton_id"] = (
                    "ops-dashboard" if spec["id"] == "trading-desk" else "ops-list"
                )
                touched = True

    # Prefer Trading Desk first.
    desk = next(
        (
            p
            for p in pages
            if isinstance(p, dict)
            and (
                p.get("id") == "trading-desk"
                or p.get("skeleton_id") == "ops-dashboard"
            )
        ),
        None,
    )
    if desk is not None and pages and pages[0] is not desk:
        pages = [desk] + [p for p in pages if p is not desk]
        touched = True

    role["pages"] = pages

    nav = dict(role.get("navigation") or {})
    links = [
        link
        for link in (nav.get("links") or [])
        if isinstance(link, dict)
        and not any(
            bad in str(link.get("label") or "").lower()
            for bad in ("get started", "access dashboard", "sign up", "book now")
        )
    ]
    for page in pages:
        pid = page.get("id")
        if not pid:
            continue
        if any(link.get("page_id") == pid for link in links):
            continue
        links.append(
            {
                "label": str(page.get("title") or pid),
                "page_id": pid,
                "style": "cta" if pid == "trading-desk" else "link",
            }
        )
        touched = True
    if links:
        nav["links"] = links
        role["navigation"] = nav
    return touched


def ensure_internal_desk_experience_plan(
    plan: dict[str, Any] | None,
    *,
    context: str = "",
) -> dict[str, Any]:
    """Rewrite a marketing-home plan into a multi-page ops trading desk."""

    updated = copy.deepcopy(dict(plan or {}))
    if not is_internal_desk_brief(context, updated.get("design_direction") or ""):
        return updated

    roles = list(updated.get("roles") or [])
    if not roles:
        return updated

    touched = False
    for role in roles:
        if not isinstance(role, dict):
            continue
        pages = list(role.get("pages") or [])
        if not pages:
            role["pages"] = [_desk_page_blueprint(spec) for spec in _TRADING_DESK_PAGES]
            touched = True
        else:
            # Convert leftover marketing homes before expanding the set.
            for page in pages:
                if not isinstance(page, dict):
                    continue
                skeleton = str(page.get("skeleton_id") or "")
                surface = str(page.get("surface") or "")
                title = str(page.get("title") or "")
                is_home = (
                    skeleton in {"public-home", "public-service"}
                    or surface == "public"
                    and bool(re.search(r"home|landing|marketing", f"{title} {skeleton}", re.I))
                )
                if is_home or skeleton.startswith("public"):
                    page.update(_desk_page_blueprint(_TRADING_DESK_PAGES[0]))
                    touched = True
            if _ensure_role_desk_pages(role):
                touched = True
            continue

        if _ensure_role_desk_pages(role):
            touched = True

    if touched:
        direction = str(updated.get("design_direction") or "").strip()
        updated["design_direction"] = (
            f"{direction} | Internal trading desk — multi-page OpsShell blotter/ticket/"
            "positions/risk; never a public SaaS marketing homepage."
        ).strip(" |")
        updated["ops_direction"] = (
            "Dense institutional trading console across Desk, Ticket, Blotter, "
            "Positions & P&L, and Risk Limits — Bloomberg-like density, real symbols."
        )
        updated["public_direction"] = (
            "No consumer marketing site — the product is the internal desk itself."
        )
    updated["roles"] = roles
    return updated


def _inject_desk_architect_routes(architect: dict[str, Any]) -> None:
    routes = [rt for rt in (architect.get("routes") or []) if isinstance(rt, dict)]
    role_id = "ROLE-PRIMARY-USER"
    for role in architect.get("roles") or []:
        if isinstance(role, dict) and role.get("id"):
            role_id = str(role["id"])
            break
    for rt in routes:
        if rt.get("role_id"):
            role_id = str(rt["role_id"])
            break

    existing_paths = {str(rt.get("path") or "") for rt in routes}
    files = [
        f
        for f in (architect.get("files_to_generate") or [])
        if isinstance(f, dict)
    ]
    existing_files = {
        str(f.get("path") or "").replace("\\", "/") for f in files
    }

    for spec in _TRADING_DESK_PAGES:
        path = str(spec["path"])
        component = str(spec["component_file"])
        if path in existing_paths:
            # Upgrade any existing route at this path onto ops.
            for rt in routes:
                if str(rt.get("path") or "") != path or _is_ai_hub_route(rt):
                    continue
                rt["surface"] = "ops"
                rt["layout"] = "admin"
                rt["skeleton_id"] = (
                    "ops-dashboard" if path == "/" else "ops-list"
                )
                rt["section_slots"] = (
                    _ops_dashboard_slots() if path == "/" else _ops_list_slots()
                )
                rt["title"] = spec["title"]
                rt["page_type"] = spec["page_type"]
                rt.setdefault("component_file", component)
                rt.setdefault("role_id", role_id)
            continue

        routes.append(
            {
                "path": path,
                "page_id": spec["id"],
                "role_id": role_id,
                "title": spec["title"],
                "component_file": component,
                "layout": "admin",
                "surface": "ops",
                "skeleton_id": "ops-dashboard" if path == "/" else "ops-list",
                "section_slots": (
                    _ops_dashboard_slots() if path == "/" else _ops_list_slots()
                ),
                "page_type": spec["page_type"],
                "purpose": spec["purpose"],
            }
        )
        if component not in existing_files:
            files.append(
                {
                    "type": "page",
                    "kind": "page",
                    "path": component,
                    "instructions": (
                        "INTERNAL TRADING DESK page using OpsShell + catalogue slots. "
                        f"{spec['purpose']} Dense institutional UI with realistic "
                        f"symbols/sizes/P&L — never CRM or SaaS marketing. "
                        f"Sample: {spec['sample_data_notes']}"
                    ),
                }
            )
            existing_files.add(component)

    architect["routes"] = routes
    architect["files_to_generate"] = files


def ensure_internal_desk_architect(
    architect: dict[str, Any] | None,
    *,
    context: str = "",
) -> dict[str, Any]:
    """Force AppSpec-locked public marketing routes onto ops multi-page desks."""

    updated = copy.deepcopy(dict(architect or {}))
    if not is_internal_desk_brief(context, updated.get("design_direction") or ""):
        return updated

    slots = _ops_dashboard_slots()
    for route in updated.get("routes") or []:
        if not isinstance(route, dict):
            continue
        # Never collapse the AI hub into an ops-dashboard scaffold.
        if _is_ai_hub_route(route):
            continue
        route["surface"] = "ops"
        route["layout"] = "admin"
        if not route.get("skeleton_id") or str(route.get("skeleton_id")).startswith(
            "public"
        ):
            route["skeleton_id"] = "ops-dashboard"
            route["section_slots"] = list(slots)
        path = str(route.get("component_file") or "src/pages/HomePage.tsx")
        if "/owner/" not in path and "/admin/" not in path and "/ops/" not in path:
            route["component_file"] = path
        title = str(route.get("title") or "")
        if not re.search(
            r"desk|blotter|trading|ticket|position|risk|p&l|pnl", title, re.I
        ):
            route["title"] = "Trading Desk"

    _inject_desk_architect_routes(updated)

    for item in updated.get("files_to_generate") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").replace("\\", "/").lower()
        if "aifeaturespage" in path:
            continue
        kind = str(item.get("kind") or item.get("type") or "").lower()
        if kind not in {"page", ""} and "page" not in path:
            continue
        instructions = str(item.get("instructions") or "")
        prefix = (
            "INTERNAL TRADING DESK page using OpsShell + ops slots "
            "(header, kpis, filters, table, chart, activity, risk). "
            "Dense blotter/P&L/risk copy only — never a SaaS marketing hero or "
            "'Access Dashboard' CTA. "
        )
        if "INTERNAL TRADING DESK" not in instructions:
            item["instructions"] = (prefix + instructions).strip()

    direction = str(updated.get("design_direction") or "").strip()
    updated["design_direction"] = (
        f"{direction} | OpsShell multi-page trading desk — Desk, Ticket, Blotter, "
        "Positions, Risk — plus AI features in the ops nav."
    ).strip(" |")
    return updated


__all__ = [
    "ensure_internal_desk_architect",
    "ensure_internal_desk_experience_plan",
    "is_internal_desk_brief",
]
