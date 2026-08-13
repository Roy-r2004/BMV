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

## Found and not fixed

**The active nav item never moves.** All three screens of 130 render
`Home` as the active item. This is session 38's `active_nav_item` fix
behaving exactly as specified — only name an active item when a nav label
matches the screen title — and none of the customer's four labels
(Home/Gallery/About/Contact) matches a demo screen title (Dashboard,
Analytics, Customers). The nav is honoured and the navigation *state* is
now meaningless. Honouring a customer's header and mapping it to the demo's
screens are two different problems and only the first is solved.

**A coherence defect no instrument caught.** 130/Analytics captions the
hero image "Crimson Tide" while the detail panel beside it reads "Azure
Embrace", $2,800, Available — and "Azure Embrace" is the underlined
selection in the picker. Two different paintings named as the same one.
The inspector raised one claim on that screen and the QA judge saw only
"'Crimson Tide' is cut off at the bottom of its card". This is a
cross-panel consistency failure; nothing in the pipeline looks for those.

**The judge calls the portfolio class marketing-like.** 130/Analytics drew
"the overall feel is a bit more like a marketing [page]" as a QA issue at
8.1. That is the same tension session 38 named when it declined to build a
public-site archetype: for this class of customer the honest product
*does* look like a gallery page, and the judge is written to penalise
that. The framing paragraph mitigates it in words; the rubric still docks
it in points.

**Verifier instability on the double-CTA class**, above — v2 confirms and
refutes the same shape on different screens.

## Cost accounting

| item | cost |
|---|---|
| carried from session 38 | $3.80092 |
| harness smoke tests (5 images, both arms) | $0.02560 |
| verifier cost replay, 47 images / 76 claims / 2 arms | $0.18215 |
| request 130, funded run | $0.75268 |
| **total** | **$4.76135** |

$0.23865 to the $5 stop, $1.23865 to the envelope.

## Tests

`docker exec -w /repo/consultant-service bmv-consultant python -m pytest -q`
— **372 passed**, from a 368 baseline. The four new ones
(`tests/test_verifier_cost_ab.py`) pin the two ways the cost harness fails
silently: a mis-parsed `--requests` range measures the wrong corpus and
reports a confident number about it, and a `TEMPLATE` constant that drifts
from the path `defect_check` reads would run both arms against the live
prompt and report a null result for any change whatsoever.
