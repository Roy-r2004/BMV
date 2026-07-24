# Preview Generator v2 Phase 2 Design Contract

Phase 2 is a strict three-stage AI boundary downstream of the immutable
Phase 1A source/strategy seed and the canonical Phase 1B AppSpec/tier
contract. It produces no React, component plan, workspace, build, browser
run, or visual refinement.

## Configured model routing

- ProductStrategyV2: `deepseek/deepseek-v4-pro`
- InformationArchitecture: `google/gemini-2.5-flash`
- DesignDNA: `z-ai/glm-5.2`
- DesignDNA with a local reference image:
  `meta-llama/llama-3.2-11b-vision-instruct`

Haiku is not a default. Operators may configure it explicitly as an economy
model. Unknown model families fail before provider calls.

The uncached happy path is exactly three calls. Each stage permits at most one
additional call, and only after JSON/schema or deterministic validation
failure. A conservative but valid design is not retried.

## Artifact separation

All artifacts include `DesignContractRefs`, which references:

- immutable customer source ID/hash;
- immutable Phase 1A ProductStrategy seed ID/revision/hash;
- canonical AppSpec ID/revision/hash;
- ordered Tier 1, Tier 2, and Tier 3 artifact IDs/hashes/policy revision.

`ProductStrategyV2` is an AI-authored downstream strategy. It never overwrites
the Phase 1A seed. `InformationArchitecture` references ProductStrategyV2.
`DesignDNA` references both upstream Phase 2 artifacts.

The schemas contain no skeleton IDs, catalogue slots, fixed heroes, ops-shell
IDs, component choices, source paths, JSX, TSX, or generated content.

## Caching

Each stage cache key includes the source, strategy seed, AppSpec, all three
tier hashes, schema version, design policy revision, prompt revision,
effective model, model family, sampling/budget values, reference mode, and
upstream artifact/cache hashes.

Every cache hit reparses the strict Pydantic schema, recomputes the artifact
hash, verifies database provenance, and reruns deterministic validation.
Corrupt or invalid matching entries fail closed.

## Telemetry and limits

Each persisted stage records effective model, provider, family, prompt
revision, provider calls, prompt/completion/total tokens, cost, wall latency,
transport retries, validation retries, and validation-retry reason.

Stage defaults:

- ProductStrategyV2: 4,500 output tokens, 90 seconds.
- InformationArchitecture: 9,000 output tokens, 120 seconds.
- DesignDNA: 5,000 output tokens, 120 seconds.
- Entire phase: 300 seconds and a measured `$0.25` cost ceiling.

## Terminal state

Only three valid, persisted artifact references can produce
`design_contract_ready`. The request summary contains references and metrics,
not duplicated artifact contents. Failure leaves the last safe Phase 1B
`contract_ready` boundary or reusable valid Phase 2 cache entries.
