# Session 39 — what verifier v2 costs, and the first funded run behind it

Session 38 shipped a stricter defect gate and wrote that request 129 was
"the first cost reading under verifier v2". It was not. This session
established that, measured the cost question a way that is actually
affordable, and put the first real funded run behind the change.

Spend: **$0.96043**, against a $6 envelope with a $5 stop. Running total
**$4.76135**. Bracket: OpenRouter `total_usage` $491.4001 → $492.3626,
Δ $0.9625 on a shared key — $0.002 of drift against the ledger.

## The correction that started the session

`docs/evidence/session38/results.md` claimed request 129 ($0.65490) was
the first cost reading under `image-defect-verifier-v2`. The file mtimes
say otherwise: 129 ran at **06:48**, `verifier-v2-measurement.json` was
written at **09:46** and `defect_check.py`'s version bump at **09:48**.
The verifier was still v1 when 129 went through.

So session 38 shipped a stricter gate with **zero funded runs behind it**,
and the "one data point" I reported at the end of that session did not
exist. The claim is corrected in place in session 38's results.md.

## JOB 1 — the cost of verifier v2

### Why this was not measured by running generations

The obvious reading — run a few more and watch `by_purpose.image` — cannot
work at any price the project would pay. The eight-run corpus (requests
96–103) has mean **$0.63370**, sd **$0.13495**, range $0.385–$0.761, at
**5.0 images per run**. The effect being looked for is at most a fraction
of one image. Detecting a +$0.04 shift against that sd at 80% power needs
**~175 runs per arm, about $111 a side**.

Instruments re-judge existing screenshots, so the same question costs
$0.18 as a replay. That is the whole argument for the method, and it is
the same argument that paid for session 38's instrument work.

### The measurement

`scripts/verifier_cost_ab.py` (new). Every image requests 104–129 actually
produced — **47 images, shipped screens AND the candidates the pipeline
discarded**, because scoring only shipped screens measures a set already
filtered for cleanliness. One inspector pass raises **76 claims**; both
verifier arms then score *the same claims*, since the inspector did not
change and re-running it per arm would only inject its own sampling noise
into a paired comparison. Arms differ solely in which template
`image_defect_verifier.j2` resolves to.

`docs/evidence/session39/verifier-cost-ab.json`. Cost: inspector $0.05155,
v1 arm $0.06426, v2 arm $0.06634 — **$0.18215** total.

| | v1 | v2 |
|---|---|---|
| confirmed claims | 31 / 76 | **34 / 76** |
| images carrying ≥1 confirmed defect | 24 / 47 | **24 / 47** |
| screens where *every* image is dirty | 6 / 27 | **9 / 27** |
| shipped screens dirty | 9 / 27 | 12 / 27 |
| `duplicated_panel` | 5 | **8** |
| `malformed_data_display` | 7 | 9 |
| `non_app_chrome` | 7 | 7 |
| `blank_or_unlabelled` | 6 | 4 |
| `clipping_or_truncation` | 6 | 6 |

**The image-level rejection rate is identical — and that is the rate that
spends money.** A confirmed defect sets `approved=False` (qa.py); a screen
with no approved candidate buys at most one regeneration; a regeneration is
one image. 24 of 47 both arms.

The 24 are **not the same 24**: five images in, five out. Rolled up to
screens, "every candidate dirty" moves 6 → 9 of 27. Taken at face value
that is **+0.33 images per run, +$0.0404, +6.4%** — the upper end of what
this measurement can support, and a third of one sd of the corpus it
would have to be detected in.

### What actually moved, and it is not all noise

Nineteen individual verdicts flipped, twelve toward confirmed and seven
away. The **gains are systematic and quote the exact v1 rules session 38
diagnosed**:

- *120/Analytics, 'Avg. Response Time' duplicated.* v1: "the claim relies
  on reading the text content of the panels, which is outside this
  pipeline's jurisdiction." v2: "the two rightmost KPI cards in the top row
  are both titled 'Avg. Response Time' and display the same value '5s'."
- *104/Analytics, 'Apply Model' twice.* v1: "they are located in different
  contexts within the interface, thus not con[stituting a duplicate]."
  v2: "appears in the top right corner and also within the 'Core Alpha
  Allocation' panel, serving the same function."

Both carve-outs are doing precisely the job they were written for.

The **losses are one class**: the header-vs-panel double CTA — 'Book This
Slot' (106), 'Request Info' (107), 'View Painting' (108) — all refuted by
v2 on the "two panels doing DIFFERENT jobs" clause. But v2 *confirms* the
identically-shaped 'Apply Model' (104) and 'Apply Strategy' (128). **v2 is
internally inconsistent on that one class**, which is instability, not a
principled regression.

It also matters less than it looks: the double CTA is a *pipeline* defect
that session 38 removed at source in `prompt_builder`, verified on 129 and
again on 130 below. The class is leaving the corpus.

### Answer

**Verifier v2 costs between $0 and about +$0.04 a run — at most ~6%, well
inside a corpus sd of $0.135.** It buys a materially better duplication
gate for that. No tuning back is warranted, and the cost line does not
need watching run-by-run: the effect is smaller than the noise any such
watch would be made of.

## Request 130 — the first funded run under verifier v2

[/studio/130](http://localhost:5173/studio/130) — **$0.75268, 6 images,
2 regenerations**, both on follow-up screens; the anchor's two candidates
are by design. Config at target: 3 screens, 2 dashboard candidates, 1
secondary, QA_MIN_SCORE 8, MAX_REGENERATIONS 1.

The brief is the owner's own verbatim intake, the one that produced
request 108: *"I wanna showcase my paitings, with a dashboard that
contains home, gallery, about, contact"*. Same brief pre-v2 (108) was
$0.64505 at 5 images. One run is not a rate and this one sits +0.88 sd
above the corpus mean — it neither confirms nor contradicts the replay.

**Fidelity, checked in the pixels and not only in the spec:**

- **The four-item header is honoured exactly** — `Home | Gallery | About |
  Contact`, that order, on all three screens, in the rendered images.
  Text-truth passed on all three.
- **Placeholder names are gone.** 108's Analytics spec contained "Guest
  Artist A" and "Guest Artist B". 130 has Olivia Chen, Marcus Bell, Sophia
  Lee, real painting titles, real referrer sources. The one borderline
  string is `{"name": "Buyer"}` in a Dashboard activity row — a role label,
  not a fabricated person.
- **No double CTA** on either tool screen. The `prompt_builder` fix holds
  on a second archetype and a second brief.
- **No scaffolding leak.** The AI-insight chips read "High value", "New
  inquiry", "Prompt reply" — product vocabulary, not prompt vocabulary.
- **The chart is clean.** "Inquiry Conversion", ticks at 0/2/4/6 evenly
  spaced and correctly placed against values 3/4/2/5/3/6. The session-36
  chart tail did not appear on this run.
- **The framing paragraph works, and works retroactively** — it is composed
  server-side per request with no model call, so /studio/108 renders it
  too. The portfolio trigger fires: "It is not your public website."

## Found on run 130

Two of these were fixed the same session, below. One was not.

**The active nav item never moves.** *(fixed — `ui-spec-v5`)* All three screens of 130 render
`Home` as the active item. This is session 38's `active_nav_item` fix
behaving exactly as specified — only name an active item when a nav label
matches the screen title — and none of the customer's four labels
(Home/Gallery/About/Contact) matches a demo screen title (Dashboard,
Analytics, Customers). The nav is honoured and the navigation *state* is
now meaningless. Honouring a customer's header and mapping it to the demo's
screens are two different problems and only the first is solved.

**A coherence defect no instrument caught.** *(fixed — `ui-spec-v5`)* 130/Analytics captions the
hero image "Crimson Tide" while the detail panel beside it reads "Azure
Embrace", $2,800, Available — and "Azure Embrace" is the underlined
selection in the picker. Two different paintings named as the same one.
The inspector raised one claim on that screen and the QA judge saw only
"'Crimson Tide' is cut off at the bottom of its card". This is a
cross-panel consistency failure; nothing in the pipeline looks for those.

**The judge calls the portfolio class marketing-like.** *(NOT fixed — needs an owner decision)* 130/Analytics drew
"the overall feel is a bit more like a marketing [page]" as a QA issue at
8.1. That is the same tension session 38 named when it declined to build a
public-site archetype: for this class of customer the honest product
*does* look like a gallery page, and the judge is written to penalise
that. The framing paragraph mitigates it in words; the rubric still docks
it in points.

**Verifier instability on the double-CTA class**, above — v2 confirms and
refutes the same shape on different screens.

## The two fixes — `ui-spec-v5`

### The navigation state

Matching a screen title against the customer's labels only ever works when
their words happen to be the archetype's words. Matching them by
*similarity* is the one thing not to do (brand-variant specs: fuzzy
rewriting is how invented strings get in). So the model, which already
sees both the honoured list and the screen's role, declares the mapping in
a new spec field `active_nav`, and code validates it to death:

- it must be a member of that screen's `navigation`, or it is dropped —
  request 107's invented sixth header item cannot return by this road;
- **no two screens may claim the same item**, which is the session-39
  defect written as an invariant the field that fixes it cannot undo;
- declaring nothing stays legal, because "this screen is none of your
  sections" is honest and banning it would be a new rule with its own
  blast radius.

`active_nav_item` prefers the declared value and keeps the title match as
the fallback, so every frozen golden bundle still behaves as before.

**Verified on real model output, not only on hand-built specs.** The v5
golden set (`golden/briefs-v5`, seven briefs, $0.0659): **20 of 21 screens
declare an active item, every one a member of its own navigation, no brief
marking the same item twice.**

| brief | screen 1 / 2 / 3 |
|---|---|
| hedgefund | Overview \| Portfolios \| Reporting |
| hvac | Home \| Schedule \| Reports |
| retail | Sales \| Home \| Subscriptions |
| assistant | Conversations \| *(none)* \| Knowledge |

`hedgefund`, `hvac` and `retail` are the request-130 shape — nav labels
that are not screen titles — and all three now resolve to three distinct
items instead of collapsing onto the first. `assistant/analytics` declares
nothing, correctly: that console's menu is Inbox/Conversations/Clients/
Knowledge/Settings and an analytics screen is none of them.

### The hero's subject

On a tool screen the hero is a photograph *of* the thing the detail panel
describes, so `_apply_hero_subject_invariant` forces `hero.caption` to
`concept.detail.title`, falling back to the last step's `selected`. It runs
before the brand invariant so a replaced caption still gets its brand
widened, and it leaves dashboard heroes alone — those are scenes, and
renaming one to a table row would be a new defect.

Honest limit: all six tool screens in the v5 set were **already coherent**,
so the golden rebuild shows the invariant harms nothing but does not show
it firing. The firing case is unit-tested against request 130's exact
values ("Crimson Tide" beside "Azure Embrace").

### What is NOT fixed

**The judge.** Criterion 4 grades data-visualisation craft and docked
130/Analytics for reading "more like a marketing page" — on a brief where
a gallery is the correct answer. Changing it breaks score comparability
with every screen in every prior session and needs its own before/after
over a labelled set. Left alone, flagged, and it needs an owner decision
and a budget this session does not have.

**Neither fix has a funded image run behind it.** Both deterministic halves
are unit-tested and the prompt half is verified across seven briefs of real
model output, but nothing has yet drawn a screen under v5. That is the
first thing to spend on next.

## Request 138 — the funded run under v5

[/studio/138](http://localhost:5173/studio/138) — **$0.78697, 6 images**,
same brief again. The service was restarted first: uvicorn runs without
`--reload`, so the live process was still holding v4 and this run would
otherwise have paid to test the old code.

**The hero fix is verified end to end.** The bug reproduced — the model
again captioned the hero with the wrong painting — and the invariant
caught it before anything was drawn:

    hero caption renamed to the screen's subject: 'Tuscan Sunset' -> 'Morning Mist'

In the rendered Analytics screen the caption reads "Morning Mist", the
detail panel reads "MORNING MIST", and the picker's selected row reads
"MORNING MIST". On request 130 those three were three different paintings.
The fix is load-bearing, not cosmetic.

**The navigation fix was inert on this brief.** Only 1 of 3 screens
declared an item (Dashboard → Home); Analytics and Customers declared "".
The prompt gives "a screen browsing the catalogue for a header containing
'Gallery' is Gallery" as its worked example and the model still declined
to apply it to a screen whose `screen_type` is "analytics". The declared
value that did exist was honoured, so the mechanism works; the model's
willingness to use it does not survive contact with this brief.

**Silence is not neutral — the assumption behind the design was wrong.**
"Declaring nothing is honest" was the reasoning for letting a screen
abstain. On the Customers screen, which declared "", the image model
marked **Gallery** active — on a screen of collectors, patrons and contact
counts. Where the spec says nothing the model does not leave the header
alone; it fills the vacancy, exactly as an untitled panel gets a heading
invented for it. Abstention needs to become an explicit instruction, not
an absence.

### The serious one: the honoured header lost the customer's word

The Dashboard renders **`Home | Analytics | About | Contact`**. The
customer asked for Gallery. It is not an extra item — the count is still
four — it is a **substitution**, and every gate passed it:

- `text_truth` returned `passed: true, checked: 6, failures: []`, because
  it checks whether each expected string is present *anywhere* on the
  screen, and "Gallery" is present twice on that Dashboard — "GALLERY
  VIEWS" in the KPI strip and "Gallery Showcase" in Upcoming Exhibitions.
  The header lost the word; the screen did not.
- The spec-level coherence guard compares specs, not pixels, and all three
  specs carry the identical four items.
- A count check would not fire either.

The anchor was Analytics and it drew the header correctly. The Dashboard
is a *follow-up*, drawn with the anchor attached as a reference image and
told "Navigation items — placed exactly where the attached image places
them", and it still swapped one. Session 38 recorded this class as
undetectable without positional transcription; session 39 shows it is
worse than recorded, because a substitution hides behind any displaced
word that happens to appear elsewhere on the screen.

### Blast radius

QA 7.5 / 7.0 / 7.5 (mean 7.33) against request 130's mean 8.27, same brief
and config. Flagged at the time as "the wrong direction". **Put in corpus
context it is an unremarkable draw**, and the original flag over-weighted
it — corrected here.

Twenty-five completed runs from 90 on: mean of run-means **8.228**, sd
**0.489**. 138 sits at −1.83 sd, second-lowest of 25. But the same brief
re-run changes by that much on the seed alone:

| brief | runs | spread |
|---|---|---|
| Hartwell & Grey | 8.50, 8.03, 7.20, 8.47 | **1.30** |
| Jeanne Art | 7.63, 8.03, 8.27, **7.33** | 0.94 |
| Northgate | 8.50, 7.57, 8.40 | 0.93 |
| Lumière | 8.43, 9.20, 9.13, 8.63, 8.70 | 0.77 |
| Meridian | 8.27, 8.10, 7.80, 7.83 | 0.47 |

Hartwell moved 1.30 points across four runs with no code change between
them. 138's 7.33 is the low end of a brief that has always run low — the
gallery brief's four-run mean is 7.82 against a corpus 8.23. The last six
runs average 8.222, which is the corpus mean to three decimals.

**The consequence for method: the aggregate QA score cannot adjudicate a
generator change at any affordable N.** Within-brief sd is ~0.4, so
detecting a 0.3-point regression needs ~28 runs an arm, ~$21 a side — the
same wall the verifier cost question hit. Judge scores are for tracking
the corpus, not for accepting or rejecting a prompt version. What settles
v5 is the deterministic checks, which are free and unambiguous: does the
rendered header match `spec.navigation`, and does the hero caption match
its detail panel. So v5's image-quality effect is **unmeasured and
probably unmeasurable this way** — not "harmful", and not "neutral".

## Cost accounting

| item | cost |
|---|---|
| carried from session 38 | $3.80092 |
| harness smoke tests (5 images, both arms) | $0.02560 |
| verifier cost replay, 47 images / 76 claims / 2 arms | $0.18215 |
| request 130, funded run | $0.75268 |
| v5 golden set, 7 briefs, text stages only | $0.06590 |
| request 138, the v5 verification run | $0.78697 |
| **total** | **$5.61422** |

Past the $5 checkpoint (reported and authorised), $0.38578 to the envelope.

## Tests

`docker exec -w /repo/consultant-service bmv-consultant python -m pytest -q`
— **414 passed**, from a 368 baseline. Four
(`tests/test_verifier_cost_ab.py`) pin the two ways the cost harness fails
silently: a mis-parsed `--requests` range measures the wrong corpus and
reports a confident number about it, and a `TEMPLATE` constant that drifts
from the path `defect_check` reads would run both arms against the live
prompt and report a null result for any change whatsoever. The rest cover
the two fixes: nine on the invariants themselves (including that an
off-menu declaration is dropped rather than added, and that two screens
cannot both claim one item), four on `active_nav_item`'s precedence and
its fallback for pre-v5 specs, and the v5 golden set parametrised over
seven briefs.
