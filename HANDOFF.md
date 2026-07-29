# Session handoff — preview quality: from "gates green" to "actually looks good" (2026-07-29)

Successor to [docs/handoffs/2026-07-29-v2-removal.md](docs/handoffs/2026-07-29-v2-removal.md)
(archived, still accurate on branch/deploy constraints). Process notes, not product docs.
The permanent record of *why* the pipeline shipped bad output is
[docs/PREVIEW_QUALITY_FINDINGS.md](docs/PREVIEW_QUALITY_FINDINGS.md) — read that first.

## TL;DR

Preview request 36 — `status=ready`, `quality gate PASSED`, recorded by the previous handoff as
meeting or beating the 8.5/10 reference on every measured axis — **was not shippable to an
investor.** Its hero image was a dental clinic. Its "Featured Works" cards, captioned *Crimson
Tide*, *Emerald Depths* and *Desert Bloom*, were dentures in surgical gloves, a dentist beside a
"Smile" sign, and oral surgery in progress. It carried **59 TypeScript errors**, seven image
paths that resolved to HTML, four empty credential cards on four separate pages, and a hero
headline rendered white-on-white.

Every one of those measurements was accurate. Every one was blind to the page.

Root cause in one line: **nothing in the pipeline ever looked at the artifact.** Twelve substring
matches over source text, one `is_file()`, and a policy flag. The only component that rendered
pixels could not fail a build. The compiler that would have caught 59 contract violations in
seconds was never run.

The design system is genuinely strong — confident editorial typography, a deep green palette,
generous whitespace, tasteful motion. Nothing needed redesigning. Every defect was content
correctness.

## Branch and deploy constraints — unchanged, still binding

- Work is **uncommitted** on `chore/remove-preview-generator-v2` (last commit `27c5de9`).
  `main` and `origin/main` remain at `66902f0`. No PR opened.
- **Pushing `main` auto-deploys to production** via Coolify (`DEPLOY.md`).
- **Do not force-push. Do not amend `5fcae7c`.**
- **`.env.prod` is gitignored and holds real production values.** Do not undo the `.gitignore`
  rules denying `.env` / `.env.*` at any depth.
- The six commits (`f98e6eb`…`66902f0`) that landed mid-session during the v2 removal are
  already reconciled. **Do not redo that work** — see the archived handoff.

## Use this test command — both documented ones lie

Two different path roots must line up with the mounted repo, and the documented invocations each
get one wrong, so each reports a phantom failure the other hides:

```bash
docker run --rm -v "$PWD:/repo" -w /repo/backend \
  -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template \
  --entrypoint sh bmv-local-api \
  -c 'pip install -q pytest; python -m pytest tests/ -q'
```

- Plain `docker run -v "$PWD:/repo"` fails template-dependent tests: the image sets
  `PREVIEW_TEMPLATE_DIR=/app/backend/preview-template`, and that env var **wins over**
  `Settings`' path discovery — so tests read the template *baked into the image* while your edits
  sit unread under `/repo`. Symptom: `test_task5_deterministic_fixture` reports `src/ui/**` drift
  that does not exist in the repo. Hence the explicit `-e` override.
- `docker compose exec api` fixes the template (compose mounts `./backend` onto `/app/backend`)
  but fails `test_admin_build_info.py::test_deploy_files_stamp_the_code_policy_revision`, which
  walks to `parents[3]` for the repo root, finds `/app`, and cannot see the deploy files.

Neither is a code defect. Recorded in `docs/KNOWN_TEST_FAILURES.md`.

## Verification status

| Check | Result |
|---|---|
| Backend suite | **836 passed / 4 failed** under the command above; the 4 are the documented pre-existing set. Baseline was 671/4 → **+165 tests, zero regressions** |
| End-to-end | **Two full generations run** (requests 37 and 38), both `ready`, both inspected with the QA harness and screenshotted |
| Imagery P0 | Verified in a live run (`imagery subject=art`, `template=art-gallery-portfolio-home`, `ops=-`) **and by looking at the photographs** |
| Typecheck gate | Live in the pipeline. Verified against app 36: 59 errors in 1.7s |
| Asset 404 | Verified live: broken paths 404 while real assets and SPA routes are untouched |
| Every new behavior | Paired with a test proven to fail without its fix |

### Measured before/after — request 36 (baseline) vs request 38 (after)

Same brief, same harness (`scripts/preview-qa.sh`).

| | req 36 (before) | req 38 (after) |
|---|---|---|
| Hero image | a dental clinic | **an artist painting at her easel** |
| "Featured works" | dentures, a dentist, oral surgery | **real oil paintings and gallery scenes** |
| Browser tab | `Preview App` | **`Jeanne Kassab Art`** |
| Meta description | none | **business-specific** |
| npm package name | `preview-app` | **`jeanne-kassab-art`** |
| Broken image paths | **7** (200 `text/html`) | **0** |
| TypeScript errors | **59** | **23** (−61%; TS1117 duplicate keys 13 → 1) |
| Clinic JPGs served in `dist` | **1.09 MB** | **0** — no non-JS assets at all |
| Workspace size | 4,448 KB | **880 KB** (−80%) |
| Credential cards | 4 **empty** shells, on 4 pages | **populated** ("Layered Oils", "Archival Quality", …) |
| Section eyebrow on `/gallery` | — | was **"CLINICAL TRUST"**, now "WHY JEANNE KASSAB ART" |
| Carousel counter | `GUEST PATH · 01 / 00` | **`02 / 03`** |
| Hero headline | white on near-white, unreadable | **legible** |
| Nav | `About Jeanne Kassab` **and** `About` | **deduplicated** |

Two caveats on that table, so nobody over-reads it. Request 38 still shipped 23 type errors
because **both** runs' typecheck repair rounds produced a patch that broke the build and were
rolled back (see open item 1) — the 59 → 23 improvement comes from the prop-shape prompts, not
from the repair loop. And request 38's route table still contained `/gallery/:id/:id`; that was
diagnosed and fixed **after** the run (open item 2), so it is fixed in code but not yet
demonstrated in a generation.

## What changed

### 1. Imagery subject comes from the business; a pack may only contribute framing

The fix for the dental photos, and the architectural point worth preserving: **a pack is a choice
about layout, and must never redefine what the photographs depict.**

- `services/industry_images.py` — a role query now **composes** with the resolved business subject
  (brand + category subject + role framing, deduped and word-capped) instead of replacing it
  wholesale. The four callers passing no `imagery_roles` get byte-identical queries.
- `industry_templates/apply.py` — no longer joins a pack's `industry_tags` into a search subject.
  A pack without explicit `imagery_roles` contributes **no subject at all** rather than a wrong
  one, and a pack whose imagery category disagrees with the business logs a WARN naming both.
- `industry_templates/loader.py` — three defects: negated clauses are now dropped (the brief said
  *"not a booking SaaS or clinic front desk"*, and `clinic` picked a dental pack); a lone tag hit
  must be a ≥6-char token from the **declared** industry rather than any word in model prose; ties
  break on merit with a seeded hash instead of descending template-id spelling, which is why
  `clinic-*` beat `agency-portfolio-*` at every seed. `art`/`arts`/`craft`/`creative` removed from
  the weak-token blacklist.
- **New pack** `art-gallery-portfolio-home` — no existing pack contained any art, gallery,
  painting, sculpture or exhibition vocabulary.
- `pipeline/plan_phase.py` — refines the correct appspec-gate imagery instead of replacing it.

**Verified on the real brief:** pack is `art-gallery-portfolio-home` at every seed (was
`clinic-dental-home`); the ops surface correctly returns `None` instead of stamping a bogus ledger
pack; recipe still resolves to `editorial`; queries carry art vocabulary with zero dental words. I
downloaded the resulting photographs and looked at them — a warm abstract landscape oil, a cool
layered oil on visible canvas, and a visitor viewing framed paintings in a gallery.

### 2. Assets must resolve, and a missing one must be visible

- `api/v1/routers/preview_apps.py` — asset-like paths now **404** instead of SPA-falling-back to
  `index.html` with `200 text/html`. Safe because generated React-Router paths are extensionless;
  `.html` is deliberately excluded so the shell still falls back.
- **New** `preview_app/asset_integrity.py` — finds runtime-resolved asset references that exist in
  neither `public/` nor `dist/`, ignoring remote URLs, `data:`/`blob:` and bundler imports.
- `quality_gate.py` — wired in with a deliberate threshold: **public-surface** breakage blocks (a
  broken hero is worse than no preview), owner/admin-only breakage is repaired and reported but
  still ships. Plus a heal that repoints broken refs at imagery known to load.

### 3. The visual loop can now fail a build

- `pipeline/visual_critic.py` — findings carry severity; an **unavailable verdict is a measurement
  failure, never a pass**; route selection covers ops/admin surfaces rather than the first six
  public routes; the page cap is configurable.
- `codegen/critic.py` — the scaffold exemption is resolved rather than deleted: scaffold pages are
  no longer *rewritten* (which used to break Vite) but they **are** now honestly judged.
- `preview_app_visual_critic.j2` — asks whether the photography depicts *this* business, with the
  dental case as a worked example, reserving severe verdicts for unmistakable mismatch.
- A **zero-cost deterministic detector** (`check_imagery_industry_consistency`) compares the
  resolved business family against the imagery actually installed — no model call. Both sides must
  classify confidently, so an abstract brief is not treated as evidence of a defect.

### 4. Codegen stops failing silently

- `codegen/generate.py` — a rejected slot-fill now **retries once** (bounded at
  `_MAX_SLOT_FILL_ATTEMPTS = 2` so it cannot starve `PREVIEW_MAX_AI_CALLS`) with guidance tailored
  to the failure mode, and logs the reason. Previously a truncated answer silently kept the
  scaffold, indistinguishable from one never attempted.
- `source_quality.py` — adds `tsx_parse_error`, a **real** TSX parse check via the TypeScript
  compiler, closing the old open item where slot-fill accepted syntactically-invalid JSX. Size
  capped, timeout bounded, and deliberately fails open so a missing toolchain cannot demote every
  page to a scaffold.
- `pipeline/finalize.py` — `fallback_pages` is measured from source alone at the measurement site,
  with `enforce_app_spec` gating only the *failure*. Previously the clearing branch was unreachable
  in the default configuration, so the metric inflated to "every catalogue page" — and that
  inflated number is what the previous handoff used to judge quality.

### 5. Shell identity and scaffold weight

- Generated apps carry the real business name in `<title>`, a meta description, and a slugified
  valid npm `name`. Every app in the fleet previously shipped `Preview App` / `preview-app`, and
  nothing in the pipeline rewrote either.
- Deleted from the scaffold: 19 screenshots of unrelated businesses, 12 laser-clinic images, three
  demo reference pages plus their screenshots, and two never-invoked dev scripts. **3.64 MB less
  copied per generation; 1.09 MB less served in every `dist/`** — the clinic imagery alone was
  larger than the JS bundle.

### 6. The compiler now runs — the highest-leverage fix in the system

`vite build` uses rolldown and does not typecheck, so the component library's exported
TypeScript interfaces — a precise, complete, machine-checkable spec of what every generated page
must satisfy — were never enforced. Running `tsc` takes **1.7 seconds** and found **59 errors
across 11 files** in the app that shipped as "ready".

- **New** `preview_app/typecheck.py` — runs the workspace's own `tsc` and returns structured
  diagnostics with a **three-state** result: `clean` / `errors` / `unavailable`. A broken compiler
  run can never be reported as a healthy app. Uses project mode
  (`-p tsconfig.app.json --noEmit --incremental false`) rather than `tsc -b`, because workspaces
  symlink a shared `node_modules` and build mode would race on one `tsBuildInfoFile` across
  concurrent generations.
- `pipeline/build_phase.py` — repairs run after the Vite build succeeds and before the visual
  critic, bounded by `PREVIEW_MAX_TYPECHECK_FIX_ROUNDS` (2) and the existing fix-loop budget.
  Each round snapshots sources **and the shipping `dist`**; a round whose rebuild fails is rolled
  back and the pre-typecheck `dist` restored — Vite empties `outDir` on start, so without that a
  failed repair would delete a servable preview. Leftover errors are recorded to
  `.bmv-debug/typecheck/summary.json` and **the app still ships**.
- `codegen/fix_agent.py` — the existing build-fix flow is refactored and reused rather than
  duplicated (its signature and behavior are unchanged), plus `regressive_fix_reason`, a
  deterministic veto on the failure mode that matters: a "fix" that **deletes a component usage,
  empties an array that had content, or adds `as any` / `: any` / `@ts-ignore`** is rejected.
  Silencing the compiler by making the page emptier is the exact defect being removed.
- `PREVIEW_TYPECHECK` **defaults on**. A quality gate that defaults off is the disease.

### 7. The model is now shown the contract it must satisfy

`catalogue.json` told the model `CredentialStrip` requires `items` but never that an item is
`{title, detail}` — so it invented `{label, value}`, and four empty cards shipped on four pages.

`ui_catalogue.py` now derives prop and item type shapes **from the component `.tsx` sources** at
prompt-build time, so the contract can never drift from the components, and there is no second
copy to maintain. Wired into `preview_app_slot_fill.j2`, `preview_app_mock_synthesize.j2` and
`preview_app_file.j2` for **~649 tokens**. Verified output:
`CredentialStripItem { title, detail }`, `TestimonialRailItem { quote, author, role? }`,
`MarketingHero.imageSrc` required with no `children`, `Button` with no `target` — every guess the
model previously got wrong is now stated, including allowed literal unions.

### 8. Rendered hygiene

- `catalogue_contract/scaffold.py` — a single `_js()` helper (mirroring the existing
  `utility_compositor.py:66` pattern) replaces every raw `json.dumps`, so `ensure_ascii=True` can
  no longer ship `—` as six visible characters through a JSX attribute. All 31 call sites
  fixed, not just the one that was visibly broken.
- **New** `safety/copy_hygiene.py` — a deterministic net so a literal `\uXXXX` escape or template
  jargon ("LEAD DROP", "NEXT MOVE", "GUEST PATH") cannot reach rendered copy from any source,
  including model output.
- `pipeline/architect_normalize.py` — route-table normalization. On app 36's real routes this
  collapses **17 → 10**: `/works*` merges into `/gallery/:slug` (they rendered byte-identical
  pages), `/works/:slug/:slug` (the same param name twice) is gone, `/admin/:id` and
  `/admin/:slug` unify, and literal admin routes are ordered ahead of the dynamic sibling that
  used to shadow them.
- `safety/mock_data.py` — nav deduplicated by destination and ordered primary-journey-first, so
  "About Jeanne Kassab" and "About" can no longer both appear.

### 9. The vision model had no endpoints — so the visual gate could never run

Found by reading the logs of a real generation. Every route logged
`visual critic route error: No endpoints found for meta-llama/llama-3.2-11b-vision-instruct`.
OpenRouter no longer serves that model, and it was the `openrouter` **default** in
`_DEFAULT_MODELS`, with `.env.prod.example` pinning it **uncommented** so production actively
selected it. The consequence is the worst possible shape: the one component that renders pixels
failed on every page, reviewed nothing, and — because an unavailable verdict is correctly *not* a
pass — the run still completed. We had just given that gate teeth and it could not bite.

Verified directly against the provider with a real screenshot:
`google/gemini-2.5-flash` → `VISION_OK`; the old default → `No endpoints found`. Changed the
default to `google/gemini-2.5-flash` (already the pipeline's codegen model, and multimodal), fixed
`.env.prod.example`, `backend/.env.example` and `docs/architecture/PREVIEW_GENERATOR_V1_BASELINE.md`.
`backend/.env` has it commented out, so it inherits the new default — nothing to change there.
Guarded by `tests/preview_app/test_vision_model_is_servable.py`, which pins the default away from
known-dead models, asserts it looks multimodal, and fails if a deploy template or doc re-advertises
a dead one.

### 10. The shared kit shipped a clinic-branded default and rendered empty shells

Found only by rendering a generated page and looking at it. On the fine-art gallery's `/gallery`,
a section eyebrow read **"CLINICAL TRUST"** — `CredentialStrip`'s default heading was the literal
`'Clinical trust'`, the single industry-specific default in an otherwise generic kit, and it leaked
onto every business that did not pass its own heading.

Worse, the generated page passed `<CredentialStrip items={[]} />` — a hardcoded empty array — and
the component happily rendered its heading, its background and its gradient over nothing.
`FeatureBento` did the same and added a counter reading `01 / 00`; `TestimonialRail` too. A heading
over an empty body reads as a broken page, whereas an absent section reads as a design choice.

All three now return `null` when they have no items (with `FeatureBento`'s guard placed after its
hooks, or React throws "rendered fewer hooks than expected"), the default heading is neutral, and
the `Guest path ·` jargon is gone from the counter. Guarded by
`tests/preview_app/test_kit_empty_and_neutral.py`, which also scans **every** kit component for
industry-specific default copy so the next `'Clinical trust'` cannot be introduced quietly.

## Two integration gaps found by reviewing the work rather than trusting it

All five adversarial QA reviewers died on a session usage limit, so the change sets landed
unreviewed. Reviewing them by hand surfaced two instances of the *exact* disease this session was
about — a check that records a defect into something nobody reads:

1. **Warning-only asset breakage was never repaired.** `GateReport.ok` ignores warnings and
   `run_quality_gate_with_heal` early-returns when `ok`. So a run whose only defect was
   owner-surface breakage — precisely request 36's shape, all seven broken paths on admin pages —
   returned before `heal_quality_gate`, the deterministic asset repair never fired, and
   `report.warnings` was written to a field with no readers. Fixed via `_settle_warnings`, which
   repairs and logs on that path, and deliberately adopts only the rescan's *warnings* — never its
   issues — so a repair can never withhold an app that was about to ship.
   Test: `tests/preview_app/test_warning_only_asset_settle.py`. Proven pre-fix: `ok=True`,
   `healed=[]`, broken references still present.
2. **The visual report never reached the gate.** `visual_critique_gate_issues()` existed,
   documented as "triples a quality gate can fail on directly" — and nothing called it. The loop
   rendered pixels, persisted a report, and the report was never read. Now wired into
   `evaluate_quality_gate`. Test: `tests/preview_app/test_visual_report_reaches_gate.py`. Proven
   pre-fix: `ok=True` with a blocking mismatch sitting on disk.
   The wiring deliberately **excludes** `missing_image_asset`, because `imagery_findings` emits it
   at BLOCK on every surface and would otherwise re-break the owner-surface threshold that
   `asset_integrity` sets correctly.

## The QA harness

`scripts/preview-qa.sh <request_id> [tag]` reports, for any request id, what the pipeline's own
gates cannot see: shell identity, the declared route table, every image reference resolved **by
content-type** rather than status code, `tsc` error count by code, leaked placeholder/jargon/escape
strings, shipped bundle weight, and screenshots of every public route. Artifacts land in
`.preview-qa/<tag>/` (gitignored); `QA_OUT_DIR`, `QA_BASE_URL` and `QA_CHROME` override the
defaults. Run it from the repo root — it shells into the `api` compose service.

The content-type check is the important part: a missing asset used to return `200 text/html` via
SPA fallback, so any status-code-based check saw a healthy app.

Screenshots need no new dependency:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --no-sandbox --hide-scrollbars --virtual-time-budget=9000 --window-size=1440,2000 \
  --screenshot=/tmp/shot.png "http://localhost:8001/api/preview-apps/<id>/"
```

**Baseline for request 36**, to compare any future run against: title `Preview App`, 7 broken
image paths, 6 dental photos, **59** TypeScript errors, 1.09 MB of clinic JPGs in `dist`, and a
route table containing `/works/:slug/:slug` plus `/admin/:id` shadowing `/admin/dashboard`.

## Environment gotchas that cost time

- **The test command.** See above. This is the big one.
- **`docker compose exec api` does not reload code.** No `--reload`, so edits are invisible until
  `docker compose up -d api` (not `restart`, which does not re-read `env_file`). Verify with
  `docker compose exec api env | grep KEY`.
- **`POST /api/requests` is multipart `Form(...)`, not JSON.** Use `-F`; the trailing slash
  307-redirects and drops the body.
- **Local DB is Postgres.** `sum(bool)` fails; use `count(*) FILTER (WHERE ...)`.
- **`tests/appspec/` cannot always be collected as a directory** — importing
  `app.domain.appspec.validation` before `app.application.appspec` triggers a circular import.
  Name individual files.
- `awk` and `timeout` are absent from this shell; `ugrep` rejects some PCRE repeats.

## Still open

1. **The typecheck repair loop has never produced a usable patch.** In both live runs it patched 8
   files, the rebuild failed, and all 8 were rolled back — so the loop currently costs two builds
   and delivers nothing. The rollback is working exactly as designed (a viewable preview is never
   traded for a broken one), but the repair itself is not. Look at
   `.bmv-debug/typecheck/summary.json` and the `fix-agent/` dumps in
   `/app/data/preview-apps/38/.bmv-debug/` to see what it emitted. My suspicion is that patching 8
   files in one shot is too coarse — a per-file patch-and-rebuild, or feeding the rejection reason
   back to the model (which the author deliberately did not do, to save calls), would likely fix it.
   Until then the 59 → 23 error reduction comes entirely from the prop-shape prompts.
2. **`/gallery/:id/:id` — fixed in code, not yet demonstrated.** Diagnosed after request 38:
   `assemble.py`'s detail-alias loop appended `/:id` to paths that were *already* dynamic, because
   `/gallery/:id` also matches the listing regex. Note this is **separate** from the architect route
   normalization, which was working — `App.tsx` routes 49-62 were clean and 63-69 were appended
   aliases. Guarded by `tests/preview_app/test_router_alias_params.py`, proven to reproduce the
   exact malformed paths without the fix. A fresh generation should confirm it.
3. **Two Wave-2 packages died on a session limit while writing their final report**, after their
   code and tests had landed. The prop-shape and rendered-hygiene work is on disk, its 28 tests
   pass, and I verified the behavior by hand. What is missing is their written self-assessment — and
   **no package in either wave ever received an independent adversarial review** (all five Wave-1
   reviewers also died on a limit). Reviewing Wave 1 by hand found two real blockers, so **a review
   pass over both waves is the highest-value next step.**
4. **Listing page headers are still clipped** against the nav on `/gallery` — cosmetic, unfixed,
   and it was in the rendered-hygiene brief.
5. **The hero can still be made illegible by the model.** The prompts now forbid adding
   overlay/blend/background utilities to catalogue components that manage their own contrast, but
   there is no deterministic guard — a model that ignores the instruction can still ship
   `after:bg-blend-multiply … bg-background` and a white-on-white headline. A contrast check on the
   rendered screenshot, or a scrub of those utilities off kit components, would close it properly.
6. **AppSpec shadow authoring is fragile, and now has a third failure mode.** The archived handoff
   recorded `call_budget_exhausted` (req 34) and `coverage_review_malformed` (req 36). Request 37
   added two more in a single run: first `app_spec_schema_parse_failed` + `invalid_page_shape`
   ("Tuple should have at least 1 item after validation, not 0"), then on the preview pass
   `unresolved_requirement_source_ref` — three requirements citing
   `reference_evidence.screenshot_analysis.features_worth_adapting.0` and similar paths that carry
   no authoritative source value. That last one looks like a real bug rather than model flakiness:
   the authoring prompt is inviting citations into a evidence path that the validator does not
   accept. Non-fatal only because `APPSPEC_MODE=shadow`, but it costs ~2.5 minutes per run and
   means the AppSpec contract is never actually exercised. **Note this also makes the shadow pass a
   misleading signal** — a `failed` blip appears in `/progress` mid-run while `is_failed` stays
   false and generation continues; poll `is_generating`, not the stage string.
7. **`requests.py:303-314` reads `result["preview_contract"]["status"]`**, which v1 `run_finalize`
   never returns (it returns `{"preview_app", "experience_plan"}`) — that key came from the removed
   v2 service. So `req.status` is left stale after any preview-only regeneration.
8. **`retry-generation`'s lock does not serialize** — `requests.py:188-193` builds the thread
   inside `with _preview_gen_lock(...)` but calls `.start()` outside it.
9. **31 empty v2 tables** and **`APPSPEC_V2_COVERAGE_MODEL`** (a live v1 setting with a v2 name)
   carry over unchanged from the archived handoff.

## If you are demoing to an investor

Do **not** show request 36 — it is the broken baseline, kept only for comparison. Generate fresh,
run the QA harness, and actually look at the screenshots before showing anyone.

Reproduce the reference brief with the `curl` in the archived handoff (unchanged). Expect
`product_kind=storefront`, recipe `editorial`, and 8-12 minutes end to end. Per the previous
handoff: do not re-run rematerialize or pack-seed nit loops for a demo.
