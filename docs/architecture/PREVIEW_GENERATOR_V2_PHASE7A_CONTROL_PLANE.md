# Preview Generator v2 — Phase 7A Control Plane

**Status:** Implemented (Phase 7A committed).
**Umbrella:** `PREVIEW_GENERATOR_V2_PHASE7_ROLLOUT_DESIGN.md` (approved conceptually).
**Scope:** Phase 7A only — contracts, persistence, audit, read-only resolution.
**Forbidden in 7A:** shadow execution, promotion writes, rollback writes, live
providers, percentage-driven serving, circuit-breaker actions, dashboards that
mutate state, serving-pointer mutation through operational APIs, production
serving-path replacement.

## Implementation clarifications (approved)

### Serving-pointer transaction ordering

Future-safe sequence (test harness only in 7A; no operational executor):

1. Begin transaction.
2. Acquire request-scoped serialization (`SELECT FOR UPDATE` on Postgres;
   `BEGIN IMMEDIATE` + version check on SQLite).
3. Read and verify expected current pointer version.
4. Insert promotion decision in non-applied `requested` state.
5. Mark the previous pointer non-current.
6. Insert the new pointer as current.
7. Mark the decision applied via **append-only status-event row** (never mutate
   the decision row in place).
8. Append the audit event.
9. Commit.

Partial unique index: `UNIQUE(request_id) WHERE is_current = true`.
The sequence never temporarily inserts two current rows.

### Sticky bucket (64-bit SHA-256)

```text
digest = SHA256(UTF8(normalized_salt + ":" + normalized_request_id))
value  = int.from_bytes(digest[0:8], "big")
bucket = value % 100
eligible = bucket < rollout_percent
```

Normalization: trim UTF-8 salt (non-empty); trim canonical positive integer
request ID string; no case-fold; percent integer 0–100; reject malformed.

### Frozen vectors (`salt = 2026-07-25.1`)

| request_id | first8 hex         | bucket |
|-----------:|--------------------|-------:|
| 1          | `f6cad4035b48872f` | 23     |
| 42         | `4ceb7e209e8260a1` | 89     |
| 100        | `54de3fb01b9a3816` | 74     |
| 999        | `1d3ecfbd7f8c1c69` | 37     |
| 23104      | `2d1c6c7da625a71e` | 66     |

### No applied promotions in production path

Operational decision statuses: `requested` | `rejected` | `cancelled`.
`applied` / `test_only_simulated` and promote/rollback pointer versions exist
only via `tests/rollout/harness.py` (`PHASE7A_TEST_ONLY_MODE=1`).

### Append-only strategy

- Strict tables: UPDATE/DELETE rejected by SQLite `RAISE(ABORT)` / Postgres
  triggers, plus SQLAlchemy `before_flush`.
- Status transitions: append-only event tables
  (`preview_promotion_decision_status_events`,
  `preview_live_canary_approval_status_events`).
- Pointer versions: DELETE forbidden; only `is_current` may change.

---

## 0. Goal and non-goals

### Goal

Build the safe rollout-control foundation without changing what any customer
sees. Production serving of `PREVIEW_APPS_DIR` / existing preview URLs remains
byte-for-byte and object-for-object identical when Phase 7 flags are off.

### Non-goals (deferred)

| Subphase | Deferred work |
|---|---|
| 7B | Shadow pipeline execution and v1/v2 comparison runs |
| 7C | Manual allowlist promotion and rollback write APIs |
| 7D | Circuit-breaker actions and automatic rollback |
| 7E | Dashboards, alerts, operational runbook automation |
| 7F | Live canary execution and percentage rollout |

---

## 1. Feature flags (fail-closed)

| Flag | Default | Phase 7A behavior |
|---|---|---|
| `V2_PHASE7_ROLLOUT_ENABLED` | `false` | Parsed; never serves a candidate |
| `V2_PHASE7_SHADOW_ENABLED` | `false` | Parsed; never starts shadow |
| `V2_PHASE7_PROMOTE_ENABLED` | `false` | Parsed; no promote API exists |
| `V2_PHASE7_ROLLOUT_PERCENT` | `0` | Integer 0–100 inclusive; else fail closed |
| `V2_PHASE7_REQUEST_ALLOWLIST` | empty | Comma-separated positive ints; malformed → fail closed |
| `V2_PHASE7_CIRCUIT_BREAKER_ENABLED` | `false` | Parsed only; no breaker actions |
| `V2_PHASE7_POLICY_REVISION` | `2026-07-25.1` | Stable salt input for sticky bucketing |
| `V2_PHASE7_ROLLOUT_SALT` | equals policy revision unless overridden | Immutable salt for buckets |

### Validation rules

- Percent outside `[0, 100]` → configuration error at settings load.
- Allowlist tokens that are not positive integers → configuration error.
- Duplicate allowlist IDs → normalized unique sorted set; configuration hash
  uses the normalized form.
- Conflicting settings (e.g. promote enabled while master disabled) are stored
  but eligibility always requires master + promote for write authorization in
  later phases; Phase 7A exposes eligibility only.

### Guarantees

No flag may: serve a candidate, invoke a provider, or update a serving pointer.

---

## 2. Persistence schemas (append-only)

All tables: no `UPDATE`/`DELETE` through repositories. SQLAlchemy session hooks
reject mutations other than `INSERT`. Postgres optionally adds `REVOKE UPDATE,
DELETE` from the app role in a later ops hardening step.

### 2.1 `preview_rollout_policies`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Surrogate |
| `policy_revision` | VARCHAR(64) UNIQUE | e.g. `2026-07-25.1` |
| `master_enabled` | BOOLEAN NOT NULL | |
| `shadow_enabled` | BOOLEAN NOT NULL | |
| `promote_enabled` | BOOLEAN NOT NULL | |
| `rollout_percent` | SMALLINT NOT NULL | CHECK 0–100 |
| `allowlist_json` | TEXT NOT NULL | Canonical JSON array of ints |
| `allowlist_sha256` | CHAR(64) NOT NULL | Hash of canonical allowlist JSON |
| `circuit_breaker_policy_json` | TEXT NOT NULL | Serialized breaker policy contract |
| `circuit_breaker_policy_sha256` | CHAR(64) NOT NULL | |
| `rollout_salt` | VARCHAR(128) NOT NULL | Sticky-bucket salt |
| `configuration_sha256` | CHAR(64) NOT NULL UNIQUE | Hash of all config fields |
| `created_at` | TIMESTAMPTZ/TEXT NOT NULL | UTC |
| `created_actor_id` | VARCHAR(128) NOT NULL | |
| `created_actor_role` | VARCHAR(64) NOT NULL | Trusted role at creation |

Policy changes always `INSERT` a new row. Historical rows are immutable.

### 2.2 `preview_promotion_decisions`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `request_id` | INTEGER NOT NULL FK → requests.id | |
| `decision_type` | VARCHAR(32) NOT NULL | `promote`, `rollback`, `reject`, `request` |
| `decision_status` | VARCHAR(32) NOT NULL | `recorded`, `rejected`, `approved`, `applied`, `conflict` |
| `candidate_revision_id` | INTEGER NULL FK → candidate_revisions.id | |
| `effective_tier_summary_id` | INTEGER NULL FK → candidate_effective_tier_summaries.id | |
| `phase4_validation_summary_id` | INTEGER NULL FK → candidate_validation_summaries.id | |
| `phase5_visual_summary_id` | INTEGER NULL FK → candidate_visual_summaries.id | |
| `lineage_sha256` | CHAR(64) NOT NULL | |
| `candidate_manifest_sha256` | CHAR(64) NULL | |
| `actor_id` | VARCHAR(128) NOT NULL | |
| `actor_role` | VARCHAR(64) NOT NULL | |
| `reason` | TEXT NOT NULL | |
| `ticket_ref` | VARCHAR(256) NULL | |
| `policy_revision` | VARCHAR(64) NOT NULL | |
| `eligibility_sha256` | CHAR(64) NOT NULL | |
| `idempotency_key` | VARCHAR(128) NULL | UNIQUE per request when set |
| `requested_at` | TIMESTAMPTZ/TEXT NOT NULL | |
| `rejection_reason` | TEXT NULL | |
| `previous_pointer_version` | INTEGER NULL | |
| `resulting_pointer_version` | INTEGER NULL | |
| `decision_sha256` | CHAR(64) NOT NULL UNIQUE | Canonical payload hash |

Phase 7A creates the table and repository insert helpers used only by tests /
internal fixture writers. **No operational HTTP API creates successful
`applied` promotions.**

### 2.3 `preview_serving_pointer_versions`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `request_id` | INTEGER NOT NULL FK → requests.id | |
| `pointer_version` | INTEGER NOT NULL | Monotonic per request, start at 1 |
| `target_kind` | VARCHAR(16) NOT NULL | `legacy_v1` \| `v2_candidate` |
| `candidate_revision_id` | INTEGER NULL FK | Required when `v2_candidate` |
| `legacy_preview_relpath` | VARCHAR(512) NULL | Required when `legacy_v1` |
| `effective_tier` | SMALLINT NULL | 1–3 when v2 |
| `effective_summary_id` | INTEGER NULL | |
| `summary_sha256` | CHAR(64) NULL | |
| `candidate_manifest_sha256` | CHAR(64) NULL | |
| `previous_pointer_version` | INTEGER NULL | |
| `pointer_action` | VARCHAR(32) NOT NULL | `initialize`, `promote`, `rollback` |
| `decision_id` | INTEGER NULL FK → preview_promotion_decisions.id | |
| `actor_id` | VARCHAR(128) NOT NULL | |
| `policy_revision` | VARCHAR(64) NOT NULL | |
| `created_at` | TIMESTAMPTZ/TEXT NOT NULL | |
| `is_current` | BOOLEAN NOT NULL | Exactly one true per request |
| `pointer_sha256` | CHAR(64) NOT NULL UNIQUE | |

Constraints:

- `UNIQUE (request_id, pointer_version)`
- `CHECK` target_kind/path consistency
- Current-pointer enforcement — see §3

### 2.4 `preview_rollout_audit_events`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `request_id` | INTEGER NULL FK | Nullable for global policy events |
| `event_type` | VARCHAR(64) NOT NULL | See §13 taxonomy |
| `actor_id` | VARCHAR(128) NOT NULL | Or `system:...` |
| `actor_role` | VARCHAR(64) NOT NULL | |
| `policy_revision` | VARCHAR(64) NULL | |
| `decision_id` | INTEGER NULL | |
| `pointer_version_before` | INTEGER NULL | |
| `pointer_version_after` | INTEGER NULL | |
| `lineage_sha256` | CHAR(64) NULL | |
| `reason` | TEXT NULL | |
| `ticket_ref` | VARCHAR(256) NULL | |
| `metadata_json` | TEXT NOT NULL | Extra typed payload |
| `metadata_sha256` | CHAR(64) NOT NULL | |
| `created_at` | TIMESTAMPTZ/TEXT NOT NULL | |
| `event_sha256` | CHAR(64) NOT NULL UNIQUE | |

### 2.5 `preview_shadow_evaluations`

Defined now; **no rows written by Phase 7A runtime code** (tests may insert
fixtures).

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `request_id` | INTEGER NOT NULL FK | |
| `served_target_kind` | VARCHAR(16) NOT NULL | `legacy_v1` \| `v2_candidate` \| `none` |
| `served_pointer_version` | INTEGER NULL | |
| `v2_candidate_revision_id` | INTEGER NULL | |
| `v2_effective_summary_id` | INTEGER NULL | |
| `comparison_policy_revision` | VARCHAR(64) NOT NULL | |
| `telemetry_json` | TEXT NOT NULL | |
| `telemetry_sha256` | CHAR(64) NOT NULL | |
| `result_status` | VARCHAR(32) NOT NULL | `pending`, `completed`, `failed` |
| `comparison_artifact_sha256` | CHAR(64) NULL | |
| `no_serving_mutation` | BOOLEAN NOT NULL DEFAULT TRUE | CHECK = TRUE |
| `created_at` | TIMESTAMPTZ/TEXT NOT NULL | |
| `evaluation_sha256` | CHAR(64) NOT NULL UNIQUE | |

### 2.6 Supporting tables (contracts only in 7A)

- `preview_live_canary_approvals` — see §8
- `preview_circuit_breaker_policies` / `preview_circuit_breaker_states` — see §11
  (state rows unused until 7D)

---

## 3. Serving-pointer concurrency

### Choice

**Optimistic concurrency with exclusive current-row enforcement.**

Human promotion/rollback (7C+) must not auto-retry. Callers reload the current
pointer and re-authorize.

### Transaction sequence (later write phases; schema + test harness now)

1. `BEGIN`
2. Acquire request-scoped serialization
   - Postgres: `SELECT … FOR UPDATE` on current pointer (or advisory lock)
   - SQLite: `BEGIN IMMEDIATE` + version verification
3. Assert `pointer_version == expected_previous`
4. Insert `preview_promotion_decisions` with status `requested` (pending)
5. Mark previous pointer `is_current=0` (never insert a second current row first)
6. Insert new pointer with `is_current=1`
7. Append decision status-event `applied` (do not mutate the decision row)
8. Insert audit event
9. `COMMIT`

On version conflict: rollback entire transaction; zero partial rows.
Phase 7A exposes this sequence only through `tests/rollout/harness.py`.

### SQLite mechanism

```sql
CREATE UNIQUE INDEX uq_serving_pointer_one_current
  ON preview_serving_pointer_versions(request_id)
  WHERE is_current = 1;

-- Writes use:
BEGIN IMMEDIATE;
-- validate expected version
UPDATE ... SET is_current = 0 WHERE request_id = ? AND is_current = 1;
INSERT ... is_current = 1 ...;
COMMIT;
```

`BEGIN IMMEDIATE` prevents concurrent writers. Unique partial index guarantees
at most one current row even if application bugs occur.

### Postgres mechanism

```sql
CREATE UNIQUE INDEX uq_serving_pointer_one_current
  ON preview_serving_pointer_versions(request_id)
  WHERE is_current IS TRUE;

-- In transaction:
SELECT ... FOR UPDATE;
-- version check
UPDATE ... SET is_current = FALSE WHERE id = <current_id>;
INSERT ... is_current = TRUE ...;
```

Isolation: `READ COMMITTED` minimum; writers take row locks via `FOR UPDATE`.

### Idempotency

- Optional `idempotency_key` UNIQUE on `(request_id, idempotency_key)` for
  decision inserts.
- Repeated human promote with the same key returns the prior decision without
  creating a second pointer when status is already `applied`.
- Different key + same candidate/tier → reject unless policy marks as
  idempotent no-op.

---

## 4. Read-only serving resolver

### API (library)

```text
resolve_serving_pointer(db, request_id) -> ServingPointerView
```

`ServingPointerView` fields:

- `request_id`
- `target_kind` (`legacy_v1` | `v2_candidate` | `unset`)
- `pointer_version` (nullable if unset)
- `candidate_revision_id` / `legacy_preview_relpath`
- `effective_tier`
- `summary_sha256`
- `candidate_manifest_sha256`
- `is_current`

### Phase 7A exposure

- Unit/integration tests
- Optional internal admin **GET** diagnostic endpoint
  `GET /api/v1/admin/rollout/requests/{id}/serving-pointer`
  (read-only; no effect on customer iframe)
- **Not** wired into `preview_apps.py` static serving

### Production invariance proof

With all Phase 7 flags default-off:

1. Capture current serve URL / dist bytes for a fixture request before Phase 7A
   code lands (characterization in tests).
2. After Phase 7A, same request serves the same `get_dist_dir(request_id)` path
   and bytes.
3. Resolver may return `unset` or an initialized diagnostic legacy pointer that
   is **not consulted** by production serve code.

---

## 5. `PromotionEligibilityResult`

Strict Pydantic extra-forbid schema:

| Field | Type |
|---|---|
| `schema_version` | literal |
| `request_id` | int |
| `candidate_revision_id` | int \| null |
| `effective_tier_summary_id` | int \| null |
| `highest_accepted_tier` | 0–3 |
| `phase4_status` | str |
| `phase5_status` | str |
| `lineage_ok` | bool |
| `manifest_ok` | bool |
| `policy_revision` | str |
| `master_enabled` | bool |
| `shadow_enabled` | bool |
| `promote_enabled` | bool |
| `allowlisted` | bool |
| `sticky_bucket` | int 0–99 |
| `percent_eligible` | bool |
| `circuit_breaker_state` | `closed` \| `open` \| `half_open` \| `disabled` |
| `actor_id` | str |
| `actor_role` | str |
| `actor_authorized` | bool |
| `eligible_for_shadow` | bool |
| `eligible_for_promote` | bool |
| `rejection_reasons` | tuple[str, ...] |
| `eligibility_sha256` | char64 |

### Fail when

- incomplete lineage / hash mismatch
- Phase 4 ≠ `candidate_runtime_validated`
- Phase 5 ≠ `candidate_visual_accepted` (for promote)
- requested tier > highest accepted
- outside allowlist and percent
- promote/master disabled
- breaker open (promote)
- actor unauthorized
- current pointer already same candidate+tier (unless idempotent no-op)

Deterministic: same inputs → same `eligibility_sha256`. May be persisted as
JSON artifact in tests; write phases (7C) must recompute fresh before commit.

---

## 6. Sticky percentage bucketing

### Algorithm

```text
salt = rollout_salt  # from current policy; default policy_revision
material = f"{salt}:{request_id}".encode("utf-8")
digest = SHA256(material)
bucket = int.from_bytes(digest[:8], "big") % 100   # 0..99 inclusive
eligible = bucket < rollout_percent                 # percent=0 → none; 100 → all
```

### Rules

- Do **not** use Python `hash()`.
- Allowlist bypasses bucket (still recorded).
- Increasing percent with the **same salt** preserves prior cohort:
  every request with `bucket < old_percent` still has `bucket < new_percent`.
- Changing salt reshuffles (explicit policy event).

### Test vectors (frozen)

| salt | request_id | first8 hex | bucket | percent | eligible |
|---|---:|---|---:|---:|---|
| `2026-07-25.1` | 1 | `f6cad4035b48872f` | 23 | 0 | false |
| `2026-07-25.1` | 1 | `f6cad4035b48872f` | 23 | 100 | true |
| `2026-07-25.1` | 42 | `4ceb7e209e8260a1` | 89 | 90 | true |
| `2026-07-25.1` | 42 | `4ceb7e209e8260a1` | 89 | 89 | false |
| `2026-07-25.1` | 100 | `54de3fb01b9a3816` | 74 | — | — |
| `2026-07-25.1` | 999 | `1d3ecfbd7f8c1c69` | 37 | — | — |
| `2026-07-25.1` | 23104 | `2d1c6c7da625a71e` | 66 | — | — |

Increasing percent with unchanged salt preserves prior cohort membership.
Changing salt may reshuffle. Python `hash()` / `PYTHONHASHSEED` has no effect.

---

## 7. RBAC matrix

| Role | Read policies/pointers/decisions/audits | Request promote (7C) | Approve promote/rollback (7C) | Change policy/allowlist/freeze | Run shadow (7B) |
|---|---|---|---|---|---|
| `rollout_viewer` | yes | no | no | no | no |
| `rollout_operator` | yes | yes | no | no | yes |
| `rollout_approver` | yes | no | yes | no | no |
| `rollout_admin` | yes | yes* | yes* | yes | yes |

\*Admin may request and approve only when
`V2_PHASE7_ALLOW_ADMIN_DUAL_ROLE=false` by default → **denied**; emergency
policy `true` + ticket required.

### Authority source

- Actor identity and roles come from trusted server auth context (session /
  admin JWT / service principal), **never** from client-supplied role strings.
- Service principals: `system:phase7-shadow`, `system:phase7-breaker` with
  least privilege.

### Separation of duties

- Production promote: `requester.actor_id != approver.actor_id` unless
  emergency dual-role policy + ticket.
- Emergency actions require non-empty `reason` and `ticket_ref`.

---

## 8. Live-canary approval schema (no execution)

Table `preview_live_canary_approvals`:

| Column | Type |
|---|---|
| `id` | PK |
| `approval_uuid` | UNIQUE |
| `request_id` | FK, exactly one request |
| `provider_model_allowlist_json` | TEXT |
| `max_calls` | INT |
| `max_output_tokens` | INT |
| `max_cost_usd` | NUMERIC |
| `max_wall_seconds` | INT |
| `expires_at` | TIMESTAMPTZ |
| `approver_id` | VARCHAR |
| `ticket_ref` | VARCHAR NOT NULL |
| `policy_revision` | VARCHAR |
| `status` | `approved` \| `consumed` \| `expired` \| `revoked` |
| `used_at` | NULL until consumed |
| `approval_sha256` | UNIQUE |

Rules: single-use; expire by time; Phase 7A never constructs OpenRouter/Ollama
clients.

---

## 9. Cache and identity

| Surface | Cache | Key | Invalidate on |
|---|---|---|---|
| Sticky bucket | pure function / memo optional | `(salt, request_id)` | salt/policy change |
| Eligibility | **no durable cache authorizing writes** | n/a | always recompute before write |
| Lineage verify | short process memo | revision+summary hashes | hash mismatch / new summary |
| Serving pointer resolve | optional TTL ≤ 5s | `(request_id, pointer_version)` | any pointer insert / current flip |
| Shadow artifacts | durable rows only | evaluation hash | never mutate |
| Dashboards | eventual | query params | standard |

Rules:

- Cached eligibility **cannot** authorize a later promotion.
- Policy change → new policy row; eligibility must use latest
  `configuration_sha256`.
- Audit rows are immutable source of truth, never a writable cache.

---

## 10. Migrations

### Creation order

1. `preview_rollout_policies`
2. `preview_live_canary_approvals`
3. `preview_circuit_breaker_policies`
4. `preview_circuit_breaker_states`
5. `preview_promotion_decisions`
6. `preview_serving_pointer_versions`
7. `preview_rollout_audit_events`
8. `preview_shadow_evaluations`

### Indexes / uniqueness

- partial unique current pointer (SQLite + Postgres)
- `(request_id, pointer_version)` unique
- `idempotency_key` unique when not null
- hash uniqueness columns listed above

### Append-only enforcement

- Repository base rejects `UPDATE`/`DELETE`
- Optional DB triggers (Postgres) raising on update/delete for audit tables

### Downgrade policy

- Downgrade **fails** if any `preview_serving_pointer_versions` row exists with
  `target_kind='v2_candidate'` and `is_current=1`
- Downgrade **fails** if any `decision_status='applied'` rows exist
- Otherwise drop Phase 7A tables in reverse order
- **Never** delete or rewrite Phase 0–6B history
- Do not silently delete serving history; fail instead

### Upgrade idempotency

Startup migration creates missing tables/indexes only; safe to re-run.

---

## 11. Circuit-breaker contract (schema only in 7A)

### Policy fields

| Field | Proposed default (for later approval) |
|---|---|
| `window_type` | sliding |
| `window_seconds` | 900 |
| `min_samples` | 20 |
| `promote_write_failure_rate` | 0.10 |
| `serving_health_failure_rate` | 0.05 |
| `consecutive_serving_health_failures` | 3 |
| `p95_serve_latency_ms` | 5000 |
| `cost_spike_multiplier` | 3.0 vs 24h baseline |
| `open_duration_seconds` | 600 |
| `half_open_max_probes` | 2 |
| `manual_override` | admin + ticket |

### Metric classes (not equal weight)

| Class | Counts toward auto-rollback (7D) | Notes |
|---|---|---|
| Promotion-write failure | yes (promote breaker) | |
| Serving-health failure | yes (rollback candidate) | |
| Generation failure | no (shadow/gen quality) | |
| Runtime-validation failure | no for serve rollback | blocks promote via eligibility |
| Visual rejection | no for serve rollback | blocks promote via eligibility |
| Operator rejection | no | human decision |

Phase 7A persists policy JSON on rollout policies; no open/close actions.

---

## 12. Serving-health contract (define only)

| Check | Sync before promote (7C) | Async after promote (7D) | Triggers rollback | Advisory |
|---|---|---|---|---|
| Pointer resolves | yes | yes | yes | |
| Manifest exists + hash | yes | yes | yes | |
| Dist exists | yes | yes | yes | |
| Entry `index.html` resolves | yes | yes | yes | |
| Health route HTTP 200 | optional | yes | yes if configured | |
| No severe console errors | | yes | configurable | |
| Primary journey smoke | | yes | configurable | |
| Latency below threshold | | yes | yes if over p95 policy | |
| Visual score drift | | | | yes |

Phase 7A only ships the typed contract + fixtures.

---

## 13. Operational event taxonomy

`shadow_started`, `shadow_completed`, `shadow_failed`,
`promotion_requested`, `promotion_rejected`, `promotion_approved`,
`pointer_changed`, `rollback_requested`, `rollback_completed`,
`breaker_opened`, `breaker_half_open`, `breaker_closed`,
`canary_approved`, `canary_started`, `canary_completed`, `canary_failed`,
`rollout_policy_changed`, `history_mutation_attempted`,
`eligibility_computed` (7A diagnostic), `pointer_resolved` (7A diagnostic).

Every event carries: request (nullable), actor/system, policy revision,
lineage, pointer before/after, reason, outcome, timestamp, metadata hash.

Phase 7A may emit only: `rollout_policy_changed`, `eligibility_computed`,
`pointer_resolved`, `history_mutation_attempted` (on forbidden update).

---

## 14. Exact file plan

### New files

```text
docs/architecture/PREVIEW_GENERATOR_V2_PHASE7A_CONTROL_PLANE.md  # this doc

backend/app/domain/schemas/rollout.py
backend/app/domain/models/rollout.py

backend/app/application/rollout/__init__.py
backend/app/application/rollout/policy.py
backend/app/application/rollout/targeting.py
backend/app/application/rollout/eligibility.py
backend/app/application/rollout/pointer.py
backend/app/application/rollout/audit.py
backend/app/application/rollout/authorization.py
backend/app/application/rollout/cache.py
backend/app/application/rollout/repository.py
backend/app/application/rollout/service.py
backend/app/application/rollout/health_contract.py
backend/app/application/rollout/breaker_contract.py
backend/app/application/rollout/canary_contract.py

backend/tests/rollout/__init__.py
backend/tests/rollout/helpers.py
backend/tests/rollout/test_phase7a_flags.py
backend/tests/rollout/test_phase7a_targeting.py
backend/tests/rollout/test_phase7a_eligibility.py
backend/tests/rollout/test_phase7a_pointer_concurrency.py
backend/tests/rollout/test_phase7a_persistence_append_only.py
backend/tests/rollout/test_phase7a_migration.py
backend/tests/rollout/test_phase7a_authorization.py
backend/tests/rollout/test_phase7a_resolver_invariance.py
backend/tests/rollout/test_phase7a_cache_invalidation.py
backend/tests/rollout/test_phase7a_contracts.py
```

### Existing files expected to change

```text
backend/.env.example                          # Phase 7A flags (all off)
backend/app/core/config.py                    # parse/validate flags
backend/app/domain/models/__init__.py         # export rollout models
backend/app/main.py                           # register models / optional admin GET
backend/app/infrastructure/db/migrations.py   # Phase 7A table migrations
backend/app/api/v1/routers/admin.py           # optional read-only diagnostic GET only
backend/ops/migrations/import_sqlite_to_postgres.py  # include new tables if required
```

### Explicitly unchanged in 7A

```text
backend/app/api/v1/routers/preview_apps.py    # production static serve path
backend/app/application/preview_app/workspace.py
Phase 6B / tier_orchestration serving semantics
```

---

## 15. Focused test plan

Must prove every bullet in the user Phase 7A test list, grouped as:

1. **Flags** — defaults; malformed percent/allowlist fail closed; flags never serve/call/write.
2. **Targeting** — sticky vectors; cohort preservation; allowlist precedence.
3. **Persistence** — append-only on all five primary tables; unique current pointer.
4. **Concurrency** — two writers → one winner; loser zero partial rows; no auto-retry.
5. **Resolver** — legacy/v2/unset views; production serve invariance with flags off.
6. **Eligibility** — all reject paths; deterministic hash; breaker-open reject;
   unauthorized actor reject.
7. **Auth** — roles from trusted context; SoD; emergency dual-role gated.
8. **Canary schema** — single-use + expiry (no provider).
9. **Cache** — policy/pointer invalidation rules.
10. **Migrations** — upgrade idempotent; downgrade fails with active v2 current
    pointer or applied decisions.
11. **Regressions** — Phase 0–6B suites green; `compileall`; zero provider calls;
    zero operational promote/pointer mutation APIs.

### Expected local runtime

- Focused Phase 7A suite: ~5–30 s (no Vite/Playwright).
- Full Phase 0–6B regression: unchanged from Phase 6B release gate (~15–20 min).
- Zero paid provider calls.

---

## 16. Phase 7A implementation gate

Implementation starts only after explicit approval of this document.

Still forbidden until later subphases are approved separately:

- 7B shadow execution
- 7C promotion/rollback writes
- 7D breaker actions / auto-rollback
- 7E dashboards/alerts automation
- 7F live canary + percent rollout
