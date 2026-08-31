# Extension contracts

Everything the engine can do is registered data. Adding a capability means adding a declaration and its
tests; it never means editing the loop that runs it. That is the whole point of the spine: a new method
that requires a change to `partner/loop.py` is a method the selector could not have chosen on shape alone,
which is the same defect as an engagement-type branch wearing a different hat.

## Files you never edit to extend the engine

| file | why it stays closed |
|---|---|
| `app/engine/partner/loop.py` | the loop reads `METHODS` and `select_methods`; a method it had to know about would be a hardcoded pack |
| `app/engine/methods/contract.py` | the selector reads `QuestionShape` and `FILTERABLE_FIELDS`; a special case here is a branch for one caller |
| `app/engine/specialists/runner.py` | admission is `ADMISSION_RULES` for every method equally; a per-method exemption is an unadmitted delta |
| `app/engine/work_products/plan.py` | planning evaluates declarations; a product named here is a fixed deliverable set |
| `app/engine/gates/release.py` | release runs `LAWS`; a law invoked directly here is a law nobody can remove and test |

Frozen entirely, in every direction, by `tests/engine/test_engine_r30_frozen.py`: `app/pipeline/**`,
`app/prompts/**`, `tools/**`, the top-level `tests/*.py` and `tests/conftest.py`. Reuse them by import.

## 1. Add a method

1. Create `app/engine/methods/builtin/<method_id>.py`. The package's `__init__.py` imports every module in
   the directory, so the file being there is the registration; no list to append to.
2. Declare a class with a `spec = MethodSpec(...)` and decorate it with `@register` from
   `app.engine.methods.contract`. `MethodSpec.__post_init__` refuses the specs that would break selection:
   a deterministic or calculation method with a non-zero model-call ceiling (M1), an `InputSpec` filtering
   a field outside `FILTERABLE_FIELDS` (M2), an empty or uncovered `answers` set (M3), and empty
   applicability (M4).
3. Applicability is `QuestionShape`s only - interrogative, subject kind, and the booleans and enums the
   shape carries. If you find yourself wanting to read an issue node's prose to decide whether your method
   applies, the shape is missing a field: add the field to the shape, not a string test to your method.
4. Write `run(ctx) -> MethodResult` returning deltas only. Build every entity with `new_entity` so the
   envelope and provenance are stamped for you, and produce every quantity through `ctx.calc` so it
   arrives with a formula and inputs. Validators are part of the spec, not of `run`.
5. Register the method's prompt as `app/engine/prompts/method_<id>.j2` if it is model assisted, and give
   the spec an `output_schema_version` so a later schema change invalidates cassettes instead of
   mis-parsing them.
6. Document it in the `registry:methods` table of `ARCHITECTURE.md`. `tests/engine/test_engine_docs.py`
   fails on a method that is registered and undocumented, and on a method that is documented and not
   registered.

Tests to add: a selection test that a matching shape picks it up (registering the spec inside the test
module is enough - that is the proof no orchestrator edit was needed), one test per declared validator,
and the named mutation that kills each.

## 2. Add a work product

1. Build a `WorkProductDecl` in `app/engine/work_products/decl.py` and hand it to `register_product`.
2. Applicability is a `Predicate`: `Count`, `AllOf`, `AnyOf` or `Always` over `InputSpec`s. There is no
   fifth constructor, and `Count` over a text field raises - a product cannot be planned because a document
   said a word (P1). Mandatory products declare `Always()` (P3); everything else earns its place from the
   registry's own counts.
3. Thresholds inside predicates come from `BOUNDS` through settings, never as literals. A product that
   needs "at least three" of something needs a named bound.
4. Sections are `SectionDecl`s whose queries are `InputSpec`s (P2). Mark a section `required=False` unless
   the product is meaningless without it: an optional section with no rows is dropped, and that is how
   applicability reaches inside a document.
5. Titles come from `title_template` over entity fields (`{central_decision}`, `{deadline}`,
   `{workstream}`). A title is never an engagement label.
6. Document it in the `registry:work_products` table of `ARCHITECTURE.md`.

Tests to add: a registry state where the predicate is true and one where it is false, the section-drop
case, and a divergence check that the new product does not appear in every case's plan.

## 3. Add a law

1. Write the query in `app/engine/gates/laws.py` as `(view, artifacts) -> list[Finding]`, add its id to
   `LawId`, and register it with `LAWS.register(Law(LawId.L<n>, law_<name>))`.
2. A law is a query over the registry or over the extracted artifact text. It never rewrites anything: a
   law that repairs its own finding cannot fail, and a gate that cannot fail is not a gate.
3. Decide `blocks_final`. Blocking is the default; a non-blocking law still lands in the Integrity Record,
   which is where a reader looks for what was noticed but not fatal.
4. Absence is not a defect. A flag written by a newer normaliser is tested with `is False`, never falsily,
   so an older stored record with the field missing is not condemned by a law that did not exist when it
   was written.
5. Document it in the `registry:laws` table of `ARCHITECTURE.md`.

Tests to add: a fixture that fails the law, a fixture that passes it, both driven through the gate rather
than through the law function, and the mutation that removes the registration - which the failing fixture
must catch.

## 4. Add a regulated domain

1. Add the member to `RegulatedDomain` in `app/engine/types.py` and its adviser class to `ADVISER_CLASS`
   in `app/engine/synthesis/regulated.py`. That mapping asserts total coverage at import time, so a domain
   without a named adviser cannot ship.
2. The classifier prompts receive the domain list as data; no branch anywhere names a domain. If your
   domain needs different handling, it needs a different adviser class, not a code path.
3. Clearance stays literal. Stage two clears a claim only on the exact clearance verdict; anything else -
   a synonym, a hedge, a schema failure, a provider outage - leaves the matter regulated. Widening that
   comparison is the mutation the regulated tests exist to kill.
4. Note anything the new domain cannot bound in `LIMITATIONS.md`.

Tests to add: a candidate the classifier claims for the domain and a verifier response that fails to clear
it, plus the L4 pair showing the routed matter and the licensed recommendation that never reaches a
product.

## 5. Add a benchmark case

1. Drop `tests/engine/benchmarks/<id>.json` (the case: opening statement, persona, dossier, documents,
   regulated matters) and `tests/engine/benchmarks/<id>.keys.json` beside it.
2. The `.keys.json` annotation is what makes the simulated client honest: `topic_map` maps each dossier
   topic to typed `asks_for` rows (kind plus a filter over `FILTERABLE_FIELDS`), `overrides` does the same
   per item, and `regulated_domains` annotates each regulated matter with its domain. The loader is
   strict - an unannotated topic, an unknown enum value, a filter on a text field or any unrecognised key
   is a load error, not a default. A question reveals an item only when the kinds match and the filters do
   not contradict, so no case can pass on prose overlap.
3. Mark `adversarial` and list the `checks` the case is expected to exercise. A core case joins the
   pairwise divergence set and must surface at least `MIN_REVEALED_CHANGERS` recommendation-changing
   dossier items; an adversarial case is asserted on its own named behaviour instead.
4. The engine never imports the benchmark package. If a case needs an engine change to run, the change
   belongs to a contract above, not to the harness.

Tests to add: nothing bespoke. The fake-provider benchmark test discovers cases from the directory; adding
the two files is the whole extension.

## 6. Change a bound

Add the name and default to `BOUNDS` in `app/engine/types.py`, add the `ENGINE_<NAME>` field to `Settings`,
use it through settings at the call site, and document it in the `registry:bounds` table of
`ARCHITECTURE.md` with its exact default. The docs test compares the table to `BOUNDS` name for name and
default for default, so a bound that changes value in code and not in the table fails the suite.
