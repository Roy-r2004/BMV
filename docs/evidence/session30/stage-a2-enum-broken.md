# Stage A / A2 — the enum broken, props honoured, 'split' deleted (session 30)

Branch `phase3-stage-a`, on top of A1 (`89d81b8`). Implemented against the
HEAD verification's five drifts, not the roadmap's line numbers.

## What landed

**Maps become defaults; SiteSpec.design is the rendered value.** All six
`*_BY_RECIPE` maps in `src/lib/recipe.ts` survive as defaults; every accessor
now resolves `designVariant(SITE_DESIGN.variants.<axis>, <VALID_SET>, recipeId)
?? MAP[recipeId]`. `SITE_DESIGN` (emitted per preview by A1) answers only for
its own site's recipe family (`normalizeRecipeId` guard) and only with values
from the axis's declared valid set — emitted design is data, so consumption is
runtime-guarded, and an invalid value falls back to the map instead of
rendering garbage.

**The discarded props are honoured (3.1), narrowed per the HEAD verification:**

- `MarketingHero.tsx` — the discard at :94-96 already honoured `'item'`; the
  fix is "the rest": any caller variant in the accepted union
  (`HERO_VARIANTS` + `'item'`) is honoured; everything else falls back to the
  recipe's hero. (Request 163's class — a variant the component implements
  but the plumbing discarded — cannot recur.)
- `FeatureBento.tsx` — `variant: _variant` (the destructure-into-discard at
  :51,:54-55) now validates against `FEATURE_VARIANTS` and honours valid
  values; the recipe's composition stays the default.

**'split' DELETED at all twelve sites** — the ruling the plan left open
("implement for real or delete — a declared API that lies is the defect
either way") is taken as DELETE, because: (a) no signed design exists for a
real split hero — inventing a seventh hero composition is Stage C/D authoring,
and Stage A must not change or add looks; (b) deletion is provably
rendering-neutral — the variant was doubly unreachable (never emitted by
`HERO_BY_RECIPE`, discarded by the prop filter) and fell through to cinematic
when forced; (c) Stage B/D can re-admit it WITH an implementation. Removed
from: `MarketingHeroVariant` union, the component registry entry
(`registry.ts:148`), five skeleton `supportedVariants` lists (:496/510/542/
574/618 pre-edit), and the six `catalogue.json` mirrors — the catalogue was
REGENERATED via `python -m app.application.ui_registry --write`, never
hand-edited (its own header forbids it). The unrelated `ops-recon-split`
skeleton id is untouched (pinned at exactly 1 occurrence). The booking-side
skeleton that advertised only `['split', 'editorial']` now advertises
`['editorial']` — deletion only; nothing new is advertised.

**Validator interplay:** the registry enum is enforced by
`validate_catalogue_page_content` (request 163 died on exactly this wall), so
a model that still emits `variant="split"` is caught at validation — and if
one ever slipped through, the new runtime guards fall back to the recipe
default instead of the silent cinematic lie.

## Gates

| gate | result |
|---|---|
| Template typecheck | `tsc --noEmit -p tsconfig.app.json` exit 0 |
| Silhouette | **17/17 byte-identical** vs the branch-point baseline (A2 touches no CSS writer; proven, not assumed) |
| Full suite | run after A2 (see HANDOFF row; targeted blast-radius set — variant consumption, trio-162 pins, catalogue guards, drift, propshape, site_design — 64 passed first) |
| Mutation sweep | **9 killed / 0 survived** (`mutate_session30_a2.py`) — accessor bypass, family guard, validity guard, item-only regression, bento discard regression, registry split resurrection, catalogue hand-edit, map family loss, invalid emission |

## Equivalent mutant, proved with data

Swapping the Python emitter's variant SOURCE (`ds.get("hero_variant")` ↔
`resolved.get("hero_variant")`) is unkillable today: on the production chain
the sealed design_system's variants and the recipe's are value-identical for
**8/8 recipes** (measured via `_production_design_system` over all recipe ids
— see sweep docstring). They stay identical until Stage D varies values;
the A1 cross-language pin (variants == recipe.ts maps) holds either way.

## Test updates (honest accounting)

- `test_task3_catalogue_guards.py` — 5 occurrences of the fixture variant
  `"split"` (used as the *valid* example) switched to `"editorial"`; the
  tests' subjects (invented-prop rejection, invalid-literal rejection) are
  unchanged.
- New `test_recipe_variant_consumption.py` (7 tests): occurrence-counted
  split deletion; the inverse-direction registry⊆component pin that 'split'
  lived in the gap of; catalogue==regenerated pin (hand-edits die);
  per-axis SITE_DESIGN consumption + map completeness; both honour-props
  pins; emitted-variants-pass-guards end-to-end.
