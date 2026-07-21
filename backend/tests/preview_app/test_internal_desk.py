"""Internal trading desks must not become SaaS marketing landings."""
from __future__ import annotations

from app.application.appspec.fallback import build_fallback_app_spec
from app.application.preview_app.ai_feature_surfaces import ensure_ai_feature_route
from app.application.preview_app.internal_desk import (
    ensure_internal_desk_architect,
    ensure_internal_desk_experience_plan,
    is_internal_desk_brief,
)
from app.application.services.ai_features import ai_feature_hub_page_source


def test_detects_hedge_fund_brief() -> None:
    assert is_internal_desk_brief(
        "Fintech / Hedge fund trading",
        "internal trading engine blotter portfolio not a SaaS for clients",
    )


def test_experience_plan_expands_to_multi_page_ops_desk() -> None:
    plan = {
        "roles": [
            {
                "id": "pm",
                "pages": [
                    {
                        "id": "home",
                        "title": "Home",
                        "surface": "public",
                        "skeleton_id": "public-home",
                        "section_slots": ["hero", "features", "cta", "footer"],
                    }
                ],
                "navigation": {
                    "links": [
                        {"label": "Access Dashboard", "page_id": "home", "style": "cta"}
                    ]
                },
            }
        ]
    }
    out = ensure_internal_desk_experience_plan(
        plan,
        context="hedge fund trading blotter internal desk not a saas",
    )
    pages = out["roles"][0]["pages"]
    assert len(pages) >= 5
    assert pages[0]["surface"] == "ops"
    assert pages[0]["skeleton_id"] == "ops-dashboard"
    titles = {str(p.get("title") or "") for p in pages}
    assert "Order Blotter" in titles
    assert "Risk Limits" in titles
    assert "hero" not in pages[0]["section_slots"]
    assert "table" in pages[0]["section_slots"]


def test_architect_forces_ops_surface_and_skips_ai_hub() -> None:
    architect = {
        "routes": [
            {
                "path": "/",
                "title": "Home",
                "surface": "public",
                "layout": "public",
                "skeleton_id": "public-home",
                "component_file": "src/pages/HomePage.tsx",
            },
            {
                "path": "/ai-features",
                "title": "AI features",
                "surface": "public",
                "layout": "public",
                "skeleton_id": "",
                "page_type": "ai_hub",
                "component_file": "src/pages/AiFeaturesPage.tsx",
            },
        ],
        "files_to_generate": [
            {
                "type": "page",
                "path": "src/pages/HomePage.tsx",
                "instructions": "Build a marketing hero.",
            }
        ],
    }
    out = ensure_internal_desk_architect(
        architect,
        context="hedge fund trading blotter oms desk",
    )
    home = next(rt for rt in out["routes"] if rt["path"] == "/")
    hub = next(rt for rt in out["routes"] if rt["path"] == "/ai-features")
    assert home["surface"] == "ops"
    assert home["skeleton_id"] == "ops-dashboard"
    assert hub["page_type"] == "ai_hub"
    assert hub.get("skeleton_id") in {"", None}
    paths = {rt["path"] for rt in out["routes"]}
    assert "/blotter" in paths
    assert "/ticket" in paths
    assert "/positions" in paths
    assert "/risk" in paths
    assert "INTERNAL TRADING DESK" in out["files_to_generate"][0]["instructions"]


def test_ai_hub_route_stays_openable_on_ops_desk() -> None:
    architect = {
        "routes": [
            {
                "path": "/",
                "title": "Trading Desk",
                "surface": "ops",
                "layout": "admin",
                "skeleton_id": "ops-dashboard",
                "role_id": "ROLE-TRADER",
                "component_file": "src/pages/TradingDeskPage.tsx",
            }
        ],
        "roles": [{"id": "ROLE-TRADER", "label": "Trader"}],
    }
    out = ensure_ai_feature_route(
        architect,
        [
            {
                "id": "ai-signal-digest",
                "name": "Signal digest",
                "description": "Summarize overnight risk and fills.",
                "category": "digest",
            }
        ],
    )
    hub = next(rt for rt in out["routes"] if rt["path"] == "/ai-features")
    assert hub["layout"] == "admin"
    assert hub["surface"] == "ops"
    assert hub["owns_shell"] is True
    assert hub["page_type"] == "ai_hub"
    source = ai_feature_hub_page_source(
        brand_name="TradeForge",
        features=out["ai_features"],
        ops_shell=True,
    )
    assert "OpsShell" in source
    assert "useAdminNavItems" in source


def test_appspec_sanitize_coerces_trading_home_to_ops() -> None:
    source = {
        "customer_input": {
            "business_name": "TradeForge",
            "industry": "Hedge fund trading",
            "business_description": "Internal trading engine blotter P&L",
            "desired_outcome": "Desk can stage orders",
            "main_problem": "Fragmented OMS",
            "target_customers": "Portfolio managers",
        }
    }
    payload = {
        "schema_version": "1.0",
        "product_intent": {
            "name": "TradeForge",
            "summary": "Trading",
            "problem": "Fragmented",
            "desired_outcome": "Orders",
            "target_users": ["PM"],
        },
        "requirements": [],
        "pages": [
            {
                "id": "PAGE-HOME",
                "route": "/",
                "surface": "public",
                "primary": True,
            }
        ],
    }
    from app.domain.appspec.sanitize.structure import _sanitize_pages_for_internal_desk

    _sanitize_pages_for_internal_desk(payload, source)
    assert payload["pages"][0]["surface"] == "ops"


def test_fallback_trading_spec_is_multi_page_ops() -> None:
    spec = build_fallback_app_spec(
        {
            "customer_input": {
                "business_name": "TradeForge",
                "industry": "Hedge fund trading",
                "business_description": "Internal blotter and OMS",
                "desired_outcome": "Traders place orders",
                "main_problem": "No desk",
                "target_customers": "Execution traders",
            }
        }
    )
    assert len(spec.pages) >= 5
    assert all(page.surface == "ops" for page in spec.pages)
    routes = {page.route for page in spec.pages}
    assert "/" in routes
    assert "/blotter" in routes
    assert "/risk" in routes
