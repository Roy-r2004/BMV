# Kickoff — confirm the realised mean, then buy first-shot quality

Session 36 confirmed **nominal $0.390** at the target config and landed
the regeneration policy (`QA_REGEN_SCORE_FLOOR=7`), but the realised
target mean measured **$0.6255 over n=4** with a defect-heavy tail —
against a $0.42–0.47 projection that assumes the two defect-class fixes
(brand-variant specs, verifier false-confirms) actually deleted their
regenerations. Read `docs/evidence/session36/results.md` first.

Three steps, in order:

1. **The confirmation batch (~$1.80–2.50).** Four briefs, target config
   (`--candidates 1 --label s37-target`), full pipeline. If the realised
   mean lands in $0.42–0.47 and text-truth failures stay at zero, flip
   `DASHBOARD_CANDIDATES` to 1 for real: config default, the
   `test_the_shipped_anchor_candidate_count_is_two` pin, and the
   cost-model comment all move together. If it doesn't land, say why
   before touching the default.

2. **The chart-ticks A/B (~$2).** The proposal is written in results.md:
   compute nice round tick labels in code, hand them to the model as
   literal strings (the annotation pattern `_chart_block` already uses).
   Same briefs both arms, separate labels, look at the screens — the
   scaffolding-renders-as-UI trap is the thing to check with eyes.
   Success = the malformed_data_display rate on chart screens drops
   without new weirdness. This is half of JOB 6's value at a fraction of
   its build cost; JOB 6 (PIL compositing) still owns marker alignment.

3. **Watch the brand-variant fix hold.** Zero text-truth failures across
   the batch is the expected result. Any recurrence is paraphrase-class
   (the template constraint failing) — bring the evidence back before
   writing any fuzzy rewriting; the RoasterFlow trap is documented.

Budget the lot at ~$5 with headroom. Bracket per request via
`/api/requests/<id>/admin`, report every `/studio/<id>`, never two bakeoff
batches concurrently. The clock (still ~270s vs the 180s line) stays
untouched until the money questions close.
