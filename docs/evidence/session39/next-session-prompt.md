# Kickoff — the header is the customer's; the navigation still isn't

*Supersedes session 38's prompt. JOB 1 of that brief is closed and does
not need reopening: verifier v2's cost is measured and bounded. The cost
program remains closed. JOB 2 (the chart tail) is unchanged and still
owner-gated.*

Read first, in this order:

1. `docs/evidence/session39/results.md` — the cost answer, the funded run,
   and three things found and not fixed
2. `docs/evidence/session39/verifier-cost-ab.json` — 47 images, 76 claims,
   both arms, per-claim reasons
3. `docs/evidence/session38/results.md` — still the substantive record;
   note the correction block at the request-129 section
4. Memory: "Count it, don't sample a window", "Describing a thing next to
   where it is drawn", "LLM judges confabulate about text"

## Settled — do not reopen without a reason

- **Verifier v2 stays.** Cost is $0 to +$0.04 a run (≤6%), against a
  corpus sd of $0.135. Do not tune it back, and do not watch the cost line
  run-by-run — detecting the effect that way needs ~175 runs a side.
  Session 38's claim that request 129 was a v2 reading was wrong and is
  corrected in place; the first v2 run is **130**.
- **Criterion 4 stays as it is** (session 38). Console scores stay flagged
  as not-comparable wherever they are quoted.
- **The v4 golden set is frozen** and the DEFAULT set did not move.
  Address the new set explicitly with `GOLDEN_BRIEFS_DIR=golden/briefs-v4`.
- **No public-site archetype** without a judge change first — and a judge
  change is its own step with a before/after over a labelled set. Session
  39 got fresh evidence for the original decision: the judge docked
  130/Analytics for feeling "more like a marketing page", on a brief where
  looking like a gallery is the *correct* answer.

## The one thing to say back before instrument work

Any change to `image_quality_judge.j2`, the defect inspector, or the
verifier is its own step, measured before/after over a labelled set, stated
back to the owner first. Generators may vary; instruments are held fixed
while they do. That rule is what makes every number in these documents
comparable across sessions.

## JOB 1 — the navigation is honoured but the navigation state is dead

This is the direct, visible consequence of the fidelity work and the
highest-value thing open.

Request 130 renders `Home | Gallery | About | Contact` exactly as the
customer wrote it, on all three screens — and **all three show `Home` as
the active item**, because none of those four labels matches a demo screen
title (Dashboard, Analytics, Customers). `active_nav_item` is behaving as
specified: name an active item only when a nav label actually matches the
screen. The gap is upstream of it. Honouring a customer's header and
mapping the demo's screens onto that header are two different problems and
session 38 solved only the first.

Two candidate shapes, both cheap to reason about before spending:

- **Map screens onto the customer's labels.** When explicit navigation
  exists, let it drive the screen set — the demo's three screens become
  three of the customer's four items rather than the archetype's defaults.
  This touches `ui_spec.py` screen-role selection, not the judge.
- **Accept it and say so.** Leave the nav static and treat the header as
  chrome. Cheaper, honest, and defensible — but the prospect sees a
  four-item menu that never responds.

Decide with the owner before building. A funded run on request 130's brief
is the natural check either way, and 108/130 give two pre-existing points
to compare against.

## JOB 2 — cross-panel coherence has no instrument at all

130/Analytics captions its hero image "Crimson Tide" while the detail
panel beside it reads "Azure Embrace", $2,800 — and "Azure Embrace" is the
underlined selection in the picker. Two different paintings presented as
one. The defect inspector raised one claim on that screen and it was not
this; the QA judge reported only that the image was "cut off at the bottom
of its card"; text-truth passed, correctly, because every string on the
screen is a string the spec authorised.

Nothing in the pipeline compares one panel against another. That is a new
defect class, not a miss by an existing instrument, and it is exactly the
kind a prospect notices. If it gets built it is instrument work: a
labelled set first, before/after second, and only then a landing.

## JOB 3 — the chart tail (unchanged, owner-gated)

Both of request 119's console re-rolls were `malformed_data_display` on a
chart: unevenly stepped Y-axis ticks at even spacing. Same finding as
sessions 36, 37, 38. The two specced answers are unchanged — the
coded-ticks prompt experiment (~$2 to measure) and JOB 6 (PIL-composited
charts). **Fund only if defect-carrying charts bother the demos
commercially.** Note that 130's chart was clean, ticks correct and evenly
spaced, so the tail is a tail and not a constant.

## Smaller, all with receipts

- **The verifier is unstable on the header-vs-panel double CTA.** v2
  confirms 'Apply Model' (104) and 'Apply Strategy' (128) and refutes
  'Book This Slot' (106), 'Request Info' (107), 'View Painting' (108) —
  the same shape, opposite verdicts. Shrinking blast radius, since
  `prompt_builder` no longer generates the top-bar button. Worth an A/A
  control if anyone wants the noise floor: re-run
  `scripts/verifier_cost_ab.py` with `--baseline-template` pointing at the
  live v2 template, ~$0.18, and the flip count you get back is pure
  instrument variance.
- **Placeholder names look fixed** — 108's "Guest Artist A/B" did not
  recur on the same brief in 130. One run, one brief; the investment and
  schedule briefs that produced "Institutional Fund ABC" and "Client
  B/C/D/E/F" have not been re-run since the v4 rule landed.
- **An honoured navigation still cannot catch an INVENTED item.** Both
  known sources are cut off upstream, but a third would be silent.
  Detecting extras needs positional transcription, which nothing has.
- **Archetype selection is not deterministic.** No write-up should say a
  class "lands on X" from a single run.
- **The scaffolding leak has not recurred.** 105's "Floating Labels" chip
  was pre-fix; 130 is clean. Keep looking at analytics heroes.

## Traps

- The judge is held fixed while generators vary. State instrument changes
  back before making them.
- `scripts/verifier_cost_ab.py` **swaps a live template file** and restores
  it in a `finally`. Do not run a generation while it is running, and check
  `git status` after — a killed process leaves the baseline template live.
- Read spend from `ai_usage_events` via `/api/requests/<id>/admin`. The
  OpenRouter key is shared; use its balance only as a bracket.
- Do not run two bakeoff batches concurrently.
- Instrument replays are ~$0.004 an image a side. Regeneration is $0.121 an
  image. Reach for the replay first, every time — session 39's entire
  answer cost less than a third of one funded run.
