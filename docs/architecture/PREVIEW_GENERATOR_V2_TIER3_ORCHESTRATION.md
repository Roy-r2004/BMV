# Preview Generator v2 — Phase 6B Tier 3 Orchestration

Phase 6B extends one immutable, visually accepted Tier 2 candidate into a
cumulative Tier 1+2+3 product candidate. It is metadata-only orchestration: it
does not promote, serve, mark ready/degraded, regenerate Tier 1 or Tier 2, or
begin Phase 7.

## Boundary and rollback

The feature is disabled by default:

```text
V2_TIER3_GENERATION_ENABLED=false
```

When false, the coordinator returns the exact Phase 6A result object by
identity. Stored Phase 6 history is never deleted or rewritten. When Tier 2
generation is also disabled, the pipeline still returns the exact Phase 5
result through the Phase 6A coordinator.

The only Phase 6B terminal statuses are:

- `tier_3_accepted`
- `tier_3_failed_serving_tier_2`

“Serving” is descriptive fallback metadata. Both summaries explicitly record
`serving_pointer_changed=false`, `promoted=false`, and `phase_7_invoked=false`.
Phase 4 and Phase 5 run with request-bundle mutation disabled inside Phase 6B.

## Accepted Tier 2 precondition

Tier 3 requires a completely accepted and verified Tier 2 lineage:

- Phase 6A effective summary status `tier_2_accepted`;
- matching orchestration attempt, extension manifest, Phase 4 runtime summary,
  Phase 5 visual summary, and blind Tier 1 baseline comparison;
- accepted Tier 2 candidate workspace bytes that still match the stored
  manifest; and
- a unique terminal resume identity for that Tier 2 result.

Any corrupt, cross-request, or stale reference fails closed before the first
Tier 3 provider call and never mutates the accepted Tier 2 workspace.

## Deterministic Tier 3 projection

The projection is canonical ordered set subtraction:

```text
Tier 3 delta = cumulative Tier 3 closure − cumulative Tier 2 closure
```

It retains AppSpec order for every reference collection. It records the
accepted Tier 1 and Tier 2 revision/manifest/visual/effective summary IDs,
Tier 1/2/3 closure hashes, delta hash, inherited dependency IDs, and
explicitly justified lower-tier integration pages.

Phase 6B creates a separate cumulative Tier 3 extension manifest containing
deterministic:

- Tier 3 PagePurpose projection across all active pages;
- business-component contracts grounded in canonical pages, requirements,
  roles, capabilities, actions, states, and evidence;
- structured content/data extensions;
- interaction projection; and
- a closed, acyclic component dependency graph.

It does not re-author ProductStrategyV2, IA, DesignDNA, accepted Tier 1/2
pages, or the complete product architecture.

## Lower-tier byte preservation

Before generation every accepted Tier 2 source file receives:

- classification (`immutable` or `extendable`);
- original and final SHA-256;
- canonical owner IDs;
- dependency path;
- exact justification; and
- edit authority (`none`, `ai`, or `deterministic`).

Package/lock, foundation, runtime infrastructure, unrelated lower-tier pages
and components, and canonical accepted contracts remain immutable. AI can
touch only dependency-justified page or business-component paths. Data, route,
navigation, and `App.tsx` integration are deterministic-only. New paths are
confined to `src/pages/` and `src/components/business/`. The accepted Tier 2
workspace is rehashed before generation and after either success or failure.

## Generation and validation

The normal order is:

1. deterministic delta/extension projection;
2. deterministic structured-data extension;
3. one DeepSeek Tier 3 component batch for the remaining delta only;
4. one DeepSeek Tier 3 page batch for the remaining delta only;
5. deterministic route/navigation/application integration;
6. the complete cumulative Phase 3B static validator;
7. complete Phase 4 runtime validation for every cumulative route, viewport,
   and Tier 1/2/3 journey;
8. complete Phase 5 visual evaluation with explicit accepted Tier 2 as the
   same-policy baseline; and
9. deterministic effective-tier summary.

No call is made per file and Tier 1/2 are never regenerated. AI batches are
validated for exact delta ownership and namespace. They cannot write
deterministic manifests or infrastructure.

If the cumulative static validator returns source-local diagnostics, one
GLM repair per affected component/page batch is allowed. The repair must keep
the exact paths, file kinds, owner IDs, and delta boundary, then the complete
static gate reruns once.

## Dynamic Phase 5 grouping

Phase 6B does **not** assume a four-call happy path. Before the first Tier 3
provider call it:

1. selects a visual page scope (delta, integration, primary journey, and
   role/surface samples);
2. plans one screenshot per selected page × `{mobile, tablet, desktop}`;
3. groups critic and reviewer images by provider capability limits; and
4. computes `mandatory_calls = 2 generation + critic_groups + reviewer_groups`.

When the full cumulative product produces 13 routes × 3 viewports (39 images),
the fixture-validated grouping yields 3 critic groups + 3 reviewer groups, so
`mandatory_calls = 8`. Budgets fail closed when mandatory calls exceed
`V2_TIER3_MAX_CALLS`.

## Models, calls, and budgets

| Stage | Model | Normal calls | Maximum |
|---|---|---:|---:|
| Tier 3 components | `deepseek/deepseek-v4-pro` | 1 | 1 |
| Tier 3 pages | `deepseek/deepseek-v4-pro` | 1 | 1 |
| Narrow static repair | `z-ai/glm-5.2` | 0 | 2 |
| Phase 5 critic | existing Phase 5 routing | dynamic groups | grouped policy |
| Phase 5 reviewer | existing Phase 5 routing | dynamic groups | grouped policy |

Defaults: 12 aggregate calls, 168,000 output tokens, $2.50, and 3,600 seconds.
Existing request and daily cost limits remain authoritative. Unknown
component/page/repair or Phase 5 model capabilities fail closed.

No live provider canary is part of Phase 6B.

## Cache and resume

The terminal identity includes:

- accepted Tier 2 revision, source manifest, visual summary, and effective
  summary;
- Tier 1/2/3 closure and delta hashes;
- Phase 2 and inherited Phase 3A hashes;
- dependency lock;
- component/page/repair models and prompt parameters;
- generation policy and aggregate budget;
- Phase 4 tool versions, runtime/capture policy; and
- Phase 5 routing, image/grouping, baseline, and evaluation policy.

A full terminal hit still validates accepted Tier 2 lineage and source bytes,
reprojects the delta, and recomputes the complete resume identity; then it
returns with zero provider calls.

## Failure semantics

Generation, Phase 4, or Phase 5 failure produces an append-only
`tier_3_failed_serving_tier_2` summary. It records the failed stage,
diagnostic, derived revision when one exists, and aggregate telemetry, while:

- `highest_accepted_tier=2`;
- `last_accepted_candidate_revision_id` remains the original Tier 2 revision;
- the accepted Tier 2 workspace remains byte-identical;
- no failed Tier 3 revision becomes effective; and
- no Phase 7, promotion, serving-pointer, ready, or degraded path runs.

## Local verification

Fixture providers implement the injected provider interface and construct no
OpenRouter/Ollama client.

```powershell
cd backend
python -m pytest -q -p no:cacheprovider tests/tier_orchestration/test_phase6b_migration.py tests/tier_orchestration/test_phase6b_projection_policy.py tests/tier_orchestration/test_phase6b_policy_persistence.py
python -m pytest -q -p no:cacheprovider tests/tier_orchestration/test_phase6b_integration.py
python -m pytest -q -p no:cacheprovider tests/tier_orchestration
python -m compileall -q app
git diff --check
```

Final local fixture record for the continued Phase 6B validation:

- Phase 6B fast suites: `20 passed`;
- Phase 6B cumulative integration: `1 passed` in about 216 s;
- happy-path provider calls: `8` (`2` generation + `6` visual groups);
- Phase 6 aggregate provider calls including Tier 2: `12`;
- screenshot matrix: `39` route×viewport captures;
- full terminal cache hit: `0` provider calls; and
- failure fallbacks preserve accepted Tier 2 bytes.
