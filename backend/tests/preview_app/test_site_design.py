"""SiteSpec.design — the single resolution (Stage A / A1).

Pins the resolution's precedence (overlay tokens > recipe; brief fonts >
recipe; locked palette > caller colors; renderer defaults), the emitted
``src/lib/site-design.ts`` contract, the template default's anti-drift pin,
and the cross-language 1:1 between the resolved variants and the template's
``recipe.ts`` maps — the comment in that file claimed 1:1 and nothing
enforced it until now.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.assemble import write_index_css
from app.application.preview_app.design_recipes import RECIPES, get_recipe
from app.application.preview_app.site_design import (
    resolve_site_design,
    site_design_ts,
)
from app.core.config import settings


def _bare(recipe_id: str | None) -> dict:
    return resolve_site_design(
        design_system={},
        recipe=get_recipe(recipe_id) if recipe_id else None,
        primary=None,
        secondary=None,
        font=None,
    )


def test_overlay_token_overrides_win_over_recipe_tokens() -> None:
    recipe = get_recipe("editorial")
    overrides = {
        "radius_ui": "0.99rem",
        "bg_mix": "9%",
        "atmosphere": "linear-gradient(#000, #fff)",
    }
    design = resolve_site_design(
        design_system={"token_overrides": overrides},
        recipe=recipe,
        primary="#123456",
        secondary="#654321",
        font="Source Sans 3",
    )
    assert design["tokens"]["radius_ui"] == "0.99rem"
    assert design["tokens"]["bg_mix"] == "9%"
    assert design["tokens"]["atmosphere"] == "linear-gradient(#000, #fff)"
    # Keys the overlay did not override keep the recipe's value.
    assert design["tokens"]["fg_mix"] == recipe["tokens"]["fg_mix"]
    # None-valued overrides never erase a recipe token.
    design2 = resolve_site_design(
        design_system={"token_overrides": {"card": None}},
        recipe=recipe,
        primary="#123456",
        secondary="#654321",
        font="Source Sans 3",
    )
    assert design2["tokens"]["card"] == recipe["tokens"]["card"]


def test_brief_fonts_win_over_recipe_fonts() -> None:
    design = resolve_site_design(
        design_system={
            "font_sans": '"Nunito Sans", sans-serif',
            "font_display": '"Libre Baskerville", serif',
            "font_import": "Nunito+Sans:wght@400",
            "font_family": "Nunito Sans",
        },
        recipe=get_recipe("bold-retail"),
        primary="#123456",
        secondary="#654321",
        font="Space Grotesk",
    )
    assert design["typography"]["font_sans"] == '"Nunito Sans", sans-serif'
    assert design["typography"]["font_display"] == '"Libre Baskerville", serif'
    assert design["typography"]["font_family"] == "Nunito Sans"
    assert "family=Nunito+Sans:wght@400&display=swap" in design["typography"]["font_import"]
    # Without design_system fonts the recipe's pair ships.
    bare = _bare("bold-retail")
    assert bare["typography"]["font_sans"] == get_recipe("bold-retail")["fonts"]["sans"]


def test_locked_palette_wins_and_unlocked_keeps_sanitized_inputs() -> None:
    locked = resolve_site_design(
        design_system={
            "brand_locked": True,
            "primary_color": "#8b1e3f",
            "secondary_color": "#2f6f4f",
        },
        recipe=get_recipe("craft"),
        primary="#111111",
        secondary="#222222",
        font="DM Sans",
    )
    assert locked["palette"] == {"primary": "#8b1e3f", "secondary": "#2f6f4f"}
    unlocked = resolve_site_design(
        design_system={"primary_color": "#8b1e3f", "secondary_color": "#2f6f4f"},
        recipe=get_recipe("craft"),
        primary="#111111",
        secondary="#222222",
        font="DM Sans",
    )
    # Without the lock the caller-supplied (sanitized) colors stand.
    assert unlocked["palette"] == {"primary": "#111111", "secondary": "#222222"}


def test_renderer_defaults_fill_empty_recipe() -> None:
    design = resolve_site_design(
        design_system={},
        recipe={"id": "bare"},
        primary=None,
        secondary=None,
        font=None,
    )
    assert design["tokens"]["radius_ui"] == "0.75rem"
    assert design["tokens"]["card"] == "white"
    assert design["tokens"]["shadow"] == "0 24px 50px -36px"
    # No fonts anywhere -> the sanitized font family carries the CSS.
    assert design["typography"]["font_sans"] == design["typography"]["font_family"]
    assert design["typography"]["font_import"] == ""
    assert design["recipe_id"] == "bare"
    # recipe=None falls back to warm-service, same as get_recipe(None).
    assert _bare(None)["recipe_id"] == "warm-service"


def _template_maps() -> dict[str, dict[str, str]]:
    recipe_ts = (
        settings.PREVIEW_TEMPLATE_DIR / "src" / "lib" / "recipe.ts"
    ).read_text(encoding="utf-8")
    maps: dict[str, dict[str, str]] = {}
    for name in (
        "HERO_BY_RECIPE",
        "FEATURE_BY_RECIPE",
        "SHELL_BY_RECIPE",
        "NAV_BY_RECIPE",
        "FOOTER_BY_RECIPE",
        "BRAND_BY_RECIPE",
    ):
        block = re.search(rf"const {name}[^=]*= \{{(.*?)\}};", recipe_ts, re.S)
        assert block, f"map {name} missing from recipe.ts"
        entries = dict(
            re.findall(r"['\"]?([\w-]+)['\"]?:\s*['\"]([\w-]+)['\"]", block.group(1))
        )
        assert len(entries) == 6, f"{name} must cover the 6 recipe families"
        maps[name] = entries
    return maps


def test_resolved_variants_match_template_maps_for_every_recipe() -> None:
    """The 1:1 the recipe.ts comment promises, enforced across the language
    boundary. Ledger/floor resolve through their dense-ops family row."""
    maps = _template_maps()
    variant_keys = {
        "hero": "HERO_BY_RECIPE",
        "feature": "FEATURE_BY_RECIPE",
        "shell": "SHELL_BY_RECIPE",
        "nav": "NAV_BY_RECIPE",
        "footer": "FOOTER_BY_RECIPE",
        "brand_placement": "BRAND_BY_RECIPE",
    }
    for recipe_id in RECIPES:
        family = "dense-ops" if recipe_id.startswith("dense-ops") else recipe_id
        design = _bare(recipe_id)
        for key, map_name in variant_keys.items():
            assert design["variants"][key] == maps[map_name][family], (
                f"{recipe_id}.{key} diverged from recipe.ts {map_name}[{family}]"
            )


def test_placeholder_axes_present_and_recipe_invariant() -> None:
    """Stage A states today's constants once; Stage D varies them. Until then
    every recipe must carry identical placeholder axes — EXCEPT motion, which
    3.10 made per-recipe (its own pin below)."""
    baseline = _bare("editorial")
    for axis in ("type_ramp", "spacing", "container", "grid", "image_treatment", "motion"):
        assert axis in baseline, f"axis {axis} missing"
    assert baseline["container"] == {"max": "92rem"}
    assert baseline["spacing"]["section_y"] == "7rem"
    for recipe_id in RECIPES:
        design = _bare(recipe_id)
        for axis in ("type_ramp", "spacing", "container", "grid", "image_treatment"):
            assert design[axis] == baseline[axis], f"{recipe_id}.{axis} diverged"


def test_motion_identity_is_authored_per_recipe() -> None:
    """3.10: motion is a first-class axis (session-26 ruling). Every recipe
    ships a complete authored identity; the six families never share one
    (the Phase 3 DoD's distinctness seed); ops recipes stay more restrained
    than every marketing recipe — fast, calm, instant, by the owner's
    demo-matches-the-business rule. A bare/unknown recipe keeps the
    entrance-only fallback."""
    identities: dict[str, str] = {}
    marketing_staggers: list[int] = []
    ops_staggers: list[int] = []
    for recipe_id in RECIPES:
        motion = _bare(recipe_id)["motion"]
        assert isinstance(motion["identity"], str) and motion["identity"]
        ease = motion["ease"]
        assert isinstance(ease, list) and len(ease) == 4
        assert all(isinstance(n, (int, float)) for n in ease)
        assert isinstance(motion["stagger_ms"], int) and motion["stagger_ms"] > 0
        assert str(motion["travel"]).endswith("px")
        assert motion["reveal"]
        family = "dense-ops" if recipe_id.startswith("dense-ops") else recipe_id
        identities.setdefault(family, motion["identity"])
        (ops_staggers if recipe_id.startswith("dense-ops") else marketing_staggers).append(
            motion["stagger_ms"]
        )
    assert len(set(identities.values())) == 6, "two families share a motion identity"
    assert max(ops_staggers) < min(marketing_staggers), (
        "ops restraint violated — an ops recipe staggers slower than a marketing one"
    )
    # The fallback shape survives for recipes that author nothing.
    bare = resolve_site_design(
        design_system={}, recipe={"id": "bare"}, primary=None, secondary=None, font=None
    )
    assert bare["motion"]["identity"] == "entrance-only"
    assert bare["motion"]["ease"] is None


def test_emitted_ts_round_trips_and_template_default_is_pinned() -> None:
    design = _bare("nocturne")
    content = site_design_ts(design)
    assert content.startswith("/** SiteSpec.design")
    assert "export interface SiteDesign" in content
    literal = re.search(r"export const SITE_DESIGN: SiteDesign = (\{.*\});\n\Z", content, re.S)
    assert literal, "emitted module must end with the SITE_DESIGN const"
    assert json.loads(literal.group(1)) == design
    # The committed template default is exactly the bare warm-service emission;
    # regenerating it is the only legal way to change it.
    template_default = (
        settings.PREVIEW_TEMPLATE_DIR / "src" / "lib" / "site-design.ts"
    ).read_text(encoding="utf-8")
    assert template_default == site_design_ts(_bare(None))


def test_write_index_css_writes_css_recipe_id_and_site_design() -> None:
    from app.infrastructure.templating.renderer import JinjaTemplateRenderer

    design_system = {
        "brand_locked": True,
        "primary_color": "#8b1e3f",
        "secondary_color": "#2f6f4f",
        "token_overrides": {"glow": "9%"},
        "font_sans": '"Manrope", sans-serif',
        "font_display": '"Instrument Serif", serif',
        "font_import": "Manrope:wght@400",
        "font_family": "Manrope",
    }
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        write_index_css(
            ws,
            "#111111",
            "#222222",
            "Manrope",
            JinjaTemplateRenderer(),
            recipe=get_recipe("nocturne"),
            design_system=design_system,
        )
        css = (ws / "src" / "index.css").read_text(encoding="utf-8")
        assert "--color-brand: #8b1e3f;" in css
        assert "color-mix(in srgb, #8b1e3f 9%, transparent)" in css  # glow override
        assert (ws / "src" / "lib" / "recipe-id.ts").read_text(encoding="utf-8") == (
            'export const RECIPE_ID = "nocturne" as const;\n'
        )
        emitted = (ws / "src" / "lib" / "site-design.ts").read_text(encoding="utf-8")
        literal = re.search(
            r"export const SITE_DESIGN: SiteDesign = (\{.*\});\n\Z", emitted, re.S
        )
        assert literal
        parsed = json.loads(literal.group(1))
        assert parsed["recipe_id"] == "nocturne"
        assert parsed["palette"]["primary"] == "#8b1e3f"
        assert parsed["tokens"]["glow"] == "9%"


if __name__ == "__main__":
    test_overlay_token_overrides_win_over_recipe_tokens()
    test_brief_fonts_win_over_recipe_fonts()
    test_locked_palette_wins_and_unlocked_keeps_sanitized_inputs()
    test_renderer_defaults_fill_empty_recipe()
    test_resolved_variants_match_template_maps_for_every_recipe()
    test_placeholder_axes_present_and_recipe_invariant()
    test_motion_identity_is_authored_per_recipe()
    test_emitted_ts_round_trips_and_template_default_is_pinned()
    test_write_index_css_writes_css_recipe_id_and_site_design()
    print("Site design resolution tests passed (8 tests)")
