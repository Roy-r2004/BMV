# Kickoff — the demo can be a website now; go and draw one

*Supersedes session 38's prompt. Its JOB 1 is closed — verifier v2's cost
is measured and bounded. Of the two defects session 39 found on request
130, the hero-coherence fix is verified live on request 138 and the
navigation fix is landed but inert on that brief. The cost program remains
closed. The chart tail is unchanged and still owner-gated.*

Read first, in this order:

1. `docs/evidence/session39/results.md` — the cost answer, the funded run,
   three things found on it, and the two that were fixed
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
- **`golden/briefs-v5` is the current set** (session 39, adds `active_nav`);
  `briefs-v4` stays frozen at ui-spec-v4 as session 38's control arm, and
  the DEFAULT set is still v1 because every evidence document before
  session 38 means v1 by "the golden set" and `--frozen-specs` replays it.
  Address a set explicitly: `GOLDEN_BRIEFS_DIR=golden/briefs-v5`.
- **The public-site archetype exists** (session 39, owner's decision), and
  the reasoning that blocked it in session 38 is retired: declining to
  build a product because the measuring instrument rejects it is the wrong
  dependency direction. It ships with its own rubric rather than a change
  to the dashboard one, so no published score moved.
- **The additive rule for surfaces.** Anything that existed before session
  39 routes to `image_quality_judge.j2`, the same file. Moving
  `conversation` onto its own rubric is available but is a score-moving
  change and owes a before/after.

## The one thing to say back before instrument work

Any change to `image_quality_judge.j2`, the defect inspector, or the
verifier is its own step, measured before/after over a labelled set, stated
back to the owner first. Generators may vary; instruments are held fixed
while they do. That rule is what makes every number in these documents
comparable across sessions.

## JOB 1 — draw a public page. Nothing ever has.

Session 39 built the surface mechanism (`app/surfaces.py`): a screen
declares what CLASS of surface it is, and that routes both the prompt that
draws it and the rubric that scores it. The `public-site` archetype is
**home** (marketing) → **gallery** (catalog) → **manage** (back office),
and the classifier picks it correctly for the owner's brief while leaving
the salon control on its dashboard (probe, $0.02193, requests 139/140).

**All of it is unproven in pixels.** No image has ever been generated on a
public surface. Unit tests cover the routing and the prompt text; a text
probe covers the classification; nothing covers whether the image model
renders a credible landing page or whether the new rubric scores one
sanely. One funded run on the gallery brief (~$0.75) is the first job and
it answers:

- does `_marketing_block` produce a landing page, or a dashboard with the
  furniture stripped out and nothing put in its place?
- does `_catalog_block` produce a real grid with captions and filters?
- does `image_quality_judge_public.j2` score them in a sane range, or does
  it reject correct pages? **A rejection costs a regeneration**, so a badly
  calibrated public rubric spends money on every run.
- is the third screen still recognisably the owner's back office?

Report those scores flagged as public-surface — they are NOT comparable to
the dashboard corpus (mean 8.228, sd 0.489), for the same reason console
scores are not.

**Two known loose ends to look for on that run.**

1. `_apply_anchor_tool` still gives the anchor a selection flow ("explorer:
   Select Collection" on request 139), but the anchor is now a landing page
   and `_marketing_block` ignores `concept.steps`. Harmless — the surface
   branch runs before every `is_tool_screen` check — but the spec carries a
   flow that never renders, and the mechanism assumes the anchor is an app
   screen.
2. The model renames screens (`home-page` rather than `home`). Surface
   routing is positional and indifferent, but `screen_title` becomes "Home
   Page" while the customer's nav says "Home", so `active_nav_item`'s
   title-match fallback cannot fire and the whole burden falls on the
   declared `active_nav`.

## JOB 2 — the header can still lose the customer's word

Request 138 rendered `Home | Analytics | About | Contact` on its Dashboard.
The customer asked for Gallery. This is the highest-value open defect,
because it defeats the fidelity work at the last step and **every gate
passed it**:

- `text_truth` checks whether each expected string is present ANYWHERE on
  the screen. "Gallery" appears twice on that Dashboard ("GALLERY VIEWS",
  "Gallery Showcase"), so the header could lose it and the gate still
  passed, `checked: 6, failures: []`.
- It is a substitution, not an addition, so the count is still four.
- The anchor drew the header correctly; the *follow-up* corrupted it,
  while being shown the anchor and told to place navigation exactly where
  the attached image places it.

The fix has been named since session 38 and is now clearly worth its
price: **positional transcription**. Ask the transcriber not "is this
string on the screen" but "read the items in the top navigation bar, left
to right", then diff that list against `spec.navigation` in code. That is
one extra cheap call per screen, it catches substitutions, additions,
drops and reorderings in one move, and it is the only thing that can.

It is a new instrument, so it needs the owner's go, a labelled set and a
before/after — but the labelled set is free: requests 107, 108, 130 and
138 are already on disk with their specs, and the headers can be eyed.

## JOB 3 — make abstention explicit, not silent

`active_nav` shipped with "declaring nothing is honest" as its fallback.
Request 138 falsified that. On the Customers screen — collectors, patrons,
contact counts — the spec declared "" and the image model marked
**Gallery** active anyway. Where the spec is silent the model fills the
vacancy, the same mechanism as an untitled panel getting a heading
invented for it.

Two things to do, both cheap:

1. When no screen-appropriate item exists, `prompt_builder` should say so
   explicitly rather than omit the clause — the omission is what the model
   is filling. Mind the blast radius: this is a new instruction, so it is
   a prompt change with a funded run behind it, not a free edit.
2. The model declined to declare on 2 of 3 screens of the gallery brief
   even though the prompt's worked example is literally that brief's
   mapping. It mapped confidently on 5 of 7 golden briefs, so the
   instruction works in general and fails on this shape. Worth one look at
   whether `screen_type` is anchoring it.

## JOB 4 — the judge, if the owner wants it touched

`image_quality_judge.j2` criterion 4 grades data-visualisation craft, and
it docked 130/Analytics for reading "more like a marketing page" — on a
brief where a gallery IS the correct product. Session 38 declined to build
a public-site archetype for the same reason and session 39 got fresh
evidence for it.

This is instrument work and it is expensive in a way that is not just
money: criterion 4 touches every screen ever scored, so changing it
invalidates cross-session score comparisons wherever it applies. It needs
the owner's explicit go, a labelled set, and a before/after. Do not touch
it as a side effect of anything else.

## JOB 5 — the chart tail (unchanged, owner-gated)

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
- **The hero-coherence invariant is verified live** (request 138: the model
  again captioned the wrong painting, `'Tuscan Sunset' -> 'Morning Mist'`,
  and the caption, detail panel and picker all agreed in the pixels).
- **v5 blast radius is unmeasured.** Request 138 scored 7.5/7.0/7.5 against
  130's 8.1/8.0/8.7 on the same brief and config. One run each and image QA
  is noisy, but it is the wrong direction after a prompt change and should
  not be quoted as "no effect".
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
