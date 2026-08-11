# Definition of done — session 33, measured

*2026-08-12, branch `consultant-images-pipeline`. Ledger delta **$3.71**
against a $15 ceiling. Suite 164 → 222.*

**Phase 1 is not shippable.** Two of the five lines fail on measurement, and
both failures are new information rather than known gaps: they were invisible
until this session ran the public path end to end and produced a complete
5×3 golden set in this register for the first time.

| # | line | verdict | measured against |
|---|---|---|---|
| 1 | brand-critical text 100% | **FAILS** | a shipped nav label rendered "Cilents"; the gate reported the screen as passing |
| 2 | no screen < 8, no structural defect | **FAILS** | 4 of 15 screens scored below 8; **13 of 15** carry a listed defect |
| 3 | beats the old default, owner's eye | **PASSES** | owner signed off on the session-32 sheets, 2026-08-11 |
| 4 | ≤ $0.60/request, ≤ 3 min | **PASSES** | $0.5336 and 2m48s on the real path; $0.4415 and 94s per golden brief |
| 5 | zero unbranded bytes under /uploads | **PASSES** | 14/14 files on request 68, screenshots and composites alike |

---

## Line 1 — brand-critical text accuracy 100%. FAILS.

The salon schedule screen rendered its navigation item as **"Cilents"** — i
and l transposed. The text-truth gate passed it.

- [`job1/cilents-followup-8x.png`](job1/cilents-followup-8x.png) — the
  follow-up screen's nav at 8×.
- [`job1/clients-anchor-8x.png`](job1/clients-anchor-8x.png) — the same slot,
  same font, same size, on the anchor of the same run, rendering "Clients"
  correctly.

The control matters: the difference is in the pixels, not in my reading of
them.

The gate missed it because the transcription model read back the word it
expected. Its prompt has said *"if a word looks misspelled, transcribe the
misspelling — do not correct it"* since the day it was written, and that is
the whole lesson: **the model was short of resolution, not willingness.** A
nav label is around ten pixels tall in a 1376px-wide screenshot, and a vision
model downsamples before it reads.

The fix ships (deterministic 3× magnifications of the top and left bands ride
along on the transcription call that was already happening) but is
**UNVERIFIED** — the re-run did not reproduce the misspelling, so nothing has
yet shown it catching one.

Two things this line does NOT fail on, both worth stating because both look
like failures in the raw data:

- **`business_name` reported absent on all 15 screens.** That is the gate
  working as designed. Real product UIs show the product wordmark, not the
  client's company name, and the rule is "if the client's name appears it must
  be exact", not "it must appear". The relaxation was bought by a false
  rejection in session 31.
- **Non-brand-critical misspellings** — "Workfiow" for "Workflow",
  "viabllity" for "viability", both confirmed at 7–8× zoom. The gate does not
  check these and never claimed to. They are line 2's business, as garbled
  labels.

## Line 2 — no screen below 8, and no structural defect. FAILS, on both clauses.

**The score clause.** 4 of 15 screens scored below 8 on the fixed judge: law
dashboard 7.5, law analytics 7.5, salon dashboard 7.9, hedgefund performance
7.9. Mean 8.43.

There is a mechanism behind this, and it has been there the whole time:
**`QA_MIN_SCORE` is 7.** The pipeline's approval threshold has never been set
to the number the DoD is judged against. Sessions 31 and 32 passed this clause
by luck — every screen happened to land at 8 or above — not by construction.
Only 2 of 20 candidates this run fell below 7; 7 of 20 fell below 8.

I have not changed the threshold. Raising it to 8 would reject 7 of 20
candidates instead of 2, buy one more regeneration per affected screen, and
still not guarantee the floor — the best-effort path ships the highest scorer
when nothing is approved. It is a real option with a measured cost and an
unmeasured benefit, and it is the owner's call, not a change to slip in at the
end of a session.

**The defect clause.** All fifteen screens were inspected — nine of them read
at full size by me, and all fifteen by an independent per-screen sweep whose
every claim was then put to an adversarial verifier told to refute it. **13 of
15 carry at least one item from the list**, including both screens that scored
9.2. Only dental's dashboard and hedgefund's analytics overview came back
clean, and I disagree with the sweep on both — I read a duplicated
button pair on one and a floating frame on the other. Take 13/15 as the
conservative number.

| screen | QA | defect found by looking |
|---|---|---|
| dental dashboard | 8.1 | "Book Appointment"/"Reschedule" button pair drawn twice |
| law dashboard | 7.5 | AI module titled "HERO INTELLIGENCE" — the composition variant's own name |
| law analytics | 7.5 | "Attorney Performance" panel twice, identical rows; module titled "ONLY AI INTELLIGENCE" |
| retail analytics | **9.2** | interface floating on a backdrop; module titled "PREMIUM AI INTELLIGENCE"; placeholder "Action" button |
| retail customers | **9.2** | module titled "INTELLIGENCE MODULE"; three unlabelled controls on the hero |
| salon dashboard | 7.9 | interface floating as a rounded card on a pink backdrop |
| salon schedule | 9.1 | two mouse cursors drawn on the hero photo; "Cilents" |
| hedgefund analytics overview | 8.7 | floating; two cards hanging outside the app frame |
| hedgefund performance | 7.9 | "Recent Trades" twice, identical rows; five unlabelled controls on the hero |

Six more the sweep found and verified, that I had not opened:

| screen | QA | defect |
|---|---|---|
| dental schedule | 8.7 | panel titled "Premium Intelligence" |
| dental analytics | 8.1 | y-axis labelled 60/50/40/20/0 at equal pixel spacing — an unreadable scale, verified at 10×; card titled "OPINION" |
| law pipeline | 8.7 | the *entire* recommendation card drawn twice side by side, identical eyebrow, headline, subtitle and chips |
| retail analytics | 9.2 | "WHOLE BEAN SLB" / "GROUND SLB" — an S where a 5 belongs, verified at 10× against a real 5 in "$4,850" |
| retail dashboard | 8.7 | four metric cards carrying bare numbers and no labels at all; interface floating on a backdrop |
| hedgefund clients overview | 8.5 | see the sweep record |

That the two 9.2s are in this table is the point the owner made when they
amended this line on 2026-08-11. **The judge's score does not track the defect
list**, so the score clause and the defect clause are measuring different
things and only one of them can be automated.

Five of these defect classes were fixed and pinned this session, and the
fixes were re-measured on the two worst briefs ($0.8789): law's anchor lost
"HERO INTELLIGENCE" and went 7.5 → 8.1; salon's anchor stopped floating and
went 7.9 → 8.1. **Both re-runs then produced new defects** — an unlabelled "+"
button where "Book Consultation" had been, and "viabllity" at 7× zoom.

That is the finding, not a footnote. The register produces beautiful screens
carrying a small, varying handful of structural defects, and no single prompt
change removes the class. Line 2 needs either a mechanism that catches defects
per screen and regenerates on them, or an owner's decision about what is
acceptable in a demo.

## Line 3 — beats the old default, owner's eye. PASSES.

Signed off 2026-08-11 on the session-32 sheets. Nothing this session
re-opens it: the register is unchanged, and every change made was a defect
fix rather than an art-direction change.

Full-set sheets — the complete three-screen deliverable per business, which
no sheet has ever shown — are in [`sign-off/`](sign-off/). They are for the
next conversation, not a re-litigation of this line.

## Line 4 — ≤ $0.60 per request, ≤ 3 minutes. PASSES.

Measured on the real path, request 68, ledgered per call:

| | |
|---|---|
| total | **$0.5336** |
| images | $0.50044 across 5 calls (2 pro anchor candidates, 3 flash follow-ups) |
| QA + text-truth | $0.01476 across 10 calls |
| text stages (analyze → ui_spec) | $0.01839 across 6 calls |
| wall clock | **2m48s** |

The five image calls include one regeneration: the analytics candidate scored
9.2 and **failed the text-truth gate**, so it was rejected and re-rolled. The
gate earning its keep on the public path is worth as much as the number.

Per golden brief, three screens, no regeneration: **$0.4415** at 90–101s.

`app/pipeline/cost_model.py` now evaluates this line without spending
anything, and its pin takes the image count from the real generator rather
than from itself. Projections at the shipped defaults:

| | nominal | worst case |
|---|---|---|
| images | 4 | 7 |
| cost | **$0.4604** | $0.7538 |

The worst case is over the line. It only fires when *no* candidate for a
screen was approved, and it is pinned rather than left to be discovered
during a funded run.

That pin immediately caught something nobody had costed: `scheduling-dashboard`
and `pipeline-dashboard` are selectable by the public intake, no golden brief
lands on either, and both fell through to the pro-class model for **both**
roles — $0.68 a request, over the line, silently. Fixed with
`FOLLOWUP_MODEL_FALLBACK`.

## Line 5 — zero unbranded bytes under /uploads. PASSES.

All 14 PNGs written by request 68 carry a mark: the three screenshots and the
two retained candidates on the footer strip, the nine composites on the
backdrop clear of the interface. See
[`job1/hero-composite.png`](job1/hero-composite.png).

---

## What would make Phase 1 shippable

1. **Line 1** — reproduce a rendered misspelling and show the magnified-band
   gate catching it. Until then the fix is a hypothesis with a mechanism.
2. **Line 2, the score clause** — an owner's decision on `QA_MIN_SCORE`.
   Raising it to 8 makes the pipeline enforce the number it is judged
   against, at roughly one extra image on 20% of screens.
3. **Line 2, the defect clause** — the harder one. The per-image judge cannot
   be the instrument; it scored 9.2 twice for screens carrying duplicated
   panels and invented titles. The swap-tested pairwise judge **can** —
   see [`results.md`](results.md#job-5) — and it is now the only automated
   instrument in this project that has been shown to find real structural
   defects and survive an order swap.

   The per-screen sweep run in this session is a second existence proof: 15
   independent inspectors, each claim then put to a verifier told to refute
   it, found 13 of 15 screens defective and root-caused one class nobody had
   diagnosed (the top-bar button labelled "Action" is the prompt's own
   descriptive word, because the block asked for "an accented action button"
   and supplied no string). That fix landed. The mechanism generalises.
