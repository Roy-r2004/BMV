# Preview Generator v2 — Phase 3B Tier 1 Candidates

Phase 3B generates one isolated, business-specific Tier 1 React candidate from
the accepted Phase 3A composition contracts. It does not build, serve, promote,
or replace an accepted preview.

## Boundary

- `PREVIEW_GENERATOR_V2=false` continues to select the frozen v1 pipeline.
- v2 loads and revalidates the complete Phase 3A artifact chain.
- Every attempt uses
  `uploads/preview-candidates/<request>/.staging/<uuid>`.
- A verified non-terminal staging attempt may resume. Otherwise a retry gets a
  new UUID and revision.
- A completed or failed staging workspace is atomically moved to
  `uploads/preview-candidates/<request>/revisions/<uuid>`.
- `PREVIEW_APPS_DIR`, its accepted `dist`, and all serving pointers remain
  untouched.

Phase 3B uses only these candidate states:

- `candidate_generated`: durable generation checkpoint represented in the
  successful lifecycle summary.
- `candidate_build_pending`: the deterministic pre-build gate passed.
- `candidate_contract_failed`: generated files failed the contract gate after
  the allowed scoped repair.
- `candidate_failed`: provider, timeout, storage, model-policy, or transaction
  failure.

No Phase 3B path can mark a candidate ready or degraded.

## Persistence

`candidate_artifacts` is an append-only cache with this parent chain:

1. deterministic foundation
2. deterministic data exports
3. AI-authored business-component batch
4. AI-authored page batch
5. deterministic routes and application entry
6. deterministic validation report

Every row records its schema/policy/prompt/model provenance, cache key, input
provenance hash, artifact hash, validation result, provider calls, repair
calls, tokens, cost, latency, and parent.

`candidate_revisions` records the immutable revision UUID, full source/AppSpec/
tier/design/composition reference manifest, dependency-lock hash, model
manifest, frozen workspace path, file manifest and hash, artifact references,
terminal status, failure evidence, and aggregate telemetry.

Successful artifacts and the revision summary persist in one database
transaction. If that transaction fails, its artifacts roll back and a
`candidate_failed` revision is recorded against the already isolated,
unserved workspace.

## Deterministic generation

Foundation copies only these approved low-level project files from
`preview-template`:

- package and lock files
- TypeScript configurations
- Vite configuration
- `index.html`

It then projects minimal Tailwind/global CSS wiring, the React entrypoint,
error boundary, role-binding wrapper, and type declarations. It never copies
legacy `src`, layouts, catalogue code, skeletons, navigation, pages, or visible
shells.

`ContentDataPlan`, `PagePurposeContract`, and `InteractionContract` are
materialized as canonical JSON/TypeScript exports without an AI call.

Routes, role access, navigation bindings, `App.tsx`, and application entry are
projected deterministically from canonical Tier 1 routes, IA, roles, and the
validated page-file ownership map.

## AI stages

The cold happy path makes exactly two calls:

| Stage | Model | Calls |
|---|---|---:|
| Tier 1 business components | `deepseek/deepseek-v4-pro` | 1 |
| Tier 1 pages | `deepseek/deepseek-v4-pro` | 1 |

`z-ai/glm-5.2` is available only for one narrow repair per AI-authored batch.
The maximum is four calls. Repairs receive one batch, its exact owned files,
concrete diagnostics, and immutable canonical bindings. They cannot change
paths, another batch, routes, dependencies, DesignDNA, or AppSpec behavior.

Unknown model families fail before provider calls. Existing global call,
request-cost, daily-cost, and cancellation controls remain authoritative.
Phase 3B additionally enforces 240-second component, 300-second page,
150-second repair, 600-second phase, four-call, and $0.25 ceilings.

## Static pre-build gate

The candidate reaches `candidate_build_pending` only when all checks pass:

- exact DAG-derived file manifest
- TypeScript parsing and no-emit compilation using the checked-in compiler
- approved package imports and resolved local imports
- required component/page exports
- exact deterministic routes and role access
- canonical action, state, transition, evidence, and acceptance-test hooks
- exact ContentDataPlan JSON and hashes
- IA mobile bindings
- absence of legacy scaffold/catalogue markers and `@/ui`

Vite, Playwright, Axe, visual criticism, novelty review, Tier 2/3 generation,
polish, finalize, promotion, and serving are Phase 3B-prohibited.

## Cache invalidation

- Dependency-lock/foundation changes invalidate foundation and downstream.
- ContentDataPlan changes invalidate data, components, pages, routes, and
  validation.
- BusinessComponentPlan or DesignDNA changes invalidate components and
  downstream.
- IA/page-route changes invalidate pages, deterministic routes, and validation.
- Component prompt/model changes invalidate components and downstream.
- Page prompt/model changes invalidate pages, routes, and validation.

Every hit is reparsed, hash-checked, rematerialized into a new revision, and
run through the complete static gate. Terminal workspaces are never mutated.

## Local verification

No fixture test constructs a live provider. Candidate tests use strict
structured fixture responses and the checked-in TypeScript compiler:

```powershell
cd backend
python -m pytest -q tests/candidate_generation/test_phase3b_candidate_generation.py
python -m pytest -q tests/composition_contract/test_phase3a_composition_contract.py
python -m pytest -q tests/design_contract/test_phase2_design_contract.py
```

The known Windows environment issue remains: pytest may warn that it cannot
write `.pytest_cache` because of local ACLs. Tests use an injected repo-local
candidate root rather than `tmp_path`.

No paid provider or live canary is authorized by Phase 3B.
