# Phase 1's remaining rows, read offline — and the seed defect the reading found

Session 28, 2026-08-09. **$0 spent: no generation was launched.** Every number
below comes from `ai_usage_events`, the `requests` table, or the 98 stored
workspaces on the volume.

The phase was left *code-complete and not proven*, with a middle row of items
described as "the data is stored, the reading is offline and free". This is that
reading. It closed three rows, re-scoped one, and turned up a defect big enough
to fix in the same block.

## The headline

**`mock_synthesize` — the stage that writes every app's catalogue content — has
been failing 87 % of the time since request 101, and nothing showed it.**

    google/gemini-2.5-flash   requests 72-98    19 of 23 usable   mean 27.0 s
    deepseek/deepseek-v4-pro  requests 101+      4 of 31 usable   mean 66.1 s
    the last two trios (146-161)                 1 of 11 usable

Ten of those eleven are `provider_timeout` with `output_chars = 0`; six rode the
120 s ask cap to the millisecond. The stage spends ~91 s of every run and
delivers nothing on ten runs out of eleven.

It was invisible because the failure path is a *quiet* one: the caller keeps the
plumbing mock, which is the Brand-default seed with the business name pasted
through it. That is why request 161 — **a hardware store** — shipped:

    services:      "Copperline Hardware Signature", "AI-guided consult",
                   "Member aftercare", "Follow-up visit"
    testimonials:  "the owner hub's no-show risk view alone paid for itself"
    social_proof:  "Trusted by over 2,400 delighted Copperline Hardware clients."
    client_names:  [… "Client 7", "Client 8"]

That is the wellness/booking default seed on an ironmonger, and it is the
*"demo matches the business"* problem at its actual root. **Every catalogue
defect filed against the writers since request 101 was read off a run where the
writer never answered at all** — including session 26's row-7 work and session
27b's industry-pack finding.

Cause: the seed was the one content-critical stage in the pipeline **with no
model failover** — one hardcoded `attempt=1`, one model, one silent fallback.
Fixed in `be7ae70`; 10 mutations, 0 survivors; suite 2,245 / 1 skipped. Model
*order* is left to settings, because on these numbers the primary is the weakest
link in its own chain and that is a ruling, not a retry policy.

## Row by row

| row | was | now |
|---|---|---|
| `appspec` ask ceiling | unprovable — all 49 rows carried `writer = NULL, attempt = 1`, so the logical-ask grouping had nothing to group on | **MET.** 37 appspec asks across 146-161, **all 37 with a writer**, max attempt 1, mean 20.1 s, **max 47.3 s** against a 120 s ceiling. The session-6 scopes work |
| the 120 s ask ceiling overall | breached by a constant — four asks at 135.0 s to the millisecond, `_CANCEL_GRACE_SECONDS` spent after the cap fired | **HOLDS.** 24 asks hit the cap across 146-161 and the **largest overshoot is 21 ms**. The grace fix is confirmed live. Four writers ride the cap: `slot_fill` ×11, `mock_synthesize` ×6, `planner` ×5, `architect` ×2 |
| p50 ≤ 560 s no-regression floor | "re-base it, do not score the trio" — the 558.7 s baseline was 8 serial runs, and trios 8/9 came in at 564 s under the first real contention | **MET at 559.0 s, and no re-base is needed.** Eight simultaneous-start runs now exist (146/147/148/150/151 and 158/160/161): **553, 553, 556, 556, 562, 564, 570, 577** — p50 **559.0 s**, mean 561.4 s. Concurrent evidence against a floor that finally has a matching experiment |
| ≤ 600 s cap | MET on 5 of 5 timed runs, two trios | **8 of 8 across three trios**, worst 577 s |
| `degraded: [stage]` marker | fixed and verified on 77/78/79 | **still populated**, every run in 146-161 carries a non-empty list |
| seed's cap-riding call | carved out, "the next funded trio measures it" | **measured, and it is worse than the row supposed** — see the headline. The row asked whether the truncated seed degrades; the answer is that it does not truncate, it does not return at all |
| `slot_fill`'s discarded output | 205.3 s/run, 147.7 s discarded (duo 1) | **375.6 s/run, 179.6 s discarded — 47.8 %.** And the *distribution*, which the standing row wanted: **transport 16 asks / 1320.1 s, rejected 10 asks / 655.1 s, usable 28 / 2156.0 s.** Two thirds of the waste is asks that never returned, not fills the judge threw away |
| `placeholder_content_shipped` = 0 over 20 businesses | "not closable — the row wants 20 businesses and the database holds 16" | **still open, denominator still short, and a third placeholder family found** — below |

## The placeholder row, and a third family

`scripts/measure/placeholder_gate_census.py`, corpus now **98 workspaces**
(was 87). The database holds 147 requests across **22 distinct business names**
(was 131/16), so the row's *headline* denominator is finally reachable — but the
denominator that matters is the clean tail, and it is not.

    SHIPPED    (the gate's own bracket regex)       7 of 98 fire, none since request 93
    SPECIFIED  (1.8's early_brand_* helpers)        7 of 98 fire, none since request 140
    BRAND      (fix D's family, NEW this session)  21 of 98 fire, none since request 156

**The BRAND predicate is new and it is the point.** Session 27's fix D found that
`"Business"` is a placeholder brand too — request 156 shipped *"Ready for
Business?"*, *"Tell Business what you need"*, *"Business — clear choices and real
bookings."* Those live in **page TSX**, and the shipped gate reads
`src/data/mock.ts` only, so it cannot see them by construction. The census now
measures the class by running production's own `scrub_placeholder_brand` over
`src/pages/**` and counting what it would rewrite.

It fires on 21 of 98 workspaces, last at **156** — 157, 158, 160 and 161 are
clean, which is fix D working, confirmed across the corpus rather than on the one
run it was written from.

**One trap walked into and recorded.** The first cut scanned all of `src/` and
fired on 91 of 98 with an identical signature every time: `components/Nav.tsx`,
`ui/public/AiFeature{Deck,Panel,Stage}.tsx`. Those are the **template's own
default parameter values** — `function Nav({ brandName = 'Brand' })` — copied
verbatim into every workspace. A default is not shipped copy; it renders only
where a call site omits the prop, and every call site passes it
(`<Nav brandName={brand?.name ?? 'Brand'} />`, with `brand.name` populated on
every workspace checked). That is the same defect as this script's original
unguarded SPECIFIED set firing on 87 of 87 and meaning nothing. The count is
reported as `template_default_runs: 98` rather than dropped.

**Where the row actually stands.** Scored against all three predicates on current
code, the clean tail is requests **157, 158, 160, 161** — four runs, **three
distinct businesses**. The row wants twenty. It is not closable by a trio and it
is not closable by re-reading the archive; it needs either funding or a re-scope
to *"zero fires over the last N distinct businesses"* with N stated honestly.

## Two things checked that are not defects

- **"Zero consecutive asks to the same resolved model id"** fires 5 times over
  146-161 under a literal reading. Three are `slot_fill` attempt 1 → 2 on the
  same model, which is the **quality-rejection retry** re-asking with
  `_slot_fill_retry_prompt` — a different prompt, by design, and not the
  request-74 defect the row was written about. The other two are one query
  artifact: two pages' cross-provider rungs both land on attempt 3 and the
  partition did not separate them by file. **No regression; the row's wording is
  ambiguous and should say "consecutive *failover* asks".**
- **`slot_fill`'s transport rung is gated, not broken.** 16 transport cuts
  produced 6 rung asks (attempt 3), 2 of them usable. The other 10 were declined
  by `_has_transport_fallback_runway()` — out of time, which is the guard doing
  its job.

## What is left in Phase 1 after this

Nothing that costs money except the placeholder row's denominator, and nothing
that needs code. What remains is three owner rulings, all filed and none of them
a bug:

1. **The seed's model order.** `deepseek/deepseek-v4-pro` is 4-of-31 usable at
   66.1 s mean; `google/gemini-2.5-flash` was 19-of-23 at 27.0 s. The failover
   now catches the failure, but the primary is still the weakest link and every
   run pays ~120 s to discover that.
2. **Industry packs ship literal copy, and the selector mismatched one**
   (session 27b, unchanged — and note this is now known to fire *on top of* a
   dead seed, not instead of one).
3. **The catalogue's photos cannot depict its items**, and **the item pool is 8
   against catalogues of 12-16** (session 26, unchanged).

## Process notes

- **Read a suspect check in `ai_usage_events` by `finish_reason`, never by run
  outcomes.** This session opened by finding fix F had misfired 27 times across
  14 requests rather than twice; the same query shape then found the seed. A
  retry ladder hides a misclassifier, and a quiet deterministic fallback hides a
  dead stage.
- **A stage that fails silently is worse than one that fails loudly**, and the
  pipeline has two such fallbacks left by design (plumbing mock, scaffold
  slot-fill). Both are correct as behaviour and both need a *counter* the gate
  can see, or the next dead writer takes another twenty runs to notice.
- `docker cp` the census into the api container before running it: the script
  imports production modules and the workspaces live on the container's volume.
