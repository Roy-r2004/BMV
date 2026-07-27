"""Tests for sealed design brief — single design authority before codegen."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.brand_brief import build_brand_brief
from app.application.preview_app.design_brief import (
    apply_sealed_brief_to_architect,
    apply_sealed_brief_to_plan,
    design_brief_prompt_block,
    resolve_design_brief,
    seal_design_brief,
)
from app.application.preview_app.design_overlay import apply_design_overlay_to_plan
from app.application.preview_app.design_recipes import apply_recipe_to_plan, get_recipe
from app.application.preview_app.industry_templates.apply import _stamp_pack_voice
from app.application.preview_app.product_kind import apply_product_kind_to_plan, resolve_product_kind_contract


def _mushy_plan() -> dict:
    """Simulate the historical pile-on before sealing."""
    brand = build_brand_brief(
        {
            "product_name": "Harbor Yoga",
            "visual_theme": {
                "primary_color": "#0f766e",
                "secondary_color": "#134e4a",
                "background_color": "#f0fdfa",
                "style": "calm",
            },
        },
        business_name="Harbor Yoga",
        industry="Wellness",
        business_description="yoga spa massage studio",
        seed=11,
    )
    plan: dict = {
        "design_system": {},
        "roles": [{"id": "ROLE-GUEST", "label": "Guest", "pages": []}],
    }
    from app.application.preview_app.brand_brief import apply_brief_to_plan

    plan = apply_brief_to_plan(plan, brand)
    contract = resolve_product_kind_contract("yoga spa wellness studio booking")
    plan = apply_product_kind_to_plan(plan, contract)
    plan = apply_recipe_to_plan(
        plan,
        industry="Wellness",
        business_description="yoga spa",
        concept_name="Harbor Yoga",
        seed=11,
        recipe_id=brand["recipe_id"],
    )
    # Packs historically append into recipe_prompt + design_direction.
    _stamp_pack_voice(
        plan,
        {
            "id": "wellness-studio",
            "label": "Wellness studio",
            "prompt_hints": ["Full-bleed calm hero", "Credential rail"],
            "signature_moves": ["soft mesh", "quiet CTA"],
        },
        key_prefix="template",
    )
    plan = apply_product_kind_to_plan(plan, contract)
    plan = apply_design_overlay_to_plan(
        plan,
        seed=11,
        context="yoga spa wellness",
        industry="Wellness",
        business_name="Harbor Yoga",
    )
    return plan, brand


def test_seal_collapses_direction_mush_into_one_authority() -> None:
    plan, brand = _mushy_plan()
    mush_direction = plan.get("design_direction") or ""
    mush_recipe = (plan.get("design_system") or {}).get("recipe_prompt") or ""
    assert "PRODUCT_KIND=" in mush_direction or "Template" in mush_direction
    assert "TEMPLATE" in mush_recipe

    brief = seal_design_brief(plan, brand_brief=brand)
    assert brief["sealed"] is True
    assert brief["version"] == "1.0"
    assert brief["brand_locked"] is True
    assert brief["recipe_id"] == brand["recipe_id"]
    assert brief["recipe_prompt"] == get_recipe(brand["recipe_id"])["prompt"]
    assert "TEMPLATE" not in brief["recipe_prompt"]
    assert "PRODUCT_KIND=" not in (brief["direction"] or "")
    assert brief["direction"].count("Product kind") <= 1
    assert brief["template_prompt"]
    assert brief["palette"]["primary"] == brand["palette"]["primary"]
    assert brief["signature"]


def test_apply_sealed_brief_cleans_plan_and_architect() -> None:
    plan, brand = _mushy_plan()
    brief = seal_design_brief(plan, brand_brief=brand)
    sealed_plan = apply_sealed_brief_to_plan(plan, brief)
    assert sealed_plan["design_brief"]["sealed"] is True
    assert sealed_plan["design_direction"] == brief["direction"]
    assert sealed_plan["design_system"]["recipe_prompt"] == brief["recipe_prompt"]
    assert sealed_plan["design_system"]["design_brief_sealed"] is True
    assert "TEMPLATE wellness-studio" not in sealed_plan["design_system"]["recipe_prompt"]
    # Pack voice survives as structured field, not mush.
    assert sealed_plan["design_system"].get("template_prompt")

    architect = {
        "design_direction": "Invented contradictory cinematic noir dashboard",
        "recipe_id": "dense-ops",
        "files_to_generate": [],
        "routes": [],
    }
    sealed_arch = apply_sealed_brief_to_architect(architect, brief)
    assert sealed_arch["design_direction"] == brief["direction"]
    assert sealed_arch["recipe_id"] == brief["recipe_id"]
    assert sealed_arch["design_brief"]["sealed"] is True


def test_prompt_block_and_resolve() -> None:
    plan, brand = _mushy_plan()
    brief = seal_design_brief(plan, brand_brief=brand)
    plan = apply_sealed_brief_to_plan(plan, brief)
    block = design_brief_prompt_block(brief)
    assert "SEALED DESIGN BRIEF" in block
    assert brief["recipe_id"] in block
    assert "NON-NEGOTIABLE" in block
    assert resolve_design_brief(plan=plan) is plan["design_brief"]
    assert resolve_design_brief(plan={}, architect={"design_brief": brief}) is brief
    assert design_brief_prompt_block(None) == ""
    assert design_brief_prompt_block({"recipe_id": "x"}) == ""


if __name__ == "__main__":
    test_seal_collapses_direction_mush_into_one_authority()
    test_apply_sealed_brief_cleans_plan_and_architect()
    test_prompt_block_and_resolve()
    print("Sealed design brief tests passed (3 tests)")
