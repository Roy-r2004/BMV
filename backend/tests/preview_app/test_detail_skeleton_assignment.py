"""A page is a detail page because of its route, not because of its prose.

`_infer_skeleton_id` matched the bare substring "detail" anywhere in a page's id,
title, page_type, purpose, layout, path or role labels. Ordinary English put
About, Contact, booking-confirmation and treatment-plan pages under the
`public-detail` contract — "contact details.", "a page detailing our story",
"detailed room information" — and that contract
(`catalogue_contract/validate.py:227-244`) *requires* a painting-first hero, an
`itemSpecs` binding and an `#inquire` CTA. It was written against request 50, a
fine-art gallery. So a dentist's About page failed three assertions about
paintings and had its fill thrown away for a deterministic scaffold, which is
what two of session 11's four captured `slot_fill` rejections are.

Measured over the 399 stored public routes before this shipped: **95 reached the
detail branch, 94 of them on the bare word alone, and 35 of those named no item
in their path at all.**
"""
from __future__ import annotations

from app.application.ui_catalogue import infer_page_contract


def _skeleton(**page) -> str:
    page.setdefault("surface", "public")
    return infer_page_contract(page)["skeleton_id"]


# --- prose is not a page kind -------------------------------------------------


def test_an_about_page_that_details_a_story_is_not_an_item_page() -> None:
    """Request 79's `/about`: "Page detailing the story and ethos of the lodge"."""
    assert (
        _skeleton(
            path="/about",
            title="About",
            purpose="Page detailing the story and ethos of Cedar Point Lodge.",
        )
        != "public-detail"
    )


def test_a_contact_page_with_contact_details_is_not_an_item_page() -> None:
    """Request 76's `/contact`: "guest inquiries and lodge contact details."."""
    assert (
        _skeleton(
            path="/contact",
            title="Contact Us",
            purpose="A page with a contact form for guest inquiries and lodge contact details.",
        )
        != "public-detail"
    )


def test_a_treatment_plan_page_is_not_an_item_page() -> None:
    """Request 81's `/patient/treatment-plan`: "a detailed plan"."""
    assert (
        _skeleton(
            path="/patient/treatment-plan",
            title="Treatment Plan",
            purpose="Shows the patient a detailed plan with costs and stages.",
        )
        != "public-detail"
    )


def test_a_listing_described_as_detailed_stays_a_listing() -> None:
    """Request 96's `/rooms`: "detailed room information" — a catalogue, not an item."""
    assert (
        _skeleton(
            path="/rooms",
            title="Rooms",
            purpose="Browse the room collection with detailed information for each type.",
        )
        == "public-catalog"
    )


# --- the route is ------------------------------------------------------------


def test_a_parameterized_path_is_an_item_page_with_no_prose_at_all() -> None:
    assert _skeleton(path="/rooms/:roomId", title="Room") == "public-detail"


def test_a_bracketed_parameter_is_an_item_page_too() -> None:
    assert _skeleton(path="/works/[slug]", title="Work") == "public-detail"


def test_a_parameterized_listing_child_is_an_item_and_not_a_catalogue() -> None:
    """Request 38's `/collection/:slug` was read as a catalogue by its own name."""
    assert (
        _skeleton(
            path="/collection/:slug",
            title="Collection piece",
            purpose="One work from the collection.",
        )
        == "public-detail"
    )


def test_a_parameter_in_the_middle_of_a_path_is_a_step_not_an_item() -> None:
    """Request 45's `/artwork/:artworkId/inquire` is a form about an item, not the item."""
    assert (
        _skeleton(
            path="/artwork/:artworkId/inquire",
            title="Inquire",
            purpose="Send an inquiry about this work with your contact details.",
        )
        != "public-detail"
    )


def test_a_named_service_child_path_is_still_an_item_page() -> None:
    assert (
        _skeleton(path="/services/deep-cleaning", title="Deep cleaning")
        == "public-detail"
    )


def test_an_unambiguous_phrase_still_names_an_item_page() -> None:
    assert (
        _skeleton(
            path="/piece",
            title="Piece",
            purpose="A single product page with specifications and an inquiry CTA.",
        )
        == "public-detail"
    )


# --- the boundary: nothing above this branch moved ----------------------------


def test_a_parameterized_booking_step_is_still_a_booking_page() -> None:
    """The booking test runs first and must keep winning."""
    assert (
        _skeleton(
            path="/book/:step",
            title="Book",
            purpose="Guests book a table for a chosen date.",
        )
        == "public-booking"
    )


def test_a_parameterized_account_page_is_still_a_utility_page() -> None:
    assert (
        _skeleton(
            path="/account/:tab",
            title="Account",
            purpose="Manage your account and saved cards.",
        )
        == "public-utility"
    )


def test_an_ops_route_is_untouched_by_the_public_rule() -> None:
    assert (
        _skeleton(
            path="/admin/bookings/:id",
            title="Booking",
            surface="ops",
            purpose="View and manage details for a specific booking.",
        )
        == "ops-detail"
    )
