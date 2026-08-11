# Session 24-parallel — roadmap deltas — FOLDED IN (2026-08-08, after session 25 landed)

> Status: every delta below is now in `PREVIEW_ROADMAP.md` (rows 0.2 / 0.4 / 0.8, the
> "also land here" verification note, the session-24-parallel status block, 2.6's
> gates-answered line) and `HANDOFF.md` (the session-24-parallel page). This file stays
> as the provenance record. The 0.8 branch remains held pending its merge gate.

A second session ran beside the session-24 offline block (which owned R2's
retry-site audit, censuses 0.1/0.5/0.9, Phase 3's 3.7/3.2/3.5, DoD 9's CI half
and DoD 6's convolution). To avoid racing that session's close-out, nothing
here edits `PREVIEW_ROADMAP.md` or `HANDOFF.md`; this file holds the exact
text to fold in once it lands. Everything below is offline, $0, and touches
only new files plus one held branch.

## 0.4 — ANSWERED (fold into the Phase 0 table + a detail section)

**Are the critic's `revision_instructions` expressible as content-key edits?
Mostly yes — and the structural remainder is real.** Over the 41 stored visual
critique reports (requests 37-122; 153 defect findings; 752 classifiable asks
after punctuation-anchored splitting; the raw `revision_instructions` field is
never persisted — the findings carry the same asks item-by-item, capped 6 per
page): **48.9 % of asks are content-key expressible** (copy 115, nav/CTA 139,
imagery-subject 64, data completeness 49) under a rubric whose ties break
*against* expressibility, so it is a floor; **49.6 % among blocking-severity
asks**. A 58-atom hand audit (archived, per-atom) agrees with the rubric 79 %,
and its errors run **10-to-2 toward under-counting content** — the true share
is plausibly around **60 %**. Under Phase 2's pages-as-data reading (a missing
planned section becomes a spec-data edit, not a component change) the share is
**68.6 % / 73.6 % severe**. Structural asks that no content edit fixes:
missing sections 123, styling/layout 97, wrong-page identity 34, slot-contract
violations 25, rendering 19.

**Consequence for 2.6, same direction as 0.3:** a spec-level actor mapping
visual findings to content-key edits covers the majority of what the critic
asks; the ~⅓ structural remainder (sections, identity, styling) is exactly
what the BLOCK must keep catching. Both 2.6 gates (0.3 + 0.4) are now
answered, in the same direction.

Evidence: `revision-instruction-census.json` + `revision-instruction-audit.json`
(this dir), corpus archived at `docs/evidence/visual-critique-reports.tar.gz`
(extracted from the api volume — no run after 122 has a report; the critic
never ran on 129-145, the R5 tail-starvation fact). Tool:
`backend/scripts/measure/revision_instruction_census.py`; `--check` red-exits
on any drift from the archived numbers (proven red under tamper).

## 0.2 — ANSWERED (fold into the Phase 0 table)

**P(refine fires): 74.2 % of judged critic runs** (23 of 31 stored reports
with a judged verdict have a non-empty `refined` list); by telemetry, **23 of
74 scoped-era runs (31.1 %), 136 `refine` calls** — the `refine` scope exists
only from request 72, so earlier runs are not measurable (they sit in the
unscoped `stage=''` bucket).

**Does a slot-filled page keep the scaffold marker? Yes, wholesale.** 275 of
631 pages (43.6 %) across the 87-run union corpus (archive + live volume)
carry the literal `deterministic catalogue contract scaffold`; on the 62 runs
with a stored preview record, **195 marker-carrying pages were reported NOT
fallback — every one of them routed, inspected and accepted by finalize's
`_scaffold_page_is_acceptable`; 0 unrouted stragglers; 0 ghost reports**
(reported-fallback-without-marker). So `fallback_pages` is internally coherent
under its own substantive predicate — but the LITERAL marker is a dead signal
**today**, not merely after the Phase 2 flip: `files_with_scaffold_marker`
and any naive marker census read 44 % scaffold on a corpus the pipeline
itself judges mostly substantive. This measured fact is 0.8's premise,
strengthened.

Evidence: `refine-scaffold-census.json`, `stored-fallback-pages.txt`,
`stored-route-files.txt`, `refine-telemetry.json` (this dir). Tool:
`backend/scripts/measure/refine_scaffold_census.py`; `--check` red-exits,
proven red under tamper.

## Phase 0's "also land here" residue — all four verifiably closed, no code

- **`ai_usage_events.request_id` NULLs: dead on the current pipeline.**
  0 NULLs across 1,009 rows on Aug 4/6/7 (runs 143-145 era); the only 3
  post-Aug-1 stragglers are requestless `stage='pipeline'` rows. The 853
  historical NULLs (Jul 27–Aug 1) stand as an undercount caveat for any
  census over pre-scoping rows.
- **`success` semantics: superseded** by `usable`/`unusable_reason` — 164
  rows with `success=t, usable=f` are exactly the "HTTP 200, unusable output"
  class the item wanted distinguishable.
- **Duration logs: present** (`typecheck.py` stores `duration_ms`;
  `build.py` logs attach/build seconds).
- **The `mkdtemp` dist-backup leak: fixed** — cleanup in the `finally`
  (`build_phase.py:290-296`).

## 0.8 — implemented on a HELD branch (merge after the parallel session lands)

Branch `session24b/content-density` (pushed, not merged — a checkout or merge
now would race the session working in the main tree): new
`app/application/preview_app/content_density.py` measures prose characters
per routed page with the archived DoD-2 census's exact predicate — pinned
against `scripts/measure/content_census.py` by test so the two rulers cannot
drift apart silently — and finalize stores `content_density` beside
`fallback_pages` (`status`, `pages_measured`, `prose_chars_total`/`median`,
`pages_under_200_chars`, `per_page`); a failed measurement is stored as
`status: unmeasured` with the reason, never an absent key. Measurement only;
nothing reads it. **10 tests; 9 mutations / 0 survivors first pass**
(`scripts/cli/mutate_content_density.py`). The DoD-2 census numbers (mean
859 / median 529 per page, 12 % ≥ 200 target) are the metric's "before" by
construction. Merge gate: full suite via docker run once the tree is quiet.

## Handoff paragraph (for the session-24-parallel page)

Spend $0 (no model calls; DB and archives only). Closed offline: 0.2 and 0.4
(the last Phase 0 measurement gates for 2.6 — both now answered, both pointing
the same way as 0.3), plus verification that all four "also land here" residue
items were already closed by earlier sessions. Implemented and held: 0.8 on
`session24b/content-density`, 9/0 mutation sweep, awaiting a quiet tree to
merge. New standing fact: the scaffold marker literal survives slot-fill on
43.6 % of shipped pages while finalize's substantive predicate accepts them —
retire every literal-marker reading. Nothing in the other session's lane was
touched: no roadmap/HANDOFF edits, no retry-site code, no `.github`, no
template files.
