"""Product Face Contract — packs gap-fill only; intent beats keywords."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.catalogue_contract.scaffold import (
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.industry_templates.apply import (
    apply_industry_template_to_plan,
    apply_ops_industry_template_to_plan,
)
from app.application.preview_app.industry_templates.loader import load_templates
from app.application.preview_app.product_face import (
    ensure_product_face_on_plan,
    gap_fill_ops_seed_from_pack,
    materialize_mock_seed,
)


def setup_module() -> None:
    load_templates.cache_clear()


def test_pack_gap_fill_does_not_overwrite_ops_kpis() -> None:
    face = {
        "version": 1,
        "roles": [],
        "routes": [],
        "public_seed": {
            "hero": {
                "headline": "Care that starts on time",
                "subcopy": "Clinic marketing",
            }
        },
        "ops_seed": {
            "hero": {"headline": "Today's patient flow", "subcopy": "Check-ins"},
            "kpis": [
                {"label": "Arrivals today", "value": "28", "delta": "+4", "hint": "vs yesterday"}
            ],
        },
    }
    filled = gap_fill_ops_seed_from_pack(
        face,
        {
            "hero": {"headline": "Floor board", "subcopy": "Restaurant"},
            "items": [{"title": "Waitlist · 6 parties", "description": "Table 12"}],
            "kpis": [{"label": "Running tickets", "value": "11", "delta": "", "hint": "expo"}],
        },
    )
    assert filled["ops_seed"]["hero"]["headline"] == "Today's patient flow"
    assert filled["ops_seed"]["kpis"][0]["label"] == "Arrivals today"
    # Empty items may be filled from pack — OK; non-empty KPIs must stay.
    seed = materialize_mock_seed(filled)
    assert seed["opsHero"]["headline"] == "Today's patient flow"
    assert seed["kpis"][0]["label"] == "Arrivals today"


def test_ops_seed_not_overwritten_by_staff_floor_pack() -> None:
    plan = {
        "roles": [
            {
                "id": "staff",
                "label": "Front Desk",
                "pages": [
                    {
                        "id": "desk",
                        "title": "Staff Dashboard",
                        "path": "/staff/dashboard",
                        "surface": "ops",
                        "skeleton_id": "ops-dashboard",
                        "page_intent": "ops",
                    }
                ],
            }
        ],
        "product_face": {
            "version": 1,
            "roles": [],
            "routes": [
                {
                    "path": "/staff/dashboard",
                    "title": "Staff Dashboard",
                    "role_id": "staff",
                    "page_intent": "ops",
                }
            ],
            "public_seed": {
                "hero": {
                    "headline": "Care that starts on time and explains every step",
                    "subcopy": "Cleanings and orthodontics",
                }
            },
            "ops_seed": {
                "hero": {
                    "headline": "Today's patient flow",
                    "subcopy": "Check-ins and no-show risk",
                },
                "kpis": [
                    {
                        "label": "In chair now",
                        "value": "6",
                        "delta": "2 waiting",
                        "hint": "active visits",
                    }
                ],
            },
        },
    }
    # Even with cafe/hospitality context forcing staff-floor tags, contract KPIs win.
    out = apply_ops_industry_template_to_plan(
        plan,
        industry="Restaurant",
        seed=3,
        context="cafe host stand expo patio dining floor front desk staff",
    )
    assert out["mock_seed"]["opsHero"]["headline"] == "Today's patient flow"
    assert out["mock_seed"]["kpis"][0]["label"] == "In chair now"
    assert "table" not in out["mock_seed"]["kpis"][0]["label"].lower()


def test_page_intent_listing_face_without_doctor_keyword() -> None:
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/ProvidersPage.tsx",
        {
            "path": "/providers",
            "title": "Our Providers",
            "skeleton_id": "public-service",
            "section_slots": ["hero", "features", "cta", "footer"],
            "page_intent": "listing",
        },
        brand_name="Northside Family Clinic",
    )
    assert "// directory listing scaffold" in tsx
    assert "seed.hero" not in tsx
    assert "ProductShowcase" in tsx


def test_ops_header_uses_ops_seed_not_public_hero() -> None:
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/admin/StaffDashboardPage.tsx",
        {
            "path": "/staff/dashboard",
            "title": "Staff Dashboard",
            "skeleton_id": "ops-dashboard",
            "section_slots": ["header", "kpis", "activity"],
            "page_intent": "ops",
        },
        brand_name="Northside Family Clinic",
    )
    assert "seed.opsHero?.headline" in tsx
    assert "seed.hero?.headline" not in tsx


def test_public_pack_does_not_wipe_existing_hero() -> None:
    plan = {
        "roles": [{"id": "patient", "label": "Patient", "pages": []}],
        "product_face": {
            "version": 1,
            "roles": [],
            "routes": [],
            "public_seed": {
                "hero": {
                    "headline": "Brief-owned headline",
                    "subcopy": "From the LLM contract",
                }
            },
            "ops_seed": {},
        },
    }
    out = apply_industry_template_to_plan(
        plan,
        industry="Healthcare",
        seed=3,
        surface="public",
        context="Northside Family Clinic dental patients",
    )
    assert out["mock_seed"]["hero"]["headline"] == "Brief-owned headline"


def test_ensure_product_face_stamps_intents() -> None:
    plan = ensure_product_face_on_plan(
        {
            "roles": [
                {
                    "id": "patient",
                    "label": "Patient",
                    "pages": [
                        {
                            "id": "home",
                            "title": "Home",
                            "path": "/",
                            "skeleton_id": "public-home",
                            "surface": "public",
                        }
                    ],
                }
            ],
            "routes": [
                {
                    "path": "/",
                    "title": "Home",
                    "skeleton_id": "public-home",
                    "role_id": "patient",
                }
            ],
        }
    )
    assert plan["roles"][0]["pages"][0]["page_intent"] == "home"
    assert plan["routes"][0]["page_intent"] == "home"
    assert plan["product_face"]["version"] == 1


if __name__ == "__main__":
    setup_module()
    test_pack_gap_fill_does_not_overwrite_ops_kpis()
    test_ops_seed_not_overwritten_by_staff_floor_pack()
    test_page_intent_listing_face_without_doctor_keyword()
    test_ops_header_uses_ops_seed_not_public_hero()
    test_public_pack_does_not_wipe_existing_hero()
    test_ensure_product_face_stamps_intents()
    print("Product face contract tests passed")
