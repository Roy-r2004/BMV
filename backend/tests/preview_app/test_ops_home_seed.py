"""Run 135's ops-home seed gap: the staff home exists BEFORE codegen.

The dispatch-desk run's spec was ACCEPTED (rev 2, internal_ops/ops) with all
three pages on their own spec routes — `/queue` (primary), `/records`,
`/ai-features` — and nothing at `/`. Under enforced appspec the canonical
worklist is substantive, so the blueprint injection that gives a thin
architect its home never fires; `validate_product_kind_chrome` honestly
refused the ship (`ops_kind_missing_home:architect.routes`) after codegen had
spent the run, and past-deadline the AI repair was refused. The fix re-paths
the seed's own ops home to `/` inside `lock_chrome_on_architecture_seed` —
never inventing a page, never touching non-ops kinds, never electing the AI
hub, and keeping role defaultPaths in step.
"""
from __future__ import annotations

import copy

from app.application.preview_app.product_kind import (
    lock_chrome_on_architecture_seed,
    resolve_product_kind_contract,
    validate_product_kind_chrome,
)

_OPS_BRIEF = (
    "internal dispatch desk for warehouse staff only, not a public website, "
    "staff tool for shipment dispatch queue and records"
)
_STOREFRONT_BRIEF = "Restaurant / cafe menu ordering dine-in takeout storefront"


def _run135_seed() -> dict:
    # The shape `to_architecture_seed` produced for run 135's accepted spec:
    # primary ops page marked ops-dashboard, no route at "/" or "/home".
    return {
        "app_name": "dispatch-desk",
        "roles": [
            {
                "id": "ROLE-WAREHOUSE-STAFF",
                "label": "Warehouse Staff",
                "defaultPath": "/queue",
                "route_prefix": "",
                "icon": "users",
            }
        ],
        "routes": [
            {
                "path": "/queue",
                "page_id": "PAGE-DISPATCH-QUEUE",
                "role_id": "ROLE-WAREHOUSE-STAFF",
                "title": "Dispatch Queue",
                "component_file": "src/pages/role-warehouse-staff/DispatchQueuePage.tsx",
                "layout": "admin",
                "surface": "ops",
                "skeleton_id": "ops-dashboard",
            },
            {
                "path": "/records",
                "page_id": "PAGE-SHIPMENT-RECORDS",
                "role_id": "ROLE-WAREHOUSE-STAFF",
                "title": "Shipment Records",
                "component_file": "src/pages/role-warehouse-staff/ShipmentRecordsPage.tsx",
                "layout": "admin",
                "surface": "ops",
                "skeleton_id": "ops-list",
            },
            {
                "path": "/ai-features",
                "page_id": "PAGE-AI-FEATURES",
                "role_id": "ROLE-WAREHOUSE-STAFF",
                "title": "AI Features",
                "component_file": "src/pages/role-warehouse-staff/AiFeaturesPage.tsx",
                "layout": "admin",
                "surface": "ops",
                "skeleton_id": "ops-list",
            },
        ],
    }


def _ops_contract():
    contract = resolve_product_kind_contract(_OPS_BRIEF)
    assert contract.kind == "internal_ops"  # the fixture must bind the ops branch
    return contract


def test_run135_seed_gets_its_ops_home() -> None:
    locked = lock_chrome_on_architecture_seed(_run135_seed(), _ops_contract())
    paths = [rt["path"] for rt in locked["routes"]]
    assert "/" in paths
    home = next(rt for rt in locked["routes"] if rt["path"] == "/")
    # The home is the seed's own primary ops page, re-pathed — not an invention.
    assert home["page_id"] == "PAGE-DISPATCH-QUEUE"
    assert home["surface"] == "ops"
    assert not str(home.get("skeleton_id") or "").startswith("public")
    # The role's defaultPath follows its re-pathed home.
    assert locked["roles"][0]["defaultPath"] == "/"
    # The exact gate that refused run 135 now passes on the seed.
    assert "ops_kind_missing_home" not in validate_product_kind_chrome(locked)


def test_seed_with_existing_home_is_untouched() -> None:
    # The existing home is deliberately NOT the ops-dashboard candidate: if the
    # home-exists guard ever vanishes, the dashboard page (/queue) would be
    # re-pathed onto the records home and mint a duplicate "/".
    seed = _run135_seed()
    seed["routes"][1]["path"] = "/"
    seed["roles"][0]["defaultPath"] = "/"
    before = copy.deepcopy(seed["routes"])
    locked = lock_chrome_on_architecture_seed(seed, _ops_contract())
    assert [rt["path"] for rt in locked["routes"]] == [rt["path"] for rt in before]
    assert [rt["path"] for rt in locked["routes"]].count("/") == 1
    queue = next(
        rt for rt in locked["routes"] if rt["page_id"] == "PAGE-DISPATCH-QUEUE"
    )
    assert queue["path"] == "/queue"


def test_public_kind_seed_is_never_repathed() -> None:
    contract = resolve_product_kind_contract(_STOREFRONT_BRIEF)
    assert contract.kind == "storefront"  # the fixture must bind the guard
    seed = _run135_seed()
    locked = lock_chrome_on_architecture_seed(seed, contract)
    assert [rt["path"] for rt in locked["routes"]] == ["/queue", "/records", "/ai-features"]
    assert locked["roles"][0]["defaultPath"] == "/queue"


def test_no_ops_surface_routes_invents_nothing() -> None:
    # A mislabeled-surface spec: the honest gate refusal must stand — the fix
    # re-paths a real ops home, it never conjures one.
    seed = _run135_seed()
    for route in seed["routes"]:
        route["surface"] = "public"
        route["layout"] = "public"
        route["skeleton_id"] = ""
    locked_paths_input = [rt["path"] for rt in seed["routes"]]
    locked = lock_chrome_on_architecture_seed(seed, _ops_contract())
    assert [rt["path"] for rt in locked["routes"]] == locked_paths_input
    assert "ops_kind_missing_home" in validate_product_kind_chrome(locked)


def test_ai_hub_is_never_elected_home() -> None:
    seed = _run135_seed()
    # Only the AI hub carries ops surface; the real pages were mislabeled.
    seed["routes"][0]["surface"] = "public"
    seed["routes"][1]["surface"] = "public"
    locked = lock_chrome_on_architecture_seed(seed, _ops_contract())
    hub = next(rt for rt in locked["routes"] if rt["page_id"] == "PAGE-AI-FEATURES")
    assert hub["path"] == "/ai-features"
    assert "/" not in [rt["path"] for rt in locked["routes"]]


def test_dashboard_skeleton_wins_over_route_order() -> None:
    seed = _run135_seed()
    # Records first in scope order, but the queue carries the ops-dashboard
    # marker (the spec's primary ops page) — the marked page becomes home.
    seed["routes"] = [seed["routes"][1], seed["routes"][0], seed["routes"][2]]
    locked = lock_chrome_on_architecture_seed(seed, _ops_contract())
    home = next(rt for rt in locked["routes"] if rt["path"] == "/")
    assert home["page_id"] == "PAGE-DISPATCH-QUEUE"
    records = next(
        rt for rt in locked["routes"] if rt["page_id"] == "PAGE-SHIPMENT-RECORDS"
    )
    assert records["path"] == "/records"
