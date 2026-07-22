"""Ops packs must match the business — not stamp restaurant floor on clinics."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.catalogue_contract.scaffold import minimal_catalogue_page_scaffold
from app.application.preview_app.industry_templates.apply import (
    apply_industry_template_to_plan,
    apply_ops_industry_template_to_plan,
)
from app.application.preview_app.industry_templates.loader import load_templates, pick_template_id


def setup_module() -> None:
    load_templates.cache_clear()


def test_clinic_ops_pack_wins_over_restaurant_floor() -> None:
    tid = pick_template_id(
        industry="Healthcare",
        surface="ops",
        seed=3,
        context="Northside Family Clinic front desk staff appointments patients",
    )
    assert tid == "clinic-front-desk-ops"


def test_restaurant_floor_still_matches_cafe_ops() -> None:
    tid = pick_template_id(
        industry="Restaurant",
        surface="ops",
        seed=3,
        context="cafe host stand expo patio dining floor shift",
    )
    assert tid == "staff-floor-ops"


def test_ops_merge_keeps_marketing_hero_but_stamps_ops_board() -> None:
    plan = apply_industry_template_to_plan(
        {},
        industry="Healthcare",
        seed=3,
        surface="public",
        context="Northside Family Clinic dental patients",
    )
    plan = apply_ops_industry_template_to_plan(
        plan,
        industry="Healthcare",
        seed=3,
        context="Northside Family Clinic front desk appointments patients",
    )
    seed = plan["mock_seed"]
    assert "Care that starts on time" in str(seed.get("hero", {}).get("headline", ""))
    assert seed.get("opsHero", {}).get("headline")
    assert "patient" in str(seed["opsHero"]["headline"]).lower() or "flow" in str(
        seed["opsHero"]["headline"]
    ).lower()
    labels = " ".join(str(k.get("label", "")) for k in (seed.get("kpis") or [])).lower()
    assert "table" not in labels
    assert "expo" not in labels
    assert any(
        token in labels
        for token in ("arrival", "chair", "no-show", "slot", "patient", "check")
    )


def test_ops_dashboard_scaffold_prefers_ops_hero() -> None:
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/admin/StaffDashboardPage.tsx",
        {
            "path": "/staff/dashboard",
            "title": "Staff Dashboard",
            "skeleton_id": "ops-dashboard",
            "section_slots": ["header", "kpis", "chart", "activity"],
        },
        brand_name="Northside Family Clinic",
    )
    assert "seed.opsHero" in tsx
    # Must not bind the marketing homepage hero as the console title.
    assert "seed.hero?.headline" not in tsx or "opsHero" in tsx.split("PageHeader", 1)[1][:200]


if __name__ == "__main__":
    setup_module()
    test_clinic_ops_pack_wins_over_restaurant_floor()
    test_restaurant_floor_still_matches_cafe_ops()
    test_ops_merge_keeps_marketing_hero_but_stamps_ops_board()
    test_ops_dashboard_scaffold_prefers_ops_hero()
    print("Ops seed industry match tests passed")
