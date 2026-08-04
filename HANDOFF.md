# Session handoff — the first funded trio, a bound that did not fire, and a duo (2026-08-04, session 9)

Successor to session 7's handoff (in git history at `01facbe`). Still-binding parts are restated
below; do not go back for them. Process notes, not product docs.

- **The plan and its evidence: [docs/PREVIEW_ROADMAP.md](docs/PREVIEW_ROADMAP.md).** Read **The
  no-generation window**, then **Status**, then **Phase 1 DoD**.
- **Before spending a trio: [docs/FIRST_FUNDED_TRIO_PREFLIGHT.md](docs/FIRST_FUNDED_TRIO_PREFLIGHT.md).**
- Why the pipeline shipped bad output: [docs/PREVIEW_QUALITY_FINDINGS.md](docs/PREVIEW_QUALITY_FINDINGS.md).

**If you read one thing: [The next step](#the-next-step).** It is an ordered list, not a theme.

---

## State of the repo, in four lines

- **`main` is PUSHED and level with `origin/main`** as of 2026-08-04 — the first push in several
  sessions. A vitest CI run on `main` should now exist; nobody here can read it.
- **Suite: 1,690 passed / 1 skipped / 0 xfailed / 0 failed. Vitest: 32 passed.** Run pytest the
  documented way — see the operating notes. Collection floor ratcheted to 1,669.
- **Credits: ~$22 left of $330, and a generation costs $0.34.** Runs are not the constraint and never
  were — see *Credits* below, where the numbers overturn a premise four sessions rationed against.
  Still run the pre-flight's 28,000-`max_tokens` probe before a batch: it costs $0.00014 and it is
  the only check that catches the per-request 402 that voided trio 6.
- **CI is still unreadable from here.** `gh` is not installed and
  [github.com/Roy-r2004/BMV/actions](https://github.com/Roy-r2004/BMV/actions) 404s unauthenticated.
  **1.10 is not done until that vitest job is green on `main`.** `main` is now pushed, so a run
  should exist. Someone with a browser has to look once.

---

## Session 9 — the trio's write-up finished, and what auditing it turned up

Session 8 ran trio 7 and was stopped before committing the analysis. Everything below the credits
section was already drafted; this session verified it rather than inheriting it, and three things
came out of the audit that were not in the draft.

| | |
|---|---|
| **`api7.log` had never been archived** | Two published claims — no credit refusal in the window, and the gate instrument's first live output — rested on a log living only inside a running container. 914 lines, now in `preview-trio-logs.tar.gz`. **The container was restarted 24 s before the trio launched, so it survived; one more restart and both claims were unverifiable.** |
| **Q10 was silently missing** | `tail.py` hardcodes `RUNS = [74…82]` and skips runs with no stored elapsed, so it had nothing to say about 92-94 and said so silently. Run by hand: 93's tail is **32.0 s of which 0.1 s is AI**, 3 pages judged. Parameterize it. |
| **The credits premise was wrong** | See the section below. A trio is **$1**, not the scarce resource four sessions rationed against. |

**What re-derived and what did not.** Wall clocks, the two empty records, both suite numbers and the
`[public-service]` gate line all reproduce exactly. Nothing in the draft was found false.

### 1.13 — the appspec bound, and the mechanism the trio write-up got wrong

Owner ruled **(B)**: add a Phase 1 item rather than move the p50 row to Phase 2, with (A) as the
documented fallback if the bound lands and p50 still misses.

Working out *what* to bound overturned the draft's conclusion. It said *"the fix is a repair-loop
bound."* The mechanism is that **`APPSPEC_MAX_CALLS = 6` was enforced per entry into the stage and
the stage is entered twice per generation**, so 92/93/94 made 7, 6 and 10 calls and never logged a
budget-exhausted line. The confirming entry is meant to be a cache hit; it re-authored from scratch
on every run because **all 18 revisions in the trio are `rejected`** and there was nothing to reuse.
Request 92 authored from scratch three times. That duplicate pass is **~50-59 %** of appspec's AI
time, and it explains the bimodality `appspec_cost.py` measured and could not account for.

**Landed:** the tally moved onto `RequestDeadline` (the object already scoped to one generation and
already crossing threads with it), plus a runway reservation — appspec may not start a call leaving
the pipeline under **280 s**. Sized to the corpus, not guessed: the five runs that reached `ready`
left 284.6-504.9 s, and 92 and 94 left 91 s and 136 s. **14 mutations, 0 survivors.**

**Two traps I nearly walked into, both the "case that does not bind" blind spot:**

1. **"Just don't re-author on the second entry"** would have killed request 87, whose accepted spec
   came from a fresh re-author on entry two. *Then* I checked whether 87 shipped — **it did not**, it
   failed at the gate anyway. A rescue that changes no outcome is not a reason to keep a cost, but I
   was one query away from protecting it on reputation.
2. **A per-request budget of 6** — the configured number — would have refused the 7th call that
   produced 87's only accepted contract. The number had to move to 8 *because* the semantics changed.
   Changing where a ceiling is enforced changes what the number means; carrying the old value over
   would have been a silent tightening.

**And the check that actually mattered — which I did, and it was still not enough.** All 14
mutations were caught on the first sweep, which is not this repo's norm, so I checked the fix was
not inert: `orchestrator.py:66` opens the deadline scope around `_run_inner` and the appspec call at
`:134` is inside it, same thread. The guard *can* fire. **Duo 1 then showed it does not fire on a
healthy run** — 2 and 5 calls against a ceiling of 8, and appspec nowhere near the reservation's
elapsed. "Reachable" and "reached" are different claims and I proved only the first. **A bound
written against the worst run in the corpus is silent on every run that is not that bad**, which is
correct behaviour and also means the trio that motivated it is the only evidence it was needed.

### Duo 1 (95-96) — the fix did not fire, and the runs improved anyway

Two runs on the briefs of 92 and 94 verbatim, all five pre-flight checks verified first. **Both
shipped `ready` with zero gate issues**, against 0 of 3 for the trio. appspec AI went 336.5 → 43.2 s
and 331.6 → 94.3 s.

**And 1.13 gets no credit for it.** No `stopped_low_downstream_runway`, no `call_budget_exhausted`:
calls were 2 and 5 against a ceiling of 8, and appspec never reached the elapsed at which the
reservation engages. **The code I shipped did not execute its new paths on either run.** What moved
is acceptance — 95's spec was accepted on its first authoring call, 96's never accepted — which is
the accepted-is-cheap / rejected-is-double mechanism the analysis already predicted.

Two consequences I would rather have found before publishing:

1. **Trio 7's 0-of-18 acceptance was probably an unlucky sample, not a regression**, and the same
   goes for *"1.12 reproduced twice in one trio"*. I wrote that row as if it were systematic. Duo 1
   re-ran those exact briefs and both shipped. Corrected in place.
2. **p50 is not appspec's to fix.** 571 s and 573 s, and codegen is **315 s / 24 calls** and
   **436.9 s / 33 calls** of AI against appspec's 43 and 94. The (B) experiment answered its
   question: the answer is (A), for a reason neither of us predicted.

**What else the duo showed, none of it the filed task:** DoD 7's instrument is live and the cap
binds — 95 is 12 checked / 13 eligible / **1 skipped**, 96 is 12 / 19 / **7 skipped**, so 8 declared
routes were never smoke-loaded and the record now says so. `typecheck` is **`None`** on both runs,
which is a DoD row that wants a record with `error_count = 0` on 5 consecutive runs and currently
has no record at all. And `viewable` is `None` on both despite `status: ready` — unexplained, and
the same shape as the `visual_review_status` defect session 7 fixed one measurement over.

**Still open, and it is the root cause of the cost:** acceptance. 96 failed on
`trace_evidence_mismatch`; trio 7's three runs failed on three different things. 1.13's second half.

## The next step

**Duo 1 answered the (B) experiment and the answer is (A), for a reason nobody predicted: `codegen`,
not `appspec`, is what decides p50.** 315 s and 437 s of AI against appspec's 43 s and 94 s. Both
runs shipped `ready`, and **1.13's bounds never fired**, so the improvement is acceptance variance
and the fix remains unproven in production.

**The one decision only the owner can make** is whether the p50 row moves to Phase 2 under (A). The
evidence is in; the ruling is not. **Everything below is workable without it.**

1. **`codegen` is the p50 term. Decompose it before touching it.** 24 and 33 calls a run, 315 s and
   437 s of AI, dwarfing every other stage. Nobody has ever broken it down by writer the way
   `appspec_cost.py` broke down appspec — and the `ai_call` scopes to do it already exist. Build the
   census first and land nothing until it says which writer spends the calls. **The appspec lesson,
   learned twice now: the obvious loop was not the expensive one.**
2. **1.13's second half — acceptance.** Trio 7 failed on three different causes and 96 on a fourth
   (`trace_evidence_mismatch`), so there is no single defect. `analyse.py`'s `appspec_health` now
   reports `final_blocking` per run; **collect it over the next several runs before choosing a fix**,
   because n=4 across four causes is not a distribution. Do not relax the schema to make specs
   acceptable — that makes them pass without making them better, which is
   `placeholder_content_shipped`'s lesson one layer up.
3. **Land the allow-list-once-per-run bound.** Waiting on nothing since trio 7 (Q6: request 93's real
   9-route list collapses to `{"truncated":true,…}`). The consumer is the **fix agent**, not the
   architect. Land it with a run ready to measure repair quality.
4. **`typecheck` is `None` on both duo runs.** A DoD row wants the record to exist with
   `error_count = 0` on 5 consecutive runs; there is no record at all. Find out whether the stage is
   skipped, failing silently, or never publishing — this is the fifth entry in the running list of
   *the instrument was the defect*, if it turns out to be one.
5. **`viewable` is `None` on both duo runs despite `status: ready`.** Unexplained. Same shape as the
   `visual_review_status` defect from session 7. Cheap to chase, and it gates whether a shipped
   preview is actually shown.
6. **The render cap binds and 8 routes went unchecked.** 95 is 12 checked / 13 eligible / 1 skipped,
   96 is 12 / 19 / 7. DoD 7 predicted this and the instrument now proves it live. The fix is the
   denominator (2.1-2.3, one route per file), not a bigger cap — but the number is worth watching.
7. **The redundant menu and the universal gallery — owner-reported, confirmed in duo 1.**
   `navigation` publishes the same links under several role keys (95: `public` ≡ `customer`; 96:
   `admin` ≡ `features`), there are two exports aliasing one array, and a **twelve-table trattoria
   shipped `GalleryPage.tsx`, `ArtworkDetailPage.tsx` and a hero CTA reading "Explore the
   collection"**. **Both fixes must be general** — anything keyed on an industry string is the
   `generic`-industry defect wearing a new hat. **Screenshot the header before fixing the duplicate
   half**: the template's selector reads one key, caps at 5 and dedupes, so the on-screen cause is
   not yet established. Full write-up in the roadmap.
8. **Q8 and Q11 still need a trio**, and only those two do. Q8 is the dead-link confirming run; Q11
   needs runs that actually collide, and **contention appeared on only 4 of 16 runs ever**, so a trio
   is necessary and not sufficient. Batch them with item 3 so the trio earns its three runs.
9. **Someone with a browser still has to look at CI once.** `main` is pushed as of 2026-08-04, so a
   vitest run on `main` should now exist to look at.

### Credits — a premise this document and the pre-flight both had wrong

**A trio costs about one dollar, and something else is spending the account.** Measured from
`ai_usage_events`, which reconciles exactly with `google/gemini-2.5-flash` list price:

| trio | calls | cost | per run |
|---|---|---|---|
| 1 (74-76) | 116 | $1.27 | $0.42 |
| 2 (77-79) | 169 | $1.26 | $0.42 |
| 3 (80-82) | 160 | $0.94 | $0.31 |
| 4 (83-85) | 114 | $1.15 | $0.38 |
| 5 (86-88) | 135 | $1.22 | $0.41 |
| 6 (89-91) **void** | 96 | $1.03 | $0.34 |
| 7 (92-94) | 100 | $1.01 | $0.34 |

**Every trio ever run totals $7.88. The whole project has recorded $26.89 across 2,707 calls since
2026-07-27.** The account has used **$307.29 of $330** — so the pipeline is **9 %** of its own
account's spend, and the per-generation cost is **~$0.34**, not the "real money" both this file and
the pre-flight have been rationing against.

**The gap is live, not historical.** `GET /api/v1/key` reports `usage_daily: $17.62` for
2026-08-04, a day on which this pipeline made **zero** AI calls — no `ai_usage_events` rows after
2026-08-03 17:41, nothing in the api container log for the day, no generation in flight. That key's
lifetime usage equals the account's entire usage, so one key is doing all of it.

**Consequences for how this document has been read:**

- **Trio 6 was not voided by trio cost.** It was voided by an exhausted balance that trios
  contributed $7.88 to. No amount of pre-flight discipline would have prevented it, and check 1
  cannot prevent the next one either — it confirms a balance it does not control.
- **"Is a trio affordable" has been the wrong question.** At $1 a trio, generations are not the
  constraint on this project and never were. Do not defer a measurement to save a dollar.
- **Escalate the key before the next top-up**, or the top-up funds whatever spent $17.62 today. The
  candidates, in the order worth checking: a deployed instance sharing the key
  (`docker-compose.coolify.yml` implies one), another tool pointed at it, or a leaked key. **The
  owner has been told and it is the owner's call — no session should rotate it unilaterally.**

---

## What landed in session 8

Five commits. The no-generation window's remaining Day 2 work, all of it offline, all mutation-swept.

| commit | what |
|---|---|
| `3fc04ca` | **DoD 7** — route bijection measured; `_smoke_routes` dropped a served URL |
| `fa41e0a` | **DoD 2 / DoD 5** — the "before" numbers, one of which was in the wrong unit |
| `c09b96d` | **gate `skeleton_id`** — pre-flight question 5's instrument, plus a dead `analyse.py` key |
| `30ed9b9` | **vitest** — scroll reset and anchor landing, 17 → 32 tests |
| this one | handoff + roadmap |

### The findings worth carrying, none of which was the filed task

1. **`analyse.py` has been reporting `gate_issues: 0` for every trio it ever summarised.** It reads
   `preview_app["gate_issues"]` and **nothing has ever written that key** — confirmed against the
   database, zero rows. Every per-code gate count in the roadmap was grepped out of container logs
   instead, which is *why* pre-flight question 5 was unanswerable: a log line has no `skeleton_id`
   in it. `finalize` writes `gate_issues` and `gate_warnings` now, each with the failing page's
   skeleton. This is the fifth entry in the running list of *the instrument was the defect*.
2. **DoD 2's `13,540` is per workspace and the DoD row compares it to a per-page target.** Measured
   per page TSX: mean 859, median 529, max 6,534 — nothing in 753 files approaches 13,540. Per
   workspace over the 27 most recent runs: 13,095. The figure was right and the unit was wrong, so
   the row read as a 68× reduction when the median page needs about 2.6×. **12 % of pages already
   meet the 200-char target**, which is not what a 68× gap sounds like.
3. **`_smoke_routes` deduped on `component_file`, so a URL the router serves was never loaded.**
   Request 22 declared `ArtworkDetailPage.tsx` at both `/artwork` and `/gallery/:id`; only the first
   was ever render-checked, and the un-parameterized alias is the one that renders with nothing to
   resolve. 12 URLs across 11 of 42 runs. Fixed by deduping on URL with aliases sorted behind every
   first sighting, so the 12-route cap cannot displace an unchecked page.
4. **DoD 5's claim reproduces exactly** — 1 key (`credentials`) common to all 47 archived workspaces
   that have a `seed`, out of 75 distinct keys. When a published number *does* re-derive, say so;
   two of the four checked this window did not.

### Mutation results — 48 mutations, and the six that survived were a different failure than last time

`14 + 11 + 9 + 14 (vitest)`, zero survivors at the end. **Six survived a first sweep**, same count as
session 7 and almost the opposite cause. Session 7's were tests that could not fail. Session 8's
were mostly **guards that could not fail** — four conditions I wrote that cannot change an outcome:

| dead condition | why it can never fire |
|---|---|
| `" " not in text` | the two-word rule below it already implies a space |
| `any(t[:1].isupper())` | the lowercase-only charset check already rejects those tokens |
| `if not path` | `catalogue_route_for_file` can never match an empty path |
| `if self.architect is None` | that function already does `(architect or {})` |

All four were deleted rather than tested around. **If you catch yourself adding a defensive
short-circuit in front of a call, check whether the call already handles it** — that is now the
single most common thing my sweeps find in my own code.

The other two survivors were real: a detector defect (requiring *one* hyphenated token to call a
string Tailwind misread `self-catering apartments available` as a class list and silently dropped
it from the DoD 2 count — it needs half the tokens now), and a fixture too short to reach the rule
it was meant to pin (`"5 %"` is three characters and never got past the length guard).

### A third way `docker compose exec` lies about the suite

`mutate_route_bijection.py` runs `docker run`, not `docker compose exec`, and unlike the older
drivers it has to: the compose `api` service mounts only `backend/`, and on that driver's suite set
that is **2 failed / 134 passed** against **136 passed** on the same commit under `docker run`. The
two casualties are `test_request_40_defects.py`'s kit-reading tests. The baseline reads red before a
single mutation is applied. Prefer `docker run` in every new driver.

---

## Binding owner constraints — these do not expire

- **Fix the PIPELINE, never a generated preview.** Editing anything under `data/preview-apps/**` to
  make a defect go away is always wrong. *Reading* those workspaces for evidence is fine and is how
  most findings get made.
- **Generation must not exceed 10 minutes.** Do **not** relax the deadline to make runs pass. A
  degraded preview that ships is the designed outcome; two of three audited runs used to ship nothing.
- **If you find a defect, fix it in the pipeline and add a test that fails with the fix reverted.**
- **Work the roadmap in order.** Phase 0 → 1 → 2 → 3 → 4. Session 5 proposed reordering and the owner
  pushed back: *"why not work in order by the preview roadmap?"*. **Phase 1 is not finished.** 2.9 was
  a documented one-off exception (`475265e`), authorised by the window; the Phase 2 *DoDs* (7, 8, 9,
  2, 5) were the roadmap's own Day 2 plan — building a scoreboard is not starting the phase. **Both
  lists are now exhausted. There is no remaining licence to pull Phase 2 work forward.**

### The rule that has caught the most defects

**Mutation-test every guard.** A guard whose success looks like its failure is this repo's recurring
defect. Revert the fix, confirm the test goes red, restore — from an **in-memory backup**, never
`git checkout` (it ate a session's uncommitted work once already). Five drivers to copy live in
`backend/scripts/cli/mutate_*.py` and one in `preview-template-tests/tools/mutate.py`.

Four blind spots, all four found the expensive way. Check for each by default:

1. **Asserting against the case that does not bind.** Every contract test used `public-home`, the one
   skeleton under budget, so reverting the fix changed nothing it could see.
2. **Driving the consumer, never the producer** — or the reverse. A test that builds its own copy of
   the record and asserts on that is green with the publication deleted. One of mine did exactly that
   this session and I only caught it by asking which function the test actually calls.
3. **Guards that cannot fail** — the four in the table above.
4. **Fixtures too small to reach the rule.** Size the fixture to the boundary: the cap only binds
   above 12 routes, so a three-route app proves nothing about it.

Assume any DoD row you did not personally mutate is unproven. Three that session 4 marked "done" were
false in production **and** in the test meant to pin them.

---

## Operating notes — every one has cost real time

| | |
|---|---|
| **The test command** | **`docker run`, not `docker compose exec`.** See below. Three independent ways it lies, all three looking like application defects |
| **`industry` is `Form(None)`** | Omitting it silently resolves to `generic` and produces convincing garbage. **Always set it** |
| Host port | **8001**. Multipart, not JSON |
| Trailing slash | `POST /api/requests/` 307-redirects and **drops the body**. No trailing slash |
| `reviewing` | **Transient, not terminal.** Watch `is_generating` |
| Reload code | `docker compose restart api`. `exec api` does **not** reload — the bind mount updates the files, the running interpreter keeps the old modules. **Restart before any trio that is meant to measure today's code** |
| Industries | A **different** one per run in a trio. Three art galleries only prove the art-gallery path |
| pytest | **Read the SUMMARY LINE, never the exit code.** Piping to `tail` inside an `&&` chain has masked red suites twice |
| Working directory | **Drifts between tool calls. Use absolute paths.** Fourth session running |
| Checking credits | `GET /api/v1/credits` is free and gives granted-minus-used. It is **not** sufficient: the failure that voided trio 6 is a *per-request affordability* 402 on `max_tokens`. Send one real 28,000-`max_tokens` call per model — it bills only the tokens actually produced ($0.00014 for both) |
| **`preview-template/package.json` has a runtime cost** | It is the shared-npm cache key — `shared_npm_root()` sha256s it with `package-lock.json` (`npm_shared.py:29-44`). **One added byte invalidates the cache and the next generation pays a cold `npm ci` inside the run**, holding `_install_lock` while concurrent runs wait. Verify warmth before timing: `shared_npm_root()` then `_vite_ready(root/"node_modules")` |
| Archive what you measure | A number derived from the database or the docker volume is unverifiable next session. `docs/evidence/architect-routes.json` exists because DoD 7's numbers came out of `requests.generated_pages` |

### The test command, and the three traps in the convenient alternative

```bash
docker run --rm -v "/Users/maurice/Documents/Dev/BMV:/repo" -w /repo/backend \
  -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api \
  -c 'pip install -q pytest; python -m pytest tests/ -q'
```

`docker compose exec api` is faster to type and wrong three independent ways, **and all three look
like application defects**:

1. **`sh -lc` drops node.** A login shell re-reads `/etc/profile`, resets PATH, loses
   `/opt/node/bin`. `tsx_parse_error` shells out to node and **fails open**, so six unrelated tests
   go red with messages pointing at application logic.
2. **The `api` service mounts only `backend/`.** Four tests read repo-root files —
   `scripts/preview-qa.sh`, `Dockerfile.app`, `docker-compose.coolify.yml` — and get
   `FileNotFoundError`, which reads as "the QA harness lost its script".
3. **Same mount, different casualty:** `test_request_40_defects.py`'s two kit-reading tests fail.
   Measured this session: 2 failed / 134 passed under compose, 136 passed under `docker run`.

Measured earlier on one commit: `sh -lc` → 10 failed / 1,509 passed. `sh -c` → 4 failed / 1,518
passed. `docker run` → **0 failed / 1,531 passed.**

**Do not run a pytest container or a mutation sweep while a timed trio is in flight.** It
contaminates the measurement, and trio 1 is timing-invalid for exactly that reason.

### Running the offline census tools

Both DoD scripts need the archived corpus extracted and the repo's own `app` package, not the
image's baked copy:

```bash
mkdir -p /tmp/ws && tar -xzf docs/evidence/preview-workspaces.tar.gz -C /tmp/ws
docker run --rm -v "$REPO:/repo" -v /tmp/ws:/ws:ro -w /repo/backend \
  -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api \
  -c 'python3 /repo/backend/scripts/measure/route_bijection.py --workspaces /ws'
```

`route_bijection.py` prefers the *repo* over `/app/backend` on `sys.path`, deliberately and unlike
the other tools in that directory — the baked image copy silently shadowed the function under test
on the first attempt and the import failed with a name that exists in the checkout.

---

## What is still broken

Ordered by what I would do first. Every item has evidence; none is speculative.

### 1. p50 is 569-590 s against a ≤ 500 s DoD, and the lever is call *count*

`appspec` spans **264.5 s and 288.8 s** on requests 83 and 84 — roughly half the budget before
anything is built. **Bounding `appspec` is not in Phase 1's item list.**

**Owner decision still pending:** move the p50 row to Phase 2, or add a Phase 1 item for `appspec`.
Do not quietly re-fit the number.

`scripts/measure/appspec_cost.py` over trios 2-5 (12 runs) decomposed it: **147.0 s of AI per run**,
2 to 7 calls, 49-94 s at 2-3 calls and 253-294 s at 5-7, no single call over 120 s, 0.0-27.3 s of
non-AI in the span, 13 % of AI time recorded `usable=false`. Not a per-call latency problem and not
an orchestration problem — the total is set by **how many** calls. Each extra call ≈ 50-75 s.
*Which* loop spends them is instrumented (`56d8f08`) and answerable only from a funded trio.

### 2. 1.12 — a MANDATORY stage with no deterministic path

Request 74 stored **nothing**: no `preview_app`, no `roles`, empty `generated_pages`. At t=540.4 s
`call_architect` raised 9 ms later. `architect` is MANDATORY, whose contract is that such stages take
their deterministic path — **it has none** outside the AppSpec branch, and 74's AppSpec had already
burned 390 s and failed.

**Recommendation, reversing session 5's:** do *not* build a deterministic architect. Past the
deadline codegen is refused too, so it would ship an architecture with wholly generic pages —
precisely the artifact 2.9 exists to avoid. Bound `appspec` instead. **Owner has not ruled.**

### 3. The **fix agent's** route context collapses — confirmed live, deliberately unfixed

`_catalogue_routes_context` (`codegen/architect.py:139`) serializes one **full** skeleton contract per
catalogue route into a 10,000-char `bounded_json`. Offline: 1 route = 5,004 chars, 2 routes =
list-clipped to 12 components each, **3 routes = collapsed to `{"truncated": true, "preview": …}`**.
Confirmed on request 93's real 9-route list.

**Everyone who has written this up, including me, said "the architect" and it is wrong.** The
function lives in `architect.py` and never prompts the architect — it takes the *completed* architect
dict, and its only callers are `fix_agent` (`:482`, `:530`) and `chat_rebuild` (`:245`). The
truncated preview goes to the **repair path**, the consumer that most needs each page's contract. On
93 the fix agent ran twice for 147.8 s of AI against a route block it could not read.

The fix is "state the allow-list once per run rather than once per route", which also recovers most
of the ~18k tokens/run. **It changes what the model sees.** Trio 7 supplied the confirmation it was
waiting for; it did not supply a before/after on repair quality, so land it with a trio ready to
measure that.

### 4. DoD 7's second half — one page file, two routes, one reachable contract

New this session and **not fixed**: `catalogue_route_for_file` is a file→route lookup over a relation
that is not one-to-one in **11 of 42** archived runs. The loser's `skeleton_id`, `section_slots` and
`app_spec_page_id` are unreachable by all six callers that resolve a file to a route. Closing it is
2.1-2.3's job — one route per file by construction. Enforcing it today would raise in production on
a quarter of runs, which is the mistake DoD 8's static cross-check avoided.

### 5. Ship rate is still 1 of 3

Remaining blocking gate codes across trios 2-5, after the dead-link fix: `visual_defect_severe` 5,
`listing_not_schedule_rail` 4, `placeholder_content_shipped` 2, `confirm_not_stage` 1. Genuine
judgment calls, not link plumbing. `placeholder_content_shipped` firing at all **inverts a DoD row**
that wants zero fires — the gate works; the *writers* still emit placeholders.

What does **not** decide it: typecheck. Request 83 shipped `ready` with 10 type errors; 78 failed
with zero. Do not chase `tsc` counts expecting the ship rate to move.

### 6. 1.11 — the reserve is unbounded as a whole

`RESERVE_SECONDS = 60` was fitted to the render-smoke and capture pass. Over nine runs the 382 s of
tail is **127 s AI (33 %) and 255 s non-AI (67 %)**. The elective guards took ~10 s a run off it.

The screenshot **session-budget clip** was implemented, measured and **reverted** — 2-of-3 over 600 s
and **0 of 18 pages visually reviewed**. The measurement is a comment in `screenshot.py` so nobody
re-adds it. The lock-**wait** bound was kept. If you attack this again, the axis that killed attempt
one is *pages actually given a visual verdict*, not wall clock. **Measure both, separately.**

### 7. 1.10 — green on `main` is unverified, and cannot be verified from this machine

Runner and CI job are done and merged; **`main` has never been observed running them**. `gh` is not
installed and the Actions page 404s unauthenticated. Until someone looks, pytest remains the only
suite anything may depend on.

The job **has** been run end-to-end in a clean `node:22` container, which is what caught a defect
local green was hiding: the unit under test lives outside the test package, so its bare imports
resolve from `preview-template/node_modules`, which does not exist on a fresh checkout. The same fact
has a second edge — once that directory *does* exist React resolves twice and hooks break, so
`resolve.dedupe` is set. **Verify a CI job on the CI platform, not on the machine that wrote it.**

It is a **sibling package on purpose**, because `preview-template/package.json` is the shared-npm
cache key. Do not "tidy" it into the template.

### 8. Appspec telemetry is verified against fakes only

Scopes added in `builder.py` (`authoring`, real attempt numbers; `repair`), `coverage.py`
(`coverage_review`), `schema_repair.py` (`schema_repair`), pinned by
`tests/appspec/test_appspec_call_telemetry.py`, 5 mutations / 5 caught. Consequence: the DoD row **"no
ask > 120 s inclusive of failovers"** groups logical asks by `(request_id, stage, writer)`, and for
appspec that grouping had nothing to group on — **the row was evaluated on data that structurally
could not show an appspec failover.** Unproven for this stage until a funded trio re-measures.

---

## Things I got wrong in session 8, so you don't repeat them

- **I wrote four guard conditions that could not change an outcome**, in two unrelated files, and
  only the mutation sweeps found them. Both times the pattern was a defensive short-circuit in front
  of a call that already handled the case. It is now the first thing I would check in my own diff.
- **I wrote a persistence test that built its own copy of the record and asserted on that.** Green
  with the publication deleted. Fixed by extracting `gate_issue_summary` so the test calls the
  function `finalize` calls — the fix is always "name the seam", never "assert harder".
- **I added a field to `GateReport` and seven tests went red on `AttributeError`**, because two fakes
  were `SimpleNamespace` objects shaped like the real report and missing `warnings`. A fake that is
  not the real type is a test that stops tracking the thing it tests. They construct `GateReport()`
  now — which also revealed that those tests *do* drive finalize end-to-end, so the consumer half had
  better coverage than I had assumed.
- **My mutation anchors drifted twice on indentation** (8 spaces where the source has 6). The driver
  caught it and refused to apply — that refusal is the most valuable line in those scripts and it is
  worth keeping in any new one.
- **I sed-renamed the trio launcher's log file from `launch5.log`** when trio 6's copy already used
  `launch6.log`, so trio 7 wrote to `launch6.log`. Harmless, but check what you are copying.

## Things I got wrong in session 7, still worth not repeating

- **Six tests that could not fail**, found only by mutation sweeps: asserting against the skeleton
  that does not bind, and driving the consumer instead of the producer.
- **A `cd backend` drifted between tool calls** and a heredoc died on a relative path.
- **I nearly enforced DoD 8 on the runtime census alone.** It would have raised in production for
  eleven modules writing computed paths the suite's fixtures never exercise with a page.
- **I started a mutation sweep and then kept editing.** The sweep mutates live-mounted source; a
  concurrent edit makes its verdict noise.
- Session 6's list still stands in `dfbfdd6`, and session 5's in `08a9abf`. The important one from
  5: **a dead-link repair that improved the gate metric and made the artifact worse.** When a fix
  moves a gate number, measure the artifact separately.
