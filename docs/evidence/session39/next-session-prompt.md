# Kickoff — the demo is right; the instrument scoring it is not

*Supersedes every earlier prompt. The owner's goal is MET and verified over
seven funded runs: a brief asking to showcase paintings with home, gallery,
about and contact now produces a public landing page, a gallery page, and a
back office carrying analytics and artwork management
([/studio/147](http://localhost:5173/studio/147)). What is left is
calibration, one code-level promise, and one new instrument.*

Read first, in this order:

1. `docs/evidence/session39/results.md` — the whole session, including the
   seven-run table and the three defects that were in the prompt text
2. `app/surfaces.py` — the routing key, and the additive rule at the top
3. `app/prompts/image_quality_judge_public.j2` — the rubric JOB 1 is about
4. Memory: "Price instrument changes by replay", "Describing a thing next
   to where it is drawn", "LLM judges confabulate about text", "Count it,
   don't sample a window"

## Settled — do not reopen without a reason

- **The surface architecture stands.** A screen declares what class it is
  and that routes the prompt shape, the rubric and the defect policy.
  Anything that existed before session 39 routes to
  `image_quality_judge.j2`, the same file, so no published score moved.
  Adding a business shape that reuses surfaces costs one archetype entry
  and one art-pack entry — there is a test that says so.
- **The nav split cannot be bought with a prompt.** Three attempts failed
  (an explicit "no item is marked" clause; scoping the forced list to
  public surfaces; removing the two contradicting rules and the hard-coded
  list in the JSON shape). Do not try a fourth wording. JOB 3 is the fix.
- **Criterion 4 of the dashboard rubric stays as it is.** Public pages have
  their own rubric now, which is what that debate was actually about.
- **Verifier v2 stays** — $0 to +$0.04 a run, measured.
- **The cost program is closed.** $0.39 nominal, ~$0.63 realised.

## The one thing to say back before instrument work

JOBs 1 and 4 both change an instrument. Each is its own step: a labelled
set first, a before/after second, the owner's go before either lands.
Generators may vary; instruments are held fixed while they do. That is what
makes every number in these documents comparable across sessions.

## JOB 1 — the public rubric under-scores clean pages

**The finding.** Gallery was the weakest screen in all seven runs. It is
not the weakest page — it is the most under-scored one. Request 146 scored
**7.5 on a single complaint**: *"the typography for the artwork titles
feels a bit small."* Request 147's five complaints are nav spacing "not
quite even", a glow that is "slightly pixelated", typography "a bit
generic", captions aligned bottom-left, and rounded corners on cards.

`image_quality_judge_public.j2` already says taste calls "should cost at
most a fraction of a point, should never by themselves drive the score
below 7". Two things are wrong with that guard:

1. It is being ignored — a lone typographic preference is taking a point
   and a half.
2. Its floor is **7**, and `QA_MIN_SCORE` is **8**. Even obeyed exactly, it
   permits a structurally perfect page to be marked unapproved on
   preference alone.

The rubric is not badly designed — request 141 proves it catches real
problems precisely ("This is an admin/management screen, not a public
gallery page", "drawn as a card floating on a visible backdrop"). It is
mis-calibrated.

**The change to try:** a page with no structural defect and only
typographic or spacing preferences scores at least `min_score`. Tie the
floor to the threshold rather than to a hard-coded 7.

**How to measure it, and this is the point: do NOT fund runs.** Instruments
re-judge existing screenshots. Requests 141-147 left roughly a dozen public
screens on disk with their specs, all of them eyeballed and written up in
results.md — that is the labelled set, free. Two arms over the same images,
old rubric vs new, roughly **$0.03**. Report per-screen score deltas and,
specifically, how many structurally-clean pages cross from below 8 to at or
above it. Session 39 answered a $111 question for $0.18 this way; the same
discipline applies here.

Watch the other direction too. A rubric that stops penalising taste can
become a rubber stamp — include at least one genuinely bad screen in the
set (request 141's gallery, 5.0, is on disk) and confirm it still fails.

## JOB 2 — delete the corner reserve, it is protecting nothing

Every image prompt still carries `_CORNER_RESERVE`: keep roughly the last
12% of width and 17% of height clear, "a real logo is composited into
exactly that small corner afterward". It is not. `compositing.py` places
the mark on the BACKDROP now, and its own comment says why: *"The corner
mark painted onto the screenshot itself is what clipped card content in the
W1 and W2 runs."*

So the pipeline reserves a chunk of every canvas for something that moved,
and **both** judges still auto-reject "content encroaching into the
reserved bottom-right logo corner" — the public rubric inherited that line
because it was copied across without being questioned.

On a full-bleed landing page this is actively harmful, and it is a live
suspect for the margins still visible around request 147's hero. Deleting
the block and the two rubric lines is a few lines of work, and it can be
measured by re-judging the existing corpus rather than by funding runs.

## JOB 3 — the back-office navigation, as a promise in code

The back office still carries the WEBSITE's menu — Home, Gallery, About,
Contact — on a screen of enquiry counts and revenue charts. It is none of
them, `active_nav` is correctly empty, and the model highlights "Home"
anyway, every run.

`_apply_explicit_navigation` already stops FORCING the public list onto
back-office screens. What is missing is what fills the gap. Use the pattern
that actually works here: **a dedicated JSON field**. `active_nav` is filled
correctly on 20 of 21 golden screens because it is a named field in the
output shape; the same instruction written as prose in the rules block was
ignored three times running.

So: ask for the owner's menu as its own field on the back-office screen,
and enforce in code that what comes back is not simply the public list
copied over, falling back to a short generic admin list if it is. Verify
with one run on the gallery brief (~$0.65) and check the pixels, not the
spec — the spec has looked right before while the image did not.

## JOB 4 — positional transcription, the one that closes a class

Request 138 rendered `Home | Analytics | About | Contact` where the
customer asked for Gallery. Every gate passed it: `text_truth` returned
`passed: true, checked: 6, failures: []`, because it asks whether an
expected string appears ANYWHERE on the screen, and "Gallery" appeared
twice elsewhere on that page ("GALLERY VIEWS", "Gallery Showcase"). It is a
substitution, so the count is unchanged too.

Ask the transcriber a positional question instead — *"read the items in the
top navigation bar, left to right"* — and diff that list against
`spec.navigation` in code. One cheap call per screen, and it catches
substitutions, insertions, drops and reorderings in a single move. Nothing
else can.

Instrument work: labelled set, before/after, owner's go. The set is already
on disk — requests 107, 108, 130, 138 and 141-147, each with its spec and a
header that can be read by eye.

## JOB 5 — owner-gated, neither blocks anything

- **The chart tail.** Unevenly stepped Y-axis ticks at even spacing, the
  same finding since session 36, seen again on request 141's back office
  (0, 10, 20, 30, 40, 50, **160**). Coded-ticks experiment ~$2, or JOB 6's
  PIL-composited charts.
- **Re-run the art-pack A/B.** `ENABLE_ART_PACKS` is False in production,
  so no art direction reaches any prompt today — including the `public-site`
  pack written in session 39. It was measured in session 31 and lost 0-2 on
  pairwise, but all four judged runs named the SAME deciding defect: panel
  text clipped behind the composited logo. That logo has since moved
  (JOB 2). Session 31 called this "the one experiment most likely to flip".
  ~$0.9.

## Smaller, all with receipts

- **Images bleeding through data panels.** Request 144's back office drew a
  cityscape painting through the "Pending Inquiries" list, destroying
  legibility, and a forest through the chart. Seen once in seven runs; the
  defect inspector did not raise it. Watch for it before building anything.
- **"Oll on Canvas"** — request 142 misspelled "Oil" twice in card captions,
  `text_truth` passed (it checks 6 brand-critical strings, not panel
  content) and the judge scored the page 9.0 without noticing. The known
  "judges confabulate about text" blind spot; JOB 4 is the same shape of
  fix.
- **A duplicated hero caption** — request 141 drew "Studio View" as both an
  overlay chip and a caption beneath the image.
- **v6 has no golden set.** The newest frozen set is v5, and the live stage
  is ui-spec-v6. The version test is generic now, so building one is
  `GOLDEN_BRIEFS_DIR=golden/briefs-v6 python scripts/build_golden.py`
  (~$0.07) and nothing else.
- **A stray empty `consultant.db`** sits untracked at the repo root, left by
  a query that ran from the wrong directory. Safe to delete.

## Traps

- **uvicorn runs without `--reload`.** Restart the container after ANY code
  change, or the run pays to test the old code. This nearly cost a run.
- Read spend from `ai_usage_events` via `/api/requests/<id>/admin`. The
  OpenRouter key is shared; use its balance only as a bracket.
- `scripts/verifier_cost_ab.py` swaps a live template and restores it in a
  `finally`. Never run a generation alongside it; check `git status` after.
- Instrument replays are ~$0.004 an image a side; a regeneration is $0.121.
  **Reach for the replay first, every time.**
- Prompt changes have blast radius the previous run never predicts. Every
  fix in session 39 was verified in the pixels, and three of them were
  defects introduced by the fix before.
- Explicit pathspecs on `git add` — parallel sessions share this checkout.
