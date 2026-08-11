# Session 32 — the cinematic register

*2026-08-11, branch `consultant-images-pipeline`. **$0 spent** — no image was
generated. Suite 132/132 → 159/159.*

The owner looked at the session-31 sign-off sheets, said they were nice but
wanted "more wow and futuristic… revolves around AI", and showed a reference:
a luxury property configurator — deep emerald ground, gold accent, a photoreal
tower render sitting inside the UI, a three-step block/floor/unit selector.

The honest diagnosis was that **the pipeline was written, in code, to forbid
that image**. Four separate instructions in `_DESIGN_CONSTRAINTS` ruled it
out: a mandated white/light-grey base, a ban on "futuristic … dark themes",
a ban on hero-style composition, and a ban on rendered imagery. No amount of
prompting was going to get there.

Those bans were not arbitrary — the module docstring records that freewritten
prompts produced the dark-glow "AI dashboard" cliché every time. The mistake
was the blast radius: it killed the cliché by killing the entire dark
register, including the disciplined version. This session separates the two.

Owner's rulings this session: **cinematic replaces light everywhere** (not
alongside), and **$0 authorized** — build unfunded, generate nothing.

## What was built

| | |
|---|---|
| **The mark moved to a footer strip** | The corner is free. `WATERMARK_STYLE=footer` grows the canvas ~6% and puts the logo below the interface; the prompt's ~120-word corner reservation is now emitted **only** when the mark actually goes in the corner |
| **A cinematic register** | Deep single-hue ground, exactly one luminous accent, two typographic voices, real depth and light. Every anti-slop guard from the light register is preserved and pinned |
| **A hero asset slot** | `spec.hero` — a photoreal centerpiece rendered inside the content area. Plays to what image models do well instead of spending the whole canvas on dense text, which is what they do worst |
| **Tool screens** | `spec.concept` — a screen can now be a selector / configurator / explorer with real steps, options and a result panel. Before this the spec had no field in which "choose a block, then a floor, then a unit" could be said |
| **An AI module** | `spec.ai` — a recommendation, its reasoning and a confidence read, replacing the "AI Workstream" log. Nobody says "wow" at a log |

The light register is kept **verbatim and pinned**, purely so the funded A/B
has a control arm. Nothing selects it.

## Why the corner mattered so much

Session 31 measured three prompt improvements losing their swap-tested
pairwise — W2 art packs (0–2), W5 design sheet, and one W1 cell — and every
losing run named the same cause: content clipped in the reserved corner.
Anything that makes the model fill the canvas more confidently pushes content
into it.

It was also mis-firing in production. In both session-31 anchors the logo
sits **on top of** the AI card and clips its status text, and in the dental
anchor the model gave up and rendered the literal word "Logo" in the reserved
space — visible at the top of
[`watermark/footer-strip-detail.png`](watermark/footer-strip-detail.png).

[`watermark/footer-on-a-real-anchor.png`](watermark/footer-on-a-real-anchor.png)
is the new strip applied to a real session-31 anchor. It carries two marks —
the old corner one is baked into that artifact, because everything on disk is
watermarked by policy and no unmarked source exists to demo against.

## What you can read without spending anything

[`prompts/`](prompts/) holds the exact bytes the pipeline would send:

- [`demo-tool-cinematic.txt`](prompts/demo-tool-cinematic.txt) — the full
  tool-screen prompt (hero + selection flow + AI module), from a hand-authored
  spec shaped like the owner's reference
- [`dental-cinematic.txt`](prompts/dental-cinematic.txt) — a real frozen
  golden brief in the new register
- [`dental-light-control.txt`](prompts/dental-light-control.txt) — the same
  brief in the old register, the A/B's control
- [`dental-light-to-cinematic.diff`](prompts/dental-light-to-cinematic.diff) —
  exactly what changed

Regenerate any of them for free:

```
python scripts/preview_prompt.py --demo tool
python scripts/preview_prompt.py dental --diff
```

## Two honest limits

**Nothing here has been seen by a model.** Every claim in this document is
about code and prompt text. Whether the cinematic register actually beats the
light one is unmeasured, and the entire session-31 lesson is that built ≠
better — W2 and W5 were both built, both looked right, and both lost.

**The frozen golden briefs predate these fields.** They were frozen under
`ui-spec-v1` and carry no `hero`, `concept` or `ai`, so the funded run's first
step must re-freeze them under `ui-spec-v2`. `GOLDEN_BRIEFS_DIR` now exists so
that writes to a *new* directory: the v1 set is the control arm of the
comparison, and a control overwritten by the change being measured is not a
control. The `--demo tool` preview is hand-authored for exactly this reason
and is labelled as such — it shows what the builder does, not what the spec
stage produces.

## The funded run, pre-scripted

See [`funded-run.md`](funded-run.md). Roughly $18–24 at measured rates for the
full comparison; ~$6 for the cheap version that just answers "is the new look
better".
