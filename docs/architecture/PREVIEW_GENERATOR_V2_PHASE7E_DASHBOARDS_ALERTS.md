# Preview Generator v2 — Phase 7E Operational Dashboards & Alerts

**Status:** Implemented (Phase 7E committed).
**Umbrella:** `PREVIEW_GENERATOR_V2_PHASE7_ROLLOUT_DESIGN.md`.
**Depends on:** Phase 7A–7D (`c7d41e2` and predecessors) — control plane,
shadow, allowlist promotion, circuit breaker + automatic rollback.
**Scope:** Phase 7E only — read-oriented operational visibility, alert
emission, and bounded runbook assist surfaces for Phase 7 rollout health.
**Forbidden in 7E:** percentage serving (7F), live canary provider runs (7F),
automatic promotion, silent pointer mutation from dashboards, unpaid provider
construction, deleting append-only history, changing flags-off legacy serving,
browser-based customer probes as a dashboard dependency.

---

## 0. Goal and non-goals

### Goal

Give trusted operators a single operational view of Phase 7 rollout health —
breaker state, promotion/rollback volume, shadow volume, serving-fallback
pressure, and error-budget burn — plus deterministic alerts when budgets trip,
**without** making the dashboard a write authority for serving pointers.

### Non-goals (deferred)

| Subphase | Deferred |
|---|---|
| 7F | Live canary + percentage serving |
| — | Multi-region fan-out, customer A/B UI, Tier regen on failure |
| — | ChatOps bots that apply promotions without SoD |
| — | Paid observability SaaS hard dependency (optional sink only) |

---

## 1. Hard constraints

1. **Dashboards are read-mostly.** Default APIs are GET aggregations over
   append-only tables already written by 7A–7D. No dashboard click may directly
   call `apply_pointer_swap_transaction`.
2. **Alerts never mutate pointers.** Alert emission appends audit/alert
   records only. Auto-rollback remains exclusively the Phase 7D breaker path.
3. **No provider / browser dependency.** Metrics and cards use DB samples,
   audits, pointer history, and filesystem health already defined in 7C/7D.
4. **Fail closed.** Invalid Phase 7 config or flags-off yields empty/disabled
   dashboard payloads and suppresses alert delivery (except a single
   `phase7_config_invalid` diagnostic when an admin explicitly queries).
5. **`preview_apps.py` unchanged.** Customer serving remains Option A via
   `workspace.get_dist_dir`; dashboards are admin-only.
6. **Reuse 7D metric samples.** Do not re-derive sliding windows solely from
   loosely structured audit JSON when `preview_breaker_metric_samples` already
   holds the classed outcomes.
7. **No percentage / canary UI as authority.** Cards may *display* that
   percent remains `0` and canary is unused; they must not offer controls that
   enable 7F behavior.

---

## 2. Relationship to Phase 7D

| Concern | 7D | 7E |
|---|---|---|
| Breaker evaluate / open / close | yes | read + optional “request evaluate” that calls existing 7D admin APIs |
| Auto-rollback | yes | display claims/results only |
| Metric samples | write path | aggregate/query for cards + alerts |
| Human promote/rollback | blocked while open/half-open | show freeze banner from live breaker state |
| Serving hot path | read-only + 0.25s audit | never imported |

---

## 3. Dashboard surfaces (first cut)

Admin-only, under `/api/admin/rollout/ops/...` (names illustrative).

### 3.1 Global overview card

- Current global breaker state + `state_id` + policy revision + age
- Flags snapshot: rollout / shadow / promote / breaker / auto-rollback /
  config valid / percent (must be 0) / allowlist size
- Counts in lookback window: promotions applied, rollbacks applied,
  auto-rollbacks applied/failed/skipped, shadow evaluations
- Serving-fallback audit count (7C) and `serving_health_failure` sample count

### 3.2 Error-budget / breaker card

From `preview_breaker_metric_samples` + last `BreakerEvaluationResult` shape:

- promotion-write failure rate vs threshold
- serving-health failure rate vs threshold
- consecutive serving-health failures
- optional p95 latency when policy enables it
- last trip reasons + metric snapshot sha
- open → half_open countdown (derived from `open_duration_seconds`)

### 3.3 Request drill-down (allowlisted only by default)

Per `request_id`:

- current serving pointer view (reuse 7A/7C GET)
- recent decisions + status lineage
- recent shadow evaluations
- auto-rollback claims for recent open events
- fallback audits

### 3.4 Comparison / shadow card

Reuse Phase 7B shadow list/detail; no regenerate-live controls in 7E.

### 3.5 Explicit non-cards (first cut)

- No percent slider
- No canary launch button
- No “force close breaker” (7D already has no emergency force-close)
- No apply-from-dashboard shortcut that collapses SoD

---

## 4. Alert model

### 4.1 Alert classes (approved first cut)

| Alert class | Trigger | Severity |
|---|---|---|
| `breaker_opened` | 7D audit `breaker_opened` / state transition to `open` | high |
| `breaker_half_open` | transition to `half_open` | medium |
| `breaker_closed` | recovery to `closed` | info |
| `promote_error_budget_burn` | promo failure rate ≥ threshold with min samples (even before open if evaluate ran) | high |
| `serving_health_budget_burn` | health failure rate or consecutive streak trip criteria | high |
| `promotion_write_failure_burst` | N write failures in short sub-window | high |
| `auto_rollback_failed` | claim status `failed` | high |
| `auto_rollback_skipped_unhealthy_no_predecessor` | skip reason `no_verified_predecessor` | medium |
| `history_mutation_denied` | append-only guard / trigger abort observed in ops logs (best-effort) | critical |
| `phase7_config_invalid` | `V2_PHASE7_CONFIG_VALID=false` while any Phase 7 flag requested on | high |

Deferred (need 7F): `live_canary_budget_overrun`, percent-drift alerts.

### 4.2 Delivery

First cut: **persist + poll**, not webhook fan-out.

1. Append-only table `preview_rollout_alert_events` (proposed):
   - alert_id, alert_class, severity, created_at
   - scope_key (`global:preview-generator-v2` or request id)
   - source_event_type / source_event_id / source_sha256
   - payload_json + payload_sha256
   - delivery_status: `recorded` | `acked` | `suppressed`
2. Admin GET list + POST ack (reuse admin alert ack patterns if present).
3. Optional later sink: structured log line / metrics exporter — never required
   for correctness.

### 4.3 Dedup / storm control

- Idempotency key = hash(alert_class, scope_key, source_event_id or
  open_state_id, policy_revision).
- Suppress duplicates while an unacked identical key exists.
- Max alerts persisted per evaluate tick (e.g. 20).

### 4.4 What alerts must not do

- Must not open/close the breaker themselves (7D owns transitions).
- Must not run auto-rollback (7D owns that on open transition).
- Must not page external systems in first cut unless an explicit optional
  flag is approved later.

---

## 5. Runbook assist (bounded, non-authoritative)

Optional Phase 7E “runbook” GET that returns **recommended next actions** as
text + deep links to existing admin APIs:

- If breaker `open`: link to GET breaker state/history; remind human apply is
  frozen; show auto-rollback claim summary for the open event.
- If `half_open`: remind synthetic probes are filesystem-only; link to
  evaluate.
- If config invalid: show which flag/config field failed closed.

The runbook payload is advisory JSON. Clients must still call the normal
7C/7D endpoints with SoD for any mutation.

---

## 6. APIs (proposed)

Trusted admin/system surfaces only; bodies extra-forbid; no client-supplied
actor/roles/eligibility/pointer authority.

| Method | Path | Role |
|---|---|---|
| GET | `/api/admin/rollout/ops/overview` | viewer+ |
| GET | `/api/admin/rollout/ops/breaker-budget` | viewer+ |
| GET | `/api/admin/rollout/ops/requests/{id}` | viewer+ |
| GET | `/api/admin/rollout/ops/alerts` | viewer+ |
| POST | `/api/admin/rollout/ops/alerts/{id}/ack` | operator+ or admin |
| GET | `/api/admin/rollout/ops/runbook` | viewer+ |

Evaluate/open/close/disable remain the Phase 7D routes — 7E does not fork them.

---

## 7. Flags (proposed)

Defaults fail closed / off:

| Flag | Default | Purpose |
|---|---|---|
| `V2_PHASE7_OPS_DASHBOARD_ENABLED` | `false` | Master for ops GET aggregations |
| `V2_PHASE7_OPS_ALERTS_ENABLED` | `false` | Persist alert events from evaluate/audit hooks |
| `V2_PHASE7_OPS_ALERT_LOOKBACK_SECONDS` | `3600` | Aggregation window for cards |

Invalid values → `V2_PHASE7_CONFIG_VALID=false` semantics already used by 7A–7D
(or a dedicated ops-invalid bit that disables only 7E writes). Prefer reusing
the existing fail-closed master where practical.

---

## 8. Data sources (no new serving path)

| Card / alert | Source |
|---|---|
| Breaker state/history | `preview_circuit_breaker_states` / policies |
| Rates / p95 / streaks | `preview_breaker_metric_samples` |
| Auto-rollback outcomes | `preview_breaker_auto_rollback_claims` + audits |
| Promotions / rollbacks | decisions + status events + pointer versions |
| Shadow | `preview_shadow_evaluations` |
| Fallbacks | `preview_rollout_audit_events` (`serving_fallback`) |

Aggregation is deterministic given the same rows + window. Persist
`overview_sha256` / `budget_sha256` on responses for support diffs.

---

## 9. Authorization

Reuse Phase 7 roles:

- `rollout_viewer` / operator / approver / admin: read ops + alerts
- ack alerts: operator or admin (decide at approval; recommend admin-only if
  ack is treated as an operational control)
- no new role that can apply promotions from the dashboard

---

## 10. Migration (when approved)

Additive only:

- `preview_rollout_alert_events` (+ indexes on class/created_at, dedup key)
- schema meta `phase7e.1`
- append-only protections
- downgrade fails if alert rows or ack history exist

Preserve 7A–7D rows and hashes.

---

## 11. Required tests (when approved)

- flags off → empty/disabled ops payloads; no alert inserts
- invalid config fails closed
- overview hashes stable for fixed fixtures
- budget card matches 7D snapshot math for the same samples
- alert dedup / storm control
- ack is append-only status transition (or ack table), never deletes
- dashboard modules never import `apply_pointer_swap_transaction`
- serving adapter / `preview_apps.py` unchanged
- no providers, browsers, percent serving, canary consume
- Phase 0–7D regressions remain green (excluding known pre-existing failures)

---

## 12. Approval decisions needed before implementation

1. **Alert persistence vs log-only** — recommend persist + ack table.
2. **Who may ack** — recommend admin-only first cut.
3. **Whether ops evaluate shortcut exists** — recommend deep-link to existing
   `POST /breaker/evaluate` only (no new write wrapper).
4. **Allowlist-only drill-down vs any request_id** — recommend allowlist-only
   by default when promote plane is on.
5. **External notification sinks** — recommend none in first cut.

---

## 13. Implementation gate

Do **not** implement Phase 7E until this design is explicitly approved.

Do **not** begin Phase 7F from this document.

---

## 14. Known pre-existing failures (carry-forward)

These fail identically on Phase 7C `cc6f5e8` and Phase 7D `c7d41e2` and are
out of scope for 7E unless separately approved:

- `test_pottery_picks_craft_studio_pack`
- `test_enriched_industry_packs_carry_seed_items`
- `test_production_callsites_render_with_strict_undefined`
