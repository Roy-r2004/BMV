# W3 — the text-truth gate, and what validating it cost

*Built and validated 2026-08-11. Build cost $0; validation ~$0.01 of
transcription calls against screenshots the W1 bake-off had already paid
for.*

## The instrument

A second vision call per candidate transcribes every string the image
actually renders (`prompts/image_text_transcription.j2` — no rubric, no
scoring, nothing to approve). `pipeline/text_truth.py` then diffs that
transcription against the spec **in code**. Failure forces `approved=False`
on the QA verdict, so the existing single regeneration handles it; the gate
adds no second retry budget.

Why not just ask the judge? Because judges are unreliable about text in
both directions, which this session demonstrated twice:

- The aesthetic judge scored bake-off screens in the 8s while reporting
  their text as correct.
- The pairwise judge **invented** two misspellings — "Hartwell Chamers"
  and "Northgate Roast Inteligence" — on screenshots where both wordmarks
  are spelled correctly and merely wrap across two sidebar lines.

A transcribe-then-diff comparison makes a one-character difference
arithmetic instead of opinion.

## What the gate enforces, and what it refuses to

Every relaxation below was bought by a **false rejection observed on a real
bake-off screenshot**. A gate that rejects correct screens burns a
regeneration and, when both attempts "fail", ships something worse.

| rule | why |
|---|---|
| case-insensitive | a sidebar rendering "DASHBOARD" is styling, not a misspelling |
| whitespace collapsed | ditto |
| matched against the flattened transcription | every model wraps the wordmark across two lines ("SmileBright" / "Operations"); per-line matching called 4 of 4 correct screens misspelled |
| word-boundary containment, not raw substring | "Dashboard 12" must satisfy "Dashboard", but "Recal" must NOT satisfy "Recall" |
| a substring relationship is never a "misspelling" | "SmileBright Dental" vs a wordmark reading "SmileBright" scores 0.76 similar — nothing is misspelled, the name is just shorter on screen. Most businesses share a prefix between company and product name |
| only `navigation[:8]` | that is the slice `prompt_builder` actually sends; holding a screen to a 9th label it was never given is an unfixable permanent failure |
| **the business name's absence is not a failure** | see below |

### The business name is usually not on screen — correctly

None of the models rendered "Hartwell & Grey LLP", "SmileBright Dental" or
"Northgate Coffee Roasters" anywhere. That is what real product software
looks like: the sidebar carries the *product* wordmark, not the client's
company name. Requiring it would have failed every screenshot in the
bake-off.

So the rule is the roadmap's actual one, stated precisely: **if the
client's name appears, it must be spelled correctly.** Absence is reported
(`text_truth.absent`) and never rejected. The product name and navigation
labels, which the prompt does explicitly ask to be rendered, must be
present AND exact.

## Validation

Against four real bake-off screenshots (two models, three briefs):

| screenshot | gate |
|---|---|
| law / gemini-3.1-flash | pass |
| law / gemini-3-pro | pass |
| retail / gemini-3.1-flash | pass |
| dental / gemini-3-pro | pass |

Matching what the images actually show — no false positives. Then the same
real transcription with a typo injected into the *rendered* text, which is
the direction that happens in production:

| image renders | gate |
|---|---|
| "Smilebrite" for "SmileBright" | **rejected** |
| "Recal" for "Recall" | **rejected** |
| "Operatons" for "Operations" | **rejected** |

An earlier draft of the gate failed all four real screenshots. Every one of
those was a false positive; each fix above is one of them.

## Limits

- The gate is only as good as the transcription. A transcriber that
  silently corrects a misspelling would hide exactly what this checks;
  the prompt orders it not to, but that is an instruction, not a
  guarantee.
- A transcription outage fails **open** (`passed: None`) — an outage must
  not reject every candidate a request has. In the best-effort fallback,
  "unknown" ranks above "known bad" and below "known good".
- KPI values and panel row text are not checked. The roadmap's hard-fail
  set is business name, product name and nav labels; extending it to every
  number would multiply false rejections on the exact strings models are
  worst at transcribing.
- No end-to-end run yet with a genuinely misspelled screenshot produced by
  a model — none of the bake-off images contained one. The injected-typo
  runs above are the closest available evidence.
- Cost: one extra flash call per candidate, measured at ~$0.001. On a
  5-image request that is ~$0.005, inside the $0.60 budget.

## Reproducing

The gate is pinned by `tests/test_text_truth.py` (17 tests) covering the
diff and the wiring, including that the gate can only ever reject, that it
still runs when the aesthetic judge is down, and that a rejected-everything
fallback prefers a plainer screen with correct text over a prettier one
with the client's name wrong.
