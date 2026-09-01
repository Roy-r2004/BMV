# Real-model benchmark proposal — universal consultancy engine

Prepared before any paid call. Nothing runs until you approve.

## 1. Why the fake cannot answer this

Every result so far comes from a case-blind structural oracle. That design is what makes divergence
meaningful — differences come from the input, not a script — but a fake that may not read the case cannot
reason about it. It can prove a recommendation *selects* an option, *cites* criteria and *does not copy* a
fact. It cannot prove the advice is worth paying for. That is the whole purpose of this benchmark.

## 2. Calibration first — two cases

| # | Case | Why this one |
|---|------|--------------|
| 1 | `acquisition-integration-nordvik-baltic` | Norway/Estonia acquisition, 54 staff transferring, two ERPs, an earn-out that misaligns the seller, a change-of-control clause on 38% of the target's revenue, and EU biocidal re-registration at 9–14 months. Densest interlocking constraints of the fifteen; the one most likely to expose shallow reasoning. |
| 2 | `adv-symptom-not-problem` | Client demands a CRM. The dossier shows churn concentrates in year one and is driven by comp design, and a previous Salesforce was abandoned for exactly the reason a new one would fail. Tests whether the engine reframes the request or builds what it was asked for. |

These two answer a single question: **does it reason like a consultant, or does it produce well-formed
structure with nothing inside?** If the answer is no, the broader run is money wasted.

## 3. Models

| Role | Model | Reason |
|---|---|---|
| Consultant (engine) | `anthropic/claude-sonnet-4` | Strongest reasoning-per-dollar for long structured work; the engine's `structured_call` retries once on schema mismatch, which needs a model that self-corrects. |
| Simulated client | `google/gemini-2.5-flash` | Cheap, and its job is narrow: play a persona and reveal a dossier fact only when a question genuinely touches it. |
| Independent grader | `anthropic/claude-sonnet-4`, fresh context, rubric only | Never the model that produced the work; sees the transcript and deliverables, not the engine's internals. |

Rationale for splitting: the client is ~40% of calls but needs no reasoning depth, so paying reasoning
prices for it doubles cost for nothing. Grading in a fresh context prevents self-marking.

## 4. Cost

Measured, not estimated: the 15 fake runs made **1,336 engine calls, mean 89 per case** (range 49–152).
The two calibration cases measured 66 and 64 calls. Real runs will exceed this — the fake never retries on
schema mismatch and never triggers a specialist re-run — so I budget **1.6×**.

| Item | Per case |
|---|---|
| Engine calls | ~105–145 (89 mean × 1.6, capped by the run's own bounds) |
| Client calls | ~25–40 (one per turn plus document requests) |
| Engine tokens | ~2,000 in / 800 out per call → ~380k in, 150k out |
| Client tokens | ~1,500 in / 300 out per call → ~50k in, 10k out |
| **Engine cost** | ~$2.30 |
| **Client cost** | ~$0.05 |
| **Grading** | ~$0.15 |
| **Total per case** | **~$2.50** |

**Calibration (2 cases): ~$5.00. Hard ceiling `--max-usd 8`.**
**Full benchmark (13 remaining): ~$32.50. Hard ceiling `--max-usd 45`.**
**Maximum total exposure: $53**, and the harness enforces the ceiling per run — it aborts mid-case rather
than overspending, and a credit probe runs first.

## 5. Rubric

Nine dimensions, scored 1–5 by the independent grader against the case's hidden dossier. The grader sees
what the client knew; the engine only saw what it asked for.

| # | Dimension | 5 = | 1 = |
|---|---|---|---|
| 1 | Diagnosis quality | Names the real problem, not the presenting symptom | Accepts the opening statement as the brief |
| 2 | Adaptive questioning | Questions follow from prior answers; surfaces dossier facts marked `changes_recommendation` | Fixed script; misses the decisive facts |
| 3 | Evidence use | Every material claim traces to something the client actually said or a document | Asserts figures nobody provided |
| 4 | Recommendation specificity | Names what to do, by when, who owns it | "Improve alignment", "consider options" |
| 5 | Trade-offs | States what the recommendation gives up and what would change it | One-sided advocacy |
| 6 | Commercial reasoning | Costs, benefits and timing are arithmetically coherent | Numbers that don't reconcile |
| 7 | Implementation realism | A plan the client's actual staff and systems could execute | Ignores stated constraints |
| 8 | Consistency | No two deliverables contradict | Different figures in different volumes |
| 9 | Unsupported claims | None; gaps are declared | Confident invention |

Dimensions 3 and 9 are graded **against the dossier**, so laundering or invention is detectable rather than
a matter of taste.

## 6. Artifacts retained per case

Written to `uploads/benchmarks/<case>/<timestamp>/` (gitignored — the repo is public):

- Full conversation transcript, every turn
- Complete registry export (every entity with provenance, authority, lineage)
- All rendered deliverables (PDF/deck/CSV)
- Integrity record and release status
- Every model call: prompt, response, tokens, cost, latency (cassettes for free replay)
- Grader's scored rubric with quoted justification per dimension
- A diff of what the engine learned vs what the dossier held — which decisive facts it never surfaced

Cassettes make the assertions re-runnable at zero cost, so a later regression is caught without respending.

## 7. Pass/fail

**Calibration passes** if, across both cases:
- Diagnosis quality ≥ 4 on both — this is the gate. A consultancy that misreads the problem fails whatever
  else it scores.
- No dimension scores 1 on either case
- Mean across all nine ≥ 3.5
- Zero unsupported claims that the dossier contradicts (dimension 9 is pass/fail, not scored)
- `adv-symptom-not-problem` reframes the CRM request rather than scoping it

**Calibration fails** → stop, report, fix, and re-run the same two before spending on the rest.

**Full benchmark passes** if ≥ 11 of 13 meet the calibration bar and the adversarial cases hold their
specific laws (invented numbers, averaged conflicts, impossible objectives planned toward, regulated
questions answered rather than routed).

## 8. What this still will not prove

A real client's reaction, whether the advice would survive contact with their board, and long-run
correctness. Nine cases graded by a model is evidence, not proof. It is however the difference between
"the structure is sound" and "the reasoning is sound", and only the second is worth selling.
