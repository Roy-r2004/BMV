# The funded run — exact commands, in order

Everything in session 32 is built and pinned but **unmeasured**. This is the
sequence that measures it, written now so the funded session spends its money
on generation rather than on deciding what to generate.

Every figure below is derived from session 31's own per-cell ledger
(`docs/evidence/session31/bakeoff/results.json`), not estimated:
`gemini-3-pro-image` **$0.145/image**, `gemini-3.1-flash-image` **$0.070**,
a QA judgement **$0.001**, a swap-tested pairwise **~$0.02**, and a
text-only brief re-freeze **~$0.01**.

For scale: session 31 ran **21 cells and 66 images** — the entire bake-off
matrix, both experiments and the full golden set — for **$8.55**. This run is
a fraction of that, because the models and the tiering are already settled and
only the register is in question.

| step | what it answers | cost |
|---|---|---|
| 1 | do the new spec fields get filled sensibly? | **$0.05** |
| 2 | **is the new look actually better?** | **$1.82** |
| 3 | is it the hero, the flow, or the register doing the work? | $0.60 |
| 4 | the five sheets for your eye | $2.35 |
| 5 | do W2/W5 win now the corner is free? | $1.25 |
| | **everything** | **$6.07** |

**Steps 1 and 2 are the run.** $1.87 answers the only question that matters,
and if the answer is no, steps 3–5 never happen.

## Before anything: bracket the ledger

```
docker run --rm -v "$PWD:/repo" -w /repo/consultant-service --entrypoint sh bmv-local-api -c \
  'pip install -q -r requirements.txt; python scripts/bakeoff.py --report'
```

The key is shared — attribute only the delta from BMV's own ledger, never the
OpenRouter balance.

## Step 1 — re-freeze the golden briefs under ui-spec-v2  ($0.05)

The frozen set carries no `hero`, `concept` or `ai`; without this step the new
fields are all empty and the run measures the register alone.

```
GOLDEN_BRIEFS_DIR=golden/briefs-v2 python scripts/build_golden.py
```

Writes a **new** directory. `golden/briefs/` stays as the v1 control.

Then read three of them before spending anything further. This is the step
most likely to disappoint: the spec stage has never been asked for a hero
subject or a selection flow, and `ui_spec.j2`'s new instructions are
unvalidated. Specifically check —

- is `hero.subject` concrete and physical, or has it drifted to "modern
  innovation"?
- did any brief pick a tool `concept.kind`, or did every one stay a dashboard?
- is `ai.rationale` ≤ 8 words and defensible for that trade?

If those come back weak, fix `ui_spec.j2` and re-freeze. That is $0.05 a go
and it gates everything downstream — image spend on bad specs measures
nothing, however small.

## Step 2 — the register A/B  ($1.82: 12 pro images, 3 swap-tested pairwise)

Three briefs, two conditions, anchor only (`--screens 1`), 2 candidates each.
The judge stays fixed. Register is the only thing that varies.

```
for b in dental law retail; do
  GOLDEN_BRIEFS_DIR=golden/briefs-v2 python scripts/bakeoff.py --brief $b \
    --model google/gemini-3-pro-image --screens 1 --candidates 2 \
    --register light --watermark corner
  GOLDEN_BRIEFS_DIR=golden/briefs-v2 python scripts/bakeoff.py --brief $b \
    --model google/gemini-3-pro-image --screens 1 --candidates 2 \
    --register cinematic --watermark footer
done
```

`--register` auto-appends to the cell label, so these land as `…__light` and
`…__cinematic` — no `--label` needed, and no chance of the two sharing an
output directory.

Note the control pairs `light` with `corner`: that is the *shipped* old
pipeline, which is what the owner is actually comparing against. It does mean
this cell varies two things at once. If the cinematic arm wins, a third cell
(`--register light --watermark footer`) separates "the dark register won" from
"freeing the corner won" — $0.87, worth it only if the answer changes a
decision.

Then, swap-tested pairwise. Both sides ran on the same anchor model, so
`--a`/`--b` are the same model and the *labels* are what distinguish them:

```
python scripts/pairwise_run.py \
  --a google/gemini-3-pro-image --a-label light \
  --b google/gemini-3-pro-image --b-label cinematic \
  --briefs dental law retail
```

**Adopt on ≥ 2 of 3 swap-surviving wins. Revert on fewer.** W2 and W5 were
both built, both looked right, and both lost — this is the whole reason the
light register is still in the tree.

## Step 3 — hero and tool screens, isolated  ($0.60)

Only if step 2 adopts. These are separate claims and cost little to separate:

```
python scripts/bakeoff.py --brief retail --register cinematic --screens 1 --candidates 2 \
  --model google/gemini-3-pro-image --label no-hero      # with ENABLE_HERO_ASSET=0
python scripts/bakeoff.py --brief retail --register cinematic --screens 1 --candidates 2 \
  --model google/gemini-3-pro-image --label no-tool      # with ENABLE_TOOL_SCREENS=0
```

The specific risk to look for: a hero asset that eats the canvas and pushes
the UI text into garbling. That failure would show up as a text-gate rejection,
not as a low aesthetic score — check `text_truth` in the saved metadata, not
just `qa_score`.

## Step 4 — full golden set + owner sheets  ($2.35)

Five briefs, 2 screens, tiered pro anchor + flash follow-ups, the shipping
configuration:

```
for b in dental law retail salon hedgefund; do
  GOLDEN_BRIEFS_DIR=golden/briefs-v2 python scripts/bakeoff.py --brief $b \
    --anchor-model google/gemini-3-pro-image \
    --followup-model google/gemini-3.1-flash-image --screens 2
done
python scripts/side_by_side.py --old-label light --new-label cinematic \
  --briefs dental law retail salon hedgefund
```

Then **stop for the owner's eye**. The pairwise criterion is theirs.

## Step 5 — re-run the two experiments the corner defeated  ($1.25)

W2 art packs and W5 design sheet are built, versioned and pinned, and both
lost specifically to corner clipping. With the corner free they deserve one
honest re-run each — one env var apiece, `ENABLE_ART_PACKS` and
`USE_DESIGN_SHEET`.

## Watch-outs, all of them learned the hard way

- **Per-cell `UPLOADS_DIR` and an explicit `-e DATABASE_URL`.** The image's
  baked-in `DATABASE_URL` beats `.env`, so every ephemeral container restarts
  request ids at 1 and cells overwrite each other. Cost: one lost cell, $0.353.
- **Mount the repo root** (`-v "$PWD:/repo"`), not `consultant-service` — the
  logo lives at `frontend/public/logo.png` and a service-only mount makes the
  watermark silently no-op.
- **The pairwise judge is `claude-sonnet-5`, not flash.** Flash answered "A"
  in 6 of 6 runs across three briefs, reading position rather than pixels.
- **Trust judges on structure, never on spelling.** The pairwise judge has
  invented misspellings that are not in the images. Text truth is decided in
  code by `text_truth.py`, and only there.
- **The register belongs in the cell key.** `--register` now auto-appends to
  the label so two cells cannot share an output directory.
