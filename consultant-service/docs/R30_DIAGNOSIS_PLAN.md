# r30 learns to diagnose

One pipeline. The deciding half becomes a real consultation; the building half
is not touched.

---

## 1. Where we are

r30 already has diagnosis stages. `orchestrator._run_inner` runs:

```
research → analyze → consult → plan → decompose → extras → blueprint
        → technical → playbook → qa_experts → integrity → ui_spec → images
```

`analyze` and `consult` *are* the diagnosis. They are broken in three specific
ways, and nothing else in the pipeline is at fault.

**It never asks anything.** `analyze.analyze_business` (app/pipeline/analyze.py:53)
renders `analyze.j2` from `business_description`, `main_problem`,
`desired_outcome` — read once off the signup form. Whatever the client typed
when they signed up *is* the input. No follow-up, no numbers, no "show me".

**It cannot say no.** `consult.consult` (app/pipeline/consult.py:49) ends with
`result.setdefault("recommended_ai_employees", [])`. The output shape is
already *which AI employees*. And `_fallback` (consult.py:12) hardcodes
"Front-Desk AI + AI Analyst" for every business on earth. There is no field in
which "software is not your problem" can be expressed.

**It never stops.** `_run_inner` is a straight line. The client submits and
returns to a finished PDF. They never see the reasoning before it has been
built on — so a wrong diagnosis costs a full generation and their trust.

## 2. The shape after

```
research → interview → evidence → diagnose → challenge → decide → brief
                                                                    │
                                                          ┌─────────┴─────────┐
                                                    client approves      client says no
                                                          │                   │
                                                          ▼                   ▼
plan → decompose → extras → blueprint → technical →    (build)          back to interview
     playbook → qa_experts → integrity → ui_spec → images
```

Six stages replace two. Everything from `plan` onward is byte-identical.

## 3. The new stages

| # | Stage | In | Out | Fails how |
|---|---|---|---|---|
| 1 | `interview` | what is known so far | next questions, or `[]` | open — falls back to today's static discovery set |
| 2 | `evidence` | uploaded files | claims in the registry | open — no upload is a valid engagement |
| 3 | `diagnose` | claims + answers | 3–5 competing hypotheses | open — degrades to today's `analyze` output |
| 4 | `challenge` | the leading hypothesis | survived / killed | open — unchallenged is marked unchallenged |
| 5 | `decide` | surviving diagnosis | the intervention | open — degrades to today's `consult` |
| 6 | `brief` | all of the above | client-facing brief + gate | **closed** — no brief, no build |

Only the gate fails closed. That is deliberate: every other stage in r30 fails
open so one bad call degrades the package instead of killing it
(orchestrator.py:37-46), and the new stages keep that contract. But a build
that runs without an approved brief is the exact failure this whole change
exists to prevent.

### 1. `interview` — asks until asking stops paying

Replaces the static six-question discovery step. Given everything known, the
interviewer returns the questions whose answers would most change the
diagnosis — and returns `[]` when none would. An empty list is a real answer
and ends the stage; it is not an error.

Hard cap: 3 rounds, 4 questions each. A consultation that will not converge in
twelve questions has a different problem.

### 2. `evidence` — their numbers, not their adjectives

The client attaches what they have: a bookings export, a P&L, a screenshot of
their dashboard. Tables are parsed, figures become registry claims with
`provenance="client_file"` and a source pointing at the sheet and cell.

This is the single highest-value stage. It is the difference between "we hear
you're losing bookings" and "your own export shows 22% of Thursday slots went
unfilled."

### 3. `diagnose` — competing explanations, not one story

Replaces `analyze`. Returns 3–5 hypotheses, each with the claim ids that would
support it and what would refute it. Then each is tested against the registry
and marked `supported` / `refuted` / `untestable`.

`untestable` is a first-class outcome and appears in the brief. "We could not
verify this without your booking data" is worth more to a client than a
confident guess, and it tells them exactly what to send next.

### 4. `challenge` — the stage that stops us agreeing with the client

Two adversarial auditors run in parallel on the leading hypothesis, mirroring
the `qa_experts` panel (qa_experts.py). Their brief is to kill it:

- **the alternative** — what else explains the same evidence?
- **the confirmation check** — did we conclude this because the client
  said it in their intake?

If both fail to kill it, it goes forward marked `challenged`. If either lands,
it returns to `diagnose` once. A hypothesis that survives nothing is reported
as the weak finding it is.

Without this stage the pipeline is a very expensive way to tell clients what
they already believe.

### 5. `decide` — allowed to answer "not software"

Replaces `consult`. Given the surviving diagnosis, the intervention. Its
output keeps `recommended_ai_employees` so stages 7–19 need no change, and
gains:

```json
{
  "central_problem": "...",
  "rests_on": ["claim-04", "claim-11"],
  "intervention_kind": "software | process | pricing | staffing | none",
  "why_not_the_others": "...",
  "recommended_ai_employees": [...],
  "confidence": "high | medium | low",
  "unverified": ["..."]
}
```

When `intervention_kind` is not `software`, the brief is the deliverable and
the build half never runs. The client gets an answer worth more than a
blueprint they did not need — and it costs us one model call instead of
thirteen stages of generation.

### 6. `brief` + the gate

`brief.j2` already exists. It gets the diagnosis, the evidence, the challenge
result, and the decision. The client reads it and either approves — which
starts the build — or pushes back, which returns to `interview` carrying what
they disputed.

## 4. The agents

| Agent | Template | Model | Job | Stops when |
|---|---|---|---|---|
| Interviewer | `interview.j2` *(new)* | ANALYSIS | next 4 questions | returns `[]`, or 3 rounds |
| Extractor | `extract_evidence.j2` *(new)* | ANALYSIS | table → claims | file exhausted |
| Diagnostician | `diagnose.j2` *(new)* | REASONING | 3–5 hypotheses | — |
| Tester | `test_hypothesis.j2` *(new)* | ANALYSIS | supported/refuted/untestable | per hypothesis |
| Skeptic ×2 | `challenge.j2` *(new)* | QA | kill the hypothesis | — |
| Decider | `decide.j2` *(new)* | REASONING | the intervention | — |
| Economist | `economics.j2` *(new)* | ANALYSIS | cost/benefit from cited claims only | — |
| Brief writer | `brief.j2` *(exists)* | ANALYSIS | the client-facing brief | — |

Eight prompts, seven new. They follow r30's existing convention: a `.j2` in
`app/prompts/`, rendered by `app.templating.render`, parsed by
`_shared.extract_json_from_text`, logged through `_shared.log_usage`.

**`REASONING` is a new setting.** `ANALYSIS_MODEL` is `gemini-2.5-flash` —
correct for extraction and formatting, too weak to hold five competing
hypotheses against a claim set. `REASONING_MODEL` defaults to a stronger model
and is used by exactly two agents. Cost note in §8.

## 5. What we reuse

Most of this already exists. That is why it is a smaller job than it sounds.

| Need | Already there |
|---|---|
| Facts with provenance | `registry._claim` — has `provenance`, `approval_status`, `source`, `time_basis` |
| Client figures → claims | `registry.client_fact_claims(ops_numbers, free_texts)` |
| Adversarial panel pattern | `qa_experts.py` — two auditors in parallel, senior-partner pass |
| Numbers must trace to inputs | `qa_numbers.j2` + the integrity layer |
| Fail-open degradation | every stage's `_fallback` |
| Progress to the client | `_shared.emit(db, id, stage, message, pct)` |
| Client-facing brief | `brief.j2` |
| Tailored questions | `discovery.j2` |

Diagnosis claims are written into **the same registry** the integrity layer
already validates. A hypothesis resting on a figure the client never gave will
be caught by machinery that exists today — no new validation to build.

## 6. Frontend

`StudioPage.tsx` is 3,453 lines in one file. The intake is `INTAKE_STEPS`
(line 197) — six steps ending in "Numbers", then submit → progress timeline →
deliverable tabs.

**Kept:** steps 1–2 (Business, Challenge). You need a starting point, and that
data genuinely shapes the analysis. Progress timeline and deliverable tabs are
untouched.

**Replaced:** step 6 "Numbers". Today it asks four pre-tailored questions. It
becomes the conversation — the interviewer asks, you answer, it asks again or
stops.

**New — four components, extracted as files rather than added to the 3,453-line page:**

| Component | What the client sees |
|---|---|
| `Conversation.tsx` | Questions arriving, each with the "why we're asking" line the discovery step already has |
| `EvidenceDrop.tsx` | Drop a spreadsheet; extracted figures appear as cards you can correct or delete |
| `DiagnosisView.tsx` | What we think is wrong · what it rests on · what we could not verify · what we tried to kill it with |
| `ApprovalGate.tsx` | "This is the decision." → Build it / Not quite, because… |

`DiagnosisView` is the product. It is the first screen where the client sees us
think rather than output, and it is the moment the engagement is sold.

**Routing stays as it is on `main`:** `/demo` → `StudioPage`. No new route, no
second page, no parallel UI.

## 7. Milestones

Each ships something visible. Each is independently revertable.

### Done

**M1 — the pause.** `orchestrator.run` stops at `awaiting_approval`;
`run_build` is a separate entry point that re-reads the diagnosis from the
row. `GET /decision`, `POST /decision/approve`, `POST /decision/revise`.
`ApprovalGate.tsx`, and a `decision` act checked BEFORE `is_generating` —
at the gate nothing is generating, and the other order falls through to an
engagement with no deliverables in it.

The approve route claims the run with a conditional UPDATE and only the
caller whose update matched a row starts a thread; eight simultaneous
presses start one build. `revise` appends the objection under
`CORRECTIONS_MARKER`, which `build_engagement_register` already injects.

**M2 — real diagnosis.** `diagnose.py` + `diagnose.j2`, `test_hypothesis.j2`,
`challenge.j2`. `REASONING_MODEL` (gemini-2.5-pro) for the diagnostician
only. `diagnosis_json` on Request. Fed into `consult.j2` so the
recommendation answers the diagnosis rather than running beside it.
`DiagnosisView.tsx`.

Three things the first real runs taught, all fixed:

- **The session is not thread-safe.** `log_usage` inside the worker threads
  left it rolled back, every parallel call after the first failed, and the
  stage reported its skeptics as never having run — which reads downstream
  exactly like a diagnosis nobody could challenge. Usage now comes back with
  the result and is logged after the pool joins, as `qa_experts` does it. An
  ORM attribute read inside a worker is the same unsafe access; those are
  hoisted too.
- **`provider.chat` defaults to `max_tokens=2000`**, and on a reasoning model
  the thinking is spent from the same budget. The first run returned JSON
  that stopped mid-sentence. `DIAGNOSE_TOKENS = 8000`.
- **A killed hypothesis reached the client anyway.** Both skeptics refuted
  the leading explanation and the recommendation still opened by asserting
  it. The re-diagnosis this plan promised is now built: objections go back to
  the diagnostician, one retry, and a second kill is reported honestly rather
  than retried until something survives.

Known calibration gap: the tester completes arithmetic from cited figures and
still labels the result `untestable`. Prompt rules 2 and 3 push against it and
the substance is right either way — the client reads "Could not verify" beside
the real reasoning, which is more honest than a forced "Supported". Not worth
more paid iterations before M4 puts real files in front of it.

**M3 — the honest answer.** `decide.py` + `decide.j2` replace `consult` at
the call site, on `REASONING_MODEL`. Output keeps `consulting_summary`,
`recommended_ai_employees` and `recommended_features` unchanged in name and
meaning, so stages 7-19 never learn the stage was replaced, and adds
`intervention_kind`, `central_problem`, `why_not_the_others`, `confidence`
and `unverified`. New status `advised` and `POST /decision/accept`.

`advised` is NOT terminal. It records "we told you a build would not fix this
and you read it" and nothing else. The first version treated it as closed: the
page told the client to "come back and press Build whenever the picture
changes" while `approve` and `revise` both refused an advised engagement with
a 409 and the page had no button to press. Both routes now accept it, the gate
keeps Build, Not quite and the file drop after "keep the brief", and the copy
no longer promises anything about charges (a commercial fact nobody gave us).

`builds()` decides whether the build half is justified, and its failure mode
is deliberately the OLD behaviour: a missing, unreadable or absent
`intervention_kind` all build. Only an explicit non-software answer withholds
one, and even then the client keeps a "Build it anyway" — they paid for a
build, and deciding for them would be the same paternalism as building
without asking, pointed the other way.

Proved on a bakery at its oven's ceiling, priced 33% under two neighbours,
whose owner asked for an online ordering app:

```
intervention_kind: 'pricing'   -> builds? False
recommended_ai_employees: []   (empty is the correct answer)

"An online ordering app will not fix the problem of selling out; it will
 only create a more formal way to disappoint customers."
"Software would only automate taking reservations for bread you don't have."
```

`EngagementsPage.statusOf` had to learn both new states: they fell through to
the same green "Ready" badge as a finished build, so a decision nobody had
answered looked complete and an advisory promised deliverables behind it.

**M4 — their numbers.** `evidence.py` + `extract_evidence.j2`, `evidence_json`
on Request, `GET/POST /evidence` and `DELETE /evidence/{id}`,
`EvidenceDrop.tsx`. Reads .xlsx, .csv/.tsv and .pdf.

**The property the stage exists for:** a figure from a file must be traceable
to the cell it came from, and that must be CHECKABLE. So the work is split —
parsing is deterministic and a model never gets to say what is in the file;
the model only says which figures matter and what they mean, citing a cell.
Every citation is then checked against the parsed grid, and a figure whose
cited cell does not hold it is dropped rather than kept with a caveat. A
hypothesis may rest on these, and "probably in their file somewhere" is not
evidence.

Offered five figures in a check — two good, one real number cited from the
wrong cell, one absent from the file, one in a nonexistent table — it keeps
two and drops three.

**Where the drop zone lives is the design.** Not the intake form: at the gate,
under the sentence where the diagnosis has just said what it could not verify.
A file request the client understands the reason for. Uploading re-opens the
engagement through the same door `revise` uses — one path that re-diagnoses,
not two.

One bug worth remembering: `_render_table` printed `TABLE: <name>` and the
prompt asked for the name "exactly as printed above", so the model returned
`"TABLE: Bookings by month"` as the name. Every cell reference was correct and
all 23 were thrown away. Names are now quoted, and `_resolve_table` is loose
on the name and strict on the cell — the right way round, since the sheet
title is a label a model can reasonably echo back differently while the cell
is the thing under verification. Where a name resolves to nothing the cell is
searched across sheets, and only an unambiguous single hit counts.

After the fix, on a sheet seeded with an order-id column, a postcode and a
phone number: 7 figures kept, 0 rejected, every trap left alone.

**M5 — the conversation.** `interview.j2` + `POST /api/discovery/interview`
replace the one-shot tailored set; `Conversation.tsx` replaces the static
Numbers step. Rounds accumulate on screen so the client can change what they
already said. Capped at `INTERVIEW_MAX_ROUNDS` × `INTERVIEW_MAX_PER_ROUND`,
enforced server-side, because the model is the thing being capped.

`done` is authoritative and goes true when the model has enough, when the cap
is reached, AND when a round fails — a failed call must END the interview
rather than trap the client on a step that will not advance. Round 1 falls
back to the static set, so the worst case is the old behaviour.

Two real defects the first live run exposed, both fixed:

- **It interviewed to scope the owner's solution.** It asked the
  receptionist's working hours in all three rounds and never once asked about
  rooms or capacity. The cause was `build_engagement_register`, which says
  "The capability: We miss evening enquiries — scope everything to that
  capability", drowning the constraint rule. The prompt now separates the two
  explicitly: the register scopes what we might BUILD, never what we may ASK,
  because the diagnosis has to be able to conclude the client's own idea is
  the wrong answer, and it can only do that with numbers the interview went
  and got.
- **Skipped questions were invisible.** Only ANSWERED pairs reached the
  model, so an unanswered question came back every round under a fresh id.
  The client now sends every label it has put to them, and `_repeats`
  compares content words rather than strings — a round-2 question returned in
  round 3 with a clause bolted on the front was word-for-word identical apart
  from a contraction, and sailed past both equality and substring matching.

After the fix, round 1 opens on the ceiling and reads their own description
back — "You mention you have two rooms. Is each room used by a separate
physio at the same time?" — and round 2 follows their answers: "You mentioned
your two physios provide about 80 sessions a week. If both were fully booked,
what is the maximum they could deliver?" All four things a diagnosis needs to
tell explanations apart (a price, a volume, a ceiling, something that leaks)
were collected.

`_sanitize_ops_numbers` capped the intake at 8 pairs, from when one fixed
round asked at most 6. A full interview collects twelve, so the cap would
have silently discarded the last four answers the client typed — after asking
for them. It is now derived from the interview settings, and
`tests/test_discovery.py` asserts both halves: that the bound exists, and
that it never cuts into a complete interview.

All five are built. The pipeline now asks until asking stops paying, reads
the files they send, forms competing explanations and tests them against
their own figures, attacks the survivor from two angles, names the KIND of
intervention the cause needs — and stops for the client's approval before a
single stage of generation runs.

Cost as built: 2 reasoning calls worst case (the retry), 3–5 tester calls and
2 skeptics, on top of analyze and consult. A clean pass logged 10 model calls;
a pass that used its retry logged 17.

**M6 — the handoff: the build is written from the diagnosis, not from the
request.** Until now the build half read three things — a summary paragraph, a
list of AI employees, a list of features — and never saw WHY. A client whose
diagnosis said "you are at your ceiling, the constraint is price" and who then
chose to build anyway got documents written from their original request and a
summary that argued against it. Nothing made the documents agree with the
finding.

`handoff.for_build(req)` words the diagnosis as constraints — the cause, what
actually fixes it, the client's own figures it rests on (cited by id, one line
per FIGURE not per mention), the explanations ruled out, what is still
unverified, the confidence — and `build_engagement_register` appends it to the
register. That paragraph is already rendered by every build prompt (plan,
decompose, blueprint, technical plan, playbook, procedures, journey,
organisation, governance, checklists, pilot SOP, the expert review), so
seventeen prompts learn the finding through one seam and none is edited. Seven
build-stage call sites pass it; the stages that run before or during the
diagnosis deliberately do not — they must not be handed a conclusion that does
not exist yet.

When the client builds software the diagnosis did not recommend, the block
also says how to write about that honestly: open the decision section with what
the diagnosis found, describe the software as SUPPORTING the real fix, justify
every module by what it does for the diagnosed cause, and never by "more
customers" or revenue the business cannot serve.

Uploaded-file figures had to be made legal for the build. `registry.py`
validates every claim's provenance against a closed set of four values and
reports anything else as an error; the file figures were tagged `client_file`,
so they would have failed validation the moment they reached the registry
(proved: `CE-02: unknown provenance client_file`). They are now `client_input`
with `origin: "file"`, added to the registry through
`build_registry(extra_claims=)` and listed in `_format_owner_numbers` — the list
the decomposition computes from and the number auditor checks against. The
registry also de-duplicates its free texts, because the opening paragraph can
now be the description AND the problem, which registered every figure in it
twice.

## 8. What does not change

- **Stages 7–19** — `plan`, `decompose`, `extras`, `blueprint`, `technical`,
  `playbook`, `qa_experts`, `integrity`, `ui_spec`, `images`. Untouched.
- **The deliverables** — same blueprint, same technical plan, same playbook,
  same screenshots, same exports.
- **`app/engine/`** — not deleted, not extended. It sits where it is. Its
  question-loop design informs `interview.j2`; its code is not imported.
- **Routing** — `/demo` stays on `StudioPage`.
- **No deploy.**

## 9. Open decisions

1. **The gate, hard or soft.** Recommended: hard — the client presses Build.
   It is the best sales moment in the product. Soft (auto-proceed after a
   countdown) is available if you want the funnel frictionless.

2. **`REASONING_MODEL` cost.** Two agents on a stronger model adds roughly
   $0.05–0.15 per engagement over today. Against it: a wrong diagnosis
   currently costs a full thirteen-stage generation. Recommended: take the
   cost, cap it by running the strong model only on `diagnose` and `decide`.

3. **Non-software outcome.** When `decide` answers "not software", the client
   paid for a build and gets a brief. Recommended: deliver the brief, charge
   nothing, offer the build when the real problem is fixed. This is a business
   call, not a technical one.

---

## Recovery

Parked, not deleted:

- `stash@{0}` — expert + agent work, 3,919 insertions across 25 files
- branch `consultancy-intelligence-ux` @ `efa8d02` — the committed
  consultation work
- `app/engine/` on `main` — untouched

Baseline for this plan: `main` @ `25d9739`, working tree clean.
