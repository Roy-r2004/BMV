# The remaining failure surface, enumerated end to end — what was built, what was ruled, what needs money or an owner

Session 29 part 2, 2026-08-09. The ask: make AppSpec fail-proof — every edge
case named, best-practice answer for each, changing the shape of the stage
where warranted. Constraints honored: `APPSPEC_MODE=on`, fallback stays
disabled, scope is never silently degraded (session 18 ruling).

"Bullet-proof" has an honest boundary: a stage whose input is a paid model
call can always be starved by weather or the clock. What CAN be guaranteed is:
**no run dies while a deterministic, scope-preserving action could still save
it, and no deterministic action ever degrades scope to buy a ship.** That
guarantee is what this pass builds.

## The failure surface, stage by stage

| # | stage | edge case | answer | status |
|---|---|---|---|---|
| 1 | authoring ask | transport cut / zero tokens | same-model re-ask + cross-provider rung, budget refund | closed earlier (post-134 ladder) |
| 2 | authoring ask | truncation (`length` at 24k) | model fallback chain (139 proved it live) | closed earlier |
| 3 | extraction | fragment accepted as document | fragment guard (≥2k raw, <50 % recovered → re-ask class) | **closed part 1** |
| 4 | extraction | model never emits parseable JSON | every parse failure is a re-ask with a varied corrective instruction; ends at call budget — a model that cannot produce JSON in 8 asks has nothing to ship | fatal BY DESIGN, recorded |
| 5 | sanitize/bind | binder collides with model-authored hub (route, initial state, state id) | adopt-by-route; initial-state guard (62cb26d); **foreign `STATE-AI-HUB-READY` gets a minted sibling id** | **closed (part 1 + 2)** |
| 6 | sanitize/bind | repair strands injector requirements | binder re-traces after every candidate pass | **closed part 1** |
| 7 | sanitize/bind | synthetic evidence narrower than its page | surface evidence carries every page capability | **closed part 1** |
| 8 | validation | model re-emits identical error (no legal move) | taught fixes (fix B + visible-assertion) + targeted salvage + **terminal salvage pass** | **closed (parts 1 + 2)** |
| 9 | validation | mechanical issue meets an exhausted rung cap | **terminal salvage pass**: full code-driven heal + unbindable-assertion drops, once, uncapped, at every deterministic fatal exit; progress = changed document | **built part 2** |
| 10 | model repair | repair silently drops unfaulted objects (attrition) | **attrition guard**: dropped trace rows restored when the whole proof chain still resolves; refuses on any doubt | **built part 2** (trace rows — the one observed class; other collections stay watch-items until one is ever observed) |
| 11 | model repair | repair collapses the document | `_repair_collapsed_spec` parent-keep guard | closed earlier |
| 12 | model repair | duplicate ids | deep-equal duplicates healed deterministically; conflicting objects stay with the model (merge is judgement) | **built part 2** |
| 13 | deadline | runway reserve stops the stage mid-ladder | `ai_budget = 0` path now falls through the terminal salvage before dying — a deadline-stopped run with only mechanical/unprovable-claim issues ships its own document | **built part 2** |
| 14 | coverage | reviewer output malformed twice | varied retry; then fatal — a quality failure never takes a model fallback (R1 ruling, settled) | fatal by ruling |
| 15 | coverage | double transport cut | cross-provider rung (post-133) | closed earlier |
| 16 | coverage | reviewer honestly finds missing scope, repairs can't close it | fatal — this is the gate doing its job | fatal BY DESIGN |
| 17 | spec content | `blocking_open_question` | fatal — shipping around it fakes a customer decision | fatal by ruling |
| 18 | provider | full multi-provider outage | nothing software can buy; the run fails honestly and the next run succeeds | out of scope |

## What changed about how AppSpec works (part 2's four changes)

1. **Terminal salvage pass** (`_terminal_salvage_pass`, generation.py). Every
   rung is individually capped, so a run could reach a fatal exit holding an
   issue a rung would have fixed if its budget had not been spent on an
   earlier shape of the document. Now, at all three deterministic fatal exits
   (schema attempts spent, repairs spent/deadline-zeroed, identical-error
   stop), the code-driven heals and unbindable-assertion drops run once more,
   uncapped, and the loop revalidates. Progress is a **changed document**, not
   a non-empty action list, so a no-op pass cannot buy a loop. Scope-safety by
   construction: heals wire references and strip rejected shapes; the salvage
   removes only unprovable proof claims; neither can delete a requirement,
   page, or capability. Anything still failing dies exactly as before.
2. **Attrition guard** (`restore_dropped_trace_links`, heal.py). Request 130's
   class: whole-document re-emission dropping an object it was never asked to
   touch. A dropped trace row is restored only when the repaired document
   still contains the requirement, no other row traces it, every cited id
   resolves, and the row passes the validator's own trace-consistency rules.
   Anything less stays dropped — the repair may have meant it.
3. **Exact-duplicate heal**. The one mechanically safe slice of
   `duplicate_global_id`: byte-identical re-emission dropped; different
   objects under one id remain a model merge (the graph repair's
   no-invention ruling).
4. **Binder state-id collision**. A model-authored `STATE-AI-HUB-READY` on a
   different page no longer collides; the hub mints a sibling id.

## Deliberately NOT built, with reasons

- **Patch-based / section-scoped repair** — measured and rejected in
  `repair-shape-recommendation.md`; the convergence curve says the deaths were
  never the repair shape.
- **Coverage quality fallback (a third model on malformation)** — R1 ruled a
  quality failure never takes a model fallback; relitigating that is an owner
  decision, not an edge case.
- **Demoting `blocking_open_question`** — fakes a decision the customer never
  made.
- **Attrition restore for collections beyond traceability** — evidence/test
  restore is designed the same way, but only the trace class has ever been
  observed (once). Building unobserved restores adds risk without a measured
  defect. The design note in `restore_dropped_trace_links` is the template
  when one is observed.
- **A second cross-provider transport rung** — the ladder already takes two
  cuts before the rung; a third distinct provider is config
  (`APPSPEC_TRANSPORT_FALLBACK_MODEL`), not code, and every observed storm
  cleared within one rung.

## Gates

Suite green (see HANDOFF count). Hardening sweep `mutate_hardening.py`:
**10 killed / 0 survived** (restore proof-chain checks ×4, duplicate heal ×2,
terminal-salvage wiring ×2, attrition wiring ×1, binder collision ×1), on top
of part 1's 19/0. Integration tests drive the real generation loop with
scripted providers: a deadline-shaped run that used to die
`deterministic_validation_failed` now ships its own document with the salvage
recorded in `heal_actions`; an unsalvageable run still dies with the identical
terminal reason; a repair that drops an unfaulted trace row gets it restored
and accepts.

## What still needs money (unchanged)

The five part-1 fixes and four part-2 mechanisms have not been through a live
run. First funded trio: same read-outs as the session 29 block, plus — if any
run trips a fatal exit — `heal_actions` should show whether the terminal
salvage fired and what it did.
