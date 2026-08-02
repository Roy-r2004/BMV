# Session handoff — the clock, the gate, and what is still broken (2026-08-02, session 5)

Successor to session 4's handoff (preserved in git history at `6e7c28d`; the still-binding parts are
restated below, including the five nav fixes and why they must not be pinned by source grep).
Process notes, not product docs.

- **The plan and its evidence: [docs/PREVIEW_ROADMAP.md](docs/PREVIEW_ROADMAP.md).** Read its
  **Status** table and the **Phase 1 DoD** table first. Both are current as of `6e6309b`.
- Why the pipeline shipped bad output: [docs/PREVIEW_QUALITY_FINDINGS.md](docs/PREVIEW_QUALITY_FINDINGS.md).

**If you read one thing: [What is still broken](#what-is-still-broken) — that is this session's
actual deliverable to you.**

> ## ⛔ Blocker before any live run: the OpenRouter account is out of credits
>
> From **19:29 (container clock) on 2026-08-02**, calls fail with
> *"This request requires more credits, or fewer max_tokens. You requested up to 28000 tokens, but
> can only afford 9612."* — 14 occurrences in trio 6, zero in trios 2–5.
>
> **Top up before running any generation, or every measurement you take will be wrong** — and wrong
> in a way that mimics the deadline defects. Request 89 degraded `codegen` (a MANDATORY stage) and
> stored nothing at all; that looks exactly like item 2 below and **is not** — it is an unfunded
> account. Requests 89 and 90 stored `generated_pages = {}`; only 91 completed (565 s, `ready`).
>
> **Trio 6 (89-91) is void. Do not cite it.** Trios 2–5 are clean and are the evidence base.

---

## Work the roadmap's order, and do not re-litigate it

The roadmap is Phase 0 → 1 → 2 → 3 → 4 and **you work it in that order.** In this session I proposed
reordering — pulling 2.9 forward, calling the clock done-enough — and the owner pushed back: *"why
not work in order by the preview roadmap?"*. I withdrew it, and the withdrawal was right on three
counts:

1. 2.9 lives in `codegen/generate.py:269-489`, exactly the range Phase 2's 2.4–2.5 deletes. Fixing it
   now is throwaway work.
2. "Declare the clock done-enough and move on" is this codebase's named recurring failure.
3. The dependencies in the roadmap are reasoned and it has survived three adversarial reviews.

**Phase 1 is not finished.** Do not start Phase 2 because Phase 1 is tiring.

---

## Binding owner constraints — these do not expire

- **Fix the PIPELINE, never a generated preview.** Editing anything under `data/preview-apps/**` to
  make a defect go away is always wrong. *Reading* those workspaces for evidence is fine and is how
  most of this session's findings were made.
- **Generation must not exceed 10 minutes.**
- **If you find a defect, fix it in the pipeline and add a test that fails with the fix reverted.**
- **Do NOT relax the deadline to make runs pass.** A degraded preview that ships is the designed
  outcome; two of three audited runs used to ship nothing at all.

### The rule that has caught the most defects

**Mutation-test every guard.** A guard whose success looks like its failure is this repo's recurring
defect. Revert the fix, confirm the new test goes red, restore. This session that found:

- `publish_degradations` — the first test called the helper directly instead of the call site, and
  passed with the fix reverted.
- The nav normalizer — reverting it to declared routes passed the **entire 1,469-test suite**. My own
  change, untested, caught only because I mutated all three changes rather than the interesting one.
- 1.7's original test — pre-flight refusal and post-hoc rollback produce identical end states, so an
  end-state assertion cannot tell them apart.

Three DoD rows session 4 marked "done" were false in production **and** false in the test environment
meant to pin them. Assume the same of any row you did not personally mutate.

---

## Operating notes — every one of these has cost real time

| | |
|---|---|
| **`industry` is `Form(None)`** | Omitting it silently resolves to `generic` and produces convincing garbage. **Always set it.** Cost three runs and a wrong escalation. |
| Host port | **8001**. Multipart, not JSON. |
| Trailing slash | `POST /api/requests/` 307-redirects and **drops the body**. No trailing slash. |
| `reviewing` | **Transient, not terminal.** Watch `is_generating`. |
| Reload code | `docker compose restart api`. `exec api` does **not** reload. |
| Industries | Use a **different** one per run in a trio. Three art galleries only prove the art-gallery path. |
| pytest | **Read the SUMMARY LINE, never the exit code.** Piping to `tail` inside an `&&` chain has masked red suites twice. |
| Working directory | **Drifts between tool calls. Use absolute paths.** It broke one `docker compose` call and two `docker run` calls this session. |
| **`preview-template/package.json` has a runtime cost** | It is the shared-npm cache key — `shared_npm_root()` sha256s it together with `package-lock.json` (`npm_shared.py:29-44`). **One added byte invalidates the cache, and the next generation pays a cold `npm ci` inside the run**, holding `_install_lock` through `contended_lock` while concurrent runs wait it out. Trios 4/5 cleared 600 s by 9-17 s. Editing it is fine; warm the cache out of band before you time anything. |

**The test command** — both documented ones lie:

```
docker run --rm -v "/Users/maurice/Documents/Dev/BMV:/repo" -w /repo/backend \
  -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api \
  -c 'pip install -q pytest; python -m pytest tests/ -q'
```

**Do not run a pytest container while a timed trio is in flight.** It contaminates the measurement —
I did it to my own trio 2 after criticising another session for the same thing.

---

## What landed this session

9 commits on `chore/remove-preview-generator-v2` (`6e7c28d`…`6e6309b`). `main` and `origin/main` are
both still at `66902f0` — **nothing pushed, no PR.** Working tree clean. Suite **1,472 passed / 1
skipped / 8 xfailed**.

| commit | what |
|---|---|
| `f9f41eb` | contention: charge a blocked run for the wait it did not choose |
| `56f5c39` | three DoD rows that were marked done and were not true |
| `115375f` | 0.9: 2,375 lines of assertions that had never run, and what they found |
| `b7a9056` | roadmap: Phase 1 failed its DoD under concurrency, and why |
| `533dff3` | bound the lock wait; the budget clip was wrong and is reverted |
| `f36a5d0` | **five of eight elective stages were never actually elective** |
| `44736dd` | **the 120 s ask ceiling was 135 s, by a constant** |
| `6e6309b` | **repair dead links deterministically instead of withholding** |

Six concurrent trios were run (requests 74–91): three runs each, started 60 s apart, one with a
`reference_url`, one with a `reference_file`, a different industry per run.

| trio | wall clock | ≤ 600 s | what it tested |
|---|---|---|---|
| 2 (77-79) | 619.7 / 576.4 / 573.0 | 2 of 3 | baseline + contention instrumentation |
| 3 (80-82) | 590.2 / 600.2 / 602.7 | 1 of 3 | screenshot lock-wait bound |
| 4 (83-85) | 591 / 583 / 590 | **3 of 3** | elective-stage guards |
| 5 (86-88) | 569 / 562 / 570 | **3 of 3** | dead-link guard — **zero dead-link gate failures** |
| 6 (89-91) | **VOID — out of credits** | — | would have confirmed the dead-link guard |

**So the dead-link guard has one clean live trio (5), not two.** Re-run the confirming trio once the
account is funded. Trio 5 is strong evidence — zero dead-link gate failures where trios 2–4 had 37
dead links across 9 gate failures — but it is n=3, and this session has twice been wrong about a fix
after a single trio.

### Tooling — rescued into the repo (session 6)

It was session-scoped and about to be lost. Now at
**[`backend/scripts/measure/`](backend/scripts/measure/)** with a README of its own, verified
running from that location: `analyse.py 5` reproduces trio 5's degradation record and `replay.py`
reproduces "31 dead hrefs → 0".

| file | what |
|---|---|
| `analyse.py <trio>` | per-trio DoD evidence: wall clock, degradations, contention, logical asks inclusive of failovers. Knows trios 1–5 by launch epoch; add yours the same way |
| `replay.py` | replays the dead-link guard over stored workspaces **read-only**. Reports repair *kind* per run — a link `homed` to `/` improves the gate metric and worsens the artifact |
| `resolve_probe.py` | measures how much of the real dead-link population each resolver rule can retarget |
| `tail.py` | decomposes post-deadline time into AI vs non-AI. This is what found the elective-stage defect |
| `launch_trio*.sh` | the trio launchers, one per trio as provenance — correct `industry`, port, multipart and 60 s spacing baked in. `OUT=` now defaults to `$PWD` |
| `docs/evidence/preview-trio-logs.tar.gz` | `api.log`…`api6.log`, the raw logs behind every number here (109 KB). `api6.log` is the **void** trio; kept so nobody re-derives from it by accident |

Also added this session: **`scripts/cli/mutate_extractors.py`** (reverts each JSON-extractor fix and
asserts the parity suite reddens) and **`preview-template-tests/tools/mutate.py`** (the same, for the
vitest suite). Both exist because a green suite is not evidence.

---

## What is still broken

Ordered by what I would do first. Every item has evidence attached; none is speculative.

### 1. p50 is 569–590 s against a ≤ 500 s DoD, and the lever is call *count*

`appspec` spans **264.5 s and 288.8 s** on requests 83 and 84 — roughly half the whole budget, before
anything is built. No amount of deadline enforcement fixes a stage that is simply slow, and
**bounding `appspec` is not in Phase 1's item list.**

This is the same work as item 2. **Owner decision still pending:** move the p50 row to Phase 2, or
add a Phase 1 item for `appspec`. Do not quietly re-fit the number.

**Session 6 decomposed the stage so the decision has evidence.**
`scripts/measure/appspec_cost.py`, over trios 2–5 (12 runs):

| | |
|---|---|
| appspec AI time | **147.0 s per run**, 1,763 s total |
| calls per run | **2 to 7** |
| runs with 2–3 calls | 49 / 54 / 69 / 94 s |
| runs with 5–7 calls | 253 / 268 / 294 s |
| slowest single call | 23.6–76.2 s — **none over 120 s** |
| non-AI wall clock inside the stage | **0.0–27.3 s** (validation, sanitize, persistence) |
| AI time recorded `usable=false` | **13 %**, 18.7 s per run, thrown away |

So it is **not** a per-call latency problem and **not** an orchestration problem — ~90 % of the span
is model calls, and the total is set almost entirely by how many of them a run makes. Each extra
call costs roughly 50–75 s. Bounding `appspec` means bounding the **repair/coverage loop**, not
tuning the prompt.

*Which* calls the slow runs make was unanswerable: appspec was the only AI-calling stage in the
pipeline with **no `ai_call` scope**, so all 49 rows carried `writer = NULL, attempt = 1` (see the
telemetry note below). Now instrumented — the next funded trio will attribute those 147 s to
authoring vs coverage vs repair, and show the re-asks.

**Do not decide this from the table above alone.** It tells you where the time is, not which loop
is spending it.

### 2. 1.12 — a MANDATORY stage with no deterministic path

Request 74 stored **literally nothing**: no `preview_app`, no `roles`, empty `generated_pages`. At
t=540.4 s `call_architect` raised 9 ms later — past the deadline every ask budget is zero. `architect`
is in `MANDATORY_STAGES`, whose contract is that such stages take their deterministic path. **It has
none** outside the AppSpec branch, and 74's AppSpec had already burned 390 s of the 540 s budget and
failed. The orchestrator read the message as transient, looked for the 180 s retry runway, found
none, and the `role_pages` fallback under `except Exception: pass` produced nothing either.

`require_model_time` now attributes the error to the deadline rather than to the model. That fixes
the misdiagnosis and does **not** make the run ship.

**My recommendation, reversing my earlier one:** do *not* build a deterministic architect. Past the
deadline codegen is refused too, so it would ship an architecture with wholly generic pages — given
item 4, precisely the artifact to avoid. Bound `appspec` instead. Owner has not ruled.

### 3. Ship rate is still 1 of 3

After the dead-link fix, the remaining blocking gate codes across trios 2–5:

| code | count |
|---|---|
| `visual_defect_severe` | 5 |
| `listing_not_schedule_rail` | 4 |
| `placeholder_content_shipped` | 2 |
| `confirm_not_stage` | 1 |

These are genuine judgment calls, not link plumbing, and they now decide whether a preview ships.
`placeholder_content_shipped` firing at all **inverts a DoD row** that wants zero fires — the gate
works; the *writers* still emit placeholders.

Note what does **not** decide it: typecheck. Request 83 shipped `ready` with 10 type errors; request
78 failed with zero. Do not chase `tsc` counts expecting the ship rate to move.

### 4. 2.9 — slot-fill falls back to the generic scaffold with no retry

`_slot_fill_rejection` (`codegen/generate.py:95`) only returns a reason for empty / truncated /
missing-export-default / unparseable-tsx output. A **contract-invalid** page is not a rejection, so
`enforce_catalogue_page_contract` (`:394`) silently replaces it with the generic scaffold and
`_MAX_SLOT_FILL_ATTEMPTS = 2` (`:77`) never fires. **26 pages across requests 74–79, and zero
syntactic rejections in those same runs — the retry loop did not run once.** Of 25 distinct
gate-blocked pages, 11 (44 %) had been scaffolded.

This is the measured root of the "everything looks the same" complaint. ~4 extra asks per run to fix.
**Owner decision pending**, and note it is in the range Phase 2's 2.4–2.5 deletes.

### 5. 1.11 — the reserve is still unbounded as a whole

`RESERVE_SECONDS = 60` was fitted to the post-deadline render-smoke and capture pass. Decomposed over
nine runs, the 382 s of tail is **127 s AI (33 %) and 255 s non-AI (67 %)**. The elective guards took
~10 s a run off it. Two attempts at the rest:

- The screenshot **session-budget clip** was implemented, measured and **reverted** — it produced
  2-of-3 over 600 s and **0 of 18 pages visually reviewed**. The measurement is written into
  `screenshot.py` as a comment so nobody re-adds it.
- The lock **wait** bound was kept (`533dff3`).

If you attack this again, the axis that killed attempt one is *pages actually given a visual verdict*,
not wall clock. Measure both, separately.

### 6. Template components hardcoding routes they cannot guarantee

`preview-template/src/ui/public/AiFeaturePanel.tsx:44` hardcodes `/ai-features`. The dead-link guard
**skips template-owned files** (`restore_template_owned_files` would revert the edit) and `AppLink`
requires `href`, so there is no safe removal. Dead in 1 of 9 runs; did not block that run.
`MarketingHero`'s `DEFAULT_PRIMARY_CTA` was the same defect and is fixed at source — this one is not.

### 7. 1.10 — JS test runner: built, but not green on `main`

**Done in session 6** (`backend/preview-template-tests/`, vitest 4 + jsdom + testing-library, 9
tests over `SkeletonComposer`, 9/9 mutation-caught, plus
`.github/workflows/preview-template-tests.yml` — the repo's first CI job of any kind).

**What is left is not code: the workflow has never run.** Nothing is pushed, so the standing rule —
*no test may leave pytest until that CI job is green on main* — is still unsatisfied, and it cannot
be satisfied from a branch. Until then pytest remains the only suite anything may depend on.

The job has, however, been run end-to-end on a clean `node:22` linux container — `npm ci` (template)
→ `npm ci` (tests) → `tsc -b` → 9 passed. **That run is what caught the defect a local green was
hiding:** the unit under test lives outside the test package, so its bare imports resolve from
`preview-template/node_modules`, which does not exist on a fresh checkout. Both `tsc` and vite failed
with `Failed to resolve import "react"`. It passed on this machine only because the template's
install was already there. The same fact has a second edge — once that directory *does* exist, React
resolves twice and hooks break — so `resolve.dedupe` is now set. **Verify a CI job on the CI
platform, not on the machine that wrote it.**

The one design fact worth carrying: it is a **sibling package on purpose**, because
`preview-template/package.json` is the shared-npm cache key (see the operating note above). Do not
"tidy" it back into the template.

### 8. The other JSON extractors — DONE in session 6, and the accounting here was wrong

Fixed. What follows is the correction, because two of the three named items did not matter and an
unnamed fourth one did.

Replaying the four verbatim payloads in `tests/fixtures/model_json/` through every extractor:

```
                                     req67-esc  req67-quo  req68      req69
shared/json_utils (1.6, fixed)       ok         ok         ok         ok
appspec/sanitize/preparse_normalize  FAIL       FAIL       FAIL       FAIL
services/page_experience   [LIVE]    FAIL       PARTIAL    FAIL       FAIL
appspec/authoring_parser   [LIVE]    FAIL       FAIL       ok         FAIL
```

- **`preparse_normalize.py` and `pipelines/_shared.py:107` had no production caller.** Only a test
  imports the first; nothing at all imports the second (the `_strip_fences` used across codegen,
  critic, fix_agent and safety is a *different* function in `preview_app/text_utils.py`, and it
  already routes through the shared extractor). Hygiene, not repair.
- **`authoring_parser.py:76` was not on the list and is on the AppSpec path** — the 264-288 s stage,
  item 1 above. It failed 3 of 4. Shapes 2 and 3 are structurally complete, so it reported
  `json_syntax_invalid` and `build_app_spec_candidate` **re-asked a 28k-token authoring call for
  output the model had already sent.** That is the 161 s waste from requests 67/69, on the most
  expensive stage in the pipeline.
- **`PARTIAL` was the real defect.** `page_experience._parse_json_from_response` did not fail on
  `request67_fix_agent_retry_unescaped_quotes` — it returned three files with the right paths, the
  first two byte-identical, and the third's **15,143 characters of content replaced by `""`**. No
  exception, no log, no `None`; callers test `if plan and plan.get("roles")` and shipped it. Its
  truncation closer cannot tell an under-escaped complete document from a truncated one, so it
  trimmed a recoverable document until something parsed. Success looked exactly like failure, on
  four live call sites including the `role_pages` fallback that 1.12 leans on.

All four extractors now recover 4 of 4. `tests/test_json_extractor_parity.py` pins parity **and**
wholeness (equality against the shared extractor, not just "returns a dict"), plus strict-first
ordering so a well-formed response can never reach a repair path.
`scripts/cli/mutate_extractors.py` reverts each fix and asserts the suite reddens: **5 mutations, 5
caught, 0 survivors.** One test has no mutation partner and is a forward guard rather than a pinned
one: `test_a_genuinely_truncated_response_still_fails_closed`.

**The generalisable bit:** "how many extractors are there" was answered from the previous handoff
rather than from the code, and the code had one more, on the stage that costs the most. Grep for the
behaviour, not the list.

### 9. Eight xfailed tests are recorded defects, not stale assertions

Five are in `tests/preview_app/test_catalogue_contract.py` with detailed reasons, including the 2.9
one. Roadmap 0.9 unmasked them by splitting a 266-assertion mega-test that had never been collected.
Treat each as a filed defect that already has a reproduction written.

### 10. The most expensive stage was the least instrumented — FIXED, unverified live

`admin_ops.py:330-332` derives a usage row's `stage` from the active `ai_call` scope and, with no
scope, falls back to `purpose` and hardcodes **`writer = None, attempt = 1`**. Every AI-calling stage
in the pipeline opens a scope — codegen, fix_agent, design_critic, vision, refine, seed, architect,
quality_repair — **except appspec**, which had none anywhere. All 49 of its rows across trios 2–5 are
`writer = NULL, attempt = 1`.

Three consequences, none of them cosmetic:

1. The 147 s per run could not be split into authoring / coverage / repair, which is exactly what the
   pending decision in item 1 turns on.
2. **Its re-asks were invisible.** `build_app_spec_candidate` retries a malformed authoring response
   up to `APPSPEC_AUTHORING_MALFORMED_RETRY_MAX` times and every attempt was recorded as attempt 1.
   Combined with item 8 — the authoring parser could not read a structurally complete but
   under-escaped response — the pipeline was re-asking 28k-token calls and *recording them as first
   attempts*.
3. The DoD row **"no ask > 120 s inclusive of failovers"** groups logical asks by
   `(request_id, stage, writer)` with `attempt` not resetting. For appspec that grouping had nothing
   to group on, so **the row was evaluated on data that structurally could not show an appspec
   failover.** Treat that row as unproven for this stage until a funded trio re-measures it.

Scopes added in `builder.py` (`authoring`, real attempt numbers; `repair`), `coverage.py`
(`coverage_review`) and `schema_repair.py` (`schema_repair`). Pinned by
`tests/appspec/test_appspec_call_telemetry.py`, 5 mutations, 5 caught, 0 survivors. **Verified only
against fakes** — no live run has produced a labelled row yet, because of the credit wall.

### 11. Minor — telemetry vanishes when the visual critic is skipped

Trios 4 and 5 store `visual_review_status: None` rather than `unmeasured` when the critic is skipped
past the deadline. The degradation record covers it, so this is an observability nit rather than data
loss. Listed so nobody reads it as the latter.

---

## Things I got wrong this session, so you don't repeat them

- **I mutated a live-mounted source file while three generations were in flight.** Verified harmless
  — the module was imported at startup, before the edit — but it should never have happened.
- **`git checkout` discarded my own uncommitted work** while cleaning up a mutation. Back up before
  reverting.
- **A regex-based test falsely flagged three guarded stages.** They are guarded through a loop
  variable, not a string literal. Rewritten against the AST. That is the grep-brittleness the roadmap
  warns about, committed by the person quoting the warning.
- **My first dead-link repair made the artifact worse.** Grounding every unresolvable href shipped
  request 88 with 33 of 81 internal links pointing at `/` — a footer whose Activities, Contact and
  Privacy Policy entries all landed on Home. Gate metric up, artifact down: the same shape as the
  reverted screenshot clip. **When a fix improves a gate number, measure the artifact separately.**
- **A silent edit collision** in that same guard would have shipped request 82 with a dead
  `/plan-your-stay` repaired by nothing, because the collision resolver dropped one edit without a
  word. Anything that skips work must say so out loud.
- **I claimed the elective guards would remove ~250 s of tail. They removed ~10 s a run.** The
  decomposition was right; attributing the bulk of it to two stages was not. State magnitudes only
  after measuring them.
