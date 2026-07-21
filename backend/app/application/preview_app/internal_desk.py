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


def is_internal_desk_brief(*parts: str) -> bool:
    blob = " ".join(str(p or "") for p in parts).lower()
    # "not a client portal" is a negative phrase — still a desk signal via "not a"
    hits = sum(1 for hint in _DESK_HINTS if hint in blob)
    return hits >= 2


def _ops_dashboard_slots() -> list[str]:
    return ["header", "kpis", "filters", "table", "chart", "activity", "risk"]


def ensure_internal_desk_experience_plan(
    plan: dict[str, Any] | None,
    *,
    context: str = "",
) -> dict[str, Any]:
    """Rewrite a marketing-home plan into an ops trading desk when the brief demands it."""

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
            desk = {
                "id": "trading-desk",
                "title": "Trading Desk",
                "page_type": "trading-desk",
                "surface": "ops",
                "skeleton_id": "ops-dashboard",
                "section_slots": _ops_dashboard_slots(),
                "purpose": (
                    "Internal fund trading desk — watchlist, blotter, positions, P&L, risk."
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
                "layout_notes": "OpsShell with main blotter and right activity/risk rail.",
                "sample_data_notes": (
                    "AAPL BUY 25k Working; MSFT SELL 12k Partial; Day P&L +1.24M; exposure 62%."
                ),
            }
            role["pages"] = [desk]
            touched = True
            continue

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
            if not is_home and skeleton == "ops-dashboard":
                continue
            if not is_home and surface == "ops":
                continue
            # Convert marketing/public primary pages into the desk console.
            if is_home or skeleton.startswith("public"):
                page["title"] = page.get("title") if "desk" in title.lower() else "Trading Desk"
                page["page_type"] = "trading-desk"
                page["surface"] = "ops"
                page["skeleton_id"] = "ops-dashboard"
                page["section_slots"] = _ops_dashboard_slots()
                page["purpose"] = (
                    "Internal hedge-fund trading desk — not a SaaS marketing landing."
                )
                page["layout_notes"] = "OpsShell desk: KPIs, blotter table, P&L chart, risk rail."
                page["sample_data_notes"] = (
                    "Symbols, sides, fills, exposure, P&L — never client/CRM tickets."
                )
                if not page.get("sections"):
                    page["sections"] = [
                        {
                            "name": "Blotter",
                            "description": "Live working orders and fills.",
                            "priority": "required",
                        }
                    ]
                touched = True

        # Prefer desk as first page for nav.
        pages = list(role.get("pages") or [])
        desk_pages = [
            p
            for p in pages
            if isinstance(p, dict) and p.get("skeleton_id") == "ops-dashboard"
        ]
        if desk_pages and pages and pages[0] is not desk_pages[0]:
            role["pages"] = desk_pages + [
                p for p in pages if p not in desk_pages
            ]
            touched = True

        nav = dict(role.get("navigation") or {})
        links = list(nav.get("links") or [])
        if desk_pages and links:
            desk_id = desk_pages[0].get("id")
            # Drop SaaS CTAs like "Get started" pointing at marketing.
            cleaned = []
            for link in links:
                if not isinstance(link, dict):
                    continue
                label = str(link.get("label") or "").lower()
                if any(bad in label for bad in ("get started", "access dashboard", "sign up")):
                    continue
                cleaned.append(link)
            if desk_id and not any(l.get("page_id") == desk_id for l in cleaned):
                cleaned.insert(0, {"label": "Desk", "page_id": desk_id, "style": "cta"})
            if cleaned:
                nav["links"] = cleaned
                role["navigation"] = nav
                touched = True

    if touched:
        direction = str(updated.get("design_direction") or "").strip()
        updated["design_direction"] = (
            f"{direction} | Internal trading desk first — OpsShell blotter/P&L/risk, "
            "never a public SaaS marketing homepage."
        ).strip(" |")
        updated["ops_direction"] = (
            "Dense institutional trading console: blotter, tickets, positions, P&L, risk limits."
        )
        updated["public_direction"] = (
            "No consumer marketing site — product is the internal desk itself."
        )
    updated["roles"] = roles
    return updated


def ensure_internal_desk_architect(
    architect: dict[str, Any] | None,
    *,
    context: str = "",
) -> dict[str, Any]:
    """Force AppSpec-locked public marketing routes onto ops-dashboard for desks."""

    updated = copy.deepcopy(dict(architect or {}))
    if not is_internal_desk_brief(context, updated.get("design_direction") or ""):
        return updated

    slots = _ops_dashboard_slots()
    for route in updated.get("routes") or []:
        if not isinstance(route, dict):
            continue
        route["surface"] = "ops"
        route["layout"] = "admin"
        route["skeleton_id"] = "ops-dashboard"
        route["section_slots"] = list(slots)
        path = str(route.get("component_file") or "src/pages/HomePage.tsx")
        if "/owner/" not in path and "/admin/" not in path and "/ops/" not in path:
            # Keep filename; OpsShell is selected from surface, not folder.
            route["component_file"] = path
        title = str(route.get("title") or "")
        if not re.search(r"desk|blotter|trading", title, re.I):
            route["title"] = "Trading Desk"

    for item in updated.get("files_to_generate") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").lower()
        kind = str(item.get("kind") or item.get("type") or "").lower()
        if kind not in {"page", ""} and "page" not in path:
            continue
        instructions = str(item.get("instructions") or "")
        prefix = (
            "INTERNAL TRADING DESK page using OpsShell + ops-dashboard slots "
            "(header, kpis, filters, table, chart, activity, risk). "
            "Blotter/P&L/risk copy only — never a SaaS marketing hero or "
            "'Access Dashboard' CTA. "
        )
        if "INTERNAL TRADING DESK" not in instructions:
            item["instructions"] = (prefix + instructions).strip()

    direction = str(updated.get("design_direction") or "").strip()
    updated["design_direction"] = (
        f"{direction} | OpsShell trading desk first — blotter, positions, P&L, risk."
    ).strip(" |")
    return updated


__all__ = [
    "ensure_internal_desk_architect",
    "ensure_internal_desk_experience_plan",
    "is_internal_desk_brief",
]
