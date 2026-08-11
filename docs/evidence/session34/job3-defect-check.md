# JOB 3 — the defect check, wired into the request path

*2026-08-12, session 34. One funded dental run $0.7832 (ledger-bracketed:
515→548 rows, $21.3139→$22.0971).*

## What was built

`app/pipeline/defect_check.py` + two rubrics, wired into `qa.review_image`
as a third instrument beside the judge and the transcription. The
structure IS session 33's sweep, kept deliberately: **one inspector per
screen reports countable structural defects, then each claim goes to a
separate verifier told to refute it, defaulting to refuted when
uncertain.** Only a claim both stages agree on rejects a candidate; the
existing regeneration path handles the rest. Text claims are forbidden in
both rubrics and off-rubric claims die in code before a verifier ever
sees them (`text_truth.py` owns text, nothing else does). Both stages
fail OPEN. `ENABLE_DEFECT_CHECK` on by default, `DEFECT_MODEL` =
gemini-2.5-flash.

## The clock guard is architecture, not hope

The brief said "screens are already generated in parallel" — they were
NOT: follow-up screens ran serially, and adding any per-screen check to
that serial path would have blown the 3-minute line. Two changes:

1. **Follow-up screens now run concurrently**, each on its own DB session
   (orchestrator.run's own pattern; no SQLAlchemy Session crosses a
   thread).
2. **The three instruments fire concurrently per candidate** (independent
   reads of the same bytes), then the per-claim verifiers in the same
   pool. qa.py was split into pure network calls + a calling-thread
   orchestrator that owns every ledger write.

Both are pinned with barrier tests that DEADLOCK (loudly, 10s timeout) if
either ever goes serial again. The regeneration budget stays at 1.

## First funded run (dental, request 77) — every path exercised at once

| screen | what happened |
|---|---|
| schedule | cand 0 (8.5) carried a **confirmed** defect → rejected → regen produced a clean **9.2** that shipped. The gate buying a real improvement for $0.103. |
| analytics | 1 inspector claim → **refuted** by the verifier → nothing lost but the $0.0008 verify call. The stage that kills single-judge noise, working. |
| dashboard | both pro candidates confirmed as floating-on-backdrop (verified by eye — [`job3-dental-dashboard-float-half.png`](job3-dental-dashboard-float-half.png); this is the tone-on-tone/asymmetric float JOB 2's crop refuses by design) → regen produced a **clean 7.8** → best-effort shipped the *defective 8.1* instead. **Bug, fixed and pinned**: `_fallback_rank` now prefers text-true > defect-free > score, so the clean screen ships. |

Costs, measured from the ledger: inspector $0.00103/candidate, verifier
$0.00084/call at 1.5 claims/candidate → **$0.00228 per candidate**, now a
constant in `cost_model.py`. Cents, as briefed.

## The honest cost picture

This brief cost $0.7832 — both regens fired, which is what the worst-case
projection describes ($0.905 with the defect check on; it was already
over the line at $0.754 before this session and pinned as the accepted
regeneration tail). Nominal projection with everything on: **$0.537**,
inside the $0.60 line. What the gate changed is how often the tail fires:
a defect-confirmed candidate now costs a regeneration where it used to
ship silently. Whether the golden-set MEAN stays under $0.60 is exactly
what the full re-measure at the end of this session answers — and if it
does not, the owner's options are the knob (`ENABLE_DEFECT_CHECK=false`)
or the price of shipping defects, stated plainly.

Wall clock: 212s for the whole brief in the SEQUENTIAL bakeoff harness
including both regenerations; the request-path number (parallel
follow-ups, parallel instruments) is measured end-to-end before this
session closes.
