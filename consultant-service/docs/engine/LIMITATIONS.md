# Limitations

What follows is the honest list: what the tests prove, what they cannot prove, and what this scope
deliberately did not build. A limitation written down is a bounded risk; the same limitation discovered by
a client is a defect.

## 1. What the deterministic suite proves, and what it does not

The whole benchmark suite runs against a `FakeProvider` driven by a structural oracle - a fake whose
answers are derived from each call's own context by generic rules, never from per-case scripts. That
design is what makes divergence meaningful: if the bundles for different cases differ under a case-blind
fake, the difference came from the input, not from a script. The suite therefore proves:

- the deterministic core reacts to the shape of the input (different questions, central decisions,
  issue trees, method multisets, evidence requests, assignments, recommendations, workstreams,
  deliverable sets and section signatures);
- that divergence is not vacuous: each core case must surface at least `MIN_REVEALED_CHANGERS` dossier
  items flagged as changing the recommendation, and the simulated client reveals only on typed matches,
  never on prose overlap;
- every law fails on its failing fixture and passes on its passing one, and the named mutation that
  removes each law is caught.

It does not prove, and cannot:

- **that the questions are good.** The oracle cannot judge whether a question is the one a partner would
  ask. Only real-model runs and human reading answer that.
- **that the prose is good.** Narrative quality, tone and executive readability are outside every
  assertion here. The gates check traceability, labelling and presentation, not persuasiveness.
- **that extraction is accurate.** A mislabelled number becomes a faithful, well-provenanced, wrong
  PROPOSED entity. The mitigations are structural (nothing is confirmed without playback, record class
  outranks recollection, quotes are verified verbatim), not semantic.
- **that the classifier over-routes acceptably.** Under-routing regulated matters is closed by
  construction; over-routing degrades usefulness and is visible only on real runs.

## 2. Real runs cost money and are a separate step

`test_engine_benchmarks_real.py` is skipped unless `ENGINE_BENCHMARK_REAL=1`. The costed CLI is
`python -m app.engine.benchmark --case <id> --model <slug> --max-usd <n> --out <dir>`; `--max-usd` is a
ceiling the harness enforces, and a credit probe runs first. Expect several dollars per case, roughly
doubled because the simulated client is itself a model. Outputs land under `uploads/benchmarks/`, which is
gitignored - the repository is public and no client payload or run bundle belongs in it.
`test_engine_benchmarks_replay.py` re-runs the same assertions from recorded cassettes with no spend, but
a cassette is invalidated by any `output_schema_version` change, so replay is a regression net, not a
substitute for a fresh run.

## 3. Regulated classification is bounded in one direction only

The two-stage screen is deliberately asymmetric: generous claiming, literal-word clearance. The safe
direction - never inventing licensed advice - is closed. The unsafe-for-usefulness direction is not: a
matter that is not really regulated can still be routed, and the client sees a qualified-adviser
requirement they did not need. `RegulatedDomain` has ten members; a matter that falls outside all of them
is still routed, under the catch-all domain, which is a choice the record makes visible rather than a
silent drop. No adviser accounts exist: a `QUALIFIED_PROFESSIONAL` resolution needs the reviewer token plus
an adviser identity string recorded in the provenance, and nothing in the engine verifies that identity.

## 4. Spreadsheets are deferred

There is no `openpyxl` in `requirements.txt` and this scope added no dependency. Consequences:

- `.xlsx`, `.xlsm` and `.xls` attachments are refused at ingestion and turned into a QUESTION asking for a
  CSV or PDF export. They are never parsed, and never silently ignored.
- Tabular work products export as CSV (stdlib) and PDF. There is no xlsx export.

This is a dependency decision, not a design one: the declarations and renderers would take an xlsx format
without structural change.

## 5. The legacy adapter's rows stay visible where they always were

The r30 pipeline is untouched, which includes `app/routers/requests.py`. An engagement that invokes the
legacy adapter creates an ordinary Request row, and that row therefore appears in `/api/requests/mine` for
the same owner alongside their standalone requests. The engine UI labels it; hiding it would mean editing
frozen r30 code, and the frozen manifest is worth more than the tidier list. The adapter also runs a paid,
roughly ten-minute pipeline inside the engagement's analysis thread, so its timeouts, its concurrency
valve and its daemon-thread fragility are inherited as they are.

## 6. Detection that is narrower than its name suggests

- **Clipping** covers text spans and frames: a span outside the body frame, two spans overlapping, a span
  past the right margin. It does not rasterise the page, so a drawn shape covering text is not detected.
- **Statement drift and untraceable numbers** are matched on the extracted text of the frozen PDF with
  page furniture and entity ids stripped. A restatement that changes no number and echoes no measure name
  can still slip past L6.
- **Reconciliation** is only as good as measure attachment. Two facts joined by `measure_id` reconcile
  correctly; a fact attached to the wrong MEASURE reconciles wrongly until the client corrects it. Every
  contested measure raises a provenance question, which is the only guard.
- **Symptom versus problem** depends on the model proposing the causal chain. Without that proposal the
  client's stated request stays in charge - fail-safe, but weak - and one adversarial case is the only
  guard on it.
- **The word denylist** in the universality guard is evadable by synonym. The whitelist AST law, the
  text-scramble test and the execution trace are what actually carry the proof; the denylist is the cheap
  first net.

## 7. Scale and concurrency

Rows are append-only and grow with every delta. There is an index on `(engagement_id, entity_id)`, but no
latest-version cache; engagements beyond a few thousand entities will need one before query time matters.
Two writers on one engagement are serialised by a row-level working flag (a concurrent turn gets a 409); a
finer-grained lock is future work.

## 8. Absent evidence is not evidence of a defect

A flag introduced by a newer normaliser is read with `is False`, never falsily, everywhere in the engine.
The consequence worth naming: a stored record written before a flag existed is never condemned by the law
that reads it, so an old row can pass a check a new row would fail. That is the deliberate direction. The
alternative - treating a missing field as a violation - would condemn history for the crime of predating
the rule.

## 9. Not deployed

Per the owner's constraint, the engine is not deployed and does not replace the r30 pipeline. r30 remains
the proven path until the universal engine passes every benchmark independently, on real models, read by a
human.
