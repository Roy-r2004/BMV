# Journey contract + BMV Core capability seam — implementation plan

Written and executed 2026-07-29 (session 3). **All phases landed**; see
[Outcome](#outcome) for what shipped, what it found, and what is still open.
Companion to
[PREVIEW_QUALITY_FINDINGS.md](PREVIEW_QUALITY_FINDINGS.md) (why the pipeline
shipped bad output) and [KNOWN_TEST_FAILURES.md](KNOWN_TEST_FAILURES.md).

## The problem in one line

Every check in the pipeline validates a page **in isolation**; nothing validates
the **path between pages**. So a generated site can pass every gate while the
visitor cannot browse a collection, open an item, or ask about it.

Evidence gathered before writing any code:

| finding | location |
|---|---|
| Browse page rendered 3 of N items | `ProductShowcase` destructures `[featured, secondary, tertiary]` |
| Card links optional and unenforced | `ProductShowcaseItem.href?` |
| Detail CTA "Inquire about this piece" → `/about`, a route that does not exist | `scaffold.py:231` |
| Storefront listing CTA "Inquire" → `/about` | `scaffold.py` directory listing |
| Nav derived from all routes then truncated at 8 | `assemble.py:373`, `quality_gate.py:219` (`nav_clutter`) |
| No detail-param contract anywhere | `useParams` appears only in an allow-list |
| Only link validator in the gate is AI-hub scoped | `dead_ai_step_link` |
| `public-catalog` absent from all 6 recipes | `design_recipes.py` — **fixed**, see Outcome |

## Decisions taken (owner: rr@phoeniciancapital.com)

1. **Mock-backed now, real seam later.** Capabilities render and validate against
   seeded data behind an interface a real backend can slot into. No persistence,
   tenancy, or auth in this pass.
2. **`CatalogGrid`** as a new component rather than making `ProductShowcase`
   variadic — the editorial 8/4 mosaic is deliberate for home pages and every
   generated app inherits changes to it.
3. **Gate severity: BLOCK public, WARN ops.** Mirrors
   `asset_integrity.blocking_missing_assets()`'s `public_surface` policy. The
   report is **re-derived after heal** so a repaired page can clear it — the trap
   in P0-3, where a persisted BLOCK could never be cleared.
4. **Nav derives from the declared journey spine**, replacing all-routes →
   dedup → cap-at-8.
5. **Commit in focused chunks on `chore/remove-preview-generator-v2`, push that
   branch.** No PR, `main` untouched. Pushing this branch does not deploy; only
   `main` does (Coolify, see `DEPLOY.md`).

## Phases

### A — Capability registry (the BMV Core seam)
Generalise the anatomy the AI-features subsystem already proves works
(declares → classify → place → require surface → verify in workspace → gate) into
a registry any capability plugs into.

- `capabilities/registry.py`: `inquiry`, `booking` implemented; `chatbot`
  declared but not implemented, so the shape is exercised by more than one case.
- Each entry: required slot, component, journey role, gate codes, submit seam.
- Packs may declare `"capabilities": [...]`; product kind supplies the default.

### B — Journey spec + walker
- `journey.py`: one declared journey per product kind.
  - `storefront`: browse (`/gallery`) → detail (`/gallery/:id`) → inquire
  - `booking_service`: browse (`/services`) → detail → book → confirm
- `walk_journey(workspace, architect)` returns a hop result per edge, checking:
  1. the browse page renders a listing component,
  2. every item link resolves to a **declared** route,
  3. the detail page reads its route param,
  4. a terminal action slot exists.

### C — Detail page resolves its param
Scaffold emits `useParams()`, an item lookup against the seed, a specs block
(`CredentialStrip`, which already takes `{title, detail}`), a graceful not-found
state linking back to the browse page, and passes `itemTitle`/`itemId` into
`InquiryPanel` so the inquiry names the piece.

### D — Booking journey
`ScheduleRail` hardcodes `href = item.href || '/classes/${item.id}'` and
`/waitlist-confirmation` — neither route is in the booking blueprint, so both are
dead links. Give it a `detailBase` like `CatalogGrid` and wire
services → book → confirm.

### E — Nav from the journey spine
`assemble.py` ranks nav by the spine; secondary routes stay reachable by link but
leave the chrome. Note: the *ranking* is journey-driven now, but `nav_clutter`'s
cap remains as a backstop — it was not removed.

### F — Barber pack + vertical audit
A barbershop currently resolves to `spa-wellness-home`, and a barbershop is not a
spa. Add `barber-grooming-home`, and check the verticals named in the brief
(stores, ecom, galleries, barbers) plus the mis-bucketing cases already found
(auto repair, law firm, commercial cleaning, fashion retail).

### G — Codegen prompts
The deterministic scaffold is only the fallback. Prompts must tell the model to
use `CatalogGrid` on a catalogue page and `InquiryPanel` on a detail page, or the
AI path will keep choosing `ProductShowcase`.

### H — Tests, mutation-proven
Every mechanism disabled in turn must kill exactly the test that guards it, per
this branch's standing discipline.

## Standing constraints honoured

- `main` / `origin/main` stay at `66902f0`. No force-push, no amend.
- `.env*` gitignore rules untouched.
- Test command (both documented ones report phantom failures):
  ```bash
  docker run --rm -v "$PWD:/repo" -w /repo/backend \
    -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template \
    --entrypoint sh bmv-local-api \
    -c 'pip install -q pytest; python -m pytest tests/ -q'
  ```
- Baseline entering this work: **863 passed, 1 failed** (the documented
  `test_appspec_v2_policy` fixture failure).

---

# Outcome

**Suite: 897 passed, 1 failed** (the documented `test_appspec_v2_policy` fixture
failure). Entering this work it was 863/1, so 34 tests were added and none broken.

## Verified by rendering, not by assertion alone

A throwaway app was built from the template with nine catalogue items, served,
and its post-JS DOM inspected:

| surface | before | after |
|---|---|---|
| `/gallery` | 3 cards rendered, rest unreachable | **9** cards, each linking to a distinct `/gallery/:id`, filters auto-derived (`All · Originals · Studies · Prints`) |
| `/gallery/5` | generic content for every id | headline **"Marsh Study I"**, specs strip, inquiry addressed to that piece |
| `/gallery/999` | generic content | visible not-found state linking back to the collection |
| inquire CTA | `/about` — a route the storefront does not have | `#inquire`, the anchor `InquiryPanel` renders on that page |

## Defects the work uncovered

All of these were in the generator, not model output:

1. `ProductShowcase` destructures `[featured, secondary, tertiary]` — the browse
   page silently rendered 3 of N items.
2. The detail CTA read *"Inquire about this piece"* and linked to `/about`. A test
   pinned the label and never the destination, so it passed throughout.
3. The storefront listing CTA `"Inquire"` → `/about`, same dead route.
4. `ScheduleRail` fell back to `/classes/${id}` and sent full rows to
   `/waitlist-confirmation` — neither is in the booking route table.
5. The schedule scaffold's hero CTA pointed at `#schedule-list` while
   `ScheduleRail` renders `id="classes-list"` — a dead anchor.
6. That scaffold's CTA band pointed at `/contact`, which no booking blueprint
   declares.
7. `_non_home_hero_ctas` decided "storefrontish" from **brand words**, so a
   gallery-flavoured brand on a `public-booking` page emitted a `/gallery` CTA.
   The skeleton now outranks the brand.
8. Three verticals resolved to **no pack at all**: barbershop, hair salon
   (`spa-wellness-home` has `salon`, but a lone 5-character token fails the
   6-character distinctiveness gate), and independent bookshop.
9. Four gate/validator sites hardcoded `"ProductShowcase" in src` for the listing
   face — with the scaffold emitting `CatalogGrid` the gate would have rejected
   its own output and healed in a loop.
10. Adding both new components to `PUBLIC_ALLOWED` pushed every public skeleton's
    codegen contract past its 5000-char budget, silently starving `public-detail`
    and `public-home` of the prop shapes that keep cards from rendering empty.
    They are now scoped to the skeletons that use them.

## Design decisions worth keeping

- **Links are structural.** `CatalogGrid` derives each card's link from
  `detailBase + item.id`, so codegen cannot emit a non-clickable card. The old
  `ProductShowcaseItem.href?` was optional and silently produced dead cards.
- **The contract is true by construction.** `_ensure_terminal_action_slot`
  injects the `inquire` slot when a detail route has no terminal action, so
  `#inquire` is never anchored to nothing — rather than weakening the CTA when the
  slot happens to be missing.
- **The walk is recomputed, never persisted.** `evaluate_quality_gate` is called
  again after heal, so a repaired page clears its own finding. This is exactly the
  trap P0-3 describes, avoided structurally.
- **Advisory findings exist so the WARN path is real.** An off-funnel dead-link
  sweep covers ops/owner pages without letting one withhold a public storefront.
  Without it the ops-severity branch would have been unreachable dead code — the
  same computed-never-read shape this whole effort is about.

## Still open

1. **Not demonstrated in a live generation.** Everything above is verified through
   the deterministic scaffold and a hand-built app. A real end-to-end run (with
   the AI codegen path, not the fallback) has not happened — the prompts now carry
   the journey rules but no generated output has been inspected against them.
2. **`catalogue.json` has no generator.** `registry.ts` says
   `npm run sync:ui`, but that script was deliberately removed when the template
   was slimmed (`sync-ui-catalogue` is in `test_scaffold_pruned.py`'s forbidden
   list). The two files are hand-synced and can drift silently. Either restore a
   generator or add a drift test.
3. **QA harness screenshots only capture the hero.** Every attempt to screenshot
   below the fold returned the hero, because public heroes are viewport-height and
   the sections below use scroll-triggered reveals. `scripts/preview-qa.sh` cannot
   currently see a broken catalogue grid, so "look at the screenshots" has a blind
   spot. A scrolling capture (CDP `captureBeyondViewport`) would close it.
4. **The imagery bucket for a barbershop is `generic`.** Harmless now that the
   brief's prose leads the query and the pack supplies barbershop framings, but
   `_CATEGORY_QUERY_HINT` has no grooming bucket.
5. **P0-2, P0-3, P0-4, P0-5 in the previous handoff are untouched.** All four are
   in `visual_critic.py`. P0-3 and P0-5 still compound into permanently
   withholding a correct preview.
6. **Real persistence.** `InquiryPanel.onSubmit` / `BookingPanel` are seams, not
   implementations. Booking is where correctness bites (availability,
   double-booking, notifications) and it needs tenancy and auth first.
