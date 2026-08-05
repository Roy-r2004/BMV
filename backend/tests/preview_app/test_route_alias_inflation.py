"""Route alias inflation, fixed from the end that causes it.

`assemble.py` minted **two** detail aliases for every listing — `base/:id` and
`base/:slug` — because the scaffolded detail page read
`params.id ?? params.slug`. The router was shaped by one line of generated TSX.

The cost is not only route count. Request 69 shipped three routes to the same
page:

    <Route path="/gallery/:paintingId" element={<PaintingDetailPage />} />
    <Route path="/gallery/:id"         element={<PaintingDetailPage />} />
    <Route path="/gallery/:slug"       element={<PaintingDetailPage />} />

All three match `/gallery/whatever`; React Router binds exactly one of them, so
**at most one of the three param names is the one the page reads**, and the page
read `params.id`. Request 82 shipped the same shape for `/rooms/:roomId`. Across
the 47 stored route tables, **16 routes in 10 runs declare a param named neither
`id` nor `slug`** — every one of them a detail page the deterministic scaffold
could not resolve an item for, rendering the generic "This piece" against a
default image for every id.

So the scaffold reads whichever param the route declared, and the router stops
minting a second alias whose only difference is the name. Measured with
`scripts/measure/route_alias_census.py` over all 47 stored tables, driving the
previous `assemble.py` out of git for the "before" column: **36 runs change,
800 → 727 routes, 73 removed, and no declared route is lost on any run.**
"""
from __future__ import annotations

import re
from pathlib import Path

from app.application.preview_app.assemble import _has_param_child, write_app_tsx
from app.application.preview_app.catalogue_contract.scaffold import _detail_param_block
from app.infrastructure.templating.renderer import get_template_renderer

_PATH_RE = re.compile(r'<Route\s+path="([^"]+)"')


def _architect(paths: list[tuple[str, str, str]]) -> dict:
    """The route shape `write_app_tsx` actually reads.

    `component_file` and `surface` are both load-bearing: without them the
    function re-derives a path from the file stem, so `/gallery/:paintingId`
    silently became `/paintingdetail` and `/rooms` disappeared altogether. The
    first version of this file used `layout` and no `component_file` and its
    fixtures were wrong rather than the code.
    """
    return {
        "routes": [
            {
                "path": path,
                "component_file": f"src/pages/{component}.tsx",
                "component": component,
                "surface": surface,
            }
            for path, component, surface in paths
        ],
        "files_to_generate": [],
        "roles": [],
    }


def _routes_for(architect: dict, tmp_path: Path) -> list[str]:
    workspace = tmp_path / "ws"
    pages = workspace / "src" / "pages"
    pages.mkdir(parents=True)
    for route in architect["routes"]:
        component = route["component"]
        (pages / f"{component}.tsx").write_text(
            f"export default function {component}() {{ return <div />; }}\n",
            encoding="utf-8",
        )
    write_app_tsx(workspace, architect, get_template_renderer())
    found = _PATH_RE.findall((workspace / "src" / "App.tsx").read_text(encoding="utf-8"))
    assert len(found) > 1, (
        f"fixture produced no routes ({found}); every assertion below would pass "
        "vacuously, so the fixture is wrong rather than the code"
    )
    return found


# --------------------------------------------------------------------------
# the scaffold reads the param the route declared
# --------------------------------------------------------------------------


def test_the_detail_page_reads_whichever_param_the_route_declared() -> None:
    block = _detail_param_block("Harbour & Vine", "/gallery")

    assert "Object.values(params)[0]" in block, (
        "the detail page still reads two hardcoded param names, so a route that "
        "declares any third name resolves no item"
    )
    assert "params.id ??" not in block
    assert "params.slug" not in block


def test_the_page_still_resolves_an_item_and_a_not_found() -> None:
    """The read changed; nothing else about the block may have.

    `itemKey` feeds the id/slug/title/position matcher and the `notFound` path,
    and a fix that quietly dropped either would turn every detail page into a
    permanent empty state — which is exactly the failure it is meant to remove.
    """
    block = _detail_param_block("Harbour & Vine", "/gallery")

    # The trim is behaviour, not decoration: a card linking `/gallery/ 3` (or a
    # param carrying a stray space) matches nothing without it, and the page
    # silently renders the empty state. Pinned in the same anchor as the read so
    # neither can be dropped while the other is asserted.
    assert "String(Object.values(params)[0] ?? '').trim();" in block
    assert "const notFound = itemKey !== '' && itemIndex < 0;" in block
    assert "itemToken(entry?.slug) === wantedToken" in block
    assert "String(index + 1) === itemKey" in block


# --------------------------------------------------------------------------
# the router stops minting the twin
# --------------------------------------------------------------------------


def test_a_listing_with_no_detail_route_still_gets_exactly_one_alias(
    tmp_path: Path,
) -> None:
    """The alias exists to make seed cards linking `/gallery/<slug>` resolve.

    Removing it entirely would reintroduce the dead link it was added for, so
    the fix reduces two to one — never two to none.
    """
    paths = _routes_for(
        _architect(
            [
                ("/", "HomePage", "public"),
                ("/gallery", "GalleryPage", "public"),
                ("/artwork-detail", "ArtworkDetailPage", "public"),
            ]
        ),
        tmp_path,
    )

    assert "/gallery/:id" in paths, "a listing with no detail child lost its alias"
    assert "/gallery/:slug" not in paths, (
        "both aliases are still minted — two routes matching the same URLs, "
        "differing only in the name the page no longer reads"
    )


def test_an_app_that_declares_its_own_param_child_gets_no_alias(
    tmp_path: Path,
) -> None:
    """Request 69, and the reason this is more than bundle weight.

    `/gallery/:paintingId` already matches every URL `/gallery/:id` would. The
    alias adds a second route the router may prefer, binding a name the page
    does not read.
    """
    paths = _routes_for(
        _architect(
            [
                ("/", "HomePage", "public"),
                ("/gallery", "GalleryPage", "public"),
                ("/gallery/:paintingId", "PaintingDetailPage", "public"),
            ]
        ),
        tmp_path,
    )

    assert "/gallery/:paintingId" in paths, "the declared detail route was dropped"
    assert "/gallery/:id" not in paths, (
        "a second route matching the same URLs was minted beside the declared one"
    )
    assert "/gallery/:slug" not in paths
    assert len([p for p in paths if p.startswith("/gallery/")]) == 1, (
        f"more than one route serves /gallery/<x>: {paths}"
    )


def test_the_listing_site_also_respects_a_declared_param_child(
    tmp_path: Path,
) -> None:
    """The *other* alias site, bound on its own.

    There are two, and the fixture above only reaches one of them: the listing
    site needs a detail component that is **not** itself under the listing
    prefix, because a page at `/gallery/:paintingId` is excluded from the
    candidate list by the same regex that selects the listing. Without a
    `/artwork-detail` sitting outside it the site never runs, and disabling its
    suppression changed nothing — a mutation survivor, and blind spot 4 exactly.
    """
    paths = _routes_for(
        _architect(
            [
                ("/", "HomePage", "public"),
                ("/gallery", "GalleryPage", "public"),
                ("/gallery/:paintingId", "PaintingDetailPage", "public"),
                ("/artwork-detail", "ArtworkDetailPage", "public"),
            ]
        ),
        tmp_path,
    )

    assert "/gallery/:paintingId" in paths
    assert "/gallery/:id" not in paths, (
        "the listing site minted an alias over a declared param child: "
        f"{[p for p in paths if p.startswith('/gallery/')]}"
    )
    assert len([p for p in paths if p.startswith("/gallery/")]) == 1


def test_a_declared_route_is_never_dropped(tmp_path: Path) -> None:
    """The safety property. Suppressing an alias must never suppress a page.

    Measured over all 47 stored tables by the census; pinned here so a future
    change to the suppression cannot quietly take a real route with it.
    """
    paths = set(
        _routes_for(
            _architect(
                [
                    ("/", "HomePage", "public"),
                    ("/rooms", "RoomsPage", "public"),
                    ("/rooms/:roomId", "RoomDetailPage", "public"),
                    ("/about", "AboutPage", "public"),
                    ("/admin/guests", "GuestsPage", "admin"),
                    ("/admin/guests/:guestId", "GuestDetailPage", "admin"),
                ]
            ),
            tmp_path,
        )
    )

    for declared in (
        "/",
        "/rooms",
        "/rooms/:roomId",
        "/about",
        "/admin/guests",
        "/admin/guests/:guestId",
    ):
        assert declared in paths, f"{declared} was declared and is not routed"


def test_the_sibling_alias_site_also_mints_one(tmp_path: Path) -> None:
    """There are two alias sites and they must not disagree.

    This one fires on a *literal* child (`/gallery/coastal-whispers`) rather
    than on a listing, and it was the site that minted `/owner/:id` pairs.
    """
    paths = _routes_for(
        _architect(
            [
                ("/", "HomePage", "public"),
                ("/collection", "CollectionPage", "public"),
                ("/collection/coastal-whispers", "ArtworkDetailPage", "public"),
            ]
        ),
        tmp_path,
    )

    assert "/collection/:id" in paths
    assert "/collection/:slug" not in paths


# --------------------------------------------------------------------------
# the predicate itself
# --------------------------------------------------------------------------


def test_the_param_child_test_reads_one_segment_only() -> None:
    """`/gallery/:id/edit` is not a param child of `/gallery`.

    A grandchild does not match `/gallery/<x>`, so suppressing the alias for it
    would reintroduce the dead link. Both directions are pinned because the two
    cases differ by a single `/` and nothing else would catch a slip.
    """
    assert _has_param_child("/gallery", {"/gallery", "/gallery/:paintingId"}) is True
    assert _has_param_child("/gallery", {"/gallery", "/gallery/:id/edit"}) is False
    assert _has_param_child("/gallery", {"/gallery", "/gallery/coastal"}) is False
    assert _has_param_child("/gallery", {"/gallery"}) is False
    # A trailing slash on the base must not change the answer.
    assert _has_param_child("/gallery/", {"/gallery/:slug"}) is True
