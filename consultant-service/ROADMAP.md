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
`docs/evidence/session31/sign-off/`. (Line 3 was signed off on 2026-08-11;
line 2 still fails as of session 33, on both of its clauses.)

## Status after session 32 (2026-08-11) — the cinematic register

The owner saw the sign-off sheets, called them nice, and asked for something
modern, futuristic and AI-forward, with a luxury property configurator as the
reference. The pipeline could not produce that image: `_DESIGN_CONSTRAINTS`
mandated a light base and banned dark themes, hero composition and rendered
imagery. Session 32 rebuilt the register and ran the funded comparison.

| | | |
|---|---|---|
| W8 Footer-strip mark | **DONE, ON** | no corner clipping in 120 images; the corner reservation is gone from the prompt |
| W9 Cinematic register | **DONE, ON — OWNER SIGNED OFF 2026-08-11** | chosen on the owner's eye; no automated instrument could rank it, which is why that line was always theirs |
| W10 Hero asset | **DONE, ON** | 6/6 briefs produced concrete photographable subjects |
| W11 Tool screens | **DONE, ON** | 6/6 tool anchors once `anchor_tool` became a top-level required field |
| W12 AI module | **DONE, ON** | recommendation + reasoning + confidence, replacing the log |
| W2 Art packs | **STILL OFF** | re-run with the corner free: tied at 9.2 on a saturated judge — no evidence either way |
| W5 Design sheet | **CLOSED, OFF** | re-run with the corner free: 8.5 vs 9.2. Session 31 blamed the corner; that was wrong, it loses on its own merits |
| W7 Phase-2 bridge | **DONE (session 33)** | `phase2_bridge.py` + 15 tests |

**The measurement problem is the finding.** The per-image judge scored full
cinematic, hero-off, tool-off and packs-on all at exactly 9.2 — it is a defect
detector, not a quality meter. The pairwise judge (`claude-sonnet-5`) picked
the first-presented image 6 of 6 and fabricated text failures to justify it,
contradicted by the text-truth gate passing all 8 files. That is the second
judge to fail this way, and the order-swap protocol caught it both times.

DoD line 3 therefore rested entirely on the owner's eye, as it was always
written to — **and they signed off on 2026-08-11: the cinematic register
ships.** Line 2 was amended the same day (see the DoD below). Sheets:
`docs/evidence/session32/sign-off/`. Full write-up:
`docs/evidence/session32/results.md`. The closing session's brief:
`docs/evidence/session32/next-session-prompt.md`.

Cost holds: a 2-screen brief with tiering measured **$0.372**, inside the
$0.60 DoD line, and flash follow-ups inherit the register from a pro anchor.
(Superseded by session 33's measurement: **$0.4415** for a 3-screen brief,
**$0.5336** for a full request through the public path.)

## Status after session 33 (2026-08-12) — measured on the real thing

The closing session ran the pipeline the way a client does — one request
through the public intake, then the first complete 5-brief x 3-screen golden
set in this register — and **Phase 1 is not shippable.** Two DoD lines fail,
and both failures were invisible to every measurement taken before, because
every measurement before went through `scripts/bakeoff.py` on frozen
single-screen briefs.

| | | |
|---|---|---|
| W7 Phase-2 bridge | **DONE** | `phase2_bridge.py` + 15 tests; blueprint prose deliberately does not cross |
| W4 Compositing | **DONE, ON** | deck rebuilt, all 7 slides read; two proportion defects fixed |
| Cost knob | **DONE** | `DASHBOARD_CANDIDATES` 3 -> 2; `cost_model.py` evaluates DoD line 4 for $0 |
| Pairwise instrument | **KEPT** | the v2 rubric passes both the known pair and the order swap. Two models had failed v1 identically |
| DoD line 1 | **FAILS** | a shipped nav label reads "Cilents"; the gate passed it |
| DoD line 2 | **FAILS** | 4 of 15 screens below 8 (gate raised to 8 and now enforced in code); **13 of 15 carry a listed defect**, including both that scored 9.2 |

Full assessment: `docs/evidence/session33/dod-assessment.md`. Findings and
spend: `docs/evidence/session33/results.md`.

**The two things the next session has to decide.**

1. ~~`QA_MIN_SCORE` is 7 and DoD line 2's floor is 8.~~ **Decided 2026-08-12:
   the gate goes to 8.** The pipeline had never been configured to enforce the
   number it is judged against; sessions 31 and 32 passed that clause by luck.
   Raising it costs roughly one extra image per request (~$0.10, expected
   ~$0.55) and still does not guarantee the floor, because the best-effort
   path ships the highest scorer when nothing is approved.

   Acting on the decision found a second bug: `QA_MIN_SCORE` was only ever
   interpolated into the judge's PROMPT, and the judge's own `approved`
   boolean was taken at face value. Raising the number would have changed the
   wording of a request and nothing about what shipped — a candidate scoring
   7.9 was still approved. The threshold is compared in code now, the same
   way text truth already was, and `tests/test_qa_and_selection.py` pins the
   gate against `DOD_MIN_SHIPPED_SCORE` so the two cannot drift apart again.
2. The defect clause needs an instrument. The per-image judge cannot be it —
   it scored 9.2 twice for screens carrying duplicated panels and invented
   panel titles. The swap-tested **pairwise** judge now can: across four runs
   it found real duplication, real clipping and a real floating-card
   violation, made no text claims, and attributed the same defect to the same
   image under an order swap. Wiring it into the request path as a per-screen
   defect check has never been tried and is the obvious next move.

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

**W7 — The Phase-2 bridge. DONE** (session 33): `app/pipeline/phase2_bridge.py`
maps a finished Phase-1 request onto the payload backend's
`POST /api/v1/requests` accepts — same name, industry, palette, and the
already-agreed screen inventory, read from the images that really rendered
rather than from a plan that can name a screen that never did. The MVP
blueprint deliberately does NOT cross: Phase 2's `capture_request_source`
excludes blueprint prose from the AppSpec author's snapshot on purpose, and
routing it through an intake field would defeat that decision under another
name. It invents nothing — no palette produces no palette and a note saying
so. 15 tests.

## What "astonishing" means (the DoD)

1. **Brand-critical text accuracy 100%** on shipped screens (W3 gate).
2. **No shipped screen scores below 8/10 on the fixed QA judge, and none
   carries a structural defect** — a duplicated panel, clipped or truncated
   content, a blank or unlabelled control, prompt scaffolding rendered as UI,
   or a garbled axis/label.
3. Pairwise: new pipeline beats today's output on ≥ 4 of 5 briefs
   (judge + owner eye — final call is the owner's, like Stage C).
4. Cost ≤ **$0.60/request** at pro-anchor + flash-follow-up tiering;
   wall ≤ 3 min.
5. Zero unbranded bytes reachable under `/uploads` (pinned, W0).

*Line 2 was amended by the owner on 2026-08-11.* It previously read "Every
shipped screen QA ≥ 8/10; anchors ≥ 9 on ≥ 4 of 5 golden briefs". The ≥9
threshold was retired because the instrument that measures it was shown not
to track quality: the fixed QA judge scored **9.2** for a retail screen
carrying two panels both titled "Inventory Status" and a chart axis reading
"Low / Misit / High / High", and **8.7** for the retail screen the owner
picked as the best output of the run. It also gave exactly 9.2 to four
materially different conditions of the same brief. The ≥8 floor is kept — it
is live, has passed in both measured sessions, and would catch a real
collapse — and the anchor threshold is replaced by a defect list, which is
what the judge is demonstrably reliable at. See
`docs/evidence/session32/results.md`.

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
