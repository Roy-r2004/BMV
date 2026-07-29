# Journey contract + BMV Core capability seam — implementation plan

Written 2026-07-29 (session 3), executed in the same session. Status markers are
updated as each phase lands. Companion to
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
| `public-catalog` absent from all 6 recipes | `design_recipes.py` |

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
`assemble.py` builds nav from the spine; secondary routes stay reachable by link
but leave the chrome. `nav_clutter`'s truncation is replaced.

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
