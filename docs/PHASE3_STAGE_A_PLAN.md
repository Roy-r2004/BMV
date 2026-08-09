# Phase 3 Stage A — execution plan (prepared 2026-08-09, session 29)

Stage A is the plumbing: one Python resolution into `SiteSpec.design`, the
enum broken, `compatible_recipes` consumed per ruling, and the license
policy + provenance manifest live. This plan was prepared during the
no-generation window while the validation trio waits on a top-up.

## Sequencing — the one hard rule

**Stage A does not merge until the validation trio has run on the frozen
build.** The trio validates sessions 28-29 (nine mechanisms) on the generator
as it exists at `d85a660`-era code; Stage A changes the generator, and
landing it first makes the trio's read-outs unattributable. Work happens on a
branch (`phase3-stage-a`); the merge gate is the trio's readout filed in
evidence. The Phase 1 clock baseline (p50 559.0, 8/8 under 600) is already
banked, so nothing *else* blocks the merge.

## The work, in landing order

### A1 — `SiteSpec.design`: one resolution, in Python, once
Today the design tokens are resolved by competing layers (recipe defaults,
overlay, brand kit) and the losing layers still exist in code. A1 collapses
this to a single resolution function that emits a complete, explicit
`SiteSpec.design` — type ramp, spacing scale, container width, grid logic,
image treatment, motion identity (placeholder values until 3.10) — and the
template consumes ONLY that. Delete the losing layers, including dead
`merge_overlay_into_recipe`.
*Verification of current-state claims: see `phase3-stage-a-verification.md`
(HEAD re-check of the session-25 inventory) — implement against what IS,
not against the inventory's snapshot.*

### A2 — break the enum (roadmap 3.1)
The per-recipe `Record<RecipeId,…>` maps in the template become *defaults*;
the rendered value comes from `SiteSpec.design`. Honour the props the kit
currently discards; implement the declared-but-unimplemented `'split'` hero
variant (today it silently falls through to cinematic — a declared API that
lies). **Per the HEAD verification:** all six maps live in
`src/lib/recipe.ts:29-83` keyed by the 6 recipe families; `'split'` is
declared at SIX registry sites (not the roadmap's three) plus six
`catalogue.json` mirrors; and `MarketingHero`'s discard at `:94-96` already
honours `'item'`, so its fix is "honour the rest", not "honour at all".
Registry lines 148/496 changed after the session-25 inventory — patch
against HEAD, not the inventory.

### A3 — consume `compatible_recipes` (roadmap 3.2, per ruling)
Packs gain `compatible_recipes: [ids]`; `pick_recipe_id`'s fallback rotates
over the *reachable* set (today it rotates over eight, three of which are
nulled downstream for public kinds — a fallback that can pick the
unpickable). Do NOT decouple pack order from recipe: the fail-closed pairing
("pottery → agency stack" must fail loudly) is deliberate. **Per the HEAD
verification:** the map already covers 27 packs and is still imported by
nothing in `app/`; the null-out gate is `plan_phase.py:130-133`
(`hub_variant == "app"` at :132); `pick_recipe_id`'s only production caller
is `brand_brief.py:94` — one call site to change.

### A4 — license policy + provenance manifest live
`docs/PHASE3_LICENSE_POLICY.md` (written) + `PROVENANCE.json` (empty array
lands with the guard pytest suite): manifest/allowlist/pin rules enforced by
tests from day one, so the Stage B foundry cannot start unmanifested.

## Gates per item (same as every session)
Full suite green at the exact invocation; mutation sweep per behavior change,
zero survivors; evidence file with numbers. A2 additionally needs a
**silhouette snapshot**: render the six public recipes on one brief before
and after — byte-identical CSS custom-property output for unchanged recipes
is the no-regression proof (A1/A2 are refactors until Stage D varies values).

## Explicitly deferred out of Stage A
- Motion engine, Lenis, scroll primitives (Stage B — and Lenis is a global
  lockfile decision gated on the license policy).
- Any new component mining (Stage B, blocked on A4's manifest guards).
- Voice props (3.0a — Stage D, after the Stage C sign-off).
- Any change to values the recipes render today: Stage A is plumbing;
  variety arrives in Stage D. If Stage A changes what any current recipe
  looks like, that is a defect in Stage A.

## Inputs standing ready
- `phase3-stage-a-verification.md` — HEAD state of every claim (session 29).
- `phase3-foundry-shortlist.md` — MIT-verified mining candidates for Stage B
  (session 29).
- `compatible_recipes.py` + census, 20-brief corpus (`980ca63`),
  `token-systems-inventory.md`, `motion-feasibility.md`.
- Owner artifacts: STACKLAB/MAILLARD motion bar, static-bones candidate
  sheet (Stage C pacing, not Stage A).
