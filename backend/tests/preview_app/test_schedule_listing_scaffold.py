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


CLASSES_ROUTE = {
    "path": "/classes",
    "title": "Classes & Workshops",
    "skeleton_id": "public-service",
    "section_slots": ["hero", "process", "features", "cta", "footer"],
    "page_id": "classes",
}


def test_classes_route_scaffold_uses_schedule_rail() -> None:
    architect = {
        "routes": [
            {"path": "/", "surface": "public", "skeleton_id": "public-home"},
            CLASSES_ROUTE,
            {
                "path": "/get-in-touch",
                "title": "Get in touch",
                "surface": "public",
                "skeleton_id": "public-utility",
            },
        ]
    }
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/ClassesPage.tsx",
        CLASSES_ROUTE,
        brand_name="Wheelhouse Ceramics",
        architect=architect,
    )
    assert "ScheduleRail" in tsx
    assert "BRAND_MANIFEST" in tsx
    assert "FeatureBento" not in tsx
    assert "seed.hero" not in tsx
    assert "/ai-features" not in tsx
    # The contact CTA lands on the contact page this app declared, which it calls
    # `/get-in-touch`. The literal `/contact` was right for the apps that happen
    # to use that word and a dead link for the rest.
    assert 'href: "/get-in-touch"' in tsx
    assert "/contact" not in tsx


def test_the_contact_cta_is_dropped_when_no_contact_page_exists() -> None:
    """A missing button beats a dead one — the rail is on this page."""
    architect = {
        "routes": [
            {"path": "/", "surface": "public", "skeleton_id": "public-home"},
            CLASSES_ROUTE,
        ]
    }
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/ClassesPage.tsx",
        CLASSES_ROUTE,
        brand_name="Wheelhouse Ceramics",
        architect=architect,
    )
    assert "/contact" not in tsx
    assert 'href: "#classes-list"' in tsx


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
    # Non-home pages must not reuse homepage seed.hero copy.
    assert "seed.hero" not in tsx
    assert "About Us" in tsx
    assert 'variant="compact"' in tsx


def test_doctors_route_uses_directory_face() -> None:
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/DoctorsPage.tsx",
        {
            "path": "/doctors",
            "title": "Doctor Listing",
            "skeleton_id": "public-service",
            "section_slots": ["hero", "features", "cta", "footer"],
            "page_id": "doctors",
        },
        brand_name="Northside Family Clinic",
    )
    assert "// directory listing scaffold" in tsx
    assert "ProductShowcase" in tsx
    assert "PageHeader" in tsx
    assert "seed.hero" not in tsx
    assert "MarketingHero" not in tsx
    assert validate_catalogue_page_content(
        tsx,
        {
            "path": "/doctors",
            "title": "Doctor Listing",
            "skeleton_id": "public-service",
        },
    ) == []


def test_enforce_replaces_doctor_home_clone() -> None:
    architect = {
        "routes": [
            {
                "path": "/doctors",
                "title": "Doctor Listing",
                "skeleton_id": "public-service",
                "section_slots": ["hero", "features", "cta", "footer"],
                "component_file": "src/pages/DoctorsPage.tsx",
            }
        ]
    }
    home_clone = """
import { PublicShell, PublicNav, MarketingHero } from '@/ui';
import { images, seed } from '@/data/mock';
export default function DoctorsPage() {
  return (
    <PublicShell brandName="Clinic">
      <MarketingHero brandName="Clinic" headline={seed.hero?.headline} imageSrc={images.hero} />
    </PublicShell>
  );
}
"""
    updated, replaced = enforce_catalogue_page_contract(
        "src/pages/DoctorsPage.tsx",
        home_clone,
        architect,
        brand_name="Northside Family Clinic",
    )
    assert replaced is True
    assert "ProductShowcase" in updated
    assert "seed.hero" not in updated
