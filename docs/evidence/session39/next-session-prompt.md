# Kickoff — the navigation answers now; go and look at it

*Supersedes session 38's prompt. Its JOB 1 is closed — verifier v2's cost
is measured and bounded. The two defects session 39 found on request 130
are both fixed in `ui-spec-v5` and both await a funded run. The cost
program remains closed. The chart tail is unchanged and still
owner-gated.*

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

## JOB 1 — draw a screen under ui-spec-v5

Session 39 fixed both defects it found on request 130 and **neither has a
funded image run behind it**. The deterministic halves are unit-tested and
the prompt half is verified across seven briefs of real model output
(`golden/briefs-v5`, 20 of 21 screens declaring a valid, unique
`active_nav`) — but nothing has yet *drawn* a screen under v5.

One run on request 130's brief (~$0.75 at that brief's observed rate)
answers all of it at once:

- does the header now show a **different** item active on each screen, in
  the pixels — Home on the overview, Gallery on the browser?
- does the hero caption match its detail panel?
- did adding a field to the spec prompt cost anything elsewhere? A new
  instruction always has blast radius, and v5's is the first change to
  that prompt since v4.

Compare against 108 ($0.64505, 5 images, v1 verifier, dead nav) and 130
($0.75268, 6 images, v2 verifier, dead nav). Same brief three times is as
close to a controlled series as this pipeline gets.

**Watch for one specific regression.** `active_nav` is chosen by the model
and validated only for membership and uniqueness — not for being the
*right* item. A screen marked Gallery that is plainly the customer list is
a new failure mode, invisible to text-truth (the string is authorised) and
to the defect inspector (it looks within a panel). Eyes on the images.

## JOB 2 — the judge, if the owner wants it touched

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
