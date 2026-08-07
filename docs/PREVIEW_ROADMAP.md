# Preview pipeline roadmap — variety and latency

**Written:** 2026-08-01 · **Baseline:** `90f4d5f` · **Suite:** 1,107 green

Two goals, in the owner's words: *"most generations are the same template which is getting
disgusting"* and *"I don't want the generation to take more than 10 minutes."*

This plan is grounded in a six-part audit of the tree, three adversarial reviews of an earlier
draft (all three returned **unsound**, 9 fatal objections), and one controlled experiment —
requests 68 and 70, same business, one field different.

---

## The no-generation window (2026-08-03, two days) — scope and rationale

The OpenRouter account is out of credits, so **no live generation can run.** This section is the
plan for that window. It is deliberately in the roadmap rather than in a handoff: what a team does
when its most expensive instrument is unavailable is a roadmap decision, not a process note.

**The framing.** Credits are the scarce resource, so a no-generation window has exactly two jobs:

1. **Land everything that never needed a generation.** Several open items have been waiting on
   credits they do not require, including the largest block of known defects in the repo.
2. **Make the first funded trio maximally informative.** As of today a trio answers roughly two open
   questions. It should answer eight. Every instrument added this week is a question that trio
   answers for free — and the marginal cost of asking more of a single run is nearly zero.

**What makes this possible:** 58 generated workspaces (requests 11-91) and the trio 2-5 telemetry in
`ai_usage_events`. Most Phase 2 questions are census questions over that corpus, and a census needs
no model. Both are now archived in [`docs/evidence/`](evidence/) — they were living in a docker
volume and a session scratchpad respectively, one cleanup away from taking several published numbers
with them.

### Day 1 — the offline defect backlog

| # | Work | Why it needs no generation |
|---|---|---|
| 1 | **The 8 xfails** — 7 in `test_catalogue_contract.py`, 1 in `test_phase5_ui_alias_imports.py` | Each is a filed defect whose reproduction is already written. Fix what is fixable; for each one that is not, record *why*, so it stops being re-triaged every session |
| 2 | **2.9 slot-fill retry** | `_slot_fill_rejection` does not treat a contract-invalid page as a rejection, so `_MAX_SLOT_FILL_ATTEMPTS` never fires — 26 pages across requests 74-79, zero retries. Pure unit-testable logic |
| 3 | `AiFeaturePanel.tsx:44` hardcodes `/ai-features` | Template source, provable in the vitest harness 1.10 just stood up |
| 4 | `visual_review_status: None` → `unmeasured` | Fixes the telemetry *before* the next trio is collected through it |

Item 2 carries a known cost: it lives in `generate.py:269-489`, exactly the range Phase 2's 2.4-2.5
deletes, so it is throwaway work. Do the minimal version anyway — it is the measured root of the
"everything looks the same" complaint and Phase 2 is 8-10 weeks out.

**Item 1: 8 of 8 closed.** Five were tests that had stopped testing anything — two mutation decoys
whose anchors had drifted, one assertion that was green because its `str.replace` was a no-op, one
pinning prompt *prose*, one guessing at a number it never measured. The class fix is `_mutated()`,
which refuses to return an unmutated string. The sixth was 2.9.

The last two were real, and **both were hiding a live defect rather than being stale markers**:

- **The skeleton-contract size bound** (`0082f5f`). The pinned 4,000 had no derivation. Retiring it
  meant finding the real ceiling, which is the callers' `bounded_json(contract, 5000)` — and above
  5,000 chars that function stops bounding and starts *mutating*, clipping every list to 12 items.
  `public-catalog` (5,296 chars, 30 components) was shipping **12** to the model, silently missing
  the `MarketingHero` and `ProductShowcase` its own `slot_components` assigned to that page's hero
  and showcase slots. Fixed by splitting the complete validator view from a deliberately
  budget-fitted prompt view; the validator still needs the full list or legitimate components become
  `forbidden @/ui component` errors. **The token cost is essentially unchanged** — ~1.2k saved out
  of ~18k a run. Stating the allow-list once per run is the fix for that and is a separate, larger
  change.
- **`write_file` canonicalization** (`614d772`). The rename is deliberate and stays: leaving the
  pre-canonical file means the import guards "fix" a duplicate page and Vite bundles both. What was
  wrong is that callers recorded the path they passed in, which no longer exists. `write_file` now
  returns the path it wrote. Three assertions across two test files were pinning the defect.

**Item 2: done.** See the 2.9 row in the defect table below.

**Item 3 (`AiFeaturePanel`): done** (`430453a`). The archive revised the rate: **5 of the 41
workspaces that render the panel have no `/ai-features` route** (32, 36, 45, 47, 77), not 1 in 9.
The template's catch-all redirects unknown paths to `/` instead of 404ing, which is why a dead link
behaved like a working one.

**Item 4 (`visual_review_status`): done** (`2d69917`), and **deliberately not as specified.** The
brief said `None` → `unmeasured`; `unmeasured` already means "the critic ran, had pages, judged
none" and drives `PREVIEW_VISUAL_CRITIC_BLOCK_ON_UNMEASURED`, so reusing it would have made every
deadline skip read as a vision outage. The field now names which of four reasons applied.

### Day 2 — build Phase 2's scoreboard before Phase 2 starts

Four Phase 2 DoDs need no generation at all. Doing them now means Phase 2 opens with its own
measurements already in place:

- **DoD 8 — the write allowlist. DONE.** *No module outside a named allowlist may write
  `src/pages/**.tsx` or `src/render/**`, enforced at runtime inside `workspace.write_file`,
  allowlist pinned by test.* Enforced at the seam, raising `UnauthorizedPageWrite`.

  **The number is the finding: 26 modules can write pages today.** That is Phase 2's baseline, and
  2.4-2.5 is now measurable as how far it falls. The list is derived, not designed — `observed` (13)
  is the census from running the suite under `BMV_AUDIT_PAGE_WRITES=1`; `static` (13) is modules
  that call the seam with a *computed* path, which rewrite whatever `list_source_files` returns and
  therefore include pages, but which the suite's fixtures never put a page in front of. **Enforcing
  on the observed set alone would have raised in production on the first workspace that differs
  from a test fixture** — every `static` entry is equally a test-coverage gap, and confirming or
  removing each one is cheap Phase 2 work.

  `src/render/**` is armed although it does not exist yet, deliberately: the point is that Phase 2
  *opens* with the guarantee instead of establishing it after twenty modules have learned to write
  there.
- **DoD 9 — test-count floor. HALF DONE, and it was not trivial.** *"Trivial now that CI exists"*
  was wrong: the CI that exists runs **vitest only**, and 1,107 is a pytest count. The floor itself
  is enforced in `tests/conftest.py` via `pytest_collection_modifyitems` — not as a test, because a
  test cannot see how many tests were collected beside it, and the thing being guarded against is
  tests *disappearing* (0.9 found eight files that had never been collected at all, and nothing was
  red). Two numbers: `DOD_9_FLOOR = 1107` is contractual, `COLLECTED_FLOOR = 1624` is the ratchet
  that does the work, because a floor 500 below the real count would let a third of the suite vanish
  quietly. Subset runs are exempt — every mutation driver runs two or three files.

  **The "asserted in CI" half is open** and needs a pytest workflow. It was deliberately not written
  blind: 1.10's lesson is that a CI job must be verified on the CI platform, and that job would have
  failed its first run with local green hiding it.
- **DoD 7 — route bijection. MEASURED, and the row is open on both halves.**
  `scripts/measure/route_bijection.py`, over the 42 stored architect route lists now archived at
  [`docs/evidence/architect-routes.json`](evidence/architect-routes.json) plus the workspace archive.
  It calls the real functions rather than reimplementing them.

  | | before | after |
  |---|---|---|
  | `len(_smoke_routes)` ≠ non-wildcard routes with a page file | **31 of 42 runs**, 79 of 553 routes never smoke-loaded | 26 of 42, 74 routes |
  | of which the 12-route cap | 26 of 42 | 26 of 42 |
  | one page file under two or more URLs | 11 of 42 runs, 12 alias URLs | same corpus fact; all now loaded |
  | `catalogue_route_for_file` not injective | **11 of 42 runs** | unchanged — Phase 2's job |
  | a *generated* page with no route | 4 of 42 runs | reported as `pages_unrouted` |
  | a *template seed* page with no route | 35 of 42 runs | reported |
  | a route naming a file that does not exist | 0 of 42 | 0 |

  **The 5-run improvement is a defect fix, not a measurement change.** `_smoke_routes` deduped on
  `component_file`, so a second URL on one page was never loaded — request 22 declared
  `ArtworkDetailPage.tsx` at both `/artwork` and `/gallery/:id`, the shipped router serves both, and
  only the first was ever render-checked. The un-parameterized alias is the render condition that
  fails. It dedupes on URL now, with aliases sorted behind every first sighting so the cap cannot
  displace an unchecked page with a second look at a checked one.

  **The remaining 74 are the cap, and the cap stays.** This pass runs post-deadline inside the
  reserve 1.11 is already fighting; the fix is the denominator, not a bigger number.
  `render_pages_checked = 12` on a 19-route app read as "every page rendered" — the record carries
  `render_pages_eligible` and `render_pages_skipped` now, and the log says so at WARN. Same defect
  class as `visual_review_status: None`, one measurement over.

  Request 33 was the first case, as planned: it shipped `src/pages/AiFeaturesPage.tsx` and a nav
  entry for `/ai-features` with no route declaring it, so the link fell through `path="*"` to home
  and the page was bundled, typechecked and unreachable. 14 mutations, zero survivors.
- **DoD 2 and DoD 5 — the "before" numbers. TAKEN.** `scripts/measure/content_census.py` over the
  58 archived workspaces. **DoD 5 reproduces; DoD 2's figure is in the wrong unit.** Details in the
  Phase 2 DoD rows below.

Plus: extend the vitest suite toward the nav guarantees this document already specifies —
scroll-reset, anchor landing, header clearance. `SkeletonComposer` is pinned; those are not. The
harness gained two pieces it was missing, both of which had presented as broken components rather
than as harness faults: `src/test-setup.ts` stubs `IntersectionObserver` (jsdom has none, and the
motion layer constructs one, so every `MotionReveal`-wrapped component died in a passive effect),
and `react-router-dom` is deduped so a `MemoryRouter` in the test package and a `Link` resolved from
the template's `node_modules` share one context.

### The deliverable that pays for the window

**DELIVERED: [`docs/FIRST_FUNDED_TRIO_PREFLIGHT.md`](FIRST_FUNDED_TRIO_PREFLIGHT.md)** — eleven
questions, each with the instrument it needs, plus five pre-launch checks that have each already cost
a trio or a published number. Read it before spending the first funded trio.

A **first-funded-trio pre-flight**: one list of every question the next three runs must answer and
the instrument each one needs. Today a trio would confirm the dead-link guard and the wall clock.
With this week's work it should also settle appspec writer attribution, the ask-ceiling row for
appspec, whether the extractor fixes removed the re-asks, the slot-fill retry rate, and the
ship-rate blockers.

2.9 adds two specific questions to that list, and they are not the same question. **How often does
the contract retry fire**, now readable straight off the call census (`writer=slot_fill`,
`attempt=2`, `unusable_reason=rejected`) — and **does a re-asked page come back different**, which
the census cannot answer. The second is the one that matters: the fix guarantees a second ask
carrying the exact validator errors, not that the model does anything useful with them. A run where
every retry fails still ships the same scaffolds, and it will look busy while doing it.

### What this window explicitly cannot do

**p50, ship rate, 1.11's reserve, and 1.12.** All four need live runs. No amount of offline work
substitutes, and the DoD rows for them stay open and unevidenced until a funded trio says otherwise.
Recording that here so the next session does not read a productive week as progress against them.

---

## Status — updated 2026-08-07 (session 23)

> ### Session 23 — the empty-tuple trio lands evidence-corrected, R6 and the R3 audit close, and run 145 ships rev-1 under the new prompt
>
> - **The empty-tuple reject class (143, session 19 before it) — the trio LANDED
>   (`772ac82`), reshaped by deeper mining of 143's stored artifact:** (1) revs 1-3's
>   empty arrays were NOT authored — the authored spec had 6 pages and ONE error, and
>   the `ai_appspec_repair` call replaced it with a 503-byte fragment (one acceptance-
>   test object); (2) rev 5 made NO new AI call (identical schema_diagnostics incl.
>   completed_at and raw_response_sha256 — a terminal re-persistence of rev 4); (3) the
>   minItems class NEVER reaches `app_spec_repair.j2` (pydantic parse fails first →
>   schema-repair rung exclusively → fallback), so the handoff's named target would
>   have been dead code — the R2 catalogue-contract lesson. What landed: app_spec.j2
>   rule **9a** (no stateless page, real type-prefixed ids, mined `Page1` exemplar);
>   the repair prompt's **anti-collapse** line (sub-object / emptied pages-states =
>   collapse, unfaulted objects survive verbatim); the schema-repair prompt's **7a**
>   constructive stateless-page fix (author the default state, never resend unchanged,
>   never placeholder ids); and the **identical-error-set early stop** — an AI repair
>   whose output reproduces its input's (code, path, message) set fails closed with
>   `repair_reproduced_parent_errors` instead of spending remaining budget, armed only
>   at the two AI dispatch points, any set change = progress. Prompt revision
>   **2026-08-07.3**. 6 tests, **11 mutations / 0 survivors first pass**.
> - **R6 DONE both halves (`f9fc60c`)** — analyze/blueprint/demo were the only stages
>   with 100% record_usage-fallback rows (no ai_call scope at any ask site); now
>   scoped (reference_url_analysis, screenshot_analysis, mvp_blueprint,
>   preview_extraction, visual_demo). And `_StageLimitedAIProvider` refunds the budget
>   unit for an ask the provider never answered — 143's error-cut authoring had spent
>   `APPSPEC_MAX_CALLS` for nothing. 7 tests, **6 mutations / 0 survivors**.
> - **R3 audit DONE (offline, no code)** — full classification table under the
>   R-backlog; architect + design_manifest have no decorative strictness (0
>   unparseable/rejected rows ever); the finding is `detail inquire CTA (#inquire)`,
>   which alone discarded two whole artifacts for a constant href. Owner ruling wanted.
> - **Run 145 (Osteria, 143's brief verbatim): SHIPPED `ready` ~568 s, quality gate
>   PASSED, spec accepted rev-1 coverage 98 under 2026-08-07.3** — authoring
>   deterministically valid (no schema parse issues, no heals, no empty tuples, no
>   placeholders), one semantic-coverage repair, calls 4. New rev-1 count: 1. R1 read
>   live (above). **CONFOUND, reported honestly: the tail's critic 5/5 + fix_agent 6/6
>   transport failures at $0/0 ms coincide with the SHARED KEY EXHAUSTING mid-run
>   (380.148/380 at post-run bracket) — not pipeline weather, not the R5 pattern; do
>   not read this run's tail against the R5 table.** Suite **2,026 / 1 / 0**.
>   Session tally: ships 1/1, accepts 1/1 rev-1, transport-dead 0, BMV spend $0.245 +
>   ~$0.02 probes. **The key is EXHAUSTED (380.15/380, the other project burned ~$4.5
>   during this session) — no funded runs possible until it is topped up.**

## Status archive — session 22

> ### Session 22 — four R-rows land in one session, every sweep 0-survivor
>
> - **R5 MEASURED (no behavioral change):** the codegen/tail split table + the ~150 s
>   tail-reservation recommendation live under the R-backlog below; run 140 is the natural
>   experiment (only complete tail on record). Implementation PARKED on the owner's ruling.
> - **R1+R2 at slot_fill LANDED:** transport classification (`_is_transport_failure`,
>   retryable-only), ONE cross-provider rung (`PREVIEW_APP_TRANSPORT_FALLBACK_MODEL`,
>   default haiku, telemetry attempt 3, same judge as the primary, runway-gated with its
>   own degradation label), and R2's real remaining half — the `catalogue-contract`
>   TRANSLATION was dead code on the live path (session 20's `8198cdb` already threads raw
>   errors; the translation only rode `_slot_fill_retry_prompt`, which contract rejections
>   never reach). Now threaded via `_catalogue_retry_context(guidance=...)` and pinned on
>   the LIVE path. 17 tests, **15 mutations / 0 survivors** (1 first-pass survivor exposed a
>   fixture sitting in enforce's shadow — rebuilt with a parse-broken/face-intact fill).
> - **R4 ladder LANDED (the ruling, all five rungs):** `OPS_MIN_NON_HUB_PAGES = 4` shared
>   by gate + prompt + gap-fill + refusal (gate refactored to derive, semantics pinned);
>   `app_spec.j2` 8b floor line for ops faces only (prompt revision **2026-08-07.2**,
>   builder lazy-imports the producer — `source.py`'s own pattern); ops gap-fill PATH-KEYED
>   with stop-at-floor (the census correction: the skeleton key adds ONE page, `/settings`,
>   not zero — still under floor); seed-time refusal `OpsSeedUnderFloorError` opt-in on the
>   enforced path only. Census extended: 135's stored artifact fills to exactly the floor
>   (`/queue` + `/reports`) and passes the FULL chrome gate offline; 47-corpus untouched;
>   gallery census byte-identical to pristine HEAD. 13 tests, **10 mutations /
>   0 survivors**; `mutate_blueprint_gap_fill.py` re-anchored (2 anchors) and re-run
>   **13 / 0**.
> - **R7 LANDED (+ generalized):** `assert_safe_runtime_configuration` WARNS (never
>   crashes) when `APPSPEC_TRANSPORT_FALLBACK_MODEL` shares a provider prefix with
>   `APPSPEC_MODEL`/`APPSPEC_REPAIR_MODEL` — and a sibling check covers the new
>   `PREVIEW_APP_TRANSPORT_FALLBACK_MODEL`/`PREVIEW_APP_MODEL` pair. 7+2 tests,
>   **7 mutations / 0 survivors** (the preview pair pinned in the R1 sweep).
> - **Suite 2,012 / 1 / 0** (+45). Funded duo (weather-gated, healthy): **run 143**
>   (Osteria) — authoring attempt 1 transport-cut and ABSORBED (attempt 2 healthy), then
>   honest quality reject ×5 revisions on `state_ids: []` (the session-19 empty-tuple
>   class) — rev-1 streak ends at 3; the slot_fill read did not bind (never reached
>   codegen; next healthy run reads it free). **Run 144** (dispatch desk, 135 verbatim) —
>   spec accepted rev-2 coverage 100 under prompt 2026-08-07.2, authored 3 pages with `/`
>   NATIVE, the gap-fill added `/queue` + `/records` (blueprint page_ids in the shipped
>   table) exactly to the floor, and the run **SHIPPED `ready` at 552 s, quality gate
>   PASSED** — the class that cost run 135 a full paid run is now a ship. Session tally:
>   ships 1/2, accepts 1/1 requests-with-judged-specs each way, transport-dead 0. Spend
>   $0.33 telemetry-attributed; $7.86 left at close.

## Status archive — session 21

> ### Session 21 — transport can no longer kill a run; ships 3/5 with the closing duo 2/2
>
> - **The transport model-fallback LANDED (`3f7f7f9`) and FIRED LIVE the same session.**
>   `APPSPEC_TRANSPORT_FALLBACK_MODEL` (cross-provider by configuration): when a candidate
>   ask's bounded same-model re-ask is also cut, ONE ask goes to the other provider before
>   failing closed — telemetry attempt 3 under the same writer. Fires ONLY on the transport
>   class (mutation-pinned); malformation/refusal raise as before; the deterministic
>   validator still gates the fallback's answer. Also closed authoring's empty-cut raise
>   hole (zero retries before). 13 tests, 11 mutations / 0 survivors. **Live: run 139's
>   authoring survived two 0-char haiku burns via a gemini attempt-3 candidate.** A
>   transport-classified dead run is now a NEW bug at every appspec ask site.
> - **The haiku APPSPEC migration duo (runs 138/139): REVERTED, 0/2 accepts, $0.70.**
>   3-of-4 haiku authoring asks returned finish=length with 0 output chars at the full 24k
>   budget ($0.13, 95-116 s each) — the session-18 reasoning-burn class at the appspec slot.
>   Its one authored spec broke a taught rule and its repair repeated the identical
>   validator error verbatim. October migration: haiku-4.5 AND gemini-3-flash are both
>   ruled out as-is; a new candidate needs an owner sign-off.
> - **Run 135's ops-home seed gap LANDED (`e895ef7`) — and run 140 (135's brief verbatim)
>   SHIPPED `ready` at 553 s, the first internal_ops ship under enforced appspec ever**
>   (spec accepted rev-1, coverage 100). `lock_chrome_on_architecture_seed` re-paths the
>   seed's own ops-dashboard route to `/` when no home exists; census over all 47 stored
>   kind_contexts: 0 route paths change; 135's stored spec reproduces the defect pre-lock
>   and seeds home post-lock. 7 tests, 7 mutations / 0 survivors. **FILED with offline
>   proof (full-chain replay archived): a 3-page ops spec next refuses on
>   `ops_kind_too_few_pages` — the ops blueprint gap-fill fires only on non-substantive
>   route tables; needs a gap-fill extension or an owner ruling.**
> - **Run 133's coverage determinism trap LANDED (`aced8e7`).** The malformation was
>   explicit nulls on DEFAULTED fields (cosmetic) — now coerced, with required fields and
>   the proof ledger pinned strict; and the one-shot retry varies (corrective instruction
>   naming the first failure, attempt bumped to 2). 6 tests, 7 mutations / 0 survivors.
> - **Closing duo 141/142: 2/2 shipped `ready`, both specs accepted rev-1 at coverage 100**
>   (~565/558 s; tail degraded past deadline: typecheck errors, visual critic never ran —
>   the tail starvation is now the dominant residual). Zero seeded gallery artifacts (142's
>   PAGE-ROOM-GALLERY is the planner's own, as on 132). design_manifest 3-for-3 this
>   session, 5-for-5 live since the fix. **Session tally: ships 3/5, accepts 3-for-3 rev-1,
>   transport-dead 0. Spend $1.94 telemetry-attributed; $11.24 left at close.**

## Reliability hardening backlog — owner-directed (2026-08-07, post-session-21)

The owner reviewed session 21's failure-class analysis and directed: **implement all of
these.** Each row generalizes a pattern already proven in one place to every place the same
failure class can occur. Standing rules apply unchanged: measure first, one variable per
change, mutation-pinned, a run beside anything behavioral, and the rows that intersect a
PARKED ruling still need that ruling's specifics before the behavioral half moves.

| # | practice | done where | remaining work | needs |
|---|---|---|---|---|
| R1 | **Cross-provider fallback at every AI ask site** — a retry only helps if the failure is independent; same-model re-asks are correlated. Classify transport first, bound every rung at one ask, fail closed inside the deadline. | appspec authoring/repair/schema_repair (`3f7f7f9`, fired live on 139) | `slot_fill` (NO fallback today — 1.12(b) proved scaffolds ship to the gate when the writer is unroutable); `coverage_review`'s one-shot retry is still same-model; survey any other single-provider ask | code + mutation sweep per site; one run beside the slot_fill change |
| R2 | **A retry must be a different ask** — temp-0 + identical prompt = identical output by construction. Thread the failure back into the retry (corrective message naming the exact errors), or vary something material. | appspec authoring (compact instruction), coverage (`aced8e7`: corrective + attempt bump) | FILED instance: slot_fill contract retry fails attempt 2 with the **byte-identical** validator message (session 18 — "the writer does not use the validator feedback"); audit every retry site for verbatim re-asks | code + the slot_fill rejection-count read on the next funded run |
| R3 | **Cosmetic-vs-substantive validation** — be strict about decision-carrying fields, lenient about decoration. Explicit `null` where the schema default is `""`/`[]` is absence, not substance. Pin the strict set by mutation so leniency never creeps into load-bearing fields. | coverage models (`aced8e7`) | audit the other strict parsers of model output (slot_fill contract, architect JSON, design_manifest) for whole-artifact rejections on decorative fields; classify each failure code before touching anything | offline audit first; code only where the reject evidence shows the class fired |
| R4 | **Enforce invariants at the earliest stage that has the information** — any ship-gate rule decidable at seed/plan time should be satisfied (or refused) there, in seconds, not after a paid run. The late gate stays as backstop. | ops home at the architecture seed (`e895ef7`; run 140 shipped) | the FILED `ops_kind_too_few_pages` (offline-proven on 135's artifact: ops gap-fill fires only on non-substantive tables); then a systematic pass over `validate_product_kind_chrome` + quality-gate rules: "could this be known before codegen?" | **RULED (owner, 2026-08-07): implement the defense-in-depth ladder, gap-fill variant** — one floor constant shared by gate + prompt render (derive, never duplicate); a per-kind floor line in `app_spec.j2` (ops kinds only); ops gap-fill to the floor with a PATH-KEYED unserved test (the skeleton-keyed test collides on `ops-list` and adds zero pages — proven session 21); seed-time refusal if still under floor; the ship gate untouched as backstop. Never lower the gate; never prompt-only. Census + mutation-pin per rung + one dispatch-desk run |
| R5 | **Per-stage tail budgets** — codegen runs to the deadline by design, so typecheck-fix and the visual critic starved on ALL THREE session-21 ships. Replace first-come-first-served time with explicit downstream reservations (the appspec stage already has `APPSPEC_DOWNSTREAM_RESERVE_SECONDS` as the in-repo precedent). | appspec's downstream reserve | measure the codegen/tail split from stored stage timings (runs 129-142 have them all); then a reservation for the tail stages. **Intersects the owner-parked ≤500 s p50 row — reservations are implementable without moving the DoD, but bring the measured split before any behavioral change** | measurement first (free, offline); owner look at the numbers before the split changes |
| R6 | **Telemetry completeness: every ask row self-describing** — writer/attempt/model on every row is what made every session-21 diagnosis a query instead of a hunt. | appspec stage (sessions 20-21), coverage attempt bump | stages still hitting the `admin_ops.py:330` fallback (`writer=None, attempt=1`); plus the FILED budget-accounting item: errored $0 calls currently spend the appspec call budget — refund them | code, offline-provable, mutation-pinned |
| R7 | **Config invariants asserted, not remembered** — the fallback model must stay cross-provider from the primary or item R1 silently defeats itself; today that's a comment in `.env`. `assert_safe_runtime_configuration` (config.py) is the natural home for a same-provider warning. | the runtime skips a same-model fallback (guard, mutation-pinned) | the startup-time check that WARNS when `APPSPEC_TRANSPORT_FALLBACK_MODEL` shares a provider prefix with `APPSPEC_MODEL`/`APPSPEC_REPAIR_MODEL` | small code item, offline-provable |

Suggested order: **R5-measurement → R1(slot_fill) + R2(slot_fill) as one neighborhood → R4's
ruling-or-gap-fill → R6 → R3 audit → R7** — R5's measurement is free and feeds the owner
ruling; slot_fill is the highest-volume ask site still carrying both the no-fallback and the
verbatim-retry defects, and one funded run reads both fixes.

**Session-22 statuses:** R1 — slot_fill rung LANDED (remaining: `coverage_review`'s
same-model one-shot; the single-provider ask-site survey). R2 — slot_fill translation
LANDED on the live path (remaining: the audit of every other retry site; NOTE the R2 row's
"byte-identical" claim was already half-fixed by `8198cdb` — the surviving defect was the
dead translation and an empty-report hole). R3 — untouched (offline audit still open).
R4 — DONE per the ruling (all five rungs, censused, swept; live read on run 144).
R5 — MEASURED, table + recommendation below; behavioral half owner-parked. R6 — untouched.
R7 — DONE, generalized to the new preview_app fallback pair.

**Session-23 statuses:** R1 — the slot_fill ladder READ LIVE on run 145: ReservationsPage
attempt-1 transport-cut (HTTP 408 at the 120 s ceiling) → classified, and the
cross-provider rung correctly RUNWAY-GATED with its own label
(`slot_fill_transport_fallback_skipped_low_runway`, 98.3 s remaining) — designed
fail-closed; the rung itself has still never fired with runway (0 attempt-3 rows
all-time). Remaining unchanged: coverage_review one-shot; ask-site survey.
R2 — INSIDE THE REPAIR LOOP now: the identical-error-set early stop
(`repair_reproduced_parent_errors`, commit `772ac82`) fails closed when an AI repair's
output reproduces its input's validator error set — run 138's paid-identical-repeat
class; 145's contract-rejection count was 0 (second consecutive run with none), so the
slot_fill contract translation is still unread live. R3 — AUDIT DONE (table above;
NO code): the actionable finding is `detail inquire CTA (#inquire)` — two whole
artifacts discarded for one constant href; needs the owner's ruling before any coercion
lands. R5 — still parked, no ruling. R6 — DONE both halves (`f9fc60c`): analyze/
blueprint/demo asks now carry writer/attempt (the record_usage fallback census is
clean), and an errored $0 appspec call refunds its budget unit. 6 mutations / 0
survivors. Empty-tuple trio: see the session-23 status callout at the top of this
Status section.

### R3 — the classification audit (session 23, 2026-08-07; offline, NO code; stored evidence = `ai_usage_events` + deduplicated rejection lines across `docs/evidence/session18-23`)

Evidence base: slot_fill `rejected` rows = 43 (request_id >= 100; 113 all-time);
architect: **0 `unparseable` rows ever** (only provider transport 5 / truncated 3, all
>=100 recovered on the chain); design_manifest: **0 `rejected` rows ever** (14
`truncated` + 1 transport, all at the provider's 1,500-token cap before the parser saw
bytes). The DB stores only the coarse reason (`rejected`, generate.py:562); per-code
counts come from the archived rejection logs (37 deduplicated slot_fill lines).

**Verdict per parser:**

- **architect JSON and design_manifest have NO decorative strictness to relax.** The
  architect parse is already 4-rung lenient with full post-parse coercion
  (`_normalize_architect`), and its only code is whole-JSON unparseability — never fired.
  design_manifest is the repo's most forgiving parser and falls back deterministically;
  its `design_system` is force-overwritten from the plan regardless, so any model-sent
  value is decorative by construction. For design_manifest the fix lever, if any, is the
  1,500-token `max_tokens` cap, not the parser.
- **slot_fill's catalogue contract is where the class lives.** Most codes are correctly
  decision-carrying (faces, skeleton wiring, imports, undefined JSX, painting-first hero,
  itemSpecs bindings — each anchored to a request-numbered incident). The validator
  already has the in-repo precedent for tolerance: `invalid prop:` / `invalid variant:`
  are classified cosmetic and tolerated (validate.py:380-388).
- **THE ACTIONABLE FINDING: `detail inquire CTA (#inquire)` (validate.py:238) fired
  ALONE 4 times — two whole artifacts (ArtworkDetailPage, RoomDetailPage, both at
  attempt 2/2) discarded to the generic scaffold, plus two retry asks burned, for one
  CTA href whose correct value is a compile-time constant.** The cleanest aced8e7
  candidate: coerce the href by codemod, stay strict on the hero variant and itemSpecs.
- Second candidate: the `catalogue item photo pool` / `lifestyle imageSrc` pair
  (validate.py:251,256) — substantive intent (request 62's wrong photos) but exactly
  coercible (`images.card/hero` → `images.item*`); its one firing discarded a HomePage
  at attempt 1/2 with no retry (runway-gated).
- Non-candidates despite looking mechanical: `missing BRAND_MANIFEST services binding`
  fired 10 times but never alone (coercing it saves zero artifacts); `extra slot:`,
  `dead hash CTA`, `contact #inquire anchor` (dead code — only fires when InquiryPanel
  is also missing) are decorative but have zero or co-fired evidence.

The R3 change, when ruled: extend the tolerated-prefix list + a deterministic codemod
for the inquire-CTA (first) and image-pool (second) codes, mutation-pinned so leniency
never reaches the face/skeleton/import/binding set. Needs the owner's ruling per the
standing R3 boundary (leniency never reaches decision-carrying fields).

### R5 — the measured codegen/tail split (session 22, 2026-08-07; runs 129-142, stored `generation_log` + `ai_usage_events`; NO behavioral change)

Deadline architecture at measurement time: `DEFAULT_TOTAL_SECONDS=540` from the pipeline
top; the only reservation, `RESERVE_SECONDS=60`, protects the **post-gate** render-smoke
pass (`request_deadline.py:77-82`). Codegen is MANDATORY (runs to 540 unbounded); the
pre-gate tail — design_critic, refine, fix_agent (typecheck-fix), visual critic — is
ELECTIVE and is skipped/starved past the deadline. Nothing reserves time for it.

| run | appspec wall | codegen starts | codegen wall | codegen ends | pre-gate tail window | tail outcome (from `ai_usage_events`) |
|---|---|---|---|---|---|---|
| 129 ✓ | 106 s | +151 s | 389 s | **+540 (deadline)** | ~20 s | critic 0/2 ($0), fix_agent 0/6 ($0) — fully starved |
| 132 ✓ | 124 s | +162 s | 378 s | **+540 (deadline)** | ~20 s | critic 0/5 ($0), fix_agent 0/6 ($0) — fully starved |
| 135 ✗gate | 79 s | +119 s | 404 s | +523 | ~31 s | critic 3/5, refine 0/2 ($0), fix_agent 0/6 ($0) |
| **140 ✓** | 103 s | +141 s | **270 s** | **+411** | **~142 s** | **critic 5/5, refine 3/3, fix_agent 1 success — the only complete tail on record; ready at 553 s** |
| 141 ✓ | 56 s | +92 s | 365 s | +457 | ~107 s | critic 6/8, refine 0/5 ($0), fix_agent 0/6 ($0) |
| 142 ✓ | 98 s | +113 s | 363 s | +498 | ~60 s | critic 3/5, refine 0/2 ($0), fix_agent 0/6 ($0) |

What the numbers say:

- **Run 140 is the natural experiment.** Its spec authored 6 pages and codegen finished in
  270 s; the ~142 s tail that bought ran EVERYTHING — critique 5/5, refine 3/3, one
  fix_agent success — and the run shipped `ready` at 553 s. Every other ship gave the tail
  ≤107 s and refine + fix_agent starved at $0 on all of them (typecheck landed `errors`).
- **The measured cost of a complete tail is ~140 s** (140's codegen-end +411 → ready +553:
  critic ~104 s, build ~22 s, gate ~10 s). 141's 107 s was NOT enough — critique mostly ran
  but refine (5 calls) and fix_agent (6 calls) still got $0. The floor is between 107 and
  142 s; the safe reservation is **~140-150 s**.
- **What a reservation would cost:** slot_fill per-call latency on these runs is avg
  59-104 s (max pinned at the 120 s ask ceiling), batches parallelized. A 140-150 s
  codegen cutoff on 129/132-shaped runs (codegen 378-389 s) trades roughly one parallel
  page-batch for the entire critique/refine/typecheck-fix tail. On 140-shaped runs (spec
  lean enough that codegen ends early) it costs nothing — the reservation only binds when
  codegen would starve the tail anyway.
- **The precedent to copy is already in the file:** `codegen_phase.py:216-222` clamps the
  fix-loop ceiling to `remaining - RESERVE_SECONDS`. A tail reservation is the same clamp
  applied to the page-batch loop with a new constant beside `RESERVE_SECONDS`.

**Recommendation (implementation is PARKED pending the owner's ruling on this table):**
introduce `TAIL_RESERVE_SECONDS = 150` in `request_deadline.py` and have codegen stop
opening new batches once `remaining < TAIL_RESERVE_SECONDS + RESERVE_SECONDS`, falling
through to its existing stub+wire path for unwritten routes. This does not move the 540 s
deadline or the parked ≤500 s p50 DoD row; it re-allocates time codegen provably wastes
(129/132 ran to the wire and still shipped with a dead tail). Judge it on: refine/fix_agent
$0-row count and typecheck state on the next ships, against this table as baseline.

## Status archive — session 20

> ### Session 20 — the three remaining items land in one session, each measurement-first
>
> - **Item 5, both halves, LANDED — with the plan census that item 5 was waiting for.**
>   NEW `scripts/measure/plan_blueprint_census.py` reads the 60 stored `experience_plan`s from
>   the DB, fingerprints blueprint-seeded pages against each run's OWN stored contract literals,
>   reconstructs the pre-seed roles, and replays the REAL `_ensure_role_pages` (verdicts:
>   reproduces / seeds_fewer / diverges_other, red exit on the last). Before/after archived in
>   `docs/evidence/session20/`. **The serve-aware seed** (`_plan_served_kinds`: plan-WIDE
>   inference + the hoisted `CATALOG_BROWSE_LEAVES` token rule; paired detail rule; public-only
>   scope): 109/124 stop seeding entirely, 125 keeps its legitimate bootstrap minus the redundant
>   `home` — its plan genuinely had no catalogue anywhere. **The detail-assignment guard**
>   (`_explicit_detail_is_anchored`): planner-assigned `public-detail` survives only with an
>   end-anchored item path, a `detail` id segment, or prose agreement — over the 60 stored plans
>   that keeps all 41 genuine detail pages (painting-detail ×11, room-detail variants, run 88's
>   sauna via prose) and flips 52 mislabeled ones (about ×9, contact ×8, our-story,
>   private-dining — the 124 PrivateDining rejection class). 47 stored kind_contexts: 0
>   regressions (boundary/synthetic/deterministic censuses green; gallery census byte-identical
>   to a pristine-HEAD worktree run). 15 tests, 9 mutations / 0 survivors — after two
>   fixture-binding survivors were caught and fixed (ops chrome-repair masked the scope pin; a
>   plural "details" title cannot catch a titles-widened rule). **Live on run 129 (restaurant):
>   ZERO gallery artifacts in the plan, ZERO slot_fill contract rejections of any class,
>   shipped `ready` 559 s.**
> - **The repair-path transport re-ask LANDED** (`_candidate_ask_with_transport_reask`):
>   `repair` + `schema_repair` route through one bounded helper (1 re-ask on the gate's
>   `provider_error` verdict or a retryable empty-cut raise, attempt bumped,
>   `transport_reask_used` in diagnostics) — fixing `schema_repair`'s missing-`finish_reason`
>   bug, run 123's exact killer, as a side effect; `coverage_review` now refuses
>   `finish_reason=error` so generation's existing one-shot retry is its bounded re-ask (one
>   layer, never stacked). 8 tests, 7 mutations / 0 survivors.
> - **The appspec authoring prompt hardening LANDED (revision `2026-08-07.1`).** The
>   reject-shape catalog was mined from `app_spec_revisions` 114-128 with transport artifacts
>   excluded and labeled; five rules taught in `app_spec.j2` (EXACTLY-ONE initial state with
>   `page_id`/`state_ids` consistency; per-kind assertion references — 12a; declare-before-cite
>   — 17; the minItems floor outside traceability — 6a; trace-or-defer — 16) and the three
>   recurring codes translated into exact fixes in `app_spec_repair.j2`. 6 render tests read the
>   wording off REAL prompts via a fake provider; 7 mutations / 0 survivors; the pinned revision
>   test updated (container env does not override — verified). **First data points: 129's spec
>   was accepted on revision 2 — the first spec-repair success on record — while 130 still
>   rejected on `requirement_unaccounted_for` (the taught rule violated anyway, n=1; honest
>   fail-fast).**
> - **Item 4's deferred live observable is CONFIRMED on 129**: `design_manifest` SUCCEEDED —
>   2,139 output chars in 5.9 s, `finish_reason=stop` on gemini-3-flash — after returning 0
>   chars at its exact token cap on every haiku run. Planning serial (planner 31.8 s + manifest
>   5.9 s) did not regress vs the ~22-30 s baseline plus the old 12-13 s failure burn.
> - **Session-20 tally (enforced appspec): 2 accepts (129 rev-2, 132 rev-1) / 2 rejects
>   (130 `requirement_unaccounted_for`, 131 `state_assertion_state_required` ×3) — both rejects
>   violated freshly-taught rules, so the teaching narrowed nothing to zero on gemini-2.5-flash,
>   but 129's rev-2 accept is the FIRST spec-repair success on record. Run 132 (hotel) shipped
>   with its only gallery being the planner's own PAGE-ROOM-GALLERY and zero /gallery routes —
>   the item-5 hotel half, live. Spend $0.77 (129-132); the key was topped up mid-session
>   (360 → 380; $17.47 left at close).**
> - Recorded landmine: `pytest tests/appspec/` alone fails collection on
>   `test_app_spec_contract` via the long-standing generation/sanitize import cycle unless an
>   earlier module warms `app.application.appspec` — present at HEAD `92c8f0f`, full-suite runs
>   unaffected. Fixing the cycle is filed, not attempted.

## Status archive — session 19

> ### Session 19 — the provider's bad day found the pipeline's next defect, and three fixes landed with runs beside them
>
> Thirteen generations (116-128), all on the duo3 briefs, $1.62 telemetry-attributed. **The
> session's standing tally under enforced appspec: 3 accepts / 10 rejects** — 5 of the 10 were
> transport (4 pre-fix adjudicated, 1 post-fix honest), 4 real spec-quality, 1 mixed; all
> 3 accepts shipped `ready`:
>
> - **gemini-2.5-flash returned error-cut streams on the big appspec asks** (HTTP 200,
>   `finish_reason=error`, 0 tokens, 1k-34.6k chars of partial body) and the authoring parser's
>   fragment strategies extracted tiny complete objects out of the cuts, adjudicated them as
>   candidates, and failed requests 118-121 as fake "spec rejections" — session 16's
>   provider-errors-as-answers finding, alive in the appspec path. **FIXED: a parser gate
>   refuses fragment extraction on an error-cut stream, classifies it truncated (retryable),
>   and the authoring loop re-asks the provider.** 4 tests, 5 mutations / 0 survivors
>   (`mutate_appspec_provider_error.py`). **Live-proven within the hour: run 122's authoring
>   attempt 1 errored, attempt 2 re-asked and its spec was ACCEPTED rev-1, run shipped `ready`
>   554 s.** Residual, filed: repair/coverage/schema_repair asks classify honestly but have no
>   per-call transport re-ask (run 123 died on an errored schema_repair).
> - **With transport removed, appspec acceptance on gemini-2.5-flash is genuinely variable:**
>   116 and 123 rejected on real spec-quality grounds (state assertions without `state_id`;
>   missing required fields + empty-tuple page shape; a missing evidence reference; a call
>   budget exhausted on real outputs) on the same briefs+model that went 2/2 yesterday.
>   Enforced-acceptance record across sessions 18-19: **5 accepts (109/110/122/124/125) vs
>   4 quality-rejects (116/123/126/127)**. The appspec authoring prompt/schema is the next
>   hardening target; judge October-migration candidates on accepts over more than two runs.
> - **Item 1 (`QUALITY_FIX_MODEL=z-ai/glm-5.2:nitro`): ADOPTED** on the probe + run 112 evidence
>   (base failed `length/truncated` at 85 s; nitro's fix_agent succeeded in the same run). The
>   confirmation duo could not observe the stage — 122 shipped with a clean quality gate, so
>   `quality_repair` never fired. No counter-evidence; the routing arithmetic stands.
> - **Item 3 (catalogue-contract vocabulary): LANDED + ADOPTED.** `face_prompt.py` derives a
>   LOCKED LISTING FACE block from the validator's own required tuples, rendered into slot_fill
>   prompts for face scaffolds only; the contract retry translates the two error strings into
>   edits. 4 tests, 5 mutations / 0 survivors — after a first sweep where an infrastructure-red
>   masked a REAL survivor (the component names also live in the embedded scaffold source; the
>   assertion now targets the block's own joined line). **Duo 124/125: the taught class
>   ("missing directory face component:PageHeader, missing BRAND_MANIFEST services binding")
>   fell 5-of-6 (session 18) → 0-of-5; both runs shipped `ready`; acceptance 4/11 (36%), flat vs
>   baseline but confounded by deadline-tail transport deaths.** Remaining rejection classes are
>   other defects: enforce's no-error-string "assigned face not preserved" clone test (filed —
>   vocabulary cannot teach it), the composed-page slots class (AboutPage/0e678fa's half, item 5's
>   neighborhood), detail-hero. New n=1 on watch: `forbidden @/ui component:PageHeader` on a
>   composed page (0 in session 18); the block provably does not render for composed scaffolds.
> - **Item 4 (haiku planning starvation): LANDED.** `design_manifest` and `plan_validation` ask
>   TEXT_MODEL first (ARCHITECT_MODEL stays for the architect call; it remains plan_validation's
>   fallback). 3 tests, 3 mutations / 0 survivors. **Live observation deferred: all three run
>   attempts (126/127 restaurant, 128 hotel) died at appspec before planning. design_manifest
>   success + planning serial time (baseline ~22 s) are free observables on the next healthy
>   run's log — read them first.**
> - **Item 2 (1.12 rewrite): DONE** — the row now pins "fail fast, fail honest, stored failure
>   state, customer retry works", citing runs 111/112/113; both 1.12 rows updated.
> - **Item 5 (gallery residual at plan stage): NOT LANDED — and this session's runs sharpened
>   the diagnosis.** Under enforced appspec, runs 122/124/125 all carry gallery artifacts — but
>   **the shipped route tables have NO `/gallery` (bbe6359's architect-stage gap-fill holds).**
>   The entry point is the PLAN stage: 124's `experience_plan.roles[1].pages` contains blueprint
>   `gallery` + `gallery_detail` pages and "Gallery"/"Artwork" nav links — `_ensure_role_pages`'s
>   thin-branch appends the whole `_storefront_pages()` blueprint (GalleryPage + ArtworkDetail
>   literals) into any role whose page list reads thin, with none of the serve-aware resolution
>   `_inject_blueprint_routes` got. Cost today: wasted slot_fill calls on gallery pages
>   (GalleryPage rejections on 124/125), dead nav labels, and on run 111 a failed ship at the
>   visual critic. Next session: make the plan-stage seeding serve-aware (resolve menu/catalogue
>   via the same `force_catalog_browse` leaf rule the scaffold uses), fix AboutPage's plan-page
>   public-detail half in the same neighborhood, wrap-measure with `gallery_gapfill_census.py`
>   (47 stored kind_contexts must not regress), mutation-pin, one duo.
> - Spend: **$1.62 telemetry-attributed** across 116-128 (142 calls); credits bracket
>   349.9196 → 355.0122 of 360 (the delta beyond telemetry is the shared key's other project —
>   tracked, not alarmed on).

> ### Session 18 — THE FUNDED SESSION: 11 runs, three model verdicts, appspec wins its head-to-head, 1.12 answered
>
> Eleven generations on the duo3 briefs (requests 103-113), $3.01 telemetry-attributed of the
> owner's $10 budget. Full logs `docs/evidence/session18/`; verdicts with numbers in
> [MODEL_RESEARCH_2026-08.md](MODEL_RESEARCH_2026-08.md) "Funded-session results".
>
> - **The seven-fix read-list: 5 of 7 pass on the baseline duo (103/104, both shipped `ready`
>   ~575 s).** Hotel gallery gone (was 8/8 broken); no hero literal; real font names; `:slug` 0;
>   `Object.values(params)[0]` with token lookup on both detail pages. **Restaurant gallery is
>   the census's known 2-of-6 residual and fired on 103, 107 and 111, not 105/109** — and on 111
>   the visual critic scored the gallery pages 30/40 (`visual_defect_severe`, "completely
>   misaligned with a restaurant business") and FAILED the run: the residual can kill a ship
>   under the demo-matches-business rule. Item 2 unexercised (architect declared only
>   `/reservations`). **AboutPage.tsx appeared in slot_fill rejections → `0e678fa` is confirmed
>   half a fix; the plan page still assigns public-detail.**
> - **The frame for everything: runway starvation.** Pre-codegen serial cost was 342-389 s of the
>   600 s cap on baseline; every call after ~490 s died with runway-sized timeouts (76% of
>   baseline calls, $0 each). The critic and fixer never ran on healthy briefs. Model verdicts:
>   **TEXT_MODEL → `gemini-3-flash-preview` ADOPTED** (codegen starts 245/247 s vs 342/389 s —
>   the October migration, done early because it cuts the bottleneck); **FIX_MODEL →
>   `glm-5.2:nitro` ADOPTED** (probe: default routing pins to StreamLake at 57-66 t/s, past the
>   120 s call cap at real fix sizes; nitro = 178-185 t/s; first live fix success on run 112);
>   **PREVIEW_APP_MODEL v4-flash REVERTED** (quality flat-to-slightly-worse, cost saving ~6¢/run,
>   doesn't touch the bottleneck).
> - **The appspec head-to-head (109/110 `on` vs 107/108 `off`, same models): enforcement won.**
>   2/2 rev-1 accepts (the 0-of-18 history predates this year's appspec fixes), planning
>   collapses ~100-150 s → ~22 s (`canonical_seed` set ⇒ `validate_and_expand_plan` skipped),
>   **0 codegen failures**, the tail ran for the first time (critic 4 successes, refine fired,
>   tsc 0 on 109), wall 566/561 vs 573/572, route tables leaner and business-matched (9 and 7
>   routes). Cost +$0.16/run. **Recommendation to the owner: KEEP appspec and turn it ON;**
>   `.env` left `off` pending the ruling. Caveat: n=2 accepts, and a rejected spec now fails the
>   request honestly (strict raises, post-v1-removal).
> - **1.12 is answered and the row's premise is dead.** (a) Unroutable ARCHITECT_MODEL is
>   absorbed by the model-fallback chain (v4-pro architected successfully, +~100 s) — the
>   deterministic blueprint is unreachable from model failure alone. (b) Unroutable
>   PREVIEW_APP_MODEL: slot_fill has NO fallback; all pages kept scaffolds and the quality gate
>   failed the run inside the cap (566 s). (c) Unroutable TEXT_MODEL: the pipeline fails at
>   blueprint in 4 s, $0. **Nowhere does a degraded blueprint preview ship** — the modern
>   pipeline converts degraded output into honest `failed` + the customer retry endpoint. The
>   row should be rewritten to pin THAT behavior (fail fast, fail honest, never a bad demo)
>   rather than a degraded ship that no longer exists.
> - **`_design_system_dict` palette fix LANDED with a run beside it (`83bb7c6`).** The derived
>   palette (text/muted/background/surface) threads ctx → guards → every design_system fallback;
>   `surface_color` (previously omitted) always emitted; the two diverging copies of the
>   function unified — patterns' copy was still writing squashed `font_family` slugs to every
>   brand_contract consumer. 6 tests, 7 mutations, 0 survivors. **Live-proven on run 112's
>   mock.ts: brand-derived `#1b3126`/`#577466` instead of the hardcoded neutrals.**
> - **slot_fill rejection distribution (backlog item 3), measured:** 49 baseline calls = 34
>   transport (starvation), 5 contract, 1 truncated-then-retried — **attempt 2 PASSED, the first
>   observed 2.9 retry success**. The contract class is concentrated: "missing directory face
>   component:PageHeader, missing BRAND_MANIFEST services binding" fired 5× on catalogue pages,
>   and a with-runway retry (107) failed attempt 2 with the byte-identical error — the writer
>   does not use that validator feedback. Prompt vocabulary (preflight Q5), not model quality.
> - New filed items: QUALITY_FIX_MODEL should get `:nitro` (one line/change rule kept it base;
>   its base-glm call failed truncated on 112); haiku planning writers (`plan_validation` /
>   `design_manifest`) burn their exact token budgets with 0 chars out — reasoning-burn shape,
>   wants a budget/model change with a run; run 104 shipped `/book` + `/book-appointment` +
>   `/book-appointments` (route-alias class).

> ### Session 16 — an offline architecture review, and AppSpec is switched OFF by owner ruling
>
> - **`APPSPEC_MODE` is now `off`** (was `shadow` since it was introduced — confirmed from the
>   historical generation logs, which stamp `mode=shadow` on requests 95/97/101/102, and from the
>   running process before and after the flip). Owner ruling, 2026-08-06. The shadow pass cost
>   **~100-125 s of serial critical path per run** (request 102's timeline: three appspec calls,
>   10 s → 102 s, before planning starts) and its functional consumers are ALL behind
>   `enforce_app_spec` — shadow produced provenance and nothing else. `.env` changed, container
>   recreated (not restarted), `off` verified from the running process, prior log archived at
>   `docs/evidence/api-log-before-appspec-off-recreate.txt`.
> - **FILED EXPERIMENT — does AppSpec earn its place?** After the first funded duo proves the
>   landed fixes on the current settings (one variable at a time), run the head-to-head:
>   the same brief with `APPSPEC_MODE=on` vs `off`. Judge on (a) does the enforced run ship at
>   all — enforcement's known failure mode is a rejected spec starving the run (trio 7: 0 of 3) —
>   (b) route table fit (enforced replay measured 6 and 9 routes vs 13 and 18 declared free-form)
>   and page identity, (c) wall clock. If enforcement wins, turn it on for real; if it loses,
>   delete the appspec stage and fold route budget + page identity into the architect contract.
>   Note: this experiment tests STRUCTURE fit, not visual variety — silhouettes are the
>   recipe/template axis and appspec cannot move them.
> - **The mock-synthesis prompt's CATALOGUE ITEM SHAPES section had never reached a model**
>   (`d28df68`) — the producer, template section and render-tests all landed while the one kwarg
>   at the production call site did not; the `is defined` guard hid it. Found by the new standing
>   audit `scripts/measure/prompt_variable_audit.py` (red exit on any missing variable at any
>   render site — it gates clean now). Wired; the catching test drives `synthesize_mock_data`
>   itself. 2 mutations, 0 survivors. Suite **1,881 / 1 / 0**.
> - Also filed (HANDOFF one-pager): `slot_fill`'s "truncated" rejections are provider errors
>   adjudicated as model answers (14 of 28 in duo 1) — reclassify WITH the funded distribution
>   measurement, not before it.

> ### Session 15 — the account is STILL empty (FOURTH identical reading), and the offline remainder is now spent
>
> `total_credits 330, total_usage 330.229`, probed first, byte-identical for the fourth session.
> The duo, 1.12's reachability, the `slot_fill` distribution and the colour-fix run stay blocked;
> **there is no meaningful offline work left after this session** — the next session needs either
> credits or an owner ruling, or it should not run.
>
> - **The `design_direction` dedupe guard is LANDED** — `38d66f5`, the one sanctioned offline item.
>   The kind clause is appended once per dict at both sites (`apply_product_kind_to_plan`,
>   `apply_product_kind_to_architect`); the guard keys on the full `PRODUCT_KIND={kind}/{subtype}`
>   marker so a kind flipped through the forcer feedback loop still appends its own note —
>   today's loop behaviour is preserved by construction, not by luck. 3 tests, 6 mutations,
>   0 survivors (`mutate_design_direction_dedupe.py`). Suite **1,870 / 1 / 0**.
>   `design_direction_census.py` re-run: `transient_duplicate_chars` **0 on every kind**, was
>   263–591 per run. No run needed and none spent — the seal already discarded the duplicates;
>   nothing observable changes, exactly as the demotion said.
> - **The classifier ruling was NOT given at session start** — the prompt carried the unfilled
>   template `[prefix-anchored / word-boundary / leave it]`. **Later the same session the owner
>   ruled: prefix-anchored, adopted** — see the UPDATE in the classifier row below. Wrap-measured:
>   the only verdict that changes anywhere is SB-07 to its intended kind; 0 of 47 stored runs move.
>   Suite **1,873 / 1 / 0** after adoption.
> - **1.10 is CLOSED**: the owner opened the Actions run in a browser — run #11 on `f019d39`,
>   Success, vitest 39/39. The first human observation of this repo's CI.
> - **The classifier's two remaining gaps are RULED AND CLOSED** (`87cd085`) — the owner ruled
>   "fix" on both, stating the goal: the demo matches the business (workflow tool, menu site,
>   portfolio, company site), storefront is not the universal default. Staff-only briefs now
>   reach `internal_ops/ops`; a driving school books lessons. 20/20 exact on the synthetic
>   corpus, 0 of 47 stored runs move. Detail in the classifier row's second UPDATE.
> - **Dead nav data is deleted** (`1df35e3`) — measured first over the 67 archived workspaces:
>   per-role navigation keys (customer ×48, owner ×18, staff ×8, never `member`) read by
>   nothing, `navItemsAdmin`/`adminNavItems` aliases imported by nothing. Both writers removed
>   from `sync_mock_roles_navigation`; 2 mutations, 0 survivors. Behaviour-identical on every
>   archived app. The last no-credit code item is gone.
> - No generation (credits still $0), vitest/`tsc -b` not run from here (no JS/TS touched;
>   CI's vitest run is the observation above).

> ### Session 14 — the account is STILL empty (third reading), and the session was measurement-only
>
> `total_credits 330, total_usage 330.229`, byte-identical to sessions 12 and 13. Probed first,
> before anything was restarted. Zero generations; the duo, the `slot_fill` distribution, the
> colour-fix verification run and 1.12's reachability proof all stay blocked — 1.12's
> unroutable-model trick needs every *other* stage able to complete a real call, so an empty
> account cannot isolate a branch.
>
> What this session did instead, all offline and all re-derivable:
>
> - **The classifier's blast radius is measured and the owner can now rule** —
>   `scripts/measure/boundary_variant_census.py`, detail in the classifier row below.
>   **0 of the 47 stored kind_contexts change kind under either boundary variant.**
> - **Session 13's finding 2 ("design_direction is concatenated twice per run — prompt pollution
>   on the healthy path") is WRONG as filed.** The double-append is real but transient:
>   `seal_design_brief` seals unconditionally, and the sealed replaces at `plan_phase.py:265`
>   (before `call_architect` at `:288`) and `:349` (before codegen) discard the direction before
>   any prompt or artifact reads it. **All 47 stored `preview_app.design_direction` values carry
>   zero `PRODUCT_KIND=` occurrences.** `scripts/measure/design_direction_census.py` has the
>   per-kind sizes; the fix is demoted from "wants a run" to a belt-and-braces dedupe.
> - **A session-13 census claim is corrected in place**: `deterministic_paths_census.py`'s
>   internal_ops row resolved `storefront/storefront` — the classifier's own unreachability
>   finding, biting the census — so the internal_ops/ops contract was never driven. Fixed, with
>   a label/resolved assertion that goes red on the old context. See the 1.12 update block.

> ### The account is still empty — re-probed at the top of session 13
>
> `total_credits 330, total_usage 330.229`, unchanged from session 12's reading. **Session 13 ran
> zero generations and everything it landed is mutation-proven and production-UNPROVEN.** The
> duo (`launch_duo3.sh`) and the `slot_fill` distribution are still blocked on this and on nothing
> else.
>
> **`main` is pushed.** `122ef79..80a3d71`, sixteen commits, on the owner's authorisation — the
> five-sessions-on-one-disk risk is closed. **CI is still unobserved**: the repository returns 404
> unauthenticated on both `api.github.com` and the HTML page, so it is private, and `gh` is not
> installed. The workflow triggers `on: push: branches: [main]`, so a run was certainly queued.
> **1.10's blocker has changed from "never pushed" to "needs a browser or a token"** and the row
> stays open.

> ### The OpenRouter account is exhausted, and the mystery spend recurred — larger
>
> **No live generation can run.** Checked before launching a duo, which is the only reason the
> duo was not wasted: `https://openrouter.ai/api/v1/credits` returns
> `total_credits 330, total_usage 330.229`, and a 28,000-`max_tokens` probe against
> `google/gemini-2.5-flash`, `deepseek/deepseek-v4-pro` and `z-ai/glm-5.2` returns
> **"Insufficient credits"** on all three in under a second.
>
> **The pipeline did not spend it.** `usage_daily` is **$22.25**; `ai_usage_events` records
> **$1.94** for 2026-08-05 across 217 calls — session 11's six runs at 06:00-07:00 plus three
> zero-cost probes at 15:00. **~$20.3 of today's spend is not this pipeline**, on a day this
> session ran zero generations. That is the **second measured occurrence**: 2026-08-04 was $17.62
> by the same arithmetic, and session 11 recorded it as "one data point, not an all-clear". It is
> now two, and the second one emptied the account. **Escalating or rotating the key is the owner's
> call and nothing here can proceed past it.**
>
> Everything session 12 landed is therefore **mutation-proven and production-unproven**, and the
> three fixes session 11 could not prove are still unproven. `session11_fix_replay.py` is the
> substitute and its own docstring says what it cannot show.

> ### The enforcement spike — run 2026-08-05, and it is the session's answer
>
> `APPSPEC_MODE=on` was set (recreate, not restart — `docker compose restart` does **not** re-read
> `env_file`), verified from the running process, and the brief of 95/97 was run twice. **Both runs
> shipped nothing.** Requests 99 and 100 are `status: failed` with an empty `generated_pages`:
> the authored spec failed deterministic validation (`must_requirement_cannot_be_deferred:
> REQ-ABOUT-001` on 99, `requirement_traced_and_deferred: REQ-RESPONSIVE-001` on 100) and
> `appspec_gate.py:182` turns that into a `raise` when `enforce_app_spec`.
>
> **That is not enforcement authoring a worse spec.** `ensure_approved_app_spec` takes neither a mode
> nor a policy and `APPSPEC_FALLBACK_ENABLED` is `False` in both modes, so the authoring and
> validation path is byte-identical; the rejections are model variance and what enforcement changes
> is the *consequence*. On this one brief the spec is now **accepted on 95 and 97 and rejected on 99
> and 100 — 2 of 4**. `.env` is back to `shadow`, verified from the running process.
>
> **What enforcement would ship, replayed deterministically** from the stored accepted specs
> (`scripts/measure/appspec_enforcement_replay.py`, re-derivable offline):
>
> | | shipped in shadow | under enforcement | removed | survives |
> |---|---|---|---|---|
> | request 95 | 13 routes | **6** | owner console (5), `/my-profile`, `/my-reservations`, `/private-events` | `/gallery`, `/gallery/:id` |
> | request 97 | 18 routes | **9** | owner console (5), `/menu/food`, `/menu/wine`, `/privacy-policy`, `/terms-of-service` | `/gallery`, `/gallery/:id` |
>
> **Exactly one line puts the gallery back, on both runs.**
> `apply_product_kind_to_architect` (`plan_phase.py:305`) reaches `product_kind.py:1008-1010`, which
> gap-fills the storefront blueprint into every `PUBLIC_KINDS` app **even when the routes are already
> substantive** — and `_storefront_pages()` (`product_kind.py:475-496`) declares `/gallery` and
> `/gallery/:id → ArtworkDetailPage.tsx` as literals. **The twelve-table trattoria's art gallery is a
> hardcoded blueprint page**, not an industry inference and not a writer's guess. The
> `internal_desk` and `saas_accounting` forcers (`:306`, `:310`), the second kind lock (`:315`) and
> `ensure_ai_feature_route` (`:370`) add **nothing** on this brief.
>
> Two consequences for the plan: an enforced AppSpec **does** collapse the route table roughly in
> half and would bring the render-check denominator under the cap of 12 by itself (DoD 7 / item 8
> below) — and it **cannot** fix page identity while a blueprint gap-fill outranks the contract.
> Turning the mode on today would also make every rejected spec a run that ships nothing, at a
> measured acceptance of 2 of 4 on the one brief with four samples.

> **`APPSPEC_MODE=shadow` (the standing state).** `.env:12`, confirmed resolved in the running api
> container. `app_spec_is_required` returns True only for `on`, so on **every** run in this
> environment `enforce_app_spec` is `False`, `app_spec_scope` is never computed, and
> `canonical_plan_seed` is `None`. Request 95's own stored record says so:
> `app_spec_ref.enforced: false` beside an **accepted** revision. Consequences, all of which change
> how sections below should be read:
>
> - **Every consumer of the AppSpec is gated behind `enforce_app_spec`** (`plan_phase.py:86`, `:296`,
>   `:299`; `finalize.py:533`, `:616`, `:994`). The stage authors, validates, repairs,
>   coverage-reviews and persists a spec, and then the pipeline plans as if it did not exist.
> - **`build_experience_plan` therefore takes the legacy path on every run** — planner *plus*
>   `validate_and_expand_plan`, which is two more full asks. That is most of the 41 % of "codegen"
>   the census below re-attributes.
> - **1.12's "a MANDATORY stage with no deterministic path" is explained.** `plan_phase.py:295-298`
>   rescues an architect failure only `if ctx.enforce_app_spec and ctx.app_spec_result and
>   ctx.app_spec_scope`. In shadow mode that is never true, so `call_architect` raising always
>   propagates — which is exactly what requests 74, 92 and 94 did.
> - **1.13 bounded a stage whose output is not enforced.** The bound is still correct and the tail it
>   caps is still real; what it buys is cheaper *shadow* work.
>
> Nothing here says the setting is wrong — it may be deliberate. It says the roadmap has been
> reasoning about an enforced AppSpec that this environment has never run. **Whether to set `on` is
> an owner decision and is not taken here.**

| Item | State |
|---|---|
| **1.12 — the deterministic paths for MANDATORY stages** | **done, mutation-proven — and reachability was answered live in session 18 (runs 111/112/113): the paths are unreachable from model failure, by design of the fallback chain, and the pipeline fails honestly instead.** `dc750a3`. All four pieces of the ruling. Five runs shipped NULL because three MANDATORY stages had no deterministic path; the designed outcome — *a degraded preview that ships* — was unreachable then and is deliberately not the goal now (see the rewritten 1.12 row below). 19 tests, 23 mutations, 0 survivors. Detail in the 1.12 update block in Phase 1 |
| **route alias inflation — from the scaffold end** | **done, mutation-proven, production-UNPROVEN** — `bd58502`, and it was **more than bundle weight**. `assemble.py` minted `base/:id` *and* `base/:slug` for every listing because the scaffolded detail page read `params.id ?? params.slug`. Request 69 shipped **three** routes to one page — `/gallery/:paintingId`, `/gallery/:id`, `/gallery/:slug` — all matching `/gallery/x`; React Router binds one, and the page read `params.id`, so the detail page resolved **no item** and rendered the generic "This piece" against a default image for every id. Request 82 shipped the same shape for `/rooms/:roomId`. **16 routes across 10 of the 47 stored runs declare a param named neither `id` nor `slug`.** The scaffold now reads `Object.values(params)[0]` — whichever param the route declared — and both alias sites mint one alias, and none at all when the app declares its own param child. Measured by `scripts/measure/route_alias_census.py` over all 47 stored tables, driving the *previous* `assemble.py` out of git rather than paraphrasing it: **36 runs change, 800 → 727 routes, 73 removed, and no declared route is lost on any run.** 8 tests, 11 mutations, 0 survivors after two first-sweep survivors. **Two earlier versions of that census were wrong and both were caught before publication** — see the traps section |
| **the 20-brief synthetic corpus — Phase 3's denominator** | **built and measured, classification only** — `980ca63`. `docs/evidence/synthetic-briefs.json` + `scripts/measure/synthetic_kind_census.py`. The archived corpus is 84 rows but **18 distinct briefs, 15 of them `storefront`**, so five skeletons were unreachable by construction and no measurement over it could say whether the classifier can find them. **15 of 20 land their intended kind and subtype; 5 distinct contracts are reached against 3 in the whole archived corpus.** The five misses are findings and are deliberately **not** tuned away — see the row below |
| **the classifier decides a product kind on bare substrings** | **NEW, open, not fixed.** Same class as session 12's bare `"detail"`, found by the corpus above. **A nine-bedroom guest house resolves `internal_ops/trading`** and would be built `/ticket`, `/blotter`, `/positions`, `/risk` — because the hint `"oms"` matches inside **"Rooms"**, in the *business name*. Renaming it "The Wilder House" flips it to `storefront`; that one substring both clears `internal >= 1` and satisfies the strong-signal test at `product_kind.py:258`. Also `"spa"` matching inside "work**spa**ce" and "di**spa**tch" — harmless to those two verdicts, same defect. **And `internal_ops` is close to unreachable in plain English**: a warehouse desk, a facilities desk and a dispatch console each stating they are staff-only all resolve `saas_workspace`, because the kind needs two hint phrases or one of `blotter/oms/hedge/trading desk` and otherwise falls to the ambiguous branch on "queue". Measured: `"internal desk"` + `"warehouse floor"` together do reach `internal_ops/ops`; either alone does not. **A driving school matches zero hints in any table** and takes the final `return "storefront"` default — an art-gallery blueprint for a business that sells lesson packages. Not fixed: the brief was to measure, and a keyword table is not repaired by adding keywords. **UPDATE, session 14 — the blast radius is measured and the ruling can proceed** (`scripts/measure/boundary_variant_census.py`, offline, wraps the real classifier by patching `_blob` — a self-check proves the patch reaches it). Two variants, because the hint table holds deliberate prefix stems (`reconcil`, `bookkeep`) that a boundary on both sides kills: **word** (both sides) and **prefix** (left only). **Under either variant, 0 of the 47 stored kind_contexts change kind or subtype, and the only change anywhere is SB-07 itself** — the guest house drops `internal_ops/trading` for its intended `storefront` (15/20 → 16/20 intended kinds). The other four synthetic misses do not move: they are reachability gaps in the hint table, not substring accidents, and boundary matching neither helps nor hurts them. The cost side: the **word** variant deadens plural hosts — `collector`@collectors, `painting`@paintings, `appointment`@appointments, `reservation`@reservations, `menu`@menus, `trader`@traders, `cafe`@cafes — 48 of 67 rows lose at least one hit and no verdict changes **only because every affected row has redundant hits**; a one-signal brief would fall to the default. The **prefix** variant's losses are almost exactly the defect class (`spa` mid-word ×16 — including "white**spa**ce" — plus `oms`@Rooms) at the price of two genuine suffix matches: `shop`@bookshop and `therapy`@physiotherapy. Still not fixed; whether to move, and to which variant, is the owner's ruling. **UPDATE, session 15 — RULED AND ADOPTED: prefix-anchored.** The owner ruled "yes, fix it" on the prefix recommendation. `_blob` now returns `_HintBlob`, a str subclass whose `in` requires the hint to start at a word edge (`(?<!\w)`, applied only when the hint's first character is alphanumeric — hint-borne delimiters like `"hr "` keep working); the right side stays free for the stems. **Wrap-measured before/after: exactly one verdict changes anywhere — SB-07 to its intended `storefront/storefront` (16/20); 0 of the 47 stored kind_contexts move** (archived: `docs/evidence/boundary-adoption-session15.json`). Both censuses re-run green; `boundary_variant_census.py` is re-anchored to the adopted baseline and now **red-exits on any per-row drift between the shipped classifier and the measured prefix variant** — proven red under a substring revert, for the filed reason. 4 tests / 4 mutations / 0 survivors (`mutate_classifier_boundary.py`), including the overshoot to a both-sides boundary, which stays rejected. **Still open, per the same ruling: `internal_ops` reachability (the three staff-only desks) and the driving-school default — boundaries never touched them.** **UPDATE, session 15 later — BOTH RULED "FIX" AND CLOSED (`87cd085`).** The owner stated the product goal: the demo must match the business — a workflow tool, a menu site, a portfolio, a company site — storefront is not always the answer. Fix A: an internal-facing ASSERTION (`staff-only`, `not a public website`, `no customer ever`, `nobody outside`) beside ops/transactional language resolves `internal_ops`, guarded by `saas == 0` — "an internal tool our studio uses to run client projects" names an audience, not a product, and stays a workspace (that guard exists because the first cut flipped SB-11; it is mutation-pinned). `back office` joins the ops hints. Fix B: `lesson`/`instructor` join the booking hints. Wrap-measured: exactly the four intended briefs change, **the synthetic corpus is 20/20 on kind AND subtype for the first time, and 0 of the 47 stored kind_contexts move** (`docs/evidence/reachability-session15.json`). 6 tests / 5 mutations / 0 survivors; every census tool re-run green. The classifier item is, for the first time since it was filed, **fully closed** |
| **the blueprint gap-fill — the trattoria's art gallery** | **done, mutation-proven, production-UNPROVEN** — `bbe6359`. The `elif contract.kind in PUBLIC_KINDS` branch gap-filled `_storefront_pages()` into every public app *whose routes were already substantive*, testing "already served" by exact **path string**, so an app declaring `/menu` or `/rooms` was told it had no catalogue. It now adds a page only when nothing already serves it — same path, or same resolved page contract, asked of the plan page merged under the route exactly as `_normalize_architect` will twelve lines later. A detail page is added only when its listing is served and has no detail child. Two exemptions stated rather than implied: `/` is keyed on path alone (`assemble.py:1123` routes the catch-all to it, so an app without one redirects to nothing), and a **thin** inventory still gets the whole blueprint, where the blueprint is the product face rather than a gap-fill. Measured over the 47 stored route tables (`scripts/measure/gallery_gapfill_census.py`, archive at `docs/evidence/preview-routes.json`): **23 of 47 runs change; 0 briefs and 0 runs lose their last catalogue page; 1 run loses its last detail page — request 95, the trattoria, which keeps `/menu` and loses `ArtworkDetailPage.tsx`.** Requests 77, 83, 95 and 97 lose the gallery outright; 47 and 69 stop being given a second detail route beside their own `/gallery/:paintingId`. **The boundary, stated: 4 runs still get a gap-filled catalogue because they declared none** — 19 and 43 are art galleries and should; 80 and 86 are the trattoria, whose `/menu` does not resolve to `public-catalog` on those runs. 15 tests, 13 mutations, 0 survivors |
| **`slot_fill`'s `public-detail` rejections — the upstream half** | **done, mutation-proven, production-UNPROVEN** — `0e678fa`. Answers the first of the three questions filed below: *why is an About page assigned `public-detail` at all*. `_infer_skeleton_id` matched the bare substring `"detail"` anywhere in a page's id, title, page_type, purpose, layout, path or role labels, so ordinary English decided a page kind — "lodge contact details." (76), "Page detailing the story" (79), "a detailed plan" (81), "detailed room information" (96). **Measured over the 399 stored public routes: 95 reach the detail branch, 94 of them on the bare word alone, and 35 of those name no item in their path** — including `/book`, `/booking/checkout` and `/booking/confirmation`, booking steps judged against a painting contract. A detail page shows ONE item, which is a fact about the route: the rule is now a path that selects an item, anchored at the end so `/artwork/:artworkId/inquire` stays a form *about* an item; plus the unambiguous multi-word phrases; plus the existing `/services/<name>` rule. **22 of the 399 change and 21 of the 22 are corrections**; the one loss is `/painting/coastal-whispers`, a literal item path with no parameter, which becomes `public-service`. That is the deliberate trade — over-assignment discards a page's work, under-assignment only gives it a more permissive contract. 13 tests, 8 mutations, 0 survivors. **The contract itself is untouched and questions 2 and 3 below stay open** |
| **the palette's second half — appropriateness** | **checked and stopped, as instructed.** `reference_metadata` carries **no colour of any kind**. `fetch_reference_metadata` (`reference_scraper.py`) returns exactly six keys — `title`, `description`, `h1`, `visible_text_snippet`, `og_image`, `fetch_success` — and never reads CSS, an inline style or an image. 40 of the stored requests carry a `reference_url`, 39 stored metadata, all 39 fetched successfully, and the 12 whose JSON contains a `#` are matching **street addresses** ("757 S Alameda St #180") and phone numbers. **The only latent signal is `og_image`, present on 13 of 39** — the reference site's own hero image, which would need a real extractor (fetch, decode, quantise) on the critical path. That is a new capability with a per-run network cost, not a check, so it is written down and **not built**. Derived palettes stay distinct-and-not-appropriate; Northgate Dental is still magenta |
| **Duo 2 (97-98)** — the first generation to see session 10's four fixes | **2 of 2 shipped `ready`**, 563 s and 570 s, on the briefs of 95/96 verbatim. **All four fixes are production-proven**, which is the gap session 10's handoff named: `planning/planner`, `planning/plan_validation` and `planning/design_manifest` rows exist on 97 with **no `codegen` row carrying a NULL writer** (the `(unattributed)` bucket is gone); `withheld_reason` is a key on 97 and absent on 95/96; `viewable` is correctly still not a key; and `mock.ts` contains "Explore the collection" **once on 95 and zero times on 97**. The one scope still unexercised is `plan_expansion` — `validate_and_expand_plan` made a single ask on 97 |
| **the palette monoculture — and what it costs** | **done** — `3b63a07`. **The trade is stated up front: derived palettes are distinct and legible, and none of them is *appropriate*.** Northgate Dental Studio resolves to `#b62bb6` (magenta), Osteria Vinci to a green, Cedar Point Lodge to a slate blue. Every palette's lightness is solved by bisection against the surface it is used on, so WCAG AA holds for all 48 identities by construction — but nothing picks a colour *because* it suits a dentist. Appropriateness was never on offer from a five-bucket keyword table that put 28 of 62 businesses in `wellness`; getting it back needs a signal that is not an industry string, and **the reference site's own colours were the obvious unused candidate** — **checked 2026-08-05 (session 12) and the pipeline holds none of them.** `fetch_reference_metadata` returns six keys and not one is a colour; the 12 stored metadata blobs containing a `#` are matching street addresses. The only latent signal is `og_image` on 13 of 39, which needs a real extractor rather than a read. See the palette row above. Detail below |
| **the palette monoculture** | **done** — `3b63a07`. **58 of 62 archived workspaces ship `#0f766e`; three distinct primary colours in the whole corpus.** Two industry→palette tables existed and the coarser ran first. **Candidate (a) was simulated before being rejected: letting `brand_brief._industry_bucket` decide alone gives three distinct colours — the identical count** — and buckets 28 of 62 as `wellness` because the gallery briefs say *"not a booking SaaS or **clinic** front desk"*. Replaced by a palette derived from the business name, contrast-solved per hue. **3 → 10 distinct over the same 62 workspaces, against a ceiling of 12** — the corpus has only 12 distinct business names, which is a fact worth carrying: a "62-site corpus" is 18 distinct briefs. 13 mutations / 0 survivors |
| **the menu, both halves** | **done** — `8fe8955`, and **the roadmap's attribution below was wrong**. The shipped `mock.ts` already labels `/my-reservations` "Reservations", so the visible defect is the *generator's*: `_normalize_nav_section` deduped on the label key and **deleted** the declared public `/reservations`. Both halves land together with one rule, about the list and never a route name. 9 + 5 mutations / 0 survivors |
| **the scaffold's hero subcopy** | **done** — `8fe8955`. *"A clear next step from {brand} — warm, specific, and ready when you are."* verbatim in 7 of 64 workspaces. **The gate is right not to fire on it** and was not widened: `placeholder_content_shipped` looks for *unfilled* tokens like `[Artist Name]` and this is a filled one, so matching it would make a DoD row measure whether we updated our own regex. The scaffold states the app's declared public destinations instead. Also `_design_system_dict` wrote `sourcesans3` for `"Source Sans 3"` — the second spelling behind "5 fonts" where there are 3 |
| **`finish_reason: error`** | **measured, and the answer is do nothing** — duo 1 carried **52 `error` rows of 149 calls (34.9 %)**, 50 with zero completion tokens; duo 2 carries **2 of 152 (1.3 %)** and **both have real tokens**. So the 200-that-failed-mid-stream shape is **0 of 152** on a healthy day. Session 10 flagged it as possibly "a bad day at the provider"; it was. **Do not touch the transport layer for this** |
| **the dead skeletons and components** | **answered, nothing changed** — 9 of 46 catalogue components have never been imported by any page in 62 workspaces (Tooltip, AccentBeam, ResultRail, EmptyState, InvoiceBoard, ReconSplit, BlotterTape, DeskTicker, ExpenseQueue) and 5 of 15 skeletons never selected. The selector is `classify_product_kind` → `resolve_product_kind_contract`. Over the **18 distinct briefs** in the corpus: 16 `storefront`, 1 `booking_service`, 1 `saas_workspace/generic`, and **zero** `internal_ops` or trading/accounting subtypes — which are the only paths that emit those five skeletons. **They are correctly unreachable for this corpus, not unreachable code.** Detail and the chrome-vs-layout split below |
| **codegen census** — which writer spends the calls | **done** — `46c28d2`, `scripts/measure/codegen_cost.py`. **41 % of the `codegen` stage total is not codegen.** `record_usage` falls back to the run *purpose* with no `ai_call` scope and `generate_preview_app` runs the whole preview pipeline under `purpose="codegen"`, so `page_experience.py`'s unscoped planner, validator and design manifest were billed to it: **310.7 s over 11 calls on duo 1** (143.7 s on 95, 167.0 s on 96). Four scopes added under a `planning` stage. Detail below |
| **`withheld_reason` / `viewable` / `typecheck`** | **two filed defects, both the reader** — `e0eeec5`. `viewable` was **never a key**: `finalize` keeps it as a local and publishes `status` and `url`, so `analyse.py` has read a key no run ever stored. `withheld_reason` likewise, and it is now published (always present, `None` when served, naming which of build / gate / unresolved-crash refused). `viewable` stays *unstored* and derived — a second key free to disagree with `status` is the same defect one layer down. **`typecheck` was never `None`**: the key is `typecheck_status`, and duo 1 stored `errors` with **4** and **8** type errors |
| **fix agent's route block** | **done** — `eb49f43`. Allow-list stated once per run, and the block degrades by dropping rather than collapsing. Measured on request 93's real nine routes: library 6,019 chars + prop shapes 2,206 + routes 10,597 = **18,869 against a 10,000 budget**, down from 45k+ — so **the hoist alone is a 2.4× cut and still not enough**, which is why the four-rung ladder exists. Across every archived run (10-19 routes) nothing now receives `{"truncated": true}` and no route is dropped. **Repair quality is unmeasured** |
| **the scaffold's hero CTA** | **done** — `{ label: 'Explore the collection', href: '/gallery' }` was a **literal** in `safety/mock_data.py`, injected whenever the AI's mock dropped `hero`. Verbatim in **7 of 64 archived workspaces** (20, 66, 78, 81, 85, 93, 95) across unrelated industries; request 95's secondary CTA had already been rewritten to `/` by the dead-link guard, so it shipped a "Talk to us" button that reloads the home page. Now derived from the app's own declared public routes, reading no industry. **It does not stop a restaurant being given a gallery page** — that is the plan/architect layer and stays 2.1-2.3's |
| **0.3** gate-issue classification (content vs layout) | **done** — `a0ecff8`. **Reverses the branch 2.6 had chosen** |
| **0.6** call census, `ai_usage_events` defects | **done** — `a4f8b55` |
| **1.1** request-scoped deadline + degradation contract | **done** — `c534fdf`, `58b4956`. **540 s, not 480** |
| **1.2** model-chain dedupe | **done** — `ac10c9b` |
| **1.3** per-ask ceiling | **done** — `c534fdf`, `58b4956` |
| **1.4** screenshot session budget | **done** — `a919f86` |
| **1.5** documents off the critical path | **done** — `c534fdf` |
| **1.6** JSON extractor | **done** — `ac10c9b`, and the diagnosis in this doc was wrong; see below |
| **1.7** validate repair-plan paths before the first write | **done** — `1b5e0d1` |
| **1.8** industry derivation + placeholder gate | **done** — `ac10c9b`, `a919f86`. Token-length work still gated on 0.1 |
| **1.9** bound items to the image pool | **done** — `ac10c9b`, **verified live on request 73** (12 items, below) |
| **1.10** JS test runner (vitest) | **done — observed GREEN on `main` (session 15).** The owner opened run #11 of `preview-template-tests.yml` (push of `f019d39`) in a browser: **Success, vitest 39/39 across 4 files, 27 s, 1 warning annotation.** A human saw it on the CI platform, which is what this row demanded. Previously: **runner done, CI green-on-main pending a merge.** `backend/preview-template-tests/` — vitest 4 + jsdom + testing-library, 9 tests over `SkeletonComposer`, all nine mutation-tested by `tools/mutate.py` with zero survivors. It is a **sibling package on purpose**: the template's `package.json` is the shared-npm cache key, so a devDependency there costs the next generation a cold `npm ci` inside the run (below) |
| **1.11** bound the post-deadline reserve | **still open. First attempt was wrong and is reverted.** Clipping the capture session's budget to the remaining cap bought **nothing on the cap and cost every judged page**: requests 80/81/82 went 2-of-3 over 600 s (vs 1-of-3) and `visual_pages_reviewed` went **10-of-18 → 0-of-18**. Contention was 0.0 s on all three, so the clip was not even answering a queue. What survives is the lock-**wait** bound, which is cheap and never fired. The overrun is not capture: the gate, the AI repair and finalize all run past the deadline and nothing bounds them. Capping one consumer of an unbounded reserve tightens the distribution without closing it. **Trio 7 adds one sample and it points the same way**: request 93's tail is 32.0 s of which **0.1 s is AI**, with 3 pages judged — see Q10 in the trio 7 section. The tail to attack is non-AI work, and `tail.py` cannot see it without being parameterized past its hardcoded run list |
| **Duo 1 (95-96)** — the 1.13 proof run | **2 of 2 shipped `ready` with zero gate issues**, on the briefs of 92 and 94 verbatim, and **neither of 1.13's bounds fired** — so the improvement is acceptance variance, not the fix. appspec AI 336.5 → 43.2 s and 331.6 → 94.3 s. **p50 unmoved at 571/573 s**, and codegen is now the dominant term at 315-437 s of AI. Detail below |
| **1.13** bound `appspec` per request | **landed, and UNPROVEN in production — it did not fire on either duo run.** Added by owner ruling on 2026-08-04 rather than moving the p50 row to Phase 2 — *"let's try B, if it works it works if not we try A."* **`APPSPEC_MAX_CALLS` was enforced per entry into the stage, and the stage is entered twice a generation**, so requests 92/93/94 made **7, 6 and 10** calls against a configured **6** and no budget-exhausted line was ever logged. The tally is the deadline's now, and a runway reservation refuses any appspec call that would leave the pipeline less than **280 s** — under all five shipped runs in the corpus, above what 92 and 94 left themselves (91 s and 136 s). 14 mutations / 0 survivors. **Duo 1 then measured it and neither bound engaged** — 2 and 5 calls against a ceiling of 8, and appspec never reached the elapsed at which the reservation fires. The code is correct and tested and caps a tail trio 7 proved is real; it is simply **not shown to do anything in production yet**, and the duo's improvement belongs to acceptance variance. p50 unmoved at 571/573 s. **The evidence now points at (A)** — not because the bound failed to land but because codegen, at 315-437 s of AI, is the term that decides p50. Owner ruling pending |
| **1.12** a mandatory stage with no deterministic path | **CLOSED, live-proven on all three slots (session 18, runs 111/112/113) — and the row's original premise is dead: the degraded blueprint ship it demanded does not exist and should not.** What the reachability runs proved, one unroutable model per run, same brief: **(a) run 111, ARCHITECT_MODEL unroutable** — the model-fallback chain absorbed it (deepseek-v4-pro architected successfully, +~100 s); the deterministic blueprint is unreachable from model failure alone, and the run then failed the quality gate on content, honestly. **(b) run 112, PREVIEW_APP_MODEL unroutable** — `slot_fill` has NO fallback; every page kept its scaffold, the quality gate failed the run inside the cap (566 s), stored `failed`. **(c) run 113, TEXT_MODEL unroutable** — the pipeline fails at blueprint in **4 s, $0.00**. Nowhere does a degraded blueprint preview ship: degraded output becomes an honest `failed` + the customer retry endpoint (post-v1-removal strict behavior, session 17). **The DoD this row now pins: fail fast, fail honest, stored failure state, customer retry works** — all four observed on 111/112/113. The owner's "demo the customer loves" rule makes a degraded generic ship a defect, not a fallback; session 13's deterministic paths (`dc750a3`, 19 tests / 23 mutations / 0 survivors) remain as internal safety stubs, but shipping them was never reachable and is not the goal. History below stands as the record of how the premise died: request 74, trio 7's 92/94 (appspec starvation, not model outage), duo 1's variance |
| **0.9** convert the never-collected test files | **done, and it paid.** Eight files, not the six in the brief — the collection guard found `test_qa_probe.py` (empty) and `test_quote_fix.py` (a print probe) immediately. Suite 1,265 → **1,443 collected, 1,434 passed / 1 skipped / 8 xfailed** |
| **2.9** contract-invalid pages are scaffolded, never re-asked | **done offline — fix landed, effect unmeasured (needs a funded trio).** A syntactically valid page that failed the catalogue contract was replaced wholesale by the generic deterministic scaffold with **no retry**: `_slot_fill_rejection` only knew empty/truncated/no-export/unparseable, so the retry loop never saw a contract violation. **26 pages across requests 74-79** went that way — HomePage, GalleryPage, ServicesPage, RoomsSuitesPage, ArtworkDetailPage — with **zero** syntactic rejections in the same runs, so `_MAX_SLOT_FILL_ATTEMPTS = 2` had never fired once. The retry now fires on **enforce's own verdict**, not the validator's, and carries the exact `validate_catalogue_page_content` errors. Detail below |
| critic coverage: surface priority + placeholder gate | **done** — `a919f86` |
| dead-link occurrence counting, DataTable, seed backfill | **done** — `d8ef2e9` |
| **skeleton-contract prompt budget** | **done** — `0082f5f`. The stale 4,000-char xfail was hiding a live clip: `public-catalog` shipped 12 of 30 allowed components to the model, `MarketingHero` and `ProductShowcase` among the missing. Bound is now derived from the callers' 5,000, and pinned by a round-trip rather than a number |
| **`AiFeaturePanel` hub link** | **done** — `430453a`. Dead in 5 of the 41 archived workspaces that render it. Reads the app's own `navigation` instead of hardcoding `/ai-features`. First defect proved in the vitest harness |
| **`visual_review_status`** | **done** — `2d69917`. Always present, and names which of four reasons the critic did not run. **Not** folded into `unmeasured`, which means a vision outage and drives an operator switch |
| **`write_file` canonicalization** | **done** — `614d772`. The seam returns the path it wrote; the rename stays. Last of the 8 xfails |
| **2.8 / DoD 8** — write allowlist | **done, pulled forward** — see the Day 2 section. **26 modules can write `src/pages/**.tsx` today**; that is Phase 2's baseline and 2.4-2.5 is now measurable against it |
| **DoD 7** — route bijection | **measured, row open, one defect fixed** — `3fc04ca`. 26 of 42 runs smoke-load fewer routes than they declare (74 of 553), 11 of 42 have a non-injective file→route lookup. The fix: `_smoke_routes` deduped on `component_file` and silently dropped a served URL — 12 URLs across 11 runs. Also `render_pages_skipped`, so the cap stops reading as full coverage, and `pages_unrouted` for request 33's orphan class. **The unchecked-routes half is answered as of 2026-08-05, and the answer is the denominator, exactly as this row said:** duo 2 is 12 checked / 18 eligible / **6 skipped** on 97 and the shipped table has grown, not shrunk (95 declared 13, 97 declared 18 on the same brief). Replayed under an enforced AppSpec the same two runs declare **6 and 9** routes — **both under the cap of 12, so enforcement closes this row by itself and no bigger cap is needed.** Do not raise the cap |
| **DoD 2 / DoD 5** — the "before" numbers | **taken** — `fa41e0a`. DoD 5 reproduces exactly (1 `seed` key common to 47 workspaces). **DoD 2's 13,540 is per workspace, not per page TSX** — per page it is mean 859 / median 529, and 12 % of pages already meet the 200-char target. Row corrected rather than left standing |
| **gate `skeleton_id`** | **done** — `c09b96d`. Pre-flight question 5's blocker: `listing_not_schedule_rail` fires on `public-catalog` *or* `public-service` and nothing recorded which. **And `analyse.py` has read `preview_app["gate_issues"]` since it was written while no run ever wrote it** — every DoD evidence table it produced said `gate_issues: 0`, which is why the roadmap's per-code counts came from log greps |
| **Trio 7 (92-94)** — the first funded trio | **valid, and it answered 9 of the 11 pre-flight questions.** Open: **Q8** (the dead-link confirming trio — only one of the three runs produced a gate verdict at all) and **Q11's concurrency half** (contention was 0.0 s, so nothing collided). Wall clock **543.9 / 572.2 / 542.1 s — 3 of 3 under 600 s**, but **contention was 0.0 s**, so it is a second clean clock and *not* a second concurrency test. **Ship rate 0 of 3**, worse than 1 of 3: 93 failed its gate, and **92 and 94 stored no `preview_app` at all** — 1.12, twice in one trio, with `appspec` at 353 s and 339 s. Credits confirmed before launch and the api log has zero credit refusals across the window; the two empty runs are the pipeline, not the account. Detail below |
| **1.10 nav guarantees in vitest** | **partly** — `30ed9b9`. 15 tests over `ScrollToTop`, vitest 17 → 32, 31 mutations / 0 survivors. **Scroll-reset and anchor landing only**: jsdom has no layout engine, so the [16, 48] px landing and the header-clearance measurement are not expressible there and stay on the Playwright path. What is pinned is the layer beneath — which element is chosen and the offset arithmetic, which is where request 67's defect was |

Phase 0's remaining measurements — **0.1** (pack thesis) and **0.4** (are
`revision_instructions` expressible as content-key edits) — are **not** done and still gate 1.8's
token work and 2.6 respectively. 0.7 was answered by the audit (388 of 1,012).

### `page_experience.py`'s "double ask" — WITHDRAWN, the premise is false

Session 12's handoff filed *"`TEXT_MODEL == ARCHITECT_MODEL == google/gemini-2.5-flash` at runtime,
so `build_experience_plan`'s and `validate_and_expand_plan`'s loops are the same model asked twice
— 34-48 s a run."* **Resolved from the running api container on 2026-08-05 (session 13):
`TEXT_MODEL` is `google/gemini-2.5-flash` and `ARCHITECT_MODEL` is `anthropic/claude-haiku-4.5`.**
All three planning chains — planner, validator, expander — are genuine two-model failover chains,
and each second ask goes to a *different* provider, which is what a failover chain is for. **There
is no duplicate to dedupe**, and the owner's constraint (*"explicit retry, or nothing"*) resolves
to nothing, for a better reason than expected.

The second ask also fires **only when the first fails or returns no roles** — all three loops break
or return on success — so the 34-48 s is a failure-path cost, not a per-run tax. On request 95 the
second ask returned the usable plan: that was a failover working.

`backend/.env` is **not tracked in git**, so when `ARCHITECT_MODEL` changed is not recoverable, and
this note does not claim the earlier reading was wrong when it was taken. It claims the standing
rule earned its keep: **resolve config from the running process, never from a file** — and, this
time, never from a previous session's note either. Any other row resting on "these two settings
resolve alike" should be re-read with that in mind.

### Suite state — and the two ways the harness lied about it in one afternoon

**1,867 passed / 1 skipped / 0 xfailed / 0 failed** and **vitest 39 passed**, `tsc -b` clean,
2026-08-05 (session 13). Session 13 added 27 pytest cases across two new files, both fixes
mutation-swept one sweep at a time: **34 new mutations, 68 applied across three sweeps, 0 survivors
at the end, 3 survived a first sweep.** Two of the three are fixtures too small to reach the rule —
nothing asserted the detail page's `.trim()`, and the listing alias site does not run at all unless
a detail component sits *outside* the listing prefix. **The third is a new failure mode worth
naming: a mutation that applied cleanly and was semantically a no-op**, because it inserted a route
table one line above the `architect = {}` that overwrote it. The driver reported it as a survivor,
which is the correct conservative call — `mutated == original` cannot see a no-op that the
*interpreter* undoes. Previously **1,838 / vitest 39** at `80a3d71`.

**1,838 passed / 1 skipped / 0 xfailed / 0 failed** and **vitest 39 passed**, `tsc -b` clean,
2026-08-05 (session 12). Session 12 added 28 pytest cases across two files, both fixes
mutation-swept: **21 new mutations, 41 applied across four sweeps, 0 survivors at the end, 2
survived a first sweep**, and one more *never applied* because its anchor matched twice — which the
driver reports as a survivor rather than counting as caught. Both real survivors are fixtures too
small to reach the rule: a plan page that could not disagree with its route, and a path with no
parameter in the middle of it. Previously **1,808 / vitest 39** at `283f60c`.

**1,808 passed / 1 skipped / 0 xfailed / 0 failed** and **vitest 39 passed**, `tsc -b` clean,
2026-08-05 (session 11). Session 11 added 23 pytest cases and 7 vitest cases across five files, every
fix mutation-swept: **33 new mutations, 44 applied across four sweeps (13 + 9 + 17 + 5), 0 survivors
at the end, 5 survived a first sweep** — and all five were fixtures too small to reach a guard, four
of them the same shape (two guards that overlap on the obvious fixture). Previously **1,785 passed /
vitest 32** at `ad0cc6f`.

**1,785 passed / 1 skipped / 0 xfailed / 0 failed** and **vitest 32 passed**, 2026-08-04 (session
10). Session 10 added 95 of those across five files, every fix mutation-swept: 18 + 10 + 12 + 11 = 51
mutations, **0 survivors at the end, 11 survived a first sweep**. Previously **1,690 passed / 1
skipped** at `122ef79`. The earlier reading (session
9's 1.13 work added 6 of those: 5 tests plus one auto-parametrized case from
`test_every_test_file_is_collected.py`, which is session 7's collection floor doing exactly its
job). Previously **1,668 passed / 1 skipped**, 2026-08-03 (session
8), on the command documented in `HANDOFF.md`. Up from 1,531 / 1 / 2 at the start of the
no-generation window; **all eight xfails are closed**, and the last two each turned out to be
covering a live defect rather than a stale marker. Every fix in the window was mutation-tested:
8 + 17 (vitest) + 11 + 7 + 11 in session 7, then 14 + 11 + 9 + 14 (vitest) in session 8.

**Six mutations survived a first sweep in each session, and the second session's were a different
failure than the first's.** Session 7's were tests asserting against the case that does not bind, or
driving the consumer and not the producer. Session 8's were mostly the opposite mistake: **four
guard conditions that could not change an outcome** — `" " not in text` behind a two-word rule, a
capitalization test behind a lowercase-only charset, `if not path` and `if architect is None` in
front of a lookup that already handles both. Those were deleted, not tested around. The other two
were a real detector defect (lowercase hyphenated prose read as Tailwind) and fixtures too small to
reach the rule they were meant to pin. Both lists are worth reading before writing the next guard.

```
docker run --rm -v "$REPO:/repo" -w /repo/backend \
  -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api \
  -c 'pip install -q pytest; python -m pytest tests/ -q'
```

**Use that one.** `docker compose exec api` is convenient and wrong, for two independent reasons
that each look like an application defect:

1. **`sh -lc` drops node.** A login shell re-reads `/etc/profile`, which resets PATH and loses
   `/opt/node/bin`. `tsx_parse_error` shells out to node and **fails open** — no node means "this
   source parses fine" — so nothing errors; *six* unrelated tests go red with messages pointing at
   application logic. Same commit: `sh -lc` → 10 failed / 1,509 passed. `sh -c` → 4 failed.
2. **The `api` service mounts only `backend/`.** Four tests read repo-root files —
   `scripts/preview-qa.sh`, `Dockerfile.app`, `docker-compose.coolify.yml` — and get
   `FileNotFoundError`, which reads as "the QA harness lost its script". Those were the four
   failures. They are not failures; the files were never mounted. All 140 pass under `docker run`.

I reported both rounds as real before checking the harness — first as "4 pre-existing untriaged
failures", which is why this paragraph exists rather than a ticket. Third and fourth entries in the
running list of harness-lies-about-the-verdict findings, after `tail` swallowing a red `tsc` and the
mutation decoys whose anchors had drifted. **The measurement instrument is part of the measurement.**

### Trio 7 (92-94), in detail — the first funded trio

Same three briefs as trios 5 and 6 (restaurant / dental clinic / hotel, three industries, 60 s
apart, one `reference_url`, one `reference_file`, one plain), so questions 8 and 11 stay controlled
comparisons. **Valid**: credits were confirmed with a 28,000-`max_tokens` probe against both
production models before launch, and the api log carries **zero** credit refusals across the window.
Nothing else ran on the host. `analyse.py 7`.

| | 92 restaurant | 93 dental | 94 hotel |
|---|---|---|---|
| wall clock | **543.9 s** | **572.2 s** | **542.1 s** |
| stored a `preview_app` | **no** | yes (`failed`) | **no** |
| `appspec` span / AI / calls | 353.2 / 336.5 s / **7** | 143.9 / 120.9 s / 6 | 338.8 / 331.6 s / **10** |
| logical asks / p50 / max | 17 / 25.3 / 80.6 s | 46 / 5.6 / 120.0 s | 34 / 9.7 / 68.4 s |
| asks over 120 s | 0 | 0 | 0 |
| contention | — | **0.0 s** | — |

**Q1 — which loop spends appspec's calls: answered, and it is `repair`.** The scopes added in
`56d8f08` produced labelled rows on their first live outing — **no `writer = NULL` in any appspec
row**, so the telemetry is not the defect. Per run:

| | repair | authoring | schema_repair | coverage_review |
|---|---|---|---|---|
| 92 (336.5 s) | **2 calls / 139.9 s** | 2 / 113.4 s | 2 / 68.3 s | 1 / 14.9 s |
| 93 (120.9 s) | 3 / 47.3 s | 2 / 50.6 s | 1 / 22.9 s | — |
| 94 (331.6 s) | **5 calls / 181.9 s** | 3 / 101.4 s | 1 / 32.8 s | 1 / 15.6 s |

`repair` is 42 % of appspec's AI time on 92 and **55 % on 94**, and it is what separates the cheap
run from the expensive ones. Note 94 made **10** appspec calls against a previously observed range
of 2-7.

**Corrected 2026-08-04 — the first reading of this table said "the fix is a repair-loop bound" and
that is the symptom, not the mechanism.** `APPSPEC_MAX_CALLS` is **6**, and these runs made 7, 6 and
10 calls without one budget-exhausted line, because the ceiling was held on the provider instance
and **the stage is entered twice a generation**: `orchestrator.py:134` defines the contract,
`preview_app/pipeline/appspec_gate.py:133` confirms it, and each entry minted a fresh budget.

The confirming entry is *meant* to cost nothing — `ensure_approved_app_spec` returns
`reused=True, calls_used=0` when a revision with the same source digest is already accepted. It
re-authored from scratch on all three runs instead, because **all 18 revisions in this trio are
`rejected` and nothing was ever accepted**. The source digest is identical within each request, so
reuse was not blocked by the digest; it was blocked by there being nothing to reuse. Request 92
authored from scratch **three** times — revisions 182, 192 and 194 all have a null
`parent_revision_id` — discarding a repair chain each time. The duplicate pass is **53 %, 59 % and
50 %** of each run's appspec AI time (178.7 s, 71.6 s, 164.5 s).

That reframes the whole row, because it explains the bimodality `appspec_cost.py` found and could
not account for — 2-3 calls costing 49-94 s against 5-7 costing 253-294 s. **Accepted → the second
entry is a cache hit and appspec is cheap. Rejected → the second entry repeats the stage and appspec
roughly doubles.** So the lever is the **acceptance rate**, and a call ceiling alone would only make
a failing run fail faster with a worse contract — the "improved the gate metric, made the artifact
worse" trap this document already records once.

**Why nothing is ever accepted** is a schema mismatch, dominated by one field: `pages[].state_ids`
arrives empty against a `min_length=1` tuple — **22 of the parse failures across pages 0-4** — then
`actions[].kind` enum violations and missing `product_intent` / `roles` / `capabilities`. Historically
46 revisions were accepted and requests 76-88 mostly accepted on the first attempt, so **0 of 18 is
anomalous but not proof of a regression**: failures happened before (75, 80, 81, 84 all had none),
and 0-for-3 against a ~60 % base rate has about a 6 % chance of being luck. Closing it is 1.13's
second half.

**Q2 — the ask ceiling holds, and for the first time it is evaluated on data that could break it.**
Zero logical asks over 120 s on any run; 93's maximum is exactly 120.0 s, at the cap. With appspec
rows finally carrying a writer, the `(request_id, stage, writer)` grouping has something to group on.

**Q3 — the 2.9 contract retry fired for the first time in the project's history, and it works
sometimes.** Request 93: `slot_fill attempt=1` × 3 (2 `rejected`), **`slot_fill attempt=2` × 2, of
which 1 came back usable**. So a re-asked page does sometimes come back different — 1 of 2, n=2.
2.9 is not pure cost. Request 94 recorded `slot_fill_contract_retry_skipped_low_runway` and has **no
attempt-2 rows at all**: the runway gate refused every retry with no time left, exactly as designed.

**Q4 — appspec's wasted AI time went from 13 % to zero.** No `usable=false` appspec row on any of
the three runs, against 18.7 s a run across trios 2-5. Codegen still has plenty (2/6, 3/14, 13/21)
but those are `transport` — post-deadline refusals — and `rejected`, which 2.9 files deliberately.

**Q5 — answered by the instrument added the same day.** 93's single `listing_not_schedule_rail` fire
is on `src/pages/ServicesPage.tsx` and resolves to **`public-service`** — the subset the contract
clipping never touched, because `public-service` is 4,899 chars and was never over budget. So this
fire is **writer judgment, not prompt vocabulary**, and the `0082f5f` fix cannot have moved it.
One fire is not the population, but the question is now answerable off the record instead of guessed.

**Q6 — confirmed live, and both this document and the pre-flight named the wrong consumer.**
Request 93 declared **9 catalogue routes**; `_catalogue_routes_context` over its real route list
returns 10,000 chars beginning `{"truncated":true,"preview":…}`. But that function is **never used to
prompt the architect** — it lives in `architect.py` and its only callers are `fix_agent`
(`:482`, `:530`) and `chat_rebuild` (`:245`). It takes the *completed* architect dict. So the
collapsed context is what the **fix agent** receives, which is worse rather than better: the repair
path is the one that most needs each page's contract, and on 93 it ran twice for 147.8 s of AI.
Corrected wherever it was stated.

**Q7 — `visual_review_status` names a reason where there is a record to name it on.** 93 reports
`partial`, a real status. 92 and 94 report nothing, because they stored no `preview_app` at all —
which is 1.12, not a regression in `2d69917`.

**Q8 — one clean run, not three.** 93's gate carries no `dead_link` code. 92 and 94 produced no gate
verdict. The confirming trio is still owed.

**Q9 / Q11 — the clock held and the ship rate fell.** 3 of 3 under 600 s makes this the second trio
to clear the cap, but **`blocked_seconds` was 0.0 and contention was zero on every lock**, so it
tested three sequential-in-practice runs and says nothing about concurrency. The DoD row's own words
are *"including 3 runs started 60 s apart"* — that half is still unproven. Meanwhile **0 of 3
shipped**: 93 was withheld on 4 gate issues (`visual_defect_severe` ×2, `listing_not_schedule_rail`,
`placeholder_content_shipped`), and 92 and 94 are **1.12 reproduced twice**, both with `appspec`
consuming ~62 % of the budget before the preview pipeline had finished planning.

**Q10 — n=1, and on that one run the tail is not AI at all.** Only 93 stored an `elapsed_seconds`,
so the decomposition has one sample: **tail 32.0 s, of which 0.1 s is AI (a single `vision` call) and
31.9 s is not** — against the nine-run baseline of 33 % AI / 67 % non-AI, and at the low end of that
corpus's 33-80 s range. Judged pages, the axis that killed 1.11's first attempt: **`visual_pages_reviewed`
= 3**, `visual_review_status` = `partial`. Both axes moved the right way and neither is a population.
**`tail.py` hardcodes `RUNS = [74…82]`** and skips a run with no stored elapsed, which is why this
question was not in the first write-up — the numbers above come from running its own query against
92-94 by hand. Parameterize it before the next trio or the work repeats.

That same record carries the **first live output of `3fc04ca`**: `render_pages_checked = 10`,
`render_pages_eligible = 10`, `render_pages_skipped = 0`. The fields are populated in production, and
93 declared few enough routes that the 12-route cap never bound — so this run confirms the
instrument, not the cap.

**The through-line: Q1 and Q9 are the same finding.** Bounding `appspec`'s repair loop is no longer
a p50 optimisation — on this trio it is the difference between a preview and an empty record.

### Duo 1 (95-96), in detail — the fix landed, did not fire, and the runs improved anyway

**Two runs, not three, and deliberately.** The DoD row's *"3 runs started 60 s apart"* is the only
thing three buys: `blocked_seconds` was recorded on just **4 of 16** runs across the whole corpus,
and trios 3, 4 and 7 collided on none. The questions 1.13 had to answer are binary — did the
reservation fire, did appspec cap per request, did the duplicate authoring pass go away — so a third
run adds a sample to something that is not a rate. **The briefs are requests 92 and 94 verbatim**,
the two runs that stored nothing, so the bound is the only intended variable. `analyse.py duo1`.

| | 95 (was 92, restaurant) | 96 (was 94, hotel) |
|---|---|---|
| shipped | **`ready`, 0 gate issues** | **`ready`, 0 gate issues** |
| wall clock | 571 s | 573 s |
| appspec AI / calls | **43.2 s / 2** (was 336.5 / 7) | **94.3 s / 5** (was 331.6 / 10) |
| accepted AppSpec | **yes, first authoring call** | no — `trace_evidence_mismatch` |
| fresh authoring chains | **1** | 2 |
| asks over 120 s | 0 | 0 |
| contention | 0.0 s | 0.0 s |
| render smoke | 12 checked / 13 eligible / **1 skipped** | 12 / 19 / **7 skipped** |

**Ship rate 0 of 3 → 2 of 2 on the same briefs.** And **1.13 cannot claim it.**

**Neither bound fired.** No `stopped_low_downstream_runway`, no `call_budget_exhausted` in
`api_duo1.log`; the only such lines in the container's history are July runs. Calls were 2 and 5
against a ceiling of 8, and appspec never approached the 260 s elapsed at which the reservation
engages. **The new code did not execute its new paths on either run**, so what improved is not what
was changed. Recorded here rather than quietly credited, because "a fix moved a metric" has been
wrong in this project twice before.

**What did change is acceptance, and it is the mechanism this document already predicted.** 95's
spec was accepted on its first authoring call and appspec cost 43 s; 96's never accepted, so the
stage was re-entered and cost 94 s. Accepted → cheap, rejected → roughly double: exactly the
bimodality `appspec_cost.py` measured. **So trio 7's 0-of-18 acceptance now reads as an unlucky
sample rather than a regression** — which is also the most parsimonious reading of *"1.12 reproduced
twice in one trio"*, since both facts have the one cause. Softened wherever it was stated.

**p50 did not move, and the bottleneck is not appspec.**

| stage | 95 AI | 96 AI |
|---|---|---|
| **codegen** | **315.0 s / 24 calls** | **436.9 s / 33 calls** |
| refine | 136.9 s / 13 | 166.0 s / 14 |
| design_critic | 127.5 s / 12 | 149.2 s / 20 |
| appspec | 43.2 s / 2 | 94.3 s / 5 |

571 s and 573 s, both past the 540 s deadline and under the 600 s cap. **Bounding `appspec` cannot
bring p50 under 500 s while codegen alone is 315-437 s of AI**, and 96 already degraded
`slot_fill_contract_retry_skipped_low_runway` at 381 s, so codegen is hitting its own runway guard.
**This is the evidence for taking (A) after all** — not because 1.13's bound failed to land, but
because the measurement says appspec was never the dominant term. Owner ruling pending.

Caveats, none of them small: **n=2**, contention 0.0 s on both so nothing about concurrency was
tested, and two concurrent runs put less pressure on `_SESSION_LOCK` than three, so the wall clock
is **not** a like-for-like against the trio baselines.

### The codegen census — 41 % of the p50 term is not codegen

`scripts/measure/codegen_cost.py`, over duo 1. It reconciles exactly with the table above
(315.0 + 436.9 = 751.8 s), and then splits it three ways:

| writer | calls | sec | sec/run | re-asks | re-ask s | discarded s |
|---|---|---|---|---|---|---|
| `slot_fill` | 40 | **410.7** | 205.3 | 15 | 125.4 | **295.4** |
| `(unattributed) pre-architect` | 11 | **310.7** | 155.4 | 0 | 0.0 | 45.7 |
| `utility_content` | 6 | 30.4 | 15.2 | 0 | 0.0 | 0.0 |

**The unattributed bucket is the plan phase.** `record_usage` derives a row's `stage` from the active
`ai_call` scope and falls back to the run **purpose** when there is none (`admin_ops.py:330`), and
`generate_preview_app` runs the *whole* preview pipeline under `ai_run_scope(purpose="codegen")`
(`pipeline/orchestrator.py:39`). `services/page_experience.py` had no scopes, so its asks were
recorded as `stage = codegen, writer = NULL`. Placed by timestamp against the `architect` call, all
eleven precede it. Named as of `46c28d2`: `planner`, `plan_validation`, `plan_expansion`,
`design_manifest`, under a `planning` stage.

Two of those writers had **no log line either**. `validate_and_expand_plan` loops two models,
swallows every exception, and logs nothing at all — it spent **69.9 s on request 95 and 94.0 s on
96**, two asks apiece, and neither the container log nor the census carried one word about it. It is
reached only when `canonical_seed` is `None`, which under `APPSPEC_MODE=shadow` is every run.

**`slot_fill` discarded 295.4 s of 410.7 — 147.7 s per run — and the pipeline knew.** 28 of its 40
calls were adjudicated `rejected`:

| rejection | count | what it is |
|---|---|---|
| `truncated` | 14 | **not truncation.** `finish_reason: error`, 0 completion tokens, ~1,165 chars of partial body, HTTP 200 |
| catalogue contract | 12 | the fill violated its own skeleton contract |
| missing export | 2 | |

The first row is a distinct defect: a 200 that failed mid-stream. `call_with_retry` never sees it —
the HTTP call succeeded — so the *application* re-asks and pays the whole prompt again. Across the
corpus since 2026-07-27: **79 calls carry `finish_reason: error`; 55 of them billed no output tokens,
for 474.4 s**, and 15 of those were recorded **usable** because nothing read `finish_reason` past
`length`. `presumed_usable` condemns that shape as of `46c28d2`, and *only* that shape — 24 other
`error` rows carry real completion tokens and 514.3 s of work the pipeline used.

**Measured on duo 2 (2026-08-05), and it was a bad day at the provider — not a standing cost.**
Session 10 asked for the rate to be checked on a fresh run before anything in the transport layer was
touched. It was:

| | `error` rows | of calls | with 0 completion tokens |
|---|---|---|---|
| duo 1 (95, 96), 2026-08-04 | **52** | 149 — **34.9 %** | 50 |
| duo 2 (97, 98), 2026-08-05 | **2** | 152 — **1.3 %** | **0** |

Both of duo 2's `error` rows carry real completion tokens, so the failed-mid-stream shape occurred
**zero times in 152 calls**. `slot_fill`'s discarded time fell with it — 147.7 s/run on duo 1 to
**83.4 s/run** on duo 2 (25 of 42 calls rejected, all `finish_reason: stop`). **Do not rewrite the
transport layer for this**; the remaining rejections are contract violations, which is a writer
problem and a different fix. What `46c28d2` added still stands: the shape is condemned when it
happens, and now there is a second measurement showing how variable "how often" is.

### `slot_fill`'s contract rejections — the transport half is closed, the contract half has a lead

**Duo 2, 2026-08-05:** 42 `slot_fill` calls, **25 rejected (59.5 %)**, 83.4 s/run discarded — and
**every rejected row carries `finish_reason: stop`**. So on a healthy provider day the rejections are
*entirely* the writer violating its own contract; the 14 "truncated" rows of duo 1 were the outage
above and are not a standing class.

**What the per-rejection errors say. n=4, so read it as a lead, not a distribution.** The validator
errors are logged at `codegen/generate.py:483-491` and stored nowhere, and duo 2's container log was
destroyed by a recreate before it was dumped (see the handoff). Four rejections were captured live
across requests 101 (restaurant) and 102 (dental practice), 25 `slot_fill` calls:

| page | errors |
|---|---|
| `AboutPage.tsx` (restaurant) | `detail painting-first hero (variant=item)`, `detail itemSpecs binding`, `detail inquire CTA (#inquire)` |
| `AboutPage.tsx` (dental) | `detail painting-first hero (variant=item)`, `detail itemSpecs binding`, `detail seed.credentials instead of itemSpecs` |
| `ServicesPage.tsx` | `SkeletonComposer invocation`, `assigned skeleton literal`, `slot:hero`, `slot:features`, `slot:testimonials`, `slot:cta`, … |
| `TreatmentsPage.tsx` | `missing directory face component:PageHeader`, `missing BRAND_MANIFEST services binding` |

**Two of four are the same defect in two unrelated industries**, and it is the art gallery again. An
About page is being assigned the `public-detail` skeleton, whose contract
(`catalogue_contract/validate.py:227-244`) *requires* a **painting-first hero**, an `itemSpecs`
binding and an `#inquire` CTA. The comment above that block names its origin: it was written against
**request 50, a fine-art gallery**, to stop the model swapping a painting for a marketing billboard.
The corpus is 25 art galleries, so the contract was fitted to them — and now the model, writing a
perfectly reasonable About page for a dentist, fails three assertions about paintings and has its
work thrown away for a deterministic scaffold.

Three questions follow. **The first is answered as of 2026-08-05 (session 12); the other two are
not.**

1. **Why is `AboutPage.tsx` assigned `public-detail` at all? — ANSWERED, and fixed (`0e678fa`).**
   `_infer_skeleton_id` (`ui_catalogue.py:645`) matched the **bare substring `"detail"`** anywhere
   in the blob `_search_text` builds from a page's id, title, page_type, purpose, layout, path and
   role labels. Ordinary English therefore decided a page kind. Demonstrated on stored production
   routes, with the route text alone and no plan merged: request 76's `/contact` ("guest inquiries
   and lodge contact **details**.") and request 79's `/about` ("Page **detailing** the story and
   ethos") both resolve to `public-detail`.

   **The rate, over the 399 stored public routes:** 95 reach the detail branch, **94 of them on the
   bare word alone**, and **35 of those name no item in their path at all**. It is not only About
   pages — `/book`, `/booking/checkout`, `/booking/confirmation` and `/patient/treatment-plan` were
   all being judged against a painting contract. 16 of the 76 stored About/OurStory/Contact routes
   ship `skeleton_id: public-detail`.

   The rule is now structural: a path that selects one item. **Not proven in production** — no run
   was possible.

   One thing this could *not* establish offline, and it is worth knowing before the next attempt:
   for most of those 16 the route text alone resolves to `public-service`, so the stored
   `public-detail` came from the **plan page** merged under the route. **Plans are not stored** —
   `preview_app.roles` keeps role ids and no pages — so which of the two mechanisms fired on any
   given run is not recoverable. Add it to the "prompts are not observable" note: *plans are not
   observable either.*
2. **How much of duo 2's 59.5 % is this?** Still unmeasured — the only record was the destroyed
   log, and no run has been possible since.
3. **Is the `public-detail` contract right even for a gallery?** Untouched. It hard-codes one
   page's design decisions as a validity condition, which is the shape of defect this document
   keeps finding.

**Dump `docker compose logs api` the moment a run finishes.** If one error dominates, that is the
fix; if they are scattered, the contract or the prompt is wrong and that is a bigger decision than a
retry.

**What the next run should read, now that the assignment is fixed:** whether `AboutPage.tsx` and
`ContactPage.tsx` still appear in the rejection log at all. If they do, the remaining cause is the
plan page rather than the route text, and question 1 is only half answered.

### p50 — the recommendation is (A), and this is the arithmetic

**Owner ruling pending; this row is not moved here.** Per-run AI seconds on duo 1, after the census
re-attributes the plan phase:

| term | s/run | |
|---|---|---|
| `slot_fill` | **205.3** | of which **147.7 discarded** |
| planning (planner + validator + manifest) | **155.4** | |
| `refine` | 151.5 | |
| `design_critic` | 138.4 | |
| `appspec` | **68.8** | the stage 1.13 bounds |
| everything else | 144.3 | vision, architect, fix_agent, seed, blueprint, demo, utility_content, analyze |

**Deleting `appspec` outright does not reach a 500 s p50.** It is 68.8 s of 863.7 s of AI per run —
**8 %** — against runs measured at 571 s and 573 s wall clock. The (B) experiment was run, the bound
landed, and it did not fire on either duo run; the answer the measurement gives is (A).

The four largest terms — 650 s/run, **75 % of a run's AI** — are all per-page fan-out, which is
exactly what 2.1-2.5 removes by construction. And the single largest recoverable number in the
pipeline is **147.7 s per run of `slot_fill` output the pipeline itself threw away**, which no bound
on appspec can touch.

**Recommendation: take (A).** Move the p50 row to Phase 2 and keep 1.13's bound on its own merits —
it caps a tail trio 7 proved is real (7, 6 and 10 calls against a configured 6) — without crediting
it with p50 movement it has not produced.

### The menu is redundant by construction, and every business gets a collection

**Owner-reported on 2026-08-04 and confirmed against duo 1 the same day.** Two defects, both
*general* — they are not one industry's problem and must not be fixed with an industry special case.

#### 1. `navigation` publishes the same links under several keys

`src/data/mock.ts` exports one `navigation` object whose role keys overlap almost totally:

| run | keys that carry the same links |
|---|---|
| 95 (restaurant) | `public` and `customer` are **identical** (Home, Gallery, Our Menu, Profile, Reservations, Private Events); `staff` is `admin` plus two role labels |
| 96 (hotel) | `admin` and `features` are **identical** (AI features, Activities, Bookings, Dashboard, Login, Rooms); `customer` is `public` ± one item |

It also emits two exports for one array — `navItemsAdmin = navigation.admin` and
`adminNavItems = navigation.admin` — and duplicate destinations *inside* one menu: 95's public nav
labels `/my-reservations` as **"Reservations"** while a separate `/reservations` route exists, so the
menu shows one "Reservations" and the app serves two. 96 carries "Login" and "Contact" in both
`public` and `manager`.

**There is no single source of truth for a menu**, so which links a shell shows depends on which key
it happens to read, and two shells reading different keys disagree about the same app.

**Resolved 2026-08-04 (session 10), statically and decisively: the duplicate keys are invisible.**
Every consumer of `navigation` in the shipped app was enumerated:

| reader | key |
|---|---|
| `app-nav.ts:113` `sectionLinks('admin')` | `nav.admin` |
| `app-nav.ts:114` `sectionLinks('member')` | `nav.member \|\| nav.public` |
| `app-nav.ts:115` `sectionLinks('public')` | `nav.public` |
| `PublicLayout.tsx:6` | `navigation?.public` |
| `AdminLayout.tsx:5` | `navigation?.admin` |
| `aiHubHref()` | every key, but only to find `/ai-features` |

`customer`, `staff`, `features` and `manager` are **read by nothing**. `navItemsAdmin` and
`adminNavItems` in `mock.ts` are **imported by nothing** — every ops page calls the
`useAdminNavItems()` hook and names its *local variable* `adminNavItems`, which is what makes a grep
look like a consumer. So the redundancy is real, it is dead data, and **no shell renders it twice**.
Screenshotting was the right instruction and the static answer is stronger than one would have been.

**What IS on screen is a different defect, and it is the one worth fixing.** Request 95's public nav
is Home, Gallery, Our Menu, Profile, Reservations (capped at 5, `Private Events` dropped). That
"Reservations" is **`/my-reservations`**, and `/reservations` — a declared public route serving
`ReservationsPage.tsx` — is **absent from `navigation.public` entirely**. The header names the member
page with the public page's name and never links the public page.

**Corrected 2026-08-05 (session 11), and the attribution above was wrong.** The sentence that stood
here said `shortLabel` strips the leading `My ` at `app-nav.ts:20-31`. Read out of the shipped
workspace, **`mock.ts` already carries the label "Reservations" on `/my-reservations`** — the strip
happened in the *generator*, at `safety/mock_data._NAV_LABEL_NOISE_RE` (`mock_data.py:1016`, the same
`^(welcome|manage|my|the)\s+` rule). And the reason `/reservations` is missing is one line further
on: `_normalize_nav_section` deduped on the **label key** as well as the path, so a route whose
shortened label was already taken was **dropped from the menu entirely**. Request 95's route table
declares 13 routes including `/reservations` at `layout: public`; the nav has six entries.

So the two halves are the same rule at two layers, and both are landed (`8fe8955`):

1. **The generator (`_nav_labels_for_section`).** A duplicate *destination* is redundancy and still
   collapses. A duplicate *label* is a naming clash: it renames, it never deletes.
2. **The template (`app-nav.shortLabels`).** Same rule for the labels the shell renders.

Both are about the **list** — shorten only while the shortened form stays unique among its siblings,
then fall back through the full label to a path-derived one — and never about a route name;
`/my-orders` and `/orders`, `/my-bookings` and `/bookings` are the same shape. Deciding entry by
entry is not enough and is mutation-tested as such: whichever entry came first would take the short
label and the other would still collide. Session 10 wrote (2) alone, measured that it changes nothing
without (1), and reverted it — which was right, and is why they landed together.

#### 2. Every business gets a gallery, whatever the business is

A **twelve-table Neapolitan trattoria** shipped `src/pages/GalleryPage.tsx` **and**
`src/pages/ArtworkDetailPage.tsx`, routes `/gallery` and `/gallery/:id`, a "Gallery" nav item, and a
hero CTA reading **`{ label: 'Explore the collection', href: '/gallery' }`**. The lakeside lodge got
`/gallery`, `/gallery/:id` and `/gallery/:slug`.

"Explore the collection" and an `ArtworkDetailPage` are **art-gallery vocabulary reaching an
industry that has no collection**, and it is the same bias the corpus already shows elsewhere
(request 22's `ArtworkDetailPage` at `/artwork` and `/gallery/:id`). A restaurant has a menu, a lodge
has rooms; neither has a collection to explore.

Related and visible in the same run: **route alias inflation.** 96 serves `/rooms/:roomId`,
`/rooms/:id` **and** `/rooms/:slug` for one page, plus `/gallery/:id` and `/gallery/:slug` — the
synthesised aliases the evidence README describes, now three deep on a single resource.

**Measured 2026-08-04 (session 10), and it is not where DoD 7 is looking.** Request 96's architect
declared **19 routes with no duplicate `component_file` at all**; the router in `App.tsx` serves
**23 paths**. The surplus is minted by `assemble.py:1098`, which appends `{base}/:id` and
`{base}/:slug` for every param-free listing with a detail component — and `registered` is keyed on
the exact path string, so an architect-declared `/rooms/:roomId` does not block either of them.

Two consequences:

1. **DoD 7's corpus cannot see this defect.** `docs/evidence/architect-routes.json` is the
   *architect's* table; measured over it, 11 of 42 runs have 12 surplus paths, **zero** three-deep
   and **zero** differing only in the parameter name. The three-deep inflation lives strictly
   between the architect and the router, so DoD 7's non-injective file→route number is real but is
   counting something else.
2. **Deleting the aliases would break the page.** `catalogue_contract/scaffold.py:466` reads
   `params.id ?? params.slug` — it cannot read `roomId`. The aliases exist *because* the scaffold's
   param reader is hardcoded to two names. So the fix is the other direction: have the scaffold read
   the single declared param whatever it is called, after which one route suffices and both aliases
   can go. That is a template-side change and wants a run to verify, so it is written down here and
   **not landed**.

**The fix must be general.** Not "suppress gallery for restaurants" — a rule that decides whether a
business *has a collection* at all, applied the same way for every industry, with the CTA vocabulary
following from the entity rather than from a default. Anything keyed on an industry string is the
`generic`-industry defect wearing a new hat. **2.1-2.3 owns this**: one route per file by
construction, and page identity derived from the spec rather than appended by a template.

**Located exactly, 2026-08-05 (session 11). It is not an inference at all — it is a literal.**

```
product_kind.py:475-496   _storefront_pages()
    PageBlueprint("gallery",        "Gallery",  "/gallery",     ... "GalleryPage.tsx")
    PageBlueprint("gallery_detail", "Artwork",  "/gallery/:id", ... "ArtworkDetailPage.tsx")
product_kind.py:1008-1010
    elif contract.kind in PUBLIC_KINDS:
        routes, files, _ = _inject_blueprint_routes(routes, files, contract, role_id)
```

Every brief that classifies `storefront` is gap-filled with those two pages, **even when
`_routes_are_substantive(routes)` is already True** — the `elif` exists precisely to gap-fill a
substantive inventory. So `ArtworkDetailPage.tsx` on a trattoria is one hardcoded blueprint page,
and the string "Artwork" is a `PageBlueprint` title, not a model's word.

**Two corrections, 2026-08-05 session 12, both from re-deriving the classification properly.**
This paragraph said *"`storefront` **or `booking_service`**"* and that is wrong: a
`booking_service` contract carries `_booking_pages()` — home, `/services`, `/book` — and has no
gallery in it at all. The dental brief is a `booking_service` and has never been given a gallery;
requests 75-93 were gap-filled `/services` and `/book`. And the corpus figure was **15 of 17
distinct briefs**, not 16 of 18: 17 distinct (name, industry, description) briefs across the 88
stored requests, of which 15 `storefront`, 1 `booking_service` (Northgate Dental) and 1
`saas_workspace/generic` (PlateSync ERP). Both errors came from the same place — a census that
called `resolve_product_kind_contract(*context_from_request(req))`, splatting a *string* into one
character per argument so that every brief fell through to the `storefront` default. See the
gap-fill row in Status.

**It survives an enforced AppSpec.** Replayed from request 95's accepted 4-page contract, the
canonical route list holds through `merge_architecture_enrichment` and then
`apply_product_kind_to_architect` (`plan_phase.py:305`) adds `/gallery` and `/gallery/:id` — 4 → 6.
Same on 97, 7 → 9. **Nothing else added a route on either run.** So the enforcement work and this
defect are independent: a contract that names four pages does not stop the sixth being appended.

**Fixed 2026-08-05 (session 12), `bbe6359` — and it does not close the enforced case.** The
gap-fill now adds a blueprint page only when nothing in the app already serves it: the same path,
or the same resolved page contract, asked of the plan page merged under the route. A detail page is
added only when the listing it belongs to is served and has no detail child of its own. **In shadow
mode the trattoria loses both pages** (requests 77, 83, 95, 97). **Under enforcement it does not**:
the replay above still shows 4 → 6, because the AppSpec page for `/menu` reads *"To display the
current food and wine menus."* and nothing in that resolves it to a catalogue — the capability id
`CAP-BROWSE-MENU` would, and `_search_text` does not read capability ids. Recorded rather than
patched, because `APPSPEC_MODE` is `shadow` and turning it on is an owner decision. Detail and the
measured boundary are in the Status row.

### The catalogue census — a third of it is dead, and that is one fact, not two

Measured 2026-08-05 over the 62 archived workspaces that shipped pages, by parsing `import { … }`
statements in `src/pages/**.tsx` (a substring census is not sound here: `OpsShell` appears as a bare
word in 60 workspaces and is *imported* by 60 — but `ProductShowcase` appears in 62 and is imported
by 56, and `Table` appears in 10 and is imported by 1).

**9 of 46 catalogue components have never been imported by any page ever:** `Tooltip`, `AccentBeam`,
`ResultRail`, `EmptyState`, `InvoiceBoard`, `ReconSplit`, `BlotterTape`, `DeskTicker`,
`ExpenseQueue`. **5 of 15 skeletons have never been selected:** `ops-ledger-home`,
`ops-invoice-board`, `ops-recon-split`, `ops-blotter-desk`, `ops-expense-queue`.

**The selector, and why it is right.** `classify_product_kind` (`product_kind.py:240`) →
`resolve_product_kind_contract` (`:538`). Run over the **18 distinct briefs** in the corpus:

| kind / subtype | briefs |
|---|---|
| `storefront` / `storefront` | 16 |
| `booking_service` / `booking` | 1 |
| `saas_workspace` / `generic` | 1 |
| `internal_ops` (any) | **0** |
| `saas_workspace` / `trading` or `accounting` | **0** |

The trading subtype (`:545`) and the accounting subtype (`:579`) are the *only* paths that emit those
five skeletons, and no archived brief reaches either. So the five dead skeletons and the five dead
ops components (`InvoiceBoard`, `ReconSplit`, `BlotterTape`, `DeskTicker`, `ExpenseQueue`) are **one
fact: nobody has ever asked this pipeline for a trading desk or a bookkeeping workspace.** That is
correct behaviour, not unreachable code, and **rotating skeletons for variety would put a ledger desk
on a restaurant — the art gallery again**. The remaining four (`Tooltip`, `AccentBeam`, `ResultRail`,
`EmptyState`) are a *different* and much smaller question: they have no skeleton slot that names them
except `results`/`empty`, which no skeleton in `catalogue.json` declares.

**And the corpus itself is the caveat.** 62 workspaces, **18 distinct briefs, 12 distinct business
names**, 25 of them one art gallery. Any statement of the form "N of 62 runs" in this document is
closer to "N of 18 briefs" than it sounds.

**The chrome / layout split, which is what makes this actionable.** Of the 15 components imported by
≥ 90 % of runs:

| | components | verdict |
|---|---|---|
| **Chrome** — the app frame, legitimately universal | `PublicShell` 100 %, `PublicNav` 100 %, `BrandFooter` 100 %, `PageHeader` 100 %, `OpsShell` 97 % | correct at 100 %. A page needs a shell, a nav and a footer |
| **Ops-page primitives, universal *because the console is universal*** | `StatCard` 90 %, `DataTable` 97 %, `FilterBar` 97 %, `ActivityFeed` 95 %, `ChartCard` 89 % | these are the owner console's slot defaults. They are at 90 %+ because **a five-page ops console is appended to storefronts that never asked for one** — the same routes enforcement removes |
| **Layout choices that should vary and do not** | `MarketingHero` 100 %, `CTABand` 100 %, `FeatureBento` 98 %, `TestimonialRail` 98 %, `ProductShowcase` 90 % | **this is the visual monoculture on screen.** Every public home page in the corpus is hero → features → showcase → testimonials → CTA → footer, in that order |

The third row is the one to attack, and it is Phase 3's (`within-recipe axes`), not a bug to patch.

### 2.9, in detail — the fix, and what bounds it

The predicate is the part worth reviewing. The obvious implementation rejects on
`validate_catalogue_page_content` errors; that is **wrong and expensive**, because
`enforce_catalogue_page_contract` repairs a broken `SkeletonComposer` invocation and back-fills
missing slots before it gives up. A page missing one slot is contract-invalid *and* free to fix, and
re-asking for it spends ~50 s to arrive at the same file. So the rejection test is enforce's own
verdict — reject exactly what would be thrown away, and nothing else — pinned by
`test_a_fill_enforce_can_repair_is_not_re_asked`.

Cost is bounded three ways, and only the third is new:

1. `_MAX_SLOT_FILL_ATTEMPTS = 2` per page, which already existed and had never been reached.
2. `PREVIEW_MAX_AI_CALLS` (96), which already covered these calls.
3. `_has_contract_retry_runway()` — a contract retry is discretionary and will not start unless
   `DEFAULT_ASK_CEILING_SECONDS + RESERVE_SECONDS` remain, so the worst-case ask still leaves the
   post-deadline smoke pass its reserve. Syntactic retries stay ungated: they fire on already-broken
   files and effectively never happen. A skipped retry records
   `slot_fill_contract_retry_skipped_low_runway` — never silent.

The ~4-extra-asks-per-run estimate in the original filing overstates the wall clock: codegen pages
generate in parallel, so those asks overlap rather than sum. Contract rejections now also file as
**unusable** in the call census, so the next trio can measure the retry's cost and its hit rate
instead of estimating them.

Seven mutations, zero survivors —
[`backend/scripts/cli/mutate_slotfill_contract_retry.py`](../backend/scripts/cli/mutate_slotfill_contract_retry.py).
The first pass had one survivor (the census adjudication), which is why
`test_a_contract_rejected_fill_is_filed_as_an_unusable_call` exists.

**What is still unmeasured:** whether re-asked pages actually come back *different*. The fix
guarantees a second ask with the specific errors; it does not guarantee the model uses it. That
needs a funded trio, and it is on the first-funded-trio pre-flight list.

### What request 73 verified, and what it did not

Same brief as request 72, deadline armed on both.

| | 72 (before `58b4956`) | 73 (after) |
|---|---|---|
| wall clock | **~37 min** | **579 s** — under the 600 s cap |
| degradations | none recorded; the clock expired and the run kept asking | `['tech','proposal','build_plans']`, all ELECTIVE, all recorded |
| overrun past the 540 s deadline | ~1,700 s | **38.7 s** |

- **1.9 exercised for the first time on ≥ 9 items.** 73's catalogue is **12 items**;
  all 12 bind `item1…item8` (1–4 cycling twice), and **zero** land on
  `images.card1/2/3` — the people-photo role slots that produced "artist at an easel,
  captioned *Oil on Linen*" on request 70.
- **`placeholder_content_shipped` fired on its first live outing** — `[Customer Name]`
  and `[Painting Title]` — and correctly withheld the preview.
- **The detail page scored 79** against 0–5 on 66–68, when the critic was fetching
  `/painting/:id` literally.
- **73 was still withheld**: 4 gate issues, including a severe visual defect on
  `/about-artist` and a dead link. Phase 1 bought the clock and the honesty, not the
  ceiling. Phase 3 is where the ceiling moves.

**Two defects were found by running the pipeline, not by reading it**, and both
were in the deadline work itself. They are written up at `58b4956`; the short
version is that a 1 s ask floor past the deadline inverted the degradation
contract into a fast-fail retry loop, and `_run_with_heartbeat` only checked
its cap once per 20 s heartbeat, so a short cap could not fire. Request 72 ran
**~37 minutes with the deadline armed and expiring on schedule**. The second bug
predates this work: any caller passing a `hard_deadline` under 20 s has always
been silently rounded up to 20 s.

### Two deliberate deviations from this plan, both still standing

1. **`PREVIEW_MAX_FIX_LOOP_SECONDS` was clamped, not deleted.** 1.1 says delete it.
   It is read by callers that have no other bound, so deleting it removes a ceiling
   before the deadline is proven to replace it on every path. Clamped to the request
   deadline instead; revisit once Phase 1's DoD has 3 clean concurrent runs.
2. **`BudgetedAIProvider.ask_chat` still returns `""` rather than raising.** 1.1 says
   raise. Making it raise broke 5 tests that pin *outcomes* (deterministic fallbacks
   preserved), not the mechanism — and the plan's own justification for raising is a
   Phase 2 condition ("under Phase 2 a silent empty string ships a blank site"). Today
   raising converts proven degradations into a pipeline exception that triggers the
   180 s retry. **Exhaustion is now recorded** (`ai_budget/exhausted_chat`), so it is
   no longer silent. Deferred to Phase 2, documented at `ai_budget.py:_refuse`.

---

## Diagnosis

Three failures wearing one complaint.

**1. Sameness is axis collapse inside one kit.** The type system permits ~7.46 × 10⁸
combinations and renders **~5 perceived designs**. `recipe.ts:29-82` is six
`Record<RecipeId,…>` maps keyed by one enum; 8 of 11 public bands have zero layout variants;
`CatalogGrid.tsx:145` is a single three-column grid for every business on earth; and the emitted
`@theme` block (`index_css.j2:5-23`) declares **no type scale, no spacing scale, no container
width, no grid tokens**. Every site is the same six bands, at the same measure, in the same flat
stack (`SkeletonComposer.tsx:91-98`).

**2. Latency is model wall-clock, spent serially.** AI time is 1.01–1.06× of total wall clock on
all three audited runs. The build substrate is innocent: npm attach 0.0005 s, vite 0.52–0.63 s,
tsc 1.75–1.83 s — **under 12 s of a 688 s run**.

**3. The variance, not the mean, breaks the 600 s promise.** Request 68's quality-repair loop was
882.2 s — 52.7 % of the run — **for zero applied file operations**. Two of three audited runs
shipped nothing at all.

---

## What request 70 changed, and what it cost us to learn

Requests 66/67/68 were created with an **empty `industry` field** — a test-harness omission.
Request 70 is the same business description with the field populated. The delta:

| | 68 (`industry=''`) | 70 (`industry` set) |
|---|---|---|
| `imagery subject` | `generic` | `art` |
| catalogue cards showing a painting | **0 of 3** | **9 of 11** |
| `seed.items` | 3 marketing blurbs, rendered as inventory | **11 real records** with medium, dimensions, year, price |
| dead links | 8 across 5 pages | **0** |
| quality gate | FAILED, withheld | **PASSED first pass, no repair invoked** |
| terminal state | `preview_url: null` | shipped |

**Three plan-level consequences.**

- **Imagery is no longer the hard problem.** The remaining defect is a bound, not a content-
  verification problem: the imagery service supplies **8** `item*` slots, the model wrote **11**
  items, so items 9–11 wrap onto `images.card1/2/3` (`mock.ts:459,471,483`) — and `card2`/`card3`
  are the role images ranked last *precisely because they show people*. That is why 2 of 11 cards
  are a photograph of someone at an easel captioned "Oil on Linen". **Cap items at pool size, or
  extend the pool.** Hours, not weeks.
- **The pack-coverage thesis needs re-testing before it is funded.** The audit found ~half of
  businesses miss an industry pack via `_MIN_DISTINCTIVE_TOKEN_LEN = 6` (`loader.py:43`), which
  rejects `spa`, `gym`, `yoga`, `cafe` — packs that exist. But the pack matched on **both** 68 and
  70 (`art-gallery-portfolio-home`), even with an empty industry. Pack selection was not the
  failure here. The token bug is real; its blast radius is unproven.
- **A scaffold is only as good as the seed it reads.** Fallback count did not improve (4 of 12 →
  5 of 17), but the *consequence* inverted: the same scaffold that rendered blurbs as inventory on
  68 produced the best gallery page the pipeline has shipped on 70. Do not spend on the fallback
  rate; spend on seed quality.

**And one genuine product defect the experiment exposed:** the pipeline accepted an empty
`industry`, had `"fine-art gallery … original oil paintings"` sitting in the description, and
silently resolved to `generic`. No warning, no derivation, no gate.

---

## Verdict on the "content as data" hypothesis

> *Four AI writers emit TSX; flipping to "AI emits structured content, templates are pure
> renderers" makes templates cheap, deletes the repair machinery, and clears 600 s.*

| Claim | Verdict |
|---|---|
| Deletes the repair machinery | **True.** ~2,500 lines delete outright (`fix_agent.py` 460, `quality_repair.py` 433, `deterministic_repairs.py` 69, four `build_phase.py` blocks ≈ 250, `preview_app_fix.j2` 89, `preview_app_file.j2` 254, `quality_gate.py:819-916` ≈ 98). Two rollback systems vanish as a side effect. |
| Clears 600 s | **False.** Post-flip mean ≈ **411 s**, but the worst audited run *minus its entire repair loop* is still 757 s. The flip cannot bound the tail. **600 s is won in Phase 1 by a deadline, not by the refactor.** |
| Templates become cheap | **Only with one specific correction** — the deterministic renderer must move out of Python into the template. And it was never the variety lever. |
| "Every template is a new language for the model" | **False.** The model never sees the template — only a contract compacted to 4,900 chars (`ui_catalogue.py:70-74`). Adding templates multiplies **Python emitter and validator** cost, not prompt cost. |

---

## The 100-templates question: the answer is three

| Path | Per template | ×100 |
|---|---|---|
| Re-skin the existing kit (same 46 exports, 30 slots, 265 props, all DOM contracts) | 60–110 h | **3.3–6.1 engineer-years** |
| An off-the-shelf React template with its own vocabulary — **this is what "100 React templates" means** | 240–460 h first, 120–220 h after | **13–26 engineer-years** |

Plus **23.5 GB** of `_shared_npm` at N=100 (235 MB per fingerprint, measured; there is no prune,
evict, or rmtree anywhere in `backend/app`), 100 forks of a 1,713-line fallback, and 187
template-reading tests to fork.

**And it would not fix the complaint.** 100 re-skins render the same one-layout bands, at the same
hardcoded `clamp()` scale, in the same flat stack.

**Do instead:** treat the 100 templates as a **design-reference corpus** — triage them into a
signed archetype spec sheet (grid logic, type ramp, spacing scale, container width, image
treatment). Same visual diversity, ~1 % of the cost, inside a kit that already satisfies all 68
conformance clauses. Then build **one** second kit, measure the real hours, and **cap at three**.

**The target is not a template count.** It is: *of 20 synthetic businesses, no two home pages and
no two catalogue pages share a silhouette.* Today: ~5 and ~1.

---

## Wall-clock ledger (run-67 shape, 688.0 s)

Every "after" figure has a named mechanism or it is not claimed.

| Stage | Now | P1 | P2 | Mechanism |
|---|---:|---:|---:|---|
| pre-preview blueprint + AppSpec | 94.3 | 94.3 | 94.3 | data dependency; not concurrent |
| preview start + AppSpec re-ensure | 9.1 | 9.1 | 9.1 | — |
| planning (product_kind, imagery, recipe) | 77.4 | 77.4 | ~68 | `build_design_manifest` concurrent with imagery |
| architect | 21.0 | 21.0 | 21.0 | — |
| codegen / content | 55.9 | 55.9 | ~35 | **content asks batched by surface — 3, not 12** |
| design critic + guards + assemble | 30.5 | 30.5 | ~20 | — |
| typecheck + fix agent | 161.4 | ~45 | ~5 | P1: JSON-extractor fix + chain dedupe |
| visual critique | 88.2 | 82 | ~50 | widen vision fan-out 2 → 6 (network-bound) |
| imagery verification (new) | — | — | +15 | one contact-sheet call, same wave |
| quality gate | 48.1 | ~40 | ~2 | evaluate only; repair deleted |
| refine + rebuild + re-measure | 23.0 | 23 | ~30 | conditional; expected value |
| render smoke + conditional re-probe | 42.0 | 42 | ~52 | **not merged with the critic pass** |
| finalize docs | 37.1 | 0 | 0 | off the critical path |
| **Total** | **688.0** | **~495** | **~411** | |

**Consistency check.** After P2 the mandatory logical-call floor is **16–17**. At the measured
~23 s/call for non-vision calls: 13 serial × 23 = 299 s + one vision wave ~30 s + capture ~60 s +
build ~5 s + deterministic ~20 s ≈ **414 s**. Ledger and census agree within 1 %.

**This ledger is historical as of 2026-08-05 (session 12).** It models the run-67 shape; keep it
for the mechanism column and do not quote its totals. Measured on requests 95-98: p50 is
**563-590 s**, not the ~495 the P1 column predicts; `typecheck + fix agent` did not fall to ~45 s
(`fix_agent` alone ran 147-150 s on 97); and the dominant term the ledger has no row for is
**`slot_fill` at 205.3 s/run, of which 83-148 s is rejected output the pipeline paid for and threw
away**, beside the plan phase at 155.4 s/run that the codegen census re-attributed out of
"codegen". The P2 column's mechanism — batch by surface — stands, and is *strengthened*: the
discard rate is a second, independent argument for it (see 2.4-2.5).

---

## Phase 0 — Measure first (1 week, no behaviour change)

| # | Question | Why it changes the plan |
|---|---|---|
| 0.1 | **Re-test the pack thesis.** Replay 60 days of real `industry` strings through `pick_template_id`; report hit / miss / wrong-family | Request 70 showed the pack matched even with an empty industry. **Sizes or cancels 1.8** |
| 0.2 | `P(refine fires)` per run; does a slot-filled page keep the scaffold marker? | Sets two ledger rows |
| 0.3 | ~~Fraction of gate blocking issues that are content-shaped vs layout-shaped~~ **ANSWERED — see below** | Gated 2.6, and the answer **reverses** the branch the plan had provisionally chosen |
| 0.4 | Are visual `revision_instructions` expressible as content-key edits? | **Gates 2.6** with 0.3 |
| 0.5 | Real `product_kind` distribution (60 days) — `plan_phase.py:119-124` already logs it | Decides whether Phase 3 spends on the 6 public or 9 ops skeletons |
| 0.6 | Per-call latency distribution + the call census | p95 must be **derived by convolution**, not by scaling a mean. Today p95/p50 = 2.4× |
| 0.7 | Test classification: **388 of 1,012** tests sit on TSX-source machinery | ~3× the original budget; goes straight into P2 staffing |
| 0.8 | Spec-level content-density metric, logged in parallel on the current architecture | The `fallback_pages` signal reads a literal marker; after the flip it reads 0 forever or 12 forever. Both are silent |
| 0.9 | Are the 3 script-style test files (2,061 lines, not pytest-collected) run by CI? | Assertions that may never run |

**Also land here:** fix `ai_usage_events.request_id` NULLs (39 of 58 rows in run 67, so per-request
queries undercount by ~⅔); make `success` mean *usable output*, not HTTP 200; add duration logs at
`typecheck.py:494-499` and around `build.py:83`; clean the leaked `mkdtemp(prefix="bmv-dist-")`
backups (`build_phase.py:134`, cleaned only at `:289-291`, outside the try).

### 0.3 answered — the repair edits content, not layout

88 ops across 19 stored repair plans (`.bmv-debug/quality_repair_plan*.json`,
requests 19-73), classified by **what each op actually changed** — a `difflib`
delta between `old` and `new`, not a pattern match over the new blob:

| what changed | ops | |
|---|---:|---:|
| string / identifier edits — `/gallery`→`/collection`, `item`→`artwork`, label and href renames | 41 | 46.6 % |
| content strings ≥ 12 chars | 29 | 33.0 % |
| routes and links | 5 | 5.7 % |
| **layout / structure** | **4** | **4.5 %** |
| changed nothing at all | 5 | 5.7 % |
| whole-file writes | 4 | 4.5 % |

**Method note, because it changed the answer.** A first pass pattern-matched the
*new* text and reported 34 % layout. That was an artifact: almost any TSX blob
contains `className` or `<Capitalised`, so layout won every tie. Diffing what
changed drops layout to 4.5 %. Sampling the "string / identifier" bucket shows
it is overwhelmingly copy and href renames, so the true content share is well
above 33 %.

**Consequence for 2.6.** The plan said: *if 0.3 shows "mostly layout, not
content", demote `visual_defect_severe` to WARN in the same commit that deletes
the repair.* That branch is **not supported** — layout is the smallest
identified category. A spec-level actor (visual finding → content-key edit) is
what the evidence supports, so 2.6 should build that and keep the BLOCK.

Still open: 0.5, whether the critic's `revision_instructions` are *expressible*
as content-key edits, which is a different question from whether the repair's
output happens to be content-shaped.

Worth a ticket on its own: **5 of 88 ops changed nothing**, and the model was
paid for every one.

**DoD:** all nine answered in writing with evidence; `(writer, calls, wall-clock, ops applied)` for
3 fresh runs; a fitted p50/p95 per model.

---

## Phase 1 — Make 600 s a guarantee (2 weeks)

**This is the phase that meets the hard constraint. Not Phase 2.**

**1.1 Request-scoped deadline with a degradation contract.** Stamp `deadline_at = t0 + 480` at the
top of `GenerationPipeline._run_inner`, **before** `blueprint.generate_mvp_blueprint`. Attach it to
the existing request-scoped `AICallBudget` (`ai_budget.py:18-45`). The retry at
`orchestrator.py:200` becomes conditional on `now() < deadline_at - 180` and **inherits the same
absolute deadline** — today it re-runs the whole preview generation with a fresh budget. Classify
every stage MANDATORY or ELECTIVE; the deadline skips only ELECTIVE, and a MANDATORY stage that
would cross it falls through to its deterministic default and records `degraded: [stage]`.
**`BudgetedAIProvider.ask_chat` must raise, not return `""`** (`ai_budget.py:61-63`) — under Phase 2
a silent empty string ships a blank site that passes both tsc and vite.
Delete `PREVIEW_MAX_FIX_LOOP_SECONDS = 900` (`config.py:714`) — 1.5× the entire user constraint.

**1.2 De-duplicate the model chains.** `quality_repair.py:332-337` resolves to
`('z-ai/glm-5.2', 'z-ai/glm-5.2', 'google/gemini-2.5-flash', 'google/gemini-2.5-flash')`, and
`_FAILED_FIX_MODELS` at `:346` is consulted only when *building* the list, never inside the loop at
`:349`. *(Saving is a subset of 1.1's, not additive.)*

**1.3 Per-ask ceiling, not per-call.** `_WALL_CLOCK_BUDGET_FACTOR = 2.5` × `timeout=120` ×
`attempts=2` = 600 s per logical call, and `hard_deadline` is per *attempt*, so model failover
doubles it again. Cap at **120 s per ask inclusive of all failovers and transport retries**. For
MANDATORY stages, **do not fail over on timeout** — degrade and record. Add an absolute socket
deadline that does not reset on byte arrival (one call was held open 1,040 s).

**1.4 Screenshot budget.** `capture_routes_visual(timeout_ms=20000)` applies that timeout **twice**
per route (`screenshot.py:158,163`) — ~40 s/route, serial behind `_SESSION_LOCK`, 12 routes = 480 s
worst case. Add a 90 s session budget; `timeout_ms` → 8000; `wait_until` `networkidle` →
`domcontentloaded` plus the existing `_ROOT_HAS_CHILDREN_JS` — `networkidle` makes the Pexels CDN a
latency dependency. **Merge only the pre-gate captures; keep the post-gate smoke pass unconditional**
(request 41 shipped `aiFeatures is not defined` under `status=ready`).

**1.5 Finalize documents off the critical path.** `orchestrator.py:247,254,261` runs three
document generations serially *after* the preview is built, for 37.1 / 49.8 / 22.8 s the user is not
waiting on. Mark ready first, then run them concurrently.

**1.6 Fix the JSON extractor. — DONE, and this section's original diagnosis was wrong.** It claimed
the failures were structurally complete JSON the extractor could not find. Measured against the six
captured payloads in `/app/data/preview-apps/{67,68,69}/.bmv-debug/fix-agent/`, that is true of
**one**. There were three distinct failure modes read as one:

- **Ours (1 of 6).** Prose before the fence. `_strip_markdown_fence_once` only fired at position 0,
  so the bracket matcher latched onto a `{` inside the model's opening sentence, failed, and
  `break`-ed instead of trying the next candidate. A valid repair plan, discarded.
- **The model's, and unfixable by re-asking (4 of 6).** Inside a ~30 KB `content` value the model
  escapes correctly for thousands of characters and then drifts — bare `"` where `\"` was required,
  or `\` + newline as a shell-style line continuation. Structurally complete, not valid JSON.
  Re-asking never fixed it because it is a habit, not a limit; requests 67 and 69 each burned three
  calls for zero applied ops.
- **A genuine truncation (1 of 6),** `finish_reason: length` from glm-5.2.

Fixed in `shared/json_utils.py`: strict parse first, then every fenced block, then a skeleton-tracking
re-escaping repair pass, then candidate spans — with the decoder's own error in the failure message.
6 of 6 now parse.

**The other extractors — closed, and the count above was wrong.** Replaying the four captured
payloads through every extractor in the repo scored `json_utils` 4/4, `preparse_normalize` **0/4**,
`page_experience` **0/4** (one of them a *partial*), `authoring_parser` **1/4**.

The two flagged as carrying "the original bugs" turned out to have **no production caller** —
`preparse_normalize.extract_json_object_text` is imported only by a test, and nothing imports
`pipelines/_shared.strip_fences` at all (the `_strip_fences` used across codegen, critic, fix_agent
and safety is a different function in `preview_app/text_utils.py`, already routed through the shared
extractor). Meanwhile a **fourth implementation that was never on the list**,
`domain/appspec/authoring_parser.py:76`, sits on the AppSpec authoring path — the 264-288 s stage —
and failed 3 of 4. Shapes 2 and 3 above are structurally complete, so it returned
`json_syntax_invalid` and `build_app_spec_candidate` re-asked a 28k-token authoring call for output
the model had already sent. **The 161 s re-ask waste was still live, on the most expensive stage in
the pipeline**, for every session that read this section and believed the extractor question was
closed.

Worse than any of the outright failures was `page_experience`'s partial. On
`request67_fix_agent_retry_unescaped_quotes` it returned a dict — three files, correct paths, first
two byte-identical, third's 15,143 characters of content replaced by `""` — with no exception, no
log and no `None`. Its truncation closer cannot distinguish an under-escaped complete document from
a truncated one, so it trimmed a recoverable document back until something parsed. Four live call
sites accept that as a plan.

All four now recover 4/4. `tests/test_json_extractor_parity.py` pins parity **and wholeness** —
equality against the shared extractor, because "returns a dict" is exactly the assertion the partial
would have passed — plus strict-first ordering, so a well-formed response can never reach a repair
path. `scripts/cli/mutate_extractors.py` reverts each fix and asserts the suite reddens: 5
mutations, 5 caught, 0 survivors.

**Two lessons, both cheap to repeat.** The extractor count came from the previous handoff rather
than from the code, and the code had one more. And a duplicate that fails *silently* outranks one
that fails loudly: measure recovered documents against a reference, never against `is not None`.

**The strategic read matters more than the fix.** Asking a model for a 30 KB JSON document with
escaped source code inside it is fragile by construction. That is an independent argument for
ops-only repair (small payloads do not hit this) and for the Phase 2 content flip.

**1.7 Validate repair-plan paths before the first write. — DONE (`1b5e0d1`).** Runs `RepairAPI._safe`
(`quality_repair.py:76-84`) over **every** op before applying **any**; names the offending path in a
single re-ask. All-or-nothing is intact.

*A note on how this was tested, because the first test was worthless.*
`test_a_plan_naming_a_forbidden_path...` passed with the fix reverted — pre-flight
refusal and post-hoc rollback produce **identical end states**, so an end-state
assertion cannot tell them apart. It needed a `snapshot_source` spy to assert the
workspace was never snapshotted, i.e. that no write was attempted. Mutation-test any
guard whose success looks like its failure.

**1.8 Industry derivation and an empty-industry guard.** *(Re-scoped by request 70.)* When
`industry` is absent, derive it from `business_description` rather than resolving silently to
`generic`. Add a blocking gate code `placeholder_content_shipped` using the existing
`early_brand_placeholder_strings()` / `early_brand_placeholder_item_titles()` (`seed.py:411-451`,
today consumed only by `product_face.py:90`). **Size the `_MIN_DISTINCTIVE_TOKEN_LEN` work from
0.1's answer, not from the original estimate.**

**1.9 Bound the item pool. — DONE (`ac10c9b`), verified on request 73.** The imagery service supplies
8 `item*` slots; the model writes N. Items now cycle within the pool, so items 9+ cannot wrap onto the
people-photo role images. Request 73's 12-item catalogue binds `item1…item8` only, `card1/2/3`
untouched by items.

**1.10 Stand up a JS test runner. — DONE; observed green on `main` by the owner, session 15 (run #11, 39/39).**
`preview-template/package.json` had `dev`/`build`/`typecheck` only — no vitest, jest,
testing-library, playwright, and no `.github/` anywhere in the repo. Two Phase 2 DoDs depend on a
runner that did not exist. **No test may leave pytest until that CI job is green on main** — that
condition is still unmet, because nothing is pushed.

What landed: `backend/preview-template-tests/` (vitest 4, jsdom, @testing-library/react, vite 8
pinned to the template's major so there is one vite in the tree) and
`.github/workflows/preview-template-tests.yml`, which runs `npm ci` → `typecheck` → `test` on every
push to `main` and every PR. No `paths:` filter: a filtered job reports *skipped*, not *green*, and
cannot serve as a required check.

**Why it is a sibling package rather than devDependencies in the template.** `shared_npm_root()`
keys the shared `node_modules` cache on a sha256 of the template's `package.json` **and**
`package-lock.json` (`npm_shared.py:29-44`). Any byte added to either — a `devDependencies` line
included — changes the fingerprint, so the next generation misses the cache and pays a full cold
`npm ci` *inside the run*, holding `_install_lock` through `contended_lock` while every concurrent
run waits it out. Trios 4 and 5 cleared the 600 s DoD with 9-17 s of margin; a cold install is
minutes. Second reason: `workspace.py:_SKIP_COPY` skips only `node_modules`/`dist`/`.git`, so test
files under `preview-template/src/` would ship inside every generated preview app and be typechecked
by `tsc -b`. The tests import across the directory boundary instead, via the same `@` → `src` alias
the template already defines.

**This generalises: treat `preview-template/package.json` as a file with a runtime cost.** Editing
it is legitimate, but it is never free, and the bill arrives on the next generation's clock rather
than at edit time. Warm the cache out of band before timing anything.

**The sibling arrangement has one cost, and it was nearly shipped as a broken CI job.** The unit
under test lives outside the test package, so *its* bare imports resolve from
`preview-template/node_modules` — never from the test package's. On a clean checkout that directory
does not exist and both `tsc -b` and vite fail with `Failed to resolve import "react"`; on a machine
that has ever built a preview it does exist, everything passes, and the defect is invisible. CI now
runs the template's own `npm ci` first. The same fact has a second edge: with both installs present,
React resolves twice — once for the test file, once for the template source — and two React copies
break hooks at runtime, so `resolve.dedupe: ['react', 'react-dom']` is set. Both were found by
running the job in a clean `node:22` container rather than trusting a local green.

The nine tests pin `SkeletonComposer`: what it throws on, that `shell` is the layout and not a
section, that an explicit recipe order **drops leftover optional slots** (the variety contract —
without it every business collapses into the same long marketing stack) while still restoring a
supplied required section, the `public-utility` content frame with its full-bleed footer, and the
ops rail split. `tools/mutate.py` reverts each of those behaviours in turn and asserts the suite
goes red: **9 mutations, 9 caught, 0 survivors**, source restored byte-identical. Re-run it after
touching the composer.

### Phase 1 DoD — with what is evidenced after four concurrent trios (74-85)

Twelve live runs, four trios of three started 60 s apart, each trio a
`reference_url` run, a `reference_file` run and a plain one, on three different
industries. Trio 1 (74/75/76) is **timing-invalid** — another session ran a
mutation sweep on the same host inside the window — but its *outcomes* stand.
Trio 2 (77/78/79) added the contention instrumentation. Trio 3 (80/81/82) tested
the screenshot lock-wait bound. Trio 4 (83/84/85) is the current code and the
only trio in which **every run finished under 600 s**.

| trio | wall clock | over the 540 s deadline | ≤ 600 s | pages given a visual verdict |
|---|---|---|---|---|
| 2 | 619.7 / 576.4 / 573.0 | 79.7 / 36.4 / 33.0 | 2 of 3 | 10 of 18 |
| 3 | 590.2 / 600.2 / 602.7 | 50.2 / 60.2 / 62.7 | 1 of 3 | 0 of 18 |
| **4** | **591 / 583 / 590** | **51.3 / 43.1 / 50.1** | **3 of 3** | 0 of 18 |

| | Status |
|---|---|
| Every generation ≤ 600 s request-accepted to ready-or-failed, **including** 3 runs started 60 s apart (`_SESSION_LOCK`, `_install_lock` serialize concurrent runs), one with a `reference_url`, one with a `reference_file` | **holds on trio 4, 3 of 3 — with 9-17 s of margin, on n=3.** It did not hold on trio 2 (619.7 s) or trio 3 (600.2 / 602.7 s). Call it met when a trio clears it twice; one clean trio is how the "met and real, on n=1" overstatement happened last time |
| p50 ≤ 500 s. No repair loop > 120 s. No ask > 120 s inclusive of failovers | **p50 still FAILED at 590 s** (want ≤ 500) — the elective guards bought ~10 s, not 90. **The ask-ceiling half of this row is unproven for `appspec`:** that stage had no `ai_call` scope, so all 49 of its rows carry `writer = NULL, attempt = 1`, and the logical-ask grouping (`request_id`, `stage`, `writer`, attempt not resetting) had nothing to group on. Scopes added in session 6; re-measure on the next funded trio. `appspec` is **147 s of AI per run** and its cost tracks **call count**, not per-call latency — 2-3 calls is 49-94 s, 5-7 calls is 253-294 s, no single call over 120 s, and only 0-27 s of the span is non-AI (`scripts/measure/appspec_cost.py`). **The ask ceiling was off by a constant and is now fixed.** Exactly four asks exceeded 120 s across all twelve runs and all four were 135.0 s to the millisecond (135012 / 135010 / 135007 / 135001 ms; 77, 80, 82, 85; `fix_agent`, `z-ai/glm-5.2`, attempt 1, no failover): `_CANCEL_GRACE_SECONDS` was spent *after* the cap fired. Held back inside it now, and the grace cut 15 s → 2 s. Ask p50 is healthy at 8.1 / 5.7 / 9.6 s, so this was the only ask-side breach |
| Zero consecutive asks to the same resolved model id | **was FALSE, now fixed.** `ac10c9b` deduped the *repair* chains and its test pins those; `call_architect`'s three-name chain was never deduped, and `ARCHITECT_MODEL` = `PREVIEW_APP_MODEL` = `TEXT_MODEL` = `google/gemini-2.5-flash` here **and in the test environment**, so the guard could not have caught it. 7 violations across trio 1; request 74's architect wrote 3 rows, one model, all unusable |
| Every degraded run carries a machine-readable `degraded: [stage]` marker | **was FALSE, now fixed.** Requests **73, 75 and 76 each degraded three stages and each stored `degraded: []`** — the marker was only ever a log line at scope exit. `finalize` runs inside `generate_preview_app`; `tech`/`proposal`/`build_plans` are skipped *after* it returns, so it structurally could not see them. Published from `GenerationPipeline.run` now, and verified live on 77/78/79 |
| `placeholder_content_shipped` fires zero times over 20 businesses; an empty `industry` never reaches `generic` silently | **inverted so far** — the gate exists and fires correctly; it caught 2 leaks on 73 and 2 on 68. The DoD wants **zero fires**, which means the *writers* still emit placeholders. **Session 11 ruled on the adjacent question and did not widen the gate:** the scaffold's *"A clear next step from {brand} — warm, specific, and ready when you are."* (7 of 64 workspaces) is a **filled** token, and this gate detects *unfilled* ones like `[Artist Name]`. Matching a sentence this repo writes itself would make this row measure whether we updated our own regex, so the scaffold was fixed instead (`8fe8955`). **The row's number is unchanged by that** — it was never counting these |
| 11 of 11 catalogue cards show the artifact type the business sells | **9 of 11 on request 70**; 73's binding is correct but its cards were not scored card-by-card |
| Suite green at ≥ 1,107 | **1,288 passed / 1 skipped / 1 failed** — the red is another session's in-flight refactor of `test_phase5_ui_alias_imports.py` (at `f9f41eb` that file has zero test functions), not Phase 1 work |
| Vitest CI job green on main | **runner and workflow exist; `main` has never run them.** 9 tests, 9/9 mutation-caught, `tsc -b` clean, and the whole job verified on a clean `node:22` linux container — which is what caught a resolution defect that a local green was hiding (the template's `node_modules` must exist for its source's bare imports; see 1.10). The row stays **unmet** until `.github/workflows/preview-template-tests.yml` is green on `main` — it cannot be closed from a branch |

**The honest summary:** the clock was **not** a guarantee — run it concurrently
and the 600 s cap broke on 3 of the first 9 runs, and two DoD rows marked *done*
were false in production and false in the test environment that was supposed to
pin them. After the elective guards, trio 4 cleared 600 s on 3 of 3 with 9-17 s
to spare. That is the first trio to do it and it is still n=3: the margin is
thinner than the run-to-run spread within a single trio (8 s here, 47 s in
trio 2), so a slower model day puts it back over. **Not "met" — "no longer
reproducibly broken."** p50 is 590 s against a 500 s target, and the 120 s ask
ceiling is still exceeded by design (`_CANCEL_GRACE_SECONDS`, below).

#### Where the 600 s went, on request 77

`RESERVE_SECONDS = 60` was sized from single-run measurements of the
post-deadline render-smoke and capture pass (41-42 s on requests 66 and 67).
That pass goes through `_SESSION_LOCK`. Under three concurrent runs the capture
sessions queue, so the reserve does work it was never measured doing:

| | blocked on `_SESSION_LOCK` | overran deadline by | verdict on its degradations |
|---|---|---|---|
| 77 | 16.9 s | 79.7 s | **CORRECT** — 62.8 s over even with the block removed. But the *cap breach* survives it too: 619.7 − 16.9 = 602.8 s |
| 78 | 35.9 s | 36.4 s | **ARTIFACT** — subtract the block and it lands within 0.5 s of its deadline. It degraded three stages it had the time for |
| 79 | 16.7 s | 33.0 s | **CORRECT** — 16.3 s over without the block, though contention doubled the overrun |

Every wait was on `screenshot_session`; `npm_install` was 0.0 s on all six runs
(warm cache). Trio 1 recorded **zero** contention — the runs never collided,
which is why one trio is not evidence about concurrency either way.

**This is the owner's hypothesis, confirmed but smaller than feared, and in a
place the plan did not look:** not in the 540 s budget, in the 60 s reserve
after it. A deadline whose reserve is unbounded is a 540 s deadline with a
600 s label.

#### The elective contract had one caller (trios 3 and 4)

Every one of the first nine runs finished 33-80 s past its deadline regardless
of what changed between trios, which reads as structural rather than as tuning.
Decomposed against `ai_usage_events`, the 382 s of tail across those nine runs
is **127 s of AI (33 %) and 255 s of non-AI (67 %)** — so `RESERVE_SECONDS = 60`,
which was fitted to the post-deadline render-smoke and capture pass, was fitted
to a minority of what actually runs after the deadline.

The cause: **`should_skip_elective` had exactly one caller in the whole tree** —
the orchestrator's `tech`/`proposal`/`build_plans` loop at `orchestrator.py:315`.
Five of the eight declared `ELECTIVE_STAGES` (`visual_critic`, `quality_repair`,
`refine`, `demo`, `reference_analysis`) were elective in name only: they ran
their expensive deterministic half past the deadline and only their *model calls*
degraded. Request 82 shows it cleanly, in a window where the other two runs had
already finished — the visual critique **starts 18 s past the deadline**,
screenshots its pages, then takes six consecutive `ask budget of 0s exhausted`
refusals. All of the browser cost, none of the verdicts.

Guards added at the two that dominate the measured tail (`build_phase.py:487`,
`quality_gate.py:862`), and `test_the_expensive_elective_stages_are_actually_skippable`
pins the contract for all five by AST rather than by grep — an earlier regex
version of that test falsely flagged the three document stages, which are
guarded through a loop variable and not a string literal.

**What it bought, measured, and the claim it does not support.** Trio 4's tail
averages 48.2 s against trio 3's 57.7 s: **~10 s a run.** The 255 s of non-AI
tail is real, but attributing the bulk of it to these two stages was wrong —
most of it is the post-gate smoke-and-capture pass the reserve was sized for.
What the guards did buy is the difference between 3 of 3 under 600 s and 1 of 3.

**It costs nothing in judged pages, and that was the thing to check** — the
reverted session-budget clip (1.11) failed on exactly this axis. Over six
observations the split is clean: every time the critic ran *past* the deadline
it reviewed **0 of 6** pages (80, 81, 82 — its vision calls were all refused);
every time it ran *before* it reviewed 4-6 of 6 (78 at t=497 s, 79 at t=450 s).
The guard only fires past the deadline, so it removes captures that were already
producing no verdicts and leaves the pre-deadline path untouched.

#### 1.3's ceiling was 135 s, not 120 s

Four asks over 120 s across twelve runs, and **all four the same number to the
millisecond**. A slow model does not produce that. `_run_with_heartbeat` armed
the cancel *at* `hard_deadline`, then joined the worker for a further
`_CANCEL_GRACE_SECONDS = 15.0`, so the recorded latency of any ask that hit its
cap was `cap + 15`. `latency_ms` is measured around the whole `call_with_retry`
in `openrouter_provider.py:231`, so the telemetry was right and the ceiling was
wrong.

Fixed by arming the cancel at `hard_deadline - grace` and cutting the grace to
2 s. The grace only runs once the call is already known to have failed: closing
the socket makes a blocked read raise almost at once, and where it does not
(stuck handshake, dead DNS) 15 s would not have rescued it either — it would
just cost 13 s more before raising the same `Timeout`. The grace is capped at
half the budget so a nearly-exhausted request still gets call time rather than a
budget made entirely of cancellation.

**Why no test caught it.** `test_a_worker_that_ignores_the_cancel_is_abandoned`
monkeypatches the grace to 0.1 s and then asserts `elapsed < 5` against a 0.2 s
deadline — 25× slack. A test that tolerates a 24× overshoot cannot see a 12.5 %
one. The replacement pins the arithmetic directly (120 → 118) so the production
number is checked without a test sitting through a 120 s budget.

#### Dead links were 76 % of everything the gate blocked on

Across trios 2-4, nine gate failures carried 49 blocking issues. **37 of them — 76 % — were dead
links**, and **5 of the 9 failures were dead links and nothing else**. That single class was the
largest reason a finished preview was withheld.

Measured, they are neither typos nor routes assembly dropped (`declared - rendered` is empty on all
of 78/81/82/84/85): the writers link to pages that were never planned. Of the 31 distinct dead hrefs,
**22 have no plausible target at all**, so retargeting could never have been the whole answer.

Repaired deterministically in `safety/dead_links.py`, inside `apply_workspace_guards` — before every
build attempt, so it costs no ask and no second `vite build`, and it still works past the deadline:
retarget to a served parent or dash-prefix (9), drop the `href` from a tag whose contract we own (3),
delete the whole entry when it is an object inside an array (12), ground to `/` and count it as a
last resort. Replayed over all nine stored workspaces: **31 → 0**. Trio 5 confirmed it live with
**zero dead-link gate failures**.

Two upstream defects it exposed, both fixed at source:

- `normalize_mock_navigation` judged nav entries against the *architect's declared* routes rather
  than the shipped router. `served_route_paths` exists precisely because those diverge — that is how
  78 and 81 shipped nav items for `/contact` and `/gallery` that no `<Route>` served.
- The template's own `MarketingHero.DEFAULT_PRIMARY_CTA` was `href: '/gallery'`, so every app the
  architect built without a gallery shipped a dead hero CTA on every page (78, 81, 84).

**The grading is graded because the first version was wrong in a way the gate could not see.**
Grounding every unresolvable href shipped request 88 with 33 of 81 internal links pointing at `/` — a
footer whose Activities, Contact and Privacy Policy entries all landed on the home page. That reads
as navigable and is not, which for a demo is worse than the dead link, and it is the same mistake as
the reverted screenshot clip in 1.11: the gate metric improved and the artifact got worse. **When a
fix moves a gate number, measure the artifact on its own axis.**

*Residual:* `AiFeaturePanel.tsx:44` hardcodes `/ai-features`. Template-owned, so the guard skips it
and the restore would revert an edit anyway; `AppLink` requires `href`, so there is no safe removal.
Dead in 1 of 9 runs and non-blocking there.

#### The failure mode the contract exists to prevent, still live

**Request 74 stored nothing at all** — no `preview_app`, no `roles`, an empty
`generated_pages`. At t=540.4 s `call_architect` started and raised 9 ms later
with *"Architect agent failed to produce valid JSON"*. No model was asked
anything: past the deadline every ask budget is zero. The orchestrator read
that message as transient, looked for the 180 s retry runway, found none, and
the `role_pages` fallback under `except Exception: pass` produced nothing
either.

`architect` is in `MANDATORY_STAGES`, whose contract is that such stages *"take
their deterministic path"*. **It has none** outside the AppSpec branch, and
74's AppSpec had already crashed on truncated output after 390 s of the 540 s
budget. The error now names the deadline (`require_model_time`), which fixes
the misattribution — **it does not make the run ship.** Two open questions for
the owner, both design decisions rather than defects:

1. Should `architect` get a deterministic route builder from `plan` (the
   machinery synthesises `roles` from plan already, but never `routes`)? Note
   that past the deadline `codegen` would be refused too, so the run would ship
   an architecture and no pages.
2. Should a mandatory stage be *bounded* rather than only refused — `appspec`
   spent 72 % of one request's budget and still failed.

**Update, 2026-08-05 (session 13): all four pieces are LANDED — `dc750a3` — mutation-proven and
production-UNPROVEN.** 19 tests, 23 mutations, 0 survivors. Half the mutations push each fallback
onto the *healthy* path rather than removing it, because that is how a widened `except` fails; the
healthy-run fixtures are what catch those. What a funded run still has to prove is **reachability**
— that a real outage lands in these branches — and that the degraded artifact is worth shipping.

Measured by `scripts/measure/deterministic_paths_census.py`
(no database, no network, no model — it drives the production functions):

| | |
|---|---|
| kinds whose empty-architect fallback ships routes | **6 of 6 distinct contracts** — 3 for a storefront, 3 booking, 5 workspace, 5 ops, 5 trading, 6 accounting |
| kinds whose fallback `_normalize_architect` accepts | **6 of 6** |
| kinds whose deterministic plan passes `_plan_meets_minimums` | **6 of 6** — the pipeline's own gate, not an opinion |
| stable under the second application `plan_phase` already performs | **6 of 6** |

**Correction, session 14 — "seven reachable kinds" was wrong, and the census had the classifier's
own defect.** The internal_ops context ("internal ops back office desk for warehouse staff")
resolved `storefront/storefront` — neither `"internal desk"` nor `"warehouse floor"` is a
substring of it, which is precisely the unreachability finding the 20-brief corpus filed — so the
original run drove **five** distinct contracts, measured storefront on three of its seven rows,
and never drove `internal_ops/ops` at all. The context now uses the measured hint pair, an
`EXPECTED` label→kind map turns any silent mislabel into a red summary line (proven red on the
old context), and all **six** distinct contracts pass every check. The per-kind numbers above
were right for the five contracts actually driven; `internal_ops/ops` (5 routes, the generic
workspace blueprint under the ops recipe) is measured for the first time.

**The census had the defect first, and it is worth recording.** Its first version compared the
architect before and after a second application *after* calling `_normalize_architect`, which
mutates the dict it is handed — so it reported every kind as unstable and was measuring its own
side effect. Take the comparison before the normalize call.

The four pieces as landed, against the spec as written:

1. **A shadow-mode architect fallback — done.** The enforced branch already rescued
   (`plan_phase.py:295-298`); shadow re-raised. `{}` is not a substantive route table, so
   `apply_product_kind_to_architect` injects the resolved kind's whole blueprint eleven lines
   later. **The spec said the builder "exists in all but name" and that is confirmed by driving
   it.** The enforced path is byte-identical and pinned by a test that fails if the shadow branch
   reaches it — including one asserting the enforced rescue records no degradation it did not
   record before. A booking brief is rescued with `/services` and `/book`, never a gallery.
2. **`synthesize_mock_data` degrades — done.** The catch sits *outside* the `ai_call` scope, which
   settles in a `finally`, so the usage row is written exactly as before. An **unusable answer**
   stays a rejection and is deliberately not recorded as an outage: the model was reached and the
   ask was adjudicated, and collapsing the two would make a provider failure and a bad answer
   indistinguishable in the record.
3. **A run that built a workspace stores a `preview_app` — done, and `finalize`'s contract was
   read first.** `status` keeps its three-value vocabulary (`ready`/`failed`/`rebuilding`) because
   four production readers and the frontend poller branch on it; a crashed run is `failed`, exactly
   as a gate failure is. `withheld_reason` keeps its meaning and gains the one case it could not
   express, `pipeline_crashed` — its three existing values all presuppose a run that reached
   `finalize`. Three refusals, each mutation-bound on its own: no workspace, an existing `ready`
   record (a chat rebuild that crashes must not mark the user's working site failed), and its own
   bookkeeping, which may never mask the exception it is describing.
4. **`build_experience_plan`'s deterministic path — done, and an honest minimal plan does exist.**
   The spec said this was unmeasured and to read the consumers first. The consumer is `plan_phase`,
   which applies `apply_product_kind_to_plan` itself: `_normalize_plan({})` supplies the design
   system and the seeds, the caller's resolved contract supplies the inventory, and the result
   satisfies `_plan_meets_minimums` for every kind. The validator and expander are skipped on that
   path — they are three more asks to the model that just failed twice. **With no contract the
   raise stands**, which is the explicit bound for `role_pages` and the chat rebuild; and an
   accepted AppSpec still outranks the blueprint, which is why the fallback sits *after* the
   canonical-seed rescue and has a test saying so.

1. **A shadow-mode architect fallback.** The enforced branch already rescues
   (`plan_phase.py:295-298`); shadow re-raises. The deterministic builder exists in all but name —
   `apply_product_kind_to_architect({}, kind_contract, plan)` over an empty route table injects the
   full blueprint (`_routes_are_substantive` is False there), and `_normalize_architect` runs on
   the result either way. Past the deadline codegen is refused too, so the shipped artifact is
   blueprint routes with deterministic scaffolds — which is the owner's stated designed outcome
   (*"a degraded preview that ships is the designed outcome"*), against runs that today ship NULL.
   The enforced-mode path must stay byte-identical; pin it.
2. **`synthesize_mock_data` degrades instead of raising.** `write_plumbing_mock` has already
   written a complete `mock.ts` by the time it runs — 101 and 102 both have one; the palette was
   production-proven *from* it. A provider failure there should record a degradation and keep the
   plumbing mock, not kill the run.
3. **A run that built a workspace stores a `preview_app`.** 101 and 102 built workspaces and stored
   nothing, so the record of what happened lives only in a docker volume one prune from gone —
   that is how "read the volume before concluding a run proved nothing" became a trap in the first
   place. Store the record with a status naming the degradation instead of storing nothing.
4. **`build_experience_plan`'s own deterministic path.** Unmeasured — read what consumes its plan
   and derive the minimal shape those consumers accept before inventing one. If no honest minimal
   plan exists, an explicit bound (fail fast, degrade, record) still beats a raise that ships NULL.

### Phase 1 risk, stated plainly

**1.1 and 1.3 deliberately ship worse previews on bad runs** — a degraded preview instead of a
1,675 s run that ships nothing. Two of three observed runs already ship nothing, so this is a strict
throughput improvement and a temporary ceiling regression. Phase 2 recovers the ceiling.

---

## Phase 2 — One spec; Python emits data, not TSX (8–10 weeks, 2 engineers)

Budgeted at 8–10 rather than 5–7 because **0.7 measured 388 tests on TSX-source machinery**.
Schedule pressure on test surgery is how a 40-defect regression ledger gets deleted as "obsolete".

> **Decide which spec before 2.0 writes a line — an owner decision, filed 2026-08-05 (session 12)
> and not yet taken.** The pipeline already authors, validates, repairs and persists an **AppSpec**
> (68.8 s/run) and then, in shadow, plans as if it did not exist; the architect dict is a second
> de-facto spec. 2.0 as written mints a **third**. The options:
>
> - **(a) `SiteSpec` is a projection of the *accepted AppSpec* plus the design axes.** This makes
>   AppSpec acceptance the critical path for the whole phase — measured at **2 of 4** on the one
>   brief with four samples, with the dominant rejection being `pages[].state_ids` empty against
>   `min_length=1` (118 of 1,356 stored pages carry none). A deterministic authoring-side backfill
>   is a **repair-path option, not the schema relaxation the owner has reserved** — but it changes
>   acceptance semantics, so it needs a ruling either way.
> - **(b) `SiteSpec` is independent and the AppSpec leaves the preview path** — stop spending
>   68.8 s/run authoring a document nothing downstream reads.
>
> What is not viable is shipping both and a third. The enforcement replay bears on the choice:
> an enforced AppSpec halves the route table and closes DoD 7's denominator by itself, which is
> the largest single prize on the board — and it is only reachable under (a).

**2.0 Derive the schema, freeze it in two parts (1 week).** Run `load_ui_type_declarations`
(`ui_catalogue.py:295-317`) over `src/ui`, cross with `catalogue.json`'s 265 props and 30 slot ids,
emit the pydantic schema from the intersection.
*Freeze now:* `SiteSpec.brand / routes / nav / content / images / aiFeatures`.
*Leave open, versioned, additive-only:* `SiteSpec.design` — the axes that make a designer say
"different site" are discovered in 3.3/3.6, weeks 8–12.

Two hard rules, both from verified failure modes:
- **Python-facing route keys stay snake_case.** `skeleton_id` has 272 refs across 32 files. The
  sharpest edge: `has_catalogue_routes` (`protected_paths.py:9-14`) returns False when no route
  carries `skeleton_id`, and `is_template_owned_path` opens with it — **a camelCase key silently
  disables all template-ownership protection**. Also make `has_catalogue_routes` fail closed.
- **Emit `src/data/site.ts` with `satisfies SiteSpec`, and keep a per-request `tsc --noEmit` as a
  hard gate.** `run_build` (`build.py:21`) runs vite only; esbuild strips types without checking, so
  a `satisfies` violation ships. tsc is 1.8 s — under 0.5 % of budget. **Drop the repair round, keep
  the measurement.**

**2.1–2.3 Move the renderer into the template (4–5 weeks).** `scaffold.py` (1,713) +
`utility_compositor.py` (839) become a React renderer under `src/render/`. This is what collapses
per-template cost from 240–460 h toward 60–110 h.

**Two non-negotiable constraints**, all three failure modes verified in the tree:
1. **Every route keeps a real file** — `GalleryPage.tsx = () => <SpecPage routeId="gallery" />`.
   167 references key on it. The version of this warning that said `_smoke_routes` "dedupes on
   `component_file`, so 12 routes sharing one file makes the render smoke check probe **one** page
   and log success" was correct and is now half-fixed: it dedupes on **URL** (`3fc04ca`), so twelve
   routes on one file are twelve probes. The other half stands and is the sharper one —
   `catalogue_route_for_file` still returns the *first* route for a file, so under a shared file
   eleven of those twelve routes have no reachable contract. Measured today at 11 of 42 runs with
   only two routes sharing; a renderer that puts twelve on one file makes it universal.
2. **The terminal stub stays Python-emitted**, importing only `react` and `react-router-dom`. If the
   fallback and the failing writer share an implementation, one renderer bug crashes all 12 pages and
   the repair re-crashes them.

**2.4–2.5 Flip the writers (1 week).** Slot-fill (`generate.py:269-489`) and the freeform path
(`:491-684`) collapse into **content asks batched by surface — 3, not 12**. This is the only lever
that removes double-digit call count. Parallelise the codegen retry loop (`codegen_phase.py:122` is
a serial `for`, triggered by exactly the failure mode that dominates on a bad provider day).

**Measured since (duos 1-2, 2026-08-04/05), and it strengthens this item: the case is now the
discard rate as much as the call count.** `slot_fill` paid for and threw away **83-148 s per run**
— 28 of 40 calls rejected on duo 1, 25 of 42 on duo 2, every duo-2 rejection `finish_reason: stop`,
i.e. the TSX violating its own skeleton contract. A writer that emits data against a schema makes
that rejection class unrepresentable, and the retry/scaffold machinery it feeds goes with it.

**2.6 Delete, in dependency order (3 days) — gated on 0.3 and 0.4.**

**The hard gate:** `visual_critic.py:1288` raises `visual_defect_severe` at BLOCK, and **the only
path that clears it** is the AI repair touching the file → verdict retired → gate passes. A
deterministic re-render produces identical pixels, so `_remeasure_repaired_pages` → `_regate_after_
remeasure` re-blocks with the same score: **a guaranteed livelock into shipping nothing**. So either
land a spec-level actor first (visual finding → design-axis reselect or content-key edit), **or
demote `visual_defect_severe` to WARN in the same commit that deletes the repair**, and say so in
the release notes.

**What stays:** `evaluate_quality_gate` and `heal_quality_gate` — **every issue code**, because the
codes are the regression ledger for 40+ shipped defects.

**2.7 Retarget the validators (3 weeks, parallel track).** Every validator reads page *source text*;
under a renderer they see a three-line wrapper and go quiet — this codebase's recurring fail-open
mode. **Before any of it lands: write one positive test per gate code** and add a collection-time
assertion that every code in a `report.fail(` call is named by a test. Measured today: **11 of 18
fail codes are never named anywhere under `tests/`**.

Notable retargets: `journey.py`'s `LISTING_COMPONENTS` tag-match → section-component query; the dead-
link sweep → **every href in the spec vs every path in the spec, both data** (the class becomes
unrepresentable); `quality_gate.py:101-218`'s 19 component-name greps; and
`_route_table_is_stale` (`:391-415`), whose `re.findall(r'<Route\s+path="…"')` **returns `False` on
zero matches** — a data-driven router makes that three-commit-old guard silently no-op.

**Ownership, in the same commit that creates the files:** extend `is_template_owned_path` to
`src/render/**` and add `src/data/site.ts` as generator-owned **by full canonical path**. Blast
radius inverts after the flip: one bad write takes down 12 pages.

**2.8 Imagery (1 week).** Persist the candidate pool — `_fetch_pexels_images`
(`industry_images.py:479-537`) returns a flat `dict[slot, url]` and discards spares, so a rejection
has nowhere to go. Then per-slot-policy verification: object slots must depict the artifact named by
`content.items[i].title`; scene slots must depict the *industry*. One contact-sheet vision call,
folded into the existing wave. **Hero subject policy keyed on `product_kind`** — request 70 got this
right by accident (home hero a painting, `/artist` hero the artist at her easel); make it deliberate.

### Phase 2 DoD

1. Data-bound content props ≥ 95 % **and** `placeholder_content_shipped` fires zero times over 20
   businesses. *(The first alone is satisfied by mad-libs.)*
2. Inline prose in page TSX ≤ 200 chars (wrappers only). **Baseline re-taken 2026-08-03, and the
   original 13,540 is per *workspace*, not per page TSX** — the row was comparing a per-page target
   to a whole-app figure, which reads as a 68× reduction when the median page needs about 2.6×.
   Measured per page over 753 page files in 58 workspaces (`scripts/measure/content_census.py`):
   **mean 859, median 529, p90 2,090, max 6,534**, and **12 % of pages are already under 200**. Per
   workspace: mean 11,149 over all 58, **13,095 over the 27 most recent** — the corpus size the
   original claim names, which is how the unit was identified. The definition's one judgment call is
   `className` exclusion, and the script prints its own sensitivity: 1,629 chars of 646,646, 0.25 %.
3. Zero dead internal links by the spec-level cross-check.
4. The typecheck record exists, its `source_fingerprint` matches shipped source, `error_count = 0`,
   on 5 consecutive runs. **The record exists and this row is FAILING, not unmeasured** — corrected
   2026-08-04. Duo 1 stored `typecheck_status: "errors"` with `type_errors` of **4** (request 95) and
   **8** (request 96). The handoff's *"there is no record at all"* came from reading a key named
   `typecheck`; the writer's key is `typecheck_status` (`finalize._typecheck_summary`). Note the
   row's own caveat still stands separately: request 83 shipped `ready` with 10 type errors and 78
   failed with zero, so this number does not decide the ship rate.
5. `SiteSpec` key-set identical across 5 runs of 5 industries. **Baseline re-taken and it
   reproduces exactly.** There is no `SiteSpec` yet, so the measurement is `src/data/mock.ts`, and
   the "1 key" is `seed`'s: **1 key — `credentials` — is common to all 47 archived workspaces that
   have a `seed`**, out of **75 distinct keys**, 9 to 26 per workspace, with only 10 keys present in
   90 % of runs. At the module's own export level, 2 of 22 keys (`brand`, `images`) are common to
   all 58. The other 11 workspaces predate `seed` and export bespoke names —
   `featuredPaintings`, `recentPaintings`, `publicCta` — which is the same finding one layer up.
6. p50 ≤ 420 s; p95 ≤ 540 s, **derived by convolution over the 0.6 census, not asserted**.
7. `len(_smoke_routes(architect))` equals the count of non-wildcard routes with a page file;
   `catalogue_route_for_file` is injective. **Measured, both halves open** (`3fc04ca`): the count
   identity fails on **26 of 42** archived runs leaving **74 of 553** routes never smoke-loaded (all
   of it the deliberate 12-route cap, now published as `render_pages_skipped` rather than hidden
   inside `render_pages_checked`), and the lookup is non-injective on **11 of 42** — two routes
   naming one page file, where the second route's contract is unreachable by any of the six callers
   that resolve a file to a route. Closing the second half is 2.1-2.3's `<SpecPage routeId="…" />`,
   one route per file by construction. Baseline table in the Day 2 section above.
8. **No module outside a named allowlist may write `src/pages/**.tsx` or `src/render/**`** —
   enforced at runtime inside `workspace.write_file`, allowlist pinned by test. **DONE** (`3b2e72a`,
   pulled forward under the no-generation window). Baseline: **26 modules can write pages today**;
   this row's value from here is watching that number fall as 2.4-2.5 lands.
9. **Total collected test count never drops below 1,107**, asserted in CI. **Floor done, CI half
   open** (`7f8f91f`) — there is no pytest job in CI yet.

### The nav guarantees — how they are actually protected

Do **not** pin `[data-public-header]`, `#inquire`, `data-footer-variant` etc. by source grep. That is
the class of guard `90f4d5f` just spent a commit removing — `test_the_scroll_reset_ships_one_
behaviour_from_two_files` documents in its own comment that pinning the alias map "let the two drift
anyway… for two rounds with this test green."

**Two layers, and only one of them can live in vitest.** jsdom has no layout engine — every
`getBoundingClientRect()` is zeros — so a pixel guarantee cannot be asserted there at all. What
vitest holds (`preview-template-tests/src/scroll-reset.test.tsx`, `30ed9b9`) is the logic beneath
the pixels: which element a hash resolves to, that the header is measured from the DOM rather than
from `--public-header-h` (request 67's defect exactly), the `+24` of air, `scrollY` added because a
rect is viewport-relative, `Math.max(0, …)`, the six contact aliases, the 50 ms retry for an
unmounted target and its cleanup. It tests the *template's* copy; the shipped app runs the inlined
copy in `app_tsx.j2`, and the only thing connecting them is
`test_the_scroll_reset_ships_one_behaviour_from_two_files`, which compares the two effect bodies
normalized. **That test is load-bearing for the vitest ones.**

The pixels stay here. `tests/preview_app/test_nav_contract.py` is a **rendered-DOM assertion**
through the existing Playwright path, asserting the numbers request 70 verified:
- `scrollHeight` delta between scroll-0 and scroll-past-24px is **0** on every route;
- a cold load of `/<detail>/1#inquire` lands the target's `top` in **[16, 48]** (measured: 25 px);
- hero content clears the measured header on every public route;
- `SkeletonComposer` still **throws** on a null required slot, and a spec with a null required
  section stubs **one** route, not twelve.

Source greps survive as a cheap pre-filter, never as the contract.

---

## Phase 3 — Variety: authored designs with within-recipe axes (10–12 weeks, from week 4)

**The strategic call.** Axes over one silhouette is one system wearing hats — five of six heroes are
a `min-h-[100svh]` full-bleed photo plane and all 11 bands hardcode `max-w-[92rem]` and
`px-6 py-28 lg:px-12 lg:py-36`. But eight authored recipes each hardcoding their own clamps is how we
got here. **Deepen the 6 public-reachable recipes into complete designs that each own a type ramp,
spacing scale, container width, grid logic, image treatment and page composition — expressed as
tokens, with axes as *within-recipe* choices from a declared valid set, never a free cross-product.**

**3.0a Brand voice — the kit speaks in one business's voice on every site.** A sweep of
`src/ui/**` found 92 hardcoded strings; most are legitimate chrome. These carry *business voice*
and are a sameness defect, not a leak (none is in `_BANNED_COPY`):

*Unoverridable literal JSX — no prop exists, so no caller can change them. Each needs a prop first,
exactly as `CTABand`'s eyebrow did:* `MarketingHero.tsx:269` "Scroll to taste" (restaurant);
`ProcessSection.tsx:43,79` "The path", "You arrive" (hotel/spa); `InquiryPanel.tsx:119,200`
"Enquiries", "We never share your details."; `AiFeatureDeck.tsx:71` "Previewed on this hub";
`BookingPanel.tsx:135,206,210` "Choose treatment", "Treatment", "Duration" (clinic);
`ScheduleRail.tsx:104,134,143,145` "Level", "Availability", "Waitlist" (fitness);
`ConfirmStage.tsx:85` "What you can do next".

*Overridable defaults carrying business voice:* `BrandFooter.tsx:67` — agency marketing copy in
every footer, the worst of these; `CatalogGrid.tsx:67,69,70` "/gallery", "The collection", "pieces"
as the default catalogue; `CashPulseBar.tsx:27,28` a fabricated "$48,220"; and three CTA defaults.

**3.0 The design corpus, signed (1 designer-week, runs during Phase 1).** This is where the
100-template impulse is captured. Deliverable is not a list of names but a **signed spec sheet per
archetype**: grid logic, type ramp (six named steps with actual clamp values), spacing scale,
container width, image treatment, and the catalogue archetype it pairs with. Cut to what a named
designer will actually sign: **4–6 heroes, 3 type ramps, 3 densities, 3 catalogue archetypes, 2 page
compositions.** For scale: `MarketingHero.tsx` is 568 lines for six variants.

**3.1 Break the enum (1 week).** The six `Record<RecipeId,…>` maps become defaults; the rendered
value comes from `SiteSpec.design`. Honour the props the kit discards
(`MarketingHero.tsx:90-91`, `FeatureBento.tsx:54-55`). Implement `'split'` — declared at
`registry.ts:148,496,618`, no branch, silently falls through to cinematic.

**3.2 Recipe/pack compatibility (3 days).** Do **not** decouple pack order from recipe —
`design_recipes.py:653-668` fails closed on purpose (*"pottery → agency stack"*). Instead each pack
gains **`compatible_recipes: [ids]`**. Also, `pick_recipe_id`'s fallback rotates over eight recipes,
three of which `plan_phase.py:129-132` then nulls for public kinds — rotate over the *reachable* set.

**3.3 + 3.6 Tokens and composition, together (4 weeks).** Run as one workstream so composition is not
the thing cut when the schedule slips — it is the one that changes the silhouette. Add
`--text-display/-hero/-h1/-h2/-body/-meta`, `--space-section/-block/-gutter`, `--container-max`,
`--grid-rhythm`. Refactor the 11 public bands off hardcoded values. Retire the three `[data-recipe]`
padding hacks. Wire `density` — computed today and reaching nothing on the public surface.
**`--container-max` must differ meaningfully per recipe**; at least two recipes default to a
two-column or offset body, not the flat stack. **Gate every commit on the rendered-DOM nav-contract
test** — hero clearance and anchor offset are spacing-dependent.

**3.4 Band layouts — CatalogGrid first (4 weeks).** `CatalogGrid.tsx:145` is one grid for every
business; it is also the page the owner screenshotted. Three archetypes differing in **grid logic,
not spacing**: (a) varied-ratio wall with a lead item spanning two columns — portfolio, gallery;
(b) editorial list, full-width row per item — services, property; (c) dense spec grid, 4–6 columns —
retail, inventory. **Image aspect policy is part of the archetype.** Then features → cta → showcase →
testimonials → process → credentials.

**3.5 Collapse the three systems fighting over ten variables (3 days).** `design_overlay`'s six font
pairs are unreachable (`brand_locked` always true), its ten token overrides wipe the recipe's
identity, and two recipes hard-code their palette back in CSS. One resolution, in Python, into
`SiteSpec.design`. Delete the losing layers.

**3.7 Two distinctness gates (1 week).**
1. **Mechanical — silhouette, not enum identity.** Per page, the ordered list of *(section component,
   rendered column count, container-width bucket, media aspect ratio, section-height bucket)*. Over
   20 synthetic businesses: **no two home pages and no two catalogue pages may share a silhouette.**
   A recolour cannot pass it. *(The naive version — a tuple over five enums — is satisfied with
   certainty by 20 permutations, the same failure as `len(set(faces.values())) >= 4`, which the
   current collapse already passes.)*
2. **Human — a standing contact sheet** of 20 home pages and 20 catalogue pages side by side. **Run
   it once now, on HEAD, to establish the baseline.** Blocking at three milestones only: 3.0 sign-off,
   3.4 exit, 3.7 exit.

**Prerequisite, named 2026-08-05 (session 12): the 20-business synthetic brief set does not
exist.** Every corpus number in this document rides on **17 distinct briefs, 12 business names, and
25 of 62 workspaces being one art gallery** — a denominator that cannot certify variety. Building
the set is free offline work: 20 briefs across the kinds' real spread, including the
never-requested `internal_ops` / trading shapes (which would make the five dead skeletons reachable
for the first time), committed under `docs/evidence/` so funded runs stop re-running the same three
briefs. It gates 3.7's silhouette measurement, and until a generation can run, its offline value is
the classification spread — `resolve_product_kind_contract` over all 20, checked against the kinds
each brief intends.

### Phase 3 DoD

- Silhouette gate passes on home **and** catalogue over 20 businesses (today ~5 / ~1).
- Designer sign-off at the three milestones: "these read as different sites."
- Each `SiteSpec.design` axis independently settable within its recipe's valid set, with a test
  flipping one axis and asserting a DOM or computed-style change.
- Zero regressions in the rendered-DOM nav-contract test.
- No page uses a hardcoded `clamp()`, `py-28`, or `max-w-[92rem]`.

---

## Phase 4 — Residual AI path, then kit #2 (3 weeks)

**4.1 What is actually movable.** Two tempting optimisations are false and are withdrawn: blueprint
and AppSpec cannot run concurrently (`capture_derived_context` feeds `ensure_approved_app_spec` — a
data dependency), and imagery cannot be prefetched with the blueprint (the direction is reversed;
`get_images_for_industry` reads the AI-authored plan). **What is real:** run `build_design_manifest`
concurrently with the imagery block (~9 s), and make recipe resolution pure Python after 3.1/3.5
(~4 s). Total after P4: **~402 s**.

**4.2 Kit #2 — gated on Phase 3's DoD.** Building a second kit before the axes exist just produces a
second re-skin. Budget **40–80 h**. Measure the actual hours and set N from that; recommendation,
to be revised by that measurement: **cap at 3**.

Constraints that hold at any N > 1: one dependency set and one lockfile
(`_template_lock_fingerprint` hashes both); **add eviction to `_shared_npm` before N > 1** — there is
none; per-fingerprint lock plus a cross-process guard (`_install_lock` is intra-process only); and
the three hardcoded `PREVIEW_TEMPLATE_DIR/node_modules` resolutions mean each template dir carries
its own 194 MB install.

---

## Sequencing

```
Week  0   1   2   3   4   5   6   7   8   9  10  11  12  13  14  15  16
      ├P0─┤
          ├─── P1 (600 s lands here) ───┤
          ├ 3.0 designer corpus ┤ (signed)
                  ├2.0┤
                      ├──── 2.1-2.3 renderer port ────────┤├2.4-2.5┤├2.6┤
                      ├──── 2.7 validator retarget ───────────┤
                      ├─ test surgery (388) ──────────────────────┤
                              ├3.1┤├3.2┤├─── 3.3 + 3.6 ───┤├──── 3.4 ────┤├3.5┤├3.7┤
                                                                              ├4.1┤├4.2┤
```

**Hard dependencies:** P0 before everything. P1 before P2 — it meets the constraint and keeps a
shippable product alive during a 10-week refactor. 2.0 gates the renderer port and the validator
retarget; it does **not** gate Phase 3, and Phase 3 does not gate it. 2.6 gates on 0.3 + 0.4.
4.2 gates on Phase 3's DoD.

**Staffing for the full plan:** 2 senior engineers on pipeline, 1 on validators and test surgery,
1 designer-engineer on the kit, 1 designer at 20 %. **4.5 people, ~16 weeks.**

### If you are not staffing 4.5 people

Phase 2 is **not on the critical path for either stated goal**. It buys reliability (today 2 of 3
runs ship nothing) and makes kits cheap later. A small team should run:

- **Weeks 1–3: Phase 0 (trimmed) + Phase 1.** Delivers the 600 s cap and, with 1.8/1.9, the content
  and imagery floor. Both stated goals, substantially met.
- **Weeks 4–16: Phase 3**, with a designer. This is the long pole and it needs design input, not
  engineering throughput.
- **Phase 2 when the failure rate justifies it.** Deferring is legitimate; the cost is that every new
  variant is a prop the model can still get wrong.

Keep every new variant **inside the kit, selected by Python from the recipe** — never a new thing
the AI must author. That is what makes deferring Phase 2 safe.

**Annotation, 2026-08-05 (session 12): this section is the operating reality, not the fallback.**
The project is one owner plus agent sessions at ~$0.42 a generation, and by this section's own
clock it is in week ~5 of "weeks 1-3" — Phase 1 is still open on 1.10 (blocked on a push), 1.11,
1.12 and the p50 ruling. The 4.5-people/16-weeks plan above prices a team that does not exist;
treat it as the full-staffing variant. One gap in this lane is a decision rather than work:
**weeks 4-16 assume a designer, and 3.0's deliverable is literally "what a named designer will
actually sign."** No such person is attached. Surfacing that hire — or explicitly deciding the
owner plays the role — belongs on the owner's queue beside the p50 ruling.

---

## Do not do this

1. **Do not build 100 templates.** 3.3–6.1 engineer-years as re-skins, 13–26 as real templates,
   23.5 GB of unreclaimable `_shared_npm`, 100 forks of a 1,713-line fallback — and it does not fix
   the complaint.
2. **Do not ship a shared `<SpecPage/>` without per-route wrapper files.** Render-smoke coverage
   silently drops 12 → 1 while logging success.
3. **Do not let the deterministic fallback share an implementation with the renderer.**
4. **Do not delete the gate's AI repair before 0.3/0.4 answer**, or without demoting
   `visual_defect_severe` to WARN in the same commit. Otherwise a severe visual finding is an
   unbreakable livelock and shipping goes from 1-in-3 to 0.
5. **Do not optimise the build.** Under 2 % of a run. `build_phase.py:183`'s "~20 s" comment is 40×
   stale.
6. **Do not add general pool workers.** Whole-run AI concurrency is 1.01–1.06×; the dominant stages
   issue one call at a time. The one legitimate widening is the vision fan-out, which is
   network-bound.
7. **Do not add another guard on AI-authored TSX.** ~6,800 lines / 23 % of `preview_app` already is
   that, and `HANDOFF.md:196` already concluded they "do not fix the cause."
8. **Do not weaken the all-or-nothing repair rule.** Validate paths before the first write.
9. **Do not give the visual critic the screenshot.** It keeps a TSX writer in the loop with unbounded
   latency. Route findings to the composer.
10. **Do not delete gate issue codes when deleting the repair.** They are the regression ledger.
11. **Do not pin nav guarantees by source grep.** Every one of `90f4d5f`'s five fixes would pass one.
12. **Do not decouple pack `section_order` from recipe compatibility.** `f7df0cf` fixed that on
    purpose.
13. **Do not edit the template's `package.json`** until eviction and a warm-cache startup hook exist —
    any change mints a new 235 MB fingerprint and a cold `npm ci` under the global lock.
14. **Do not delete `test_request_40_defects.py` tests as obsolete.** Rewrite each at the new layer,
    keeping docstring and request number.
15. **Do not treat "≥ 95 % data-bound" as a variety metric.** Mad-libs score 100 % on it.
16. **Do not trust a guard that reports success. — Worked example, now fixed.** "NEXT MOVE" shipped
    as visible CTA copy on every generated site while `preview-qa.sh` reported clean *and*
    `strip_template_jargon_copy` logged "template jargon replaced" on every run. Three layers were
    each wrong in a different way. The source says `Next move`; a CSS `uppercase` class renders it
    as `NEXT MOVE`, and the harness grepped the **rendered** casing case-sensitively. The ban table
    (`safety/copy_hygiene.py:137-139`) *did* match it case-insensitively and *did* rewrite the file
    — and then `restore_template_owned_files` (`orchestrator.py:257`, eight lines later) put it back,
    because `is_template_owned_path` claims all of `src/ui/**`. And when this was audited, the
    auditing agent grepped the uppercase literal too, concluded the string did not exist, and nearly
    closed it as unreproducible.
    Fixed in the kit rather than by weakening `src/ui/**` ownership, which is load-bearing
    (`protected_paths.py:132-142`). `test_the_kit_never_ships_copy_the_pipeline_has_banned` is the
    standing invariant. Casing is now split deliberately: folded for rendered copy, exact for
    `PLACEHOLDER` (11 false hits on `placeholder=`) and bracket classes (4 false hits on
    `[location.pathname]` dep arrays).

---

## Summary

| | Today | P1 (wk 3) | P2 (wk 13) | P3 (wk 16) | P4 |
|---|---|---|---|---|---|
| Wall clock (run-67 shape) | 688 s | ~495 s | ~411 s | — | ~402 s |
| **Hard cap** | none | **600 s, by construction** | 600 s | 600 s | 600 s |
| p95 | 1,675 s | ≤ 600 s | ≤ 540 s (derived) | — | ≤ 500 s |
| Runs that ship | 1 of 3 | 3 of 3 (some degraded) | 5 of 5 clean | — | — |
| Shipped tsc errors | 1–16 | — | **0**, fingerprint-verified | — | — |
| Dead internal links | 0–8 | — | **0** | — | — |
| Cards showing the right artifact | 0–9 of 11 | **11 of 11** | — | — | — |
| Distinct silhouettes / 20 | ~5 | — | — | **20** | — |
| Templates | 1 | 1 | 1 | 1 | **3 (not 100)** |

**Correction, 2026-08-05 (session 12) — read two rows against what is now measured.** *Wall clock
at P1*: measured p50 is 563-590 s, not ~495 — see the ledger note above. *Runs that ship at P1*:
the measured swing is **0 of 3 (trio 7, all 18 AppSpec revisions rejected) → 2 of 2 and 2 of 2
(duos 1-2)**, and the variable is **AppSpec acceptance, not the deadline** — an accepted spec is a
cheap appspec stage and a run that ships; a rejected one starves everything after it. "3 of 3 (some
degraded)" additionally assumes a degraded path that **does not exist for three MANDATORY stages**
(1.12, five fires: 74, 92, 94, 101, 102). The ruling of 2026-08-05 is to build those deterministic
paths — see the 1.12 update in Phase 1; until they land, this row's promise is conditional on
provider health.

**The bet, in one paragraph.** Four TSX writers are the wrong architecture and Phase 2 removes them —
but with the renderer moved into the template behind per-route wrapper files, and the validators
retargeted from source text to spec *before* the source they read disappears. That refactor does not
deliver 600 s: **the constraint is met in week 3 by a request-scoped deadline and an explicit
degradation contract**, and the flip buys the margin that keeps the deadline from binding. Template
count was never the variety lever — the kit renders five silhouettes from a type system permitting
7.46 × 10⁸. Fix the content floor and the clock in week 3, the silhouettes over weeks 6–16, and buy
three kits instead of a hundred.
