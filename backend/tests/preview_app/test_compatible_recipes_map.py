"""Pin the inert compatible_recipes map to the packs and recipes it describes.

Session 25, roadmap 3.2 (backend half). The map is DATA — nothing in the
pipeline consumes it — but it must never drift from the corpus it indexes:
every pack keyed, every recipe id real, and the pairing HEAD deterministically
produces (the pack's recipe_hint via ``template_recipe_hint``) present in the
pack's list. The deep prover is
``scripts/measure/compatible_recipes_census.py``; this test pins the invariants
cheap enough to run on every suite pass.
"""
from __future__ import annotations

from app.application.preview_app.design_recipes import RECIPES
from app.application.preview_app.industry_templates import TEMPLATE_IDS
from app.application.preview_app.industry_templates.apply import template_recipe_hint
from app.application.preview_app.industry_templates.compatible_recipes import (
    COMPATIBLE_RECIPES,
    MARKETING_RECIPE_IDS,
    OPS_CONTRACT_RECIPE_IDS,
    UNREACHABLE_PACK_IDS,
    compatible_recipes_for,
)
from app.application.preview_app.industry_templates.loader import (
    _is_ops_skeleton,
    _is_public_marketing_skeleton,
    load_templates,
)


def test_map_keys_are_exactly_the_pack_corpus():
    packs = load_templates()
    assert set(COMPATIBLE_RECIPES) == set(packs) == set(TEMPLATE_IDS)


def test_every_pack_has_a_non_empty_valid_compatible_list():
    for pack_id, recipes in COMPATIBLE_RECIPES.items():
        assert recipes, f"{pack_id} has an empty compatible_recipes list"
        unknown = [r for r in recipes if r not in RECIPES]
        assert not unknown, f"{pack_id} references unknown recipe ids {unknown}"
        assert len(set(recipes)) == len(recipes), f"{pack_id} has duplicate entries"


def test_current_deterministic_pairing_is_in_the_map():
    """The pairing HEAD produces without a brand brief: the pack's own hint."""
    packs = load_templates()
    for pack_id, pack in packs.items():
        if pack_id in UNREACHABLE_PACK_IDS:
            continue  # pick_template_id can never return these (census proves it)
        sk = str(pack.get("skeleton_id") or "")
        surface = "ops" if _is_ops_skeleton(sk) else "public"
        tags = " ".join(str(t) for t in (pack.get("industry_tags") or []))
        hint = template_recipe_hint(industry=tags, seed=0, surface=surface, context="")
        assert hint == str(pack.get("recipe_hint") or ""), (
            f"{pack_id}: template_recipe_hint no longer returns the declared hint"
        )
        assert hint in COMPATIBLE_RECIPES[pack_id], (
            f"HEAD-produced pairing outside the map: {pack_id} -> {hint}"
        )


def test_surface_classes_match_recipe_hub_reachability():
    """Ops packs carry only app-hub contract recipes; public packs only marketing."""
    packs = load_templates()
    app_hub = {rid for rid, r in RECIPES.items() if str(r.get("hub_variant")) == "app"}
    assert app_hub == set(OPS_CONTRACT_RECIPE_IDS)
    assert set(RECIPES) - app_hub == set(MARKETING_RECIPE_IDS)
    for pack_id, pack in packs.items():
        sk = str(pack.get("skeleton_id") or "")
        entry = set(COMPATIBLE_RECIPES[pack_id])
        if _is_ops_skeleton(sk):
            assert entry == set(OPS_CONTRACT_RECIPE_IDS), pack_id
        elif _is_public_marketing_skeleton(sk):
            assert entry == set(MARKETING_RECIPE_IDS), pack_id
            # Deterministic hint leads the list for public packs.
            assert COMPATIBLE_RECIPES[pack_id][0] == str(pack.get("recipe_hint")), pack_id
        else:
            assert pack_id in UNREACHABLE_PACK_IDS, (
                f"{pack_id} fails both surface filters but is not flagged unreachable"
            )
            assert entry == {str(pack.get("recipe_hint") or "")}, pack_id


def test_accessor_is_total_and_safe():
    assert compatible_recipes_for("pottery-craft-studio")[0] == "craft"
    assert compatible_recipes_for("no-such-pack") == ()
    assert compatible_recipes_for(None) == ()  # type: ignore[arg-type]
