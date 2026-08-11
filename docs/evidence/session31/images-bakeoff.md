# W1 — the image-model bake-off

*Run 2026-08-11 on `consultant-images-pipeline`. Every number below comes
from the service's own `ai_usage_events` ledger, not from the key balance
(the OpenRouter key is shared — see the reconciliation at the end).*

## What was measured

Three golden briefs, each frozen at the ui_spec stage (`golden/briefs/`),
each a different archetype, run through the **real** pipeline
(`generate_demo_screens`) — same composition variants, same regeneration
rule, same fixed per-image judge (`google/gemini-2.5-flash`).

| brief | business | archetype |
|---|---|---|
| dental | SmileBright Dental | operations-dashboard |
| law | Hartwell & Grey LLP | crm-dashboard |
| retail | Northgate Coffee Roasters | analytics-dashboard |

Candidates per cell: anchor = 3 distinct composition variants, follow-ups =
1 candidate each. Most cells ran 2 screens (anchor + 1 follow-up); the
tiering cell ran the full 3.

## The matrix

| brief | archetype | anchor model | follow-up model | imgs | QA (anchor / follow-ups) | $ cell | wall |
|---|---|---|---|---|---|---|---|
| dental | operations | gemini-3-pro-image | same | 4 | 8.7 / 8.0 | 0.580 | 117s |
| dental | operations | gemini-3.1-flash-image | same | 4 | 8.7 / 8.5 | 0.283 | 53s |
| dental | operations | gpt-5.4-image-2 | same | 4 | 8.1 / 7.8 | 1.056 | **354s** |
| dental | operations | **gemini-3-pro-image** | **gemini-3.1-flash** | 5 | 8.5 / 7.5 / 8.5 | **0.583** | 175s |
| law | crm | gemini-3-pro-image | same | 4 | 8.7 / 8.7 | 0.579 | 96s |
| law | crm | gemini-3.1-flash-image | same | 4 | 7.9 / 8.7 | 0.282 | 136s |
| law | crm | gpt-5.4-image-2 | same | 1 | 7.0 | 0.259 | 159s |
| retail | analytics | gemini-3-pro-image | same | 5 | 8.7 / 7.9 | 0.730 | 173s |
| retail | analytics | gemini-3.1-flash-image | same | 4 | 8.7 / 7.0 | 0.282 | 67s |

Measured per-image cost, from the ledger, over the whole run:

| model | images | $/image | vs roadmap estimate |
|---|---|---|---|
| `google/gemini-3-pro-image` | 12 | **0.1447** | as expected (~0.14) |
| `google/gemini-3.1-flash-image` | 14 | **0.0695** | **2.3x the assumption** — "cheap tier" is not cheap |
| `openai/gpt-5.4-image-2` | 5 | **0.2620** | as expected (~0.25) |

The roadmap's per-token pricing table badly under-predicts flash: image
output dominates, and the flash tier's lower per-token rate does not carry
through to a 2x cheaper image. Anything downstream that budgets from the
token table rather than from this ledger will be wrong.

## Pairwise

Absolute scores saturate — nearly every candidate lands between 7.8 and
8.7, which cannot separate "good" from "excellent". So each brief's anchors
were also compared head-to-head, **judged in both orders**, and a winner
counted only when the verdict survived the swap.

**The first pairwise judge failed the swap test outright.** With
`gemini-2.5-flash` as the comparator, the answer was "A" in all six runs
across three briefs — it was reading position, not pixels, and rationalized
opposite defects for the same image depending on where it sat. Labeling the
images explicitly in the payload did not fix it. The comparator was moved
to `anthropic/claude-sonnet-5` (a separate, still-FIXED instrument; the
per-image judge was NOT changed, so generator and judge never varied
together). That judge produced specific, differentiated findings.

| brief | pro vs flash, both orders | verdict |
|---|---|---|
| dental | flash, then pro | **tie** (order-dependent) |
| law | pro, then pro | **pro** |
| retail | pro, then pro | **pro** |

Structural findings the pairwise judge named, all independently visible in
the images: flash duplicated the entire Settings/Help navigation block on
law, garbled a chart tooltip ("Thurso: 8") and mismatched an axis scale;
pro's dental anchor had text clipped behind the composited logo corner —
which is why dental came out a tie, and is a compositing defect (W4), not
a model one.

**Its text findings, however, were confabulated.** The judge reported
"Hartwell Chamers" and "Northgate Roast Inteligence" as misspellings on
two specific screenshots. Both are false: `law-anchor-gemini-3.1-flash.png`
reads "Hartwell Chambers" and the retail anchor reads "Northgate / Roast
Intelligence", correctly spelled and merely wrapped across two sidebar
lines. Verified by eye and, afterwards, by transcription. So the pairwise
judge is trustworthy on structure and untrustworthy on spelling — which is
the entire argument for W3 doing that check by transcribe-and-diff in code
rather than by asking a judge. No verdict in the table above turns on the
false claims (both cells were decided by structural defects too), but any
future comparison must not take a judge's spelling report at face value.

## Verdicts

**`openai/gpt-5.4-image-2` is eliminated.** Not on taste:

1. It renders **square** (1024x1024). The product needs a wide desktop
   screenshot; a square one is the wrong artifact before quality enters.
2. 354s for four images against a 3-minute DoD budget for a whole request.
3. Lowest QA of the three (8.1 dental anchor, 7.0 law anchor).
4. 3.8x flash's cost per image.

**`gemini-3-pro-image` is the anchor model.** It won the swap-tested
pairwise 2-0 with one tie, matched or beat flash's anchor QA on every
brief, and was the only model to render the dental chart's axis correctly
(flash merged the labels into the values: "Mon 15, Tue 18, ...").

**`gemini-3.1-flash-image` is the follow-up model** — the tiering result.
Follow-up screens copy a design handed to them as a reference image rather
than inventing one, and that cheaper job survives the cheaper model. It
also has to be true for the DoD to hold: an all-pro 3-screen request costs
**$0.72**, over the $0.60 line. Pro anchor + flash follow-ups measured
**$0.583 at 175s** — inside both the cost and the 3-minute wall budget,
with nothing to spare on wall time.

Written into `ARCHETYPE_IMAGE_MODELS` for the three measured archetypes.
`scheduling-dashboard` and `pipeline-dashboard` are unmeasured and fall
back to `IMAGE_MODEL`.

## Stated limits — what this run does NOT establish

- **gpt-5.4 got 5 images, not 12.** After dental showed square output at
  354s, the third brief was dropped and law was run as a single-image
  confirmation. The eliminating properties (aspect ratio, latency, price)
  are model-level, not brief-level, but this is a deliberate reduction in
  coverage, made to stay inside the $6 cap.
- **Tiering was measured end-to-end on one archetype** (operations). crm
  and analytics inherit it from their all-flash follow-up scores (8.7 and
  7.0). The retail 7.0 is the weakest evidence in this document.
- **Two screens per cell, not three**, except the tiering run.
- **One sample per cell.** No variance estimate; a 0.2 QA difference here
  means nothing.
- The dental x flash cell was run twice — the first run's screenshots were
  destroyed by a rig bug (below) and its ledger row replaced.
- 2 of 5 archetypes have no golden brief at all.

## Two defects found and fixed while running this

1. **An upstream 429 arrives as HTTP 200.** OpenRouter returns a rate-limit
   failure inside a 200 body (`choices[0].error`, `finish_reason: "error"`,
   content truncated mid-string). Only the status code was checked, so
   2 of 6 ui_spec calls were counted as successes, failed to parse, and
   silently fell back to generic specs — a lead would have been shown a
   demo about "Alex" and "Bookings Today". Fixed in `provider` with
   detection plus one spaced retry for transient conditions only; the
   retries fired repeatedly during this bake-off and are visible in its
   logs. (commit `7b33b49`)
2. **The bake-off rig overwrote its own output.** The throwaway container's
   baked-in `DATABASE_URL` beat the service `.env`, so every cell opened a
   fresh DB, was handed request id 1, and wrote over the previous cell's
   screenshots. Costs and QA rows survived in `results.json`; two images did
   not. Cells now pin their own output directory and record the DB they
   resolved.

A third, unfixed, is visible in the pro dental anchor: the composited BMV
logo sits on top of the AI Workstream card, and the model even rendered the
word "Logo" in the reserved corner. That is W4's problem.

## Spend

| | |
|---|---|
| Ledgered this run (service DB) | **$4.203** |
| First dental x flash cell (DB destroyed by the rig bug) | $0.353 |
| Golden-brief text calls (`build_golden.py`) | $0.046 |
| **Attributed to this work** | **~$4.60** |
| Shared-key delta over the same window | $5.178 |

The ~$0.58 difference is not attributed here: the key is shared, and this
session also made a handful of unledgered ad-hoc probes (raw ui_spec
dumps, one Claude reachability probe). Per standing practice, only the
ledger delta is claimed.

Judge cost is negligible: 31 per-image QA calls came to $0.035; the 8
Claude pairwise calls to $0.141.

## Reproducing

```
python scripts/build_golden.py                    # freeze briefs (text only)
python scripts/bakeoff.py --brief dental --model google/gemini-3-pro-image --screens 2
python scripts/bakeoff.py --report
python scripts/pairwise_run.py --a <model> --b <model>
```

Raw data: `consultant-service/scripts/out/bakeoff/results.json` and
`pairwise.json` (gitignored working copies); images alongside them under
`<brief>/<model>/`.

Committed here in `bakeoff/`: both raw result files and the five anchors
the verdicts turn on —

| file | what to look at |
|---|---|
| `dental-anchor-gemini-3-pro.png` | correct chart axis and callouts; the composited logo sitting on the AI Workstream card, and "Logo" rendered in the reserved corner |
| `dental-anchor-gemini-3.1-flash.png` | label/value merge on the x-axis ("Mon 15", "Tue 18") |
| `dental-anchor-gpt-5.4-image-2.png` | square canvas, invented "Practice Overview" card, dead space |
| `law-anchor-gemini-3-pro.png` | the pairwise winner |
| `law-anchor-gemini-3.1-flash.png` | duplicated Settings/Help navigation block |
