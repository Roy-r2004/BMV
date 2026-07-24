# Preview Generator v2 Contract Baseline

This note records the deterministic contract boundary introduced by Phase 1A
and Phase 1B. It is additive: preview generator v1 remains the default and its
generation path is unchanged.

## Phase 1A inputs

- `CustomerSourceSnapshotV2` is a frozen copy of customer-authored input and
  captured reference evidence.
- `ProductStrategy` is a deterministic, inferred projection. It stores the
  source hash and cannot mutate the source snapshot.
- A v2 AppSpec is complete only after strict deterministic validation and an
  independent coverage review whose model family differs from the author.
- Unknown model families and fallback AppSpecs fail closed.

## Phase 1B artifacts

`PreviewTierArtifact` is a frozen, extra-forbid, reference-only schema. It
stores:

- tier schema version and selection-policy revision;
- request ID and parent tier number;
- immutable source, strategy, and canonical AppSpec IDs/revisions/hashes;
- canonical ID collections for requirements, roles, entities, capabilities,
  pages, states, actions, transitions, evidence, journeys, and acceptance
  tests;
- reference-only completion proofs and a reference-only primary journey proof.

It has no fields for AppSpec objects, page definitions, prompts, source code,
or generated content. Unknown fields are rejected recursively.

The persisted `preview_tier_artifacts` row adds the database record ID, the
parent artifact row ID, the canonical JSON hash, and the deterministic
validation report. A unique constraint permits exactly one artifact for each
AppSpec revision and tier.

## Deterministic selection policy

Selection-policy revision: `2026-07-24.1`.

1. Validate the canonical AppSpec.
2. Select the highest-ranked active interaction requirement that has a
   complete journey, executable action/transition chain, terminal visible
   success evidence, and a journey-backed acceptance test. Priority, customer
   source rank, ProductStrategy outcome overlap, and AppSpec order form the
   deterministic ranking key.
3. Build Tier 1 from that complete primary journey.
4. Build Tier 2 from every Tier 1 reference plus every `must` requirement.
5. Build Tier 3 from every Tier 2 reference plus every active non-deferred
   requirement and every canonical AppSpec page.
6. Expand each graph to a fixed point and emit every reference collection in
   canonical AppSpec order.
7. Verify Tier 2 is a superset of Tier 1 and Tier 3 is a superset of Tier 2
   across every reference collection.

The selector has no page-count cap. The AppSpec contract currently accepts up
to 100 canonical pages, and Tier 3 references all of them.

## Failure and transaction policy

- Unknown, invalid, cross-request, or deferred references fail closed.
- A partial persisted tier set fails closed and is never repaired implicitly.
- Existing tiers are reused only when all three artifacts, hashes, validation
  reports, parent links, and the selection-policy revision match exactly.
- A changed selection-policy revision cannot silently reuse older artifacts.
- All three tiers are built and validated in memory before persistence.
- Tier 1, Tier 2, Tier 3, their parent links, and the request's
  `contract_ready` summary are committed in one transaction. An insert or
  summary failure rolls back every new tier row.

## Pipeline boundary

The v2 path stops at `contract_ready`. Phase 1B does not invoke planning,
codegen, workspace creation, UI generation, polish, build, finalization,
Playwright, or paid canaries. Tier selection itself makes zero AI calls; the
only provider calls in the end-to-end boundary test remain the Phase 1A
AppSpec author and independent coverage reviewer calls.

## Local regression record

Recorded on 2026-07-24 with pytest's cache provider disabled because the
workspace retains the Windows cache/temporary-directory ACL limitation noted
in the v1 baseline:

- Phase 1B focused tier and transaction tests: `14 passed`.
- Original Phase 1A contract regression tests: `17 passed`.
- Phase 0 boundary and frozen characterization tests: `13 passed`.

All provider behavior in these tests is supplied by local fixture doubles. No
paid canary, workspace generation, build, commit, or push is part of this
record.
