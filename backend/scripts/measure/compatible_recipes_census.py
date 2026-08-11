#!/usr/bin/env python3
"""compatible_recipes census — does the pack->recipe map cover everything HEAD can produce?

QUESTION. Session 25, roadmap 3.2 (backend half): the new inert data module
``industry_templates/compatible_recipes.py`` claims, per pack, the recipes HEAD
can pair with it. Is every pairing HEAD can currently produce present in the
map, does the map reference only real pack/recipe ids, and do the reachability
facts the map bakes still hold at HEAD?

METHOD. No DB, no network, no preview generation. Replay the REAL selection and
pairing functions over all packs:

  1. Corpus guards: exactly 27 packs on disk == loader corpus == map keys, and
     exactly 8 recipes. Any drift RED-EXITS — a rerun must never silently
     measure a different corpus.
  2. Id validity: every mapped recipe id is a real RECIPES key; every map key a
     real pack id; every list non-empty.
  3. Reachability replay: classify every pack with the loader's own surface
     filters (``_is_ops_skeleton`` / ``_is_public_marketing_skeleton`` — the
     exact gates ``pick_template_id`` applies). Expect 16 public-home packs,
     8 ops packs, 3 filtered-on-both-surfaces packs matching
     ``UNREACHABLE_PACK_IDS``.
  4. Hub-variant fact: recipes with hub_variant=="app" must equal
     OPS_CONTRACT_RECIPE_IDS; the rest must equal MARKETING_RECIPE_IDS (this is
     what plan_phase's public-kind nulling keys on).
  5. Contract replay: ``resolve_product_kind_contract`` over probe briefs for
     each kind/subtype must yield exactly the three ops contract recipes for
     OPS_KINDS and marketing recipes for PUBLIC_KINDS, with the kind sets
     unchanged.
  6. Selection replay: for every reachable pack, ``pick_template_id`` probed
     with the pack's own industry_tags on its own surface must return that pack,
     and ``template_recipe_hint`` (the very function plan_phase calls) must
     return the pack's declared hint. The produced pairing (pack, hint) must be
     in the map — for public packs as the deterministic first entry.
  7. Exactness: map[pack] must EQUAL the derived compatible set (hint + the five
     marketing recipes for public packs; the three contract recipes for ops
     packs; declared hint only for unreachable packs). An extra entry would be
     aspiration, a missing one a producible pairing outside the map — both RED.
  8. Fallback-rotation fact: ``pick_recipe_id`` with no keyword signal rotates
     over all 8 recipes (each seed 0..7 hits a distinct recipe).
  9. Fail-closed pairing replay: ``apply_recipe_to_architect`` applies a pack's
     template_section_order to public-home ONLY when template_recipe_hint ==
     recipe_id (mismatch leaves slots untouched). This is the pairing semantics
     the map documents; behavior drift here invalidates the map.

JUDGMENT CALLS, STATED.
  * "Compatible" scopes to the pack as PRIMARY template on its own surface. Ops
    packs also gap-fill member/ops seed slots inside public-kind runs
    (plan_phase calls apply_ops_industry_template_to_plan unconditionally), but
    there the marketing recipe owns every rendered surface's composition and the
    pack contributes seed copy only — recorded here as a fact, excluded from
    the map, and any change to that exclusion is an owner call.
  * Probe briefs for the contract replay are minimal keyword bundles chosen to
    hit each classifier branch; they are inputs to the replay, not baked facts —
    the baked fact is the SET of recipes the contracts can emit.
  * The three unreachable packs carry their declared hint in the map so the map
    stays total; this census proves they are unreachable (both surface filters
    reject them) and RED-EXITS if that ever changes.

RED-EXIT on: pack/recipe corpus size drift, unknown ids either direction, an
empty compatible list, reachability drift, hub-variant drift, a contract or
selection replay producing a pairing outside the map, map-vs-derived
inequality, rotation not covering all 8, or the fail-closed guard not failing
closed.

Run (offline, documented shape):
  docker run --rm -v "/Users/maurice/Documents/Dev/BMV:/repo" -w /repo/backend \
    -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh \
    bmv-local-api -c 'python3 scripts/measure/compatible_recipes_census.py \
    --json-out /repo/docs/evidence/session25/compatible-recipes-census.json'

Read-only over the repo; writes only the optional --json-out file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.application.preview_app.design_recipes import (  # noqa: E402
    RECIPES,
    apply_recipe_to_architect,
    pick_recipe_id,
)
from app.application.preview_app.industry_templates import TEMPLATE_IDS  # noqa: E402
from app.application.preview_app.industry_templates.apply import (  # noqa: E402
    template_recipe_hint,
)
from app.application.preview_app.industry_templates.compatible_recipes import (  # noqa: E402
    COMPATIBLE_RECIPES,
    MARKETING_RECIPE_IDS,
    OPS_CONTRACT_RECIPE_IDS,
    UNREACHABLE_PACK_IDS,
)
from app.application.preview_app.industry_templates.loader import (  # noqa: E402
    _is_ops_skeleton,
    _is_public_marketing_skeleton,
    load_templates,
    pick_template_id,
)
from app.application.preview_app.product_kind import (  # noqa: E402
    OPS_KINDS,
    PUBLIC_KINDS,
    resolve_product_kind_contract,
)

# Baked corpus facts — a rerun on a changed corpus must die loudly, not adapt.
EXPECT_PACKS = 27
EXPECT_RECIPES = 8
EXPECT_PUBLIC_PACKS = 16
EXPECT_OPS_PACKS = 8
EXPECT_UNREACHABLE = 3

#: Probe briefs per contract branch (inputs to the replay, not baked facts).
CONTRACT_PROBES: tuple[tuple[str, str, str], ...] = (
    ("internal_ops/trading", "internal trading desk blotter oms for traders", "dense-ops-floor"),
    ("internal_ops/ops", "internal ops console back office staff only tool", "dense-ops"),
    ("saas_workspace/accounting", "saas accounting platform invoices ledger", "dense-ops-ledger"),
    ("saas_workspace/generic", "saas platform workspace dashboard software", "dense-ops"),
    ("booking_service", "salon appointment booking reserve a session", "warm-service"),
    ("storefront", "local pottery shop storefront browse and buy", "warm-service"),
)


def die(msg: str) -> None:
    print(f"\nRED-EXIT: {msg}", file=sys.stderr)
    print("RED-EXIT — the census refused to measure against drifted assumptions.")
    sys.exit(2)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json-out", default=None, help="write machine-readable results here")
    args = ap.parse_args()

    packs = load_templates()
    report: dict[str, object] = {"question": "every HEAD-producible pack->recipe pairing is in the map"}

    # 1. Corpus guards -------------------------------------------------------
    if len(packs) != EXPECT_PACKS:
        die(f"pack corpus drifted: loader serves {len(packs)}, census bakes {EXPECT_PACKS}")
    if set(packs) != set(TEMPLATE_IDS):
        die(f"loader ids != TEMPLATE_IDS registry: {set(packs) ^ set(TEMPLATE_IDS)}")
    if len(RECIPES) != EXPECT_RECIPES:
        die(f"recipe corpus drifted: {len(RECIPES)} recipes, census bakes {EXPECT_RECIPES}")
    if set(COMPATIBLE_RECIPES) != set(packs):
        die(f"map keys != pack ids: {set(COMPATIBLE_RECIPES) ^ set(packs)}")
    print(f"corpus: {len(packs)} packs, {len(RECIPES)} recipes, map total over both — OK")

    # 2. Id validity ---------------------------------------------------------
    for pid, recipes in COMPATIBLE_RECIPES.items():
        if not recipes:
            die(f"map entry for {pid} is empty")
        unknown = [r for r in recipes if r not in RECIPES]
        if unknown:
            die(f"map entry for {pid} references unknown recipe ids {unknown}")
        if len(set(recipes)) != len(recipes):
            die(f"map entry for {pid} has duplicates: {recipes}")
    print("ids: every mapped recipe id is a real RECIPES key, no empties/dupes — OK")

    # 3. Reachability replay (the loader's own surface gates) ----------------
    public_packs, ops_packs, unreachable = [], [], []
    for pid, pack in sorted(packs.items()):
        sk = str(pack.get("skeleton_id") or "")
        on_ops = _is_ops_skeleton(sk)
        on_public = _is_public_marketing_skeleton(sk)
        if on_ops:
            ops_packs.append(pid)
        elif on_public:
            public_packs.append(pid)
        else:
            unreachable.append(pid)
    if len(public_packs) != EXPECT_PUBLIC_PACKS:
        die(f"public reachable set drifted: {len(public_packs)} != {EXPECT_PUBLIC_PACKS}: {public_packs}")
    if len(ops_packs) != EXPECT_OPS_PACKS:
        die(f"ops reachable set drifted: {len(ops_packs)} != {EXPECT_OPS_PACKS}: {ops_packs}")
    if set(unreachable) != set(UNREACHABLE_PACK_IDS) or len(unreachable) != EXPECT_UNREACHABLE:
        die(f"unreachable set drifted: {sorted(unreachable)} != {sorted(UNREACHABLE_PACK_IDS)}")
    print(f"reachability: {len(public_packs)} public / {len(ops_packs)} ops / "
          f"{len(unreachable)} unreachable ({', '.join(sorted(unreachable))}) — OK")

    # 4. Hub-variant fact ----------------------------------------------------
    app_hub = {rid for rid, r in RECIPES.items() if str(r.get("hub_variant")) == "app"}
    marketing_hub = set(RECIPES) - app_hub
    if app_hub != set(OPS_CONTRACT_RECIPE_IDS):
        die(f"app-hub recipes drifted: {sorted(app_hub)} != {sorted(OPS_CONTRACT_RECIPE_IDS)}")
    if marketing_hub != set(MARKETING_RECIPE_IDS):
        die(f"marketing-hub recipes drifted: {sorted(marketing_hub)} != {sorted(MARKETING_RECIPE_IDS)}")
    print(f"hub variants: app={sorted(app_hub)} marketing={sorted(marketing_hub)} — OK")

    # 5. Contract replay -----------------------------------------------------
    contract_rows = []
    ops_contract_recipes, public_contract_recipes = set(), set()
    if OPS_KINDS != frozenset({"saas_workspace", "internal_ops"}):
        die(f"OPS_KINDS drifted: {sorted(OPS_KINDS)}")
    if PUBLIC_KINDS != frozenset({"storefront", "booking_service"}):
        die(f"PUBLIC_KINDS drifted: {sorted(PUBLIC_KINDS)}")
    for label, brief, expect in CONTRACT_PROBES:
        c = resolve_product_kind_contract(brief)
        contract_rows.append({"probe": label, "kind": c.kind, "subtype": c.subtype,
                              "recipe_id": c.recipe_id})
        if c.recipe_id != expect:
            die(f"contract probe {label!r} yields recipe {c.recipe_id!r}, census bakes {expect!r}")
        (ops_contract_recipes if c.kind in OPS_KINDS else public_contract_recipes).add(c.recipe_id)
    if ops_contract_recipes != set(OPS_CONTRACT_RECIPE_IDS):
        die(f"ops contract recipe set drifted: {sorted(ops_contract_recipes)}")
    if not public_contract_recipes <= set(MARKETING_RECIPE_IDS):
        die(f"public contract emitted a non-marketing recipe: {sorted(public_contract_recipes)}")
    print(f"contracts: ops emit exactly {sorted(ops_contract_recipes)}; "
          f"public emit {sorted(public_contract_recipes)} (marketing) — OK")

    # 6. Selection replay ----------------------------------------------------
    pairing_rows = []
    for pid in public_packs + ops_packs:
        pack = packs[pid]
        surface = "ops" if pid in ops_packs else "public"
        tags = " ".join(str(t) for t in (pack.get("industry_tags") or []))
        got = pick_template_id(industry=tags, surface=surface, seed=0, context="")
        if got != pid:
            die(f"selection replay: {pid} probed with its own tags returns {got!r} — "
                f"own-tags-select-self fact drifted")
        hint = template_recipe_hint(industry=tags, seed=0, surface=surface, context="")
        declared = str(pack.get("recipe_hint") or "")
        if hint != declared:
            die(f"template_recipe_hint({pid}) == {hint!r} != declared hint {declared!r}")
        if hint not in COMPATIBLE_RECIPES[pid]:
            die(f"HEAD-produced pairing OUTSIDE the map: {pid} -> {hint}")
        if surface == "public" and COMPATIBLE_RECIPES[pid][0] != hint:
            die(f"map order: {pid} deterministic hint {hint!r} is not first entry")
        pairing_rows.append({"pack": pid, "surface": surface, "picked": got, "hint": hint})
    # Unreachable packs: their own tags must NOT select them on either surface.
    for pid in unreachable:
        tags = " ".join(str(t) for t in (packs[pid].get("industry_tags") or []))
        for surface in ("public", "ops"):
            got = pick_template_id(industry=tags, surface=surface, seed=0, context="")
            if got == pid:
                die(f"unreachable pack {pid} became selectable on surface={surface}")
    print(f"selection replay: {len(pairing_rows)} reachable packs each self-select and "
          f"hint into the map; 3 unreachable stay unselectable — OK")

    # 7. Exactness: map == derived set per pack ------------------------------
    for pid in public_packs:
        derived = {str(packs[pid].get("recipe_hint") or "")} | set(MARKETING_RECIPE_IDS)
        if set(COMPATIBLE_RECIPES[pid]) != derived:
            die(f"map[{pid}] != derived public set: {sorted(set(COMPATIBLE_RECIPES[pid]) ^ derived)}")
    for pid in ops_packs:
        if set(COMPATIBLE_RECIPES[pid]) != set(OPS_CONTRACT_RECIPE_IDS):
            die(f"map[{pid}] != ops contract recipes")
    for pid in unreachable:
        if set(COMPATIBLE_RECIPES[pid]) != {str(packs[pid].get("recipe_hint") or "")}:
            die(f"map[{pid}] != declared hint for unreachable pack")
    print("exactness: every map entry equals its derived compatible set — OK")

    # 8. Fallback rotation fact ----------------------------------------------
    rotation = [pick_recipe_id(industry=None, business_description=None,
                               concept_name=None, seed=k) for k in range(len(RECIPES))]
    if sorted(rotation) != sorted(RECIPES):
        die(f"fallback rotation no longer covers all recipes: {rotation}")
    print(f"fallback rotation: seeds 0..{len(RECIPES)-1} cover all {len(RECIPES)} recipes — OK")

    # 9. Fail-closed pairing replay ------------------------------------------
    def _home_slots(hint: str) -> list[str]:
        arch = {"routes": [{"path": "/", "skeleton_id": "public-home",
                            "section_slots": ["hero", "features", "cta", "footer"]}]}
        plan = {"recipe_id": "craft", "hub_variant": "marketing",
                "template_section_order": ["hero", "showcase", "process", "cta", "footer"],
                "design_system": {"recipe_id": "craft", "template_recipe_hint": hint}}
        out = apply_recipe_to_architect(arch, plan)
        return list(out["routes"][0]["section_slots"])

    from app.application.preview_app.design_recipes import recipe_section_slots

    template_order = ["hero", "showcase", "process", "cta", "footer"]
    start = ["hero", "features", "cta", "footer"]
    # What HEAD does with the guard CLOSED: recipe's own order only.
    expect_closed = recipe_section_slots("public-home", RECIPES["craft"], start)
    # What HEAD does with the guard OPEN: template order applied on top.
    expect_open = recipe_section_slots(
        "public-home", {"section_orders": {"public-home": template_order}}, expect_closed
    )
    if expect_closed == expect_open:
        die("fail-closed replay is vacuous: template order equals recipe order")
    mismatched, matched = _home_slots("editorial"), _home_slots("craft")
    if mismatched != expect_closed:
        die(f"fail-closed guard drifted: mismatched hint produced {mismatched}, "
            f"expected recipe-only {expect_closed}")
    if matched != expect_open:
        die(f"matched hint did not apply template order: {matched} != {expect_open}")
    print(f"fail-closed pairing: mismatched hint keeps recipe face {mismatched}; "
          f"matched hint applies template order {matched} — OK")

    # ------------------------------------------------------------------------
    report.update({
        "packs": len(packs), "recipes": len(RECIPES),
        "public_packs": public_packs, "ops_packs": ops_packs,
        "unreachable_packs": sorted(unreachable),
        "marketing_recipes": list(MARKETING_RECIPE_IDS),
        "ops_contract_recipes": list(OPS_CONTRACT_RECIPE_IDS),
        "contract_probes": contract_rows,
        "deterministic_pairings": pairing_rows,
        "fallback_rotation": rotation,
        "map": {k: list(v) for k, v in sorted(COMPATIBLE_RECIPES.items())},
        "verdict": "PASS — every HEAD-producible pairing is in the map; map has no extras",
    })
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"json: {args.json_out}")
    print("\nVERDICT: PASS — map covers HEAD exactly "
          f"({len(public_packs)}x5 public + {len(ops_packs)}x3 ops + {len(unreachable)}x1 unreachable pairings).")


if __name__ == "__main__":
    main()
