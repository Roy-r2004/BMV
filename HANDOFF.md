# Session handoff — the no-generation window, day 1 (2026-08-03, session 6)

Successor to session 5's handoff (in git history at `08a9abf`). Still-binding parts are restated
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

- **`main` is at `475265e` and pushed.** Session 5's 9 commits plus session 6's are all merged;
  `chore/remove-preview-generator-v2` is fully contained in `main`. No open PR, working tree clean.
- **Suite: 1,531 passed / 1 skipped / 2 xfailed / 0 failed.** Run it the documented way — see the
  operating notes, this bit up and it cost me two wrong reports today.
- **CI exists now** (`.github/workflows/preview-template-tests.yml`) and has run on `main` at least
  once. **I cannot read the result.** Check
  [github.com/Roy-r2004/BMV/actions](https://github.com/Roy-r2004/BMV/actions) — 1.10 is not done
  until that job is green there.

---

## The next step

Day 1 of the window is 2 of 4 done. Work these in order; each is offline and each has its
reproduction already written.

### 1. The skeleton-contract size bound — a live token cost, currently an xfail

`test_the_attached_skeleton_contract_stays_under_four_thousand_chars`
(`tests/preview_app/test_catalogue_contract.py:1988`). The attached skeleton/slot contract is
**5,241 chars against a pinned 4,000**. It grew when the contract started carrying the full skeleton
allow-list so validators and prompts accept `Button`/`Badge`/`Input` and not only slot defaults.
That growth was deliberate; re-checking the bound was not.

~5.2 KB rides on **every** generated file's instructions — roughly 1,300 tokens × ~14 files ≈ **18k
tokens per run** of pure contract boilerplate, on a pipeline fighting for a 600 s cap.

**Retire the bound deliberately or re-fit it. Do not raise the number until it passes** — that is
the move the xfail exists to prevent. Real options, in the order I would try them: dedupe the
allow-list against what the *assigned* skeleton can actually use (most of the 5.2 KB is components
the page cannot legally render); or split it so the allow-list is stated once per run rather than
once per file. Either way the new bound needs a stated derivation, not a fitted constant.

### 2. `AiFeaturePanel.tsx:44` hardcodes `/ai-features`

Template source, so the vitest harness that 1.10 stood up can prove it. The dead-link guard **skips
template-owned files** (`restore_template_owned_files` reverts the edit) and `AppLink` requires
`href`, so there is no safe removal — it needs a real fix, not a deletion. Dead in 1 of 9 runs; did
not block that run. `MarketingHero`'s `DEFAULT_PRIMARY_CTA` was the same defect and is fixed at
source; this one is not.

### 3. `visual_review_status: None` → `unmeasured`

Trios 4 and 5 store `None` when the critic is skipped past the deadline. Small, but do it **before**
the next trio is collected through it, or the first funded trio inherits the ambiguity.

### 4. The last xfail — `test_phase5_ui_alias_imports.py:153`

`write_file` canonicalizes `Dashboard.tsx` → `DashboardPage.tsx`, so a caller holding the original
`Path` finds nothing. The content contracts still hold on the canonical path (the sibling test
proves it). Decide: either `write_file` stops renaming out from under callers, or the touched-list
reports post-canonicalize paths and callers update. Then delete the xfail.

### Then: Day 2 — Phase 2's scoreboard, built before Phase 2 starts

Four Phase 2 DoDs need no generation. Details in the roadmap; the order I would take them:

1. **DoD 8 — the write allowlist.** No module outside a named allowlist may write
   `src/pages/**.tsx` or `src/render/**`, enforced at runtime inside `workspace.write_file`
   (`workspace.py:120`), allowlist pinned by test. **Highest value on the list** — it is a hard
   guarantee, not a measurement, and Phase 2's whole thesis is that one writer owns pages.
2. **DoD 9 — test-count floor in CI.** Trivial now CI exists.
3. **DoD 7 — route bijection.** `_smoke_routes` vs non-wildcard routes with a page file, and
   `catalogue_route_for_file` injective. Pure functions over the archived corpus.
4. **DoD 2 and 5 — the "before" numbers.** Inline prose per page TSX (claimed 13,540 chars) and
   `SiteSpec` key-set commonality (claimed 1 key across 27 workspaces). Census over
   `docs/evidence/preview-workspaces.tar.gz`. **This window is the only cheap time to take them.**

Plus: extend vitest toward the nav guarantees the roadmap already specifies — scroll-reset, anchor
landing, header clearance. `SkeletonComposer` is pinned; those are not.

**The deliverable that pays for the window** is the *first-funded-trio pre-flight*: one document
listing every question the next three runs must answer and the instrument each one needs. Do not
skip it to do more code. It is what stops the next trio from being spent confirming things we
already know.

---

## Work the roadmap's order, and do not re-litigate it

Phase 0 → 1 → 2 → 3 → 4. Session 5 proposed reordering and the owner pushed back: *"why not work in
order by the preview roadmap?"*. **Phase 1 is not finished. Do not start Phase 2 because Phase 1 is
tiring.**

One documented exception, already taken: **2.9 was pulled forward and is done** (`475265e`). It was
authorised by the no-generation window — it is pure offline logic and the alternative was idling.
It is throwaway work by design (it lives in the range 2.4-2.5 deletes) and that was the accepted
price. **This is not a precedent for pulling more Phase 2 items forward.**

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

8 commits, `88ff2be`…`475265e`, all on `main` and pushed.

| commit | what |
|---|---|
| `88ff2be` | **1.10** — a JS test runner, in a sibling package for a measurable reason |
| `1839376` | **1.6 cont.** — the duplicate extractor that failed silently, and the one nobody listed |
| `5eaa5b2` | rescue the Phase 1 evidence tooling out of a session scratchpad |
| `56d8f08` | **telemetry** — appspec is the most expensive stage and was the only unscoped one |
| `6f16ad9` | **CI** — the vitest job would have failed its first run, and local green hid it |
| `67a4301` | roadmap: plan the no-generation window, and archive what it depends on |
| `4e61c01` | **xfails** — five of eight were tests that had stopped testing anything |
| `475265e` | **2.9** — the slot-fill retry loop had never fired once |

### 2.9, since it is the one with a live effect

A page that compiled but violated the catalogue contract was *accepted* by the retry loop and thrown
away one call later by `enforce_catalogue_page_contract`, replaced with the generic scaffold.
`_slot_fill_rejection` knew four reasons — empty, truncated, missing-export-default,
unparseable-TSX — and **none of them is what actually goes wrong**. Across requests 74-79: 26 pages
discarded that way, **zero** syntactic rejections in the same runs. The cap, the per-reason
guidance and the log line had all been sitting there unreached.

The part to review is the predicate. Rejecting on `validate_catalogue_page_content` errors is wrong
and expensive: `enforce` repairs a broken composer invocation and back-fills missing slots before
giving up, so a page missing one slot is contract-invalid **and** free to fix, and re-asking for it
spends ~50 s to arrive at the same file. The test is **enforce's own verdict** — reject exactly what
would be discarded. Pinned by `test_a_fill_enforce_can_repair_is_not_re_asked`.

Cost is bounded three ways and only the third is new: the pre-existing per-page cap of 2 (never
reached), the pre-existing `PREVIEW_MAX_AI_CALLS`, and `_has_contract_retry_runway()`, which will not
start a discretionary ask unless the per-ask ceiling plus the reserve remain. Skipping records
`slot_fill_contract_retry_skipped_low_runway`; it is never silent. Seven mutations, zero survivors
(`scripts/cli/mutate_slotfill_contract_retry.py`).

**What it does not do:** guarantee the re-asked page comes back *different*. It guarantees a second
ask carrying the exact validator errors. Whether the model uses them is a funded-trio question and
it is on the pre-flight list.

### Tooling now in the repo

- **[`backend/scripts/measure/`](backend/scripts/measure/)** — `analyse.py <trio>` (per-trio DoD
  evidence), `replay.py` (dead-link guard, read-only over stored workspaces), `resolve_probe.py`,
  `tail.py` (post-deadline AI vs non-AI — this is what found the elective-stage defect),
  `appspec_cost.py`, and the trio launchers with `industry`/port/multipart/60 s spacing baked in.
- **[`docs/evidence/`](docs/evidence/)** — `preview-trio-logs.tar.gz` (109 KB, trios 1-6;
  `api6.log` is the **void** trio) and `preview-workspaces.tar.gz` (2.4 MB, 58 workspaces, requests
  11-91: shipped `src/` plus `.bmv-debug/` raw model responses). Both were one `docker volume prune`
  or one scratchpad cleanup from taking published numbers with them. **Every Day 2 census reads
  these.** `src/ui` is excluded on purpose — 58 byte-identical copies of a tree already in the repo,
  and including it took the archive to 10.8 MB.
- **Mutation drivers** — `scripts/cli/mutate_extractors.py`,
  `scripts/cli/mutate_slotfill_contract_retry.py`, `preview-template-tests/tools/mutate.py`.

---

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

### 7. Two xfails remain, both real

The skeleton-contract size bound and the `write_file` canonicalization marker — items 1 and 4 of
[The next step](#the-next-step). The other six are closed; five of them were tests that had stopped
testing anything, which is a finding about the suite rather than about the code.

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
