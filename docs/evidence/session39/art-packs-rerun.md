# W2 art packs, re-measured — the reason changed, the verdict did not

*Run 2026-08-13, owner-funded. $1.5689 of image generation and judging.
Outcome: `ENABLE_ART_PACKS` stays **off**.*

## Why it was re-run

Session 31 built the packs, measured them and did not adopt them: 0 wins,
2 losses on the swap-tested pairwise judge. But all four judged runs named
the SAME deciding defect — panel text clipped behind the bottom-right logo,
because the pack tells the model to fill the canvas confidently and the
"keep the corner clear" rule sat earlier in the prompt and lost to the
instruction that came last.

That was a verdict about a watermark, not about typography. Session 31 said
so explicitly and called this "the one experiment in the session whose
result is most likely to flip" once W4 moved the mark.

W4 has since landed. `WATERMARK_STYLE` is `footer`: the mark goes in a
strip grown BELOW the interface, covering nothing, and `_CORNER_RESERVE` is
only emitted when the style is `corner` — verified by rendering a prompt,
the reservation text is absent. The confound is gone, so the question was
worth re-asking.

## The measurement

Session 31's two briefs, its image model, one anchor screen per cell,
packs off vs packs on. Same pipeline the customer gets — every cell is
viewable at `/studio/<id>`.

| brief | screen | packs off | packs on | delta |
|---|---|---|---|---|
| dental | Dashboard | **9.2** | 8.7 | −0.5 |
| dental | Schedule | 7.9 | **8.1** | +0.2 |
| retail | Analytics | **7.5** | 4.5 | **−3.0** |
| retail | Dashboard | **8.7** | 7.9 | −0.8 |
| | **mean** | **8.325** | **7.30** | **−1.03** |

Cells: [/studio/148](http://localhost:5173/studio/148) dental nopack
$0.3153 · [/studio/149](http://localhost:5173/studio/149) retail nopack
$0.4683 · [/studio/150](http://localhost:5173/studio/150) dental pack
$0.3155 · [/studio/151](http://localhost:5173/studio/151) retail pack
$0.4698.

**Three of four screens are worse with packs on, and the mean falls a full
point.** Session 31's QA judge had packs winning both cells (8.5 vs 7.5,
9.1 vs 8.7) and only the pairwise pass caught the loss. This time the
absolute scores agree with the pairwise verdict rather than contradicting
it, which is a stronger result than session 31 had.

## What the −3.0 actually is, stated carefully

Request 151's analytics anchor scored 4.5, and the judge listed ten issues.
They are not all attributable to the pack, and the write-up would be wrong
to claim they are:

- *"Not an analytics screen; this is an ordering interface"* and *"no
  analytics charts are present"* — this is the anchor-tool mechanism, which
  makes the anchor a selection flow on every archetype. The packs-off cell
  for the same brief is the same shape and scored 7.5, so this is not the
  difference between the arms.
- *"Duplicate 'Sales Insights' module, one is a title and the other is a
  card"* and *"duplicated 'Order Summary', one is a button and the other is
  a card"* — **real, and visible in the image.** Both are the double-render
  pattern that has cost this pipeline repeatedly.
- *"Many UI elements have a glassmorphism/gradient style, which was
  specifically excluded"* — the pack pushing toward the exact register the
  design constraints exist to forbid.
- *"Branding (logo corner) is encroached by the main content"* — the stale
  corner rule firing again, on a corner nothing reserves. More evidence for
  the judge fix, unrelated to the pack.

So the honest attribution is: one cell of four dropped hard, with two
genuine duplications and a banned visual register among its causes, on
n=1. The direction is consistent across three of four screens and matches
session 31's pairwise verdict. It is not proof that packs cause
duplication; it is a clear absence of the flip that was predicted.

## Verdict

**Keep `ENABLE_ART_PACKS = False`.** The hypothesis being tested — that the
packs lost only to a watermark collision that has since been removed — is
refuted. The collision is gone and they still lose, now on their own
merits: a heavier, more gradient-laden register and more modules to
duplicate.

This closes a question that has been open since session 31 and was
explicitly flagged as the most likely to flip. It did not. The `public-site`
pack written in session 39 stays on disk, unused, along with the rest.

Do not re-run this a third time without a new reason — "the watermark
moved" was the reason, and it has now been spent.

## Cost

| item | cost |
|---|---|
| dental nopack (148) | $0.3153 |
| retail nopack (149) | $0.4683 |
| dental pack (150) | $0.3155 |
| retail pack (151) | $0.4698 |
| **total** | **$1.5689** |

Estimated at $0.90 and then at $1.25; both estimates were wrong because
`--candidates 1` does not prevent a regeneration, so cells produced two and
three images rather than one. The owner authorised the larger scope on the
$1.25 figure and was told the corrected $1.57 before the second arm ran.
**A bake-off cell costs what a customer run costs — about $0.32 to $0.47 —
and should be budgeted that way, not from the candidate count.**
