# Row 7 — the catalogue cards, scored card by card (session 26, 2026-08-08)

Offline, **$0**, no generation. The row had stood open since request 70 with the note
*"73's binding is correct but its cards were not scored card-by-card"* — nobody had
looked at the pictures. This is that look.

## Method

Stored workspace only; nothing was regenerated.

1. `docker compose exec api` → `/app/data/preview-apps/73/src/data/mock.ts`.
2. Read the `items` array: 12 entries, each with a `title` and an `image`.
3. Read the `images` export: the eight `item1…item8` Pexels URLs.
4. Fetched the eight photographs **from inside the api container** (the sandbox has no
   outbound network; the container does, which is how it fetched them in the first place),
   copied them out with `docker cp`, and looked at all eight.

Business (`requests.id = 73`): **Atelier Sorel** — *"An independent fine-art gallery
representing a single painter, with a deep catalogue of at least twelve original oil
paintings on show at any time."* So the artifact the business sells is **an original oil
painting**, and that is what a catalogue card must show.

## The binding

```
item1 … item8, then item1, item2, item3, item4      ← 12 items, 8 slots, i % 8
```

1.9's fix holds. Items 9-12 cycle back into the item pool and **do not** wrap onto
`images.card1/2/3` — the role images ranked last precisely because they show people. That
wrap is what put a photograph of someone at an easel, captioned "Oil on Linen", on request
70's cards, and it is gone.

## The score

| slot | Pexels id | what it is | shows an oil painting? |
|---|---|---|---|
| item1 | 16397728 | impasto abstract, red / blue / yellow, canvas weave visible | **yes** |
| item2 | 3684544 | violet-black abstract, heavy palette-knife work | **yes** |
| item3 | 1475951 | orange / blue blocked abstract | **yes** |
| item4 | 1530709 | deep blue-violet abstract, thick facets | **yes** |
| item5 | 15377378 | primary-colour abstract, broad strokes | **yes** |
| item6 | 16397723 | red / blue abstract, textured ground | **yes** |
| item7 | 1023767 | orange / gold / blue abstract, macro crop | **yes** |
| item8 | 1414327 | orange / blue geometric abstract | **yes** |

**12 of 12 cards.** No people, no studios, no palettes, no hands. Under the row's own bar —
*shows the artifact type the business sells* — request 73 passes it outright, and this is
the first time the row has been scored rather than inferred from a binding.

## Two things the score found that are not this row's bar

Recorded separately and **not** used to fail row 7, because scoring a row against a bar it
was never given is how a DoD stops meaning anything.

### 1. The photographs cannot depict the items — structural

The twelve works are titled:

> Whispers of the Forest · Coastal Serenity · City Nocturne · Golden Hour · River's Edge ·
> Morning Mist · Autumn Hues · Deep Sea Currents · Mountain Ascension · Whispering Dunes ·
> Rustic Village · Celestial Bloom

Every one names a representational landscape. **Every photograph is a non-representational
abstract**, and several (16397728, 16397723, 1023767) are macro crops of paint surface
rather than a whole framed work. "Coastal Serenity" is a purple abstract. "Rustic Village"
is an orange-and-blue abstract. The card shows *a* painting; it does not show *that*
painting.

This is not a bad draw from the stock index. `item_pool_query(industry)`
(`industry_images.py:511-527`) builds its search text from the **industry string alone** —
no brand, no item, no title — and `_search_pexels` takes `per_page=8, page=1`. The pool is
fetched **before any item exists**, so correspondence is impossible by construction. No
query tuning reaches it. Fixing it means fetching after the items are known, per item, or
generating the imagery — a new capability with a per-run network cost, which is the same
shape as the `og_image` extractor that was written down and deliberately not built.

Same defect class as request 70's easel photo, one notch subtler, and **invisible to every
gate in the pipeline**: the vision critic blocked request 41 for "all of the artwork catalog
images show people painting rather than the finished artworks" — a wrong-subject check. It
has no wrong-*work* check, and could not have one without knowing what the work looks like.

### 2. The pool is 8 and most catalogues are bigger

Census over the 18 stored workspaces that have a slugged catalogue:

| items vs the 8-slot pool | runs |
|---|---|
| more items than photos | **13 of 18** |
| items ≤ 8 | 5 of 18 — 22 (5), 32 (6), 77 (8), 80 (8), 95 (8) |

Worked examples: request **65 is 16 items over 8 photos — every picture shown twice**; 73
is 12 items with 4 repeats; 88 is 12 items with 4 repeats.

`_IMAGE_POOL_SIZE` is `len(item_slot_names())` and the cycle is `i % 8`
(`item_source.py:113,136`, `scaffold.py:1389`). The pool size is not a considered number —
it is `_search_pexels`'s `per_page=8`.

A repeat still shows the artifact type, so it does not fail row 7. But for a gallery
selling **originals**, two different works sharing one photograph contradicts the product in
a way it does not for a café's menu. A second Pexels page is nearly free; whether that or a
cap on declared items is the answer is an owner ruling.

## Caveat, stated

n=1 run for the visual score. Request 73 was chosen because it is the run the row names,
and because the eight most recent runs (129-145) have **no slugged items array at all** —
145's seed degraded to the plumbing mock (4 items, no slug, no image, no price). The newest
workspace with a real catalogue is request **95**. If a funded trio is meant to re-score
this row, at least one of its three briefs has to be a catalogue business, or the row gets
no sample.

Findings 1 and 2 are **not** n=1: 2 is a census over 18 workspaces, and 1 is read off the
query builder's signature.
