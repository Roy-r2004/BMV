# Preview Generator v2 — Phase 7D Circuit-Breaker Actions & Automatic Rollback

**Status:** Implemented (Phase 7D committed).
**Umbrella:** `PREVIEW_GENERATOR_V2_PHASE7_ROLLOUT_DESIGN.md`.
**Depends on:** Phase 7A contracts + Phase 7B shadow + Phase 7C allowlist
promotion (`cc6f5e8` and predecessors).
**Scope:** Phase 7D only — execute circuit-breaker state transitions and
bounded automatic rollback of unhealthy promoted pointers.
**Forbidden in 7D:** percentage serving (7F), live canary provider runs (7F),
dashboard mutation automation (7E), unpaid provider construction, deleting
pointer/decision history, collapsing human REQUEST→APPROVE→APPLY into one
call, changing flags-off legacy serving.

---

## 0. Goal and non-goals

### Goal

Detect promote/serve health budget burn using Phase 7A metric classes, open a
circuit breaker with audited state transitions, freeze further promotions
while open, and — when policy allows — automatically roll back **recently
promoted** unhealthy pointers to the last verified predecessor without
mutating history.

### Non-goals (deferred)

| Subphase | Deferred |
|---|---|
| 7E | Dashboards / alerts automation and runbook bots |
| 7F | Live canary + percentage serving |
| — | Multi-region fan-out, deleting accepted candidates, Tier regen on failure |

---

## 1. Hard constraints (inherited + 7D-specific)

1. **Reuse Phase 7C pointer transaction.** Auto-rollback must call the same
   atomic pointer-swap sequence (`apply_pointer_swap_transaction` or a thin
   trusted wrapper). Never invent a second swap path.
2. **Append-only history.** Breaker states, decisions, status events, audits,
   and pointers remain insert-only (pointers: `is_current` flip only).
3. **No provider construction.** Auto-rollback and breaker evaluation must
   not call LLMs, browsers, or paid APIs. Health probes use filesystem +
   optional cheap HTTP against already-served assets only.
4. **Human promotion remains three-step.** Breaker freeze rejects **apply**
   (and optionally request) when open; it does not auto-approve promotions.
5. **Auto-rollback is not silent.** Every automatic rollback creates a
   `decision_type=rollback` decision with system actor, status lineage
   `requested→approved→applied` (or a dedicated `system_auto` status path
   approved below), plus `rollback_completed` / `breaker_*` audits.
6. **Scope is bounded.** Auto-rollback only targets pointers promoted within
   a configurable lookback window that fail serving-health checks. It never
   rolls back arbitrary historical versions without policy match.
7. **Flags-off unchanged.** When
   `V2_PHASE7_ROLLOUT_ENABLED` / `V2_PHASE7_CIRCUIT_BREAKER_ENABLED` are
   false or config invalid, no breaker transitions and no auto-rollback.
8. **Serving hot path stays read-only.** Customer `get_dist_dir` / Option A
   adapter must not open breakers or perform rollback. Metrics may be
   recorded asynchronously off the hot path.

---

## 2. Relationship to Phase 7C

| Concern | 7C | 7D |
|---|---|---|
| Human promote/rollback | yes | unchanged |
| Apply eligibility checks `breaker != open` | yes (fail closed) | still required; state now mutable |
| Breaker tables | schema only | write state transitions |
| Auto-rollback | forbidden | allowed under policy |
| Serving fallback audit | best-effort, 0.25s | unchanged; may emit metrics feed |
| Percent serving | forbidden | still forbidden |

When breaker is **open**:

- Phase 7C **apply** (promote and human rollback apply) must fail closed
  with reason `breaker_open` unless a documented emergency admin override
  with ticket is approved (default: **no override in first 7D cut**).
- Shadow (7B) may continue if policy says so (default: shadow allowed).
- Customer serving continues via current pointer + 7C fallback order.

---

## 3. Breaker state machine

States (already in Phase 7A models): `closed` | `open` | `half_open` |
`disabled`.

```text
disabled ──(enable+valid policy)──► closed
closed ──(trip criteria)──► open
open ──(open_duration elapsed)──► half_open
half_open ──(probe success budget)──► closed
half_open ──(probe failure)──► open
any ──(admin disable)──► disabled
```

### 3.1 Scopes

Reuse policy `scope`:

- `global` — one breaker for the Phase 7 rollout plane
- `request` — per `request_id` (optional second cut; first cut may ship
  **global only**)

Recommended first cut: **global scope only**, with per-request rollback
targets selected from the promote window.

### 3.2 Trip criteria (evaluate against policy)

Use `CircuitBreakerPolicyContract` fields already defined:

| Input | Threshold field | Trip when |
|---|---|---|
| Promotion-write failure rate in window | `promotion_write_failure_threshold` | rate ≥ threshold and samples ≥ `min_samples` |
| Serving-health failure rate | `serving_health_failure_threshold` | rate ≥ threshold and samples ≥ `min_samples` |
| Consecutive serving-health failures | `consecutive_serving_health_failures` | streak ≥ N |
| p95 serve latency | `p95_serving_latency_seconds` | p95 ≥ threshold (optional first cut) |
| Cost spike | `cost_spike_multiplier` | **deferred** (no paid providers in 7D) |

Metric classes that **do not** trip serve-rollback (from 7A):

- generation failure, visual rejection, operator rejection,
  runtime-validation failure (these continue to block human promote via
  eligibility, not auto-rollback).

### 3.3 Half-open probes

- After `open_duration_seconds`, transition to `half_open`.
- Allow up to `half_open_probes` successful human **or** system promote
  applies (or synthetic health probes) before closing.
- Any serving-health failure during half-open re-opens the breaker.

---

## 4. Automatic rollback policy

### 4.1 When auto-rollback runs

Trigger only if **all** are true:

1. `V2_PHASE7_ROLLOUT_ENABLED=true`
2. `V2_PHASE7_PROMOTE_ENABLED=true` (rollback still needs promote plane)
3. `V2_PHASE7_CIRCUIT_BREAKER_ENABLED=true`
4. `V2_PHASE7_CONFIG_VALID=true`
5. `V2_PHASE7_AUTO_ROLLBACK_ENABLED=true` (**new flag**, default `false`)
6. Breaker just opened **or** consecutive serving-health failures hit policy
7. Target pointer is `v2_candidate` (or rollback-to-v2) and current
8. Target was promoted within `auto_rollback_lookback_seconds` (proposed
   default: equal to `window_seconds` or 3600)
9. Verified predecessor exists (prefer `previous_pointer_version`; else
   latest verified `legacy_v1` for that request)
10. Predecessor passes the same rollback-target verification as Phase 7C
11. No concurrent human apply in flight for that request (serialization)

### 4.2 What auto-rollback does

For each eligible request (bounded concurrency, default 1):

1. Create system decision (`actor_id=system:phase7-breaker`,
   `decision_type=rollback`) with reason/ticket metadata
   `auto_rollback:<breaker_event_id>`.
2. System SoD: requester/approver/apply may be the same system principal
   **only** for auto-rollback; record `emergency_dual_role` style metadata
   with `auto_rollback=true` (human SoD rules unchanged).
3. Recompute health; verify expected current pointer version.
4. Execute Phase 7C atomic pointer swap with `pointer_action=rollback`.
5. Append audits: `rollback_completed`, `breaker_auto_rollback_applied`.

### 4.3 What auto-rollback must not do

- Must not delete or reactivate old pointer rows.
- Must not roll back to another request’s pointer.
- Must not call providers, Playwright, or Tier regeneration.
- Must not change `V2_PHASE7_ROLLOUT_PERCENT` or allowlist.
- Must not open infinite retry loops; failed auto-rollback increments
  failure metrics and remains audible via audit + log.

### 4.4 Decision status model for system auto path

**Preferred (minimal schema churn):** insert decision + three status events
(`requested`, `approved`, `applied`) in one transaction with system actor,
or a single transaction that writes `requested` + `applied` with metadata
`system_auto_approved=true` if product accepts collapsing system SoD.

**Open decision for approval:** keep full three status events for symmetry
with 7C (recommended) vs compact system path.

---

## 5. Serving-health evaluation (async)

Reuse `ServingHealthCheckContract` from Phase 7A:

| Check | First-cut required | Notes |
|---|---|---|
| Pointer resolves | yes | DB |
| Manifest exists + hash | yes | candidate row |
| Dist exists | yes | filesystem |
| `index.html` resolves | yes | filesystem |
| Health route HTTP 200 | optional | off by default |
| Severe console errors | deferred | needs browser |
| Primary journey smoke | deferred | needs browser |
| Latency below threshold | optional | from serving metrics |
| Visual score drift | advisory only | never alone triggers rollback |

Evaluation cadence: background worker / cron-like admin tick (sync admin
`POST /api/admin/rollout/breaker/evaluate` allowed for ops), **not** on the
customer `get_dist_dir` path.

---

## 6. APIs (trusted admin only)

Proposed additions under `/api/admin/rollout`:

| Method | Path | Purpose |
|---|---|---|
| GET | `/breaker/state` | Current breaker view |
| GET | `/breaker/history` | Append-only state snapshots |
| POST | `/breaker/evaluate` | Recompute metrics; maybe trip/recover |
| POST | `/breaker/open` | Manual open (admin + ticket + reason) |
| POST | `/breaker/close` | Manual close / disable (admin + ticket) |
| POST | `/breaker/auto-rollbacks/run` | Explicit ops trigger for eligible set |
| GET | `/breaker/auto-rollbacks` | List recent auto-rollback decisions |

Bodies: extra-forbid schemas; ban client `actor_id`, roles, breaker override
without ticket fields, eligibility hashes, pointer objects.

No combined “trip and rollback and promote” endpoint.

---

## 7. Authorization

| Action | viewer | operator | approver | admin | system:phase7-breaker |
|---|---|---|---|---|---|
| Read breaker state/history | yes | yes | yes | yes | yes |
| Evaluate / tick | no | no | no | yes | yes |
| Manual open/close | no | no | no | yes | no |
| Auto-rollback execute | no | no | no | yes (ops trigger) | yes |
| Human promote apply | — | — | — | (7C rules; blocked if open) | no |

Service principal `system:phase7-breaker` must be mapped only via trusted
server config, never request JSON.

---

## 8. Configuration

| Flag | Default | Meaning |
|---|---|---|
| `V2_PHASE7_CIRCUIT_BREAKER_ENABLED` | `false` | Allow state transitions |
| `V2_PHASE7_AUTO_ROLLBACK_ENABLED` | `false` | Allow automatic pointer rollback |
| `V2_PHASE7_AUTO_ROLLBACK_LOOKBACK_SECONDS` | `3600` | Promote age window |
| `V2_PHASE7_BREAKER_EVAL_MAX_REQUESTS` | `50` | Cap per evaluate tick |

Invalid config → fail closed (no trips, no auto-rollback). Percent still
must not authorize promotion (7C rule remains).

---

## 9. Persistence

### Existing (7A)

- `preview_circuit_breaker_policies` — append-only policy versions
- `preview_circuit_breaker_states` — append-only state snapshots

### Additive (7D migration)

Prefer additive columns / tables only if needed:

- `preview_breaker_metric_samples` (optional) — append-only samples for
  windowed rate math, **or** derive from existing audit/status events to
  avoid new tables in the first cut
- Decision metadata keys: `auto_rollback`, `breaker_state_id`,
  `lookback_seconds` in audit `metadata_json`

Downgrade fails if any `breaker_opened` / auto-rollback applied events
exist.

---

## 10. Audit events (new emitters)

Already reserved in 7A taxonomy; 7D begins emitting:

- `breaker_opened`
- `breaker_half_open`
- `breaker_closed`
- `breaker_auto_rollback_applied` (or reuse `rollback_completed` with
  metadata `auto_rollback=true`)

Every event: actor/system, policy revision, scope key, reason, ticket
(when human), pointer before/after when rollback, metric snapshot hash,
timestamp.

---

## 11. Interaction with serving adapter (7C)

- Unhealthy v2 fallback order stays:
  1. verified `legacy_v1` pointer
  2. legacy workspace
  3. existing not-found
- Fallback **must not** open the breaker synchronously.
- Optional: emit a bounded, async metric sample “serving_fallback_observed”
  after response (never block; same timeout discipline as 7C audit ≤ 0.25s
  if done inline).

---

## 12. Concurrency and safety

1. Global evaluate tick uses a process lock (similar to 7B shadow gate) or
   DB advisory lock.
2. Per-request auto-rollback reuses pointer `SELECT FOR UPDATE` /
   SQLite immediate write semantics from 7C.
3. If human apply wins the race, auto-rollback sees version conflict and
   aborts without partial rows.
4. No automatic retry storm; ops may re-run evaluate.

---

## 13. Testing requirements (implementation gate)

Prove:

- flags off → no breaker transitions, no auto-rollback
- trip on promotion-write failure rate / consecutive serve failures
- open freezes human promote apply
- half-open probe success closes; failure re-opens
- auto-rollback disabled flag prevents pointer changes even when open
- auto-rollback creates new pointer version with `pointer_action=rollback`
- predecessor validation failures skip request without mutating current
- version conflict with concurrent human apply is all-or-nothing
- no provider construction
- no percent serving
- no canary consumption
- serving adapter still timeout-bounds audit and never calls breaker write
  path
- Phase 0–7C regressions remain green

---

## 14. File plan (proposed)

```text
docs/architecture/PREVIEW_GENERATOR_V2_PHASE7D_CIRCUIT_BREAKER_AUTO_ROLLBACK.md

backend/app/application/rollout/breaker_service.py
backend/app/application/rollout/breaker_metrics.py
backend/app/application/rollout/auto_rollback.py
backend/app/domain/schemas/breaker.py
backend/app/infrastructure/db/phase7d_migrations.py
backend/tests/rollout/test_phase7d_*.py
```

Extend `rollout_diagnostics.py` (or a dedicated breaker router) with GET/POST
surfaces above. Reuse `apply_transaction.py` for pointer swaps.

---

## 15. Open decisions for approval

1. **First-cut scope:** global breaker only, or per-request breakers too?
2. **System SoD:** full `requested→approved→applied` status events for
   auto-rollback, or compact system path?
3. **Human apply while open:** hard block only, or admin+ticket override?
4. **Auto-rollback trigger:** on breaker open only, or also on consecutive
   serving-health failures while closed?
5. **Metric source:** derive from audit/status events vs new sample table?
6. **Optional HTTP health probe:** enabled in first cut or filesystem-only?

---

## 16. Implementation gate

Implementation starts only after explicit approval of this document and the
open decisions above.

Still forbidden until later approval:

- 7E dashboard/alert automation that mutates state
- 7F live canary + percentage serving
- paid provider construction for breaker/rollback paths

### Expected runtime (implementation phase)

| Path | Expected |
|---|---|
| Focused Phase 7D suite | tens of seconds (no providers) |
| Evaluate tick | milliseconds–low seconds |
| Full Phase 0–7C regression | ~15–20 min |
| Paid provider calls | **zero** |
