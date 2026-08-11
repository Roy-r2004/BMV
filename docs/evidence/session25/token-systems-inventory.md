# Three-token-systems inventory (Session 25, roadmap 3.5 — analysis half)

**Question.** Where does each of the three design-token systems WRITE tokens, in what order, who wins,
and is the roadmap claim right: *"design_overlay's six font pairs are unreachable (brand_locked always
true), its ten token overrides wipe the recipe's identity, and two recipes hard-code their palette back
in CSS."*

**Method.** Pure code reading (offline session, no generation, no DB). Every row cites file:line in the
repo at commit c5249dc. READ access only into `backend/preview-template/**`; nothing edited anywhere.

**Verdict.** The claim is **substantiated on all three parts**, with three refinements (§6).

---

## 1. The three systems and their write sites

### System A — palette / recipe (`brand_palette.py` + `design_recipes.py`)

| what | where written |
|---|---|
| 6 palette hexes (primary, secondary, background, surface, text, muted), contrast-solved from the business name | `backend/app/application/preview_app/brand_palette.py:155-189` (`palette_for_index`), entry `derive_palette` :192-197 |
| 8 recipes × 10 kit tokens (`radius_ui, bg_mix, fg_mix, muted_mix, border_mix, shadow, shadow_alpha, glow, card, atmosphere`) | `backend/app/application/preview_app/design_recipes.py` — editorial :19-33, dense-ops :80-95, dense-ops-ledger :139-153, dense-ops-floor :195-210, warm-service :250-265, bold-retail :310-325, nocturne :367-382, craft :425-438 |
| 8 recipes × font pair (sans/display/import) | `design_recipes.py` — :14-18, :75-79, :134-138, :190-194, :245-249, :305-309, :362-366, :420-424 |
| plan stamp: `recipe_id` :559, `hub_variant` :560, **fonts :563-569 (DEAD, see §4)**, `border_radius` :570, `style_keywords` :571, `hero_variant`/`feature_variant` :572-573, chrome (`shell_chrome`,`nav_variant`,`footer_variant`,`brand_placement`) :575-579, `recipe_prompt` :580, plan-level `design_direction` :584-586 | `design_recipes.py:537-587` (`apply_recipe_to_plan`) |

Note: `derive_palette` is *invoked by* brand_brief (`brand_brief.py:89-92`); the palette hexes travel
into `design_system` only through the brief (System C). The recipe's kit tokens travel through
`write_index_css` (§3).

### System B — design_overlay (`design_overlay.py`)

| what | where written |
|---|---|
| 6 moods × font pair | `backend/app/application/preview_app/design_overlay.py` — calm_air :29-33, warm_paper :65-69, bold_ink :100-104, ledger_light :137-141, night_floor :174-178, soft_glass :210-214. (6 configured pairs; **5 distinct** — ledger_light and night_floor are the identical IBM Plex Sans pair.) |
| 6 moods × the same 10 kit-token keys as recipes | `design_overlay.py` — :34-48, :70-84, :105-119, :142-157, :179-195, :215-232; seed micro-tweak of `radius_ui`/`glow` :277-282 |
| plan stamp: `design_overlay_id/label/blurb` :316-318, `density` :319, **`token_overrides` (all 10 keys) :320**, **fonts :322-331 (DEAD, see §4)**, no-op setdefault fonts :334-335, `border_radius` :336, `style_keywords` append :337, plan-level `design_overlay` :339-343 | `design_overlay.py:293-344` (`apply_design_overlay_to_plan`) |
| `merge_overlay_into_recipe` :347-371 | **DEAD CODE — zero call sites** in backend/app (repo-wide grep); `assemble.write_index_css:848-858` re-implements the same merge inline |

### System C — brand_brief (`brand_brief.py`)

| what | where written |
|---|---|
| brief: `locked: True` :118 (unconditional), `palette` :121 (from System A's `derive_palette` :89-92), `typography` :122-131 (**fonts copied from the brief-time recipe** :100-104, chosen at :94-99) | `brand_brief.py:62-146` (`build_brand_brief`) |
| demo sync: `visual_theme.primary_color/secondary_color/background_color/font_style/style` :169-173 | `brand_brief.py:149-175` (`ensure_brand_brief`) — called **unconditionally** at `pipeline/appspec_gate.py:197` and `pipelines/visual_demo.py:64` |
| design_system: `primary_color … muted_text_color` :184-189, `font_family/display/import_url/sans/display` :190-194, **`brand_locked: True` :195 (unconditional literal)**, `mood/voice/signature/avoid/rules/recipe_id` :197-202 | `brand_brief.py:178-203` (`design_system_from_brief`) |
| plan stamp: replaces `design_system` wholesale :226, but preserves 7 recipe composition fields (`hub_variant, hero_variant, feature_variant, recipe_prompt, style_keywords, border_radius, recipe_id`) :213-223; prepends signature to `design_direction` :229-232 | `brand_brief.py:206-238` (`apply_brief_to_plan`) |

### Carrier — sealed design brief (`design_brief.py`, collapses all three; not a fourth identity)

`seal_design_brief` (:89-204): palette :115-126 and typography :127-140 prefer `design.*` (i.e. what the
three systems already stamped) with brand-brief fallback; `brand_locked` :113+:166; `token_overrides`
:196; `border_radius` :197. `apply_sealed_brief_to_plan` (:207-275) restamps everything, incl.
`brand_locked` :246 and `token_overrides` :256-257.

---

## 2. Write order on the one production path (`pipeline/plan_phase.py`)

`orchestrator.py:105-106` runs `run_appspec_gate` then `run_plan_phase` — always.

1. appspec_gate: `ensure_brand_brief` **unconditional** → `ctx.brand_brief` never empty (`appspec_gate.py:197-209, 234`)
2. `apply_brief_to_plan` — `plan_phase.py:111` → **`brand_locked=True` is on the plan from here on**
3. `apply_product_kind_to_plan` — :119
4. `apply_recipe_to_plan` — :142 (recipe_id = brief's, unless suppressed :130-133 or template/kind override :134-141; ops kinds force `plan["recipe_id"]=kind_contract.recipe_id` :165)
5. industry/ops template packs — :153-181
6. `apply_brief_to_plan` again on the manifest design_system — :237-244 (re-locks palette/type over pack writes)
7. `apply_design_overlay_to_plan` — :250-256
8. `seal_design_brief` + `apply_sealed_brief_to_plan` — :264-265
9. codegen → `apply_workspace_guards` (`pipeline/polish_phase.py:28-31`) → `write_index_css` (`safety/orchestrator.py:214-222`) merges: recipe tokens as base (`assemble.py:844`) ← overlay `token_overrides` win (:848-850) ← ds fonts (:851-860) ← ds palette when `brand_locked` (:861-865) → renders `templates/codegen/index_css.j2`
10. Browser: Tailwind `@theme` vars (j2:5-23, layered) ← **unlayered `[data-recipe=…]` hard-code blocks win** (j2:204-239). `data-recipe` is stamped on `<html>` by `preview-template/src/main.tsx:9` from `RECIPE_ID` written by `assemble.write_recipe_id:819-828` (family-normalized: `dense-ops-ledger/-floor` → `dense-ops`, `preview-template/src/lib/recipe.ts:88-96`).

Gap-fill only: `safety/runtime.py:34-82` re-inserts hard default token values if a CSS var is missing
from index.css (normally a no-op after step 9 — defaults there are constants, not recipe values).

---

## 3. The token table

Legend: **winner** = last effective writer on the production path. j2 = `backend/app/templates/codegen/index_css.j2`.

| token | who writes it (system, file:line) | write order / who wins | collides with | reachable or dead |
|---|---|---|---|---|
| `primary_color` → `--color-brand`,`--color-ring`,`--treatment-light` + all mixes (j2:6-8,10-11,14,19-21) | palette via brand_brief (`brand_palette.py:170-173` → `brand_brief.py:89,121,184`); sealed `design_brief.py:116,228`; CSS `assemble.py:861-863` | brand_brief always wins (`brand_locked` gate at `assemble.py:861`) | `page_experience.py:570` or-fallback (inert when locked); `visual_theme` (overwritten `brand_brief.py:169`) | REACHABLE — survives even under nocturne/craft (only its *mixes* are defeated, §5) |
| `secondary_color` → `--color-brand-dark`,`--color-accent`,`--color-chart` (j2:12-13,15) | palette via brand_brief (`brand_palette.py:174-180` → `brand_brief.py:185`); CSS `assemble.py:864-865` | brand_brief | same as above | REACHABLE |
| palette `background`/`surface`/`text`/`muted` hexes | palette via brand_brief (`brand_palette.py:181-189` → `brand_brief.py:186-189`) | brand_brief (unopposed in design_system) | **nothing in CSS — index_css.j2 never reads them**; `--color-background/foreground/muted` are recomputed from `primary`+mixes (j2:6-8) | PROMPT-ONLY. The contrast-solved background/text/muted never become CSS variables; they reach LLM prompts (`generate.py:815-821`) and mock.ts only |
| `bg_mix`,`fg_mix`,`muted_mix`,`border_mix` (j2:6-8,10) | recipe (`design_recipes.py` token dicts §1A); overlay (`design_overlay.py` mood dicts §1B → `token_overrides` :320 → sealed `design_brief.py:256` → `assemble.py:848-850`) | **overlay wins all four** — every mood defines every key, `dict.update` replaces the recipe value | each other; then nocturne/craft CSS hard-codes discard the computed result (§5) | overlay values REACHABLE; recipe values DEAD in CSS (only used if an override key were missing — never happens) |
| `card` → `--color-card` (j2:9) | recipe; overlay (same chain) | overlay | nocturne `#16131a` j2:208 / craft `#ffffff` j2:226 hard-codes win in browser | overlay value reachable on 6 of 8 recipe families; DEAD under nocturne/craft |
| `atmosphere` → `--recipe-atmosphere` (j2:22) | recipe; overlay | **overlay** — a mood atmosphere replaces the recipe's on every run | nocturne paints the overlay's (often light) gradient over its hard-coded `#0a090c` background (j2:211-214) — the visible mismatch class | overlay reachable; recipe atmospheres DEAD |
| `shadow`,`shadow_alpha`,`glow` (j2:19-20) | recipe; overlay (glow seed-tweaked `design_overlay.py:281-282`) | overlay | — | overlay reachable; recipe DEAD |
| `radius_ui`/`border_radius` → `--radius-ui` (j2:18) | recipe (`design_recipes.py:570`); overlay (`design_overlay.py:280,336`, seed-tweaked :277-280); brief preserves earlier value (`brand_brief.py:213-223`); sealed `design_brief.py:254-255` | overlay | craft hard-code `--radius-ui:0.25rem` j2:228 wins in browser | overlay reachable except craft (DEAD there) |
| `font_sans`,`font_display`,`font_import(_url)`,`font_family`,`display_font_family` (j2:1,16-17) | brand_brief carrying its brief-time recipe's pair (`brand_brief.py:100-104,122-131,190-194`); recipe direct (`design_recipes.py:563-569` — **DEAD**); overlay (`design_overlay.py:322-331` — **DEAD**, :334-335 setdefault no-op); sealed `design_brief.py:127-140,236-245`; CSS `assemble.py:851-860` | brand_brief (i.e. the recipe picked at brief time, `brand_brief.py:94-99`) | final recipe may differ from brief recipe (`plan_phase.py:130-151,165`) → shipped fonts can belong to a different recipe than shipped composition/CSS family; per-family `font-display` styling j2:174-198 | brief chain REACHABLE; recipe-direct and all 6 overlay pairs DEAD (§4) |
| `density` | overlay only (`design_overlay.py:319`; sealed :190,:252) | overlay | none | REACHABLE (prompt/composition lane) |
| `style_keywords` | recipe (`design_recipes.py:571`); brief preserves (`brand_brief.py:213-223`); overlay appends label (`design_overlay.py:337`) | concatenation — both survive | — | REACHABLE |
| `hero_variant`,`feature_variant`,`hub_variant`, chrome quad | recipe only (`design_recipes.py:560,572-579`); sealed `design_brief.py:171-179,221-227` | recipe | none — composition is the recipe's uncontested lane | REACHABLE |
| `mood`,`voice`,`signature`,`avoid`,`rules` | brand_brief only (`brand_brief.py:113-145,197-201`); sealed :191-193,:247-251 | brand_brief | none | REACHABLE (prompt lane) |
| `design_direction` | recipe (`design_recipes.py:584-586`), brief prepend (`brand_brief.py:229-232`), packs, then sealed **replaces** with composed direction (`design_brief.py:203,274`) | sealed brief | historical string-concat mush — the seal exists to end it | REACHABLE |
| `visual_theme.*` (demo lane) | brand_brief (`brand_brief.py:169-173`) | brand_brief overwrites whatever the demo model produced | upstream demo enrichment | REACHABLE |
| `brand_locked` | `brand_brief.py:118` (`locked: True`), `brand_brief.py:195` (`brand_locked: True`), `design_brief.py:113→166` (OR of the two), `design_brief.py:246` (restamp) | always `True` (§4) | readers: `design_recipes.py:558,562`; `design_overlay.py:321`; `assemble.py:861`; `page_experience.py:569`; `generate.py:808`; `plan_phase.py:275` | the *only* four assignment sites; none can write `False` on a pipeline run |

---

## 4. (b) What `brand_locked: True` makes unreachable — and proof it is always True

**Every assignment site** (complete, from repo-wide grep of `brand_locked`/`locked`):

1. `brand_brief.py:118` — `"locked": True`, unconditional literal in `build_brand_brief` (no failure path; deterministic, no model call).
2. `brand_brief.py:195` — `"brand_locked": True`, unconditional literal in `design_system_from_brief`.
3. `design_brief.py:113` → `:166` — `bool(design.brand_locked or brand.locked)`; on the pipeline path both operands are True.
4. `design_brief.py:246` — `bool(sealed.brand_locked)` restamp; True whenever site 3 was.

`ensure_brand_brief` runs unconditionally on both entry paths (`appspec_gate.py:197` for every
generation; `pipelines/visual_demo.py:64` at demo time), and `plan_phase.py:110`'s `if brand_brief:` is
therefore always taken. **No site in the codebase writes `brand_locked=False`.** It is falsy only in
code paths that never received a brief — unit tests and direct calls, not production runs.

**Dead branches under the lock:**

- `design_recipes.py:563-569` — recipe's direct `font_family`/`display_font_family`/`font_import_url` writes. (Recipe fonts still ship, but only via the brief's snapshot, `brand_brief.py:100-104` — of the *brief-time* recipe.)
- `design_overlay.py:322-331` — **all six mood font pairs** (`calm_air` :29-33, `warm_paper` :65-69, `bold_ink` :100-104, `ledger_light` :137-141, `night_floor` :174-178, `soft_glass` :210-214) plus their `font_import_url`s can never ship. Honest count: 6 configured pairs, 5 distinct (ledger_light ≡ night_floor).
- `design_overlay.py:334-335` — the locked-branch `setdefault`s are permanent no-ops (the brief always sets `font_sans`/`font_display` first, `brand_brief.py:190-194` via `plan_phase.py:111`).
- `page_experience.py:572-584` — the not-locked normalization branch (fallback `#0f766e` etc.).

Conversely, `assemble.py:861-865` and `generate.py:808-829` are *only*-when-locked branches — always active.

---

## 5. (c) Hard-coded CSS that defeats all three systems

Two recipes re-declare the surface variables with literal hexes, in **unlayered** author CSS that beats
Tailwind's layered `@theme` output; `data-recipe` sits on `<html>` (`preview-template/src/main.tsx:9`)
so the override is global:

1. **nocturne** — `templates/codegen/index_css.j2:204-215` (+ `.font-display` color `#f7f2ea` :216-220): `--color-background:#0a090c`, `--color-foreground:#f4f0ea`, `--color-muted` (mix of `#f4f0ea`), `--color-card:#16131a`, `--color-border-subtle` (mix with `#2a2430`). 5 variables.
2. **craft** — `templates/codegen/index_css.j2:222-229`: `--color-background:#f3f0ea`, `--color-foreground:#171512`, `--color-muted:#625c54`, `--color-card:#ffffff`, `--color-border-subtle:#ddd6cb`, **`--radius-ui:0.25rem`**. 6 variables.
3. **craft (template copy)** — `backend/preview-template/src/index.css:297-304`, identical values (teammate lane — see FILED). The **nocturne block is absent from the template copy**, although j2:61 claims the files are "kept in sync" (see FILED).

What they defeat, for every preview on those recipes:

- System A (palette): the brand-tinted `--color-background/foreground/muted/border-subtle` computed from the derived `primary` (j2:6-10) are discarded. Only `--color-brand/-accent/-ring/-chart` survive.
- System B (overlay): its winning `bg_mix/fg_mix/muted_mix/border_mix/card` values (and for craft, its seed-tweaked `radius_ui`) are computed at generation time and then discarded in the browser. Its `atmosphere` *does* survive — painted over nocturne's hard-coded `#0a090c`, which is the mismatch class (a light mood atmosphere over a dark hard-coded floor).
- System C (brand_brief): its rule "never hardcode hex colors" (`brand_brief.py:142-144`) is violated by the pipeline's own stylesheet.

Ironic note: after the overlay wipe (§3), these hard-coded blocks are the *only* reason nocturne still
looks dark and craft still looks stone — the hard-coding compensates for the wipe.

---

## 6. Answers to the roadmap claim

- **(a) Tokens written by 2+ systems (the actual fight):** the 10 kit tokens (recipe vs overlay — overlay wins 10/10, every run, because every mood defines every key: `assemble.py:848-850`); fonts (brand_brief vs recipe-direct vs overlay — two of the three writers dead); `border_radius` (recipe → overlay → craft CSS); `style_keywords` (recipe + overlay concat); `design_direction` (recipe/brief/packs → sealed replaces); and in the browser, `--color-background/foreground/muted/card/border-subtle` (all-three-systems' computed values vs 2 recipes' hard-codes).
- **(b) brand_locked:** always True in production — 4 assignment sites, all unconditional-True or propagation; zero False-writing sites (§4). Kills recipe-direct fonts, all six overlay font pairs, and the page_experience fallback branch.
- **(c) hard-coded CSS:** nocturne + craft in `index_css.j2:204-229` (every generated app), craft duplicated in `preview-template/src/index.css:297-304`; nocturne missing there despite the "kept in sync" comment (j2:61).
- **Refinement 1:** the six overlay font pairs are 5 distinct (ledger_light ≡ night_floor).
- **Refinement 2:** the palette system's contrast-solved `background/text/muted/surface` hexes never become CSS variables at all — `index_css.j2:6-8` recomputes surfaces from `primary` + mix tokens; the solved hexes are prompt/mock-only. The claim understates the palette system's reach: only 2 of its 6 colours (`primary`, `secondary`) reach CSS.
- **Refinement 3:** shipped fonts belong to the *brief-time* recipe (`brand_brief.py:94-104`), while the final recipe id — and therefore the `[data-recipe]` CSS family and composition — can be changed afterwards (`plan_phase.py:130-151,165`), so font identity and CSS family can legitimately diverge on ops/template overrides.
- **Dead code:** `merge_overlay_into_recipe` (`design_overlay.py:347-371`) has zero call sites; `assemble.write_index_css:848-858` re-implements it. Removal is a code move — out of scope this session, flagged for the roadmap.

*Session 25 · offline · read-only · no generation runs. Author: 3.5-analysis subagent.*
