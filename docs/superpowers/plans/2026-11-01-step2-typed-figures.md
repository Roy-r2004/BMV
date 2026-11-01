# Step 2: Typed Figures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every number a client can see is a `Figure` with one of four tags (theirs, derived, ours, reference). A number the model wrote that matches a known figure prints as that figure's literal value. A number that matches nothing is not printed as if it were sound: short web prose drops it, and a rendered document that holds one fails the release law and names the page.

**Architecture:** A new package `consultant-service/app/figures/`, outside the r30 freeze and with no top-level import of `app.engine`. `model` holds `Figure` and `FigureSet`. `read` is the rebuilt number reader and checker. `bind` replaces matched numbers with literal values and strips sentences that cannot be matched. `calc` is exact Decimal arithmetic that returns derived Figures with their working. `casefile` is the stored set of the client's own figures. `known` builds the `FigureSet` for a request. `law` is the rendering rule. The old `app/pipeline/figures.py` entry points and every call site move to the package; the leniency thresholds are deleted.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (SQLite), pytest, reportlab, python-pptx, Jinja, PyMuPDF; React 19 + Vite + TypeScript.

**Spec:** `docs/superpowers/specs/2026-10-31-package-to-a-firms-standard-design.md` (Step 2; decisions under "Decided by the owner" and "Calls made"). The code map this plan rests on is `docs/superpowers/plans/2026-11-01-step2-typed-figures.recon.md` (every file, line and signature below that is not quoted comes from it; read it before the task you take).

This is plan 2 of 7. Step 1 (honest failure) is committed on this branch. Steps 3 to 7 are planned one at a time after this ships.

## Rulings made while planning

The recon found places where the design and the code disagree. The spec's "Calls made" list holds the assistant's calls, not the owner's, so these are settled here and binding on every task. Each says what it costs if wrong.

1. **`Figure` extends the pipeline's claim dict, not an engine class.** The engine has no `Claim`. The three provenances in the spec (`client_input`, `machine_computed`, `consultant_proposed`) live in `app/pipeline/registry.py:93`. Mapping: `client_input` is theirs, `machine_computed` is derived, `consultant_proposed` is ours, and a `canonical_gate` claim takes its kind from its approval status (`client_stated` theirs, `machine_verified` derived, anything proposed ours, `rejected` is not a figure). `reference` is new. Cost if wrong: a mapping edit.
2. **The exact arithmetic is `app/figures/calc.py`, not the engine's `DecimalCalculator`.** The engine calculator refuses subtraction, shares nobody approved (our proposals), the `USD` unit, period steps outside five values and the pipeline's claim ids, and importing it from the pipeline closes an import cycle. `calc.py` is Decimal-only, never floats, and a differential test proves it returns the same value as the engine wherever the engine accepts the operation. Cost if wrong: two calculators to keep aligned.
3. **Sample data is not a fifth kind.** Numbers inside a drawn screen's sample region are exempt from the tag requirement only inside an element the renderer marks as sample and that carries the SAMPLE DATA stamp. Captions, story text and the proposal cover are tagged or carry no number. The proposal cover's hero stops using the first sample tile. Cost if wrong: a cover with no hero number until Step 3 designs one.
4. **Page furniture is declared by the code that draws it, never guessed by pattern.** The law sees only text that passes through the content choke points (`_rich`, `_markdown_flowables`, `_table`, `_add_text`, the screens template). Page numbers, volume numerals, headers and footers are drawn outside them. Model prose may hold a digit only as a bound figure, a date (a year, a day and month name, a clock time checked against the hours the client gave), or the digit after a label word from the closed list in `labels.py`, which holds only words our own renderers number. Cost if wrong: a label word added to the list.
5. **The case file is stored in a new column, `Request.case_file_json`.** Step 6's interview session moves or extends it. Cost if wrong: a data move in Step 6.
6. **`registry._numbers` and the registry's own arithmetic stay as they are.** The engine, a mutation anchor and the frozen tests depend on them. Their claims become derived Figures through the mapping, with the working text taken from the claim's source. Cost if wrong: a few period conversions stay float-computed inside and are shown through Decimal.
7. **Two enforcement modes.** Short prose a client reads on the web (answer, diagnosis, summaries, captions, interview facts) is bound; a sentence that holds an unmatched number is dropped, as the screens already do. If that empties a required field, the stage's existing "nothing usable" path runs. Long authored documents (the PDF volumes, the deck) are not edited: the law records every unmatched number with its page, and `release_status` returns `draft` with reasons that name the pages. Cost if wrong: a real run may come out draft until the prompts are tuned against a paid run, which waits for the owner.
8. **What the reader counts.** Digits, money, percents, `k`/`M` suffixes, ranges (both ends), multipliers (`3x`, `3` followed by the multiplication sign U+00D7, `threefold`, `twice`, `double`, `triple`), digit ordinals (`3rd`), number words from two up (compounds and hyphenated included, `dozen`, `half a dozen`), and word ordinals from `third` up. It does not count `one`, `a`, `an`, `first`, `second`, because they are articles and a unit of time before they are quantities. Cost if wrong: "one week" slips through.
9. **Where a duration or count in plan prose comes from.** A duration or count the plan proposes (six weeks, three phases) is an `ours` Figure registered by the stage that proposes it (the move's `proposed` list, each roadmap phase's weeks). Prose mentions bind to it. A plan name that carries a duration is rendered by code from that Figure, not written by the model.
10. **Web scope for this step.** The consultation payloads (decision, shared link, case file, week grid, roadmap) carry no unmatched number in prose, carry a `figures` map, and show a tag on every structured figure. The legacy preview surface is swept in Step 7. Cost if wrong: the legacy page keeps its raw markdown until Step 7.

## Global Constraints

- No `try again`, exception text, stage id or model name in any client text. No human-review or "AI is not confident" wording anywhere.
- Tags in client words: `yours` (theirs), `worked out` (derived), `our estimate` (ours), `reference` (reference). One vocabulary across web, PDF, deck, screens.
- Everything that varies per business is bounded in `consultant-service/app/config.py` with a minimum and a maximum. No new fixed counts.
- `app/pipeline/`, `app/prompts/`, `tools/` and top-level `tests/*.py` are byte-frozen by `tests/engine/r30_manifest.json`. New code goes in `app/figures/`, new tests in `tests/figures/` (neither is frozen). Edits to frozen files are expected; until Task 10 re-freezes, `test_engine_r30_frozen.py` is the only new expected red.
- `registry._numbers` keeps its behaviour. Text anchors in `app/engine/types.py`, `app/engine/registry.py`, `app/engine/calc/arith.py` and the "client facts" comment anchor in `app/pipeline/registry.py` stay byte-identical.
- `tests/test_hollow_run_is_not_done.py` reads the orchestrator for the exact line `if not (req.mvp_blueprint or req.technical_plan):`. Keep it.
- Run checks from `consultant-service/` with `TMP=/d/bmv-pytest-tmp TEMP=/d/bmv-pytest-tmp .venv/Scripts/python.exe -m pytest <target> -q -p no:cacheprovider`. Frontend from `frontend/`: `npx tsc -p tsconfig.app.json --noEmit` (no output) and `npm run lint` (0 errors, no more than the 14 warnings that exist today, none in touched files).
- Baseline is the last full run on this branch: `31 failed, 2157 passed, 1 skipped`. The 31 failing ids are in the scratchpad file `step2-evidence/baseline-failures.txt`. A task may add no failing id that is not in that file, except the r30 freeze test before Task 10.
- Never read or print `.env*`, `*.pem`, `*.db`. Tests use stubs, never the live provider. No paid run.
- Commit after each task with a message that says why. Do not push. Commit trailer: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Each task's result is checked by a reviewer who did not write it, who runs the task's command and quotes the output.

## Review Focus

Each line has its test in the task named.

1. A model rounding that is near two figures of different values ($4,700 against 4,720 and 4,680) must not bind to either; it is unmatched. Task 3.
2. A request row made before this step has no `case_file_json`; every payload and render must still work, building the case file on read. Task 5.
3. A document whose only numbers are page furniture (page numbers, "Volume II", dates, the label "Phase 2") must pass the law. Task 8.
4. `25%` in prose binds to a claim stored as 0.25, and `25 percent` too. Task 2 and Task 3.
5. The code-drawn tables (financial model, KPI, evidence) print verified derived values and must pass the law; an unverified line must not print. Task 8.
6. A client's own number echoed in a sentence ("you have twelve reformers") is theirs and passes. Task 6.

## File Structure

- Create `consultant-service/app/figures/{__init__,model,labels,read,bind,calc,casefile,known,law,audit}.py`.
- Create `consultant-service/tests/figures/` with one test file per module and `test_acceptance.py`.
- Modify (frozen, re-freeze at Task 10): `app/pipeline/{figures,answer,action_plan,capacity,decide,analyze,diagnose,evidence,export_pdf,export_pptx,orchestrator}.py` as the tasks name, the prompts in Task 9, and the top-level tests the new behaviour changes.
- Modify (not frozen): `app/models.py`, `app/routers/{requests,discovery,shared}.py`, `app/screens/{generate,render}.py` and its templates, `app/config.py`, `app/engine/work_products/{render_pdf,render_deck}.py` (repair only).
- Modify frontend: `src/api/consultant.ts`, `src/components/consult/{Answer,Package,Interview}.tsx`, a new `src/components/consult/Fig.tsx`, and their types.

---

### Task 1: The Figure model

**Files:**
- Create: `app/figures/__init__.py`, `app/figures/model.py`, `app/figures/labels.py`
- Test: `tests/figures/test_model.py`

**Interfaces:**
- Produces, all in `model.py`:
  - `Kind = Literal["theirs", "derived", "ours", "reference"]`
  - frozen dataclasses `TheirsSource(turn: int | None, field: str | None, quote: str, file: str | None, cell: str | None)`, `Working(inputs: tuple[str, ...], op: str, text: str)`, `Proposal(note: str)`, `Reference(publication: str, year: int, population: str, url: str)`
  - frozen dataclass `Figure(id: str, value: Decimal, unit: str, period: str | None, kind: Kind, source: TheirsSource | Working | Proposal | Reference, precision: int)`. `precision` is the digits shown after the point; negative rounds to tens, hundreds.
  - `display(f: Figure) -> str`. Theirs and reference print exactly at their precision. Derived and ours print rounded to their precision, with `~` in front only when rounding changed the value.
  - `tag_word(kind: Kind) -> str` returning `yours`, `worked out`, `our estimate`, `reference`.
  - `as_json(f) -> dict` and `from_json(d) -> Figure` (round trip, `value` as a string).
  - `from_claim(c: dict) -> Figure` and `to_claim(f: Figure) -> dict` per ruling 1. A percent claim stored as a fraction becomes a Figure with the percent number (0.25 becomes 25, unit `percent`); `to_claim` reverses it. The value is `Decimal(repr(float))`, never a float.
  - `FigureSet`: `__init__(figures=())`, `add`, `get(id)`, `__iter__`, `__len__`, `by_kind(kind)`, `counts() -> dict[Kind, int]`, `match(value: Decimal, unit: str | None = None) -> list[Figure]` (all figures equal to the value within 0.5%, or equal to the value as that figure displays it).
- `labels.py`: `LABEL_WORDS: tuple[str, ...]`, only the words our renderers number (phase, step, section, exhibit, volume, page, module, screen, part, appendix, table, slide, footnote, option), with a comment saying a word is added only together with a renderer that numbers it.

- [ ] **Step 1:** Write `tests/figures/test_model.py` first: round trips for a CF, CE, DV, SA and CAP claim (the recon section 2.1 table); the canonical_gate mapping by approval status; percent in and out; `display` for each kind including `~` appearing exactly when rounding changed the value (`derived 44928` at precision -3 shows `~45,000`; `theirs 22` shows `$22`; a derived exact `864` shows no `~`); `match` returns two figures when two are within tolerance; a `float` passed as `value` is refused.
- [ ] **Step 2:** Run it and see it fail on import.
- [ ] **Step 3:** Implement `model.py` and `labels.py`. Units follow what the r30 claims use (read `registry._infer_unit` and `canonical_capacity_unit`); an unknown unit prints the number then the unit word.
- [ ] **Step 4:** Run `tests/figures/test_model.py`, then `tests/engine/test_engine_r30_frozen.py` (must still pass; nothing frozen changed).
- [ ] **Step 5:** Commit: `feat(figures): one Figure type with four kinds, so every number can say whose it is`.

---

### Task 2: The rebuilt reader and checker

**Files:**
- Create: `app/figures/read.py`
- Test: `tests/figures/test_read.py`

**Interfaces:**
- Consumes: `FigureSet`, `Figure` (Task 1); `labels.LABEL_WORDS`.
- Produces in `read.py`:
  - `Mention` (frozen dataclass): `text: str`, `start: int`, `end: int`, `value: Decimal`, `form: Literal["digit", "money", "percent", "word", "multiplier", "ordinal", "range", "time", "date"]`.
  - `mentions(text: str) -> list[Mention]` per ruling 8, in text order, a range giving one Mention per end.
  - `supported(m: Mention, known: FigureSet, hours: set[int] | None = None) -> bool`. A `time` is supported when `hours` is None or holds its hour. A `date` (year, day plus month name) is supported by form. Every other form needs a figure in `known.match(m.value)`; a percent is compared as the percent number.
  - `unsupported(text: str, known: FigureSet, *, hours: set[int] | None = None) -> list[Mention]`. No leniency parameter exists.
- Does not touch `registry._numbers`. This is a separate reader.

- [ ] **Step 1:** Write `tests/figures/test_read.py` first. Must-flag cases, every row of recon section 1.3 that passes today: `twelve classes`, `a dozen spots`, `half a dozen`, `twenty-two`, `3x more bookings`, `3` + U+00D7 + ` more bookings`, `threefold`, `twice`, `the 3rd phase`, `1st week`, `8 hrs a week`, `12 reformers`, `2-3 weeks` (two mentions), `six-week pilot`, `1.5 hours`, `0.5`, `one in 20` (flags 20), `$35`, `50%`, `10k`, `$1.2M`. Must-not-flag cases: `one of the explanations`, `no one`, `the first week`, `a second`, `a week`, `Phase 2`, `Step 3`, `Exhibit 2.1`, `in 2025`, `31 Oct`, `6pm` when `hours` is None or contains 18. Supported cases: `about 45,000` against derived 44928 at precision -3; `25%` against a percent Figure 25; `twelve` against theirs 12; `$4,700` against figures 4,720 and 4,680 is unmatched.
- [ ] **Step 2:** Run it and see it fail on import.
- [ ] **Step 3:** Implement `read.py`. A digit after a `LABEL_WORDS` word is a label, not a mention. Never add a special case for a sentence; grammar only.
- [ ] **Step 4:** Run `tests/figures/test_read.py` and `tests/figures/test_model.py`.
- [ ] **Step 5:** Commit: `feat(figures): a number reader that catches words, multipliers, ordinals and small numbers, with no leniency`.

---

### Task 3: Binding and sentence cleaning

**Files:**
- Create: `app/figures/bind.py`
- Test: `tests/figures/test_bind.py`

**Interfaces:**
- Consumes: `read.mentions`, `read.supported`, `FigureSet`, `display`.
- Produces in `bind.py`:
  - `BindResult(text: str, bound: list[Figure], unresolved: list[Mention])` (frozen dataclass).
  - `bind(text: str, known: FigureSet, *, hours: set[int] | None = None) -> BindResult`. A mention matching exactly one figure, or several of equal value and unit (the most trusted kind wins: theirs, derived, reference, ours), is replaced by `display(figure)`. A mention matching figures of different values is unresolved. The token `{{F:<id>}}` is replaced by that figure's display; an unknown id is unresolved. Dates, times and labels are left alone.
  - `clean_sentences(text: str, known: FigureSet, *, hours: set[int] | None = None) -> tuple[str, list[str]]`: binds, then removes each sentence that still has an unresolved mention; returns the cleaned text and the removed sentences.
  - `segments(text: str, known: FigureSet) -> list[dict]`: `{"text": str}` or `{"figure": id, "text": str}` items for the web, in order, after binding.

- [ ] **Step 1:** Write `tests/figures/test_bind.py` first: `about $45,000` with derived 44928 becomes the figure's display; `$4,700` stays and is reported unresolved when two nearby figures differ (Review Focus 1); a theirs figure is never re-rounded; a token resolves and an unknown token is unresolved; `clean_sentences` drops only the offending sentence and keeps the rest; a text with no numbers is returned unchanged byte for byte; `segments` rebuilds the bound text exactly when joined.
- [ ] **Step 2:** Run and see it fail.
- [ ] **Step 3:** Implement `bind.py`. Replacement works from the end of the text backwards so spans stay valid.
- [ ] **Step 4:** Run `tests/figures/`.
- [ ] **Step 5:** Commit: `feat(figures): print a figure's own value wherever the model rounded it, and drop sentences with numbers nobody owns`.

---

### Task 4: Exact derived arithmetic

**Files:**
- Create: `app/figures/calc.py`
- Modify (frozen): `app/pipeline/capacity.py` (CAP products, `capacity.py:170-254`), `app/pipeline/answer.py` (`compute_move`, `answer.py:112`)
- Test: `tests/figures/test_calc.py`, plus the existing `tests/test_consultation_flow.py` move tests and the capacity tests, unchanged and green

**Interfaces:**
- Consumes: `Figure`, `Working`.
- Produces in `calc.py`:
  - `Op = Literal["product", "total", "difference", "ratio"]`
  - `derive(op: Op, inputs: Sequence[Figure], *, id: str, unit: str, period: str | None = None, precision: int = 0, factors: Sequence[tuple[Decimal, str]] = ()) -> Figure`. `factors` are calendar constants as `(value, words)` pairs such as `(Decimal(52), "weeks a year")`; they appear in the working text. The result is `derived` when every input is theirs, derived or reference, and `ours` when any input is ours. The working text lists each input's display and the operation. A ratio by zero, a unit mismatch among the inputs of a total or difference, and a float input raise `ValueError` with a plain message.
- Migrates `capacity.shape` and `answer.compute_move` onto `derive`, keeping every string they produced before (the `$6 x 144 = $864 a week` style) identical, and returning Figures where they returned bare floats.

- [ ] **Step 1:** Write `tests/figures/test_calc.py` first: `12 x 6 x 6 = 432` exact; a difference; a total that refuses mixed units; ours-in gives ours-out; no float anywhere; and a differential test that builds the same operation through the engine's `DecimalCalculator` (recon section 2.2: `make_entity`, `product(..., period_step=...)`, `total`, `ratio`) for at least five cases the engine accepts and asserts equal values. If the engine refuses every constructible case, drop the differential test and say so in the report.
- [ ] **Step 2:** Run and see it fail.
- [ ] **Step 3:** Implement `calc.py` with `decimal.Decimal` and a fixed context. Then swap `capacity.shape` and `answer.compute_move` to call it.
- [ ] **Step 4:** Run `tests/figures/test_calc.py`, `tests/test_consultation_flow.py`, the capacity tests (grep `tests/` for `capacity`) and `tests/test_discovery.py`. All previously passing tests still pass.
- [ ] **Step 5:** Commit: `refactor(figures): derived numbers come from one exact calculator, with their working kept`.

---

### Task 5: The case file as the store of the client's own figures

**Files:**
- Create: `app/figures/casefile.py`
- Modify: `app/models.py` (`Request.case_file_json`, Text, nullable; `database._ensure_columns` picks it up with no change), `app/routers/requests.py` (`create_request`; `_sanitize_ops_numbers` keeps the question id the client sent, trimmed and length-bounded; the evidence routes), `app/routers/discovery.py` (`/casefile` returns `kind` and a plain source per figure), frozen `app/pipeline/evidence.py` (`save` calls the store)
- Test: `tests/figures/test_casefile.py`

**Interfaces:**
- Consumes: `read.mentions`, `Figure`, `TheirsSource`.
- Produces in `casefile.py`:
  - `build(req) -> list[Figure]`: one `theirs` Figure per mention in the client's interview answers (turn = 1-based position of the pair, with the question id if kept), the free-text columns (`field` set), and the evidence claims (`file` and `cell` set). Number words count (twelve is 12). `quote` is the sentence it sits in.
  - `load(req) -> FigureSet`: reads `case_file_json`; when it is null (a row from before this step) builds on read and does not write.
  - `save(db, req) -> None`, `add_evidence(db, req, claims) -> None`, `remove_evidence(db, req, file) -> None`.
- The registry's `client_fact_claims` and `evidence.load` keep producing the CF/CE claims the engine and registry need. The case file feeds `known` (Task 6), not the registry.

- [ ] **Step 1:** Write `tests/figures/test_casefile.py` first: a request with interview pairs, free text and one uploaded-file claim yields theirs Figures each with its turn, field or file and cell; a number written as a word is present; an old row with null `case_file_json` loads without error and without writing; removing a file removes only its figures; `/api/discovery/casefile` figures carry `kind: "theirs"`; a `brief_json` fact value that is not inside a quote never becomes a theirs figure.
- [ ] **Step 2:** Run and see it fail.
- [ ] **Step 3:** Implement. `create_request` saves the case file in the same commit as the row.
- [ ] **Step 4:** Run `tests/figures/`, `tests/test_discovery.py`, `tests/test_consultation_flow.py` and the evidence tests (grep `tests/` for `evidence`).
- [ ] **Step 5:** Commit: `feat(figures): store what the client told us as figures with the turn or cell each came from`.

---

### Task 6: One known set, and every checking call site on the new reader

**Files:**
- Create: `app/figures/known.py`
- Modify (frozen): `app/pipeline/figures.py` (keep `rounded`, `money`, `quoted`, `CONSTANTS`, `times_in`, `given_hours`; delete `numbers_in`, `given`, `close`, `holds`, `unsupported` and the `lenient_below` parameter once no caller is left), `answer.py` (`answer.py:191,214,225`), `action_plan.py` (delete `LENIENT_BELOW`, `action_plan.py:40,55`), `capacity.py` (`_num`, `_clock`), `decide.py`, `analyze.py`, `diagnose.py` (the prose fields in recon section 3 that have no check today)
- Modify (not frozen): `app/screens/generate.py` (delete `LENIENT_BELOW`, `generate.py:51,55,185,192`), `app/routers/discovery.py` (`shape_fact_updates`, `shape_casefile`, `_fact_value`)
- Modify (frozen tests): `tests/test_consultation_flow.py:54` and any test that pinned the old leniency
- Test: `tests/figures/test_known.py` plus the touched suites

**Interfaces:**
- Consumes: Tasks 1 to 5.
- Produces in `known.py`: `known_for(req) -> FigureSet`. It is the union of the case file's theirs figures, the registry's derived and ours claims mapped through `from_claim` (CF and CE excluded, since the case file holds them), the capacity picture's derived figures, the answer's move and proposed figures, and the roadmap's ours figures (ruling 9). A request still in the interview has no row yet; `known_for_texts(texts: Sequence[str]) -> FigureSet` covers the interview endpoints from the text alone.
- The roadmap stage registers each phase's weeks and the plan's total duration as `ours` Figures in `action_plan_json` (field `figures`), and the plan name is rendered from them (ruling 9).
- The answer's headline figures (`answer_json` `figures[]`, model strings such as a price pair) are bound through `bind.bind`: each keeps the ids of the figures its value binds to in `ids`, shows the bound text as its value, and is dropped when any number in it is unmatched, as today. Tasks 7 and 8 read these ids.
- Every stage listed above binds its prose through `bind.clean_sentences` (short web prose) or keeps its existing drop behaviour with the new `unsupported`. No stage calls the old API.

- [ ] **Step 1:** Update `tests/test_consultation_flow.py:54` to the new truth (`one of 1 explanations` now flags the `1`; reword the case if the intent was prose with no figures) and add tests to `tests/figures/test_known.py`: an answer headline with `twelve` that the client never gave is dropped; with `twelve` given it is kept; a roadmap phase with an invented price is dropped; a headline figure "$22 vs $32" keeps the ids of both figures it binds to and a headline figure with an unmatched number is dropped; a six-week plan name comes from the stored duration Figure; interview fact values are checked at the same strictness; `known_for` includes a derived capacity figure and the move.
- [ ] **Step 2:** Run the touched suites; record exactly which fail (expect the ones that pinned leniency).
- [ ] **Step 3:** Implement `known.py`, then move each call site. Run the suites after each stage file, not once at the end.
- [ ] **Step 4:** Run `tests/figures/`, `tests/test_consultation_flow.py`, `tests/test_discovery.py`, `tests/test_screens.py`, the action-plan tests (grep `tests/` for `action_plan`), and `tests/engine/test_engine_r30_frozen.py` (expected red: hashes). Report any other new failing id.
- [ ] **Step 5:** Commit: `fix(figures): the same strict check on every client sentence, so small numbers and number words no longer pass`.

---

### Task 7: Payloads and the web carry the tags

**Files:**
- Modify: `app/routers/requests.py` (`_decision_payload`, `/preview`, the roadmap payload), `app/routers/shared.py`, `app/routers/discovery.py`; frontend `src/api/consultant.ts` (types: `FigureJson`, `figures`, `segments`), new `src/components/consult/Fig.tsx`, `Answer.tsx`, `Package.tsx`, `Interview.tsx`
- Test: `tests/figures/test_payloads.py`; a frontend type check and a Playwright-with-mocked-API run kept as evidence

**Interfaces:**
- Consumes: `known_for`, `bind.segments`, `model.as_json`, `tag_word`.
- Produces: the decision, shared and casefile payloads gain `figures: {id: {display, kind, tag, source}}` where `source` is a plain-words sentence built by code ("From your answer to 'what do you charge a class'", "Worked out: 6 classes a day x 144 ...", "Our estimate: ...", "Reference: <publication>, <year>"). The answer's `headline`, `turn` and `sub` also arrive as `*_segments`. No other prose changes shape.
- `Fig.tsx` renders a figure segment with its tag word and a tap or hover that shows the source, usable one-handed at 390 px (the source opens in place, never as a hover-only tooltip). `Answer.tsx` shows the tag on the headline figures, the move, the proposals and the week-grid derived values. `Package.tsx` roadmap shows its ours figures with the tag.
- Prose fields without segments are served already bound and cleaned (Task 6), so a raw model number cannot arrive.

- [ ] **Step 1:** Write `tests/figures/test_payloads.py` first: build a request fixture, call the payload functions, and assert every digit in served prose (outside `*_segments` figure items and the `figures` map) is a bound display; the `figures` map includes each kind present; an old row without a case file still serves.
- [ ] **Step 2:** Run and see it fail.
- [ ] **Step 3:** Implement the backend, then the frontend. Keep the existing layout; tags are added, nothing is re-skinned yet (Step 3 and Step 7 do that).
- [ ] **Step 4:** Run `tests/figures/test_payloads.py`, the router suites, `npx tsc -p tsconfig.app.json --noEmit`, `npm run lint`. Run a mocked-API Playwright pass at 390 px and 1440 px on the answer and the roadmap; save screenshots under the evidence folder and read them.
- [ ] **Step 5:** Commit: `feat(web): every figure on the answer and the plan says whose it is and where it came from`.

---

### Task 8: The rendering rule

**Files:**
- Create: `app/figures/law.py`
- Modify (frozen): `app/pipeline/export_pdf.py` (`_rich`, `_markdown_flowables`, `_table`, `build_pdf`, `release_status`), `app/pipeline/export_pptx.py` (`_add_text`, `build_presentation`)
- Modify (not frozen): `app/screens/render.py` (Jinja environment), `app/screens/templates/{proposal,system,_blocks,_frame}.html`, `app/screens/export.py`, `app/engine/work_products/{render_pdf,render_deck}.py` (repair only)
- Test: `tests/figures/test_law.py`

**Interfaces:**
- Consumes: `known_for`, `read.mentions`, `bind`.
- Produces in `law.py`:
  - `scope(known: FigureSet, *, where: str)`, a context manager that sets the active known set and collects findings.
  - `check(text: str, *, region: str | None = None) -> str`: called at the choke points; returns the text with matched numbers replaced by their literal display, records a `Finding(text, number, region)` for each unmatched one, and never raises, so a build completes.
  - `Finding(number: str, snippet: str, region: str, page: int | None)` and `locate_pages(pdf_path: str, findings) -> list[Finding]` (PyMuPDF text search of the snippet; sets `page`).
  - `sample_region()`: a marker the screens template wraps around sample-data blocks; text inside is not checked and the template refuses to render a sample region without the SAMPLE DATA stamp.
- Wiring: `build_pdf` runs inside `scope`, then `locate_pages`, and stores the findings where `release_status` reads them; `release_status` adds one reason per page, in team words ("Volume I, page 7: the number 35 matches none of the client's figures, our workings, our estimates or a cited reference"), and returns `draft` when any exist. The deck and the proposal PDF do the same. The proposal cover's hero comes from the answer's first headline figure, or is omitted when there is none (ruling 3). A client email body is asserted figure-free by a test.
- The engine renderers that call the same choke points keep passing `tests/engine`; repair them in this task if they do not.

- [ ] **Step 1:** Write `tests/figures/test_law.py` first, including the acceptance test: render the blueprint PDF from a fixture row (pattern `tests/test_consultancy_layers.py::test_blueprint_pdf_roundtrip`) with one untagged number injected; assert `release_status(...)["status"] == "draft"` and a reason that names the page; the same fixture without the injection is not draft because of the law. Also: page numbers and "Volume II" pass (Review Focus 3); a verified financial-model line passes and an unverified one is flagged (Review Focus 5); the same for the deck with the slide number named; a screens page with a number in its caption fails and one in a sample region does not; a sample region without the stamp fails to render.
- [ ] **Step 2:** Run and see it fail.
- [ ] **Step 3:** Implement `law.py`, then the PDF, deck and screens wiring. Furniture is whatever the code draws outside the choke points; add no regex to hide a number.
- [ ] **Step 4:** Run `tests/figures/`, `tests/test_consultancy_layers.py`, `tests/test_screens.py`, `tests/engine/` (compare with baseline), and the PDF suites (grep `tests/` for `export_pdf`).
- [ ] **Step 5:** Commit: `feat(figures): the release law, so a document with a number nobody owns cannot go out as final`.

---

### Task 9: Prompts

**Files:**
- Modify (frozen): `app/prompts/{answer,roadmap,casefile,interview,decompose,blueprint}.j2` and their stage callers to pass the known-figures block; `app/prompts/{screens_plan,screen}.j2` and `app/screens/generate.py:54-60` `BLOCK_GUIDE`
- Modify: `app/figures/known.py` adds `prompt_lines(known) -> str` (one line per figure: id, display, tag word)
- Test: `tests/figures/test_prompt_examples.py`

**Interfaces:**
- Each prompt that writes client prose receives a "Figures you may use" block and the rule: write only these numbers or cite them as `{{F:id}}`; a plan's duration or counts are proposed in the structured field, never only in prose.
- Every digit-bearing quoted example in these prompts is an obvious example (round invented values) and the test fails if an example would pass the checker as a known figure when `known` is empty.

- [ ] **Step 1:** Write `tests/figures/test_prompt_examples.py` first: scan every `app/prompts/*.j2` for quoted strings that contain a digit or a number word; assert `unsupported(example, FigureSet())` flags each one unless its only number is a date, a time or a label. Add a note in the test that a coincidence between an example and a client's real figure cannot be caught here.
- [ ] **Step 2:** Run and list the failing examples.
- [ ] **Step 3:** Edit the prompts and callers. Do not change any prompt's output schema except to add `{{F:id}}` as allowed text.
- [ ] **Step 4:** Run `tests/figures/`, every suite that renders a prompt (grep `tests/` for the template names), and the stage tests with stubs.
- [ ] **Step 5:** Commit: `feat(prompts): tell the model which figures exist, and make every example plainly an example`.

---

### Task 10: Acceptance, the audit tool, the baseline, the re-freeze

**Files:**
- Create: `app/figures/audit.py` (a command `python -m app.figures.audit <request public id>` that prints, per document and page, every number not matched to a figure, for the owner's local test), `tests/figures/test_acceptance.py`
- Modify: `tests/engine/r30_manifest.json`, `tests/engine/test_engine_r30_frozen.py`, `tests/engine/test_engine_mutation_manifest.py:526` (the two commit constants) via `tests/engine/refreeze_r30.py`

- [ ] **Step 1:** Write `tests/figures/test_acceptance.py`: the spec's acceptance. A package rendered from a fixture with one untagged number fails the release law and names the page; the checker's tests cover the word, multiplier, ordinal and small-number cases that pass today; an interview fixture with a number the client never gave produces no fact for it.
- [ ] **Step 2:** Implement `audit.py` against a fixture row and test it.
- [ ] **Step 3:** Run the whole consultant suite in the background with `-rf`, save the failing ids, and diff against the baseline file. Expected: every id is in the baseline, plus the r30 freeze test. Run `tsc` and `lint`.
- [ ] **Step 4:** Commit all frozen changes, then `python tests/engine/refreeze_r30.py --commit <short sha of the last frozen change> --after "the typed-figures step"`, update the two constants, and run `tests/engine/test_engine_r30_frozen.py` and `tests/engine/test_engine_mutation_manifest.py` (its three old failures remain, no new ones).
- [ ] **Step 5:** Commit: `test(engine): re-freeze r30 at <sha>`.
