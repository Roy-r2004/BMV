# Session 32 — what the funded run measured

*2026-08-11. 6 businesses, 24 image cells. Ledger delta **$8.21**.*

## The headline

The cinematic register, tool screens, hero assets and the AI module all
work, and the follow-up screens inherit them. **But no automated instrument
in this project could prove the new look beats the old one** — one is
saturated, the other is position-biased. The decision is the owner's, which
is what DoD line 3 says it should be.

## Every instrument, and what it was worth

| instrument | verdict | trustworthy? |
|---|---|---|
| text-truth gate (code) | 8/8 pass, both registers | **yes** — the only one that held up |
| per-image vision judge | light 8.88 avg, cinematic 8.58 avg | **partly** — good on defects, saturated on quality |
| swap-tested pairwise | 3 ties, no verdict | **no** — position bias, fabricated evidence |
| the owner | prefers cinematic | the DoD's final word |

### The pairwise judge fabricated its evidence

`claude-sonnet-5` picked the first-presented image in **6 of 6** runs and
justified every pick with a text-accuracy claim:

> "Image A accurately renders the full product name … while Image B omits
> 'Dental' from the business name."
> "Image A flawlessly renders all brand-critical text, whereas Image B fails
> this primary criterion."

The text-truth gate transcribed the same files and found **every**
brand-critical string exact on both sides. The claims are inventions, produced
to justify a positional preference.

This is the second judge to do this. Session 31 caught `gemini-2.5-flash`
answering "A" 6 of 6 and replaced it with Sonnet 5; Sonnet 5 now does the same
thing. **The order-swap protocol is what saved both runs** — it converted six
false wins into three honest ties.

### The per-image judge is a defect detector, not a quality meter

Four conditions on the same brief — full cinematic, hero off, tool flow off,
art packs on — all scored **exactly 9.2**. It cannot see the difference
between a screen with a photoreal hero and one without.

It is still useful, and it earned its keep this session: its three complaints
about the first cinematic dental anchor were three real misspellings, which I
confirmed at 4× zoom. Use it to catch defects. Do not use it to rank designs.

## What was proven

**Tool screens: 6/6.** Asked for as a per-screen `concept` field, the spec
stage returned "dashboard" for 6 of 6 businesses across two prompt revisions —
the archetype catalogue above it names a sequence of dashboards, so a
per-screen field reads as "which kind of dashboard". Hoisted to a required
top-level `anchor_tool` key answered *before* the screens array, and mapped on
in code: **6 of 6**, with real options (salon: service → stylist → slot;
retail chose `configurator` on its own for blend → roast → bag).

**Inheritance holds.** A `gemini-3.1-flash-image` follow-up conditioned on a
pro anchor kept the ground, the accent, the typography and the footer strip.
This is what a 3-screen deliverable depends on and it had never been tested in
this register. Cost of a 2-screen brief: **$0.372**, comfortably inside the
$0.60 DoD line.

> **Superseded 2026-08-12 (session 33).** That figure was two screens at three
> anchor candidates. The shipped configuration is now three screens at two
> anchor candidates, measured across five briefs:
>
> | | measured |
> |---|---|
> | 3-screen golden brief (images + QA) | **$0.4415** average, 90–101s |
> | full request through the public path, incl. text stages | **$0.5336**, 2m48s |
> | projected nominal, from `cost_model.py` | $0.4604 |
> | projected worst case (every screen regenerates) | $0.7538 |
>
> Per successful image call, from the ledger: `gemini-3-pro-image` $0.14578
> (n=90), `gemini-3.1-flash-image` $0.06959 (n=25). See
> [`../session33/dod-assessment.md`](../session33/dod-assessment.md).

**The footer strip works.** No corner clipping anywhere in 120 generated images. The
old corner mark is visible clipping the "Schedule Filler" chip in the light
control on the dental sheet.

## What was disproven

**The corner was not what defeated W5.** Session 31 concluded the design
sheet lost because content clipped in the reserved corner, and the roadmap
recorded that as the reason to retry. With the corner gone, W5 scored **8.5
against a 9.2 baseline** — it loses on its own merits. W2 art packs tied at
9.2 (the judge is saturated, so this is "no evidence either way", not a win).

## Four defects the run found, all in prompt text written this session

Each was found by generating, looking, and fixing — none by reasoning.

1. **Small dark text garbles.** The register asked for small, letterspaced,
   low-contrast labels three ways at once. Dental came back with "histarical",
   "No-Shew Rate", "Schedule Fllier"; the light control had none. Fixed with an
   explicit legibility floor.
2. **The app floated on a backdrop.** "Breathing at the outer margins" made
   the model draw the interface as a rounded card with margin around it.
3. **Then it packed the canvas.** The fix for (2) said the interface must
   reach all four edges; the model read that as "fill it", and retail
   regressed to nine panels with two cards both titled "Inventory Status" and
   axis labels reading "Low / Misit / High / High". Separating *background
   reaches the edges* from *content stays sparse* took retail to its best
   score of the run, 9.4.
4. **Prompt scaffolding rendered as UI.** A retail anchor shipped a panel
   titled "RESULT PANEL"; the golden set came back with "HERO ASSET" drawn
   above the salon photo and "Supporting chips" above the AI pills.
   **Instructing the model not to render them did not work** — the fix was to
   stop writing ALL-CAPS headings at all and use sentence-case prose.

Lesson worth keeping: if the model renders your scaffolding, change the
scaffolding. Asking it not to is not a fix. Same shape as the old corner
instruction producing a screen with the word "Logo" drawn in it.

## Scores

Golden set, final settings (`ship`), anchors only:

| brief | old (light) | new (cinematic) |
|---|---|---|
| dental | 8.7 | 8.7 |
| law | 8.0 | 8.7 |
| retail | 8.7 | 8.7 |
| salon | — | 8.1 |
| hedgefund | — | 8.7 |

Session 31's light golden set averaged 8.88 across five briefs; this one
averages 8.58. Given the saturation and the confabulation documented above, I
would not read a 0.3 difference on this scale as meaning anything.

## Spend

Ledger $8.7741 → $16.9806, delta **$8.21** against the $6.07 I quoted (the
owner lifted the cap mid-run). 120 successful image calls across the session.

The overrun is four revision cycles the estimate did not budget for, plus two
full golden-set runs instead of one — the first came back with prompt
scaffolding rendered as UI and had to be redone — plus **$0.29 wasted** on a
cell run with a misplaced `-e` flag, which silently used the v1 briefs and the
wrong database. That last one is the exact trap listed in this session's own
watch-outs document.

Estimating lesson: the $6.07 costed one pass per step. Real prompt work is
iterative, and four of the five findings above only exist *because* of a
revision cycle. Budget image work at roughly 2x a single-pass estimate.

## Open

- **The owner's judgement on the five sheets** in [`sign-off/`](sign-off/).
  Three have both sides; salon and hedgefund have no light control.
- **No working pairwise instrument.** Two judges have now failed the same way.
  Options: a third model, a rubric that forbids text claims (the judge is
  reliable on structure), or accept that ranking two good screens is the
  owner's job and stop paying for it.
- W7 Phase-2 bridge, still gated on sign-off.
