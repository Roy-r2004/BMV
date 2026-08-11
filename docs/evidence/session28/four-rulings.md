# The four rulings, executed

Session 28, 2026-08-09, second half. The owner ruled on the four items the
offline reads had left open. **$0 spent — no generation was launched.** Nothing
below is validated by a live run; that is stated again at the bottom because it
is the one thing that matters for whoever picks this up.

| # | ruling | commit |
|---|---|---|
| 1 | the seed gets its own model setting | `b2c1ba9` |
| 2 | packs carry structure only; every sentence written for the business | `eab4ef2`, `f11b9d2` |
| 3 | imagery: *"best practice not a patch — do the best solution"* | `e5002a3` |
| 4 | re-scope the placeholder row to the last N distinct businesses | `d72142c` |

Suite **2,153 → 2,280 passed / 1 skipped**. Four mutation sweeps, 42 mutations,
**0 behavioural survivors**; two equivalent mutants proved and recorded.

## 1. The seed's model — and the obvious default was the wrong one

`SEED_MODEL` now exists and leads the failover chain. It defaults to
`google/gemini-2.5-flash`, and the reason is not the seed's own history but the
shape of the ask. Measured across **every stage**, requests 129-161:

    google/gemini-2.5-flash        97 asks   93 % usable   max 15,248 tok
    google/gemini-3-flash-preview 124        61 %          max  4,522 tok
    anthropic/claude-haiku-4.5    114        53 %          max 24,000 tok
    deepseek/deepseek-v4-pro      192        42 %          max 10,107 tok

`mock_synthesize` asks for `max_tokens=14000` and its one success emitted
**10,107 completion tokens**. Inheriting `TEXT_MODEL` would have looked correct
and been wrong: `gemini-3-flash-preview` is the fastest model in the table and
has never produced more than a third of what the seed needs here, so it would
have **truncated** — a quieter version of the same failure. The 2.5 line carries
AppSpec's 12-15k answers at 88-100 % usable.

Resolved chain in this environment, reliable first:

    google/gemini-2.5-flash → deepseek/deepseek-v4-pro → anthropic/claude-haiku-4.5

deepseek is demoted, not removed: it produces 10k-token seeds when it answers.

## 2. Packs — the leak, its mechanism, and the selector

**The mechanism was in plain sight once looked for.** `write_plumbing_mock`
writes the pack's `mock_seed` into `mock.ts`; `synthesize_mock_data` then hands
that same file back to the model as **"CURRENT mock.ts"**. The pack's copy was
being presented to the writer as the current draft, and the writer kept it.

Both ends are closed:

- **The prompt** now says what that block is — scaffolding whose sentences
  describe no real business, keep the shape and replace every sentence — and
  names the two real failures so the instruction is concrete.
- **A new gate row, `pack_copy_shipped`**, fails any run whose `mock.ts` carries
  a pack sentence verbatim. It fails rather than repairs, per the house rule
  since session 18: a degraded generic ship is a defect, not a fallback.

The predicate is **read from the packs**, never restated — add a sentence to a
pack and the gate sees it with no code change. Exact leaf, never substring.
Leaves under 16 characters or without a space are structure, not voice: `"bold"`,
`"Popular"`, `"60 min"` must never fail a run.

**The selector, reproduced exactly.** Request 160's declared industry is
*"Bicycle retail, service and workshop"*. It matched
`fashion-retail-storefront` on **one token — "retail"** — and that was the only
pack that matched at all. At six characters the single declared word cleared
`_MIN_DISTINCTIVE_TOKEN_LEN`, so one category noun chose a whole visual identity.
`"shop"` and `"store"` were already weak for exactly this reason; `"retail"` and
`"retailer"` join them, and the brief now falls to recipe-only — which
`pick_template_id`'s own docstring already calls the better answer. A real
womenswear boutique still gets the pack, and a test holds that line.

No bicycle pack was added. Authoring a pack means authoring copy, which the same
ruling says should not exist as sentences.

## 3. Imagery — two defects, one cause

**The pool was 8 because `_search_pexels` asked for `per_page=8`.** It was never
a considered number. Census over the 18 stored workspaces with a slugged
catalogue: 13 declare more items than that, and the bind is
`i % len(item_slot_names())`, so item 9 showed item 1's photograph. Request 65 is
**16 items over 8 photos — every picture twice.** The pool is now **24**, sized
from the corpus with headroom over its largest catalogue, and still **one
request**: Pexels takes `per_page` up to 80, so a bigger pool is a bigger page.

**The deeper one: correspondence was impossible by construction.**
`item_pool_query` composes its search from the industry string and runs during
planning, before any item exists. Request 73's twelve representational
landscapes — *Whispers of the Forest*, *Coastal Serenity*, *City Nocturne* — were
captioned with eight non-representational abstracts. Right artifact type, wrong
artifact, invisible to every gate.

It needed the items first, so it now runs after the seed: read the titles out of
`mock.ts`, ask the index once for photographs of *those things*, and assign each
item its own picture by scoring the index's own `alt` text. Assignment is greedy
over the best remaining (title, photo) pair rather than left to right — taking
items in order lets item 1 consume the only photograph item 6 could have matched.
Every score is an integer and both tie-breaks are indices, so the result is
stable across machines.

**The first cut had the insertion point wrong, and that is worth recording.** It
was in `sync_mock_images`, which `apply_workspace_guards` calls before **every**
build attempt — so the photographs were re-picked on each retry and the workspace
stopped being idempotent. `test_unknown_slot_is_controlled_and_guards_are_idempotent`
caught it, **but only because this machine has a Pexels key**: on a machine
without one the same defect ships green. There is now a structural test that no
module under `safety/` can reach the fetch, and another pinning the single call
site in the codegen phase.

Every failure path returns `{}` and leaves the planning pool untouched — no
catalogue, no titles, no key, a search that raises, or a binding that would
repeat a photograph. Take it whole or leave it.

## 4. The placeholder row, re-scoped and scoreable

The bar of twenty is unchanged; *which* twenty is. The census now walks
newest-first, stops at the first run firing **any** of the three predicates, and
counts **distinct businesses rather than runs**:

    CLEAN TAIL (no predicate fires): 3 of 20 distinct businesses over 4 runs — FAILED
      Copperline Hardware
      Ridgeline Bike Works
      Kestrel & Fern Bakehouse

Session 26's "28 clean workspaces" were 6 businesses, one of them 25 runs of the
same restaurant. A row about whether the writers leak placeholders learns nothing
from asking one business twenty-five times. The business map is passed in with
`--businesses` rather than queried, so the script keeps the property its
docstring claims: **it reads no database.** Without the map it reports runs and
says explicitly that runs are not businesses.

## Mutation sweeps

| sweep | mutations | survivors |
|---|---|---|
| seed failover (re-run on the new chain) | 10 | 0 |
| catalogue photo binding | 12 | 0 |
| `pack_copy_shipped` | 8 | 0 behavioural (1 equivalent) |
| — first passes | | **10 real gaps, all in my tests** |

**Ten first-pass survivors, and for the first time in six sessions they were not
fixture defects — they were genuine holes in tests I had just written**:
catalogue selection on a tie, nested arrays, stopword-only matches, the greedy
ordering itself, more titles than slots, both new imagery constants, a
tautological assertion comparing a set against the constant that built it, and a
substring test whose phrase differed in case from the pack's.

Two equivalent mutants, both proved rather than argued:

- `m10` — `return content or None` in the seed. `_valid_synthesized_mock_source`
  opens with `if not content.strip(): return False`, verified directly against
  `""`, `"   "` and `"\n"`, so the success path is unreachable with falsy
  content. Its meaningful form `m10b` is killed.
- `q3` — the route-literal guard in the pack walker. No leaf in any of the 27
  packs is 16+ characters **and** contains a space **and** starts with a path or
  URL, verified by scanning them, so removing the guard changes nothing today. It
  stays for the pack that adds a long link tomorrow.

## What is not proven

**None of this has been through a live generation.** Specifically:

- The imagery binding adds **one HTTP request per generation on the critical
  path** and changes what ships in every catalogue.
- `pack_copy_shipped` **can fail runs that previously shipped**. That is the
  intent, but the first trio after it must be read with that in mind — a run
  withheld for pack copy is the gate working, not a regression.
- `SEED_MODEL` points at a model the seed has not used since request 98.

One trio answers all three. It is ~$0.70 and it should be the next thing spent.
