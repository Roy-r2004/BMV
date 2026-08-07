"""The plan-stage blueprint seed must not duplicate what the plan already serves.

Session 19/20: request 124's owner role — one AI-hub page, so `len(real) < 2`
read it as thin — was handed the full `_storefront_pages()` blueprint while the
guest role already carried PAGE-MENU, a public-catalog. The shipped ROUTE table
stayed clean (`bbe6359`'s architect-stage guard held) but the plan carried
`gallery`/`gallery_detail` pages plus Gallery/Artwork nav links: wasted
slot_fill calls (GalleryPage rejections on 124/125), dead nav labels, and run
111's failed ship at the visual critic. Measured over the 60 stored plans
(`plan_blueprint_census.py`, session-20 evidence): the serve-aware seed drops
the redundant pages on 109/124 entirely and only the redundant `home` on 125,
whose plan genuinely had no catalogue anywhere.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.product_kind import (
    apply_product_kind_to_plan,
    resolve_product_kind_contract,
)
from app.application.ui_catalogue import infer_page_contract

# No booking language on purpose: "we take reservations" classifies
# booking_service, whose blueprint has no gallery — the storefront pages are
# what the residual ships and what these tests must reach.
_TRATTORIA = (
    "Osteria Vinci",
    "A twelve-table Neapolitan trattoria in Boston. Guests browse the weekly "
    "changing menu of wood-fired pizza and house-made pasta, and shop the "
    "short Campanian wine list.",
)

_STAFF_DESK = (
    "Dispatch Desk",
    "A staff-only internal tool our warehouse floor team uses to work the "
    "dispatch queue and shipment records. Not a public website; no customer "
    "ever sees it.",
)


def _storefront_contract():
    contract = resolve_product_kind_contract(*_TRATTORIA)
    # The fixture must reach the storefront blueprint or every assertion below
    # tests nothing (blind spot 4).
    assert contract.kind == "storefront"
    assert any(bp.id == "gallery" for bp in contract.pages)
    return contract


def _hub_page() -> dict:
    return {
        "id": "PAGE-AI-FEATURES",
        "title": "AI Features Hub",
        "surface": "public",
        "skeleton_id": "public-service",
        "purpose": "Showcase the AI-powered features of the product.",
        "sections": [{"name": "Feature deck", "description": "AI features."}],
    }


def _rich_role_with_menu(menu_page: dict) -> dict:
    return {
        "id": "ROLE-GUEST",
        "label": "Guest",
        "pages": [
            {
                "id": "PAGE-HOME",
                "title": "Home",
                "surface": "public",
                "skeleton_id": "public-home",
                "purpose": "Warm brand home for the trattoria.",
            },
            menu_page,
            {
                "id": "PAGE-RESERVATIONS",
                "title": "Reservations",
                "surface": "public",
                "skeleton_id": "public-booking",
                "purpose": "Book a table online.",
            },
        ],
    }


def _explicit_menu_page() -> dict:
    return {
        "id": "PAGE-MENU",
        "title": "Menu",
        "surface": "public",
        "skeleton_id": "public-catalog",
        "purpose": "Weekly changing menu of wood-fired dishes.",
    }


def _prose_only_menu_page() -> dict:
    # No explicit skeleton, and prose that under-resolves: the browse-leaf
    # TOKEN rule is the only thing that can mark this as the catalogue face.
    page = {
        "id": "menu-page",
        "title": "Menu",
        "surface": "public",
        "purpose": "What we are cooking this week.",
    }
    inferred = infer_page_contract(page)["skeleton_id"]
    assert inferred != "public-catalog", inferred  # the token rule must matter
    return page


def _thin_owner_role() -> dict:
    return {"id": "ROLE-OWNER", "label": "Owner", "pages": [_hub_page()]}


def _page_ids(role: dict) -> list[str]:
    return [p["id"] for p in role["pages"]]


def _nav_labels(role: dict) -> list[str]:
    return [
        str(link.get("label") or "")
        for link in (role.get("navigation") or {}).get("links") or []
    ]


def test_thin_role_skips_blueprint_the_plan_already_serves() -> None:
    plan = {"roles": [_rich_role_with_menu(_explicit_menu_page()), _thin_owner_role()]}
    updated = apply_product_kind_to_plan(plan, _storefront_contract())
    owner = updated["roles"][1]
    assert _page_ids(owner) == ["PAGE-AI-FEATURES"]
    assert "Gallery" not in _nav_labels(owner)
    assert "Artwork" not in _nav_labels(owner)


def test_browse_leaf_token_marks_the_catalogue_served() -> None:
    plan = {"roles": [_rich_role_with_menu(_prose_only_menu_page()), _thin_owner_role()]}
    updated = apply_product_kind_to_plan(plan, _storefront_contract())
    owner = updated["roles"][1]
    assert "gallery" not in _page_ids(owner)
    assert "gallery_detail" not in _page_ids(owner)


def test_detail_child_never_rides_without_its_parent() -> None:
    # The plan serves a catalogue but NO detail page anywhere: gallery is
    # skipped as served, and gallery_detail must be skipped WITH it — an
    # Artwork detail attached to a /menu catalogue is exactly the residual.
    plan = {"roles": [_rich_role_with_menu(_explicit_menu_page()), _thin_owner_role()]}
    updated = apply_product_kind_to_plan(plan, _storefront_contract())
    owner = updated["roles"][1]
    assert "gallery_detail" not in _page_ids(owner)


def test_bootstrap_still_seeds_when_nothing_is_served() -> None:
    thin_only = {
        "roles": [
            {
                "id": "ROLE-OWNER",
                "label": "Owner",
                "pages": [_hub_page()],
            }
        ]
    }
    updated = apply_product_kind_to_plan(thin_only, _storefront_contract())
    owner = updated["roles"][0]
    for page_id in ("home", "gallery", "gallery_detail"):
        assert page_id in _page_ids(owner)


def test_empty_role_branch_is_untouched() -> None:
    plan = {
        "roles": [
            _rich_role_with_menu(_explicit_menu_page()),
            {"id": "ROLE-OWNER", "label": "Owner", "pages": []},
        ]
    }
    updated = apply_product_kind_to_plan(plan, _storefront_contract())
    owner = updated["roles"][1]
    # An EMPTY role is the bootstrap branch, deliberately not serve-aware.
    assert _page_ids(owner) == ["home", "gallery", "gallery_detail"]


def test_ops_seeding_is_out_of_scope() -> None:
    contract = resolve_product_kind_contract(*_STAFF_DESK)
    assert contract.kind == "internal_ops"  # fixture must reach the ops pages
    ops_home = contract.pages[0]
    plan = {
        "roles": [
            {
                "id": "ROLE-LEAD",
                "label": "Lead",
                "pages": [
                    {
                        "id": "PAGE-QUEUE",
                        "title": "Dispatch Queue",
                        "surface": "ops",
                        "skeleton_id": ops_home.skeleton_id,
                        "purpose": "Work the queue.",
                    },
                    {
                        "id": "PAGE-RECORDS",
                        "title": "Shipment Records",
                        "surface": "ops",
                        "skeleton_id": "ops-list",
                        "purpose": "Browse records.",
                    },
                ],
            },
            {
                "id": "ROLE-PICKER",
                "label": "Picker",
                # One NON-marketing ops page: thin, but not a landing —
                # otherwise `_repair_ops_home_chrome` rewrites it into the ops
                # home and the seeding assertion below binds nothing (the
                # first sweep proved it: the scope mutation survived).
                "pages": [
                    {
                        "id": "PAGE-PICKLIST",
                        "title": "Pick List",
                        "surface": "ops",
                        "skeleton_id": "ops-list",
                        "path": "/desk/picks",
                        "purpose": "Work the pick queue.",
                    }
                ],
            },
        ]
    }
    updated = apply_product_kind_to_plan(plan, contract)
    picker = updated["roles"][1]
    # The measured residual is the PUBLIC storefront blueprint; ops thin roles
    # keep today's seeding even when another role serves the same skeletons —
    # ROLE-LEAD's queue page serves the ops-home skeleton, and the blueprint
    # home must still be appended here.
    assert ops_home.id in _page_ids(picker)


def test_reapplication_is_idempotent() -> None:
    plan = {"roles": [_rich_role_with_menu(_explicit_menu_page()), _thin_owner_role()]}
    contract = _storefront_contract()
    once = apply_product_kind_to_plan(plan, contract)
    twice = apply_product_kind_to_plan(once, contract)
    assert _page_ids(twice["roles"][1]) == ["PAGE-AI-FEATURES"]
