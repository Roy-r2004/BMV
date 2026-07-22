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
