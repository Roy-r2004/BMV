# Session handoff — preview quality (2026-07-29, session 2)

Successor to [docs/handoffs/2026-07-29-v2-removal.md](docs/handoffs/2026-07-29-v2-removal.md)
(archived, still accurate on branch/deploy constraints). Process notes, not product docs.
The permanent record of *why* the pipeline shipped bad output is
[docs/PREVIEW_QUALITY_FINDINGS.md](docs/PREVIEW_QUALITY_FINDINGS.md) — read that first.

**If you read one thing: [Next steps](#next-steps), item P0-1.** An adversarial review confirmed
that our own imagery fix introduced a new way to ship wrong photographs. It is a regression against
`main` and it is not yet fixed.

## TL;DR

Preview request 36 — `status=ready`, `quality gate PASSED` — was not shippable: a dental-clinic
hero on a fine-art gallery, 59 TypeScript errors, seven image paths resolving to HTML, four empty
credential cards, a white-on-white headline. Every measurement was accurate and every measurement
was blind to the page. Root cause: **nothing in the pipeline ever looked at the artifact.**

Session 1 fixed that and demonstrated it end to end (request 38: real artist imagery, 0 broken
paths, 23 type errors, correct shell identity). Session 2 did the review that session 1 never got,
plus the repair loop that had never worked.

**Session 2 outcome, honestly stated:** the review confirmed **6 defects, 1 a blocker**, and
**22 of its 33 agents died**, so coverage is partial — two subsystems were never reviewed at all
and 18 candidate findings were never verified. Details in
[Review coverage](#review-coverage-read-this-before-trusting-the-result). The pipeline is in better
shape than session 1 left it *and* it has a confirmed release-blocking regression. Both are true.

## Branch and deploy constraints — unchanged, still binding

- All of session 1 and session 2's code is **committed** as `fcee0f5` ("refining v1") on
  `chore/remove-preview-generator-v2` — 115 files. `main` and `origin/main` remain at `66902f0`, so
  **nothing has deployed.** No PR opened.
- **Pushing `main` auto-deploys to production** via Coolify (`DEPLOY.md`).
- **Do not force-push. Do not amend `5fcae7c`.**
- **`.env.prod` is gitignored and holds real production values.** Do not undo the `.gitignore`
  rules denying `.env` / `.env.*` at any depth.
- The six commits (`f98e6eb`…`66902f0`) that landed mid-session during the v2 removal are already
  reconciled. **Do not redo that work** — see the archived handoff.

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
  `PREVIEW_TEMPLATE_DIR=/app/backend/preview-template`, and that env var **wins over** `Settings`'
  path discovery — so tests read the template *baked into the image* while your edits sit unread
  under `/repo`. Symptom: `test_task5_deterministic_fixture` reports `src/ui/**` drift that does not
  exist in the repo. Hence the explicit `-e` override.
- `docker compose exec api` fixes the template (compose mounts `./backend` onto `/app/backend`) but
  fails `test_admin_build_info.py::test_deploy_files_stamp_the_code_policy_revision`, which walks to
  `parents[3]` for the repo root, finds `/app`, and cannot see the deploy files.

Neither is a code defect. Recorded in `docs/KNOWN_TEST_FAILURES.md`.

---

# Next steps

Ordered by what would stop a demo. P0 items can ship a wrong preview or withhold a correct one.

## P0-1 — Imagery role queries dropped the industry text (**regression vs `main`, blocker**)

`backend/app/application/services/industry_images.py:236`

```python
queries[slot] = _compose_query(brand, category_hint, role)   # industry_clean never passed
```

`industry_clean` is computed at line 221 and never used on this branch, so the **entire subject** of
every Pexels query is `_CATEGORY_QUERY_HINT[_resolve_category(industry)]` — one of nine buckets.
`_resolve_category` is an *unanchored substring* match, so it mis-buckets badly:

| brief industry | resolves to | subject actually searched |
|---|---|---|
| `Auto repair garage and detailing` | `tech` (`"ai"` inside `"repair"`) | `software office technology` |
| `Plumbing and heating repair` | `tech` | `software office technology` |
| `Boutique law firm — estate and family law` | `retail` (`"boutique"`) | `fashion retail apparel outdoor gear` |
| `Commercial cleaning company` | `realestate` (`"commercial"`) | `modern home real estate` |

Reproduced against the real pack picker: `industry="Auto repair garage and detailing"`,
`brand="Ridge Motors"` → pack `home-services-trades` → **all six slots** query
`Ridge Motors software office technology <framing>`. On `main` the same input queried
`home services plumber electrician hvac handyman cleaning repair trades …`. So the change swapped
on-industry pack tags for a mis-bucketed hint *and* dropped the one signal that was still correct.

This is the pipeline's default path: `apply.py:_pack_imagery_roles` returns `_ROLE_FRAMINGS`
whenever a pack has no explicit `imagery_roles` (**18 of 25 packs**), `apply_industry_template_to_plan`
gap-fills all six slots, and `plan_phase.py:226` merges the role-path result over everything the
roleless branch produced. Nothing downstream catches it — `asset_integrity` only checks
reachability, and `check_imagery_industry_consistency` returns `[]` for these cases.

**Fix:** put the business prose back at the head of the subject —
`_compose_query(brand, industry_clean, category_hint, role)` — and note that `_MAX_QUERY_WORDS = 14`
clips, so brand + industry + role must win and the category hint must be filler, not the head term.
The comment already on line 235 describes the intended behaviour; the code one line below
contradicts it. Separately, anchor `_resolve_category` on word boundaries (`\bai\b`, `\bhome\b`,
`\bagent\b`, `\bcommercial\b`) so the hint stops mis-firing on the roleless path too.

**Why the tests missed it:** `tests/preview_app/test_imagery_subject_from_business.py` only exercises
the art case, where the bucket happens to resolve correctly. Add a table-driven case per bucket, and
one asserting the composed query **contains the brief's own industry words**.

## P0-2 — A vision outage still reports "quality gate PASSED / status ready"

`backend/app/application/preview_app/pipeline/visual_critic.py:726`

If `VISION_MODEL` is unservable again, or OpenRouter 5xx/429s, or the key is missing, or the vision
budget is exhausted: every route raises → all pages land in `report.unmeasured` at severity
**WARN** → `report.blocking == []` → `visual_critique_gate_issues() == []` → `gate.ok` →
`viewable=True` → `status: "ready"`. **Zero pages were judged.** Worse, `visual_critic.py:643`
emits the progress line `Visually reviewed 6/6` *before* the exception check, so the user-visible
feed claims full coverage.

The severity hinges on `PREVIEW_VISUAL_CRITIC_BLOCK_ON_UNMEASURED`, which appears **exactly once in
the repo** — at the line that reads it. It is in no `Settings` field, no `.env` template, no doc, no
test, so it is off everywhere and every unmeasured page is a warning.

`VisualCritiqueReport.measurement_failed` carries the docstring *"callers must not read `ok` as 'the
pages were checked and are fine' without also checking this"* — and has **zero production readers**
(only `tests/preview_app/test_visual_feedback_loop.py`). Same for `.verified`, `.reviewed`,
`.scores`, `.refined`. `build_phase.py:487` discards the returned report inside a bare
`except Exception`, so it is unreachable in-process too.

**Fix:** surface measurement into the API result the way `_typecheck_summary` already does —
`finalize.py` should carry `visual_pages_reviewed` / `visual_pages_unmeasured`, and "ready" must not
be reportable when nothing was measured. Define the flag in `Settings` with a documented default, or
delete it and decide the policy in code. Move the progress emit after the exception check.

## P0-3 — A blocking visual finding can never be cleared, so a repaired preview still ships nothing

`backend/app/application/preview_app/pipeline/visual_critic.py:708`

`_bmv_visual_critique.json` is written **once, pre-refine**, and is the only BLOCK source in the
gate that is never re-derived. On the refine success path the report is persisted *unchanged* — no
re-screenshot, no re-critique, only `report.refined.append(...)`. So: vision scores `/gallery` 30 →
BLOCK recorded → `refine_file` rewrites the page → guards and build succeed → the page is now fine →
the stale BLOCK still fails the gate → `viewable=False`, `url=None`, `status="failed"`.

Proven: `run_quality_gate_with_heal` on a workspace whose only defect was a persisted BLOCK returned
`ok=False` after deterministic heal, 3 AI repair attempts that each touched the file, and 4
successful rebuilds — with the report byte-identical on disk.

**Fix:** re-measure the refined pages and rewrite the report before the gate reads it, or have the
gate ignore BLOCKs for paths listed in `report.refined`. The first is correct; the second is cheap.

## P0-4 — `broken_rendered_image` blocks on every surface, defeating the deliberate deferral

`backend/app/application/preview_app/pipeline/visual_critic.py:757`

`report.add("broken_rendered_image", ...)` relies on `add`'s `severity=BLOCK` default and applies no
surface check — while the gate deliberately filters the visual `missing_image_asset` code for exactly
this reason, and `asset_integrity.blocking_missing_assets()` blocks only on `ref.public_surface`.
Since route selection now deliberately screenshots an ops/admin route, **one broken owner-only
thumbnail withholds the entire public storefront.** It fires even on a `pass` verdict at score 90,
because `broken_images` comes from the browser probe, not the model.

Our own two new tests encode the contradiction for the same defect on the same kind of page:
`test_visual_report_reaches_gate.py:100-124` asserts a missing image on `admin/ManageArtworksPage.tsx`
must **not** fail the gate; `test_visual_feedback_loop.py:206-225` asserts a missing local image on
`admin/DashboardPage.tsx` **does** produce a BLOCK.

**Fix:** pass `WARN` when `_route_surface(rt)` says the page is ops/owner-only, mirroring
`asset_integrity`'s `public_surface` policy. Keep the BLOCK for public surfaces — it is correct
there. Then reconcile the two tests.

## P0-5 — Industry-mismatch margins are computed and never read

`backend/app/application/preview_app/pipeline/visual_critic.py:383`

`classify_industry_family` returns `(family, margin)` and `check_imagery_industry_consistency` binds
`business_margin` / `imagery_margin` — then uses them **only inside the f-string message**. No
threshold reads them. The docstring's *"Both must classify confidently"* is enforced only by a weak
internal rule (≥2 hits and strictly more than the runner-up), so a 3–2 win counts as confident. And
nothing reconciles the semantically overlapping `health` and `beauty` families.

Reproduced with the real pack picker and real pack roles: `industry="spa and wellness clinic"` →
pack `spa-wellness-home` → business `('health', 2)`, imagery `('beauty', 3)` → **BLOCK
`imagery_industry_mismatch`** against imagery the pipeline itself selected as on-industry. A med-spa
brief gets `('health', 1)` vs `('beauty', 3)` → same BLOCK. Combined with P0-3, that permanently
withholds a correct preview.

**Fix:** require a real margin on both sides before reporting, and add a family-adjacency allowance
(`health`/`beauty`, and check the other pairs in `_CATEGORY_FAMILY` for the same overlap).

## P1-1 — Re-run the full suite; I could not

My shell tool went down partway through session 2 (sandbox outage, not a repo problem). Everything
below was verified before it did — **but the full suite has not been run since the repair-loop
changes, so `fcee0f5` is committed without a full-suite pass.** Do this first; it is one command.

Verified in isolation, 10/10 in its own file, and mutation-proven (each mechanism disabled in turn
kills exactly the test that guards it):

- `tests/preview_app/test_typecheck_repair_loop.py` — 10 passed
- `tests/preview_app/test_task4_prompt_contract.py` — 7 passed (**was a documented failure**)
- `tests/preview_app/test_task3_security.py` — 7 passed (**was a documented failure**)

Not yet re-run: everything else, including `tests/preview_app/test_typecheck_fix_guard.py` and
`test_typecheck_diagnostics.py` (37 passed together with the prompt-contract file before the
outage).

## P1-2 — Finish the template typecheck triage (interrupted mid-verification)

`tests/preview_app/test_task3_catalogue_guards.py::test_catalogue_fallback_typechecks_with_template`
used to invoke `node_modules/.bin/tsc.cmd` — the **Windows** shim — so on Linux it raised
`FileNotFoundError` and never typechecked anything. That was its documented "pre-existing failure".
It now resolves the compiler through the production `typecheck_workspace`, and immediately finds
**4 type errors in the shipped preview template**, which every generated app inherits:

```
src/ui/motion/anime.ts(5,74):            TS2307  Cannot find module 'animejs'
src/ui/public/ProductShowcase.tsx(59,18): TS2741  Property 'children' is missing … required in
src/ui/public/ProductShowcase.tsx(82,22): TS2741    type '{ href: string; children: ReactNode }'
src/ui/public/ProductShowcase.tsx(100,26):TS2741
```

- The three `ProductShowcase` errors **look real**: `AppLink` is used as a full-area overlay click
  target with `href` + `className` + `aria-label` and no children, which is a legitimate accessible
  pattern that `AppLink`'s prop type forbids. Likely correct fix: make `children` optional on
  `AppLink`.
- The `animejs` error is **unverified** — `animejs@^4.5.0` *is* in `package.json` and
  `package-lock.json`, so this may be an artifact of the test's temp workspace resolving modules
  differently, not a template defect. I was interrupted running `tsc` against the template in place
  to settle it. **Do that before changing anything.**

Net test count is unchanged either way (it failed before, it fails now) but the failure is now
informative rather than a crash. Either fix the template or scope the test, and update
`docs/KNOWN_TEST_FAILURES.md` — three of its four rows are now stale.

## P1-3 — Verify the 18 candidate findings whose verifiers died

Three subsystems produced findings that were never adversarially verified, so they are **leads, not
defects.** Recover them from the workflow journal:

```
/Users/maurice/.claude/projects/-Users-maurice-Documents-Dev-BMV/\
8176582d-9cdb-4839-8c98-929e788ce52a/subagents/workflows/wf_816c9888-98b/journal.jsonl
```

One `{"type":"result",...}` line per agent; the `review:*` rows carry the full findings arrays.

| subsystem | candidates | verified | flagged locations from the run log |
|---|---|---|---|
| `gate-and-repair` | 5 | **0** | `quality_gate.py:306,586,630`, `asset_integrity.py:223`, `source_quality.py:151` |
| `typecheck-repair` | 5 | **0** | `build_phase.py:58,260,500`, `fix_agent.py:82`, `test_typecheck_repair_loop.py:305` |
| `safety-copy` | 8 | **0** | `copy_hygiene.py:101`, `BookingPanel.tsx:135`, `CTABand.tsx:40`, `ProcessSection.tsx:28`, `preview_app_mock_synthesize.j2:25` |

Note `build_phase.py` and `test_typecheck_repair_loop.py` are files **I edited after** that reviewer
ran, so those two leads may already be moot — check line numbers against the current file.

## P1-4 — Two subsystems were never reviewed at all

`codegen-scaffold` and `test-integrity` reviewers both stalled through all 6 attempts and returned
nothing. Re-run just those two. `test-integrity` matters most: its whole job was to find tests that
pass vacuously, and **the two vacuous-assertion bugs found by hand this session were both of exactly
that shape**, so its absence is a real gap.

Re-run with the cached prefix (unchanged agents replay instantly):

```
Workflow({ scriptPath: "…/workflows/scripts/maverick-adversarial-review-wf_816c9888-98b.js",
           resumeFromRunId: "wf_816c9888-98b" })
```

Cut it to those two dimensions and reduce concurrency — the stalls looked like contention, and the
run burned 2.5 M tokens over 74 minutes for 11 useful agents.

## P1-5 — Negation stripping is a closed cue list

`backend/app/application/preview_app/industry_templates/loader.py:47`

`_NEGATED_CLAUSE_RE` matches only `not|never|no longer|isn't|aren't|rather than|instead of`. So
`no`, `without`, `unlike`, `other than`, `as opposed to`, `far from` still let a negated word pick a
pack. Reproduced: `industry="Independent bookshop, no clinic front desk"` → `clinic-dental-home`,
yielding hero copy *"Care that starts on time and explains every step"*, CTA *"Book a visit"*, and
**14 occurrences of "clinic"** in the plan. `check_imagery_industry_consistency` returns `[]`, so
nothing catches it.

Precise statement: it is not "any negated word wins" — the leaked evidence must still clear the
existing gates (one *declared* token ≥6 chars, or ≥2 strong tokens). The bug is that **negated words
are indistinguishable from claimed words once they clear the distinctiveness gate.** Fix in
`_NEGATED_CLAUSE_RE`/`_claimed_tokens` so both the public and ops call paths inherit it
(`plan_phase.py:174` passes the same unstripped context to the ops pack), and add a regression test
per cue word. The committed test covers only the `not a …` phrasing.

## P2 — carried forward

1. **The repair loop is fixed but not yet demonstrated in a generation.** See
   [What session 2 changed](#what-session-2-changed). Run a fresh generation and confirm from
   `.bmv-debug/typecheck/summary.json` that `repair_rounds > 0` and the error count actually dropped.
2. **`/gallery/:id/:id` — fixed in code, still not demonstrated.** Guarded by
   `test_router_alias_params.py`. A fresh generation should confirm it.
3. **Listing page headers are still clipped** against the nav on `/gallery`. Cosmetic, unfixed.
4. **The hero can still be made illegible by the model.** Prompts forbid overlay/blend utilities on
   catalogue components that manage their own contrast, but there is no deterministic guard. A
   contrast check on the screenshot, or scrubbing those utilities off kit components, would close it.
5. **AppSpec shadow authoring is fragile, now with three failure modes** — `call_budget_exhausted`
   (req 34), `coverage_review_malformed` (req 36), and req 37's `app_spec_schema_parse_failed` +
   `invalid_page_shape` followed by `unresolved_requirement_source_ref`. That last looks like a real
   bug: the authoring prompt invites citations into a `reference_evidence.screenshot_analysis.*` path
   the validator does not accept. Non-fatal under `APPSPEC_MODE=shadow` but it costs ~2.5 min/run and
   means the AppSpec contract is never exercised. It also makes the shadow pass a **misleading
   signal** — a `failed` blip appears in `/progress` while `is_failed` stays false; poll
   `is_generating`, not the stage string.
6. **`requests.py:303-314` reads `result["preview_contract"]["status"]`**, which v1 `run_finalize`
   never returns (it returns `{"preview_app", "experience_plan"}`) — that key came from the removed
   v2 service. So `req.status` is left stale after any preview-only regeneration.
7. **`retry-generation`'s lock does not serialize** — `requests.py:188-193` builds the thread inside
   `with _preview_gen_lock(...)` but calls `.start()` outside it.
8. **31 empty v2 tables** and **`APPSPEC_V2_COVERAGE_MODEL`** (a live v1 setting with a v2 name)
   carry over unchanged from the archived handoff.

---

# Review coverage — read this before trusting the result

The adversarial review ran 7 file-disjoint reviewers, each finding piped into independent
refutation-oriented verifiers. **33 agents: 11 completed, 22 died** on repeated stalls
(6 attempts each). So:

| dimension | reviewed? | findings verified? |
|---|---|---|
| `vision-path` | yes | **4 of 4** — complete |
| `imagery-subject` | yes | 2 of 7 |
| `gate-and-repair` | yes | **0 of 5** |
| `typecheck-repair` | yes | **0 of 5** |
| `safety-copy` | yes | **0 of 8** |
| `codegen-scaffold` | **no — reviewer died** | — |
| `test-integrity` | **no — reviewer died** | — |

**The run's own `clean_dimensions` field lists five of these as clean. That field is wrong** — my
post-processing conflated "no verified findings" with "verifiers never ran". Only `vision-path` got
a complete find-and-verify pass. Treat the other six as open.

Of the 6 verified findings, **0 were refuted** — every one survived a verifier explicitly instructed
to refute it and to default to refuted when uncertain. Two came back with corrections to the
reviewer's details (wrong pack name, a branch wrongly called dead code, a nonexistent `template_id`,
a margin of 2 rather than 1); those corrections are folded into the P0 items above.

# What session 2 changed

## The typecheck repair loop now keeps its good patches

The loop had never landed a repair: in both live runs it patched 8 files, the rebuild failed, and
**all 8 rolled back**. The rollback was correct; the granularity was not.

`pipeline/build_phase.py` now screens each round with `tsc` (~2 s) before spending a `vite build`
(~20 s) on it, compares **per-file** error counts across the two reports, hands back only the files
the model made worse, and keeps the rest of the batch. One bad patch out of eight now costs one
patch.

The subtle part: a parse failure **hides from an error-count comparison.** `tsc` abandons a file it
cannot parse and reports a single `'}' expected.` where twelve type errors stood — so a broken patch
scores as a large *improvement*. Mutation-testing showed this exactly: with the check disabled, the
log reads `typecheck initial: 6 error(s)` → `after round 1: 1 error(s)` while the file no longer
compiles. `_unparseable_files` matches on the diagnostic message rather than a `TS1xxx` code range,
because that range also holds grammar complaints esbuild accepts — `TS1117` (duplicate object key)
being the one this pipeline hits most.

Also: a round that is strictly worse is now given back **without spending a build**, and a round
that makes no net progress stops the loop instead of repeating three more times.

**Rejection reasons now reach the next round.** `regressive_fix_reason` logged why a patch was thrown
away and dropped it — the same computed-never-read shape this whole effort is about — so the model
reoffered the same forbidden patch every round. `fix_type_errors` now takes `prior_rejections` and
fills `rejections_out`, and `preview_app_fix.j2` renders them under
*"YOUR PREVIOUS ATTEMPT WAS THROWN AWAY FOR THESE REASONS"*.

Each mechanism is proven load-bearing by mutation: disabling it kills exactly the test that guards
it, and the file returns green when restored.

## Three of four "pre-existing" failures cleared — and one was masking a regression

`test_task4_prompt_contract.py::test_production_callsites_render_with_strict_undefined` was failing
for the documented reason (`synthesize_mock_data` returning falsy). But it was **also** failing
earlier in the same test, at `assert inconsistent_ai.prompts == []` — an assertion identical to
`main`'s that Wave 2 had broken. Because the test id was already on the known-failure list, nobody
saw it.

The behaviour change was correct: scaffold pages used to short-circuit to `{"score":72,"verdict":"ok"}`
**without calling the vision model**, which is how a dental hero shipped inside a "PASSED" gallery.
They are now judged, with `verdict` held at `ok` (so no freeform rewrite fires) and `visual_verdict`
carrying the honest judgement. I confirmed `visual_verdict` really is consumed — `_absorb_review`
prefers it over `verdict` — so this one is not a computed-never-read. The stale assertion was
updated to pin the new intent, including that the 80-point threshold still overrides a self-declared
`pass` at score 20.

The documented `synthesize_mock_data` failure was a **stale fixture**, not a code defect: the
workspace's pages import `images`, `reservations` **and** `seed`, and the canned response defined
only the first two, so validation correctly refused to write a `mock.ts` missing an imported symbol.
Fixture completed, and the fail-closed path it had been exercising by accident is now pinned
deliberately.

`test_task3_security.py::test_workspace_writes_fail_closed` failed on the same
`src/pages/*.tsx` canonicalisation that bit my own fixture: `write_file` renames non-canonical page
names and unlinks the pre-canonical entry. Worse, `assert not linked_file.is_symlink()` was passing
**vacuously** — the path no longer existed. Fixed by using an already-canonical `LinkedPage.tsx` so
the symlink is genuinely replaced in place, and by asserting `is_file() and not is_symlink()`.

**Watch for this trap in fixtures:** any test writing `src/pages/Foo.tsx` through `write_file` gets
`FooPage.tsx` and loses `Foo.tsx`.

## Session 1's changes — unchanged summary

Imagery subject from the business (**now partly regressed, see P0-1**); asset 404s instead of
`200 text/html`; the visual loop can fail a build; slot-fill retries and a real TSX parse check;
shell identity and a 3.64 MB lighter scaffold; `tsc` in the pipeline; prop shapes derived from
component sources for ~649 tokens; `_js()` fixing all 31 `json.dumps` JSX-attribute call sites;
route normalisation 17 → 10; nav dedup; the servable vision model. Full detail in
[docs/PREVIEW_QUALITY_FINDINGS.md](docs/PREVIEW_QUALITY_FINDINGS.md) and the archived handoff.

# The QA harness

`scripts/preview-qa.sh <request_id> [tag]` reports what the pipeline's own gates cannot see: shell
identity, the declared route table, every image reference resolved **by content-type** rather than
status code, `tsc` errors by code, leaked placeholder/jargon/escape strings, bundle weight, and
screenshots of every public route. Artifacts land in `.preview-qa/<tag>/` (gitignored);
`QA_OUT_DIR`, `QA_BASE_URL`, `QA_CHROME` override defaults. Run from the repo root.

The content-type check is the important part: a missing asset used to return `200 text/html` via SPA
fallback, so any status-code check saw a healthy app.

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --no-sandbox --hide-scrollbars --virtual-time-budget=9000 --window-size=1440,2000 \
  --screenshot=/tmp/shot.png "http://localhost:8001/api/preview-apps/<id>/"
```

**Baseline for request 36**, to compare any future run against: title `Preview App`, 7 broken image
paths, 6 dental photos, **59** TypeScript errors, 1.09 MB of clinic JPGs in `dist`, and a route
table containing `/works/:slug/:slug` plus `/admin/:id` shadowing `/admin/dashboard`.

# Environment gotchas that cost time

- **The test command.** See above. This is the big one.
- **`docker compose exec api` does not reload code.** No `--reload`, so edits are invisible until
  `docker compose up -d api` (not `restart`, which does not re-read `env_file`). Verify with
  `docker compose exec api env | grep KEY`.
- **`write_file` renames `src/pages/*.tsx`** to canonical `*Page.tsx` and unlinks the original. Name
  fixture pages canonically or you will measure the rename instead of your code.
- **`POST /api/requests` is multipart `Form(...)`, not JSON.** Use `-F`; the trailing slash
  307-redirects and drops the body.
- **Local DB is Postgres.** `sum(bool)` fails; use `count(*) FILTER (WHERE ...)`.
- **`tests/appspec/` cannot always be collected as a directory** — importing
  `app.domain.appspec.validation` before `app.application.appspec` triggers a circular import. Name
  individual files.
- `awk` and `timeout` are absent from this shell; `ugrep` rejects some PCRE repeats.
- **Working directory drifts.** A `cd` persists across tool calls; prefix with
  `cd /Users/maurice/Documents/Dev/BMV` or `docker compose` and `git` both fail confusingly.

# If you are demoing to an investor

**Fix P0-1 first.** Until then any brief whose industry words mis-bucket ships confidently wrong
photography — and the buckets mis-fire on ordinary phrasings like "auto repair" and "boutique law
firm". P0-2 through P0-5 can either pass a preview nobody looked at or withhold a correct one.

Do **not** show request 36 — it is the broken baseline, kept only for comparison. Generate fresh,
run the QA harness, and actually look at the screenshots before showing anyone.

Reproduce the reference brief with the `curl` in the archived handoff (unchanged). Expect
`product_kind=storefront`, recipe `editorial`, and 8–12 minutes end to end. Per the previous
handoff: do not re-run rematerialize or pack-seed nit loops for a demo.
