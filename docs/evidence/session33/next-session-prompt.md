# Kickoff — make the demo good enough to send, in under three minutes

Work happens ONLY on branch `consultant-images-pipeline` (local, 31 commits
ahead of origin, suite 228/228, tree clean). **Main is not to be touched.**

Read first, in order: `docs/evidence/session33/README.md`,
`docs/evidence/session33/dod-assessment.md`, then the gallery of every screen
session 33 produced, with its flaws annotated:
https://claude.ai/code/artifact/fc6b481a-ffd6-4158-9558-1316dd1079b7

## The owner's framing, which sets the priority order

> "We're here now only for an MVP. I want the customer to have a full workable
> demo in just a couple of minutes from a prompt. After we accomplish that we
> can work on the other small issues."

Two things follow, and they are the whole brief:

**The clock is already met and must not be lost.** A real request through the
public intake takes **2m48s** and costs **$0.5336**. Every job below adds
work to that path. Anything that pushes a request past 3 minutes has failed
even if it fixes what it set out to fix — parallelise it, cap it, or don't
ship it.

**"Workable" is the gap, not "fast" and not "pretty."** The screens already
look expensive; the owner signed off on the register. 13 of 15 carry a small
visible flaw. A prospect who spots "Cilents" in a menu stops believing the
rest of the screen, and that is the whole product.

So: fix the flaw classes that cost credibility, in the order of how much
credibility they cost per pound of engineering. Leave the rest.

## Settled — do not re-litigate

- **The cinematic register ships.** Owner signed off 2026-08-11. No
  art-direction work this session.
- **The QA gate is 8, enforced in code** (`9dbc186`). It was never enforced
  before — the number went into the judge's prompt and the judge's own
  approval was taken at face value. Pinned against `DOD_MIN_SHIPPED_SCORE`.
- **The pairwise judge is KEPT** on the v2 rubric: text claims forbidden,
  structure only, tie made a real answer. It survived the order swap and got
  a known pair right. Two models had failed v1. Do not rewrite it again
  without a measured reason.
- **`DASHBOARD_CANDIDATES` is 2.** Cost knob, owner's call.
- Everything settled in sessions 31–33 stands: watermark on every byte under
  `/uploads`; presentation glamour composited in PIL, never asked of the image
  model; text truth decided in code, never by a judge; the QA judge held FIXED
  while generators vary.

## The diagnosis this session is acting on

Every flaw class traces to one thing: **we ask one model to invent a beautiful
room and to typeset exact facts inside it.** It is superb at the first and
unreliable at the second. Every failure is the second job — exact strings,
exact numbers, exactly-one-of-each-panel.

This codebase already solved this once and stopped halfway. The logo, the
browser frame, the shadow are not drawn by the model; they are composited in
Python afterwards, because asking the model for them garbled the screen (W4).
Nobody applied the same split to the facts *inside* the frame.

## JOB 1 — The resolution probe. Do this first (~$0.40, half a day at most)

**The cheapest thing that might kill the worst flaw class.** Seven of the
eighteen screens have collapsed letterforms: "Cilents", "Portfollo", "10:1S",
"beoking", "Highiights", "SLB" for "5LB". None of these is a spelling
mistake. They are ten-pixel glyphs where `i`/`l`/`1` and `S`/`5` become the
same shape.

Images come back at roughly **1408×768** before the watermark strip. If the
model can be asked for a larger canvas, every one of those glyphs gets more
pixels and the class may simply go away — for near-zero engineering.

1. Find out what output sizes `google/gemini-3-pro-image` and
   `google/gemini-3.1-flash-image` actually honour through OpenRouter. Check
   the API surface before spending: aspect/size hints, `image_config`,
   whatever the current shape is. Read the docs, don't guess from our wrapper.
2. If a larger canvas is available, generate the **same** golden brief at both
   sizes and compare the small text at 8× zoom. One brief, both sizes, that
   is the whole experiment.
3. If it works: adopt it, check the cost delta (output tokens scale with
   pixels — this may not be free), re-check the $0.60 line with
   `cost_model.py`, and pin it.
4. If the model will not go bigger: say so plainly and move to JOB 3, which
   is then the only route for menu labels.

**Do not skip to the clever fix without running this.** It is $0.40 and it
either removes a whole class or tells you the class needs real work.

## JOB 2 — Crop the floating backdrop (free, deterministic, ~1 hour)

Five screens are drawn as a rounded card sitting on a background, sometimes
with cards hanging outside the app's own edge. The prompt forbids this in two
places and the model does it anyway; session 32 "fixed" it twice.

Stop asking. **Detect it and cut it off in PIL**, next to the watermark code:
a uniform, low-variance border ring around a high-variance interior is a
backdrop, and cropping to the interior is unambiguous. Where a card hangs
outside the frame, cropping to the card's bounding box is still right.

Be conservative — a false positive that crops real UI is much worse than a
missed backdrop. Pin both directions: a full-bleed screenshot must come
through byte-identical, a floating one must lose its margin.

## JOB 3 — Wire in the defect check that already works (~$1, and watch the clock)

Session 33's per-screen sweep found 13 of 15 screens defective, including the
duplicated panels, the invented panel titles and the "Action" button — and
it root-caused one class nobody had diagnosed. It is not connected to
anything.

**The structure is what made it reliable, so keep the structure:** one
inspector per screen reports countable structural defects, then each claim
goes to a separate verifier told to refute it and defaulting to refuted when
uncertain. That two-stage shape is the same thing that makes the pairwise
judge trustworthy, and single-stage judging is exactly what has failed here
three times.

1. Build it as a per-screen check in the request path, on the flash model.
   Budget: it must cost cents, not tens of cents.
2. On a confirmed defect, reject the candidate — the existing regeneration
   path already handles the rest.
3. **Guard the clock.** Screens are already generated in parallel; the check
   must be too, and the regeneration budget stays at one. If a request cannot
   stay under three minutes with this on, ship it off by default and say so.
4. Forbid text claims in the inspector's rubric, exactly as the pairwise
   rubric does. Text truth is `text_truth.py`'s job and nothing else's.

Measure it honestly on the golden set: how many real defects caught, how many
false rejections bought, what it did to wall clock and cost.

## JOB 4 — Draw the charts in code (the structural one — only if 1–3 land)

Four screens have charts whose plotted points contradict their own axis: a
marker sitting on the 2,000 line labelled 5,800, a scale stepping 10, 10, 20,
20 at equal spacing. The model draws a plausible chart and then writes our
numbers onto it. It is not doing arithmetic and will not start.

We already have the exact numbers in the spec. **Composite the chart in PIL**
over the region the model leaves for it, the same way W4 composites the
browser chrome.

The honest risk: done badly this looks pasted on, and the register is the one
thing the owner has already approved. So — one archetype, one chart, side by
side against the model-drawn version, and the owner's eye decides. Do not roll
it out on five briefs before it has been looked at once.

If JOBS 1–3 consume the session, **stop here and leave this for the next one**.
A half-built compositor that makes screens look cheap is worse than four
charts with wrong axes.

## What is explicitly NOT this session's work

Leave these; they are the "small issues" the owner named:

- unlabelled arrows and toggles the model scatters on hero photographs
- the `business_name` never appearing on screen (by design — the gate's
  documented relaxation; the wordmark is the product name)
- non-brand-critical misspellings inside body copy ("viabllity")
- the remaining ALL-CAPS `AI WORKSTREAM` heading on the fallback path
- W2 art packs, W5 design sheet — both measured, both lost, both off

## Gates on every job

- Suite green in the container:
  `docker run --rm -v "$PWD:/repo" -w /repo/consultant-service --entrypoint sh bmv-consultant-py -c 'python -m pytest tests/ -q'`
  (`bmv-consultant-py` is a local image = `bmv-local-api` + the service's
  requirements; rebuild with `/tmp/Dockerfile.consultant` if it is gone.)
- Every behavior change lands with a pin. No silent caps.
- Bracket every funded step against the service ledger, before and after.
- **Re-measure the whole golden set before claiming any class is fixed.**
  Session 33 fixed five classes, re-ran two briefs, and both re-runs produced
  new defects. One brief is not evidence.
- Host python is externally managed — run through the container.
- `OPENROUTER_API_KEY` is in `consultant-service/.env`. Never commit it.

## Traps — each of these has cost real money or real time

- **Docker `-e` flags go BEFORE the image name.** One placed after was passed
  to the shell instead; cost $0.29 and a wasted comparison.
- **Never run two bake-off batches concurrently.** `results.json` is rewritten
  wholesale from an in-memory list loaded at start.
- **Mount the repo root** (`-v "$PWD:/repo"`), not `consultant-service` — the
  logo lives at `frontend/public/logo.png` and a service-only mount makes the
  watermark silently no-op.
- **Pass `-e DATABASE_URL` explicitly.** The image bakes in its own.
- **Use `GOLDEN_BRIEFS_DIR=golden/briefs-v2`.** `golden/briefs/` is the frozen
  v1 control arm.
- **NEW: SQLite in WAL mode over a bind mount is not readable by a second
  process.** A ledger bracket taken while the service is running shows the
  database as it was before the run — which looks exactly like a run that
  spent nothing. Read through `/api/requests/{id}/admin`, or after a clean
  `docker stop`. Ephemeral bake-off containers are fine; they exit and
  checkpoint.
- **If the model renders your scaffolding, change the scaffolding.** Four
  shapes of this were found in session 33 — a field label, a section name, a
  quotation mark used as a delimiter, and a descriptive adjective. All four
  are the same mistake: *describing* a thing next to the place it should be
  drawn. Name the string or ask for nothing.
- **Trust judges on structure, never on spelling.** And zoom in before
  believing a text complaint — or dismissing one. Both have happened.

## Definition of done — state entering this session

| # | line | state |
|---|---|---|
| 1 | brand-critical text 100% | **FAILS** — "Cilents" shipped, the gate passed it. JOB 1 is the cheap shot at this |
| 2 | no screen < 8, and no structural defect | **FAILS** on both clauses. Gate now 8 and enforced; JOBS 2–4 are the defect clause |
| 3 | beats the old default, owner's eye | **PASSES** — signed off 2026-08-11 |
| 4 | ≤ $0.60/request, ≤ 3 min | **PASSES** — $0.5336, 2m48s. Every job this session spends against this line |
| 5 | zero unbranded bytes under /uploads | **PASSES**, pinned |

**Two unmeasured things carried in from session 33**, both worth an early
cheap answer:

1. Does the gate at 8 actually lift a 7.5 above 8, or just spend $0.10 to ship
   the same screen? One golden-set run answers it, and JOB 1 needs a golden-set
   run anyway — fold them together.
2. Does the magnified-band text-truth fix catch a real misspelling? Nothing has
   shown it catching one; the re-run did not reproduce the failure.

## Spend

Ceiling **$15**, ledger-attributed, the key is shared — bracket every funded
step against `ai_usage_events` and attribute only the delta. Never read the
account balance.

Rough plan: JOB 1 ~$0.40, JOB 2 $0, JOB 3 ~$1, a full golden-set re-measure
~$2.30. Budget image work at roughly 2× a single-pass estimate — session 32
learned that the hard way and session 33 confirmed it.
