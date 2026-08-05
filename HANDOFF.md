# Session handoff — the gallery is a literal, and enforcement cannot delete it (2026-08-05, session 11)

Successor to session 10's handoff (in git history at `ad0cc6f`). Still-binding parts are restated
below; do not go back for them. Process notes, not product docs.

---

## Session 11, in one page

**Six generations run** (97, 98, 99, 100, 101, 102) — the first session in three to spend runs, and
they answered three questions offline work could not. Four commits, 30 new tests (23 pytest, 7
vitest), **33 new mutations — 44 applied across four sweeps, 0 survivors** (5 survived a first sweep).

**Scoreboard: 97 and 98 shipped `ready`. 99, 100, 101 and 102 all shipped nothing.** 99 and 100 are
the enforcement spike (spec rejected, gate raised). **101 and 102 are a provider outage**:
`build_experience_plan`'s planner took `ProviderGenerationError: Provider HTTP 408` on *both* models
in its chain and the `deepseek/deepseek-v4-pro` failover stalled 60-100 s a call, so both runs
degraded `codegen` at `retry_skipped_no_runway` and stored no `preview_app`. **1.12 reproducing a
fourth and fifth time**, and not caused by anything in this session's diff — a probe between the runs
returned in 0.6-1.5 s on the same model.

### What that proves and what it does not — read this before trusting the fixes

Both proof runs **built a workspace** before dying, so `mock.ts` exists for 101 and 102 and the
question is which stages had already run when they did.

| fix | status | evidence |
|---|---|---|
| **the derived palette** | **PRODUCTION-PROVEN**, two runs, two industries | 101 ships `primary_color: #1d7b4c`, 102 ships `#b62bb6`. The same briefs shipped `#0f766e` on 95, 97 and on every prior run of the dental brief. It is written at the plumbing stage, which precedes codegen, so the degradation did not reach it |
| **the menu label collision** | **NOT proven** — mutation-proven only | `normalize_mock_navigation` runs *before every build*, and neither run reached a build. Both `mock.ts` files carry raw architect titles ("Menu — Osteria Vinci") and even a `/gallery/:id` nav entry, which is exactly what an un-normalised nav looks like |
| **the hero subcopy** | **NOT proven** — mutation-proven only | Neither `mock.ts` has a `subcopy:` key at all: `ensure_seed_scaffold_fields` only fires when the AI's mock synthesis drops `hero`, which happened in 7 of 64 archived runs (~11 %). One run was never likely to exercise it |
| **the font spelling** | **NOT proven** | 102 carries `"Source Sans 3"`, but that is the brief's spelling and the `_design_system_dict` repair path never fired. Indistinguishable from the old behaviour on this run |

**Do not let the palette result carry the other three.** Three of the four remain exactly where
session 10's four fixes were: mutation-proven, production-unproven.

**One thing the dead runs did prove, and it is the session's headline seen live:** request 101's
architect route table for the twelve-table trattoria contains `/gallery` **and `/gallery/:id` labelled
"Artwork"** — the `_storefront_pages()` literal, on a restaurant, in a run of today's code.

### The finding that explains the owner's headline complaint

**The twelve-table trattoria's art gallery is a hardcoded blueprint page.** Not an industry
inference, not a writer's guess, not the AppSpec being discarded:

```
product_kind.py:475-496   _storefront_pages()
    PageBlueprint("gallery",        "Gallery", "/gallery",     ... "GalleryPage.tsx")
    PageBlueprint("gallery_detail", "Artwork", "/gallery/:id", ... "ArtworkDetailPage.tsx")
product_kind.py:1008-1010
    elif contract.kind in PUBLIC_KINDS:
        routes, files, _ = _inject_blueprint_routes(routes, files, contract, role_id)
```

Every brief classified `storefront` or `booking_service` is gap-filled with those two pages **even
when its route list is already substantive** — the `elif` exists to do exactly that. 16 of the
corpus's 18 distinct briefs classify `storefront`. The string "Artwork" is a `PageBlueprint` title.

**And it survives an enforced AppSpec**, which is what the spike was for.

### The enforcement spike — the experiment failed twice and the answer came out anyway

`APPSPEC_MODE=on`, verified from the running process, brief of 95/97, twice. **Both runs shipped
nothing.** 99 and 100 are `status: failed` with empty `generated_pages`: the authored spec failed
deterministic validation (`must_requirement_cannot_be_deferred: REQ-ABOUT-001`;
`requirement_traced_and_deferred: REQ-RESPONSIVE-001`) and `appspec_gate.py:182` raises when
`enforce_app_spec`. Exactly the risk the brief named.

**It is not enforcement authoring a worse spec.** `ensure_approved_app_spec` takes neither a mode nor
a policy, and `APPSPEC_FALLBACK_ENABLED` is `False` in both modes — the authoring and validation path
is byte-identical. The rejections are model variance; enforcement changes only the *consequence*. On
this one brief the spec is now **accepted on 95 and 97, rejected on 99 and 100 — 2 of 4.**

So rather than gamble a third run on a coin flip, I replayed it. Everything downstream of an accepted
spec is deterministic and two accepted specs for this brief are stored:
`scripts/measure/appspec_enforcement_replay.py`, re-derivable offline, no credits.

| | shadow | enforced | removed | survives |
|---|---|---|---|---|
| 95 | 13 routes | **6** | owner console (5), `/my-profile`, `/my-reservations`, `/private-events` | `/gallery`, `/gallery/:id` |
| 97 | 18 routes | **9** | owner console (5), `/menu/food`, `/menu/wine`, `/privacy-policy`, `/terms-of-service` | `/gallery`, `/gallery/:id` |

**One line puts the gallery back on both runs** — `apply_product_kind_to_architect`
(`plan_phase.py:305`) reaching `product_kind.py:1008-1010`. The `internal_desk` and
`saas_accounting` forcers (`:306`, `:310`), the second kind lock (`:315`) and
`ensure_ai_feature_route` (`:370`) add **nothing**. That was the surprise the brief asked for, and it
is narrower than expected: one line, not four.

Two consequences: enforcement **does** halve the route table and would bring the render-check
denominator under the cap of 12 by itself (closes item 8 with no cap change) — and it **cannot** fix
page identity while a blueprint gap-fill outranks the contract.

**`.env` is back to `APPSPEC_MODE=shadow`, verified from the running process.**

### Duo 2 (97, 98) — session 10's four fixes are production-proven

2 of 2 shipped `ready`, 563 s / 570 s, on the briefs of 95/96 verbatim. All four checks the brief
asked for:

| claim | verdict |
|---|---|
| `codegen_cost.py` shows `planning` and no `(unattributed)` | **holds** — `planning/planner` 60.6 s, `plan_validation` 33.9 s, `design_manifest` 3.6 s on 97, and **no `codegen` row with a NULL writer** |
| `withheld_reason` present on both runs | **holds** — a key on 97, absent on 95/96, value `None` when served. `viewable` correctly still not a key |
| the fix agent's route block carries a `detail_level` | **not proven, and it cannot be from a run** — the block goes into a prompt, and prompts are not logged or stored. `fix_agent` ran 3 calls / 150.1 s on 97, so the code path executed. Verifiable only by replay |
| no `mock.ts` contains "Explore the collection" | **holds** — once on 95, **zero** on 97 |

Three of four production-proven; the fourth is unobservable from a run and needs a replay harness.

### What landed

| commit | what |
|---|---|
| `3b63a07` | the palette is derived from the business. 13 mutations |
| `8fe8955` | a label collision renames a route, it does not delete it; hero subcopy; font spelling. 9 + 5 + 17 mutations |
| `241812e` | the enforcement replay tool |
| this one | handoff + roadmap |

---

## Findings that were NOT the filed defect

1. **The corpus is 18 distinct briefs, not 62 sites.** 62 workspaces, **12 distinct business names**,
   25 of them one art gallery (`Jeanne Kassab Art`). Every "N of 62" in these documents is closer to
   "N of 18" than it sounds, and **12 is the ceiling any per-business palette could reach on it.**
   This is the most load-bearing correction in the session and it reframes several measurements.

2. **Candidate (a) for the palette was measured and is worthless.** Deleting the demo-stage table and
   letting `brand_brief._industry_bucket` decide gives **three** distinct colours over the same 62
   workspaces — the identical count, merely redistributed, with 28 still on `#0f766e`. The brief
   asked me to check this before choosing and it was the right instruction.

   **And state the cost of (b) plainly, because you will see it before you read this.** A derived
   palette gives every business *its own* colour and gives no business a *fitting* one. Northgate
   Dental Studio now resolves to **`#b62bb6`, a magenta**; Osteria Vinci to a green, Cedar Point
   Lodge to a slate blue. Every one is contrast-solved and legible — that is guaranteed by
   construction — and none of them is chosen because it suits a dental practice or a trattoria.
   That is the trade the measurement forced: appropriateness was never on offer from a five-bucket
   keyword table that put 28 of 62 businesses, most of them art galleries, in `wellness`. **If you
   want appropriateness back it needs a signal that is not an industry string** — the reference
   site's own colours are the obvious candidate and the pipeline currently extracts none. That is a
   real next question, not a defect in what landed.

3. **An art gallery is bucketed `wellness` because its brief says it is not a clinic.** The gallery
   description ends *"not a booking SaaS or clinic front desk"* and `_industry_bucket` matches
   `clinic`. `product_kind.scrub_negated_product_clauses` exists for exactly this and **does not
   reach it** — its pattern lists product nouns and `clinic` is not one. Measured over all 84 stored
   requests, applying that scrub changes **zero** buckets, so I did **not** ship it: an inert edit is
   not a fix. The bucket now decides voice prose only.

4. **The menu's on-screen defect is entirely the generator's, and the roadmap said otherwise.** The
   shipped `mock.ts` already labels `/my-reservations` "Reservations" — the `My ` strip happens at
   `mock_data.py:1016`, not in the template. And `/reservations` is missing because
   `_normalize_nav_section` deduped on the **label key** and **deleted** the losing route. Corrected
   in place in the roadmap rather than left standing beside the correction.

5. **`finish_reason: error` was a bad provider day.** Duo 1: **52 error rows of 149 calls (34.9 %)**,
   50 with zero completion tokens. Duo 2, next day: **2 of 152 (1.3 %)**, and **both carry real
   tokens** — the failed-mid-stream shape occurred **0 times in 152 calls**. `slot_fill`'s discarded
   time fell 147.7 → **83.4 s/run** with it. **Do not rewrite the transport layer.** The brief said
   measure first; measuring said stop.

6. **The five dead skeletons are correctly dead.** Over the 18 distinct briefs: 16 `storefront`, 1
   `booking_service`, 1 `saas_workspace/generic`, and **zero** `internal_ops` or trading/accounting
   subtypes — the only paths that emit `ops-ledger-home`, `ops-invoice-board`, `ops-recon-split`,
   `ops-blotter-desk`, `ops-expense-queue`. Nobody has ever asked this pipeline for a trading desk.
   **Not unreachable code.** Rotating skeletons for variety would put a ledger desk on a restaurant.

7. **The ops components are at 90 %+ because the ops console is universal.** `StatCard`, `DataTable`,
   `FilterBar`, `ActivityFeed`, `ChartCard` are the owner console's slot defaults, and a five-page
   owner console is appended to storefronts that never asked for one — the same routes enforcement
   removes. The genuinely universal *chrome* is `PublicShell` / `PublicNav` / `BrandFooter` /
   `PageHeader` / `OpsShell`. The layout choices that should vary and do not are `MarketingHero`,
   `CTABand`, `FeatureBento`, `TestimonialRail`, `ProductShowcase` — every public home in the corpus
   is hero → features → showcase → testimonials → CTA → footer.

8. **A substring census of component usage is wrong and I nearly published one.** `OpsShell` appears
   as a bare word in 60 workspaces and is imported by 60; `ProductShowcase` appears in 62 and is
   imported by 56; `Table` appears in 10 and is imported by 1. Parse the `import { … }` list.

9. **`appspec_gate.py:212` still carries a hardcoded `#0f766e`** as the last fallback for
   `primary_color`. It is provably unreachable — `ensure_brand_brief` runs three lines above and
   always produces a palette — so I left it rather than make an untested edit. Recorded here so it
   stops being rediscovered as the palette defect.

10. **`_design_system_dict` hardcodes `text_color`, `muted_text_color` and `background_color`.** When
    the brand-contract repair fires (8 of 62 workspaces show its signature), those three overwrite
    the brief's derived values. `primary`/`secondary` are passed in and survive. Not fixed — it needs
    a run to verify and the colour half of the monoculture is the visible one.

---

## Mutation results — 33 new, 44 applied, and five survived a first sweep

| survivor | why |
|---|---|
| `collisions against a sibling's FULL label stop counting` (vitest **and** pytest) | my fixture's two *full* labels collided too, so one guard explained every failure and the other could be deleted green |
| `collisions between two shortened labels stop counting` (vitest) | same fixture, opposite guard — the two overlap on the obvious case |
| `the label key stops normalising` (vitest) | every fixture label was byte-identical, so case folding never mattered |
| `the path-derived fallback is removed` (pytest) | no fixture ever exhausted both candidates; it needs **two routes carrying the same literal label** |

**All five are blind spot #4 — fixtures too small to reach the rule** — and four of them are the same
shape: *two guards that overlap on the obvious fixture*. When a fix has two conditions, write a
fixture that binds each one **alone**, or the sweep will tell you one of them is decoration. The
vitest sweep found this first and the pytest sweep then found it again on the same rule, which is a
useful accident: the same fix at two layers gave two independent chances to notice.

---

## What I got wrong in session 11

- **I destroyed duo 2's container log with `docker compose up -d --force-recreate api`.** The recreate
  was necessary (see the trap below) but I ran it before dumping the log, so the `slot_fill rejected
  … (catalogue-contract: <validator errors>)` lines for 97 and 98 — the entire input to item 5 — are
  gone. Session 9 wrote down that a log living only inside a container is one restart from
  unverifiable. **Dump the log before any recreate.**
- **I wrote a fix, measured it, and it changed nothing** — applying `scrub_negated_product_clauses`
  in `_industry_bucket` alters **0 of 84** briefs. Caught before committing this time, which is the
  only difference from session 10's version of the same mistake.
- **I wrote a vitest test asserting an improvement that never existed** (a missing nav label falling
  back to a title-cased path). The old code produced the raw href and so does the new one; I had
  written a test for behaviour I assumed rather than read. Replaced with a case that is actually
  about the rule.
- **My first palette test asserted `industry_bucket == "creative"`** for the gallery brief — an
  outcome my own change did not produce, because the scrub does not reach `clinic`. The test was
  right about the intent and wrong about the mechanism, and it went red immediately, which is the
  system working.

---

- **The plan and its evidence: [docs/PREVIEW_ROADMAP.md](docs/PREVIEW_ROADMAP.md).** Read the
  **enforcement spike** callout at the top of **Status**, then **The catalogue census**, then
  **Phase 1 DoD**.
- **Before spending a trio: [docs/FIRST_FUNDED_TRIO_PREFLIGHT.md](docs/FIRST_FUNDED_TRIO_PREFLIGHT.md).**
- Why the pipeline shipped bad output: [docs/PREVIEW_QUALITY_FINDINGS.md](docs/PREVIEW_QUALITY_FINDINGS.md).

**If you read one thing: [The next step](#the-next-step).** It is an ordered list, not a theme.

---

## State of the repo, in four lines

- **`main` has nine unpushed commits** as of 2026-08-05 session 11 — session 10's five (`46c28d2`,
  `e0eeec5`, `eb49f43`, `b729d88`, `ad0cc6f`) plus `3b63a07`, `8fe8955`, `241812e` and this one. It
  was level with `origin/main` at `122ef79`.
- **Suite: 1,808 passed / 1 skipped / 0 xfailed / 0 failed. Vitest: 39 passed**, `tsc -b` clean. Run
  pytest the documented way — see the operating notes.
- **Credits: $19.50 left of $330** (used $310.50). Six generations this session; `usage_daily` was
  **$0.04 at session start and $2.53 after six runs**, so this session's spend is ~$2.49 — about
  $0.42 a generation, in line with every trio ever measured. **The $17.62/day mystery spend of
  2026-08-04 did not recur.** One data point, not an all-clear; escalating the key is still the
  owner's call. Runs are not the constraint.
- **CI is still unreadable from here.** `gh` is not installed and the Actions page 404s
  unauthenticated. **1.10 is not done until that vitest job is green on `main`.**

---

## The next step

**Ordered. The first three change what a person looking at a preview sees.**

1. **Delete the gallery gap-fill, or make it conditional on the contract.** `product_kind.py:1008-1010`
   gap-fills `_storefront_pages()` into every public-kind app whose routes are *already substantive*.
   That single `elif` is why a trattoria ships `ArtworkDetailPage.tsx`, and it survives an enforced
   AppSpec. **The fix must not be an industry keyword** — the honest shape is that a gap-fill may only
   add a page the app has no equivalent of, and "catalogue of things you can look at" is not
   something a twelve-table restaurant lacks, it is something it does not have. Measure how many of
   the 18 briefs lose a page they actually needed before shipping it.
2. **Prove the menu, subcopy and font fixes on a run that actually finishes.** The palette is done
   (101 and 102, two industries). The other three need a run that reaches a *build*, because
   `normalize_mock_navigation` and `ensure_seed_scaffold_fields` both run there and both of this
   session's proof runs died in codegen. What to read afterwards: `navigation.public` must contain
   **both** `/reservations` and `/my-reservations` with **different labels** when the architect
   declares both; and no `mock.ts` may contain *"warm, specific, and ready when you are"*. The
   subcopy fires in ~11 % of runs, so **a single run will probably not exercise it** — check the
   route-table shape instead, or force it offline.
3. **`slot_fill`'s contract rejections — one captured rejection, and it is the gallery again.** 25 of
   42 calls rejected on duo 2, **all `finish_reason: stop`**, so they are contract violations, not
   transport failures — that half is measured and closed. The per-rejection validator errors are
   logged at `generate.py:483-491` and nowhere else; duo 2's log was destroyed, but one was captured
   live on request 101:

   ```
   AboutPage.tsx (restaurant)  detail painting-first hero (variant=item),
                               detail itemSpecs binding, detail inquire CTA (#inquire)
   AboutPage.tsx (dental)      detail painting-first hero (variant=item),
                               detail itemSpecs binding, detail seed.credentials instead of itemSpecs
   ServicesPage.tsx            SkeletonComposer invocation, assigned skeleton literal, slot:hero, …
   TreatmentsPage.tsx          missing directory face component:PageHeader, missing services binding
   ```

   **Two of four are the same defect in two unrelated industries.** An About page is being assigned
   the `public-detail` skeleton, whose contract (`catalogue_contract/validate.py:227-244`) requires a
   **painting-first hero**, an `itemSpecs` binding and an `#inquire` CTA — written, per its own
   comment, against **request 50, a fine-art gallery**. So a dentist's About page is discarded for
   failing three assertions about paintings. Three questions, none answered: why is an About page
   assigned `public-detail` at all (that is upstream of the contract, and fixing the contract alone
   would only move the failure); how much of duo 2's 59.5 % is this; and is that contract right even
   for a gallery. **Dump the log the moment a run finishes.** n=4 is a lead, not a distribution.
4. **Route alias inflation, from the scaffold end.** Unchanged from session 10 and still not landed:
   `catalogue_contract/scaffold.py:466` reads `params.id ?? params.slug`, which is *why*
   `assemble.py:1098` mints both aliases. Have the scaffold read the single declared param whatever
   it is named, then one route suffices and both aliases can go.
5. **`page_experience.py`'s double ask.** `TEXT_MODEL == ARCHITECT_MODEL == google/gemini-2.5-flash`
   at runtime, so `build_experience_plan`'s `(TEXT_MODEL, ARCHITECT_MODEL)` loop and
   `validate_and_expand_plan`'s `(ARCHITECT_MODEL, TEXT_MODEL)` loop are the same model asked twice —
   34-48 s a run. **Not looked at this session.** Careful: on request 95 the *second* ask returned
   the usable plan, so a naive dedupe loses it. Explicit retry, or nothing.
6. **Dead nav data** — `navigation.customer/.staff/.features/.manager` and `navItemsAdmin` /
   `adminNavItems` are read by nothing. Bundle weight and reader confusion, zero visible effect.
   Listed so it stops being rediscovered as a rendering defect.
7. **Someone with a browser still has to look at CI once.**

**Two owner decisions, unchanged and still yours:** whether the p50 row moves to Phase 2 under (A)
(the arithmetic is in the roadmap and session 11 did not touch it), and whether a four-to-six page
preview is the product you want to ship — which the enforcement replay now answers concretely, since
it says an enforced contract gives 6 routes on 95 and 9 on 97.

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
**in-memory backup**, never `git checkout`. **Seventeen** drivers now live in
`backend/scripts/cli/mutate_*.py` and one in `preview-template-tests/tools/mutate.py`.
**Run one at a time** — two sweeps against the same live-mounted source make both verdicts noise.

Seven blind spots, all found the expensive way. Check for each by default:

1. **Asserting against the case that does not bind.**
2. **Driving the consumer, never the producer** — or the reverse.
3. **Guards that cannot fail.**
4. **Fixtures too small to reach the rule.** Session 11's five survivors were all this, and four were
   one specific version of it: **two guards that overlap on the obvious fixture.** When a fix has two
   conditions, write a fixture that binds each one *alone*.
5. **A test that adapts until it passes cannot fail.**
6. **Never assert against the constant a mutation would change.**
7. **A fix that changes no outcome is not a fix.** Measure it against the corpus *before* committing.
   Session 10 shipped one into the working tree and reverted it; session 11 caught one at the same
   spot (a scrub that changes 0 of 84 briefs).

Assume any DoD row you did not personally mutate is unproven.

---

## Operating notes — every one has cost real time

| | |
|---|---|
| **`restart` reloads code; it does NOT reload `env_file`** | **New, session 11, and it cost a wasted verification cycle.** `docker compose restart api` re-execs the process with the environment baked in at *container-create* time, so an edit to `backend/.env` is invisible. `docker compose up -d --force-recreate api` is required — and **that destroys the container log**, so dump it first |
| **Dump the log before any recreate** | `docker compose logs api --no-color > file`. Session 11 lost duo 2's `slot_fill rejected` lines — the entire input to a filed task — to a recreate run one command too early |
| **The test command** | **`docker run`, not `docker compose exec`.** Three independent ways it lies, all three looking like application defects |
| **`industry` is `Form(None)`** | Omitting it silently resolves to `generic` and produces convincing garbage. **Always set it** |
| Host port | **8001**. Multipart, not JSON |
| Trailing slash | `POST /api/requests/` 307-redirects and **drops the body**. No trailing slash |
| Reload code | `docker compose restart api`. `exec api` does **not** reload. **Restart before any run meant to measure today's code** |
| Industries | A **different** one per run in a batch |
| pytest | **Read the SUMMARY LINE, never the exit code** |
| Working directory | **Drifts between tool calls. Use absolute paths.** Fifth session running |
| **Prompts are not observable** | Nothing stores or logs a prompt, so any claim about *what a model was shown* can only be proven by replaying the builder offline. Three of session 10's four fixes were checkable from a run; the fix agent's `detail_level` was not |
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
kit-reading tests fail on the same mount. Measured: 2 failed / 134 passed under compose, 136 passed
under `docker run`.

**Do not run a pytest container or a mutation sweep while a generation is in flight.**

### Running the offline census tools

```bash
mkdir -p /tmp/ws && tar -xzf docs/evidence/preview-workspaces.tar.gz -C /tmp/ws
docker run --rm -v "$REPO:/repo" -v /tmp/ws:/ws:ro -w /repo/backend \
  -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api \
  -c 'python3 /repo/backend/scripts/measure/route_bijection.py --workspaces /ws'
```

The ones that read the **database** run in the api container and take run ids:

```bash
docker compose exec api python /app/backend/scripts/measure/codegen_cost.py 97 98
docker compose exec api python /app/backend/scripts/measure/appspec_cost.py 97 98
docker compose exec api python /app/backend/scripts/measure/appspec_enforcement_replay.py 97 95
```

`appspec_enforcement_replay.py` is new in session 11 and needs an **accepted** AppSpec revision for
the run id — 95 and 97 have one; 99 and 100 do not, which is the point of them. Postgres credentials
are `-U bmv -d buildmyversion`, not `postgres`.

---

## What is still broken

Ordered by what I would do first. Every item has evidence; none is speculative.

### 1. Page identity is a blueprint literal, and no contract outranks it

`product_kind.py:1008-1010` gap-fills `_storefront_pages()` — `/gallery` and `/gallery/:id →
ArtworkDetailPage.tsx` — into every `PUBLIC_KINDS` app, including ones whose routes are already
substantive, and including ones whose accepted AppSpec declares four pages and none of them a
gallery. This is the largest single cause of "every site looks the same" that is not a colour.

### 2. p50 is 563-570 s against a ≤ 500 s DoD

Duo 2 is 563 s and 570 s against duo 1's 571/573 — no material movement. Session 10's census stands:
`slot_fill` and the plan phase are the terms that decide it, `appspec` is 8 %, and the recommendation
is **(A)**. Owner ruling still pending; **the row is not moved.**

### 3. `slot_fill` rejects 25 of 42 fills and nobody knows why

Duo 2: 59.5 % rejection rate, **all `finish_reason: stop`**, 83.4 s/run discarded. These are contract
violations, not transport failures — that half is now measured and closed. The validator errors are
logged and only logged. See *The next step* item 3.

### 4. 1.12 — a MANDATORY stage with no deterministic path

Unchanged. `plan_phase.py:295-298` rescues an architect failure only when `enforce_app_spec`, which
is never true in shadow. **Session 11 adds the other edge of the same knife:** in enforced mode
`appspec_gate.py:182` makes a rejected spec fatal, and rejection is 2 of 4 on the one brief with four
samples. Both modes have a failure that ships nothing; they are different failures.

### 5. Ship rate and the gate

Duo 2 shipped 2 of 2 `ready`. Trio 7 shipped 0 of 3. The variable is AppSpec acceptance, which is
also what decides whether an enforced run ships at all.

### 6. 1.11 — the reserve is unbounded as a whole

Unchanged from session 10. If you attack this again the axis that killed attempt one is *pages
actually given a visual verdict*, not wall clock. **Measure both, separately.**

### 7. 1.10 — green on `main` is unverified

Runner and CI job are done and merged; `main` has never been observed running them.

### 8. Four of session 10's fixes were unproven; three now are

`46c28d2`, `e0eeec5` and `b729d88` are production-proven on request 97. `eb49f43`'s `detail_level`
is **not**, and cannot be from a run — it lives in a prompt, and nothing stores prompts. It needs an
offline replay of `_catalogue_routes_context` against a stored architect dict.
