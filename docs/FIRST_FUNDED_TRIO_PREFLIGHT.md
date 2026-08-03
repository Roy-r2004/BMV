# First funded trio — pre-flight

**Status:** ready to run the moment OpenRouter credits are topped up. Written during the
no-generation window of 2026-08-03, against `main`.

This is the list of every question the next three runs must answer and the instrument each one
needs. It exists because a trio costs real money and the last few spent most of their value
confirming things already known. Today an unplanned trio answers about two open questions; with the
instruments landed this window it should answer **eleven**.

Read [`docs/PREVIEW_ROADMAP.md`](PREVIEW_ROADMAP.md) first — *The no-generation window*, then
*Status*, then *Phase 1 DoD*. This document does not restate them.

---

## Before you launch — five things that invalidate the measurement

Every one of these has already cost a trio or a published number.

1. **Top up credits and confirm with one cheap call.** Request 89 degraded `codegen` (MANDATORY)
   and stored nothing. That looks exactly like defect 1.12 and **is not**. Trio 6 (89-91) is void;
   do not cite it.
2. **Warm the shared-npm cache out of band.** `shared_npm_root()` sha256s
   `preview-template/package.json` with `package-lock.json` (`npm_shared.py:29-44`). That file is
   unchanged this window, but the tests package next to it did change — verify the key resolves to a
   warm root before timing anything, or the first run pays a cold `npm ci` *inside* its own clock
   while holding `_install_lock`. Trios 4 and 5 cleared 600 s by 9-17 s; a cold install erases that
   and every latency row with it.
3. **Set `industry` explicitly on all three runs, to three different values.** It is `Form(None)`;
   omitting it resolves to `generic` and produces convincing garbage. Three art galleries only prove
   the art-gallery path.
4. **Do not run a pytest container, a mutation sweep, or a second trio during the window.** Trio 1
   is timing-invalid because another session ran a sweep on the same host.
5. **One of the three runs must have ≥ 3 catalogue routes.** Question 6 below cannot be answered
   otherwise, and most briefs produce that naturally — just confirm it rather than assuming.

Launchers with port, multipart, `industry` and the 60 s spacing already baked in:
[`backend/scripts/measure/`](../backend/scripts/measure/). Copy the newest `launch_trio*.sh`.

---

## The questions

Ordered by what a `NO` answer changes. **New** marks a question this window made answerable; the
rest were already open and are listed so nothing is spent re-deriving them.

### 1. Does bounding `appspec` bound p50? — the one that gates Phase 1

p50 is 569-590 s against a ≤ 500 s DoD. `appspec` is **147 s of AI per run** and its cost tracks
call *count*, not per-call latency: 2-3 calls is 49-94 s, 5-7 calls is 253-294 s, no single call
over 120 s (`scripts/measure/appspec_cost.py`, trios 2-5, 12 runs).

**What the table cannot say is which loop spends the calls.** That is what the telemetry added in
`56d8f08` is for.

| | |
|---|---|
| **Instrument** | `ai_call` scopes in `builder.py` (`authoring`, real attempt numbers; `repair`), `coverage.py` (`coverage_review`), `schema_repair.py` (`schema_repair`) |
| **Read it** | Call census grouped by `(request_id, stage, writer, attempt)`. Compare a 2-3 call run against a 5-7 call run and read off which writer accounts for the extra 3-4 calls |
| **Decides** | Whether the fix is a repair-loop bound, a coverage-loop bound, or a schema-repair bound. Currently unknowable, so no Phase 1 item can be written for it |
| **Caveat** | **No live run has ever produced a labelled row.** The scopes are verified against fakes only (5 mutations, 5 caught). If the census still shows `writer = NULL` for appspec, the telemetry is wrong and *that* is the finding |

**Owner decision still pending, and this trio informs it but does not settle it:** move the p50 row
to Phase 2, or add a Phase 1 item for `appspec`. Do not quietly re-fit the number.

### 2. Is the ask-ceiling DoD row true for `appspec`?

The row is *"no ask > 120 s inclusive of failovers"*. It groups logical asks by
`(request_id, stage, writer)`. For appspec that grouping **had nothing to group on** — all 49 rows
carried `writer = NULL, attempt = 1` — so the row was evaluated on data that structurally could not
show an appspec failover. Treat it as unproven, not as passing.

| | |
|---|---|
| **Instrument** | Same scopes as question 1 |
| **Read it** | Re-run the ask-ceiling query with appspec rows now carrying a writer. Any logical ask over 120 s is a breach |
| **Decides** | Whether the row can be marked evidenced at all |

### 3. Does a re-asked page come back *different*? — 2.9's real question

`475265e` made the slot-fill retry fire on `enforce_catalogue_page_contract`'s verdict. Across
requests 74-79, 26 pages were discarded with **zero** retries; the cap of 2 had never been reached
once. The fix guarantees a second ask carrying the exact validator errors. **It does not guarantee
the model uses them.** A run where every retry fails still ships the same scaffolds and will look
busy doing it.

| | |
|---|---|
| **Instrument (rate)** | Call census: `writer=slot_fill`, `attempt=2`, `unusable_reason=rejected` |
| **Instrument (effect)** | `.bmv-debug/` raw model responses. Diff attempt 1 against attempt 2 for the same page |
| **Read it** | Two numbers, and they are different questions: how often the retry fired, and how often attempt 2 passed `enforce` when attempt 1 did not |
| **Decides** | If the retry fires and never succeeds, 2.9 is pure cost — ~50 s an ask — and should be reverted rather than tuned. That is a real possible outcome |
| **Also check** | `slot_fill_contract_retry_skipped_low_runway` degradations. If the runway gate is skipping every retry, the rate above is zero for a reason that is not the model's fault |

### 4. Did the extractor fixes remove the re-asks? — 1.6

`1839376` fixed a duplicate extractor that failed silently and one that was never listed.

| | |
|---|---|
| **Instrument** | Call census, `unusable=true` rows per stage |
| **Read it** | Trios 2-5 baseline: 13 % of appspec AI time recorded `usable=false`, 18.7 s per run thrown away. Compare |
| **Decides** | Whether 1.6 can be closed |

### 5. **New** — Did the contract clipping fix change the ship-rate blockers?

`0082f5f`. Above 5,000 chars `bounded_json` was clipping every list to 12 items, so the
`public-catalog` prompt shipped 12 of its 30 allowed components — including, silently,
`MarketingHero` and `ProductShowcase`, which that same contract assigned to the page's own hero and
showcase slots. `ScheduleRail` was also in the dropped set.

`listing_not_schedule_rail` is the second most common blocking gate code (4 across trios 2-5).

**Partly narrowed offline, and it did not resolve — here is exactly how far it got, so nobody
repeats the work.** From the archived trio logs, all four fires are on `ServicesPage.tsx` (×3) and
`TreatmentsPage.tsx` (×1). Then, from the catalogue:

- `ScheduleRail` is in `allowedComponents` for `public-home`, `public-service` **and**
  `public-catalog`. The gate never demands a component the skeleton forbids.
- Only `public-catalog` ever overflowed the budget, and `ScheduleRail` was among the 18 components
  the clip dropped. `public-service` is 4,899 chars — under budget, never clipped.
- A page titled "Services" or "Treatments" resolves to **either** skeleton depending on its purpose
  text: `_infer_skeleton_id` sends it to `public-catalog` if the text contains `browse`, `collection`,
  `catalog`, `shop`, `store` or `compare`, and to `public-service` otherwise. Both were verified by
  running the real inference.

So the hypothesis is live **only** for the `public-catalog` subset. The archive cannot settle which
subset these were: `.bmv-debug/catalogue-contract/` only dumps pages that were *rejected*, and these
pages compiled fine — they just lacked a component.

| | |
|---|---|
| **Instrument** | Gate codes per run, **recorded with the page's `skeleton_id`**; plus `catalogue_contract_components_dropped` WARN lines in the api log, which are new and name every dropped component |
| **Read it** | For each fire, record the skeleton. `public-service` fires are unaffected by the clipping fix and are writer-judgment. `public-catalog` fires are the ones the fix could have changed |
| **Decides** | Whether the code is a prompt-vocabulary problem (fixed) or a writer-judgment problem (Phase 3). Today it is being counted as one number when it is two different defects |
| **Caveat** | n=3 against a base rate of 4-in-12. A drop to zero is suggestive, not conclusive |
| **Cheap instrument worth adding first** | The gate failure message does not carry `skeleton_id`, which is the only reason this needed guessing. Adding it makes this and every future skeleton-conditional gate question answerable off the log. Offline, small, and not done this window |

### 6. **New** — Is the architect's route context a truncated preview on every real run?

`_catalogue_routes_context` (`codegen/architect.py:138-152`) serializes one **full** skeleton
contract per catalogue route into a 10,000-char `bounded_json`. Measured offline:

| catalogue routes | chars | what the architect receives |
|---|---|---|
| 1 | 5,004 | 1 route, 22 components |
| 2 | 7,745 | 2 routes, **12 components each** (list-clipped) |
| **3** | 10,000 | **collapsed to `{"truncated": true, "preview": "…"}`** |
| 8, 14 | 10,000 | collapsed |

Real runs have roughly 8-14 routes. If that holds live, the architect prompt's entire route/contract
block is a truncated preview string on every generation — and has been.

| | |
|---|---|
| **Instrument** | `.bmv-debug/` architect prompt for each run; count catalogue routes and grep the context block for `"truncated"` |
| **Read it** | Present-and-collapsed is a confirmed defect. Absent is a different finding — it would mean the offline reproduction does not match the live shape, and the reproduction is wrong |
| **Decides** | Whether this is filed as a defect or discarded. **Deliberately not fixed offline:** the fix is "state the allow-list once per run rather than once per route", which changes what the architect sees, and prompt changes cannot be validated without generations |

### 7. **New** — Does `visual_review_status` now name a reason on every run?

`2d69917`. Trios 4 and 5 stored `None`, which conflated a deadline skip, a configured skip, a stage
that raised, and a schema that predated the field.

| | |
|---|---|
| **Instrument** | `scripts/measure/analyse.py <trio>` |
| **Read it** | Every run reports one of `VISUAL_NOT_RUN_REASONS`, or a real status (`reviewed`/`partial`/`unmeasured`/`no_routes`). **A `None` in this trio means the fix did not reach the path that produced it** |
| **Decides** | Whether 1.11 can be measured at all on the pages-judged axis |

### 8. Is the dead-link guard actually fixed? — the confirming trio

Trio 5 (86-88) had zero dead-link gate failures where trios 2-4 had 37 dead links across 9 failures.
Trio 6 would have confirmed it and is void. n=3, and session 5 was twice wrong about a fix after a
single trio.

This trio also carries `430453a`, which stopped `AiFeaturePanel` linking to `/ai-features` when the
app has no hub route — dead in **5 of the 41 archived workspaces that render the panel** (requests
32, 36, 45, 47, 77).

| | |
|---|---|
| **Instrument** | Gate `dead_link` codes; `scripts/measure/replay.py` over the stored workspaces |
| **Read it** | Zero dead links across three runs is the second clean trio. Any dead link: record its href and whether it is a conditional route |
| **Decides** | Closes the dead-link work, or reopens it |

### 9. Does the ship rate move, and on which gate code?

1 of 3. Remaining blocking codes across trios 2-5, after the dead-link fix:
`visual_defect_severe` 5, `listing_not_schedule_rail` 4, `placeholder_content_shipped` 2,
`confirm_not_stage` 1.

| | |
|---|---|
| **Read it** | Per code, not in aggregate. `placeholder_content_shipped` firing **inverts a DoD row** that wants zero fires — the gate works, the writers still emit placeholders |
| **Do not** | Chase `tsc` counts expecting the ship rate to move. Request 83 shipped `ready` with 10 type errors; 78 failed with zero |

### 10. Wall clock and judged pages — measured separately

The reverted screenshot session-budget clip (1.11) improved nothing on the cap and took
`visual_pages_reviewed` from 10-of-18 to **0-of-18**. The measurement is a comment in
`screenshot.py` so nobody re-adds it.

| | |
|---|---|
| **Instrument** | `scripts/measure/tail.py` (post-deadline AI vs non-AI), plus `visual_pages_reviewed` |
| **Read it** | **Two axes, never one.** A tail improvement that costs judged pages is a regression |
| **Decides** | Whether 1.11 has an attackable surface |

### 11. Does trio 4's 600 s result reproduce?

Trio 4 cleared 600 s on 3 of 3 with 9-17 s of margin. The margin is thinner than the run-to-run
spread *within* a single trio (8 s in trio 4, 47 s in trio 2), so a slower model day puts it back
over. The DoD row is called met when a trio clears it **twice**.

| | |
|---|---|
| **Read it** | 3 of 3 under 600 s makes this the second clean trio and the row can be marked met. Anything else and it stays "no longer reproducibly broken" |
| **Also record** | `blocked_seconds` and `contention`. Trio 1 recorded zero contention — the runs never collided — so a trio with no contention is not evidence about concurrency either way |

---

## What this trio explicitly cannot answer

- **1.12** — whether a MANDATORY `architect` with no deterministic path is the right design. It only
  shows up when AppSpec has already burned the budget (request 74: 390 s, then `call_architect`
  raised 9 ms past the deadline). Three runs are unlikely to reproduce it. Do not read its absence
  as fixed.
- **The 100-templates and variety questions.** Phase 3.
- **Whether ~4.9 KB of contract on every generated file is affordable.** The clipping defect is
  fixed but the token cost is essentially unchanged — roughly 1.2k tokens a run saved out of ~18k.
  Reducing it means stating the allow-list once per run, which is question 6's fix and the same
  larger change.

## Analysis order, once the runs finish

1. `scripts/measure/analyse.py <trio>` — the DoD evidence table.
2. **Confirm the instrument before reporting the measurement.** Two wrong reports in session 6 came
   from the harness, not the pipeline. If a number looks like a finding, check the tool first.
3. Call census for questions 1-4. If appspec rows still carry `writer = NULL`, stop — question 1 is
   unanswered and the telemetry is the defect.
4. `.bmv-debug/` diffs for question 3 and the prompt inspection for question 6.
5. Gate codes for 5, 8, 9.
6. `tail.py` for 10.

Write results into the roadmap's Status table, not into a new document.
