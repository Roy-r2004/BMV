"""The palette is derived from the business, and every derivation is legible.

Measured before the fix, over the 62 archived workspaces that shipped a
``mock.ts``: **three** distinct ``primary_color`` values, ``#0f766e`` on 58 of
them. Two industry->palette keyword tables disagreed and the coarser one ran
first; ``brand_locked`` then sealed its answer for the rest of the run.

The numbers these tests compare against are written **by hand**, not imported
from the module under test. Session 10 shipped an assertion that read the
constant a mutation would raise, so raising it to 100,000 passed.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.brand_brief import build_brand_brief  # noqa: E402
from app.application.preview_app.brand_palette import (  # noqa: E402
    contrast_ratio,
    derive_palette,
    every_identity,
)
from app.application.services.visual_demo_enrichment import enrich_visual_demo  # noqa: E402
from app.domain.models.request import Request  # noqa: E402

#: Every distinct business name in the archived corpus, which is what the
#: "58 of 62 are teal" measurement was actually taken over. The corpus is 62
#: *workspaces* but only 12 distinct businesses, so 12 is the ceiling any
#: per-business derivation could reach on it — a fact worth having in the test
#: rather than in a commit message.
CORPUS_BUSINESS_NAMES = (
    "Jeanne Kassab Art",
    "Cedar Point Lodge",
    "Northgate Dental Studio",
    "Osteria Vinci",
    "Galerie Aubert",
    "Maison Lelievre",
    "Atelier Vaugirard",
    "Atelier Rousseau",
    "Alder & Ash Ceramics",
    "Maison Vaillant",
    "Atelier Sorel",
    "Jane Art",
)

#: The corpus brief that broke the keyword table: it says the business is *not*
#: a clinic, and the wellness bucket matched the word "clinic" anyway.
GALLERY_DESCRIPTION = (
    "Personal fine art gallery for original paintings — abstract landscapes "
    "and layered oils. A living gallery of latest works — not a booking SaaS "
    "or clinic front desk."
)

TRATTORIA_DESCRIPTION = (
    "A twelve-table Neapolitan trattoria in Boston serving wood-fired pizza, "
    "house-made pasta and a short Campanian wine list."
)


def _rgb(hex_value: str) -> tuple[int, int, int]:
    text = hex_value.lstrip("#")
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def test_the_corpus_businesses_no_longer_share_one_colour() -> None:
    """12 real business names; the shipped corpus gave 3 colours over all 62."""

    primaries = {derive_palette(name, "")["primary"] for name in CORPUS_BUSINESS_NAMES}
    # Hand-written, and deliberately far above the 3 the corpus shipped. It is
    # below 12 because a hash over 12 names may collide, and a test that
    # demanded perfection would be pinning luck rather than the fix.
    assert len(primaries) >= 9, sorted(primaries)


def test_a_business_keeps_its_colour_across_runs() -> None:
    """Requests 92, 95 and 97 are the same restaurant and must be one brand."""

    first = derive_palette("Osteria Vinci", TRATTORIA_DESCRIPTION)
    second = derive_palette("Osteria Vinci", TRATTORIA_DESCRIPTION)
    assert first == second


def test_editing_the_description_does_not_move_the_brand_colour() -> None:
    """The name is the brand. Rewording the pitch is not a rebrand."""

    before = derive_palette("Osteria Vinci", TRATTORIA_DESCRIPTION)
    after = derive_palette("Osteria Vinci", "Completely rewritten brief copy.")
    assert before["primary"] == after["primary"]


def test_a_nameless_brief_still_gets_a_business_specific_colour() -> None:
    one = derive_palette("", GALLERY_DESCRIPTION)
    two = derive_palette(None, TRATTORIA_DESCRIPTION)
    assert one["primary"] != two["primary"]


def test_every_palette_the_derivation_can_produce_is_legible() -> None:
    """No hue may ship an unreadable button, so this asserts over all of them.

    The thresholds are WCAG AA written out by hand. The module solves to higher
    targets; if a future edit lowers a target below the floor this fails, and if
    it lowers the *floor* the assertion below still names the real number.
    """

    checked = 0
    for index, palette in every_identity():
        white = _rgb(palette["surface"])
        background = _rgb(palette["background"])
        assert contrast_ratio(_rgb(palette["primary"]), white) >= 4.5, (index, palette)
        assert contrast_ratio(_rgb(palette["secondary"]), white) >= 7.0, (index, palette)
        assert contrast_ratio(_rgb(palette["text"]), background) >= 7.0, (index, palette)
        assert contrast_ratio(_rgb(palette["muted"]), background) >= 4.5, (index, palette)
        checked += 1
    # 24 hue stops x 2 tones. Written out so shrinking the identity space to one
    # palette — the monoculture, restored — cannot pass this test.
    assert checked == 48


def test_the_identity_space_is_actually_distinct() -> None:
    """A ring that emits one colour 48 times would satisfy every check above."""

    assert len({p["primary"] for _, p in every_identity()}) == 48


def test_the_brief_takes_the_derived_palette_over_the_demo_theme() -> None:
    """The precedence that produced the monoculture, pinned at the consumer.

    ``build_brand_brief`` used to read ``visual_theme.primary_color`` first and
    fall back to a table, so whatever the demo stage had already stamped won.
    """

    brief = build_brand_brief(
        {"visual_theme": {"primary_color": "#0f766e", "secondary_color": "#134e4a"}},
        business_name="Osteria Vinci",
        industry="restaurant",
        business_description=TRATTORIA_DESCRIPTION,
        seed=95,
    )
    assert brief["palette"] == derive_palette("Osteria Vinci", TRATTORIA_DESCRIPTION)
    assert brief["palette"]["primary"] != "#0f766e"


def test_two_businesses_in_one_industry_get_different_brands() -> None:
    """The whole point: a keyword table cannot tell two restaurants apart."""

    one = build_brand_brief(
        {}, business_name="Osteria Vinci", industry="restaurant",
        business_description=TRATTORIA_DESCRIPTION,
    )
    two = build_brand_brief(
        {}, business_name="Cedar Point Lodge", industry="restaurant",
        business_description=TRATTORIA_DESCRIPTION,
    )
    assert one["palette"]["primary"] != two["palette"]["primary"]


def test_the_demo_stage_no_longer_stamps_a_palette() -> None:
    """The producer half: enrichment must leave brand colour alone entirely."""

    req = Request(
        business_name="Osteria Vinci",
        industry="restaurant",
        business_description=TRATTORIA_DESCRIPTION,
        email="rr@example.com",
    )
    demo = enrich_visual_demo({"visual_theme": {}}, req)
    assert not demo["visual_theme"].get("primary_color")
    assert not demo["visual_theme"].get("background_color")


def test_the_industry_bucket_is_still_wrong_and_no_longer_decides_a_colour() -> None:
    """The keyword table survives for *voice*, and it still misreads a negation.

    "not a booking SaaS or clinic front desk" buckets an art gallery as
    ``wellness``. That is left standing deliberately — the scrub that would fix
    it changes zero of 84 stored requests, so shipping it would be an inert
    edit. This test pins what the mistake now costs: prose, not the palette.
    """

    gallery = build_brand_brief(
        {},
        business_name="Jeanne Kassab Art",
        industry="Fine art gallery · original oil paintings · artist portfolio",
        business_description=GALLERY_DESCRIPTION,
    )
    dental = build_brand_brief(
        {},
        business_name="Northgate Dental Studio",
        industry="dental clinic",
        business_description="A three-chair family dental practice in Leeds.",
    )
    assert gallery["industry_bucket"] == dental["industry_bucket"] == "wellness"
    assert gallery["palette"]["primary"] != dental["palette"]["primary"]


if __name__ == "__main__":
    test_the_corpus_businesses_no_longer_share_one_colour()
    test_a_business_keeps_its_colour_across_runs()
    test_editing_the_description_does_not_move_the_brand_colour()
    test_a_nameless_brief_still_gets_a_business_specific_colour()
    test_every_palette_the_derivation_can_produce_is_legible()
    test_the_identity_space_is_actually_distinct()
    test_the_brief_takes_the_derived_palette_over_the_demo_theme()
    test_two_businesses_in_one_industry_get_different_brands()
    test_the_demo_stage_no_longer_stamps_a_palette()
    test_the_industry_bucket_is_still_wrong_and_no_longer_decides_a_colour()
    print("Brand palette tests passed (10 tests)")
