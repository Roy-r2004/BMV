# Measurements that were never read, and never retaken

Written and executed 2026-07-30 (session 4). Closes the four items left open at
the end of [PREVIEW_JOURNEY_IMPLEMENTATION.md](PREVIEW_JOURNEY_IMPLEMENTATION.md)
— P0-2 through P0-5 from [HANDOFF.md](../HANDOFF.md), the `catalogue.json` drift
gap, and the QA screenshot blind spot.

## The thread

Every item here is the same shape as the one the journey work was about, one level
up. The journey work found *checks that validated a page in isolation while nothing
validated the path between pages*. This session found **measurements the pipeline
takes correctly and then does not act on**:

| item | the measurement | what happened to it |
|---|---|---|
| P0-5 | `classify_industry_family` returns a confidence margin | bound to a local, used only inside the f-string message |
| P0-4 | `_route_surface` knows a page is owner-only | never consulted for `broken_rendered_image` |
| P0-3 | the visual report | written once pre-refine, never re-derived |
| P0-2 | `reviewed` / `unmeasured` / `measurement_failed` | zero production readers |
| drift | `registry.ts` declares itself canonical | nothing compared it to the generated file |
| shots | `full_page=True` was already set | the page below the fold was at `opacity: 0` |

A measurement with no reader is indistinguishable from one that was never taken.
Four of the six could withhold a working preview; two could ship an unexamined one.

---

## P0-5 — margins computed, never read

`check_imagery_industry_consistency` bound `business_margin` and `imagery_margin`
and no threshold read either, so a 3-2 keyword win counted as confident — and this
finding is a **BLOCK**.

Reproduced through the real pack picker, not a hand-written query:
`industry="spa and wellness clinic"` resolves to `spa-wellness-home`, whose
queries classify `beauty` while the brief reads `health`. The pipeline BLOCKed
imagery it had itself selected as on-industry. A med-spa brief did it on a margin
of 1.

Two guards, both narrow on purpose:

- `_MIN_CONFIDENT_MARGIN = 2`, required on **both** sides.
- `_ADJACENT_FAMILY_PAIRS` — families whose signal words genuinely overlap. Each
  pair carries the overlap that earns it a place, because "these feel related" is
  not a reason and this table is the detector's main way of going quiet.
  `"vet clinic"` contains `clinic`; `catering` is literally inside
  `catering hall`; `grooming` reads as either a dog or a beard.

**Deliberately not transitively closed.** `health~beauty` and `beauty~fitness` are
both real; chaining them gives `health~fitness~education~art` and the detector
never fires again. Membership is exact-pair only, and a test asserts it.

The app-36 case that justifies the whole detector — an art gallery with dental
photography — still fires through both guards: `art` vs `health`, both sides
confident, not adjacent.

## P0-4 — the surface was known and not asked

`broken_rendered_image` used `add`'s BLOCK default with no surface check, while
the gate deliberately filters the sibling `missing_image_asset` for exactly this
reason and route selection now goes *out of its way* to screenshot an ops route.
One owner-only broken thumbnail withheld the entire public storefront — and
because the finding comes from the browser probe rather than the model, it did
that even on a `pass` verdict at score 90.

Now BLOCK on public, WARN on ops, mirroring
`asset_integrity.blocking_missing_assets()`. A declared `surface` on the route
outranks the path guess; absent one it is inferred from the component path.

This reconciles two tests that encoded **opposite policies for the same defect on
the same kind of page**: `test_visual_report_reaches_gate.py` asserted an admin
page must not fail the gate, `test_visual_feedback_loop.py` asserted it must. The
ops case now asserts WARN; a new public case carries the BLOCK.

## P0-3 — the one BLOCK source that was never re-derived

`_bmv_visual_critique.json` was written pre-refine and, on the refine *success*
path, persisted unchanged. So: vision scores `/gallery` 30 → BLOCK recorded →
`refine_file` rewrites the page → guards and build succeed → the page is now fine
→ the stale BLOCK still fails the gate → `viewable=False`, `url=None`,
`status="failed"`, with a good `dist/` on disk.

Took the correct fix rather than the cheap one:

- `_forget_pages` drops every measurement recorded for a rewritten page —
  findings, `reviewed`, `unmeasured`, `scores`.
- those pages are then re-screenshotted and re-critiqued before anyone reads the
  verdict.
- re-measurement that itself fails records `unmeasured`, **not** a pass and not the
  old BLOCK. After a rewrite we genuinely no longer know. The cheap fix — "ignore
  BLOCKs for paths in `report.refined`" — would have called that page fine.
- imagery findings are recomputed wholesale: they are deterministic and free, and a
  rewritten page can introduce a broken local reference or repair the one that was
  found.

A test distinguishes *cleared* from *re-measured* by asserting the surviving
finding quotes the **second** review, not the first.

## P0-2 — a vision outage reported full coverage

A total outage lands every page in `unmeasured` at WARN → `report.blocking == []`
→ the gate passes → `status: "ready"` with zero pages judged. The progress feed
said `Visually reviewed 6/6`, because the emit ran *before* the exception check.
`measurement_failed` carried a docstring telling callers to check it and had no
production reader at all.

- `visual_review_summary()` puts `visual_review_status`,
  `visual_pages_reviewed`, `visual_pages_unmeasured` and `visual_pages_selected`
  on the pipeline result, the way `_typecheck_summary` already carries type errors.
  `run_finalize` logs and emits when it reports "ready" beside `unmeasured`.

  **Where to read them.** They land in `Request.generated_pages` and the progress
  feed. They deliberately do *not* reach `GET /requests/{id}/preview`:
  `CustomerPreviewApp` is an `extra="forbid"` allowlist exposing `url` alone —
  *"never accepts internal preview metadata."* That is the right boundary, and it
  means "surface into the API result" means the internal result, not the customer
  projection. Worth knowing before looking for the fields in the wrong response.
- `routes_selected` on the report, so *measured nothing* is distinguishable from
  *had nothing to measure*. Reports written before the field existed fall back to
  `len(reviewed) + len(unmeasured)` rather than to 0, which would read a real
  outage as `no_routes`.
- the emit moved after the exception check; the counter only advances on a page
  that was judged, and a failure gets its own visible line.
- `PREVIEW_VISUAL_CRITIC_BLOCK_ON_UNMEASURED` is a real `Settings` field with a
  documented default. It previously appeared **exactly once in the repo** — at the
  line that read it — so it was off everywhere by accident rather than by decision.

### The one judgement call worth flagging

The handoff asked that `"ready"` not be *reportable* when nothing was measured.
`status` keeps its `ready | failed | rebuilding` vocabulary anyway: four
production readers and the frontend poller branch on it, and — more to the point
— withholding a working preview because our vision vendor 429'd is the same
pathology as P0-3 and P0-5. A vision outage is **our** measurement failing, not a
defect in the generated app.

So the honesty lives in the field beside it: `status: "ready"` can no longer be
read on its own as "reviewed", and an operator who would rather ship nothing than
ship unreviewed now has a switch that works.

---

## `catalogue.json` had no generator — and had already drifted

`registry.ts` says *"catalogue.json is generated from this file via
`npm run sync:ui`. Do not hand-edit catalogue.json."* That script was removed when
the template was slimmed, and `sync-ui-catalogue` sits in
`test_scaffold_pruned.py`'s forbidden substrings, so restoring it in the template
fails a test **on purpose**.

**There was already drift, and it was ours.** `CatalogGrid` and `InquiryPanel` —
added last session — were in `catalogue.json` and `index.ts` but never in
`registry.ts`'s `CATALOGUE_COMPONENTS`, so the template's own
`getCatalogueComponentNames()` did not list two components its skeletons allow.
Drift inside one session of the file being marked hand-synced.

Which direction each break goes:

- **only in `registry.ts`** — invisible to every prompt, validator and skeleton
  contract, because `load_catalogue()` reads the JSON.
- **only in `catalogue.json`** — offered to the model, then fails to import.

The generator lives in `app/application/ui_registry.py`, on the side that consumes
the artifact, reusing the TS parsing primitives `ui_catalogue.py` already has:

```bash
python -m app.application.ui_registry            # report drift
python -m app.application.ui_registry --write    # regenerate
```

It parses exactly the subset `registry.ts` uses and **raises** on anything else —
a spread into an object literal, a shorthand property, a function call — rather
than skipping the member. A skipped member drops every field it carries and then
reports the difference as drift in the JSON, inviting a "fix" that deletes real
data. That bug was live in the first draft (splitting members on newlines as well
as commas lost `purpose:` for six skeletons) and has its own test.

`test_the_generator_round_trips_the_file_byte_for_byte` keeps `--write` a no-op
diff instead of a 1600-line reformat. The drift test also checks the third file in
the triangle: every catalogued component is exported from `@/ui`, its source file
exists, and no skeleton allows a component the catalogue does not list.

## The screenshots were of the hero — in the harness *and* in production

Two independent causes. Fixing either alone leaves the blind spot.

**Height.** `preview-qa.sh` drove host Chrome with `--screenshot
--window-size=1440,2000`, which captures the viewport only. Public heroes are
viewport-height, so every route's screenshot was that route's hero: the harness
structurally could not see a broken catalogue grid, the exact defect it exists to
catch.

**Visibility — and this one hit production too.** `observeSectionReveal` sets
`opacity: 0` and only animates to 1 when an IntersectionObserver fires. Nothing
below the first viewport had ever been intersected, so even `full_page=True` —
which `capture_route_visual` **already used** — produced a hero over a column of
blank space. The vision critic has been scoring pages whose below-fold sections
were invisible, and could flag a section that renders perfectly for a real visitor.

`reduced_motion="reduce"` is the fix: both reveal paths (`observeSectionReveal`,
`AnimeStagger`) check `prefersReducedMotion()` and leave content visible when it
matches. `prime_scroll_reveals` walks the page by viewport steps and returns to the
top as a backstop for a component that forgets to check, and degrades to capturing
unprimed rather than losing the shot.

Proven by rendering app 37's `/gallery` three ways:

| capture | what it showed |
|---|---|
| viewport only (the old harness) | the hero, nothing else |
| full page, unprimed (production until now) | the cards, but a **completely blank CTA band** |
| full page + reduced motion + prime | the whole page, CTA band included |

The harness also stops guessing routes. It read a hardcoded list of five names,
three of which did not exist on the app it was pointed at, and never visited a
detail page at all. It now reads the route table out of the app's own `App.tsx`
and substitutes `QA_DETAIL_ID` (default 1) for `:param` segments, so
`/gallery/:id` — the point of the journey contract — is actually captured. 14
routes on app 37 against the 5 guessed names before. `QA_LEGACY_CHROME=1` keeps
the old path, labelled `VIEWPORT ONLY`.

Playwright is already in the api image, so `full_page` (CDP's
`captureBeyondViewport`) needs no WebSocket client in `sh` and no host-Chrome
dependency. PNGs come back base64 on stdout, so no shared volume either.

---

## Verification

Suite: **946 passed, 1 failed** — the failure is the documented
`test_appspec_v2_policy` fixture, unchanged. Entering this session it was 897/1,
so 49 tests added and none broken. The preview template typechecks clean after the
`registry.ts` edit.

Every mechanism is mutation-proven — disabled in turn, each kills exactly the test
that guards it. Two of them did **not**, on the first attempt, and both tests were
too weak rather than the code being unguarded:

- the P0-5 margin gate: my case used a brief with one keyword hit, which
  `_MIN_SIGNAL_HITS` already rejected, so the margin never came into it. Replaced
  with a brief that scores retail 3 / food 2 — a real margin of 1, past every
  other guard.
- the finalize wiring: the test called `_visual_review_summary` directly, proving
  the helper works and nothing about whether anything calls it — which is the exact
  defect P0-2 *is*. Now goes through `run_finalize`.

A third was weak in the same way: `page.evaluated` being non-empty was satisfied by
the broken-image probe's own `evaluate`, so the scroll prime could be deleted with
nothing failing. The fake page now keeps an ordered event log and the test asserts
the prime happened *before* the shot.

## Still open

Carried from the previous session, untouched here:

1. **The imagery bucket for a barbershop is `generic`.** Harmless now that the
   brief's prose leads the query and the pack supplies barbershop framings, but
   `_CATEGORY_QUERY_HINT` has no grooming bucket.
2. **Real persistence.** `InquiryPanel.onSubmit` / `BookingPanel` are seams, not
   implementations. Booking is where correctness bites (availability,
   double-booking, notifications) and it needs tenancy and auth first.

New, found while doing the above:

3. **`visual_defect_severe` is still surface-blind.** P0-4 fixed
   `broken_rendered_image` because that is what it named, but an ops page scoring
   20 still BLOCKs the public storefront through the same
   one-page-withholds-everything shape. Deliberately left alone rather than widened
   silently — a garbage admin page *is* a real defect, so the right policy needs a
   decision, not a patch.
4. **`nav_clutter`'s cap-at-8 backstop is still there** behind the journey-driven
   ranking, as noted last session.
