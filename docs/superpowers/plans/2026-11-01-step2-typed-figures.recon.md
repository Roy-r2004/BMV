# Step 2 recon: typed figures, end to end

Repo `D:\Your Business Version`, branch `step1-honest-failure`, HEAD `39e3920`. All paths below are relative to `consultant-service/` unless they start `frontend/`. Read-only: nothing was changed except this file.

**V** = verified (I read it or ran it). **I** = my inference.

---

## 0. Headline findings (read these first)

1. **V. There is no `Claim` class in the engine.** The three provenances the spec names (`client_input`, `machine_computed`, `consultant_proposed`) belong to the **r30 pipeline claim dict**, `app/pipeline/registry.py:93`. That set has a fourth value, `canonical_gate`. The engine's typed numbers are something else: `Entity` of kind FACT/ASSUMPTION carrying a `Quantity` (an exact `Decimal`, `app/engine/types.py:431`), with `FactBasis` set to client_stated, document_extracted, document_verified, external_sourced, calculated or inferred (`types.py:101`). Today three number systems sit side by side:
   - (a) r30 claim dicts, with float values;
   - (b) engine `Quantity` / `Entity`;
   - (c) `app/pipeline/figures.py`, which works on float sets, plus the `answer.compute_move` terms.

   **I:** "Figure extends the registry Claim" can only mean (a). The exact calculator, though, is (b).
2. **V. The figure checker today is `figures.unsupported()`** (`app/pipeline/figures.py:130`). It lets through:
   - every number word ("twelve", "a dozen", "six-week");
   - `3x` and every digit ordinal (`3rd`, `1st`), because the regex needs a non-word character after the digits;
   - everything below `lenient_below`: 2 by default, 13 in the screens and the roadmap.

   I probed these cases and the results are in §1.3. The registry reader `registry._numbers` is a separate grammar. It deliberately skips multipliers, years, clock times, counts written "N phases/steps/..." and "Phase 2".
3. **V. Most client prose is never checked against figures at all:**
   - in the PDF volumes, only KPI/acceptance sentences are checked (`registry.kpi_number_findings`);
   - the decision and diagnosis prose served to the web (`consulting_summary`, `central_problem`, `why_not_the_others`, `unverified`, `because`) has no check;
   - the screens' sample-data blocks (KPI tiles, tables) have no check, and the proposal PDF prints the first KPI tile as its hero.
4. **V. The case file is stateless today.** `/api/discovery/casefile` recomputes it from form fields on every call. The figures the client gave are rebuilt in about 4 places, from 3 columns:
   - `ops_numbers_json` (the turn `id` is stripped when it is stored);
   - `evidence_json` (the CE figures);
   - the free-text columns.
5. **V. Import direction is one way: the engine imports the pipeline, and the pipeline imports nothing from the engine** (only `app/config.py` touches `engine.types.BOUNDS`).
   - `engine.calc.units` imports `app.pipeline.registry` at module top. A pipeline module that imports `engine.calc` at its own top level will form an import cycle.
   - The engine renderers import `export_pdf._rich/_markdown_flowables/_table` and `export_pptx._add_text`. A rendering rule put at those choke points changes the engine renderers too.

---

## 1. Every place a number is checked today

### 1.1 `app/pipeline/figures.py` (frozen)

| fn (line) | signature | accepts / rejects |
|---|---|---|
| `times_in` :50 | `(text) -> list[int]` | clock times as 24h hours (`_TIME` :28) |
| `numbers_in` :65 | `(text, words=False) -> list[float]` | digits through `_NUM` :29 (`(?<![\w.])(\$\|€\|£)?(\d[\d,]*(?:\.\d+)?)\s*(k\|K\|m\|M)?(?![\w])`). Number words are read only when `words=True` (`_WORD` :30: ones/tens/dozen/hundred/thousand). Clock times are stripped first. |
| `given` :100 | `(texts) -> set[float]` | `numbers_in(words=True)` over the owner's texts; times excluded |
| `given_hours` :113 | `(texts) -> set[int]` | the clock times they named |
| `close` :118 | `(a,b)->bool` | relative tolerance 0.5% |
| `holds` :122 | `(value, allowed)->bool` | `any(close(v,a))` |
| **`unsupported`** :130 | `(text, allowed, lenient_below: float = 2, hours=None) -> list[float]` | Reads digits only (never words). A non-money, non-% value `< lenient_below` is skipped. Money and % are always checked. `k` multiplies; `M` only with a currency sign. Times are checked against `hours` when that is given. |
| `quoted` :164 | `(fragment, texts)->bool` | verbatim-substring test after normalising, at least 3 chars |
| `rounded` :173 / `money` :180 | display helpers (`44,928 -> 45,000`, `$x,xxx`) | none |
| `CONSTANTS` :34 | `{52,12,7,365,4,4.33,30,24,60}` | the calendar constants arithmetic may use |

Callers of `unsupported`, with the leniency each uses:

| caller | file:line | lenient_below | what is checked | stage |
|---|---|---|---|---|
| `answer.shape.clean` | `app/pipeline/answer.py:191` | 2 (default) | headline, turn, sub | `answering` (orchestrator :269) |
| `answer.shape` figures | `answer.py:214` | 2 | `f"{value} {label}"` of each headline figure | answering |
| `answer.shape` plan name | `answer.py:225` | 2, `allowed=set(range(2,13))` | the action name ("six-week plan" fallback from `_WEEK_WORDS`) | answering |
| `action_plan.shape.ok` | `app/pipeline/action_plan.py:55`, `LENIENT_BELOW = 13` at :40 | **13** | summary; phase `title do you` (not `when`); decisions; assumptions | `roadmap` (orchestrator, after playbook) |
| `screens._clean_text` | `app/screens/generate.py:185`, `LENIENT_BELOW = 13` at :51 | **13** | captions and story sentences; a bad sentence is dropped | `screens` |
| `screens._check_story.ok` | `generate.py:192` | **13** | headline, pillars, changes, principles, local_fit, comparison rows, needs; a bad item is dropped | screens |
| `discovery.shape_fact_updates` | `app/routers/discovery.py:347` | 0 | interview fact values | `/api/discovery/interview` |
| `discovery.shape_casefile` | `discovery.py:672` (label), `:687` summary (2), `:692` their_fix (2) | 0 / 2 | case-file labels and playback | `/api/discovery/casefile` |
| `discovery._fact_value` | `discovery.py:143` | none (uses `holds` + `quoted`) | scope fact values must sit inside their quote | `/scope` |
| `capacity._num/_clock` | `app/pipeline/capacity.py:69,80` | none (`holds`) | every capacity number must be one they gave | capacity (orchestrator `_read_capacity`; also `/casefile`) |
| `answer._term` | `answer.py:65-109` | none | a move term must equal its cited claim (`_claim_matches`), a `CONSTANTS` value, or `from:"proposed"` | answering |

The allowed sets:
- `answer.allowed_numbers(texts, claims, move)` at `answer.py:161` is `given(owner_texts) ∪ claim values (and ×100 when 0<v<1) ∪ move.value/rounded ∪ proposed`. The screens use the same set (`generate._inputs` :146-175).
- `owner_texts` (`capacity.py:58`) is `main_problem, business_description, desired_outcome, revenue_today`, plus "question: answer" for each ops pair.
- The claims are `diagnose._evidence_lines(req)` (`app/pipeline/diagnose.py:62`): `client_fact_claims(ops, free) + evidence.load(req) + capacity.as_claims(...)`.

### 1.2 The r30 registry and release checks (frozen, `app/pipeline/registry.py`, 2831 lines)

- `_numbers(text)` at :231 returns `[(tok, float, unit, start, end)]`. It is the grammar `_NUM` :105, with `_SKIP_BEFORE` :160 (phase/section/page/step/week/... /model names), `_SKIP_AFTER` :166 (`x\b|×|am|pm|:\d|-\w|...|N phases/steps/modules/...`) and years `_YEAR` :179. A % becomes a fraction. **This grammar is also used by the engine** (`engine/calc/units.py:21`, `engine/gates/laws.py:224`, `engine/work_products/render_md.py:34`).
- `kpi_number_findings(text, reg, strict_kpi=False)` at :2790: every number inside a KPI/acceptance sentence (`_KPI_SENTENCE` :2743) must map to `claim_values(reg)` (:2748) in a compatible unit. Called from:
  - `export_pdf.registry_reasons` :704 (release gate);
  - `qa_experts.py:76` (quality bench);
  - `adjudicate.py:378`.
- `threshold_pass` :1742 and `label_prose_thresholds` :1827: unregistered thresholds get a "(proposed — client approval required)" label (extras.py:169,262).
- Other number-shaped laws: `policy_findings` :1882, `cadence_findings` :2008, `attempts_text_findings` :923, `ordinal_label_findings` :741, `operating_time_findings` :780, `timebasis.identity_findings` (monthly = annual/365×30).
- `validate_registry` :2703 checks the claim shape: `_REQUIRED` :2699, `CLAIM_TYPES` :87, `PROVENANCE` :93, `APPROVAL` :94.
- `export_pdf.release_status(req)` :628 → `draft | final | client_approved`. Its reasons come from: run done; documents present; QA highs; `find_artifacts` :576 (regex classes incl. "invented ROI figure", "currency sign on a count"); `registry_reasons` :684; integrity report current and clean. **Nothing names a page.** `_is_draft` :773 stamps DRAFT on every page (`_page_chrome` :1722).
- `export_pdf.presentation_findings(path)` :475 (pymupdf): fonts, glyph round-trip, orphan headings, thin last page. **It does name pages** ("... on page N"). It is the only page-aware check, and it is reused by the engine as P1 (`engine/gates/presentation.py`).
- `integrity.verify` :1145, `validate_rendered` :1241 and `statement_findings` :622 are names, gate, policy and attempts laws. **No general law that each number traces to a claim.**
- `decompose.py:160-201`: financial-model `lines` must be a plain product of the operand numbers (period step ×1/12/26/52/365, 5% tolerance, then repaired to the exact product) → `arithmetic_verified`. `derived_claims` (registry :355) only takes verified lines.
- `diagnose._sanitize_hypotheses` :156 drops cited claim ids that do not exist. Hypothesis prose numbers are not checked.

### 1.3 Probe of today's behaviour (ran it, `allowed={22}`)

| text | default (2) | lenient 13 | lenient 0 | `numbers_in(words=True)` |
|---|---|---|---|---|
| `twelve classes` | [] | [] | [] | [12] |
| `a dozen spots` | [] | [] | [] | [12] |
| `3x more bookings` | [] | [] | [] | [] |
| `3× more bookings` | [3] | [] | [3] | [3] |
| `the 3rd phase` / `1st week` | [] | [] | [] | [] |
| `8 hrs a week` | [8] | **[]** | [8] | [8] |
| `12 reformers` | [12] | **[]** | [12] | |
| `2-3 weeks` | [2,3] | **[]** | [2,3] | |
| `six-week pilot` | [] | [] | [] | [6] |
| `1.5 hours` | [] | [] | [1.5] | |
| `one in 20` | [20] | [20] | [20] | [20,1] |
| `$35`, `50%`, `10k` | caught at every leniency | | | |

`registry._numbers`: `twelve`→[], `3x`→[], `3×`→[], `the 3rd phase`→[3], `Phase 2`→[], `in 2025`→[], `6pm`→[], `70B`→[], `25%`→0.25 %.

### 1.4 Tests that pin the checker (V)

`tests/test_consultation_flow.py` has 28 tests and is frozen:
- `test_given_reads_number_words_and_keeps_clock_times_apart` :45
- **`test_unsupported_catches_invented_money_and_leaves_small_prose_alone` :54**. It asserts that `"one of 1 explanations"` → []. This pins the leniency below 2 and **must change**.
- `test_the_move_is_multiplied_here_and_the_proposal_is_labelled` :~105, `test_a_term_that_misquotes_its_figure_kills_the_move`, `test_a_move_resting_only_on_proposals_is_refused`
- `test_the_answer_drops_a_figure_she_never_gave` :~133, `test_a_headline_with_an_invented_number_is_not_shown`
- `test_the_roadmap_is_phases_we_carry_out_and_decisions_they_make`, `test_a_phase_with_an_invented_price_is_dropped_and_too_few_phases_kill_it`, `test_a_roadmap_needs_a_decision_with_real_options`
- `test_case_file_keeps_only_figures_quoted_from_their_words` :217

`tests/test_discovery.py` has 17 tests and is frozen: `test_fact_updates_drop_numbers_they_never_gave` :~300, `test_fact_updates_never_overwrite_what_they_said_they_do_not_know`, `test_new_facts_are_capped_per_round_and_never_duplicate`.

`tests/test_screens.py` has 23 tests and is frozen. **No test pins `LENIENT_BELOW`, `_clean_text` or `_check_story`**, so the leniency of 13 is unpinned. The action_plan 13 is pinned only indirectly ($35 is caught).

Registry KPI/threshold laws are pinned across `test_registry_controls.py` (51), `test_run51_r2.py`, `test_run52_controls.py`, `test_run53_r*.py`, `test_volume_one_brief.py` and `test_consultancy_layers.py` (91 tests). Engine: `tests/engine/test_engine_calc.py` (25 tests, e.g. `test_product_recompute_is_exact_428_not_430`, `test_quantity_refuses_float`, `test_hours_times_a_share_the_client_never_gave_is_refused`).

Baseline I ran just now: `pytest tests/test_consultation_flow.py tests/test_discovery.py tests/test_screens.py` → **76 passed**. `tests/engine/test_engine_r30_frozen.py` passes. `tests/engine/test_engine_mutation_manifest.py` has **3 failures that predate this work** (pins that resolve to nothing, plus unapplicable anchors C5.m6 and C10.m3). The step-1 plan records the whole-suite baseline as `45 failed, 1734 passed, 1 skipped`.

---

## 2. The registry `Claim` and the exact calculator

### 2.1 The r30 claim dict (what the spec calls "registry Claim"), V

- Built by `_claim(cid, ctype, value, unit, *, time_basis="n/a", population, scope, phase, provenance, approval, source, sections, text="", **extra) -> dict` at `registry.py:266`. Fields: `id, type, value(float), unit, time_basis, population, scope, phase, provenance, approval_status, source, allowed_sections, text` plus extras (`question`, `event`, `item`, `formula`, `scenario`, `origin`, `cell`, `file`, `accepted`).
- Provenance :93 is `{"client_input","machine_computed","canonical_gate","consultant_proposed"}`. Approval :94 is `{"client_stated","machine_verified","consultant_proposed — client approval required","rejected"}`.
- Producers:

| id prefix | producer | provenance | source text |
|---|---|---|---|
| `CF-nn` | `client_fact_claims(ops, free_texts)` :325 | client_input | `"discovery: <question>"` / `"client brief"` |
| `CE-nn` | `evidence.extract` (`app/pipeline/evidence.py:252`) | client_input, `origin:"file"` | `"<file> · <sheet> · <CELL>"` plus `cell`, `file` |
| `DV-nn` | `derived_claims(fm)` :355 | machine_computed | `"financial_model.lines[i]: <arithmetic>"` |
| `TB-nn-day/month`, `SI-nn-month` | `derived_claims` | machine_computed | `v/365`, `v/365×30`, computed in Python floats |
| `SA-nn-j` | `derived_claims` | consultant_proposed | scenario assumption ratios |
| `SI-nn-j` | `derived_claims` | machine_computed | scenario impacts |
| `PG` values | `claim_values` :2748 from `pilot_gate` | (canonical_gate) | — |
| thresholds / module_kpi | `type_technical_specs` :2238, `kpi_statements` :2415 | consultant_proposed | — |
| `CAP-nn` (**not in the registry**) | `capacity.as_claims` (`capacity.py:~327`) | machine_computed | `"computed from their figures"` with `working` |

- Persisted as `Request.registry_json`, built once in `decompose.py:650` (`build_registry(ops_numbers_json, business_case, modules, free_texts=[...], extra_claims=evidence.load(req))`). It is also rebuilt in `adjudicate.py:224`. Read through `registry_for(req)` :2827.

### 2.2 The engine's typed numbers and exact calculator, V

- `Quantity(value: Decimal, unit: str, unit_family: UnitFamily, dimensions: Dimensions, precision: int = 2)` at `app/engine/types.py:431`. Floats are refused (`_decimal`, `test_quantity_refuses_float`).
- `Dimensions(currency, period, period_basis, scope, as_of, definition)` at :411, all `None` = unknown. `UnitFamily` at :266 is MONEY|COUNT|TIME|RATE|CAPACITY|DISTANCE_AREA_MASS|OTHER.
- `FactPayload(statement, basis: FactBasis, measure_id, quantity, record_class, formula, inputs, topic)` at :565. `AssumptionPayload(statement, rationale, quantity, approval: ApprovalState, used_by)` at :577. `Provenance(actor, actor_ref, derived_from, source_locator, model_call_id, recorded_at)` at :451.
- `make_entity(*, kind, engagement_id, payload, provenance, confidence, relevance, relation, status, entity_id="", labels=()) -> Entity` at :1237. Transient entities with a caller-chosen id are possible.
- Calculator protocol at `app/engine/registry.py:184`. `CalcResult(quantity, formula, inputs)` at :177. `IncomparableInputs` at :171. They are re-exported by `app/engine/calc/__init__.py`.
- `DecimalCalculator(view: RegistryView | None = None)` at `app/engine/calc/arith.py:94`:
  - `product(inputs: Sequence[Entity], *, unit, unit_family, period_step=1) -> CalcResult` at :152. `period_step ∈ PERIOD_STEPS.values()={1,12,26,52,365}` (:38). A RATE input must pass `share_is_given` (a FACT that is not inferred, or an APPROVED ASSUMPTION). MONEY needs `dimensions.currency`, and needs a MONEY input. Mixed period bases are refused.
  - `total(inputs)` :199 (addition only). `ratio(n, d)` :233. `convert_period(fact, to_basis)` :260. `recompute(calculated, registry) -> bool` :279 demands equality. `comparable(a,b)` :303.
  - `evaluate(formula, values: dict[str, Decimal]) -> Decimal` at :309 is a pure grammar: ids `[A-Z]{3}-\d+`, literals, `+ - * / ()`.
- `units.parse_quantity(text, context="", *, dimensions=None) -> Quantity|None` at `units.py:129` builds the Decimal from the source token. `format_quantity(q) -> str` at :161 is deterministic and never rounds past `precision`.

### 2.3 Import directions, V

- `app/pipeline`, `app/routers`, `app/screens` and `app/prompts` **never import `app.engine`**. The only non-engine importers are `app/config.py:157,173` (`BOUNDS`) and `main.py:11-12` (router and startup).
- The engine imports the pipeline at module top:
  - `engine/calc/units.py:21` ← `pipeline.registry._numbers,_infer_unit,canonical_capacity_unit`
  - `engine/llm.py:35` ← `pipeline._shared`
  - `engine/legacy/mapping.py:50-51`
  - `engine/legacy/r30_adapter.py:38-41`
  - `engine/work_products/render_pdf.py:55` ← `export_pdf._EngagementDoc,_S,_SECTION_COUNTER,_h1,_markdown_flowables,_page_chrome,_rich,_table,strip_page_chrome,F_SB,LINE`
  - `render_deck.py:28` ← `export_pptx.MARGIN,SLIDE_H,SLIDE_W,_add_bg,_add_bullets,_add_text,_hairline,_hex_to_rgb,_kicker`
  - `render_md.py:34`, `canon_bridge.py:27`, `corrections.py:40`, `statements.py:33`
- Lazy imports of the pipeline also exist (`gates/laws.py`, `gates/presentation.py`, `gates/release.py`), and `engine/api/router.py:75` imports `app.routers.requests`.
- `engine/types.py` imports only the stdlib. `engine/registry.py` imports only `engine.authority` and `engine.types` (config is imported lazily at :423). Both are safe for the pipeline to import.
- **I. A shared leaf package is needed, or at least lazy imports.** The cycle would be `pipeline.registry → engine.calc → engine.calc.units → pipeline.registry`. Proposed home: `app/figures/` (a new package under `app/`). It is outside the frozen roots and outside the engine. It may import `app.engine.types` and, lazily, `app.engine.calc`.

---

## 3. Every path a number takes to a client

| surface | where numbers are produced | where rendered | structured or free text | checked today? |
|---|---|---|---|---|
| **Answer (web)** `GET /api/requests/{ref}/decision` → `_decision_payload` (`app/routers/requests.py:607`) → `frontend/src/components/consult/Answer.tsx:100-160` | `answer.write` (`answer.py:258`) stores `answer_json`: headline/turn/sub (model prose); `figures[].value` (a **model string**, e.g. "$22 vs $32"); `move.{value,rounded}` (float, code); `move.display/working` (**code string**, `answer.py:143-153`); `proposed[].value` (float) | `Answer.tsx` shows `f.value`, `move.display`, `move.working`, and `fmt(p.value)` (`frontend/src/utils/week.ts:14`) | mixed | yes (§1.1), except the fallback `d.central_problem`/`d.summary` |
| **Decision/diagnosis prose (web)** same payload | `decide` → `consulting_recommendations_json` (`consulting_summary, central_problem, why_not_the_others, unverified[]`), `analyze` (`pain_points, growth_opportunity`), `diagnosis_json` (`statement, because, would_need`, cites → claim `text` = client's words) | Answer.tsx, Package.tsx (`unverified`, roadmap assumptions :198) | free text | **no number check** |
| **Week grid (web)** `capacity` in the decision/preview/shared payloads | `capacity.shape` (`capacity.py:142`): ints/floats checked against their words, `derived[].working` (code string) | `WeekGrid.tsx`, `weekHeadline` (`utils/week.ts:20`) formats numbers client-side | structured | yes (`holds`) |
| **Roadmap (web + proposal PDF)** `GET /plan`, `action_plan` in payloads | `action_plan.write` (`action_plan.py`) → `action_plan_json` | `Package.tsx:313-330`; `screens/render.proposal_context` phases | free text (`when` unchecked) | yes, leniency 13 |
| **Interview / case file (web, before any request exists)** `POST /api/discovery/interview`, `/casefile`, `/scope` | fact `value` strings (≤60 chars), case-file `figures[].value` strings, `capacity` | `Interview.tsx:91-95` (fact chips, with "ours"/"file" small tags), case-file panel | short strings | yes (lenient 0) |
| **Thinking trail (web)** `/progress.thinking` | `diagnose.narrate(...)` (`diagnose.py:444`), e.g. `f"Testing all {len(hypotheses)} against their own figures"` (:348); `detail` strings; `"{n} screens drawn"` (orchestrator) | `Thinking.tsx`, progress | free text, **our process counts** | no |
| **Legacy result page (web)** `GET /preview` (`requests.py:926`) | `mvp_blueprint`, `technical_plan` (markdown), `business_case`, `scoreboard`, `procedures`, `playbook`, `ops_numbers`, `answer`, `capacity`... | `frontend/src/routes/StudioPage.tsx` (3288 lines) | free text plus model JSON | KPI sentences only |
| **Shared link** `GET /api/shared/{token}` (`app/routers/shared.py:44`) | answer, capacity, action_plan, `summary`, `unverified`, screen stories | `frontend/src/routes/SharedPage.tsx` | mixed | as above |
| **PDF volumes I–III** `GET /export/pdf/{blueprint\|technical\|operations}` → `export_pdf.build_pdf(req, kind)` (`export_pdf.py:1759`); zip `build_zip` (`requests.py:1282`) | markdown from `blueprint.write_*` (model prose); structured layers `_financial_model_flowables` :1128 (`lines[].annual` strings), `_pilot_gate_flowables` :1069 (`_quantity` :1052), `_scoreboard_flowables` :949, `_evidence_flowables` :1192 (ops answers verbatim), procedures, checklists | reportlab: `_rich` :266, `_markdown_flowables` :335, `_table` :839, `Paragraph`; page chrome `_page_chrome` :1722 (page numbers, DRAFT) | free text | KPI sentences, plus gate/policy/attempts; the LLM bench `qa_numbers.j2` |
| **Proposal PDF (Volume IV), drawn screens** `GET /export/pdf/system` → `screens/export.build_system_pdf` (`app/screens/export.py:18`) → `render.proposal_context` (`app/screens/render.py:224`) + `proposal_html` :303 → Chromium (`screens/browser.render_pdf`) | story/captions (checked, leniency 13); **`hero_kpi` = first `kpis` block item (sample data, unchecked)**; `answer.figures`, `move.display/working/proposed` (`_fmt` :112); roadmap phases; screen blocks (kpis/table/pipeline/board... sample data) | Jinja `_env` (`render.py:28`), templates `app/screens/templates/{proposal,system,_blocks,_frame}.html` | sample data plus checked prose | partly |
| **System viewer (web)** `GET /system` → `generate.payload` (`generate.py:442`) | `render.system_html(system,"web")`: the whole HTML, sample data | `frontend/src/components/consult/SystemViewer.tsx` (sandboxed iframe) | server-rendered HTML | captions only |
| **Deck** `GET /export/pptx` (`requests.py:1370`) → `export_pptx.build_presentation(req, analysis, consult_result, plan_result, images)` (`export_pptx.py:301`) | analysis/consult prose, `modules[].name/purpose`, `business_case`, `playbook`, screen `spec_json` stories, `f"{i+1:02d}"` ordinals | choke point `_add_text(slide, text, ...)` (`export_pptx.py:128`, ~42 call sites), `_add_bullets` :174 | free text | **no number check** |
| **Emails** `app/mailer.py` | `notify_owner_ready` :110, `notify_owner_released` :143: fixed copy, plus `business_name`/`concept` and the run URL (`public_id`) | plain text | fixed copy | n/a. Client emails carry **no figures** today; team emails (`notify_team_failure` :171, `go_ahead` :128) are internal |

V: the screens docstring (`generate.py:17-20`) says "the screens carry sample data and say so on every frame". `what_this_is.py:68` says "plausible numbers for a business your size". **That is a fifth class of number the four tags do not cover** (see §7, conflicts).

---

## 4. The case file and the facts store today

V, `app/models.py` (`Request`, a single wide table; plus `GeneratedImage`, `AiUsageEvent`; the engine adds `engagements`, `engagement_entities`, `engagement_turns`, ... in `app/engine/persistence/models.py` on the same `Base`):

| column (line) | holds |
|---|---|
| `ops_numbers_json` :54 | interview Q&A `[{"question","answer"}]`. Sanitised by `_sanitize_ops_numbers` (`requests.py:141`), which **drops each pair's `id`**, so the source can only be cited as an index. |
| `brief_json` :113 | scope plus `facts[{key,group,label,status∈need/got/estimate/file,value≤60}]`. Client-built JSON, shape-checked only (`_sanitize_brief` :182). |
| `business_description, main_problem, desired_outcome, revenue_today` | free text; numbers in them become CF claims and enter `given()` |
| `evidence_json` :82 | CE claims from files (`evidence.save` :345). Routes `GET/POST/DELETE /{ref}/evidence` (`requests.py:713-786`). Ingested at diagnosis start (`orchestrator._run_diagnosis`). |
| `capacity_json` :99 | the capacity picture plus `derived[]` (CAP) |
| `registry_json` :170 | the r30 registry (claims etc.), built at decompose |
| `answer_json` :104, `action_plan_json` :108, `screens_json` :120 | outputs |

- The case file today: `POST /api/discovery/casefile` (`discovery.py:696`) recomputes `{figures:[{source,token,value,label}], capacity, summary?, their_words?, their_fix?}` from form fields (`casefile_sources` :619 builds ids `main_problem`, `<qid>`, `field:<k>`) on every call. **Nothing is persisted.** No interview session exists before `POST /api/requests` (`create_request` :248, which writes `ops_numbers_json` :326 and `brief_json` :329).
- `_ensure_columns` at `app/database.py:56-73`, quoted:

```python
def _ensure_columns() -> None:
    """Minimal SQLite forward-migration: create_all() never alters existing
    tables, so columns added to a model after a dev DB was first created
    have to be ADD COLUMNed here. Idempotent and additive-only."""
    ...
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in existing:
                    ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column.type.compile(engine.dialect)}"
                    conn.execute(text(ddl))
```

  Called from `init_db()` :49. It is generic: any new model column, or any new table on `Base`, is picked up with no extra code.
- **I. The natural single store of `theirs`:** a new `Request.case_file_json` (Text, nullable) holding a list of `theirs` Figures, each with its source:
  - `turn:<n>` with the quote, for typed answers and free fields;
  - `file:<name>·<sheet>·<cell>`, for CE figures.

  It is written at `create_request` (from ops and free texts) and by evidence ingest, add and remove. `client_fact_claims`, `evidence.load` and `figures.given(owner_texts)` then become readers of it.

  Alternative: a `case_figures` table (one row per figure, nullable `request_id` plus a future `session_ref`) is ready for the Step 6 pre-request interview session. Both options suit `_ensure_columns`. **Decision for the owner/planner:** a column now, or a table keyed for Step 6.

---

## 5. Freeze coverage (`tests/engine/r30_manifest.json`)

V: `roots = ["app/pipeline","app/prompts","tools"]`, plus top-level `tests/*.py` (conftest included). `tests/engine/**` is excluded. 104 files, `commit 24688c7`.

- **Frozen** (every edit forces a re-freeze): all of `app/pipeline/*.py` (incl. `figures.py, answer.py, action_plan.py, capacity.py, registry.py, export_pdf.py, export_pptx.py, evidence.py, diagnose.py, integrity.py, decompose.py`), all `app/prompts/*.j2`, `tools/{adjudicate_run,inspect_pdf,preflight_fixture,release_audit}.py`, all top-level `tests/*.py`. The collector (`test_engine_r30_frozen.collect_frozen_files`, :41) also **catches new files** added under those roots or at the top level of `tests/`.
- **Not frozen:** `app/screens/**`, `app/routers/**`, `app/models.py`, `app/database.py`, `app/mailer.py`, `app/config.py`, `app/engine/**`, a new `app/figures/**`, `tests/engine/**`, **and any test subdirectory such as `tests/figures/`** (the collector reads only top-level files in `tests/`; V at :53-60).
- Re-freeze procedure (`tests/engine/refreeze_r30.py` docstring):
  1. Commit the frozen changes.
  2. Run `python tests/engine/refreeze_r30.py --commit <short-sha-of-last-frozen-change> [--after "<what>"]`. It refuses on a dirty frozen tree, rewrites `files`, `commit` and `file_count`, and appends to `recorded`.
  3. Update the two asserted constants: `tests/engine/test_engine_r30_frozen.py` (docstring mention) and `tests/engine/test_engine_mutation_manifest.py:526` (`assert manifest["commit"] == "24688c7"`).
  4. Commit `test(engine): re-freeze r30 at <sha>`. Precedent: `39e3920`, and `514faec` per the spec.
- **Mutation anchors** (`scratchpad/mutate_engine.py`, checked by `test_every_declared_anchor_matches_its_source_exactly_once`): text-anchored edits exist in `app/engine/types.py` (3), `app/engine/registry.py` (4), `app/engine/calc/arith.py` (2) and `app/pipeline/registry.py` (anchor `# ── client facts`, C21.m3). Editing that anchor text breaks the mutation test. Run it after touching those files. It already has 3 failures from before this work.

---

## 6. Prompt examples with literal figures

V (`app/prompts`, all frozen). The model-facing examples:

| prompt:line | literal | as the new checker would see it if copied |
|---|---|---|
| `answer.j2:33` | `"$22 vs $32"`, `"8 hrs"` | `$22/$32` are money, caught unless theirs. `8` is caught under the default 2 today, and passes only on screens/roadmap (13). |
| `answer.j2:36-40` | `144` `CAP-05`, `52` constant, `28` proposed, `22` `CF-04` | structured terms, not prose. Fine. |
| `answer.j2:41` | `"moving 6pm and 7pm to $28, if regulars stay"` | `$28`: caught unless proposed. Times are checked against hours. |
| `answer.j2:46` | `{"weeks": 6, "name": "six-week pilot"}`, `"four-week plan"` | words: **missed today** |
| `casefile.j2:8-10` | `"about 10 of 12"`, `"$22 a class"`, `"8 hrs"`, `"1 in 20"`, `"$200 for 10"` | checked by quote; `1` is skipped |
| `capacity.j2:9,16` | `"400 orders a month ... 340"`, `"about 10 of 12"` | `holds()` against their texts |
| `screens_plan.j2:34` | `"10-pack, 3 left, regular at 6pm"`, `"Rana K."`, `"M3-A"`, `"R8"` | cast notes are sample data. Small numbers pass at 13. `M3-A` is an identifier. |
| `screen.j2:33-35` | `1280 × 800`, `"R. H., 31"`, `"90 minutes"` | instructions plus sample rows. In a caption or the story, `31` and `90` are ≥13 and get caught today. In screen block values (the rows), nothing is checked. |
| `app/screens/generate.py:54-60` `BLOCK_GUIDE` (not frozen) | `"22/29"`, `"$18,400"`, `"26 min"`, `"$1,200"`, `"M3-A"`, `"09:00"` | block values are **never checked** |
| `decompose.j2:39-40,79,98,125-127` | `$85`, `14 hours`, `~$1,800`, `3 no-shows/week x $95 x 52 weeks`, `25%`, `$17,500/year`, `~84 support hours/month`, `31,937.5` | copied into business_case prose: only KPI sentences or arithmetic verification would catch them |
| `blueprint.j2:73,108` | `$85`, `$1.80` | blueprint prose: **not checked** outside KPI sentences |
| `interview.j2:39,67,79` | `"150 a week"`, `"$75"`, `340 visits ... $85`, range options `"Under 20"`... | fact values lenient 0. `options` are not checked (they are choices). |
| `playbook.j2:35`, `technical_plan.j2:65`, `module_spec.j2:21` | `85%`, `100% of`, `within 3 months`, `Q3 2024` | threshold labelling, not tracing |
| `qa_numbers.j2:25`, `test_hypothesis.j2:37` | `3 x $95 x 52 weeks = $19,000`, `320 sessions` | auditor/tester instructions; output not client-facing |

**I.** The spec rule "every prompt example figure is clearly an example that the checker will catch if copied" needs a test. For each `.j2`, extract the example lines and assert that `new_checker.unsupported(example, known=∅)` flags every number in them. Today it would fail for the words, for `3x`, and for small numbers.

---

## 7. Proposed decomposition (in dependency order)

New code goes in `app/figures/` (not frozen) and new tests in `tests/figures/` (not frozen). The edits to frozen call sites, and the re-freeze, come last.

### T1. `Figure` type and mapping from r30 claims
- **Create** `app/figures/__init__.py`, `app/figures/model.py`.
- **Interface:**
  - `Kind = Literal["theirs","derived","ours","reference"]`.
  - `@dataclass(frozen=True) class Figure: id: str; value: Decimal; unit: str; period: str | None; kind: Kind; source: TheirsSource | Working | Proposal | Reference; precision: int; display: str` (computed). The source types:
    - `TheirsSource(turn: int | None, field: str | None, quote: str, file: str | None, cell: str | None)`;
    - `Working(inputs: tuple[str,...], op: str, formula: str)`;
    - `Proposal(note: str)`;
    - `Reference(publication, year, population, url)`.
  - `def display(f) -> str`: theirs shown exactly, derived/ours with "~" per the firm rule, reference as given.
  - `def from_claim(c: dict) -> Figure`: provenance map `client_input→theirs`, `machine_computed→derived`, `consultant_proposed→ours`, `canonical_gate→?`.
  - `def to_claim(f) -> dict`: keeps `validate_registry` happy.
  - `class FigureSet` with `.match(value, unit=None) -> Figure | None` (unique match, else None).
- **Tests:** `tests/figures/test_model.py`. Round-trip of CF/CE/DV/SA/CAP claims. A Decimal comes from a token, never a float. Display rules per kind.
- **Risk:** low. Decide the `canonical_gate` mapping: the gate target is ours (proposed), the baseline is theirs.

### T2. The rebuilt checker
- **Create** `app/figures/read.py`.
- **Interface:**
  - `@dataclass Mention(text, start, end, value: Decimal, form: Literal["digit","word","multiplier","ordinal","percent","money","time","year","range"])`.
  - `def mentions(text) -> list[Mention]`: words incl. compounds, "a dozen", "half"; `3x`, `3×`, `threefold`; `3rd`, `third`; clock times; years.
  - `def unsupported(text, known: FigureSet, hours: set[int] | None = None) -> list[Mention]`: **no leniency**. Exemptions only by declared form: clock times against hours. Whether years and list ordinals are exempt is a decision.
- **Modify (frozen):** `app/pipeline/figures.py` becomes a thin delegate. `numbers_in`/`given`/`unsupported` keep their signatures but lose `lenient_below`. Delete `LENIENT_BELOW` in `action_plan.py:40` and in `app/screens/generate.py:51` (with the call sites :55, :185, :192). Fix `answer.py:225`.
- **Tests:** `tests/figures/test_read.py` covers every row of §1.3 that passes today: `twelve`, `a dozen`, `3x`, `3×`, `3rd`, `1st`, `8 hrs`, `12 reformers`, `2-3 weeks`, `six-week`, `1.5`, `0.5` → caught. Update `test_consultation_flow.py:54` (`"one of 1 explanations"` now caught, or reworded).
- **Risk: high on behaviour.** Model prose is full of "two weeks", "one of", "Weeks 1-2". Expect more rejections, more retries, more cost, and possibly `StageFailed` in answer/roadmap/screens. Needs the T3/T6 token approach so the model stops writing raw numbers. Do not change `registry._numbers`: the engine and the mutation anchors depend on it.

### T3. Literal substitution
- **Create** `app/figures/substitute.py`.
- **Interface:**
  - `def bind(text, known: FigureSet, hours=None) -> tuple[str, list[Figure], list[Mention]]`: a mention matching exactly one known figure (incl. the model's rounding of it) is replaced by `display(figure)`. Ambiguous or unmatched mentions are returned as unsupported.
  - Optionally a token grammar `{{F:<id>}}`, resolved to the literal (prior art: `engine/work_products/corrections.unresolved_tokens`).
- **Tests:** `"about $45,000"` with derived 44,928 → the figure's display. An ambiguous match is refused. Theirs is never re-rounded.
- **Risk:** medium. Matching tolerance (0.5% today, or `RENDERED_RESTATEMENT_TOLERANCE`=0.005) can hit two figures.

### T4. Case file as the single store of theirs
- **Modify:** `app/models.py` (+`case_file_json`, or a `CaseFigure` table, via `_ensure_columns`); `app/routers/requests.py` (`create_request` writes it; `_sanitize_ops_numbers` keeps the turn index/id; the evidence routes update it). Frozen: `app/pipeline/evidence.py` (`save` writes into the case file), `registry.client_fact_claims` and `diagnose._evidence_lines`, which read from it. `app/routers/discovery.py` (`/casefile` returns Figures).
- **Interface:** `app/figures/casefile.py`: `def load(req) -> FigureSet`, `def build_from_request(req) -> list[Figure]`, `def add_file_figures(req, claims)`, `def remove(req, figure_id)`.
- **Tests:** `tests/figures/test_casefile.py`. Every CF/CE is present with its source turn or cell. `given()` equals the case file's values. Old rows with no case file are built on read.
- **Risk:** medium (data). Old rows need a read-time fallback. `brief_json` fact values are client-supplied JSON and must never become `theirs` unless they sit inside a quote (`_fact_value`).

### T5. Derived arithmetic through the exact calculator
- **Create** `app/figures/calc.py`.
- **Interface:** `def derive(op: Literal["product","total","ratio","convert_period","difference"], inputs: list[Figure], *, unit, period_step=1, to_basis=None) -> Figure` (kind=derived, `Working`). It builds transient entities through `make_entity(entity_id=...)`, with lazy imports of `app.engine.calc`/`app.engine.types`.
- **Migrate:** `capacity.shape` CAP products (`capacity.py:170-254`), `answer.compute_move` (`answer.py:112`), `registry.derived_claims` TB/SI conversions (`registry.py:378-398`, where `v/365×30` is not a `PERIOD_STEPS` ratio).
- **Tests:** `tests/figures/test_calc.py`. 12×6×6=432 exact. A move with a difference. A refusal on a share nobody gave. A Decimal result.
- **Risk: high (design conflicts, see below).** Also the import cycle: never import `app.engine.calc` at the top of a pipeline module.

### T6. Every client payload carries Figures
- **Modify:**
  - frozen: `answer.py`, which stores `figures[]` as Figure refs plus a `figures` map, and `move` as a derived Figure with Working and `proposed` as ours Figures;
  - frozen: `action_plan.py`;
  - not frozen: `app/screens/generate.py`;
  - `app/routers/requests.py` (`_decision_payload`, `/preview`, `/system`) and `app/routers/shared.py`, which add `figures: {id: Figure.as_json}` and run `bind` over the prose that is unchecked today (`consulting_summary, central_problem, why_not_the_others, unverified, diagnosis because/statement, pain_points, growth_opportunity`, and the blueprint/technical markdown and business_case strings).
- **Interface:** `def tag_text(text, known) -> list[Segment]`, where `Segment = {"text": str} | {"figure": id}`, for the web.
- **Tests:** payload tests (extend the patterns in `test_studio_result_page.py` / `test_admin_payload.py` in new `tests/figures/test_payloads.py`). No digit outside a figure segment.
- **Risk:** high (breadth). The legacy `StudioPage.tsx` renders raw markdown.

### T7. The rendering rule in code (release law)
- **Create** `app/figures/law.py`.
- **Interface:**
  - `class UntaggedNumber(Exception): where: str`.
  - `def require_tagged(text, known, *, where) -> str` (raises).
  - `def page_findings(pdf_path, known) -> list[str]` (pymupdf page scan, modelled on `export_pdf.presentation_findings` :475, minus the furniture from `strip_page_chrome` :1698 and `_page_chrome`). Returns `"untagged number '35' on page 7"`.
- **Wire:**
  - PDF: frozen `export_pdf.py`. `_rich`/`_markdown_flowables`/`_table` go through `require_tagged`. `release_status` :628 adds `page_findings` reasons.
  - Deck: frozen `export_pptx._add_text` :128.
  - Screens: not frozen. Jinja `finalize` on `render._env` :28 refuses unmarked digits; figures render through a `fig` filter.
  - Web: `frontend/src/components/consult/` gets a `Fig` component, plus a test that consult components render no raw number (check the API types `frontend/src/api/consultant.ts:460-560`).
  - Email: a test that client bodies (`mailer.py:110,143`) carry no figure.
- **Repair** the engine renderers that share the choke points (`engine/work_products/render_pdf.py:55`, `render_deck.py:28`) in the same task.
- **Tests:** `tests/figures/test_law.py`. Plus the acceptance test: render the blueprint PDF from a fixture row (pattern `test_consultancy_layers.py:259 test_blueprint_pdf_roundtrip`) with one untagged number injected → `release_status(...)["status"]=="draft"`, and a reason names the page.
- **Risk:** high. The furniture (page numbers, "Volume I", dates, `01` numerals, clock times, process counts, identifiers like `M3-A`) must be declared and not guessed. The engine suite must stay green.

### T8. Prompts and the prompt-example law
- **Modify (frozen):** `answer.j2`, `roadmap.j2`, `screens_plan.j2`, `screen.j2`, `decompose.j2`, `blueprint.j2`, `casefile.j2`, `interview.j2`. Each one either cites figure ids/tokens instead of writing numbers, or marks examples so they are obviously examples. Also `BLOCK_GUIDE` (`generate.py:54`).
- **Tests:** `tests/figures/test_prompt_examples.py`. Every number in example text of every `.j2` is flagged by `unsupported(..., known=∅)`.
- **Risk:** medium (prompt wording changes model output). Free in tests: the stubs stand in.

### T9. Acceptance, engine suite, re-freeze
- Run the full consultant suite against the baseline (`45 failed` recorded in step 1, incl. the 3 mutation-manifest failures). Run `tests/engine` green except the known failures.
- `python tests/engine/refreeze_r30.py --commit <sha> --after "the typed-figures step"`, then update the 2 constants and commit.
- **Risk:** low, but mandatory.

**Dependencies:** T1 → T2 → T3; T1 → T4; T1 → T5. Then T2–T5 → T6 → T7 → T9. T8 can run after T2, alongside T6–T7.

### Where the design conflicts with the code (decisions needed)
1. **"Engine registry Claim" does not exist.** The three provenances belong to the r30 claim dict, and the engine uses `FactBasis`/`ApprovalState`. Pick: Figure extends the r30 dict (a natural fit for the pipeline). The engine calculator is then reached only through an adapter (T5). The fourth provenance, `canonical_gate`, needs a mapping.
2. **The exact calculator is stricter than the pipeline's arithmetic:**
   - no subtraction op (only `evaluate()` has `-`), yet `answer` move terms use differences;
   - `period_step` is limited to {1,12,26,52,365}, while `CONSTANTS` holds 7, 24, 60, 4.33 and 30, and the 30-day month identity (`v/365×30`) is not a step;
   - a RATE (share) multiplies a client figure only when the client stated it or an ASSUMPTION is APPROVED. Our proposals (`SA-` ratios, "if a third of no-shows recover") would be **refused**;
   - MONEY needs `dimensions.currency`, and the pipeline uses unit `"USD"`;
   - formula ids must match `[A-Z]{3}-\d+`, which `CF-01`/`CE-01`/`DV-01` do not;
   - floats are refused; the pipeline holds floats.
3. **Screens' sample data** (KPI tiles, tables, the proposal `hero_kpi`) is neither theirs, derived, ours nor reference. Under "four tags are the whole law", either screens draw only tagged figures and labelled sample values become a declared fifth class, or sample numbers are dropped. Owner call.
4. **Process numbers and furniture:** page numbers, volume numerals, `"{n} screens drawn"`, "Testing all 5", phase ordinals, dates, clock times, identifiers (`M3-A`), the "six-week plan" label written by code. The law must classify them explicitly (furniture/structure vs figure). Today `registry._numbers` encodes some of these skips as regexes, which the owner's rules forbid adding as special cases. **I.** Declare the furniture by the renderer that draws it rather than by regex.
5. **The case file before a request exists:** the spec's "single store" and the Step 6 server-side interview session overlap. Today there is no session row, and the turn ids are dropped when stored.
6. **Engine renderers share the r30 choke points.** The rule placed in `export_pdf._rich/_table/_markdown_flowables` and `export_pptx._add_text` changes engine output. The spec allows repairing them in the same step, and it must be budgeted.
7. **`registry._numbers` must not change semantics:** the engine's calc, laws and render_md depend on it, it carries a mutation anchor, and it is frozen. The new checker should be a separate reader, not a rewrite of it.
