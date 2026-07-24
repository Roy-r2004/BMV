# Preview Generator v2 — Phase 7C Allowlist-Only Manual Promotion & Rollback

**Status:** Implemented (uncommitted) — Option A serving adapter; admin-only
apply; unhealthy v2 → verified `legacy_v1` pointer → legacy workspace.
**Umbrella:** `PREVIEW_GENERATOR_V2_PHASE7_ROLLOUT_DESIGN.md`.
**Depends on:** Phase 7A control plane + Phase 7B shadow execution (committed).
**Scope:** Phase 7C only — allowlist-only, two-step human promotion and
rollback with atomic serving-pointer versioning.
**Forbidden in 7C:** percentage rollout, automatic promotion, circuit-breaker
actions, automatic rollback, live canary execution, background promotion
queues, dashboard automation, paid provider construction.

---

## 0. Goal and non-goals

### Goal

Allow an explicitly authorized operator/approver workflow to promote **one**
accepted v2 candidate for **one allowlisted** request, with atomic pointer
versioning and deterministic rollback — without changing default customer
serving when flags are off.

### Non-goals (deferred)

| Subphase | Deferred |
|---|---|
| 7D | Circuit-breaker actions and automatic rollback |
| 7E | Dashboards / alerts automation |
| 7F | Live canary + percentage serving |

---

## 1. Promotion and rollback lifecycle

### 1.1 Promotion (three distinct steps — never collapsed)

```text
REQUEST  →  APPROVE  →  APPLY
```

1. **Request** (`rollout_operator` or `rollout_admin` as requester)
   - Recompute promotion eligibility from current state (advisory → gate).
   - Insert append-only `preview_promotion_decisions` with
     `decision_type=promote`, `decision_status=requested`.
   - Append status-event `requested` + audit `promotion_requested`.
   - **No pointer mutation.**

2. **Approve** (different trusted `rollout_approver` or gated admin)
   - Recompute eligibility; verify SoD; verify decision still pending.
   - Insert status-event `approved` (do not mutate decision row).
   - Optional: insert linked approval-version row if preferred for clarity.
   - Audit `promotion_approved`.
   - **No pointer mutation.**

3. **Apply** (trusted apply actor with `apply_promotion` permission)
   - Recompute eligibility and re-verify approval + expected pointer version.
   - Run health prechecks (§7).
   - Execute pointer-swap transaction (§5).
   - Append status-event `applied` + audit `pointer_changed`.
   - Return resulting pointer view.

Rejection / cancel paths:

- Requester or approver may insert `rejected` / `cancelled` status events.
- Apply refuses decisions that are not approved, stale, or ineligible.

### 1.2 Rollback (three distinct steps)

```text
ROLLBACK_REQUEST  →  ROLLBACK_APPROVE  →  ROLLBACK_APPLY
```

Symmetric to promotion:

- Target defaults to immediately previous accepted pointer version.
- Explicit earlier accepted pointer version allowed when authorized.
- Never deletes pointer history; always inserts a new current pointer with
  `pointer_action=rollback`.

### 1.3 Invariants

- No single HTTP call both requests and applies a production promotion.
- `rollout_percent` must be `0` for apply authorization in 7C.
- Allowlist match is **required** (exact request ID).
- Percent targeting **cannot** authorize promotion in 7C.
- Conflict / failure leaves zero partial pointer/decision/audit rows.

---

## 2. RBAC and separation-of-duties matrix

| Capability | viewer | operator | approver | admin |
|---|---|---|---|---|
| Read decisions / pointer history | yes | yes | yes | yes |
| Compute promotion eligibility | no | yes | review only | yes |
| Create promotion/rollback **request** | no | yes | no | yes* |
| **Approve** promotion/rollback | no | no | yes | yes* |
| **Apply** promotion/rollback | no | no† | no† | yes‡ |
| Change rollout policy / allowlist | no | no | no | yes |
| Promote via percent | **never in 7C** | | | |
| Trip breakers / auto-rollback | **never in 7C** | | | |

\* Admin may request **or** approve, but SoD still forbids the same
`actor_id` doing both unless
`V2_PHASE7_ALLOW_ADMIN_DUAL_ROLE=true` **and** non-empty `ticket_ref`.
† Optional later policy may grant operator apply under dual-control; first cut
keeps apply on `rollout_admin` (or a dedicated `rollout_applier` service
principal).
‡ Apply actor may equal requester or approver only under emergency dual-role
policy + ticket; preferred: distinct apply principal.

Roles come **only** from trusted server auth. Client JSON must not supply
`actor_id`, roles, eligibility hashes, pointer versions, or provider settings.

SoD rules (reuse Phase 7A `evaluate_separation_of_duties`):

- `requester.actor_id != approver.actor_id` by default.
- Emergency same-actor requires dual-role flag + ticket + reason.
- Apply step records `apply_actor_id` separately in audit metadata.

---

## 3. Decision / status schemas

### 3.1 Decision row (immutable after insert)

Reuse `preview_promotion_decisions` with Phase 7C production statuses expanded
via **status events**, not in-place mutation:

| Initial `decision_status` on insert | Meaning |
|---|---|
| `requested` | Open request awaiting approval |
| `rejected` | Terminal reject at request time |
| `cancelled` | Terminal cancel |

Apply / approve outcomes live in
`preview_promotion_decision_status_events`:

| Event `status` | When |
|---|---|
| `requested` | With request insert |
| `approved` | After independent approval |
| `rejected` / `cancelled` | Terminal non-apply |
| `applied` | After successful pointer swap |

Effective decision state = latest status-event for the decision ID.

### 3.2 Proposed additive columns (7C migration)

On `preview_promotion_decisions` (nullable for 7A/7B history):

- `requester_actor_id` / `approver_actor_id` / `apply_actor_id`
  (or keep actor on events only — prefer events for append-only purity)
- `idempotency_key` (already present)
- `expected_pointer_version` (integer, required for apply)
- `target_pointer_version` (for rollback: which historical version to restore)
- `approval_ticket_ref` / `apply_ticket_ref` in metadata/events

### 3.3 Eligibility result for apply (strict)

`PromotionApplyEligibilityResult` (new) extends Phase 7A eligibility with:

- allowlist **required** match (not percent)
- `rollout_percent_must_be_zero` check
- decision ID + latest status must be `approved`
- expected pointer version matches current
- health precheck summary hashes
- SoD satisfied across requester/approver/(apply)
- `advisory_only=false` **only** as a gate for the apply transaction in-process
  — still **never** persisted as a reusable write token; recompute every call

Cached promotion eligibility **cannot** authorize apply.

---

## 4. Exact API contracts

Base prefix: `/api/admin/rollout`

### Write (trusted roles; no client roles)

| Method | Path | Body (extra forbid) | Role |
|---|---|---|---|
| POST | `/requests/{id}/promotions` | `candidate_revision_id`, `effective_tier_summary_id`, `expected_pointer_version`, `reason`, `ticket_ref`, `idempotency_key?` | operator/admin |
| POST | `/promotions/{decision_id}/approvals` | `reason`, `ticket_ref?`, `idempotency_key?` | approver/admin* |
| POST | `/promotions/{decision_id}/apply` | `expected_pointer_version`, `reason`, `ticket_ref?`, `idempotency_key?` | apply-capable |
| POST | `/requests/{id}/rollbacks` | `target_pointer_version?` (default previous), `expected_pointer_version`, `reason`, `ticket_ref`, `idempotency_key?` | operator/admin |
| POST | `/rollbacks/{decision_id}/approvals` | same shape as promotion approval | approver/admin* |
| POST | `/rollbacks/{decision_id}/apply` | same shape as promotion apply | apply-capable |

Banned body fields: `actor_id`, `roles`, `eligibility_*`, `serving_target`,
`provider`, `model`, `authorization_scope`.

### Read

| Method | Path |
|---|---|
| GET | `/requests/{id}/promotions` |
| GET | `/promotions/{decision_id}` |
| GET | `/requests/{id}/serving-pointer` (existing 7A) |
| GET | `/requests/{id}/serving-pointer/history` |

No POST canary / breaker / percent-serving endpoints in 7C.

---

## 5. Pointer transaction behavior

Approved future-safe sequence (lifted from Phase 7A harness into production
apply service under flags):

1. `BEGIN`
2. Acquire request-scoped serialization
   - Postgres: `SELECT … FOR UPDATE` on current pointer (advisory lock if none)
   - SQLite: `BEGIN IMMEDIATE` + version verification
3. Verify `current.pointer_version == expected_pointer_version`
4. Verify decision latest status is `approved` and inputs still match
5. Run health prechecks (fail → rollback)
6. Insert decision status-event pending-apply marker **or** proceed directly
7. Mark previous pointer `is_current=false` (never insert second current first)
8. Insert new pointer `is_current=true` (`promote` or `rollback`)
9. Append status-event `applied`
10. Append audit `pointer_changed` / `rollback_completed`
11. `COMMIT`

Partial unique index remains:
`UNIQUE(request_id) WHERE is_current = true`.

On any failure: full rollback; previous pointer remains current; no orphan
`applied` event without pointer; no orphan current pointer without applied
event (same transaction).

---

## 6. Serving resolver integration design

### 6.1 Narrow integration

Do **not** rewrite `preview_apps.py` broadly.

Proposed approach (choose one at approval; recommendation A):

**A. Thin adapter inside `get_dist_dir` / workspace resolution (preferred)**
- When `V2_PHASE7_ROLLOUT_ENABLED && V2_PHASE7_PROMOTE_ENABLED` and a current
  `v2_candidate` pointer exists for `request_id`, resolve dist from the
  candidate revision workspace/manifest.
- Otherwise call existing legacy path unchanged.

**B. Wrapper only in `serve_preview_app`**
- Same flag gate; call `resolve_serving_pointer` then map to filesystem.
- Slightly more surface on the router; still byte-identical when flags off.

### 6.2 Flag gate

```text
if not (ROLLOUT_ENABLED and PROMOTE_ENABLED and CONFIG_VALID):
    return legacy_get_dist_dir(request_id)  # exact current behavior
```

`V2_PHASE7_ROLLOUT_PERCENT` remains `0` and is **not** consulted for serving
in 7C (allowlist promotion only affects the pointer record; serving uses the
current pointer when promote flag is on).

### 6.3 Characterization

Flags-off boundary test must prove:

- identical `get_dist_dir` / file bytes / response headers for fixture requests
- no import of apply executors on the hot path beyond a cheap flag check

---

## 7. Fallback policy

If resolver integration is enabled and any of the following occur:

- pointer row missing / corrupt
- candidate revision missing
- manifest hash mismatch
- dist or entry file missing

then:

1. Emit audit `serving_fallback` (new 7C event).
2. Serve **legacy `get_dist_dir(request_id)`** (pre-Phase-7 path) **or** the
   last known-good `legacy_v1` / prior pointer if one exists and verifies.
3. **Do not** auto-rollback pointers in 7C (that is 7D).
4. **Do not** throw 5xx to customers when legacy path can still serve.

Preferred default: **legacy workspace fallback** when v2 pointer unhealthy;
operator must explicitly rollback to repair the pointer.

---

## 8. Health prechecks (before apply)

Synchronous, no browser / critic rerun:

| Check | Required |
|---|---|
| Current pointer version matches expected | yes |
| Decision approved and not already applied | yes |
| Candidate revision exists | yes |
| Candidate manifest hash matches decision | yes |
| Dist directory exists for target | yes |
| Entry `index.html` exists | yes |
| Phase 4 summary status = `candidate_runtime_validated` | yes |
| Phase 5 summary status = `candidate_visual_accepted` | yes |
| Effective-tier summary matches decision / accepted tier | yes |
| Request still allowlisted; percent == 0; promote enabled | yes |
| Breaker state not `open` (advisory read of contract/state) | yes |

Failure → refuse apply; no pointer change.

---

## 9. Idempotency rules

| Operation | Idempotency key scope | Duplicate identical | Conflicting reuse |
|---|---|---|---|
| Promotion request | `(request_id, key)` | Return existing decision | 409 |
| Promotion approval | `(decision_id, key)` | Return existing approval event | 409 |
| Promotion apply | `(decision_id, key)` | Return existing applied pointer/decision | 409 |
| Rollback request / approval / apply | same pattern | same | 409 |

Rules:

- Keys optional but recommended for all write POSTs.
- Apply idempotency must not create a second current pointer.
- If apply already succeeded, return the applied pointer view.
- No automatic retry loops.

---

## 10. Migration changes

Additive, transactional SQLite + Postgres:

1. Ensure Phase 7A/7B tables present.
2. Add nullable columns listed in §3.2 if not already present.
3. Indexes:
   - `(request_id, decision_type, requested_at)`
   - unique partial on open requested decisions if needed
   - keep `uq_serving_pointer_one_current`
4. Schema meta `phase7c.1`.
5. Downgrade fails if any `applied` status-event or current `v2_candidate`
   pointer exists.
6. Never rewrite historical 7A/7B rows.
7. Append-only triggers remain active.

---

## 11. Exact files likely to change

```text
docs/architecture/PREVIEW_GENERATOR_V2_PHASE7C_ALLOWLIST_PROMOTION.md

backend/app/domain/schemas/promotion.py          # new apply/request contracts
backend/app/application/rollout/promotion_service.py
backend/app/application/rollout/rollback_service.py
backend/app/application/rollout/apply_transaction.py
backend/app/application/rollout/health_precheck.py
backend/app/application/rollout/repository.py     # lift production apply (gated)
backend/app/application/rollout/authorization.py  # apply permissions
backend/app/application/preview_app/workspace.py  # narrow flag-gated resolve (A)
# OR backend/app/api/v1/routers/preview_apps.py   # only if option B approved
backend/app/api/v1/routers/rollout_diagnostics.py # or new rollout_promotion.py
backend/app/infrastructure/db/phase7c_migrations.py
backend/app/core/config.py / .env.example
backend/tests/rollout/test_phase7c_*.py
```

Explicitly unchanged unless option B is approved:

- broad production serve semantics when flags are off
- Phase 7B shadow executor behavior
- breaker action modules (still contracts only)

---

## 12. Focused test plan

1. Allowlist-only promotion succeeds.
2. Percent > 0 or non-allowlisted request cannot authorize promotion.
3. Two-step SoD enforced; same actor denied without emergency policy.
4. Unauthorized roles rejected on request/approve/apply.
5. Stale `expected_pointer_version` → conflict, zero partial rows.
6. Exactly one current pointer after apply.
7. Failure mid-transaction leaves prior pointer current.
8. Idempotent request / approval / apply.
9. Conflicting idempotency keys fail.
10. Successful v1 → v2 promotion.
11. Successful v2 → higher-tier v2 promotion.
12. Rollback to previous pointer.
13. Rollback to explicit earlier pointer.
14. Invalid target rejection.
15. Immutable audit / status-event history; SQL UPDATE/DELETE still abort.
16. Flags off → exact serving characterization unchanged.
17. Resolver integration only when promote flag on.
18. Fallback to legacy on unhealthy v2 pointer.
19. Zero live provider construction.
20. Zero breaker actions / no percent serving / no canary consume.
21. Phase 0–7B regressions green.

---

## 13. Operational rollback runbook

1. Confirm customer impact and request ID.
2. `GET /serving-pointer` + history; note current and target versions.
3. Operator opens rollback request with reason + ticket; default target =
   previous version (or explicit earlier).
4. Independent approver approves.
5. Apply actor runs rollback apply with `expected_pointer_version`.
6. Verify pointer current = target; spot-check preview URL.
7. If apply conflicts, reload pointer and retry with fresh expected version
   (no auto-retry).
8. If filesystem unhealthy after rollback, fall back to legacy path remains
   available; open incident — do not delete history.
9. Document ticket on audit trail; schedule follow-up promote only after
   root-cause fix.

---

## 14. Expected runtime

| Path | Expected local runtime |
|---|---|
| Focused Phase 7C suite | ~10–60 s (no Vite/Playwright/providers) |
| Apply health prechecks | milliseconds–low seconds (filesystem + DB) |
| Full Phase 0–7B regression | ~15–20 min (unchanged gate) |
| Paid provider calls | **zero** |

---

## Implementation gate

Phase 7C implementation is complete and left **uncommitted for review**.

Still forbidden until later approval:

- 7D breaker actions / automatic rollback
- 7E dashboards/alerts automation
- 7F live canary + percentage rollout

### Approved decisions (implemented)

1. Serving integration: **Option A** (`workspace.get_dist_dir` adapter)
2. Apply authority: **admin-only** (`rollout_admin`; no `rollout_applier`)
3. Unhealthy v2 fallback: verified `legacy_v1` pointer → legacy workspace →
   existing not-found
