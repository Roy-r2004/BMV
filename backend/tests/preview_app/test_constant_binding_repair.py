"""R3 (owner-ruled, session 24): constant-binding defects coerce, never rebuild.

The audit's finding: `detail inquire CTA (#inquire)` fired ALONE four times —
ArtworkDetailPage and RoomDetailPage each discarded to the generic scaffold at
attempt 2/2 with two retry asks burned — and the image-pool pair discarded a
HomePage with no retry. Every one of those fields has a compile-time-constant
correct value. `repair_constant_binding_defects` applies the aced8e7 split:
coerce the constant when the fixable set is the WHOLE blocking set, keep
faces/skeleton/imports/slots exactly as strict as before, re-validate, and
give up (existing path unchanged) on anything it cannot prove clean.

Fixtures are the deterministic scaffold itself — valid by construction — with
exactly one constant broken, so a validator or scaffold drift fails loudly
here instead of silently weakening the fixture.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.catalogue_contract import (
    blocking_contract_errors,
    enforce_catalogue_page_contract,
    minimal_catalogue_page_scaffold,
    repair_constant_binding_defects,
    validate_catalogue_page_content,
)

DETAIL_ROUTE = {
    "path": "/gallery/:id",
    "component_file": "src/pages/ArtworkDetailPage.tsx",
    "surface": "public",
    "skeleton_id": "public-detail",
    "title": "Artwork",
    "page_intent": "detail",
    "section_slots": ["hero", "credentials", "inquire", "cta", "footer"],
}

BRAND = "Jeanne Kassab Art"


def _detail_scaffold() -> str:
    tsx = minimal_catalogue_page_scaffold(
        DETAIL_ROUTE["component_file"], dict(DETAIL_ROUTE), brand_name=BRAND
    )
    assert not blocking_contract_errors(
        validate_catalogue_page_content(tsx, DETAIL_ROUTE)
    ), "the scaffold fixture must start clean"
    return tsx


def _break_cta(tsx: str) -> str:
    assert 'href: "#inquire"' in tsx, "scaffold drift: CTA href shape changed"
    broken = tsx.replace('href: "#inquire"', 'href: "#contact"')
    errors = blocking_contract_errors(
        validate_catalogue_page_content(broken, DETAIL_ROUTE)
    )
    # The one broken href fires the primary code plus its two derived codes
    # (the dead-hash check matches the same literal, and the detail face's
    # InquiryPanel allowance is keyed on the inquire anchor).
    assert "detail inquire CTA (#inquire)" in errors, errors
    assert set(errors) <= {
        "detail inquire CTA (#inquire)",
        "dead hash CTA (#details/#contact)",
        "forbidden @/ui component:InquiryPanel",
    }, errors
    return broken


def test_sole_cta_defect_heals_to_the_constant() -> None:
    broken = _break_cta(_detail_scaffold())
    healed, did_heal = repair_constant_binding_defects(broken, DETAIL_ROUTE)
    assert did_heal
    assert "href: '#inquire'" in healed
    assert not blocking_contract_errors(
        validate_catalogue_page_content(healed, DETAIL_ROUTE)
    )


def test_mixed_defects_never_heal() -> None:
    """A strict-set error beside the constant keeps the page on the strict
    path — leniency must not reach faces/skeleton through this door."""

    broken = _break_cta(_detail_scaffold()).replace("items={itemSpecs}", "items={seed.credentials}")
    errors = blocking_contract_errors(
        validate_catalogue_page_content(broken, DETAIL_ROUTE)
    )
    assert len(errors) >= 2  # the CTA code plus strict-set errors
    healed, did_heal = repair_constant_binding_defects(broken, DETAIL_ROUTE)
    assert not did_heal
    assert healed == broken


def test_no_near_miss_shape_no_heal() -> None:
    """A page with NO recognizable CTA href stays on the rebuild path — the
    codemod never invents structure."""

    tsx = _detail_scaffold()
    assert 'href: "#inquire"' in tsx
    broken = tsx.replace('href: "#inquire"', 'href: "/gallery"')
    errors = blocking_contract_errors(
        validate_catalogue_page_content(broken, DETAIL_ROUTE)
    )
    assert "detail inquire CTA (#inquire)" in errors
    healed, did_heal = repair_constant_binding_defects(broken, DETAIL_ROUTE)
    assert not did_heal
    assert healed == broken


def test_image_pool_rebinds_inside_arrays_only() -> None:
    """`images.card/hero` rebind to the item pool inside imageSrc arrays; a
    hero binding outside an array survives untouched."""

    tsx = _detail_scaffold()
    broken = _break_cta(tsx)
    # A legitimate non-array hero read, plus the healable CTA defect.
    marker = "const heroShot = images.hero;\n"
    broken_with_marker = marker + broken
    healed, did_heal = repair_constant_binding_defects(
        broken_with_marker, DETAIL_ROUTE
    )
    assert did_heal
    assert healed.startswith(marker)  # non-array binding untouched


def test_lifestyle_array_rebind_produces_item_pool() -> None:
    from app.application.preview_app.catalogue_contract.repair import (
        _rebind_lifestyle_image_pools,
    )

    src = (
        "const PAINTING_IMAGES = [images.card, images.card2, images.hero];\n"
        "const hero = { imageSrc: [images.hero, images.card3] };\n"
        "const legit = images.hero;\n"
    )
    out = _rebind_lifestyle_image_pools(src)
    assert "PAINTING_IMAGES = [images.item1, images.item2, images.item4]" in out
    assert "imageSrc: [images.item4, images.item3]" in out
    assert "const legit = images.hero;" in out


def test_enforce_returns_the_healed_page_not_the_scaffold() -> None:
    authored_marker = "// authored-by-model: unique-composition-9f2\n"
    broken = authored_marker + _break_cta(_detail_scaffold())
    result, replaced = enforce_catalogue_page_contract(
        DETAIL_ROUTE["component_file"], broken, {"routes": [dict(DETAIL_ROUTE)]},
        brand_name=BRAND,
    )
    assert not replaced
    assert authored_marker in result  # the authored page survived
    assert "href: '#inquire'" in result


def test_partial_fix_never_ships() -> None:
    """The re-validate backstop is its own defense: a codemod that changed the
    page but could not prove it clean returns the original untouched."""

    broken = _break_cta(_detail_scaffold())
    # A second dead hash the count=1 CTA rewrite will not reach.
    assert "secondaryCta" in broken
    broken = broken.replace(
        'href: "/gallery" }} imageSrc={itemImage}',
        'href: "#details" }} imageSrc={itemImage}',
    )
    errors = blocking_contract_errors(
        validate_catalogue_page_content(broken, DETAIL_ROUTE)
    )
    assert "dead hash CTA (#details/#contact)" in errors
    healed, did_heal = repair_constant_binding_defects(broken, DETAIL_ROUTE)
    assert not did_heal
    assert healed == broken


def test_derived_codes_alone_never_trigger_the_heal() -> None:
    """The gate demands a PRIMARY defect — a page whose only blocking error is
    a derived code stays on the strict path (the ruling's scope boundary)."""

    tsx = _detail_scaffold()
    broken = tsx.replace(
        'href: "/gallery" }} imageSrc={itemImage}',
        'href: "#details" }} imageSrc={itemImage}',
    )
    errors = blocking_contract_errors(
        validate_catalogue_page_content(broken, DETAIL_ROUTE)
    )
    assert errors == ["dead hash CTA (#details/#contact)"], errors
    healed, did_heal = repair_constant_binding_defects(broken, DETAIL_ROUTE)
    assert not did_heal
    assert healed == broken


def test_judge_no_longer_rejects_the_sole_cta_defect() -> None:
    """The slot_fill judge's predicate is enforce's verdict — a fill enforce
    now heals must not burn a retry (the two burned asks in the evidence)."""

    from app.application.preview_app.codegen.generate import (
        _slot_fill_contract_rejection,
    )

    broken = _break_cta(_detail_scaffold())
    rejected = _slot_fill_contract_rejection(
        DETAIL_ROUTE["component_file"],
        broken,
        {"routes": [dict(DETAIL_ROUTE)]},
        route=DETAIL_ROUTE,
        brand_name=BRAND,
    )
    assert rejected is None
