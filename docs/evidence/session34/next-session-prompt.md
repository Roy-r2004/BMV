# Kickoff — brief me before you touch anything

**This is an explain-first session. Spend nothing and start nothing until I
say go.** Your first deliverable is understanding, not progress: I want to
know what is still open on the image pipeline, and — for everything that is
already claimed as done — how that result was actually produced and how much
I should trust it.

Work happens on `main` (the `consultant-images-pipeline` branch was merged
2026-08-12; main is ~61 commits ahead of `origin/main`, unpushed, tree clean,
suite 262 green). Use explicit git pathspecs — parallel sessions share this
checkout.

## Read first, in this order

1. `docs/evidence/session34/README.md` — what session 34 landed and measured
2. `docs/evidence/session34/fullset-results.md` — the per-screen table
3. `docs/evidence/session34/next-session-runbook.md` — the blocked work
4. `consultant-service/ROADMAP.md` — **stale on purpose**: its last status
   block is session 33. Treat it as history, not as current state, and tell
   me if it should be updated.

Then the job docs as needed: `job1-resolution.md` (2K follow-ups),
`job2-backdrop-crop.md` (the PIL crop), `job3-defect-check.md` (the two-stage
defect check).

## What I want back — two parts

### Part 1 — how the current results were produced

For each headline claim below, tell me **which instrument produced it, on
what sample, and where it could be wrong.** I do not want the number repeated
back; I want to know what kind of evidence it is.

| claim | s33 | s34 |
|---|---|---|
| screens below the 8 gate | 4 of 15 | 1 of 12 (a best-effort 6.5) |
| screens shipping a confirmed structural defect | 13 of 15 | 3 of 12, all charts |
| text-truth failures shipped | 1 ("Cilents") | 0 |
| mean cost per brief | $0.4415 | $0.6022 |
| wall per brief (bakeoff harness) | 90–101s | 116–173s |

Specifically, be honest with me about these four:

- **The defect numbers are measured by two different instruments.** s33's
  13/15 came from an offline sweep; s34's 3/12 came from the in-path check.
  Explain why that comparison is not apples-to-apples, and what it would take
  to make it one.
- **The sample is 12 screens, not 15.** Explain what is missing and why.
- **Cost is $0.6022 against a $0.60 DoD line.** Explain what pushed it up,
  and whether that is a regression or the gates doing their job.
- **The 3-minute clock has never been measured on the current path.** Explain
  what the 116–173s bakeoff walls do and do not tell us about a real request,
  and why s33's 2m48s no longer answers it.

Also explain, in plain language, the two mechanisms that most of this rests
on, because they are the parts I would have to defend to a customer:

- the **two-stage defect check** — inspector, then a verifier told to refute
  — and why "both stages must agree" is the shape that survived when single
  judges did not;
- the **text-truth gate** — why exact strings are decided in code and never
  by a judge, and what the band/magnification path is for.

### Part 2 — what is actually pending

Walk me through each open item with: what it is, why it exists (what evidence
put it on the list), what it costs, what "done" looks like, and what could go
wrong. Rank them by what stands between here and declaring Phase 1 shippable.

The list as I understand it — correct me if the repo says otherwise:

1. **Top up the OpenRouter key.** The shared key hit 402 mid-batch. Every
   funded item below is blocked on it. (Never read the account balance —
   attribute spend only via bracketed `ai_usage_events` deltas.)
2. **Three blocked measurements**, one command each, ~$2.50 total, scripted
   in `next-session-runbook.md`: the hedgefund control brief, the v3 title
   arm (law + retail), and the end-to-end clock (`run_e2e_request.sh`).
3. **JOB 6 — composite the charts in PIL.** The only remaining code. All
   three shipped defects are `malformed_data_display`; the baseline to beat
   is 3 of 12. One archetype, side by side, my eye decides.
4. **The DoD scorecard** — tell me where each of the five lines stands today
   and which are provable without new code.
5. **Ops loose ends**: the `/studio` page's backend runs as an ad-hoc
   `bmv-consultant` container on port 8002 and is not in `docker-compose.yml`;
   `ROADMAP.md` is a session stale.
6. **The watch-list** that is deliberately not scheduled: the offline sweep
   at s33 thoroughness, promoting `ai.title` into the text-truth gate (a
   tightening — it needs its own measured run), the pro anchor's letterform
   risk.

## How to answer

Verify before you assert. Where a claim can be recomputed from artifacts
already on disk for $0, recompute it rather than quoting the doc — and count
the whole artifact instead of sampling a window. Resolve settings from the
running process, not from `.env` files. Read spend via
`/api/requests/{id}/admin`, never by reading the SQLite file while the
service is running.

If the repo contradicts anything in this prompt, the repo wins — say so
plainly and tell me what changed.

Do not start any funded run, do not begin JOB 6, and do not push to origin.
When I have read your brief I will tell you which item to start.

## Settled — do not re-litigate

The cinematic register ships (owner signed off 2026-08-11). The QA gate is 8,
enforced in code. The pairwise judge stays on the v2 rubric. `DASHBOARD_CANDIDATES`
is 2. Watermark on every byte under `/uploads`; glamour composited in PIL,
never asked of the image model; text truth decided in code, never by a judge;
the QA judge held fixed while generators vary. Never run two bakeoff batches
concurrently — `results.json` is rewritten wholesale.
