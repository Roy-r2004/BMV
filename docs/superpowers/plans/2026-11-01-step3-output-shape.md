# Step 3: The Output Shape Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every client package opens with a one-page answer, carries one recommendation register whose ranges add up to the headline, and arrives as six named files plus a ZIP, all drawn from one storyline object, so that titles and numbers cannot differ between files.

**Architecture:** A new package `consultant-service/app/storyline/` (not frozen, no top-level engine import) holds the storyline object, the register, the exhibits, the page law, the roadmap and the file list. The answer page is built in code from columns the pipeline already stores. One new small model stage (`storyline`) writes only what code cannot: register row wording, owner roles, each row's share of the prize, and the action title and takeaway of each proof section; every number in it is a `{{F:id}}` figure token bound by `app/figures`, and every range and sum is computed in code with exact `Decimal`. The existing PDF and deck builders gain hooks that render from the storyline; the frozen files they live in are edited on purpose and re-frozen in the last task.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/SQLite, reportlab (PDF, `reportlab.graphics` for exhibits), python-pptx (deck), PyMuPDF (page checks), Jinja prompts, React 19 + Vite + TypeScript, Playwright with a mocked API for the visual checks.

**Spec:** `docs/superpowers/specs/2026-10-31-package-to-a-firms-standard-design.md`, section "Step 3. The output shape: three tiers" (lines 161-254), and the owner's decisions at the end of that file. Recon: `docs/superpowers/plans/2026-11-01-step3-output-shape.recon.md`. Step 2's typed figures are the base: `app/figures/{model,read,bind,calc,casefile,known,law,payload}.py`.

**Review depth (agreed with Roy, 2026-11-01):** one task review per task and at most one scoped re-review; one adversarial pass over the whole step at the end; low-severity findings parked in the ledger, not fixed in rounds. Deploys, pushes and merges wait for Roy; Roy tests locally after Step 7.

## Global Constraints

- No invented figures. Every number on a new page is a `Figure` in the known set (kinds `theirs`, `derived`, `ours`, `reference`) and goes through the number law (`law.check` via `_rich` in PDFs, `_checked` in the deck, `finalize` in Volume IV). Sample data stays a labelled region, never a fifth kind.
- No hedging language: no confidence sentence, no "AI is not sure", no "requires validation", no "human review". Trust comes from what was checked: the "rests on" line and the failures the law names. Where a number is a range, show the range and its reason.
- Nothing that varies per business is fixed: row counts, section counts, exhibit rows, flex are bounded by `app/config.py` min/max settings (`_env_int_within` pattern).
- Nothing is sliced: no character-count cut of a caption or name. Text that does not fit reflows, splits the page, or is rewritten through the model with the limit stated; a title is never shrunk to fit.
- Fail honestly: a stage that cannot finish stops the run with a named reason (`StageFailed`), as Step 1 set it up. A part with no data is absent, not filled.
- Plain client language in every printed and shown word (no "stage", "claim id", "Figure").
- Frozen set (`tests/engine/r30_manifest.json`): `app/pipeline/**`, `app/prompts/**`, `tools/**`, top-level `tests/*.py`. Edit them only where a task says so; Task 12 re-freezes. Names the engine imports from `export_pdf.py` and `export_pptx.py` (recon file, "Constraints") must keep working.
- Match the surrounding code's style. Small commits, messages that say why, ending with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Python for tests: `consultant-service/.venv/Scripts/python.exe -m pytest ... -p no:cacheprovider`; add `--basetemp=D:/bmv-pytest-tmp` for the whole-suite run (the repo is on D:, the default temp on C:). Frontend: `npx tsc --noEmit -p tsconfig.app.json` and `npm run lint` (14 old warnings, 0 errors).

## Rulings (made while planning; each costs rework if wrong)

- **R1. The answer page needs no new model call.** Question, two-line answer, numbers, "what this rests on" all exist in stored columns (`brief_json`, `answer_json`, `known_for(req)`, `qa_report_json`, `integrity_report_json`, law findings). Cost if wrong: a thin page for legacy runs; they simply lack parts.
- **R2. One new stage, `storyline`, writes only wording and shares.** Values are never written by the model. Cost: one more paid call per run (small).
- **R3. Value ranges come from our own assumptions only.** The headline move is recomputed in code with each `proposed` term (ours) flexed by `VALUE_FLEX_PCT` either way; terms that are the client's stay exact. A row's range is the headline range times its share. Shares are ours (tagged "our estimate") and must sum to 100. If the move holds no assumption of ours the range collapses to the exact value and the footnote says so. This makes "ranges add up to the headline" true by construction and still checked in code. Cost if wrong: Roy may prefer rows with their own computed values; that needs per-row move terms (a later step).
- **R4. Cost is a figure or a named gap.** A row's cost is a known figure the model cites, or the plain line "Not priced yet: needs <the input>". The model is never asked for an amount (decompose already forbids coined investments).
- **R5. Proof sections keep their existing narrative.** Each proof section of the blueprint gains a lead page (action title, one exhibit, takeaway, foot); the existing text flows after it. Rewriting every body page to one-exhibit-per-page is not attempted. Cost: body pages carry no exhibit. Option and do-nothing sections, the driver tree and the option matrix wait for Step 4's data; the storyline accepts optional sections so they slot in.
- **R6. Whole-page checks reuse the engine's measurers.** `presentation_findings` and `clipping_findings` (engine gates) run on every built PDF and their findings become release reasons; title length is checked with reportlab `stringWidth` before drawing.
- **R7. The roadmap file is as long as the plan.** `PLAN_WEEKS_*` bound the plan (default 6 weeks, max 12 by config); the file says "The roadmap" and states the plan's real length, never "ninety days" when it is six weeks. Governance cadence is built from the scoreboard's per-metric review rhythm because the pipeline stores no other.
- **R8. Files come from one server list.** `files_for(req)` returns key, title, filename, kind, available and the plain reason when absent; the shelf, ZIP, shared route and progress poll all read it. The review editor still edits only the blueprint and technical markdown; it lists the files its save rebuilds.
- **R9. Hedging words come out only where their job is to say the system is unsure** (`BMV_STATEMENT`, "REQUIRES VALIDATION", "Prepared by BMV AI", "AI-native consultancy", `ai.confidence` on the deck, "What we estimated or couldn't check."). The honest labels on numbers that are ours ("our estimate", "(proposed ...)" ) stay.

## Review Focus

Inputs the spec implies but no task's tests would otherwise exercise, most likely first. Each has its pinning test in the owning task.

1. A legacy or sparse run (no `storyline_json`, no move terms, no brief): files still build, the answer page shows only the parts that exist, no crash, no invented number. (Tasks 2, 7)
2. The diagnosis says do not build: no system file, no screens, the shelf and ZIP are still complete and the answer page does not mention a build. (Tasks 2, 10)
3. The smallest business (one-person studio, few figures): a six-page operations manual stays six pages; the answer page stays one page; the register has the minimum rows. (Tasks 7, 12)
4. The largest bounds (maximum register rows, longest names, longest titles): nothing clipped, no cut caption, a long title splits the page and is never shrunk. (Tasks 6, 12)
5. The public share link: same files as the owner, no owner words in sources, the deck available. (Tasks 10, 11)
6. A register whose model shares do not sum to 100, or whose row cites a figure that does not exist: the stage retries once with a plain hint, then stops with a named reason. (Tasks 3, 4)

## File Structure

Create (all under `consultant-service/`): `app/storyline/__init__.py`, `model.py` (dataclasses, JSON round trip), `build.py` (answer page and section outline from stored columns), `register.py`, `stage.py` (the model stage), `exhibits.py`, `pagelaw.py`, `pdf.py`, `deck.py`, `roadmap.py`, `files.py`; `app/prompts/storyline.j2`; tests in `tests/storyline/`.
Modify: `app/config.py`, `app/models.py` (+ the repo's column-adding pattern used for `case_file_json`), `app/pipeline/{answer,orchestrator,export_pdf,export_pptx,method_note}.py`, `app/produced.py`, `app/routers/{requests,shared}.py`, `app/figures/{known,payload,law}.py` (small), frontend `src/api/consultant.ts`, `src/components/consult/{Answer,Package,Register(new),AnswerPage(new)}.tsx`, `src/routes/{StudioPage,SharedPage}.tsx`, `src/styles/consult.css`. Tests pinned to old strings (recon, "Pinned by tests") change where their task says.

---

### Task 1: Bounds, move terms, and the flex calculator

**Files:** Modify `app/config.py`, `app/pipeline/answer.py`; Create `app/storyline/__init__.py` (empty docstring), `app/storyline/flex.py`; Test `tests/storyline/test_flex.py`.

**Interfaces:**
- Consumes: `answer.compute_move`, `figures.calc.derive` (exact `Decimal`, precision None = exact), `known.py` kinds.
- Produces: settings `VALUE_FLEX_PCT` (default 20, held 5..50), `REGISTER_ROWS_MIN`/`REGISTER_ROWS_MAX` (2 and 8; held 1..4 and 4..12, min never above max, `_at_most` pattern), `STORYLINE_SECTIONS_MAX` (8; 4..12), `EXHIBIT_ROWS_MAX` (12; 4..30). `answer_json["move"]["terms"]` stored as a list of `{kind: "claim"|"constant"|"proposed", id|value, sign, label}` (enough to recompute). `flex.flexed(terms, pct) -> tuple[Decimal, Decimal, Decimal]` returning `(low, mid, high)` where only `proposed` terms are scaled by `(1 - pct/100)` for low and `(1 + pct/100)` for high; sign -1 terms are handled so low is never above high. `flex.note(terms, pct) -> str | None` returns the plain footnote ("Flexes our assumption of 75% by 20% either way.") or None when there is no assumption of ours.

- [ ] **Step 1: Write failing tests** in `tests/storyline/test_flex.py`: `test_config_bounds_clamp_and_min_never_exceeds_max` (env 99 -> 50, 1 -> 5; rows min 9 with max 3 -> min lowered, as `test_known.py` ~447-465 does); `test_flexed_scales_only_our_terms` (terms: client $22, constant 5, proposed 0.75; at 20%: mid = exact product, low/high = product with 0.6 / 0.9; client terms unchanged); `test_flexed_with_no_proposed_term_collapses` (low == mid == high, `note` is None); `test_flexed_keeps_low_below_high_with_a_subtracted_term`; `test_move_stores_its_terms` (run `answer.shape`/`compute_move` on a fixture; `move["terms"]` reproduces `move["value"]` through `flexed(terms, 0)`); `test_a_move_without_terms_has_no_range` (legacy row: `flexed` on `None` raises `NoTerms`, callers treat it as "no range").
- [ ] **Step 2: Run** `pytest tests/storyline/test_flex.py -p no:cacheprovider` - expect FAIL (module missing).
- [ ] **Step 3: Implement** the settings with the existing helpers; store `terms` in `compute_move`'s result; write `flex.py` using `figures.calc` Decimal arithmetic only (no floats).
- [ ] **Step 4: Run** the new tests plus `tests/figures -q` - expect all pass.
- [ ] **Step 5: Commit** `feat(storyline): bounded flex and the move keeps its terms`.

---

### Task 2: The storyline object and the answer page

**Files:** Create `app/storyline/model.py`, `app/storyline/build.py`; Test `tests/storyline/test_build.py`.

**Interfaces:**
- Consumes: Request columns (recon, "Answer module"; data scout): `brief_json.question`, `answer_json` (headline, turn, sub, figures, move), `main_problem`, `diagnosis_json` (hypotheses with `test.verdict`, `from_owner`), `consulting_recommendations_json` (`why_not_the_others`, `intervention_kind`), `action_plan_json.phases`, `qa_report_json.checks`, `integrity_report_json.clean`, `law.states(req)`, `known.known_for(req).counts()`, `payload.entry(...)` (display, kind, tag word).
- Produces: frozen dataclasses in `model.py`: `Number(figure_id, display, tag)`, `RestsOn(theirs, derived, ours, reference, checks_passed, checks_run)`, `AnswerPage(question, answer_lines, numbers, believed, tested, monday, would_not, rests_on)`, `Section(id, title, takeaway, exhibit, footnotes, note, sources, stamp)`, `Exhibit(id, kind, caption, takeaway, data, source)`, `Storyline(answer, register, sections, builds)`; `to_json`/`from_json` round trip. `build.build(req) -> Storyline | None` (None only when there is no `answer_json`); `build.answer_page(req) -> AnswerPage`.
- Mapping rules (from the data scout; "missing" parts are None/empty, never filled): numbers = `answer.figures[:2]` then `move` (max 3, each tagged); believed = `main_problem`, tested = the verdict sentence (`test.because`) of the hypothesis that restates it (`from_owner` true), else None; monday = the first action-plan phase's `do` plus its `you` line, else the first playbook quick win with `no_software`, else None; would_not = refuted hypotheses' statements (max 3) then `why_not_the_others`; checks = count of `qa_report.checks` passed of run; `builds` = `decide.builds()` rule so "do not build" drops the system file and screens.

- [ ] **Step 1: Write failing tests** `test_answer_page_takes_each_part_from_its_column`, `test_numbers_are_at_most_three_and_each_carries_its_tag_word` (tags are exactly `yours`, `worked out`, `our estimate`, `reference`), `test_rests_on_counts_equal_known_for_counts`, `test_a_part_with_no_data_is_none_not_invented` (no brief, no move, no action plan), `test_do_not_build_run_sets_builds_false`, `test_json_round_trip_is_lossless`, `test_the_answer_page_text_contains_no_hedging_words` (scan for "confident", "AI is", "not sure", "validation", "review by a human").
- [ ] **Step 2: Run** - expect FAIL. **Step 3: Implement** `model.py` and `build.py`. **Step 4: Run** `pytest tests/storyline -q` - pass. **Step 5: Commit** `feat(storyline): the storyline object and the answer page, from what the run already stored`.

---

### Task 3: The recommendation register (code side)

**Files:** Create `app/storyline/register.py`; Modify `app/figures/known.py` (extra known figures for the register's numbers); Test `tests/storyline/test_register.py`.

**Interfaces:**
- Consumes: Task 1 `flexed`, `note`; Task 2 model; `action_plan_json.phases` (`when`, `by`, `you`); `scoreboard_json.owner`; `known_for(req, extra=...)`.
- Produces: `RegisterRow(id, recommendation, changes, value: Range | None, cost: Cost, owner, when, depends_on)`, `Range(low, mid, high, unit, period)`, `Cost(figure_id | None, needs | None)`, `Register(rows, total, footnotes)` in `model.py`. `register.assemble(req, drafted: list[dict]) -> Register` where each drafted row is `{phase: int, recommendation, changes, owner, depends_on: list[int], share_pct: int, cost_figure: str | None, cost_needs: str | None}`. Raises `RegisterInvalid(reasons: list[str])` with plain reasons (used as the retry hint). `register.extra_figures(register) -> list[Figure]` returns every range number as a `derived` figure (`ours` when any proposed term is inside) with its working, so the number law accepts them.

Rules: rows between `REGISTER_ROWS_MIN` and `REGISTER_ROWS_MAX`; `share_pct` integers sum to exactly 100; `phase` indexes an existing plan phase and gives `when` unchanged; `depends_on` indexes earlier rows only (no cycle); a `cost_figure` must exist in `known_for(req)` or the row must carry `cost_needs` (plain phrase); row range = headline `(low, mid, high)` from `flexed(move.terms, VALUE_FLEX_PCT)` times `share_pct/100` in exact `Decimal`; no move or no terms -> every `value` is None and the register footnote says why in one plain sentence. Footnotes: the flex note, "Shares are our estimate of where the gain comes from." and, when a cost is open, the list of needed inputs.

- [ ] **Step 1: Write failing tests:** `test_shares_must_sum_to_one_hundred` (99 and 101 rejected with a reason naming the sum); `test_row_ranges_add_up_to_the_headline_exactly` (sum of lows == headline low, mids == headline value, highs == headline high, `Decimal` equality); `test_a_missing_move_leaves_values_empty_and_says_why`; `test_cost_is_a_known_figure_or_a_named_gap` (unknown figure id rejected; `cost_needs` accepted); `test_dependency_on_a_later_row_is_rejected`; `test_row_count_outside_the_bounds_is_rejected_with_both_bounds_named`; `test_the_register_numbers_pass_the_number_law` (render each range display through `figures.bind` with `extra_figures` and assert no unowned number).
- [ ] **Step 2: Run** - FAIL. **Step 3: Implement** `assemble`, `extra_figures`; extend `known_for` so `known_for(req)` includes `extra_figures` of the stored register when `storyline_json` exists. **Step 4: Run** `pytest tests/storyline tests/figures -q` - pass. **Step 5: Commit** `feat(storyline): the register whose ranges add up to the headline, checked in code`.

---

### Task 4: The storyline stage (the one new model call)

**Files:** Create `app/storyline/stage.py`, `app/prompts/storyline.j2`; Modify `app/models.py` (+ column, same pattern as `case_file_json`), `app/pipeline/orchestrator.py` (call after `action_plan`, before `qa_report`), `app/produced.py`, `app/pipeline/diagnose.py` or wherever stage names/labels for progress live (search `"answering"`), `app/routers/requests.py` progress copy; Test `tests/storyline/test_stage.py`, `tests/figures/test_prompt_examples.py` (the new prompt must pass the existing example-hygiene scan).

**Interfaces:**
- Consumes: Task 2 `build.build`, Task 3 `register.assemble`, `figures_block`/`known_for` prompt lines, `provider.chat`, `StageFailed`, `settings.STAGE_REPLY_ATTEMPTS`, the retry-hint pattern in `answer.write`.
- Produces: `stage.write(db, request_id) -> None` storing `Request.storyline_json = {"register": [drafted rows], "sections": [{id, title, takeaway}], "written_at": ...}`; on failure after the attempts raises `StageFailed("storyline", <plain reason>)`. Prompt JSON reply: `{"register": [...drafted rows as in Task 3...], "sections": [{"id": "...", "title": "...", "takeaway": "..."}]}`; text uses `{{F:id}}` tokens for every number; the model gives shares, never amounts.

Title rule enforced here: after binding, a section title must fit two lines of the proof-page title font at the page's text width (`pagelaw.title_lines(text) <= 2`, measured by `stringWidth`); if not, one retry whose hint states the limit; if still too long the stage fails (never cut).

- [ ] **Step 1: Write failing tests** with a stub `provider.chat` (the autouse guard blocks live calls): `test_a_good_reply_is_stored_and_the_register_assembles`; `test_unowned_number_in_a_title_is_sent_back_with_the_drop_hint`; `test_shares_not_summing_to_100_get_one_retry_with_the_sum_named_then_stop`; `test_a_title_over_two_lines_gets_one_retry_naming_the_limit_then_stops_honestly`; `test_sections_for_a_do_not_build_run_exclude_the_system_section`; `test_the_stage_failure_reaches_the_client_in_plain_words` (progress copy names "the plan summary", not "storyline"); `test_prompt_asks_for_no_amounts_and_no_hedging` (scan `storyline.j2`).
- [ ] **Step 2: Run** - FAIL. **Step 3: Implement** stage, prompt, column, orchestrator hook, progress label. **Step 4: Run** `pytest tests/storyline tests/figures tests/test_honest_failure.py -q`. **Step 5: Commit** `feat(storyline): one stage writes the register wording and the proof titles, numbers bound by code`.

---

### Task 5: Exhibits drawn in code

**Files:** Create `app/storyline/exhibits.py`; Test `tests/storyline/test_exhibits.py`.

**Interfaces:**
- Consumes: Task 2 `Exhibit`, `known_for(req)`, `capacity_json.weekly_grid`, `answer.move.terms`, `action_plan_json.phases`, `scoreboard_json`, tag words from `figures.model`.
- Produces: `exhibits.for_section(req, section_id) -> Exhibit | None` choosing the kind by the data present (never by the model): `bar` (their week's fill by class from the weekly grid), `waterfall` (the prize: the move's terms as steps to the headline, ours steps tagged), `week_grid`, `plan_chart` (phases over the plan's weeks), `kpi_table` (baseline to target). Each `Exhibit.data` holds only `Figure` ids and display strings; `exhibits.draw_pdf(exhibit, width, height) -> reportlab.graphics.shapes.Drawing`; `exhibits.draw_slide(exhibit, slide, box)` for python-pptx. Numbering "Exhibit n.m" is assigned by section order in `build.py`. Number format: theirs exact; derived and ours with "~"; ranges "low to high" with the flex footnote. Every value label carries its tag word. Rows beyond `EXHIBIT_ROWS_MAX` are grouped under the plain label "Other classes (n)" with their summed figure derived in code, never dropped.

- [ ] **Step 1: Write failing tests:** `test_bar_labels_are_figures_with_their_tags`; `test_waterfall_steps_sum_to_the_headline`; `test_rows_over_the_bound_are_grouped_and_the_group_sum_is_exact`; `test_no_data_gives_no_exhibit_not_an_empty_chart`; `test_drawing_fits_its_box_at_min_and_max_rows` (shape bounds inside width x height); `test_every_drawn_string_passes_the_number_law` (extract strings from the Drawing, bind against `known_for`).
- [ ] **Step 2-4: Run FAIL, implement, run PASS.** **Step 5: Commit** `feat(storyline): exhibits are drawn from figures in code, never by the model`.

---

### Task 6: The presentation law on every rendered page

**Files:** Create `app/storyline/pagelaw.py`; Modify `app/pipeline/export_pdf.py` (`release_status` reasons only); Test `tests/storyline/test_pagelaw.py`.

**Interfaces:**
- Consumes: `presentation_findings(path)` (`export_pdf.py:496`), `clipping_findings` (`app/engine/gates/presentation.py:258`), `law.page_reasons`.
- Produces: `pagelaw.title_lines(text, font, size, width) -> int` (reportlab `stringWidth` wrapping); `pagelaw.check_section(section) -> list[str]` (plain reasons: title over two lines; more than one exhibit; foot parts out of order; stamp not one of ESTIMATE, PRELIMINARY, ILLUSTRATIVE, SAMPLE DATA, FOR DISCUSSION); `pagelaw.pdf_findings(path) -> list[str]` = `presentation_findings` + `clipping_findings`, each reason naming the page; `release_status` adds them as reasons (a clipped page makes the file a draft that names the page).
Foot order law: numbered footnotes, then "Note:", then "Source:" ending "BMV analysis" when any number on the page is derived or ours.

- [ ] **Step 1: Write failing tests:** `test_a_two_line_title_passes_and_a_three_line_title_is_named`; `test_a_title_is_never_shrunk` (the font size used for any title equals the constant); `test_foot_parts_out_of_order_are_reported`; `test_source_line_ends_with_bmv_analysis_only_when_a_number_is_ours_or_derived`; `test_a_clipped_pdf_becomes_a_draft_naming_its_page` (build a PDF with an overflowing flowable in a test frame; `release_status` lists "page N"); `test_unknown_stamp_is_rejected`.
- [ ] **Step 2-4: FAIL, implement, PASS.** **Step 5: Commit** `feat(storyline): page rules are a law, measured on the rendered page`.

---

### Task 7: The answer page, the register and the proof lead pages in the PDFs

**Files:** Create `app/storyline/pdf.py`; Modify `app/pipeline/export_pdf.py` (`_volume_flows`, `build_pdf`, hedging strings), `app/pipeline/method_note.py`, `app/screens/export.py` (answer page first in the system PDF); Modify pinned tests (`tests/test_run53_r3.py`, `tests/test_run52_controls.py`, `tests/test_consultancy_layers.py` cases named in the recon); Test `tests/storyline/test_pdf.py`.

**Interfaces:**
- Consumes: Tasks 2-6; `export_pdf._EngagementDoc`, `_S`, `_h1`, `_rich`, `_table`, `DrawnCell`; `law` hooks.
- Produces: `pdf.answer_page_flowables(story) -> list` (one page: the question, the answer in two lines, the three numbers each with its tag, "What you believed / what the test said", "Monday", "What we would not do", "What this rests on: n figures are yours, n worked out, n references with sources, n checks passed"); `pdf.register_flowables(story) -> list` (landscape-friendly table, columns as in the spec, footnotes beneath); `pdf.proof_lead_flowables(section, exhibit) -> list` (title, exhibit, takeaway, foot). `build_pdf` puts the answer page first in every kind; the register goes in the blueprint only (the others print one line "The register is in the blueprint, page n."); each blueprint proof section starts with its lead page (R5). Legacy runs (no storyline): unchanged output.
Hedging copy (R9): replace `BMV_STATEMENT` with a plain imprint ("Prepared by Build My Version for {business}, {date}."), `DRAFT - REQUIRES VALIDATION` with `DRAFT` plus the named reasons ("A check failed on page n: ..."), drop "AI-native consultancy", and update the tests that pin the old strings.

- [ ] **Step 1: Write failing tests:** `test_every_pdf_kind_opens_with_the_answer_page` (page 1 text of blueprint, technical, operations, system contains the question and the rests-on line); `test_the_register_is_in_the_blueprint_and_only_referenced_elsewhere`; `test_a_legacy_run_builds_as_before` (no storyline_json: byte-identical to today's golden hash from the existing identical-bytes test); `test_answer_page_fits_one_page_at_the_longest_inputs`; `test_pdf_text_has_no_hedging_words` (scan all kinds); `test_register_rows_at_the_maximum_do_not_clip` (uses Task 6 findings == []); `test_a_one_person_studio_operations_manual_is_not_padded` (page count equals its content, here six pages or fewer).
- [ ] **Step 2: Run** - FAIL. **Step 3: Implement**; keep the names the engine imports. **Step 4: Run** `pytest tests/storyline tests/figures tests/test_consultancy_layers.py tests/test_run53_r3.py tests/test_run52_controls.py tests/engine/test_engine_legacy_adapter.py -q`. **Step 5: Commit** `feat(storyline): every PDF opens with the answer; the blueprint carries the register and lead pages`.

---

### Task 8: The roadmap file (new)

**Files:** Create `app/storyline/roadmap.py`; Modify `app/routers/requests.py` only through Task 10's list; Test `tests/storyline/test_roadmap.py`.

**Interfaces:**
- Consumes: Task 2 model, `action_plan_json` (phases, decisions), `scoreboard_json` (metric, baseline, target, owner, review), `risks_json`, `decisions_json`, Task 5 `plan_chart` and `kpi_table` exhibits, Task 7 answer page flowables.
- Produces: `roadmap.build_roadmap_pdf(req) -> str` path `uploads/exports/{id}-roadmap.pdf`, opening with the answer page; sections: the plan week by week with owners (client's role words from the register and scoreboard), KPIs from baseline to target (baseline "measure in week 1" shown as is), risks with mitigation and who feels it, the decisions the owner must make, and a governance cadence table built from each metric's `review` rhythm (R7). Raises `NotReady("roadmap")` when there is no action plan. Uses the same page law and cache rule as `build_pdf`.

- [ ] **Step 1: Write failing tests:** `test_roadmap_names_the_plans_real_length` (a 6-week plan never says ninety days); `test_kpi_rows_keep_week_one_baselines_verbatim`; `test_cadence_table_groups_metrics_by_their_review_rhythm`; `test_no_action_plan_is_not_ready_and_not_a_blank_file`; `test_roadmap_passes_the_number_law_and_page_law`.
- [ ] **Step 2-4: FAIL, implement, PASS.** **Step 5: Commit** `feat(storyline): the roadmap is its own file, as long as the plan`.

---

### Task 9: The deck from the storyline

**Files:** Create `app/storyline/deck.py`; Modify `app/pipeline/export_pptx.py` (first slides, titles from the storyline, `ai.confidence` tail, hedging fallbacks); Modify `tests/test_deck_layout.py` and `tests/test_deck_palette_and_callouts.py` only where they pin changed text; Test `tests/storyline/test_deck.py`.

**Interfaces:**
- Consumes: Tasks 2-5, `export_pptx` helpers the engine already imports (`_add_text`, `_add_bg`, `_hairline`, `MARGIN`, `SLIDE_W`, `SLIDE_H`).
- Produces: `deck.storyline_slides(prs, story, req)` adding, in order: the answer slide, the register slide, one slide per proof section (action title, the exhibit, takeaway, foot), the plan slides, then the existing screens slides titled as "how the plan runs". Slide titles read from `story.sections[i].title` so a title cannot differ from the PDF. `build_presentation` calls it when a storyline exists, else behaves as today.

- [ ] **Step 1: Write failing tests:** `test_deck_titles_equal_the_pdf_section_titles` (compare slide titles with `story.sections` titles); `test_first_two_slides_are_the_answer_and_the_register`; `test_one_exhibit_per_exhibit_slide`; `test_deck_text_has_no_hedging_words_and_no_ai_confidence_line`; `test_deck_slides_are_named_slides_in_law_findings` (law page = slide number, as `test_the_deck_names_the_slide`); `test_a_legacy_run_deck_is_unchanged`.
- [ ] **Step 2-4: FAIL, implement, PASS.** **Step 5: Commit** `feat(storyline): the deck tells the same story from the same object`.

---

### Task 10: One list of files: shelf, ZIP, share link, progress

**Files:** Create `app/storyline/files.py`; Modify `app/routers/requests.py` (export routes, `build_zip`, payloads), `app/routers/shared.py`, `app/produced.py`; Modify `tests/test_consultancy_layers.py::test_engagement_zip_bundle`, `tests/test_consultation_flow.py:404-412`, `tests/test_honest_failure.py:1961-1990` where they pin the old fixed sets; Test `tests/storyline/test_files.py`.

**Interfaces:**
- Produces: `files.files_for(req) -> list[PackageFile]` with `PackageFile(key, title, filename, kind: "pdf"|"pptx"|"zip", available: bool, reason: str | None)`; keys `blueprint`, `technical`, `operations`, `roadmap`, `system`, `deck`, then `zip`. `system` is `available=False` with the reason "Your diagnosis says not to build, so there are no screens." when `builds` is false. Routes: `GET /{ref}/export/{key}` generalises `/export/pdf/{kind}` and `/export/pptx` (the old paths keep answering the same content); `build_zip` iterates `files_for` and includes every available file, skipping `NotReady` and `UnstampedSample` ones and naming them in an `X-Skipped` header; `GET /api/shared/{token}/export/{key}` serves every key the owner can, the deck included. The list is added as `files` to the preview payload, the shared payload (the fixed `documents` booleans stay for one release, derived from `files`) and the progress payload (replaces `produced.documents_for` content; same title/state shape plus `key`).
The review editor still edits `mvp_blueprint` and `technical_plan` only; its response lists the keys its save rebuilds.

- [ ] **Step 1: Write failing tests:** `test_the_list_names_six_files_and_a_zip_in_order`; `test_a_do_not_build_run_marks_the_system_file_absent_with_its_reason_and_zip_still_builds`; `test_the_zip_contains_every_available_file_including_the_deck_and_the_roadmap`; `test_the_share_link_serves_the_deck_and_the_roadmap`; `test_an_unknown_key_is_a_404_with_plain_words`; `test_old_export_paths_still_answer`; `test_progress_files_match_preview_files`.
- [ ] **Step 2-4: FAIL, implement, PASS** (run the three pinned test files too). **Step 5: Commit** `feat(storyline): the server says which files exist; the shelf, ZIP and share link read it`.

---

### Task 11: Frontend - the answer first, the register, the shelf from the list

**Files:** Create `frontend/src/components/consult/AnswerPage.tsx`, `Register.tsx`; Modify `src/api/consultant.ts` (types `PackageFile`, `StudioAnswerPage`, `StudioRegister`; `files` on `StudioPreview`, `SharedPackage`, `StudioProgress`; `StudioExportKind` becomes `string`), `Package.tsx` (the shelf renders `files`; "Download everything" stays), `Answer.tsx` (hedging copy), `StudioPage.tsx` (a finished run opens on the answer page, then `Package`; the reviewer view too), `SharedPage.tsx` (answer page first, then `Package readOnly`), `src/styles/consult.css`. The server payloads expose `answer_page` and `register` built by `storyline.build` (this task adds them to the preview and shared payloads).

**Interfaces:** `AnswerPage` props `{page: StudioAnswerPage, figures, readOnly?}` renders the question, the two answer lines, up to three numbers with `FigTags`, believed and tested, Monday, would-not, and the rests-on line. `Register` props `{register: StudioRegister, figures}`: at 1440px a real table with the spec's columns; at 390px stacked cards (one per row, same fields), no horizontal page scroll. Copy (R9): "What we estimated or couldn't check." becomes "What rests on our estimates" and lists them; remove `story.ai.confidence` at `StudioPage.tsx:2879`; reword `Package.tsx:272` and `:471` to plain statements of what was checked.

- [ ] **Step 1: Build** the components and wire them. **Step 2: Check** `npx tsc --noEmit -p tsconfig.app.json` (0 errors) and `npm run lint` (0 errors, 14 warnings or fewer). **Step 3: Visual check** with Playwright against a mocked API (the harness pattern is in `scratchpad/step2-evidence/shots` and `r6/`): owner finished run, shared link, reviewer, each at 390px and 1440px; assert no horizontal scroll (`document.documentElement.scrollWidth <= innerWidth`) and that the register shows every row. Save screenshots under `docs/superpowers/evidence/step3/`. **Step 4: Commit** `feat(web): the answer is the first screen of a finished result; the register and the shelf read the server`.

---

### Task 12: Acceptance, the whole-step review, re-freeze

**Files:** Test `tests/storyline/test_acceptance.py`; Modify `tests/engine/r30_manifest.json` and the two commit constants (`tests/engine/test_engine_r30_frozen.py` docstring and line 81, `tests/engine/test_engine_mutation_manifest.py` line 526).

- [ ] **Step 1: Write acceptance tests** (fixtures built the way `tests/figures/test_acceptance.py` does): `test_minimum_and_maximum_fixtures_render_every_file_without_a_clipped_page` (pagelaw findings are empty for each PDF; no deck text box overflows); `test_register_sums_to_the_headline_in_every_fixture`; `test_every_page_passes_the_presentation_law`; `test_reading_only_the_proof_titles_gives_the_argument` (titles in order are sentences with a verb, at most two lines, none a bare label like "The opportunity"); `test_zip_has_exactly_the_available_files`; `test_no_file_contains_a_hedging_word`; `test_old_runs_still_build`.
- [ ] **Step 2: Run the whole suite** from `consultant-service/` in the background: `.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider -rf --basetemp=D:/bmv-pytest-tmp`, output to a file, exit code to a second file; read the exit code file, not the launcher notice. Compare failing ids with the baseline of four (three `test_engine_mutation_manifest` ids and `test_engine_universality.py::test_an_exempt_word_is_a_word_and_not_a_name`). Any other red is understood before going on.
- [ ] **Step 3: One whole-step adversarial review** (a fresh reviewer on a mid-to-top model; the diff is `git diff 8ef72d6..HEAD`); fix what is load-bearing once; park the rest in the ledger.
- [ ] **Step 4: Re-freeze.** `git log -1 --format=%h -- app/pipeline app/prompts tools ':(glob)tests/*.py'` gives the sha. Run `python tests/engine/refreeze_r30.py --commit <sha> --after "the output-shape step (date), same rules, same collector."`, update the two constants, run `tests/engine/test_engine_r30_frozen.py` and `test_engine_mutation_manifest.py` (the three old mutation failures remain), commit `test(engine): re-freeze r30 at <sha>`.
- [ ] **Step 5: Report** to Roy: what changed, the commands run and results, what was not run, rulings R1-R9 as they stood, the open owner decisions.

---

## Self-review (run once, 2026-11-01)

- **Spec coverage:** answer page (T2, T7, T11); register with ranges that sum, checked in code (T3); proof sections, action titles, exhibits, foot, stamps, number format (T4-T7); nothing sliced (T4 title retry, T5 grouping, T6 checks); one storyline for all files (T2, T7-T9); six files plus ZIP and a server list (T8, T10); no hedging (T2, T7, T9, T11); page measurement by PyMuPDF (T6) and the existing Chromium overflow measure for the system volume; deck follows the same story (T9). Left on purpose: options and do-nothing section, driver tree, option matrix (Step 4 data); per-row computed values (R3).
- **Order and parallelism:** T1, then T2, then T3. After T3, T5 and T10 are independent. T4 needs T3. T6 needs T5. T7 needs T4, T5, T6. T8 and T9 need T7 and can run in parallel. T11 needs T10 and T4. T12 last.
- **Type check:** `Range`, `Register`, `RegisterRow`, `Exhibit`, `Section`, `PackageFile` are defined once (T2, T3, T10) and used with the same names later.
