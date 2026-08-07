"""R4's ladder for `ops_kind_too_few_pages` (owner-ruled, 2026-08-07).

Run 135's accepted 3-page dispatch-desk spec seeds its home (`e895ef7`) and
then — offline-proven on the stored artifact — refuses at the ship gate on
`ops_kind_too_few_pages`: the ops blueprint gap-fill fired only on
non-substantive tables, and the skeleton-keyed unserved test collides on
`ops-list` (it adds `/settings` alone, one page, still under the floor).

The ladder, each rung pinned here:
1. ONE floor constant (`OPS_MIN_NON_HUB_PAGES`) shared by the gate, the
   prompt render, the gap-fill target, and the seed refusal — derive, never
   duplicate (the `face_prompt.py` pattern).
2. A per-kind floor line in `app_spec.j2`, rendered for ops kinds only.
3. Ops gap-fill to the floor with a PATH-KEYED unserved test.
4. Seed-time refusal (`refuse_ops_under_floor=True`, the enforced-seed path)
   if still under floor — fail in seconds, not after a paid codegen run.
5. The ship gate UNTOUCHED as backstop — never lowered; reaching it again on
   this class is a NEW bug.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.product_kind import (
    OPS_MIN_NON_HUB_PAGES,
    OpsSeedUnderFloorError,
    apply_product_kind_to_architect,
    lock_chrome_on_architecture_seed,
    ops_floor_prompt_block,
    resolve_product_kind_contract,
    validate_product_kind_chrome,
)
from app.infrastructure.templating.renderer import JinjaTemplateRenderer

TEMPLATES_DIR = REPO_ROOT / "backend" / "app" / "templates"

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


def _non_hub_ops_paths(architect: dict) -> list[str]:
    """The gate's own counting rule, restated for assertions."""
    routes = [rt for rt in architect.get("routes") or [] if isinstance(rt, dict)]
    counted = []
    for rt in routes:
        if str(rt.get("path") or "") == "/ai-features":
            continue
        if (
            str(rt.get("surface") or "") == "ops"
            or str(rt.get("layout") or "") == "admin"
            or str(rt.get("skeleton_id") or "").startswith("ops")
        ):
            counted.append(str(rt.get("path") or ""))
    return counted


# --- rung 1 + 5: one constant, the gate derived from it, never lowered --------


def test_the_floor_is_four_and_the_gate_derives_from_it() -> None:
    # The owner's ruling pins the VALUE: never lower the gate. A change to
    # this constant is a product decision, not a refactor.
    assert OPS_MIN_NON_HUB_PAGES == 4

    def _table(n: int) -> dict:
        routes = [
            {"path": f"/p{i}", "surface": "ops", "skeleton_id": "ops-list"}
            for i in range(n)
        ]
        routes[0]["path"] = "/"
        routes[0]["skeleton_id"] = "ops-dashboard"
        return {"product_kind": "internal_ops", "routes": routes}

    at_floor = validate_product_kind_chrome(_table(OPS_MIN_NON_HUB_PAGES))
    under_floor = validate_product_kind_chrome(_table(OPS_MIN_NON_HUB_PAGES - 1))
    assert "ops_kind_too_few_pages" not in at_floor
    assert "ops_kind_too_few_pages" in under_floor


# --- rung 3: the run-135 shape, end to end ------------------------------------


def test_run135_shape_fills_to_the_floor_and_passes_the_gate() -> None:
    contract = _ops_contract()
    locked = lock_chrome_on_architecture_seed(_run135_seed(), contract)
    applied = apply_product_kind_to_architect(locked, contract, {"roles": []})
    assert validate_product_kind_chrome(applied) == []
    assert len(_non_hub_ops_paths(applied)) >= OPS_MIN_NON_HUB_PAGES


def test_the_gap_fill_is_path_keyed_not_skeleton_keyed() -> None:
    """The session-21 collision: `/queue` and `/reports` share `ops-list` with
    an already-served page, so the skeleton key blocks both and the table stays
    under the floor. The path key must add them."""
    contract = _ops_contract()
    locked = lock_chrome_on_architecture_seed(_run135_seed(), contract)
    pre_paths = {str(rt.get("path") or "") for rt in locked["routes"]}
    assert pre_paths == {"/", "/records", "/ai-features"}  # fixture must bind

    applied = apply_product_kind_to_architect(locked, contract, {"roles": []})
    paths = {str(rt.get("path") or "") for rt in applied["routes"]}
    added = paths - pre_paths
    # ops-list pages that the skeleton key would have refused:
    assert "/queue" in added or "/reports" in added, (
        "no ops-list blueprint page was added — the unserved test is still "
        "keyed on skeletons"
    )


def test_the_gap_fill_stops_at_the_floor() -> None:
    """Gap-fill TO the floor, not the whole blueprint: every invented page is
    a scaffold the customer sees, so the ladder adds the minimum that ships."""
    contract = _ops_contract()
    locked = lock_chrome_on_architecture_seed(_run135_seed(), contract)
    applied = apply_product_kind_to_architect(locked, contract, {"roles": []})
    assert len(_non_hub_ops_paths(applied)) == OPS_MIN_NON_HUB_PAGES, (
        "the fill overshot (or undershot) the gate's floor"
    )


def test_an_ops_table_at_the_floor_is_untouched() -> None:
    contract = _ops_contract()
    routes = [
        {"path": "/", "surface": "ops", "skeleton_id": "ops-dashboard",
         "component_file": "src/pages/A.tsx"},
        {"path": "/a", "surface": "ops", "skeleton_id": "ops-list",
         "component_file": "src/pages/B.tsx"},
        {"path": "/b", "surface": "ops", "skeleton_id": "ops-list",
         "component_file": "src/pages/C.tsx"},
        {"path": "/c", "surface": "ops", "skeleton_id": "ops-list",
         "component_file": "src/pages/D.tsx"},
    ]
    applied = apply_product_kind_to_architect(
        {"routes": routes, "files_to_generate": []}, contract, {"roles": []}
    )
    assert {str(rt.get("path") or "") for rt in applied["routes"]} == {
        "/", "/a", "/b", "/c"
    }, "a table already at the floor was gap-filled anyway"


def test_public_kinds_never_take_the_ops_branch() -> None:
    contract = resolve_product_kind_contract(_STOREFRONT_BRIEF)
    assert contract.kind == "storefront"  # the fixture must bind
    applied = apply_product_kind_to_architect(
        {
            "routes": [
                {"path": "/", "surface": "public", "skeleton_id": "public-home",
                 "component_file": "src/pages/HomePage.tsx"},
                {"path": "/menu", "surface": "public", "skeleton_id": "public-catalog",
                 "component_file": "src/pages/MenuPage.tsx"},
            ],
            "files_to_generate": [],
        },
        contract,
        {"roles": []},
    )
    assert not any(
        str(rt.get("skeleton_id") or "").startswith("ops")
        for rt in applied["routes"]
    ), "a public kind's table gained ops blueprint pages"


# --- rung 4: the seed-time refusal --------------------------------------------


def _unfillable_under_floor_table() -> dict:
    """Every blueprint path already exists but dressed FULLY public — surface,
    skeleton and an explicit `layout` (the injector's `setdefault` would
    otherwise dress a layout-less route `admin` and make it gate-countable).
    The path-keyed gap-fill can add nothing and only the marketing-home repair
    yields one ops route — the shape only the refusal rung can catch early."""
    paths = ["/", "/queue", "/records", "/reports", "/settings"]
    return {
        "routes": [
            {"path": p, "surface": "public", "layout": "public",
             "skeleton_id": "public-info",
             "component_file": f"src/pages/P{i}.tsx"}
            for i, p in enumerate(paths)
        ],
        "files_to_generate": [],
    }


def test_an_enforced_seed_still_under_floor_refuses_in_seconds() -> None:
    contract = _ops_contract()
    table = _unfillable_under_floor_table()
    with pytest.raises(OpsSeedUnderFloorError, match="ops_kind_too_few_pages"):
        apply_product_kind_to_architect(
            table, contract, {"roles": []}, refuse_ops_under_floor=True
        )


def test_the_refusal_is_opt_in_only() -> None:
    # The default path (non-enforced, forcer re-locks) must keep today's
    # behavior: the late gate is the backstop, not an exception.
    contract = _ops_contract()
    applied = apply_product_kind_to_architect(
        _unfillable_under_floor_table(), contract, {"roles": []}
    )
    assert "ops_kind_too_few_pages" in validate_product_kind_chrome(
        applied, product_kind=contract.kind
    )


def test_the_refusal_never_fires_for_public_kinds() -> None:
    contract = resolve_product_kind_contract(_STOREFRONT_BRIEF)
    assert contract.kind == "storefront"
    apply_product_kind_to_architect(
        {"routes": [{"path": "/", "surface": "public",
                     "component_file": "src/pages/HomePage.tsx"}],
         "files_to_generate": []},
        contract,
        {"roles": []},
        refuse_ops_under_floor=True,
    )  # must not raise


def test_the_refusal_never_fires_at_the_floor() -> None:
    contract = _ops_contract()
    locked = lock_chrome_on_architecture_seed(_run135_seed(), contract)
    apply_product_kind_to_architect(
        locked, contract, {"roles": []}, refuse_ops_under_floor=True
    )  # gap-fill reaches the floor first — must not raise


# --- rung 2: the prompt line, derived and kind-scoped -------------------------


def test_the_prompt_block_derives_from_the_gate_constant() -> None:
    block = ops_floor_prompt_block(
        {"product_face": {"product_kind": "internal_ops"}}
    )
    assert str(OPS_MIN_NON_HUB_PAGES) in block
    assert "ops_kind_too_few_pages" in block


def test_the_prompt_block_renders_for_ops_kinds_only() -> None:
    assert ops_floor_prompt_block(
        {"product_face": {"product_kind": "storefront"}}
    ) == ""
    assert ops_floor_prompt_block({}) == ""
    assert ops_floor_prompt_block(None) == ""
    assert ops_floor_prompt_block(
        {"product_face": {"product_kind": "saas_workspace"}}
    ) != ""


def test_the_floor_line_reaches_the_real_authoring_prompt() -> None:
    renderer = JinjaTemplateRenderer(TEMPLATES_DIR)
    from app.application.prompts import PromptTemplate

    common = dict(
        prompt_revision="test",
        schema_version="1.0",
        source_snapshot_json="{}",
        derived_context_json="{}",
        app_spec_json_schema="{}",
    )
    ops_block = ops_floor_prompt_block(
        {"product_face": {"product_kind": "internal_ops"}}
    )
    with_block = renderer.render(
        PromptTemplate.APP_SPEC, ops_floor_block=ops_block, **common
    )
    without = renderer.render(
        PromptTemplate.APP_SPEC, ops_floor_block="", **common
    )
    assert ops_block in with_block, "the template dropped the floor line"
    assert str(OPS_MIN_NON_HUB_PAGES) in with_block
    assert "ops_kind_too_few_pages" not in without


def test_the_builder_passes_the_block_for_an_ops_face() -> None:
    from app.application.appspec.builder import build_app_spec_candidate

    captured: dict = {}

    class _CapturingRenderer:
        def render(self, _template, **kwargs):
            captured.update(kwargs)
            raise RuntimeError("stop after render — the test only needs kwargs")

    with pytest.raises(RuntimeError, match="stop after render"):
        build_app_spec_candidate(
            source_snapshot={},
            derived_context={"product_face": {"product_kind": "internal_ops"}},
            ai_provider=object(),
            template_renderer=_CapturingRenderer(),
        )
    assert captured.get("ops_floor_block"), (
        "the builder never passed the ops floor block for an ops face"
    )
    assert str(OPS_MIN_NON_HUB_PAGES) in captured["ops_floor_block"]
