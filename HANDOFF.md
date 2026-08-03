# Session handoff — the no-generation window, day 2 (2026-08-03, session 7)

Successor to session 6's handoff (in git history at `dfbfdd6`). Still-binding parts are restated
below; do not go back for them. Process notes, not product docs.

- **The plan and its evidence: [docs/PREVIEW_ROADMAP.md](docs/PREVIEW_ROADMAP.md).** Read **The
  no-generation window**, then **Status**, then **Phase 1 DoD**. Current as of `475265e`.
- Why the pipeline shipped bad output: [docs/PREVIEW_QUALITY_FINDINGS.md](docs/PREVIEW_QUALITY_FINDINGS.md).

**If you read one thing: [The next step](#the-next-step).** It is a specific ordered list, not a
theme.

> ## ⛔ Still blocked on the owner: OpenRouter credits
>
> Since **19:29 (container clock) 2026-08-02**: *"This request requires more credits, or fewer
> max_tokens. You requested up to 28000 tokens, but can only afford 9612."*
>
> **Top up before running any generation, or every measurement will be wrong** — and wrong in a way
> that mimics the deadline defects. Request 89 degraded `codegen` (MANDATORY) and stored nothing;
> that looks exactly like item 1.12 and **is not**. **Trio 6 (89-91) is void. Do not cite it.**
> Trios 2-5 are clean and are the evidence base.
>
> Nothing below needs credits. That is the point of the window.

---

## State of the repo, in three lines

- **`main` is at `c764f3a`, 9 commits ahead of `dfbfdd6`, NOT pushed.** Working tree clean.
- **Suite: 1,623 passed / 1 skipped / 0 xfailed / 0 failed.** All eight xfails are closed. Run it
  the documented way — see the operating notes.
- **CI still runs vitest only** (`.github/workflows/preview-template-tests.yml`). **I cannot read
  the result.** Check [github.com/Roy-r2004/BMV/actions](https://github.com/Roy-r2004/BMV/actions) —
  1.10 is not done until that job is green there, and **there is still no pytest job at all**.

---

## The next step

Day 1 is **done, all four**. Day 2 is **2 of 4 DoDs plus the pre-flight**. Work these in order.

### 1. DoD 7 — route bijection *(not started)*

`len(_smoke_routes(architect))` against the count of non-wildcard routes with a page file, and
`catalogue_route_for_file` injective. Pure functions over the archived corpus, no credits.

Something to look at first: **request 33 has an `AiFeaturesPage.tsx` and a nav entry for
`/ai-features`, and no route declaring it.** Found while validating item 3 against the archive. That
is an orphaned page and it is exactly what this DoD is meant to catch, so it makes a good first
test case rather than a synthetic one.

### 2. DoD 2 and 5 — the "before" numbers *(not started)*

Inline prose per page TSX (claimed 13,540 chars) and `SiteSpec` key-set commonality (claimed 1 key
across 27 workspaces). Census over `docs/evidence/preview-workspaces.tar.gz`. **This window is the
only cheap time to take them** and neither has been taken.

### 3. The cheap instrument the pre-flight asks for

Gate failures do not record `skeleton_id`. That is the only reason question 5 of the pre-flight
could not be settled offline — `listing_not_schedule_rail` fires on pages that resolve to *either*
`public-service` or `public-catalog` depending on their purpose text, and only `public-catalog` was
ever affected by the contract clipping. Small, offline, and it makes every future
skeleton-conditional gate question answerable off the log.

### 4. Extend vitest toward the nav guarantees

Scroll-reset, anchor landing, header clearance. `SkeletonComposer` is pinned; those are not. The
harness now also has `src/test-setup.ts` (jsdom lacks `IntersectionObserver`, which every
`MotionReveal`-wrapped component needs) and `react-router-dom` deduped, so a component that needs a
Router renders. Both were missing and both read as broken components rather than as harness faults.

### Do NOT do these

- **A pytest CI job written blind.** DoD 9's floor is enforced in `tests/conftest.py`; the "in CI"
  half is open *because* I could not verify a job on the CI platform. 1.10's whole lesson is that
  the job would have failed its first run and local green hid it.
- **Bounding the contract by stating the allow-list once per run.** It is the right fix for the
  ~18k tokens/run and for the architect's collapsed route context (pre-flight question 6), and it
  changes what the model sees. Not verifiable without generations.

---

## What landed in session 7

9 commits, `0082f5f`…`c764f3a`, on `main`, **not pushed**.

| commit | what |
|---|---|
| `0082f5f` | **contract budget** — the 4,000-char bound was hiding a mutilated allow-list |
| `430453a` | **AiFeaturePanel** — linked to a route it did not create |
| `2d69917` | **telemetry** — `visual_review_status` said `None` for three different things |
| `614d772` | **`write_file`** — returns the path it wrote; last of the 8 xfails |
| `2f96cf6` | **the pre-flight** — [docs/FIRST_FUNDED_TRIO_PREFLIGHT.md](docs/FIRST_FUNDED_TRIO_PREFLIGHT.md) |
| `3b2e72a` | **DoD 8** — page writes allowlisted; 26 modules are on the list |
| `7f8f91f` | **DoD 9** — collection floor, and the CI half I did not fake |
| `98aa600` | this handoff |
| `c764f3a` | roadmap: correct DoD 9's "trivial", mark what Day 2 landed |

**The pre-flight is the deliverable.** Eleven questions, each with its instrument. Read it before
spending the first funded trio; five pre-launch checks in it have each already cost a trio or a
published number.

### The three findings worth carrying, none of which was the filed defect

1. **`bounded_json` is not a bound above its limit — it is a mutation.** Past 5,000 chars it clips
   every list to 12 items. `public-catalog` was sending the model 12 of its 30 allowed components,
   missing the `MarketingHero` and `ProductShowcase` its own contract assigned to that page's slots.
   The stale 4,000-char xfail was sitting on top of it. **The same defect is live and larger at
   `codegen/architect.py:138` and I did not fix it**: `_catalogue_routes_context` puts one full
   contract per route into a 10,000-char bound, so at **3 routes it collapses to
   `{"truncated": true, …}`** and real runs have 8-14. Offline reproduction only — pre-flight
   question 6.
2. **`AiFeaturePanel`'s dead link was 5 of 41, not 1 of 9.** The earlier figure only looked at trios
   2-5. The template's catch-all redirects unknown paths to `/` rather than 404ing, which is why a
   dead link behaved like a working one for 40 requests.
3. **26 modules can write `src/pages/**.tsx`.** That is DoD 8's real output and Phase 2's baseline.
   Half the list is `static` — modules that write computed paths the suite never exercises with a
   page — so each of those is also a test-coverage gap.

### Mutation results, and the pattern in the failures

`8 + 17 (vitest) + 11 + 7 + 11` mutations, zero survivors at the end. **Six survived a first
sweep**, and every one had the same cause, in two flavours:

- **Asserted against the case that does not bind.** Every contract assertion used `public-home`,
  the one skeleton comfortably under budget, so reverting the fix changed nothing it could see.
  That is *why* the clipping went unnoticed for as long as it did — the tests could not fail.
- **Drove the consumer, never the producer.** All the `visual_review_status` tests asked "given a
  reason, does the field say so" and none asked "does anything set a reason", so `build_phase`
  recording nothing at all was invisible. `test_visual_report_is_re_derived.py`'s own docstring
  warns about exactly this shape, and I wrote the new tests the way it warned against.

Both are worth checking for by default in the next sweep you write.

## Work the roadmap's order, and do not re-litigate it

Phase 0 → 1 → 2 → 3 → 4. Session 5 proposed reordering and the owner pushed back: *"why not work in
order by the preview roadmap?"*. **Phase 1 is not finished. Do not start Phase 2 because Phase 1 is
tiring.**

One documented exception, already taken: **2.9 was pulled forward and is done** (`475265e`). It was
authorised by the no-generation window — it is pure offline logic and the alternative was idling.
It is throwaway work by design (it lives in the range 2.4-2.5 deletes) and that was the accepted
price. **This is not a precedent for pulling more Phase 2 items forward.**

**Phase 2 DoDs 8 and 9 are a different thing and not a second exception.** The roadmap's own
no-generation-window plan schedules four Phase 2 *DoDs* for Day 2, on the grounds that none of them
needs a generation and Phase 2 should open with its measurements already in place. Building a
scoreboard is not starting the phase. DoD 7 and DoD 2/5 remain from that list.

---

## Binding owner constraints — these do not expire

- **Fix the PIPELINE, never a generated preview.** Editing anything under `data/preview-apps/**` to
  make a defect go away is always wrong. *Reading* those workspaces for evidence is fine and is how
  most findings get made.
- **Generation must not exceed 10 minutes.**
- **If you find a defect, fix it in the pipeline and add a test that fails with the fix reverted.**
- **Do NOT relax the deadline to make runs pass.** A degraded preview that ships is the designed
  outcome; two of three audited runs used to ship nothing.

### The rule that has caught the most defects

**Mutation-test every guard.** A guard whose success looks like its failure is this repo's recurring
defect. Revert the fix, confirm the test goes red, restore — from an **in-memory backup**, never
`git checkout` (it ate a session's uncommitted work once already).

Session 6's yield from this rule alone:

- 2.9's census adjudication survived the first sweep. Six mutations caught, one did not; the
  seventh test exists because of it.
- Three tests in `test_catalogue_contract.py` were built by `.replace()` on anchors that had since
  moved. Two failed loudly (they also asserted `decoy != stub`); **the third was green and testing
  nothing.** Fixed as a class: `_mutated()` refuses to return an unmutated string and requires the
  anchor exactly once.
- Both mutation drivers scored a **green baseline as red**, because `"failed"` is a substring of
  `"xfailed"`. A sweep that will not start on a suite with one xfail is a guard failing closed for
  the wrong reason.

Assume any DoD row you did not personally mutate is unproven. Three that session 4 marked "done"
were false in production **and** in the test meant to pin them.

---

## Operating notes — every one has cost real time

| | |
|---|---|
| **The test command** | **`docker run`, not `docker compose exec`.** See below. This burned an hour and produced two wrong reports today. |
| **`industry` is `Form(None)`** | Omitting it silently resolves to `generic` and produces convincing garbage. **Always set it.** |
| Host port | **8001**. Multipart, not JSON. |
| Trailing slash | `POST /api/requests/` 307-redirects and **drops the body**. No trailing slash. |
| `reviewing` | **Transient, not terminal.** Watch `is_generating`. |
| Reload code | `docker compose restart api`. `exec api` does **not** reload. |
| Industries | A **different** one per run in a trio. Three art galleries only prove the art-gallery path. |
| pytest | **Read the SUMMARY LINE, never the exit code.** Piping to `tail` inside an `&&` chain has masked red suites twice. |
| Working directory | **Drifts between tool calls. Use absolute paths.** Bit me again this session — a `cd backend` persisted and turned the next two commands into `backend/backend/...`. |
| **`preview-template/package.json` has a runtime cost** | It is the shared-npm cache key — `shared_npm_root()` sha256s it with `package-lock.json` (`npm_shared.py:29-44`). **One added byte invalidates the cache and the next generation pays a cold `npm ci` inside the run**, holding `_install_lock` while concurrent runs wait. Trios 4/5 cleared 600 s by 9-17 s. Editing it is fine; warm the cache out of band before timing anything. |

### The test command, and the two traps in the convenient alternative

```bash
docker run --rm -v "/Users/maurice/Documents/Dev/BMV:/repo" -w /repo/backend \
  -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api \
  -c 'pip install -q pytest; python -m pytest tests/ -q'
```

`docker compose exec api` is faster to type and wrong two independent ways, **and both look like
application defects**:

1. **`sh -lc` drops node.** A login shell re-reads `/etc/profile`, resets PATH, loses
   `/opt/node/bin`. `tsx_parse_error` shells out to node and **fails open** — no node means "this
   source parses fine" — so nothing errors and *six* unrelated tests go red with messages pointing
   at application logic (`test_slotfill_retry`, `test_typecheck_diagnostics`, `test_task4/5/6_*`).
2. **The `api` service mounts only `backend/`.** Four tests read repo-root files —
   `scripts/preview-qa.sh`, `Dockerfile.app`, `docker-compose.coolify.yml` — and get
   `FileNotFoundError`, which reads as "the QA harness lost its script".

Measured on one commit: `sh -lc` → 10 failed / 1,509 passed. `sh -c` → 4 failed / 1,518 passed.
`docker run` → **0 failed / 1,531 passed.** I reported both intermediate numbers as real findings
before checking the harness. `docker compose exec -T api sh -c` (never `-lc`) is fine for a single
file that touches no repo-root path; nothing else.

**Do not run a pytest container while a timed trio is in flight.** It contaminates the measurement.

---

## What landed in session 6

8 commits, `88ff2be`…`475265e`. Summarised in git and in the roadmap Status table; the two with a
live effect are **1.10** (the vitest runner, a sibling package on purpose because
`preview-template/package.json` is the shared-npm cache key — do not "tidy" it into the template)
and **2.9** (the slot-fill retry loop, which had never fired once: `_slot_fill_rejection` knew four
syntactic reasons and none of them is what actually goes wrong. 26 pages discarded across requests
74-79, zero syntactic rejections in the same runs). 2.9 now rejects on **enforce's own verdict**.
Whether a re-asked page comes back *different* is unmeasured and is pre-flight question 3.

## What is still broken

Ordered by what I would do first. Every item has evidence; none is speculative.

### 1. p50 is 569-590 s against a ≤ 500 s DoD, and the lever is call *count*

`appspec` spans **264.5 s and 288.8 s** on requests 83 and 84 — roughly half the budget before
anything is built. **Bounding `appspec` is not in Phase 1's item list.**

**Owner decision still pending:** move the p50 row to Phase 2, or add a Phase 1 item for `appspec`.
Do not quietly re-fit the number.

`scripts/measure/appspec_cost.py` over trios 2-5 (12 runs) decomposed it:

| | |
|---|---|
| appspec AI time | **147.0 s per run**, 1,763 s total |
| calls per run | **2 to 7** |
| runs with 2-3 calls | 49 / 54 / 69 / 94 s |
| runs with 5-7 calls | 253 / 268 / 294 s |
| slowest single call | 23.6-76.2 s — **none over 120 s** |
| non-AI wall clock in the stage | **0.0-27.3 s** |
| AI time recorded `usable=false` | **13 %**, 18.7 s per run, thrown away |

Not a per-call latency problem, not an orchestration problem: ~90 % is model calls and the total is
set by **how many**. Each extra call ≈ 50-75 s. Bounding appspec means bounding the
**repair/coverage loop**. *Which* calls the slow runs make is now answerable — the stage was
instrumented in `56d8f08` — but only by a funded trio. **The table tells you where the time is, not
which loop is spending it.**

### 2. 1.12 — a MANDATORY stage with no deterministic path

Request 74 stored **nothing**: no `preview_app`, no `roles`, empty `generated_pages`. At t=540.4 s
`call_architect` raised 9 ms later. `architect` is MANDATORY, whose contract is that such stages take
their deterministic path — **it has none** outside the AppSpec branch, and 74's AppSpec had already
burned 390 s and failed.

**My recommendation, reversing session 5's earlier one:** do *not* build a deterministic architect.
Past the deadline codegen is refused too, so it would ship an architecture with wholly generic pages
— precisely the artifact 2.9 exists to avoid. Bound `appspec` instead. **Owner has not ruled.**

### 3. Ship rate is still 1 of 3

Remaining blocking gate codes across trios 2-5, after the dead-link fix:

| code | count |
|---|---|
| `visual_defect_severe` | 5 |
| `listing_not_schedule_rail` | 4 |
| `placeholder_content_shipped` | 2 |
| `confirm_not_stage` | 1 |

Genuine judgment calls, not link plumbing. `placeholder_content_shipped` firing at all **inverts a
DoD row** that wants zero fires — the gate works; the *writers* still emit placeholders.

What does **not** decide it: typecheck. Request 83 shipped `ready` with 10 type errors; 78 failed
with zero. Do not chase `tsc` counts expecting the ship rate to move.

### 4. 1.11 — the reserve is unbounded as a whole

`RESERVE_SECONDS = 60` was fitted to the render-smoke and capture pass. Over nine runs the 382 s of
tail is **127 s AI (33 %) and 255 s non-AI (67 %)**. The elective guards took ~10 s a run off it.

The screenshot **session-budget clip** was implemented, measured and **reverted** — 2-of-3 over
600 s and **0 of 18 pages visually reviewed**. The measurement is a comment in `screenshot.py` so
nobody re-adds it. The lock-**wait** bound was kept.

If you attack this again, the axis that killed attempt one is *pages actually given a visual
verdict*, not wall clock. **Measure both, separately.**

### 5. The dead-link guard has one clean live trio, not two

Trio 5 (86-88): zero dead-link gate failures where trios 2-4 had 37 dead links across 9 failures.
Trio 6 would have confirmed it and is void. n=3, and session 5 was twice wrong about a fix after a
single trio. **Re-run the confirming trio once funded.**

### 6. 1.10 — green on `main` is unverified

Runner and CI job are done and merged. The standing rule — *no test may leave pytest until that CI
job is green on main* — cannot be satisfied from here. **Check the Actions tab.** Until it is green,
pytest remains the only suite anything may depend on.

The job **has** been run end-to-end in a clean `node:22` container, and that is what caught a defect
local green was hiding: the unit under test lives outside the test package, so its bare imports
resolve from `preview-template/node_modules`, which does not exist on a fresh checkout — `tsc` and
vite both failed with `Failed to resolve import "react"`. The same fact has a second edge: once that
directory *does* exist, React resolves twice and hooks break, so `resolve.dedupe` is set. **Verify a
CI job on the CI platform, not on the machine that wrote it.**

The design fact worth carrying: it is a **sibling package on purpose**, because
`preview-template/package.json` is the shared-npm cache key. Do not "tidy" it into the template.

### 7. The architect's route context collapses — new, unfixed

`_catalogue_routes_context` (`codegen/architect.py:138`) serializes one **full** skeleton contract
per catalogue route into a 10,000-char `bounded_json`. Measured offline: 1 route = 5,004 chars,
2 routes = list-clipped to 12 components each, **3 routes = collapsed to
`{"truncated": true, "preview": …}`**. Real runs have 8-14 routes.

If that holds live, the architect has been receiving a truncated preview string for its entire
route/contract block on every generation. **Offline reproduction only** — deliberately not fixed,
because the fix is "state the allow-list once per run", which changes what the model sees and cannot
be validated without generations. Pre-flight question 6.

All eight xfails are closed. Five were tests that had stopped testing anything; the last two were
each hiding a live defect.

### 8. Appspec telemetry is verified against fakes only

Scopes added in `builder.py` (`authoring`, real attempt numbers; `repair`), `coverage.py`
(`coverage_review`), `schema_repair.py` (`schema_repair`), pinned by
`tests/appspec/test_appspec_call_telemetry.py`, 5 mutations / 5 caught. **No live run has produced a
labelled row**, because of the credit wall.

Consequence to carry: the DoD row **"no ask > 120 s inclusive of failovers"** groups logical asks by
`(request_id, stage, writer)`. For appspec that grouping had nothing to group on, so **the row was
evaluated on data that structurally could not show an appspec failover.** Treat it as unproven for
this stage until a funded trio re-measures.

---

## Things I got wrong in session 7, so you don't repeat them

- **I wrote six tests that could not fail, and only the mutation sweeps found them.** Two flavours,
  both described above: asserting against the skeleton that does not bind, and driving the consumer
  instead of the producer. In one case the file's own docstring warned about the exact shape.
- **A `cd backend` drifted between tool calls again** and a `python3 - <<PY` heredoc died on a
  relative path. Third session running. Use absolute paths; the note has been in this file since
  session 5.
- **I nearly enforced DoD 8 on the runtime census alone.** It would have raised in production for
  eleven modules that write computed paths the suite's fixtures never exercise with a page. The
  static cross-check was not optional.
- **I started a mutation sweep and then kept editing.** The sweep mutates live-mounted source, so a
  concurrent edit can make its pytest run red for a reason that has nothing to do with the mutation.
  Nothing was lost, but the verdict would have been noise. Wait for the sweep.

## Things I got wrong in session 6, so you don't repeat them

- **I reported phantom test failures twice in one afternoon, both from my own harness.** First 6
  (login shell, no node), then 4 more (compose service mounts only `backend/`). I wrote the second
  batch into the roadmap as "pre-existing untriaged failures" before checking. The correct suite
  state was 0 failed the whole time. **Confirm the instrument before reporting the measurement.**
- **I reported a suite figure from a subset and called it the suite.** Same root cause.
- **A `cd backend` persisted between tool calls** and turned the next two commands into
  `backend/backend/...`. The operating note about absolute paths has been in this file for two
  sessions and I still did it.
- **Both mutation drivers had a substring bug** (`"failed" in "1 xfailed"`) that made a green
  baseline read as red. They had never been run against a suite containing an xfail.
- Session 5's list still stands and is worth re-reading in `08a9abf`: mutating a live-mounted source
  file mid-generation, `git checkout` discarding uncommitted work, a grep-brittle test falsely
  flagging three guarded stages, and — the important one — **a dead-link repair that improved the
  gate metric and made the artifact worse.** When a fix improves a gate number, measure the artifact
  separately.
