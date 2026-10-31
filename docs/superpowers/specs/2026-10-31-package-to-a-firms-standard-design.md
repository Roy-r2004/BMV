# The package to a firm's standard

Design, 2026-10-31. Owner: Roy Rizkallah. Written from the brainstorm of the
same day and the research report kept beside this file,
`2026-10-31-what-top-consultancies-deliver.md`, which every claim about
"what the firms do" below points to.

## Intent

Build My Version is an AI consultancy in a browser that tells the truth: it
agrees the question, asks until it has every fact, tests every explanation
including the client's own, gives an answer where every figure is the
client's or marked as ours, then writes the plans and draws the system
screen by screen.

The owner's bar: a client must never think "I could have got this from
ChatGPT". The research shows what the big firms sell is not documents but
traceable judgment: a number built from the client's own data, the
benchmark named, every assumption marked as the firm's own on the page, the
range explained, every source checkable, and a story the client challenged
before the final version existed. That is the product Roy described from
the start. This design makes it true on every page, every run.

Two findings from the research set the priorities. The failures clients
actually caught in 2025 and 2026 were checkable facts, not style. And in the
BCG and Harvard experiment, AI made consultants' write-ups read better while
cutting correctness from 84% to 60 to 70% on the one task that required
combining a spreadsheet with interviews. So: proof over polish.

## Goals

1. Every number on every client surface (screen, PDF, deck, email) carries
   one of four tags and cannot be printed without it: **theirs**,
   **derived** (arithmetic on theirs, working shown), **ours** (our
   proposal), **reference** (an outside benchmark with a named source).
2. The package has three tiers: a one-page answer, a register of every
   recommendation with value, cost, owner and timing that adds up to the
   headline, and the full proof behind it.
3. Every page of the proof follows the firm's page rules: a one-sentence
   title that states the finding, one exhibit that proves it, footnotes,
   a source line, a stamp that says how sure we are.
4. The thinking is deeper than the client's own words: derived facts about
   their business, sourced references, options with a costed "do nothing",
   a sensitivity on the key assumption, and an expert panel that writes.
5. The client sees and challenges the storyline before the documents are
   written.
6. While it happens, the client watches facts land in a live case file and
   is told why each question is asked, in their own nouns.
7. When our side breaks, the client sees it in plain words, the team is
   emailed the same minute, and the run stops. Nothing canned ever stands
   in for work we did not do.

## Non-goals

- Anything after the client has the files: pilot tracker, weekly log,
  partner link improvements. Out of scope by the owner's decision.
- The retired backend preview generator and `bmv-core`.
- Cost reduction. The owner's instruction is the best output at any cost.
  Usage is still logged per call as today.

## Anti-goals (a failure even if it works)

- A number on any surface without its tag and source.
- Canned content presented as work for this client (a "front-desk AI"
  fallback, stock interview questions, invented pain points).
- Bulk. Four volumes nobody reads is the incumbents' failure mode. Size is
  bounded by what the business needs, never a fixed count.
- A "try again" message, or raw exception text, when the fault is ours.
- Generic nouns ("Customer", "Item 1", "Pilot Review Queue") where the
  client has a word of their own.
- The method, including that an AI did the work, hidden. It goes on the
  method page, early, in plain words. Deloitte buried it on page 58 of 273
  and it became the story.
- A screen or page that clips, or text cut mid-word anywhere.

## Constraints

- Stack as it is: `consultant-service` (FastAPI, SQLAlchemy, Jinja prompts,
  reportlab PDFs, python-pptx decks, Chromium for the drawn screens) and
  `frontend` (React, Vite). The shipping path is the pipeline under
  `app/pipeline`, `app/routers`, `app/prompts`, `app/screens`.
- Everything that should vary per business is bounded with a minimum and a
  maximum in `app/config.py`, never fixed.
- No invented figures. The four tags above are the whole law.
- Models through OpenRouter. The thinking stages (derived facts review,
  diagnosis, options, expert panel, partner review) run on the strongest
  reasoning model available on the key; formatting stages stay cheap.
- All work runs through the scan, edit, verify workflow with independent
  verification before anything is reported done. Deploys and pushes wait
  for Roy.
- Never read or print secrets; the tests' stubs stand in for the provider.

## The decided how

Built in this order. Each step is shippable on its own and is verified
against the project's checks and the acceptance tests named under it.

### Step 1. Honesty first

What changes:

- One failure path in the orchestrator. When a stage raises or the provider
  refuses, the run stops, the request is marked failed with a plain-words
  reason written for the client (never the exception text), and the team
  is emailed the same minute with the reference, the stage and the error.
  A new mailer function carries this. The client page says, in effect:
  "Our side failed at the step where we [write the roadmap]. Roy has been
  told. You will hear from us; nothing is lost." Copy is written per stage,
  not one generic line.
- The three canned fallbacks are deleted: the consult "front-desk AI"
  recommendation, the analysis pain points, and the stock interview
  questions. A failed interview round says the step stalled and offers to
  resume, never "that's everything we need".
- A hypothesis test that crashed on our side is shown as "we couldn't run
  this test", never "couldn't check with your figures". The `not_tested`
  flag already written is read and rendered.
- A failed business breakdown (decompose) stops the run; it no longer
  continues to a "done" package.
- The "we'll email you" promise is shown only when the mail layer reports
  it can send, and a failed send is treated as a failure of ours.
- The building screen's document list is read from what the run produced,
  not a fixed list of six.
- The method page in every package states, as a matter of record and in
  plain words, how the work was done: that Build My Version's analysis
  system produced it, which figures came from the client, which checks ran
  and passed, and what was not verified. It is written as a statement of
  method, never as a disclaimer. No human review is required and no
  reviewer is named; the existing optional review gate stays as it is.

Acceptance: a provider refusal injected at each stage produces the client
page, the team email, a stopped run, and no canned text anywhere in the
database for that request. A test per stage.

### Step 2. Typed figures, end to end

The spine of everything after it.

- A `Figure` carries: value, unit, period, kind (`theirs | derived | ours |
  reference`), source (for theirs: the interview turn or file and cell; for
  derived: the working as a list of figure ids and the operation; for
  ours: the proposal note; for reference: the publication, year,
  population and URL), and a display precision. Theirs is shown exactly as
  given; derived and ours are shown rounded with "~" where the firm
  convention applies; reference shown as the source gives it.
- Every number that reaches a client surface is a `Figure`. Prose from the
  model is checked: the figure checker is rebuilt so that word numbers
  ("twelve", "a dozen"), multipliers ("3x", "3×"), ordinals and small
  numbers are all caught; the "under 13 passes" leniency on screens goes.
  A number the model wrote that matches a known figure is replaced by that
  figure's literal value, never left at the model's rounding.
- A rendering rule, enforced in code in the PDF, deck, screens and web
  renderers, refuses to print a number that is not a `Figure` with a tag.
  It is a release law, not a prompt instruction.
- The case file (facts the client gave) becomes the single store of
  `theirs` figures, with the vocabulary map from Step 6 attached.

Acceptance: a package rendered from a fixture with one untagged number
fails the release law and names the page. The checker's tests cover the
word, multiplier, ordinal and small-number cases that pass today.

### Step 3. The output shape: three tiers

**Tier 1, the answer page.** One page, printed first in the PDF, first in
the deck, and shown as the first screen of the result. It contains: the
question as agreed with the client; the answer in two lines; the three
numbers that carry it, each tagged; what the client believed and what the
test said; what to do Monday; what we would not do; and a "what this rests
on" line: how many figures are the client's, how many derived, how many
references with sources, how many checks passed. Written last, from the
register.

Trust on this page comes from what was checked, never from hedging. The
owner's rule: the client must feel the system gives them something trusted.
So the answer page carries no confidence sentence, no "AI" caveat and no
"not sure" language; where a number is a range, the range and its reason
are shown, which is how a firm states precision.

**Tier 2, the recommendation register.** One table: recommendation; what it
changes; value as a range with the flex rule; cost; owner by role in the
client's words; timeframe (short, medium, long as the business measures
it); what it depends on. The ranges add up to the headline number on the
answer page and the sum is checked in code. This table is also the input
to the roadmap and the deck's plan slides, so the three can never
disagree.

**Tier 3, the proof.** Sections sized by the business (bounded, never a
fixed count): the fact base; what is actually wrong (diagnosis, with the
client's explanation struck out and the reason); the options and the
do-nothing case; the case for the recommended option with sensitivity; the
plan; the system, screen by screen, presented as how the plan is run;
the appendix (sources table, method page, what we could not verify). The
system volume still exists; it moves from headline to enabler. If the
diagnosis says do not build, there are no screens and the package is still
complete.

**Page rules, enforced by a presentation law on every rendered page:**

- The title is one sentence stating the finding, at most two lines, never
  shrunk to fit; if it does not fit, the page splits.
- One exhibit per page that proves the title. Exhibits are drawn in code
  from `Figure`s (bar, column, waterfall for the prize, driver tree,
  option scoring matrix, 90-day plan, KPI baseline-to-target table, their
  week as a grid), numbered "Exhibit n.m", each with a one-line takeaway.
  The model never draws a chart.
- The foot of the page, in this order: numbered footnotes (definitions,
  what is excluded, "Assumes ..."), a Note line (abbreviations, key
  assumptions), a Source line naming each source separated by semicolons,
  ending "BMV analysis" when the number is ours or derived.
- A stamp top right where it applies: ESTIMATE, PRELIMINARY, ILLUSTRATIVE,
  SAMPLE DATA (every drawn screen keeps this), FOR DISCUSSION (options).
- Number format carries meaning: theirs exact, derived and ours rounded
  with "~", ranges with the flex rule in a footnote.
- Nothing is sliced. Text that does not fit reflows, splits the page, or
  shortens by rewriting through the model with the limit stated; captions
  and names are never cut by character count. Every page, including the
  proposal pages, is measured in the browser before it ships.

The deck follows the same storyline: answer page, register, one exhibit
per slide with the same titles and foot, screens as "how the plan runs".
The deck and the document are rendered from one storyline object, so a
title cannot differ between them.

**The client receives six named files and a ZIP of all of them**, decided
by the owner: separate, substantial files read as professional when each
has a reason to exist. All six render from the one storyline object, so
titles and numbers cannot differ between them.

1. **The blueprint** (PDF): the answer page, the register, then the proof:
   the fact base, what is actually wrong, the options and the do-nothing
   case, the case for the recommended option with its sensitivity, the
   plan in outline, and the sources and method pages.
2. **The technical plan** (PDF).
3. **The operations manual** (PDF).
4. **The roadmap** (PDF): the ninety-day plan, owners, KPIs from baseline
   to target, risks, and the governance cadence.
5. **The system, screen by screen** (PDF, plus the live viewer on the
   site). Absent when the diagnosis says do not build.
6. **The deck** (PPTX): the same story in slides, one exhibit per slide.

Two conditions hold for every file. Each opens with the answer page, so
whichever file is opened first gives the decision. The register lives in
the blueprint and is referenced, never repeated, in the others. And each
file is sized by the business: a six-page operations manual for a
one-person studio is six pages, never padded to look like a volume.

The download shelf, the ZIP and the review editor read the list of
rendered files rather than a fixed set, so the list can change by
configuration if the owner revises it after seeing real packages.

Acceptance: fixtures at the minimum and maximum bounds render without a
clipped page or a cut caption; the register sums to the headline; every
page passes the presentation law; a reviewer can read only the titles of
the proof and get the argument.

### Step 4. Deeper thinking

- **Derived facts stage**, before the diagnosis. Code computes what their
  figures imply (capacity per period, revenue per unit, lost revenue from
  unfilled capacity, break-even fill, cost per lead, and whatever the
  method library yields for the business shape), each a `derived` Figure
  with working. The model proposes which derivations matter; the
  arithmetic is never the model's. These seed the hypotheses and the
  exhibits.
- **Reference layer.** A research stage gathers benchmarks for the sector
  and question from two sources: live web research through a search
  provider (a new vendor and key, approved by the owner), and a curated
  reference library per sector that Roy maintains and that is cited the
  same way. The honesty rule for references: the model may propose a
  source, but code fetches the page, confirms the figure is on it, and
  records the URL, publication year and population before a `reference`
  Figure may exist. A citation the model reports but code cannot confirm
  is dropped. That is the mechanism that keeps us out of the Deloitte and
  PwC failure. The library starts empty and Step 4 ships with it empty;
  until it fills, the only benchmark on a page may be the client's own
  data. Benchmarks are shown next to the client's number, never in place
  of it, and the first benchmark is always drawn from the client's own
  data (their best day against their average day) before any outside one.
- **Options stage**, after the diagnosis and before the recommendation.
  Two to four options including "do nothing" costed over the same
  horizon. Criteria stated first, independent of each other, scored, and
  presented FOR DISCUSSION. The recommended option carries a sensitivity:
  the key assumption moved by a stated amount, and what happens to the
  prize and the payback.
- **Expert panel that writes.** Three lenses (operations, money,
  customers and people) each produce findings through the consulting
  methods already in the repo's engine library (issue tree, cost-benefit,
  scenario, option evaluation, risk and control, KPI design, operating
  model). A synthesis step resolves where they disagree and records the
  disagreement. The existing challenge round stays.
- **Partner review pass.** Before rendering, a reviewing model reads every
  section against four questions: is the title a finding; does the
  exhibit prove it; is every number tagged; what is the "so what". A
  section that fails is sent back once with the reason; a second failure
  is reported, not patched.
- The "ChatGPT test" as a release law: a paragraph of the proof that
  cites no `theirs`, `derived` or `reference` figure and no fact from the
  case file is flagged, and the package is a draft until it is fixed or
  removed.

Acceptance: on the benchmark set in `tests/engine/benchmarks`, every
package shows at least one derived fact the client did not state, one
sourced reference, an options page with a costed do-nothing, and a
sensitivity line; the ChatGPT-test law fires on a fixture paragraph that
could be about any business.

### Step 5. The client challenges the story first

After the answer and before the documents are written, the client sees
"the story": the titles of every section of the proof in order, the draft
register, and the three numbers. Each title can be accepted, questioned
("this isn't right because ...") or struck. The client's words go back
into the case file as facts or as objections to test. Then the documents
are written.

The run waits for the client at this step, bounded. The request sits in a
new "story" state until the client responds, presses "write it now", or a
wait bound in config expires (default 30 minutes), after which the
documents are written as drafted. One challenge round by default; the
maximum rounds is a bound in config. The waiting state is excluded from
the concurrency valve that counts generating runs, and the building
screen's email promise is made when writing actually starts.

Acceptance: an objection on a title changes the written section, and the
objection and the response appear in the appendix.

### Step 6. The experience while it happens

- **Live case file.** Beside the conversation, the facts landed so far
  (each a `theirs` Figure with the turn it came from), the gaps still open
  and why each matters, and the client's own explanation shown as "one we
  will test". It fills as they type. The API for it exists and is unused
  today; it is wired, extended for gaps and the explanation, and the week
  grid is mounted.
- **Why we ask.** Every question carries one line on what it is for, in
  the client's nouns.
- **Vocabulary map.** Early in the interview we capture what they call
  their customers, staff, units of work and places, and every surface
  after that uses those words. "Customer" on a chat screen for a clinic
  becomes "patient" because the map says so, not because a prompt asked
  nicely.
- **One time promise.** The durations shown (door, brief, thinking) are
  either measured from recent real runs and shown as "usually about", or
  not shown. Three different numbers on three screens is a defect.
- **Files.** A dropped file shows what we read from it, as `theirs`
  Figures with the cell or line they came from; a failure to read it is
  reported as our failure, not as "no figures found".
- **Their words intact.** The client's own answers are echoed whole.

Acceptance: a scripted interview shows every fact landing in the case
file with its turn; the vocabulary map's nouns appear on the drawn screens
and in the documents; no client-facing string in the interview contains a
sliced echo.

### Step 7. The whole website, mobile and desktop

The same rules apply to every page a visitor or client can reach, not only
the consultation. Each earlier step builds its own frontend responsive from
the start (a phone at 390 px and a desktop at 1440 px are both first-class);
this step is the sweep over everything else and the proof that it holds.

- **Public pages** (landing, solutions, about, private-ai, nav, footer,
  FAQ and any component still mounted): rewritten to say what the product
  now is, in plain words, with no figure that is not true. The landing
  card showing 12, 84%, 6 and 3x is replaced with something real or
  removed. The footer that still sells "share a tool you admire" and
  "custom MVP" is rewritten. One name for the one main action across nav,
  hero and footer. Package timelines and inclusions on any page are
  labelled as our proposal or removed.
- **Invented social proof goes.** Showcase testimonials, star ratings,
  patient counts and demo dashboards that present invented people or
  numbers are either removed, or kept only if every one is plainly
  labelled sample on the surface itself. Unrouted showcase code, unmounted
  marketing components and the legacy submit and result pages are deleted,
  not left (rule 6). Routes that survive are checked to be reachable and
  to say true things.
- **The consultation on a phone.** The interview, the live case file
  (which becomes a drawer or a collapsible strip on narrow screens), the
  story challenge, the thinking screen, the answer page, the register and
  the downloads shelf all work one-handed at 390 px: no horizontal scroll,
  controls reachable, nothing clipped, no text cut mid-word. The drawn
  system viewer scales or scrolls its frame intentionally on narrow
  screens rather than shrinking text below legibility.
- **Desktop** uses the width: case file beside the conversation, the
  register as a real table, exhibits at reading size.
- **One house style** across public site, consultation and documents:
  type scale, spacing, colour tokens and components shared, so the product
  looks like the documents it produces.
- **Gate.** A browser check renders every surviving route at 390 px and
  1440 px, fails on horizontal overflow, clipped text, a visible raw error,
  or a number without its tag where one is required, and the screenshots
  are kept as evidence. The frontend gains a check command and, with it,
  a CI job (today neither the frontend nor the consultant service has one).

Acceptance: the browser check passes on every surviving route at both
widths; a scripted run through the consultation on a 390 px viewport
completes; a grep for the removed invented figures, testimonials and the
old footer copy returns nothing in `frontend/src`.

## What is left to the builder

- Exact schemas for `Figure`, the register and the storyline object, and
  where they are stored (new columns or tables are fine; the existing
  `_ensure_columns` pattern applies).
- The chart library and the SVG-to-PDF and SVG-to-PPTX path, as long as
  charts are drawn from data in code and look like one house style in the
  web, PDF and deck.
- Template layout details within the page rules; fonts stay IBM Plex Sans
  and Syne as embedded today.
- Prompt wording, within the rules that the model proposes and code
  computes, and that every prompt example figure is clearly an example
  that the checker will catch if copied.
- How research results and the reference library are cached and refreshed.
- Model ids per stage, chosen from what the key offers, strongest for the
  thinking stages.
- Test design for each acceptance line above, including the fixtures at
  the bounds.
- Which of the engine's method modules are imported as libraries first and
  which later, as long as the pipeline remains the shipping path.

## Decided by the owner (2026-10-31)

- The run waits for the client's challenge of the story, bounded.
- A search provider is added for live references.
- No human review is required on a package, and no page carries
  "a human reviewed this" or "the AI is not confident" language. Trust
  comes from what was checked and shown.
- The client receives six named files (blueprint, technical plan,
  operations manual, roadmap, the system screen by screen, the deck) and
  a ZIP, each standing alone and sized by the business.
- The whole website is in scope, including the public pages everyone
  sees, on mobile and on desktop. The builder has the freedom to change,
  rewrite or remove any public page, component or copy that does not meet
  the rules in this document.

## Calls made in this document (check these while reading)

- The pipeline stays the shipping path and the engine's method, calc and
  gate modules are imported into it as libraries. Rewriting the product
  onto the engine is not in this design. Where the engine already imports
  pipeline internals (the PDF renderer, the presentation gate, the r30
  adapter), shared code may be extracted into a leaf package both import;
  engine renderers that break in a step are repaired in the same step.
- The frozen r30 manifest is re-frozen at the end of each shipped step,
  with a commit that says why, as the owner did in `514faec`. Each step
  carries the engine suite green.
- The `Figure` extends the existing registry `Claim` (client input,
  machine computed, consultant proposed) with the `reference` kind and the
  source fields, rather than starting a fourth typed-number system. All
  derived arithmetic runs through the engine's exact calculator.
- The interview gets a server-side session with its own reference, owned
  by the signed-in client, so the case file, the vocabulary map, a stalled
  round and a team email all have something to point at before the
  request row exists.
- Step 4's acceptance runs the benchmark cases through a stubbed, free
  pipeline harness (the dossier answers the interview by script); it
  proves the code-side derivations, references and laws. Paid real runs
  stay behind the existing money gate and run when the owner asks.
- Reference benchmarks come from both the search provider and a curated
  library, both cited the same way, both fetched and confirmed by code.
- The storyline wait bound defaults to 30 minutes; one challenge round by
  default; both bounded in config.
- "Do nothing" is always one of the options.
- The system volume stays in the package and moves from headline to
  enabler; no screens are drawn when the diagnosis says do not build.
- Four tags, not three: `reference` is added to the owner's "theirs,
  derived, ours".
- The method page near the front of every package states how the work was
  done, as a record of method in plain words, not as a disclaimer.
- Page stamps (ESTIMATE, PRELIMINARY, FOR DISCUSSION) stay, because they
  say what kind of number a page holds, as a firm's pages do; no stamp or
  sentence expresses doubt in the system itself.
- Build order is honesty, typed figures, output shape, thinking, story
  challenge, experience, then the whole-site sweep. Each step ships on its
  own, and every step's frontend work is built responsive from the start.
- Deleting the retired public surfaces (showcase demos, unmounted
  marketing components, legacy submit and result pages) is part of the
  sweep, and the backend routes that only served them are listed for the
  owner rather than removed in this design.
