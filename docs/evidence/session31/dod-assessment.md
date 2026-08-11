# Phase 1 — the five DoD lines, measured

*Golden-set run 2026-08-11, five briefs, the shipped configuration:
`gemini-3-pro-image` anchor + `gemini-3.1-flash-image` follow-ups, text-truth
gate on, art packs off, design sheet off, presentation compositing on.*

**Three of five lines hold. Line 2 fails on the evidence; line 3 is the
owner's to judge and is waiting.** Phase 1 is not declared shippable in this
session.

## The run

Two screens per brief (anchor + one follow-up), two anchor composition
variants. Both reductions are stated in "Limits" below.

| brief | archetype | anchor QA | follow-up QA | cell $ | wall |
|---|---|---|---|---|---|
| dental | operations | 8.7 | 8.5 | 0.367 | 82s |
| law | crm | 8.1 | **7.5** | 0.366 | 64s |
| retail | analytics | **9.2** | 8.1 | 0.444 | 104s |
| salon | operations | **9.2** | 8.7 | 0.587 | 125s |
| hedgefund | analytics | **9.2** | 8.7 | 0.368 | 73s |

## Line by line

### 1. Brand-critical text accuracy 100% on shipped screens — **HOLDS**

Ten of ten shipped screens passed the W3 gate: every navigation label and
product name rendered exactly, business names either exact or (correctly)
absent. Verified from each screen's saved `text_truth` block, not from a
judge's opinion.

One caveat, and it is the honest one: the gate confirms what the
transcriber read. A transcription that silently corrected a misspelling
would hide the thing being checked.

### 2. Every shipped screen QA ≥ 8; anchors ≥ 9 on ≥ 4 of 5 briefs — **FAILS**

- Screens ≥ 8: **9 of 10**. The law follow-up (pipeline/kanban) scored 7.5.
- Anchors ≥ 9: **3 of 5** (retail, salon, hedgefund). dental 8.7, law 8.1.

The shortfall is concentrated on one brief and one layout: `law`, the crm
archetype, whose kanban screen is the weakest artifact in the set on both
runs it has appeared in. Two anchor variants rather than three is a real
handicap on this line — fewer candidates to select from can only lower a
selected score — but it does not explain a 7.5, and I am not claiming it
would have crossed 9.

### 3. Pairwise beats today's default on ≥ 4 of 5 briefs — **AWAITING THE OWNER**

The sheets are in `docs/evidence/session31/sign-off/`, one per brief,
current default beside new pipeline, no scores and no commentary on them.
Three briefs (dental, law, retail) have a genuine current-default run to
compare against; salon and hedgefund do not — the W1 matrix never covered
them — so those two sheets show the new artifact alone and cannot count
toward the 4-of-5.

**This is the gate that stops the session.** The DoD makes the owner's eye
final, and two of five comparisons do not exist yet.

### 4. Cost ≤ $0.60/request with tiering, wall ≤ 3 min — **HOLDS, WITH NO MARGIN**

The production-shaped measurement (3 screens, 3 anchor variants, tiered)
is **$0.583 at 175s** — inside $0.60 and inside 180s, with 3% and 5 seconds
to spare. Both budgets are effectively at their limit.

And a regeneration breaks the cost line: `salon` cost $0.587 for **two**
screens because the gate rejected its anchor twice. That rejection was a
false positive (below), now fixed, but the general point stands — one
regeneration on a three-screen request puts it over $0.60.

### 5. Zero unbranded bytes reachable under /uploads — **HOLDS**

Every screenshot, every non-selected candidate, and the W5 design sheet go
through the watermark; every W4 composite carries the mark on its backdrop.
Pinned, and the pins are green.

## What the golden set found

**A false positive in the text-truth gate, caught in production shape and
not by any test.** The salon screen renders its product wordmark "Lumière
Studio OS"; the gate scored that similar enough to the business name
"Lumière Hair Studio" to call it a misspelling, rejected a correct screen,
and spent a regeneration — which is exactly why that request cost 60% more
than its siblings. Text that correctly renders one required string can no
longer be reported as a corruption of another. Fixed and pinned.

That is the second time this session a measurement paid for itself: the
first was the upstream-429 defect found while freezing the briefs.

## The pattern across all three experiments

W2 (art packs), W5 (design sheet) and the W1 dental tie all lost the same
way: **content crowding the bottom-right corner reserved for the composited
logo.** Every judged run that went against a change named clipped or
truncated text in that corner as the deciding defect.

The reserved corner is now the binding constraint on prompt improvement.
Anything that makes the model fill the canvas more confidently — which is
what a design system is for — pushes content into it. W4 already moved the
mark off the composite; the raw screenshot still carries a corner mark, so
the prompt still has to reserve the corner.

**The recommended next change, and it is cheap:** brand the raw screenshot
with a thin composited footer strip below the interface instead of a corner
mark. The canvas grows ~4%, the UI is never covered, the "no unbranded
bytes" policy still holds, and the ~120 words of corner-reserve instruction
leave the prompt entirely. Then re-run the W2 and W5 comparisons, both of
which are already built and one env var away.

## Limits of this assessment

- Two screens per brief, not three; two anchor variants, not three. Both to
  stay inside the session's spend ceiling. The reductions can only
  understate quality on line 2 and understate cost on line 4.
- One sample per brief. No variance estimate.
- The QA judge is `gemini-2.5-flash` throughout, unchanged all session, so
  the scores are comparable to each other — and no further than that.
- Line 3 is unmeasured for two of five briefs.

## Spend

| | |
|---|---|
| Ledgered (service DB) | **$8.774** |
| First bake-off cell (DB destroyed by a rig bug) | $0.353 |
| Golden-brief text calls | $0.046 |
| **Attributed to this session** | **~$9.17** |
| Shared-key delta over the same window | $9.91 |

Against a $10 ceiling. **No further funded steps were taken after the
golden-set run**, which is why the two missing comparisons for line 3 were
left missing rather than bought.
