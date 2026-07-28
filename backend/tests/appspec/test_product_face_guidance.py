"""Product-face guidance handed to the shared AppSpec author.

Request 26 (Jeanne Kassab Art) hard-killed the v2 boundary at Tier 1 closure:
the author invented ``PAGE-OPS-DASHBOARD`` for a fine-art gallery, the closure
heal classified it journey-mandatory, and ``Tier1ClosureHealError`` aborted the
request. v1 survives the same spec because ``product_kind`` reshapes the plan
*downstream*; v2 enforces the AppSpec strictly, so the ops surface is fatal.

These tests pin the deterministic classification that is now surfaced to the
author through ``derived_context.product_face``. It is advisory context only —
it must never affect ``source_sha256`` or semantic source coverage.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.appspec.source import (  # noqa: E402
    capture_derived_context,
    capture_request_source,
)
from app.domain.models.request import Request  # noqa: E402


def _gallery_request() -> Request:
    return Request(
        business_name="Jeanne Kassab Art",
        industry="Fine art gallery · original oil paintings · artist portfolio",
        business_description=(
            "Personal fine art gallery for original paintings — abstract "
            "landscapes and layered oils. A living gallery of latest works — "
            "not a booking SaaS or clinic front desk."
        ),
        target_customers="Collectors, interior designers, and gallery visitors",
        main_problem="No elegant online home to show and sell original paintings",
        desired_outcome="Editorial storefront / portfolio, not an ops ledger",
        email="private@example.com",
    )


def test_gallery_request_is_restricted_to_public_surfaces() -> None:
    face = capture_derived_context(_gallery_request())["derived_context"][
        "product_face"
    ]

    assert face["product_kind"] == "storefront"
    # The whole point: an art gallery may not be given a staff/ops surface.
    assert face["allowed_surfaces"] == ["public"]
    assert "ops" not in face["allowed_surfaces"]

    routes = {page["route"] for page in face["expected_pages"]}
    assert "/" in routes
    assert "/gallery" in routes
    assert "/gallery/:id" in routes
    assert all(page["surface"] == "public" for page in face["expected_pages"])


def test_negated_product_clause_does_not_flip_the_face() -> None:
    """"not a booking SaaS or clinic front desk" must not classify as booking."""

    face = capture_derived_context(_gallery_request())["derived_context"][
        "product_face"
    ]
    assert face["product_kind"] not in {"booking_service", "saas_workspace"}


def test_ops_product_still_receives_an_ops_surface() -> None:
    """The guard must not flatten genuine back-office products to public-only."""

    req = Request(
        business_name="Apex Fund Desk",
        industry="Hedge fund trading operations",
        business_description=(
            "Internal trading desk console — blotter, positions, and P&L for "
            "the fund book. Staff only, no public marketing site."
        ),
        target_customers="Portfolio managers and the trading desk",
        main_problem="Positions and risk live in spreadsheets",
        desired_outcome="One internal console for the desk",
        email="private@example.com",
    )
    face = capture_derived_context(req)["derived_context"]["product_face"]

    assert face["product_kind"] in {"internal_ops", "saas_workspace"}
    assert "ops" in face["allowed_surfaces"]


def test_guidance_is_omitted_without_business_context() -> None:
    req = Request(business_name="", email="private@example.com")
    assert "product_face" not in capture_derived_context(req)["derived_context"]


def test_guidance_never_enters_the_authoritative_source_snapshot() -> None:
    """product_face is advisory — it must not shift source_sha256 or coverage."""

    req = _gallery_request()
    snapshot = capture_request_source(req)
    serialized = repr(snapshot)

    assert "product_face" not in serialized
    assert "allowed_surfaces" not in serialized
    assert "expected_pages" not in serialized
