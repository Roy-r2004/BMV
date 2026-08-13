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

## JOB 1 — the overlay-text blind spot (~$0.20, and it is the best-value job here)

Counted across all 33 shipped screens of requests 100–120
(`duplication-census.md`), the instruments split cleanly:

- panels, modules, cards, rows, controls: **8 caught, 1 missed**
- text painted on top of an image or a chart: **0 caught, 2 missed**

`image_defect_inspector.j2`'s `duplicated_panel` asks for "the same panel,
card, button pair, label or block of information drawn twice" — a hero
caption or a chart annotation is none of those nouns, and both misses are
exactly that. The one panel-level miss (120 Knowledge, a whole AI
Suggestion module drawn twice) shipped approved at **8.5 with zero issues
from either instrument**, which is the defect the judge's own rejection
list promises to catch.

This is an instrument change, so it is staged properly and it is now
cheap to stage, because instruments re-judge EXISTING images — no
regeneration. The 33 census screens are on disk with eye-labels; run the
current inspector and a candidate revision over all of them and compare
against the census, ~$0.0022 a screen a side. That is a real before/after
on a labelled set for about $0.20. State the judge-held-fixed implication
and get a go before landing it.

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
