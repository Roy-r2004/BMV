"""Per-request design token overlays — unique face without industry packs."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.brand_brief import apply_brief_to_plan, ensure_brand_brief
from app.application.preview_app.design_overlay import (
    apply_design_overlay_to_plan,
    build_design_overlay,
    pick_design_mood,
)
from app.application.preview_app.design_recipes import apply_recipe_to_plan


def test_clinic_brief_picks_calm_air() -> None:
    mood = pick_design_mood(
        "Northside Family Clinic",
        "Healthcare",
        "family medicine patient portal appointments",
        seed=3,
    )
    assert mood == "calm_air"


def test_seed_diverges_when_keywords_tie() -> None:
    a = pick_design_mood("generic software platform workspace", seed=1)
    b = pick_design_mood("generic software platform workspace", seed=99)
    # Same brief can still diverge across requests via seed.
    assert a in {
        "soft_glass",
        "warm_paper",
        "bold_ink",
        "ledger_light",
        "night_floor",
        "calm_air",
    }
    assert b in {
        "soft_glass",
        "warm_paper",
        "bold_ink",
        "ledger_light",
        "night_floor",
        "calm_air",
    }
    # Soft glass keyword hit should dominate for SaaS-ish copy.
    assert pick_design_mood("SaaS CRM dashboard platform workspace", seed=1) == "soft_glass"


def test_overlay_stamps_tokens_and_never_fonts() -> None:
    """Stage A deleted the overlay's font lane — the six mood pairs were dead
    on every production run (brand_locked always True). The overlay owns
    atmosphere / radius / density; fonts are the brand brief's lane only."""
    plan = apply_recipe_to_plan(
        {},
        industry="Healthcare",
        business_description="clinic patients appointments",
        concept_name="Northside Clinic",
        seed=3,
    )
    stamped = apply_design_overlay_to_plan(
        plan,
        seed=3,
        context="family clinic patient portal",
        industry="Healthcare",
        business_name="Northside Clinic",
    )
    ds = stamped["design_system"]
    assert ds["design_overlay_id"] == "calm_air"
    assert isinstance(ds.get("token_overrides"), dict)
    assert "atmosphere" in ds["token_overrides"]
    assert ds["border_radius"] == ds["token_overrides"]["radius_ui"]
    # The deleted lane stays deleted: no overlay writer for any font key.
    assert "font_sans" not in ds
    assert "font_display" not in ds
    assert "font_import" not in ds
    assert stamped["design_overlay"]["id"] == "calm_air"


def test_overlay_respects_brand_locked_fonts() -> None:
    demo = ensure_brand_brief(
        {"visual_theme": {"primary_color": "#0f766e", "secondary_color": "#134e4a"}},
        business_name="Harbor Yoga",
        industry="Wellness",
        business_description="yoga spa massage",
        seed=3,
    )
    brief = demo["brand_brief"]
    plan = apply_brief_to_plan({"design_system": {}, "roles": []}, brief)
    locked_font = plan["design_system"]["font_family"]
    plan = apply_recipe_to_plan(
        plan,
        industry="Wellness",
        business_description="yoga spa",
        concept_name="Harbor Yoga",
        seed=3,
        recipe_id=brief.get("recipe_id"),
    )
    plan = apply_brief_to_plan(plan, brief)
    stamped = apply_design_overlay_to_plan(
        plan,
        seed=3,
        context="yoga spa massage wellness",
        industry="Wellness",
        business_name="Harbor Yoga",
    )
    assert stamped["design_system"]["brand_locked"] is True
    assert stamped["design_system"]["font_family"] == locked_font
    # Atmosphere / radius still come from the overlay.
    assert stamped["design_system"]["design_overlay_id"]
    assert stamped["design_system"]["token_overrides"]["atmosphere"]


def test_overlay_micro_variation_by_seed() -> None:
    a = build_design_overlay("clinic patient care", seed=1, mood_id="calm_air")
    b = build_design_overlay("clinic patient care", seed=2, mood_id="calm_air")
    assert a["id"] == b["id"] == "calm_air"
    # Same mood, different seed → slight token drift.
    assert a["tokens"]["radius_ui"] != b["tokens"]["radius_ui"] or a["tokens"]["glow"] != b["tokens"]["glow"]


if __name__ == "__main__":
    test_clinic_brief_picks_calm_air()
    test_seed_diverges_when_keywords_tie()
    test_overlay_stamps_tokens_and_never_fonts()
    test_overlay_respects_brand_locked_fonts()
    test_overlay_micro_variation_by_seed()
    print("Design overlay tests passed (5 tests)")
