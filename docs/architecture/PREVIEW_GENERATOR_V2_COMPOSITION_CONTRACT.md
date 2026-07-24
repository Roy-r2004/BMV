# Preview Generator v2 Phase 3A Composition Contract

Phase 3A turns the accepted AppSpec, Tier 1, ProductStrategyV2,
InformationArchitecture, and DesignDNA into a generation-ready composition
contract without creating source files or a workspace. The terminal state is
`composition_contract_ready`.

## Call boundary

The uncached happy path makes exactly two AI calls:

- `BusinessComponentPlan`: `deepseek/deepseek-v4-pro`
- `ContentDataPlan`: `qwen/qwen-2.5-coder-32b-instruct`

`PagePurposeContract`, `InteractionContract`, and
`ComponentDependencyGraph` are deterministic and make zero provider calls.
Each AI stage permits one retry only after schema or deterministic-validation
failure. The phase call cap is four, the wall timeout is 240 seconds, and the
measured phase cost ceiling is `$0.20`. Existing request-wide call limits and
admin request/daily cost controls remain in force.

No paid canary was run for Phase 3A.

## Upstream references

Every artifact contains the same frozen `CompositionContractRefs`:

- request ID and target Tier 1;
- immutable source and Phase 1A strategy-seed references;
- canonical AppSpec reference;
- ordered Tier 1, Tier 2, and Tier 3 references;
- ProductStrategyV2, InformationArchitecture, and DesignDNA references.

The JSON stores IDs, schema versions, and hashes instead of duplicating
upstream artifacts. Database rows also carry direct foreign keys to every
accepted upstream record.

## Deterministic projections

`PagePurposeContract` is projected in canonical AppSpec page order. Every
Tier 1 page appears exactly once with its exact route, roles, requirements,
outcomes, capabilities, states, actions, transitions, evidence, journeys,
acceptance tests, IA navigation/mobile behavior, and immutable locks.
DesignDNA hierarchy, density, motion, and avoid constraints are copied
without allowing AI to change page-purpose truth.

`InteractionContract` is projected after both AI artifacts are valid. It
combines canonical actions, transitions, states, effects, journeys, evidence,
and acceptance assertions with:

- exactly one accepted trigger-component binding per Tier 1 action; and
- structured collection/field bindings for data-requiring actions.

An unbound action, transition, success-evidence item, or acceptance test fails
closed. Browser assertions are deterministic records for a later browser
gate; Phase 3A does not run a browser.

## AI-authored contracts

`BusinessComponentPlan` defines visible business components and page
composition. Domain specificity is evaluated from the component purpose,
domain language, and linked canonical requirements, entities, capabilities,
states, actions, and evidence. A common word such as `Dashboard` or `Hero` is
not rejected by name alone.

`ContentDataPlan` contains structured content items, canonical entity-backed
collections, realistic seed records, relationships, state payloads, evidence
bindings, and action input bindings. It rejects JSX, TSX, HTML, Tailwind,
TypeScript, JavaScript, source paths, and placeholder content.

Neither artifact can define routes, transitions, source code, skeleton IDs,
catalogue slots, fixed page types, ops shells, or high-level `@/ui` choices.

## Dependency graph

The deterministic DAG contains only:

- structured content nodes;
- entity-backed data nodes;
- business-component nodes;
- page nodes; and
- route nodes.

Edges are prerequisites-to-dependent. Stable Kahn ordering preserves
canonical input order inside each generation batch. Missing nodes,
self-dependencies, and cycles fail closed. No visually mandatory shared
layout, template, skeleton, or catalogue node exists.

## Caching and persistence

The `composition_contract_artifacts` table stores five immutable rows linked
as:

```text
PagePurpose
  -> BusinessComponentPlan
  -> ContentDataPlan
  -> InteractionContract
  -> ComponentDependencyGraph
```

Cache keys include all canonical upstream hashes, target tier, schema and
policy revisions, stage dependencies, and—for AI stages—prompt revision,
effective model, family, temperature, and token limit. Every hit is reparsed,
rehashed, provenance-checked, and deterministically revalidated.

A BusinessComponentPlan change invalidates ContentDataPlan, interactions, and
the DAG. A ContentDataPlan change invalidates interactions and the DAG.
Unchanged deterministic inputs reuse PagePurpose without a provider call.

Valid intermediate rows are reusable caches but do not change request status.
The final DAG row and `composition_contract_ready` summary are committed
together. Summary failure rolls back the DAG while retaining four valid
stage caches; resume requires zero provider calls.

## Boundary

Phase 3A never invokes React/component source generation, planning, codegen,
workspace creation, Vite, build, polish, finalization, Playwright, visual
critique, refinement, or a fallback scaffold. Preview generator v1 remains
unchanged and remains the default while `PREVIEW_GENERATOR_V2=false`.

## Local verification

The focused suite uses only local fixture providers and proves:

- two calls on a cold run and zero on a full cache hit;
- exact deterministic PagePurpose and Interaction projections;
- semantic component specificity rather than a name blacklist;
- complete outcome, action, evidence, data, state, journey, and test bindings;
- stable DAG ordering and cycle rejection;
- schema/validation retry provenance and unknown-model fail-closed behavior;
- cache invalidation cascades and final-summary rollback/resume; and
- the strict no-React/workspace/build downstream boundary.
