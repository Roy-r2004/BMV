# Session 30 kickoff — run the validation trio, then open Phase 3 Stage A

Paste this whole file as the first message.

---

Read `HANDOFF.md`'s session 29 block first, then `docs/PHASE3_STAGE_A_PLAN.md`,
`docs/PHASE3_LICENSE_POLICY.md`, and the two evidence files they cite
(`docs/evidence/session29/phase3-stage-a-verification.md`,
`docs/evidence/session29/phase3-foundry-shortlist.md`). Everything below
assumes them; nothing below restates them in full.

**This session has two jobs, in a fixed order: (1) run and read the funded
validation trio on the frozen build; (2) open Phase 3 Stage A on a branch.**
The order is not preference — the trio validates nine session-29 mechanisms
plus the session-28 fixes on the generator as it exists at `cc6cee0`-era code,
and Stage A changes that generator. **Stage A work may start on the branch
before the trio reads out, but nothing merges to main until the trio's
readout is filed.**

## Settled — do not relitigate

- **`APPSPEC_MODE=on`, fallback disabled, degraded generic ship is a defect.**
  All standing.
- **The Stage A merge gate is the trio readout.** Ruled in
  `PHASE3_STAGE_A_PLAN.md`; the Phase 1 clock baseline is already banked
  (p50 559.0, 8/8 under 600), so nothing else blocks the merge.
- **License rulings (owner, 2026-08-09):** React Bits ADMITTED — its license
  explicitly permits distribution "as part of an application, website, or
  product"; bright line: the template's mined components are never published
  as a standalone kit; manifest rows say `MIT+Commons-Clause`, never `MIT`.
  Aceternity GATED — no findable license text; no ruling can cure absence.
  Stage B mining set: Magic UI 20 + React Bits picks (~26-30).
- **Session 26 rulings stand:** motion is a first-class axis; the workforce is
  agents; free-license only; Stage A consumes `compatible_recipes.py`;
  pack→recipe pairing stays fail-closed.
- **Phase 2 DoD 10** (zero upstream deaths over N consecutive funded runs,
  withholds tracked separately) — the streak starts with this trio. The
  owner has not yet set N / distinct-business spread / stress-brief scope;
  score the trio against the proposed N=10 and note the rulings as pending.

## Job 1 — the trio (blocked only on money)

At last probe the shared OpenRouter key was **overdrawn (−$0.063)**, and
something other than BMV spent $0.24 while idle — top up **≥ $5** so a
concurrent draw cannot starve a run mid-flight (trio ≈ $0.99).

Then follow **`docs/evidence/session29/TRIO_LAUNCH_RUNBOOK.md`** exactly. It
already contains: the executed preflight, launch order (top-up → one cheap
confirm call → restart `bmv-api` + behaviour probe → quiet host →
`session27/launch_trio.py` → bracket the balance), the readout order
(`readout_validation_trio.py <ids>` first), and the interpretation notes from
the pipeline sweep. Two of those notes are easy to forget:
`_FAILED_FIX_MODELS` is process-global (runs 2-3 may repair on a different
model — grep "already failed this process"), and the remeasure critic path
can ship `ready` with repaired pages unmeasured (check
`_bmv_visual_critique.json`).

**Known blind spot, expected, not a finding:** all three briefs are
`needs_ai: no`, so the AI-hub binder fixes cannot fire and absent salvage
markers in `heal_actions` prove nothing. File the readout in
`docs/evidence/session30/`, update the DoD 10 streak count, and move the
HANDOFF H1.

## Job 2 — Stage A, on branch `phase3-stage-a`

The plan is `docs/PHASE3_STAGE_A_PLAN.md`; execute A1→A4 in order. The
critical craft rule: **implement against
`phase3-stage-a-verification.md`, not against the roadmap's line numbers** —
five drifts are pinned there ('split' at SIX registry sites + six
catalogue.json mirrors; registry 148/496 dirty since the session-25
inventory; plan_phase null-out at 130-133; `MarketingHero`'s discard at
:94-96 already honours `'item'`; "Scroll to taste" at :275).

- **A1** — one Python resolution into `SiteSpec.design`; delete the losing
  layers including dead `merge_overlay_into_recipe` (`design_overlay.py:347`,
  zero call sites). The resolution files are byte-identical to the session-25
  autopsy, so its design holds as written.
- **A2** — the six `Record<RecipeId,…>` maps (`src/lib/recipe.ts:29-83`,
  keyed by the 6 recipe *families*) become defaults; honour the discarded
  props (`FeatureBento.tsx:51,54-55`; MarketingHero "the rest", not `'item'`);
  implement `'split'` for real at all six declaration sites or delete the
  declaration — a declared API that lies is the defect either way.
- **A3** — packs gain `compatible_recipes`; `pick_recipe_id` (single
  production caller: `brand_brief.py:94`) rotates over the *reachable* set.
  The map already covers 27 packs and imports nothing from `app/` — this is
  consumption, not authoring.
- **A4** — `PROVENANCE.json` (empty array) + the guard pytests from
  `PHASE3_LICENSE_POLICY.md` + `ATTRIBUTIONS.md` generation, so Stage B
  cannot start unmanifested.

**Stage A adds NO dependencies.** Lenis is Stage B, and the npm lockfile
fingerprint (`npm_shared.py:29-44`) is global — rotating it cold-starts the
shared cache for every run, which voids clock numbers if it happens before
the trio.

## Gates — every change

- **Full suite green.** Baseline **2,337 passed / 1 skipped / 0 failed**.
  Exactly this invocation; anything else lies:

      docker run --rm -v "$PWD:/repo" -w /repo/backend \
        -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template \
        --entrypoint sh bmv-local-api -c 'pip install -q pytest; python -m pytest tests/ -q'

  Never `docker compose exec api`; always `cd` to the repo root first. Do
  not run suites or sweeps while the trio is in flight.
- **A mutation sweep per fix, zero survivors**, anchors verbatim,
  occurrence-counted (MISCOUNT ≠ SKIP). Equivalent mutants proved with data.
- **The Stage-A no-regression gate:** render the six public recipes on one
  brief before and after — **byte-identical CSS custom-property output** for
  unchanged recipes. Stage A is plumbing; if it changes what any recipe looks
  like today, that is a Stage A defect.
- Evidence file per finding in `docs/evidence/session30/`.

## Traps this project has paid for

- `app.domain.appspec` ↔ `app.application.appspec` import cycle — enter via
  the application package in every new test/script.
- Restart `bmv-api` and prove **behaviour, not presence** — uvicorn holds old
  modules; `docker exec python` reads the mount fresh and will lie about
  what the server runs.
- Read live config from the running process, never from files.
- Parallel sessions share the checkout: explicit pathspecs only; verify
  provenance of unexpected files.
- Count the whole artifact, never a sampled window; read `ai_usage_events`
  by `finish_reason`, never run outcomes; rejected `app_spec_revisions`
  include heal audit rows — read `terminal_reason` on the FINAL revision
  before calling anything a death.
- Test fixtures are the usual mutation survivor — before believing a green
  test, check it can fail.
- The OpenRouter key is shared: bracket every run with a balance probe,
  attribute only the delta, no leak alarms.
- `apply_workspace_guards` runs before every build attempt — nothing
  networked or non-idempotent goes in it (grep-proven clean; keep it so).

## Definition of done

1. Trio run, bracketed, read out per the runbook; readout + evidence filed;
   DoD 10 streak updated; any death root-caused the same session.
2. Stage A A1-A4 landed on `phase3-stage-a` with every gate green, including
   the byte-identical silhouette gate.
3. Merge to main if and only if the trio readout is clean for the fixed
   classes (upstream deaths from fixed classes = 0); otherwise the readout's
   findings outrank Stage A and get fixed first.
4. `HANDOFF.md` updated with the H1 moved; roadmap Stage A rows updated with
   commit hashes.
