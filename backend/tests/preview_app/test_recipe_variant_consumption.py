"""Stage A / A2 — the enum broken honestly.

Three contracts, each of which was violated on HEAD before Stage A:

1. `'split'` is gone everywhere it was declared and nowhere implemented —
   six registry sites + six catalogue mirrors. A declared API that lies was
   the defect; deletion is the cure (no signed design exists for a real
   split hero, and Stage A must not invent a look).
2. The template consumes `SiteSpec.design` for every variant axis; the six
   `*_BY_RECIPE` maps are the defaults, not the decision.
3. The props the kit used to discard are honoured when valid —
   `MarketingHero` for every accepted variant (not just `'item'`),
   `FeatureBento` for its variant prop (previously destructured into a
   discard).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.ui_registry import build_catalogue_from_registry
from app.core.config import settings

TEMPLATE = Path(settings.PREVIEW_TEMPLATE_DIR)
RECIPE_TS = TEMPLATE / "src" / "lib" / "recipe.ts"
REGISTRY_TS = TEMPLATE / "src" / "ui" / "registry.ts"
CATALOGUE_JSON = TEMPLATE / "src" / "ui" / "catalogue.json"
HERO_TSX = TEMPLATE / "src" / "ui" / "public" / "MarketingHero.tsx"
BENTO_TSX = TEMPLATE / "src" / "ui" / "public" / "FeatureBento.tsx"


def _hero_accepts() -> set[str]:
    """What MarketingHero actually accepts: HeroVariant members + its own union extras."""
    recipe_ts = RECIPE_TS.read_text(encoding="utf-8")
    hero_union = re.search(r"export type HeroVariant =([^;]+);", recipe_ts, re.S)
    assert hero_union, "HeroVariant union missing from recipe.ts"
    accepted = set(re.findall(r"'([a-z-]+)'", hero_union.group(1)))
    hero_tsx = HERO_TSX.read_text(encoding="utf-8")
    union_line = next(
        line
        for line in hero_tsx.splitlines()
        if line.startswith("export type MarketingHeroVariant")
    )
    accepted |= set(re.findall(r"'([a-z-]+)'", union_line))
    return accepted


def test_split_is_deleted_everywhere_occurrence_counted() -> None:
    """Exact counts, not spot checks — MISCOUNT was the trap this repo paid for."""
    registry = REGISTRY_TS.read_text(encoding="utf-8")
    assert registry.count("'split'") == 0, "registry.ts still declares 'split'"
    catalogue = CATALOGUE_JSON.read_text(encoding="utf-8")
    assert catalogue.count('"split"') == 0, "catalogue.json still mirrors 'split'"
    # The unrelated skeleton id must survive the deletion untouched.
    assert catalogue.count("ops-recon-split") == 1
    hero = HERO_TSX.read_text(encoding="utf-8")
    assert "'split'" not in hero, "MarketingHero still types the deleted variant"


def test_registry_never_advertises_what_the_hero_rejects() -> None:
    """The inverse of test_trio_162's direction — 'split' lived in this gap:
    every variant any skeleton or the component registry advertises must be
    a variant the component's own union accepts."""
    accepted = _hero_accepts()
    catalogue = build_catalogue_from_registry()
    hero_entry = next(
        c for c in catalogue["components"] if c.get("name") == "MarketingHero"
    )
    advertised = set(hero_entry["variants"]["variant"])
    assert advertised <= accepted, (
        f"component registry advertises {sorted(advertised - accepted)} "
        "and the component rejects it"
    )
    for skeleton in catalogue["skeletons"]:
        supported = (skeleton.get("supportedVariants") or {}).get("MarketingHero")
        if not supported:
            continue
        assert set(supported) <= accepted, (
            f"skeleton {skeleton['id']} advertises "
            f"{sorted(set(supported) - accepted)} and the component rejects it"
        )


def test_checked_in_catalogue_matches_the_regenerated_one() -> None:
    """`--write` output committed verbatim; hand-edits to catalogue.json die here."""
    from app.application.ui_registry import serialize_catalogue

    assert CATALOGUE_JSON.read_text(encoding="utf-8") == serialize_catalogue(
        build_catalogue_from_registry()
    )


def test_recipe_accessors_consume_site_design_with_map_fallback() -> None:
    """Every axis accessor asks SITE_DESIGN first and falls back to its map.
    The maps stay complete (all six families) — they are defaults, not dead."""
    source = RECIPE_TS.read_text(encoding="utf-8")
    assert "import { SITE_DESIGN } from './site-design';" in source
    for axis, valid_set, map_name in (
        ("hero", "HERO_VARIANTS", "HERO_BY_RECIPE"),
        ("feature", "FEATURE_VARIANTS", "FEATURE_BY_RECIPE"),
        ("shell", "SHELL_CHROMES", "SHELL_BY_RECIPE"),
        ("nav", "NAV_VARIANTS", "NAV_BY_RECIPE"),
        ("footer", "FOOTER_VARIANTS", "FOOTER_BY_RECIPE"),
        ("brand_placement", "BRAND_PLACEMENTS", "BRAND_BY_RECIPE"),
    ):
        pattern = (
            rf"designVariant\(SITE_DESIGN\.variants\.{axis}, {valid_set}, recipeId\)\s*\?\?\s*"
            rf"{map_name}\[recipeId\]"
        )
        assert re.search(pattern, source), f"axis {axis} does not consume SITE_DESIGN"
        block = re.search(rf"const {map_name}[^=]*= \{{(.*?)\}};", source, re.S)
        assert block, f"{map_name} deleted — it must survive as the default"
        entries = re.findall(r"['\"]?[\w-]+['\"]?:\s*['\"][\w-]+['\"]", block.group(1))
        assert len(entries) == 6, f"{map_name} no longer covers the 6 families"
    # The design answers only for its own site's recipe family…
    assert "normalizeRecipeId(SITE_DESIGN.recipe_id) !== recipeId" in source
    # …and only with values from the axis's declared valid set.
    assert (
        "return value != null && (valid as readonly string[]).includes(value) ? (value as T) : null;"
        in source
    )


def test_marketing_hero_honours_every_valid_caller_variant() -> None:
    source = HERO_TSX.read_text(encoding="utf-8")
    # The old single-variant carve-out is gone…
    assert "variantProp === 'item' ? 'item' : recipeHeroVariant" not in source
    # …replaced by the guard over the full accepted set, with the recipe default.
    assert re.search(
        r"variantProp === 'item' \|\| \(HERO_VARIANTS as readonly string\[\]\)\.includes\(variantProp\)",
        source,
    ), "MarketingHero no longer honours the full valid set"
    assert ": recipeHeroVariant(recipeId);" in source


def test_feature_bento_honours_its_variant_prop() -> None:
    source = BENTO_TSX.read_text(encoding="utf-8")
    assert "variant: _variant" not in source, "the destructure-discard is back"
    assert re.search(
        r"\(FEATURE_VARIANTS as readonly string\[\]\)\.includes\(variantProp\)", source
    ), "FeatureBento does not validate the caller variant"
    assert ": recipeFeatureVariant(currentRecipeId());" in source


def test_emitted_site_design_variants_are_json_the_guards_accept() -> None:
    """End-to-end: what A1 emits parses, and every variant it carries passes
    the recipe.ts validity sets — so consumption can never fall back for a
    value the backend resolved on the production chain."""
    from app.application.preview_app.design_recipes import RECIPES, get_recipe
    from app.application.preview_app.site_design import resolve_site_design

    recipe_ts = RECIPE_TS.read_text(encoding="utf-8")
    valid: dict[str, set[str]] = {}
    for key, name in (
        ("hero", "HERO_VARIANTS"),
        ("feature", "FEATURE_VARIANTS"),
        ("shell", "SHELL_CHROMES"),
        ("nav", "NAV_VARIANTS"),
        ("footer", "FOOTER_VARIANTS"),
        ("brand_placement", "BRAND_PLACEMENTS"),
    ):
        block = re.search(
            rf"const {name}: readonly \w+\[\] = \[(.*?)\];", recipe_ts, re.S
        ) or re.search(rf"export const {name}: readonly \w+\[\] = \[(.*?)\];", recipe_ts, re.S)
        assert block, f"{name} valid set missing"
        valid[key] = set(re.findall(r"'([\w-]+)'", block.group(1)))
    for recipe_id in RECIPES:
        design = resolve_site_design(
            design_system={},
            recipe=get_recipe(recipe_id),
            primary=None,
            secondary=None,
            font=None,
        )
        payload = json.loads(json.dumps(design["variants"]))
        for key, value in payload.items():
            assert value in valid[key], (
                f"{recipe_id}.{key}={value!r} would be rejected by recipe.ts guards"
            )


if __name__ == "__main__":
    test_split_is_deleted_everywhere_occurrence_counted()
    test_registry_never_advertises_what_the_hero_rejects()
    test_checked_in_catalogue_matches_the_regenerated_one()
    test_recipe_accessors_consume_site_design_with_map_fallback()
    test_marketing_hero_honours_every_valid_caller_variant()
    test_feature_bento_honours_its_variant_prop()
    test_emitted_site_design_variants_are_json_the_guards_accept()
    print("Recipe variant consumption tests passed (7 tests)")
