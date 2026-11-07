# Step 3 ledger

Rulings made while executing `docs/superpowers/plans/2026-11-01-step3-output-shape.md`. The spec wins where it and the plan disagree.

Ruling: commit messages say why and do not carry a Claude co-author line - this session is not that model, and a trailer naming someone else would be false - history lacks the trailer the plan asked for.

Ruling: the roadmap states the plan's real length (plan R7), not a fixed "ninety days" - the spec names a ninety-day plan and also says each file is sized by the business; a six-week plan called ninety days would state a length it does not have - Roy may still want those words as the file's name.

Ruling: the answer page is assembled when the package is rendered, from what the run already stored (plan R1), and the register is computed from the headline so its ranges add up to it - the spec says the page is written last, from the register, which is when it is composed, not a new model call that rewrites the answer from the rows - the answer is not rewritten from the register's wording.

Ruling: Task 4 creates `pagelaw.title_lines` and Task 6 adds the rest of the page law to that module - the stage has to measure a title before the page-law task, and the user order runs Task 4 first - the module appears one task early.

Ruling: Task 10 introduces `roadmap.build_roadmap_pdf` only far enough for the zip to contain a real file, and Task 8 replaces the body with the full roadmap - the zip test requires the file and the user order runs Task 10 before Task 8 - one commit has a thin roadmap that the next task fills in.

Ruling: `release_status` records a clipped page, and names that page, only for a run that has a storyline - the plan adds presentation and clipping findings to every release; the volumes' cover is drawn outside the body frame on purpose and they use base faces, so folding those findings in stamps every current clean file DRAFT - a run with no storyline stays final exactly as it is today.

Ruling: the cover panel's own words (the wordmark and the volume numeral) are not a clipped page - they are painted on the navy panel, left of the body frame, on purpose; counting them would stamp every storyline file DRAFT - a line of the register or the answer that actually leaves the frame is still a finding.

Parked after the whole-step review, not fixed in this pass: the new PDF pages are drawn with Paragraph rather than the number-law path, so a title can still carry a figure token and a register word is not checked; the prize exhibit types every step as USD and those figures join the known set for a run that has terms; the draft line on the cover quotes the gate's own reasons; the roadmap is served from its file time and not from the release stamp; a deck exhibit can run past the slide when it has many rows; the PDF and the deck print the register without its ranges; a roadmap measure with no baseline still says "From". Each of these needs its own test before a fix.

Ruling: the storyline acceptance file is `tests/storyline/test_output_shape.py`, not `test_acceptance.py` - `tests/figures/test_acceptance.py` already has that name, and the default importer cannot load both; importlib mode breaks the engine tests that `import conftest` - the plan's file name is the only thing that moved.

Ruling: the page law measures a PDF on the pipeline's body frame and ignores the cover panel's own words - `release_status` already does both, and a law that counted the panel would fail every clean volume - a line of the answer that leaves the frame is still a finding.

Ruling: the rests-on line names the kinds that are there and does not print the counts - the plan's sentence is "n figures are yours, n worked out", and a count is a number the known set has no figure for, so the number law rejects it - the client does not see how many of each kind.

## Fix pass after the independent review (2026-11-07)

Ruling: a run is a storyline run only when it stored a storyline (`storyline_json`), not when it stored an answer - the review's H2: every Step-2 run opened its files on an answer page it never had, while the deck was already gated this way; one gate in `build()` keeps the PDFs, the roadmap, Volume IV, the deck and the web in agreement - a Step-2 run shows no answer page on the web either until it is rerun.

Ruling: the register's flex footnote is declared to the number law as a phrase our code prints (`register.phrases`, through `document_phrases`), not by adding the flex percent and the assumption as figures - a figure of 20% or 75% in the known set would vouch for any "20%" the model writes anywhere; the phrase covers only that exact sentence - a footnote reworded in code must keep `register.phrases` in step or it becomes a finding.

Ruling: the share link's answer page leaves out the question, what the owner believed, the test of that belief and every hypothesis, and keeps "why not the others" - those four are the owner's words or restate them; our reason for the other options is ours - a partner sees the answer without what it answers.

Ruling: a waterfall step is the client's own figure when it is one of their terms alone, the move when it is the move's number and kind, and otherwise a worked-out product (our estimate once an assumption of ours is in it) in money once money is in it, or in the one unit its terms share; a step whose unit cannot be said has no figure and is drawn as words - only an exhibit a stored section draws adds figures - a derived product still vouches for its exact value in any text of that run, as every worked-out figure does.

Ruling: the roadmap is a document of the release law ("The roadmap", after Volume III), so the package now has six law documents and `LAW_RULES` is 2 - the brief asks for the whole roadmap through a law scope with its own record; without a place in `DOCUMENTS` its findings could not hold the release - every record and cached file made under rules 1 is stale once.

Ruling: the DRAFT cover names a file and a page, and when the law found a number in the volume being built, the volume is laid out a second time so its own cover can name that page - the cover is drawn before the pages exist; a reason with no page names only the file - a draft volume with findings costs a second layout.

Ruling: the register's row numbers and its "After 1" dependency cells are drawn by code (`DrawnCell`, drawn deck boxes), not read by the law - they are positions code computes from the row order, like page numbers - a model word can never reach those cells.

Ruling: the deck measures every box with Helvetica widths times 1.1, a face wider than the deck's Segoe UI, and continues a slide under the same title when the next box would pass 7.0 in - python-pptx cannot measure the real face; measuring wide leaves room rather than overlap - a slide may hold a little less than it could.

Ruling: a proof section's foot and stamp are composed from its exhibit's own tags: a Note line and "Source: <the exhibit's source>; BMV analysis" when a number is worked out or ours, and ESTIMATE when one is ours; sources are named in client words ("Your week", "Your figures") - the model writes only the title and takeaway - footnotes stay empty until Step 4 brings definitions and exclusions.

Ruling (L8): a stored register that no longer assembles is a release reason ("the register no longer checks out") rather than a stored copy of the assembled register - the register stays computed from what the run holds now, and the change is said instead of the table vanishing - a run whose cited figure was removed is DRAFT until the plan summary is written again.

Ruling: a zip asks its stamped files (the volumes and the roadmap) for their file again, up to three passes, until none is rebuilt - each file is served from disk only while its stamp is still the package's, so the passes converge on one stamp - a zip whose first file is stamped before a later one clips costs one rebuild of the earlier files.

Ruling (L3): the rests-on line keeps naming kinds without counts, as ruled above - it is Roy's decision.

Ruling: this pass's commits carry the trailer the caller asked for (`Co-Authored-By: Claude Opus 5.5`) - the earlier ruling about trailers was about a different session - history now has both.

Parked: the exhibit's group row says "Other classes", a studio's word; the bars use the week's own unit, but the group name is not yet the business's own noun.
