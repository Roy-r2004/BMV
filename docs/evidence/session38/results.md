# Session 38 — make the demo obey the customer

*2026-08-12, `main`, following session 37. Budget $6 with a $5 stop line.
Everything below is measured through the customer path: intakes submitted
to `POST /api/requests`, screens viewable at `/studio/<id>`, cost read from
this service's own ledger via `/api/requests/<id>/admin` — never from the
shared key balance.*

## What the session was for

Request 107 ("Jeanne Art") asked to showcase paintings with a four-item
header — home, gallery, about, contact — and got an operations dashboard
whose navigation carried a fifth item the template invented. Two failures:
explicit customer constraints losing to template defaults, and requests
outside the dashboard vocabulary being coerced into it silently. Both are
now measured, and both have landed fixes.

## Step 1 — explicit constraints win

### The defect had two causes, not one

Reading all three screens of request 107 with eyes:

| screen | qa | navigation actually drawn |
|---|---|---|
| dashboard (anchor) | 8.0 | Home · Gallery · About · Contact · **Settings** |
| schedule | 8.1 | Home · **Schedule** · Gallery · About · Contact · **Settings** |
| analytics | 6.8 | Home · Gallery · About · Contact · Settings, with **"Settings" marked as the active screen** |

1. **`ui_spec.j2` padded the list.** The RULES block asked for "5-7 short
   one-word items", so the spec itself carried five.
2. **The follow-up prompt asked for an active item that did not exist.**
   `build_continuation_prompt` said *"Only the active item changes, to
   {screen_title}"*; on the schedule screen that title was not in the
   navigation, so the model added a sixth item to have something to
   activate.

Cause 2 is systemic, not a Jeanne quirk. **Every one of the six golden
briefs** has at least one screen whose title is absent from its
navigation, and **11 of the 21 screens shipped on requests 100-106** were
in that state. Sampled, they either invented an item (107's schedule) or
highlighted an unrelated one (101's Analytics screen marks "Pipeline").

And **text-truth passed 7/7 on all three screens**. The gate reads
`spec.navigation` as its ground truth, so it dutifully checked the
invented item. A gate cannot see a string the pipeline never ordered.

### What landed

- `extract_explicit_navigation()` (`pipeline/ui_spec.py`) reads a
  navigation list out of the intake deterministically. It needs a
  navigation cue word followed by a run of at least three label-shaped
  items, which is why it reads request 107's typo'd sentence and reads
  nothing out of the dental, HVAC, law or roastery briefs. The list is
  passed to the template **and** applied to every spec in code, including
  on the model-failure fallback path.
- `ui_spec.j2` → **ui-spec-v4**: "5-7 items" survives as an explicitly
  labelled DEFAULT; when the customer has named a list, the template is
  told the exact list and told that a shorter one is their decision. The
  archetype line stops claiming to govern navigation in that branch —
  leaving a contradiction in a prompt is what caused this class.
- `active_nav_item()` (`pipeline/prompt_builder.py`) names the active item
  only when the screen genuinely is one; otherwise the clause is dropped
  from both the anchor block and the continuation prompt. No new ban was
  added: the defect was a contradiction, not a missing rule.

### Verified live — [/studio/108](http://localhost:5173/studio/108)

Same intake text as 107, typos and all. **$0.64505, 299s, 0 failed calls.**
Bracket $487.5875 → $488.2306 (Δ $0.6431; the ledger is the truth, the key
is shared).

| screen | qa | text-truth | navigation drawn |
|---|---|---|---|
| Analytics (anchor, pro) | 7.0 | pass, **checked 6** | Home · Gallery · About · Contact |
| Dashboard (flash) | 7.9 | pass, checked 6 | Home · Gallery · About · Contact |
| Customers (flash) | 9.2 | pass, checked 6 | Home · Gallery · About · Contact |

`checked 6` is the number that matters — it was `7` on request 107. The
gate now measures the four labels the customer named plus the two brand
strings. Four items on every screen, including both follow-ups.

**Honest limit, unchanged:** honouring the list makes a *dropped* item a
measured failure. An *extra* item still is not, because the transcript is
an unpositioned list of rendered lines. Both sources of extras are cut off
upstream instead.

## Step 2 — the demo vocabulary, measured before it was built

`scripts/classify_probe.py` (new) runs analyze → consult → plan → ui_spec
on a real request and stops before the image stage: ~$0.012 a brief
against ~$0.63 for a generation. Ten probes, recorded in
`classification-probe.json`, each row carrying the catalogue it ran
against so a landing stays readable later.

| class | before the console existed | after |
|---|---|---|
| investment | analytics-dashboard (109) | fallback (113, a bug — see below), crm-dashboard (118) |
| chatbot | **operations-dashboard, "Chatbot" as the 4th nav item** (110) | **assistant-console, conversation anchor** (114) |
| courses (assistant-first) | — | **assistant-console, conversation anchor** (116) |
| portfolio | analytics-dashboard, nav honoured (111) | analytics-dashboard, nav honoured (115) |
| salon (control) | operations-dashboard (112) | operations-dashboard (117) |

**The headline finding was not on the agenda: archetype selection is not
deterministic for a given intake.** The investment brief landed on
analytics-dashboard and then on crm-dashboard on identical text; the
portfolio brief landed on operations-dashboard (107) then analytics
twice. What *is* stable is the two ends of the range — a brief with an
obvious home, and a brief whose product IS the assistant. Only those are
pinned as equalities in `tests/test_intake_classification.py`; pinning a
coin flip produces a test that fails for the wrong reason on a Tuesday.

### Investment system — nothing built

Confirmed by measurement: it lands on a credible numbers-or-clients shape
and never on the console. Pinned, no code.

### Chatbot / AI assistant — `assistant-console` landed

The recorded coercion (request 110) is the whole argument for it: the
product the customer came to see was rendered as the fourth item in a
service dashboard's navigation.

- **New archetype** `assistant-console`: conversations → analytics →
  knowledge, the anchor carrying no chart.
- **New concept shape.** A conversation cannot be described with steps and
  options, so `ScreenConcept` gained `turns` and `_conversation_block()`
  renders the thread. `"assistant"` was removed from `TOOL_CONCEPT_KINDS`
  so a thread can never be pushed through the selection-flow layout.
- **The pairing is enforced in code**, not trusted to the prompt: a
  conversation anchor on any other archetype degrades to a dashboard.
  Nearly every brief this pipeline sees is sold an AI front-desk in its
  consulting summary, so `assistant` is a kind any of them could reach
  for, and a salon whose anchor became a chat window instead of its
  booking flow would be a worse demo, not a more honest one. Measured:
  adding the console moved none of investment, portfolio or salon.
- An art pack, so the console is not the one archetype rendering with no
  art direction.

**Effect on the judge-held-fixed rule.** `image_quality_judge.j2`, the
defect inspector, the verifier and `text_truth.py` are byte-identical.
The judge takes only screen title, product, business, industry and
min_score — it is archetype-blind, so no rubric edit was needed to land
this. But criterion 4 grades *"premium craft of cards & data
visualization — a thoughtfully crafted hero chart/progress element"*, and
a conversation screen has none. **Console scores are therefore not
comparable to the dashboard corpus**, and criterion 4 is a systematic drag
on them. Any rubric extension is its own step with a golden-set run.

### Two funded pilots, looked at with eyes

| pilot | link | cost | wall | screens (qa) |
|---|---|---|---|---|
| Halden & Co — the recorded coercion case, re-run | [/studio/119](http://localhost:5173/studio/119) | $0.75847 | 235s | Conversations 7.9 · Analytics 9.2 · Knowledge 8.4 |
| Northlight Studio School — evening art courses | [/studio/120](http://localhost:5173/studio/120) | $0.65164 | 221s | Conversations **9.2** · Knowledge 8.5 · Analytics 6.5 |

Text-truth passed 7/7 on all six screens. Both landed on the console with
a conversation anchor; both rendered a real thread — customer bubbles left
in the surface colour, assistant bubbles right in the accent with avatars,
the spec's own composer placeholder ("Reply to Sarah"), its suggestion
chip, and the context rail. The navigation is preserved across all three
screens of each set with the correct item marked active.

Pilot 120's thread is the argument for the whole shape: *"Tell me about
your watercolor painting course" / "Our Watercolor Fundamentals starts Oct
15, Tuesdays, 7-9 PM" / "What's the cost and materials needed?" / "£250
for 8 weeks. Kit list on course page."* Real course names, real prices,
real times. The same class of request previously came back as a service
dashboard with "Chatbot" in the navigation.

**Cost: $0.706 mean, against the corpus's $0.634.** Five of the six
screens bought their one regeneration. That is what a shape the pipeline
has never drawn before costs on its first outing; two runs is not a rate.

Remember the caveat above when reading those scores: they were produced by
a rubric that grades data-visualisation craft on screens that have none.

### Portfolio / showcase — framing, not an archetype

A public-site archetype cannot be landed against the fixed judge at all:
it auto-rejects *"a device/browser mockup frame around the app, or a
marketing-page composition"*, and a portfolio website is exactly that.
Every screen would auto-reject, burn its regeneration and ship
unapproved. That archetype is a **judge change first**, and it is not a
session's work.

What shipped instead is `pipeline/what_this_is.py`: one paragraph at the
top of the result page, composed server-side from strings already on the
request — no model call, nothing that can hallucinate.

> Jeanne Artistry Canvas is the software Jeanne Art would run day to day —
> the screens below are its interface, drawn with your own services, your
> own customers and plausible numbers for a business your size. **It is
> not your public website. It is the back-office tool you would use to run
> the enquiries, bookings and sales that come in through one — and it is
> what we are proposing to build first.**

Always on, for every request. A conditional would need a classifier to
decide when honesty applies, and the first sentence is true for all six
archetypes. The second sentence appears only when the brief mentions a
website or a shopfront. It is live on
[/studio/108](http://localhost:5173/studio/108) — a page already paid for.

First draft pasted the whole consulting summary in as a middle sentence
and turned the panel into a wall of text on the first real page it was
tried against; the page already carries that promise twice, so the
paragraph answers one question and stops.

## Found and fixed on the way

**A single bad chart value discarded an entire request's spec.** Caught
live on the investment probe (request 113): ui_spec returned a
multi-series chart whose seventh value was `{"series1": 1.4, "series2":
6.9}`, `list[float]` rejected it, and because the screens array validates
in one pass, `build_ui_specs` fell back to the generic deterministic specs
— a demo specific to nobody, for the whole request, over one data point.
`ChartSpec` now drops a series it cannot plot, and `_chart_block` asks for
no chart at all rather than sending labels with no numbers (which is how a
screen invents its own data). Nothing is repaired or guessed.

**`build_golden.py` would have mixed prompt versions into a control arm.**
Adding the `assistant` intake fixture would have frozen a v4 brief
straight into `golden/briefs`, a set frozen at v1 — after which "the
golden set" means two different things depending on which brief you load.
The script now refuses and prints the `GOLDEN_BRIEFS_DIR` invocation that
does it properly.

## The instrument finding, and it is the loudest thing in this session

`image_quality_judge.j2`'s automatic-rejection list names *"a duplicated
AI-activity/workstream module, or any other UI panel repeated when it
should appear once"*. Across the six pilot screens a module was drawn
twice on three of them, and the instruments handled the three differently:

| screen | what was drawn twice | what the instruments said |
|---|---|---|
| 120 Analytics | "Top Course Inquiries" panel, identical content | **caught** — "Duplicate module… appears twice with identical content", scored 6.5, re-rolled, re-roll lost, shipped |
| 119 Analytics | the hero caption "Growth Trends" | **downgraded** — reported as "a slightly thicker border" on a button |
| 120 Knowledge | the whole "AI Suggestion / Review 'Gift Vouchers' entry" module, same title, same headline, same rationale | **missed entirely** — zero issues reported, **scored 8.5, shipped approved** |

The last row is the problem. A screen carrying the exact defect the rubric
promises to auto-reject passed the gate with a clean sheet, and the defect
inspector — whose `duplicated_panel` category exists for this — did not
report it either. Both instruments were held fixed this session and both
are wrong about the same screen, which is the same shape of failure
session 36 fixed under "stop the pipeline contradicting its own
instruments".

This is NOT a console problem. Request 107's analytics screen shipped a
duplicated "Top Artworks" panel at 6.8 before any of this session's work.
It is a corpus-wide miss that three new screens happened to make visible.
It is written up rather than fixed because fixing it means touching the
judge, and that is the one thing this session agreed not to do without a
golden-set run.

## Found and not fixed

- **Archetype selection is not deterministic** (above). Not a defect with
  an obvious fix — it is a property of an LLM classifier — but it means
  no session should describe a class as "landing on X" from one run.
- **No golden brief for the console.** The intake fixture is in
  `golden/intake.py`, but freezing it means freezing a whole v4 set, which
  retires the v1 and v3 control arms. That is a measurement decision with
  a price tag (~$0.05), not a side effect of this session.
- **Placeholder options in anchor flows.** Request 108's selector rendered
  "Guest Artist A" / "Guest Artist B" — the prompt's "never Option A" rule
  wearing a costume. The template now names that pattern explicitly;
  unverified by a funded run.
- **No screen marks itself active** on a request whose navigation is the
  customer's own words, because none of the screen titles is one of their
  items. That is the honest consequence of a header that does not describe
  the screens; the fix is a matching archetype, not a prompt tweak.
- **Request 107's analytics screen** shipped a duplicated "Top Artworks"
  panel at 6.8. Pre-existing, untouched.

## Spend accounting

| what | requests | cost |
|---|---|---|
| Step 1 verification (Jeanne, nav fix live) | 108 | $0.64505 |
| Classification probes, text stages only | 109–118 | $0.11254 |
| Console pilot 1 (Halden & Co) | 119 | $0.75847 |
| Console pilot 2 (Northlight Studio School) | 120 | $0.65164 |
| **Session total** | | **$2.16772** |

Against a $6 budget with a $5 stop line — stopped at **36% of budget** with
every planned deliverable landed. Key bracket $487.5875 → $489.7670
(Δ $2.1795); the ledger is the truth, the key is shared, and the ~$0.012
gap is other traffic on it.

Suite: **354 passed**, from a 308 baseline. One pre-existing test changed:
`test_the_spec_stage_version_carries_the_field` pinned
`UI_SPEC_PROMPT_VERSION == "ui-spec-v3"` by equality, which turns every
later template change into a spurious failure. Rewritten as "v3 or later"
and extended to check what its own docstring claimed — that every frozen
golden bundle was built at a version having the field, and that none is
ahead of the live stage.

Requests 109–118 are classification probes: real ledger rows, no images.
Opening one at `/studio/<id>` honestly says its screens are not on file.
