"""Stage A / A3 — compatible_recipes CONSUMED (session-26 ruling).

Two consumers, both pinned here: the loader stamps the map onto every pack,
and ``pick_recipe_id``'s no-keyword fallback rotates over the REACHABLE set
(the five marketing recipes) instead of all eight — the old rotation spent
3 of 8 seed slots on app-hub recipes that public runs null downstream
("a fallback that can pick the unpickable").

What must NOT change, pinned too: the keyword path still reaches ops recipes
at brief time (the plan_phase null-out stays the guard), and packs never
author ``compatible_recipes`` themselves — the module is the single source.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.design_recipes import RECIPES, pick_recipe_id
from app.application.preview_app.industry_templates.compatible_recipes import (
    COMPATIBLE_RECIPES,
    MARKETING_RECIPE_IDS,
    compatible_recipes_for,
)
from app.application.preview_app.industry_templates.loader import (
    _PACKS_DIR,
    get_template,
    load_templates,
)

# A brief with zero recipe-keyword hits, verified below before use.
_NO_KEYWORD = {
    "industry": "General",
    "business_description": "A local neighbourhood organisation.",
    "concept_name": "Northwind",
}


def _assert_no_keyword_hits() -> None:
    scores_hit = [
        rid
        for rid, recipe in RECIPES.items()
        for token in str(recipe.get("industry_keywords") or "").split()
        if token in _NO_KEYWORD["business_description"].lower()
    ]
    assert not scores_hit, f"fixture is not keyword-free: {scores_hit}"


def test_fallback_rotates_over_the_reachable_marketing_set() -> None:
    _assert_no_keyword_hits()
    seen: set[str] = set()
    for seed in range(10):
        picked = pick_recipe_id(seed=seed, **{
            "industry": _NO_KEYWORD["industry"],
            "business_description": _NO_KEYWORD["business_description"],
            "concept_name": _NO_KEYWORD["concept_name"],
        })
        assert picked in MARKETING_RECIPE_IDS, (
            f"seed {seed} fell back to unreachable recipe {picked!r}"
        )
        seen.add(picked)
    # Rotation still rotates: five consecutive seeds cover all five recipes.
    assert seen == set(MARKETING_RECIPE_IDS)


def test_the_previously_unpickable_slots_are_reclaimed() -> None:
    """Old order rotated all 8 (dict order: editorial, dense-ops,
    dense-ops-ledger, dense-ops-floor, …) — seeds 1..3 landed app-hub recipes
    public runs null downstream. Those seeds must land marketing now."""
    for seed in (1, 2, 3):
        picked = pick_recipe_id(seed=seed, **_NO_KEYWORD)
        assert picked in MARKETING_RECIPE_IDS
        assert not picked.startswith("dense-ops")


def test_fallback_is_deterministic_per_seed() -> None:
    for seed in (0, 7, 31):
        assert pick_recipe_id(seed=seed, **_NO_KEYWORD) == pick_recipe_id(
            seed=seed, **_NO_KEYWORD
        )


def test_keyword_path_still_reaches_ops_recipes_at_brief_time() -> None:
    """The reachable-set rule constrains the FALLBACK only. Keyword hits keep
    their full range; the plan_phase null-out stays the guard for false hits
    on public kinds."""
    assert (
        pick_recipe_id(
            industry="Hedge fund",
            business_description="institutional trading desk, blotter, execution and risk pnl",
            concept_name="Meridian Capital",
            seed=0,
        )
        == "dense-ops-floor"
    )


def test_every_loaded_pack_carries_its_map_row() -> None:
    packs = load_templates()
    assert packs, "no packs loaded"
    for pack_id, pack in packs.items():
        assert pack.get("compatible_recipes") == list(
            compatible_recipes_for(pack_id)
        ), f"{pack_id} does not carry its map row"
    assert get_template("pottery-craft-studio")["compatible_recipes"] == list(
        COMPATIBLE_RECIPES["pottery-craft-studio"]
    )


def test_packs_never_author_the_field_themselves() -> None:
    """Single source: the module. A hand-authored copy in a pack JSON is the
    27-unexplained-copies drift the map's design note forbids."""
    offenders = [
        path.name
        for path in sorted(_PACKS_DIR.glob("*.json"))
        if "compatible_recipes" in json.loads(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"packs authoring compatible_recipes: {offenders}"


if __name__ == "__main__":
    test_fallback_rotates_over_the_reachable_marketing_set()
    test_the_previously_unpickable_slots_are_reclaimed()
    test_fallback_is_deterministic_per_seed()
    test_keyword_path_still_reaches_ops_recipes_at_brief_time()
    test_every_loaded_pack_carries_its_map_row()
    test_packs_never_author_the_field_themselves()
    print("Compatible recipes consumption tests passed (6 tests)")
