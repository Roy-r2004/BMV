# Stage A / A3 — compatible_recipes consumed (session 30)

Branch `phase3-stage-a`, on top of A2 (`4202abe`). Consumption, not authoring
— the map (27 packs, census-pinned) is byte-unchanged except its docstring,
which now states the two consumers instead of claiming inertness.

## What landed

1. **Packs gain `compatible_recipes`.** `loader.load_templates` stamps the
   map's row onto every loaded pack (single attach point — `get_template`
   flows through it). Packs never author the field themselves: zero did
   (grep-proven), and a new pin fails the suite if one ever does — the map
   module stays the single source, per its own 27-unexplained-copies design
   note. A pack the map doesn't know would carry `()`, and the existing
   map-corpus pin (set equality over pack ids) red-exits before that can be
   reached.
2. **`pick_recipe_id`'s fallback rotates over the REACHABLE set** —
   `MARKETING_RECIPE_IDS`, not all eight. The old rotation spent seeds
   1-3 (mod 8) on `dense-ops*`, which public kinds null downstream
   (`plan_phase.py:130-133`) — "a fallback that can pick the unpickable."
   The keyword path is UNTOUCHED: ops recipes stay reachable on keyword hits
   at brief time, and the null-out remains the guard for false hits. The
   fail-closed hint-match pairing in `apply_recipe_to_architect` is
   untouched ("pottery → agency stack" still fails loudly).

## Behavior change, stated precisely

Only the no-keyword-hit fallback changes. For public runs (92.6 % of the
corpus) every fallback slot now lands a recipe the run can keep — previously
3 of 8 slots produced a brief recipe that was nulled AND shipped that dead
recipe's FONTS (the session-25 autopsy's refinement 3: font identity
diverging from CSS family). For ops runs the brief recipe was always
overridden at `plan_phase.py:165`; only brief-time fonts shift, and under the
old rotation 5 of 8 ops fallback slots already shipped marketing fonts — the
divergence class is pre-existing and narrow (ops = 7.4 % of runs × zero-
keyword briefs only). The gate brief ("bakery") hits keywords, so the
silhouette chain is untouched — proven below, not assumed.

## Gates

| gate | result |
|---|---|
| Silhouette | **17/17 byte-identical** vs branch-point baseline |
| Full suite | green after A3 (see HANDOFF row; targeted 32-test blast radius first) |
| Mutation sweep | **5 killed / 0 survived** (`mutate_session30_a3.py`) — fallback-all-8 regression, frozen rotation, loader stamp removal, marketing-set membership, keyword-path bypass |

## Equivalent mutants, recorded not forced

- Stamp `=` → `setdefault`: unkillable while zero packs author the field —
  the never-author pin guards that half directly.
- `compatible_recipes_for`'s unknown-id default: unreachable while the
  map-corpus pin holds set equality over pack ids.
- Public-pack list ORDER (hint-first) is asserted nowhere behavioral yet —
  rotation-within-pack is not a Stage A consumer; noted for the stage that
  adds one.

## New tests

`test_compatible_recipes_consumption.py` (6): reachable-set rotation +
full coverage over 5 seeds; reclaimed seeds 1-3; per-seed determinism;
ops-keyword reachability pin; every-pack-carries-map-row (incl.
`get_template`); packs-never-author pin. `test_compatible_recipes_map.py`
docstring updated (consumed, not inert); its 5 pins unchanged.
