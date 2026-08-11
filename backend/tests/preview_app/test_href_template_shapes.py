"""Template-literal links resolved to route shapes — the lexing half of the walk.

`internal_href_templates` reads a link out of generated TSX and asks the route
table whether anything serves it. It used to split the raw href on "/" *before*
masking `${…}`, so an interpolation containing a slash of its own shattered into
extra segments and produced a shape no route could match.

Requests 146 (Kestrel & Fern Bakehouse) and 148 (Ridgeline Bike Works) were both
withheld on that. Every link on both sites worked; the reader could not parse
them. This module pins the lexer so neither run's href can be mis-read again.

Fixture note, learned the hard way on the placeholder gate: a fixture that omits
the *shape* which distinguishes the fix from the bug passes against the mutation
it was written to kill. Every href below therefore carries the specific hostile
construct named in its docstring — a slash inside the interpolation, a nested
brace, a "#" — and not merely a generic `${id}`.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.capabilities.journey import (  # noqa: E402
    _mask_interpolations,
    _route_matches,
    internal_href_templates,
)

#: Request 146's homepage, verbatim from `/app/data/preview-apps/146`. The
#: `.replace(/\s+/g, '-')` is the whole point: two slashes inside one `${…}`.
BAKERY_HREF = (
    r"href={`/gallery/${encodeURIComponent("
    r"item.title.toLowerCase().replace(/\s+/g, '-'))}`}"
)
#: Request 148's `BikeRangePage.tsx`, verbatim. Same construct, double quotes.
BIKE_HREF = r'href={`/bikes/${b.name.toLowerCase().replace(/\s+/g, "-")}`}'

#: The route tables the two runs actually declared in `App.tsx`.
BAKERY_ROUTES = [
    "/", "/products", "/checkout", "/cakes/order",
    "/admin/dashboard", "/gallery", "/gallery/:id",
]
BIKE_ROUTES = [
    "/", "/bikes", "/service/book", "/bikes/v2", "/service/:id", "/bikes/:id",
]


def test_regex_literal_inside_interpolation_stays_one_segment() -> None:
    """A slash inside `${…}` must not open a segment.

    Split-before-mask yields `/gallery/:_/\\s+/g, '-'))}` — the literal string
    request 146 was withheld on. Asserting the full shape (not `startswith`)
    is what kills it: the bug's output starts with `/gallery/:_` too.
    """
    assert internal_href_templates(BAKERY_HREF) == ["/gallery/:_"]
    assert internal_href_templates(BIKE_HREF) == ["/bikes/:_"]


def test_both_withheld_previews_resolve_against_their_own_route_tables() -> None:
    """The finding itself: neither dead link was dead.

    This is the assertion that would have kept both previews from being
    withheld, so it is pinned against the real declared routes rather than a
    synthetic table.
    """
    (bakery_shape,) = internal_href_templates(BAKERY_HREF)
    (bike_shape,) = internal_href_templates(BIKE_HREF)
    assert _route_matches(bakery_shape, BAKERY_ROUTES)
    assert _route_matches(bike_shape, BIKE_ROUTES)


def test_nested_braces_are_one_interpolation() -> None:
    """An object literal inside `${…}` is one group, not two.

    Kills the `\\$\\{[^}]*\\}` regex the module carried before the depth scan:
    it stops at the inner `}` of `({ id: i.id })`, leaving `))}` behind as
    trailing text. Generated `.map` callbacks return object literals routinely,
    so this is a live shape, not a contrived one.
    """
    href = r"href={`/catalogue/${items.map((i) => ({ id: i.id }))[0].id}`}"
    assert internal_href_templates(href) == ["/catalogue/:_"]


def test_fragment_inside_interpolation_does_not_truncate_the_path() -> None:
    """A "#" inside `${…}` is data, not the start of a fragment.

    Kills stripping the fragment before masking: that ordering cuts the href at
    the quote-internal "#" and loses the trailing segment entirely.
    """
    href = r"""href={`/gallery/${slug.replace("#", "")}/detail`}"""
    assert internal_href_templates(href) == ["/gallery/:_/detail"]


def test_real_fragment_outside_the_interpolation_is_still_stripped() -> None:
    """The other direction — request 46's `/contact#contact-form` rule holds.

    The fragment must trail a *literal* segment. `` `/gallery/${id}#inquire` ``
    does not discriminate: the "#inquire" lands in the same segment as the mask,
    which collapses to ":_" whether the strip ran or not, so dropping the strip
    entirely survives it. Anchoring the fragment to "detail" makes the two
    outcomes different strings.
    """
    assert internal_href_templates(r"href={`/gallery/${item.id}/detail#inquire`}") == [
        "/gallery/:_/detail"
    ]
    assert internal_href_templates(r"href={`/gallery/${item.id}/detail?ref=nav`}") == [
        "/gallery/:_/detail"
    ]


def test_unterminated_interpolation_yields_no_trailing_segments() -> None:
    """A truncated template must not spray its remainder across the shape."""
    assert internal_href_templates(r"href={`/gallery/${item.id`}") == ["/gallery/:_"]


def test_plain_interpolation_keeps_request_44s_fix() -> None:
    """The simple case the shape test was built for still resolves."""
    assert internal_href_templates(r"href={`/artwork/${id}`}") == ["/artwork/:_"]
    assert _route_matches("/artwork/:_", ["/", "/artwork/:id"])


def test_partial_segment_interpolation_collapses_to_a_param() -> None:
    """`item-${id}` is one param segment — a route cannot serve half a literal."""
    assert internal_href_templates(r"href={`/gallery/item-${id}`}") == ["/gallery/:_"]


def test_literal_backtick_href_is_left_to_internal_hrefs() -> None:
    """No `${…}` means this is not a template shape — skipped, not emitted.

    Emitting it here would double-count every literal link in the sweep.
    """
    assert internal_href_templates(r"href={`/gallery`}") == []


def test_mask_replaces_each_group_with_exactly_one_mark() -> None:
    """Two interpolations in one path stay two segments, not one run."""
    masked = _mask_interpolations(r"/a/${x.replace(/\s/g,'')}/b/${y}")
    assert masked == "/a/\x00/b/\x00"
    assert internal_href_templates(r"href={`/a/${x.replace(/\s/g,'')}/b/${y}`}") == [
        "/a/:_/b/:_"
    ]


def test_mask_consumes_a_nested_group_to_its_outer_close() -> None:
    """Depth counting pinned where it lives, on the exact masked string.

    Asserting through `internal_href_templates` cannot pin this: when the mask
    closes early, the leftover text (`))[0].id}`) carries no slash, so it stays
    glued to the mark's own segment and still collapses to ":_" — the shape is
    identical and a broken scanner survives. The masker's output is the only
    place the two behaviours differ, so the contract is asserted there.
    """
    assert _mask_interpolations(r"/x/${a.map((i) => ({ id: i.id }))[0].id}/y") == (
        "/x/\x00/y"
    )
