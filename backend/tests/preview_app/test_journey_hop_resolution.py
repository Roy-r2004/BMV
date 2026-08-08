"""The walk follows the funnel, not the words the architect used for it.

`_find_route` matched the hop's `path_hint` exactly, then by first path segment.
`/hire/reserve` shares no first segment with `/book`, so request 150's terminal
hop resolved to nothing and the walk reported `journey_next_hop_missing` — "the
next step (/book) is not a declared route" — against an app whose booking page
was sitting right there under another name. Request 148 lost its whole journey
the same way: `/bikes` shares no stem with `/gallery`, so browse, detail and
inquire all came back absent and nothing about that app's funnel was checked at
all.

Each hop now carries the skeleton its page wears, and that is tried between the
exact-hint pass and the stem pass. Stem matching stays underneath it, so a thin
contract with no `skeleton_id` anywhere resolves exactly as it did before.

The load-bearing test is `test_the_verdict_does_not_depend_on_the_routes_name`:
one app, four names for its booking page, one verdict. It is a property, not an
example, so a rename this fix does not cover fails it rather than passing quietly.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.capabilities.journey import (  # noqa: E402
    JOURNEYS,
    walk_journey,
)
from app.application.preview_app.catalogue_contract.scaffold import (  # noqa: E402
    minimal_catalogue_page_scaffold,
)
from tests.preview_app.real_route_records import architect, brand  # noqa: E402

#: What each stored request was classified as, read off
#: `requests.generated_pages -> preview_app -> journey -> product_kind`.
REAL_PRODUCT_KIND = {
    146: "storefront",
    147: "booking_service",
    148: "storefront",
    150: "booking_service",
    151: "internal_ops",
}


def _build(workspace: Path, contract: dict[str, Any], brand_name: str) -> None:
    """Generate every page of an app, exactly as the pipeline does."""
    for route in contract["routes"]:
        rel = str(route["component_file"])
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            minimal_catalogue_page_scaffold(
                rel, route, brand_name=brand_name, architect=contract
            ),
            encoding="utf-8",
        )


def _verdict(
    workspace: Path,
    contract: dict[str, Any],
    brand_name: str,
    *,
    served: list[str] | None = None,
) -> dict[str, Any]:
    """Walk one generated app and reduce its report to what this module is about.

    `served` writes an `App.tsx` when the router matters — the walk answers
    against the table `App.tsx` ships, and falls back to the architect's when
    there is none.

    Dead-link codes are dropped. They are the subject of steps 2a/2b and of the
    href-mask fix in `37f054c`, and on a scaffold-only workspace they also count
    the absence of `src/data/mock.ts` and of `assemble.py`'s route aliasing. What
    is under test here is which route each hop resolves to.
    """
    _build(workspace, contract, brand_name)
    if served is not None:
        (workspace / "src").mkdir(parents=True, exist_ok=True)
        (workspace / "src/App.tsx").write_text(
            "\n".join(
                f'          <Route path="{p}" element={{<Page />}} />' for p in served
            ),
            encoding="utf-8",
        )
    summary = walk_journey(workspace, contract).summary()
    return {
        "hops_ok": summary["hops_ok"],
        "hops_absent": summary["hops_absent"],
        "codes": sorted(
            f["code"] for f in summary["broken"] if not f["code"].startswith("journey_dead_link")
        ),
    }


def _real(request_id: int) -> dict[str, Any]:
    contract = architect(request_id)
    contract["product_kind"] = REAL_PRODUCT_KIND[request_id]
    return contract


# --------------------------------------------------------------------------- #
# the property: a rename changes nothing


#: One booking business, four names for the same page. `/hire/reserve` is 150's
#: real one and the one the stem pass cannot reach; `/book` is the literal the
#: walker used to hold everything against.
BOOKING_ROUTE_NAMES = ["/book", "/reserve", "/appointments", "/hire/reserve"]


def _permutation_architect(booking_path: str) -> dict[str, Any]:
    return {
        "product_kind": "booking_service",
        "routes": [
            {
                "path": "/",
                "title": "Homepage",
                "surface": "public",
                "skeleton_id": "public-home",
                "page_intent": "home",
                "component_file": "src/pages/HomePage.tsx",
                "section_slots": ["hero", "features", "cta", "footer"],
            },
            {
                "path": "/services",
                "title": "Services",
                "surface": "public",
                "skeleton_id": "public-service",
                "page_intent": "listing",
                "component_file": "src/pages/ServicesPage.tsx",
                "section_slots": ["hero", "showcase", "cta", "footer"],
            },
            {
                "path": booking_path,
                "title": "Book a visit",
                "surface": "public",
                "skeleton_id": "public-booking",
                "page_intent": "booking",
                "component_file": "src/pages/BookingPage.tsx",
                "section_slots": ["hero", "booking", "footer"],
            },
        ],
    }


def test_the_verdict_does_not_depend_on_the_routes_name(tmp_path: Path) -> None:
    """One app, four names for its booking page, one verdict."""
    verdicts = {}
    for index, name in enumerate(BOOKING_ROUTE_NAMES):
        workspace = tmp_path / f"app{index}"
        workspace.mkdir()
        verdicts[name] = _verdict(
            workspace, _permutation_architect(name), "Fixture Physio"
        )
    distinct = {repr(v) for v in verdicts.values()}
    assert len(distinct) == 1, f"the name changed the verdict: {verdicts}"


def test_the_permutation_app_is_one_the_walk_actually_passes(tmp_path: Path) -> None:
    """Guards the guard: four identical *failures* would satisfy the test above."""
    workspace = tmp_path / "app"
    workspace.mkdir()
    verdict = _verdict(workspace, _permutation_architect("/hire/reserve"), "Fixture Physio")
    assert verdict["codes"] == []
    assert verdict["hops_ok"] == ["browse", "book"]


def test_the_permutation_covers_a_name_the_stem_pass_cannot_reach() -> None:
    """`/hire/reserve` is the case; `/reserve` alone would pass on shape luck."""
    hint = JOURNEYS["booking_service"].hops[-1].path_hint
    stem = hint.strip("/").split("/")[0]
    assert any(
        name.strip("/").split("/")[0] != stem for name in BOOKING_ROUTE_NAMES
    ), "every permutation shares a first segment with the hint — nothing is proven"


# --------------------------------------------------------------------------- #
# the real records


def test_150_no_longer_reports_its_booking_page_missing(tmp_path: Path) -> None:
    """The finding, verbatim: "the next step (/book) is not a declared route".

    150's booking page is `/hire/reserve` and the walk compared the literal `/book`
    against the route table. Both the missing-hop finding and the dead `/book`
    link it produced downstream are gone.
    """
    verdict = _verdict(
        tmp_path,
        _real(150),
        brand(150),
        # `/catalogue/:id` is the alias `assemble.py` mints from the `/product`
        # detail page onto the catalogue listing; it exists only in `App.tsx`.
        served=["/", "/catalogue", "/product", "/hire/reserve", "/services", "/catalogue/:id"],
    )
    assert "journey_next_hop_missing" not in verdict["codes"]
    assert "book" not in verdict["hops_absent"]
    assert verdict["hops_ok"] == ["browse", "book"]
    assert verdict["codes"] == []


@pytest.mark.parametrize("request_id", [146, 147])
def test_the_corpus_shaped_apps_are_unchanged(request_id: int, tmp_path: Path) -> None:
    """146 and 147 named their routes the way the hints do — nothing may move.

    146 walked all three storefront hops and 147 both booking hops in session 26;
    the only finding either had was 146's href-mask defect, fixed in `37f054c`.
    """
    verdict = _verdict(tmp_path, _real(request_id), brand(request_id))
    expected_hops = {
        146: ["browse", "detail", "inquire"],
        147: ["browse", "book"],
    }[request_id]
    assert verdict["hops_ok"] == expected_hops
    assert verdict["hops_absent"] == []
    assert verdict["codes"] == []


def test_151_has_no_journey_at_all(tmp_path: Path) -> None:
    """An ops console declares no funnel, so there is nothing to resolve."""
    verdict = _verdict(tmp_path, _real(151), brand(151))
    assert verdict == {"hops_ok": [], "hops_absent": [], "codes": []}


def test_148s_browse_hop_resolves_to_the_page_that_serves_it(tmp_path: Path) -> None:
    """The intentional verdict change, pinned so it is not a surprise.

    148's browse face is `/bikes`. The stem pass could not reach it from the hint
    `/gallery`, so all three storefront hops came back absent in session 26 and
    *nothing about that app's funnel was checked*. It resolves now, and passes:
    the grid is a CatalogGrid and its cards link into `/bikes/:id`, which is the
    route `assemble.py` mints from the `/bikes/v2` detail page.
    """
    verdict = _verdict(
        tmp_path,
        _real(148),
        brand(148),
        served=["/", "/bikes", "/service/book", "/bikes/v2", "/bikes/:id"],
    )
    assert "browse" not in verdict["hops_absent"]
    assert verdict["hops_ok"] == ["browse"]
    assert verdict["codes"] == []


def test_the_skeleton_outranks_a_route_that_merely_shares_the_first_segment(
    tmp_path: Path,
) -> None:
    """Order matters, not just presence.

    The stem pass matches on first segment alone, so a booking policy page at
    `/book/faq` answers the hint `/book` and a services *terms* page answers
    `/services`. Both are the wrong page — one has no BookingPanel, the other no
    listing — and both used to win because they were tried first. The skeleton is
    the architect's statement of what a page *is*; the stem is a guess about what
    it is called, so the guess goes second.

    Demoting the skeleton pass below the stem pass fails here and nowhere else.
    """
    contract = _permutation_architect("/hire/reserve")
    contract["routes"].extend(
        [
            {
                "path": "/book/faq",
                "title": "Booking policy",
                "surface": "public",
                "skeleton_id": "public-home",
                "page_intent": "home",
                "component_file": "src/pages/BookingPolicyPage.tsx",
                "section_slots": ["hero", "features", "footer"],
            },
            {
                "path": "/services/terms",
                "title": "Service terms",
                "surface": "public",
                "skeleton_id": "public-home",
                "page_intent": "home",
                "component_file": "src/pages/ServiceTermsPage.tsx",
                "section_slots": ["hero", "features", "footer"],
            },
        ]
    )
    verdict = _verdict(tmp_path, contract, "Fixture Physio")
    assert verdict["codes"] == []
    assert verdict["hops_ok"] == ["browse", "book"]


def test_an_ops_detail_route_does_not_satisfy_a_public_browse_page(
    tmp_path: Path,
) -> None:
    """The owner's record editor is not where a shopper opens an item.

    `App.tsx` carries no `surface` field, so the served-route pass has to exclude
    ops namespaces by path. Without that, `/admin/bikes/:id` would answer "can a
    visitor open a bike" — and it cannot; it is behind the owner console.
    """
    verdict = _verdict(
        tmp_path,
        _real(148),
        brand(148),
        served=["/", "/bikes", "/service/book", "/bikes/v2", "/admin/bikes/:id"],
    )
    assert verdict["codes"] == ["journey_no_detail_route"]


def test_a_detail_route_only_the_router_has_still_counts(tmp_path: Path) -> None:
    """Drop the minted alias and the same app is honestly broken.

    Both halves matter. The check reads the architect, which never carries the
    alias, so without the served table it reports "items cannot be opened" on an
    app whose router opens them; without the check at all, an app that really has
    no detail route ships a grid of cards that go nowhere.
    """
    without_alias = _verdict(
        tmp_path / "a",
        _real(148),
        brand(148),
        served=["/", "/bikes", "/service/book", "/bikes/v2"],
    )
    assert without_alias["codes"] == ["journey_no_detail_route"]
