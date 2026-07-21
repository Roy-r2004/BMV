"""Trading / hedge-fund desk must not collapse into CRM ops scaffolds."""
from __future__ import annotations

from app.application.preview_app.catalogue_contract.scaffold import (
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.industry_templates.apply import (
    apply_ops_industry_template_to_plan,
)
from app.application.preview_app.industry_templates.loader import (
    load_templates,
    pick_template_id,
)


def test_hedge_fund_brief_picks_trading_desk_pack() -> None:
    load_templates.cache_clear()
    tid = pick_template_id(
        industry="Fintech / Hedge fund trading",
        surface="ops",
        context=(
            "internal trading engine for a hedge fund desk blotter "
            "portfolio P&L risk limits not a SaaS for clients"
        ),
    )
    assert tid == "hedge-fund-trading-desk"


def test_ops_miss_does_not_rotate_crm_pack() -> None:
    load_templates.cache_clear()
    assert (
        pick_template_id(industry="Cupcake bakery", surface="ops", context="frosting")
        is None
    )


def test_tradeforge_scaffold_has_no_crm_client_copy() -> None:
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/DashboardPage.tsx",
        {
            "skeleton_id": "ops-dashboard",
            "title": "Main Dashboard",
            "path": "/dashboard",
            "slots": ["header", "kpis", "table", "activity", "risk"],
        },
        brand_name="TradeForge",
    )
    lowered = tsx.lower()
    assert "customer asked" not in lowered
    assert "client is waiting" not in lowered
    assert "fund book" in lowered or "open orders" in lowered
    assert "seed" in tsx


def test_ops_plan_stamps_trading_kpis() -> None:
    load_templates.cache_clear()
    plan = apply_ops_industry_template_to_plan(
        {},
        industry="Hedge fund trading",
        seed=7,
        context="blotter order ticket positions P&L",
    )
    assert plan["ops_template_id"] == "hedge-fund-trading-desk"
    labels = " ".join(k["label"] for k in plan["mock_seed"]["kpis"]).lower()
    assert "p&l" in labels or "orders" in labels or "exposure" in labels
