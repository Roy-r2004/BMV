# Is whole-document repair the right shape? Measured, and answered: keep it, with the ladder this session built around it

Session 29, 2026-08-09. The question from the kickoff: every repair re-emits
the entire ~10,000-token document, so one bad field costs a full regeneration,
and a regeneration can collapse or die on transport. Candidates: RFC-6902
patches, section-scoped re-emission, deterministic heals for mechanical codes.

## The convergence curve (measure first — accepted runs since 129, n=24)

| repairs to acceptance | runs | share | requests |
|---|---|---|---|
| 0 | 13 | 54 % | 141, 146, 148, 153, 156, 158, 160-166 |
| 1 | 7 | 29 % | 132, 142, 144, 145, 147, 151, 157 |
| 2 | 3 | 13 % | 129, 135, 140 |
| 3 | 1 | 4 % | 150 |

**83 % of accepted runs converge within one repair; the whole recent tail
(158-166) is zero-repair.** Repair asks average 8,214 completion tokens, and
34 of 38 repair-stage asks since 129 finished `stop` and usable; the 4
failures were $0 transport cuts, not truncations — a smaller patch response
would have been cut identically.

And the dead runs did **not** die of repair economics: every one died with
repair budget remaining — of no-legal-move errors (131, 138, 149, 154, 155),
of pipeline-inflicted state (130, 136, 137, 139), or of a fragment mistaken
for the document (143). **Patches would have saved none of them.** A patch
against 143's 198-char fragment is still garbage; a patch for "declare the
state you never declared" still needs the model to author the state; a patch
cannot re-trace a requirement the binder stranded.

## The one real whole-document cost the corpus shows

Request 130: a repair re-emitted the document and silently dropped one
traceability row it was never asked to touch. That is *attrition of unfaulted
objects* — the failure mode rule 9's anti-collapse line polices at the
document level but cannot see at the object level. It has appeared once in 36
requests, and this session removed its only observed victim class (the binder
now re-traces its own requirements after every candidate pass).

## The alternatives, costed

**RFC-6902 / edit-list patches.** Saves ~8k output tokens per repair (~1-2 ¢
at flash pricing, ~30 s latency). Costs: a patch grammar the model must emit
validly (a new failure class replacing one that measurably almost never
fires — zero length-truncated repairs since 129); a deterministic patch
applier + path validator; taught fixes rewritten from "emit the corrected
document" to "emit ops against paths", which is strictly harder for
multi-section moves — fix B's taught repair (declare a state, list it on the
page, wire two transitions, keep reachability) touches four sections in one
coherent move. The measured upside is a cost the pipeline is not paying:
repairs converge in ≤1 attempt when the error has a legal move.

**Section-scoped re-emission** (only `states`, only `traceability`). Same
grammar safety as whole-document, smaller output — but the recurring codes are
cross-section by nature (a state repair touches `states`, `pages.state_ids`,
`transitions`; a trace repair touches `traceability`, `evidence`,
`pages.evidence_ids`). Scoping forces either multi-section requests (back to
most of the document) or a coordinator that knows which sections each code
touches (new machinery, new failure class). Worth revisiting only if repair
output cost ever becomes the binding constraint; it is not today.

**Deterministic heals for mechanical codes.** This is the one that pays, and
it is where the pipeline has been converging for weeks: `strip_extra`,
graph/membership repair, trace-evidence repair, trace-reference reconcile,
source-ref normalize, schema-version, tier1-journey — plus this session's
binder re-trace and fragment guard. The audit
(`validator-rule-audit.md`) finds **no mechanical code still reaching the
model or killing runs**.

## Recommendation

1. **Keep whole-document repair as the model interface.** The measured curve
   says it converges when the error has a legal move; the deaths were never
   the repair shape.
2. **Keep hardening the rungs around it** — that is where every one of this
   session's 12 root causes lived: deterministic heals for the mechanical
   (done, ongoing), taught legal moves for every recurring code (fix B
   pattern; `visible_assertion_evidence_required` added this session — apply
   the same treatment to any code that ever reproduces byte-identically),
   salvage at the would-otherwise-die branch (two codes now), and input
   integrity (the fragment guard).
3. **The one watch item: repair attrition.** If a future death shows a repair
   dropping unfaulted objects the binder cannot restore, the cheap
   countermeasure is a deterministic post-repair diff check that restores
   dropped-but-unfaulted top-level objects — not a patch protocol. One
   occurrence in 36 requests does not justify it yet.

## What a funded run would answer (the three briefs stand ready)

- Fix B and the visible-assertion fix live: a run that trips either code
  should end in a declared state / bound evidence (prompt escape) or a
  salvage action in `heal_actions` — never `repair_reproduced_parent_errors`.
- The binder fixes live: a model-authored hub or a stranded `REQ-AI-*` should
  show `deterministic` heal actions, zero `duplicate_route` /
  `requirement_unaccounted_for` deaths.
- 165's brief re-run: the cake gallery should bind cake photographs
  (`item_photos_by_title` queries in the logs, one per distinct subject), and
  `visual_defect_severe` should not fire on subject mismatch.
