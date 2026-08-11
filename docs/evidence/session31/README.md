# Session 31 — Phase 1 image pipeline

*2026-08-11, branch `consultant-images-pipeline`. Spend ~$9.17 of a $10
ceiling. Suite 27/27 → 132/132.*

## Read in this order

| doc | what it settles |
|---|---|
| [`dod-assessment.md`](dod-assessment.md) | the five DoD lines, measured. 3 hold, 1 fails, 1 waits on the owner |
| [`images-bakeoff.md`](images-bakeoff.md) | W1: which model, per archetype, and what an image really costs |
| [`text-truth-gate.md`](text-truth-gate.md) | W3: transcribe-and-diff, and every false rejection that shaped it |
| [`art-packs-ab.md`](art-packs-ab.md) | W2: built, measured, not adopted — and the hex leak, twice |
| [`w4-compositing.md`](w4-compositing.md) | W4: the composites and the deck, and what looking at it changed |

Artifacts: [`sign-off/`](sign-off/) (the owner's sheets),
[`bakeoff/`](bakeoff/) (anchors, raw results, both hex leaks, the W5 style
board), [`deck/`](deck/) (sample pptx + rendered slides).

## What shipped on by default

Per-archetype tiering (`gemini-3-pro-image` anchor, `gemini-3.1-flash-image`
follow-ups), the text-truth gate, presentation compositing, the `/admin`
cost view. `model` is now a per-call generation variable, so the ledger,
the logs and the saved metadata all name the model that actually ran.

## What shipped off

Art packs (W2) and design-sheet conditioning (W5). Both are complete,
versioned and pinned; both lost their comparison and neither was adopted on
the strength of having been built.

## Two defects the measurements paid for

1. **An upstream 429 arrives as HTTP 200** with truncated content. Two of
   six ui_spec calls were counted as successes and silently fell back to
   generic specs — a lead would have seen a demo about "Alex" and "Bookings
   Today". Found while freezing the golden briefs; fixed in `provider`.
2. **A false positive in the text-truth gate**: a correct product wordmark
   read as a misspelling of the business name, rejecting a good screen and
   spending a regeneration that pushed that request 60% over its siblings.
   Found by the golden-set run, not by any test.

## Two things about instruments

The pairwise judge had to be changed before it measured anything: with
`gemini-2.5-flash` it answered "A" in six of six runs across three briefs,
reading position rather than pixels. Every comparison in this session is
run in both orders and counted only if it survives the swap.

And the judges confabulate about text specifically. The pairwise judge
reported two misspellings that do not exist in the images. Its structural
findings held up under inspection every time; its spelling findings did
not. That is the entire argument for W3 doing that check in code.

## Waiting on the owner

The five sheets in [`sign-off/`](sign-off/) — current default beside new
pipeline, no scores, no commentary. Three briefs have both sides; salon and
hedgefund have no current-default run to compare against, so they cannot
count toward the DoD's 4-of-5.
