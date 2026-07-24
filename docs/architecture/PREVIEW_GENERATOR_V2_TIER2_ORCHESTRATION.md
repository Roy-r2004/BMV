# Preview Generator v2 — Phase 6A Tier 2 Orchestration

Phase 6A extends one immutable, visually accepted Tier 1 candidate into a
cumulative Tier 1+2 candidate. It is metadata-only orchestration: it does not
promote, serve, mark ready/degraded, generate Tier 3, or begin Phase 6B/7.

## Boundary and rollback

The feature is disabled by default:

```text
V2_TIER2_GENERATION_ENABLED=false
```

When false, the coordinator returns the exact Phase 5 result object by
identity. Stored Phase 6 history is never deleted or rewritten.

The only Phase 6A terminal statuses are:

- `tier_2_accepted`
- `tier_2_failed_serving_tier_1`

“Serving” is descriptive fallback metadata. Both summaries explicitly record
`serving_pointer_changed=false`, `promoted=false`, and
`tier_3_invoked=false`. Phase 4 and Phase 5 run with request-bundle mutation
disabled inside Phase 6A; their existing callers retain the old default.

## Candidate target-tier migration

`candidate_revisions.target_tier` now accepts `IN (1, 2, 3)`. Startup performs
an explicit migration rather than relying on `create_all`.

SQLite migration behavior:

1. inspect and validate all existing target-tier values;
2. capture exact rows plus explicit indexes and triggers;
3. enable legacy table-rename behavior so child foreign-key targets are not
   rewritten to the temporary table;
4. rebuild the table transactionally with the reviewed constraint;
5. copy the exact column set and compare every row before/after;
6. restore indexes/triggers and run `PRAGMA foreign_key_check`; and
7. restore the original foreign-key and legacy-rename settings.

Postgres drops and recreates the named check constraint in a transaction after
validating stored values. Downgrade contracts the constraint to Tier 1 only
and fails before mutation when any Tier 2 or Tier 3 row exists.

## Append-only persistence

Phase 6A adds exactly seven tables:

1. `candidate_tier_orchestration_attempts`
2. `candidate_tier_extension_manifests`
3. `candidate_lower_tier_preservation_audits`
4. `candidate_tier_generation_results`
5. `candidate_tier_validation_results`
6. `candidate_tier_visual_outcomes`
7. `candidate_effective_tier_summaries`

The rows link existing Phase 3B, Phase 4, and Phase 5 records rather than
copying build, browser, screenshot, critic, or refinement internals. A session
guard rejects updates and deletes for all seven models.

The orchestration attempt and deterministic extension manifest may be committed
as resumable non-terminal checkpoints. Preservation, generation, validation,
visual outcome, and effective summary rows are flushed in one terminal
transaction. A failure injected after those flushes rolls all five back.

## Deterministic Tier 2 projection

The projection is canonical ordered set subtraction:

```text
Tier 2 delta = cumulative Tier 2 closure − cumulative Tier 1 closure
```

It retains AppSpec order for every reference collection. It records the
accepted Tier 1 revision/manifest/visual summary, Tier 1 and Tier 2 closure
hashes, delta hash, inherited dependency IDs, and explicitly justified
lower-tier integration pages.

Tier 1 Phase 3A artifacts remain the inherited Tier 1 truth. Phase 6A creates
a separate cumulative extension manifest containing deterministic:

- Tier 2 PagePurpose projection;
- business-component contracts grounded in canonical pages, requirements,
  roles, capabilities, actions, states, and evidence;
- structured content/data extensions;
- interaction projection; and
- a closed, acyclic component dependency graph.

It does not re-author ProductStrategyV2, IA, DesignDNA, Tier 1 pages, or the
complete product architecture.

## Lower-tier byte preservation

Before generation every accepted source file receives:

- classification (`immutable` or `extendable`);
- original and final SHA-256;
- canonical owner IDs;
- dependency path;
- exact justification; and
- edit authority (`none`, `ai`, or `deterministic`).

Package/lock, foundation, runtime infrastructure, unrelated Tier 1 pages and
components, and canonical accepted contracts remain immutable. AI can touch
only dependency-justified page or business-component paths. Data, route,
navigation, and `App.tsx` integration are deterministic-only. New paths are
confined to `src/pages/` and `src/components/business/`. The accepted Tier 1
workspace is rehashed before generation and after either success or failure.

## Generation and validation

The normal order is:

1. deterministic delta/extension projection;
2. deterministic structured-data extension;
3. one DeepSeek Tier 2 component batch;
4. one DeepSeek Tier 2 page batch;
5. deterministic route/navigation/application integration;
6. the complete target-tier-aware Phase 3B static validator;
7. complete Phase 4 runtime validation;
8. complete Phase 5 visual evaluation with explicit Tier 1 baseline; and
9. deterministic effective-tier summary.

No call is made per file and Tier 1 is never regenerated. AI batches are
validated for exact delta ownership and namespace. They cannot write
deterministic manifests or infrastructure.

If the cumulative static validator returns source-local diagnostics, one
GLM repair per affected component/page batch is allowed. The repair must keep
the exact paths, file kinds, owner IDs, and delta boundary, then the complete
static gate reruns once. Global, cached, out-of-scope, or still-failing
diagnostics fail closed. This caps generation at four calls.

Phase 4 reruns TypeScript, Vite, dist, every cumulative route at all three
viewports, every Tier 1+2 journey, accessibility, screenshots, and network
isolation. Phase 5 evaluates new/changed/primary routes plus role/surface
coverage, uses the accepted Tier 1 candidate as a same-policy blind baseline,
and requires both absolute acceptance and no material Tier 1 regression.

## Models, calls, and budgets

| Stage | Model | Normal calls | Maximum |
|---|---|---:|---:|
| Tier 2 components | `deepseek/deepseek-v4-pro` | 1 | 1 |
| Tier 2 pages | `deepseek/deepseek-v4-pro` | 1 | 1 |
| Narrow static repair | `z-ai/glm-5.2` | 0 | 2 |
| Phase 5 critic | existing Phase 5 routing | 1 | grouped/refinement policy |
| Phase 5 reviewer | existing Phase 5 routing | 1 | grouped/refinement policy |

The happy path is four calls. Generation is capped at four, Phase 5 at six,
and the aggregate at ten calls, 118,000 output tokens, $1.75, and 2,400
seconds. Before the first Tier 2 provider call, model families and mandatory
call/token/wall-time headroom are checked. Existing request and daily cost
limits remain authoritative. Unknown component/page/repair or Phase 5 model
capabilities fail closed.

No live provider canary is part of Phase 6A.

## Cache and resume

The terminal identity includes:

- accepted Tier 1 revision, source manifest, and visual summary;
- Tier 1/Tier 2 closure and delta hashes;
- Phase 2 and inherited Phase 3A hashes;
- dependency lock;
- component/page/repair models and prompt parameters;
- generation policy and aggregate budget;
- Phase 4 tool versions, runtime/capture policy; and
- Phase 5 routing, image/grouping, baseline, and evaluation policy.

Generation stage keys additionally consume the preservation manifest and
extendable source hashes. Deterministic data, routes, static validation,
Phase 4, Phase 5, and the effective summary keep their existing separate
stage records/caches.

A full terminal hit still validates accepted Tier 1 lineage and source bytes,
reprojects the delta, and recomputes the complete resume identity; then it
returns with zero provider calls. Non-terminal staging resumes only when
request, upstream hash, policy revision, workspace UUID, and every completed
file hash match. Any mismatch creates a new isolated staging identity.

## Failure semantics

Generation, Phase 4, or Phase 5 failure produces an append-only
`tier_2_failed_serving_tier_1` summary. It records the failed stage,
diagnostic, derived revision when one exists, and aggregate telemetry, while:

- `highest_accepted_tier=1`;
- `last_accepted_candidate_revision_id` remains the original Tier 1 revision;
- the accepted Tier 1 workspace remains byte-identical;
- no failed Tier 2 revision becomes effective; and
- no Tier 3, promotion, serving-pointer, ready, or degraded path runs.

## Local verification

Fixture providers implement the injected provider interface and construct no
OpenRouter/Ollama client.

```powershell
cd backend
python -m pytest -q -p no:cacheprovider tests/tier_orchestration
python -m pytest -q -p no:cacheprovider tests/visual_evaluation
python -m pytest -q -p no:cacheprovider tests/runtime_validation
python -m pytest -q -p no:cacheprovider tests/candidate_generation
python -m pytest -q -p no:cacheprovider tests/composition_contract
python -m pytest -q -p no:cacheprovider tests/design_contract
python -m pytest -q -p no:cacheprovider tests/preview_contract/test_preview_tiers.py tests/preview_contract/test_v2_contract_boundary.py::test_contract_ready_summary_failure_rolls_back_every_tier
python -m pytest -q -p no:cacheprovider tests/preview_contract/test_appspec_v2_policy.py tests/preview_contract/test_customer_source.py tests/preview_contract/test_preview_contract_persistence.py tests/preview_contract/test_v2_contract_boundary.py::test_v2_boundary_persists_contract_and_never_reaches_generation_phases tests/preview_contract/test_v2_contract_boundary.py::test_full_v2_pipeline_returns_immediately_after_contract_boundary
python -m pytest -q -p no:cacheprovider tests/preview_app/test_generator_version_boundary.py tests/preview_app/test_phase0_characterization_fixtures.py
python -m compileall -q app
git diff --check
```

The known Windows `.pytest_cache`/shared `tmp_path` ACL issue and the three
unrelated historical baseline failures remain documented in
`PREVIEW_GENERATOR_V1_BASELINE.md`. Phase 6A tests use repository-local,
isolated paths and clean them after use. One combined regression sweep also
observed a transient Windows `WinError 5` while `os.replace` moved a Phase 3B
staging directory; that test passed immediately in isolation and the complete
24-test Phase 3B file then passed on rerun. During the final Phase 6A audit,
one aggregate run also observed a single non-reproducible Tier 2 fallback in
the terminal-cache test after repeated runtime suites. The cache node, its
two-node and four-node ordered prefixes, and the final complete Phase 6A suite
all passed on rerun. No deterministic collection or state-leak failure was
reproduced.

Final local fixture record:

- Phase 6A: `24 passed`;
- happy-path calls: `4` (`2` generation + `2` visual);
- fixture output tokens: `200`;
- synthetic fixture cost: `$0.02`;
- measured Phase 6A latency: `45,125 ms`;
- full terminal cache hit: `0` provider calls;
- Phase 5: `28 passed`;
- Phase 4: `36 passed`;
- Phase 3B: `24 passed`;
- Phase 3A: `24 passed`;
- Phase 2: `14 passed`;
- Phase 1B canonical focused suite: `14 passed`;
- Phase 1A canonical requested suite: `17 passed`; and
- Phase 0: `13 passed`.

### Phase 1 collection audit

The Phase 1B commit introduced thirteen nodes in
`test_preview_tiers.py` and one transaction-boundary node,
`test_contract_ready_summary_failure_rolls_back_every_tier`, in
`test_v2_contract_boundary.py`. The later `13 passed` record ran only the
tier file. No Phase 1B test was removed, renamed, merged, skipped, deselected,
or made uncollectable, and Phase 6A does not modify a Phase 1 fixture or test.

The original Phase 1A requested suite intentionally selects the two boundary
tests that existed at the Phase 1A commit. It collects seventeen nodes. The
broader four-file selection collects eighteen because Phase 1B later added the
transaction-boundary node to `test_v2_contract_boundary.py`.

### Docker worktree audit

`docker/entrypoint.sh` and `docker/ollama-init.sh` appeared as unstaged
modifications during Phases 0 through 5, but every contemporaneous plain,
`--raw`, and `--numstat` diff was empty. The entries were status/stat-cache
anomalies rather than recoverable content changes. Neither file appears in a
Phase 0 through Phase 5 commit, a stash, or a Phase 6A diff. Both working-tree
files now normalize to their exact `HEAD` blob IDs:

- `docker/entrypoint.sh`: `c10fd198e03494712417772013b438f4c5a3243c`;
- `docker/ollama-init.sh`: `af8a3068bc99bb9cf661e7cd20033eb77dee9eae`.

The local execution log contains no Phase 6A command that writes, restores,
checks out, stages, or deletes either Docker path. Their status cleared outside
the recorded Phase 6A file operations; the exact stat-refresh operation is not
recoverable. No Docker content is recreated or included in Phase 6A.
