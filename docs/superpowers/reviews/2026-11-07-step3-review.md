# Step 3 review: the output shape (c0ae9a6..43f218a)

Independent review, 2026-11-07. Read-only apart from running tests. Repro scripts: `docs/superpowers/reviews/step3-review-repro.py` (copied from the reviewer's scratch folder). In that file a passing test means the defect was reproduced.

## Verdict: fix first

The parts underneath are sound: the storyline object, the flex and register arithmetic (exact Decimal, shares that must sum to 100), the one server file list, the stage's retry and StageFailed, and the re-freeze all hold. The defects sit in the rendering paths. Every new PDF page, and the whole roadmap file, skips the number law. Model tokens print raw, so a title differs between the PDF and the deck. An exhibit puts invented "theirs" figures into the known set. The share link's JSON carries the owner's own intake words. Runs from before this step change their output. None of this needs a rework of the design, but all of it touches promises the product makes. Three of these were found by the step's own review and parked in the ledger. I judge them load-bearing.

Counts: Critical 3, High 5, Medium 6, Low 9.

## Findings, ranked by severity

### Critical

**C1. New PDF pages and the roadmap file skip the number law, and the stage never checks register words for numbers.**
- Where: `app/storyline/pdf.py:27-76` (answer page, register, proof lead pages: plain `Paragraph(escape(...))`, never `export_pdf._rich`). `app/storyline/roadmap.py:26-78` (the whole roadmap is built with `doc.build` outside any `law.scope`, with no `law.save`, and `roadmap` is not a law document). `app/storyline/stage.py:97-105` (`_accept` checks the register's shape through `assemble` only. `recommendation`, `changes`, `owner` and `cost_needs` are never bound).
- Failure: the model drafts `"recommendation": "Raise the price to $999 a class."` and `"cost_needs": "a quote of $5,000 from the builder"`. The stage accepts both and stores them. The blueprint then prints "$999" (register row) and "$5,000" (the "Not priced yet" footnote). `law.recorded(row)["Volume I"]` is `[]`. The only catch was the deck's `_checked` ("The deck, slide 2: the number $999 ..."), and only because a deck exists. The answer page's believed, tested, Monday and would-not texts, and the roadmap's phases, measures ("From 12 to 20"), risks and decisions, are all printed with no law check either.
- Verified: reproduced (`test_register_words_and_tokens_skip_the_law`: PDF has '$999' True, '$5,000' True, LAW FINDINGS Volume I: []).

**C2. Figure tokens print raw in the PDF and on the web, so a title differs between files.**
- Where: `app/storyline/stage.py:130` stores the raw title and takeaway. It binds them only to measure the title (`:125`). `app/storyline/build.py` `_sections` and `_register_web` pass the raw strings on. `pdf.py:59,75` print them. The deck path binds them through `_add_text`/`_checked`. The prompt (`app/prompts/storyline.j2`) tells the model to write numbers as `{{F:id}}` tokens, so this will happen on most real runs.
- Failure: the stored title is "The class stays full at {{F:CF-04}}". The blueprint prints `The class stays full at {{F:CF-04}}`. The deck prints `The class stays full at $22`. The web register row reads `Keep the price at {{F:CF-04}}.` This breaks "one storyline object so titles cannot differ" and puts template syntax in front of the client.
- Verified: reproduced (`test_title_token_in_each_file`, output quoted above).

**C3. The waterfall exhibit invents figures, mistypes them, and puts them in the known set, so the law vouches for them anywhere.**
- Where: `app/storyline/exhibits.py:133-170` and `_money` at `:252-257`: every step becomes a USD figure whatever the term's unit. A cumulative product is typed `theirs` (with a made-up `TheirsSource`) whenever the current term is a client claim. `app/figures/known.py:354-361` adds `_exhibit_figures(req)` to every `known_for(req)` for any run whose move has terms (all new runs), whether or not any section draws the exhibit.
- Failure, case 1: move terms [12 empty spots a week (claim), $22 price (claim), 0.75 (proposed)]. The waterfall rows read "empty spots a week **$12** yours", then "her price **$264** yours". 12 spots is printed as money, and a product is tagged as the client's own exact number.
- Failure, case 2: terms [$22, $22, 0.75] create `EX-PRIZE-2 = 484 USD, kind theirs`. `bind("Her studio already makes $484 a week.", known_for(row)).unresolved == []`. With the exhibits part left out, it is `['$484']`. So any document's invented "$484" now passes the number law as the client's figure.
- Verified: reproduced (`test_waterfall_units_and_tags`, `test_waterfall_figures_vouch_for_numbers`). Parked in the ledger ("types every step as USD and those figures join the known set"). Load-bearing.

### High

**H1. The public share link's JSON carries the owner's private intake words.**
- Where: `app/routers/shared.py:83` adds `**_storyline_web(req)`. `app/storyline/build.py:208-214` serves `question` (the brief) and `believed` (`req.main_problem`, the owner's own form field), with no `public` handling. `shared.py:65` itself says "none of the owner's own words (questions, quotes, files) is in it".
- Failure: with `main_problem = "My partner Dana keeps losing the bookings and I am thinking of firing her."`, `GET /api/shared/<token>` returns that sentence verbatim in `answer_page.believed`. SharedPage renders it to anyone holding the link. `would_not` can also carry the owner's own hypotheses.
- Verified: reproduced (`test_shared_payload_leaks_main_problem`).

**H2. A run from before this step (answer stored, no storyline) no longer builds as before.**
- Where: `app/storyline/build.py` `build()` returns a Storyline whenever `answer_json` exists. `export_pdf.py:1989-1990` and `:2151` open every volume on the answer page whenever `build_story(req)` is not None. `screens/export.py:52` prepends a page to Volume IV the same way. The deck is the only path gated on `storyline_json` (`export_pptx.py` `_package_story`), so on these rows the PDF and the deck now disagree in shape.
- Failure: for a Step-2 run (answer present, `storyline_json` NULL), page 1 of the blueprint becomes "Should the studio keep the evening class? | You are full. | Keep the class. | What you believed: ... | Monday: ..." where it used to be the cover. `tests/storyline/test_pdf.py::test_a_legacy_run_builds_as_before` cannot see this: it seeds `answer_json=None` and compares the new build with itself, not with the output from before the step.
- Verified: reproduced (`test_legacy_run_with_answer_changes`: build() for a legacy run: Storyline; PAGE 1 shown).

**H3. Volume IV renders in quirks mode for every run with an answer.**
- Where: `app/screens/export.py:52`: `_answer_first(req) + render.proposal_html(...)` puts `<section class="page">` in front of the template's `<!doctype html>` (`templates/proposal.html:7`).
- Failure: Chromium's `document.compatMode` is `BackCompat` for content before the doctype, and `CSS1Compat` for the template alone. Every screen page of the system PDF is laid out under quirks rules. The page measurement and the acceptance tests skip the system file, so nothing catches it. The added "answer page" is also only the question and the rests-on line, not the answer page.
- Verified: reproduced the mode switch with Playwright on the same concatenation shape. I did not build a full Volume IV.

**H4. The DRAFT cover prints the release gate's internal reasons verbatim.**
- Where: `app/pipeline/export_pdf.py:883`: `"; ".join(release_status(req)["reasons"][:4])` goes into a client cover Paragraph, again outside the law.
- Failure: the cover reads "DRAFT. 1 open high finding(s) on the quality bench; 5 document(s) not yet checked against the figures since the last data change". Other reasons this can print include "client-unsafe artifacts: <the artifacts themselves>", "integrity layer: n finding(s)" and the law's own reasons. Those quote the rejected number: the edit to `tests/figures/test_law.py:~392` admits "$9,000" is now "also on the cover". That is internal language and a number the law rejected, both printed to the client.
- Verified: reproduced the jargon (`test_draft_cover_prints_internal_reasons`). The quoted number is read from the test change. Parked in the ledger. Load-bearing.

**H5. The register is not in the files as the spec defines it.**
- Where: `pdf.py:53-62` prints `"{recommendation} {when} {owner}"` per row, run together with no separators, with no range, no cost, no "what it changes" and no dependency. `deck.py:44-52` prints `"{recommendation} {owner}"`. `build._register_web` omits cost, so the cost column (R4) is shown nowhere.
- Failure: the blueprint row reads "Keep the price at {{F:CF-04}}. Week 1 o". The acceptance line "the register sums to the headline" holds only in memory. No file shows the ranges or the headline they add up to.
- Verified: reproduced (PDF register line in `test_title_token_in_each_file`). Parked in the ledger as "print the register without its ranges". Load-bearing.

### Medium

**M1. Exhibits never reach a page in practice, and the page law is not run at render time.**
- `draw_pdf` and `draw_slide` (`exhibits.py`) are called nowhere in `app/`. The PDF lead page prints only the caption (`pdf.py:72-76`). The exhibit is chosen by section id (`week`, `prize`, `grid`, `plan`, `scoreboard`), but the prompt never names those ids (`storyline.j2:11`, "A section has id, title and takeaway"). Real model ids ("fact-base", "diagnosis") will mostly match nothing.
- `pagelaw.check_section` and `pagelaw.pdf_findings` are used only by tests. There is no foot, no stamp and no "Exhibit n.m" (every exhibit id is "1.1"). The Tier 3 page rules exist only as unit-tested functions.
- Verified: read-only (grep of `app/`).

**M2. The deck lays rows out at a fixed pitch with no measuring, and they overlap at the default bounds.**
- Where: `deck.py:52,77,79`. With 14 classes, the default `EXHIBIT_ROWS_MAX=12` shows 11 rows plus "Other classes (3)". Rows J and K sit at 6.10-6.85 in, over the section takeaway box at 6.30-6.80 in. At `REGISTER_ROWS_MAX=12`, the register rows reach 7.66 in on a 7.5 in slide.
- The deck also prints the raw label "Other classes (3)", not the law-safe `drawn` text. The acceptance check `_deck_overflows` measures each box alone, so it cannot see overlaps or boxes past the slide edge.
- Verified: reproduced (`test_deck_exhibit_rows_overlap`, box positions above). Parked ("many rows"), but it happens at the default config.

**M3. `STORYLINE_SECTIONS_MAX` is defined and never enforced.** The stage keeps every section the model returns (`stage.py:108-131`). Nothing bounds the number of lead pages or slides. This breaks "nothing that varies per business is fixed or unbounded". Verified: read-only (grep: config.py only).

**M4. New deck code cuts text by character count.** `_screens_for_the_plan` (new in `export_pptx.py:~355-386`) runs the screen description, AI rationale and tracks through `_fit`, which is `_clamp` to an estimated character count. That breaks "nothing is cut by character count". Verified: read-only.

**M5. The release stamp reads earlier builds from disk, and the roadmap has no stamp or law record of its own.**
- `_presentation_reasons` (`export_pdf.py:~655-678`) judges the PDFs already on disk. `build_pdf` decides its stamp before writing. So a file that clips is first stamped FINAL. The next volume built for the same ZIP reads the clipped file and is stamped DRAFT, giving one ZIP with mixed stamps.
- The roadmap's cache (`roadmap.py:38-41`) checks file time only, never the stamped state, so its DRAFT/FINAL can go stale (parked).
- Verified: read-only.

**M6. Volume IV and the deck do not open with the answer page.** Volume IV gets the question and the rests-on line only (`screens/export.py:56-68`). The deck's first slide has the question, the answer lines and the rests-on line, with no numbers, believed/tested, Monday or would-not (`deck.py:32-42`). This breaks the spec's "Each opens with the answer page". Verified: read-only.

### Low

- **L1.** `build_zip.skipped` is a process-wide function attribute (`requests.py:1391`). Two concurrent ZIP requests can send each other's `X-Skipped` header. The shared route reads it too. Read-only.
- **L2.** Progress runs backwards: storyline emits 62, quality emits 61 (`orchestrator.py:435,439`). Read-only.
- **L3.** The rests-on line prints no counts, against the spec ("how many figures are the client's..."). This is ruled in the ledger. It needs Roy's decision, or counts made into figures. Read-only.
- **L4.** "The sum is checked in code" is true only by construction. `assemble` never checks that the row ends add up to the headline at runtime. The displayed rounded ends ("~$X") need not add up visually. Read-only.
- **L5.** Test gaps. The legacy test compares a file with itself (see H2). The "large" acceptance fixture uses 8 rows and 8 short titles, not the config maximum (12) or long titles. `_deck_overflows` cannot see overlaps (M2). No test covers the share-link JSON for owner words. Read-only.
- **L6.** Leftovers in the frontend commit (b53f518, committed tree). StudioPage still says "Download your full plan (ZIP — all three volumes)" (`StudioPage.tsx:1298`), and its deck button reads `preview.deck_available`, not the file list. With `files` present, the shelf loses the system "View" action, the AI-team book and the roadmap scroll. `studioPdfUrl` still builds `/export/pdf/{kind}`. `StudioExportKind = string` works: 'pptx' keeps its old route and every other key goes to `/export/{key}`. SharedPage does show the answer page first, then the register, then Package. Read-only.
- **L7.** A roadmap measure with no baseline or target prints "Metric. From  to ." (`roadmap.py:126`). That is a part with no data filled with an empty sentence (parked). Read-only.
- **L8.** The register is re-assembled from the model's raw rows on every read (`build._register`, `register.figures_for`). The integrity layer runs after the storyline stage. If anything later changes the plan phases or the figures, the register and its REG figures vanish silently, with no failure raised. Every `known_for` call also re-runs `assemble`. Read-only.
- **L9.** The targeted set is flaky: each run failed a different test, all caused by "document(s) not yet checked since the last data change" or the file-time cache. Every one passes alone. The runs shared the machine with the full suite. Not attributed to Step 3 (see Tests).

## Parked items judged (ledger)

- New PDF pages drawn with Paragraph, so titles keep tokens and register words go unchecked: **load-bearing** (C1, C2; reproduced).
- Prize exhibit types every step as USD and its figures join the known set: **load-bearing** (C3; the law accepts invented "theirs" numbers).
- The draft line on the cover quotes the gate's reasons: **load-bearing** (H4; internal words and rejected numbers on a client cover). The fix is small.
- The roadmap is served from its file time, not the release stamp: **load-bearing together with C1**, because the roadmap has no law record either. Alone it would be acceptable.
- A deck exhibit can run past the slide with many rows: **load-bearing** (M2; it already overlaps at the default bound).
- The PDF and the deck print the register without its ranges: **load-bearing** (H5; Tier 2's whole point).
- A roadmap measure with no baseline still says "From": **acceptable** to ship (cosmetic).
- Ruling, the rests-on line without counts: acceptable as a ruling, but it is a spec deviation for Roy to decide.
- Ruling, release clipping only for storyline runs, and the cover panel words ignored: acceptable.
- Ruling, roadmap length instead of "ninety days": acceptable.
- Not in the ledger at all: H1 (share-link leak), H2/H3 (legacy change, quirks mode), M1, M3, M4, M5 (mixed stamps), M6.

## Tests I ran (cwd `consultant-service`, `.venv` python, `-p no:cacheprovider`)

1. `pytest tests/storyline tests/figures/test_law.py tests/figures/test_acceptance.py tests/test_consultancy_layers.py --basetemp=D:/bmv-pytest-tmp-review -rf`: `1 failed, 277 passed, 1336 warnings in 131.56s (0:02:11)`. FAILED `tests/test_consultancy_layers.py::test_repaired_findings_release_the_gate` (`assert 'draft' == 'final'`).
2. That test alone: `1 passed, 12 warnings in 1.77s`.
3. `tests/test_consultancy_layers.py` alone: `91 passed, 452 warnings in 26.99s`.
4. `tests/storyline` plus that test: `76 passed, 459 warnings in 46.47s`. `tests/figures/test_law.py tests/figures/test_acceptance.py` plus that test: `113 passed, 449 warnings in 32.02s`.
5. storyline, figures and that test, with a probe printing its release reasons: `188 passed, 896 warnings in 116.85s`.
6. Run 1 repeated with the probe: `2 failed, 276 passed, 1347 warnings in 131.68s (0:02:11)`. FAILED `tests/figures/test_law.py::test_a_cached_volume_still_reports_its_findings` (cache mtime) and `tests/figures/test_acceptance.py::test_the_same_blueprint_without_the_number_is_not_a_draft_because_of_the_law` (`'1 document(s) not yet checked ...'`). The test that failed in run 1 passed this time. These are timing flakes, run while the full suite ran elsewhere. I did not check whether they flake before Step 3.
7. `tests/engine/test_engine_r30_frozen.py tests/engine/test_engine_mutation_manifest.py`: `3 failed, 34 passed, 1 skipped in 0.78s`. The 3 are the baseline mutation-manifest ids. `git log -1 --format=%h 43f218a -- app/pipeline app/prompts tools 'tests/*.py'` gives `98a46f3`, which matches the manifest constant. The re-freeze matches the tree.
8. Reviewer repros (`repro/test_review_repro.py`, `-p tests.conftest`): `6 passed, 45 warnings in 3.85s`. Then `test_title_token_in_each_file` gave `1 passed in 1.82s`, and `test_waterfall_figures_vouch_for_numbers` gave `1 passed in 0.87s`. Every one reproduced its defect.
9. Playwright `document.compatMode` check: `with answer first: BackCompat`, `template alone: CSS1Compat`.

## What I did not check

- I did not build Volume IV end to end (it needs a screens payload). The quirks-mode finding comes from the concatenation shape only.
- I did not run the frontend `tsc` or `lint`: the working tree holds uncommitted frontend changes that are out of scope. I did not run the Playwright visual evidence. Frontend files were read from the committed range.
- I did not run the full suite (it was running elsewhere), and I did not check the targeted flakes against c0ae9a6.
- I did not test the deck's law on a raw token in a register row beyond the one repro, or check the TOC entries the new `h1toc` headings add.
- I did not measure the cost of `release_status` reading up to four PDFs with PyMuPDF on every call.
- I did not check the integrity layer for rewriting `action_plan_json` after the storyline stage (L8 is reasoned, not shown).
