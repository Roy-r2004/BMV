"""A booking CTA lands on the route the architect declared, whatever it is named.

The scaffold wrote the literal `/book` into every booking CTA it emitted. That is
right for request 147, whose architect happened to choose that word, and a dead
link for 148 (`/service/book`), 150 (`/hire/reserve`) and 146 (`/cakes/order`) —
the router has no such path, so the catch-all sent every one of those clicks back
to the home page. The same shape ran through `/gallery`.

The fix is to read the route table back: exactly one route per app carries
`skeleton_id == "public-booking"`, and at most one `"public-catalog"`. Resolve by
skeleton, never by name — the naming freedom is the point, and normalising the
architect's names to `/book`/`/gallery` would have deleted the very thing Phase 3
is about.

Every fixture here is a real route table (see `real_route_records`), because the
defect is precisely that hand-written fixtures keep choosing the obvious names.
The load-bearing test is
`test_147_is_unchanged_because_its_architect_chose_the_literal_names`: it runs the
emitters twice, once live and once with the resolvers stubbed back to the
literals they replaced, and asserts the two agree on 147 and disagree on 148 and
150. That is the control and the mutation guard in one — stubbing the resolver to
a constant `"/book"` is exactly the mutation it fails.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.catalogue_contract import scaffold  # noqa: E402
from app.application.preview_app.catalogue_contract.scaffold import (  # noqa: E402
    booking_route,
    catalog_route,
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.safety.mock_data import sync_mock_images  # noqa: E402
from tests.preview_app.real_route_records import (  # noqa: E402
    DECLARED_BOOKING,
    DECLARED_BROWSE,
    REAL_APPS,
    architect,
    brand,
    emit_all,
)

#: Every way a page in this pipeline spells a link target.
_HREF_RE = re.compile(r"""href(?:=|:)\s*\{?\s*['"]([^'"]+)['"]""")


def _hrefs(tsx: str) -> set[str]:
    return set(_HREF_RE.findall(tsx))


def _all_hrefs(pages: dict[str, str]) -> set[str]:
    return {href for tsx in pages.values() for href in _hrefs(tsx)}


# --------------------------------------------------------------------------- #
# the resolver reads the table


@pytest.mark.parametrize("request_id", sorted(REAL_APPS))
def test_the_resolvers_return_what_each_app_declared(request_id: int) -> None:
    assert booking_route(architect(request_id)) == DECLARED_BOOKING[request_id]
    assert catalog_route(architect(request_id)) == DECLARED_BROWSE[request_id]


def test_the_corpus_disagrees_with_the_literals_it_replaced() -> None:
    """Guards the guard: a corpus that all said `/book` would prove nothing."""
    booking = set(DECLARED_BOOKING.values())
    assert booking - {"/book", None}, "no fixture app renamed its booking route"
    assert "/book" in booking, "no fixture app kept the literal as its control"
    assert set(DECLARED_BROWSE.values()) - {"/gallery", None}


def test_the_premise_holds_across_the_corpus() -> None:
    """One booking face per app, at most one catalogue face — the fact resolved on.

    If an architect ever declared two `public-booking` routes the resolver would
    be picking one arbitrarily, and this is where that shows up.
    """
    for request_id, (_, routes) in REAL_APPS.items():
        booking = [r for r in routes if r["skeleton_id"] == "public-booking"]
        catalog = [r for r in routes if r["skeleton_id"] == "public-catalog"]
        assert len(booking) <= 1, f"{request_id} declares {len(booking)} booking faces"
        assert len(catalog) <= 1, f"{request_id} declares {len(catalog)} catalogue faces"


def test_an_ops_booking_console_is_not_a_public_cta_target() -> None:
    """A public button must never hand the visitor the owner's console.

    Nothing in the corpus has this shape, so it is stated here rather than found:
    an ops-surface route is not somewhere a storefront CTA may point, even when it
    is the only thing wearing the booking skeleton.
    """
    ops_only = {
        "routes": [
            {"path": "/", "surface": "public", "skeleton_id": "public-home"},
            {"path": "/staff/book", "surface": "ops", "skeleton_id": "public-booking"},
        ]
    }
    assert booking_route(ops_only) is None


def test_a_param_route_is_a_shape_not_a_destination() -> None:
    """`/book/:step` is a template; a button cannot point at it."""
    param_only = {
        "routes": [
            {"path": "/", "surface": "public", "skeleton_id": "public-home"},
            {"path": "/reserve/:step", "surface": "public", "skeleton_id": "public-booking"},
        ]
    }
    assert booking_route(param_only) is None


# --------------------------------------------------------------------------- #
# the emitters use it


@pytest.mark.parametrize("request_id", [146, 148, 150])
def test_a_renamed_booking_route_is_the_one_every_page_links_to(request_id: int) -> None:
    """148 → `/service/book`, 150 → `/hire/reserve`, 146 → `/cakes/order`."""
    declared = DECLARED_BOOKING[request_id]
    hrefs = _all_hrefs(emit_all(request_id))
    assert declared in hrefs, f"{request_id} never links its declared booking route"
    assert "/book" not in hrefs, f"{request_id} still emits the literal"


def test_151_declares_no_booking_page_and_none_is_invented() -> None:
    """An ops console with no public face. `/book` here is pure fabrication."""
    hrefs = _all_hrefs(emit_all(151))
    assert "/book" not in hrefs
    assert not any(href.startswith("/book") for href in hrefs)


def test_a_service_listing_with_no_booking_route_asks_in_page_instead() -> None:
    """A missing button beats a dead one.

    150's table with its booking page removed: the listing's funnel has nowhere
    to hand off to, so the CTA becomes an in-page ask and the cards hold on the
    grid anchor. Deleting the fallback — emitting `/book` when the resolver
    returns None — fails here.
    """
    contract = architect(150)
    contract["routes"] = [r for r in contract["routes"] if r["path"] != "/hire/reserve"]
    route = next(r for r in contract["routes"] if r["path"] == "/services")
    tsx = minimal_catalogue_page_scaffold(
        str(route["component_file"]), route, brand_name=brand(150), architect=contract
    )
    hrefs = _hrefs(tsx)
    assert "/book" not in hrefs and "/hire/reserve" not in hrefs
    assert "#inquire" in hrefs, "the CTA must become an in-page ask"
    assert "#catalog" in hrefs, "the cards must hold on this page's own grid"


def test_a_composed_hero_with_no_booking_route_asks_in_page_instead() -> None:
    """Same rule on the other emitter — `_non_home_hero_ctas`, not the listing face.

    148's service page demoted to `public-service`, which is the thin-contract
    shape: booking wording, no booking face anywhere in the table.
    """
    contract = architect(148)
    route = next(r for r in contract["routes"] if r["path"] == "/service/book")
    route["skeleton_id"] = "public-service"
    route["page_intent"] = "home"
    tsx = minimal_catalogue_page_scaffold(
        str(route["component_file"]), route, brand_name=brand(148), architect=contract
    )
    hrefs = _hrefs(tsx)
    assert "/book" not in hrefs
    assert "#inquire" in hrefs


@pytest.mark.parametrize("request_id", [148, 150])
def test_a_renamed_catalogue_is_where_view_collection_goes(request_id: int) -> None:
    """The `/gallery` half of the same defect.

    A storefront hero emits "View collection" → the literal `/gallery`. 148 calls
    its browse face `/bikes` and 150 calls it `/catalogue`, so on both the one CTA
    the browse journey exists to offer pointed at nothing. Exercised through
    `_safe_slot_jsx` because that is the entry point `repair.py` uses when it
    re-injects a hero into a page that lost one.
    """
    jsx = scaffold._safe_slot_jsx(
        "hero",
        brand(request_id),
        "Our collection",
        skeleton_id="public-catalog",
        architect=architect(request_id),
    )
    assert "View collection" in jsx
    assert DECLARED_BROWSE[request_id] in _hrefs(jsx)
    assert "/gallery" not in _hrefs(jsx)


# --------------------------------------------------------------------------- #
# the control, and the mutation it kills


def _stub_literals(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pre-fix emitters: both resolvers replaced by the constants they wrote."""
    monkeypatch.setattr(scaffold, "booking_route", lambda architect: "/book")
    monkeypatch.setattr(scaffold, "catalog_route", lambda architect: "/gallery")


def test_147_is_unchanged_because_its_architect_chose_the_literal_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The free control: resolved and literal agree byte for byte on 147.

    147's architect named its booking page `/book`, so this whole change must be
    invisible on it. Comparing against the stubbed emitters rather than a stored
    snapshot keeps the control honest without pinning unrelated scaffold copy.
    """
    live = emit_all(147)
    _stub_literals(monkeypatch)
    literal = emit_all(147)
    assert live == literal


@pytest.mark.parametrize("request_id", [146, 148, 150])
def test_the_control_is_not_vacuous(
    request_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """And on the three renamed apps the two must differ — else nothing was fixed.

    This is the mutation "stub the resolver to the constant `/book`": it passes
    the test above and fails here, on every app whose architect picked its own
    name. `/hire/reserve` and `/cakes/order` also kill "match the path instead of
    the skeleton", which `/service/book` alone would survive.
    """
    live = emit_all(request_id)
    _stub_literals(monkeypatch)
    literal = emit_all(request_id)
    assert live != literal
    changed = {rel for rel in live if live[rel] != literal[rel]}
    assert changed, "the emitters ignored the resolver entirely"
    for rel in changed:
        assert DECLARED_BOOKING[request_id] in live[rel] or (
            (DECLARED_BROWSE[request_id] or "\0") in live[rel]
        )


# --------------------------------------------------------------------------- #
# the safety net that would have undone all of it


def _workspace_with_dead_cta(tmp_path: Path) -> Path:
    (tmp_path / "src/data").mkdir(parents=True)
    (tmp_path / "src/data/mock.ts").write_text(
        "export const images = {\n  hero: 'https://example.com/a.jpg',\n};\n"
        "export const seed = {\n"
        "  cta: { primaryHref: '/book-appointment' },\n"
        "};\n",
        encoding="utf-8",
    )
    return tmp_path


def test_sync_mock_images_rewrites_dead_ctas_to_the_declared_route(
    tmp_path: Path,
) -> None:
    """The trap that would have quietly undone the fix.

    `sync_mock_images` is the last guard to touch a page before the build, and it
    rewrote every dead booking href to the literal `/book`. On a `/hire/reserve`
    app that re-manufactures the dead link the scaffold had just resolved away.
    """
    workspace = _workspace_with_dead_cta(tmp_path)
    sync_mock_images(
        workspace,
        {"hero": "https://images.unsplash.com/photo-1541961017774-22349e4a1262?w=1400"},
        architect=architect(150),
    )
    text = (workspace / "src/data/mock.ts").read_text(encoding="utf-8")
    assert "/book-appointment" not in text
    assert "/hire/reserve" in text
    assert '"/book"' not in text and "'/book'" not in text


def test_sync_mock_images_invents_no_booking_route_when_none_is_declared(
    tmp_path: Path,
) -> None:
    """151 has no booking page — the dead href stays dead rather than moving to `/book`.

    Deleting the `if book_target:` guard fails here.
    """
    workspace = _workspace_with_dead_cta(tmp_path)
    sync_mock_images(
        workspace,
        {"hero": "https://images.unsplash.com/photo-1541961017774-22349e4a1262?w=1400"},
        architect=architect(151),
    )
    text = (workspace / "src/data/mock.ts").read_text(encoding="utf-8")
    assert "'/book'" not in text and '"/book"' not in text
