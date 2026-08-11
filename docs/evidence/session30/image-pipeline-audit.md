# Image pipeline audit — professional-services and drinks-led businesses

Requested as "check the … consultant image pipeline". **No branch by that
name exists** — checked every local and remote ref in BMV, all worktrees, the
repo for the string `consultant`, and the five sibling projects in
`~/Documents/Dev`. So this audits the image pipeline itself for the
consultant/professional-services case, and it turned up two live defects
using today's runs as evidence. **$0 spent — all reads.**

## Defect 1 — the per-item query drops the business's subject noun

`item_photos_by_title` builds each item's search as the item's own words plus
a qualifier taken from the industry phrase:

```python
industry_head = _clip_words(industry or "", 2)   # first TWO positional tokens
```

`_clip_words` takes the first two *word tokens*, not the two most salient
ones. When the industry phrase leads with adjectives, the subject noun is cut
off. Measured on today's runs (queries pulled from `bmv-api` logs):

| business | industry phrase | head | item query actually fired |
|---|---|---|---|
| Copperline Hardware (167) | Independent **hardware** store and tool hire | `Independent hardware` | `large angle grinder Independent hardware` ✅ |
| Kestrel & Fern (169) | Artisan **bakery** and neighbourhood cafe | `Artisan bakery` | on-subject ✅ |
| **Lantern & Ash (170)** | **Late-night** cocktail bar and listening room | **`Late night`** | `midnight sazerac Late night`, `old flame Late night`, `the last word Late night`, `crimson tide Late night`, `smoke mirrors Late night` ❌ |

For the bar, **no query contains "cocktail", "bar", or "drink".** The
hyphenated `Late-night` tokenises to `Late` + `night` and consumes both
allowed slots on a single adjective. Pexels is then asked for "old flame late
night" and returns whatever that phrase means — not a drink.

Same class hits consultancies: `Independent strategy consultant` → head
`Independent strategy`, dropping `consultant`. (`Management consultancy`
happens to survive because its noun is in position two — luck of word order,
not design.)

This is run 165's defect in a new coat: 165 bound cake titles to bread photos
because the *pool* was wrong; here each title gets its own query, but the
qualifier steers it off-subject. Per-item binding is working — the
qualifier is not.

## Defect 2 — drinks-led hospitality has no path to the food bucket

`_MIN_CATEGORY_SCORE = 2`, and in the `food` keyword table `bar` carries
weight **1**. `cocktail`, `pub`, `brewery`, `taproom`, `wine`, `lounge`, and
`drinks` are absent entirely. Result:

| industry | category |
|---|---|
| Late-night cocktail bar and listening room | `generic` |
| Wine bar | `generic` |
| Craft brewery and taproom | `generic` |
| Management consultancy | `generic` |

So run 170's slot and hero imagery searched
`Lantern & Ash Late-night cocktail bar and listening room **professional
small business** hero lifestyle wide` — a dim late-night bar dressed in
generic small-business stock.

`generic` for a **consultancy is correct and deliberate** — the
`_resolve_category` docstring owns that decision, and "professional small
business" is the right hint for legal, trades, logistics and the rest. The
defect is that drinks-led hospitality falls into the same bucket when a
perfectly good `food` bucket exists.

Note `retail` would be the *wrong* answer for the hardware store — that
bucket is fashion/apparel/outdoor-gear weighted, and the same docstring
records a law firm once getting shopfront photography. Hardware → `generic`
is defensible. Bar → `generic` is not.

## Corroboration: 169 was rendered as a restaurant twice over

The bakehouse's imagery queries included `chef plated pasta dish detail` and
`brunch guests dining experience restaurant`, while its `mock.ts` shipped
`House pasta`, `Chef tasting`, `Bar bites` — the copy defect that withheld
the run. **Two independent subsystems — the industry pack and the imagery
bucket — agreed on the same misclassification.** The `food` bucket is
restaurant-shaped, so a bakery inherits restaurant imagery even when it
scores correctly.

## Suggested fixes (not applied — this was a check)

1. Pick `industry_head` by **salience, not position**: drop leading
   adjectives and prefer the highest-weight keyword the category tables
   already know (`cocktail`/`bar` for 170, `hardware` for 167). The tables
   needed to do this exist.
2. Add the missing drinks keywords to `food` at weight 2 (`cocktail`, `pub`,
   `brewery`, `taproom`, `wine bar`, `lounge`), or give drinks its own
   bucket so a bar stops inheriting plated-dinner imagery.
3. Split the `food` bucket's restaurant bias so `bakery` does not import
   `chef plated pasta`.

Each changes live generation output, so each wants the usual treatment: a
pin, a sweep, and a funded run to confirm — not a quiet edit.
