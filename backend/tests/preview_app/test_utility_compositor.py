"""Unit tests for public-utility JSON → TSX compositor."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.catalogue_contract import (  # noqa: E402
    blocking_contract_errors,
    validate_catalogue_page_content,
)
from app.application.preview_app.utility_compositor import (  # noqa: E402
    compose_utility_page_tsx,
    infer_utility_workspace_type,
    normalize_utility_content,
)


def test_infer_types():
    assert infer_utility_workspace_type("/cart", "Cart") == "cart"
    assert infer_utility_workspace_type("/checkout", "Pay") == "checkout"
    assert infer_utility_workspace_type("/order-tracking", "Track") == "tracking"
    assert infer_utility_workspace_type("/account", "Account") == "account"
    assert infer_utility_workspace_type("/help", "Help") == "generic"


def test_compose_cart_passes_contract():
    route = {
        "path": "/cart",
        "title": "Cart",
        "skeleton_id": "public-utility",
        "section_slots": ["header", "workspace", "summary", "footer"],
        "component_file": "src/pages/CartPage.tsx",
    }
    content = normalize_utility_content(
        {
            "header": {"title": "Bag", "description": "Review items"},
            "workspace": {
                "lines": [
                    {"name": "Laptop X", "detail": "16GB", "qty": 1, "price": 1999},
                ]
            },
            "summary": {
                "title": "Totals",
                "rows": [{"label": "Total", "value": 1999}],
                "primary_cta": {"label": "Checkout", "href": "/checkout"},
            },
            "footer": {"description": "Voltbyte checkout"},
        },
        "cart",
        brand_name="Voltbyte",
        title="Cart",
        path="/cart",
    )
    tsx = compose_utility_page_tsx(
        file_path="src/pages/CartPage.tsx",
        route=route,
        content=content,
        brand_name="Voltbyte",
        workspace_type="cart",
    )
    assert "composed public-utility page" in tsx
    assert "SKELETON_ID" in tsx
    assert "SkeletonComposer" in tsx
    assert "Laptop X" in tsx
    assert "navItems is not defined" not in tsx
    errors = validate_catalogue_page_content(tsx, route)
    assert not blocking_contract_errors(errors), errors


def test_compose_tracking_and_checkout():
    for wtype, path, title in (
        ("checkout", "/checkout", "Checkout"),
        ("tracking", "/order-tracking", "Track"),
        ("account", "/account", "Account"),
    ):
        route = {
            "path": path,
            "title": title,
            "skeleton_id": "public-utility",
            "section_slots": ["header", "workspace", "summary", "footer"]
            if wtype != "account"
            else ["header", "workspace", "footer"],
            "component_file": f"src/pages/{title}Page.tsx",
        }
        tsx = compose_utility_page_tsx(
            file_path=f"src/pages/{title}Page.tsx",
            route=route,
            content={},
            brand_name="Acme",
            workspace_type=wtype,
        )
        errors = validate_catalogue_page_content(tsx, route)
        assert not blocking_contract_errors(errors), (wtype, errors)


def test_bad_ai_payload_normalized():
    normalized = normalize_utility_content(
        {"workspace": {"lines": [{"name": "Only name"}]}},
        "cart",
        brand_name="Brand",
        title="Cart",
    )
    assert normalized["workspace"]["lines"][0]["price"]
    assert normalized["header"]["title"]


if __name__ == "__main__":
    test_infer_types()
    test_compose_cart_passes_contract()
    test_compose_tracking_and_checkout()
    test_bad_ai_payload_normalized()
    print("utility_compositor tests OK")
