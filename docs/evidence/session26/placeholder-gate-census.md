# Phase 1 DoD — `placeholder_content_shipped` fires zero times over 20 businesses

Session 26, 2026-08-08. Offline, **$0**, read-only. Tool:
`backend/scripts/measure/placeholder_gate_census.py`, archived JSON beside this file.

The row had stood open on *"inverted so far — the gate exists and fires correctly; the DoD
wants zero fires, which means the writers still emit placeholders"*, with two data points
(2 leaks on request 73, 2 on 68), waiting on a 20-business run. **It never needed a run for
the part that could be measured** — the gate's predicate is a regex over `src/data/mock.ts`
and 87 workspaces are on the volume. It turns out to need a *bigger* run than anyone had
priced, for a reason nobody had checked.

## The headline

**The row cannot be closed from this corpus, and could not have been.** It asks for zero
fires over **20 businesses**. The entire database holds **131 requests across 16 distinct
`business_name` values.** There has never been a 20-business corpus to score it against.

## What the shipped gate says

`_BRACKETED_PLACEHOLDER_RE` (`quality_gate.py:45`), imported rather than restated:

| | |
|---|---|
| corpus | **87** workspaces with a `src/data/mock.ts` |
| runs firing | **7** |
| last run to fire | **request 93** |

| request | leaked |
|---|---|
| 33 | `[Painting Title]` |
| 68 | `[Owner Name]`, `[Painter's Name]` |
| 71 | `[Artist Name]` |
| 73 | `[Customer Name]`, `[Painting Title]` |
| 78 | `[Next available slot]` |
| 81 | `[Patient Name]` |
| 93 | `[Phone Number]` |

**Requests 94-145 are clean — and that is much weaker evidence than it looks.** The clean
tail is 28 workspaces but only **6 distinct businesses**, and two of them dominate: Osteria
Vinci 25 runs, Cedar Point Lodge 19, then Harbor Dispatch Desk 3, Petal & Stem 2, Riverbend
Yoga 2, Northgate Dental Studio 1. It is 28 runs, not 28 samples. A placeholder class that
only a seventh business would trigger cannot appear in it.

## What the gate was *specified* to use, and does not

Item 1.8 reads: *"Add a blocking gate code `placeholder_content_shipped` using the existing
`early_brand_placeholder_strings()` / `early_brand_placeholder_item_titles()`."*

**The shipped gate calls neither.** It uses a bracket regex instead, and those two helpers
remain consumed only by `product_face.py` — exactly as 1.8 described them *before* the work
was done. The substitution was never recorded anywhere.

Scored with the same guard `product_face.py:90,117` applies (`"Brand" in text`, plus the two
named titles), the specified predicate fires on **7 of 87 runs** — a set that does **not
overlap** the shipped gate's seven:

| requests | leaked |
|---|---|
| 19, 34, 37, 39, 43, **135**, **140** | `Everyday essential`, `Guest favorite` |

**135 and 140 are recent** — inside the "clean" tail above. So there is a live placeholder
class shipping today that the gate cannot see, and the row's own number never counted it.

### A note on the guard, because the first cut of this census was wrong

Matched **bare**, `early_brand_placeholder_strings()` fires on **87 of 87 workspaces** — it
is every string leaf of the Brand-default seed, which includes `/gallery`, `60 min`,
`Get started`, `On schedule`. Routes, durations and CTAs that any genuine site ships. The
first version of this script reported that 87/87 as a finding; it is noise. Production never
matches bare, and the census now reproduces `product_face`'s guard instead of paraphrasing
it. The bare number is retained in the JSON as `specified_predicate_unguarded` so the
difference stays visible. **Same trap as the two route censuses in the traps section: a
census that paraphrases the code it measures will eventually measure the paraphrase.**

## Verdict

**FAILED, and re-scoping is wanted before it is scored again.** Three separate reasons, only
the first of which was known:

1. The writers do still emit unfilled placeholders — 7 of 87 workspaces, though none since
   request 93.
2. The gate is **narrower than the item that created it specified**, and misses a class that
   fired as recently as request 140.
3. **The denominator is unreachable.** 20 businesses, against 16 in the whole database. At
   ~$0.42 a generation, twenty distinct businesses is ~$8.40 of new runs — more than the
   entire remaining balance — and no trio can close this row.

## Reproduce

```
docker compose exec -T api python3 \
  /app/backend/scripts/measure/placeholder_gate_census.py \
  --workspaces /app/data/preview-apps \
  --check /app/data/../tmp/placeholder-gate-census.json
```

`--check` red-exits on any drift in any block. Proven: tampering
`shipped_predicate.run_count` to 0 and `verdict` to `MET` exits **1** with both keys named;
the untampered archive exits **0**.
