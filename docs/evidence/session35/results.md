# Session 35 — the customer's result, and the deck that goes with it

*2026-08-12, `main`. One funded run, request 90 (Beacon Physiotherapy),
**$0.79708** ledger-attributed. Suite 262 → 288. The OpenRouter key was
topped up mid-session ($119.82 available at the time of the run).*

The session started as explain-first and turned into product work when the
brief surfaced a question the repo could not answer well: **how does a
customer see their screens after the pipeline makes them?** They could not.
A finished run was reachable exactly once, in the tab that started it, while
the page told them to check an inbox nothing ever sends to.

## What landed

1. **A run has a permanent address.** `/studio/:id` is a real route; the
   page navigates to it the moment the request exists rather than holding
   the id in component state. A refresh mid-generation resumes; a bookmark
   works tomorrow; a forwarded link opens the same screens. `elapsed_s` is
   computed server-side because `created_at` is a naive `utcnow()` that a
   browser parses as local time.
2. **The dead email promise is gone.** Nothing in this service sends mail
   (no `smtplib`/`sendgrid`/`resend` anywhere), so the page no longer says
   anything is on its way. It hands over the link instead, and the deck.
3. **The screen's spec is persisted** (`spec_json` on `generated_images`).
   It used to be built, rendered into a prompt and discarded, so nothing
   downstream could say what a finished screen contained.
4. **Each screen is captioned from that spec** (`screen_story.py`, shared by
   the result page and the deck so the two can never describe the same
   screenshot differently). The sentence is COMPOSED from strings the image
   model was handed to render — subheading, KPI labels, panel titles, the AI
   module's own headline — so a client can check the caption against the
   picture. No spec, no caption.
5. **Every generation is a customer run** (owner's rule). `scripts/bakeoff.py`
   no longer replays frozen specs into `generate_demo_screens`; it submits
   the brief's intake and calls `orchestrator.run`. Cells are viewable at
   `/studio/<id>` like anything else. `--frozen-specs` survives only to
   reproduce a session 31–34 cell.
6. **The deck takes its colour from its own screens** (`deck_palette.py`),
   shows one image per slide, and states the AI module drawn on each.

## The measurement — DoD line 4 now has a number, and it fails

Request 90, the full public-intake path, everything on:

| | measured | DoD line |
|---|---|---|
| wall clock | **254s** | ≤ 180s — **FAILS by 74s** |
| cost | **$0.79708** | ≤ $0.60 — **FAILS by $0.197** |
| shipped screens | analytics 8.5, dashboard **7.9**, schedule 8.0 | none below 8 — **FAILS** (best-effort ship) |

Six image calls against a nominal four: two regenerations fired. This is
the first time the 3-minute clause has ever been measured on the real path —
session 33's 2m48s predates parallel follow-ups, the defect check and 2K,
and the s34 bakeoff walls of 116–173s were frozen replays with no text
stages. **Phase 1 is further from line 4 than the projection suggested, not
closer**, and one sample is one sample: the same run under a warmer cache or
without the two regenerations would land differently. Two more runs before
anyone treats 254s as the number.

Where the time goes is not yet instrumented per stage. That is the next
measurement, and it is cheap: the orchestrator already emits every stage
transition with a timestamp.

## Defects found by looking at the artifact

The deck was rendered to PNG through LibreOffice and read, which found four
things no structural test would have:

- the cover used the hero composite — a designed frame on a light backdrop —
  bled to the slide edges and dimmed, showing two pale margins that read as
  a rendering fault. Now the raw screenshot;
- two scrims at 76/88% made a seam that looked like a failed render;
- the shift slide's headline wrapped **into** the panels below it, and the
  consulting summary ran off the slide — PowerPoint does not shrink text to
  fit, it draws it over whatever is underneath;
- in the AI strip, the rationale box ran 0.4" into the KPI box.

The per-call-site character clamps that fixed the last two kept being wrong
by a few glyphs, so they were replaced by `_fit()`, deriving the limit from
box width and point size.

A test also caught a real bug in the palette's own fallback: a pale
greyscale screenshot pasted its light ground into the fixed dark scheme and
left the text white — contrast **1.09**. The fallback now runs the same
guards as every other path.

## Retired

The three detail-crop pins in `test_deck_layout.py`. The owner removed the
IN DETAIL column from both surfaces; a test for a feature that no longer
exists is not coverage. What replaced them: one image per screen slide,
centred, filling the band the column freed. The composite crops are still
generated — the deck's own history is that they were worth the space, and
they may come back — they are simply not shown.

## Still open

- **The clock (254s vs 180s)** — the headline failure. Per-stage timings
  next, then `SECONDARY_CANDIDATES` and the verify pool before any quality
  gate is touched.
- **Cost at $0.797 on a two-regeneration run.** The nominal projection is
  $0.537 and s34's nominal briefs landed ~$0.52; this run was the tail, not
  the middle. Needs more than one sample before it means anything.
- **JOB 6 (composite the charts in PIL)** — untouched, and its baseline is
  still soft: two of session 34's three shipped defects had their
  regeneration die with the key rather than fail on merit.
- **Ops**: the consultant service still runs as an ad-hoc `bmv-consultant`
  container on 8002, absent from `docker-compose.yml`, reporting unhealthy
  because its healthcheck probes 8000 while uvicorn listens on 8002.
- **`ROADMAP.md`** is still a session stale.
