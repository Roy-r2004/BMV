# Preview Generator v2 — Phase 7B Shadow Execution Design

**Status:** Implemented (Phase 7B committed).
**Umbrella:** `PREVIEW_GENERATOR_V2_PHASE7_ROLLOUT_DESIGN.md`.
**Depends on:** Phase 7A control plane (committed) and Phases 0–6B.
**Scope:** Phase 7B only — shadow evaluation execution, telemetry, and
v1/v2 comparison artifacts without changing what customers see.
**Forbidden in 7B:** promotion writes, rollback writes, serving-pointer
mutation, percentage-driven serving, circuit-breaker actions, live canary
provider runs, dashboards that mutate state, production serving-path
replacement.

---

## 0. Goal and non-goals

### Goal

Run (or reuse) the v2 candidate lineage in a **shadow** lane that never
updates the serving pointer, then persist an append-only
`preview_shadow_evaluations` record with telemetry and optional comparison
against the currently served preview (legacy v1 or prior pointer).

### Non-goals (deferred)

| Subphase | Deferred work |
|---|---|
| 7C | Manual allowlist promotion and rollback write APIs |
| 7D | Circuit-breaker actions and automatic rollback |
| 7E | Dashboards, alerts, operational runbook automation |
| 7F | Live canary execution and percentage rollout serving |

---

## 1. Hard constraints (inherited + 7B-specific)

1. **No serving mutation.** Shadow must set and enforce
   `no_serving_mutation = true`. Any code path that calls pointer swap,
   promote, or rollback is a hard failure.
2. **Production serve path unchanged.** `preview_apps.py` continues to use
   `get_dist_dir(request_id)` only. Shadow never becomes a read dependency of
   customer iframe serving.
3. **Fail closed.** Shadow does not run unless
   `V2_PHASE7_ROLLOUT_ENABLED` and `V2_PHASE7_SHADOW_ENABLED` are true,
   Phase 7A config is valid, and the actor is authorized for shadow
   eligibility computation / shadow run.
4. **Eligibility remains advisory for promote.** Shadow eligibility may
   authorize a shadow run only when the master + shadow flags and RBAC allow
   it; it still never authorizes promotion.
5. **Append-only history.** Shadow rows and comparison artifacts are insert
   only. Status transitions use append-only events or a new evaluation row,
   never in-place mutation of completed evaluations.
6. **Provider policy is explicit.** Phase 7B must choose one of the modes
   in §3; unpaid / fixture-only mode is the default recommendation for the
   first cut.

---

## 2. Feature flags (reuse Phase 7A parsing)

| Flag | Default | Phase 7B behavior |
|---|---|---|
| `V2_PHASE7_ROLLOUT_ENABLED` | `false` | Master gate; off → no shadow |
| `V2_PHASE7_SHADOW_ENABLED` | `false` | Enables shadow executor |
| `V2_PHASE7_PROMOTE_ENABLED` | `false` | Ignored for shadow; still no promote API |
| `V2_PHASE7_ROLLOUT_PERCENT` | `0` | Used for shadow targeting eligibility |
| `V2_PHASE7_REQUEST_ALLOWLIST` | empty | Allowlist bypasses percent for shadow |
| `V2_PHASE7_SHADOW_MODE` | `reuse_accepted` | See §3 |
| `V2_PHASE7_SHADOW_MAX_CONCURRENCY` | `1` | Process-local cap |
| `V2_PHASE7_SHADOW_MAX_WALL_SECONDS` | `3600` | Hard wall for a shadow attempt |

Proposed new flags (fail closed; not yet in settings):

- `V2_PHASE7_SHADOW_MODE` ∈
  `{reuse_accepted, regenerate_fixture, regenerate_live}`
  - malformed → treat as `reuse_accepted` and mark config invalid for live
    regeneration
- `V2_PHASE7_SHADOW_COMPARE_ENABLED` default `true` (artifact compare only)
- `V2_PHASE7_SHADOW_LIVE_PROVIDERS_ENABLED` default `false`
  - must be true **and** mode `regenerate_live` to construct providers

No flag may update a serving pointer.

---

## 3. Shadow execution modes

### 3.1 `reuse_accepted` (recommended default for first 7B cut)

Inputs:

- request ID
- latest accepted effective-tier summary for the requested tier
  (`tier_1_accepted` / `tier_2_accepted` / `tier_3_accepted` as available)
- Phase 4 + Phase 5 summary hashes already on the lineage
- current serving-pointer view (read-only resolver from 7A)

Behavior:

- **Do not** regenerate candidate files or call providers.
- Build telemetry from persisted lineage + workspace fingerprints.
- Optionally compare served target (v1 dist / current pointer) versus the
  accepted v2 candidate workspace/dist hashes and route inventories.
- Persist `preview_shadow_evaluations` with `result_status=completed|failed`.

### 3.2 `regenerate_fixture`

- Re-run bounded pipeline stages against recorded fixtures / stub providers.
- Zero paid provider calls.
- Useful for CI and local soak tests.

### 3.3 `regenerate_live` (explicit opt-in only)

- Constructs real providers under existing Phase 3–6 budgets.
- Requires `V2_PHASE7_SHADOW_LIVE_PROVIDERS_ENABLED=true`, trusted
  `rollout_operator` or `rollout_admin`, non-empty ticket/reason, and
  allowlist membership (percent alone is insufficient for live regenerate).
- Still **must not** mutate serving pointers.
- Out of scope for the first implementation PR unless separately approved.

**Recommendation:** Implement 7B with `reuse_accepted` + `regenerate_fixture`
only. Leave `regenerate_live` as a typed mode that rejects at the service
boundary until a later approval.

---

## 4. Authorization and targeting

Reuse Phase 7A:

- `TrustedRolloutActor` roles from server auth only
- `compute_promotion_eligibility` / shadow fields on
  `PromotionEligibilityResult`
- sticky bucket + allowlist

Phase 7B permission addition:

| Role | Start shadow (`reuse_accepted` / fixture) | Start live regenerate | Read shadow results |
|---|---|---|---|
| `rollout_viewer` | no | no | yes |
| `rollout_operator` | yes | no (until live mode approved) | yes |
| `rollout_approver` | no | no | yes |
| `rollout_admin` | yes | gated same as operator for live | yes |

Client JSON must not supply roles. Shadow start APIs accept only request ID,
mode (optional, default from settings), reason, and ticket (required for live).

---

## 5. Shadow evaluation lifecycle

### 5.1 Row shape (Phase 7A table — already migrated)

`preview_shadow_evaluations` fields from 7A remain canonical:

- `request_id`
- `served_target_kind` (`legacy_v1` | `v2_candidate` | `none`)
- `served_pointer_version` (nullable)
- `v2_candidate_revision_id` / `v2_effective_summary_id`
- `comparison_policy_revision`
- `telemetry_json` / `telemetry_sha256`
- `result_status` (`pending` | `completed` | `failed`)
- `comparison_artifact_sha256`
- `no_serving_mutation` CHECK = true
- `evaluation_sha256` UNIQUE
- `created_at`

### 5.2 Status pattern

Because the table is append-only:

1. Insert evaluation row with `result_status=pending` and provisional hashes.
2. On completion, **do not UPDATE** the pending row.
3. Insert a terminal row (or a sibling status-event table if preferred) with
   `completed` / `failed` and final hashes, linked by
   `shadow_attempt_uuid` (proposed additive column or metadata field).

**Selected pattern for 7B:** add nullable `shadow_attempt_uuid` +
`terminal_of_evaluation_id` columns via an additive Phase 7B migration, and
insert a new terminal row rather than mutating pending. Pending rows remain
forever as history.

Alternative (if additive columns deferred): store only terminal rows and keep
in-flight state in process memory / a separate non-customer queue table that
is also append-only. Prefer explicit UUID lineage.

### 5.3 Transactional guarantees

- Shadow commit never opens the pointer-swap transaction.
- Shadow repository methods must refuse any call into
  `apply_pointer_swap` / promote / rollback helpers.
- Boundary tests: production serve object/path bytes unchanged before and
  after a successful shadow run.

---

## 6. Telemetry contract

`telemetry_json` (strict schema, extra forbid):

| Field | Notes |
|---|---|
| `schema_version` | `1.0` |
| `mode` | `reuse_accepted` / `regenerate_fixture` / `regenerate_live` |
| `wall_ms` | end-to-end shadow attempt |
| `provider_calls` | 0 for reuse/fixture |
| `output_tokens` | 0 for reuse |
| `estimated_cost_usd` | 0 for reuse/fixture |
| `phase4_status` | from lineage |
| `phase5_status` | from lineage |
| `highest_accepted_tier` | 0–3 |
| `served_target_kind` | at evaluation start |
| `candidate_manifest_sha256` | |
| `effective_summary_sha256` | |
| `compare_enabled` | bool |
| `compare_status` | `skipped` / `completed` / `failed` |
| `rejection_reasons` | tuple |

Hash `telemetry_sha256` over canonical JSON.

---

## 7. Comparison artifact contract

When compare is enabled and a served preview exists:

Dimensions (advisory, not gate-to-promote in 7B):

- time-to-ready delta (served vs candidate build timestamps when known)
- route inventory coverage (served routes vs candidate route manifest)
- dist/entry existence and content hashes (not byte-identical expectation)
- Phase 4/5 status of candidate lineage
- cost/latency of the shadow attempt itself

Artifact persistence:

- store opaque JSON blob under content-addressed path or DB text column
  referenced by `comparison_artifact_sha256`
- never overwrite; new shadow → new artifact hash

Comparison must not call browsers or paid vision critics unless mode is
`regenerate_live` and separately approved. First cut: filesystem + manifest
diff only.

---

## 8. Service / API surface

### Library

```text
ShadowExecutionService.start_shadow(db, actor, request_id, *, mode, reason, ticket)
  -> ShadowEvaluationView   # advisory handle; not a promote token

ShadowExecutionService.get_evaluation(db, actor, evaluation_id)
  -> ShadowEvaluationView
```

### HTTP (proposed)

Read:

- `GET /api/admin/rollout/requests/{id}/shadow-evaluations`
- `GET /api/admin/rollout/shadow-evaluations/{evaluation_id}`

Write (shadow only):

- `POST /api/admin/rollout/requests/{id}/shadow-evaluations`
  - body: `{ "mode"?: ..., "reason": "...", "ticket_ref"?: "..." }`
  - **no** actor roles in body
  - returns pending/terminal evaluation view
  - refuses if flags off, ineligible, or mode forbidden

Still forbidden:

- any POST promote / rollback / pointer-swap endpoint

### Sync vs async

Recommended first cut: **synchronous** `reuse_accepted` / fixture path under
admin auth with wall-clock timeout. Async worker deferred unless soak tests
require it.

---

## 9. Audit events (7B may emit)

In addition to Phase 7A diagnostic events:

- `shadow_started`
- `shadow_completed`
- `shadow_failed`

Each carries request, actor, policy revision, lineage hashes, pointer version
observed (before only; after must equal before), mode, and evaluation hash.

Invariant: `pointer_version_after == pointer_version_before` for every shadow
audit event.

---

## 10. Interaction with Phase 7A eligibility

Before start:

1. Build current policy view from settings + latest persisted policy (if any).
2. Recompute `PromotionEligibilityResult` from current state (no cached token).
3. Require `eligible_for_shadow` (and mode-specific gates).
4. Record `eligibility_sha256` inside telemetry metadata.
5. Proceed only as shadow; ignore `eligible_for_promote`.

---

## 11. File plan (implementation later — not now)

```text
docs/architecture/PREVIEW_GENERATOR_V2_PHASE7B_SHADOW_EXECUTION.md  # this doc

backend/app/domain/schemas/shadow_evaluation.py
backend/app/application/rollout/shadow_service.py
backend/app/application/rollout/shadow_compare.py
backend/app/application/rollout/shadow_telemetry.py
backend/app/api/v1/routers/rollout_diagnostics.py   # GET list/detail; POST shadow only
backend/app/infrastructure/db/phase7b_migrations.py # additive UUID/lineage columns
backend/tests/rollout/test_phase7b_*.py
```

Explicitly unchanged in 7B:

```text
backend/app/api/v1/routers/preview_apps.py
pointer swap harness usage outside tests
promotion repository apply paths
```

---

## 12. Focused test plan

1. Flags off → POST shadow rejected; no rows written.
2. `reuse_accepted` completes with `no_serving_mutation=true` and zero provider
   imports/calls.
3. Served pointer version identical before and after shadow.
4. `preview_apps.py` still does not import shadow or resolver.
5. Append-only: pending row not updated; terminal row inserted.
6. Direct SQL UPDATE/DELETE on shadow table still aborted by 7A triggers.
7. RBAC: viewer cannot start; operator can start reuse/fixture; client roles
   rejected.
8. Allowlist / sticky percent gates shadow start.
9. Compare artifact hash stable for identical inputs.
10. Live mode refused when live flag off.
11. No POST promote/rollback routes appear.
12. Phase 7A + 0–6B regressions remain green.

---

## 13. Implementation gate

Implementation starts only after explicit approval of this document.

Still forbidden until later subphases are approved separately:

- 7C promotion/rollback writes
- 7D breaker actions / auto-rollback
- 7E dashboards/alerts automation
- 7F live canary + percent serving
- `regenerate_live` shadow mode (unless called out in the 7B approval)

### Open decisions for approval

1. Confirm first cut modes: `reuse_accepted` + `regenerate_fixture` only?
2. Sync admin POST vs background worker for shadow start?
3. Additive columns (`shadow_attempt_uuid`, `terminal_of_evaluation_id`) vs
   metadata-only linkage for pending→terminal lineage?

## Approved implementation decisions

1. Modes: `reuse_accepted` (default) + `regenerate_fixture` only.
   `regenerate_live` rejected before provider construction.
2. Synchronous trusted-admin POST; no background worker.
3. Additive columns: `shadow_attempt_uuid`, `terminal_of_evaluation_id`
   with append-only pending to terminal lineage.
