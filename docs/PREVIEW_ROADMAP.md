# Preview pipeline roadmap — variety and latency

**Written:** 2026-08-01 · **Baseline:** `90f4d5f` · **Suite:** 1,107 green

Two goals, in the owner's words: *"most generations are the same template which is getting
disgusting"* and *"I don't want the generation to take more than 10 minutes."*

This plan is grounded in a six-part audit of the tree, three adversarial reviews of an earlier
draft (all three returned **unsound**, 9 fatal objections), and one controlled experiment —
requests 68 and 70, same business, one field different.

---

## Status — updated 2026-08-02

| Item | State |
|---|---|
| **0.3** gate-issue classification (content vs layout) | **done** — `a0ecff8`. **Reverses the branch 2.6 had chosen** |
| **0.6** call census, `ai_usage_events` defects | **done** — `a4f8b55` |
| **1.1** request-scoped deadline + degradation contract | **done** — `c534fdf`, `58b4956`. **540 s, not 480** |
| **1.2** model-chain dedupe | **done** — `ac10c9b` |
| **1.3** per-ask ceiling | **done** — `c534fdf`, `58b4956` |
| **1.4** screenshot session budget | **done** — `a919f86` |
| **1.5** documents off the critical path | **done** — `c534fdf` |
| **1.6** JSON extractor | **done** — `ac10c9b`, and the diagnosis in this doc was wrong; see below |
| **1.7** validate repair-plan paths before the first write | **done** — `1b5e0d1` |
| **1.8** industry derivation + placeholder gate | **done** — `ac10c9b`, `a919f86`. Token-length work still gated on 0.1 |
| **1.9** bound items to the image pool | **done** — `ac10c9b`, **verified live on request 73** (12 items, below) |
| **1.10** JS test runner (vitest) | **runner done, CI green-on-main pending a merge.** `backend/preview-template-tests/` — vitest 4 + jsdom + testing-library, 9 tests over `SkeletonComposer`, all nine mutation-tested by `tools/mutate.py` with zero survivors. It is a **sibling package on purpose**: the template's `package.json` is the shared-npm cache key, so a devDependency there costs the next generation a cold `npm ci` inside the run (below) |
| **1.11** bound the post-deadline reserve | **still open. First attempt was wrong and is reverted.** Clipping the capture session's budget to the remaining cap bought **nothing on the cap and cost every judged page**: requests 80/81/82 went 2-of-3 over 600 s (vs 1-of-3) and `visual_pages_reviewed` went **10-of-18 → 0-of-18**. Contention was 0.0 s on all three, so the clip was not even answering a queue. What survives is the lock-**wait** bound, which is cheap and never fired. The overrun is not capture: the gate, the AI repair and finalize all run past the deadline and nothing bounds them. Capping one consumer of an unbounded reserve tightens the distribution without closing it |
| **1.12** a mandatory stage with no deterministic path | **open, new.** `architect` raises past the deadline and request 74 shipped nothing. See the DoD section |
| **0.9** convert the never-collected test files | **done, and it paid.** Eight files, not the six in the brief — the collection guard found `test_qa_probe.py` (empty) and `test_quote_fix.py` (a print probe) immediately. Suite 1,265 → **1,443 collected, 1,434 passed / 1 skipped / 8 xfailed** |
| **2.9** contract-invalid pages are scaffolded, never re-asked | **open, new, and this is the sameness complaint.** A syntactically valid page that fails the catalogue contract is replaced wholesale by the generic deterministic scaffold with **no retry**. `_slot_fill_rejection` only rejects empty/truncated/no-export/unparseable, so the retry loop never sees a contract violation. **26 pages across requests 74-79** were replaced this way — HomePage, GalleryPage, ServicesPage, RoomsSuitesPage, ArtworkDetailPage — with **zero** syntactic rejections in the same runs, so the retry never fired once. Pinned by `test_a_contract_invalid_page_is_re_asked_with_its_validation_errors` (xfail). Fixing it costs ~4 extra asks per run against a cap that request 77 already breached, so it trades directly against Phase 1 |
| critic coverage: surface priority + placeholder gate | **done** — `a919f86` |
| dead-link occurrence counting, DataTable, seed backfill | **done** — `d8ef2e9` |

Suite 1,107 → **1,246 collected, 1,245 passed / 1 skipped / 0 failed**. Phase 0's
remaining measurements — **0.1** (pack thesis) and **0.4** (are `revision_instructions`
expressible as content-key edits) — are **not** done and still gate 1.8's token work
and 2.6 respectively. 0.7 was answered by the audit (388 of 1,012).

### What request 73 verified, and what it did not

Same brief as request 72, deadline armed on both.

| | 72 (before `58b4956`) | 73 (after) |
|---|---|---|
| wall clock | **~37 min** | **579 s** — under the 600 s cap |
| degradations | none recorded; the clock expired and the run kept asking | `['tech','proposal','build_plans']`, all ELECTIVE, all recorded |
| overrun past the 540 s deadline | ~1,700 s | **38.7 s** |

- **1.9 exercised for the first time on ≥ 9 items.** 73's catalogue is **12 items**;
  all 12 bind `item1…item8` (1–4 cycling twice), and **zero** land on
  `images.card1/2/3` — the people-photo role slots that produced "artist at an easel,
  captioned *Oil on Linen*" on request 70.
- **`placeholder_content_shipped` fired on its first live outing** — `[Customer Name]`
  and `[Painting Title]` — and correctly withheld the preview.
- **The detail page scored 79** against 0–5 on 66–68, when the critic was fetching
  `/painting/:id` literally.
- **73 was still withheld**: 4 gate issues, including a severe visual defect on
  `/about-artist` and a dead link. Phase 1 bought the clock and the honesty, not the
  ceiling. Phase 3 is where the ceiling moves.

**Two defects were found by running the pipeline, not by reading it**, and both
were in the deadline work itself. They are written up at `58b4956`; the short
version is that a 1 s ask floor past the deadline inverted the degradation
contract into a fast-fail retry loop, and `_run_with_heartbeat` only checked
its cap once per 20 s heartbeat, so a short cap could not fire. Request 72 ran
**~37 minutes with the deadline armed and expiring on schedule**. The second bug
predates this work: any caller passing a `hard_deadline` under 20 s has always
been silently rounded up to 20 s.

### Two deliberate deviations from this plan, both still standing

1. **`PREVIEW_MAX_FIX_LOOP_SECONDS` was clamped, not deleted.** 1.1 says delete it.
   It is read by callers that have no other bound, so deleting it removes a ceiling
   before the deadline is proven to replace it on every path. Clamped to the request
   deadline instead; revisit once Phase 1's DoD has 3 clean concurrent runs.
2. **`BudgetedAIProvider.ask_chat` still returns `""` rather than raising.** 1.1 says
   raise. Making it raise broke 5 tests that pin *outcomes* (deterministic fallbacks
   preserved), not the mechanism — and the plan's own justification for raising is a
   Phase 2 condition ("under Phase 2 a silent empty string ships a blank site"). Today
   raising converts proven degradations into a pipeline exception that triggers the
   180 s retry. **Exhaustion is now recorded** (`ai_budget/exhausted_chat`), so it is
   no longer silent. Deferred to Phase 2, documented at `ai_budget.py:_refuse`.

---

## Diagnosis

Three failures wearing one complaint.

**1. Sameness is axis collapse inside one kit.** The type system permits ~7.46 × 10⁸
combinations and renders **~5 perceived designs**. `recipe.ts:29-82` is six
`Record<RecipeId,…>` maps keyed by one enum; 8 of 11 public bands have zero layout variants;
`CatalogGrid.tsx:145` is a single three-column grid for every business on earth; and the emitted
`@theme` block (`index_css.j2:5-23`) declares **no type scale, no spacing scale, no container
width, no grid tokens**. Every site is the same six bands, at the same measure, in the same flat
stack (`SkeletonComposer.tsx:91-98`).

**2. Latency is model wall-clock, spent serially.** AI time is 1.01–1.06× of total wall clock on
all three audited runs. The build substrate is innocent: npm attach 0.0005 s, vite 0.52–0.63 s,
tsc 1.75–1.83 s — **under 12 s of a 688 s run**.

**3. The variance, not the mean, breaks the 600 s promise.** Request 68's quality-repair loop was
882.2 s — 52.7 % of the run — **for zero applied file operations**. Two of three audited runs
shipped nothing at all.

---

## What request 70 changed, and what it cost us to learn

Requests 66/67/68 were created with an **empty `industry` field** — a test-harness omission.
Request 70 is the same business description with the field populated. The delta:

| | 68 (`industry=''`) | 70 (`industry` set) |
|---|---|---|
| `imagery subject` | `generic` | `art` |
| catalogue cards showing a painting | **0 of 3** | **9 of 11** |
| `seed.items` | 3 marketing blurbs, rendered as inventory | **11 real records** with medium, dimensions, year, price |
| dead links | 8 across 5 pages | **0** |
| quality gate | FAILED, withheld | **PASSED first pass, no repair invoked** |
| terminal state | `preview_url: null` | shipped |

**Three plan-level consequences.**

- **Imagery is no longer the hard problem.** The remaining defect is a bound, not a content-
  verification problem: the imagery service supplies **8** `item*` slots, the model wrote **11**
  items, so items 9–11 wrap onto `images.card1/2/3` (`mock.ts:459,471,483`) — and `card2`/`card3`
  are the role images ranked last *precisely because they show people*. That is why 2 of 11 cards
  are a photograph of someone at an easel captioned "Oil on Linen". **Cap items at pool size, or
  extend the pool.** Hours, not weeks.
- **The pack-coverage thesis needs re-testing before it is funded.** The audit found ~half of
  businesses miss an industry pack via `_MIN_DISTINCTIVE_TOKEN_LEN = 6` (`loader.py:43`), which
  rejects `spa`, `gym`, `yoga`, `cafe` — packs that exist. But the pack matched on **both** 68 and
  70 (`art-gallery-portfolio-home`), even with an empty industry. Pack selection was not the
  failure here. The token bug is real; its blast radius is unproven.
- **A scaffold is only as good as the seed it reads.** Fallback count did not improve (4 of 12 →
  5 of 17), but the *consequence* inverted: the same scaffold that rendered blurbs as inventory on
  68 produced the best gallery page the pipeline has shipped on 70. Do not spend on the fallback
  rate; spend on seed quality.

**And one genuine product defect the experiment exposed:** the pipeline accepted an empty
`industry`, had `"fine-art gallery … original oil paintings"` sitting in the description, and
silently resolved to `generic`. No warning, no derivation, no gate.

---

## Verdict on the "content as data" hypothesis

> *Four AI writers emit TSX; flipping to "AI emits structured content, templates are pure
> renderers" makes templates cheap, deletes the repair machinery, and clears 600 s.*

| Claim | Verdict |
|---|---|
| Deletes the repair machinery | **True.** ~2,500 lines delete outright (`fix_agent.py` 460, `quality_repair.py` 433, `deterministic_repairs.py` 69, four `build_phase.py` blocks ≈ 250, `preview_app_fix.j2` 89, `preview_app_file.j2` 254, `quality_gate.py:819-916` ≈ 98). Two rollback systems vanish as a side effect. |
| Clears 600 s | **False.** Post-flip mean ≈ **411 s**, but the worst audited run *minus its entire repair loop* is still 757 s. The flip cannot bound the tail. **600 s is won in Phase 1 by a deadline, not by the refactor.** |
| Templates become cheap | **Only with one specific correction** — the deterministic renderer must move out of Python into the template. And it was never the variety lever. |
| "Every template is a new language for the model" | **False.** The model never sees the template — only a contract compacted to 4,900 chars (`ui_catalogue.py:70-74`). Adding templates multiplies **Python emitter and validator** cost, not prompt cost. |

---

## The 100-templates question: the answer is three

| Path | Per template | ×100 |
|---|---|---|
| Re-skin the existing kit (same 46 exports, 30 slots, 265 props, all DOM contracts) | 60–110 h | **3.3–6.1 engineer-years** |
| An off-the-shelf React template with its own vocabulary — **this is what "100 React templates" means** | 240–460 h first, 120–220 h after | **13–26 engineer-years** |

Plus **23.5 GB** of `_shared_npm` at N=100 (235 MB per fingerprint, measured; there is no prune,
evict, or rmtree anywhere in `backend/app`), 100 forks of a 1,713-line fallback, and 187
template-reading tests to fork.

**And it would not fix the complaint.** 100 re-skins render the same one-layout bands, at the same
hardcoded `clamp()` scale, in the same flat stack.

**Do instead:** treat the 100 templates as a **design-reference corpus** — triage them into a
signed archetype spec sheet (grid logic, type ramp, spacing scale, container width, image
treatment). Same visual diversity, ~1 % of the cost, inside a kit that already satisfies all 68
conformance clauses. Then build **one** second kit, measure the real hours, and **cap at three**.

**The target is not a template count.** It is: *of 20 synthetic businesses, no two home pages and
no two catalogue pages share a silhouette.* Today: ~5 and ~1.

---

## Wall-clock ledger (run-67 shape, 688.0 s)

Every "after" figure has a named mechanism or it is not claimed.

| Stage | Now | P1 | P2 | Mechanism |
|---|---:|---:|---:|---|
| pre-preview blueprint + AppSpec | 94.3 | 94.3 | 94.3 | data dependency; not concurrent |
| preview start + AppSpec re-ensure | 9.1 | 9.1 | 9.1 | — |
| planning (product_kind, imagery, recipe) | 77.4 | 77.4 | ~68 | `build_design_manifest` concurrent with imagery |
| architect | 21.0 | 21.0 | 21.0 | — |
| codegen / content | 55.9 | 55.9 | ~35 | **content asks batched by surface — 3, not 12** |
| design critic + guards + assemble | 30.5 | 30.5 | ~20 | — |
| typecheck + fix agent | 161.4 | ~45 | ~5 | P1: JSON-extractor fix + chain dedupe |
| visual critique | 88.2 | 82 | ~50 | widen vision fan-out 2 → 6 (network-bound) |
| imagery verification (new) | — | — | +15 | one contact-sheet call, same wave |
| quality gate | 48.1 | ~40 | ~2 | evaluate only; repair deleted |
| refine + rebuild + re-measure | 23.0 | 23 | ~30 | conditional; expected value |
| render smoke + conditional re-probe | 42.0 | 42 | ~52 | **not merged with the critic pass** |
| finalize docs | 37.1 | 0 | 0 | off the critical path |
| **Total** | **688.0** | **~495** | **~411** | |

**Consistency check.** After P2 the mandatory logical-call floor is **16–17**. At the measured
~23 s/call for non-vision calls: 13 serial × 23 = 299 s + one vision wave ~30 s + capture ~60 s +
build ~5 s + deterministic ~20 s ≈ **414 s**. Ledger and census agree within 1 %.

---

## Phase 0 — Measure first (1 week, no behaviour change)

| # | Question | Why it changes the plan |
|---|---|---|
| 0.1 | **Re-test the pack thesis.** Replay 60 days of real `industry` strings through `pick_template_id`; report hit / miss / wrong-family | Request 70 showed the pack matched even with an empty industry. **Sizes or cancels 1.8** |
| 0.2 | `P(refine fires)` per run; does a slot-filled page keep the scaffold marker? | Sets two ledger rows |
| 0.3 | ~~Fraction of gate blocking issues that are content-shaped vs layout-shaped~~ **ANSWERED — see below** | Gated 2.6, and the answer **reverses** the branch the plan had provisionally chosen |
| 0.4 | Are visual `revision_instructions` expressible as content-key edits? | **Gates 2.6** with 0.3 |
| 0.5 | Real `product_kind` distribution (60 days) — `plan_phase.py:119-124` already logs it | Decides whether Phase 3 spends on the 6 public or 9 ops skeletons |
| 0.6 | Per-call latency distribution + the call census | p95 must be **derived by convolution**, not by scaling a mean. Today p95/p50 = 2.4× |
| 0.7 | Test classification: **388 of 1,012** tests sit on TSX-source machinery | ~3× the original budget; goes straight into P2 staffing |
| 0.8 | Spec-level content-density metric, logged in parallel on the current architecture | The `fallback_pages` signal reads a literal marker; after the flip it reads 0 forever or 12 forever. Both are silent |
| 0.9 | Are the 3 script-style test files (2,061 lines, not pytest-collected) run by CI? | Assertions that may never run |

**Also land here:** fix `ai_usage_events.request_id` NULLs (39 of 58 rows in run 67, so per-request
queries undercount by ~⅔); make `success` mean *usable output*, not HTTP 200; add duration logs at
`typecheck.py:494-499` and around `build.py:83`; clean the leaked `mkdtemp(prefix="bmv-dist-")`
backups (`build_phase.py:134`, cleaned only at `:289-291`, outside the try).

### 0.3 answered — the repair edits content, not layout

88 ops across 19 stored repair plans (`.bmv-debug/quality_repair_plan*.json`,
requests 19-73), classified by **what each op actually changed** — a `difflib`
delta between `old` and `new`, not a pattern match over the new blob:

| what changed | ops | |
|---|---:|---:|
| string / identifier edits — `/gallery`→`/collection`, `item`→`artwork`, label and href renames | 41 | 46.6 % |
| content strings ≥ 12 chars | 29 | 33.0 % |
| routes and links | 5 | 5.7 % |
| **layout / structure** | **4** | **4.5 %** |
| changed nothing at all | 5 | 5.7 % |
| whole-file writes | 4 | 4.5 % |

**Method note, because it changed the answer.** A first pass pattern-matched the
*new* text and reported 34 % layout. That was an artifact: almost any TSX blob
contains `className` or `<Capitalised`, so layout won every tie. Diffing what
changed drops layout to 4.5 %. Sampling the "string / identifier" bucket shows
it is overwhelmingly copy and href renames, so the true content share is well
above 33 %.

**Consequence for 2.6.** The plan said: *if 0.3 shows "mostly layout, not
content", demote `visual_defect_severe` to WARN in the same commit that deletes
the repair.* That branch is **not supported** — layout is the smallest
identified category. A spec-level actor (visual finding → content-key edit) is
what the evidence supports, so 2.6 should build that and keep the BLOCK.

Still open: 0.5, whether the critic's `revision_instructions` are *expressible*
as content-key edits, which is a different question from whether the repair's
output happens to be content-shaped.

Worth a ticket on its own: **5 of 88 ops changed nothing**, and the model was
paid for every one.

**DoD:** all nine answered in writing with evidence; `(writer, calls, wall-clock, ops applied)` for
3 fresh runs; a fitted p50/p95 per model.

---

## Phase 1 — Make 600 s a guarantee (2 weeks)

**This is the phase that meets the hard constraint. Not Phase 2.**

**1.1 Request-scoped deadline with a degradation contract.** Stamp `deadline_at = t0 + 480` at the
top of `GenerationPipeline._run_inner`, **before** `blueprint.generate_mvp_blueprint`. Attach it to
the existing request-scoped `AICallBudget` (`ai_budget.py:18-45`). The retry at
`orchestrator.py:200` becomes conditional on `now() < deadline_at - 180` and **inherits the same
absolute deadline** — today it re-runs the whole preview generation with a fresh budget. Classify
every stage MANDATORY or ELECTIVE; the deadline skips only ELECTIVE, and a MANDATORY stage that
would cross it falls through to its deterministic default and records `degraded: [stage]`.
**`BudgetedAIProvider.ask_chat` must raise, not return `""`** (`ai_budget.py:61-63`) — under Phase 2
a silent empty string ships a blank site that passes both tsc and vite.
Delete `PREVIEW_MAX_FIX_LOOP_SECONDS = 900` (`config.py:714`) — 1.5× the entire user constraint.

**1.2 De-duplicate the model chains.** `quality_repair.py:332-337` resolves to
`('z-ai/glm-5.2', 'z-ai/glm-5.2', 'google/gemini-2.5-flash', 'google/gemini-2.5-flash')`, and
`_FAILED_FIX_MODELS` at `:346` is consulted only when *building* the list, never inside the loop at
`:349`. *(Saving is a subset of 1.1's, not additive.)*

**1.3 Per-ask ceiling, not per-call.** `_WALL_CLOCK_BUDGET_FACTOR = 2.5` × `timeout=120` ×
`attempts=2` = 600 s per logical call, and `hard_deadline` is per *attempt*, so model failover
doubles it again. Cap at **120 s per ask inclusive of all failovers and transport retries**. For
MANDATORY stages, **do not fail over on timeout** — degrade and record. Add an absolute socket
deadline that does not reset on byte arrival (one call was held open 1,040 s).

**1.4 Screenshot budget.** `capture_routes_visual(timeout_ms=20000)` applies that timeout **twice**
per route (`screenshot.py:158,163`) — ~40 s/route, serial behind `_SESSION_LOCK`, 12 routes = 480 s
worst case. Add a 90 s session budget; `timeout_ms` → 8000; `wait_until` `networkidle` →
`domcontentloaded` plus the existing `_ROOT_HAS_CHILDREN_JS` — `networkidle` makes the Pexels CDN a
latency dependency. **Merge only the pre-gate captures; keep the post-gate smoke pass unconditional**
(request 41 shipped `aiFeatures is not defined` under `status=ready`).

**1.5 Finalize documents off the critical path.** `orchestrator.py:247,254,261` runs three
document generations serially *after* the preview is built, for 37.1 / 49.8 / 22.8 s the user is not
waiting on. Mark ready first, then run them concurrently.

**1.6 Fix the JSON extractor. — DONE, and this section's original diagnosis was wrong.** It claimed
the failures were structurally complete JSON the extractor could not find. Measured against the six
captured payloads in `/app/data/preview-apps/{67,68,69}/.bmv-debug/fix-agent/`, that is true of
**one**. There were three distinct failure modes read as one:

- **Ours (1 of 6).** Prose before the fence. `_strip_markdown_fence_once` only fired at position 0,
  so the bracket matcher latched onto a `{` inside the model's opening sentence, failed, and
  `break`-ed instead of trying the next candidate. A valid repair plan, discarded.
- **The model's, and unfixable by re-asking (4 of 6).** Inside a ~30 KB `content` value the model
  escapes correctly for thousands of characters and then drifts — bare `"` where `\"` was required,
  or `\` + newline as a shell-style line continuation. Structurally complete, not valid JSON.
  Re-asking never fixed it because it is a habit, not a limit; requests 67 and 69 each burned three
  calls for zero applied ops.
- **A genuine truncation (1 of 6),** `finish_reason: length` from glm-5.2.

Fixed in `shared/json_utils.py`: strict parse first, then every fenced block, then a skeleton-tracking
re-escaping repair pass, then candidate spans — with the decoder's own error in the failure message.
6 of 6 now parse. **Three other extractor implementations exist**
(`appspec/sanitize/preparse_normalize.py:149` carries both original bugs;
`services/page_experience.py:133`; `pipelines/_shared.py:107`) — untouched, flagged.

**The strategic read matters more than the fix.** Asking a model for a 30 KB JSON document with
escaped source code inside it is fragile by construction. That is an independent argument for
ops-only repair (small payloads do not hit this) and for the Phase 2 content flip.

**1.7 Validate repair-plan paths before the first write. — DONE (`1b5e0d1`).** Runs `RepairAPI._safe`
(`quality_repair.py:76-84`) over **every** op before applying **any**; names the offending path in a
single re-ask. All-or-nothing is intact.

*A note on how this was tested, because the first test was worthless.*
`test_a_plan_naming_a_forbidden_path...` passed with the fix reverted — pre-flight
refusal and post-hoc rollback produce **identical end states**, so an end-state
assertion cannot tell them apart. It needed a `snapshot_source` spy to assert the
workspace was never snapshotted, i.e. that no write was attempted. Mutation-test any
guard whose success looks like its failure.

**1.8 Industry derivation and an empty-industry guard.** *(Re-scoped by request 70.)* When
`industry` is absent, derive it from `business_description` rather than resolving silently to
`generic`. Add a blocking gate code `placeholder_content_shipped` using the existing
`early_brand_placeholder_strings()` / `early_brand_placeholder_item_titles()` (`seed.py:411-451`,
today consumed only by `product_face.py:90`). **Size the `_MIN_DISTINCTIVE_TOKEN_LEN` work from
0.1's answer, not from the original estimate.**

**1.9 Bound the item pool. — DONE (`ac10c9b`), verified on request 73.** The imagery service supplies
8 `item*` slots; the model writes N. Items now cycle within the pool, so items 9+ cannot wrap onto the
people-photo role images. Request 73's 12-item catalogue binds `item1…item8` only, `card1/2/3`
untouched by items.

**1.10 Stand up a JS test runner. — RUNNER DONE; the CI job has not yet run on `main`.**
`preview-template/package.json` had `dev`/`build`/`typecheck` only — no vitest, jest,
testing-library, playwright, and no `.github/` anywhere in the repo. Two Phase 2 DoDs depend on a
runner that did not exist. **No test may leave pytest until that CI job is green on main** — that
condition is still unmet, because nothing is pushed.

What landed: `backend/preview-template-tests/` (vitest 4, jsdom, @testing-library/react, vite 8
pinned to the template's major so there is one vite in the tree) and
`.github/workflows/preview-template-tests.yml`, which runs `npm ci` → `typecheck` → `test` on every
push to `main` and every PR. No `paths:` filter: a filtered job reports *skipped*, not *green*, and
cannot serve as a required check.

**Why it is a sibling package rather than devDependencies in the template.** `shared_npm_root()`
keys the shared `node_modules` cache on a sha256 of the template's `package.json` **and**
`package-lock.json` (`npm_shared.py:29-44`). Any byte added to either — a `devDependencies` line
included — changes the fingerprint, so the next generation misses the cache and pays a full cold
`npm ci` *inside the run*, holding `_install_lock` through `contended_lock` while every concurrent
run waits it out. Trios 4 and 5 cleared the 600 s DoD with 9-17 s of margin; a cold install is
minutes. Second reason: `workspace.py:_SKIP_COPY` skips only `node_modules`/`dist`/`.git`, so test
files under `preview-template/src/` would ship inside every generated preview app and be typechecked
by `tsc -b`. The tests import across the directory boundary instead, via the same `@` → `src` alias
the template already defines.

**This generalises: treat `preview-template/package.json` as a file with a runtime cost.** Editing
it is legitimate, but it is never free, and the bill arrives on the next generation's clock rather
than at edit time. Warm the cache out of band before timing anything.

The nine tests pin `SkeletonComposer`: what it throws on, that `shell` is the layout and not a
section, that an explicit recipe order **drops leftover optional slots** (the variety contract —
without it every business collapses into the same long marketing stack) while still restoring a
supplied required section, the `public-utility` content frame with its full-bleed footer, and the
ops rail split. `tools/mutate.py` reverts each of those behaviours in turn and asserts the suite
goes red: **9 mutations, 9 caught, 0 survivors**, source restored byte-identical. Re-run it after
touching the composer.

### Phase 1 DoD — with what is evidenced after four concurrent trios (74-85)

Twelve live runs, four trios of three started 60 s apart, each trio a
`reference_url` run, a `reference_file` run and a plain one, on three different
industries. Trio 1 (74/75/76) is **timing-invalid** — another session ran a
mutation sweep on the same host inside the window — but its *outcomes* stand.
Trio 2 (77/78/79) added the contention instrumentation. Trio 3 (80/81/82) tested
the screenshot lock-wait bound. Trio 4 (83/84/85) is the current code and the
only trio in which **every run finished under 600 s**.

| trio | wall clock | over the 540 s deadline | ≤ 600 s | pages given a visual verdict |
|---|---|---|---|---|
| 2 | 619.7 / 576.4 / 573.0 | 79.7 / 36.4 / 33.0 | 2 of 3 | 10 of 18 |
| 3 | 590.2 / 600.2 / 602.7 | 50.2 / 60.2 / 62.7 | 1 of 3 | 0 of 18 |
| **4** | **591 / 583 / 590** | **51.3 / 43.1 / 50.1** | **3 of 3** | 0 of 18 |

| | Status |
|---|---|
| Every generation ≤ 600 s request-accepted to ready-or-failed, **including** 3 runs started 60 s apart (`_SESSION_LOCK`, `_install_lock` serialize concurrent runs), one with a `reference_url`, one with a `reference_file` | **holds on trio 4, 3 of 3 — with 9-17 s of margin, on n=3.** It did not hold on trio 2 (619.7 s) or trio 3 (600.2 / 602.7 s). Call it met when a trio clears it twice; one clean trio is how the "met and real, on n=1" overstatement happened last time |
| p50 ≤ 500 s. No repair loop > 120 s. No ask > 120 s inclusive of failovers | **p50 still FAILED at 590 s** (want ≤ 500) — the elective guards bought ~10 s, not 90. **The ask ceiling was off by a constant and is now fixed.** Exactly four asks exceeded 120 s across all twelve runs and all four were 135.0 s to the millisecond (135012 / 135010 / 135007 / 135001 ms; 77, 80, 82, 85; `fix_agent`, `z-ai/glm-5.2`, attempt 1, no failover): `_CANCEL_GRACE_SECONDS` was spent *after* the cap fired. Held back inside it now, and the grace cut 15 s → 2 s. Ask p50 is healthy at 8.1 / 5.7 / 9.6 s, so this was the only ask-side breach |
| Zero consecutive asks to the same resolved model id | **was FALSE, now fixed.** `ac10c9b` deduped the *repair* chains and its test pins those; `call_architect`'s three-name chain was never deduped, and `ARCHITECT_MODEL` = `PREVIEW_APP_MODEL` = `TEXT_MODEL` = `google/gemini-2.5-flash` here **and in the test environment**, so the guard could not have caught it. 7 violations across trio 1; request 74's architect wrote 3 rows, one model, all unusable |
| Every degraded run carries a machine-readable `degraded: [stage]` marker | **was FALSE, now fixed.** Requests **73, 75 and 76 each degraded three stages and each stored `degraded: []`** — the marker was only ever a log line at scope exit. `finalize` runs inside `generate_preview_app`; `tech`/`proposal`/`build_plans` are skipped *after* it returns, so it structurally could not see them. Published from `GenerationPipeline.run` now, and verified live on 77/78/79 |
| `placeholder_content_shipped` fires zero times over 20 businesses; an empty `industry` never reaches `generic` silently | **inverted so far** — the gate exists and fires correctly; it caught 2 leaks on 73 and 2 on 68. The DoD wants **zero fires**, which means the *writers* still emit placeholders |
| 11 of 11 catalogue cards show the artifact type the business sells | **9 of 11 on request 70**; 73's binding is correct but its cards were not scored card-by-card |
| Suite green at ≥ 1,107 | **1,288 passed / 1 skipped / 1 failed** — the red is another session's in-flight refactor of `test_phase5_ui_alias_imports.py` (at `f9f41eb` that file has zero test functions), not Phase 1 work |
| Vitest CI job green on main | **runner and workflow exist, `main` has never run them.** 9 tests, 9/9 mutation-caught locally, `tsc -b` clean, pytest unchanged at 1,472 passed / 1 skipped / 8 xfailed. The row stays **unmet** until `.github/workflows/preview-template-tests.yml` is green on `main` — it cannot be closed from a branch |

**The honest summary:** the clock was **not** a guarantee — run it concurrently
and the 600 s cap broke on 3 of the first 9 runs, and two DoD rows marked *done*
were false in production and false in the test environment that was supposed to
pin them. After the elective guards, trio 4 cleared 600 s on 3 of 3 with 9-17 s
to spare. That is the first trio to do it and it is still n=3: the margin is
thinner than the run-to-run spread within a single trio (8 s here, 47 s in
trio 2), so a slower model day puts it back over. **Not "met" — "no longer
reproducibly broken."** p50 is 590 s against a 500 s target, and the 120 s ask
ceiling is still exceeded by design (`_CANCEL_GRACE_SECONDS`, below).

#### Where the 600 s went, on request 77

`RESERVE_SECONDS = 60` was sized from single-run measurements of the
post-deadline render-smoke and capture pass (41-42 s on requests 66 and 67).
That pass goes through `_SESSION_LOCK`. Under three concurrent runs the capture
sessions queue, so the reserve does work it was never measured doing:

| | blocked on `_SESSION_LOCK` | overran deadline by | verdict on its degradations |
|---|---|---|---|
| 77 | 16.9 s | 79.7 s | **CORRECT** — 62.8 s over even with the block removed. But the *cap breach* survives it too: 619.7 − 16.9 = 602.8 s |
| 78 | 35.9 s | 36.4 s | **ARTIFACT** — subtract the block and it lands within 0.5 s of its deadline. It degraded three stages it had the time for |
| 79 | 16.7 s | 33.0 s | **CORRECT** — 16.3 s over without the block, though contention doubled the overrun |

Every wait was on `screenshot_session`; `npm_install` was 0.0 s on all six runs
(warm cache). Trio 1 recorded **zero** contention — the runs never collided,
which is why one trio is not evidence about concurrency either way.

**This is the owner's hypothesis, confirmed but smaller than feared, and in a
place the plan did not look:** not in the 540 s budget, in the 60 s reserve
after it. A deadline whose reserve is unbounded is a 540 s deadline with a
600 s label.

#### The elective contract had one caller (trios 3 and 4)

Every one of the first nine runs finished 33-80 s past its deadline regardless
of what changed between trios, which reads as structural rather than as tuning.
Decomposed against `ai_usage_events`, the 382 s of tail across those nine runs
is **127 s of AI (33 %) and 255 s of non-AI (67 %)** — so `RESERVE_SECONDS = 60`,
which was fitted to the post-deadline render-smoke and capture pass, was fitted
to a minority of what actually runs after the deadline.

The cause: **`should_skip_elective` had exactly one caller in the whole tree** —
the orchestrator's `tech`/`proposal`/`build_plans` loop at `orchestrator.py:315`.
Five of the eight declared `ELECTIVE_STAGES` (`visual_critic`, `quality_repair`,
`refine`, `demo`, `reference_analysis`) were elective in name only: they ran
their expensive deterministic half past the deadline and only their *model calls*
degraded. Request 82 shows it cleanly, in a window where the other two runs had
already finished — the visual critique **starts 18 s past the deadline**,
screenshots its pages, then takes six consecutive `ask budget of 0s exhausted`
refusals. All of the browser cost, none of the verdicts.

Guards added at the two that dominate the measured tail (`build_phase.py:487`,
`quality_gate.py:862`), and `test_the_expensive_elective_stages_are_actually_skippable`
pins the contract for all five by AST rather than by grep — an earlier regex
version of that test falsely flagged the three document stages, which are
guarded through a loop variable and not a string literal.

**What it bought, measured, and the claim it does not support.** Trio 4's tail
averages 48.2 s against trio 3's 57.7 s: **~10 s a run.** The 255 s of non-AI
tail is real, but attributing the bulk of it to these two stages was wrong —
most of it is the post-gate smoke-and-capture pass the reserve was sized for.
What the guards did buy is the difference between 3 of 3 under 600 s and 1 of 3.

**It costs nothing in judged pages, and that was the thing to check** — the
reverted session-budget clip (1.11) failed on exactly this axis. Over six
observations the split is clean: every time the critic ran *past* the deadline
it reviewed **0 of 6** pages (80, 81, 82 — its vision calls were all refused);
every time it ran *before* it reviewed 4-6 of 6 (78 at t=497 s, 79 at t=450 s).
The guard only fires past the deadline, so it removes captures that were already
producing no verdicts and leaves the pre-deadline path untouched.

#### 1.3's ceiling was 135 s, not 120 s

Four asks over 120 s across twelve runs, and **all four the same number to the
millisecond**. A slow model does not produce that. `_run_with_heartbeat` armed
the cancel *at* `hard_deadline`, then joined the worker for a further
`_CANCEL_GRACE_SECONDS = 15.0`, so the recorded latency of any ask that hit its
cap was `cap + 15`. `latency_ms` is measured around the whole `call_with_retry`
in `openrouter_provider.py:231`, so the telemetry was right and the ceiling was
wrong.

Fixed by arming the cancel at `hard_deadline - grace` and cutting the grace to
2 s. The grace only runs once the call is already known to have failed: closing
the socket makes a blocked read raise almost at once, and where it does not
(stuck handshake, dead DNS) 15 s would not have rescued it either — it would
just cost 13 s more before raising the same `Timeout`. The grace is capped at
half the budget so a nearly-exhausted request still gets call time rather than a
budget made entirely of cancellation.

**Why no test caught it.** `test_a_worker_that_ignores_the_cancel_is_abandoned`
monkeypatches the grace to 0.1 s and then asserts `elapsed < 5` against a 0.2 s
deadline — 25× slack. A test that tolerates a 24× overshoot cannot see a 12.5 %
one. The replacement pins the arithmetic directly (120 → 118) so the production
number is checked without a test sitting through a 120 s budget.

#### Dead links were 76 % of everything the gate blocked on

Across trios 2-4, nine gate failures carried 49 blocking issues. **37 of them — 76 % — were dead
links**, and **5 of the 9 failures were dead links and nothing else**. That single class was the
largest reason a finished preview was withheld.

Measured, they are neither typos nor routes assembly dropped (`declared - rendered` is empty on all
of 78/81/82/84/85): the writers link to pages that were never planned. Of the 31 distinct dead hrefs,
**22 have no plausible target at all**, so retargeting could never have been the whole answer.

Repaired deterministically in `safety/dead_links.py`, inside `apply_workspace_guards` — before every
build attempt, so it costs no ask and no second `vite build`, and it still works past the deadline:
retarget to a served parent or dash-prefix (9), drop the `href` from a tag whose contract we own (3),
delete the whole entry when it is an object inside an array (12), ground to `/` and count it as a
last resort. Replayed over all nine stored workspaces: **31 → 0**. Trio 5 confirmed it live with
**zero dead-link gate failures**.

Two upstream defects it exposed, both fixed at source:

- `normalize_mock_navigation` judged nav entries against the *architect's declared* routes rather
  than the shipped router. `served_route_paths` exists precisely because those diverge — that is how
  78 and 81 shipped nav items for `/contact` and `/gallery` that no `<Route>` served.
- The template's own `MarketingHero.DEFAULT_PRIMARY_CTA` was `href: '/gallery'`, so every app the
  architect built without a gallery shipped a dead hero CTA on every page (78, 81, 84).

**The grading is graded because the first version was wrong in a way the gate could not see.**
Grounding every unresolvable href shipped request 88 with 33 of 81 internal links pointing at `/` — a
footer whose Activities, Contact and Privacy Policy entries all landed on the home page. That reads
as navigable and is not, which for a demo is worse than the dead link, and it is the same mistake as
the reverted screenshot clip in 1.11: the gate metric improved and the artifact got worse. **When a
fix moves a gate number, measure the artifact on its own axis.**

*Residual:* `AiFeaturePanel.tsx:44` hardcodes `/ai-features`. Template-owned, so the guard skips it
and the restore would revert an edit anyway; `AppLink` requires `href`, so there is no safe removal.
Dead in 1 of 9 runs and non-blocking there.

#### The failure mode the contract exists to prevent, still live

**Request 74 stored nothing at all** — no `preview_app`, no `roles`, an empty
`generated_pages`. At t=540.4 s `call_architect` started and raised 9 ms later
with *"Architect agent failed to produce valid JSON"*. No model was asked
anything: past the deadline every ask budget is zero. The orchestrator read
that message as transient, looked for the 180 s retry runway, found none, and
the `role_pages` fallback under `except Exception: pass` produced nothing
either.

`architect` is in `MANDATORY_STAGES`, whose contract is that such stages *"take
their deterministic path"*. **It has none** outside the AppSpec branch, and
74's AppSpec had already crashed on truncated output after 390 s of the 540 s
budget. The error now names the deadline (`require_model_time`), which fixes
the misattribution — **it does not make the run ship.** Two open questions for
the owner, both design decisions rather than defects:

1. Should `architect` get a deterministic route builder from `plan` (the
   machinery synthesises `roles` from plan already, but never `routes`)? Note
   that past the deadline `codegen` would be refused too, so the run would ship
   an architecture and no pages.
2. Should a mandatory stage be *bounded* rather than only refused — `appspec`
   spent 72 % of one request's budget and still failed.

### Phase 1 risk, stated plainly

**1.1 and 1.3 deliberately ship worse previews on bad runs** — a degraded preview instead of a
1,675 s run that ships nothing. Two of three observed runs already ship nothing, so this is a strict
throughput improvement and a temporary ceiling regression. Phase 2 recovers the ceiling.

---

## Phase 2 — One spec; Python emits data, not TSX (8–10 weeks, 2 engineers)

Budgeted at 8–10 rather than 5–7 because **0.7 measured 388 tests on TSX-source machinery**.
Schedule pressure on test surgery is how a 40-defect regression ledger gets deleted as "obsolete".

**2.0 Derive the schema, freeze it in two parts (1 week).** Run `load_ui_type_declarations`
(`ui_catalogue.py:295-317`) over `src/ui`, cross with `catalogue.json`'s 265 props and 30 slot ids,
emit the pydantic schema from the intersection.
*Freeze now:* `SiteSpec.brand / routes / nav / content / images / aiFeatures`.
*Leave open, versioned, additive-only:* `SiteSpec.design` — the axes that make a designer say
"different site" are discovered in 3.3/3.6, weeks 8–12.

Two hard rules, both from verified failure modes:
- **Python-facing route keys stay snake_case.** `skeleton_id` has 272 refs across 32 files. The
  sharpest edge: `has_catalogue_routes` (`protected_paths.py:9-14`) returns False when no route
  carries `skeleton_id`, and `is_template_owned_path` opens with it — **a camelCase key silently
  disables all template-ownership protection**. Also make `has_catalogue_routes` fail closed.
- **Emit `src/data/site.ts` with `satisfies SiteSpec`, and keep a per-request `tsc --noEmit` as a
  hard gate.** `run_build` (`build.py:21`) runs vite only; esbuild strips types without checking, so
  a `satisfies` violation ships. tsc is 1.8 s — under 0.5 % of budget. **Drop the repair round, keep
  the measurement.**

**2.1–2.3 Move the renderer into the template (4–5 weeks).** `scaffold.py` (1,713) +
`utility_compositor.py` (839) become a React renderer under `src/render/`. This is what collapses
per-template cost from 240–460 h toward 60–110 h.

**Two non-negotiable constraints**, all three failure modes verified in the tree:
1. **Every route keeps a real file** — `GalleryPage.tsx = () => <SpecPage routeId="gallery" />`.
   `_smoke_routes` (`finalize.py:147-168`) dedupes on `component_file`; 12 routes sharing one file
   makes the render smoke check probe **one** page and log success. 167 references key on it.
2. **The terminal stub stays Python-emitted**, importing only `react` and `react-router-dom`. If the
   fallback and the failing writer share an implementation, one renderer bug crashes all 12 pages and
   the repair re-crashes them.

**2.4–2.5 Flip the writers (1 week).** Slot-fill (`generate.py:269-489`) and the freeform path
(`:491-684`) collapse into **content asks batched by surface — 3, not 12**. This is the only lever
that removes double-digit call count. Parallelise the codegen retry loop (`codegen_phase.py:122` is
a serial `for`, triggered by exactly the failure mode that dominates on a bad provider day).

**2.6 Delete, in dependency order (3 days) — gated on 0.3 and 0.4.**

**The hard gate:** `visual_critic.py:1288` raises `visual_defect_severe` at BLOCK, and **the only
path that clears it** is the AI repair touching the file → verdict retired → gate passes. A
deterministic re-render produces identical pixels, so `_remeasure_repaired_pages` → `_regate_after_
remeasure` re-blocks with the same score: **a guaranteed livelock into shipping nothing**. So either
land a spec-level actor first (visual finding → design-axis reselect or content-key edit), **or
demote `visual_defect_severe` to WARN in the same commit that deletes the repair**, and say so in
the release notes.

**What stays:** `evaluate_quality_gate` and `heal_quality_gate` — **every issue code**, because the
codes are the regression ledger for 40+ shipped defects.

**2.7 Retarget the validators (3 weeks, parallel track).** Every validator reads page *source text*;
under a renderer they see a three-line wrapper and go quiet — this codebase's recurring fail-open
mode. **Before any of it lands: write one positive test per gate code** and add a collection-time
assertion that every code in a `report.fail(` call is named by a test. Measured today: **11 of 18
fail codes are never named anywhere under `tests/`**.

Notable retargets: `journey.py`'s `LISTING_COMPONENTS` tag-match → section-component query; the dead-
link sweep → **every href in the spec vs every path in the spec, both data** (the class becomes
unrepresentable); `quality_gate.py:101-218`'s 19 component-name greps; and
`_route_table_is_stale` (`:391-415`), whose `re.findall(r'<Route\s+path="…"')` **returns `False` on
zero matches** — a data-driven router makes that three-commit-old guard silently no-op.

**Ownership, in the same commit that creates the files:** extend `is_template_owned_path` to
`src/render/**` and add `src/data/site.ts` as generator-owned **by full canonical path**. Blast
radius inverts after the flip: one bad write takes down 12 pages.

**2.8 Imagery (1 week).** Persist the candidate pool — `_fetch_pexels_images`
(`industry_images.py:479-537`) returns a flat `dict[slot, url]` and discards spares, so a rejection
has nowhere to go. Then per-slot-policy verification: object slots must depict the artifact named by
`content.items[i].title`; scene slots must depict the *industry*. One contact-sheet vision call,
folded into the existing wave. **Hero subject policy keyed on `product_kind`** — request 70 got this
right by accident (home hero a painting, `/artist` hero the artist at her easel); make it deliberate.

### Phase 2 DoD

1. Data-bound content props ≥ 95 % **and** `placeholder_content_shipped` fires zero times over 20
   businesses. *(The first alone is satisfied by mad-libs.)*
2. Inline prose in page TSX ≤ 200 chars (wrappers only; today 13,540).
3. Zero dead internal links by the spec-level cross-check.
4. The typecheck record exists, its `source_fingerprint` matches shipped source, `error_count = 0`,
   on 5 consecutive runs.
5. `SiteSpec` key-set identical across 5 runs of 5 industries (today: 1 key common to 27 workspaces).
6. p50 ≤ 420 s; p95 ≤ 540 s, **derived by convolution over the 0.6 census, not asserted**.
7. `len(_smoke_routes(architect))` equals the count of non-wildcard routes with a page file;
   `catalogue_route_for_file` is injective.
8. **No module outside a named allowlist may write `src/pages/**.tsx` or `src/render/**`** —
   enforced at runtime inside `workspace.write_file`, allowlist pinned by test.
9. **Total collected test count never drops below 1,107**, asserted in CI.

### The nav guarantees — how they are actually protected

Do **not** pin `[data-public-header]`, `#inquire`, `data-footer-variant` etc. by source grep. That is
the class of guard `90f4d5f` just spent a commit removing — `test_the_scroll_reset_ships_one_
behaviour_from_two_files` documents in its own comment that pinning the alias map "let the two drift
anyway… for two rounds with this test green."

`tests/preview_app/test_nav_contract.py` is a **rendered-DOM assertion** through the existing
Playwright path, asserting the numbers request 70 verified:
- `scrollHeight` delta between scroll-0 and scroll-past-24px is **0** on every route;
- a cold load of `/<detail>/1#inquire` lands the target's `top` in **[16, 48]** (measured: 25 px);
- hero content clears the measured header on every public route;
- `SkeletonComposer` still **throws** on a null required slot, and a spec with a null required
  section stubs **one** route, not twelve.

Source greps survive as a cheap pre-filter, never as the contract.

---

## Phase 3 — Variety: authored designs with within-recipe axes (10–12 weeks, from week 4)

**The strategic call.** Axes over one silhouette is one system wearing hats — five of six heroes are
a `min-h-[100svh]` full-bleed photo plane and all 11 bands hardcode `max-w-[92rem]` and
`px-6 py-28 lg:px-12 lg:py-36`. But eight authored recipes each hardcoding their own clamps is how we
got here. **Deepen the 6 public-reachable recipes into complete designs that each own a type ramp,
spacing scale, container width, grid logic, image treatment and page composition — expressed as
tokens, with axes as *within-recipe* choices from a declared valid set, never a free cross-product.**

**3.0a Brand voice — the kit speaks in one business's voice on every site.** A sweep of
`src/ui/**` found 92 hardcoded strings; most are legitimate chrome. These carry *business voice*
and are a sameness defect, not a leak (none is in `_BANNED_COPY`):

*Unoverridable literal JSX — no prop exists, so no caller can change them. Each needs a prop first,
exactly as `CTABand`'s eyebrow did:* `MarketingHero.tsx:269` "Scroll to taste" (restaurant);
`ProcessSection.tsx:43,79` "The path", "You arrive" (hotel/spa); `InquiryPanel.tsx:119,200`
"Enquiries", "We never share your details."; `AiFeatureDeck.tsx:71` "Previewed on this hub";
`BookingPanel.tsx:135,206,210` "Choose treatment", "Treatment", "Duration" (clinic);
`ScheduleRail.tsx:104,134,143,145` "Level", "Availability", "Waitlist" (fitness);
`ConfirmStage.tsx:85` "What you can do next".

*Overridable defaults carrying business voice:* `BrandFooter.tsx:67` — agency marketing copy in
every footer, the worst of these; `CatalogGrid.tsx:67,69,70` "/gallery", "The collection", "pieces"
as the default catalogue; `CashPulseBar.tsx:27,28` a fabricated "$48,220"; and three CTA defaults.

**3.0 The design corpus, signed (1 designer-week, runs during Phase 1).** This is where the
100-template impulse is captured. Deliverable is not a list of names but a **signed spec sheet per
archetype**: grid logic, type ramp (six named steps with actual clamp values), spacing scale,
container width, image treatment, and the catalogue archetype it pairs with. Cut to what a named
designer will actually sign: **4–6 heroes, 3 type ramps, 3 densities, 3 catalogue archetypes, 2 page
compositions.** For scale: `MarketingHero.tsx` is 568 lines for six variants.

**3.1 Break the enum (1 week).** The six `Record<RecipeId,…>` maps become defaults; the rendered
value comes from `SiteSpec.design`. Honour the props the kit discards
(`MarketingHero.tsx:90-91`, `FeatureBento.tsx:54-55`). Implement `'split'` — declared at
`registry.ts:148,496,618`, no branch, silently falls through to cinematic.

**3.2 Recipe/pack compatibility (3 days).** Do **not** decouple pack order from recipe —
`design_recipes.py:653-668` fails closed on purpose (*"pottery → agency stack"*). Instead each pack
gains **`compatible_recipes: [ids]`**. Also, `pick_recipe_id`'s fallback rotates over eight recipes,
three of which `plan_phase.py:129-132` then nulls for public kinds — rotate over the *reachable* set.

**3.3 + 3.6 Tokens and composition, together (4 weeks).** Run as one workstream so composition is not
the thing cut when the schedule slips — it is the one that changes the silhouette. Add
`--text-display/-hero/-h1/-h2/-body/-meta`, `--space-section/-block/-gutter`, `--container-max`,
`--grid-rhythm`. Refactor the 11 public bands off hardcoded values. Retire the three `[data-recipe]`
padding hacks. Wire `density` — computed today and reaching nothing on the public surface.
**`--container-max` must differ meaningfully per recipe**; at least two recipes default to a
two-column or offset body, not the flat stack. **Gate every commit on the rendered-DOM nav-contract
test** — hero clearance and anchor offset are spacing-dependent.

**3.4 Band layouts — CatalogGrid first (4 weeks).** `CatalogGrid.tsx:145` is one grid for every
business; it is also the page the owner screenshotted. Three archetypes differing in **grid logic,
not spacing**: (a) varied-ratio wall with a lead item spanning two columns — portfolio, gallery;
(b) editorial list, full-width row per item — services, property; (c) dense spec grid, 4–6 columns —
retail, inventory. **Image aspect policy is part of the archetype.** Then features → cta → showcase →
testimonials → process → credentials.

**3.5 Collapse the three systems fighting over ten variables (3 days).** `design_overlay`'s six font
pairs are unreachable (`brand_locked` always true), its ten token overrides wipe the recipe's
identity, and two recipes hard-code their palette back in CSS. One resolution, in Python, into
`SiteSpec.design`. Delete the losing layers.

**3.7 Two distinctness gates (1 week).**
1. **Mechanical — silhouette, not enum identity.** Per page, the ordered list of *(section component,
   rendered column count, container-width bucket, media aspect ratio, section-height bucket)*. Over
   20 synthetic businesses: **no two home pages and no two catalogue pages may share a silhouette.**
   A recolour cannot pass it. *(The naive version — a tuple over five enums — is satisfied with
   certainty by 20 permutations, the same failure as `len(set(faces.values())) >= 4`, which the
   current collapse already passes.)*
2. **Human — a standing contact sheet** of 20 home pages and 20 catalogue pages side by side. **Run
   it once now, on HEAD, to establish the baseline.** Blocking at three milestones only: 3.0 sign-off,
   3.4 exit, 3.7 exit.

### Phase 3 DoD

- Silhouette gate passes on home **and** catalogue over 20 businesses (today ~5 / ~1).
- Designer sign-off at the three milestones: "these read as different sites."
- Each `SiteSpec.design` axis independently settable within its recipe's valid set, with a test
  flipping one axis and asserting a DOM or computed-style change.
- Zero regressions in the rendered-DOM nav-contract test.
- No page uses a hardcoded `clamp()`, `py-28`, or `max-w-[92rem]`.

---

## Phase 4 — Residual AI path, then kit #2 (3 weeks)

**4.1 What is actually movable.** Two tempting optimisations are false and are withdrawn: blueprint
and AppSpec cannot run concurrently (`capture_derived_context` feeds `ensure_approved_app_spec` — a
data dependency), and imagery cannot be prefetched with the blueprint (the direction is reversed;
`get_images_for_industry` reads the AI-authored plan). **What is real:** run `build_design_manifest`
concurrently with the imagery block (~9 s), and make recipe resolution pure Python after 3.1/3.5
(~4 s). Total after P4: **~402 s**.

**4.2 Kit #2 — gated on Phase 3's DoD.** Building a second kit before the axes exist just produces a
second re-skin. Budget **40–80 h**. Measure the actual hours and set N from that; recommendation,
to be revised by that measurement: **cap at 3**.

Constraints that hold at any N > 1: one dependency set and one lockfile
(`_template_lock_fingerprint` hashes both); **add eviction to `_shared_npm` before N > 1** — there is
none; per-fingerprint lock plus a cross-process guard (`_install_lock` is intra-process only); and
the three hardcoded `PREVIEW_TEMPLATE_DIR/node_modules` resolutions mean each template dir carries
its own 194 MB install.

---

## Sequencing

```
Week  0   1   2   3   4   5   6   7   8   9  10  11  12  13  14  15  16
      ├P0─┤
          ├─── P1 (600 s lands here) ───┤
          ├ 3.0 designer corpus ┤ (signed)
                  ├2.0┤
                      ├──── 2.1-2.3 renderer port ────────┤├2.4-2.5┤├2.6┤
                      ├──── 2.7 validator retarget ───────────┤
                      ├─ test surgery (388) ──────────────────────┤
                              ├3.1┤├3.2┤├─── 3.3 + 3.6 ───┤├──── 3.4 ────┤├3.5┤├3.7┤
                                                                              ├4.1┤├4.2┤
```

**Hard dependencies:** P0 before everything. P1 before P2 — it meets the constraint and keeps a
shippable product alive during a 10-week refactor. 2.0 gates the renderer port and the validator
retarget; it does **not** gate Phase 3, and Phase 3 does not gate it. 2.6 gates on 0.3 + 0.4.
4.2 gates on Phase 3's DoD.

**Staffing for the full plan:** 2 senior engineers on pipeline, 1 on validators and test surgery,
1 designer-engineer on the kit, 1 designer at 20 %. **4.5 people, ~16 weeks.**

### If you are not staffing 4.5 people

Phase 2 is **not on the critical path for either stated goal**. It buys reliability (today 2 of 3
runs ship nothing) and makes kits cheap later. A small team should run:

- **Weeks 1–3: Phase 0 (trimmed) + Phase 1.** Delivers the 600 s cap and, with 1.8/1.9, the content
  and imagery floor. Both stated goals, substantially met.
- **Weeks 4–16: Phase 3**, with a designer. This is the long pole and it needs design input, not
  engineering throughput.
- **Phase 2 when the failure rate justifies it.** Deferring is legitimate; the cost is that every new
  variant is a prop the model can still get wrong.

Keep every new variant **inside the kit, selected by Python from the recipe** — never a new thing
the AI must author. That is what makes deferring Phase 2 safe.

---

## Do not do this

1. **Do not build 100 templates.** 3.3–6.1 engineer-years as re-skins, 13–26 as real templates,
   23.5 GB of unreclaimable `_shared_npm`, 100 forks of a 1,713-line fallback — and it does not fix
   the complaint.
2. **Do not ship a shared `<SpecPage/>` without per-route wrapper files.** Render-smoke coverage
   silently drops 12 → 1 while logging success.
3. **Do not let the deterministic fallback share an implementation with the renderer.**
4. **Do not delete the gate's AI repair before 0.3/0.4 answer**, or without demoting
   `visual_defect_severe` to WARN in the same commit. Otherwise a severe visual finding is an
   unbreakable livelock and shipping goes from 1-in-3 to 0.
5. **Do not optimise the build.** Under 2 % of a run. `build_phase.py:183`'s "~20 s" comment is 40×
   stale.
6. **Do not add general pool workers.** Whole-run AI concurrency is 1.01–1.06×; the dominant stages
   issue one call at a time. The one legitimate widening is the vision fan-out, which is
   network-bound.
7. **Do not add another guard on AI-authored TSX.** ~6,800 lines / 23 % of `preview_app` already is
   that, and `HANDOFF.md:196` already concluded they "do not fix the cause."
8. **Do not weaken the all-or-nothing repair rule.** Validate paths before the first write.
9. **Do not give the visual critic the screenshot.** It keeps a TSX writer in the loop with unbounded
   latency. Route findings to the composer.
10. **Do not delete gate issue codes when deleting the repair.** They are the regression ledger.
11. **Do not pin nav guarantees by source grep.** Every one of `90f4d5f`'s five fixes would pass one.
12. **Do not decouple pack `section_order` from recipe compatibility.** `f7df0cf` fixed that on
    purpose.
13. **Do not edit the template's `package.json`** until eviction and a warm-cache startup hook exist —
    any change mints a new 235 MB fingerprint and a cold `npm ci` under the global lock.
14. **Do not delete `test_request_40_defects.py` tests as obsolete.** Rewrite each at the new layer,
    keeping docstring and request number.
15. **Do not treat "≥ 95 % data-bound" as a variety metric.** Mad-libs score 100 % on it.
16. **Do not trust a guard that reports success. — Worked example, now fixed.** "NEXT MOVE" shipped
    as visible CTA copy on every generated site while `preview-qa.sh` reported clean *and*
    `strip_template_jargon_copy` logged "template jargon replaced" on every run. Three layers were
    each wrong in a different way. The source says `Next move`; a CSS `uppercase` class renders it
    as `NEXT MOVE`, and the harness grepped the **rendered** casing case-sensitively. The ban table
    (`safety/copy_hygiene.py:137-139`) *did* match it case-insensitively and *did* rewrite the file
    — and then `restore_template_owned_files` (`orchestrator.py:257`, eight lines later) put it back,
    because `is_template_owned_path` claims all of `src/ui/**`. And when this was audited, the
    auditing agent grepped the uppercase literal too, concluded the string did not exist, and nearly
    closed it as unreproducible.
    Fixed in the kit rather than by weakening `src/ui/**` ownership, which is load-bearing
    (`protected_paths.py:132-142`). `test_the_kit_never_ships_copy_the_pipeline_has_banned` is the
    standing invariant. Casing is now split deliberately: folded for rendered copy, exact for
    `PLACEHOLDER` (11 false hits on `placeholder=`) and bracket classes (4 false hits on
    `[location.pathname]` dep arrays).

---

## Summary

| | Today | P1 (wk 3) | P2 (wk 13) | P3 (wk 16) | P4 |
|---|---|---|---|---|---|
| Wall clock (run-67 shape) | 688 s | ~495 s | ~411 s | — | ~402 s |
| **Hard cap** | none | **600 s, by construction** | 600 s | 600 s | 600 s |
| p95 | 1,675 s | ≤ 600 s | ≤ 540 s (derived) | — | ≤ 500 s |
| Runs that ship | 1 of 3 | 3 of 3 (some degraded) | 5 of 5 clean | — | — |
| Shipped tsc errors | 1–16 | — | **0**, fingerprint-verified | — | — |
| Dead internal links | 0–8 | — | **0** | — | — |
| Cards showing the right artifact | 0–9 of 11 | **11 of 11** | — | — | — |
| Distinct silhouettes / 20 | ~5 | — | — | **20** | — |
| Templates | 1 | 1 | 1 | 1 | **3 (not 100)** |

**The bet, in one paragraph.** Four TSX writers are the wrong architecture and Phase 2 removes them —
but with the renderer moved into the template behind per-route wrapper files, and the validators
retargeted from source text to spec *before* the source they read disappears. That refactor does not
deliver 600 s: **the constraint is met in week 3 by a request-scoped deadline and an explicit
degradation contract**, and the flip buys the margin that keeps the deadline from binding. Template
count was never the variety lever — the kit renders five silhouettes from a type system permitting
7.46 × 10⁸. Fix the content floor and the clock in week 3, the silhouettes over weeks 6–16, and buy
three kits instead of a hundred.
