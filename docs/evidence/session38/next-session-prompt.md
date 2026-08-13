# Kickoff — the console has a shape; give it instruments

*Supersedes session 37's prompt. Fidelity work is done and measured
(session 38 results): explicit navigation is honoured end to end, the
assistant-console archetype exists and was piloted, and the result page
says what class of software it is showing. The cost program remains
closed — do not reopen it.*

Read first, in this order:

1. `docs/evidence/session38/results.md` — what landed and what it cost
2. `docs/evidence/session38/duplication-census.md` — all 33 shipped
   screens, eye-labelled, against what the instruments said
3. `docs/evidence/session38/classification-probe.json` — ten measured
   landings, each with the catalogue it ran against
4. `tests/test_intake_classification.py` — what is pinned as an equality
   and, more importantly, what deliberately is not
5. Memory: "Demo matches the business", "LLM judges confabulate about
   text", "Count it, don't sample a window"

## The one thing that must be said back before any instrument work

The assistant console ships **judged by a rubric written for data
screens**. `image_quality_judge.j2` criterion 4 grades "premium craft of
cards & data visualization — a thoughtfully crafted hero chart", and a
conversation screen has no chart. Its scores are therefore NOT comparable
to the dashboard corpus, and every number quoted about it must carry that
caveat. That specific gap was decided in session 38 and left alone (below)
— but JOB 1 does touch an instrument, so the rule still applies: a change
to the judge or the inspector is its own step with a before/after over a
labelled set (the gate-relaxations rule). State it back and get a go.

## Settled in session 38 — do not reopen without a reason

- **Criterion 4 stays as it is.** It grades data-visualisation craft on
  screens that have none, so it under-rates the console — conservative in
  the only direction that matters, and changing it would invalidate
  cross-session score comparisons on every screen it touches. Console
  scores stay flagged as not-comparable wherever they are quoted.
- **The v4 golden set is frozen** in `golden/briefs-v4/`, all seven briefs
  including `assistant`. The DEFAULT set did not move and should not: every
  evidence document before session 38 means v1 by "the golden set", and
  `bakeoff.py --frozen-specs` reproduces historical cells against it.
  Address the new set explicitly with `GOLDEN_BRIEFS_DIR=golden/briefs-v4`.

## JOB 1 — watch what verifier v2 does to the cost line

Session 38 measured the defect instruments on a labelled set and changed
one of them. `image-defect-verifier-v2` confirms **12 of 17** true
duplication claims where v1 confirmed 5, with no false confirmations in
either arm (`verifier-v2-measurement.json`). Two rules were colliding with
the category they policed: "a similar-but-different pair is not a
duplicate" acquitted every real case, because a model's duplicate is never
byte-identical, and the text-claim ban was being applied to the act of
NAMING which panel was duplicated.

That is a gate getting stricter, and a stricter gate buys regenerations.
Nothing in session 38 measured the cost consequence — the verifier change
landed after the last funded batch but one. **First job: read the next few
runs' `by_purpose.image` call counts against the eight-run baseline of
~$0.63 realised.** If regenerations rise materially, the owner decides
whether the extra confirmations are worth it; do not tune the verifier
back without that number.

An inspector change was also tried and **reverted** — widening
`duplicated_panel` to cover overlay text made it worse (caught 2 where v1
caught 3) and still missed both overlay cases. The inspector was never the
problem: it raises a correct claim on 9 of 11 genuinely duplicated
screens. Do not re-try that edit without reading
`inspector-v2-measurement.json` first.

## JOB 2 — the chart tail, still the only open quality lever

Both of the console's follow-up re-rolls (request 119) were bought by
`malformed_data_display` on a chart: unevenly stepped Y-axis ticks at even
spacing, twice. That is the same finding as sessions 36 and 37, now on a
third archetype. The two specced answers are unchanged — the coded-ticks
prompt experiment (~$2 to measure) and JOB 6 (PIL-composited charts).
Fund only if defect-carrying screens bother the demos commercially.

## Smaller, all with receipts in the session-38 record

- **Placeholder names keep appearing in list content.** "Guest Artist A"
  and "Guest Artist B" (108), "Client B/C/D/E/F" (102 Schedule),
  "Endowment Fund XYZ" / "Jane Doe Trust" / "Institutional Fund ABC"
  (104 Customers). The template's "never Option A" rule now names the
  pattern explicitly; it is unverified by a funded run.
- **A scaffolding leak is still reachable.** Request 105's analytics hero
  carries a chip reading "Floating Labels" — prompt vocabulary rendered as
  UI, the class the memory rule "name the string or say nothing" exists
  for. Pre-fix run; worth one look on any future analytics screen.
- **Archetype selection is not deterministic.** Identical intake text
  landed the investment brief on analytics-dashboard and then
  crm-dashboard. Nothing is broken; it means no write-up should say a
  class "lands on X" from a single run. If stability matters
  commercially, that is a real piece of work and it starts with a count,
  not a fix.
- **An honoured navigation still cannot catch an INVENTED item.** The
  text-truth gate measures the strings the spec ordered, so a dropped item
  fails and an extra one does not. Both known sources are cut off
  upstream; a third would be silent. Detecting extras needs positional
  transcription, which nothing here has.

## Traps, all still paid for

- Do not run two funded batches concurrently; read spend via
  `/api/requests/<id>/admin`, never the shared key balance.
- Prompt bans have blast radius; scaffolding renders as UI. The
  conversation block names every visible string and describes nothing —
  keep it that way.
- Any classifier touch is measured against the synthetic-briefs 20/20 pin
  and the stored kind_contexts (backend), and against
  `classification-probe.json` (this service) before landing.
- New shapes ship at the same three-screen, same-model economics. A fourth
  screen or a model change is an owner decision with a price tag.
