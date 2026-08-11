"""A route literal may define a route or describe a path shape. It may never *reference* one.

That is the whole rule. `product_kind`'s blueprints define routes; `_is_ops_path`
and `_LISTING_BASE_RE` describe path shapes; both are fine. What is not fine is an
emitter writing `href: "/book"` or `` href: `/gallery/${id}` `` into a page, because
the page it writes belongs to a business whose architect named those routes, and
requests 148 and 150 named them `/service/book`, `/bikes`, `/hire/reserve` and
`/catalogue`. Every one of those hrefs fell through `path="*"` to the home page.

The behavioural tests for that live in `test_booking_route_resolution.py` and
below. This module is the thing that keeps the count at zero afterwards: it reads
the emitters' own source and fails on any route literal in emitted-href position
that is not on a short allowlist with a reason next to it. Deleting every
behavioural test in the tree would not let the literal back in.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.catalogue_contract.repair import (  # noqa: E402
    repair_missing_catalogue_slots,
)
from app.application.preview_app.catalogue_contract.scaffold import (  # noqa: E402
    catalog_base_from_path,
    minimal_catalogue_page_scaffold,
)
from app.application.services.ai_features import PAGE_AI_HUB_ROUTE  # noqa: E402
from tests.preview_app.real_route_records import (  # noqa: E402
    DECLARED_BROWSE,
    architect,
    brand,
    emit_all,
)

#: The emitters. Anything that writes TSX a browser will click through.
SCANNED = (
    "app/application/preview_app/catalogue_contract/scaffold.py",
    "app/application/preview_app/utility_compositor.py",
)

#: `href: "/x"`, `href="/x"`, `href={ "/x" }`, `` href: `/x/${id}` ``, and the
#: `?? "/x"` fallback form the `cta` slot uses. Deliberately narrow: it looks for
#: a link *target*, not for every string in the file that starts with a slash, so
#: route definitions and path-shape vocabularies do not trip it.
EMITTED_HREF_RE = re.compile(
    r"""href["']?\s*[:=]\s*(?:\{\s*)?(?:[^,}\n"'`]*?\?\?\s*)?["'`](/[^"'`\s]*)"""
)

#: Route literals allowed to stay, each with the reason it is not a reference to
#: an architect-named route. Anything not here fails the census — resolve it from
#: the route table (`booking_route`, `catalog_route`, `catalog_base_from_path`)
#: or add it here with a sentence saying why it cannot be.
ALLOWED: dict[str, str] = {
    # The root is not a name an architect picks. Every route table has it, and
    # `architect_normalize._PINNED_PATHS` keeps it through normalization.
    "/": "the home route, pinned by the pipeline and present in every app",
    # Asserted below against the pipeline's own constant rather than derived: the
    # AI hub is minted by `ai_feature_surfaces.ensure_ai_hub_route` at a fixed
    # path and pinned through normalization, so it is a pipeline constant, not a
    # business's naming choice.
    "/ai-features": "pipeline constant — see test_the_ai_hub_path_is_a_pipeline_constant",
}
# The four utility/ops paths that were listed here as debt — `/contact`,
# `/checkout`, `/order-tracking`, `/invoices`, `/ticket` — are gone.
# `utility_route` resolves the first three by page kind and `declares_path`
# gates the ops header actions, so the list is down to the two literals that
# genuinely cannot be an architect's naming choice.


def _literals(path: Path) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for match in EMITTED_HREF_RE.finditer(line):
            # `/gallery/${id}` is a reference to `/gallery`; the fragment on
            # `/contact#inquire` is an anchor, not a route.
            literal = match.group(1).split("$")[0].split("#")[0].rstrip("/") or "/"
            found.append((number, literal))
    return found


def test_no_emitter_references_a_route_by_literal() -> None:
    offenders = []
    for relative in SCANNED:
        path = BACKEND_DIR / relative
        for number, literal in _literals(path):
            if literal not in ALLOWED:
                offenders.append(f"{relative}:{number}: {literal}")
    assert not offenders, (
        "route literals in emitted-href position:\n  "
        + "\n  ".join(offenders)
        + "\n\nA literal may define a route or describe a path shape; it may "
        "never reference one. Resolve it from the architect's route table "
        "(booking_route / catalog_route / catalog_base_from_path), or add it to "
        "ALLOWED with a sentence saying why it cannot be."
    )


def test_the_census_is_actually_reading_the_emitters() -> None:
    """Guards the guard: a regex that matched nothing would pass forever."""
    for relative in SCANNED:
        found = _literals(BACKEND_DIR / relative)
        assert found, f"{relative}: the census pattern found no hrefs at all"


@pytest.mark.parametrize("reintroduced", ["/book", "/gallery", "/bikes"])
def test_the_census_catches_a_literal_put_back(reintroduced: str) -> None:
    """The mutation this module exists for, run against a synthetic source.

    Reverting either slot to `` href: `/gallery/${…}` `` must fail the census on
    its own, with every behavioural test in the tree deleted.
    """
    source = (
        "        \"showcase\": (\n"
        "            'items={(seed.items ?? []).map((item, index) => ({ '\n"
        f"            'href: `{reintroduced}/${{encodeURIComponent(String(item.id))}}` '\n"
        "        ),\n"
    )
    literals = [
        match.group(1).split("$")[0].split("#")[0].rstrip("/")
        for match in EMITTED_HREF_RE.finditer(source)
    ]
    assert literals == [reintroduced]
    assert reintroduced not in ALLOWED


def test_the_ai_hub_path_is_a_pipeline_constant() -> None:
    """Assert, do not derive — the one allowlisted path that is genuinely fixed.

    `/ai-features` is minted by the pipeline, not chosen by an architect. If that
    constant ever moves, the scaffold's `header` slot has to move with it, and
    this is what says so.
    """
    assert PAGE_AI_HUB_ROUTE == "/ai-features"

    from app.application.preview_app.pipeline.architect_normalize import _PINNED_PATHS

    assert PAGE_AI_HUB_ROUTE in _PINNED_PATHS


def test_every_allowlist_entry_carries_a_reason() -> None:
    for literal, reason in ALLOWED.items():
        assert reason.strip(), f"{literal} is allowlisted with no justification"


def test_the_allowlist_has_no_dead_entries() -> None:
    """An entry nobody emits any more is a licence left lying around."""
    emitted = {
        literal
        for relative in SCANNED
        for _, literal in _literals(BACKEND_DIR / relative)
    }
    assert set(ALLOWED) <= emitted, f"stale allowlist entries: {set(ALLOWED) - emitted}"


# --------------------------------------------------------------------------- #
# the behaviour the census is protecting


@pytest.mark.parametrize("request_id", [146, 148, 150])
def test_card_links_hang_off_the_declared_browse_route(request_id: int) -> None:
    """148 → `/bikes/:_`, 150 → `/catalogue/:_`, 146 → `/gallery/:_`.

    146 is the control on this half: its architect *did* call the browse face
    `/gallery`, so the literal and the resolved answer agree and its cards must
    not move.
    """
    browse = DECLARED_BROWSE[request_id]
    pages = emit_all(request_id)
    card_bases = {
        match.group(1).rstrip("/")
        for tsx in pages.values()
        for match in re.finditer(r"href: `(/[^$`]*)\$\{", tsx)
    }
    assert card_bases, f"{request_id} emitted no card links at all"
    assert card_bases == {browse}, f"{request_id} cards link into {card_bases}"


def test_a_repaired_listing_inherits_the_derived_base() -> None:
    """The repair path used to fall back to the `/gallery` default.

    `repair.py` injects missing slots through `_safe_slot_jsx` and passed no
    `detail_base`, so a page the repair loop touched came out with card links the
    generator would never have written — visible only on pages that failed
    validation once, which is the hardest place to see it.
    """
    contract = architect(148)
    route = next(r for r in contract["routes"] if r["path"] == "/")
    lean = {**route, "section_slots": [s for s in route["section_slots"] if s != "showcase"]}
    content = minimal_catalogue_page_scaffold(
        str(route["component_file"]), lean, brand_name=brand(148), architect=contract
    )
    assert "ProductShowcase" not in content

    repaired, healed = repair_missing_catalogue_slots(
        content, route, brand_name=brand(148), architect=contract
    )
    assert healed, "the showcase slot was not injected"
    assert "href: `/bikes/${" in repaired
    assert "/gallery" not in repaired


def test_a_page_with_no_path_of_its_own_reads_the_table() -> None:
    """The home page's card grid has nothing to derive from but the route table.

    `catalog_base_from_path("")` returned the `/gallery` default outright, which
    is how 148's home page shipped a grid of cards into a route it does not have.
    """
    assert catalog_base_from_path("", architect(148)) == "/bikes"
    assert catalog_base_from_path("/", architect(150)) == "/catalogue"
    # No architect at all: nothing to read, so the default stands.
    assert catalog_base_from_path("") == "/gallery"
    # A page whose own base *is* declared still wins — request 44's fix.
    assert catalog_base_from_path("/gallery/:id", architect(146)) == "/gallery"
