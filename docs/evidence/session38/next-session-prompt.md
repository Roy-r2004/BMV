# Kickoff — the console has a shape; give it instruments

*Supersedes session 37's prompt. Fidelity work is done and measured
(session 38 results): explicit navigation is honoured end to end, the
assistant-console archetype exists and was piloted, and the result page
says what class of software it is showing. The cost program remains
closed — do not reopen it.*

Read first, in this order:

1. `docs/evidence/session38/results.md` — what landed and what it cost
2. `docs/evidence/session38/classification-probe.json` — ten measured
   landings, each with the catalogue it ran against
3. `tests/test_intake_classification.py` — what is pinned as an equality
   and, more importantly, what deliberately is not
4. Memory: "Demo matches the business", "LLM judges confabulate about
   text", "Count it, don't sample a window"

## The one thing that must be said back before any judge work

The assistant console currently ships **judged by a rubric written for
data screens**. `image_quality_judge.j2` criterion 4 grades "premium craft
of cards & data visualization — a thoughtfully crafted hero chart", and a
conversation screen has no chart. The console's scores are therefore NOT
comparable to the dashboard corpus, and every number quoted about it must
carry that caveat. Any rubric change is its own step with a golden-set run
before and after (the gate-relaxations rule). State this back and get a go
before touching the judge.

## JOB 1 — decide whether the console keeps its scores (~$0 to specify)

Two honest options, and the owner picks:

- **Leave the judge alone.** The console is measured by a rubric that
  under-rates it, which is conservative — it can only make the console
  look worse than it is, never better. Cheapest, and it keeps every
  historical comparison valid.
- **Make criterion 4 conditional on the screen having a chart.** This is a
  judge change. It needs the golden set run before and after, and it
  invalidates cross-session score comparisons on the screens it touches.

There is no third option where the console gets a fairer score for free.

## JOB 2 — the golden set is one version behind the stage (~$0.05)

`golden/briefs` is frozen at ui-spec-v1 and the live stage is
ui-spec-v4. `build_golden.py` now refuses to mix versions into one set and
prints the right invocation. Freezing a v4 set — including the new
`assistant` intake fixture, which has no frozen brief yet — retires the v1
and v3 control arms, so it is a measurement decision, not a chore. If it
is taken: freeze all seven, keep the old directories, and say in the
write-up which comparisons the new set invalidates.

## JOB 3 — the chart tail, still the only open quality lever

Both of the console's follow-up re-rolls (request 119) were bought by
`malformed_data_display` on a chart: unevenly stepped Y-axis ticks at even
spacing, twice. That is the same finding as sessions 36 and 37, now on a
third archetype. The two specced answers are unchanged — the coded-ticks
prompt experiment (~$2 to measure) and JOB 6 (PIL-composited charts).
Fund only if defect-carrying screens bother the demos commercially.

## Smaller, all with receipts in the session-38 record

- **A duplicated hero caption is invisible to both instruments.** Request
  119's analytics screen drew "Growth Trends" twice; the aesthetic judge
  called it "a slightly thicker border" and the defect inspector did not
  report it. Duplication is on the inspector's list as `duplicated_panel`
  — an overlay caption apparently does not read as a panel.
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
- **`assistant` has an intake fixture and no golden brief** (see JOB 2).

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
