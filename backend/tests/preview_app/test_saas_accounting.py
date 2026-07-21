"""SaaS accounting briefs must become product workspaces, not marketing landings."""
from __future__ import annotations

from app.application.preview_app.industry_templates.loader import pick_template_id
from app.application.preview_app.saas_accounting import (
    ensure_saas_accounting_architect,
    ensure_saas_accounting_experience_plan,
    is_saas_accounting_brief,
)


def test_detects_accounting_brief() -> None:
    assert is_saas_accounting_brief(
        "Fintech / SaaS accounting",
        "invoices expenses bank reconciliation ledger for SMB bookkeepers",
    )


def test_picks_saas_accounting_pack() -> None:
    tid = pick_template_id(
        industry="SaaS accounting",
        surface="ops",
        context="invoices expenses bookkeeping reconciliation ledger",
    )
    assert tid == "saas-accounting"


def test_experience_plan_kills_marketing_home() -> None:
    plan = {
        "roles": [
            {
                "id": "owner",
                "pages": [
                    {
                        "id": "home",
                        "title": "Foresight Engine",
                        "surface": "public",
                        "skeleton_id": "public-home",
                        "section_slots": ["hero", "features", "cta"],
                    }
                ],
                "navigation": {
                    "links": [
                        {"label": "Get Started", "page_id": "home", "style": "cta"}
                    ]
                },
            }
        ]
    }
    out = ensure_saas_accounting_experience_plan(
        plan,
        context="saas accounting invoices expenses bank reconciliation ledger",
    )
    pages = out["roles"][0]["pages"]
    assert len(pages) >= 5
    assert pages[0]["surface"] == "ops"
    assert pages[0]["skeleton_id"] == "ops-dashboard"
    titles = {str(p.get("title") or "") for p in pages}
    assert "Invoices" in titles
    assert "Bank reconciliation" in titles


def test_architect_injects_product_routes() -> None:
    architect = {
        "routes": [
            {
                "path": "/",
                "title": "Financial Foresight",
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
                "instructions": "Build a foresight marketing hero.",
            }
        ],
    }
    out = ensure_saas_accounting_architect(
        architect,
        context="accounting bookkeeping invoices expenses reconciliation",
    )
    paths = {rt["path"] for rt in out["routes"]}
    assert "/" in paths
    assert "/invoices" in paths
    assert "/reconciliation" in paths
    assert "/reports" in paths
    home = next(rt for rt in out["routes"] if rt["path"] == "/")
    assert home["surface"] == "ops"
    assert "PRODUCT_KIND=saas_workspace" in out["files_to_generate"][0]["instructions"]
