# Session handoff — the gallery is gone in shadow, and the account is empty (2026-08-05, session 12)

Successor to session 11's handoff (in git history at `283f60c`). Still-binding parts are restated
below; do not go back for them. Process notes, not product docs.

---

## Session 12, in one page

**Zero generations run, and not by choice.** The OpenRouter account is exhausted. Four commits, 28
new pytest cases, **21 new mutations, 22 applied across three sweeps, 0 survivors** (1 survived a
first sweep). Suite **1,838 passed / 1 skipped / 0 failed**, vitest **39**, `tsc -b` clean.

### Read this first: no live run is possible

`https://openrouter.ai/api/v1/credits` returns `total_credits 330, total_usage 330.229`. A
28,000-`max_tokens` probe against `google/gemini-2.5-flash`, `deepseek/deepseek-v4-pro` and
`z-ai/glm-5.2` returns **"Insufficient credits"** on all three in under a second. That probe is the
only reason a duo was not launched into a wall — run it before anything else next session.

**The pipeline did not spend it.** `usage_daily` is **$22.25**; `ai_usage_events` records **$1.94**
for 2026-08-05 across 217 calls, which is session 11's six runs at 06:00-07:00 plus three zero-cost
probes at 15:00. **~$20.3 of today's spend is not this pipeline**, on a day this session ran zero
generations. **This is the second measured occurrence** — 2026-08-04 was $17.62 by the same
arithmetic, and session 11 wrote it down as "one data point, not an all-clear." It is now two, and
the second one emptied the account. Escalating or rotating the key is the owner's call.

**Consequence for everything below: session 12 landed two fixes and neither is production-proven.
Session 11's three unproven fixes are still unproven.** Nothing here has been through a generation.

### What landed

| commit | what |
|---|---|
| `bbe6359` | a blueprint page is added only when nothing already serves it — **the gallery** |
| `0e678fa` | a page is a detail page because of its route, not its prose — **the `public-detail` assignment** |
| `28712b3` | the three unproven fixes, replayed against stored production inputs |
| `cbb5b1e` | the gap-fill census measured a corpus it had forced to `storefront` — corrected |
| this one | handoff + roadmap |

### 1. The gallery gap-fill — done in shadow, still there under enforcement

`product_kind.py`'s `elif contract.kind in PUBLIC_KINDS` branch gap-filled `_storefront_pages()`
into every public app whose routes were **already substantive**, and its only test for "already
served" was an exact **path string**. So an app declaring `/menu` or `/rooms` was told it had no
catalogue and was given `/gallery` + `/gallery/:id → ArtworkDetailPage.tsx`.

It now adds a page only when nothing in the app already serves it: the same path, or **the same
resolved page contract** — asked of the plan page merged under the route, which is the same
question and the same document `_normalize_architect` answers twelve lines later. A **detail** page
is added only when the listing it belongs to is served and has no detail child of its own.

Two exemptions, stated rather than implied. `/` is keyed on its path alone, because
`assemble.py:1123` is `<Route path="*" element={<Navigate to="/" replace />} />` and an app with no
root route redirects to nothing. And a **thin** inventory still receives the whole blueprint — there
the blueprint is the product face, not a gap-fill.

**Measured before shipping**, over the 47 stored route tables:

| | |
|---|---|
| runs that change | **23 of 47** (21 of the 42 that round-trip) |
| briefs / runs that lose their last **catalogue** page | **0 and 0** |
| briefs / runs that lose their last **detail** page | **1 and 1** — request 95, the trattoria, which keeps `/menu` and loses `ArtworkDetailPage.tsx` |
| the trattoria | 77, 83, 95, 97 lose `/gallery` and `/gallery/:id` outright |
| free win | 47 and 69 stop being given a second detail route beside their own `/gallery/:paintingId` |
| **the boundary** | **4 runs still get a gap-filled catalogue because they declared none** — 19 and 43 are art galleries and should; **80 and 86 are the trattoria**, whose `/menu` does not resolve to `public-catalog` on those runs |

**It does not close the enforced case, and I checked.** The replay still shows 4 → 6 on request 95:
the AppSpec page for `/menu` reads *"To display the current food and wine menus."*, and nothing in
that resolves it to a catalogue. The capability id `CAP-BROWSE-MENU` would, and `_search_text` does
not read capability ids. `APPSPEC_MODE` is `shadow`, so this is a note for whenever it is turned on.

15 tests, 13 mutations, 0 survivors.

### 2. Why an About page is assigned `public-detail` — answered, and it is one substring

This is item 3's upstream question, and the answer is smaller and worse than expected.
`_infer_skeleton_id` matched the **bare substring `"detail"`** anywhere in the blob built from a
page's id, title, page_type, purpose, layout, path and role labels. Ordinary English decided a page
kind. Shown on stored production routes with **no plan merged**: request 76's `/contact` ("lodge
contact **details**.") and request 79's `/about` ("Page **detailing** the story") both land on
`public-detail`, whose contract then demands a painting-first hero, an `itemSpecs` binding and an
`#inquire` CTA.

**Over the 399 stored public routes: 95 reach the detail branch, 94 of them on the bare word alone,
and 35 of those name no item in their path.** It is not only About pages — `/book`,
`/booking/checkout`, `/booking/confirmation` and `/patient/treatment-plan` were all being judged
against a painting contract.

A detail page shows ONE item, which is a fact about the route. The rule is now a path that selects
an item, **anchored at the end** so `/artwork/:artworkId/inquire` stays a form *about* an item;
plus the unambiguous multi-word phrases; plus the existing `/services/<name>` rule. **22 of the 399
change and 21 are corrections.** The one loss is `/painting/coastal-whispers` — a literal item path
with no parameter — which becomes `public-service`. That is the deliberate trade: over-assignment
throws a page's work away, under-assignment only gives it a more permissive contract.

13 tests, 8 mutations, 0 survivors.

### 3. The palette's second half — checked, and there is nothing to extract

`reference_metadata` carries **no colour of any kind**. `fetch_reference_metadata` returns exactly
six keys — `title`, `description`, `h1`, `visible_text_snippet`, `og_image`, `fetch_success` — and
never reads CSS, an inline style or an image. 40 requests carry a `reference_url`, 39 stored
metadata, 39 fetched successfully. The 12 blobs containing a `#` are matching **street addresses**
("757 S Alameda St #180") and phone numbers.

The only latent signal is **`og_image`, present on 13 of 39** — the reference site's own hero image.
Turning that into a palette needs a fetch, a decode and a quantiser on the critical path. That is a
new capability, not a check, so it is written down and not built. As instructed: checked, and
stopped.

### 4. The three unproven fixes — replayed, not proven

A duo was the plan. `scripts/measure/session11_fix_replay.py` is the sanctioned substitute and it
drives the real functions with the workspaces and route tables production produced:

| fix | replayed verdict |
|---|---|
| **the menu label collision** | request 95's table declares `/reservations` and `/my-reservations`; rebuilt through `_nav_from_architect` and normalized, `navigation.public` carries **both**, "Book Your Table" and "Reservations". **n=1** — it is the only archived workspace with a colliding pair |
| **the hero subcopy** | the **12** workspaces that shipped *"warm, specific, and ready when you are"* have their `hero` stripped (the condition the scaffold fires under) and rebuilt: **12 of 12** come back without it. Better than a run would have given — the subcopy fires in ~11 % of runs |
| **the font spelling** | `Source Sans 3` stays `Source Sans 3`; the `+` slug stays in the Google Fonts URL |

**None of this is a production proof.** What a replay cannot show is that the pipeline *reaches*
these functions with this data on a live run, and both of session 11's proof runs died in `codegen`
before it could. All three stay production-unproven.

---

## Findings that were NOT the filed defect

1. **My own census forced the whole corpus to `storefront`, and it took an archive mode to notice.**
   It called `resolve_product_kind_contract(*context_from_request(req))`. `context_from_request`
   returns a **string**; the splat passed it one character per argument, `_blob` rejoined them as
   "r e s t a u r a n t", no keyword matched, and every run fell through to the `storefront`
   default. `appspec_enforcement_replay.py:98` has the same call written correctly, which is how the
   shapes were compared. **Two published numbers were wrong because of it and are corrected in the
   roadmap in place**: the corpus is **15 of 17 briefs storefront**, not 16 of 18; and a
   `booking_service` brief is gap-filled `_booking_pages()` — home, `/services`, `/book` — and
   **has never been given a gallery at all.** The dental brief is a `booking_service`. Every
   sentence of the form "every brief classified storefront *or booking_service* gets the gallery"
   was wrong.

2. **The same census re-implemented the rule instead of calling it**, and diverged on ops kinds,
   where *neither* branch of `apply_product_kind_to_architect` fires and nothing is gap-filled.
   Both columns now drive the production function; the "before" column wraps
   `_inject_blueprint_routes` to force the old behaviour. **A census that paraphrases the code is
   measuring the paraphrase.**

3. **Replaying `normalize_mock_navigation` over a shipped `mock.ts` proves nothing**, and the first
   version of the replay reported a failure because of it. The normalizer only ever *narrows* a
   list. Request 95's `/reservations` was deleted by the old rule **before** that file was written,
   so the fixed code running over the damaged output still cannot produce it. The nav has to be
   rebuilt from the architect first, which is what a live build does. **When a fix is upstream of an
   artifact, replaying it over the artifact is a null experiment.**

4. **Plans are not observable either.** The "prompts are not observable" note needs a second half:
   `preview_app.roles` stores role ids and **no pages**, so the plan a route was normalized against
   is gone. For most of the 16 stored About/OurStory/Contact routes carrying `public-detail`, the
   route text alone resolves to `public-service` — meaning the plan page supplied it, and which of
   the two mechanisms fired on a given run is **not recoverable**.

5. **Session 11's "8 of 62 workspaces show the brand-repair signature" could not be reproduced, and
   the signature does not mean what it looks like.** 31 of 66 archived workspaces carry
   `_design_system_dict`'s `#0f172a` / `#475569` / `#fafafa` triple — but that triple is
   **indistinguishable from the pre-derivation default**, and none of the 31 post-dates `3b63a07`.
   Requests 101 and 102 ship the **full** six-colour derived palette, so the repair did not fire on
   either. **The firing rate is not measurable from the corpus.** What is certain is structural, and
   it is still unfixed: `_design_system_dict(primary, secondary, font)` takes three arguments and
   hardcodes the other four colours, so *any* call to it discards derived text / muted / background
   / surface. The fix is a parameter thread through `mock_data.py:313`, `:323`, `:375` and
   `brand_contract.py:255`, `:638`, none of which currently carries the palette. **Not done blind
   with no run available.**

6. **`architect-routes.json` cannot answer a page-identity question** and I nearly used it. It holds
   42 runs and drops `purpose` — which is the single field that identifies a gap-filled route,
   because `_inject_blueprint_routes` copies `bp.purpose` verbatim and "Catalogue grid of products
   or artworks." is a repository literal no model wrote. `docs/evidence/preview-routes.json` is new
   and holds all 47 with full route dicts **and each run's `kind_context`**, so the census cannot
   drift on classification.

---

## Mutation results — 21 new, 22 applied, one first-sweep survivor and one that never applied

| | |
|---|---|
| `mutate_blueprint_gap_fill.py` | 13 mutations, **0 survivors** at the end. One did not apply on the first run: the AI-hub anchor `if not isinstance(route, dict) or _is_ai_hub_route(route):` **matches twice** in `product_kind.py`, and the driver reported it as *not applied* rather than counting it caught. Widened to include the two following lines |
| `mutate_detail_skeleton_assignment.py` | 8 mutations, **1 survived a first sweep** — moving the item-path regex from `…$` to unanchored changed nothing, because no fixture put a parameter in the *middle* of a path. Request 45's `/artwork/:artworkId/inquire` is exactly that shape and is now a fixture |

**The survivor is blind spot #4 again — a fixture too small to reach the rule** — and the near-miss
is a new one worth adding to the list: **an anchor that matches twice tests nothing, and only the
driver's own count catches it.** Both drivers report anchor drift as a survivor for that reason.

---

## What I got wrong in session 12

- **I shipped a census with two defects and cited its numbers in a commit message.** `bbe6359` says
  "22 runs change" and "no brief ends without a catalogue page or without a detail page" — both
  computed on a corpus every run of which had been forced to `storefront`. The corrected figures are
  in `cbb5b1e` and in the roadmap. The commit message stands as written; the roadmap is the
  authority.
- **I guessed the cause of the About/`public-detail` defect before measuring it** — I expected a
  purpose containing "detail" and went looking for it. That turned out to be *one* of two
  mechanisms and accounts for a minority of the stored cases; the other is the plan page, and it is
  unrecoverable. The measurement was right, the first hypothesis was half right, and only the
  measurement said which half.
- **My first replay of the nav fix reported a failure that was the replay's fault, not the fix's.**
  See finding 3. I nearly recorded "the menu fix is NOT landed."
- **I planned a duo and had to check credits to find out I could not run one.** The pre-flight
  document already lists that check as first; I ran it third, after restarting the api and warming
  the npm cache. Run the probe first.

---

- **The plan and its evidence: [docs/PREVIEW_ROADMAP.md](docs/PREVIEW_ROADMAP.md).** Read the
  **credit callout** and the **enforcement spike** at the top of **Status**, then the two new
  Status rows, then **`slot_fill`'s contract rejections**.
- **Before spending a trio: [docs/FIRST_FUNDED_TRIO_PREFLIGHT.md](docs/FIRST_FUNDED_TRIO_PREFLIGHT.md).**
- Why the pipeline shipped bad output: [docs/PREVIEW_QUALITY_FINDINGS.md](docs/PREVIEW_QUALITY_FINDINGS.md).

**If you read one thing: [The next step](#the-next-step).** It is an ordered list, not a theme.

---

## State of the repo, in four lines

- **`main` has thirteen unpushed commits** as of 2026-08-05 session 12 — session 10's five, session
  11's four, plus `bbe6359`, `0e678fa`, `28712b3`, `cbb5b1e` and this one. It was level with
  `origin/main` at `122ef79`.
- **Suite: 1,838 passed / 1 skipped / 0 xfailed / 0 failed. Vitest: 39 passed**, `tsc -b` clean. Run
  pytest the documented way — see the operating notes.
- **Credits: $0. `total_usage 330.229` of `total_credits 330`.** No generation can run.
  `usage_daily` $22.25 against $1.94 this pipeline recorded. Second occurrence of the mystery spend.
- **CI is still unreadable from here.** `gh` is not installed and the Actions page 404s
  unauthenticated. **1.10 is not done until that vitest job is green on `main`.**

---

## The next step

**Ordered. Item 0 gates every other item that needs a run.**

0. **Top up or rotate the OpenRouter key, then probe before anything else.**

   ```bash
   docker compose exec -T api python -c "
   import requests
   from app.core.config import settings
   print(requests.get('https://openrouter.ai/api/v1/credits',
       headers={'Authorization': f'Bearer {settings.OPENROUTER_API_KEY}'}, timeout=20).json())"
   ```

   Two days now carry ~$20 of spend this pipeline did not make. Whether that is a leaked key, a
   second consumer or a billing artifact is not answerable from here.

1. **Prove the four unproven fixes on a run that reaches a build.** `scripts/measure/launch_duo3.sh`
   is written and ready — the briefs of 95/97 (restaurant) and 96/98 (hotel) verbatim, which is the
   pair the census says loses the gallery on every stored run. What to read afterwards:
   - **no route at `/gallery` and no `src/pages/ArtworkDetailPage.tsx`** on either run. The
     restaurant is the sharper test; the hotel loses it on all 8 stored runs and the restaurant on
     4 of 6, so a restaurant that still ships one means `/menu` did not resolve to a catalogue and
     the boundary is wider than measured.
   - `navigation.public` carries **both** `/reservations` and `/my-reservations` with **different**
     labels when the architect declares both.
   - no `mock.ts` contains *"warm, specific, and ready when you are"* — ~11 % of runs, so one run
     probably will not exercise it; the replay covers 12 of 12 offline.
   - `design_system.font_family` is not a squashed slug.
   - **`docker compose logs api --no-color > file` the moment each run finishes**, and grep
     `slot_fill rejected`. If `AboutPage.tsx` or `ContactPage.tsx` still appear, the remaining cause
     is the plan page and `0e678fa` is only half the fix.
2. **`slot_fill`'s rejection distribution.** Questions 2 and 3 of the three filed are still open:
   how much of duo 2's 59.5 % was the `public-detail` contract, and whether that contract is right
   even for a gallery. Both need the log from item 1. n=4 is still a lead, not a distribution.
3. **`_design_system_dict` discards four derived colours.** Structural and certain; the rate is
   not measurable (finding 5). It takes `(primary, secondary, font)` and hardcodes `text_color`,
   `muted_text_color`, `background_color` and omits `surface_color`, so any call to it overwrites
   most of the derived palette. The fix threads the palette through `mock_data.py:313`, `:323`,
   `:375` and `brand_contract.py:255`, `:638`. **Wants a run to verify** — that is why it is here
   and not landed.
4. **Route alias inflation, from the scaffold end.** Unchanged from sessions 10 and 11 and still
   not landed: `catalogue_contract/scaffold.py:466` reads `params.id ?? params.slug`, which is *why*
   `assemble.py:1098` mints both aliases. Have the scaffold read the single declared param whatever
   it is named, then one route suffices and both aliases go. **`0e678fa` makes this cheaper**: a
   parameterized path now resolves to `public-detail` on its own, so the scaffold no longer needs
   the alias to be recognised as a detail page.
5. **`page_experience.py`'s double ask.** `TEXT_MODEL == ARCHITECT_MODEL == google/gemini-2.5-flash`
   at runtime, so `build_experience_plan`'s `(TEXT_MODEL, ARCHITECT_MODEL)` loop and
   `validate_and_expand_plan`'s `(ARCHITECT_MODEL, TEXT_MODEL)` loop are the same model asked twice
   — 34-48 s a run. **Still not looked at.** Careful: on request 95 the *second* ask returned the
   usable plan, so a naive dedupe loses it. Explicit retry, or nothing.
6. **1.12 — five fires, and both edges of the same knife.** 74, 92, 94, 101, 102 stored nothing. 101
   and 102 were a provider outage across `build_experience_plan`'s whole chain, so `architect` is
   not the only MANDATORY stage with no deterministic path. In shadow a planner failure ships
   nothing; in enforced mode a rejected spec ships nothing.
7. **Dead nav data** — `navigation.customer/.staff/.features/.manager` and `navItemsAdmin` /
   `adminNavItems` are read by nothing. Bundle weight, zero visible effect. Listed so it stops being
   rediscovered as a rendering defect.
8. **Someone with a browser still has to look at CI once.**

**Owner decisions, unchanged and still yours:** whether the p50 row moves to Phase 2 under (A) — the
arithmetic is in the roadmap and sessions 11 and 12 did not touch it; whether a four-to-six page
preview is the product you want; whether to relax the AppSpec schema; and whether a hash-derived
palette is the right trade now that the reference site has been checked and holds no colour.

---

## Binding owner constraints — these do not expire

- **Fix the PIPELINE, never a generated preview.** Editing anything under `data/preview-apps/**` to
  make a defect go away is always wrong. *Reading* those workspaces for evidence is fine and is how
  most findings get made.
- **Generation must not exceed 10 minutes.** Do **not** relax the deadline to make runs pass. A
  degraded preview that ships is the designed outcome.
- **If you find a defect, fix it in the pipeline and add a test that fails with the fix reverted.**
- **Work the roadmap in order.** Phase 0 → 1 → 2 → 3 → 4. **Phase 1 is not finished.** There is no
  remaining licence to pull Phase 2 work forward.

### The rule that has caught the most defects

**Mutation-test every guard.** Revert the fix, confirm the test goes red, restore — from an
**in-memory backup**, never `git checkout`. **Nineteen** drivers now live in
`backend/scripts/cli/mutate_*.py` and one in `preview-template-tests/tools/mutate.py`.
**Run one at a time** — two sweeps against the same live-mounted source make both verdicts noise.

Eight blind spots, all found the expensive way. Check for each by default:

1. **Asserting against the case that does not bind.**
2. **Driving the consumer, never the producer** — or the reverse.
3. **Guards that cannot fail.** Session 12 deleted one before writing it: there is no
   `served_kinds.add` beside the gap-fill's `existing_paths.add`, because no contract declares two
   blueprint pages of the same kind and it could not have changed an outcome.
4. **Fixtures too small to reach the rule.** Session 11's five survivors and session 12's one were
   all this. When a fix has two conditions, write a fixture that binds each one *alone*.
5. **A test that adapts until it passes cannot fail.**
6. **Never assert against the constant a mutation would change.**
7. **A fix that changes no outcome is not a fix.** Measure it against the corpus *before*
   committing.
8. **A measurement that paraphrases the code measures the paraphrase.** New in session 12, and it
   cost two published numbers. Drive the real function; if you need the old behaviour for a
   before/after, wrap the real function rather than rewriting it. And check the *shape* of every
   call you copy — `f(*context_from_request(req))` splats a string into characters and every
   downstream number was silently wrong.

Assume any DoD row you did not personally mutate is unproven.

---

## Operating notes — every one has cost real time

| | |
|---|---|
| **Probe credits BEFORE anything else** | **New, session 12.** The api restart and the npm-cache warm-up are wasted if the account is empty, and the failure looks exactly like defect 1.12. The one-liner is in *The next step*, item 0 |
| **`restart` reloads code; it does NOT reload `env_file`** | `docker compose restart api` re-execs with the environment baked in at *container-create* time, so an edit to `backend/.env` is invisible. `docker compose up -d --force-recreate api` is required — and **that destroys the container log**, so dump it first |
| **Dump the log before any recreate** | `docker compose logs api --no-color > file`. Session 11 lost duo 2's `slot_fill rejected` lines — the entire input to a filed task — to a recreate run one command too early |
| **The test command** | **`docker run`, not `docker compose exec`.** Three independent ways it lies, all three looking like application defects |
| **`industry` is `Form(None)`** | Omitting it silently resolves to `generic` and produces convincing garbage. **Always set it** |
| Host port | **8001**. Multipart, not JSON |
| Trailing slash | `POST /api/requests/` 307-redirects and **drops the body**. No trailing slash |
| Reload code | `docker compose restart api`. `exec api` does **not** reload. **Restart before any run meant to measure today's code** |
| Industries | A **different** one per run in a batch |
| pytest | **Read the SUMMARY LINE, never the exit code** |
| Working directory | **Drifts between tool calls. Use absolute paths.** Sixth session running |
| **Prompts are not observable — and neither are plans** | Nothing stores a prompt, and `preview_app.roles` stores role ids with **no pages**, so the plan a route was normalized against is gone too. Any claim about what a model was *shown*, or about which of route-text and plan-text decided a skeleton, can only be settled by replaying offline |
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

The two that need **no database** run anywhere:

```bash
docker run --rm -v "$REPO:/repo" -w /repo/backend \
  -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api \
  -c 'python3 scripts/measure/gallery_gapfill_census.py --routes ../docs/evidence/preview-routes.json'
```

The ones that read the **database** run in the api container and take run ids:

```bash
docker compose exec api python /app/backend/scripts/measure/codegen_cost.py 97 98
docker compose exec api python /app/backend/scripts/measure/appspec_cost.py 97 98
docker compose exec api python /app/backend/scripts/measure/appspec_enforcement_replay.py 97 95
docker compose exec api python /app/backend/scripts/measure/gallery_gapfill_census.py
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

Blocks every remaining production proof. See the top of this document.

### 2. Four fixes are mutation-proven and production-unproven

Session 11's menu / subcopy / font, and session 12's gap-fill and detail-assignment. The replay
harness covers what a replay can cover and says so.

### 3. Page identity is fixed in shadow and not under enforcement

`bbe6359` removes the gallery from a substantive shadow-mode app whose own catalogue resolves as
one. Under an enforced AppSpec the canonical page for `/menu` carries prose that resolves to
`public-service`, so the gap-fill still adds a catalogue. The unused signal is `capability_ids`
(`CAP-BROWSE-MENU`), which `_search_text` does not read.

### 4. p50 is 563-570 s against a ≤ 500 s DoD

Untouched by sessions 11 and 12. The census stands: `slot_fill` and the plan phase decide it,
`appspec` is 8 %, the recommendation is **(A)**. Owner ruling pending; **the row is not moved.**

### 5. `slot_fill` rejects 25 of 42 fills and the distribution is still unmeasured

`0e678fa` removes one demonstrated cause of one rejection class. How much of the 59.5 % it was is
unknown and needs a run plus a log dump.

### 6. 1.12 — a MANDATORY stage with no deterministic path

Five fires: 74, 92, 94, 101, 102. `plan_phase.py:295-298` rescues an architect failure only when
`enforce_app_spec`, which is never true in shadow; `appspec_gate.py:182` makes a rejected spec fatal
when it is. `build_experience_plan` has no deterministic path either.

### 7. `_design_system_dict` discards four of the derived palette's six colours

Structural and certain, rate unmeasurable. See finding 5 and *The next step* item 3.

### 8. 1.11 — the reserve is unbounded as a whole

Unchanged. If you attack this again the axis that killed attempt one is *pages actually given a
visual verdict*, not wall clock. **Measure both, separately.**

### 9. 1.10 — green on `main` is unverified

Runner and CI job are done and merged; `main` has never been observed running them.
