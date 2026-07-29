# Preview Generator v1 Baseline

- Snapshot date: 2026-07-24
- Repository commit: `d1cc88729a3ef5ecba78985fe1d9acfaf18371fe`
- Baseline generator: `v1`
- Phase 0 switch: `PREVIEW_GENERATOR_V2=false`

This document freezes the implementation and locally observed behavior that
later preview-generator phases must compare against. It contains no paid
canary results. The two pre-existing worktree entries under `docker/` were
excluded from Phase 0 and were not modified.

## Boundary contract

`PREVIEW_GENERATOR_V2` is false by default in code and both environment
examples.

- Flag false: every generation executes the unchanged v1 phase sequence.
- Flag true, existing unmarked `generated_pages`: the preview remains on v1.
- Flag true, new preview: the v2 boundary is selected.
- Phase 0 v2: delegates to the v1 engine and adds only
  `preview_app.generator_version = "v2"` at successful finalization.
- Existing marked v2 plus flag true: remains on v2.
- Flag switched false: regeneration uses v1, providing the rollback switch.
- v1 output receives no version key and retains its previous payload shape.
- No database migration or new persistence column is introduced.

Selection is conservative: any existing `generated_pages`, including legacy
role-page output without `preview_app`, remains v1.

## Current architecture map

```text
FastAPI background trigger
  -> GenerationPipeline
     -> optional reference fetch / screenshot analysis
     -> MVP blueprint
     -> AppSpec author + deterministic validation + coverage review
     -> visual demo/theme
     -> preview generator
        -> AppSpec gate
        -> experience plan + design manifest + architect
        -> workspace/template preparation
        -> parallel file generation + mock synthesis
        -> page critic + deterministic polish
        -> Vite build + bounded AI repair + deterministic fallbacks
        -> optional screenshot/vision critic
        -> deterministic AppSpec workspace checks + quality gate
        -> persist generated_pages + AppSpec provenance
     -> technical plan
     -> proposal
     -> build packages
```

Primary entrypoints and state:

- Full orchestration:
  `backend/app/application/pipelines/orchestrator.py`
- Preview boundary:
  `backend/app/application/preview_app/pipeline/orchestrator.py`
- Preview phases:
  `appspec_gate.py`, `plan_phase.py`, `codegen_phase.py`,
  `polish_phase.py`, `build_phase.py`, and `finalize.py`
- AppSpec schema and validator:
  `backend/app/domain/schemas/app_spec.py` and
  `backend/app/domain/appspec/validation/`
- AppSpec persistence:
  `app_spec_revisions`, including canonical SHA-256, deterministic validation,
  semantic coverage, prompt/model metadata, and revision lineage
- Preview persistence:
  `requests.generated_pages`, containing `preview_app`, `experience_plan`,
  optional `app_spec_ref`, and legacy role output
- Generated source/build:
  `backend/app/uploads/preview-apps/<request_id>/`
- Build command:
  `npm exec -- vite build`
- Build success:
  exit code zero and `dist/index.html` present
- Final readiness:
  built `dist/index.html` plus a passing automated quality gate

## Current source-of-truth boundaries

AppSpec remains the canonical product contract. It contains requirements,
roles, entities, capabilities, pages, states, actions, transitions, evidence,
journeys, acceptance tests, and traceability. It intentionally excludes design
fields and source paths.

The v1 architect/plan may enrich or drift from AppSpec routes. The frozen
observations capture two examples:

- `/clinicians` became `/doctors`, with five extra routes.
- `/ops/floor` became `/ops`.

The deterministic finalizer checks AppSpec hooks when enforcement is active,
runs the quality gate, records fallback pages, persists the plan and routes,
and exposes a preview only when a compiled distribution and passing quality
gate exist.

## AI and deterministic responsibilities in v1

AI currently handles AppSpec authoring/repair/coverage, blueprint and planning,
design manifest, architecture, route-file content, mock synthesis, design
critique, build repair, optional visual critique, and optional quality repair.

Deterministic code handles schema validation, AppSpec projection and hooks,
product-kind classification, recipe/template/catalogue normalization,
workspace ownership, route assembly, import/source guards, file caps, build
execution, fallback stabilization, quality checks, persistence, and rollback.

The current usage ledger records broad `purpose` values. Planning,
architecture, file generation, critic, and visual critique are generally
aggregated under `codegen`; per-agent stage attribution does not yet exist.

## Active local model routing at capture

These are non-secret configuration values from the local baseline:

| Stage | Configuration | Active value |
|---|---|---|
| Blueprint, proposal, plans | `TEXT_MODEL` | `google/gemini-2.5-flash` |
| Reference screenshot | `VISION_MODEL` | `google/gemini-2.5-flash` |
| Visual demo, technical plan | `CODER_MODEL` | `qwen/qwen-2.5-coder-32b-instruct` |
| AppSpec author/repair/review | `APPSPEC_*_MODEL` | `google/gemini-2.5-flash` |
| Experience/architect | `ARCHITECT_MODEL` | `anthropic/claude-haiku-4.5` |
| File generation/mock/slot fill | `PREVIEW_APP_MODEL` | `deepseek/deepseek-v4-pro` |
| Text design critic | `CRITIC_MODEL` | `anthropic/claude-haiku-4.5` |
| Build repair | `FIX_MODEL` | `z-ai/glm-5.2` |
| Quality repair | `QUALITY_FIX_MODEL` | `z-ai/glm-5.2` |

Current local modes and limits:

- Provider: `openrouter`
- AppSpec mode: `shadow`
- AppSpec target/max pages: `6 / 10`
- Preview maximum AI-authored files: `40`
- Preview maximum AI calls: `96`
- Text critic: enabled
- Visual critic: enabled
- Scaffold-first: enabled
- Catalogue slot fill: enabled
- v2 boundary: disabled

This table records the baseline; Phase 0 does not introduce new model routing.

## Frozen representative observations

The machine-readable fixtures live in
`backend/tests/fixtures/preview_characterization/`. Business identities are
synthetic/anonymized. AppSpec hashes and runtime measurements are frozen from
local artifacts where an observation existed.

| Fixture | AppSpec | Routes/files | AI calls | Build | Quality gate | Elapsed | Catalogue evidence |
|---|---:|---:|---:|---|---|---:|---|
| Premium public website | accepted, 100 | 4 / 4 | 11 | passed after one repair | passed | 1,048 s | 4 skeleton routes; 8 UI imports |
| Hybrid public + operations | accepted, 95 | 8 / 8 | 11 | passed initially | passed; 2 heals recorded | 1,939 s | 8 skeleton routes; 12 UI imports; 2 scaffold markers |
| Operations-heavy SaaS | accepted, 100 | 3 focused route files; 16 files reported | 15 | not reached | not reached | 1,533 s to last critic event | 3 skeleton routes; 10 UI imports; 1 scaffold marker |
| Booking workflow | valid repository AppSpec; focused route | 1 / 1 focus | 11 for containing run | passed | passed | 1,939 s containing run | 1 focused skeleton route |
| Data-heavy/trading | no live AppSpec | 5 deterministic route contracts | not observed | not run | not run | not observed | deterministic trading pack and skeleton contract only |

Observed usage totals are grouped by the existing ledger purpose:

- Premium public: AppSpec 3, codegen 7, build 1, quality gate 0;
  133,650 tokens; recorded cost `$0.201335`.
- Hybrid: AppSpec 4, codegen 6, build 0, quality gate 1;
  131,179 tokens; recorded cost `$0.199082`.
- Operations-heavy: AppSpec 2, codegen 13; 216,347 tokens;
  recorded cost `$0.370772`; run incomplete.

The booking measurement is a focused slice of the hybrid run, not an
independent paid observation. No matching live trading run existed. Phase 0
therefore freezes the deterministic trading route contract and explicitly
marks AI, build, gate, cost, and latency as unobserved instead of inventing
measurements.

## Fixture contract and thaw procedure

Every fixture records:

- request profile and provenance
- AppSpec schema/hash/status/page artifact
- generated routes, route files, workspace counts, fallbacks, and route drift
- AI calls by currently available purpose, tokens, and recorded cost
- initial/final build status and attempt count
- quality-gate status, issues, and heals
- elapsed-time definition and value
- scaffold-first, slot-fill, skeleton, catalogue-import, and marker usage

Tests hash canonical JSON, so formatting and line endings do not affect the
freeze. Any intentional baseline update must change both the fixture and its
expected hash in
`backend/tests/preview_app/test_phase0_characterization_fixtures.py`, with an
explanation in this document.

Fixture loading imports no provider factory and performs no generation, build,
network, or workspace mutation. Tests additionally replace the OpenRouter
factory and call methods with fail-fast sentinels.

## Phase 0 local verification

Focused tests:

```text
python -m pytest \
  tests/preview_app/test_generator_version_boundary.py \
  tests/preview_app/test_phase0_characterization_fixtures.py -q
```

They prove:

- the configuration default is false
- false dispatches only v1 and returns the exact v1 result object
- enabling v2 does not move an existing unmarked preview
- a new preview can select v2
- Phase 0 v2 delegates to the frozen v1 engine
- the rollback flag overrides a persisted v2 marker
- v1 result payloads are not marked or mutated
- all five fixtures, categories, and canonical fixture hashes are exact
- AppSpec/route/file/build/gate/timing/catalogue fields are present
- the repository booking AppSpec still validates and matches its canonical hash
- fixture tests cannot construct or call the paid provider

### Unrelated baseline test failures

The wider AppSpec/preview suite passes with these three tests deselected:

```text
206 passed, 3 deselected
```

All three were rerun in isolation and still fail in baseline catalogue/mock
behavior outside the Phase 0 files:

- `test_pottery_picks_craft_studio_pack`: the selected pottery pack returns
  generic seed item titles instead of a title containing `Wheel` or `Glaze`.
- `test_enriched_industry_packs_carry_seed_items`: enriched packs return
  generic seed items instead of the expected industry-specific terms.
- `test_production_callsites_render_with_strict_undefined`:
  `synthesize_mock_data` returns false for the test's captured empty
  reservations export.

Phase 0 does not modify the industry-template packs, recipe seed application,
or mock-data synthesis involved in these failures. The test environment also
reports an existing non-fatal warning because `backend/.pytest_cache` is not
writable.

### Phase 1A Windows test-environment note

The Phase 1A full-suite comparison re-observed the same three unrelated
failures above. It also encountered 16 setup errors in tests that request
pytest's `tmp_path` fixture because Windows denied access to the shared pytest
temporary root:

```text
C:\Users\User\AppData\Local\Temp\pytest-of-User
```

Explicit full-suite `--basetemp` attempts under `C:\tmp` and the workspace
likewise failed when pytest tried to create or recreate the base directory.
The affected tests did not reach their test bodies. The resulting diagnostic
run was `228 passed, 3 failed, 16 errors`; the three failures were exactly the
baseline failures listed above, and every setup error was the temporary-path
ACL condition.

This machine-level ACL issue is not treated as a product regression. Phase 1A
uses isolated suites that do not depend on the inaccessible shared temporary
root. Those suites cover the new persistence rollback/failure behavior and
the frozen v1/v2 boundary separately.

## Phase 0 latency and cost impact

The default v1 path adds one local flag check and no payload marker. When the
flag is enabled, selection parses existing `generated_pages` once. Expected
overhead is sub-millisecond relative to minute-scale generation.

Phase 0 adds zero AI calls, zero tokens, zero provider cost, no browser run,
and no additional build. A v2-finalized preview stores one short metadata key.

## Risks and rollback

- **Selection regression:** existing output is conservatively pinned to v1.
  Tests cover malformed/unmarked legacy state through the selector contract.
- **Payload compatibility:** v1 gets no new field. Only opted-in v2 output is
  marked.
- **Partial v2 failure:** if finalization is not reached, no marker is written;
  a retry remains eligible for v2 while the flag is enabled.
- **Emergency rollback:** set `PREVIEW_GENERATOR_V2=false`; no migration or
  workspace rewrite is required.
- **Historical fixture bias:** three runtime observations cover two public
  businesses and one finance-ops product. Booking is a focused slice and
  trading lacks a live observation. These limitations are explicit and should
  be replaced only by separately approved canaries.
- **Instrumentation granularity:** `codegen` hides individual agent stages.
  Later observability work must add detail without changing these historical
  totals.

## Explicitly out of scope

Phase 0 does not implement DesignDNA, free composition, tier generation,
Playwright, accessibility automation, new model routing, mandatory page
limits, new shared UI requirements, paid canaries, or pushes.
