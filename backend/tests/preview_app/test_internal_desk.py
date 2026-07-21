"""Internal trading desks must not become SaaS marketing landings."""
from __future__ import annotations

from app.application.appspec.fallback import build_fallback_app_spec
from app.application.preview_app.internal_desk import (
    ensure_internal_desk_architect,
    ensure_internal_desk_experience_plan,
    is_internal_desk_brief,
)
from app.domain.appspec.sanitize import sanitize_app_spec_payload


def test_detects_hedge_fund_brief() -> None:
    assert is_internal_desk_brief(
        "Fintech / Hedge fund trading",
        "internal trading engine blotter portfolio not a SaaS for clients",
    )


def test_experience_plan_converts_public_home_to_ops_desk() -> None:
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
    page = out["roles"][0]["pages"][0]
    assert page["surface"] == "ops"
    assert page["skeleton_id"] == "ops-dashboard"
    assert "hero" not in page["section_slots"]
    assert "table" in page["section_slots"]


def test_architect_forces_ops_surface() -> None:
    architect = {
        "routes": [
            {
                "path": "/",
                "title": "Home",
                "surface": "public",
                "layout": "public",
                "skeleton_id": "public-home",
                "component_file": "src/pages/HomePage.tsx",
            }
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
    assert out["routes"][0]["surface"] == "ops"
    assert out["routes"][0]["skeleton_id"] == "ops-dashboard"
    assert "INTERNAL TRADING DESK" in out["files_to_generate"][0]["instructions"]


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
    # Minimal payload — only assert surface coerce before full schema parse.
    from app.domain.appspec.sanitize.structure import _sanitize_pages_for_internal_desk

    _sanitize_pages_for_internal_desk(payload, source)
    assert payload["pages"][0]["surface"] == "ops"


def test_fallback_trading_spec_is_ops() -> None:
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
    assert spec.pages[0].surface == "ops"
