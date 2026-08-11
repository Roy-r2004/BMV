# Every AppSpec death since 129, root-caused — and three of the kickoff's claims corrected

Session 29, 2026-08-09. All offline: `app_spec_revisions` (46 revisions across
36 requests since 129), `ai_usage_events`, and the source. $0 spent.

## The 12 deaths, by actual root cause

Requests with no accepted revision since 129: 130, 131, 133, 134, 136, 137,
138, 139, 143, 149, 154, 155.

| request | terminal | root cause | status after this session |
|---|---|---|---|
| 137, 139 | AppSpecBuildError / call_budget_exhausted | binder injected a second initial state (`page_initial_state_count`) | fixed `62cb26d` (session 29 kickoff) |
| 131, 149, 154, 155 | repair_reproduced_parent_errors ×3, validation ×1 | `state_assertion_state_required` had no legal move in the prompt | fixed `31fe604` (fix B); **all four predate it** (fix landed 2026-08-08 22:53, last death 18:48) |
| 130 | deterministic_validation_failed | **binder guard**: repair kept `REQ-AI-SMART-PRICING-INSIGHTS`, dropped its trace; "already bound" = "requirement exists", so the binder never restored it → `requirement_unaccounted_for` | **fixed this session** — stranded-requirement re-trace |
| 136 | AppSpecBuildError | **binder guard**: model wrote `PAGE-AI-FEATURES-HUB` at `/ai-features`; binder guarded by page id, appended a second page at the same route → `duplicate_route` | **fixed this session** — hub adoption by route |
| 143 | deterministic_validation_failed | **fragment extraction** (see below) | **fixed this session** — fragment guard |
| 138 | deterministic_validation_failed | `visible_assertion_evidence_required` ×4 taught no legal move; repair reproduced all four byte-identically | **fixed this session** — taught fix + last-resort salvage |
| 133 | coverage_review_malformed | coverage reviewer's malformed output was terminal | fixed earlier (varied retry + cross-provider rung; code comments cite run 133) |
| 134 | authoring_output_invalid | two authoring transport cuts, no cross-provider rung yet | fixed earlier (`_candidate_ask_with_transport_reask` ladder landed 2026-08-07 18:04, hours after 134 died) |

Nine of twelve deaths trace to exactly two mechanisms: **the AI-hub binder
writing state the validator then rejects (130, 136, 137, 139 — plus the
129-family audit rows), and an error with no legal move meeting a
whole-document repair (131, 138, 149, 154, 155).**

## Correction 1 — `trace_evidence_mismatch` was never an open killer

The kickoff carried it as OPEN, 4 requests. Counted properly, all four rev-1
rows (129, 135, 138, 144) are `terminal_reason=pre_trace_evidence_repair` —
**audit rows persisted by the deterministic trace repair (`dff8bb4`, live since
2026-07-27) immediately before it healed them at zero model cost.** Three of
four accepted on the very next revision; 138 died of a different code. Probed
against the stored payloads, `repair_trace_evidence_mismatch` fires cleanly on
all four: one unambiguous `add_capability_to_evidence` each.

The systematic *source* was still ours: `_ensure_page_evidence` minted
synthetic surface evidence carrying `capability_ids[:1]` — the page's first
capability — so any trace attaching the surface for a different page
capability manufactured the mismatch (129's `EVIDENCE-ADMIN-DASHBOARD-SURFACE`
carried the page's first capability; the trace needed `CAP-AI-VISUAL-ENHANCER`,
the page's fifth). Fixed this session: the surface carries every page
capability — a page surface is proof for anything the page exposes.

## Correction 2 — the "schema_repair collapse" was garbage-in, not collapse

The kickoff: *"473 completion tokens with finish_reason: stop where a full
spec is 8,000-11,000... The repair prompt already carries an anti-collapse line
and it is not holding."* The stored diagnostics say otherwise:

    143 authoring #2   30,845 chars, stop, usable
    rev 1 candidate       503 chars — an acceptance-test object (TEST-MENU-001)
    143 repair #1      31,303 chars, stop, usable
    rev 2-3 candidates    591 / 198 chars — fragments again
    extraction method  "repaired", raw 31,303 → extracted 414 chars (1.3 %)
    143 schema_repair     473 tokens — the model returned the *anti-example
                          skeleton* ("Page1", "Role1", "Product Name") because
                          the candidate it was told to repair was a 198-char
                          fragment with every top-level field missing

An unescaped quote desynchronised the outer object; every strict parse path
failed; the span fallback surfaced one balanced nested object and
`_try_repair` accepted it — no check that the recovered object resembles the
document that was sent. The anti-collapse prompt line was never the problem
and no attention collapse occurred: **the model was asked to repair 1.3 % of
its own output, twice, and then to conjure a spec from a fragment.**

Fix: `_is_fragment_extraction` — at ≥2,000 raw chars, a recovered object under
half the response is refused (`fragment_extracted` → the syntax-invalid /
truncated class, which re-asks the writer; a re-ask is a legal move, repairing
a fragment has none). Guarded on both recovery paths (repaired and
balanced-scan). The raw floor keeps small-document extraction — prose-wrapped
objects, first-object policy — exactly as it was.

## Correction 3 — transport (kickoff finding 3) was already closed

7 of 75 asks since 129 returned zero tokens, but every death it caused (134,
and the error-cut that opened 143) predates the transport ladder
(`_candidate_ask_with_transport_reask` + cross-provider rung, landed
2026-08-07 18:04). Since then: same-model re-ask once, then one cross-provider
ask, for every candidate-shaped writer, and the call budget refunds errored
asks. Nothing to do.

## Fix B (`state_assertion_state_required`): status honest, not proven-live

Zero occurrences in 131/149/154/155's code since request 155 — and all four
deaths predate the fix by hours. The prompt escape is in the template, the
salvage is test-proven (fixtures are the rejected 154/155 payloads verbatim),
and nothing since has exercised the path live. **A $0 session cannot prove it
live; only a run that trips the code can.** What a funded run would answer:
does a `state_id: null` assertion now end in a declared state (prompt escape
taken) or a salvaged claim (`drop_unbindable_state_assertion` in
heal_actions), instead of `repair_reproduced_parent_errors`?

## The fixes, gated

| fix | files | killed by |
|---|---|---|
| hub adoption by route + stranded re-trace | `ai_features.py` | 5 mutations |
| visible-assertion taught fix + salvage | `heal.py`, `app_spec_repair.j2` | 4 mutations |
| fragment guard | `authoring_parser.py` | 4 mutations |
| surface evidence full caps | `sanitize/evidence.py` | 1 mutation |
| per-item photo queries | `industry_images.py`, `photo_binding.py` | 5 mutations |

Sweep: `mutate_session29_fixes.py` — **19 killed / 0 survived**, anchors
verbatim, occurrence-counted (a miscount reports as MISCOUNT, not SKIP). Suite
green — see HANDOFF for the count.
