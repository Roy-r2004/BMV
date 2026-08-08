# Kickoff — remove hardcoded route references (2a → 2b → 2c → verification trio)

You are continuing work on `main` (at or after `6ec0375`). Do the four steps **in
order**; each has a gate you must pass before starting the next. Do not reorder,
do not merge steps into one commit.

## Context you need (read, don't re-derive)

Session 26 ran six new businesses through the pipeline and shipped 1 of 6. Root
causes were found and two are already fixed on `main`:

- `37f054c` — journey href lexer masked `${…}` before splitting (146/148 false
  positives, `tests/preview_app/test_href_template_shapes.py`).
- `6ec0375` — one schedule-face rule for generator/gate/repair
  (147/148/150 false positives, `tests/preview_app/test_schedule_face_agreement.py`).

What remains is the third root cause: **the scaffold writes route literals
(`/book`, `/gallery`) into pages whose architect named those routes differently**
(148: `/service/book`, 150: `/hire/reserve`, `/bikes`, `/catalogue`). The route
table already carries the answer semantically: exactly one route per app has
`skeleton_id == "public-booking"` and at most one `"public-catalog"` — verified
across requests 146–151. Resolve by skeleton, never by name. Do **not** instead
normalise the architect's names to `/book`/`/gallery`: the naming freedom is
wanted (Phase 3 is about outputs differing); the bug is only that the emitters
don't read the table.

The rule being enforced: *a route literal may define a route or describe a path
shape; it may never reference one.* `product_kind.py` blueprints and
`_is_ops_path`/`_LISTING_BASE_RE` vocabularies are definitions/descriptions —
leave them alone. Only emitted hrefs change.

Line numbers below are as of `6ec0375` — anchor by function name if they drift.

## Harness facts (violating these wasted time in session 27)

- **Tests**: use the exact invocation in `docs/KNOWN_TEST_FAILURES.md` —
  `docker run --rm -v "$PWD:/repo" -w /repo/backend -e
  PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh
  bmv-local-api -c 'pip install -q pytest; python -m pytest tests/ -q'`.
  Plain `docker run` without `--entrypoint sh` hangs; `docker compose exec api`
  fakes failures. Suite baseline on `main`: **2,103 passed / 1 skipped / 0 failed**.
- **Every fix gets a mutation sweep.** Session-26/27 lesson, twice over: first
  sweeps found survivors and every survivor was a *fixture* defect — the fixture
  lacked the shape that distinguishes fix from bug. Fixtures must carry the
  hostile shape and say in the docstring which mutation they kill.
- **Offline replay of the journey walker over stored workspaces does not work**:
  `product_kind` and `industry_template_id` are not persisted in
  `generated_pages`, so the walker sees zero hops on archived records. Don't
  spend time on it; the trio is the end-to-end check.
- The real route records for 146–151 are in Postgres
  (`docker exec bmv-db psql -U bmv -d buildmyversion`, column
  `requests.generated_pages`, key `preview_app.routes`). Use them as test
  fixtures — they are the ground truth this work is verified against.

---

## Step 2a — booking route resolved from the route table

**Change** (in `backend/app/application/preview_app/catalogue_contract/scaffold.py`
unless noted):

1. Add `booking_route(architect) -> str | None`: the declared route whose
   `skeleton_id == "public-booking"` (surface not ops). Returns `None` when the
   app has none (request 151 is real: an ops console, no booking page).
2. Thread `architect` to the emitters that lack it:
   `_safe_slot_jsx` → `_non_home_hero_ctas` (callers: 2 in scaffold ~L1624/1641,
   2 in `catalogue_contract/repair.py` ~L370/402), and add it to
   `_schedule_listing_scaffold` (1 caller, dispatcher, architect in scope).
   `_directory_listing_scaffold` already has it.
3. Replace the six `/book` emit sites: `_non_home_hero_ctas` (2), 
   `_schedule_listing_scaffold` (`book_js`), `_directory_listing_scaffold` (3,
   incl. `_BOOKING_ROUTE` at ~L1411).
4. **Fallback**: resolver returns `None` → the CTA becomes
   `{ label: "Send a message", href: "#inquire" }` (the contact-branch pattern
   already in `_non_home_hero_ctas`). A missing button beats a dead one. Never
   emit `/book` on an app that doesn't declare it.
5. **The trap that would undo the fix**: `safety/mock_data.py::sync_mock_images`
   rewrites dead booking CTAs to the *literal* `"/book"` at two sites (~L957,
   L991). On a `/hire/reserve` app the safety net re-manufactures the dead link.
   Thread the resolved route in (or the architect) and rewrite to it.
6. While in `_non_home_hero_ctas` with architect available: resolve the
   `"View collection", href: "/gallery"` CTA (~L415) via `catalog_base_from_path`
   / the declared `public-catalog` route. It's the same function — folding it
   here avoids touching it twice.

**Tests** (new module, e.g. `tests/preview_app/test_booking_route_resolution.py`):

- 148's real routes → CTA hrefs are `/service/book`; 150's → `/hire/reserve`.
- 151's real routes (no `public-booking`) → **no** booking href anywhere in the
  emitted TSX; the `#inquire` fallback is present.
- **147 is the free control**: its architect chose `/book`, so emitted TSX for
  its routes must be *identical* before/after. Snapshot main's output first.
- `sync_mock_images` on a `/hire/reserve` app rewrites `/book-appointment` →
  `/hire/reserve`, not `/book`.
- Mutation sweep: resolver stubbed to constant `"/book"`, fallback deleted,
  skeleton match replaced by path match — all must die. 0 survivors.

**Gate**: full suite green (expect +N for your tests, plus 1 per new test file —
`test_every_test_file_is_collected` auto-parametrizes). Commit. Then start 2b.

## Step 2b — catalogue base + the lint

**Change**:

1. The `products` and `showcase` slots in `_safe_slot_jsx` (~L689, L699) emit
   `` `/gallery/${…}` `` while `catalog_detail_base` — already derived, already
   in scope, used correctly by the adjacent `catalog` slot — sits unused six
   lines up. Point both slots at it. **2 lines.**
2. `repair.py`'s two `_safe_slot_jsx` calls don't pass `detail_base`, so
   repaired pages get the `/gallery` default. Pass the derived base (via
   `catalog_base_from_path(route_path, architect)`).
3. **The lint that keeps the count at zero**: a test that scans `scaffold.py`
   (at minimum; ideally the emitters in `utility_compositor.py` too) for route
   literals in emitted-href position, allowlisting only `/` and `#…` anchors.
   The census pattern:
   `href["']?\s*[:=]\s*\{?\s*["'\`](/[^"'\`\s]*)`. Known remaining references
   it must either allowlist-with-a-comment or you fix while there: `/contact`,
   `/checkout`, `/order-tracking`, `/invoices`, `/ticket`, `/ai-features`
   (`/ai-features` is genuinely guaranteed by `assemble.py` — assert, don't
   derive). Prefer a small explicit allowlist with justifications over a big
   sweep in this step.

**Tests**: 148's routes → card hrefs resolve to `/bikes/:_` and match declared
`/bikes/:id`; art-gallery fixture (use 146's real routes) still emits
`/gallery/…`; repair-path test that a rewritten listing inherits the derived
base. Mutation: revert each slot to the literal — the lint alone must catch it
even if the behavioural tests are deleted.

**Gate**: suite green. Commit. Then 2c.

## Step 2c — journey walker resolves hops by skeleton

The walker is already rename-tolerant *except* in two places
(`backend/app/application/preview_app/capabilities/journey.py`):

1. `_find_route` (~L331): matches exact hint, then **first-segment stem** —
   `/hire/reserve` shares no stem with hint `/book`, so 150's terminal hop
   resolves to nothing. Add a skeleton preference *before* stem matching:
   terminal/book hop → `public-booking`; browse hop → `public-catalog` (then
   existing behaviour as fallback for thin contracts with no skeleton_ids).
2. The terminal next-hop check (~L1009): `target = _norm(next_hop.path_hint)`
   compares the literal `/book` against declared routes —
   the exact line that produced 150's `journey_next_hop_missing`. Resolve the
   next hop through `_find_route` and use the found route's actual path;
   fall back to the hint only when nothing resolves.

Touch nothing else in the walker. This step has the widest blast radius (every
walk of every app) — keep the diff minimal and alone in its commit.

**Tests**: permutation fixture — one app, booking route renamed across
`/book`, `/reserve`, `/appointments`, `/hire/reserve`, walker verdicts identical
for all four. 150's real routes → no `journey_next_hop_missing`. 146/147's real
routes (corpus-shaped) → verdicts unchanged. Mutation sweep on both changes.

**Gate**: suite green. Commit.

## Step 4 — the verification trio

Only after 2a–2c are all committed and green.

- **Restart the api container first**: `docker restart bmv-api`. It runs with
  `UVICORN_RELOAD=false` and holds the code loaded at container start — skip
  this and the trio measures the pre-fix pipeline (session 26 proved it).
  Confirm after restart that the running process has the fix (e.g.
  `docker exec bmv-api python -c "from app.application.preview_app.catalogue_contract.scaffold import booking_route"`).
- **Composition**: one trio, three briefs, rerun from
  `docs/evidence/session26/launch_trio.py` — take **Kestrel & Fern Bakehouse**
  (trio 1, plain), **Ridgeline Bike Works** (trio 1, file), **Copperline
  Hardware** (trio 2, plain). That set exercises every fix: href mask (bakery,
  bike), schedule face (bike, hardware), booking route (bike, hardware),
  catalogue base (bike), next-hop (hardware). Simultaneous POSTs (threads, no
  stagger), same as the archived launcher. Do not rerun Halcyon (149) — it fails
  on the AppSpec `state_ids` backfill, untouched by this work.
- **Budget**: ~$3.44 on the key at session end; a run costs ~$0.234, trio
  ≈ $0.70. The key is shared — bracket the run with balance probes
  (before/after), attribute only the delta, no leak alarms.
- **Expected**: 3 of 3 `ready`, wall ≤ 600 s each. Combined with 147 and 151
  from session 26, that makes the honest ship-rate 5 of 6 on unseen businesses.
- **If a run fails**: the failure codes are the finding. Diagnose from
  `requests.generation_log` and the workspace before touching code, and fix the
  pipeline — never the generated preview.
- Record the evidence in `docs/evidence/session27/` (same style as
  `session26/trios-146-151.md`) and update `HANDOFF.md` (move the H1 line —
  the file's own instruction).

## Sequencing rule

If a step's gate fails and the cause isn't yours, stop and check whether it
reproduces on clean `main` before diagnosing your change. If you must stop
mid-sequence, commit what's green, leave the rest un-started, and write the
state into `HANDOFF.md` — a half-threaded architect parameter is worse than an
honest stop after 2a.
