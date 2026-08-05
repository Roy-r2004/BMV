# Session handoff — three mandatory stages can now ship degraded, and a guest house is a trading desk (2026-08-05, session 13)

Successor to session 12's handoff (in git history at `c8f839f`). Still-binding parts are restated
below; do not go back for them. Process notes, not product docs.

---

## Session 13, in one page

**Zero generations run, and not by choice — the account is still empty.** Three commits, 27 new
pytest cases across two files, **34 new mutations, 68 applied across three sweeps, 0 survivors at
the end, 3 survived a first sweep.** Suite **1,867 passed / 1 skipped / 0 failed**, vitest **39**,
`tsc -b` clean.

### Read this first: credits, and CI

`https://openrouter.ai/api/v1/credits` returns `total_credits 330, total_usage 330.229` —
**unchanged from session 12**. Probed first, before anything was restarted or warmed, which is item
0 of the previous list and cost nothing this time. **Everything below is mutation-proven and
production-UNPROVEN.**

**`main` is pushed** — `122ef79..80a3d71`, sixteen commits, on the owner's authorisation. Five
sessions are no longer on one disk. **CI is still unobserved and 1.10 stays open**: the repository
returns 404 unauthenticated on `api.github.com` *and* on the HTML page, so it is private, and `gh`
is not installed. `.github/workflows/preview-template-tests.yml` triggers `on: push: branches:
[main]`, so a run was certainly queued — but "a run was queued" is not "the job is green", and the
row does not close on it. **1.10's blocker has changed from "never pushed" to "needs a browser or a
token."**

### What landed

| commit | what |
|---|---|
| `dc750a3` | **1.12** — three MANDATORY stages take a deterministic path instead of shipping NULL |
| `980ca63` | the 20-brief synthetic corpus, and what the classifier does with it |
| `bd58502` | the detail page reads the param the route declared, and the twin alias goes |
| this one | handoff + roadmap |

### 1. 1.12 — the session's thesis, and all four pieces are in

Five runs shipped nothing on this class: 74, 92, 94 (`architect` raising after an expensive
`appspec`) and 101, 102 (a provider outage across `build_experience_plan`, then
`synthesize_mock_data` raising the same way). `MANDATORY_STAGES`' contract is that such a stage
*takes its deterministic path*; outside the AppSpec branch there was none, so **the designed
outcome — a degraded preview that ships — was unreachable and the pipeline shipped NULL.**

- **(a) the architect.** `plan_phase` rescued only under `enforce_app_spec`, never true in shadow.
  `{}` is not a substantive route table, so `apply_product_kind_to_architect` injects the resolved
  kind's whole blueprint eleven lines later. **The enforced path is byte-identical**, pinned by a
  test that fails if the shadow branch reaches it — including one asserting the enforced rescue
  records no degradation it did not record before.
- **(b) `synthesize_mock_data`.** Degrades to the plumbing `mock.ts` the plan phase already wrote.
  The catch sits **outside** the `ai_call` scope, which settles in a `finally`, so the usage row is
  written exactly as before. An **unusable answer stays a rejection** and is deliberately not
  recorded as an outage — the model was reached and the ask was adjudicated.
- **(c) a run that built a workspace stores a `preview_app`.** `finalize`'s contract was read
  first. `status` keeps its three-value vocabulary because four production readers and the frontend
  poller branch on it; `withheld_reason` keeps its meaning and gains `pipeline_crashed`, the one
  case it could not express. Three refusals, each mutation-bound alone: no workspace, an existing
  `ready` record, and its own bookkeeping — which may never mask the exception it describes.
- **(d) `build_experience_plan`.** The spec said this was unmeasured. **An honest minimal plan does
  exist**: `_normalize_plan({})` plus the caller's resolved contract satisfies
  `_plan_meets_minimums` — the pipeline's own gate — for every kind. The validator and expander are
  skipped there; they are three more asks to the model that just failed twice. With no contract the
  raise stands, and an accepted AppSpec still outranks the blueprint.

Measured over all **seven** reachable kinds by `scripts/measure/deterministic_paths_census.py`:
every kind ships 3-6 routes, `_normalize_architect` accepts all seven, every deterministic plan
meets minimums, and both are stable under the second application `plan_phase` already performs.

19 tests, 23 mutations, 0 survivors.

### 2. The 20-brief corpus — and the classifier decides a kind on bare substrings

The archived corpus is 84 rows but **18 distinct briefs, 15 of them `storefront`**, so five
skeletons were unreachable by construction. `docs/evidence/synthetic-briefs.json` is 20 briefs with
distinct names across every kind, labelled with the kind they intend **before** the classifier was
read. **15 of 20 land it. 5 distinct contracts are reached, against 3 in the whole archived
corpus.** The five misses are findings, not tuning targets, and are not fixed:

| | |
|---|---|
| **a nine-bedroom guest house resolves `internal_ops/trading`** | and would be built `/ticket`, `/blotter`, `/positions`, `/risk`. The hint `"oms"` matches inside **"Rooms"** — in the **business name**. Renaming it "The Wilder House" flips it to `storefront` |
| the same substring does both jobs | it clears `internal >= 1` *and* satisfies the strong-signal test at `product_kind.py:258`, so one accident of English decides a product kind. Same class as session 12's bare `"detail"` |
| `"spa"` inside "work**spa**ce" and "di**spa**tch" | harmless to those two verdicts; same defect |
| **`internal_ops` is close to unreachable in plain English** | a warehouse desk, a facilities desk and a dispatch console, each saying it is staff-only, all resolve `saas_workspace`: the kind needs two hint phrases or one of `blotter/oms/hedge/trading desk`, and otherwise falls to the ambiguous branch on "queue". Measured — `"internal desk"` + `"warehouse floor"` together *do* reach `internal_ops/ops`; either alone does not |
| **a driving school matches zero hints in any table** | and takes the final `return "storefront"` default — an art-gallery blueprint for a business selling lesson packages |

**Two corrections to my own corpus before publishing its numbers**: the non-trading `internal_ops`
subtype is `ops`, not `generic`; and SB-07's intended kind was authored `booking_service` and
corrected to `storefront`, because the product's own tables put hospitality there and whether a
guest house is a booking service is a **product question**, not a defect.

### 3. Route alias inflation — and it was never only bundle weight

`assemble.py` minted `base/:id` **and** `base/:slug` for every listing because the scaffolded detail
page read `params.id ?? params.slug`. The router's shape was decided by one line of generated TSX.

Request 69 shipped **three** routes to one page — `/gallery/:paintingId`, `/gallery/:id`,
`/gallery/:slug`. All three match `/gallery/x`, React Router binds one, and the page read
`params.id` — so **the detail page resolved no item** and rendered the generic "This piece" against
a default image for every id. Request 82 shipped the same shape for `/rooms/:roomId`. **16 routes
across 10 of the 47 stored runs declare a param named neither `id` nor `slug`.**

The scaffold now reads `Object.values(params)[0]`, and both alias sites mint one alias — none at all
when the app declares its own param child. Measured over all 47 stored tables by
`scripts/measure/route_alias_census.py`: **36 runs change, 800 → 727 routes, 73 removed, and no
declared route is lost on any run.** 8 tests, 11 mutations, 0 survivors.

---

## Findings that were NOT the filed defect

1. **`page_experience.py`'s "double ask" does not exist, and the premise was a stale config read.**
   Session 12 filed *"`TEXT_MODEL == ARCHITECT_MODEL == google/gemini-2.5-flash` at runtime … the
   same model asked twice, 34-48 s a run."* **Resolved from the running api container:
   `TEXT_MODEL` is `google/gemini-2.5-flash`, `ARCHITECT_MODEL` is `anthropic/claude-haiku-4.5`.**
   All three planning chains are genuine two-model failover. The second ask also fires **only when
   the first fails or returns no roles** — every loop breaks or returns on success — so it is a
   failure-path cost, not a per-run tax. `backend/.env` is **not tracked in git**, so when it
   changed is not recoverable. The owner's constraint (*explicit retry, or nothing*) resolves to
   **nothing**, for a better reason than expected. Item withdrawn.

2. **`apply_product_kind_to_plan` is applied twice on every healthy run** — `plan_phase.py:119` and
   `:190` ("re-apply kind lock after packs") — and it **concatenates its `PRODUCT_KIND=…` clause
   into `design_direction` each time**. `apply_product_kind_to_architect` is likewise applied twice
   (`:305`, `:315`). The page inventory and route table are provably stable under the second
   application; the *direction string* is not. This is prompt pollution on every run, it predates
   this session, and I did **not** fix it — adding a dedupe guard would change the healthy path,
   which is exactly what this session's fixes were forbidden to do.

3. **Session 12's "neither branch of `apply_product_kind_to_architect` fires on ops kinds" is
   true only for *substantive* route tables.** On an empty one the `not substantive` branch fires
   for **every** kind, which is the whole reason piece (a) works for `internal_ops` and
   `saas_workspace` and not just the public kinds. Not a correction — a scope clarification, and
   the one that had to hold for the fix to be worth landing.

4. **`_normalize_architect` mutates the dict it is handed.** My first deterministic-paths census
   compared before/after a second application *after* calling it, and so reported every kind as
   unstable — measuring its own side effect. The comparison has to be taken first.

5. **A React Router app can declare three routes matching one URL and still be "correct" by every
   check we run.** The smoke pass counts them as three, the dead-link guard sees three live
   targets, and the page behind all three resolves nothing. No existing gate looks at whether the
   *bound param name* is the one the page reads.

---

## Mutation results — 34 new, 68 applied over three sweeps, three first-sweep survivors

| driver | sweeps | result |
|---|---|---|
| `mutate_mandatory_deterministic_paths.py` | 2 | 23 mutations. First sweep: **1 survivor**, 22 caught. Second: **23 applied, 0 survivors** |
| `mutate_route_alias_inflation.py` | 2 | 11 mutations. First sweep: **2 survivors**, 9 caught. Second: **11 applied, 0 survivors** |

**A new failure mode, and it belongs on the standing list.** The survivor in the 1.12 sweep applied
cleanly and was **semantically a no-op**: it inserted a substantive route table one line above the
`architect = {}` that immediately overwrote it. The driver's `mutated == original` check cannot see
a no-op the *interpreter* undoes — only the fact that no test went red revealed it, and the driver
reporting it as a survivor is the correct conservative call. Re-anchoring it on the branch's **last**
statement made it bite. Note the bare `architect = {}` could not be the anchor: it appears in both
branches, and an anchor that matches twice tests nothing.

The two survivors in the alias sweep are blind spot 4 in both its forms: nothing asserted the
detail page's `.trim()`, and **the listing alias site does not run at all unless a detail component
sits outside the listing prefix** — with only `/gallery` and `/gallery/:paintingId`, the site whose
suppression was mutated never executes.

---

## What I got wrong in session 13

- **I published a route-alias number that was a paraphrase, twice, and caught it both times only by
  checking against the shipped artifacts.** The first census reconstructed "before" by appending a
  `:slug` twin to every path ending in `/:id` — but the old code skipped paths already ending in
  `/:id` (`assemble.py:1017`), so it invented 9 routes across 7 runs that no run ever shipped
  (14 runs / 18 routes, wrong). The second drove the real previous `assemble.py` out of git but
  **flattened `src/pages/owner/*` into `src/pages/`**, so `_resolve_page` silently dropped 9 of
  request 69's 15 routes and it under-reported instead (5 runs / 9 routes, also wrong). The honest
  figure is **36 runs / 73 routes**, and the tell was that request 69 — the run whose shipped
  `App.tsx` I had already read — was missing from the changed list.
- **My first healthy-path fixture was not healthy, and it took two failures to notice.** The fake
  `req` was a `SimpleNamespace` missing `concept_name`, then `needs_ai`; each raised *inside* the
  planner loop, which the new fallback then caught, so the test asserting "a healthy planner is not
  replaced" was exercising the degraded path. Using the real `Request` model unpersisted is what
  fixed it — a hand-rolled fake of a model with 30 columns is a fixture that drifts by design.
- **I nearly wrote up "internal_ops/generic" as the corpus's intended subtype.** The contract calls
  it `ops`. Driving the resolver rather than reading the dataclass would have caught it a step
  earlier; instead a probe did, before the number was published.

---

- **The plan and its evidence: [docs/PREVIEW_ROADMAP.md](docs/PREVIEW_ROADMAP.md).** Read the
  **session 13 callout** at the top of **Status**, then the four new Status rows, then the **1.12
  update block** in Phase 1 and the **withdrawn double-ask** section.
- **Before spending a trio: [docs/FIRST_FUNDED_TRIO_PREFLIGHT.md](docs/FIRST_FUNDED_TRIO_PREFLIGHT.md).**
- Why the pipeline shipped bad output: [docs/PREVIEW_QUALITY_FINDINGS.md](docs/PREVIEW_QUALITY_FINDINGS.md).

**If you read one thing: [The next step](#the-next-step).** It is an ordered list, not a theme.

---

## State of the repo, in four lines

- **`main` is level with `origin/main` at `80a3d71` plus session 13's four commits**, which are
  unpushed. The sixteen-commit backlog is gone.
- **Suite: 1,867 passed / 1 skipped / 0 xfailed / 0 failed. Vitest: 39 passed**, `tsc -b` clean.
  Run pytest the documented way — see the operating notes.
- **Credits: $0. `total_usage 330.229` of `total_credits 330`**, unchanged in 24 hours. No
  generation can run. The ~$40 over two days is still unexplained and is the owner's call.
- **CI has been triggered on `main` and never observed.** Private repo, no `gh`, 404 unauthenticated.

---

## The next step

**Ordered. Item 0 gates every item that needs a run.**

0. **Top up or rotate the OpenRouter key, then probe before anything else.**

   ```bash
   docker compose exec -T api python -c "
   import requests
   from app.core.config import settings
   print(requests.get('https://openrouter.ai/api/v1/credits',
       headers={'Authorization': f'Bearer {settings.OPENROUTER_API_KEY}'}, timeout=20).json())"
   ```

1. **Prove the SEVEN unproven fixes on a run that reaches a build.**
   `scripts/measure/launch_duo3.sh` is written and ready — the briefs of 95/97 (restaurant) and
   96/98 (hotel) verbatim. What to read afterwards, in order:
   - **no route at `/gallery`, no `src/pages/ArtworkDetailPage.tsx`** on either run.
   - `navigation.public` carries **both** `/reservations` and `/my-reservations`, different labels.
   - no `mock.ts` contains *"warm, specific, and ready when you are"*.
   - `design_system.font_family` is not a squashed slug.
   - **NEW — no `App.tsx` contains a `:slug` route**, and no listing has two param children.
     `grep -c ':slug' src/App.tsx` should be 0 on both runs.
   - **NEW — every detail page reads `Object.values(params)[0]`**, and opening
     `/<listing>/<second card's slug>` shows the *second* item, not the first.
   - **`docker compose logs api --no-color > file` the moment each run finishes**, then grep
     `slot_fill rejected`. If `AboutPage.tsx` or `ContactPage.tsx` still appear, the remaining
     cause is the plan page and `0e678fa` is only half the fix.
2. **1.12's reachability.** Everything landed this session is proven by mutation and **not** by a
   run reaching the branch. The cheapest honest proof does not need a provider outage: point
   `ARCHITECT_MODEL` at an unroutable model id, run one generation, and confirm it **ships a
   3-6 page blueprint preview inside the 10-minute cap** with `degraded` carrying
   `architect/call_failed_deterministic_blueprint` and a stored `preview_app`. Then do the same
   with `PREVIEW_APP_MODEL` for piece (b). **Recreate, do not restart** — and dump the log first.
3. **`slot_fill`'s rejection distribution.** Questions 2 and 3 are still open and still need the
   log from item 1. n=4 is a lead, not a distribution.
4. **`_design_system_dict` discards four derived colours.** Structural and certain, rate not
   measurable. `(primary, secondary, font)` hardcodes `text_color`, `muted_text_color`,
   `background_color` and omits `surface_color`. The fix threads the palette through
   `mock_data.py:313`, `:323`, `:375` and `brand_contract.py:255`, `:638`. **Wants a run.**
5. **The classifier's substring hits.** A guest house is a trading desk because its *name* contains
   "Rooms". The corpus and the census exist and re-run offline; the fix does not, and it is not
   "add more keywords". The shape that would hold: match on **word boundaries** rather than bare
   substrings, and require an ops/trading verdict to rest on something other than a business name.
   Owner call, because it changes what every brief resolves to — re-run
   `synthetic_kind_census.py` and `gallery_gapfill_census.py` before and after.
6. **`design_direction` is concatenated twice per run.** Finding 2. Cheap, but it changes a prompt
   on the healthy path, so it wants a run beside it rather than a blind edit.
7. **Dead nav data** — `navigation.customer/.staff/.features/.manager` and `navItemsAdmin` /
   `adminNavItems` are read by nothing. Listed so it stops being rediscovered as a rendering defect.
8. **Someone with a browser still has to look at CI once.**

**Owner decisions, unchanged and still yours:** whether the p50 row moves to Phase 2 under (A);
whether `SiteSpec` or `AppSpec` is Phase 2's spec (nothing in Phase 2 has been started); the
`state_ids` backfill; whether to relax the AppSpec schema; whether a four-to-six page preview is the
product you want; key rotation and the mystery spend.

---

## Binding owner constraints — these do not expire

- **Fix the PIPELINE, never a generated preview.** Editing anything under `data/preview-apps/**` to
  make a defect go away is always wrong. *Reading* those workspaces for evidence is fine and is how
  most findings get made — including three of this session's.
- **Generation must not exceed 10 minutes.** Do **not** relax the deadline to make runs pass. A
  degraded preview that ships is the designed outcome, and as of `dc750a3` three more stages can
  actually produce one. **The degraded ship happens inside the cap or not at all** — none of this
  session's fallbacks buys time; each replaces a raise with a deterministic path that costs no
  model call.
- **If you find a defect, fix it in the pipeline and add a test that fails with the fix reverted.**
- **Work the roadmap in order.** Phase 0 → 1 → 2 → 3 → 4. **Phase 1 is not finished** — 1.10 and
  1.11 are open. There is no remaining licence to pull Phase 2 work forward.

### The rule that has caught the most defects

**Mutation-test every guard.** Revert the fix, confirm the test goes red, restore — from an
**in-memory** backup, never `git checkout`. **Twenty-one** drivers now live in
`backend/scripts/cli/mutate_*.py` and one in `preview-template-tests/tools/mutate.py`.
**Run one at a time** — two sweeps against the same live-mounted source make both verdicts noise.

Nine blind spots, all found the expensive way. Check for each by default:

1. **Asserting against the case that does not bind.**
2. **Driving the consumer, never the producer** — or the reverse.
3. **Guards that cannot fail.**
4. **Fixtures too small to reach the rule.** Two of session 13's three survivors, and it now has a
   second form worth naming: **a fixture too small to reach the CODE PATH at all.** The listing
   alias site never executes unless a detail component sits outside the listing prefix, so
   disabling its guard changed nothing.
5. **A test that adapts until it passes cannot fail** — and it can arrive through the **fixture**
   rather than the assertion. Session 13's "healthy planner" fake was missing two columns, each of
   which raised inside the planner loop, so the new fallback caught it and the healthy-path test
   was silently exercising the degraded path. **Fake a model with the model.**
6. **Never assert against the constant a mutation would change.**
7. **A fix that changes no outcome is not a fix.** Measure it against the corpus *before*
   committing.
8. **A measurement that paraphrases the code measures the paraphrase.** Session 13 paid this twice
   in one census. Drive the real function; when you need the old behaviour, **execute the old
   file** (`git show <ref>:path` into a temp module) rather than re-deriving it. And check the
   *shape* of every call you copy.
9. **A mutation can apply cleanly and still be a no-op.** New in session 13. `mutated == original`
   catches a textual no-op; nothing catches a statement the next line overwrites. Anchor a mutation
   on the **last** statement whose effect you mean to destroy, and treat an unexplained survivor as
   a possible dead mutation before concluding the test is weak.

Assume any DoD row you did not personally mutate is unproven.

---

## Operating notes — every one has cost real time

| | |
|---|---|
| **Probe credits BEFORE anything else** | The api restart and the npm-cache warm-up are wasted if the account is empty, and the failure looks exactly like defect 1.12. One-liner in *The next step*, item 0 |
| **Resolve config from the RUNNING PROCESS — and never from a previous session's note** | **Sharpened, session 13.** A filed defect ("the same model asked twice") rested on a config reading that is no longer true: `ARCHITECT_MODEL` is `anthropic/claude-haiku-4.5`, not gemini. `backend/.env` is **not tracked in git**, so a stale note about it cannot be dated or diffed |
| **`restart` reloads code; it does NOT reload `env_file`** | `docker compose restart api` re-execs with the environment baked in at *container-create* time. `docker compose up -d --force-recreate api` is required — and **that destroys the container log**, so dump it first |
| **Dump the log before any recreate** | `docker compose logs api --no-color > file` |
| **The test command** | **`docker run`, not `docker compose exec`.** Three independent ways it lies, all three looking like application defects |
| **There is no `git` inside the test image** | Session 13. A census that wanted the previous version of a file had to be handed it with `--before-file`, extracted on the host |
| **`industry` is `Form(None)`** | Omitting it silently resolves to `generic` and produces convincing garbage. **Always set it** |
| Host port | **8001**. Multipart, not JSON |
| Trailing slash | `POST /api/requests/` 307-redirects and **drops the body**. No trailing slash |
| Reload code | `docker compose restart api`. **Restart before any run meant to measure today's code** |
| Industries | A **different** one per run in a batch |
| pytest | **Read the SUMMARY LINE, never the exit code** |
| Working directory | **Drifts between tool calls. Use absolute paths.** Seventh session running, and it bit twice today |
| **Prompts are not observable — and neither are plans** | `preview_app.roles` stores role ids with **no pages**. Any claim about what a model was *shown* can only be settled by replaying offline |
| Archive what you measure | A number from the database or the docker volume is unverifiable next session |

### The test command, and the three traps in the convenient alternative

```bash
docker run --rm -v "/Users/maurice/Documents/Dev/BMV:/repo" -w /repo/backend \
  -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api \
  -c 'pip install -q pytest; python -m pytest tests/ -q'
```

`docker compose exec api` is faster to type and wrong three independent ways: `sh -lc` drops node
(six unrelated tests go red pointing at application logic); the `api` service mounts only `backend/`,
so four repo-root-reading tests get `FileNotFoundError`; and `test_request_40_defects.py`'s two
kit-reading tests fail on the same mount.

**Do not run a pytest container or a mutation sweep while a generation is in flight.**

### Running the offline census tools

The ones that need **no database** run anywhere — and there are three new ones:

```bash
docker run --rm -v "$REPO:/repo" -w /repo/backend \
  -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api \
  -c 'python3 scripts/measure/deterministic_paths_census.py'                       # 1.12, per kind
  -c 'python3 scripts/measure/synthetic_kind_census.py --explain'                  # the 20 briefs
  -c 'python3 scripts/measure/gallery_gapfill_census.py --routes ../docs/evidence/preview-routes.json'
```

`route_alias_census.py` needs the previous `assemble.py`, and the image has no `git`:

```bash
git show <ref>:backend/app/application/preview_app/assemble.py \
  > backend/scripts/measure/.assemble_before.py
docker run ... -c 'python3 scripts/measure/route_alias_census.py \
  --routes ../docs/evidence/preview-routes.json --before-file scripts/measure/.assemble_before.py'
```

The ones that read the **database** run in the api container and take run ids:

```bash
docker compose exec api python /app/backend/scripts/measure/codegen_cost.py 97 98
docker compose exec api python /app/backend/scripts/measure/appspec_cost.py 97 98
docker compose exec api python /app/backend/scripts/measure/appspec_enforcement_replay.py 97 95
```

`session11_fix_replay.py` needs both the database and the workspace archive, and the archive is not
mounted into the api container. Copy it in:

```bash
docker compose cp docs/evidence/preview-workspaces.tar.gz api:/tmp/ws.tar.gz
docker compose exec api sh -c 'mkdir -p /tmp/ws && tar -xzf /tmp/ws.tar.gz -C /tmp/ws'
docker compose exec api python /app/backend/scripts/measure/session11_fix_replay.py --workspaces /tmp/ws
```

Postgres credentials are `-U bmv -d buildmyversion`, not `postgres`.

---

## What is still broken

Ordered by what I would do first. Every item has evidence; none is speculative.

### 1. The account is empty and ~$40 over two days is unaccounted for

Blocks every remaining production proof. Unchanged, and now 24 hours older.

### 2. Seven fixes are mutation-proven and production-unproven

Session 11's menu / subcopy / font, session 12's gap-fill and detail-assignment, session 13's 1.12
and route aliases. **1.12's is the one whose unprovenness matters most**: it is a fallback, so a
run that never fails never exercises it. See *The next step* item 2 for a proof that does not
require waiting for a real outage.

### 3. The classifier decides a product kind on bare substrings

New and measured. A guest house is a trading desk because its **name** contains "Rooms";
`internal_ops` is close to unreachable in plain English; a driving school takes the storefront
default. `docs/evidence/synthetic-briefs.json` + `synthetic_kind_census.py --explain`.

### 4. Page identity is fixed in shadow and not under enforcement

`bbe6359` removes the gallery from a substantive shadow-mode app. Under an enforced AppSpec the
canonical page for `/menu` carries prose that resolves to `public-service`, so the gap-fill still
adds a catalogue. The unused signal is `capability_ids` (`CAP-BROWSE-MENU`), which `_search_text`
does not read.

### 5. p50 is 563-570 s against a ≤ 500 s DoD

Untouched by sessions 11, 12 and 13. The census stands: `slot_fill` and the plan phase decide it,
`appspec` is 8 %, the recommendation is **(A)**. Owner ruling pending; **the row is not moved.**

### 6. `slot_fill` rejects 25 of 42 fills and the distribution is still unmeasured

`0e678fa` removes one demonstrated cause of one rejection class. How much of the 59.5 % it was is
unknown and needs a run plus a log dump.

### 7. `_design_system_dict` discards four of the derived palette's six colours

Structural and certain, rate unmeasurable. See *The next step* item 4.

### 8. `design_direction` accumulates its kind clause twice a run

Finding 2. Prompt pollution on the healthy path, predates this session, not fixed blind.

### 9. 1.11 — the reserve is unbounded as a whole

Unchanged. If you attack this again the axis that killed attempt one is *pages actually given a
visual verdict*, not wall clock. **Measure both, separately.**

### 10. 1.10 — green on `main` is unverified

The push happened; the observation did not. Private repo, no `gh`, 404 unauthenticated.
