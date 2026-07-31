# Session handoff — preview quality (2026-07-31, session 3)

Successor to session 2's handoff (its content is preserved in git history at `a1fd49d`; the
still-binding parts are restated below). Process notes, not product docs. The permanent record of
*why* the pipeline shipped bad output is
[docs/PREVIEW_QUALITY_FINDINGS.md](docs/PREVIEW_QUALITY_FINDINGS.md).

**If you read one thing: [Where this stands](#where-this-stands).** Session 3 ran five live
generations and fixed everything each one exposed. Sessions 1 and 2 found defects by reading code;
session 3 found them by looking at the artifact, which is why the list below is different in kind.

## TL;DR

Session 2 left five P0s, all found by review, none demonstrated. **All five are fixed** (see
[Session 2's P0s](#session-2s-p0s--all-five-closed)). Session 3's own work came from generating
previews and inspecting them:

| run | reported | what it actually was |
|---|---|---|
| 40 | `ready`, gate PASSED, 9 type errors | unshippable: a doctor directory on a gallery's ops page, every catalogue card dead-ending, both home CTAs pointing at a route nothing serves — and **5 of 6 screenshots lost to a thread race**, so the one component that looks at pixels judged one page |
| 41 | `failed` | a repair introduced `aiFeatures is not defined`; the vision model then **described a hero image on the error box** |
| 43 | `failed` | 6/6 pages judged, 9 rendered, 3/3 journey hops walking — withheld by *our own* dead-link block over `/privacy` |
| 44 | `failed` | 12 rendered, 0 crashed — withheld by a **false positive**: template links judged as bare paths |
| 45 | `failed` | **6/6 judged, 12 rendered, 0 journey blocks** — and its own critic was right about three pages we then fixed. Also exposed the appspec hook strip emitted as adjacent JSX (build died) and a repair model holding one call open for **1040 s** before returning truncated output |
| 46 | `failed` | the retire-verdicts fix worked *too* well — five of six pages repaired, so five verdicts retired and coverage collapsed to one page. Also `/contact#contact-form` judged as a dead link, and `seed.ops` injected as four strings against `seed.ops.items.slice(0,4).map(…)` |
| 47 | **`ready`** — first pass since 40 | six of eight gallery cards were real close-up oil paintings. Still shipped: a truncated page from the *fix agent* (so `/artwork/1` served the home page), listing controls **below** the grid, `&copy; 2024` as literal text, and "Cta heading — Jeanne Kassab Art" — the last two mine |
| 48 | **in flight at handoff** | **5 initial type errors** (TS2322×2, TS2552×2, TS2353×1) against 26 on 47, 16 on 46, 15 on 45. Nothing else read yet — see [Next steps](#next-steps-in-order) |

The progression is the point. 40's defects were invisible. 43's and 44's were the *gate* being
wrong — visible, and therefore fixable. By 45 the instruments were sound enough that the pipeline's
own critic found three real product defects and described each one accurately. That is the
difference the session bought.

**29 commits** on `chore/remove-preview-generator-v2` (`31afda1`…`2b71943`),
**suite 1067 passed / 0 failed**, `docs/KNOWN_TEST_FAILURES.md` empty, working tree clean.

## The lesson request 47 taught, which is the one worth keeping

Three of its defects were **mine**, and all three had the same shape: a guard I
added to prevent a crash made the page worse than no guard at all.

The clearest is `seed.showcase`. The home page read
`seed.showcase?.length ? seed.showcase : [three real paintings]`. The seed guard saw
an undefined key, invented a one-row stub, `?.length` became truthy — and displaced
all three paintings. The page shipped a dark band with a heading over nothing. The
guard was correct about the absence and wrong about what to do with it.

So: **a repair has to be better than the thing it replaces, and that has to be
checked, not assumed.** A key whose read already falls back to a literal with
content is now left alone. An empty fallback (`?? []`) is still filled, because
there the page genuinely has nothing. Same principle as the four write guards and
the verdict retirement — the difference is that here the pipeline was overwriting
*good* data, which no gate was ever going to catch.

## What request 45's critic saw, and what it cost

Worth reading as a worked example of the instruments doing their job.

| page | score | the critic's words | the actual defect |
|---|---|---|---|
| Gallery | 60 | *"the image for 'Deep Sea Currents' clearly shows two blank canvases on small easels"* | 4 of 10 cards were photos of someone painting, one was a product mockup, one was an empty grey box |
| Owner login | 20 | *"the rest of the workspace displays three marketing cards … instead"* | `login` was lumped in with `account`, so a sign-in page rendered a card grid and no way to sign in |
| Contact | 20 | *"what is rendered is 'Your details', 'LINE ITEMS Signature package · Qty 1'"* | **true when measured, false when read** — the gate had since repaired the stub into a proper form, and the stale verdict withheld the preview |

The first two are fixed at `4979aac`, the third at `69ebba2`. The third is the more interesting one:
it is P0-3 one layer out. `_remeasure_refined_pages` re-derives the verdicts for pages the *visual
critic* refined; the *quality gate's* own heal and AI repair rewrite pages too, and nothing
re-derived those. A verdict describes source, so when a repair replaces that source the verdict is
now retired — the page becomes `unmeasured`, which is neither a pass nor a permanent block.

## Branch and deploy constraints — unchanged, still binding

- **Nothing has deployed.** `main` and `origin/main` are untouched; no PR opened.
- **Pushing `main` auto-deploys to production** via Coolify (`DEPLOY.md`).
- **Do not force-push. Do not amend `5fcae7c`.**
- **`.env.prod` is gitignored and holds real production values.** Do not undo the `.gitignore`
  rules denying `.env` / `.env.*` at any depth.

## Use this test command — both documented ones lie

```bash
docker run --rm -v "$PWD:/repo" -w /repo/backend \
  -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template \
  --entrypoint sh bmv-local-api \
  -c 'pip install -q pytest; python -m pytest tests/ -q'
```

- Plain `docker run -v "$PWD:/repo"` fails template-dependent tests: the image sets
  `PREVIEW_TEMPLATE_DIR=/app/backend/preview-template`, and that env var **wins over** `Settings`'
  path discovery — so tests read the template *baked into the image* while your edits sit unread
  under `/repo`. Hence the explicit `-e` override.
- `docker compose exec api` fixes the template but fails
  `test_admin_build_info.py::test_deploy_files_stamp_the_code_policy_revision`, which walks to
  `parents[3]` for the repo root, finds `/app`, and cannot see the deploy files.

**Read the summary line, not the exit code.** I committed `42f81b9` with 14 tests red because
`pytest … | tail -5` inside an `&&` chain masked the failure. Fixed in `051df0e`.

## Running a generation

```bash
docker compose restart api                    # `exec api` does NOT reload code
curl -s -X POST http://localhost:8001/api/requests \
  -F 'business_name=…' -F 'business_description=…' -F 'email=…'   # multipart, NOT JSON
```

- The host port is **8001**, not 8000. Creation auto-starts the pipeline.
- The **trailing slash** on `/api/requests/` 307-redirects and drops the body.
- The container's log timestamps run behind the host clock; compare log lines to each other, not to
  `date`.
- A run is ~15–20 min. Inspect with `scripts/preview-qa.sh <id> [tag]`, the stored `preview_app`
  result, and `docker compose exec api sh -c 'cd /app/data/preview-apps/<id> &&
  ./node_modules/.bin/tsc --noEmit -p tsconfig.app.json'`.

Other environment facts that cost me time: `awk` and `timeout` are absent from the host shell;
`psql` exists only inside the `db` container (`docker compose exec -T db psql -U bmv -d
buildmyversion`), where `sum(bool)` fails and you want `count(*) FILTER (WHERE …)`; the working
directory drifts between tool calls, so absolute paths or a leading `cd` are worth it; `write_file`
renames `src/pages/*.tsx` to canonical `*Page.tsx` and unlinks the original.

---

# Where this stands

Request 47 is the first `status=ready` since 40, and the first that is *close* to
demo-grade: an editorial gallery with six real close-up oil paintings, coherent
titles and prices, a working browse → detail → inquire path, and a footer wordmark
that renders. The four defects it still shipped are fixed; request 48 is the run
that tests them.

## What is now verified working, in a live run

- **Visual review: 6/6 pages judged**, 0 lost (was 1 of 6). The Playwright sync API cannot be
  entered from multiple threads — the parallel vision workers raced for the driver spawn and five
  captures died. All routes are now screenshotted in **one** browser session, serially, behind a
  process lock, before any vision call.
- **Render smoke check: 12 pages loaded, 0 crashed.** `finalize` probes each public route for a
  machine-readable error-boundary marker, stubs any page that crashes, rebuilds, and re-probes.
  `viewable` is false while a public page still crashes.
- **Journey: 3/3 storefront hops** (browse → detail → inquire) walking, with a deterministic repair
  that rewrites dead public links to a declared target before the gate blocks on them.
- **Item photography** is per-item now (`item1…item8` slots off a dedicated pool query), so the
  gallery cards are eight different pictures rather than one stock photo reused. Whether they are
  pictures *of paintings* is what `4979aac` addresses and request 46 tests.

## What is not

1. **Type errors are 16–26 per run before repair.** The *composition* keeps changing as each
   deterministic cause is removed — TS2339×10 → TS7006×9 → TS2304×12 — and each wave has been a
   real defect, so this number is a useful thermometer rather than noise. Request 44's *shipped*
   count was 5; the pre-repair number is the one to watch.
2. **The refine critic scores four pages 0–60 and skips them** (`refine SKIPPED … left as-is`).
   Honest, but those pages ship at their scaffold quality. Request 45's login page was one of them,
   and it was genuinely unusable.
3. **The gate's AI repair is the weakest remaining link.** It broke the build twice on 45 and twice
   on 47, and once returned unparseable JSON. It is asked to fix *visual* findings — "this page is
   off-brief" — which is not a patch instruction. It also tried to create a new kit component
   (`src/ui/QuantityAdjuster.tsx`), correctly refused, and then left a page importing something that
   does not exist.
4. **The home page hero is a stock photo of someone painting** (scored 65, a warn). The item grid
   ranks people last and `card1` does too; the *hero* deliberately does not, because for many
   businesses a person in the hero is right. For a portfolio it probably is not. Unresolved.
5. **`/admin/paintings/1/edit` crashed the render smoke check** on 47 (`Cannot read properties of
   undefined (reading 'trim')`). Ops surface, so recorded and not blocking — but it is a crash.

## Next steps, in order

**Start here.** Request 48 was mid-fix-loop when this session ended. Its initial typecheck was
**5 errors** — a real step down from 26/16/15 on the three runs before it. Read it end to end:

```bash
docker compose logs api --since 90m 2>&1 | grep -viE "urllib3|AIRetry|GET /api" \
  | grep -iE "quality gate|journey|visual critic|render smoke|retired|re-measur|OK Preview|not marking"
docker compose exec -T api sh -c 'cd /app/data/preview-apps/48 && \
  ./node_modules/.bin/tsc --noEmit -p tsconfig.app.json'
docker compose exec -T api python -c "import json; \
  d=json.load(open('/app/data/preview-apps/48/_bmv_visual_critique.json')); \
  print(d['review_status'], d['scores'], d['unmeasured'])"
QA_OUT_DIR=/tmp/qa48 scripts/preview-qa.sh 48 qa48
```

Then **look at the screenshots** — `/tmp/qa48/gallery.png` first. That is the page that has to say
"wow", and on 47 it was close: six real close-up oil paintings, coherent titles and prices. Four
things were fixed after it and none are verified live yet:

- the two grey placeholder cards (now a brand-tinted crop);
- the listing controls, which sat below the grid (now a `filters` slot ordered above it);
- `&copy; 2024` shipping as literal text;
- "Cta heading — Jeanne Kassab Art" shipping as body copy.

After that, in order:

1. **The gate's AI repair loop** — the weakest remaining link. It broke the build on 45 and 47, and
   returned unparseable JSON once. A visual finding ("this page is off-brief") is not a patch
   instruction: either give the repair the screenshot, or route visual findings to the composer that
   owns the page. Rollback and all-or-nothing plans now contain the damage; they do not fix the cause.
2. **The residual type errors** — one focused pass per wave. Each wave so far has been a real defect
   with a deterministic fix, and the composition keeps changing as each cause is removed.
3. **Two pages per run come back "no usable verdict"** from the vision model. Nobody has looked at a
   raw response yet.
4. Carried forward, unchanged: listing-page headers clipped against the nav on `/gallery`; no
   deterministic contrast guard on hero legibility; AppSpec shadow authoring's three failure modes;
   `requests.py:303-314` reads a `preview_contract.status` key v1 never returns; `retry-generation`'s
   lock calls `.start()` outside the `with`; 31 empty v2 tables; `APPSPEC_V2_COVERAGE_MODEL` is a
   live v1 setting with a v2 name.

---

# Session 2's P0s — all five closed

- **P0-1 imagery role queries dropped the industry text.** Fixed at `c9b0482` — the industry bucket
  is scored rather than first-match.
- **P0-2 a vision outage still reported "ready".** `finalize` now carries `visual_review_status`
  and refuses `ready` on `unmeasured`.
- **P0-3 a blocking visual finding could never be cleared.** `_remeasure_refined_pages` re-captures
  and re-derives the report before the gate reads it.
- **P0-4 `broken_rendered_image` blocked on every surface.** Now surface-scoped: BLOCK on public,
  WARN on ops — mirroring `asset_integrity`'s `public_surface` policy. A live run proved the need
  twice over: an admin *login* page scored 20 and withheld the entire public storefront.
- **P0-5 industry-mismatch margins computed and never read.** Both sides now need a real margin, and
  `_ADJACENT_FAMILIES` allows the `health`/`beauty` overlap.

# What session 3 changed

Grouped by the principle each one restores. The governing rule throughout: **a measurement with no
reader is indistinguishable from one that was never taken.**

## Nothing may look at fewer pages than it claims

`screenshot.py` captures every route in one serial session behind a process lock, and reports a
failed session as N unmeasured routes rather than silently returning fewer. `visual_critic.py`
hoists capture out of the vision workers entirely. A page that renders the error boundary is
recorded as `page_failed_to_render` (BLOCK public, WARN ops) — request 41 shipped a crashed home
page while the vision model wrote approvingly about its hero.

## A repair may not make things worse than it found them

- `refine_file` rejects a rewrite that does not parse when the source it would replace does.
  Slot-fill has checked this since the start; refine wrote straight to disk, so request 45's second
  pass on `LoginPage` killed the vite build for all twelve pages.
- `inject_appspec_contract_hooks` wraps the return body in a fragment instead of inserting its strip
  beside the existing root — the immediate cause of that build failure was **ours**, not the model's.
- `finalize`'s render smoke check stubs a crashed public page, rebuilds, and re-probes before
  reporting `viewable`.

## A measurement is only about the artifact that was measured

`invalidate_visual_verdicts` retires a persisted verdict when the gate's heal or AI repair rewrites
the page it describes. The page becomes `unmeasured` — not a pass, not a permanent block. This is
the same principle as the refine re-measurement, applied to the other writer.

Retiring alone turned out to be half a fix: request 46 repaired five of six pages and finished with
one verdict standing. `_run_visual_critique(only_components=…)` re-judges exactly the retired pages
after the gate settles, so the verdicts describe the source that ships. A page whose route the pass
cannot find stays `unmeasured` — clearing the list on the way past would turn "we could not judge
these" into "there was nothing to judge".

## No writer may replace parseable source with unparseable source

Four AI writers can replace a page: slot-fill, refine, the build fix agent, and the gate's repair
API. Slot-fill had checked its output since the start; the other three were added one at a time as
each shipped a broken page — the fix agent last, after request 47 truncated a detail page mid-attribute
so `dist/` kept an older bundle and `/artwork/1` quietly served the home page.
`test_every_ai_writer_checks_that_its_output_parses` pins all four together.

A failed rebuild after gate repair now rolls the repair back, so `evaluate_quality_gate` can never
judge source that `dist/` was not built from.

## The gate must be right before it is allowed to block

- `internal_hrefs` returns literals only; template bases go through `internal_href_prefixes` and are
  judged by whether *any declared route sits under them* (`_prefix_is_served`). Request 44 was
  withheld over three links that all worked.
- `repair_dead_internal_links` handles inert leaves (`/privacy` → `#`), surface leaves, and browse /
  contact synonyms, so blocking on a dead public link is safe — request 43 was withheld over
  `/privacy`.
- `catalog_base_from_path` yields to a declared listing rather than deriving a base nobody serves,
  and a *service* listing's cards link to `/book` instead of a `/services/:id` a booking funnel
  never declares.

## Generated data has whatever shape the business needed

Four separate defects, one lesson. The ops `table` slot asserted `row.name`, `row.owner` and a
`row.updated` that exists in no shape at all — the same line, nine TS2339s, three pages.
`seed.artworks.find(…)` defaulted the key to a *string* because `find` was missing from the
array-method list. The stock `AdminDashboardPage` read `stats.map` on an export the AI owns. And
`_brand_has_top_key` matched only unquoted keys while `assemble.py` writes brand with `json.dumps`,
so the gap-fill appended a second `name` and a second `tagline` — and the `tagline` it invented was
`{}`, which `PublicLayout` handed to React as a child.

## The template must be at least as wide as the model

`PageHeader` action variants, `AiFeatureStage`'s demo record, `MarketingHero`'s overlay children,
`FilterBar`'s `{ label, render }` dropdown filter, `Dialog`'s optional children. Each was a real
page failing on a prop a careful developer would have written.

## A page must be the page it says it is

A **sign-in** page is a credentials form; `login`/`sign-in`/`register` are now their own `auth`
workspace type rather than sharing `account`'s card grid. A **contact** page is a form, not a grid of
links (`contact`, session 3 earlier). Both were found by the visual critic scoring the page 20 and
saying exactly what was wrong.

## An image that fails to load is not a hole in the page

`ui/lib/KitImage.tsx` degrades to the brand gradient on a load error; all twelve `<img>`s in the
public kit go through it. Every one already had a fallback for a missing `src` and none for a `src`
that does not resolve, so one dead Pexels URL left a grey rectangle in request 45's gallery.

## A page must be shaped for what it does

`public-catalog` gained a `filters` slot, ordered before `showcase` in the skeleton and in all six
recipe orders. Request 47's gallery put its search box *below* the grid and wrote `-mt-24` trying to
drag it up: the affordance was missing, not misused. A recipe order owns the page face and drops
slots it does not list, so a `filters` missing from one order is a filter bar that vanishes — hence
the test that walks every recipe.

## An item photograph is of the thing being sold

The item pool reads Pexels' own `alt` text and ranks a photograph of a person or an empty prop last —
ranking, not filtering, because returning fewer than eight pictures reintroduces the repeated-photo
defect. `_CATEGORY_ITEM_HINT` names the artifact per category, since `_CATEGORY_QUERY_HINT` names the
*environment* and "art gallery painting studio" is how an artist at an easel reached the grid. "on
plain background" is gone from the framing: it asked for product mockups.

## Time is a resource the pipeline can waste

- A stalled call now has a **wall clock**, not just a socket timeout. `requests`' `timeout=` resets
  on every byte, so request 45 held one repair call open for 1040 s before it returned truncated
  output — heartbeating "still waiting" the whole way. An attempt gets 2.5× its socket timeout, then
  `cancel_inflight` closes the socket under it.
- A fix model that has already failed this process is not paid for again (`_FAILED_FIX_MODELS`).

## Honest reporting

`refine_file` records what it actually did: request 40 logged `refined 2 page(s)` for two pages it
had returned untouched, both of which then failed the build. `assemble.py` stops minting
`parent/:id` under an already-parameterised parent (`/admin/artworks/:id/:id` bound one name twice).

## Damage containment, when a cause cannot be removed

The gate's AI repair is a model, and models write bad patches. Three layers now bound what one can
cost: a plan is **all or nothing** (a refused op restores the workspace, because a plan's ops are
written against each other), a **failed rebuild rolls the repair back** (so the gate can never judge
source `dist/` was not built from), and every writer **checks that its output parses**. None of these
make the repair better; they stop a bad one from reaching a demo.

## Tests

`backend/tests/preview_app/test_request_40_defects.py` (~85 cases) covers every fix above, each named
for the defect it prevents and documenting the run that shipped it. Notable ones that pin *sets*
rather than single behaviours:

- `test_every_ai_writer_checks_that_its_output_parses` — all four writers, one place.
- `test_every_catalog_recipe_orders_the_controls_before_the_grid` — walks all six recipes.
- `test_a_shell_cannot_be_crashed_by_the_data_it_is_handed` — the crashes that take a whole page.
- `test_a_stub_never_displaces_content_the_page_already_had` — the lesson above, executable.

`backend/tests/infrastructure/ai_providers/test_retry_wall_clock.py` covers the wall-clock deadline.
`docs/KNOWN_TEST_FAILURES.md` is empty and should stay that way.
