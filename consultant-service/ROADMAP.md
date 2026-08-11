# Phase 1 — the image-demo pipeline, made astonishing

*Written 2026-08-10, on `consultant-images-pipeline` freshly updated from
main (merge `7c5eae4`, hardening `29c28ef`). Owner reframe: image demos are
**Phase 1 of BMV** — the thing a lead sees first, at a fraction of a full
build — and the React demo website is **Phase 2**. This document is the plan
for making Phase 1's images state of the art.*

## The reframe, in numbers

| | Phase 1 — image demo | Phase 2 — React demo site |
|---|---|---|
| What the client gets | 3–4 "screenshots of their future product" + a branded deck | A living clickable site |
| Marginal cost | ~7–8 images ≈ **$0.10–0.25** today (measured rail below) | **$0.35–0.40** per generation (ledger, runs 167–170) |
| Wall clock | ~1–2 min | ~9–10 min |
| Failure surface | One stage, one artifact type | Full codegen + build + critic loop |

The funnel: astonish cheaply → close → upgrade the same brief into Phase 2.
The two pipelines already live in one repo and one container rail; W7 makes
the handoff literal.

## Where the pipeline stands (verified today)

Five commits reviewed line-by-line; suite now **27/27** after three
hardening fixes (unbranded candidate leak under the static mount, a dead
cost knob, a filename collision — each pinned by a test). What it already
does *well*: composition explored as three genuinely different
art-direction prompts (not re-rolls), vision-QA selection with one bounded
regeneration, anchor-as-style-reference for cross-screen consistency,
PIL-composited watermark (never model-drawn), usage ledgered per call.

## Model strategy — answering "isn't ChatGPT best?"

Facts first (read from our OpenRouter key today, 11 image-output models):

| model | in $/M | out $/M | note |
|---|---|---|---|
| `google/gemini-3-pro-image` | 2.00 | 12.00 | current default |
| `openai/gpt-5.4-image-2` | 8.00 | 15.00 | newest OpenAI image model — **on our key** |
| `openai/gpt-5-image` / `-mini` | 10.00 / 2.50 | 10.00 / 2.00 | previous OpenAI tier |
| `google/gemini-3.1-flash-image` | 0.50 | 3.00 | new cheap tier |
| `google/gemini-2.5-flash-image` | 0.30 | 2.50 | oldest, cheapest |

The honest read: OpenAI's image models are a top-two contender and now
testable on our own rail — the instinct isn't wrong. But this product's
hardest requirement is **dense, legible, *correct* UI microtext** (KPI
labels, table rows, chart axes, the client's business name), and the
Gemini pro-image class is the reigning reference for exact text rendering
in UI-style images. Photorealistic atmosphere — where OpenAI models often
lead — matters mostly for W4's backdrops, which we composite
deterministically anyway.

So we don't guess; **model becomes a first-class generation variable**
(exactly what the code already did for composition) and a ~$3–5 bake-off
decides per archetype. Plausible outcome worth designing for: *per-role
tiering* — pro-class model for the anchor, flash-class for follow-up
screens conditioned on the anchor — halving cost with little visible loss.

## Status after session 31 (2026-08-11)

| | | |
|---|---|---|
| W0 Hardening | **DONE** | `29c28ef` |
| W1 Bake-off | **DONE** | pro anchor + flash follow-ups, per archetype; gpt-5.4 eliminated |
| W2 Art packs | **BUILT, NOT ADOPTED** | lost the A/B 0-2; ships behind `ENABLE_ART_PACKS=false` |
| W3 Text truth | **DONE, ON** | 10/10 golden screens passed |
| W4 Compositing | **DONE, ON** | hero + 2 detail crops per screen; deck rebuilt on them |
| W5 Design sheet | **BUILT, NOT ADOPTED** | lost the swap-tested pairwise; `USE_DESIGN_SHEET=false` |
| W6 Delivery polish | **DONE** | `/admin` cost view, composites in `/preview` |
| W7 Phase-2 bridge | **NOT STARTED** | gated on the owner's sign-off |

**Phase 1 is not declared shippable.** DoD line 2 fails on measurement and
line 3 is waiting on the owner's eye — see
`docs/evidence/session31/dod-assessment.md` and the sheets in
`docs/evidence/session31/sign-off/`.

The single highest-value next change, from three experiments that all lost
the same way: brand the raw screenshot with a footer strip rather than a
corner mark, so the prompt no longer has to reserve the bottom-right
corner — then re-run W2 and W5, which are built and one env var away.

## Workstreams

**W0 — Hardening. DONE** (`29c28ef`): watermark on every byte under
`/uploads`, cost knob re-wired, filename collision fixed. 27/27.

**W1 — The bake-off (first funded step, ~$3–5 ledger-bracketed).**
`IMAGE_MODEL` per call; matrix = 3 golden briefs × 3 archetypes ×
{gemini-3-pro, gpt-5.4-image-2, gemini-3.1-flash} with the QA judge
**held fixed** (never vary judge and generator together). Score with the
existing rubric + one pairwise pass (judges are better at "which of these
two" than absolute scores). Deliverables: per-archetype default table,
measured per-image cost from our own ledger, evidence doc in the session
style. Includes one tiering trial (pro anchor + flash follow-ups).

**W2 — Art-direction packs.** Today's prompts carry data + brand color;
astonishing needs a *design system per archetype*: named type pairing,
spacing/density rules, chart styling, light/dark stance, exact hex palette
derived from the brand color (the Phase-3 taste work — five personalities,
candidate sheet — maps onto consultant archetypes almost 1:1). Ship as a
versioned prompt-pack table; A/B against current prompts through the same
QA gate.

**W3 — Text truth (the credibility gate).** The spec already contains the
ground truth (business name, product name, nav labels, KPI values). Add a
transcribe-and-diff QA step: the vision judge returns all visible text;
brand-critical strings must match **exactly** or the screen regenerates —
a misspelled client name is an auto-reject regardless of aesthetic score.
This is the single biggest de-risker for client-facing use, and it's
nearly free (the judge already looks at every image).

**W4 — Presentation compositing (deterministic glamour).** Split "UI
truth" from "presentation": the model renders flat, straight-on UI (its
strength); PIL composites the astonishment — browser chrome, device
frame, brand-gradient backdrop, soft shadow, hero crop + detail crops.
Never ask the model for perspective mockups; it garbles the UI. Upgrades
the pptx export into a branded pitch deck. $0 marginal cost, pure Python.

**W5 — Consistency experiment.** Keep anchor-as-reference; trial the
design-system-sheet technique (generate one style-board image first,
condition every screen on it). Judged by the same fixed QA; adopted only
if it wins.

**W6 — Delivery polish.** ConsultantExperience page and deck as the sales
artifact; candidate hygiene and watermark policy (done); per-request cost
line surfaced in admin.

**W7 — The Phase-2 bridge.** A `blueprint → BMV brief` mapper so a closed
Phase-1 client upgrades into the React pipeline without re-intake — same
name, industry, palette, and the already-agreed screen inventory. This is
the strategic glue; it costs one mapping module plus tests.

## What "astonishing" means (the DoD)

1. **Brand-critical text accuracy 100%** on shipped screens (W3 gate).
2. Every shipped screen QA ≥ 8/10; anchors ≥ 9 on ≥ 4 of 5 golden briefs.
3. Pairwise: new pipeline beats today's output on ≥ 4 of 5 briefs
   (judge + owner eye — final call is the owner's, like Stage C).
4. Cost ≤ **$0.60/request** at pro-anchor + flash-follow-up tiering;
   wall ≤ 3 min.
5. Zero unbranded bytes reachable under `/uploads` (pinned, W0).

## Sequencing

| session | spend | lands |
|---|---|---|
| A | ~$3–5 | W1 bake-off + evidence + per-archetype defaults |
| B | ~$1 | W2 packs + W3 text-truth gate (built $0, one funded confirm) |
| C | $0 | W4 compositing + deck, W6 polish |
| D | ~$2 | W5 experiment + full golden-set eval → owner sign-off |
| E | — | W7 bridge; Phase 1 declared shippable |

Guardrails throughout, inherited from the BMV culture: every funded step
bracketed against the ledger (shared key — attribute the delta, no leak
alarms), every behavior change lands with a pin, no silent caps, evidence
doc per session.
