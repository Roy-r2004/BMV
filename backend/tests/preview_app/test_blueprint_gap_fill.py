"""The blueprint gap-fill adds a page only when nothing already serves it.

`product_kind.py`'s `elif contract.kind in PUBLIC_KINDS` branch used to gap-fill
`_storefront_pages()` into every public app whose routes were *already
substantive*, and `_storefront_pages()` declares `/gallery` and
`/gallery/:id -> ArtworkDetailPage.tsx` as literals with the page title
"Artwork". That is why a twelve-table trattoria shipped an art gallery, and it
survived an enforced AppSpec — a contract naming four pages did not stop the
sixth being appended.

The rule under test is deliberately not an industry keyword. A gap-fill may add a
page only when the app has no route that already serves it, where "serves it"
means the same path or the same resolved page contract; and a detail page is
added only when the listing it belongs to is served and has no detail child of
its own — **hung off whatever that listing is actually called**, which is the
half that was missing until session 27. Measured over the 47 stored route tables
before it shipped
(`scripts/measure/gallery_gapfill_census.py`): 22 runs change, and **no brief
ends without a catalogue page or without a detail page** — every art gallery
keeps both.
"""
from __future__ import annotations

from app.application.preview_app.product_kind import (
    apply_product_kind_to_architect,
    resolve_product_kind_contract,
)

STOREFRONT_BRIEF = (
    "Restaurant / cafe. Twelve-table Neapolitan trattoria in Brooklyn. "
    "Food menu, wine list, and a table reservation form."
)
BOOKING_BRIEF = (
    "Dental clinic. Appointment booking for cleanings and clear aligners, "
    "with a treatment enquiry form."
)


def _storefront():
    contract = resolve_product_kind_contract(STOREFRONT_BRIEF)
    assert contract.kind == "storefront"
    return contract


def _booking():
    contract = resolve_product_kind_contract(BOOKING_BRIEF)
    assert contract.kind == "booking_service"
    return contract


def _route(path: str, page_id: str, component: str, **extra) -> dict:
    return {
        "path": path,
        "page_id": page_id,
        "role_id": "customer",
        "title": page_id.replace("-", " ").title(),
        "component_file": f"src/pages/{component}",
        **extra,
    }


def _plan(*pages: dict, role_id: str = "customer") -> dict:
    return {"roles": [{"id": role_id, "pages": list(pages)}]}


def _paths(architect: dict) -> list[str]:
    return [str(r.get("path") or "") for r in architect["routes"]]


def _apply(routes: list[dict], contract, plan=None) -> list[str]:
    architect = {"routes": [dict(r) for r in routes], "files_to_generate": []}
    return _paths(apply_product_kind_to_architect(architect, contract, plan))


# --- the defect itself -------------------------------------------------------


def test_a_restaurant_with_a_menu_is_not_missing_a_catalogue() -> None:
    """Request 95's shape: `/menu` resolves to `public-catalog`, so no gallery."""
    routes = [
        _route("/", "home", "HomePage.tsx"),
        _route("/menu", "menu", "MenuPage.tsx"),
        _route("/reservations", "reservations", "ReservationsPage.tsx"),
    ]
    plan = _plan({"id": "menu", "purpose": "Diners browse the food and wine list."})
    paths = _apply(routes, _storefront(), plan)
    assert "/gallery" not in paths
    assert "/gallery/:id" not in paths
    # The detail page goes to `/menu/:id`, not away. It used to be dropped
    # entirely, because the gap-fill looked for a literal `/gallery` to hang it
    # off and this app calls its catalogue `/menu` — so the trattoria shipped a
    # dish grid whose every card fell through `path="*"` to the home page. What
    # the rule forbids is a *second* catalogue, not a way into the first.
    assert paths == ["/", "/menu", "/reservations", "/menu/:id"]


def test_the_detail_literal_goes_with_the_catalogue_literal() -> None:
    """`ArtworkDetailPage.tsx` is a gallery's file name, and this is a trattoria.

    The page survives — the menu needs a way in — but neither its blueprint path
    nor its blueprint naming does. "Artwork" is the page title, so it reaches the
    nav label and the page header; a detail page hung off a renamed listing takes
    that listing's name instead.
    """
    routes = [
        _route("/", "home", "HomePage.tsx"),
        _route("/menu", "menu", "MenuPage.tsx"),
        _route("/reservations", "reservations", "ReservationsPage.tsx"),
    ]
    plan = _plan({"id": "menu", "purpose": "Diners browse the food and wine list."})
    architect = apply_product_kind_to_architect(
        {"routes": routes, "files_to_generate": []}, _storefront(), plan
    )
    components = {str(f.get("path") or "") for f in architect["files_to_generate"]}
    assert "src/pages/ArtworkDetailPage.tsx" not in components
    assert "src/pages/GalleryPage.tsx" not in components
    assert "src/pages/MenuDetailPage.tsx" in components
    detail = next(r for r in architect["routes"] if r["path"] == "/menu/:id")
    assert detail["title"] == "Menu detail"
    assert "Artwork" not in detail["title"]


# --- the renamed catalogue: session 27's two withheld runs --------------------


#: The route tables requests 156 and 153 actually got, trimmed to what the
#: gap-fill reads. Both shipped a `public-catalog` grid and **no param route at
#: all** — every card fell through `path="*"` to the home page, and the journey
#: gate said `journey_no_detail_route` on both. Neither catalogue is called
#: `/gallery`, which is the entire reason the detail page was skipped.
WITHHELD_TABLES = {
    "156 Ridgeline Bike Works": (
        [
            _route("/", "home", "HomePage.tsx", skeleton_id="public-home"),
            _route("/bikes", "bike-range", "BikeRangePage.tsx", skeleton_id="public-catalog"),
            _route(
                "/service-booking", "service-booking", "ServiceBookingPage.tsx",
                skeleton_id="public-booking",
            ),
        ],
        "/bikes/:id",
    ),
    "153 Kestrel & Fern Bakehouse": (
        [
            _route("/", "home", "HomePage.tsx", skeleton_id="public-home"),
            _route(
                "/celebration-cakes", "celebration-cakes", "CelebrationCakesPage.tsx",
                skeleton_id="public-catalog",
            ),
            _route("/checkout", "checkout", "CheckoutPage.tsx", skeleton_id="public-utility"),
        ],
        "/celebration-cakes/:id",
    ),
}


def test_a_renamed_catalogue_still_gets_a_way_into_it() -> None:
    """The defect, against both real tables: a grid with nothing behind it."""
    for label, (routes, expected) in WITHHELD_TABLES.items():
        paths = _apply(routes, _storefront())
        assert expected in paths, f"{label}: no detail route was added ({paths})"
        assert "/gallery" not in paths, label
        assert "/gallery/:id" not in paths, label


def test_the_detail_page_is_named_after_the_listing_it_serves() -> None:
    """`Artwork` / `ArtworkDetailPage.tsx` on a bike shop is visible nonsense.

    The title reaches the nav label and the page header, so it is not an internal
    detail — it is copy the customer reads.
    """
    routes, _ = WITHHELD_TABLES["156 Ridgeline Bike Works"]
    architect = apply_product_kind_to_architect(
        {"routes": [dict(r) for r in routes], "files_to_generate": []}, _storefront()
    )
    detail = next(r for r in architect["routes"] if r["path"] == "/bikes/:id")
    assert detail["title"] == "Bike Range detail"
    assert detail["component_file"] == "src/pages/BikeRangeDetailPage.tsx"
    assert detail["skeleton_id"] == "public-detail"


def test_a_catalogue_that_is_only_a_param_route_hosts_nothing() -> None:
    """The `None` branch, and it is reachable.

    An app whose only `public-catalog` route is `/collection/:id` satisfies the
    browse page's served-kind test — so `/gallery` is not added — and offers the
    detail page nothing to hang off: it *is* a detail page. Accepting it as the
    host mints `/collection/:id/:id`, whose two segments bind the same param name
    so React Router keeps only the last; treating "no host" as an empty path mints
    a root-level `/:id` that matches every single-segment URL in the app. Both are
    worse than the missing page.
    """
    routes = [
        _route("/", "home", "HomePage.tsx", skeleton_id="public-home"),
        _route(
            "/collection/:id", "collection-detail", "CollectionDetailPage.tsx",
            skeleton_id="public-catalog",
        ),
        _route("/about", "about", "AboutPage.tsx", skeleton_id="public-home"),
    ]
    paths = _apply(routes, _storefront())
    assert "/gallery" not in paths
    assert "/gallery/:id" not in paths
    assert "/collection/:id/:id" not in paths
    assert "/:id" not in paths
    assert paths == ["/", "/collection/:id", "/about"]


def test_the_home_route_is_never_a_listing_to_hang_a_detail_page_off() -> None:
    """A one-page storefront whose `/` is the catalogue mints `//:id` otherwise."""
    routes = [
        _route("/", "shop", "ShopPage.tsx", skeleton_id="public-catalog"),
        _route("/about", "about", "AboutPage.tsx", skeleton_id="public-home"),
        _route("/contact", "contact", "ContactPage.tsx", skeleton_id="public-utility"),
    ]
    paths = _apply(routes, _storefront())
    assert not any(p.startswith("//") for p in paths), paths
    assert "/:id" not in paths


def test_a_booking_app_gets_no_detail_page_because_its_blueprint_has_none() -> None:
    """The funnel goes /services → /book; there is no per-item route to invent."""
    routes = [
        _route("/", "home", "HomePage.tsx", skeleton_id="public-home"),
        _route("/services", "services", "ServicesPage.tsx", skeleton_id="public-service"),
        _route("/book", "book", "BookPage.tsx", skeleton_id="public-booking"),
    ]
    paths = _apply(routes, _booking())
    assert not any(":" in p for p in paths), paths


# --- the boundary: a gallery must not lose its gallery ------------------------


def test_a_gallery_that_declares_a_catalogue_still_gets_its_detail_page() -> None:
    """The parent is served and has no detail child, so `/gallery/:id` is added."""
    routes = [
        _route("/", "home", "HomePage.tsx"),
        _route("/gallery", "gallery-home", "GalleryHomePage.tsx"),
        _route("/about", "about", "AboutPage.tsx"),
    ]
    plan = _plan({"id": "gallery-home", "purpose": "Collectors browse the collection."})
    paths = _apply(routes, _storefront(), plan)
    assert "/gallery/:id" in paths


def test_a_catalogue_that_already_has_a_detail_child_gets_no_second_one() -> None:
    """Requests 47 and 69 shipped `/gallery/:paintingId` *and* `/gallery/:id`."""
    routes = [
        _route("/", "home", "HomePage.tsx"),
        _route("/gallery", "gallery-home", "GalleryHomePage.tsx"),
        _route("/gallery/:paintingId", "painting", "PaintingDetailPage.tsx"),
    ]
    plan = _plan({"id": "gallery-home", "purpose": "Collectors browse the collection."})
    paths = _apply(routes, _storefront(), plan)
    assert "/gallery/:id" not in paths
    assert "/gallery/:paintingId" in paths


def test_an_unrelated_detail_page_does_not_stand_in_for_the_catalogue_s_own() -> None:
    """`/artwork/:id` details nothing at `/gallery`, so it must not suppress it."""
    routes = [
        _route("/", "home", "HomePage.tsx"),
        _route("/gallery", "gallery-home", "GalleryHomePage.tsx"),
        _route("/artwork/:id", "artwork", "ArtworkPage.tsx", skeleton_id="public-detail"),
    ]
    plan = _plan({"id": "gallery-home", "purpose": "Collectors browse the collection."})
    assert "/gallery/:id" in _apply(routes, _storefront(), plan)


# --- the entry route is an address, not a kind --------------------------------


def test_the_root_route_is_added_even_when_a_home_page_is_already_served() -> None:
    """Request 98 declared `/home`; the catch-all is `Navigate to="/"`."""
    routes = [
        _route("/home", "home", "HomePage.tsx"),
        _route("/rooms", "rooms", "RoomsPage.tsx"),
        _route("/rooms/:roomId", "room-detail", "RoomDetailPage.tsx"),
    ]
    plan = _plan({"id": "rooms", "purpose": "Guests browse the room collection."})
    paths = _apply(routes, _storefront(), plan)
    assert "/" in paths
    assert "/gallery" not in paths
    assert "/gallery/:id" not in paths


# --- a thin inventory is not a gap-fill ---------------------------------------


def test_a_thin_inventory_still_receives_the_whole_blueprint() -> None:
    """One route is not an app; there the blueprint *is* the product face."""
    routes = [_route("/menu", "menu", "MenuPage.tsx")]
    plan = _plan({"id": "menu", "purpose": "Diners browse the food and wine list."})
    paths = _apply(routes, _storefront(), plan)
    assert paths == ["/menu", "/", "/gallery", "/gallery/:id"]


# --- an app with no catalogue at all still gets one ---------------------------


def test_an_app_with_no_catalogue_is_still_given_one_and_its_detail_page() -> None:
    """The rule stops *duplicating* a catalogue; it does not stop supplying one."""
    routes = [
        _route("/", "home", "HomePage.tsx"),
        _route("/contact", "contact", "ContactPage.tsx"),
        _route("/hours", "hours", "HoursPage.tsx"),
    ]
    paths = _apply(routes, _storefront())
    assert "/gallery" in paths
    # `/gallery/:id` is only reachable because `/gallery` was added just above it.
    assert "/gallery/:id" in paths


# --- the booking contract: no detail child, so the kind test stands alone ------


def test_a_clinic_that_can_already_book_is_not_given_a_booking_page() -> None:
    routes = [
        _route("/", "home", "HomePage.tsx"),
        _route("/appointments", "appointments", "AppointmentsPage.tsx"),
        _route("/account", "account", "AccountPage.tsx"),
    ]
    paths = _apply(routes, _booking())
    assert "/book" not in paths
    # Nothing here is a services page, so that one is a real gap and is filled.
    assert "/services" in paths


def test_the_ai_hub_does_not_count_as_a_page_the_app_serves() -> None:
    """`/ai-features` resolves to `public-service` and must not absorb `/services`."""
    with_hub = [
        _route("/", "home", "HomePage.tsx"),
        _route("/account", "account", "AccountPage.tsx"),
        _route("/ai-features", "PAGE-AI-FEATURES", "AiFeaturesPage.tsx"),
    ]
    assert "/services" in _apply(with_hub, _booking())

    with_a_real_page = [
        _route("/", "home", "HomePage.tsx"),
        _route("/account", "account", "AccountPage.tsx"),
        _route("/faq", "faq", "FaqPage.tsx"),
    ]
    assert "/services" not in _apply(with_a_real_page, _booking())


# --- how a route resolves to a page contract ----------------------------------


def test_the_plan_page_decides_what_a_route_is() -> None:
    """Request 98's `/rooms` is a catalogue with the plan merged and not without it."""
    routes = [
        _route("/", "home", "HomePage.tsx"),
        _route("/rooms", "rooms", "RoomsPage.tsx"),
        _route("/dining", "dining", "DiningPage.tsx"),
    ]
    plan = _plan({"id": "rooms", "purpose": "Guests browse the room collection."})
    assert "/gallery" not in _apply(routes, _storefront(), plan)
    assert "/gallery" in _apply(routes, _storefront())


def test_a_plan_page_is_matched_by_id_when_the_role_names_differ() -> None:
    routes = [
        _route("/", "home", "HomePage.tsx"),
        _route("/rooms", "rooms", "RoomsPage.tsx"),
        _route("/dining", "dining", "DiningPage.tsx"),
    ]
    plan = _plan(
        {"id": "rooms", "purpose": "Guests browse the room collection."},
        role_id="ROLE-GUEST",
    )
    assert "/gallery" not in _apply(routes, _storefront(), plan)


def test_an_ambiguous_page_id_is_not_matched_by_id() -> None:
    """Two roles own a page called `rooms`; the normalizer refuses to guess and so do we."""
    routes = [
        _route("/", "home", "HomePage.tsx"),
        _route("/rooms", "rooms", "RoomsPage.tsx"),
        _route("/dining", "dining", "DiningPage.tsx"),
    ]
    plan = {
        "roles": [
            {
                "id": "ROLE-GUEST",
                "pages": [{"id": "rooms", "purpose": "Guests browse the room collection."}],
            },
            {
                "id": "ROLE-STAFF",
                "pages": [{"id": "rooms", "purpose": "Staff update nightly rates."}],
            },
        ]
    }
    assert "/gallery" in _apply(routes, _storefront(), plan)


def test_the_route_s_own_skeleton_wins_over_the_plan_page_s() -> None:
    """`_normalize_architect` merges `{**page, **route}`; this must agree with it."""
    routes = [
        _route("/", "home", "HomePage.tsx"),
        _route("/menu", "menu", "MenuPage.tsx", skeleton_id="public-service"),
        _route("/reservations", "reservations", "ReservationsPage.tsx"),
    ]
    plan = _plan({"id": "menu", "skeleton_id": "public-catalog"})
    assert "/gallery" in _apply(routes, _storefront(), plan)


def test_a_route_that_already_names_its_skeleton_needs_no_plan() -> None:
    """The enforced path and the archived corpus both arrive with skeleton_id set."""
    routes = [
        _route("/", "home", "HomePage.tsx"),
        _route("/menu", "menu", "MenuPage.tsx", skeleton_id="public-catalog"),
        _route("/reservations", "reservations", "ReservationsPage.tsx"),
    ]
    assert "/gallery" not in _apply(routes, _storefront())
