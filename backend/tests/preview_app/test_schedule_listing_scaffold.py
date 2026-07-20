"""Service/class listing scaffolds must use ScheduleRail, not a home clone."""
from __future__ import annotations

from app.application.preview_app.catalogue_contract.scaffold import (
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.catalogue_contract.repair import (
    enforce_catalogue_page_contract,
)
from app.application.preview_app.catalogue_contract.validate import (
    validate_catalogue_page_content,
)


def test_classes_route_scaffold_uses_schedule_rail() -> None:
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/ClassesPage.tsx",
        {
            "path": "/classes",
            "title": "Classes & Workshops",
            "skeleton_id": "public-service",
            "section_slots": ["hero", "process", "features", "cta", "footer"],
            "page_id": "classes",
        },
        brand_name="Wheelhouse Ceramics",
    )
    assert "ScheduleRail" in tsx
    assert "BRAND_MANIFEST" in tsx
    assert "FeatureBento" not in tsx
    assert "seed.hero" not in tsx
    assert "/ai-features" in tsx


def test_services_catalog_route_uses_schedule_rail() -> None:
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/ServicesCatalogPage.tsx",
        {
            "path": "/services",
            "title": "Services",
            "skeleton_id": "public-catalog",
            "section_slots": ["hero", "showcase", "features", "cta", "footer"],
            "page_id": "services",
        },
        brand_name="Harborlight Salon",
    )
    assert "ScheduleRail" in tsx
    assert "FeatureBento" not in tsx


def test_enforce_replaces_catalog_clone_without_schedule_rail() -> None:
    architect = {
        "routes": [
            {
                "path": "/services",
                "title": "Services",
                "skeleton_id": "public-catalog",
                "section_slots": ["hero", "showcase", "cta", "footer"],
                "component_file": "src/pages/ServiceCatalogPage.tsx",
            }
        ]
    }
    freeform = """
import { PublicShell, PublicNav, ProductShowcase } from '@/ui';
export default function ServiceCatalogPage() {
  return <PublicShell brandName="Salon"><ProductShowcase items={[]} /></PublicShell>;
}
"""
    updated, replaced = enforce_catalogue_page_contract(
        "src/pages/ServiceCatalogPage.tsx",
        freeform,
        architect,
        brand_name="Harborlight Salon",
    )
    assert replaced is True
    assert "ScheduleRail" in updated


def test_schedule_listing_scaffold_passes_catalogue_contract() -> None:
    route = {
        "path": "/schedule",
        "title": "Ride Schedule",
        "skeleton_id": "public-home",
        "section_slots": ["hero", "showcase", "cta", "footer"],
        "page_id": "schedule",
    }
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/SchedulePage.tsx",
        route,
        brand_name="Summit Cycle Studio",
    )
    assert validate_catalogue_page_content(tsx, route) == []


def test_about_route_keeps_marketing_scaffold() -> None:
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/AboutPage.tsx",
        {
            "path": "/about",
            "title": "About Us",
            "skeleton_id": "public-service",
            "section_slots": ["hero", "process", "features", "cta", "footer"],
            "page_id": "about",
        },
        brand_name="Wheelhouse Ceramics",
    )
    assert "ScheduleRail" not in tsx
    assert "MarketingHero" in tsx
