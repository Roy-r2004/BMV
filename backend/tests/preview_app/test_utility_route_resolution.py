"""The last route literals: the utility flows and the ops console's own chrome.

After the booking and browse faces were resolved, five literals were left in
emitted-href position and recorded in `test_route_literal_census.ALLOWED` as
debt: `/contact`, `/checkout`, `/order-tracking`, `/invoices`, `/ticket`. Each is
right for an app that happens to use that word and a dead link for every other
one — the same defect, in the flows nobody had looked at yet.

Two resolvers close them, and they are deliberately different strengths:

- `utility_route(architect, kind)` for the public flows, by page kind. It asks
  `infer_utility_workspace_type` — the same function the compositor uses to
  decide what layout a page *gets* — so "which route is the checkout" and "which
  layout does this route get" cannot disagree. An app that calls its contact page
  `/get-in-touch` is answered correctly.
- `declares_path(architect, path)` for the ops header actions. `/invoices` and
  `/ticket` are the accounting and trading blueprints' own page ids, not a
  concept another name stands in for: either the route is seeded or the button
  has nowhere to go, and the button is dropped.

The census allowlist is now `/` and `/ai-features`, and
`test_the_allowlist_has_no_dead_entries` fails if either stops being emitted.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.catalogue_contract.scaffold import (  # noqa: E402
    declares_path,
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.utility_compositor import (  # noqa: E402
    default_utility_content,
    utility_route,
)

#: A storefront that names none of its utility pages the way the literals did.
RENAMED = {
    "routes": [
        {"path": "/", "surface": "public", "skeleton_id": "public-home", "title": "Home"},
        {"path": "/shop", "surface": "public", "skeleton_id": "public-catalog", "title": "Shop"},
        {"path": "/bag", "surface": "public", "skeleton_id": "public-utility", "title": "Your bag"},
        {"path": "/pay", "surface": "public", "skeleton_id": "public-utility", "title": "Payment"},
        {
            "path": "/where-is-it",
            "surface": "public",
            "skeleton_id": "public-utility",
            "title": "Track your order",
        },
        {
            "path": "/get-in-touch",
            "surface": "public",
            "skeleton_id": "public-utility",
            "title": "Get in touch",
        },
    ]
}

#: The same app with no utility pages at all — every flow has to degrade.
BARE = {
    "routes": [
        {"path": "/", "surface": "public", "skeleton_id": "public-home", "title": "Home"},
        {"path": "/shop", "surface": "public", "skeleton_id": "public-catalog", "title": "Shop"},
    ]
}


# --------------------------------------------------------------------------- #
# the resolver


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("cart", "/bag"),
        ("checkout", "/pay"),
        ("tracking", "/where-is-it"),
        ("contact", "/get-in-touch"),
    ],
)
def test_a_utility_face_is_found_under_whatever_it_is_called(
    kind: str, expected: str
) -> None:
    assert utility_route(RENAMED, kind) == expected


@pytest.mark.parametrize("kind", ["cart", "checkout", "tracking", "contact"])
def test_an_app_without_the_face_resolves_to_nothing(kind: str) -> None:
    assert utility_route(BARE, kind) is None
    assert utility_route(None, kind) is None


def test_an_ops_route_is_never_a_public_utility_target() -> None:
    """The owner's billing console is not where a shopper pays."""
    ops_only = {
        "routes": [
            {"path": "/", "surface": "public", "skeleton_id": "public-home"},
            {
                "path": "/admin/billing",
                "surface": "ops",
                "skeleton_id": "ops-list",
                "title": "Billing",
            },
        ]
    }
    assert utility_route(ops_only, "checkout") is None


def test_a_param_route_is_not_a_destination() -> None:
    param = {
        "routes": [
            {"path": "/", "surface": "public", "skeleton_id": "public-home"},
            {
                "path": "/checkout/:step",
                "surface": "public",
                "skeleton_id": "public-utility",
                "title": "Checkout",
            },
        ]
    }
    assert utility_route(param, "checkout") is None


# --------------------------------------------------------------------------- #
# the utility flows


def test_the_flows_hand_off_to_the_pages_this_app_declares() -> None:
    cart = default_utility_content(
        "cart", brand_name="Copperline", title="Your bag", architect=RENAMED
    )
    assert cart["summary"]["primary_cta"]["href"] == "/pay"

    checkout = default_utility_content(
        "checkout", brand_name="Copperline", title="Payment", architect=RENAMED
    )
    assert checkout["summary"]["primary_cta"]["href"] == "/where-is-it"

    done = default_utility_content(
        "confirmation", brand_name="Copperline", title="Thanks", architect=RENAMED
    )
    hrefs = {card["cta_href"] for card in done["workspace"]["cards"]}
    assert "/get-in-touch" in hrefs


def test_a_flow_with_nowhere_to_hand_off_to_goes_home() -> None:
    """`/` is the one route every app has. `/checkout` is not."""
    for kind, key in (("cart", "checkout"), ("checkout", "tracking")):
        content = default_utility_content(
            kind, brand_name="Copperline", title=kind.title(), architect=BARE
        )
        assert content["summary"]["primary_cta"]["href"] == "/", key
    done = default_utility_content(
        "confirmation", brand_name="Copperline", title="Thanks", architect=BARE
    )
    assert {card["cta_href"] for card in done["workspace"]["cards"]} == {"/"}


# --------------------------------------------------------------------------- #
# the ops header


OPS_ROUTE = {
    "path": "/admin/dashboard",
    "title": "Ledger Dashboard",
    "surface": "ops",
    "skeleton_id": "ops-dashboard",
    "section_slots": ["header", "kpis", "chart", "filters", "table", "activity"],
    "component_file": "src/pages/role-owner/AdminDashboardPage.tsx",
}


def test_declares_path_is_exact() -> None:
    architect = {"routes": [{"path": "/invoices/"}, {"path": "/ticket"}]}
    assert declares_path(architect, "/invoices")
    assert declares_path(architect, "/ticket")
    assert not declares_path(architect, "/invoice")
    assert not declares_path(architect, "/tickets")
    assert not declares_path(None, "/invoices")


def test_the_ops_header_keeps_an_action_the_console_serves() -> None:
    architect = {
        "routes": [
            OPS_ROUTE,
            {"path": "/invoices", "surface": "ops", "skeleton_id": "ops-list"},
        ]
    }
    tsx = minimal_catalogue_page_scaffold(
        OPS_ROUTE["component_file"],
        OPS_ROUTE,
        brand_name="Meridian Bookkeeping",
        architect=architect,
    )
    assert 'href: "/invoices"' in tsx
    assert '"AI features"' in tsx


def test_the_ops_header_drops_an_action_with_nowhere_to_go() -> None:
    """A "New invoice" button on a console that has no invoices page.

    An ops console has no marketing nav to recover from a mis-click; the
    catch-all drops the operator on the public home page, out of the workspace
    they were in.
    """
    architect = {"routes": [OPS_ROUTE]}
    tsx = minimal_catalogue_page_scaffold(
        OPS_ROUTE["component_file"],
        OPS_ROUTE,
        brand_name="Meridian Bookkeeping",
        architect=architect,
    )
    assert "/invoices" not in tsx
    assert "New invoice" not in tsx
    # The hub is a pipeline constant and stays.
    assert 'href: "/ai-features"' in tsx


def test_an_in_page_anchor_action_is_always_kept() -> None:
    """`#queue` is on the page — there is no route for it to be missing from."""
    # No accounting or trading words in the brand or the title — `_d` falls to
    # the clinic default, whose second action is the in-page check-in anchor.
    route = {**OPS_ROUTE, "title": "Today", "path": "/staff/today"}
    tsx = minimal_catalogue_page_scaffold(
        route["component_file"], route, brand_name="Harbor Dental", architect={"routes": [route]}
    )
    assert 'href: "#queue"' in tsx
    assert "Check in" in tsx
