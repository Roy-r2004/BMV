# Preview Generator v2 — Phase 7 Rollout & Promotion Design

**Status:** Umbrella design — Phase 7A implemented; 7B–7F pending design/approval.
**Depends on:** Phase 6B (`tier_3_accepted` / `tier_3_failed_serving_tier_2`) and all prior v2 phases.
**Non-goals for this document:** code, migrations, live providers, serving-pointer mutation, or promotion execution.

## Purpose

Phase 7 is the first phase that may change what a customer sees. It must convert
an append-only, fully validated Tier 1–3 candidate lineage into a served preview
under explicit human/automation control, with atomic promotion, measured
rollout, and automatic rollback — without rewriting accepted candidate history.

## Hard constraints

1. Accepted candidate revisions, manifests, Phase 4/5/6 summaries, and workspaces
   are **immutable**. Promotion creates new serving records; it never edits
   historical candidate rows or files.
2. No silent promotion. Every serve requires an explicit promotion decision
   record with actor, policy revision, and lineage hashes.
3. Serving-pointer changes are **atomic** and transactional.
4. Rollback always targets the last accepted served tier pointer, never a
   regenerate-in-place.
5. Live provider canaries are **separately approved** and bounded.
6. `PREVIEW_GENERATOR_V2` and rollout percentages remain fail-closed defaults
   until operators enable them.

## Feature flags and targeting

Proposed flags (all default off / zero):

| Flag | Default | Role |
|---|---|---|
| `V2_PHASE7_ROLLOUT_ENABLED` | `false` | Master Phase 7 gate |
| `V2_PHASE7_SHADOW_ENABLED` | `false` | Run v2 in shadow without serving |
| `V2_PHASE7_PROMOTE_ENABLED` | `false` | Allow explicit promotion writes |
| `V2_PHASE7_ROLLOUT_PERCENT` | `0` | Sticky request hash bucket 0–100 |
| `V2_PHASE7_REQUEST_ALLOWLIST` | empty | Exact request IDs permitted regardless of % |
| `V2_PHASE7_CIRCUIT_BREAKER_ENABLED` | `true` when rollout on | Auto-disable promote on failure rate |

Selection order:

1. master flag off → return current served v1/v2 pointer unchanged;
2. allowlist match → eligible for shadow and/or promote path;
3. otherwise sticky percent bucket on stable request hash;
4. circuit breaker open → force shadow-only or freeze promote.

## Shadow execution

Shadow mode runs the full v2 contract → Tier 1–3 pipeline (or reuses the latest
accepted Tier 3 summary) **without** changing serving pointers.

Shadow produces:

- latency, token, cost, and reliability telemetry;
- comparison artifacts versus the currently served v1 preview (when present);
- a non-serving `shadow_evaluation` summary linked to the candidate lineage.

Shadow failures must never affect customer traffic.

## Explicit candidate promotion

Promotion inputs (all required):

- request ID;
- accepted effective-tier summary (`tier_1_accepted` / `tier_2_accepted` /
  `tier_3_accepted` as policy allows);
- candidate revision UUID + file manifest hash;
- Phase 4 runtime summary hash;
- Phase 5 visual summary hash;
- actor identity and reason;
- policy revision.

Promotion outputs (append-only):

- `preview_promotion_decisions` row;
- optional new `preview_serving_pointer` version row;
- audit event stream entry.

Promotion is rejected when:

- lineage hashes mismatch;
- highest accepted tier below the required rollout tier;
- circuit breaker is open;
- promote flag is off;
- request is outside allowlist/percent; or
- a concurrent promotion race loses the transaction.

## Atomic serving-pointer changes

Serving pointer shape (conceptual):

```text
(request_id, pointer_version, candidate_revision_id, effective_tier,
 summary_sha256, promoted_at, actor, previous_pointer_version)
```

Rules:

- insert-only new pointer versions;
- one current pointer per request via unique partial index / status flag flipped
  in the same transaction;
- readers always resolve the current pointer by a single indexed query;
- failed transactions leave the previous pointer current.

## Rollback

Rollback creates a new pointer version that restores the previous accepted
pointer (or an explicit earlier version), recording:

- rollback reason;
- failing promotion/decision IDs;
- circuit-breaker trip metadata when applicable.

Rollback never deletes candidate history, promotions, or audits.

## One separately approved live canary

Before any percentage rollout above zero:

1. operator writes an explicit canary approval (ticket + policy revision);
2. exactly one allowlisted request runs with live providers under hard budgets;
3. results are reviewed against v1 and against fixture baselines;
4. canary evidence is attached to the promotion decision.

No automatic multi-request live canary is in scope for the first Phase 7 cut.

## Telemetry and comparison

Required metrics per request / per phase:

- wall latency (p50/p95/p99);
- provider calls, output tokens, estimated cost;
- success / fallback / timeout rates by stage;
- Phase 4 route and journey pass rates;
- Phase 5 accept / reject / refine counts;
- Tier 2/3 fallback rates (`serving_tier_1` / `serving_tier_2`);
- promote / rollback / circuit-breaker events.

v1 comparison dimensions:

- time-to-ready;
- cost;
- route coverage;
- visual accept rate;
- operator override rate.

## Circuit breakers and automatic rollback

Suggested initial thresholds (tunable, not hard-coded in this design):

- promote failure rate above N% in a sliding window → open breaker;
- Phase 4/5 hard-fail spike → freeze promote, keep shadow optional;
- on breaker open: automatically rollback newly promoted pointers within the
  window when health checks fail, or freeze further promotes while leaving the
  last known-good pointer.

All breaker actions are audited.

## Operational dashboards and alerts

Dashboards:

- rollout percent and allowlist size;
- shadow vs promote volume;
- latency/cost/reliability by tier;
- fallback distribution;
- circuit-breaker state;
- v1 vs v2 comparison cards.

Alerts:

- breaker open;
- promote error budget burn;
- serving-pointer write failures;
- live-canary budget overrun;
- unexpected history mutation attempts (should be impossible; alert if seen).

## Audit history

Every Phase 7 action appends an immutable audit record:

- actor / system principal;
- action (`shadow`, `promote`, `rollback`, `breaker_open`, `breaker_close`);
- request and candidate lineage hashes;
- before/after pointer versions;
- reason and ticket ID when human-initiated.

## Out of scope / deferred

- deleting accepted candidates or summaries;
- mutating accepted workspaces;
- automatic Tier 2/3 regeneration on promote failure;
- multi-region serving fan-out;
- customer-facing A/B UI beyond sticky percent;
- unpaid expansion of live canaries.

## Approval gate before implementation

Implementation must not start until this design is explicitly approved and a
separate live-canary approval exists for any paid provider run.
