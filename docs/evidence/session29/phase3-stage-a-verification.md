# Stage A claims re-verified on HEAD (`d85a660`) — holds, with five drifts

Session 29, 2026-08-09. The session-25 token inventory was recorded at
`c5249dc`; commits have landed since. Baseline diff: the token-resolution
files (`design_recipes.py`, `design_overlay.py`, `design_brief.py`,
`brand_palette.py`, `assemble.py`, `index_css.j2`, `recipe.ts`,
`package.json`, `MarketingHero.tsx`, `FeatureBento.tsx`) are **byte-identical**
to the evidence commit; drift is concentrated in `registry.ts`,
`catalogue.json`, `plan_phase.py`.

## Verified still true (implement A1/A3 against these)

1. **Multi-layer resolution stands as autopsied.** Recipe tokens as base at
   `assemble.py:844`, overlay `token_overrides` win via `dict.update` at
   :847-850, fonts :851-858, palette-when-locked :861-865, rendered through
   `index_css.j2` — and the unlayered `[data-recipe]` hard-codes still win
   in-browser (nocturne j2:204-220, craft j2:222-240).
   `merge_overlay_into_recipe` (`design_overlay.py:347`) has **zero call
   sites** repo-wide — still the dead layer A1 deletes.
2. **`brand_locked` is always True in practice.** Writers:
   `brand_brief.py:195` (literal True), `:118`; `design_brief.py:113→166`
   (OR), `:246` (restamp). No writer of False. Eight readers enumerated.
3. **Six `Record<RecipeId,…>` maps, all in `src/lib/recipe.ts`**: 29
   HERO_BY_RECIPE, 39 FEATURE, 48 SHELL, 57 NAV, 66 FOOTER, 75 BRAND — each
   keyed by the 6 recipe *families* (ledger/floor normalized at :88-96).
4. **`compatible_recipes.py` is still inert** — docstring still opens "INERT
   DATA, imported by nothing"; only a test and a census script import it.
   Its own docstring already cites `plan_phase` "~130-133", i.e. the map is
   more current than the roadmap.
5. **`motion` ^12.42.2 and `animejs` ^4.5.0 ship; Lenis absent** (zero hits).
6. **One fingerprint-keyed lockfile** (`npm_shared.py:29-44`): sha256 over
   template package.json+lock only → adding Lenis rotates the fingerprint
   for every generated site at once. A global decision, as ruled.
7. **`pick_recipe_id` fallback rotates over all 8** (`design_recipes.py:527-530`)
   while public kinds can only reach 5 marketing recipes — the A3 defect
   confirmed. Only production caller: `brand_brief.py:94`. Ops kinds get
   their recipe forced at `plan_phase.py:165`.

## The five drifts (the plan MUST use these, not the roadmap's refs)

1. **`'split'` is declared at SIX registry sites, not three**:
   `registry.ts:148, 496, 510, 542, 574, 618` + six mirrors in
   `catalogue.json` (285, 867, 938, 1008, 1086, 1199). No implementing
   branch anywhere; unconditional cinematic fallthrough at
   `MarketingHero.tsx:523-525`; doubly unreachable because
   `HERO_BY_RECIPE` never emits it and the variant-prop filter only lets
   `'item'` through.
2. **`registry.ts:148` and `:496` changed after the evidence commit**
   (`'item'` appended) — patches written against the old contents conflict.
3. **The public-kind null-out is `plan_phase.py:130-133`**, gate
   `hub_variant == "app"` at :132 (roadmap says 129-132).
4. **`MarketingHero.tsx:90-91` is the destructuring, not the discard** — the
   discard is `:94-96`, and `'item'` is *already honoured* there; every
   other caller-supplied variant is replaced by `recipeHeroVariant(recipeId)`.
   A2's "honour discarded props" is narrower than stated for this component.
5. **"Scroll to taste" is `MarketingHero.tsx:275`** (roadmap: 269; the file
   is unchanged, so the roadmap's ref was stale when written).

Also confirmed for A2's neighbor: `FeatureBento.tsx` discard exactly at
:51/:54-55 as recorded; voice strings 4-of-5 exact
(`BrandFooter.tsx:67`, `CatalogGrid.tsx:67-70`, `InquiryPanel.tsx:119,200`,
`CashPulseBar.tsx:27-28`).
