# Session 33 — the closing session that did not close

*2026-08-12. Ledger $16.9806 → $20.6928, delta **$3.71** against a $15
ceiling. Suite 164 → 222. Branch `consultant-images-pipeline`.*

The session was scoped to finish Phase 1 and declare it shippable. It found
enough to stop that instead, and the two things it found were both invisible
to every measurement taken before it.

## The headline

**Running the real thing found what running the rig could not.** Sessions 31
and 32 measured 24 image cells and 120 images through `scripts/bakeoff.py`,
which calls `generate_demo_screens` directly on frozen single-screen briefs.
That rig cannot express a three-screen set where follow-ups inherit a tool
anchor, and it cannot express an operator opening `/admin`. One request
through the public intake and one complete 5×3 golden set produced eleven
distinct defects between them, six of which no bake-off cell could have shown.

**Two DoD lines fail.** Full assessment in
[`dod-assessment.md`](dod-assessment.md). Briefly: a shipped nav label reads
"Cilents" and the text-truth gate passed it, and **13 of 15 screens** carry a
structural defect the DoD forbids — including both screens that scored 9.2.

**One instrument came back from the dead.** The pairwise judge, which two
models had failed identically, passes on the rewritten rubric.

## JOB 1 — the public path, run for the first time

Request 68, Harbourline Marine, a boatyard — a business deliberately outside
the golden set, and one whose obvious demo would be wrong.

It worked. Three screens, watermarked, composited, in `/preview` with
`hero_url` and `detail_urls`; `/admin` reporting per-image cost and model;
**the anchor came out a TOOL screen** (select service → choose resource →
pick slot, over a photograph of a boat in a travel lift).
See [`job1/anchor-tool-screen.png`](job1/anchor-tool-screen.png).

It also found six things:

| # | defect | why the rig could not see it |
|---|---|---|
| 1 | schedule screen shipped a top nav bar **and** a left sidebar with the same items | needs a 3-screen set where a dashboard follows a tool anchor |
| 2 | analytics screen drew the literal text "Reasoning line: Historical patterns suggest resource need" | prompt scaffolding; possible on any screen, seen here |
| 3 | all three screens carried an OS window title bar with minimize/maximize/close | ditto — and the hero composite then framed it in browser chrome, twice-framed |
| 4 | detail crops shipped reading "morning, Marco" and "SERVICE" | the crop insets 15% to clear a sidebar; a tool anchor has none |
| 5 | `/admin` could not report `text_truth` or per-screen cost | needs an operator, not a matrix |
| 6 | the service never configured logging, so every `logger.info` went nowhere | needs the service to actually be running |

(1) is the one worth reading twice. The continuation prompt told the model to
"preserve the navigation exactly as the attached image places it" — the
attached anchor had a top bar — and, four lines later, to draw a "left
sidebar". It did both. Navigation placement is a property of the product,
decided once by the anchor; the prompt was asking each screen to decide again.

All six fixed and pinned.

## JOB 3 — the complete deliverable, and what it costs to look at it

5 briefs × 3 screens, tiered, `briefs-v2`, judge held fixed. Requests 69–73,
$2.2194, 90–101s a brief.

| brief | anchor | screen 2 | screen 3 | $ | wall |
|---|---|---|---|---|---|
| dental | 8.1 | 8.7 | 8.1 | 0.4415 | 94s |
| law | 7.5 | 8.7 | 7.5 | 0.4410 | 96s |
| retail | 9.2 | 8.7 | 9.2 | 0.4437 | 90s |
| salon | 7.9 | 9.1 | 8.7 | 0.4502 | 97s |
| hedgefund | 8.7 | 7.9 | 8.5 | 0.4430 | 101s |

**15/15 passed the text-truth gate. Mean 8.43. And one of those 15 renders
"Cilents".**

Follow-ups (mean 8.51) scored *above* anchors (8.28), which is the tiering
finding holding up: a flash follow-up conditioned on a pro anchor is not the
weak link. The anchors are.

All fifteen inspected — nine read at full size by me, all fifteen by a
per-screen sweep whose every claim was then put to a verifier told to refute
it. **13 of 15 carry a listed defect.** The table is in the DoD assessment.
Four patterns are worth naming:

**The AI module had a title vacancy, and everything nearby filled it.** It has
no title field, so the model titled it from whatever text was closest: the
composition variant's own name (`HERO INTELLIGENCE`, from a directive opening
"COMPOSITION DIRECTION — Hero Intelligence:"), the block's descriptive prose
(`SOFTWARE-FORMED OPINION`, `ONLY AI INTELLIGENCE`, `INTELLIGENCE MODULE`), or
the word "premium" from an instruction about treatment (`PREMIUM AI
INTELLIGENCE`). Five instances across two briefs.

**Flash follow-ups duplicate panels.** "Attorney Performance" twice with
identical rows, "Recent Trades" twice with identical rows, "Resource
Efficiency" twice on request 68 with the second copy untitled. Three of three
analytics-shaped follow-ups.

**The interface floats on a backdrop again.** Session 32 fixed this twice and
recorded it as fixed. It is back on salon, retail and hedgefund, sometimes
with cards hanging outside the app's own frame.

**The prompt's descriptive words become UI labels.** Both retail screens
shipped a top-bar button labelled literally "Action" — the nav block asked for
"a single accented action button at the right" and supplied no string, so the
model used the only word it had been given. The spec has carried a real one
(`concept.primary_action`) the whole time. The button is named now, and where
no name exists it is not asked for at all: an unlabelled control is on the
defect list and an invented one is worse. This is the same failure as the
field labels, the variant name and the quotation marks — four shapes of one
mistake, which is *describing* a thing next to the place it should be drawn.

### The fixes, and the honest result of testing them

Five classes fixed and pinned, then re-measured on the two worst briefs
(requests 74–75, $0.8789):

- law's anchor lost "HERO INTELLIGENCE", 7.5 → **8.1**
- salon's anchor stopped floating on a backdrop, 7.9 → **8.1**
- **and both re-runs produced new defects**: an unlabelled "+" button where
  "Book Consultation" had been, and "viabllity" for "viability" at 7× zoom

One fix made things worse before it made them better. Quoting each AI-module
value to delimit it produced a salon anchor whose headline shipped reading
`"Recommend Add-on: Deep Conditioning"` — quotation marks drawn as UI. **A
delimiter is scaffolding too.** Bare strings on their own lines now, the same
shape the metric-card and panel blocks have always used.

## JOB 5 — the pairwise instrument passes

The standing ruling: one rubric rewrite forbidding text claims, then a
verdict; retire it if position bias survives. Held the model fixed at
`claude-sonnet-5` — the one that failed in session 32 — so the rubric is the
only variable.

**Test 1, the known pair.** The retail v2 regression (two panels both titled
"Inventory Status", axis reading Low / Misit / High / High) against the retail
v3 anchor that scored 9.4.

> Both orders picked the v3 anchor. Cited: the duplicated panel, the repeated
> axis label, and "Espresso Forte" clipped at its panel edge. **All three
> verified by eye.** Zero text-accuracy claims.

**Test 2, the shape it actually failed on.** Session 32's six failures were
pairs of two *good* screens — that is where a judge with nothing to say
reaches for position. So: retail c4 (9.4) against retail s33 (9.2).

> Forward: c4 wins, because "B's panel appears to float on a visible brown
> backdrop". Reverse, with the images swapped: **the same defect attributed to
> the same image**, plus a second finding — c4 duplicates "View Full Details"
> between the nav and the result panel. Reported as a tie, one defect apiece.

Both claims are true. I opened both images and checked. Session 32's judge
answered "A" six times from six and attributed opposite defects to the same
image; this one attributes the same defect to the same image in both orders
and declines to pick a winner when the counts are level.

**Verdict: keep it.** With the honest caveat that this is two pairs, not a
population — but it is two pairs chosen to fail it, and it did not.

What changed in the rubric: text claims forbidden outright with the reason
stated, comparison restricted to countable structural defects, and "tie" made
a real answer rather than a failure to decide. The pressure to name a winner
was what the bias hid behind. Also dropped a criterion that scored images
against a bottom-right logo corner the pipeline stopped reserving in session
32.

This matters beyond JOB 5: it is now the only automated instrument here shown
to find real structural defects, which is exactly what DoD line 2 needs and
what the per-image judge demonstrably cannot do.

## JOB 4 — the deck

Rebuilt from the golden-set screens, opened, and all seven slides read
(Keynote's AppleScript export; PowerPoint's "save as PNG" still produces
nothing). Rendered slides in [`deck/`](deck/).

**No distortion, no overlap, correct aspect ratios everywhere** — the two bugs
this artifact has a history of are gone. Two proportion defects found and
fixed in the pipeline:

- Detail crops sat in fixed 2.45″ slots. A crop is a wide thin band, so at
  3.5″ wide it rendered under an inch tall and left 1.5″ of its slot empty,
  twice per slide — a column labelled IN DETAIL holding two thumbnails too
  small to show any detail. Slots now take the height the crop's own aspect
  ratio needs.
- Closing-slide cards were a fixed 2.9″. Two employees with one-line reasons
  produced boxes four times taller than their content, which reads as content
  that failed to load. Sized from the longest reason now, capped so a
  pathological one cannot run off the slide.

`scripts/deck_sample.py` also printed hardcoded **dental** pain points under
the name of a coffee roastery. Its placeholder prose is derived from the brief
now and prefixed `[sample]`, because a sample deck committed as evidence
should not be quietly wrong about the business it names.

## JOB 6 — W7, the Phase-2 bridge

`app/pipeline/phase2_bridge.py` maps a finished Phase-1 request onto the
payload backend's `POST /api/v1/requests` accepts. 15 tests.

The design decision worth recording: **the MVP blueprint does not cross.**
Phase 2's `capture_request_source` builds the AppSpec author's snapshot from
exactly the intake columns and says in its own docstring that it "deliberately
excludes contact PII, admin notes, generation progress, blueprint prose, and
preview artifacts". Routing the blueprint through `desired_outcome` would
defeat that decision under a different name. What crosses is facts — the
concept name, the agreed screen inventory (read from the images that really
rendered, not from a plan that may name a screen that never did), the palette,
the AI capabilities — carried in the two free-text fields that semantically
mean them, with the client's own words always first.

It invents nothing. No palette produces no palette and a note saying so.

## Spend

| step | ledger |
|---|---|
| JOB 1, request 68, the public path | $0.5336 |
| JOB 3, requests 69–73, the golden set | $2.2194 |
| JOB 3 verification, requests 74–75 | $0.8789 |
| JOB 5, pairwise, four judge calls | $0.0802 |
| **total** | **$3.7122** |

Against a $15 ceiling and a ~$3.20 plan. The overrun is the verification
run, which was not in the plan and is the reason this document can say what
the fixes did rather than what they were intended to do.

## Traps, confirmed and new

Every trap in the session-32 watch-list held and none cost anything this
session. One new one:

**SQLite in WAL mode over a Docker bind mount is not readable by a second
process.** With the service running against
`sqlite:////repo/consultant-service/consultant.db`, a fresh connection — from
the host *or* from inside the same container — saw the database as it was
before the run started. The rows were not lost; they landed on a clean
`docker stop`. But every ledger bracket taken while the service is up is
wrong, and it is wrong in the direction of looking like nothing was spent.
**Read the ledger through the API, or after a clean stop. Never from the file
while the service is running.**
