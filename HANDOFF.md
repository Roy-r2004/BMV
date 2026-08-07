# Session handoff — the empty-tuple trio lands evidence-corrected, and the key runs dry mid-ship (2026-08-07, session 23)

Successor to session 22's handoff (below in this file). Process notes, not product docs.

---

## Session 23, in one page

**The flagship trio landed — reshaped twice by what 143's artifact actually says — R6
closed both halves, the R3 audit produced its table, and the one funded run SHIPPED
rev-1 under the new prompt while the SHARED KEY EXHAUSTED mid-run.** Suite
**2,026 / 1 / 0** (+14). Two sweeps: **11 + 6 mutations / 0 survivors, both first
pass**. Evidence: `docs/evidence/session23/`.

### THE TALLY (ships beside accepts, always)

| | |
|---|---|
| **Ships / attempts** | **1 / 1** (**145 ✓ ready ~568 s, gate PASSED**, 29.4 s past soft deadline, inside the cap) |
| **Spec accepts / rejects** | **1 accept** (145 rev-1, coverage 98, prompt rev **2026-08-07.3** — authoring deterministically valid, zero schema-parse issues, one semantic-coverage repair). **New rev-1 count: 1** |
| **Transport-dead runs** | **0** — slot_fill's one 408 was classified and the cross-provider rung correctly runway-gated (R1's designed fail-closed, read live); the tail's $0/0 ms transport cluster was the KEY exhausting, not weather |
| Spend | **BMV $0.245** (145, 29 calls) + ~$0.02 probes; brackets 375.332 → 377.884 (pre-launch) → **380.148 of 380 (post-run)**. **KEY EXHAUSTED — the shared key's other project burned ~$4.5 during this one session; no funded runs until topped up** |

### The trio (`772ac82`) — and the three evidence corrections that reshaped it

1. **(b) moved to `app_spec_schema_repair.j2`** — the minItems/too_short class is a
   pydantic parse failure owned exclusively by the schema-repair rung; once schema
   attempts are spent the loop goes straight to `_fallback`. `app_spec_repair.j2`
   NEVER sees the class — the handoff's named target would have been dead code (the
   exact R2 catalogue-contract lesson). Landed as rule **7a**: the constructive
   stateless-page fix (author the default state, `initial:true`, add to `states`,
   reference it; never resend unchanged; never placeholder ids).
2. **143's revs 1-3 were never authored that way** — the authored spec had 6 pages and
   ONE error (`page_initial_state_count` on PAGE-AI-FEATURES); the `ai_appspec_repair`
   call REPLACED it with a 503-byte fragment (a single acceptance-test object).
   `app_spec_repair.j2` rule 9 now teaches the mined collapse shape: a sub-object or
   emptied `pages`/`states` is a collapse, not a repair; unfaulted objects survive
   verbatim. Authoring got rule **9a** (no stateless page, real `PAGE-*`/`STATE-*`
   ids, `{"id": "Page1", "state_ids": []}` as the mined Invalid exemplar).
3. **Rev 5 made NO new AI call** — identical `schema_diagnostics` including
   `completed_at` and `raw_response_sha256`; it was the terminal re-persistence of
   rev 4. So the early stop saves nothing on 143's exact trace; its payoff is run
   138's shape (a PAID identical repeat on the general path, 3 attempts live). Landed
   as the **identical-error-set early stop**: signature = sorted (code, path,
   message) triples, armed only at the two AI repair dispatches, compared exactly
   once at the next validation; identical ⇒ `_fallback("repair_reproduced_parent_errors")`.
   Any change to the set is progress. Coverage re-entry deliberately excluded.
   6 tests, 11 mutations / 0 survivors first pass.
   **Fixture lesson worth keeping: an empty `pages[0].state_ids` BESIDE a populated
   `states` array is deterministically reconciled from the siblings and never reaches
   the AI rung — 143 failed precisely because its states existed nowhere.**

### R6 — DONE both halves (`f9fc60c`)

Census: analyze (2/2 rows), blueprint (24/24), demo (7/7) were the ONLY stages whose
every row carried the `record_usage` fallback (`writer IS NULL AND attempt=1 AND
stage=purpose`) — no `ai_call` scope existed at their ask sites. Now scoped:
`reference_url_analysis`, `screenshot_analysis`, `mvp_blueprint`,
`preview_extraction`, `visual_demo`. And the refund: `_StageLimitedAIProvider` gives
back the budget unit for an ask the provider never answered (143's error-cut
authoring attempt had spent `APPSPEC_MAX_CALLS` for nothing) — answered asks spend
for good, floor at zero, both the deadline tally and the instance count refunded.
7 tests, 6 mutations / 0 survivors first pass.

### R3 — the audit table is in the roadmap (offline, NO code)

Architect JSON and design_manifest have **no decorative strictness to relax** (0
`unparseable` / 0 `rejected` rows ever; every stored failure was provider transport/
truncation — design_manifest's lever, if any, is its 1,500-token cap). The class
lives in slot_fill's catalogue contract, which already tolerates `invalid prop:` /
`invalid variant:`. **The actionable finding: `detail inquire CTA (#inquire)`
(validate.py:238) fired ALONE 4 times — ArtworkDetailPage and RoomDetailPage each
discarded to scaffold at attempt 2/2 for one CTA href whose correct value is a
compile-time constant.** Second candidate: the image-pool pair (validate.py:251,256).
Both need the owner's ruling before any coercion lands (R3 boundary).

### Run 145 — the ship, the live R1 read, and the honest confound

Osteria (143's payload byte-verbatim incl. reference_url). Weather CLEAR (2× stop,
6-7 s). Spec: authoring 36.6 s healthy → coverage review → one semantic-coverage
repair → accepted **rev-1 coverage 98**, `prompt_revision: 2026-08-07.3` in
provenance, calls 4, no heals. Codegen: slot_fill 6/7 usable; ReservationsPage
attempt-1 transport-cut (HTTP 408 at the 120 s ask ceiling) → **classified, and the
cross-provider rung correctly RUNWAY-GATED** (`slot_fill_transport_fallback_skipped_
low_runway`, 98.3 s remaining) — R1's designed fail-closed, read live; 0 attempt-3
rows all-time. **Contract rejections: 0 (second consecutive run)** — the R2 slot_fill
translation is still unread live, for the good reason. design_manifest: 1/1 healthy
(planning serial 30.9 s). Ready ~568 s, gate PASSED. **CONFOUND: critic 5/5 and
fix_agent 6/6 died transport at $0/0 ms exactly when the key crossed 380 — credit
exhaustion, NOT the R5 starvation pattern; this run's tail is unreadable against the
R5 table.**

### What I got wrong in session 23

- **My status poll watched `requests.status` for `done`** — shipped runs stay `new`
  (144 and 142 did too); the 10-minute cap fired on a run that had already shipped.
  The ship signal is the pipeline log / preview record, not that column.
- **My first schema-rung early-stop fixture used `pages[0].state_ids: []` beside a
  populated `states` array** — the deterministic reconciler fixed it and the AI rung
  never fired. The fixture now uses rev 3's true shape (`pages: []`). The failure was
  informative: it is exactly why 143 (states nowhere) could not be healed.

### State of the repo (session 23 close)

- **main: `772ac82` (trio) → `f9fc60c` (R6) + docs — pushed.** Suite **2,026 / 1 / 0**
  (documented command). New drivers, both 0-survivor first pass:
  `mutate_empty_tuple_reject_class.py` (11), `mutate_r6_telemetry_budget.py` (6).
- **Credits: the key is EXHAUSTED (380.148 of 380).** BMV's session spend: $0.245 +
  ~$0.02 probes, fully telemetry-attributed. The other project burned ~$4.5 across
  this session including ~$2 during the run's ten minutes. **No weather probes, no
  funded runs, until the owner tops up or rotates the key.**
- **Running config verified from the recreated process at close:** prompt revision
  **2026-08-07.3**; TEXT=gemini-3-flash-preview, FIX+QUALITY_FIX=glm-5.2:nitro,
  PREVIEW_APP=deepseek-v4-pro + fallback haiku-4.5, ARCHITECT/CRITIC=haiku-4.5,
  APPSPEC on + gemini-2.5-flash ×3 + fallback haiku. (`backend/.env` untouched all
  session; the session-open cosmetic drift — the container predating the
  PREVIEW_APP_TRANSPORT_FALLBACK_MODEL line — was erased by the mid-session recreate.)

### The next step (ordered)

1. **Top up or rotate the shared key** — nothing funded moves without it. Then the
   still-unbound live reads ride the next healthy run free: the R2 contract-retry
   translation (needs a run WITH contract rejections), attempt-3 slot_fill rows, and
   a CLEAN tail read against the R5 table (145's was confounded by the dry key).
2. **The R3 ruling**: coerce the `detail inquire CTA (#inquire)` href (and optionally
   the image-pool pair) per the audit table, mutation-pinned so leniency never
   reaches the face/skeleton/import set — or rule the strictness intended.
3. **R5's ruling** — the measured table has been ready since session 22; one owner
   word implements `TAIL_RESERVE_SECONDS = 150`.
4. **R1's remainder**: `coverage_review`'s one-shot is still same-model; the
   single-provider ask-site survey.
5. **FILED, new (proof archived in 143's artifact + this session's mining): a
   repair-output collapse guard** — deterministically REJECT an AI repair whose
   output empties `pages`/`states` that its parent populated (keep the parent, spend
   nothing further), the code half of the anti-collapse taught line. Fail-closed,
   invents nothing; needs a ruling only on whether teaching alone suffices first.

## Next session's prompt, ready to paste (session 24)

```
Read HANDOFF.md first — "Session 23, in one page" and THE TALLY. Then the roadmap's
session-23 callout AND the R-table's session-23 status block. Don't re-derive any of it.

main is PUSHED through f9fc60c (+ the docs commit on top). Suite 2,026 / 1 / 0.

THE KEY IS EXHAUSTED — 380.148 of 380 at session-23 close, drained by the shared key's
other project (~$4.5 in one session; BMV's own spend was $0.245 + probes, fully
attributed). PROBE CREDITS FIRST. If I have not topped up or rotated the key by the
time you read this, this is an OFFLINE-ONLY session: no weather probes, no runs, and
that is fine — the backlog below has offline items. Never launch on a key without at
least $1.00 of verified headroom AND my top-up confirmed in this prompt or the repo.

Running config verified from the process at close: prompt revision 2026-08-07.3, TEXT
gemini-3-flash-preview, FIX+QUALITY_FIX glm-5.2:nitro, PREVIEW_APP deepseek-v4-pro +
fallback haiku-4.5, ARCHITECT/CRITIC haiku-4.5, APPSPEC on + gemini-2.5-flash ×3 +
fallback haiku.

MY BUDGET: $0 until the key is topped up; if it is, $5 CAP, same rules as ever (probe
first, bracket every run, 10-minute cap monitored, one run per landed change). Time box
3 HOURS; reserve the last 20 minutes for close-out. LOCAL only.

THIS SESSION RUNS ON YOUR JUDGMENT — same standing authority as session 23 (reorder
with recorded reasons; chase what stored evidence proves; the PARKED list, the
NON-NEGOTIABLEs, fail-closed over clever, and the honest tally are absolute).

THE BACKLOG (my order — yours to re-order with reasons):

1. IF THE KEY IS FUNDED — the unbound live reads, free on the next healthy run beside
   whatever you land: the R2 contract-retry translation (needs a run WITH slot_fill
   contract rejections — two straight runs had zero), any attempt-3 slot_fill row, and
   a CLEAN tail read against the R5 table (145's tail was confounded by the dry key —
   do NOT count it).
2. R1'S REMAINDER (offline-provable, ~45 min): coverage_review's one-shot retry is
   still same-model — give it the classify-first + bounded + cross-provider treatment
   (the slot_fill/appspec rungs are the pattern); then the single-provider ask-site
   survey (the R6 scopes just made every ask site queryable — use the census).
3. THE COLLAPSE GUARD — only with my ruling (it is FILED, next-step item 5): the
   deterministic rejection of a repair output that empties pages/states its parent
   populated. If I rule "teach-only first", it stays filed until a live repeat.
4. R3's COERCION — only with my ruling on the audit table (inquire-CTA first, the
   image-pool pair second), mutation-pinned so leniency never reaches the
   face/skeleton/import set.
5. R5 — only with my ruling: TAIL_RESERVE_SECONDS = 150 per the measured table.

Standing rulings so you never wait: R4 DONE (never lower OPS_MIN_NON_HUB_PAGES=4); the
ship-gate ops floor firing again is a NEW bug; retries must differ (R2); fallbacks are
classify-first + bounded + cross-provider (R1); leniency never reaches decision-carrying
fields (R3); quality failures never take a model fallback. The identical-error-set
early stop is live — if a run terminates repair_reproduced_parent_errors, that is the
system working; mine the artifact, don't relaunch blind.

WEATHER GATE (only if funded): two long json_object probes on the spec model (~$0.06),
probe-parse as tolerant as the pipeline's. LAUNCH: POST /api/requests (never /api/v1),
multipart, industry always set, host port 8001. The requests.status column stays "new"
on shipped runs — the ship signal is the pipeline log / preview record, never that
column.

STANDING TALLY: ships vs attempts AND accepts vs rejects, every reject classified from
telemetry before any relaunch. A transport-classified dead run at any appspec ask site
is a NEW bug. Rev-1 count under 2026-08-07.3 stands at 1 — keep counting honestly.

PARKED (touch only with my ruling): ARCHITECT_MODEL, the <=500 s p50 DoD row, R5's
behavioral half (item 5), the R3 coercions (item 4), the collapse guard (item 3),
schema-level conditional assertion requirements, relaxing the AppSpec schema, the
October spec-slot migration.

NON-NEGOTIABLE: pipeline never previews; every fix mutation-proven from in-memory
backup, one sweep at a time, red for the FILED reason; suite via docker run WITH its
pip install half; recreate never restart; config from the running process; archive logs
the moment each run finishes; no code edits while a generation is in flight (sweeps
count); absolute paths; 10-minute cap.

BEFORE YOU FINISH (the reserved 20 min): .env in the state the evidence supports and
verified from the running process; R-table statuses updated; HANDOFF/MODEL_RESEARCH
updated with real numbers including the ships-vs-attempts line; push; next prompt
written; tell me plainly what each run cost, what landed, what you chose to reorder
and why, and what's left.
```

---

## Session 22, in one page

**The session was the R-backlog under a $10 / 3-hour box: R5 measured, R1+R2+R4+R7 LANDED
— every sweep 0-survivor — and the ladder's one funded test SHIPPED the exact run-135
shape that used to burn a full paid run.** Suite **2,012 / 1 / 0** (+45). Four sweeps:
**7 + 15 + 10 mutations / 0 survivors** (R7, R1+R2, R4) plus `mutate_blueprint_gap_fill.py`
re-anchored and re-run **13 / 0**. Evidence: `docs/evidence/session22/`.

### THE TALLY (ships beside accepts, always)

| | |
|---|---|
| **Ships / attempts** | **1 / 2** (143 ✗ honest quality, **144 ✓ ready at 552 s, gate PASSED**) |
| **Spec accepts / rejects** | **1 accept** (144 rev-2, coverage 100, prompt rev 2026-08-07.2) / **1 reject** (143 — 5 revisions, all `state_ids: []`, the session-19 empty-tuple class). **Rev-1 streak ends at 3** |
| **Transport-dead runs** | **0** — 143's authoring attempt 1 was error-cut and ABSORBED (attempt 2 authored healthy); 144's one demo error-cut absorbed |
| Spend | **$0.33 telemetry-attributed** (143 $0.07 + 144 $0.27) + ~$0.06 weather; bracket 370.314 → 372.141 of 380 (**$7.86 left**); the rest of the key delta is the shared key's other project |

### R5 — MEASURED, owner's table ready (no behavioral change)

The codegen/tail split from runs 129-142's stored `generation_log` + `ai_usage_events` is
in the roadmap under the R-table. Headline: **run 140 is the only complete tail on record
(~142 s: critic 5/5, refine 3/3, fix_agent success → ready 553 s); every other ship gave
the tail ≤107 s and refine/fix starved at $0.** Today only the POST-gate smoke pass has a
reservation (`RESERVE_SECONDS=60`); nothing protects the pre-gate tail. Recommendation
(PARKED on the ruling): `TAIL_RESERVE_SECONDS = 150` beside it, codegen stops opening
batches at `remaining < 150 + 60` — the same clamp `codegen_phase.py:216-222` already
applies to the fix loop.

### R1+R2 at slot_fill — LANDED (15 mutations / 0 survivors)

**Correction to the R2 row first:** the retry was NOT byte-identical anymore — session
20's `8198cdb` already threads the raw validator errors + excerpt. The live defects were
narrower: the `catalogue-contract` TRANSLATION (request 107's lesson) was **dead code** —
contract rejections divert to `_catalogue_retry_context`, which never included it, and the
test pinning it drove a path production never takes; plus an empty-report hole. Now the
live attempt-2 prompt carries errors AND translation (`guidance=` kwarg), pinned end-to-end.
**R1:** `generate.py`'s bare `except Exception: break` now classifies
(`_is_transport_failure` — retryable `ProviderGenerationError` only), and ONE bounded
cross-provider rung (`PREVIEW_APP_TRANSPORT_FALLBACK_MODEL`, default haiku, in `.env`
explicitly) fires under telemetry attempt 3, faces the identical judge, is runway-gated
with its own degradation label, and fails closed to the scaffold on any other class.
**The first sweep's survivor was the system working**: a contract-invalid fallback fill is
doubly defended (post-loop enforce), so the "ships unjudged" mutation survived — the
catching fixture is a fill that PARSES wrong but keeps its face, where the judge is the
only defense. 17 tests.

### R4 — the ladder, all five rungs, and run 144 is its live proof

`OPS_MIN_NON_HUB_PAGES = 4` shared by gate + prompt + gap-fill + refusal (gate refactored
to derive — value pinned by test, never lower); `app_spec.j2` rule **8b** for ops faces
only (builder lazy-imports the producer; **prompt revision 2026-08-07.2**, pin test
updated); ops gap-fill **PATH-KEYED** with stop-at-floor (census correction: the skeleton
key adds ONE page, `/settings`, not zero — still under floor); `OpsSeedUnderFloorError`
refusal opt-in on the enforced seed path only (plan_phase's final kind lock). Census part B
extended: 135's stored artifact fills to exactly the floor (`/queue` + `/reports`) and
passes the FULL gate offline; 47-corpus untouched; gallery census byte-identical to
pristine HEAD. 13 tests, 10 mutations / 0 survivors.
**Run 144 (135's brief verbatim): spec accepted rev-2 coverage 100 — authored 3 pages with
`/` NATIVE — the gap-fill added `/queue` + `/records` (blueprint page_ids in the shipped
table), exactly to the floor, and the run SHIPPED `ready` at 552 s, quality gate PASSED.**
The class that cost run 135 a full paid run is now a ship.

### R7 — landed and generalized

`assert_safe_runtime_configuration` WARNS (never crashes) on a same-provider transport
fallback — both pairs: `APPSPEC_TRANSPORT_FALLBACK_MODEL` vs `APPSPEC_MODEL`/
`APPSPEC_REPAIR_MODEL`, and the new `PREVIEW_APP_TRANSPORT_FALLBACK_MODEL` vs
`PREVIEW_APP_MODEL`. 7 mutations / 0 survivors (appspec pair); the preview pair rides the
R1 sweep (2 more mutations there).

### Run 143 — honest quality reject, and the transport gate earned its keep

Osteria (141's accepted brief verbatim): authoring attempt 1 `finish_reason=error` with a
1.5k partial body — **the session-19 gate classified it and re-asked; attempt 2 authored
30.8k chars healthy**. That candidate carried `pages[0].state_ids: []` and all 5 revisions
(repair + schema_repair) repeated the SAME empty-tuple error — rejected honestly in 88 s,
$0.07. **The R1+R2 slot_fill read did NOT bind** (never reached codegen): the next healthy
run past codegen reads it free (contract-rejection count + `How to repair:` in any retry
prompt + attempt-3 rows if weather hits). FILED: the empty-tuple class (`state_ids`
minItems) is now 2-for-2 sessions in rejects — it wants its own taught line + repair
translation, same treatment the three session-20 codes got.

### What I got wrong in session 22

- **My first R1 sweep fixture sat in enforce's shadow** — the "ships unjudged" mutation
  survived because post-loop enforce also discards contract-invalid fills. The sweep
  worked; the fixture was rebuilt to isolate the judge (parse-broken, face-intact).
- **My injector refactor drifted two anchors in the landed `mutate_blueprint_gap_fill.py`**
  (single-line `elif` became multi-line). Caught by the driver's own anchor-count guard on
  re-run; anchors updated (semantics unchanged), full driver re-run 13/0.
- **My first "unfillable" refusal fixture wasn't** — layout-less routes get
  `setdefault("layout", "admin")` from the injector's path-exists branch and become
  gate-countable. The fixture now pins `layout: "public"` explicitly.

### State of the repo (session 22 close)

- Suite: **2,012 passed / 1 skipped / 0 failed** (documented command). New drivers, all
  0-survivor: `mutate_transport_fallback_provider_warning.py` (7),
  `mutate_slotfill_transport_fallback.py` (15), `mutate_ops_floor_ladder.py` (10).
- **Credits: $7.86 left** (372.141 of 380). Session 22: $0.33 telemetry-attributed
  (143-144), ~$0.06 weather, ~$0.73 of pre-launch key-level delta was the other project.
- **Running config verified from the process at close:** TEXT=gemini-3-flash-preview,
  FIX+QUALITY_FIX=glm-5.2:nitro, PREVIEW_APP=deepseek-v4-pro +
  **PREVIEW_APP_TRANSPORT_FALLBACK_MODEL=anthropic/claude-haiku-4.5 (new, in `.env`)**,
  ARCHITECT/CRITIC=haiku-4.5, APPSPEC on + gemini-2.5-flash ×3 + fallback haiku,
  **prompt revision 2026-08-07.2**.

### The next step (ordered)

1. **The R-backlog's remainder**: R6 (writer/attempt scoping on the `admin_ops.py:330`
   fallback rows; refund errored $0 calls from the appspec call budget) and the R3 offline
   audit (classify slot_fill-contract + architect-JSON failure codes decision-carrying vs
   decorative from stored reject evidence — no code).
2. **The unbound R1+R2 live read** — free on the next healthy run that reaches codegen.
3. **The empty-tuple reject class** (143, and session 19 before it) — the artifact is
   already mined (post-close, this session): revisions 1-3 authored EMPTY `pages`/`states`
   arrays outright; revisions 4-5 authored a placeholder-id page (`"Page1"`, no states,
   nothing anywhere to reconcile from) beside one well-formed page, and **rev 5 reproduced
   rev 4's validator errors identically**. Three-part fix, all one neighborhood: teach the
   authoring prompt (state_ids minItems + real `PAGE-*`/`STATE-*` ids, never placeholders),
   add the `app_spec_repair.j2` translation for the schema-parse minItems class, and stop
   the repair loop when a revision reproduces its parent's IDENTICAL error set (143 would
   have failed at rev ~3, not 5). NO deterministic heal — states are decision-carrying
   (R3), and 143 proves there is nothing to back-fill from.
4. **R5's ruling** — the measured table is in the roadmap; one owner word implements the
   ~150 s tail reservation.
5. **R1's remainder**: `coverage_review`'s one-shot is still same-model; survey any other
   single-provider ask sites.

---

## Session 21, in one page

**The session's reason to exist — "2 ships in 9 runs is unacceptable" — closed at 3 ships /
5 attempts, with the two non-ships being honest quality rejects under a model trial that was
itself the experiment.** Suite **1,967 / 1 / 0** (measured at close; +26 tests this session —
session 20's 1,939 was stale by ~2, same class of note as session 18's). Three sweeps,
**25 mutations / 0 survivors** (11 + 7 + 7). Evidence: `docs/evidence/session21/`.

### THE TALLY (report ships beside accepts, always)

| | |
|---|---|
| **Ships / attempts** | **3 / 5** (138 ✗, 139 ✗, **140 ✓, 141 ✓, 142 ✓** — the closing duo 2/2) |
| **Spec accepts / rejects** | **3 accepts (140, 141, 142 — ALL rev-1, coverage 100 each) / 2 rejected requests** (138, 139 — both under the haiku trial, both honest quality) |
| **Transport-dead runs** | **0** — every `finish_reason=error` call all session was absorbed (one per shipped run, in the tail) |
| Spend | **$1.94 telemetry-attributed** (138-142); bracket 365.300 → 368.760 of 380 (**$11.24 left**); ~$0.25 weather probes; the rest of the key-level delta is the shared key's other project |

### Item 1 — transport model-fallback (`3f7f7f9`), LANDED and FIRED LIVE same-session

`APPSPEC_TRANSPORT_FALLBACK_MODEL` (default `anthropic/claude-haiku-4.5`, `.env` keeps it
cross-provider from the primary — currently haiku since the slots reverted to gemini). When a
candidate ask's bounded same-model re-ask is ALSO cut, ONE ask goes to the other provider
before failing closed — attempt 3 under the same writer, so the `ai_usage_events` row is
unmistakable. Fires ONLY on the transport class (the gate's `provider_error` verdict or the
provider's retryable empty raise); malformation and refusal raise exactly as before; the
deterministic validator still gates whatever comes back. Also closed: authoring's retryable
empty-cut raise previously escaped the loop with ZERO retries. 13 tests, 11 mutations /
0 survivors. **Live firing on run 139: after two haiku 0-char burns, authoring attempt 3 on
gemini returned a 50k-char candidate — a judged candidate instead of a dead run, the exact
designed trade.** After item 1, a transport-classified dead run is a NEW bug — file it loudly.

### Item 2 — the haiku APPSPEC migration duo: REVERTED, decisively

Runs 138/139 (duo3 briefs verbatim, haiku-4.5 in all three APPSPEC_* slots): **0/2 accepts,
$0.70 duo spend.** The failure shape: **3-of-4 haiku authoring asks returned
`finish_reason=length` with 0 output chars at the full 24k budget ($0.13, 95-116 s each)** —
the session-18 reasoning-burn class, now confirmed at the appspec slot. When haiku DID author
(138, 65k chars), the spec violated a taught rule (`visible_assertion_evidence_required`) and
haiku's repair returned rev-2 with the IDENTICAL error at the IDENTICAL path — it does not
apply the verbatim validator report. `.env` reverted to gemini-2.5-flash ×3 (+ fallback
haiku), recreated, verified from the process. October migration: haiku-4.5 is ruled out
as-is alongside gemini-3-flash; MODEL_RESEARCH has the table.

### Item 3 — the ops-home seed gap (`e895ef7`): fixed, and run 140 SHIPPED

`lock_chrome_on_architecture_seed` now re-paths an ops-kind seed's own primary
(`ops-dashboard`) route to `/` when no home exists — never inventing a page, never electing
the AI hub, never touching public kinds, role defaultPaths kept in step. Census: all 47
stored kind_contexts replayed through the real lock — 0 route paths change; 135's real
accepted spec reproduces the defect pre-lock and seeds its home post-lock. 7 tests,
7 mutations / 0 survivors. **Run 140 (135's brief verbatim): spec accepted rev-1 coverage
100, SHIPPED `ready` at 553 s — the first internal_ops ship under enforced appspec on
record.** The fresh spec authored 6 pages with `/` native, so the seed rung wasn't needed
this time; it remains the floor for 135-shaped thin specs. **FILED, offline-proven
(full-chain replay archived): a 3-page ops spec would next refuse on
`ops_kind_too_few_pages` (2 non-hub ops routes < 4) — masked live by missing_home's early
return; the ops blueprint gap-fill fires only on non-substantive route tables.**

### Item 4 — run 133's coverage determinism trap (`aced8e7`): both halves

Mined: all 4 validation errors were explicit `null`s on DEFAULTED CoverageFinding fields
(`unsupported_additions[*].source_path/source_excerpt`) — cosmetic. Nulls on defaulted
fields now coerce to `""`/`[]`; required fields and the goal_coverage proof ledger stay
strict (mutation-pinned that leniency never widens there). And the one-shot retry VARIES:
compact corrective instruction naming the first failure, telemetry attempt bumped to 2 (run
133's two rows were both attempt=1). 6 tests, 7 mutations / 0 survivors.

### The closing duo — the success criterion, met

Runs 141 (Osteria Vinci) / 142 (Cedar Point Lodge), everything adopted: **2/2 shipped
`ready`, both specs accepted rev-1 at coverage 100** (~565/558 s wall, 24.7/17.8 s past the
540 s soft deadline, inside the cap, previews delivered). Gallery: 141 zero artifacts
anywhere; 142's only gallery is the planner's own PAGE-ROOM-GALLERY (`/rooms`) — legitimate,
same as 132. `design_manifest` on gemini-3-flash: **3-for-3 this session (1.9-2.3k chars,
5-6.3 s), 5-for-5 live since the fix.** Tail state recorded: typecheck `errors`,
visual_critic skipped past deadline on both — the tail starvation is now the dominant
residual (see the p50 note below).

### What I got wrong in session 21

- **My first weather probe called healthy streams a storm twice** — a 60-item task couldn't
  fit the 6k cap (`length`), and haiku's markdown fences failed my probe's strict parse.
  The real storm class (finish_reason=error, $0, partial body) never appeared. Corrected in
  the evidence file; lesson: a probe's parse must match the pipeline parser's tolerance.
- **The first duo launch 404'd** — the requests router mounts at `/api/requests`, not
  `/api/v1/requests`. Cost one retry, no spend, no request created.
- **My first run-monitor script produced no output** (a hung docker-compose subprocess);
  replaced with a plain shell poll. Watch the watcher.
- **One mutation survived its first sweep because my existing-home fixture WAS the dashboard
  candidate** — re-pathing `/` to `/` is a semantic no-op. The fixture now puts the home on a
  non-preferred route. A sweep with survivors is the system working.

### State of the repo (session 21 close)

- **main: `3f7f7f9` → `aced8e7` → `e895ef7` + docs on top of `b84f50d` — pushed.**
- **Suite: 1,967 passed / 1 skipped / 0 failed** (documented command). Three new drivers,
  all 0-survivor: `mutate_transport_model_fallback.py` (11),
  `mutate_coverage_retry_variation.py` (7), `mutate_ops_home_seed.py` (7). New census:
  `ops_home_seed_census.py` (red-exit, archived output).
- **Credits: $11.24 left** (368.760 of 380). Session 21: $1.94 telemetry-attributed
  (runs 138-142), ~$0.25 probes.
- **Running config verified from the process at close:** TEXT=gemini-3-flash-preview,
  FIX+QUALITY_FIX=glm-5.2:nitro, PREVIEW_APP=deepseek-v4-pro, ARCHITECT/CRITIC=haiku-4.5,
  APPSPEC on + gemini-2.5-flash ×3, **APPSPEC_TRANSPORT_FALLBACK_MODEL=anthropic/claude-haiku-4.5
  (new)**, prompt revision 2026-08-07.1.

### The next step (ordered)

1. **The tail starvation is now the p50/quality lever.** All three ships ran codegen to the
   deadline; typecheck landed `errors` and the visual critic never ran on any of them. The
   appspec side is fixed (3-for-3 rev-1 accepts, ~35-40 s planning): the remaining big rocks
   are the codegen/tail budget split and the architect serial (owner-parked). Measure-first,
   owner-adjacent.
2. **The filed `ops_kind_too_few_pages` gap** — offline-proven on 135's artifact. The honest
   fix shape: let ops kinds gap-fill unserved blueprint pages on substantive-but-thin appspec
   tables (the public kinds already do), or a ruling that ≤3-page ops specs are legitimately
   too thin to demo. Needs a ruling or a run beside it.
3. **Rev-1 acceptance is suddenly 3-for-3 on gemini** after the hardened prompt + varied
   coverage retry — keep counting; if the streak holds, the repair rung becomes rare and the
   appspec wall cost drops toward its floor (~70 s).
4. **FILED code items if time remains**: the generation/sanitize import cycle; refunding
   errored $0 calls from the appspec call budget; VISION_MODEL migration beside a
   vision-touching run.

---

## Session 20, in one page

**All of session 19's "next step" items landed in one session, each measurement-first.**
Suite **1,939 / 1 / 0**; three sweeps, **23 mutations / 0 survivors total** (9 + 7 + 7);
prompt variable audit clean. Evidence: `docs/evidence/session20/`.

### Item 5 — the gallery residual and the AboutPage half, both landed

The prerequisite came first: **`plan_blueprint_census.py`**, a NEW census over the 60 stored
`experience_plan`s (the route censuses never covered the plan stage). It fingerprints
blueprint-seeded pages against each run's OWN stored contract literals, reconstructs pre-seed
roles, and replays the real `_ensure_role_pages` — red exit on any unexplained divergence.
Findings that shaped the fix: only 4 of 60 runs were ever seeded (3 modern = 122/124/125,
1 legacy); **50 of 60 runs carry planner-assigned `public-detail` without item anchors, and a
naive re-inference would have flipped 8 legitimate `painting-detail` pages** — measured before
designing, so the guard keys on end-anchored item paths, `detail` ID segments (never titles:
"contact details." is 0e678fa's own trap), and prose agreement. Result over the archive:
41 genuine detail pages keep, 52 mislabeled pages (about ×9, contact ×8, private-dining —
run 124's rejection class) flip to permissive contracts. The serve-aware seed is plan-WIDE
(124's guest-role menu is what makes the owner-role gallery redundant) with the scaffolder's
browse-leaf rule as a second signal (hoisted `CATALOG_BROWSE_LEAVES`, byte-identical), a
PAIRED detail rule (gallery_detail rides only with its parent), and public-only scope.
47 stored kind_contexts: **0 regressions**; gallery census byte-identical to a pristine-HEAD
worktree. **Live on 129 (restaurant): zero gallery artifacts in the plan, zero slot_fill
contract rejections, shipped `ready` at 559 s.** 15 tests, 9 mutations / 0 survivors.

### The repair-path transport re-ask — run 123's killer closed

`_candidate_ask_with_transport_reask` (builder.py): every candidate-shaped ask (`repair`,
`schema_repair`) gets ONE bounded re-ask on the transport class only — the gate's
`provider_error` verdict or a retryable empty-cut raise — with the ai_call attempt bumped so
telemetry rows stay distinguishable, and model-authored malformation still raising untouched.
Routing `schema_repair` through it fixes its missing-`finish_reason` bug (the exact defect
that killed run 123). `coverage_review` now refuses `finish_reason=error` outright so
generation's EXISTING one-shot retry is its bounded re-ask — one layer, never stacked.
8 tests, 7 mutations / 0 survivors. (The telemetry guard test was updated: schema_repair no
longer asks a model directly.)

### The authoring prompt hardening — revision `2026-08-07.1`

Reject shapes mined from `app_spec_revisions` 114-128 (transport artifacts excluded and
labeled as such). Taught in `app_spec.j2`: **exactly-one initial state** (+ `page_id` /
`state_ids` consistency — the heal/validator mismatch that got 114), **per-kind assertion
references** (12a — got 116), **declare-before-cite** (17 — got 127), **the minItems floor
outside traceability** (6a — got 115/123), **trace-or-defer** (16 — got 114). The three
recurring codes get exact fixes in `app_spec_repair.j2` (the repair model receives the
validator report verbatim — now with a translation). 6 render tests read the wording off REAL
prompts; 7 mutations / 0 survivors; revision pinned (env does not override — verified in the
container). **First data points: 129's spec REJECTED rev-1 then was ACCEPTED on rev-2 — the
first spec-repair success on record. 130 still rejected on `requirement_unaccounted_for`
(the taught rule, violated anyway; n=1, honest fail-fast in ~3.5 min).**

### Item 4's deferred observable — CONFIRMED on 129

`design_manifest` **SUCCEEDED**: 2,139 chars, 5.9 s, `stop`, on gemini-3-flash — after 0
chars at its exact cap on every haiku run. Planning serial (31.8 + 5.9 s) did not regress
against the ~22-30 s baseline plus the old 12-13 s failure burn.

### Session-20 runs and tally (enforced appspec)

| run | brief | spec | outcome |
|---|---|---|---|
| 129 | restaurant | **accepted rev-2** | shipped `ready` 559 s; zero gallery artifacts; design_manifest success; slot_fill 1/5 usable (tail transport deaths, ZERO rejections) |
| 130 | hotel | rejected rev-1 (`requirement_unaccounted_for`) | honest fail, ~3.5 min |
| 131 | hotel retry | rejected rev-1 (`state_assertion_state_required` ×3) | honest fail |
| 132 | hotel retry 2 | **accepted rev-1** | shipped `ready` 559.6 s; only gallery is the planner's own PAGE-ROOM-GALLERY (legit, not seeded); zero /gallery routes; design_manifest success again (2,068 chars, 5.5 s — 2-for-2 live) |

Tally: **2 accepts / 2 rejects** (cross-session enforced record on these briefs: 7 accepts /
6 quality-rejects). Both rejects violated rules the hardened prompt now states — teaching
narrowed nothing to zero on gemini-2.5-flash, but 129's rev-2 accept is the FIRST spec-repair
success on record, and the translated repair rules are the plausible cause worth watching.
Spend: **$0.77 telemetry-attributed** (129-132). **The key was topped up mid-session:
total_credits 360 → 380; $17.47 left at close** (bracket 355.384 → 362.530; the delta beyond
telemetry is the shared key's other project — tracked, not alarmed on).

### What I got wrong in session 20

- **Two mutation survivors were my fixtures' fault, found by the sweeps working as designed**:
  the ops-scope pin didn't bind (the thin role's AI-hub page was a "marketing landing", so
  chrome-repair rewrote it into the ops home before the seeding logic ever ran), and a plural
  "details" title can't catch a titles-widened anchor rule (the word-boundary regex refuses it
  either way). Both re-swept clean after rebuilt fixtures.
- **My first trattoria test brief classified `booking_service`, not `storefront`** — "we take
  reservations" is a booking hint. The fixture-binding assert caught it before any test lied.
- One sweep printed a `caught` whose anchor had drifted (two `_parse_candidate` call sites
  matched); the driver's anchor-count guard flagged it — anchors must include distinguishing
  context lines.

### Post-close: the acceptance-baseline runs and the p50 measurement (same session)

**Five new-brief/retry runs (133-137, $0.45):** 135 (staff-only dispatch desk) — spec
ACCEPTED rev-2, classified `internal_ops/ops`, staff-only workspace plan, design_manifest
3-for-3 — and the quality gate then honestly refused the ship on
**`ops_kind_missing_home:architect.routes`** with the AI repair refused past-deadline. **NEW
FILED: under enforced appspec, an ops-kind app's seeded route table can lack its ops home —
the first internal_ops enforcement data point ever.** 133 (florist): coverage_review
malformed twice on byte-identical `stop` outputs (temp 0 retry buys nothing — filed). 134,
136, 137: transport storm — 136/137 had real specs whose repair chains were double
error-cut, **and the new `_candidate_ask_with_transport_reask` fired live on both (attempt-2
rows in telemetry, its first production firings)**; the weather beat the single re-ask.

**Full-session tally (129-137): 3 spec accepts (129 rev-2, 132 rev-1, 135 rev-2) /
3 spec quality-rejects (130, 131, 133) / 3 transport-honest (134, 136, 137). Ships: 2.
Repair-accepts are suddenly 2-of-3 accepts — the translated repair rules are earning.
Spend $1.22 all-in; $15.51 left at close (364.489 of 380).**

**The p50 decomposition (item 3, measured on 129/132):** planning is fixed (~35-38 s) and
the serial big rocks are now the **architect (73-221 s of haiku AI — 221 s on 129's 2-call
retry)** and **appspec (~71-124 s wall, growing ~60-70 s per repair revision)**; codegen
still runs to the deadline by design and the critic/fixer tail still starves ($0 rows on
both shipped runs). The architect slot is quality-owner-parked (ARCHITECT_MODEL stays), so
the next p50 levers are appspec acceptance-on-rev-1 (fewer repair revisions) and the
codegen/tail budget split — both owner-adjacent, measure-first.

### Recorded landmine (filed, not fixed)

`pytest tests/appspec/` ALONE fails collection on `test_app_spec_contract` — the
long-standing generation/sanitize import cycle fires unless an earlier module warms
`app.application.appspec`. Present at HEAD `92c8f0f` (verified from a pristine worktree);
full-suite runs unaffected. A module-level `coverage → builder` import closes the same cycle,
which is why coverage's helper import is lazy.

---

## Session 19, in one page

**The plan was five ordered items; gemini-2.5-flash's bad day rewrote the first hour.** Thirteen
funded generations (116-128), **$1.62 telemetry-attributed over 142 calls**. Evidence:
`docs/evidence/session19/` (launch logs, api log dumped after every run).

### THE STANDING TALLY (enforced appspec, every run a data point)

**3 accepts / 10 rejects** across requests 116-128. The raw number needs its causes:

| class | requests | what it was |
|---|---|---|
| TRANSPORT-adjudicated (the defect, now FIXED) | 118, 119, 120, 121 | error-cut streams fragment-extracted into fake candidates |
| transport post-fix, failed HONESTLY | 128 | both authoring attempts error-cut; gate refused fragments, no fake revisions |
| real spec-quality rejects | 116, 126, 127 | state assertions without state_id; call budget exhausted on real outputs; missing evidence reference |
| mixed | 117, 123 | real authoring quality-rejected, then transport killed the repair chain |
| **accepts, all rev-1** | **122, 124, 125** | 122's authoring transport-errored and the NEW GATE re-asked — that accept exists because of the fix. All three shipped `ready` (554/556/556 s) |

Yesterday the same model+briefs went 2/2. **With transport removed, the enforced acceptance
record on these briefs across sessions 18-19 is 5 accepts (109/110/122/124/125) vs 4
quality-rejects (116/123/126/127) — spec-authoring quality on gemini-2.5-flash is genuinely
variable, the appspec authoring prompt/schema is the next hardening target, and
October-migration candidates need accepts over MORE than n=2.**

### The unplanned fix that mattered most: provider errors were minting fake spec rejections

Requests 118-121 all "rejected" their specs in seconds — but `ai_usage_events` showed the
authoring calls at `finish_reason=error`, $0, 0 tokens, with 1k-34.6k chars of partial body
over HTTP 200. The parser's fragment strategies (balanced scan, re-escape repair) found small
complete objects inside the cuts — request 118's "candidate" was **973 chars extracted from a
15,939-char cut** — returned them `ok=True`, and the pipeline minted revisions and failed the
requests honestly-looking. Session 16 filed exactly this class for slot_fill; it was alive in
appspec. **The fix** (`authoring_parser.py`): on `finish_reason=error` only a complete direct
parse passes; every fragment strategy fails as `app_spec_authoring_json_truncated` (retryable),
so `build_app_spec_candidate` re-asks the provider. 4 tests
(`tests/appspec/test_authoring_provider_error.py`), 5 mutations / 0 survivors, suite green.
**Live-proven within the hour: run 122's authoring attempt 1 errored → gate re-asked → spec
ACCEPTED rev-1 → shipped `ready` 554 s.** Residual FILED: repair/coverage/schema_repair asks
now classify honestly but have no per-call transport re-ask (123 died on an errored
schema_repair).

### The five ordered items

1. **QUALITY_FIX_MODEL=z-ai/glm-5.2:nitro — ADOPTED** (.env line 44, verified from the running
   process). Probe + run 112 evidence stands (base failed `length/truncated` at 85 s; nitro's
   fix_agent succeeded in the same run). The duo could not observe the stage live: 122 shipped
   with a CLEAN quality gate, so quality_repair never fired. No counter-evidence.
2. **1.12 rewritten** — both roadmap rows now pin "fail fast, fail honest, stored failure
   state, customer retry works", citing runs 111/112/113. The degraded-blueprint-ship premise
   is recorded dead.
3. **Catalogue-contract vocabulary — LANDED + ADOPTED.** New
   `catalogue_contract/face_prompt.py` derives a LOCKED LISTING FACE block from the validator's
   own `_DIRECTORY_FACE_REQUIRED`/`_SCHEDULE_FACE_REQUIRED`/`LISTING_FACE_COMPONENTS` (prompt
   and graded contract cannot drift); rendered only for face scaffolds; contract retry gets a
   translation entry. 4 tests, 5 mutations / 0 survivors. **Duo 124/125: the taught class fell
   5-of-6 → 0-of-5; 2/2 shipped ready.** Acceptance 4/11 (36%) flat vs baseline — confounded by
   deadline-tail transport deaths. Watch item: `forbidden @/ui component:PageHeader` ×1 on a
   composed page (class was 0 in s18; the block provably does not render for composed
   scaffolds — pinned).
4. **Haiku planning starvation — LANDED; live observation DEFERRED.** `design_manifest` +
   `plan_validation` ask TEXT_MODEL first (architect call stays haiku; haiku is now
   plan_validation's fallback only). 3 tests, 3 mutations / 0 survivors
   (`mutate_planning_writer_models.py`). **Three run attempts (126 restaurant, 127 restaurant,
   128 hotel) all died at appspec (two quality, one transport-honest) — none reached planning.
   Stopped buying tickets against the degraded provider: design_manifest success + planning
   serial time (baseline ~22 s) are FREE observables on the next session's first healthy run;
   read them from its log before anything else.**
5. **Gallery residual — NOT LANDED, diagnosis sharpened with live evidence.** Under enforced
   appspec the shipped route tables of 122/124/125 have **NO /gallery** (bbe6359 holds at the
   architect stage) — but 124's `experience_plan.roles[1].pages` carries blueprint
   `gallery`/`gallery_detail` pages + "Gallery"/"Artwork" nav links: **the entry point is
   `_ensure_role_pages`'s thin-branch blueprint append at PLAN stage**, which has none of the
   serve-aware resolution the route gap-fill got. Cost: wasted slot_fill calls (GalleryPage
   rejections on 124/125), dead nav labels, and run 111's failed ship. Next session's fix is
   scoped in the roadmap callout.

### What I got wrong in session 19

- **The first face-vocabulary sweep printed "caught" on a mutation that an infrastructure
  error had failed** (`No module named 'imp'` — a container pip flake). Re-run by hand, the
  mutation SURVIVED: my test asserted component names that also live in the embedded scaffold
  source, so gutting the block changed nothing the test read. Assertion moved to the block's
  own joined line; full sweep re-run clean. A sweep's red must be red for the filed reason.
- **I burned three duo attempts (116-121) before checking telemetry for WHY specs were
  rejecting.** The finish_reason=error rows were visible after the first failure; reading them
  then would have saved two launches (~$0.12). Check the telemetry of a surprising failure
  before repeating it.
- The suite count in session 18's handoff was stale by one (1,894 pass at HEAD, not 1,893) —
  noted so the next session doesn't chase it.

### Spend and credits

**$1.62 telemetry-attributed** (`ai_usage_events`, requests 116-128, 142 calls). Credits
bracket: probe at session start `total_usage 349.9196`, at close `355.0122` of 360 —
**$9.99 → $4.99 left on the key**. The ~$3.47 of key-level delta beyond BMV telemetry is the
shared key's other project plus non-attributed overhead — per the standing rule, tracked, not
alarmed on.

The if-budget-remains item (3 new-brief acceptance runs) was deliberately NOT run: item 5 is
unfinished, and on a day with 4 quality-rejects on calibrated briefs plus an active transport
storm, new-brief acceptance numbers would measure the provider's weather as much as the
pipeline.

### State of the repo (session 19 close)

- **main is `d5cdcd3` → `8198cdb` → `fefaf4f` → docs on top of `48ddc90` — pushed.** Four
  commits: the appspec provider-error gate, the listing-face vocabulary fix, the
  planning-writer routing, docs+evidence.
- **Suite: 1,907 passed / 1 skipped / 0 failed** (documented command). Three new mutation
  drivers, all 0-survivor: `mutate_appspec_provider_error.py` (5), `mutate_slotfill_face_vocabulary.py`
  (5), `mutate_planning_writer_models.py` (3). Vitest untouched (no JS/TS changed).
- **Credits: ~$4.99 left** (`total_usage 355.012` of 360). Session 19 spent **$1.62
  telemetry-attributed** (116-128, 142 calls). Key is SHARED — bracket, don't alarm.
- **Running config, verified from the process at close:** TEXT=gemini-3-flash-preview,
  FIX=glm-5.2:nitro, **QUALITY_FIX=glm-5.2:nitro (adopted this session)**,
  PREVIEW_APP=deepseek-v4-pro, ARCHITECT/CRITIC=haiku-4.5, APPSPEC on + gemini-2.5-flash ×3.

### The next step (ordered)

1. **Read the next healthy run's log for item 4's free observables**: `design_manifest` must
   SUCCEED (it failed 100% on haiku) and planning serial must stay ~22 s. No dedicated run
   needed — any run past appspec answers it.
2. **Item 5, scoped and evidence-backed**: `_ensure_role_pages`'s thin-branch appends the
   `_storefront_pages()` blueprint (gallery + ArtworkDetail literals) into thin roles at PLAN
   stage with no serve-aware resolution — proven by 124's `experience_plan.roles[1].pages`.
   Make it resolve menu/catalogue like the scaffold's `force_catalog_browse` leaf rule; fix
   AboutPage's plan-page public-detail in the same neighborhood; `gallery_gapfill_census.py`
   before/after (47 stored kind_contexts must not regress); mutation-pin; one duo.
3. **Transport re-ask for the appspec repair paths** (the gate's residual): repair/coverage/
   schema_repair asks classify honestly but a single errored call still kills the run (123, and
   the class will recur). Same retry shape as authoring.
4. **The appspec authoring prompt/schema hardening** — 4 quality-rejects in two days
   (state_id assertions, missing references, empty tuples). Each reject stores its exact
   validator errors in `app_spec_revisions.deterministic_validation_json`; mine them, teach
   the prompt the three recurring shapes, judge on accepts.
5. **The widened acceptance baseline** (the deferred if-budget-remains item) — after 3-4, on a
   day the provider is healthy: three enforced runs on NEW briefs, industries set, count accepts.

---

## Session 18, in one page

**The credits arrived and $3.01 of the owner's $10 budget bought 11 generations (requests
103-113), three model verdicts, the appspec head-to-head, all three 1.12 reachability runs,
and one landed+live-proven fix.** Full detail: the roadmap's session-18 callout and
`docs/MODEL_RESEARCH_2026-08.md` "Funded-session results". Evidence: `docs/evidence/session18/`
(launch logs, api log dumped after every run, slot_fill rejections, glm probe).

**The mystery spend is CLOSED as a non-issue: the owner confirmed the OpenRouter key is shared
with another project.** Balance deltas are not all BMV — track BMV spend from `ai_usage_events`,
bracket runs with the credits probe, never alarm on idle-time usage again.

### What the seven-fix read-list said (baseline duo 103/104, briefs of 95-98 verbatim)

5 of 7 pass; both runs shipped `ready` at 578/573 s. Hotel gallery GONE (was 8/8). Restaurant
gallery persists as the census's known 2-of-6 residual (fired 103/107/111, not 105/109) — and
run 111 proved it can FAIL a run outright: the visual critic scored gallery-on-restaurant 30/40,
`visual_defect_severe` ×3. AboutPage.tsx appeared in rejections → `0e678fa` is half a fix, the
plan page is the remaining cause. Item 2 (dual reservations nav) unexercised.

### The three verdicts (one .env line per run-pair, judged against the same briefs)

| slot | verdict | the number that decided it |
|---|---|---|
| TEXT_MODEL | **gemini-3-flash-preview ADOPTED** | codegen starts 245/247 s vs 342/389 s; planner 26-30 s vs 59 s; duo $0.51 vs $0.61 |
| FIX_MODEL | **glm-5.2:nitro ADOPTED** (probe-proven; slot tail-starved in-pipeline 12/12) | StreamLake 57-66 t/s vs nitro 178-185 t/s at real fix sizes; first live success run 112 |
| PREVIEW_APP_MODEL | **v4-flash REVERTED** | acceptance 28% vs 31%, tsc 4 vs 2, ship rate equal — and the writer is not the bottleneck |

**The frame: runway starvation.** Baseline burned 342-389 s before codegen; everything after
~490 s died with runway-sized timeouts (76% of calls, $0). The critic and fixer never ran on
healthy briefs — which is why the fixer experiment had to be a direct provider A/B probe.

### The appspec head-to-head: enforcement won, ruling is the owner's

109/110 (`on`) vs 107/108 (`off`), same models, same briefs: **2/2 rev-1 accepts; planning
~100-150 s → ~22 s (canonical_seed skips `validate_and_expand_plan` — session 16's prediction
verified); 0 codegen failures; the tail RAN for the first time (critic 4 successes, refine
fired, tsc 0 on 109); wall 566/561 vs 573/572; route tables leaner and business-matched (9/7
routes).** Cost +$0.16/run. **Recommendation: KEEP appspec, turn it ON.** `.env` left `off`
pending the ruling (mode is owner-parked). Caveats: n=2 accepts; a rejected spec now fails the
request honestly.

### 1.12: answered on all three slots, and the row's premise is dead

(a) architect unroutable → model-fallback chain absorbs it (v4-pro architected, +~100 s), the
deterministic blueprint is unreachable from model failure; the run then quality-gate-failed on
content. (b) page-writer unroutable → **slot_fill has no fallback**, scaffolds went to the
quality gate, honest `failed` inside the cap (566 s). (c) TEXT unroutable → fails at blueprint
in **4 s, $0.00**. Nowhere does a degraded blueprint preview ship — degraded output becomes an
honest failure + the customer retry endpoint. Rewrite the row to pin THAT (fail fast, fail
honest, never a bad demo).

### Landed: the palette fix, with a run beside it (`83bb7c6`)

`_design_system_dict` discarded the four derived colours and omitted `surface_color`; the
design system now threads ctx → `apply_workspace_guards` → every fallback writer. Also found
and fixed while landing it: the function existed as TWO diverging copies, and the font-name fix
(`8fe8955`) had only reached one — patterns' copy was still writing squashed `font_family`
slugs to every brand_contract consumer. Unified; squash regression mutation-pinned. **6 tests,
7 mutations, 0 survivors (`mutate_design_palette.py`). Suite: 1,893 / 1 / 0. Live-proven on
run 112's mock.ts: `#1b3126`/`#577466` (brand-derived) instead of `#0f172a`/`#475569`.**

### Also measured (fresh-log obligations met)

- **slot_fill distribution (backlog 3):** 49 baseline calls = 34 transport (starvation),
  5 contract, 1 truncated→retried, **attempt 2 PASSED — first observed 2.9 retry success**.
  The dominant contract failure is one vocabulary gap fired 5×: "missing directory face
  component:PageHeader, missing BRAND_MANIFEST services binding" on catalogue pages; a
  with-runway retry failed attempt 2 with the byte-identical message — the writer does not use
  the validator feedback (preflight Q5's public-catalog thread).
- **haiku planning writers fail by budget, not flakiness:** `plan_validation` burned exactly
  14,000 tokens with 0 output chars on both baseline runs (~95 s + $0.08 each), `design_manifest`
  the same at 1,500 — reasoning-burn shape. Under gemini-3 plans, validation fits (2/2);
  design_manifest still fails. FILED: budget/model change with a run.
- Run 104 shipped `/book` + `/book-appointment` + `/book-appointments` — route-alias class.

### What I got wrong in session 18

- **I read run 111's five pages as the deterministic blueprint's output.** Telemetry showed the
  architect chain had fallen back to v4-pro and succeeded — the deterministic path never ran.
  Always confirm WHICH writer produced an artifact before crediting a fallback.
- **I edited bind-mounted production code while run 111 was in flight.** Python's import cache
  protected the run, but that was luck, not procedure. Code edits wait for the window to close.
- **My first monitor watched `requests.status` for `done`** — a status that does not exist in
  this schema (success leaves `new` and writes `generated_pages`; only failure flips status).
  Caught before it mattered. Resolve terminal conditions from the schema, not assumptions.
- A `cd backend` for the mutation sweep drifted the working directory and broke the next
  compound command — the standing operating note, ignored once, cost one retry.

### Filed (each wants one line or one run next session)

1. `QUALITY_FIX_MODEL=z-ai/glm-5.2:nitro` (its base-glm call failed truncated on 112).
2. VISION_MODEL still on gemini-2.5-flash — migrate beside TEXT_MODEL after a vision-touching run.
3. The catalogue-contract vocabulary gap (PageHeader/BRAND_MANIFEST) — prompt fix, needs a run.
4. haiku planning budgets (above).
5. The appspec ON ruling — one owner word turns the measured win on.

---

## Session 17, in one page

**Still $0.** The owner read the morning summary and asked three things: (1) is there really no
way to test models without funded runs, (2) what is the gpt-4o "legacy path" — and if it is
unused, remove it, (3) does finding the best models take ~100 runs?

### The removal: the entire v1 role-pages pipeline is gone

The evidence that settled it: **all 8 recorded gpt-4o calls were one firing of the
orchestrator's double-failure fallback — request 59 (Jeanne Kassab Art), 2026-07-31 — four
page-generate + page-QA pairs that spent the money and still left the request `failed` with
`generated_pages` NULL.** The parachute did not open the only time it was pulled. The modern
pipeline already has its own internal safe-stub fallback, a single full retry, and a
customer-facing retry endpoint; a degraded generic-HTML demo also contradicts the owner's
"demo the customer loves" rule.

Removed: `pipelines/role_pages.py`, `services/page_qa.py`, `services/page_bundle.py`,
`services/page_inject.py` (the last two were role_pages-only), templates `html_page.j2` /
`page_qa.j2` / `page_fix.j2` + their `PromptTemplate` entries, the `/generate-pages` endpoint
and its background runner, both orchestrator fallback branches (a double failure now raises —
the pre-existing strict AppSpec behavior made universal — so the runner marks the request
`failed` instead of emitting `done` over nothing), the `HTML_MODEL` config slot
(`PREVIEW_APP_MODEL` gets its own default matching what .env pins today), the `.env.example`
line, and the dead llama VISION_MODEL comment in `.env`. `generated_pages` the COLUMN stays —
the modern finalize writes provenance there. `page_experience.py` and `industry_images.py`
stay — the modern pipeline imports them.

Pinned: `tests/application/test_v1_fallback_removed.py` (route/module/prompt absence + two
tests driving the real `run()` proving a once- and twice-failed generation raises) +
`scripts/cli/mutate_v1_removal.py` — **4 mutations / 0 survivors. Suite: 1,886 / 1 / 0.**
Note the live api container still runs the pre-removal code until the next
`up -d --force-recreate`; nothing urgent, the removed path was unreachable in practice.

### Answers given to the owner's other two questions

- Free-variant runs (OpenRouter `:free` models, no balance needed, ~50 req/day cap) can
  smoke-test pipeline MECHANICS but not answer which paid model wins a slot; the fixer
  `:nitro` test still needs credits.
- The plan is 8-12 runs total (4 experiments × 2-3 runs, one variable each), not ~100 — the
  3,200-call telemetry already did the narrowing.

---

## Session 16, in one page

**Still $0 — no probe run this session because no generation was attempted.** The owner asked for
an offline architecture/logic review ("something to optimize, maybe prompts"). One fix landed,
one audit became a standing tool, two timing findings are FILED (not fixed — each needs a run or
an owner call).

### The fix: the mock-synthesis prompt's prop-shape section had never reached a model (`d28df68`)

A new template/call-site variable audit (`scripts/measure/prompt_variable_audit.py`, red exit on
any missing variable) found `preview_app_mock_synthesize.j2`'s **CATALOGUE ITEM SHAPES section
guarded by `is defined` and passed by NO production call site** — the producer
`catalogue_prop_shape_block()` was authored for that exact call (its docstring says so), the
render-level tests passed it, and the test file even said "codegen/mock.py does not pass the
block yet". Wired at `codegen/mock.py`; the catching test drives `synthesize_mock_data` itself
and captures the prompt off a fake provider. 2 mutations, 0 survivors
(`mutate_mock_prop_shapes.py`). The audit's only other flag (fix_agent's build-error render) was
benign — the typecheck block is guarded — and that site now passes explicit falsy values with a
byte-equality test, so the audit gates clean at exit 0. **Suite: 1,881 / 1 / 0.**

### Filed finding 1 — shadow appspec is ~100-125 s of serial critical path with no functional reader

Request 102's telemetry timeline: blueprint ends at 10 s, then **three serial appspec calls until
102 s**, then demo to 125 s — all before planning starts. Every functional consumer of
`ctx.app_spec_result`/`app_spec_scope` (plan seed at `plan_phase.py:86`, architecture seed at
`:326`, hooks in finalize) is behind `enforce_app_spec`; under `APPSPEC_MODE=shadow` only
provenance is recorded. Moving the shadow pass off the critical path (concurrent with
plan_phase, or per-run skip) would cut p50 by roughly the gap to the 500 s DoD — but APPSPEC
mode and the p50 row are both owner-parked, and any change here needs a funded run beside it.
**Related: `validate_and_expand_plan` costs 70-94 s/run and is reached only because
`canonical_seed` is None under shadow** — seeding it from the shadow spec would be
enforcement-lite, also the owner's call.

### The ruling that followed finding 1: `APPSPEC_MODE` is now `off` (owner, 2026-08-06)

The owner flipped it after seeing the evidence — including the verification that the historical
runs really did record `mode=shadow` in their own generation logs (95/97/101/102), so the
~100-125 s cost was real and local. `.env:12` changed, container **recreated** (restart does not
re-read env), `off` confirmed from the running process (`app_spec_should_run_for_request() ==
False`), prior api log archived first at `docs/evidence/api-log-before-appspec-off-recreate.txt`.
Every future run skips the stage entirely. **The keep-or-delete question is a FILED EXPERIMENT
in the roadmap's session-16 callout**: after the funded duo proves the landed fixes on current
settings, run the same brief `on` vs `off` and judge ship-rate, route-table fit, and wall clock.
Do not run the head-to-head and the fix-proving duo as the same runs — one variable at a time.

### Overnight (owner asleep, both tasks owner-requested): model research + prompt review

- **[docs/MODEL_RESEARCH_2026-08.md](docs/MODEL_RESEARCH_2026-08.md)** (`7f8e057`) — every model
  slot, its job from code, its measured local behavior, and Aug-2026 candidates with prices.
  Headlines: the fixer (glm-5.2) fails 52% at 107 s while benchmarking 189 t/s globally — a
  provider-routing problem, testable with one `:nitro` suffix; the page writer (deepseek-v4-pro,
  77 s / 33% unusable) has a same-family flash variant 2× faster and 5× cheaper; the workhorse
  (gemini-2.5-flash) carries 80% of all spend and an October retirement date; gpt-4o serves a
  legacy path at the config's highest price. **Four experiments staged for the funded session,
  one slot per run-pair, never mixed with the appspec head-to-head. No model changed.**
- **[docs/PROMPT_REVIEW_2026-08.md](docs/PROMPT_REVIEW_2026-08.md)** (`304e360`) — honest
  verdict: above-average prompts (incident-grounded bans, taught consequences, mirrored
  enforcement), grown by accretion. **One offline-provable fix landed**: the "For App.tsx:"
  block and the index.css CRITICAL rendered into every one of ~1,170 page calls despite both
  files being assembler-owned and absent from all 42 archived worklists — now gated on
  `file_path` (conditional, not deletion), 1 test, 4 mutations, 0 survivors
  (`mutate_prompt_file_gates.py`). **Five filed** (each needs a run or judgment): duplicate
  "For page components" headers, 4× density repetition, cache-friendly static-first ordering,
  schema-enforced architect JSON, and the raw `scaffold_source[:16000]` slice (5 of 883
  archived pages exceed it — silent truncation while demanding a complete file back).

### Filed finding 2 — slot_fill's "truncated" rejections are provider errors adjudicated as answers

Already measured in duo 1 (roadmap codegen census): 14 of 28 rejections carry
`finish_reason: error`, 0 completion tokens, ~1,165 chars of partial body over HTTP 200 — a
transport failure recorded as a judged model answer, burning a full contract retry. The
reclassification fix should land WITH the funded slot_fill distribution measurement (backlog
item 3), not before it.

### What I got wrong in session 16

- **I ran the suite without `PREVIEW_TEMPLATE_DIR` once** (merged the audit and pytest into one
  container run and dropped the env) and read 14 template-dependent failures as a regression.
  The documented command has THREE load-bearing parts: the image, the pip install, and the env.

---

## Session 15, in one page

**Zero generations — the account is empty for the FOURTH session running.** Probed first, before
anything was restarted: `total_credits 330, total_usage 330.229`, byte-identical to sessions
12, 13 and 14. Items 1–4 of the session prompt (the duo, 1.12's reachability, `slot_fill`'s
distribution, the colour-fix run) were offline again, said so plainly, not attempted.

**The classifier ruling was NOT given at session start** — the prompt carried the unfilled
template `[prefix-anchored / word-boundary / leave it]`, a menu, not a choice, so the first half
of the session treated it as pending. **Mid-session the owner ruled "yes, fix it" on the prefix
recommendation, and uploaded a CI screenshot** — two items unblocked in one message.

The session landed five things (the owner also stated the product goal, which is now the
recorded yardstick for kind decisions: **the demo must match the business — a workflow tool, a
menu site, a portfolio, a company site — storefront is not the universal answer**):

### 1. The classifier is prefix-anchored — ruled, adopted, wrap-measured (`9c5b383`)

- `_blob` returns `_HintBlob`, a str subclass whose `in` requires the hint to start at a word
  edge (`(?<!\w)`, applied only when the hint's first char is alphanumeric — `"hr "` keeps its
  own delimiter); the right side stays free for the deliberate stems (`reconcil`, `bookkeep`).
- **Wrap-measured before/after: exactly one verdict changes anywhere — SB-07 to its intended
  `storefront/storefront` (16/20); 0 of the 47 stored kind_contexts move.** Before/after JSON
  archived in `docs/evidence/boundary-adoption-session15.json`. This is byte-for-byte the
  variant session 14 measured — the fix reuses the census's exact regex semantics.
- The forcers (`internal_desk.py`/`saas_accounting.py`) build their own plain blobs, were never
  patched by the census, and are deliberately untouched — the change covers exactly what was
  measured.
- `boundary_variant_census.py` is re-anchored to the adopted baseline: its self-check asserts
  the SHIPPED blob refuses mid-word hints and keeps stems, and `main()` now **red-exits on any
  per-row drift** between the shipped classifier and the measured prefix variant. Proven red
  under an in-memory substring revert, for the filed reason.
- 4 tests, 4 mutations, 0 survivors (`mutate_classifier_boundary.py`) — including the overshoot
  to a both-sides word boundary, which stays rejected.
- **Per the same ruling, still open and untouched: `internal_ops` reachability (the three
  staff-only desks) and the driving-school default.** Boundaries never touched them; the
  synthetic census's four remaining misses are exactly those.

### 2. 1.10 is CLOSED — CI observed green by a human

The owner opened run #11 of `preview-template-tests.yml` (push of `f019d39`) in a browser:
**Success, vitest 39/39 across 4 files, 27 s, 1 warning annotation.** First human observation
of this repo's CI; the row demanded exactly that and is done.

### 3. Dead nav data — measured, then deleted (`1df35e3`)

Three sessions listed, zero touched — closed by measuring first: extracted all 67 archived
workspaces (`docs/evidence/preview-workspaces.tar.gz`) and counted. 65 navigation objects,
every one with `public`+`admin`; the extra keys are per-role ids (`customer` ×48, `owner` ×18,
`staff` ×8, …) and **never `member`**, the only other key `app-nav.ts` reads; **zero imports**
of the `navItemsAdmin`/`adminNavItems` aliases — every page's `adminNavItems` is the
`useAdminNavItems()` hook local. Both writers deleted from `sync_mock_roles_navigation`
(`assemble.py`): the per-role loop and the alias block. Behaviour-identical on every archived
app. The existing test pinned the dead keys being WRITTEN — it now pins them staying dead, and
that the role routes still reach the sidebar through the admin list. 2 mutations (each writer
re-added), 0 survivors. No template file touched, so vitest is untouched.

### 4. The classifier's two remaining gaps — ruled "fix" on both, closed (`87cd085`)

- **Fix A (internal_ops reachability):** an internal-facing ASSERTION (`staff-only`,
  `not a public website`, `no customer ever`, `nobody outside`, `staff tool`, `internal tool`)
  beside ops/transactional language resolves `internal_ops` — guarded by `saas == 0`, because
  "an internal tool our design studio uses to run client projects" (SB-11) names an audience,
  not a product, and must stay a workspace. **The first cut flipped SB-11; the guard is what
  put it back, and it is mutation-pinned.** `back office` joins the ops hints.
- **Fix B (the zero-hint default):** `lesson` and `instructor` join the booking hints; the
  driving school books lessons instead of taking the art-gallery default.
- Wrap-measured (`docs/evidence/reachability-session15.json`): exactly the four intended
  synthetic briefs change; **20/20 on kind AND subtype for the first time; 0 of the 47 stored
  kind_contexts move.** All census tools re-run green — the synthetic corpus now drives
  `internal_ops/ops` from plain English.
- 6 tests, 5 mutations, 0 survivors (`mutate_internal_reachability.py`) — each of the rule's
  three guards has its own distinct catching fixture.

### 5. The `design_direction` dedupe guard — landed (`38d66f5`, earlier in the session)

- Both append sites (`apply_product_kind_to_plan` at `product_kind.py:877`,
  `apply_product_kind_to_architect` at `:1157` pre-change) now append the kind clause **once per
  dict**. Re-application — which `plan_phase`'s forcer path does 2-3× per run — is a no-op.
- **The guard keys on the full `PRODUCT_KIND={kind}/{subtype}` marker, not the bare
  `PRODUCT_KIND=` idiom** from the instructions site at `:1152`. Deliberate: if a forcer ever
  flips the kind (session 14 finding 1 — today it only re-confirms), the flipped kind still
  appends its own note, so the feedback loop keeps today's information content in all cases.
  A bare-prefix guard would silently swallow a flipped kind's note — that exact mutation is in
  the sweep and is caught.
- 3 tests in `tests/preview_app/test_product_kind.py`, 6 mutations in
  `scripts/cli/mutate_design_direction_dedupe.py`, **0 survivors** — including the inverted
  guard, both bare-prefix variants, and the skip branch's normalising assignment (pinned by a
  whitespace fixture so it is not a guard that cannot fail).
- `design_direction_census.py` re-run after the fix: **`transient_duplicate_chars` 0 on every
  kind**, was 263–591 per run. No production run needed and none spent — the seal already
  discarded the duplicates; nothing observable changes, exactly as session 14's demotion said.

**Suite: 1,873 passed / 1 skipped / 0 failed** (+6 over session 14: three dedupe tests, three
classifier tests). Vitest/`tsc -b` not re-run from here — no JS/TS touched; CI's own vitest run
is the 1.10 observation above.

**Pushed, twice.** The first push (`f019d39`) was this session's call — four sessions of
unpushed work on one disk was the risk the session-13 push existed to close — and it is the push
whose CI run the owner then observed. The classifier commits are pushed on the same standing.

---

## What I got wrong in session 15

- **First test run omitted the `pip install -q pytest` half of the documented command** — "No
  module named pytest" from the image, not a broken suite. The documented command's pip install
  is load-bearing; the failure is loud, but read it as the harness, not the code.
- **My first guest-house fixture did not bind (blind spot 1), and the mutation sweep caught me.**
  I gave it `gallery` + `menus`, so `storefront >= 2` short-circuited before the strong-signal
  branch the defect lives in — three of four mutations SURVIVED against it. The fix was SB-07's
  brief verbatim, which has a single storefront hit and genuinely reaches the branch. A sweep
  with survivors is the system working: read the survivor list before blaming the mutations.
- **A `git add` failed on pathspec because the working directory had drifted into `backend/`** —
  the operating note exists; use absolute paths or `cd` at the start of the compound command.

## Mutation results

- `mutate_design_direction_dedupe.py`: **6 mutations, 0 survivors, one sweep.**
- `mutate_classifier_boundary.py`: **4 mutations, 0 survivors** — after the fixture fix above;
  the first run had 3 survivors and each one was the fixture's fault, not the tests' subject.
- `mutate_dead_nav_data.py`: **2 mutations, 0 survivors** — each re-adds a deleted dead writer.
- `mutate_internal_reachability.py`: **5 mutations, 0 survivors** — the internal-facing rule's
  three guards each die to a different fixture, plus both new hint classes.
- `boundary_variant_census.py`'s adoption guard: **proven red under an in-memory substring
  revert**, failing with "shipped _blob regressed to bare substring matching" — red for the
  filed reason, file restored from the in-memory backup.
Run one at a time, every file restored from in-memory backups.

---

- **The plan and its evidence: [docs/PREVIEW_ROADMAP.md](docs/PREVIEW_ROADMAP.md).** Read the
  **session 15 callout** at the top of **Status**; session 14's callout and the classifier row
  UPDATE below it are still the live measurement record.
- **Before spending a trio: [docs/FIRST_FUNDED_TRIO_PREFLIGHT.md](docs/FIRST_FUNDED_TRIO_PREFLIGHT.md).**
- Why the pipeline shipped bad output: [docs/PREVIEW_QUALITY_FINDINGS.md](docs/PREVIEW_QUALITY_FINDINGS.md).

**If you read one thing: [The next step](#the-next-step).**

---

## State of the repo, in four lines

- **`main` is `83bb7c6` (the palette fix) on top of session 17's `fffeb3c`, plus the session-18
  docs/evidence commits — pushed.**
- **Suite: 1,893 passed / 1 skipped / 0 failed** (documented command). Vitest untouched (no
  JS/TS changed).
- **Credits: ~$10.26 left** (`total_usage 349.745` of `total_credits 360`). Session 18 spent
  **$3.01 telemetry-attributed** of the owner's $10 budget. The key is SHARED with another
  project (owner, 2026-08-07) — the "mystery spend" is closed; never alarm on idle usage again.
- **The running config is the adopted one, verified from the process:** TEXT=gemini-3-flash-preview,
  FIX=glm-5.2:nitro, PREVIEW_APP=deepseek-v4-pro, ARCHITECT=haiku-4.5, APPSPEC_MODE=off.

---

## The next step

Ordered by payoff; items 1-2 are single lines or single rulings that bank measured wins.

1. ~~The appspec ruling~~ — **RULED ON and FLIPPED, 2026-08-07 (same day, post-close).** The
   owner ruled after reading the head-to-head; `APPSPEC_MODE=on` in local `.env` (recreated,
   verified from the running process: `should_run=True`), appspec models kept on
   gemini-2.5-flash by the same ruling (they are what the 2/2 accepts were measured on).
   `.env.prod` already ran `on`. **Every future run is an acceptance data point — rejects now
   fail the request honestly, so count accepts vs rejects each session.** The keep-or-delete
   question from session 16 is closed: KEEP, ENFORCED.

   **And the appspec-model A/B already ran (owner-requested, runs 114/115): gemini-3-flash-preview
   REJECTED 0-of-5 spec revisions** (deterministic_validation_failed — a page authored with two
   initial states — then semantic_coverage_failed; both requests failed honestly in 72/168 s,
   $0.17 total). **Reverted to gemini-2.5-flash, verified live.** The spec slots' October
   migration is OPEN with gemini-3 ruled out as-is; candidates are haiku-4.5 or gemini-3 after
   a prompt/schema fix for the initial-state cardinality. MODEL_RESEARCH experiment 4 has the
   table.
2. **`QUALITY_FIX_MODEL=z-ai/glm-5.2:nitro`** — same routing arithmetic as FIX_MODEL, its
   base-glm call failed truncated on 112; one line, one run beside it.
3. **The catalogue-contract vocabulary gap** — "missing directory face component:PageHeader,
   missing BRAND_MANIFEST services binding" caused 5 of this session's 6 contract rejections
   and the writer repeats it verbatim on retry. A prompt-vocabulary fix in the slot_fill
   contract block, offline-draftable, judged on the next funded run's rejection count.
4. **The starvation attack is now the p50 work.** With gemini-3 the serial pre-codegen cost is
   ~245 s; appspec-on cuts planning further. The remaining big rocks: haiku planning writers
   failing by token budget (filed — budget/model change + run) and codegen running to the
   deadline by design. Measure before moving anything.
5. **The gallery residual now has teeth** — run 111 failed SHIP on it. The remaining cause is
   plan-stage: the plan's pages don't resolve menu→catalogue before the gap-fill runs. Also
   AboutPage in rejections says `0e678fa` is half a fix (plan page). Both are plan_phase work;
   both want a run beside them.
6. **VISION_MODEL migration** beside TEXT_MODEL (October clock), after a vision-touching run.

**Owner decisions:** the appspec ruling (item 1 — the measured recommendation is ON); p50 →
Phase 2 under (A); SiteSpec vs AppSpec; the `state_ids` backfill; relaxing the AppSpec schema.
The 1.12 roadmap row needs REWRITING (its degraded-ship premise is dead — see the one-pager);
that rewrite is a session task, not a ruling.

---

## Binding owner constraints — these do not expire

- **Fix the PIPELINE, never a generated preview.** Reading workspaces for evidence is fine.
- **Generation must not exceed 10 minutes.** A degraded ship happens INSIDE the cap or not at
  all; none of 1.12's fallbacks buys time.
- **Every fix gets a test that fails with the fix reverted**, proven by mutation from an
  in-memory backup, never `git checkout`.
- **Work the roadmap in order.** Phase 1 is not finished — 1.10 and 1.11 are open.

### The rule that has caught the most defects

**Mutation-test every guard.** Twenty-six drivers in `backend/scripts/cli/mutate_*.py`, one in
`preview-template-tests/tools/mutate.py`. **Run one sweep at a time.**

Ten blind spots, all found the expensive way (restated in full in session 14's handoff at
`369d5a7`; check for each by default):

1. Asserting against the case that does not bind.
2. Driving the consumer, never the producer — or the reverse.
3. Guards that cannot fail.
4. Fixtures too small to reach the rule — or the code path at all.
5. A test that adapts until it passes cannot fail — including through the fixture.
   **Fake a model with the model.**
6. Never assert against the constant a mutation would change.
7. A fix that changes no outcome is not a fix.
8. A measurement that paraphrases the code measures the paraphrase — drive the real function;
   execute old code from `git show`, never re-derive it.
9. A mutation can apply cleanly and still be a no-op — anchor on the last statement whose effect
   you mean to destroy.
10. A labelled measurement row measures its label, not its content — assert `resolved ==
    labelled` inside the tool, red exit on mismatch; a revert-proof must be red for the filed
    reason, from the right process's exit code.

Assume any DoD row you did not personally mutate is unproven.

---

## Operating notes — every one has cost real time

All of session 14's notes stand (`369d5a7`); the load-bearing ones:

| | |
|---|---|
| **Probe credits BEFORE anything else** | Item 0's one-liner. Fourth session where this was the first act and the right one |
| **Resolve config from the RUNNING PROCESS** | Never from a previous session's note; `backend/.env` is not tracked |
| **`restart` reloads code; it does NOT reload `env_file`** | `up -d --force-recreate` — and dump the log first, recreate destroys it |
| **The test command** | `docker run`, never `docker compose exec` — and its `pip install -q pytest` half is load-bearing, the image does not ship pytest |
| **The 47 kind_contexts are archived** | `docs/evidence/preview-routes.json`, key `kind_context` — classifier measurements need no DB |
| **`preview_app.design_direction` is the SEALED direction** | Anything appended between the kind locks and the seal is invisible downstream — and as of `38d66f5` it is one clause per dict anyway |
| **No `git` in the test image** | Extract old files on the host (`git show ref:path > file`) |
| **`industry` is `Form(None)`** | Always set it. Host port **8001**, multipart, no trailing slash |
| pytest | **Read the SUMMARY LINE, never the exit code** |
| Working directory | Drifts between tool calls — absolute paths |
| Archive what you measure | Or it is unverifiable next session |

### Running the offline census tools

```bash
docker run --rm -v "$REPO:/repo" -w /repo/backend \
  -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api \
  -c 'python3 scripts/measure/boundary_variant_census.py'          # classifier variants, both corpora
  -c 'python3 scripts/measure/design_direction_census.py'          # kind-clause sizes — duplicates now 0
  -c 'python3 scripts/measure/deterministic_paths_census.py'       # 1.12 per kind — label-asserted
  -c 'python3 scripts/measure/synthetic_kind_census.py --explain'  # the 20 briefs
```

DB-reading tools run via `docker compose exec api python /app/backend/scripts/measure/...`.
Postgres credentials are `-U bmv -d buildmyversion`.

---

## What is still broken

Ordered by what I would do first. Every item has evidence; none is speculative.

### 1. The account is empty and ~$40 over two days is unaccounted for
FOURTH session blocked on it. Nothing on this list moves until it does.

### 2. Nine fixes are mutation-proven and production-unproven
Sessions 11–15's (the dedupe guard and the classifier adoption join the seven; the dedupe needs
no run, and the classifier is corpus-proven over all 47 stored contexts + 20 briefs — a funded
run adds one live data point, not the proof). 1.12's matters most — it is a fallback and a
healthy run never exercises it.

### ~~3. The classifier~~ — fully closed this session
Boundary matching adopted (`9c5b383`), both reachability gaps ruled "fix" and landed
(`87cd085`). 20/20 exact on the synthetic corpus, 0 of 47 stored runs moved, all sweeps clean.
What remains classifier-adjacent is only the live data point a funded run adds.

### 4. Page identity is fixed in shadow and not under enforcement
Unchanged (`capability_ids` unread by `_search_text`).

### 5. p50 is 563-570 s against a ≤ 500 s DoD
Unchanged; recommendation (A); owner ruling pending; the row is not moved.

### 6. `slot_fill` rejects 25 of 42 fills and the distribution is still unmeasured
Needs item 1's log dump.

### 7. `_design_system_dict` discards four of six derived colours
Structural and certain; wants a run beside the fix.

### 8. 1.11 — the reserve is unbounded as a whole
Unchanged. Measure pages-judged and wall clock separately.

~~1.10 — green on `main` is unverified~~ — **closed**, observed green by the owner (run #11).

### ~~9. Dead nav data~~ — closed this session (`1df35e3`)
Measured over the 67 archived workspaces before deleting: per-role navigation keys read by
nothing (never `member`, the one other key the template reads), aliases imported by nothing.
Both writers deleted from `sync_mock_roles_navigation`; 2 mutations, 0 survivors.

~~design_direction pile-on~~ — **closed**, `38d66f5`, this session.

---

## Next session's prompt, ready to paste

```
Read HANDOFF.md first — "Session 22, in one page" and THE TALLY. Then the roadmap's
session-22 callout AND the R-table's session-22 status block. Don't re-derive any of it.

main is PUSHED through 41fd68d. Suite 2,012 / 1 / 0. The key is SHARED — probe credits
first, bracket every run, track BMV spend from ai_usage_events, never alarm on idle
deltas; ~$7.86 left at session-22 close. Running config verified at close: TEXT
gemini-3-flash-preview, FIX + QUALITY_FIX glm-5.2:nitro, PREVIEW_APP deepseek-v4-pro +
PREVIEW_APP_TRANSPORT_FALLBACK_MODEL anthropic/claude-haiku-4.5, ARCHITECT/CRITIC
haiku-4.5, APPSPEC on + gemini-2.5-flash ×3 + fallback haiku, prompt revision 2026-08-07.2.

MY BUDGET: $7 — a CAP, not a target, and it is most of what's left on the key: spend it
only where a run buys a reading you cannot get offline. Time box 3 HOURS; reserve the
last 20 minutes for close-out. 10-minute cap per generation, monitored, always. We work
LOCALLY — prod files only change when I say so.

THIS SESSION RUNS ON YOUR JUDGMENT. The backlog below is my recommended order, not a
script: you have standing authority to reorder, drop, split, or merge items when the
evidence in front of you says so — and to chase a defect you can prove from stored
evidence even if it is not listed. When you deviate, record WHY in the handoff. You do
not need to ask before: launching a weather-gated run inside the cap, landing a
mutation-proven fix, or archiving/committing/pushing your work. What stays absolute no
matter what you choose: the PARKED list, the NON-NEGOTIABLEs, fail-closed over clever,
and the tally reported honestly.

THE BACKLOG (my order — yours to re-order with reasons):

1. THE EMPTY-TUPLE REJECT CLASS — the flagship (~45-60 min + one run). 143's artifact is
   ALREADY MINED (session-22 next-step item 3; don't re-derive): revs 1-3 authored EMPTY
   pages/states arrays; revs 4-5 a placeholder "Page1" page with no states and nothing
   anywhere to reconcile from; rev 5 reproduced rev 4's validator errors IDENTICALLY.
   Land the trio as one neighborhood:
   (a) teach the authoring prompt — every page lists >=1 state_id, real PAGE-*/STATE-*
       ids, never placeholders (session-20 pattern, mined shapes verbatim);
   (b) the app_spec_repair.j2 translation for the schema-parse minItems class ("that
       page is stateless — author its default state, initial:true, reference it in
       state_ids; never resend the page unchanged");
   (c) identical-revision early stop — when a repair revision reproduces its parent's
       IDENTICAL validator error set, fail then instead of spending the remaining
       budget (R2 inside the repair loop; 143 pays 3 revisions instead of 5).
   NO deterministic heal — states are decision-carrying (R3) and 143 proves there is
   nothing to back-fill from. Bump the prompt revision (2026-08-07.3), mutation-pin each
   part, ONE Osteria run beside it. Judge on accepts, whether repairs stop repeating
   identical errors, and revisions-to-verdict.

2. THE FREE READS — ride item 1's run (or any healthy run past codegen), ~15 min offline:
   the R1+R2 slot_fill read that never bound in session 22 — contract-rejection count,
   "How to repair:" present in any contract retry prompt, attempt-2 outcomes, any
   attempt=3 slot_fill rows (the rung). Plus the standing free observables: design_manifest
   success, planning serial, tail state vs the R5 table.

3. R6 (~30-45 min, offline-provable): writer/attempt scoping on stages still hitting the
   admin_ops.py:330 fallback (writer=None, attempt=1) — find them with a telemetry query
   over recent runs FIRST; and refund errored $0 calls from the appspec call budget.
   Mutation sweep per fix, suite green.

4. R3 AUDIT (offline, no code, ~30 min): classify slot_fill-contract and architect-JSON
   failure codes into decision-carrying vs decorative from stored reject evidence. The
   deliverable is the classification table in the roadmap, not edits.

5. R5 — ONLY if I have ruled on the tail reservation by the time you read this (the
   measured table is in the roadmap): implement TAIL_RESERVE_SECONDS per the
   recommendation, mutation-pinned, one run beside it. No ruling = stays parked.

6. R1's REMAINDER if time remains: coverage_review's one-shot retry is still same-model;
   survey any remaining single-provider ask sites (architect and fix_agent already have
   chains).

Standing rulings so you never wait: R4 is DONE and live-proven (run 144 shipped the
135-shape); never lower the gate (OPS_MIN_NON_HUB_PAGES=4 is pinned). Retries must differ
(R2); fallbacks are classify-first + bounded + cross-provider (R1); leniency never reaches
decision-carrying fields (R3). If the ship gate's ops floor EVER fires again it is a NEW
bug — file it loudly. Quality failures NEVER take a model fallback — they repair or fail
closed; the transport rungs are for weather only.

WEATHER GATE before any run: two long json_object probes on the spec model (~$0.06),
probe-parse as tolerant as the pipeline's (fences healthy; the storm class is
finish_reason=error / $0 / partial body). LAUNCH: POST /api/requests (never /api/v1),
multipart, industry always set, host port 8001.

STANDING TALLY: ships vs attempts AND accepts vs rejects, every reject classified from
telemetry before any relaunch. A transport-classified dead run at ANY appspec ask site is
a NEW bug. The rev-1 streak ended at 3 — start the new count honestly.

PARKED (touch only with my ruling): ARCHITECT_MODEL, the <=500 s p50 DoD row, R5's
behavioral half (unless ruled — item 5), schema-level conditional assertion requirements,
relaxing the AppSpec schema, the October spec-slot migration (both candidates ruled out
as-is).

NON-NEGOTIABLE: pipeline never previews; every fix mutation-proven from in-memory backup,
one sweep at a time, red for the FILED reason; suite via docker run WITH its pip install
half; recreate never restart; config from the running process; archive logs the moment
each run finishes; no code edits while a generation is in flight (sweeps count — the api
container bind-mounts the repo); absolute paths; 10-minute cap.

BEFORE YOU FINISH (the reserved 20 min): .env in the state the evidence supports and
verified from the running process; the R-table statuses updated in the roadmap;
HANDOFF/MODEL_RESEARCH updated with real numbers including the ships-vs-attempts line;
push; next prompt written; tell me plainly what each run cost, what landed, what you
chose to reorder and why, and what's left.
```

## Session 21's prompt (historical — superseded above)

```
Read HANDOFF.md first — "Session 21, in one page" and THE TALLY. Then the roadmap's
session-21 callout AND the "Reliability hardening backlog — owner-directed" table (R1-R7)
right below it, including R4's recorded ruling. Don't re-derive any of it.

main is PUSHED through session 21's commits (d19bf81 + the R4 ruling). Suite 1,967 / 1 / 0.
The key is SHARED — probe credits first, bracket every run, track BMV spend from
ai_usage_events, never alarm on idle deltas; ~$11.24 left at session-21 close. Running
config verified at close: TEXT gemini-3-flash-preview, FIX + QUALITY_FIX glm-5.2:nitro,
PREVIEW_APP deepseek-v4-pro, ARCHITECT/CRITIC haiku-4.5, APPSPEC on + gemini-2.5-flash ×3,
APPSPEC_TRANSPORT_FALLBACK_MODEL anthropic/claude-haiku-4.5, prompt revision 2026-08-07.1.
My budget this session: $10 — a CAP, not a target; expected spend is ~$2-3. My time box:
3 HOURS — plan for it: two rows LANDED and mutation-proven beat five rows touched; reserve
the last 20 minutes for close-out. 10-minute cap per generation, monitored, always. We work
LOCALLY — prod files only change when I say so.

THIS SESSION IS THE R-BACKLOG, best practices always. Standing rulings so you never wait:

- R4 is RULED (2026-08-07): the defense-in-depth ladder, gap-fill variant — (1) ONE floor
  constant shared by the gate and the prompt render (derive, never duplicate — the
  face_prompt.py pattern), (2) a per-kind floor line in app_spec.j2 rendered for ops kinds
  only, (3) ops gap-fill to the floor with a PATH-KEYED unserved test (the skeleton-keyed
  test collides on ops-list and adds zero pages — session 21 proved it), (4) seed-time
  refusal if still under floor (fail in seconds, not minutes), (5) the ship gate UNTOUCHED
  as backstop — if it ever fires again it is a NEW bug, file it loudly. Never lower the
  gate. Never prompt-only.
- Retries must differ (R2); fallbacks are classify-first + bounded + cross-provider (R1);
  leniency never reaches decision-carrying fields (R3).

WEATHER GATE before any run: two long json_object probes on the spec model (~$0.06) — the
probe must tolerate what the pipeline parser tolerates (markdown fences are healthy;
finish=length on an oversized ask is the probe's fault; the storm class is
finish_reason=error / $0 / partial body).

LAUNCH MECHANICS (session 21 paid the 404 so you don't): POST /api/requests — NOT /api/v1 —
multipart, industry always set, host port 8001; the duo3 + dispatch briefs are archived
verbatim in docs/evidence/session21/briefs-129-132-135.jsonl.

Work in order — judge each yourself, stop cleanly when the clock says so:

1. R5 MEASUREMENT ONLY (~20 min, free, offline): the codegen/tail split from stored stage
   timings (runs 129-142 all carry them). Deliverable: the measured table in the roadmap +
   your recommendation. NO behavioral change — the reservation split is mine to rule on
   with the numbers in front of me.

2. R1+R2 AT SLOT_FILL as one neighborhood (~60-90 min, the biggest block): the
   highest-volume ask site has NO model fallback (1.12(b) proved scaffolds ship to the gate
   when the writer is unroutable) and a verbatim contract retry (session 18's
   byte-identical message — the writer never sees the validator feedback). Classify
   transport first (reuse the appspec predicate pattern), ONE bounded cross-provider rung,
   corrective retry that feeds the validator report back, config slot for the fallback
   model, telemetry attempts distinct. Mutation sweep per fix, suite green. ONE funded run
   reads both (contract-rejection count + retry-2 outcomes vs the session-18 baseline).

3. R4 THE LADDER (~45-60 min, ruled above): census with the existing harness
   (ops_home_seed_census.py + the run135-fullchain-replay pattern — 135's stored artifact
   must fill to the floor and pass the FULL chrome gate offline), mutation-pin each rung,
   then ONE dispatch-desk run (135 brief verbatim). It must ship or fail on something NEW.

4. R7 (~15 min): the startup warning in assert_safe_runtime_configuration when
   APPSPEC_TRANSPORT_FALLBACK_MODEL shares a provider prefix with
   APPSPEC_MODEL/APPSPEC_REPAIR_MODEL. Warn, never crash. Mutation-pin.

5. R6 if time remains: writer/attempt scoping on stages still hitting the admin_ops
   fallback (writer=None, attempt=1); refund errored $0 calls from the appspec call budget.

6. R3 audit LAST and only if time truly remains (offline, no code): classify the other
   strict parsers' failure codes (slot_fill contract, architect JSON) into
   decision-carrying vs decorative, from stored reject evidence. The deliverable is the
   classification, not edits.

STANDING TALLY: ships vs attempts AND accepts vs rejects, every reject classified from
telemetry before any relaunch. A transport-classified dead run at ANY appspec ask site is a
new bug. Keep counting the rev-1 streak (3-for-3 at session-21 close).

PARKED (touch only with my ruling): ARCHITECT_MODEL, the ≤500 s p50 DoD row, any R5
behavioral change, schema-level conditional assertion requirements, relaxing the AppSpec
schema, the October spec-slot migration (both candidates ruled out as-is).

NON-NEGOTIABLE: pipeline never previews; every fix mutation-proven from in-memory backup,
one sweep at a time, red for the FILED reason; suite via docker run WITH its pip install
half; recreate never restart; config from the running process; archive logs the moment each
run finishes; no code edits while a generation is in flight; absolute paths; 10-minute cap.

BEFORE YOU FINISH (the reserved 20 min): .env in the state the evidence supports and
verified from the running process; the R-table statuses updated in the roadmap;
HANDOFF/MODEL_RESEARCH updated with real numbers including the ships-vs-attempts line;
push; next prompt written; tell me plainly what each run cost, what landed, and what's
left.
```

## Session 20's prompt (historical — superseded above)

```
Read HANDOFF.md first — "Session 20, in one page" and its tally table. Then the roadmap's
session-20 callout. Don't re-derive any of it.

main is PUSHED through session 20's commits. Suite 1,939 / 1 / 0. Key is SHARED — track BMV
spend from ai_usage_events, bracket with the credits probe, never alarm on idle deltas;
~$17.47 left at session-20 close (topped up to 380 total). Running config verified at close:
TEXT gemini-3-flash-preview, FIX + QUALITY_FIX glm-5.2:nitro, PREVIEW_APP deepseek-v4-pro,
ARCHITECT/CRITIC haiku-4.5, APPSPEC on + gemini-2.5-flash ×3, prompt revision 2026-08-07.1.
My budget this session: $[N]. 10-minute cap per generation, monitored, always. We work
LOCALLY — prod files only change when I say so.

STANDING TALLY: count appspec accepts vs rejects, classify every reject from telemetry
(transport is now survivable at all ask sites — a reject means spec quality), and record
rev-1 vs repair-accept per run (the prompt-revision stamp makes this queryable).
Cross-session enforced record on the duo3 briefs: 7 accepts / 6 quality-rejects.

Work in order (items renumbered after the post-close runs — the baseline runs and the p50
measurement are DONE, see "Post-close" in the one-pager):

1. The October migration duo for the APPSPEC slots — now judgeable properly: candidates
   anthropic/claude-haiku-4.5 and gemini-3-flash (its 114 failure shape — initial-state
   cardinality — is now both taught in the prompt AND translated in repair). One slot
   change, one duo minimum, judged on accepts AND rev-1-vs-repair mix per prompt revision
   (2-of-3 session-20 accepts came via repair — the repair translation is earning). At
   ~50% acceptance on gemini-2.5-flash this is the biggest customer-visible lever. Probe
   the provider's weather FIRST (session 20 lost 3 of 9 runs to error-cut streams).

2. The ops-home enforcement gap, NEW from run 135: an internal_ops app under enforced
   appspec seeded a route table with no ops home — quality gate refused honestly
   (`ops_kind_missing_home:architect.routes`), AI repair refused past-deadline. Find where
   the appspec architecture seed (projection.py) intersects the ops-kind chrome contract;
   fix at the seed, census over stored ops kind_contexts, mutation-pin, one dispatch-desk
   run to confirm.

3. The coverage determinism trap, from run 133: coverage_review returned byte-identical
   malformed output twice (temp 0), so generation's one-shot retry buys nothing on
   malformation — only on transport. Either vary the retry (temp bump / compact
   instruction, like the authoring loop's) or validate leniently; measure which
   model_validate failure fired first (the artifact is in the DB).

4. p50: the measurement is done (architect 73-221 s + appspec repair revisions are the
   serial big rocks; tail still starves). Attack only with the owner's rulings in hand —
   ARCHITECT_MODEL is quality-parked, the ≤500 s row is owner-parked.

5. VISION_MODEL migration (October clock) beside a vision-touching run; filed code items:
   the generation/sanitize import cycle, schema-level conditional assertion requirements
   (owner decision), refunding errored $0 calls from the appspec call budget.

NON-NEGOTIABLE: pipeline never previews; every fix mutation-proven from in-memory backup,
one sweep at a time, red for the FILED reason; suite via docker run WITH its pip install
half; recreate never restart; config from the running process; archive logs the moment each
run finishes; no code edits while a generation is in flight; absolute paths; 10-minute cap.

BEFORE YOU FINISH: .env verified from the running process; HANDOFF/roadmap/MODEL_RESEARCH
updated with real numbers including the accept/reject tally; push; next prompt written;
tell me plainly what each run cost, what landed, and what's left.
```

## Session 19's prompt (historical — superseded above)

```
Read HANDOFF.md first — "Session 19, in one page", its tally table, and "The next step".
Then the roadmap's session-19 callout. Don't re-derive any of it.

main is PUSHED through session 19's four commits. Suite 1,907 / 1 / 0. The key is SHARED —
track BMV spend from ai_usage_events, bracket with the credits probe, never alarm on idle
deltas. ~$4.99 left on the key. Running config verified at close: TEXT gemini-3-flash-preview,
FIX + QUALITY_FIX glm-5.2:nitro, PREVIEW_APP deepseek-v4-pro, ARCHITECT/CRITIC haiku-4.5,
APPSPEC on + gemini-2.5-flash. My budget this session: $[N]. 10-minute cap per generation,
monitored, always. We work LOCALLY — prod files only change when I say so.

STANDING TALLY: count appspec accepts vs rejects for every run, and CLASSIFY each reject
from telemetry before repeating a launch (session 19's rule: finish_reason=error + 0 tokens
= transport, not spec quality). Cross-session record on the duo3 briefs: 5 accepts /
4 quality-rejects.

Work in order:

1. FIRST HEALTHY RUN reads item 4's free observables: design_manifest SUCCEEDS in the log
   (was 0-for-all on haiku; now asks TEXT_MODEL) and planning serial ~22 s. If the provider
   is still cutting streams (session 19: error-cut authoring at 1k-34k chars), don't fight
   it — the gate now fails those honestly; do offline work and retry later.

2. The gallery residual, now precisely located at PLAN stage: _ensure_role_pages's
   thin-branch appends _storefront_pages() (gallery + ArtworkDetail literals) into any
   thin role with no serve-aware check — proven by 124's experience_plan.roles[1].pages
   ("Gallery"/"Artwork" nav links, gallery_detail page) while the ROUTE table stayed clean
   (bbe6359 holds). Make the plan-stage seeding resolve menu/catalogue the way the
   scaffold's force_catalog_browse leaf rule does; fix AboutPage's plan-page public-detail
   half in the same neighborhood; wrap-measure with gallery_gapfill_census.py (47 stored
   kind_contexts must not regress); mutation-pin; ONE duo: restaurant ships no gallery
   PLAN PAGES and no Gallery/Artwork nav labels, hotel unchanged.

3. Transport re-ask for appspec repair/coverage/schema_repair calls — the gate's residual:
   they classify honestly now but one errored call still kills the run (123, 128). Same
   bounded re-ask shape as build_app_spec_candidate. Mutation-pin.

4. Appspec authoring prompt/schema hardening: mine app_spec_revisions'
   deterministic_validation_json for the recurring reject shapes (state assertions missing
   state_id; evidence references cited but never declared; initial-state cardinality —
   gemini-3's 114 failure is the same family). Teach the prompt those three shapes.
   Offline-provable half first; judge on accepts over the next runs.

5. IF the provider is healthy and budget remains: three enforced runs on NEW briefs
   (different industries, industry field always set) to widen the acceptance baseline.

NON-NEGOTIABLE: pipeline never previews; every fix mutation-proven from in-memory backup,
one sweep at a time (and a sweep's red must be red for the FILED reason — session 19 caught
an infrastructure-red masking a real survivor); suite via docker run WITH its pip install
half; recreate never restart; config from the running process; archive logs the moment each
run finishes; no code edits while a generation is in flight; absolute paths; 10-minute cap.

BEFORE YOU FINISH: .env verified from the running process; HANDOFF/roadmap/MODEL_RESEARCH
updated with real numbers including the accept/reject tally; push; next prompt written;
tell me plainly what each run cost, what landed, and what's left.
```

## Session 18's prompt (historical — superseded above)

```
Read HANDOFF.md first — "Session 18, in one page" and "The next step" (note the post-close
additions: appspec is ON by my ruling, and the appspec-model A/B already ran — gemini-3
rejected 0/5 specs and was reverted; the spec slots stay on gemini-2.5-flash). Then the
roadmap's session-18 callout and MODEL_RESEARCH "Funded-session results" incl. experiment 4.
Don't re-derive any of it.

main is PUSHED through f31f9d9. Suite 1,893 / 1 / 0. The key is SHARED with my other
project — track BMV spend from ai_usage_events, bracket runs with the credits probe, never
alarm on idle-time balance changes. The running config is verified: TEXT gemini-3-flash-
preview, FIX glm-5.2:nitro, PREVIEW_APP deepseek-v4-pro, ARCHITECT/CRITIC haiku-4.5,
APPSPEC on + gemini-2.5-flash. My budget this session: $[N]. 10-minute cap per generation,
monitored, always. We work LOCALLY — prod files only change when I say so.

STANDING TALLY: appspec is enforced, so EVERY run is an acceptance data point (baseline
2/2 rev-1 accepts on 109/110; a reject fails the request honestly). Report accepts vs
rejects for the whole session.

Work these in order — each numbered item is ONE variable with its own run(s); do not stack
two changes into the same duo:

1. QUALITY_FIX_MODEL=z-ai/glm-5.2:nitro (backend/.env line ~44). The evidence already
   exists (FIX_MODEL probe + run 112: base-glm quality_repair failed truncated while the
   nitro fix call succeeded) — this duo is confirmation, not discovery. Recreate, verify
   from the running process, run launch_duo3.sh, judge: quality_repair success/latency vs
   run 112's failures, plus the standard telemetry. Adopt or revert yourself.

2. WHILE that duo runs (docs only, no host contention): rewrite the roadmap's 1.12 row to
   pin what runs 111/112/113 proved — an unroutable architect is absorbed by the model
   fallback chain; slot_fill has NO fallback and scaffolds fail the quality gate honestly
   inside the cap; an unroutable TEXT fails at blueprint in 4 s / $0. The row's DoD becomes
   "fail fast, fail honest, stored failure state, customer retry works" — the degraded
   blueprint ship it used to demand does not exist. Cite the three runs.

3. The catalogue-contract vocabulary gap — the highest-payoff pipeline fix.
   Evidence: "catalogue-contract: missing directory face component:PageHeader, missing
   BRAND_MANIFEST services binding" caused 5 of session 18's 6 contract rejections
   (docs/evidence/session18/slot_fill_rejections.txt), and run 107 proved the writer
   repeats the violation BYTE-IDENTICAL on a retry that carried the validator errors — the
   prompt does not teach the vocabulary the validator grades. Find where the slot_fill
   contract block renders (the catalogue-contract enforcement text) and make the prompt
   state, in the writer's own terms, what "directory face PageHeader" and "BRAND_MANIFEST
   services binding" require — with the component/binding names it must emit. Offline-
   provable half: a render test that the new wording reaches the prompt (variable-audit
   style), mutation-pinned. Then ONE duo, judged on: contract rejections (baseline 5/6 of
   that class), slot_fill acceptance (baseline 31%/28%/36% across session-18 duos), pages
   shipping real content vs scaffold. Adopt/revert yourself and record the counts.

4. The haiku planning budget failures — the cheapest remaining starvation cut.
   design_manifest fails on EVERY run: exactly 1,500 completion tokens, 0 output chars,
   finish_reason=length (~12-13 s + cost wasted, then a fallback does the work);
   plan_validation did the same at 14,000 until gemini-3's tighter plans made it fit, so
   treat it as fragile, not fixed. Find where those two calls set max_tokens and either
   raise the budget or route the writers off haiku (ARCHITECT_MODEL stays — the architect
   call itself is good). ONE change, mutation-pinned where a guard changes, then one run:
   design_manifest must SUCCEED in the log and planning serial time must not regress
   (baseline ~22 s under appspec-on).

5. The gallery residual at plan stage — now a ship-killer, not cosmetics (run 111: visual
   critic scored the gallery pages 30/40, visual_defect_severe ×3, run failed). Root cause
   from session 18: at gap-fill time the plan's pages do not yet resolve menu→catalogue,
   so served_kinds misses public-catalog and _storefront_pages()'s /gallery +
   /gallery/:id → ArtworkDetailPage literals ride in (product_kind.py ~1035-1119; fired on
   103/107/111, not 105/109 — the census's 2-of-6 residual). Make the plan-stage check
   resolve a menu/catalogue page the same way the architect-stage check does, and in the
   same plan_phase neighborhood check AboutPage's public-detail assignment (0e678fa's
   unfixed half — AboutPage appeared in session-18 rejections with a full-skeleton
   violation). Wrap-measure with gallery_gapfill_census.py before/after (the 47 stored
   kind_contexts must not regress), mutation-pin, then one duo: the restaurant must ship
   with NO /gallery route and NO ArtworkDetailPage, hotel unchanged.

IF BUDGET REMAINS after all five: three enforced-appspec runs on NEW briefs (not the duo3
pair) to widen the acceptance baseline past n=2 — different industries, industry field
always set, count accepts.

NON-NEGOTIABLE: pipeline never previews; every fix mutation-proven from in-memory backup,
one sweep at a time; suite via docker run WITH its pip install half; recreate never
restart; config from the running process; archive logs for every run (dump the moment each
finishes); no code edits while a generation is in flight (bind mount); working directory
drifts — absolute paths; 10-minute cap, monitored.

BEFORE YOU FINISH: .env in the state the evidence supports and verified from the running
process; HANDOFF/roadmap/MODEL_RESEARCH updated with real numbers (including the appspec
accept/reject tally); push; next prompt written; tell me plainly what each run cost, what
landed, and what's left.
```
