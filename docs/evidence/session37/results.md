# Session 37 — the confirmation batch, and the stop the criteria ordered

*2026-08-12, `main`, same conversation as session 36. Four funded requests,
**$2.5677**, label `s37-target`: the target config (1 anchor candidate,
hard-fail+bad-screen regeneration) with all three session-36 fixes live.
Kill criteria agreed with the owner before a dollar moved: batch mean
≤ $0.60 flips `DASHBOARD_CANDIDATES=1` and closes the cost program;
mean > $0.60 stops it with this write-up.*

## The verdict

**Mean $0.6419 — above the line. The cost program stops here.** The
default stays 2 (`test_the_shipped_anchor_candidate_count_is_two`
unchanged); no further cost experiments are proposed.

| run | request | cost | wall |
|---|---|---|---|
| hedgefund | /studio/100 | $0.6602 | 349s |
| law | /studio/101 | $0.4962 | 326s |
| salon | /studio/102 | $0.7609 | 390s |
| retail | /studio/103 | $0.6504 | 376s |

Across all eight target-config runs (sessions 36+37): **mean $0.634,
spread $0.385–0.761**. That is the honest realised price of this config at
the product's current first-shot quality. The $0.42–0.47 projection
assumed the defect tail would shrink to the corpus base rate; it did not,
because the tail is not configuration — it is the model's chart drawing.
Walls this batch (326–390s) were inflated by upstream flash rate-limiting
(nine 429-inside-200s absorbed by the retry ladder, zero failures).

## What the batch validated

- **The brand-variant fix works.** Zero text-truth failures across all 12
  screens — including law and retail, which burned ~$0.46 of text-triggered
  regenerations on this exact defect in the control arm. Law's realised
  cost halved: $0.9171 → $0.4962. Eight post-fix runs, zero recurrences of
  a class that hit 4 of 8 pre-fix cells.
- **The regeneration policy is behaving as approved.** Every regeneration
  this batch was audited or spot-audited: all fired on confirmed defects or
  sub-7.0 screens; request 100's anchor re-roll turned a 7.9-with-defect
  into a clean approved 8.1. Marginal screens (101's 7.0 dashboard) shipped
  logged with nothing spent.
- **The tail is charts, again and consistently.** Every defect that bought
  a re-roll or shipped this batch is on a data-display: an unlabelled bar
  (100), uneven axis steps (102, 103), and both 6.5-scoring analytics
  screens. The remaining money is in exactly one place.

## The structural conclusion, stated plainly for the owner

The config floor is **$0.390** and it is real (hit live on request 96).
The realised price is **~$0.63** and will stay there until first-shot
chart quality improves, because the pipeline correctly refuses to ship
broken charts without one re-roll, and the model draws a broken chart on
roughly one screen in three. Turning that refusal off is a cheaper number
and a worse product — settled, not relitigated.

Anything that moves the realised number from here is **quality work, not
cost work**: the coded-ticks prompt experiment (specced in
`docs/evidence/session36/results.md`, ~$2 to measure) and JOB 6
(PIL-composited charts — also the only fix for marker alignment). Fund
them if defect-carrying screens bother the demo commercially; do not fund
them to chase a cheaper mean.

## Quality of the batch (aggregate_run s37-target)

Below 8: 4 screens (6.8, 6.5, 7.0, 6.5). Shipped with confirmed defect: 3
(all data-display class). Text-truth failures: 0. The below-8 ships are
the approved policy's logged band plus two sub-7 screens whose re-rolls
lost — the old policy ships the same screens.

## Spend accounting

Session 36: $5.9908. This batch: $2.5677. **Conversation total: $8.5585**
against the original $10 budget — past the brief's $8 stop line by $0.56,
on the owner's explicit authorization of this batch (~$2 quoted, $2.57
actual, inside the $2.60 tripwire declared at launch). Key balance after:
~$110. Nothing pushed; commits this session are documentation only.
