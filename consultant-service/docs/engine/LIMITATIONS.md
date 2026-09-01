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

## 9. The delivery half of the method library is reachable, not complete

The analysis loop now runs past its first tier: `capability_gap` writes a CAPABILITY, `operating_model`
and `org_design` turn capabilities into WORKSTREAM, GOVERNANCE, ACTION and OWNER rows, `make_buy_partner`
writes the OPTIONs it is the only writer of, `decision_criteria` writes the EVALUATION_CRITERION nothing
in the build used to write, and `recommendation` writes a RECOMMENDATION that carries the confirmed
evidence it rests on. Four things are still missing, and each is a real hole rather than a fixture
artefact:

- **INITIATIVE has no creator.** `roadmap` only re-orders initiatives and `legacy_r30_technology_blueprint`
  is the other declared producer, so no run writes one. MILESTONE is written per workstream that has work
  in it, and "work in it" is read through INITIATIVE - so `transformation_roadmap` stays unplannable even
  on engagements that hold workstreams and actions.
- **BENEFIT, COST and ASSUMPTION are written by no reachable method.** `cost_benefit` is selected and is
  blocked on a FACT filter no fake run satisfies; `scenario` is blocked on ASSUMPTION, which only the
  legacy adapter writes.
- **The legacy adapter cannot run under an assignment.** It writes CONFIRMED rows, and S2 admits only
  PROPOSED ones from a specialist, so its one selection in the fifteen cases is refused and recorded
  BLOCKED. Either the adapter proposes and something else confirms, or the rule needs a carve-out that
  says why.
- **Advice is not a copy of its evidence, and nothing in it is a client's sentence.** A RECOMMENDATION
  selects one registered OPTION, names the routes it was taken over, cites the EVALUATION_CRITERIA the
  decision is judged against and the TRADE_OFF that weighed the routes, and rests on evidence a support
  law admits. A route is now named from the CAPABILITY gaps it would close, in the words this engagement
  recorded them in - which is what makes an option about this engagement rather than about a class of
  capability - so the recommender quotes a route only where that route's own wording is not already a
  claim the register holds, and names it by id and mechanism otherwise (`route_phrase`). It refuses in
  the same way to borrow any wording a live FACT, MEASURE or EVIDENCE_SOURCE already carries. `L16`
  re-checks the same question at the door, over figures and scope.
- **The choice follows registered evidence, and there is often none to follow.** A route is advised only
  where the register tells it from every rival in the comparison AND everything that tells them apart
  points the same way: a BENEFIT bearing on one route is a reason for it, a COST, a RISK or a CONSTRAINT
  bearing on one route is a reason against it, and the direction comes from the KIND, never from the
  words. An EVALUATION_CRITERION and a Score separate routes without pointing anywhere - a criterion
  declares no direction - so a scored comparison the engine cannot read a direction in is handed back
  with the scores visible. Where nothing separates the routes, the engagement does NOT choose: it
  records a typed DECISION_REQUIRED against the decision, asks the client per route what that route
  costs and gains, and leaves a standing SPAWN_SPECIALIST question naming the kinds of evidence that
  would settle it. Under the case-blind fake this is what happens on all fifteen engagements: no COST,
  no BENEFIT, no RISK, no CONSTRAINT and no score names one sourcing route rather than another, because
  nothing in the library writes per-route evidence and the fake client's records are exhausted before
  the routes exist. **The fake benchmark therefore produces no RECOMMENDATION at all**, and three
  assertions that were green while the engine advised `make` on every engagement now fail:
  `delivery_tier_failures` P3, the blocked-claims measurement beside it, and the two rare-path entries
  that only a live recommendation reaches. That is the honest state: the engine advises whenever the
  register separates the routes (proved on hand-built mirror registries, where mirroring the evidence
  mirrors the advice), and a case-blind oracle cannot make a register that separates them.
- **Not every engagement ends in advice, and none of the fake ones does.** An engagement that registers
  the capability gaps, the sourcing routes and the comparison between them and still advises nothing -
  because no route's lineage reaches a CONFIRMED FACT or an APPROVED ASSUMPTION, or because nothing
  separates the routes - records a typed DECISION_REQUIRED against the central decision and an OPEN
  question that names, in typed fields, the decision it blocks (`Relevance.decision_id`), the routes it
  is about (`QuestionPayload.about_ids`) and the kinds of evidence that would settle it (`asks_for`).
  How many is deliberately not written down here: the count moves with the trees the model proposes,
  and a number in a paragraph goes stale without failing anything. This is written down in
  `assertions.BLOCKED_CLAIMS["advice_on_every_core_case"]` and pinned by a test that measures the
  stated cause rather than reading it.
- **A model call can still be spent on an answer nothing keeps.** A method is no longer offered a node
  once a run of it kept nothing, nor a window it has already been shown (`input_fingerprint`), nor one
  it can say from the register alone it has nothing to do with (`MethodSpec.pending`). Across the
  fifteen fake engagements that took generate-and-discard runs from 80 to 23 and runs that left the
  registry untouched from 34 to 0, and no method is run twice after a run of it kept nothing. What
  remains is 23 FIRST runs of four model-assisted methods - `market_sizing`, `market_competitor`,
  `root_cause`, `capability_gap` - whose declared output kinds are also kinds their window is full of,
  under an oracle that can only quote the window: every candidate they generate restates a wording the
  engagement already holds and the admission law refuses all of it. The engine cannot know that before
  the call without assuming the model quotes, and an engine that assumed it would silence those methods
  in production, where they do not. `test_engine_decision_laws.py::test_t6_nothing_is_generated_and_thrown_away`
  fails on exactly those 23 runs and is left failing rather than weakened.

## 10. A client can confirm their own words only through the engine, not through the API

`charter.confirm_understanding` is the act that moves a client-stated FACT from PROPOSED to CONFIRMED, and
`registry._is_support` admits nothing else without a document - so it is the only path to a supported
recommendation on an engagement with no records to hand (MF2.1). `Partner.confirm_understanding` exposes
it and the benchmark's simulated client exercises it, but `app/engine/api/router.py` has no endpoint for
it yet: the reply already carries `understanding`, and nothing lets a real client answer it. Until that
endpoint exists, a real engagement can reach a recommendation only through documents.

## 11. Not deployed

Per the owner's constraint, the engine is not deployed and does not replace the r30 pipeline. r30 remains
the proven path until the universal engine passes every benchmark independently, on real models, read by a
human.
