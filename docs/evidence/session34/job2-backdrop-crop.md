# JOB 2 — the floating backdrop, cropped instead of forbidden

*2026-08-12, session 34. $0 — deterministic PIL, no model calls.*

The prompt forbids the interface-as-a-card twice and the model drew it
anyway on 5 of 15 session-33 screens. This stops asking:
`_floating_backdrop_bbox` in `app/pipeline/images.py`, applied to every
candidate **before QA** (the judge scores what would ship, and a screen
that stops floating here needs no regeneration for having floated).
`ENABLE_BACKDROP_CROP`, default on, one env var to kill.

## The detector

The bounding box of LOCAL-contrast pixels (image minus its own blur —
text and hairlines survive, flat color and smooth gradients cancel), then
four guards, each refusing independently, because a false positive that
crops real UI is worse than any missed backdrop:

1. **margins on all four sides** — full-bleed touches an edge;
2. **interior ≥ 55% of the frame each way** — screenshot, not thumbnail;
3. **margin symmetry ≤ 2.5:1** — a floating card is drawn centered
   (salon: 21–26px all round); app padding is not (law: 18px top under
   the nav vs 61px bottom);
4. **ring vs the interface's own ground ≥ 40** (Euclidean RGB) — ground
   sampled from FLAT pixels of a frame band just inside the box edge,
   refusing when too few flat pixels exist to establish it.

Crop lands 3px inside the contrast boundary so the card's soft edge blend
goes with the backdrop.

## Two false positives were built and killed on the way

Both are now pinned as synthetic shapes in `tests/test_backdrop_crop.py`:

- **v1** compared the ring to a thin unmasked band at the box edge; a 3px
  shift in where the band sat let PANEL EDGES dominate it and flipped two
  full-bleed law screens into crops.
- **v2** compared the ring to flat pixels over the whole interior; the law
  screens' large smooth photograph dragged the mean and flipped all three.
  The symmetry guard (3) plus padding-frame ground (4) is what survived.

That the law screens are the hard case is the finding: a cinematic
full-bleed screen with generous padding *looks* like a float to every
naive detector.

## Validation on every real screen on disk

[`validate_backdrop_crop.py`](validate_backdrop_crop.py), 28 images
(all s33-full screens + their candidate pools + the s34-2k run + live
request 68):

| verdict | screens |
|---|---|
| **CROP (3)** | salon 72 dashboard / schedule / analytics — the pink-backdrop run, margins 21–26px, cropped 1376×768 → ~1316×714. Verified by eye: interface intact to the corner tips ([`job2-salon-dashboard-cropped.png`](job2-salon-dashboard-cropped.png), [`job2-crop-corners-6x.png`](job2-crop-corners-6x.png)) |
| **keep (25)** | everything else byte-identical — law (the false-positive near-miss, [`job2-law-analytics-original-half.png`](job2-law-analytics-original-half.png)), dental, retail, hedgefund, all 2K screens, request 68 |

## What it deliberately does NOT fix, and where that goes

- **retail 71 tone-on-tone floats** (2): the card edge is so low-contrast
  the content box lands inside the card; a crop would shave card padding.
  Guard 4 refuses. → JOB 3's checker.
- **hedgefund 73 clipped cards**: content touches the canvas edge — no
  backdrop ring exists, cropping cannot fix a card the model already cut
  off. Guard 1 refuses. → JOB 3's checker.

Score on the session-33 defect list: the 3 high-contrast floats die
deterministically; the 3 that cropping cannot fix losslessly are left,
loudly, to the defect check.
