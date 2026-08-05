"""Product-kind-first classifier and chrome locks."""
from __future__ import annotations

from app.application.preview_app.product_kind import (
    apply_product_kind_to_architect,
    apply_product_kind_to_plan,
    classify_product_kind,
    resolve_product_kind_contract,
    validate_product_kind_chrome,
)


def test_classifies_accounting_as_saas_workspace() -> None:
    assert (
        classify_product_kind(
            "Fintech / SaaS accounting",
            "invoices expenses bank reconciliation ledger",
        )
        == "saas_workspace"
    )


def test_classifies_trading_as_internal_ops() -> None:
    assert (
        classify_product_kind(
            "Hedge fund trading",
            "internal blotter oms portfolio desk not a saas",
        )
        == "internal_ops"
    )


def test_classifies_restaurant_as_storefront() -> None:
    assert (
        classify_product_kind(
            "Restaurant / cafe",
            "menu ordering dine-in takeout storefront",
        )
        == "storefront"
    )


def test_classifies_fine_art_gallery_as_storefront_not_booking() -> None:
    """Jeanne-shaped briefs negate booking/SaaS — must not become booking_service."""
    brief = (
        "Fine art gallery · original oil paintings · artist portfolio. "
        "Jeanne Kassab Art is a personal fine art gallery for original paintings. "
        "Collectors browse works and message on WhatsApp to inquire or reserve a piece. "
        "Brand-first hero and living gallery — not a booking SaaS or ops dashboard."
    )
    assert classify_product_kind(brief) == "storefront"
    contract = resolve_product_kind_contract(brief)
    assert contract.kind == "storefront"
    assert contract.recipe_id == "warm-service"
    assert contract.home_surface == "public"


def test_accounting_contract_locks_ops_pages() -> None:
    contract = resolve_product_kind_contract(
        "saas accounting invoices expenses bank reconciliation"
    )
    assert contract.kind == "saas_workspace"
    assert contract.subtype == "accounting"
    assert contract.home_skeleton_id == "ops-ledger-home"
    assert contract.recipe_id == "dense-ops-ledger"
    paths = {p.path for p in contract.pages}
    assert "/" in paths
    assert "/invoices" in paths
    assert "/reconciliation" in paths
    by_path = {p.path: p for p in contract.pages}
    assert by_path["/invoices"].skeleton_id == "ops-invoice-board"
    assert by_path["/reconciliation"].skeleton_id == "ops-recon-split"
    assert by_path["/expenses"].skeleton_id == "ops-expense-queue"


def test_trading_contract_locks_desk_pages() -> None:
    contract = resolve_product_kind_contract(
        "hedge fund trading blotter oms internal desk"
    )
    assert contract.kind == "internal_ops"
    assert contract.subtype == "trading"
    assert contract.recipe_id == "dense-ops-floor"
    assert contract.home_skeleton_id == "ops-blotter-desk"
    paths = {p.path for p in contract.pages}
    assert "/blotter" in paths
    assert "/ticket" in paths


def test_plan_kills_marketing_home_for_saas() -> None:
    contract = resolve_product_kind_contract(
        "accounting bookkeeping invoices expenses ledger"
    )
    plan = {
        "roles": [
            {
                "id": "owner",
                "pages": [
                    {
                        "id": "home",
                        "title": "Foresight Engine",
                        "surface": "public",
                        "skeleton_id": "public-home",
                    }
                ],
            }
        ]
    }
    out = apply_product_kind_to_plan(plan, contract)
    assert out["product_kind"] == "saas_workspace"
    assert out["roles"][0]["pages"][0]["surface"] == "ops"
    assert out["roles"][0]["pages"][0]["skeleton_id"] == "ops-ledger-home"
    assert len(out["roles"][0]["pages"]) >= 5


def test_architect_injects_routes_and_blocks_marketing() -> None:
    contract = resolve_product_kind_contract(
        "accounting invoices expenses reconciliation saas"
    )
    architect = {
        "routes": [
            {
                "path": "/",
                "title": "Financial Foresight",
                "surface": "public",
                "layout": "public",
                "skeleton_id": "public-home",
                "component_file": "src/pages/HomePage.tsx",
            }
        ],
        "files_to_generate": [],
    }
    out = apply_product_kind_to_architect(architect, contract)
    home = next(rt for rt in out["routes"] if rt["path"] == "/")
    assert home["surface"] == "ops"
    assert home["skeleton_id"] == "ops-ledger-home"
    assert "/invoices" in {rt["path"] for rt in out["routes"]}
    assert validate_product_kind_chrome(out) == []


def test_validate_flags_public_home_on_ops_kind() -> None:
    issues = validate_product_kind_chrome(
        {
            "product_kind": "saas_workspace",
            "routes": [
                {
                    "path": "/",
                    "surface": "public",
                    "skeleton_id": "public-home",
                }
            ],
        }
    )
    assert "ops_kind_public_home" in issues
    assert "ops_kind_marketing_skeleton" in issues


def test_storefront_plan_keeps_public_home() -> None:
    contract = resolve_product_kind_contract(
        "restaurant cafe menu storefront retail shop"
    )
    assert contract.kind == "storefront"
    plan = apply_product_kind_to_plan(
        {
            "roles": [
                {
                    "id": "guest",
                    "pages": [
                        {
                            "id": "home",
                            "title": "Home",
                            "surface": "public",
                            "skeleton_id": "public-home",
                        }
                    ],
                }
            ]
        },
        contract,
    )
    assert plan["roles"][0]["pages"][0]["skeleton_id"] == "public-home"


def test_llm_inventory_wins_over_kind_blueprint() -> None:
    """Rich brief-driven plans must not be replaced by hardcoded kind pages."""
    contract = resolve_product_kind_contract(
        "clinic dental booking appointment patient front desk"
    )
    assert contract.kind == "booking_service"
    plan = {
        "roles": [
            {
                "id": "patient",
                "label": "Patient",
                "pages": [
                    {
                        "id": "home",
                        "title": "Clinic home",
                        "path": "/",
                        "surface": "public",
                        "skeleton_id": "public-home",
                    },
                    {
                        "id": "services",
                        "title": "Doctors",
                        "path": "/services",
                        "surface": "public",
                        "skeleton_id": "public-service",
                    },
                    {
                        "id": "book",
                        "title": "Book",
                        "path": "/book",
                        "surface": "public",
                        "skeleton_id": "public-booking",
                    },
                ],
            },
            {
                "id": "desk",
                "label": "Front desk",
                "pages": [
                    {
                        "id": "schedule",
                        "title": "Today's schedule",
                        "path": "/desk/schedule",
                        "surface": "ops",
                        "skeleton_id": "ops-list",
                    },
                    {
                        "id": "confirm",
                        "title": "Confirmations",
                        "path": "/desk/confirmations",
                        "surface": "ops",
                        "skeleton_id": "ops-list",
                    },
                ],
            },
        ]
    }
    out = apply_product_kind_to_plan(plan, contract)
    titles = {
        str(p.get("title"))
        for role in out["roles"]
        for p in role.get("pages") or []
    }
    assert "Doctors" in titles
    assert "Book" in titles
    assert "Today's schedule" in titles
    # Kind fallback pages must not wipe brief-driven staff screens.
    assert any(r.get("id") == "desk" for r in out["roles"])


def test_a_hint_matches_only_at_a_word_start() -> None:
    """The filed defect: "oms" inside "Rooms" — a business NAME — picked internal_ops.

    SB-07 from docs/evidence/synthetic-briefs.json, verbatim. The brief has a
    single storefront hit, so it reaches the strong-signal branch where the
    bare substring both cleared `internal >= 1` and passed the "oms" test —
    a fixture with two storefront hits short-circuits earlier and never binds.
    """
    kind = classify_product_kind(
        "Hospitality",
        "The Wilder Rooms",
        "A nine-bedroom guest house on the coast. Guests should be able to look at "
        "each room, check which nights are free, and reserve a stay.",
    )
    assert kind == "storefront"


def test_prefix_stems_still_match_their_inflections() -> None:
    """Left-anchored only: "reconcil"/"bookkeep" are deliberate stems — a full
    word boundary kills them and a one-signal brief falls to the default."""
    assert (
        classify_product_kind("Fintech", "bank reconciliation and bookkeeping for smb")
        == "saas_workspace"
    )


def test_spa_inside_workspace_is_not_a_booking_signal() -> None:
    assert (
        classify_product_kind(
            "Operations", "team workspace with a dispatch queue and admin dashboard"
        )
        != "booking_service"
    )
    # The word itself must keep booking — the boundary is the fix, not a ban.
    assert (
        classify_product_kind("Wellness", "day spa retreat, book appointments and classes")
        == "booking_service"
    )


def test_a_staff_only_desk_is_internal_ops() -> None:
    """SB-17 verbatim: an internal-facing assertion plus ops language is a desk."""
    contract = resolve_product_kind_contract(
        "Facilities Management",
        "Ironmark Facilities Desk",
        "An internal maintenance desk. Building staff raise a job, the coordinator "
        "assigns it from a work queue, engineers update the record when they attend, "
        "and management reviews outstanding jobs weekly. It is a staff tool, not a "
        "public website.",
    )
    assert contract.kind == "internal_ops"
    assert contract.subtype == "ops"


def test_a_back_office_on_the_warehouse_floor_is_internal_ops() -> None:
    """Two plain ops nouns must reach the kind without any assertion phrasing."""
    assert (
        classify_product_kind(
            "Logistics", "The back office desk that runs our warehouse floor"
        )
        == "internal_ops"
    )


def test_an_internal_tool_that_reads_as_software_stays_a_workspace() -> None:
    """SB-11 verbatim: 'internal' names the audience; the product is a workspace."""
    assert (
        classify_product_kind(
            "Software",
            "Tandem Studio Planner",
            "An internal tool our design studio uses to run client projects. The team "
            "signs in and works from a queue of tasks, opens a project record to "
            "update status and notes, and looks at a weekly report of what shipped.",
        )
        == "saas_workspace"
    )


def test_the_internal_assertion_alone_flips_nothing() -> None:
    assert (
        classify_product_kind("General", "A staff tool for taking notes")
        != "internal_ops"
    )


def test_transactional_language_without_the_assertion_stays_a_workspace() -> None:
    assert (
        classify_product_kind(
            "Support", "A queue of support tickets and an admin dashboard"
        )
        == "saas_workspace"
    )


def test_a_driving_school_is_a_booking_service() -> None:
    """SB-10 verbatim: lessons and instructors are booking language, not a gallery."""
    contract = resolve_product_kind_contract(
        "Education",
        "Keystone Driving School",
        "We teach people to drive. Learners should see the lesson packages we sell, "
        "choose an instructor near them, and book their first two-hour lesson.",
    )
    assert contract.kind == "booking_service"
    assert contract.subtype == "booking"


def test_plan_kind_clause_appended_once_and_reapplication_is_idempotent() -> None:
    contract = resolve_product_kind_contract(
        "saas accounting invoices expenses bank reconciliation"
    )
    once = apply_product_kind_to_plan({"design_direction": "Warm, editorial."}, contract)
    direction = once["design_direction"]
    assert direction.count("PRODUCT_KIND=") == 1
    assert contract.design_note in direction
    assert direction.startswith("Warm, editorial.")
    twice = apply_product_kind_to_plan(once, contract)
    assert twice["design_direction"] == direction
    once["design_direction"] = f"  {direction}  "
    assert apply_product_kind_to_plan(once, contract)["design_direction"] == direction


def test_architect_apply_does_not_stack_a_second_same_kind_clause() -> None:
    contract = resolve_product_kind_contract(
        "saas accounting invoices expenses bank reconciliation"
    )
    plan = apply_product_kind_to_plan({"design_direction": "Warm, editorial."}, contract)
    architect = apply_product_kind_to_architect(
        {"design_direction": plan["design_direction"]}, contract, plan=plan
    )
    assert architect["design_direction"].count("PRODUCT_KIND=") == 1
    reapplied = apply_product_kind_to_architect(architect, contract, plan=plan)
    assert reapplied["design_direction"] == architect["design_direction"]


def test_a_flipped_kind_still_appends_its_own_clause() -> None:
    storefront = resolve_product_kind_contract(
        "Restaurant / cafe", "menu ordering dine-in takeout storefront"
    )
    ops = resolve_product_kind_contract(
        "Hedge fund trading", "internal blotter oms portfolio desk not a saas"
    )
    assert storefront.kind != ops.kind
    first = apply_product_kind_to_plan({"design_direction": "Calm."}, storefront)
    flipped = apply_product_kind_to_plan(first, ops)
    direction = flipped["design_direction"]
    assert direction.count("PRODUCT_KIND=") == 2
    assert f"PRODUCT_KIND={ops.kind}/{ops.subtype}" in direction
    assert ops.design_note in direction
    arch = apply_product_kind_to_architect(
        {"design_direction": first["design_direction"]}, ops
    )
    assert f"PRODUCT_KIND={ops.kind}/{ops.subtype}" in arch["design_direction"]


def test_architect_keeps_hybrid_public_and_ops_routes() -> None:
    contract = resolve_product_kind_contract(
        "clinic booking appointment dental"
    )
    architect = {
        "routes": [
            {
                "path": "/",
                "title": "Home",
                "surface": "public",
                "layout": "public",
                "skeleton_id": "public-home",
                "component_file": "src/pages/HomePage.tsx",
            },
            {
                "path": "/services",
                "title": "Doctors",
                "surface": "public",
                "layout": "public",
                "skeleton_id": "public-service",
                "component_file": "src/pages/ServicesPage.tsx",
            },
            {
                "path": "/book",
                "title": "Book",
                "surface": "public",
                "layout": "public",
                "skeleton_id": "public-booking",
                "component_file": "src/pages/BookPage.tsx",
            },
            {
                "path": "/desk",
                "title": "Front desk",
                "surface": "ops",
                "layout": "admin",
                "skeleton_id": "ops-list",
                "component_file": "src/pages/FrontDeskPage.tsx",
                "role_id": "ROLE-DESK",
            },
        ],
        "files_to_generate": [],
    }
    out = apply_product_kind_to_architect(architect, contract)
    paths = {rt["path"] for rt in out["routes"]}
    assert "/desk" in paths
    assert "/book" in paths
    desk = next(rt for rt in out["routes"] if rt["path"] == "/desk")
    assert desk["surface"] == "ops"
    home = next(rt for rt in out["routes"] if rt["path"] == "/")
    assert home["surface"] == "public"
