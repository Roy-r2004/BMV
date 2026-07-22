"""Host role chrome helpers — taglines + page-map filtering."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.host_role_ux import role_tagline, routes_for_role


def test_tagline_prefers_architect_then_plan() -> None:
    plan = [{"id": "patient", "tagline": "Book care online"}]
    assert role_tagline({"id": "patient", "tagline": "My chart"}, plan) == "My chart"
    assert role_tagline({"id": "patient"}, plan) == "Book care online"
    assert role_tagline({"id": "staff"}, plan) == ""


def test_routes_for_role_filters_and_orphans() -> None:
    routes = [
        {"path": "/", "title": "Home"},
        {"path": "/doctors", "title": "Doctors", "role_id": "patient"},
        {"path": "/book-appointment", "title": "Book", "role_id": "patient"},
        {"path": "/staff/dashboard", "title": "Desk", "role_id": "staff"},
        {"path": "/ai-features", "title": "AI"},
        {"path": "/doctors", "title": "Doctors dup", "role_id": "patient"},
    ]
    patient = routes_for_role(routes, "patient", "patient")
    assert [r["path"] for r in patient] == ["/", "/doctors", "/book-appointment"]
    staff = routes_for_role(routes, "staff", "patient")
    assert [r["path"] for r in staff] == ["/staff/dashboard"]
    # Orphans only for the first role
    assert "/" not in {r["path"] for r in staff}


if __name__ == "__main__":
    test_tagline_prefers_architect_then_plan()
    test_routes_for_role_filters_and_orphans()
    print("Host role UX tests passed (2 tests)")
