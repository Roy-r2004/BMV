# Preview Generator v2 — Phase 7F Percentage Serving & Live Canary

**Status:** Detailed design awaiting implementation approval.
**Umbrella:** `PREVIEW_GENERATOR_V2_PHASE7_ROLLOUT_DESIGN.md`.
**Depends on:** Phase 7A–7E (`f1a9553` and predecessors) — control plane,
shadow, allowlist promotion, circuit breaker + auto-rollback, ops dashboards.
**Scope:** Phase 7F only — enable sticky-percentage customer serving for
already-promoted v2 pointers, and a single separately approved live-provider
canary lane with hard budgets.
**Forbidden in 7F first cut:** unpaid multi-request live canaries, silent
percent increases, dashboard percent sliders that bypass SoD, mutating
accepted candidate history, collapsing human REQUEST→APPROVE→APPLY, changing
flags-off legacy serving when Phase 7 master is off.

---

## 0. Goal and non-goals

### Goal

1. Serve customers from the current Phase 7C serving pointer when a request is
   **allowlisted** or falls inside a sticky **percent bucket**, still subject
   to the Phase 7D breaker and Phase 7C unhealthy-v2 fallback order.
2. Before any `V2_PHASE7_ROLLOUT_PERCENT > 0` is considered operationally
   meaningful for live regeneration, require exactly **one** allowlisted
   request to complete a separately approved **live canary** under hard
   budgets, with append-only evidence attached to canary approval history.

### Non-goals (deferred beyond 7F)

| Item | Deferred |
|---|---|
| Multi-request automatic live canaries | later |
| Customer-facing A/B UI beyond sticky percent | later |
| Multi-region fan-out | later |
| Automatic Tier 2/3 regeneration on canary failure | later |
| External notification sinks for canary (beyond 7E alerts) | later |

---

## 1. Hard constraints

1. **Flags-off unchanged.** When `V2_PHASE7_ROLLOUT_ENABLED` is false or
   config invalid, `get_dist_dir` remains the legacy path (Phase 7C Option A).
2. **Percent never bypasses promotion.** Percentage only selects whether the
   **already current** pointer (or allowlisted promote path eligibility) may
   be used for serving. It does not create pointers.
3. **Breaker still freezes human apply.** Open/half-open continue to block
   human promote/rollback apply (7D). Percent serving of an already-current
   healthy pointer may continue unless policy says otherwise (decision below).
4. **Live canary is not default shadow.** `regenerate_live` remains forbidden
   unless the dedicated canary flags + approval record exist.
5. **One live canary at a time** for the first cut; hard wall/cost/call budgets.
6. **Append-only history.** Canary approvals and status events are insert-only;
   pointer swaps still use the Phase 7C transaction only.
7. **`preview_apps.py` stays thin.** Serving changes remain inside
   `workspace.get_dist_dir` → `serving_resolve` (or a thin percent gate beside
   it). No providers on the customer hot path.
8. **No 7E evaluate wrapper pattern for canary apply.** Canary execution uses
   dedicated trusted admin/system APIs, not ops runbook mutation.

---

## 2. Relationship to prior phases

| Concern | Prior | 7F |
|---|---|---|
| Sticky bucket math | 7A `targeting.compute_sticky_bucket` | reuse unchanged |
| Allowlist promote/rollback | 7C | still required to create pointers |
| Serving resolve + fallback | 7C | add percent/allowlist gate before pointer serve |
| Breaker / auto-rollback | 7D | remains authoritative for freeze + auto-rb |
| Ops dashboards / alerts | 7E | display percent + canary cards; add 7F alert classes |
| Live providers | forbidden | allowed only inside approved canary lane |

---

## 3. Percentage serving model

### 3.1 Eligibility order (serving read path)

When Phase 7 master + promote/config gates allow pointer serving:

```text
1. If breaker policy requires freeze-serve on open → legacy / last-good path
   (approval decision: default = continue serving current pointer with 7C
   fallback; do not promote further)
2. Else if request_id ∈ allowlist → use current pointer resolution (7C)
3. Else if sticky bucket < V2_PHASE7_ROLLOUT_PERCENT → use current pointer
4. Else → legacy_get_dist_dir (v1 workspace), no pointer mutation
```

Notes:

- Percent eligibility without a current `v2_candidate` / rollback pointer
  must not invent a promotion; serve legacy.
- Allowlist remains exact IDs; percent must not imply allowlist membership.
- Salt = `V2_PHASE7_ROLLOUT_SALT` (fail closed if empty — already 7A).

### 3.2 What percent must not do

- Must not call providers
- Must not write pointers, decisions, or breaker state
- Must not run auto-rollback
- Must not expand beyond sticky bucket math already defined in 7A
- Must not treat `percent > 0` as permission to skip canary approval for
  **live regenerate** paths (see §4)

### 3.3 Proposed flags (defaults fail closed)

| Flag | Default | Role |
|---|---|---|
| `V2_PHASE7_PERCENT_SERVE_ENABLED` | `false` | Master gate for percent branch on serve path |
| `V2_PHASE7_ROLLOUT_PERCENT` | `0` | Existing; still 0–100 |
| `V2_PHASE7_PERCENT_REQUIRES_CANARY` | `true` | If true, percent>0 rejected unless a completed live canary approval exists for the policy revision |

Invalid percent / config → existing `V2_PHASE7_CONFIG_VALID=false` fail-closed.

---

## 4. Live canary model

### 4.1 Preconditions

All required:

1. `V2_PHASE7_ROLLOUT_ENABLED=true`
2. `V2_PHASE7_CONFIG_VALID=true`
3. New `V2_PHASE7_LIVE_CANARY_ENABLED=true` (default `false`)
4. Explicit append-only canary approval record in
   `requested → approved → executed|failed|aborted` status lineage
5. Target `request_id` is allowlisted
6. Actor is `rollout_admin` (or trusted system principal for execution only)
7. Hard budgets present: max calls, max wall seconds, max cost USD
8. Ticket reference + reason on request and approval
9. Breaker not `open`/`half_open` for canary **execution** (fail closed)
10. No concurrent canary execution globally (advisory lock / unique
    `is_active` claim)

### 4.2 Lifecycle (never collapsed)

```text
REQUEST  →  APPROVE  →  EXECUTE  →  (completed|failed|aborted)
```

Reuse Phase 7A canary tables where already defined
(`preview_live_canary_approvals` + status events). 7F fills the execute path
that 7A forbade.

### 4.3 Execute behavior

1. Re-read approval + expected budgets.
2. Run **one** bounded live regenerate for that request only (provider calls
   allowed here only).
3. Persist shadow-comparable telemetry + comparison artifact (reuse 7B
   compare where possible).
4. Append status `executed` / `failed` / `aborted` + audits.
5. **Do not** auto-promote. Promotion remains 7C SoD after human review of
   canary evidence.

### 4.4 Budgets (suggested defaults — tunable)

| Budget | Default |
|---|---|
| Max provider calls | 8 |
| Max wall seconds | 600 |
| Max cost USD | policy / env capped |
| Concurrent canaries | 1 |

Exceeding any budget aborts execution and records `failed` with reason
`budget_exceeded`.

### 4.5 What canary must not do

- Must not change serving pointers during execute
- Must not open percent globally by itself
- Must not run for non-allowlisted requests
- Must not retry unboundedly
- Must not be triggered from customer `preview_apps` / `get_dist_dir`

---

## 5. Serving hot-path design

Preferred approach (aligned with 7C Option A):

1. Keep `preview_apps.py` unchanged.
2. Extend `workspace.get_dist_dir` / `serving_resolve` with a **read-only**
   eligibility helper:
   - inputs: request_id, flags, salt, percent, allowlist, optional canary gate
   - outputs: `serve_pointer | serve_legacy` reason code
3. Eligibility helper must not open DB write transactions beyond existing
   bounded fallback audit (0.25s).
4. Percent miss → `_legacy_get_dist_dir` without reading candidate workspaces
   when no pointer serve is authorized.

---

## 6. APIs (proposed)

Trusted admin surfaces only; bodies extra-forbid; no client actor/roles.

| Method | Path | Role |
|---|---|---|
| GET | `/api/admin/rollout/canaries` | viewer+ |
| GET | `/api/admin/rollout/canaries/{id}` | viewer+ |
| POST | `/api/admin/rollout/requests/{id}/canaries` | admin |
| POST | `/api/admin/rollout/canaries/{id}/approvals` | admin (SoD: ≠ requester) |
| POST | `/api/admin/rollout/canaries/{id}/execute` | admin |
| GET | `/api/admin/rollout/targeting/{request_id}` | viewer+ (bucket diagnostic) |

Do **not** add:

- percent slider mutation without policy/ticket
- combined request+approve+execute
- customer-facing canary endpoints
- ops dashboard buttons that execute canaries without SoD

Percent itself remains an **env/config** control in first cut (not a POST
body), matching fail-closed ops practice from 7A–7E.

---

## 7. Alert classes (7E extension when approved)

| Alert class | Trigger |
|---|---|
| `live_canary_budget_overrun` | canary aborted/failed on budget |
| `live_canary_failed` | execute failed |
| `rollout_percent_enabled` | percent becomes >0 while canary gate satisfied |
| `rollout_percent_blocked_missing_canary` | percent>0 attempted/configured but canary incomplete |

No cohort-imbalance ML. Sticky diagnostics only.

---

## 8. Authorization / SoD

- Canary request + approve: distinct admins unless emergency dual-role flag +
  ticket (reuse 7C dual-role rules).
- Execute: admin; must not be the same actor as requester **or** approver
  unless dual-role emergency explicitly allowed.
- Targeting diagnostic: read-only for viewer+.

---

## 9. Migration

Likely mostly status/column additions on existing 7A canary tables + schema
meta `phase7f.1`. If execute artifacts need a new append-only table
(`preview_live_canary_executions`), add it with indexes and append-only
triggers. Downgrade fails when execute/percent operational history exists.

Preserve 7A–7E rows and hashes.

---

## 10. Required tests (when approved)

- flags off → legacy serve byte-identical
- percent=0 → no percent serve even if pointer current
- percent>0 without canary when `PERCENT_REQUIRES_CANARY` → fail closed / legacy
- sticky bucket deterministic vs 7A vectors
- allowlist still serves pointer at percent=0
- non-eligible percent → legacy, no pointer leak in logs beyond request id
- breaker open blocks canary execute
- canary SoD enforced
- canary budgets abort
- canary does not mutate pointers
- no evaluate wrapper / no apply shortcut from ops
- providers only on execute path
- `preview_apps.py` unchanged
- serving audit remains 0.25s bounded
- Phase 0–7E regressions green aside from known pre-existing failures

---

## 11. Approval decisions needed before implementation

1. **Serve while breaker open?** Recommend: continue serving current pointer
   with 7C fallback; block new promotes/canary execute.
2. **`PERCENT_REQUIRES_CANARY` default true?** Recommend: yes.
3. **Percent changes via env only vs admin API?** Recommend: env/config only
   for first cut.
4. **Canary dual-role emergency?** Recommend: reuse 7C flag + ticket.
5. **Attach canary evidence to later promote decision how?** Recommend:
   promote request body may reference `canary_approval_id` (optional) with
   server-side verification.

---

## 12. Implementation gate

Do **not** implement Phase 7F until this design is explicitly approved.

Do **not** enable `V2_PHASE7_ROLLOUT_PERCENT > 0` or live providers in
production without a completed canary approval for the active policy revision.

---

## 13. Known pre-existing failures (carry-forward)

Out of scope unless separately approved:

- `test_pottery_picks_craft_studio_pack`
- `test_enriched_industry_packs_carry_seed_items`
- `test_production_callsites_render_with_strict_undefined`

These fail identically on Phase 7C `cc6f5e8` and later Phase 7 commits.
