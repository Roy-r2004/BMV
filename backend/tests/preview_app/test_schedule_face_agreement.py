"""One rule for "does this page need a ScheduleRail" — generator, gate, repair.

`_is_schedule_listing_route` answers "this route looks like a classes/services
listing". The dispatcher in `minimal_catalogue_page_scaffold` then overrides it
on `page_intent` and on catalogue browse leaves. Those overrides lived at the
call site, so only the generator applied them: the gate called the bare
predicate, and `repair.py` had drifted a third way with an inlined
`page_intent != "listing"`.

Requests 147, 148 and 150 were all withheld on `listing_not_schedule_rail` for
pages the pipeline had itself decided should not carry a rail — 147's was that
run's only gate issue. `schedule_face_required` is now the one answer.

The load-bearing test here is `test_gate_requirement_matches_what_the_generator_emits`:
it does not restate the rule, it compares the requirement against the *actual
emitted TSX*. Any future override added at a call site instead of inside the
function fails it, which is the drift this module exists to prevent.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.catalogue_contract.scaffold import (  # noqa: E402
    minimal_catalogue_page_scaffold,
    schedule_face_required,
)

#: The three routes that were withheld, verbatim from `generated_pages` on
#: requests 147, 148 and 150. Each carries a `page_intent`, which is why the
#: generator built a CatalogGrid face and the bare predicate failed it for that.
WITHHELD_ROUTES = [
    (
        "147 Meridian Physiotherapy",
        "src/pages/ServicesPage.tsx",
        {
            "path": "/services",
            "component_file": "src/pages/ServicesPage.tsx",
            "skeleton_id": "public-service",
            "page_intent": "listing",
            "title": "Services Page",
        },
    ),
    (
        "148 Ridgeline Bike Works",
        "src/pages/ServiceBookingPage.tsx",
        {
            "path": "/service/book",
            "component_file": "src/pages/ServiceBookingPage.tsx",
            "skeleton_id": "public-booking",
            "page_intent": "home",
            "title": "Service Booking",
        },
    ),
    (
        "150 Copperline Hardware",
        "src/pages/ServicesPage.tsx",
        {
            "path": "/services",
            "component_file": "src/pages/ServicesPage.tsx",
            "skeleton_id": "public-service",
            "page_intent": "listing",
            "title": "Services",
        },
    ),
]

#: A spread wide enough that both answers occur — a corpus where every route
#: agrees would pass the agreement test with the function stubbed to a constant.
#: Contact/auth paths are excluded: the utility compositor returns before the
#: listing dispatcher and the question does not arise.
FIXTURE_ROUTES = [
    # Keyword path: no intent, schedule wording — the rail's reason to exist.
    {"path": "/classes", "component_file": "src/pages/ClassesPage.tsx",
     "skeleton_id": "public-service", "title": "Classes"},
    {"path": "/services", "component_file": "src/pages/ServicesPage.tsx",
     "skeleton_id": "public-service", "title": "Services"},
    {"path": "/sessions", "component_file": "src/pages/SessionsPage.tsx",
     "skeleton_id": "public-booking", "title": "Session Booking"},
    # Same routes, intent declared — the architect's contract wins.
    {"path": "/classes", "component_file": "src/pages/ClassesPage.tsx",
     "skeleton_id": "public-service", "title": "Classes", "page_intent": "listing"},
    {"path": "/services", "component_file": "src/pages/ServicesPage.tsx",
     "skeleton_id": "public-service", "title": "Services", "page_intent": "home"},
    # Catalogue browse leaves — CatalogGrid faces even with schedule wording.
    {"path": "/shop", "component_file": "src/pages/ShopPage.tsx",
     "skeleton_id": "public-catalog", "title": "Shop services"},
    {"path": "/gallery", "component_file": "src/pages/GalleryPage.tsx",
     "skeleton_id": "public-catalog", "title": "Gallery of services"},
    # Detail and param routes are never the listing face.
    {"path": "/classes/:id", "component_file": "src/pages/ClassDetailPage.tsx",
     "skeleton_id": "public-detail", "title": "Class Detail"},
    # Ops routes: a public CatalogGrid face would fail the contract validator,
    # so the generator lets these keep the rail.
    {"path": "/staff/schedule", "component_file": "src/pages/role-staff/SchedulePage.tsx",
     "skeleton_id": "ops-dashboard", "title": "Staff schedule"},
    # Plainly not a listing at all.
    {"path": "/", "component_file": "src/pages/HomePage.tsx",
     "skeleton_id": "public-home", "title": "Homepage", "page_intent": "home"},
]


def _architect(routes: list[dict]) -> dict:
    return {"routes": routes}


def test_gate_requirement_matches_what_the_generator_emits() -> None:
    """The invariant: the gate never demands a rail the generator would not build.

    Compares against the emitted TSX rather than restating the rule, so an
    override re-added at a call site cannot satisfy it.
    """
    architect = _architect(FIXTURE_ROUTES)
    disagreements = []
    for route in FIXTURE_ROUTES:
        rel = route["component_file"]
        tsx = minimal_catalogue_page_scaffold(
            rel, route, brand_name="Fixture Co", architect=architect
        )
        emitted = "ScheduleRail" in tsx
        required = schedule_face_required(rel, route)
        if emitted != required:
            disagreements.append(
                f"{route['path']} (intent={route.get('page_intent') or '-'}, "
                f"skeleton={route['skeleton_id']}): "
                f"gate requires rail={required}, generator emitted={emitted}"
            )
    assert not disagreements, "generator/gate disagree:\n" + "\n".join(disagreements)


def test_the_fixture_corpus_exercises_both_answers() -> None:
    """Guards the test above from passing against a stubbed constant."""
    answers = {
        schedule_face_required(r["component_file"], r) for r in FIXTURE_ROUTES
    }
    assert answers == {True, False}


def test_the_three_withheld_routes_do_not_require_a_rail() -> None:
    """147, 148 and 150 — the finding, pinned against the real route records."""
    for label, rel, route in WITHHELD_ROUTES:
        assert not schedule_face_required(rel, route), label


def test_the_withheld_pages_still_do_not_render_one() -> None:
    """And the generator agrees, so the gate would now pass them.

    `schedule_face_required` returning False is only half the claim; if the
    generator emitted a rail anyway the pages would still be inconsistent.
    """
    for label, rel, route in WITHHELD_ROUTES:
        tsx = minimal_catalogue_page_scaffold(
            rel, route, brand_name="Fixture Co", architect=_architect([route])
        )
        assert "ScheduleRail" not in tsx, label


def test_intent_is_what_flips_the_three_withheld_routes() -> None:
    """Strip the architect's `page_intent` and all three want a rail again.

    Pins the *reason* rather than the outcome: without this, deleting the
    schedule branch entirely would satisfy every assertion above.
    """
    for label, rel, route in WITHHELD_ROUTES:
        without_intent = {k: v for k, v in route.items() if k != "page_intent"}
        assert schedule_face_required(rel, without_intent), label
        tsx = minimal_catalogue_page_scaffold(
            rel, without_intent, brand_name="Fixture Co",
            architect=_architect([without_intent]),
        )
        assert "ScheduleRail" in tsx, label


def test_public_browse_leaf_overrides_schedule_wording() -> None:
    """Request 64: `/shop` and `/gallery` are CatalogGrid faces, rail or not."""
    route = {"path": "/shop", "component_file": "src/pages/ShopPage.tsx",
             "skeleton_id": "public-catalog", "title": "Shop services and classes"}
    assert not schedule_face_required(route["component_file"], route)


def test_ops_route_keeps_its_rail_despite_a_browse_leaf() -> None:
    """The browse-leaf override is scoped to public faces.

    `_directory_listing_scaffold` builds a PublicShell face; on an ops route the
    contract validator rejects it, so the generator deliberately falls through.
    Dropping the `_is_public_face` guard would silently reroute ops pages.
    """
    route = {"path": "/staff/shop", "component_file": "src/pages/role-staff/ShopPage.tsx",
             "skeleton_id": "public-service", "title": "Staff shop sessions"}
    assert schedule_face_required(route["component_file"], route)
