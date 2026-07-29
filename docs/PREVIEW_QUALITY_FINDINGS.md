# Why generated previews looked unfinished — root-cause findings

Investigation date: 2026-07-29. Subject: preview request **36** ("Jeanne Kassab Art", a fine
art gallery), which the pipeline marked `status=ready` with `quality gate PASSED`, and which a
prior handoff recorded as meeting or beating the 8.5/10 reference on every measured axis.

Every one of those measurements was correct. Every one of them was also blind to what the page
actually looked like.

## The one-sentence version

**The pipeline never looks at what it produces.** Every gate is a substring match over
TypeScript source text; the only component that renders pixels is advisory-only and cannot fail
a build; and the compiler that would have caught ~59 contract violations for free was never run.

## What request 36 actually shipped

Verified by rendering it in headless Chrome and running its own bundled `tsc`:

| Symptom | Measured |
|---|---|
| Hero image on a fine-art gallery | A photo of a **dental clinic** |
| "Featured Works" cards, captioned *Crimson Tide*, *Emerald Depths*, *Desert Bloom* | Dentures in surgical gloves; a dentist beside a "Smile" sign; oral surgery |
| All 6 images in `src/data/mock.ts` | Dental clinic stock photography |
| TypeScript errors in the shipped app | **59** |
| Image paths returning HTML instead of an image | **7** |
| Hero headline, subhead, body copy, secondary CTA | White on near-white — unreadable |
| `/works` vs `/gallery` | Byte-identical pages, both in the nav |
| Browser tab title | `Preview App` |
| Laser-clinic JPGs served in every `dist/` | 1.09 MB |
| Dead scaffold copied per generated app | 3.64 MB (89.8% of what is copied) |

## Root cause 1 — a layout choice silently redefined the photography

The imagery was **correct** when first resolved and was then overwritten.

1. `pipeline/appspec_gate.py:150` calls `get_images_for_industry(req.industry, ...)` with no
   `imagery_roles`. This resolves category `art` and produces the hint
   `"art gallery painting studio"`. **`ctx.images` is correct here.**
2. `pipeline/plan_phase.py:166-173` picks an industry pack. `industry_templates/loader.py:79-117`
   scores packs by keyword token overlap, and a **single** token longer than 5 characters is
   enough to win. Every one of `clinic`, `dental`, `dentist`, `medical`, `healthcare`, `doctor`,
   `orthodontics` clears that bar. The scored corpus (`plan_phase.py:61-73`) concatenates the
   industry, business description, main problem, desired outcome, target customers, business name
   and 800 characters of context — mostly model-written prose.
   The brief contained the phrase *"not a booking SaaS or clinic front desk"*. A keyword matcher
   cannot see negation, so the word `clinic` — used to say the opposite — selected a dental pack.
3. Two aggravating defects in the same function: ties sort on **descending template id**, so
   `clinic-dental-home` beat `agency-portfolio-home` at every seed purely on spelling; and
   `art`, `arts`, `creative`, `design`, `studio` and `craft` sit in `_WEAK_INDUSTRY_TOKENS`, so
   art vocabulary could never score at all. No pack contained any art vocabulary.
4. `industry_templates/apply.py:40-51` then joined that pack's `industry_tags` **verbatim** into a
   Pexels search query. The literal query sent was
   `"clinic dental dentist medical healthcare doctor orthodontics product detail close-up"`.
5. `pipeline/plan_phase.py:211-221` overwrote the correct art images with the result. This is the
   single point where correct data became wrong data, and the only call site in the codebase that
   passes `imagery_roles`.

The architectural error: **a pack is a choice about layout and recipe, and it was allowed to
redefine what the photographs depict.** Imagery subject must come from the business; a pack may
contribute framing and composition, never subject.

## Root cause 2 — the model is asked to satisfy a contract it is never shown

`backend/preview-template/src/ui/catalogue.json` is what the backend feeds the model to describe
the component library (loaded at `app/application/ui_catalogue.py:64`). The entire description of
one component was:

```json
{ "name": "CredentialStrip", "surface": "public", "path": "public/CredentialStrip.tsx",
  "requiredProps": ["items"], "optionalProps": ["heading", "className"] }
```

Prop *names*, no prop *types*. The truth is declared as an exported interface in the component
source, and the model never sees it:

```ts
export interface CredentialStripItem { title: string; detail: string; }
```

So the model invented `{ label, value }` — an entirely reasonable guess — and
`CredentialStrip` rendered **four completely empty cards** under the heading "Trusted by art
lovers and interior designers", on four separate pages. It reads `item.title` and `item.detail`,
both `undefined`, and keys its list on `item.title`, so every React key was `undefined` too.

The same failure repeated across the library:

| Component | Model passed | Interface requires |
|---|---|---|
| `CredentialStrip` | `{label, value}` | `{title, detail}` |
| `TestimonialRail` | `{name, initials, text, service}` | `{quote, author}` |
| `MarketingHero` | `children`, omitted `imageSrc` | no `children`; `imageSrc` required |
| `Button` | `target` | no `target` on `ButtonProps` |
| `ActivityFeed` | `name` | no `name` on `ActivityFeedItem` |
| `images` object | `artwork1`…`artwork10` | only `hero, hero2, card1, card2, card3, ambient` |
| `seed` object | `features`, `featuresHeading`, `footer`, `opsHero`, `tableRows`, `activity` | none of these existed |

Downstream, `seed.features` being absent meant `FeatureBento` received `items=[]`, so the heading
"What Jeanne Kassab Art offers" was followed by an empty void and a carousel counter reading
**"Guest path · 01 / 00"**. `images.artwork1..10` being absent meant `<img src={undefined}>`
across the gallery pages.

## Root cause 3 — nothing verified the output

### The quality gate cannot see pixels or assets

`preview_app/quality_gate.py` `evaluate_quality_gate` (L64-244) runs 12 checks. All 12 are
substring or regex matches over TypeScript source, plus exactly one filesystem check
(`dist/index.html` exists, L73-74). There is no `<img`, `src=`, `.jpg`, `.png` or `public/` logic
anywhere in the file. Two checks are wrapped in bare `except Exception` (L167-168, L241-242) and
can silently vanish. L220 explicitly exempted `images` from the empty-export check, so
`export const images = []` passed.

### The visual critic renders pixels but is structurally incapable of blocking

`pipeline/visual_critic.py` does screenshot and call a vision model, and its prompt already asks
about broken images. It still could not catch anything, for five independent reasons:

1. **Advisory only.** `_run_visual_critique` returns `None` on every path (L79, 148, 181, and by
   falling off the end at 189). It never produces a gate issue and never touches `ctx.ok`.
   `build_phase.py:217-218` swallows all exceptions around it.
2. **Scaffold exemption.** `codegen/critic.py:139-147` short-circuits to
   `{"score": 72, "verdict": "ok"}` *without calling the vision model* whenever the source
   contains `"deterministic catalogue contract scaffold"`. `PREVIEW_SCAFFOLD_FIRST` defaults true,
   so most pages carry that marker and were never scored. A scaffold page still renders real
   imagery to a real user; exempting it from visual review is backwards.
3. **Capped at 6 routes** (`MAX_VISUAL_CRITIQUE_PAGES`, L20) with no override, selected as
   homepage plus role default paths — so the admin pages holding the 7 broken image paths were
   never captured.
4. **Runs before the final heals**, so anything a heal introduces is never seen.
5. **Malformed JSON degrades to silence** — verdict `"unavailable"` is treated the same as "fine".

Its prompt also had no bullet asking whether the photography *depicts this business*, which is
exactly how dentures shipped captioned "Crimson Tide — Abstract Landscape Painting".

### A missing asset returned HTTP 200 with an HTML body

`api/v1/routers/preview_apps.py:42-44` SPA-fell-back **any** unknown path to `dist/index.html`
with `200 text/html`. So `/images/mock-artwork-1.jpg` returned 200 and an `<img>` rendered a
broken-image icon, while every status-code-based check saw a healthy app. Since generated
React-Router paths are extensionless, an asset-like path was always trivially distinguishable.

### The compiler was never run

`vite build` uses rolldown/esbuild and does **not** typecheck. The scaffold's own `package.json`
ships a `"typecheck": "tsc -b"` script that the pipeline never invokes, and `tsc` is present in
every workspace's `node_modules`. Running it took seconds and reported 59 errors — including every
prop-shape violation above. This was the cheapest available quality signal in the entire system
and it was sitting unused.

## Root cause 4 — smaller defects that read as "unfinished"

- **Literal escape sequences in copy.** `/works` and `/gallery` rendered the sentence
  "Browse pieces and details … then inquire about availability." with the six literal characters
  `\` `u` `2` `0` `1` `4` displayed on screen where an em dash belonged.
  `catalogue_contract/scaffold.py:783` holds a real em dash, and
  L825 emits it as `description={json.dumps(page_desc)}`. `json.dumps` defaults to
  `ensure_ascii=True`, and because it returns its own quotes the output is a **JSX attribute**,
  not a braced expression — and JSX attribute strings do not process JavaScript escapes.
  `scaffold.py` has 31 `json.dumps` calls and none passed `ensure_ascii=False`, while
  `assemble.py`, `text_utils.py`, `brand_brief.py` and `utility_compositor.py:66` all already did.
- **Invisible hero text.** The model added
  `after:bg-blend-multiply after:bg-text-brand/20 bg-background` to `MarketingHero`, expecting a
  dark image backdrop, making the headline, subhead, body copy and secondary CTA white on
  near-white.
- **Duplicate and malformed routes.** `/works` and `/gallery` rendered identically. The route
  table also contained `/works/:slug/:slug` (the same param name twice), plus ambiguous sibling
  pairs `/works/:id` vs `/works/:slug`, `/gallery/:id` vs `/gallery/:slug`, and `/admin/:id` vs
  `/admin/:slug` — the last of which shadows the literal `/admin/about`, `/admin/artworks` and
  `/admin/dashboard` routes depending on declaration order.
- **Duplicated nav.** Rendered as `Home | Contact | About Jeanne Kassab | Gallery | Works | About`
  — two entries for one destination, with Contact ahead of the portfolio.
- **Template jargon as visible copy.** "LEAD DROP", "NEXT MOVE", "GUEST PATH" rendered on screen.
- **Generic shell identity.** `<title>Preview App</title>` and `"name": "preview-app"`; nothing in
  the pipeline rewrote either, so every generated app in the fleet shared them.
- **Dead scaffold shipped.** `prepare_workspace` (`preview_app/workspace.py:49-76`) copies the
  template wholesale with a 3-entry skip list, so every app received 19 screenshots of unrelated
  businesses, three demo reference pages, and 12 laser-clinic images — 3.64 MB, of which 1.09 MB
  was passed through into the served bundle.
- **`fallback_pages` measured a policy flag, not quality.** `pipeline/finalize.py:138-150` and-ed
  a build-quality question with `ctx.enforce_app_spec`, which is only true when `APPSPEC_MODE=on`
  — and it defaults to `off`. So the clearing branch was unreachable, every scaffold route was
  recorded, and the metric a prior handoff used to judge quality was inflated noise.

## The lesson

Each individual bug here is ordinary. What made them compound into an unshippable demo is that
**every validation layer measured something adjacent to quality rather than quality itself** —
byte counts, route counts, HTTP status codes, substring presence, and a policy flag. All of them
were green. The product was not.

The durable fix is not more checks of the same kind. It is (a) deriving content from the business
rather than from a template, (b) showing the model the contract it must satisfy, and (c) verifying
the artifact the way a human would — compile it, fetch its assets, and look at it.

## Reproducing the audit

A standalone harness that reports what the pipeline's own gates could not see — shell identity,
route table, image reference resolution by content-type, `tsc` error counts, leaked placeholder
copy, shipped bundle weight, and screenshots of every public route — was used to produce the
numbers in this document. See the session handoff for its location and usage.
