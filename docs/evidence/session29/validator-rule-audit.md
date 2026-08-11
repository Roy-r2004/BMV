# Every validator code that has ever fired, audited: heal, model repair, or fatal

Session 29, 2026-08-09. Counted from the **whole corpus** — every issue in
every stored revision of `app_spec_revisions`, all 300+ revisions, not a
window. 39 distinct codes have fired; the ~60 defined codes that never have
are classified by family at the end.

Legend for "route": **heal** = deterministic, zero model cost;
**repair** = model repair with a taught legal move; **salvage** = deterministic
last-resort at the would-otherwise-die branch; **fatal** = correctly kills the
run. A code can route through several rungs in order.

## Codes that have fired, by occurrence

| code | n | reqs | route today | verdict |
|---|---|---|---|---|
| invalid_page_shape | 206 | 34 | schema diagnostics → repair (rule 7a taught) | RIGHT — shape errors need the model; 7a covers the dominant stateless-page case |
| app_spec_schema_parse_failed | 142 | 50 | heal (strip extras) → schema_repair | RIGHT, and the dominant *source* (fragment extraction) is fixed this session |
| missing_required_field | 131 | 9 | schema_repair | RIGHT — most of these were 143's fragments judged as documents; with the fragment guard the class shrinks to real omissions |
| unexpected_field | 94 | 9 | **heal** (`strip_extra` on extra_forbidden) | already deterministic — kickoff's example was already done |
| invalid_field_constraint | 52 | 10 | schema_repair | RIGHT |
| requirement_unaccounted_for | 44 | 8 | repair ("trace or defer") | RIGHT for model-authored reqs; the injector-authored case (130) is now the binder's re-trace, so the model only ever sees its own |
| invalid_enum | 37 | 6 | sanitize normalizes known aliases → repair | RIGHT |
| trace_evidence_mismatch | 28 | 16 | **heal** (`dff8bb4` trace repair, unambiguous only) → repair | already deterministic; manufactured source (surface caps[:1]) fixed this session |
| page_membership_mismatch | 26 | 9 | **heal** (graph repair) | RIGHT |
| state_assertion_state_required | 25 | 10 | repair (taught, fix B) → **salvage** | RIGHT |
| invalid_reference_shape / invalid_trace_shape | 44 | — | preparse normalize → schema_repair (rule 10) | RIGHT |
| missing_reference | 20 | 4 | **heal** (reference integrity) → repair (taught) | RIGHT |
| duplicate_global_id / duplicate_id | 21 | — | repair | **the one mechanical-fatal candidate left** — see below |
| traceability_empty_refs_* | 15 | 5 | **heal** (trace reference reconcile) | RIGHT |
| unresolved_requirement_source_ref | 11 | 3 | **heal** (source-ref normalize) | RIGHT |
| requirement_traced_and_deferred | 9 | 4 | repair | mechanical in one direction (drop the deferred entry when the trace is proven) — candidate for a heal, not taken this session: 0 deaths, and the safe direction needs the trace proven first |
| visible_assertion_evidence_required | 8 | 1 | repair (taught **this session**) → **salvage** (this session) | fixed |
| evidence_capability_page_mismatch | 8 | 1 | graph-repair family | RIGHT |
| page_initial_state_count | 8 | 7 | repair (taught rule 48-50) | injector source fixed `62cb26d`; model-authored case keeps the taught repair |
| must_requirement_cannot_be_deferred | 5 | 2 | repair | RIGHT — scope judgement, not mechanical |
| invalid_acceptance/action/evidence_shape | 11 | — | schema_repair | RIGHT |
| app_spec_authoring_json_truncated / output_invalid | 8 | 4 | authoring re-ask ladder + model fallback | RIGHT — transport class, closed by the reask ladder |
| transition/trace/journey *_mismatch codes | ~12 | — | graph + trace repairs → repair | RIGHT |
| tier1_primary_journey_incomplete | 1 | 1 | **heal** | RIGHT |
| unreachable_state | 1 | 1 | sanitize (prunes) → repair | RIGHT |
| duplicate_route | 1 | 1 | repair | the one occurrence was binder-inflicted (136), fixed at source. A model-authored collision is a navigation-semantics choice — uniquifying a route deterministically would silently invent information architecture. Stays with the model. |

## The rule the kickoff asked about, answered

*"A rule that is mechanical and is currently fatal is costing runs for
nothing."* After this session's fixes there is **no code that is (a)
mechanical, (b) currently reaching the model or killing runs, and (c)
occurring**. The two that looked like it were `unexpected_field` (already a
deterministic heal via `strip_extra`) and duplicate ids:

**duplicate_global_id (14×, 3 reqs) is the remaining candidate** — an id that
needs uniquifying is mechanical *only when the two objects are genuinely
distinct*; when they are the same object emitted twice, the right move is a
merge, and picking wrong invents or deletes meaning. The graph repair already
declines this family (`NON_REPAIRABLE_WITHOUT_INVENTION` names
`duplicate_object_definition` / `conflicting_duplicate_object`). It has killed
no run since 129 on its own. Ruling recorded: **stays with the model repair**,
which sees both objects and can merge; revisit only if it ever kills a run.

## Codes that must stay fatal

- `blocking_open_question` — the spec itself says the product cannot be built
  without an answer; shipping around it would fake a decision the customer
  never made.
- Post-ladder exhaustion (`call_budget_exhausted`, runway reserve) — the
  ceilings are the owner's cost/latency contract, settled.
- `repair_reproduced_parent_errors` after the salvage rung has had its chance —
  a repair that changes nothing twice will change nothing thrice; the stop is
  what keeps a dead run from costing three more asks. (The salvage rung now
  covers both assertion dead-ends before this fires.)

## Never-fired codes, by family

Journey-step chain codes (`journey_step_*`, `journey_start_mismatch`), effect
codes (`*_effect_*`), role/action cross-checks — all route through
graph/sanitize repairs first and the model second, same as their fired
siblings. None has ever killed a run; none is mechanical-fatal. No change.
