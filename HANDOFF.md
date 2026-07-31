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

The progression is the point. 40's defects were invisible. 43's and 44's were the *gate* being
wrong — visible, and therefore fixable. By 45 the instruments were sound enough that the pipeline's
own critic found three real product defects and described each one accurately. That is the
difference the session bought.

**17 commits** on `chore/remove-preview-generator-v2` (`31afda1`…`69ebba2`),
**suite 1047 passed / 0 failed**, `docs/KNOWN_TEST_FAILURES.md` empty.

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

1. **No clean `status=ready` run yet.** 43, 44 and 45 each failed on a *different* defect of ours,
   every one now fixed. The next run is the first to carry the whole set.
2. **Type errors are 15–24 per run before repair.** Session 3 cut the deterministic contributors
   (below); what remains is mostly the model inventing props on ops pages. Note that request 44's
   *shipped* count was only 5, four of them ours — the pre-repair number is the one to watch.
3. **The refine critic scores four pages 0–60 and skips them** (`refine SKIPPED … left as-is`).
   Honest, but it means those pages ship at their scaffold quality. Request 45's login page was one
   of them, and it was genuinely unusable.
4. **The gate's AI repair broke the build twice on request 45** ("rebuild after AI repair failed"),
   so both attempts rolled back, and one repair response was unparseable JSON. The repair loop is
   the weakest remaining link: it is asked to fix visual findings, which it is not well suited to.
5. **The home page hero is a stock photo of someone painting** (scored 65, a warn). The item grid now
   ranks people last; the *hero* deliberately does not, because for many businesses a person in the
   hero is right. For a portfolio it probably is not. Unresolved judgement call.

## Next steps, in order

1. **Read request 46 end to end** — it is the first run carrying every fix. Check `journey_hops_ok`,
   `visual_review_status`, `render_pages_checked/crashed`, the tsc count, and every screenshot. The
   gallery grid is the page to look at first: it is the one that has to say "wow".
2. **The gate's AI repair loop** (item 4 above). A visual finding — "this page is off-brief" — is
   not a patch instruction. Either give it the screenshot, or route visual findings to the composer
   that owns the page rather than to a generic repair prompt.
3. **The residual type errors** (item 2) are worth one focused pass now the deterministic ones are
   gone.
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

## Tests

`backend/tests/preview_app/test_request_40_defects.py` (~58 cases) covers every fix above, each named
for the defect it prevents and documenting the run that shipped it.
`backend/tests/infrastructure/ai_providers/test_retry_wall_clock.py` covers the deadline.
`docs/KNOWN_TEST_FAILURES.md` is empty and should stay that way.
