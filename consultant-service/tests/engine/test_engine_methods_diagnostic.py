"""C10 diagnostic methods: root_cause, current_state, stakeholder,
process_map, journey and capability_gap.

Every law each method states in its docstring is pinned here, and each test
names the law it pins. The mutations the work breakdown requires are noted on
the tests that catch them: removing any one method's distinctive validator
from its spec, and letting root_cause emit a coined number.

No registry module is exercised through its write side: a minimal in-memory
RegistryView stands in, which is exactly the surface a method is typed
against (design 8.1 - a scoped window and the whole registry are
interchangeable to a method), so this file collects and runs independently of
the registry component's state.
"""
from __future__ import annotations

import dataclasses
import inspect
import json
from decimal import Decimal

import pytest

from app.engine import types as T
from app.engine.llm import FakeProvider
from app.engine.methods import contract as C
from app.engine.methods.builtin import capability_gap as CG
from app.engine.methods.builtin import current_state as CS
from app.engine.methods.builtin import journey as JN
from app.engine.methods.builtin import process_map as PM
from app.engine.methods.builtin import root_cause as RC
from app.engine.methods.builtin import stakeholder as SH

from conftest import sample_payload

DIAGNOSTIC = (RC, CS, SH, PM, JN, CG)
MODEL_ASSISTED = (RC, SH, PM, JN, CG)


# ---------------------------------------------------------------------------
# the read side a method is typed against
# ---------------------------------------------------------------------------

class FakeView:
    """get/query/central_decision, which is everything these methods read."""
    engagement_id = "E-1"

    def __init__(self, *entities: T.Entity):
        self._rows = list(entities)

    def get(self, entity_id):
        return next((e for e in self._rows if e.id == entity_id), None)

    def query(self, kind=None, *, status=None, where=None):
        return [e for e in self._rows
                if (kind is None or e.kind == kind) and (status is None or e.status == status)]

    def lineage(self, entity_id):
        return [e for e in self._rows if e.id == entity_id]

    def content_hash(self):
        return "0" * 64

    def central_decision(self):
        return next((e for e in self._rows
                     if e.kind is T.Kind.DECISION and e.payload.role is T.DecisionRole.CENTRAL), None)

    def supports_of(self, entity_id):
        return []

    def source_text(self, source_id):
        e = self.get(source_id)
        return e.payload.text if e is not None and e.kind is T.Kind.EVIDENCE_SOURCE else None


def ent(kind: T.Kind, payload=None, *, entity_id: str | None = None, derived_from=("EVI-1",),
        status: T.Status = T.Status.PROPOSED, actor: T.Actor = T.Actor.PARTNER) -> T.Entity:
    """A well-formed row through the only constructor producers use."""
    payload = sample_payload(kind) if payload is None else payload
    return T.make_entity(
        kind=kind, engagement_id="E-1", payload=payload,
        provenance=T.Provenance(actor=actor, actor_ref=f"{actor.value}:1", derived_from=tuple(derived_from)),
        confidence=T.Confidence(None), relevance=T.Relevance("DEC-1", 0.5),
        relation=T.RelationToCentralDecision.INFORMS, status=status,
        entity_id=entity_id or f"{T.ID_PREFIX[kind]}-1")


def issue(interrogative: T.Interrogative, target: T.Kind, *, entity_id="ISS-1", **flags) -> T.Entity:
    fields = {"quantified": False, "comparative": False, "causal": False, "temporal": False,
              "capability_class": None, **flags}
    p = sample_payload(T.Kind.ISSUE, interrogative=interrogative, target_kind=target, **fields)
    return ent(T.Kind.ISSUE, p, entity_id=entity_id, derived_from=())


def source(entity_id="EVI-1", text="we have 40 people and two handovers") -> T.Entity:
    p = sample_payload(T.Kind.EVIDENCE_SOURCE, text=text)
    return ent(T.Kind.EVIDENCE_SOURCE, p, entity_id=entity_id, derived_from=())


def fact(entity_id: str, statement: str, *, basis=T.FactBasis.CLIENT_STATED, quantity="drop",
         measure_id=None, status=T.Status.PROPOSED) -> T.Entity:
    p = sample_payload(T.Kind.FACT, statement=statement, basis=basis, measure_id=measure_id)
    if quantity != "keep":
        p = dataclasses.replace(p, quantity=None if quantity == "drop" else quantity)
    return ent(T.Kind.FACT, p, entity_id=entity_id, status=status)


def qty(value: str, unit="heads", family=T.UnitFamily.COUNT) -> T.Quantity:
    return T.Quantity(Decimal(value), unit, family, T.Dimensions(as_of="2025-12-31"))


def ctx_for(view: FakeView, provider, *, issue_id="ISS-1", actor=T.Actor.METHOD) -> C.MethodContext:
    return C.MethodContext(registry=view, provider=provider, calc=None, actor=actor,
                           actor_ref="method:test@1", issue_ids=(issue_id,))


def scripted(method_id: str, outputs, questions=()) -> FakeProvider:
    """A provider that answers exactly one method's prompt with exactly this
    sheet. The purpose key is the one model_proposals() issues."""
    body = json.dumps({"outputs": list(outputs), "questions": list(questions)})
    return FakeProvider(script={f"method_{method_id}": [body]})


def out(kind: T.Kind, text: str, derived_from, **fields) -> dict:
    """One row of the method_generic.j2 output shape, as a model would send it."""
    quantity_from = fields.pop("quantity_from", None)
    return {"kind": kind.value, "text": text, "fields": fields,
            "quantity_from": quantity_from, "derived_from": list(derived_from)}


def run_validators(spec: C.MethodSpec, view, result: C.MethodResult) -> list[str]:
    """The laws of a spec, as the runner applies them (design 8.5). Reading
    spec.validators - not the functions by name - is what makes 'remove a
    validator from the spec' a mutation these tests catch."""
    laws: list[str] = []
    for v in spec.validators:
        laws.extend(f.law for f in v(view, result))
    return laws


def added(result: C.MethodResult, kind: T.Kind) -> list[T.Entity]:
    return [d.entity for d in result.deltas if isinstance(d, T.Add) and d.entity.kind == kind]


def laws(result: C.MethodResult) -> list[str]:
    return [f.law for f in result.findings]


# ---------------------------------------------------------------------------
# the family, as declared
# ---------------------------------------------------------------------------

def test_every_diagnostic_method_is_registered_once_with_a_lawful_spec():
    for module in DIAGNOSTIC:
        spec = module.SPEC
        assert C.METHODS.get(spec.id).spec is spec
        assert spec.applicability and spec.answers            # M3/M4, re-checked as registered
        assert spec.validators, f"{spec.id} declares no validator: nothing could reject a bad output"
        assert spec.evidence.every_output_cites_inputs and spec.evidence.forbid_new_quantities
        # M1: only the model-assisted ones may spend calls.
        if spec.execution in T.FREE_EXECUTION:
            assert spec.max_model_calls == 0
        else:
            assert spec.max_model_calls >= 1
        assert T.Kind.QUESTION not in spec.output_kinds or spec.execution in T.ASSIGNMENT_EXECUTION


def test_selection_of_the_family_reads_shapes_and_inputs_only():
    # process_map and journey answer the same HOW-on-PROCESS_STEP shape and
    # are separated by their inputs, never by a branch: with a stakeholder
    # registered both are fully supplied, tie, and both run (design 7.2).
    node = issue(T.Interrogative.HOW, T.Kind.PROCESS_STEP)
    rich = FakeView(source(), fact("FCT-1", "step one"), fact("FCT-2", "step two"),
                    ent(T.Kind.STAKEHOLDER, entity_id="STK-1"))
    both = [s for s in C.select_methods([node], rich, max_per_issue=4)
            if s.method_id in ("process_map", "journey")]
    assert {s.method_id for s in both} == {"process_map", "journey"}
    assert all(s.inputs.missing == () for s in both)
    assert all(s.tied for s in both)
    # Without a stakeholder the journey is not fully supplied and loses the tie.
    thin = FakeView(source(), fact("FCT-1", "step one"), fact("FCT-2", "step two"))
    ranked = [s for s in C.select_methods([node], thin, max_per_issue=4)
              if s.method_id in ("process_map", "journey")]
    assert [s.method_id for s in ranked] == ["process_map", "journey"]
    assert ranked[0].inputs.missing == () and ranked[1].inputs.missing != ()
    assert not any(s.tied for s in ranked)


def test_no_diagnostic_module_can_name_an_engagement_type_or_a_client():
    for module in DIAGNOSTIC:
        src = inspect.getsource(module)
        assert src.isascii(), f"{module.__name__} is not pure ASCII"
        low = src.lower()
        for word in ("recovery", "vitalis", "club rally", "icarry", "restaurant", "clinic",
                     "hospital", "saas", "acquisition", "cost reduction"):
            assert word not in low, f"{module.__name__} names {word!r}"


# ---------------------------------------------------------------------------
# root_cause
# ---------------------------------------------------------------------------

def _root_cause_view(*extra: T.Entity) -> FakeView:
    return FakeView(source(), issue(T.Interrogative.WHY, T.Kind.FACT, causal=True),
                    fact("FCT-1", "two handovers per order"),
                    fact("FCT-2", "we have 40 people", basis=T.FactBasis.DOCUMENT_VERIFIED),
                    *extra)


def test_root_cause_writes_untested_hypotheses_that_cite_registered_facts():
    # R1 and the "untested -> question" rule of design 7.3: the method
    # proposes the cause and asks for what would settle it, in one result.
    view = _root_cause_view()
    provider = scripted("root_cause", [
        out(T.Kind.HYPOTHESIS, "The handover count drives the delay", ["FCT-1", "FCT-2"], causes=["FCT-1"]),
    ])
    result = C.METHODS.get("root_cause").run(ctx_for(view, provider))
    hyps = added(result, T.Kind.HYPOTHESIS)
    assert len(hyps) == 1
    h = hyps[0]
    assert h.payload.causes == ("FCT-1",)
    assert h.payload.issue_id == "ISS-1"
    assert h.payload.verdict == "untested"
    assert h.status is T.Status.PROPOSED and h.provenance.actor is T.Actor.METHOD
    assert set(h.provenance.derived_from) == {"FCT-1", "FCT-2"}
    assert h.provenance.model_call_id == result.model_call_ids[0]
    # one typed hole per untested hypothesis, naming the cause it rests on
    asks = [q for q in result.questions if "FCT-1" in q.why]
    assert len(asks) == 1 and asks[0].asks_for == (T.AsksFor(T.Kind.FACT),)
    assert run_validators(RC.SPEC, view, result) == []


def test_root_cause_refuses_a_cause_that_is_words_rather_than_a_registered_fact():
    # R1: "poor communication" is not a cause the engagement can ever test.
    view = _root_cause_view()
    provider = scripted("root_cause", [
        out(T.Kind.HYPOTHESIS, "Communication is the cause", ["FCT-1"], causes=["poor communication"]),
        out(T.Kind.HYPOTHESIS, "An unseen row is the cause", ["FCT-1"], causes=["FCT-99"]),
        out(T.Kind.HYPOTHESIS, "An objective is the cause", ["FCT-1", "OBJ-1"], causes=["OBJ-1"]),
    ])
    result = C.METHODS.get("root_cause").run(
        ctx_for(_root_cause_view(ent(T.Kind.OBJECTIVE, entity_id="OBJ-1")), provider))
    assert added(result, T.Kind.HYPOTHESIS) == []
    assert laws(result).count("M.root_cause.uncited_cause") == 3
    assert view is not None


def test_root_cause_refuses_a_second_hypothesis_resting_on_the_same_causes():
    # R2 at source: one explanation is one hypothesis, however it is worded.
    view = _root_cause_view()
    provider = scripted("root_cause", [
        out(T.Kind.HYPOTHESIS, "Handovers drive it", ["FCT-1", "FCT-2"], causes=["FCT-1", "FCT-2"]),
        out(T.Kind.HYPOTHESIS, "The same thing, said differently", ["FCT-2", "FCT-1"], causes=["FCT-2", "FCT-1"]),
    ])
    result = C.METHODS.get("root_cause").run(ctx_for(view, provider))
    assert len(added(result, T.Kind.HYPOTHESIS)) == 1
    assert "M.root_cause.duplicate_cause_set" in laws(result)


def test_root_cause_refuses_a_hypothesis_a_live_row_already_states():
    live = ent(T.Kind.HYPOTHESIS,
               T.HypothesisPayload(text="already said", issue_id="ISS-1", causes=("FCT-1",), verdict="untested"),
               entity_id="HYP-1")
    view = _root_cause_view(live)
    provider = scripted("root_cause", [
        out(T.Kind.HYPOTHESIS, "Reworded", ["FCT-1"], causes=["FCT-1"]),
    ])
    result = C.METHODS.get("root_cause").run(ctx_for(view, provider))
    assert added(result, T.Kind.HYPOTHESIS) == []
    assert "M.root_cause.duplicate_cause_set" in laws(result)


def test_root_cause_refuses_a_figure_the_cited_inputs_do_not_carry():
    # MUTATION "let root_cause emit a coined number" is caught here. The
    # hypothesis payload has no Quantity field, so the invented number would
    # ride out in the sentence and print exactly like a measured one (R3).
    view = _root_cause_view()
    provider = scripted("root_cause", [
        out(T.Kind.HYPOTHESIS, "The handovers cost 250 hours every month", ["FCT-1", "FCT-2"], causes=["FCT-1"]),
        out(T.Kind.HYPOTHESIS, "The 40 people are split across FCT-2 and two handovers",
            ["FCT-1", "FCT-2"], causes=["FCT-2"]),
    ])
    result = C.METHODS.get("root_cause").run(ctx_for(view, provider))
    texts = [h.payload.text for h in added(result, T.Kind.HYPOTHESIS)]
    assert "250" not in " ".join(texts)
    assert laws(result).count("M.root_cause.coined_quantity") == 1
    # Negative control: 40 IS in a cited fact, and an id's digits are a name,
    # not a figure - that hypothesis stands.
    assert len(texts) == 1 and "40 people" in texts[0]


def test_root_cause_validators_fire_on_a_scripted_bad_result():
    # MUTATION "remove a validator from root_cause's spec" is caught here:
    # the laws come from SPEC.validators, not from the functions by name.
    view = _root_cause_view()
    uncited = ent(T.Kind.HYPOTHESIS,
                  T.HypothesisPayload(text="rests on nothing", issue_id="ISS-1", causes=("FCT-9",)),
                  entity_id="HYP-7", derived_from=("FCT-1",), actor=T.Actor.METHOD)
    twin_a = ent(T.Kind.HYPOTHESIS,
                 T.HypothesisPayload(text="a", issue_id="ISS-1", causes=("FCT-1",)),
                 entity_id="HYP-8", derived_from=("FCT-1",), actor=T.Actor.METHOD)
    twin_b = ent(T.Kind.HYPOTHESIS,
                 T.HypothesisPayload(text="b", issue_id="ISS-1", causes=("FCT-1",)),
                 entity_id="HYP-9", derived_from=("FCT-1",), actor=T.Actor.METHOD)
    found = run_validators(RC.SPEC, view, C.MethodResult(deltas=(T.Add(uncited), T.Add(twin_a), T.Add(twin_b))))
    assert "M.root_cause.uncited_cause" in found
    assert "M.root_cause.duplicate_cause_set" in found
    # Negative control: a clean result raises nothing.
    clean = ent(T.Kind.HYPOTHESIS,
                T.HypothesisPayload(text="c", issue_id="ISS-1", causes=("FCT-2",)),
                entity_id="HYP-10", derived_from=("FCT-2",), actor=T.Actor.METHOD)
    assert run_validators(RC.SPEC, view, C.MethodResult(deltas=(T.Add(clean),))) == []


def test_a_model_outage_blocks_the_analysis_and_defaults_nothing():
    for module in MODEL_ASSISTED:
        provider = FakeProvider(script={f"method_{module.SPEC.id}": [RuntimeError("upstream refused")]})
        view = FakeView(source(), issue(module.SPEC.applicability[0].interrogative,
                                        module.SPEC.applicability[0].target_kind, causal=True))
        result = C.METHODS.get(module.SPEC.id).run(ctx_for(view, provider))
        assert result.deltas == () and result.questions == ()
        assert [f.law for f in result.findings] == [f"M.{module.SPEC.id}.model_failure"]
        assert all(f.blocks_final is False for f in result.findings)


# ---------------------------------------------------------------------------
# current_state
# ---------------------------------------------------------------------------

def _measure(entity_id="MEA-1", name="headcount") -> T.Entity:
    return ent(T.Kind.MEASURE, sample_payload(T.Kind.MEASURE, name=name), entity_id=entity_id, derived_from=())


def test_current_state_summarises_by_measure_and_copies_a_unanimous_figure():
    # C1: the summary is a rearrangement of registered rows; its one figure
    # is a copy, and it cites the whole group it stands for.
    view = FakeView(source(), _measure(),
                    fact("FCT-1", "forty heads", quantity=qty("40"), measure_id="MEA-1"),
                    fact("FCT-2", "forty heads on the payroll", quantity=qty("40"), measure_id="MEA-1"),
                    fact("FCT-3", "no measure attached"))
    result = C.METHODS.get("current_state").run(ctx_for(view, FakeProvider()))
    summaries = added(result, T.Kind.FACT)
    assert len(summaries) == 1
    s = summaries[0]
    assert s.payload.basis is T.FactBasis.INFERRED and s.payload.measure_id == "MEA-1"
    assert s.payload.quantity == qty("40")
    assert s.provenance.derived_from == ("FCT-1", "FCT-2")   # a fact with no measure joins no group
    assert "headcount" in s.payload.statement
    assert s.status is T.Status.PROPOSED                     # a method is not a record
    assert run_validators(CS.SPEC, view, result) == []


def test_current_state_never_blends_two_figures_that_disagree():
    # Nothing averages, blends or silently selects (design 1, consequence 2):
    # the divergence stays visible for synthesis to raise as a CONFLICT.
    view = FakeView(source(), _measure(),
                    fact("FCT-1", "forty heads", quantity=qty("40"), measure_id="MEA-1"),
                    fact("FCT-2", "forty five heads", quantity=qty("45"), measure_id="MEA-1"))
    result = C.METHODS.get("current_state").run(ctx_for(view, FakeProvider()))
    s = added(result, T.Kind.FACT)[0]
    assert s.payload.quantity is None
    # both figures are still readable in the summary, neither is chosen
    assert "40" in s.payload.statement and "45" in s.payload.statement


def test_current_state_writes_nothing_on_a_second_pass():
    view = FakeView(source(), _measure(),
                    fact("FCT-1", "forty heads", quantity=qty("40"), measure_id="MEA-1"))
    first = C.METHODS.get("current_state").run(ctx_for(view, FakeProvider()))
    assert len(first.deltas) == 1
    written = [d.entity for d in first.deltas]
    again = FakeView(*(list(view._rows) + [dataclasses.replace(written[0], id="FCT-9")]))
    assert C.METHODS.get("current_state").run(ctx_for(again, FakeProvider())).deltas == ()


def test_current_state_marks_a_capability_the_evidenced_process_runs_through_present():
    # C2: the signal is structural (a step naming the capability in
    # system_ids), and the earlier judgement is superseded, not duplicated.
    cap = ent(T.Kind.CAPABILITY,
              T.CapabilityPayload(text="order intake", capability_class=T.CapabilityClass.PROCESS,
                                  gap=T.GapState.MISSING, evidence=("FCT-1",)),
              entity_id="CAP-1", derived_from=("FCT-1",))
    step = ent(T.Kind.PROCESS_STEP,
               T.ProcessStepPayload(text="orders are keyed in", perspective=T.StepPerspective.INTERNAL,
                                    sequence=1, system_ids=("CAP-1",), evidence=("FCT-1",)),
               entity_id="PST-1", derived_from=("FCT-1",), actor=T.Actor.METHOD)
    view = FakeView(source(), fact("FCT-1", "orders are keyed in", status=T.Status.CONFIRMED), cap, step)
    result = C.METHODS.get("current_state").run(ctx_for(view, FakeProvider()))
    supersedes = [d for d in result.deltas if isinstance(d, T.Supersede)]
    assert len(supersedes) == 1
    d = supersedes[0]
    assert d.old_id == "CAP-1" and d.entity.id == "CAP-1"
    assert d.entity.payload.gap is T.GapState.PRESENT
    assert d.entity.payload.capability_class is cap.payload.capability_class
    assert d.entity.payload.evidence == ("PST-1",)
    # The lineage names the step AND the fact the step rests on, because that
    # fact is what the claim actually stands on.
    assert d.entity.provenance.derived_from == ("PST-1", "FCT-1")
    # The evidence requirement, not the method, decided how far it may go: the
    # underlying fact is CONFIRMED and owned by an accepted authority, so
    # PRESENT is too.
    assert d.entity.status is T.Status.CONFIRMED
    # A capability already PRESENT is left alone on the next pass.
    settled = FakeView(*(list(view._rows[:2]) + [d.entity, step]))
    assert C.METHODS.get("current_state").run(ctx_for(settled, FakeProvider())).deltas == ()


def test_current_state_leaves_a_capability_proposed_when_its_evidence_is_not_settled():
    # Absence decides downwards: a fact that is only PROPOSED settles
    # nothing, and the method does not promote itself past its evidence.
    cap = ent(T.Kind.CAPABILITY,
              T.CapabilityPayload(text="order intake", capability_class=T.CapabilityClass.PROCESS,
                                  gap=T.GapState.PARTIAL, evidence=("FCT-1",)),
              entity_id="CAP-1", derived_from=("FCT-1",))
    step = ent(T.Kind.PROCESS_STEP,
               T.ProcessStepPayload(text="orders are keyed in", perspective=T.StepPerspective.INTERNAL,
                                    sequence=1, system_ids=("CAP-1",), evidence=("FCT-1",)),
               entity_id="PST-1", derived_from=("FCT-1",), actor=T.Actor.METHOD)
    view = FakeView(source(), fact("FCT-1", "orders are keyed in"), cap, step)
    d = [x for x in C.METHODS.get("current_state").run(ctx_for(view, FakeProvider())).deltas
         if isinstance(x, T.Supersede)][0]
    assert d.entity.payload.gap is T.GapState.PRESENT and d.entity.status is T.Status.PROPOSED


def test_current_state_validators_fire_on_a_blended_summary():
    # MUTATION "remove a validator from current_state's spec" is caught here.
    view = FakeView(source(), _measure(),
                    fact("FCT-1", "forty heads", quantity=qty("40"), measure_id="MEA-1"),
                    fact("FCT-2", "fifty heads", quantity=qty("50"), measure_id="MEA-1"))
    blended = ent(T.Kind.FACT,
                  T.FactPayload(statement="on average forty five", basis=T.FactBasis.INFERRED,
                                measure_id="MEA-1", quantity=qty("45")),
                  entity_id="FCT-8", derived_from=("FCT-1", "FCT-2"), actor=T.Actor.METHOD)
    found = run_validators(CS.SPEC, view, C.MethodResult(deltas=(T.Add(blended),)))
    assert "M.current_state.blended_summary" in found
    # Negative control: a copied figure is not a blend.
    copied = dataclasses.replace(blended, payload=dataclasses.replace(blended.payload, quantity=qty("40")))
    assert run_validators(CS.SPEC, view, C.MethodResult(deltas=(T.Add(copied),))) == []


def test_current_state_may_not_manufacture_a_recollection_or_a_record():
    view = FakeView(source(), fact("FCT-1", "forty heads"))
    faked = ent(T.Kind.FACT,
                T.FactPayload(statement="the client said so", basis=T.FactBasis.CLIENT_STATED),
                entity_id="FCT-8", derived_from=("FCT-1",), actor=T.Actor.METHOD)
    assert "M.current_state.manufactured_basis" in run_validators(
        CS.SPEC, view, C.MethodResult(deltas=(T.Add(faked),)))


def test_current_state_needs_no_model_at_all():
    view = FakeView(source(), _measure(), fact("FCT-1", "forty heads", measure_id="MEA-1"))
    provider = FakeProvider()
    result = C.METHODS.get("current_state").run(ctx_for(view, provider))
    assert provider.calls == [] and result.model_call_ids == ()
    assert CS.SPEC.execution in T.FREE_EXECUTION and CS.SPEC.max_model_calls == 0


# ---------------------------------------------------------------------------
# stakeholder
# ---------------------------------------------------------------------------

def _stakeholder_view(*extra: T.Entity) -> FakeView:
    return FakeView(source(), issue(T.Interrogative.WHO, T.Kind.STAKEHOLDER),
                    ent(T.Kind.BUSINESS_CONTEXT, entity_id="BCX-1"),
                    ent(T.Kind.DECISION, entity_id="DEC-1"), *extra)


def test_stakeholder_names_people_the_record_reaches_and_types_their_influence():
    view = _stakeholder_view()
    provider = scripted("stakeholder", [
        out(T.Kind.STAKEHOLDER, "the operations lead", ["BCX-1", "DEC-1"],
            name="operations lead", role="runs the floor", interest="throughput", influence="HIGH"),
        out(T.Kind.OWNER, "the finance lead", ["BCX-1"], name="finance lead", role="owns the budget",
            reports_to="OWN-404"),
    ])
    result = C.METHODS.get("stakeholder").run(ctx_for(view, provider))
    stk = added(result, T.Kind.STAKEHOLDER)[0]
    assert stk.payload.name == "operations lead" and stk.payload.influence == "high"
    assert stk.status is T.Status.PROPOSED
    own = added(result, T.Kind.OWNER)[0]
    # a reporting line to a row this run was never shown is not recorded
    assert own.payload.reports_to is None
    assert run_validators(SH.SPEC, view, result) == []


def test_stakeholder_influence_outside_the_closed_list_becomes_unknown():
    # K2: unknown is a real answer; "kingmaker" is not a stronger ranking, it
    # is an unsortable one.
    assert SH.influence_of("kingmaker") == "unknown"
    assert SH.influence_of(None) == "unknown"
    assert SH.influence_of(" Medium ") == "medium"
    view = _stakeholder_view()
    provider = scripted("stakeholder", [
        out(T.Kind.STAKEHOLDER, "the sponsor", ["BCX-1"], name="sponsor", role="sponsor",
            influence="kingmaker"),
    ])
    stk = added(C.METHODS.get("stakeholder").run(ctx_for(view, provider)), T.Kind.STAKEHOLDER)[0]
    assert stk.payload.influence == "unknown"


def test_a_stakeholder_whose_citations_rest_on_no_source_is_rejected():
    # K1 at source. MUTATION "remove a validator from stakeholder's spec" is
    # caught by the validator half of this test.
    orphan = ent(T.Kind.BUSINESS_CONTEXT, entity_id="BCX-2", derived_from=())
    view = FakeView(source(), issue(T.Interrogative.WHO, T.Kind.STAKEHOLDER), orphan,
                    ent(T.Kind.DECISION, entity_id="DEC-1"))
    provider = scripted("stakeholder", [
        out(T.Kind.STAKEHOLDER, "invented person", ["BCX-2"], name="invented person", role="head of nothing"),
    ])
    result = C.METHODS.get("stakeholder").run(ctx_for(view, provider))
    assert added(result, T.Kind.STAKEHOLDER) == []
    assert "M.stakeholder.name_without_source" in laws(result)
    # and the same row, forced past the builder, is caught by the spec's laws
    forced = ent(T.Kind.STAKEHOLDER,
                 T.StakeholderPayload(name="invented person", role="head of nothing", influence="high"),
                 entity_id="STK-9", derived_from=("BCX-2",), actor=T.Actor.METHOD)
    found = run_validators(SH.SPEC, view, C.MethodResult(deltas=(T.Add(forced),)))
    assert "M.stakeholder.name_without_source" in found
    # Negative control: cite the row that does rest on the turn, and it stands.
    ok = dataclasses.replace(forced, provenance=dataclasses.replace(forced.provenance, derived_from=("BCX-1",)))
    assert run_validators(SH.SPEC, _stakeholder_view(), C.MethodResult(deltas=(T.Add(ok),))) == []


def test_an_unresolvable_citation_is_not_treated_as_a_missing_source():
    # Absent evidence is not evidence of a defect: a scoped view legitimately
    # hides rows, and the name is left alone rather than condemned.
    forced = ent(T.Kind.STAKEHOLDER,
                 T.StakeholderPayload(name="the sponsor", role="sponsor", influence="high"),
                 entity_id="STK-9", derived_from=("BCX-404",), actor=T.Actor.METHOD)
    assert run_validators(SH.SPEC, _stakeholder_view(), C.MethodResult(deltas=(T.Add(forced),))) == []


def test_stakeholder_refuses_a_figure_the_cited_inputs_do_not_carry():
    view = _stakeholder_view()
    provider = scripted("stakeholder", [
        out(T.Kind.STAKEHOLDER, "the ops lead", ["BCX-1"], name="ops lead", role="runs a team of 18"),
    ])
    result = C.METHODS.get("stakeholder").run(ctx_for(view, provider))
    assert added(result, T.Kind.STAKEHOLDER) == []
    assert "M.stakeholder.coined_quantity" in laws(result)


# ---------------------------------------------------------------------------
# process_map and journey
# ---------------------------------------------------------------------------

def _step_view(*extra: T.Entity) -> FakeView:
    return FakeView(source(), issue(T.Interrogative.HOW, T.Kind.PROCESS_STEP),
                    fact("FCT-1", "orders arrive by email"),
                    fact("FCT-2", "orders are keyed into the system"),
                    ent(T.Kind.STAKEHOLDER, entity_id="STK-1"),
                    ent(T.Kind.CAPABILITY,
                        T.CapabilityPayload(text="order intake", capability_class=T.CapabilityClass.SOFTWARE_SYSTEM,
                                            gap=T.GapState.PRESENT, evidence=("FCT-1",)),
                        entity_id="CAP-1"),
                    *extra)


def test_process_map_numbers_the_steps_it_keeps_and_stamps_its_own_perspective():
    # P1 and P2: the model proposes an order, the registry numbers it; the
    # perspective is the method's declared subject, not a model field.
    view = _step_view()
    provider = scripted("process_map", [
        out(T.Kind.PROCESS_STEP, "orders are keyed in", ["FCT-2"], sequence=7, system_ids=["CAP-1"],
            actor_id="STK-1", pain_point="true"),
        out(T.Kind.PROCESS_STEP, "orders arrive by email", ["FCT-1"], sequence=3,
            perspective="customer"),
    ])
    result = C.METHODS.get("process_map").run(ctx_for(view, provider))
    steps = added(result, T.Kind.PROCESS_STEP)
    assert [s.payload.sequence for s in steps] == [1, 2]
    assert [s.payload.text for s in steps] == ["orders arrive by email", "orders are keyed in"]
    assert all(s.payload.perspective is T.StepPerspective.INTERNAL for s in steps)
    keyed = steps[1]
    assert keyed.payload.system_ids == ("CAP-1",) and keyed.payload.actor_id == "STK-1"
    assert keyed.payload.pain_point is True and keyed.payload.evidence == ("FCT-2",)
    assert run_validators(PM.SPEC, view, result) == []


def test_a_step_that_states_no_place_is_refused_rather_than_positioned():
    view = _step_view()
    provider = scripted("process_map", [
        out(T.Kind.PROCESS_STEP, "somewhere in the middle", ["FCT-1"]),
        out(T.Kind.PROCESS_STEP, "orders are keyed in", ["FCT-2"], sequence="2"),
    ])
    result = C.METHODS.get("process_map").run(ctx_for(view, provider))
    steps = added(result, T.Kind.PROCESS_STEP)
    # the refusal leaves no gap: the survivor is numbered 1, not 2
    assert [(s.payload.text, s.payload.sequence) for s in steps] == [("orders are keyed in", 1)]
    assert "M.process_map.unplaced_step" in laws(result)


def test_a_pain_point_is_only_the_flag_the_model_actually_set():
    view = _step_view()
    provider = scripted("process_map", [
        out(T.Kind.PROCESS_STEP, "orders arrive by email", ["FCT-1"], sequence=1, pain_point="false"),
    ])
    step = added(C.METHODS.get("process_map").run(ctx_for(view, provider)), T.Kind.PROCESS_STEP)[0]
    assert step.payload.pain_point is False


def test_process_map_capabilities_carry_the_class_the_method_declared():
    # P3: a model relabelling a process finding into a software system would
    # route it to the wrong lane of every downstream plan.
    view = _step_view()
    provider = scripted("process_map", [
        out(T.Kind.CAPABILITY, "order handling", ["FCT-1", "FCT-2"], gap="partial",
            capability_class="software_system"),
        out(T.Kind.CAPABILITY, "unstated gap", ["FCT-1"], capability_class="process"),
    ])
    result = C.METHODS.get("process_map").run(ctx_for(view, provider))
    caps = added(result, T.Kind.CAPABILITY)
    assert [c.payload.capability_class for c in caps] == [T.CapabilityClass.PROCESS]
    assert caps[0].payload.gap is T.GapState.PARTIAL
    assert "M.process_map.gap_vocabulary" in laws(result)


def test_process_map_sequential_validator_fires_on_a_gapped_result():
    # MUTATION "remove a validator from process_map's spec" is caught here.
    view = _step_view()
    gapped = [
        ent(T.Kind.PROCESS_STEP,
            T.ProcessStepPayload(text="one", perspective=T.StepPerspective.INTERNAL, sequence=1,
                                 evidence=("FCT-1",)),
            entity_id="PST-1", derived_from=("FCT-1",), actor=T.Actor.METHOD),
        ent(T.Kind.PROCESS_STEP,
            T.ProcessStepPayload(text="three", perspective=T.StepPerspective.INTERNAL, sequence=3,
                                 evidence=("FCT-2",)),
            entity_id="PST-2", derived_from=("FCT-2",), actor=T.Actor.METHOD),
    ]
    found = run_validators(PM.SPEC, view, C.MethodResult(deltas=tuple(T.Add(s) for s in gapped)))
    assert "M.process_map.non_sequential_steps" in found
    # Negative control: 1..2 raises nothing.
    fixed = dataclasses.replace(gapped[1], payload=dataclasses.replace(gapped[1].payload, sequence=2))
    assert run_validators(PM.SPEC, view, C.MethodResult(deltas=(T.Add(gapped[0]), T.Add(fixed)))) == []


def test_journey_stamps_the_customer_perspective_and_resolves_its_actor():
    view = _step_view()
    provider = scripted("journey", [
        out(T.Kind.PROCESS_STEP, "the customer emails an order", ["FCT-1"], sequence=1,
            actor_id="STK-1", pain_point=True),
        out(T.Kind.PROCESS_STEP, "the customer waits", ["FCT-2"], sequence=2, actor_id="STK-404"),
    ])
    result = C.METHODS.get("journey").run(ctx_for(view, provider))
    steps = added(result, T.Kind.PROCESS_STEP)
    assert [s.payload.perspective for s in steps] == [T.StepPerspective.CUSTOMER] * 2
    assert steps[0].payload.actor_id == "STK-1"
    assert steps[1].payload.actor_id is None      # an actor nobody registered is not recorded
    assert run_validators(JN.SPEC, view, result) == []


def test_journey_perspective_validator_fires_on_an_internal_step():
    # MUTATION "remove a validator from journey's spec" is caught here: a
    # step filed under the wrong perspective changes which work products the
    # engagement gets and prints an experience nobody had.
    view = _step_view()
    internal = ent(T.Kind.PROCESS_STEP,
                   T.ProcessStepPayload(text="a back-office handover", perspective=T.StepPerspective.INTERNAL,
                                        sequence=1, evidence=("FCT-1",)),
                   entity_id="PST-1", derived_from=("FCT-1",), actor=T.Actor.METHOD)
    found = run_validators(JN.SPEC, view, C.MethodResult(deltas=(T.Add(internal),)))
    assert "M.journey.wrong_perspective" in found
    ok = dataclasses.replace(internal,
                             payload=dataclasses.replace(internal.payload,
                                                         perspective=T.StepPerspective.CUSTOMER))
    assert run_validators(JN.SPEC, view, C.MethodResult(deltas=(T.Add(ok),))) == []


def test_a_pain_point_without_evidence_among_its_citations_is_a_finding():
    view = _step_view()
    bad = ent(T.Kind.PROCESS_STEP,
              T.ProcessStepPayload(text="the wait", perspective=T.StepPerspective.CUSTOMER, sequence=1,
                                   pain_point=True, evidence=("FCT-9",)),
              entity_id="PST-1", derived_from=("FCT-1",), actor=T.Actor.METHOD)
    assert "M.journey.uncited_pain_point" in run_validators(
        JN.SPEC, view, C.MethodResult(deltas=(T.Add(bad),)))


# ---------------------------------------------------------------------------
# capability_gap
# ---------------------------------------------------------------------------

def _capability_view() -> FakeView:
    return FakeView(source(), issue(T.Interrogative.WHAT, T.Kind.CAPABILITY),
                    ent(T.Kind.OBJECTIVE, entity_id="OBJ-1"),
                    fact("FCT-1", "orders are keyed in by hand"))


def test_capability_gap_writes_a_stated_gap_and_refuses_an_unstated_one():
    view = _capability_view()
    provider = scripted("capability_gap", [
        out(T.Kind.CAPABILITY, "automated order intake", ["OBJ-1", "FCT-1"], gap="missing",
            capability_class="process"),
        out(T.Kind.CAPABILITY, "something", ["FCT-1"], capability_class="process"),
    ])
    result = C.METHODS.get("capability_gap").run(ctx_for(view, provider))
    caps = added(result, T.Kind.CAPABILITY)
    assert len(caps) == 1 and caps[0].payload.gap is T.GapState.MISSING
    assert caps[0].payload.evidence == ("OBJ-1", "FCT-1")
    assert "M.capability_gap.gap_vocabulary" in laws(result)
    assert run_validators(CG.SPEC, view, result) == []


def test_capability_gap_validator_fires_when_the_evidence_is_not_cited():
    # MUTATION "remove a validator from capability_gap's spec" is caught here.
    view = _capability_view()
    bad = ent(T.Kind.CAPABILITY,
              T.CapabilityPayload(text="automated intake", capability_class=T.CapabilityClass.PROCESS,
                                  gap=T.GapState.MISSING, evidence=("FCT-9",)),
              entity_id="CAP-9", derived_from=("FCT-1",), actor=T.Actor.METHOD)
    assert "M.capability_gap.gap_without_evidence" in run_validators(
        CG.SPEC, view, C.MethodResult(deltas=(T.Add(bad),)))
    ok = dataclasses.replace(bad, payload=dataclasses.replace(bad.payload, evidence=("FCT-1",)))
    assert run_validators(CG.SPEC, view, C.MethodResult(deltas=(T.Add(ok),))) == []


# ---------------------------------------------------------------------------
# the family's shared laws
# ---------------------------------------------------------------------------

def test_an_output_citing_ids_it_was_never_shown_never_enters_the_registry():
    for module in MODEL_ASSISTED:
        spec = module.SPEC
        view = _step_view() if spec.id in ("process_map", "journey") else (
            _capability_view() if spec.id == "capability_gap" else (
                _stakeholder_view() if spec.id == "stakeholder" else _root_cause_view()))
        kind = next(k for k in spec.output_kinds if k is not T.Kind.QUESTION)
        provider = scripted(spec.id, [
            out(kind, "a proposal resting on nothing", [], sequence=1, gap="missing", name="x",
                causes=["FCT-1"]),
            out(kind, "a proposal resting on a hallucinated id", ["XXX-999"], sequence=1, gap="missing",
                name="y", causes=["XXX-999"]),
        ])
        result = C.METHODS.get(spec.id).run(ctx_for(view, provider))
        assert result.deltas == (), f"{spec.id} admitted an uncited output"
        assert laws(result).count(f"M.{spec.id}.uncited_output") == 2


def test_no_diagnostic_output_carries_a_quantity_that_is_not_copied_by_id():
    # EvidenceRequirement.forbid_new_quantities, end to end: every model
    # sheet below points quantity_from at a row that carries no quantity, and
    # nothing numeric survives into any payload.
    for module in MODEL_ASSISTED:
        spec = module.SPEC
        view = _step_view() if spec.id in ("process_map", "journey") else (
            _capability_view() if spec.id == "capability_gap" else (
                _stakeholder_view() if spec.id == "stakeholder" else _root_cause_view()))
        kind = next(k for k in spec.output_kinds if k is not T.Kind.QUESTION)
        cite = "FCT-1" if spec.id != "stakeholder" else "BCX-1"
        body = out(kind, "a proposal", [cite, "FCT-2"] if spec.id == "root_cause" else [cite],
                   sequence=1, gap="missing", name="a person", causes=[cite])
        body["quantity_from"] = cite
        result = C.METHODS.get(spec.id).run(ctx_for(view, scripted(spec.id, [body])))
        for d in result.deltas:
            q = getattr(d.entity.payload, "quantity", None)
            assert q is None, f"{spec.id} wrote a quantity from a row that carries none"
        assert f"M.{spec.id}.coined_quantity" in laws(result)


def test_every_diagnostic_output_is_proposed_and_cites_what_it_rests_on():
    view = _root_cause_view()
    provider = scripted("root_cause", [
        out(T.Kind.HYPOTHESIS, "a cause", ["FCT-1", "FCT-2"], causes=["FCT-1"]),
    ])
    result = C.METHODS.get("root_cause").run(ctx_for(view, provider))
    for d in result.deltas:
        assert d.entity.status is T.Status.PROPOSED
        assert d.entity.provenance.derived_from
        assert d.entity.provenance.actor is T.Actor.METHOD


def test_the_shared_figure_scan_reads_ids_as_names_not_numbers():
    assert CG.coined_figures(["FCT-12 explains CAP-3"], [""]) == ()
    assert CG.coined_figures(["it costs 250"], ["we spent 250 last year"]) == ()
    assert CG.coined_figures(["it costs 250"], ["we spent 40 last year"]) == ("250",)
    assert CG.coined_figures(["1,250 orders"], ["1250 orders arrived"]) == ()


def test_the_shared_evidence_gate_asks_both_questions_separately():
    # Strength of evidence and right to say so are different questions, and
    # both must pass. A method summarising CONFIRMED client facts still
    # writes a current-state FACT as PROPOSED, because a method is not a
    # record (MAY_CONFIRM[VERIFIED_RECORD] is DOCUMENT and CALCULATOR).
    view = FakeView(source(), fact("FCT-1", "forty heads", status=T.Status.CONFIRMED),
                    fact("FCT-2", "fifty heads"))
    req = C.EvidenceRequirement()
    assert CG.evidenced_status(view, req, ("FCT-1",), T.Actor.METHOD,
                               T.Authority.CONSULTANT) is T.Status.CONFIRMED
    assert CG.evidenced_status(view, req, ("FCT-1",), T.Actor.METHOD,
                               T.Authority.VERIFIED_RECORD) is T.Status.PROPOSED
    # a merely proposed input, an unresolvable one, and no input at all: all
    # decide downwards, never upwards
    assert CG.evidenced_status(view, req, ("FCT-2",), T.Actor.METHOD,
                               T.Authority.CONSULTANT) is T.Status.PROPOSED
    assert CG.evidenced_status(view, req, ("FCT-404",), T.Actor.METHOD,
                               T.Authority.CONSULTANT) is T.Status.PROPOSED
    assert CG.evidenced_status(view, req, (), T.Actor.METHOD,
                               T.Authority.CONSULTANT) is T.Status.PROPOSED


def test_the_shared_flag_and_sequence_parsers_never_invent_a_value():
    assert CG.flag_of("false") is False and CG.flag_of("no") is False
    assert CG.flag_of(True) is True and CG.flag_of("yes") is True
    assert CG.int_of("0") is None and CG.int_of("later") is None and CG.int_of(None) is None
    assert CG.int_of(" 3 ") == 3


@pytest.mark.parametrize("module", DIAGNOSTIC, ids=lambda m: m.SPEC.id)
def test_every_input_spec_filters_on_structural_fields_only(module):
    # M2 as declared by this family: a filter on prose would make method
    # selection readable by vocabulary, which is the thing universality rests
    # on not being possible.
    for inp in module.SPEC.required_inputs + module.SPEC.optional_inputs:
        assert set(inp.filter) <= T.FILTERABLE_FIELDS
        assert inp.why_needed or inp in module.SPEC.optional_inputs
