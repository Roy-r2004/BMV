# W2 — art-direction packs: built, measured, NOT adopted

*Run 2026-08-11. Cost $0.91 of image generation plus ~$0.08 of judging.
Outcome: the packs ship disabled (`ENABLE_ART_PACKS=false`).*

## What was built

A per-archetype design system appended to the image prompt
(`app/pipeline/art_packs.py`, version `art-pack-v1`) — one pack for each of
the five archetypes, each naming a type pairing, a density/spacing stance,
a chart treatment and the "signature" that should make that archetype's
screens their own kind of product. Plus `derive_palette()`: fourteen exact
hex values computed from the client's brand color with plain HLS
arithmetic, including darkening a too-bright brand color until it clears
3:1 contrast against white.

## The A/B

One composition variant, one anchor screen, `gemini-3-pro-image`, packs on
vs packs off, on two archetypes. Judged per-image by the fixed QA judge and
head-to-head by the swap-tested pairwise judge.

| brief | archetype | QA with pack | QA without | pairwise (both orders) |
|---|---|---|---|---|
| dental | operations | **8.5** | 7.5 | **without** |
| retail | analytics | **9.1** | 8.7 | **without** |

The two instruments disagree, and the pairwise one is the one that
discriminates — absolute scores in the 8s were exactly what the pairwise
pass was added to see past. **0 wins, 2 losses. Not adopted.**

All four judged runs named the same deciding defect: with the pack, the AI
Workstream panel's text is clipped behind the composited bottom-right
logo. The pack tells the model to fill the canvas more confidently, and the
"keep the bottom-right corner clear" rule — which lives earlier in the
prompt — loses to the instruction that comes last.

That is worth stating precisely, because it is not a verdict on
typography or density: **the pack is losing to a watermark-placement
constraint, not to the baseline's design.** W4 changes where the watermark
lives (composited onto a frame rather than painted over the UI). The
comparison should be re-run after that, and this is the one experiment in
the session whose result is most likely to flip.

## The hex leak — measured twice, and why the palette is now prose

The first version of the pack put the derived palette in the prompt as a
list of hex values. The model rendered them **as UI text**:

1. `positive: #059669` etc. → the screenshot showed "#059669" as a green
   pill beside the Total Sales KPI, and again as an AI-Workstream status
   chip. (`bakeoff/retail-anchor-pack-hexleak-1.png`)
2. Rewritten so every entry named the role a color plays ("Negative delta
   text and alert pills — #DC2626"), with an explicit "no hex code may
   appear as visible text" prohibition stated twice → the screenshot showed
   "#DC2626" as the **Risk level** pill. Naming the UI element a color
   belongs to told the model exactly where to write it.
   (`bakeoff/retail-anchor-pack-hexleak-2.png`)

An image model renders strings it is given; a fourteen-line block of them
is an invitation whatever the surrounding instruction says. The prompt has
always carried exactly one hex — the brand color, in the BRANDING block —
and that one has never leaked.

So the palette now reaches the prompt as prose ("the brand color owns the
active nav item, the focal metric...; a very pale tint of it fills the
selected row...") while `derive_palette()` keeps the exact values for the
consumers that can use them safely: W4's compositor and the deck. Pinned:
no pack section may contain a hex code, for any archetype.

## Also fixed while measuring

The pack originally shipped its chart treatment to every screen. A
schedule or kanban screen handed "one area chart with a soft vertical
gradient" is being invited to invent a module the spec never asked for —
precisely what the prompt spends a paragraph forbidding. The chart section
now ships only when the screen actually has chart data.

## Limits

- Two archetypes, one anchor each, one composition variant, one sample.
  This is a directional result, not a measurement of the packs' ceiling.
- The pack was tested as a whole. Typography, density, chart treatment and
  color stance were not separated, so "the pack lost" does not tell us
  which part is carrying the loss — beyond the corner encroachment, which
  the judges named directly.
- The packs for `scheduling-dashboard` and `pipeline-dashboard` were
  written but never rendered — no golden brief lands on those archetypes.

## Status

Built, versioned, pinned (18 tests), and **off by default**. Enabling it is
one env var once the corner constraint changes.
