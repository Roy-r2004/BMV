"""Tests for locked brand brief inheritance."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.brand_brief import (
    apply_brief_to_plan,
    build_brand_brief,
    ensure_brand_brief,
)
from app.application.preview_app.design_recipes import apply_recipe_to_plan


def test_brief_rejects_purple_defaults_for_wellness() -> None:
    brief = build_brand_brief(
        {
            "product_name": "Harbor Yoga",
            "visual_theme": {
                "primary_color": "#6366f1",
                "secondary_color": "#9333ea",
                "background_color": "#f4f1ea",
                "style": "modern",
            },
        },
        business_name="Harbor Yoga",
        industry="Fitness & Wellness",
        business_description="yoga studio classes",
        seed=17,
    )
    assert brief["locked"] is True
    assert brief["palette"]["primary"] not in {"#6366f1", "#9333ea", "#4f46e5"}
    assert brief["palette"]["background"] != "#f4f1ea"
    assert brief["typography"]["font_family"].lower() != "inter"
    assert "purple" in " ".join(brief["avoid"]).lower()


def test_recipe_cannot_overwrite_locked_brief_fonts() -> None:
    demo = ensure_brand_brief(
        {"visual_theme": {"primary_color": "#0f766e", "secondary_color": "#134e4a"}},
        business_name="Harbor Yoga",
        industry="Wellness",
        business_description="yoga spa massage",
        seed=3,
    )
    brief = demo["brand_brief"]
    plan = apply_brief_to_plan({"design_system": {}, "roles": []}, brief)
    assert plan["design_system"]["brand_locked"] is True
    locked_font = plan["design_system"]["font_family"]
    stamped = apply_recipe_to_plan(
        plan,
        industry="Wellness",
        business_description="yoga",
        concept_name="Harbor Yoga",
        seed=3,
        recipe_id=brief["recipe_id"],
    )
    stamped = apply_brief_to_plan(stamped, brief)
    assert stamped["design_system"]["font_family"] == locked_font
    assert stamped["design_system"]["primary_color"] == brief["palette"]["primary"]
    assert stamped["design_system"].get("recipe_prompt")


if __name__ == "__main__":
    test_brief_rejects_purple_defaults_for_wellness()
    test_recipe_cannot_overwrite_locked_brief_fonts()
    print("Brand brief tests passed (2 tests)")
