r""""Business" is not a business's name, and only "Brand" was ever treated that way.

Request 156's `ServiceBookingPage.tsx` shipped to a bike shop reading

    <MarketingHero brandName={"Business"} …
    <CTABand heading={seed.cta?.heading ?? "Ready for Business?"}
             description={… ?? "Tell Business what you need — clear options, real next steps."} />
    <BrandFooter description={… ?? "Business — clear choices and real bookings."} />

`mock.ts` had the right name in it the whole time (`brand.name = "Ridgeline Bike
Works"`). The chain that put "Business" on the page:

1. `page_experience.design_manifest` returns `brand_name: plan.get("concept_name",
   "Business")` — a placeholder minted when the plan has no concept name.
2. `_brand_name_from_manifest` read `manifest["brand_name"]` by hand and returned
   it, while the placeholder filter one module over rejected only `Brand`.
3. `slot_fill` took an HTTP 408 on that one page, so the scaffold's brand-bound
   fallbacks were never overwritten and went to the customer verbatim.

Fixed at every step: the placeholder set is shared and casefolded, the manifest
stops minting one, the manifest is stamped with the name the pipeline actually
resolved, and the page scrub handles the copy forms and not just the attribute.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.brand_brief import (  # noqa: E402
    PREVIEW_BRAND_PLACEHOLDERS,
    resolve_preview_brand_name,
)
from app.application.preview_app.codegen.shared import (  # noqa: E402
    _brand_name_from_manifest,
)
from app.application.preview_app.safety.mock_data import (  # noqa: E402
    scrub_placeholder_brand,
)

BRAND = "Ridgeline Bike Works"

#: The page as request 156 shipped it, trimmed to the four lines that carry a
#: brand. Every one of them was written by `minimal_catalogue_page_scaffold`.
SHIPPED_156 = (
    '      <MarketingHero brandName={"Business"} headline={"Service Booking Page"} />\n'
    '      <CTABand heading={seed.cta?.heading ?? "Ready for Business?"} '
    'description={seed.cta?.description ?? "Tell Business what you need — clear '
    'options, real next steps."} />\n'
    '      <BrandFooter brandName={"Business"} description={seed.footer?.description '
    '?? "Business — clear choices and real bookings."} />\n'
    '    <PublicShell brandName={"Business"}>\n'
)


# --------------------------------------------------------------------------- #
# the placeholder set


@pytest.mark.parametrize("placeholder", sorted(PREVIEW_BRAND_PLACEHOLDERS))
def test_no_placeholder_is_ever_resolved_as_a_name(placeholder: str) -> None:
    for spelling in (placeholder, placeholder.title(), placeholder.upper()):
        assert resolve_preview_brand_name(brand_name=spelling, fallback=False) is None


def test_a_real_name_still_wins_from_anywhere_in_the_chain() -> None:
    assert (
        resolve_preview_brand_name(
            brand_name="Business", business_name=BRAND, fallback=False
        )
        == BRAND
    )
    assert (
        resolve_preview_brand_name(manifest={"brand_name": BRAND}, fallback=False)
        == BRAND
    )


def test_a_name_that_merely_contains_a_placeholder_word_survives() -> None:
    """`Business` is a placeholder; `Copperline Business Supplies` is a business."""
    for name in ("Copperline Business Supplies", "The Brand Studio", "Company & Sons"):
        assert resolve_preview_brand_name(brand_name=name, fallback=False) == name


# --------------------------------------------------------------------------- #
# the manifest reader


def test_the_manifest_reader_refuses_a_placeholder() -> None:
    """Step 2 of the chain: this returned `"Business"` verbatim."""
    assert _brand_name_from_manifest({"brand_name": "Business"}) == "Brand"
    assert _brand_name_from_manifest({"brand": {"name": "Business"}}) == "Brand"
    assert _brand_name_from_manifest({"brand": {"name": BRAND}}) == BRAND
    assert _brand_name_from_manifest({"brand_name": BRAND}) == BRAND


def test_the_design_manifest_no_longer_mints_one() -> None:
    """Step 1: the source of the word.

    `design_manifest` is reached through a model call, so the fallback branch is
    exercised directly — it is the branch that ran on 156.
    """
    from app.application.services import page_experience

    source = Path(page_experience.__file__).read_text(encoding="utf-8")
    assert '"brand_name": plan.get("concept_name", "Business")' not in source
    assert '"brand_name": plan.get("concept_name") or ""' in source


# --------------------------------------------------------------------------- #
# the scrub


def test_the_scrub_puts_the_real_brand_back_into_the_copy() -> None:
    """Step 3's blast radius: the attribute *and* the three sentences."""
    scrubbed, count = scrub_placeholder_brand(SHIPPED_156, BRAND)

    # Three `brandName` attributes and the three sentences of copy.
    assert count == 6, scrubbed
    assert "Business" not in scrubbed
    assert f'brandName={{"{BRAND}"}}' in scrubbed
    assert f"Ready for {BRAND}?" in scrubbed
    assert f"Tell {BRAND} what you need" in scrubbed
    assert f"{BRAND} — clear choices and real bookings." in scrubbed


def test_the_scrub_leaves_ordinary_prose_about_businesses_alone() -> None:
    """The reason this is phrase-bounded and not a `\\bBusiness\\b` sweep.

    A word-boundary sweep over a page rewrites the copy it is meant to protect,
    which is a worse defect than the one it fixes.
    """
    prose = (
        '<p>Business hours: 9-5. We serve small business owners and every '
        'company on the high street.</p>\n'
        "const businessDescription = 'A family business since 1994';\n"
    )
    scrubbed, count = scrub_placeholder_brand(prose, BRAND)
    assert count == 0
    assert scrubbed == prose


def test_the_scrub_refuses_to_run_without_a_real_brand() -> None:
    """Swapping one placeholder for another is not a repair."""
    for brand in ("", "   ", "Brand", "Business"):
        scrubbed, count = scrub_placeholder_brand(SHIPPED_156, brand)
        assert count == 0
        assert scrubbed == SHIPPED_156


def test_the_scrub_is_idempotent() -> None:
    once, first = scrub_placeholder_brand(SHIPPED_156, BRAND)
    twice, second = scrub_placeholder_brand(once, BRAND)
    assert second == 0
    assert twice == once
    assert first > 0
