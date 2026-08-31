# The universal consultancy engine

One engine runs every engagement. There is no engagement-type switch anywhere in `app/engine`, and there
cannot be one: method selection reads enums, work-product applicability reads counts over enums, and the
type system refuses a filter on a free-text field. This document is the map. `EXTENSION_CONTRACTS.md` says
how to add to it without touching the orchestrator; `LIMITATIONS.md` says what it does not do and what the
tests do not prove.

The five registries below are pinned by `tests/engine/test_engine_docs.py`: the tables here must list
exactly what the code registers, in both directions. A method registered and not documented fails the
suite, and so does a method documented and not registered. That is the only defence a document has against
going stale silently.

## 1. The spine

One typed, append-only, hash-addressed **Engagement Registry** is the only state. Every entity of every
kind (41 kinds) carries one envelope - provenance, authority, confidence, relevance to a decision, relation
to the central decision, status - and its authority is derived from its information type at write time,
never chosen by the producer (I7). The Partner, every method, every specialist, synthesis and every
renderer is a pure function `RegistryView -> deltas (Add | Supersede | SetStatus)`. Nothing edits in place,
so lineage is the row history and a superseded claim stays queryable.

Four consequences the rest of this document keeps returning to:

1. **Absence is a first-class state.** `Confidence(None)`, `Dimensions(currency=None)`, `Status.PROPOSED`,
   an unmet `InputSpec` - each is a typed hole that becomes a QUESTION, never a default.
2. **Nothing averages, blends or silently selects.** The calculator raises `IncomparableInputs`; two
   PROPOSED conclusions on one subject become a CONFLICT; resolution keeps the loser visible.
3. **The model words things; the registry decides things.** Every model call goes through one injectable
   provider, returns candidates that are PROPOSED, and cannot add a question, a method or a number that
   maps to no typed gap, shape or calculation.
4. **The gate is the law list.** An entry in `LAWS` *is* the law; removing one is the mutation its test
   catches.

## 2. Module map

| path | purpose |
|---|---|
| `app/engine/types.py` | vocabularies, `Quantity`/`Dimensions`, the entity envelope, 41 payload dataclasses, `PAYLOAD_TYPES`, `TEXT_FIELDS`, `FILTERABLE_FIELDS`, `validate_payload`, deltas, `Finding`, `BOUNDS` |
| `app/engine/authority.py` | `AUTHORITY_OF`, `MAY_CONFIRM`, `APPROVAL_OWNER`, `MAY_RESOLVE`, `may_advance`, `precedence_rank`, `resolution_authority` |
| `app/engine/registry.py` | `EngagementRegistry` (I1-I8), `ScopedView`, gate queries, `live_summary`, `support_closure`, `is_material` |
| `app/engine/calc/` | `units.py` (parsing, unit families, comparability), `arith.py` (Decimal `Calculator`, refusals, exact `recompute`), `reconcile.py` (join on `measure_id`, never an average) |
| `app/engine/llm.py` | the single model boundary: `ModelCall`/`ModelResponse`, `OpenRouterProvider`, `FakeProvider`, `RecordingProvider`, the call ledger |
| `app/engine/templating.py`, `app/engine/prompts/*.j2` | `StrictUndefined` rendering of the prompt set |
| `app/engine/partner/` | `state.py` (phase machine), `ingest.py`, `hypothesis.py`, `questions.py`, `charter.py`, `loop.py` |
| `app/engine/methods/` | `contract.py` (shapes, `InputSpec`, `MethodSpec`, `METHODS`, `select_methods`, gaps) and `builtin/` (one file per method) |
| `app/engine/specialists/` | `assignment.py` (`Assignment`, grants, budget, `ADMISSION_RULES`), `runner.py` (scoped execution and admission) |
| `app/engine/synthesis/` | `conflicts.py`, `resolve.py`, `recommend.py`, `regulated.py` |
| `app/engine/work_products/` | `decl.py` (declarations), `plan.py`, `statements.py`, `corrections.py`, `canon_bridge.py`, `render_md/pdf/deck/csv.py`, `integrity_record.py` |
| `app/engine/gates/` | `laws.py` (L1-L14), `presentation.py`, `release.py` |
| `app/engine/legacy/` | the typed r30 adapter and its entity mapping |
| `app/engine/persistence/` | seven tables on `app.database.Base`, append-only store |
| `app/engine/api/` | the `/api/engagements` router, schemas, startup sweep |
| `app/engine/benchmark/` | strict case loader, structural oracle, simulated client, harness, assertions, costed CLI |

`app/pipeline/*`, `app/prompts/*` and `tools/*` are imported and never modified; their hashes are pinned by
`tests/engine/test_engine_r30_frozen.py`. `main.py` gains three lines: the router import, `include_router`,
and `engine_startup()` inside `on_startup` after `init_db()`.

## 3. Phases and the partner loop

`Phase`: `opening -> discovery -> charter_proposed -> charter_confirmed -> analysis` (with
`paused_for_discovery` as a legal detour) `-> synthesis -> deliverables -> execution_support`. The whole
state is `(registry, phase, turn_n, bounds)`; every client message and partner reply is an
`EVIDENCE_SOURCE`, so the transcript is evidence like any other.

`Partner.turn()` ingests the turn, extracts candidates as PROPOSED entities with verbatim spans, revises
the engagement hypothesis, re-derives gaps, and asks between `MIN_QUESTIONS_PER_TURN` and
`MAX_QUESTIONS_PER_TURN` questions chosen by `question_value` - one per issue leaf, never a zero-impact
question, never a fixed script. A gap becomes an action through `fill_strategy`: ask the client, request a
document, spawn a specialist, or record an unknown.

`Partner.run_analysis()` runs rounds bounded by `MAX_ANALYSIS_ROUNDS`. Free methods (deterministic and
calculation) may run during discovery; paid ones are refused before the charter is confirmed. Every
research and model-assisted method runs only inside an Assignment.

## 4. Authority, status and precedence

Authority is a function of information type, not of the producer. Client preferences are owned by the
CLIENT; a client's recollection is `CLIENT_STATED` and rendered "as stated by the client"; a
document-verified fact is owned by `VERIFIED_RECORD`; arithmetic is owned by `DETERMINISTIC_ENGINE` and
confirmed only when `recompute()` is exact; a regulated interpretation is owned by
`QUALIFIED_PROFESSIONAL` and is never confirmed inside the engine (I4).

`may_advance(entity, status, actor)` is the single gate on status: CONFIRMED needs `MAY_CONFIRM`, APPROVED
needs `APPROVAL_OWNER[kind]` (a recommendation only by the decision owner or the client; confirming is not
approving), RESOLVED needs the conflict's own authority.

`CURRENT_STATE_PRECEDENCE` ranks record classes: system of record, then management report, correspondence,
client stated, third-party summary, opinion, inferred. Equal rank never resolves automatically. A strictly
higher rank resolves visibly, and only when the winning document's record class was confirmed by the
client - a model-guessed record class cannot overrule a client fact.

## 5. The method library

A method declares applicability as `QuestionShape`s, what it answers, its required and optional
`InputSpec`s, its execution type, its output kinds and schema version, its evidence requirement, its
validators and its model-call ceiling. M1: deterministic and calculation methods declare zero model calls.
M2: `InputSpec` filters read `FILTERABLE_FIELDS` only. M3: `answers` is non-empty and covers every declared
shape. M4: applicability is non-empty. `select_methods()` reads shapes and input satisfaction only; when
the top two rank equal both run, so their disagreement surfaces as a CONFLICT instead of a coin toss.

<!-- registry:methods -->

| id | execution | model calls | answers | writes |
|---|---|---|---|---|
| `capability_gap` | model_assisted | 1 | what, how | CAPABILITY with a gap state |
| `change_impact` | model_assisted | 1 | what | RISK, ACTION |
| `cost_benefit` | calculation | 0 | how_much | COST, BENEFIT, calculated FACT, QUESTION |
| `current_state` | deterministic | 0 | what | inferred FACT summaries, CAPABILITY |
| `financial_model` | calculation | 0 | how_much, whether | calculated FACT, OBJECTIVE feasibility, CONFLICT, DECISION_REQUIRED, QUESTION |
| `issue_tree` | model_assisted | 2 | what, why, how, how_much, which, whether | ISSUE |
| `journey` | model_assisted | 2 | how | customer PROCESS_STEP, QUESTION |
| `kpi_design` | deterministic | 0 | what, how_much | SUCCESS_CRITERION |
| `legacy_r30_technology_blueprint` | model_assisted | 0 | how | the legacy adapter's typed outputs, including its WORK_PRODUCT volumes |
| `make_buy_partner` | deterministic | 0 | which | OPTION, TRADE_OFF |
| `market_competitor` | research | 3 | what | externally sourced FACT with a locator, QUESTION |
| `market_sizing` | research | 3 | how_much | externally sourced and calculated FACT, QUESTION |
| `operating_model` | model_assisted | 2 | how | WORKSTREAM, GOVERNANCE, ACTION |
| `option_evaluation` | deterministic | 0 | which | TRADE_OFF, CONFLICT, DECISION_REQUIRED, QUESTION |
| `org_design` | model_assisted | 2 | how | OWNER with a reporting line, ACTION, GOVERNANCE |
| `prioritization` | deterministic | 0 | which | ACTION sequence, TRADE_OFF |
| `process_map` | model_assisted | 2 | how | internal PROCESS_STEP, CAPABILITY, QUESTION |
| `raci_governance` | deterministic | 0 | who | GOVERNANCE with a RACI |
| `risk_control` | model_assisted | 1 | what | RISK, CONTROL |
| `roadmap` | deterministic | 0 | how, when | MILESTONE, DEPENDENCY, INITIATIVE ordering |
| `root_cause` | model_assisted | 2 | why | HYPOTHESIS, QUESTION |
| `scenario` | calculation | 0 | how_much, whether | calculated FACT, EXPECTED_OUTCOME, QUESTION |
| `stakeholder` | model_assisted | 1 | who | STAKEHOLDER, OWNER, QUESTION |
| `systems_data_map` | model_assisted | 1 | what, how | CAPABILITY, DEPENDENCY |

<!-- /registry:methods -->

Every model-assisted output schema tolerates extra keys and carries an `output_schema_version`, so a
changed schema invalidates recorded cassettes instead of silently mis-parsing them. Every method's
validators reject uncited outputs and coined quantities: a `Quantity` in an output is either a
`CalcResult` from `ctx.calc` (formula plus inputs) or copied from an input entity by id.

## 6. Specialist assignments

An `Assignment` is built from the selection, never hand-written: `permitted_evidence` is the entities the
method's `InputSpec`s matched plus their `derived_from` closure; `forbidden_decisions` is every live
decision except the subordinate ones the issue node is decisive for; validation is the method's own
validators; the budget comes from settings. The runner executes the method against a `ScopedView` - a
query outside the permitted set returns nothing - as `Actor.SPECIALIST`, then checks every delta before it
applies any. A single violation rejects the whole result: nothing is written, and the outcome is a Finding.

<!-- registry:admission_rules -->

| rule | what the runner refuses |
|---|---|
| `S1` | any Supersede or SetStatus on an entity this assignment did not create |
| `S2` | any Add whose status is not PROPOSED |
| `S3` | a FACT the specialist is not entitled to state (client stated, document verified, document extracted); a calculated FACT must carry the formula and inputs that reproduce it |
| `S4` | a RECOMMENDATION or TRADE_OFF on a forbidden decision, or an OPTION for the central decision the issue does not target |
| `S5` | a `derived_from` id outside the permitted evidence and this run's own outputs; an ASSUMPTION with no grant, or one already approved |
| `S6` | a Quantity that is neither calculated nor copied from permitted evidence by id |

<!-- /registry:admission_rules -->

Two specialists disagreeing is two PROPOSED entities of one kind on one subject with incompatible
payloads. The runner never reconciles; synthesis turns that into a CONFLICT with both conclusions kept.

## 7. Synthesis, conflicts and regulated matters

Conflict detection is four queries: facts reconciled by `measure_id`; live analyses of one kind on one
subject that contradict; an objective a calculated fact shows infeasible; and a client statement against a
higher-ranked record. Materiality is recomputed from the live support graph at gate time, never read from
a stored flag. Resolution is authority-checked, and the loser stays in the registry with its label.

The regulated screen is a two-stage classifier over every recommendation, option, action and question
candidate. Stage one claims a `RegulatedDomain` generously; stage two may clear the claim only with the
literal clearance verdict. A hedge, a paragraph, a schema failure or a provider outage all leave the matter
regulated - under-routing is the dangerous direction and is closed. A matter that stands becomes a
REGULATED_MATTER carrying the interpretation the engine refused to state, is ROUTED by the system in a
second visible transition, and any recommendation it touched is flagged licensed and can never be approved
inside the engine.

## 8. Adaptive work products

A `WorkProductDecl` is an id, a title template over entity fields, an applicability `Predicate` built only
from `Count`/`AllOf`/`AnyOf`/`Always` over `InputSpec`s (P1: a text-reading predicate cannot be
constructed), sections whose queries are `InputSpec`s (P2: a section with no rows and `required=False` is
dropped, so applicability reaches section level), rendering rules and formats. Mandatory products declare
`Always()` and nothing else is fixed (P3).

<!-- registry:work_products -->

| id | applicability | title |
|---|---|---|
| `executive_decision_brief` | Always (mandatory) | Decision Brief: {central_decision} |
| `integrity_record` | Always (mandatory) | Integrity Record |
| `diagnostic_evidence_report` | confirmed facts and at least one hypothesis | Diagnostic and Evidence Report |
| `evidence_book` | at least one document, dataset or link source | Evidence Book |
| `options_tradeoff_assessment` | two or more options with a trade-off | Options and Trade-offs: {central_decision} |
| `business_case_financial_model` | calculated money facts with a cost or a benefit | Financial Model: {central_decision} |
| `recommended_target_state` | capability gaps with governance or process actions | Recommended Target State |
| `organization_design` | owners with a reporting line, or governance with a RACI | Organization and Responsibility Design |
| `process_redesign` | internal process steps with process actions | Process Redesign |
| `customer_journeys` | customer-perspective process steps | Customer Journeys |
| `systems_and_data_map` | software and data capabilities with dependencies | Systems and Data Map |
| `systems_migration_plan` | data and integration gaps with initiatives and dependencies | Systems Migration Plan |
| `transformation_roadmap` | workstreams, actions and milestones | Roadmap: {central_decision} |
| `implementation_plan` | workstreams with enough actions | Implementation Plan |
| `dated_event_plan` | a dated deadline that starts a clock, a gate milestone and day-horizon actions | {deadline}: first 100 days |
| `risk_register` | at least one risk | Risk Register |
| `governance_raci` | governance with a RACI | Governance and RACI |
| `change_communication_plan` | stakeholders with people-and-organisation actions | Change and Communication Plan |
| `kpi_framework` | success criteria attached to measures | KPI Framework |
| `decision_deck` | trade-offs with a recommendation (pptx) | Decision Deck: {central_decision} |
| `legacy_volume` | a workstream delivered by the legacy adapter | {workstream} |

<!-- /registry:work_products -->

`plan_work_products(view)` evaluates every declaration and records `planned_because` (the verdict's own
count string) on each planned WORK_PRODUCT, bounded by `MIN_WORK_PRODUCTS` and `MAX_WORK_PRODUCTS`.
Products that did not qualify are listed in the Integrity Record with their verdict, so absence is
explained rather than invisible.

## 9. Registry-owned rendering

Sections render from entity queries. `statement_text(entity)` is deterministic per kind: a client-stated
fact is quoted verbatim and labelled, an unapproved assumption carries the proposed label, an unknown
renders as the declared unknown text. A claim used by two sections becomes one STATEMENT entity and both
sections embed its token.

Narrative sections receive only ids and tokens and must reference claims by token. A narrative that drifts
is regenerated once (`MAX_NARRATIVE_REGENERATIONS`) with the findings attached, and then falls back to a
statement list. It is never patched by regex. `corrections.py` is the only module allowed to rewrite
rendered text, and it does exactly two things: token substitution, and exact canonical mappings over named
entities - with every client-fact span masked first, so a client's words are never rewritten. Each
application is a lineage record.

PDF, deck and CSV rendering reuse the r30 export helpers unchanged, including the brand faces, the page
footer, the draft stamp and the invariant flag that makes an unchanged registry render identical bytes.
Every artifact row carries its own sha256 and the registry hash it was rendered from, so staleness is a
comparison rather than a guess.

## 10. Gates and release

<!-- registry:laws -->

| law | id | what it queries |
|---|---|---|
| `L1` | L1.material_open_conflict | an open conflict material to something rendered, materiality recomputed |
| `L2` | L2.unsupported_recommendation | a recommendation with no live support: evidence, an approved assumption or a calculation |
| `L3` | L3.unlabelled_assumption | an unapproved assumption rendered without its label |
| `L4` | L4.unrouted_regulated_matter | a regulated matter not routed, or a licensed recommendation that reached a product |
| `L5` | L5.material_open_question | an open question material to the central decision |
| `L6` | L6.statement_drift | a restated claim on the page that no statement token backs |
| `L7` | L7.calculation_does_not_recompute | a stored calculated fact that does not recompute exactly |
| `L8` | L8.hash_mismatch | an artifact or integrity record whose hashes no longer match the registry |
| `L9` | L9.presentation | fonts, glyphs, page completeness, orphans, footers, the draft stamp and clipping |
| `L10` | L10.unreconciled_facts_rendered | two comparable facts on one measure both consumed by a rendered section |
| `L11` | L11.untraceable_number | a rendered number matching no registered quantity within the restatement tolerance |
| `L12` | L12.infeasible_objective_without_decision | an objective infeasible on the facts with no decision required from the client |
| `L13` | L13.legacy_r30_not_final | a legacy package that is not itself final |
| `L14` | L14.client_fact_not_verbatim | a rendered client fact whose words were changed |

<!-- /registry:laws -->

L3, L6, L11 and L14 run on the text extracted from the frozen PDF, chrome stripped - the page as a reader
sees it, not the markdown that produced it. L9 is three deterministic checks: the export presentation
findings, the unchanged inspection tool, and the clipping check over span bounding boxes.

A blocking finding keeps the release at DRAFT and the stamp on every page. The release record has the
existing release-audit shape and is validated by that validator unchanged; revisions are
`<engagement_id>-r<N>` under a frozen directory per revision, and `verify` re-checks every hash.

## 11. The legacy r30 adapter

The r30 technology pipeline is reached only through `legacy_r30_technology_blueprint`, an ordinary
registered method selected by shape. There is no technology-engagement switch. Its inputs are composed by
registry queries, its Request row is created through the same intake constructor and never written
afterwards, and its outputs are mapped into engine entities with legacy provenance. The resulting
workstream sits beside every other workstream in the roadmap and the plan; the client experiences one
engagement, not two systems.

## 12. Persistence and API

Seven tables on the existing declarative base, created by the existing `init_db`. `engagement_entities` is
append-only with a unique `(engagement_id, entity_id, version)`: the store never issues an UPDATE, so the
row history *is* the lineage. The router is mounted at `/api/engagements` and reuses the service's
existing auth, view rules and reviewer check. The startup sweep that fails engagements stranded mid-run is
called from `main.py` after `init_db()`, never from a router startup handler - a fresh database must not
boot into a crash.

## 13. Universality and the benchmark harness

Universality is asserted mechanically by `tests/engine/test_engine_universality.py`: a denylist AST scan
for engagement-type vocabulary in branch tests, a whitelist law that admits only comparisons against the
engine's own closed enums, a scan for names drawn from the case data in engine sources and prompts, a
forbidden-import list (no fuzzy matching, no direct provider use outside the model boundary, no `re.sub`
outside the three modules allowed to substitute), a scramble test proving selection and planning ignore
every text field, and a scoped execution trace proving no code path exists for one case alone.

The harness runs each case through the whole loop under a structural oracle - a fake provider whose
answers are derived from the call's own context by generic rules - and compares bundles pairwise: question
sets, central decisions, issue-tree hashes, method multisets, evidence requests, assignments,
recommendations, workstreams, deliverable sets and section signatures must all diverge, and each core case
must surface at least `MIN_REVEALED_CHANGERS` dossier items that change the recommendation, so divergence
cannot be vacuous.

## 14. Bounds

No count is fixed per engagement. Every bound is a `Settings` field read from an environment variable, and
the frozen defaults below are the fallback. The table is pinned name-for-name and default-for-default
against `app.engine.types.BOUNDS`.

<!-- registry:bounds -->

| bound | default | setting |
|---|---|---|
| `MIN_QUESTIONS_PER_TURN` | 1 | `ENGINE_MIN_QUESTIONS_PER_TURN` |
| `MAX_QUESTIONS_PER_TURN` | 3 | `ENGINE_MAX_QUESTIONS_PER_TURN` |
| `MIN_QUESTION_VALUE` | 0.05 | `ENGINE_MIN_QUESTION_VALUE` |
| `ASK_FLOOR` | 0.1 | `ENGINE_ASK_FLOOR` |
| `MAX_FANOUT` | 6 | `ENGINE_MAX_FANOUT` |
| `SYMPTOM_MARGIN` | 0.25 | `ENGINE_SYMPTOM_MARGIN` |
| `CHARTER_MIN_WEIGHT` | 0.45 | `ENGINE_CHARTER_MIN_WEIGHT` |
| `CHARTER_MIN_MARGIN` | 0.15 | `ENGINE_CHARTER_MIN_MARGIN` |
| `MAX_DISCOVERY_TURNS` | 12 | `ENGINE_MAX_DISCOVERY_TURNS` |
| `MAX_ANALYSIS_ROUNDS` | 6 | `ENGINE_MAX_ANALYSIS_ROUNDS` |
| `MIN_WORK_PRODUCTS` | 2 | `ENGINE_MIN_WORK_PRODUCTS` |
| `MAX_WORK_PRODUCTS` | 16 | `ENGINE_MAX_WORK_PRODUCTS` |
| `MAX_SPECIALISTS_PER_ROUND` | 4 | `ENGINE_MAX_SPECIALISTS_PER_ROUND` |
| `MIN_REVEALED_CHANGERS` | 3 | `ENGINE_MIN_REVEALED_CHANGERS` |
| `MIN_DISTINCT_DELIVERABLE_SETS` | 4 | `ENGINE_MIN_DISTINCT_DELIVERABLE_SETS` |
| `MIN_DISTINCT_SECTION_SIGNATURES` | 8 | `ENGINE_MIN_DISTINCT_SECTION_SIGNATURES` |
| `RENDERED_RESTATEMENT_TOLERANCE` | 0.005 | `ENGINE_RENDERED_RESTATEMENT_TOLERANCE` |
| `MAX_NARRATIVE_REGENERATIONS` | 1 | `ENGINE_MAX_NARRATIVE_REGENERATIONS` |

<!-- /registry:bounds -->
