# JOB 1 — the resolution probe, and what it killed

*2026-08-12, session 34. Probe $0.395 (3 direct calls, off-ledger, receipts
in [`probe/results.json`](probe/results.json)) + one funded salon run
$0.6211 (ledger-bracketed: 500→515 rows, $20.6928→$21.3139).*

## The question

Seven of eighteen session-33 screens carried collapsed letterforms —
"Cilents", "Portfollo", "Highiights", "beoking", "10:1S", "SLB" — ten-pixel
glyphs where `i`/`l`/`1` and `S`/`5` become the same shape. Can the canvas
grow?

## What the API actually honours

OpenRouter's chat-completions path accepts a top-level
`image_config: {"image_size": "1K"|"2K"|"4K", "aspect_ratio": ...}`.
Fired the REAL salon anchor prompt at 2K/16:9 on every relevant slug:

| model | asked 2K, got | latency | cost | image_tokens |
|---|---|---|---|---|
| `google/gemini-3.1-flash-image` | **2752×1536 — honoured** | 24s | $0.1019 | 1680 |
| `google/gemini-3-pro-image` | 1376×768 — **ignored** | 31s | $0.1462 | 1120 |
| `google/gemini-3-pro-image-preview` | 1376×768 — **ignored** | 31s | $0.1466 | 1120 |

Both sizes have the same 1.79:1 shape, so pixel count changes and
composition does not. Pro will not go bigger through OpenRouter, full stop —
it accepts the field silently and bills its fixed 1120 tokens.

## Why pro's refusal does not matter

The defect attribution in [`session33/defect-sweep.md`](../session33/defect-sweep.md)
is six for six: **every collapsed-letterform instance sits on a flash
FOLLOW-UP screen** (retail/analytics, salon/schedule ×3, salon/analytics,
hedgefund/clients_overview). No anchor produced one — the s33 salon anchor
rendered "Clients" correctly while the follow-up rendered "Cilents". The
model that needs the pixels is the model that honours the request.

## The same-brief comparison (the experiment the brief asked for)

One salon golden brief through the full harness with 2K follow-ups
(`s34-2k`, request 76) against the s33 baseline (`s33-full`, request 72),
small text read at matched effective zoom (baseline at 4×, 2K at 2× = same
physical magnification):

- **nav**: baseline draws "Cilents"; 2K draws "CLIENTS" flawlessly
  ([`probe/compare-s33-nav-4x.png`](probe/compare-s33-nav-4x.png) vs
  [`probe/compare-s34-2k-nav-2x.png`](probe/compare-s34-2k-nav-2x.png))
- **"Full Highlights"** (rendered "Highiights" in s33 salon/analytics):
  perfect at 2K
- the schedule slot grid, stylist names, service/price tables, chip labels:
  no malformed glyph found on any of the three screens
- incidentally, the 2K analytics chart's plotted points agree with its own
  axis (5800→7500 against an even 5000–7500 scale) — one sample, not a
  claim about JOB 6's class

Four of the six s33 instances were on this one brief. The honest claim:
**the class is dead on the brief that carried most of it**; the full
golden-set re-measure at the end of this session is what may upgrade that
to "dead".

## Two carried-in unmeasured things, both got data

1. **The gate at 8, enforced in code**: dashboard candidate 1 scored 7.9
   with the judge's own `approved: true` — the in-code comparison rejected
   it, candidate 0 (8.1) shipped, no regeneration was needed. First
   observed enforcement on a funded run.
2. **The band-magnified text-truth gate rejected a 2K candidate** —
   schedule cand0 (QA 9.2) drew the wordmark as "Lumière Hair Studio"
   instead of the spec'd product name "Lumière Studio OS"
   ([`probe/rejected-cand0-nav-2x.png`](probe/rejected-cand0-nav-2x.png)).
   A real exact-string catch through the new band path, with clean glyphs —
   a *misspelling* catch is still unobserved, and may stay that way if 2K
   simply stops producing them upstream. The regeneration it bought
   produced a passing screen (8.5).

## Cost and clock, honestly

- flash at 2K, real path, 3 ledgered calls: **$0.10341/image mean**
  (default: $0.070) → +$0.033/image, +$0.10/request at nominal counts
- projection at shipped defaults (`cost_model.py`): **nominal $0.5284**,
  inside the $0.60 line; worst case rises to ~$0.895 (was $0.754 — the
  worst case was already over the line and already pinned as the accepted
  regeneration tail)
- QA + transcription at 2K input: $0.0011–0.0022/call — no blowup, but
  transcription latency roughly doubled (~5s → ~10s)
- bakeoff wall 263s vs ~95s baseline **decomposes to**: a 116.3s pro-anchor
  latency outlier (default size — nothing to do with 2K), one text-truth
  regeneration (+~42s), 2K's own contribution ≈ +8s per flash generation
  and +5s per transcription. The 3-minute line is judged on the REQUEST
  path and is re-measured end-to-end before this session claims it.

## Adopted, pinned

`IMAGE_SIZE_FOLLOWUP=2K` (+`IMAGE_ASPECT_RATIO=16:9`) ships as the default;
the anchor sends nothing. `image_config` rides per-item exactly like
`model`, so the regeneration retry re-fires the size the candidate ran at.
The text-truth band magnification adapts (exactly the old 3× at 1376/1408
sources, capped so a 2K band cannot balloon the payload of a fail-open
call). All pinned in `tests/test_image_size.py` (10 tests).

**JOB 4 (composite nav labels) is therefore NOT triggered** — its
precondition was "the canvas cannot grow".
