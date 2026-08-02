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

### Tooling in the scratchpad

`/private/tmp/claude-501/-Users-maurice-Documents-Dev-BMV/6b80695f-52e9-41af-94b7-df5cba4e352f/scratchpad/`
(session-scoped — copy anything you want to keep into the repo):

| file | what |
|---|---|
| `analyse.py` | per-trio DoD evidence: wall clock, degradations, contention, logical asks inclusive of failovers. Knows trios 1–6 by launch epoch; add yours the same way |
| `replay.py` | replays the dead-link guard over stored workspaces **read-only** — how "31 dead hrefs → 0" was measured |
| `resolve_probe.py` | measures how much of the real dead-link population each resolver rule can retarget |
| `tail.py` | decomposes post-deadline time into AI vs non-AI. This is what found the elective-stage defect |
| `launch_trio*.sh` | the trio launchers — correct `industry`, port, multipart and 60 s spacing already baked in |
| `api2..6.log` | the raw run logs behind every number in this handoff |

---

## What is still broken

Ordered by what I would do first. Every item has evidence attached; none is speculative.

### 1. p50 is 569–590 s against a ≤ 500 s DoD, and the lever is not the deadline

`appspec` spans **264.5 s and 288.8 s** on requests 83 and 84 — roughly half the whole budget, before
anything is built. No amount of deadline enforcement fixes a stage that is simply slow, and
**bounding `appspec` is not in Phase 1's item list.**

This is the same work as item 2. **Owner decision pending:** move the p50 row to Phase 2, or add a
Phase 1 item for `appspec`. Do not quietly re-fit the number.

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

### 7. 1.10 — no JS test runner

`preview-template/package.json` has `dev`/`build`/`typecheck` only. No vitest, no `.github/`. **Two
Phase 2 DoDs depend on a runner that does not exist**, and the standing rule is: *no test may leave
pytest until that CI job is green on main.* Cheap, needs no decision, and it is the last unstarted
Phase 1 item.

### 8. Three other JSON extractor implementations, untouched

1.6 fixed `shared/json_utils.py` (6 of 6 captured payloads now parse). Still carrying the original
bugs: `appspec/sanitize/preparse_normalize.py:149` (**both** of them),
`services/page_experience.py:133`, `pipelines/_shared.py:107`.

### 9. Eight xfailed tests are recorded defects, not stale assertions

Five are in `tests/preview_app/test_catalogue_contract.py` with detailed reasons, including the 2.9
one. Roadmap 0.9 unmasked them by splitting a 266-assertion mega-test that had never been collected.
Treat each as a filed defect that already has a reproduction written.

### 10. Minor — telemetry vanishes when the visual critic is skipped

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
