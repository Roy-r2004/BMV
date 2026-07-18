"""Page component paths must canonicalize to PascalCase *Page.tsx."""
from __future__ import annotations

from app.application.preview_app.protected_paths import (
    canonicalize_page_component_path,
    safe_generated_route_path,
)


def test_homepage_variants_collapse():
    assert canonicalize_page_component_path("src/pages/Homepage.tsx") == "src/pages/HomePage.tsx"
    assert canonicalize_page_component_path("src/pages/HomePage.tsx") == "src/pages/HomePage.tsx"
    assert canonicalize_page_component_path("src/pages/Aboutpage.tsx") == "src/pages/AboutPage.tsx"


def test_admin_folder_stays_lowercase():
    assert (
        canonicalize_page_component_path("src/pages/admin/AdminDashboardPage.tsx")
        == "src/pages/admin/AdminDashboardPage.tsx"
    )
    # Stuck-together casing still ends with Page and keeps admin/
    assert (
        canonicalize_page_component_path("src/pages/admin/AdmindashboardPage.tsx")
        == "src/pages/admin/AdmindashboardPage.tsx"
    )


def test_owner_folder_stays_lowercase():
    assert (
        canonicalize_page_component_path("src/pages/owner/OwnerDashboardPage.tsx")
        == "src/pages/owner/OwnerDashboardPage.tsx"
    )
    assert (
        canonicalize_page_component_path("src/pages/Owner/Dashboard.tsx")
        == "src/pages/owner/DashboardPage.tsx"
    )


def test_safe_generated_route_path_canonicalizes():
    path = safe_generated_route_path(
        "src/pages/Homepage.tsx",
        {"_catalogue_workspace": True, "routes": []},
    )
    assert path == "src/pages/HomePage.tsx"
