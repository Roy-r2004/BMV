# Closing the gap between item 1.8 and the gate it shipped

Session 26, 2026-08-08. Owner ruling: *"let's fix the gate."* Landed before any money was
spent on the 20-business corpus, deliberately — see the last section.

## What was wrong

Item 1.8: *"Add a blocking gate code `placeholder_content_shipped` using the existing
`early_brand_placeholder_strings()` / `early_brand_placeholder_item_titles()`."*

What shipped used a bracket regex — `\[[A-Z][^,\[\]\n]{2,40}\]` — and called neither helper.
Those two remained consumed only by `product_face.py`, exactly as 1.8 described them
*before* the work was done. The substitution was never recorded, so for the life of the DoD
row the number came from one of the two families it was meant to cover.

The census (`placeholder-gate-census.md`) measured the missing family at **7 of 87 stored
workspaces** — `Everyday essential` / `Guest favorite` on requests 19, 34, 37, 39, 43,
**135 and 140** — a set with **no overlap** against the bracket regex's seven, two of whose
members sit inside the stretch the row was calling clean.

These are not brackets-with-a-capital. They are the seed's own default copy: what the
pipeline writes when it has nothing specific to say about the business. They ship looking
like content and say nothing, which is `[Artist Name]` wearing better clothes.

## The fix

Both families now fail under the same `placeholder_content_shipped` code, in
`quality_gate.py`.

**The `"Brand" in s` guard is load-bearing and is not ours to invent.**
`early_brand_placeholder_strings()` is *every* string leaf of the Brand-default seed, and
that includes `/gallery`, `60 min`, `Get started`, `On schedule` — routes, durations and
CTAs a real business legitimately ships. Matched bare it fires on **87 of 87** workspaces
and means nothing. `product_face.py:90` had already solved this with a co-occurrence test,
so the gate reproduces that guard rather than inventing a second rule for one question.
Comparison is against **exact string leaves**, never substrings, so a testimonial reading
"our Guest favorite for years" is real copy and stays green.

`_NAMED_EARLY_TITLES` restates two literals `product_face` also spells out inline. Two
copies of one decision is the shape this repo keeps finding rotted, so
`test_the_named_early_titles_track_product_face` pins the copy to its source by *reading the
source*, not by remembering to update both.

## Proof

7 tests (`tests/preview_app/test_placeholder_gate_seed_defaults.py`), 7 mutations, **0
survivors** (`scripts/cli/mutate_placeholder_gate.py`). Full suite **2,083 passed / 1
skipped / 0 failed**, up 8 from the 2,075 baseline.

**The sweep's first pass had 2 survivors and both were the tests, not the code** — which is
the entire reason the sweep exists:

| survivor | why the test was worthless |
|---|---|
| exact-leaf → substring scan | the fixture wrote *"our guest favorite"* in **lowercase**. A substring scan would not have matched that either, so the test passed against the mutation it was meant to kill |
| string-leaf regex → greedy `(.*)` | the fixture put the placeholder **alone on its line**, where a greedy match still captures it correctly. It only breaks when a second literal shares the line |

Both fixtures now carry the shape that kills the mutation, and their docstrings say why, so
the next person does not simplify them back.

## Why this landed before the corpus was funded

The row wants zero fires over 20 businesses; the database holds 16, so closing it needs
~$8.40 of new runs. Spending that against a detector already known to miss a live class
would have certified "zero placeholders shipped" on the strength of the narrower rule — and
fixing it afterwards would have invalidated all twenty samples. The expensive half is the
gathering. Fix first, then gather.

**Expect currently-"clean" runs to start failing.** That is the detector working, not a
regression, and the DoD row's number should be re-taken from here rather than compared to
the pre-fix series.
