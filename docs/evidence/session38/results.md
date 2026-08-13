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

**Would a customer reading this result page understand what they were just
shown?** Now yes — but because of the paragraph, not the screens. The
header is theirs; the product is still a back-office analytics tool, and
the page now says so in the first thing above the screenshots. That is the
honest answer for this class and it is the one that ships.

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

### Investment system — nothing built, and confirmed with screens

No code. The brief predicted this class already had a home, the probes
agreed, and a funded run closes it out — because "build nothing" is a
claim about the OUTPUT, and the brief asked for screens and a link for
each of the three classes.

**[/studio/128](http://localhost:5173/studio/128)** — $0.65018, 238s, 0
failed calls. Intake: *"I run a small investment firm. I need an
investment system to manage client portfolios, track performance against
benchmarks and see risk in one place."* Landed on `analytics-dashboard`,
exactly as the brief predicted.

| screen | qa | text-truth | notes |
|---|---|---|---|
| Analytics (anchor) | 7.5 | pass | strategy → risk band → allocation selector, real Strategy Details panel |
| Dashboard | 9.2 | pass | client meetings, portfolio alerts, an intraday S&P chart |
| Customers | 8.7 | pass | five named clients with AUM, strategy and risk posture |

Nothing duplicated on any of the three, and the correct navigation item is
active on each — the first funded set where that is true end to end, since
this archetype's screen types ARE its navigation. Would a customer
understand it? Yes: it is recognisably the investment system they asked
for.

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

**Would a customer reading this result page understand what they were just
shown?** Yes, immediately and without help. The first screen is a
conversation with their own customers about their own services — the one
class where the demo needs no explaining at all.

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

## The instrument finding — counted, not sampled

`image_quality_judge.j2`'s automatic-rejection list names *"a duplicated
AI-activity/workstream module, or any other UI panel repeated when it
should appear once"*, and the defect inspector carries a
`duplicated_panel` category. Three pilot screens looked like misses, so
rather than report three anecdotes the whole artifact was counted: **all
33 screens shipped by requests 100–120, every one of the 21 that reported
no duplication opened and read.** Full table in
[`duplication-census.md`](duplication-census.md).

The result is narrower and more useful than "the instruments are
unreliable":

- **Panels, modules, cards, rows and controls: 8 caught, 1 missed.** The
  instruments are good at this, and specific — 104's claim carries pixel
  coordinates, 107's names the table ("two identical 'Top Artworks'
  tables"), 106's calls its duplicated module "a critical flaw".
- **Text painted on top of an image or a chart: 0 caught, 2 missed.**

The one panel-level miss is the expensive one: request 120's Knowledge
screen drew the entire "AI Suggestion / Review 'Gift Vouchers' entry"
module twice — same title, same headline, same rationale — and **shipped
approved at 8.5 with zero issues reported by either instrument.** That is
the exact defect the rubric promises to auto-reject.

The two overlay misses point somewhere specific. A duplicated hero caption
(119 Analytics, "Growth Trends" twice on one image) and a duplicated chart
annotation (119 Knowledge, "+150% Week 1 → Week 4" twice on one chart) are
painted over imagery rather than laid out as panels — and the inspector's
category asks for "the same panel, card, button pair, label or block of
information", which an overlay caption is none of. The aesthetic judge did
see one of them and described it as "a slightly thicker border".

**A correction to an earlier draft of this document:** it claimed request
107's duplicated "Top Artworks" panel was a missed defect and that the
problem was corpus-wide. The census shows the opposite — that one was
caught and named precisely. The blind spot is overlay text, not structure,
and it would not have been visible without counting all 33.

### …and then it was measured, and the diagnosis was wrong

The obvious fix was to widen the inspector's category to cover overlay
text. It was written, and measured on the 29 labelled screens before
landing (`scripts/inspector_ab.py`, both arms through the real
`inspect_call`/`verify_call`, same bytes, same specs). **It failed:**
inspector v2 caught 2 where v1 caught 3, and still missed both overlay
cases it was written for. It was reverted. That is what the measurement
discipline is for.

The failed A/B also showed both arms confirming far fewer duplications
than the stored verdicts implied — which meant the census had been reading
mostly the *aesthetic judge's* free-text remarks, not the defect
instrument's output. So the next question was cheap and obvious: does the
inspector never SEE duplication, or does the verifier kill what it sees?

**The inspector raises a correct `duplicated_panel` claim on 9 of 11
genuinely duplicated screens** ($0.0133 to find out), including both
supposed misses, in v1, without any change:

> "The 'Growth Trends' button is drawn twice on the same image card element."
> "The panel 'AI Suggestion' with content 'Review 'Gift Vouchers' entry' is drawn twice."

It saw them. The verifier threw them away — confirming **3 of 10 true
claims**. And the refutation reasons name the mechanism exactly:

| refuted | stated reason |
|---|---|
| 101/Dashboard, 106/Analytics | *"relies on reading text content … outside the pipeline's jurisdiction"* |
| 107/Analytics | *"one of the panels includes a small difference in the last entry"* |
| 120/Analytics | *"the second panel displays 'Watercolor Fundame…' while the first displays…"* |
| 106/Schedule | *"the second instance of the panel contains additional information"* |
| 119/Analytics | *"there are two distinct 'Growth Trends' buttons"* |

Two rules in `image_defect_verifier.j2` were colliding with the category
they were meant to police. *"A similar-but-different pair is not a
duplicate"* acquits every real case, because an image model's duplicate is
never byte-identical — one copy is always truncated or restyled, and that
difference is the artifact, not a defence. And the text-claim ban was
being applied to the ACT OF NAMING which panel was duplicated. The last
row is simply circular.

### Verifier v2 — measured in both directions, and it ships

Both carve-outs are narrow; the refute-by-default stance is untouched.
Measured on the 17 true duplication claims plus false claims harvested
from clean screens:

| | true confirmed | false confirmed |
|---|---|---|
| v1 | **5 / 17** | 0 / 1 |
| v2 | **12 / 17** | 0 / 1 |

Recall more than doubles with no loss of precision on the adjudicated set.
$0.0536 to measure. Landed as `image-defect-verifier-v2`.

### The fix, verified live — [/studio/129](http://localhost:5173/studio/129)

Salon brief, the same intake that produced request 102 before the fix.
**$0.65490, 282s, 5 image calls.** The anchor is a tool screen, so it is
exactly the shape that carried the defect.

**"Confirm Booking" is rendered once**, in the Booking Summary panel where
the flow commits — the top bar carries no button at all. Request 102, same
brief, pre-fix, rendered it in both places. That screen scored **9.2 with
zero reported issues**.

The run doubles as the first cost reading under verifier v2: $0.65490
against the eight-run corpus mean of $0.634, with the usual two-candidate
anchor and one follow-up re-roll. One run is not a rate, and watching this
number is the next session's first job — but the stricter gate did not
visibly blow up regenerations on its first outing.

## Found and not fixed

- **Archetype selection is not deterministic.** Not a defect with an
  obvious fix — it is a property of an LLM classifier — but it means no
  session should describe a class as "landing on X" from one run.
- **Placeholder options in anchor flows.** Request 108's selector rendered
  "Guest Artist A" / "Guest Artist B", and 104's client list carried
  "Endowment Fund XYZ" and "Jane Doe Trust". The template now names that
  pattern explicitly; unverified by a funded run.
- **A scaffolding leak is still reachable.** Request 105's analytics hero
  carries a chip reading "Floating Labels" — prompt vocabulary drawn as UI.
- **No screen marks itself active** on a request whose navigation is the
  customer's own words, because none of the screen titles is one of their
  items. The honest consequence of a header that does not describe the
  screens; the fix is a matching archetype, not a prompt tweak.
- **Verifier v2's cost consequence is unmeasured.** A stricter gate buys
  regenerations, and the change landed after the last funded batch. First
  job of the next session, and it is a reading, not an experiment.
- **Two hero captions where the spec supplies one.** Requests 104 and 128
  each render two different overlay labels on one image ("Application" /
  "Trading Apps"; "VIP client" / "Client Partnership"). Not duplication —
  invention — and a different fix from anything here.

## Spend accounting

| what | requests | cost |
|---|---|---|
| Step 1 verification (Jeanne, nav fix live) | 108 | $0.64505 |
| Classification probes, text stages only | 109–118 | $0.11254 |
| Console pilot 1 (Halden & Co) | 119 | $0.75847 |
| Console pilot 2 (Northlight Studio School) | 120 | $0.65164 |
| Investment class, third deliverable | 128 | $0.65018 |
| Tool-screen CTA fix, verified live | 129 | $0.65490 |
| v4 golden set, 7 briefs, no images | — | $0.07190 |
| Inspector A/B, both arms over 29 screens | — | $0.18030 |
| Inspector raw-claim probe | — | $0.01330 |
| Verifier refutation reasons | — | $0.00900 |
| Verifier A/B, both directions | — | $0.05360 |
| Duplication census (33 screens, eyes + stored verdicts) | — | $0 |

Every instrument measurement above re-judged images already on disk —
that is why a full two-arm before/after over a labelled corpus costs less
than a third of one generation, and it is the reason an instrument change
could be measured at all inside this budget.

Requests 109–118 are classification probes: real ledger rows, no images.
Opening one at `/studio/<id>` honestly says its screens are not on file.

**Session total: $3.80092** — $3.54472 of funded requests plus $0.25620
of instrument measurement. Against a $6 budget with a $5 stop line, that
is **63%**, with every job in the brief landed plus three defects the
brief did not know about. Key bracket $487.5875 → $491.4001 (Δ $3.8126);
the ledger is the truth, the key is shared, and the ~$0.012 gap is other
traffic on it.

Suite: **368 passed**, from a 308 baseline. Two pre-existing tests changed,
both because the behaviour they pinned was replaced rather than because
they were wrong: `test_the_spec_stage_version_carries_the_field` pinned the
prompt version by equality (now "v3 or later", and extended to check what
its docstring actually claimed), and `test_the_top_bar_button_is_named_not_described`
pinned the top-bar CTA that turned out to be the duplication (now pins that
no button is asked for and the label appears exactly once).
