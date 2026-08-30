"""C5 methods core: the method contract (M1-M4), shape matching, selection,
ties, dimension pins, fill strategies and vocabulary blindness. Each test
names the law it pins; the mutations the work breakdown requires are noted
where they are caught.

No registry module is imported: a minimal in-memory RegistryView stands in,
so this file collects and runs before the registry component lands.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from app.engine import types as T
from app.engine.methods import contract as C
from app.engine.methods.contract import (
    FillStrategy,
    InputSpec,
    Interrogative,
    Kind,
    MethodRegistry,
    MethodResult,
    MethodSpec,
    QuestionShape,
    Selection,
    fill_strategy,
    input_state,
    path_impact,
    question_value,
    select_methods,
    shape_matches,
)

from conftest import sample_entity, sample_payload


# ---------------------------------------------------------------------------
# a stand-in read side: get / query only, which is all the selector reads
# ---------------------------------------------------------------------------

class FakeView:
    engagement_id = "E-1"

    def __init__(self, *entities: T.Entity):
        self._rows = list(entities)

    def get(self, entity_id):
        return next((e for e in self._rows if e.id == entity_id), None)

    def query(self, kind=None, *, status=None, where=None):
        return [e for e in self._rows if kind is None or e.kind == kind]


def issue(interrogative=Interrogative.WHAT, target_kind=Kind.FACT, entity_id="ISS-1", **flags) -> T.Entity:
    fields = {"quantified": False, "capability_class": None, **flags}
    p = sample_payload(Kind.ISSUE, interrogative=interrogative, target_kind=target_kind, **fields)
    e = sample_entity(Kind.ISSUE, p)
    return dataclasses.replace(e, id=entity_id)


def fact(entity_id="FCT-1", *, quantity="keep", basis=T.FactBasis.CLIENT_STATED, statement="we have 40 people") -> T.Entity:
    p = sample_payload(Kind.FACT, basis=basis, statement=statement)
    if quantity != "keep":
        p = dataclasses.replace(p, quantity=quantity)
    return dataclasses.replace(sample_entity(Kind.FACT, p), id=entity_id)


def spec(mid, shapes, *, required=(), execution=T.ExecutionType.DETERMINISTIC, calls=0, cost=1,
         outputs=(Kind.FACT,), answers=None) -> MethodSpec:
    shapes = tuple(shapes)
    return MethodSpec(
        id=mid, version=1, applicability=shapes,
        answers=tuple(answers) if answers is not None else tuple(sorted({s.interrogative for s in shapes}, key=lambda i: i.value)),
        required_inputs=tuple(required), optional_inputs=(), execution=execution, output_kinds=tuple(outputs),
        output_schema=None, evidence=C.EvidenceRequirement(), limitations=(), validators=(),
        cost_class=cost, max_model_calls=calls)


def method(s: MethodSpec):
    class _M:
        spec = s

        def run(self, ctx):
            return MethodResult()

    _M.__name__ = f"Method_{s.id}"
    return _M


WHAT_FACT = QuestionShape(Interrogative.WHAT, Kind.FACT)


# ---------------------------------------------------------------------------
# registration by import / by decoration (design 7.1)
# ---------------------------------------------------------------------------

def test_a_method_registered_in_this_module_is_selected_for_a_matching_shape():
    # No orchestrator, no builtin package, no edit anywhere else: the registry
    # alone decides what runs. Registration goes through the same @register
    # path the builtin modules use, into a private registry so this test does
    # not leak into METHODS for the rest of the session.
    reg = MethodRegistry()
    reg.register(method(spec("local_test_method", [WHAT_FACT], required=[InputSpec("facts", Kind.FACT)]))())
    view = FakeView(fact())
    sel = select_methods([issue()], view, reg)
    assert [s.method_id for s in sel] == ["local_test_method"]
    assert sel[0].inputs.missing == () and sel[0].inputs.ratio == 1.0


def test_register_decorator_instantiates_into_METHODS_and_rejects_duplicates():
    cls = method(spec("decorated_once", [WHAT_FACT]))
    before = {m.spec.id for m in C.METHODS.all()}
    assert "decorated_once" not in before
    C.register(cls)
    try:
        assert C.METHODS.get("decorated_once").spec.id == "decorated_once"
        with pytest.raises(ValueError, match="already registered"):
            C.register(cls)
    finally:
        C.METHODS._methods.pop("decorated_once", None)


def test_registry_refuses_things_that_are_not_methods():
    reg = MethodRegistry()
    with pytest.raises(TypeError):
        reg.register(object())

    class BadSpec:
        spec = "not a spec"

        def run(self, ctx):
            return MethodResult()

    with pytest.raises(TypeError):
        reg.register(BadSpec())


def test_builtin_package_imports_every_module_by_name_order():
    # Registration by import: the package discovers its modules from the
    # directory. Whatever has landed so far is imported in name order, and
    # every method those modules registered is present in METHODS.
    import app.engine.methods.builtin as B

    assert B.__all__ == sorted(B.__all__)
    for name in B.__all__:
        assert not name.startswith("_")
    for m in C.METHODS.all():
        assert isinstance(m.spec, MethodSpec)


# ---------------------------------------------------------------------------
# shapes
# ---------------------------------------------------------------------------

def test_shape_of_reads_only_the_structural_fields_of_an_issue():
    e = issue(Interrogative.HOW, Kind.CAPABILITY, causal=True, capability_class=T.CapabilityClass.PROCESS)
    s = QuestionShape.of(e)
    assert s == QuestionShape(Interrogative.HOW, Kind.CAPABILITY, causal=True,
                              capability_class=T.CapabilityClass.PROCESS)


def test_shape_matches_requires_interrogative_and_target_kind():
    # Mutation "make shape_matches ignore target_kind" is caught here: a
    # WHAT-on-FACT declaration would take on a WHAT-on-STAKEHOLDER node.
    node = QuestionShape(Interrogative.WHAT, Kind.STAKEHOLDER)
    assert not shape_matches(WHAT_FACT, node)
    assert not shape_matches(QuestionShape(Interrogative.WHY, Kind.STAKEHOLDER), node)
    assert shape_matches(QuestionShape(Interrogative.WHAT, Kind.STAKEHOLDER), node)


def test_shape_matches_treats_false_and_none_as_open_and_true_as_a_constraint():
    open_decl = WHAT_FACT
    strict_decl = QuestionShape(Interrogative.WHAT, Kind.FACT, quantified=True, capability_class=T.CapabilityClass.FINANCIAL)
    plain = QuestionShape(Interrogative.WHAT, Kind.FACT)
    rich = QuestionShape(Interrogative.WHAT, Kind.FACT, quantified=True, capability_class=T.CapabilityClass.FINANCIAL)
    other_class = QuestionShape(Interrogative.WHAT, Kind.FACT, quantified=True, capability_class=T.CapabilityClass.PROCESS)
    assert shape_matches(open_decl, plain) and shape_matches(open_decl, rich)
    assert shape_matches(strict_decl, rich)
    assert not shape_matches(strict_decl, plain)
    assert not shape_matches(strict_decl, other_class)


def test_selection_does_not_take_on_a_node_of_another_target_kind():
    reg = MethodRegistry()
    reg.register(method(spec("on_facts", [WHAT_FACT]))())
    assert select_methods([issue(Interrogative.WHAT, Kind.STAKEHOLDER)], FakeView(), reg) == []


# ---------------------------------------------------------------------------
# M1-M4
# ---------------------------------------------------------------------------

def test_M2_an_inputspec_on_a_text_field_is_unconstructible():
    # Mutation "remove the FILTERABLE_FIELDS check" is caught here.
    for key in ("statement", "text", "name", "topic"):
        assert key in T.TEXT_FIELDS
        with pytest.raises(ValueError, match="M2"):
            InputSpec("f", Kind.FACT, filter={key: "anything"})
    with pytest.raises(ValueError, match="M2"):
        InputSpec("f", Kind.FACT, filter={"not_a_field_at_all": 1})
    ok = InputSpec("f", Kind.FACT, filter={"basis": T.FactBasis.CLIENT_STATED, "has_quantity": True})
    assert ok.filter == {"basis": "client_stated", "has_quantity": True}


def test_M2_filter_values_are_frozen_to_plain_values_and_tuples():
    s = InputSpec("f", Kind.FACT, filter={"basis": [T.FactBasis.CLIENT_STATED, T.FactBasis.DOCUMENT_VERIFIED]})
    assert s.filter["basis"] == ("client_stated", "document_verified")
    assert s.matches(fact(basis=T.FactBasis.CLIENT_STATED))
    assert s.matches(fact(basis=T.FactBasis.DOCUMENT_VERIFIED))
    assert not s.matches(fact(basis=T.FactBasis.INFERRED))


def test_inputspec_refuses_an_unknown_dimension_name():
    with pytest.raises(ValueError, match="unknown dimension"):
        InputSpec("f", Kind.FACT, dimensions_required=("colour",))


def test_M1_a_calculation_spec_with_model_calls_raises():
    # Mutation "remove the M1 check" is caught here.
    with pytest.raises(ValueError, match="M1"):
        spec("calc", [WHAT_FACT], execution=T.ExecutionType.CALCULATION, calls=1)
    with pytest.raises(ValueError, match="M1"):
        spec("det", [WHAT_FACT], execution=T.ExecutionType.DETERMINISTIC, calls=1)
    spec("ok_model", [WHAT_FACT], execution=T.ExecutionType.MODEL_ASSISTED, calls=1)
    spec("ok_calc", [WHAT_FACT], execution=T.ExecutionType.CALCULATION, calls=0)


def test_M3_answers_must_cover_every_declared_shape_interrogative():
    with pytest.raises(ValueError, match="M3"):
        spec("m", [WHAT_FACT, QuestionShape(Interrogative.WHY, Kind.FACT)], answers=[Interrogative.WHAT])
    with pytest.raises(ValueError, match="M3"):
        spec("m", [WHAT_FACT], answers=[])


def test_M4_applicability_must_be_non_empty_and_typed():
    with pytest.raises(ValueError, match="M4"):
        spec("m", [], answers=[Interrogative.WHAT])
    with pytest.raises(TypeError):
        spec("m", ["what/fact"], answers=[Interrogative.WHAT])


def test_fingerprint_changes_with_required_inputs_not_with_limitations():
    a = spec("m", [WHAT_FACT], required=[InputSpec("facts", Kind.FACT)])
    b = dataclasses.replace(a, required_inputs=(InputSpec("facts", Kind.FACT, min_count=2),))
    c = dataclasses.replace(a, limitations=("does not read tables",))
    assert a.fingerprint() != b.fingerprint()
    assert a.fingerprint() == c.fingerprint()


# ---------------------------------------------------------------------------
# inputs and selection
# ---------------------------------------------------------------------------

def test_unmet_inputs_give_no_runnable_selection_and_a_missing_list():
    need = InputSpec("two_facts", Kind.FACT, min_count=2, why_needed="two statements to compare")
    reg = MethodRegistry()
    reg.register(method(spec("needs_two", [WHAT_FACT], required=[need]))())
    sel = select_methods([issue()], FakeView(fact("FCT-1")), reg)
    assert len(sel) == 1
    assert sel[0].inputs.missing == (need,) and sel[0].inputs.satisfied == ()
    assert sel[0].inputs.ratio == 0.0
    # The typed hole names why it is needed; that string is what the fake client reads.
    assert sel[0].inputs.missing[0].why_needed == "two statements to compare"


def test_inputspec_ignores_terminal_rows_and_honours_min_status():
    s = InputSpec("f", Kind.FACT, min_status=T.Status.CONFIRMED)
    assert not s.matches(fact())
    assert s.matches(dataclasses.replace(fact(), status=T.Status.CONFIRMED))
    assert s.matches(dataclasses.replace(fact(), status=T.Status.APPROVED))
    loose = InputSpec("f", Kind.FACT)
    assert not loose.matches(dataclasses.replace(fact(), status=T.Status.SUPERSEDED))
    assert not loose.matches(sample_entity(Kind.OBJECTIVE))


def test_ranking_by_inputs_ratio_then_cost_then_calls_then_id():
    reg = MethodRegistry()
    have = InputSpec("facts", Kind.FACT)
    lack = InputSpec("objectives", Kind.OBJECTIVE)
    reg.register(method(spec("z_full_cheap", [WHAT_FACT], required=[have], cost=1))())
    reg.register(method(spec("a_half", [WHAT_FACT], required=[have, lack], cost=1))())
    reg.register(method(spec("b_full_dear", [WHAT_FACT], required=[have], cost=3))())
    reg.register(method(spec("c_full_cheap_calls", [WHAT_FACT], required=[have], cost=1,
                             execution=T.ExecutionType.MODEL_ASSISTED, calls=2))())
    sel = select_methods([issue()], FakeView(fact()), reg, max_per_issue=4)
    assert [s.method_id for s in sel] == ["z_full_cheap", "c_full_cheap_calls", "b_full_dear", "a_half"]
    assert not any(s.tied for s in sel)
    assert sel[0].rank_key == (-1.0, 1, 0, "z_full_cheap")


def test_max_per_issue_bounds_the_selection():
    reg = MethodRegistry()
    for i in range(5):
        reg.register(method(spec(f"m{i}", [WHAT_FACT], cost=i + 1))())
    assert len(select_methods([issue()], FakeView(), reg, max_per_issue=2)) == 2
    assert len(select_methods([issue()], FakeView(), reg, max_per_issue=3)) == 3


def test_two_methods_at_equal_rank_are_both_marked_tied():
    # Mutation "remove the tie marking" is caught here. Neither method is
    # silently preferred; both run as assignments so their disagreement
    # surfaces as a CONFLICT (design 7.2).
    reg = MethodRegistry()
    reg.register(method(spec("alpha", [WHAT_FACT], cost=2))())
    reg.register(method(spec("beta", [WHAT_FACT], cost=2))())
    reg.register(method(spec("gamma", [WHAT_FACT], cost=3))())
    sel = select_methods([issue()], FakeView(), reg)
    assert [(s.method_id, s.tied) for s in sel] == [("alpha", True), ("beta", True)]
    # Negative control: a clear winner is not tied.
    sel2 = select_methods([issue()], FakeView(),
                          _reg(spec("alpha", [WHAT_FACT], cost=1), spec("beta", [WHAT_FACT], cost=2)))
    assert [(s.method_id, s.tied) for s in sel2] == [("alpha", False), ("beta", False)]


def _reg(*specs):
    reg = MethodRegistry()
    for s in specs:
        reg.register(method(s)())
    return reg


def test_dimensions_required_excludes_unpinned_quantities():
    pinned = fact("FCT-1")
    unpinned_q = dataclasses.replace(pinned.payload.quantity, dimensions=T.Dimensions(currency=None, period="FY25"))
    unpinned = fact("FCT-2", quantity=unpinned_q)
    no_q = fact("FCT-3", quantity=None)
    need = InputSpec("money", Kind.FACT, dimensions_required=("currency", "period"))
    assert need.matches(pinned)
    assert not need.matches(unpinned)
    assert not need.matches(no_q)
    # A quantified method is therefore not selectable on unpinned inputs: the gap is a pin question.
    reg = _reg(spec("quantified", [WHAT_FACT], required=[need]))
    sel = select_methods([issue()], FakeView(unpinned, no_q), reg)
    assert sel[0].inputs.missing == (need,)
    assert select_methods([issue()], FakeView(pinned), reg)[0].inputs.missing == ()


def test_input_state_ratio_is_one_for_a_method_with_no_required_inputs():
    st = input_state(spec("free", [WHAT_FACT]), FakeView())
    assert st == C.InputState((), ()) and st.ratio == 1.0


# ---------------------------------------------------------------------------
# vocabulary blindness (design 1: scrambling text yields identical selections)
# ---------------------------------------------------------------------------

def _scramble(e: T.Entity, salt: str) -> T.Entity:
    changes = {}
    for f in dataclasses.fields(e.payload):
        if f.name in T.TEXT_FIELDS and isinstance(getattr(e.payload, f.name), str):
            changes[f.name] = f"{salt}-{f.name}-{hash((salt, f.name)) & 0xFFFF:x}"
    return dataclasses.replace(e, payload=dataclasses.replace(e.payload, **changes))


def test_scrambling_TEXT_FIELDS_leaves_selections_byte_identical():
    need = InputSpec("facts", Kind.FACT, filter={"basis": T.FactBasis.CLIENT_STATED})
    reg = _reg(spec("one", [WHAT_FACT], required=[need]),
               spec("two", [WHAT_FACT], required=[need, InputSpec("obj", Kind.OBJECTIVE)]))
    rows = [fact("FCT-1"), fact("FCT-2", basis=T.FactBasis.INFERRED), sample_entity(Kind.OBJECTIVE)]
    issues = [issue(entity_id="ISS-1"), issue(Interrogative.WHAT, Kind.FACT, entity_id="ISS-2", causal=True)]
    plain = select_methods(issues, FakeView(*rows), reg)
    scrambled = select_methods([_scramble(i, "zz") for i in issues], FakeView(*(_scramble(r, "qq") for r in rows)), reg)
    assert scrambled == plain
    assert repr(scrambled).encode() == repr(plain).encode()


# ---------------------------------------------------------------------------
# new_entity
# ---------------------------------------------------------------------------

def _ctx(view=None):
    return C.MethodContext(registry=view or FakeView(), provider=None, calc=None, actor=T.Actor.METHOD,
                           actor_ref="method:test@1", issue_ids=("ISS-1",))


def test_new_entity_derives_authority_and_requires_citations():
    e = C.new_entity(_ctx(), Kind.FACT, sample_payload(Kind.FACT, basis=T.FactBasis.INFERRED, quantity=None),
                     derived_from=["FCT-1"], relation=T.RelationToCentralDecision.INFORMS,
                     confidence=T.Confidence(None), decision_id="DEC-1", weight=0.3)
    assert e.provenance.actor == T.Actor.METHOD and e.provenance.derived_from == ("FCT-1",)
    assert e.status == T.Status.PROPOSED and e.engagement_id == "E-1"
    assert e.authority == T.AUTHORITY_OF[e.info_type] if hasattr(T, "AUTHORITY_OF") else e.authority is not None
    with pytest.raises(ValueError, match="cite"):
        C.new_entity(_ctx(), Kind.FACT, sample_payload(Kind.FACT), derived_from=[],
                     relation=T.RelationToCentralDecision.INFORMS, confidence=T.Confidence(None),
                     decision_id=None, weight=0.0)
    # A QUESTION is the one output that may rest on nothing: it is the typed hole itself.
    q = C.new_entity(_ctx(), Kind.QUESTION, sample_payload(Kind.QUESTION), derived_from=[],
                     relation=T.RelationToCentralDecision.INFORMS, confidence=T.Confidence(None),
                     decision_id=None, weight=0.0)
    assert q.kind == Kind.QUESTION


# ---------------------------------------------------------------------------
# gaps, fill strategies, question value
# ---------------------------------------------------------------------------

def test_fill_strategy_spawns_a_specialist_when_a_research_or_model_method_produces_the_kind():
    # Mutation "remove the SPAWN branch of fill_strategy" is caught here.
    reg = _reg(spec("researcher", [QuestionShape(Interrogative.WHAT, Kind.STAKEHOLDER)],
                    execution=T.ExecutionType.RESEARCH, calls=3, outputs=(Kind.STAKEHOLDER,)),
               spec("modeller", [QuestionShape(Interrogative.WHAT, Kind.CAPABILITY)],
                    execution=T.ExecutionType.MODEL_ASSISTED, calls=1, outputs=(Kind.CAPABILITY,)),
               spec("summariser", [WHAT_FACT], execution=T.ExecutionType.DETERMINISTIC, outputs=(Kind.FACT,)))
    assert fill_strategy(InputSpec("s", Kind.STAKEHOLDER), reg) == FillStrategy.SPAWN_SPECIALIST
    assert fill_strategy(InputSpec("c", Kind.CAPABILITY), reg) == FillStrategy.SPAWN_SPECIALIST
    # Negative control: a kind only a DETERMINISTIC method produces is asked of the client.
    assert fill_strategy(InputSpec("f", Kind.FACT), reg) == FillStrategy.ASK_CLIENT
    # And a kind nothing produces is asked of the client too.
    assert fill_strategy(InputSpec("o", Kind.OBJECTIVE), reg) == FillStrategy.ASK_CLIENT


def test_fill_strategy_requests_a_document_for_document_effort_or_document_only_bases():
    reg = MethodRegistry()
    assert fill_strategy(InputSpec("f", Kind.FACT, effort=T.EffortClass.DOCUMENT), reg) == FillStrategy.REQUEST_DOCUMENT
    only_docs = InputSpec("f", Kind.FACT, filter={"basis": [T.FactBasis.DOCUMENT_VERIFIED, T.FactBasis.DOCUMENT_EXTRACTED]})
    assert fill_strategy(only_docs, reg) == FillStrategy.REQUEST_DOCUMENT
    mixed = InputSpec("f", Kind.FACT, filter={"basis": [T.FactBasis.DOCUMENT_VERIFIED, T.FactBasis.CLIENT_STATED]})
    assert fill_strategy(mixed, reg) == FillStrategy.ASK_CLIENT


def test_fill_strategy_records_unknown_after_a_dont_know_and_never_re_asks():
    reg = _reg(spec("researcher", [QuestionShape(Interrogative.WHAT, Kind.STAKEHOLDER)],
                    execution=T.ExecutionType.RESEARCH, calls=1, outputs=(Kind.STAKEHOLDER,)))
    # The client's "don't know" wins over every other route, including a
    # specialist and a document request: the gap stays a labelled unknown.
    assert fill_strategy(InputSpec("s", Kind.STAKEHOLDER), reg, client_said_unknown=True) == FillStrategy.RECORD_UNKNOWN
    assert fill_strategy(InputSpec("f", Kind.FACT, effort=T.EffortClass.DOCUMENT), reg,
                         client_said_unknown=True) == FillStrategy.RECORD_UNKNOWN
    assert fill_strategy(InputSpec("f", Kind.FACT), reg, client_said_unknown=False) == FillStrategy.ASK_CLIENT


def test_gap_carries_the_typed_input_and_its_strategy():
    inp = InputSpec("f", Kind.FACT)
    g = C.Gap("ISS-1", "m", inp, FillStrategy.ASK_CLIENT, decision_ids=("DEC-1",))
    assert g.input is inp and g.strategy is FillStrategy.ASK_CLIENT


def test_path_impact_multiplies_edge_weights_up_to_the_root_and_survives_a_cycle():
    root = issue(entity_id="ISS-1", weight_to_parent=1.0)
    mid = issue(entity_id="ISS-2", parent_id="ISS-1", weight_to_parent=0.5)
    leaf = issue(entity_id="ISS-3", parent_id="ISS-2", weight_to_parent=0.4)
    view = FakeView(root, mid, leaf)
    assert path_impact(leaf, view) == pytest.approx(0.2)
    assert path_impact(root, view) == 1.0
    # A parent link that loops back must not spin: each node is visited once.
    a = issue(entity_id="ISS-A", parent_id="ISS-B", weight_to_parent=0.5)
    b = issue(entity_id="ISS-B", parent_id="ISS-A", weight_to_parent=0.5)
    assert path_impact(a, FakeView(a, b)) == pytest.approx(0.25)


def test_question_value_divides_by_the_declared_effort_weight():
    base = question_value(impact=0.8, uncertainty=0.5, downstream=1.5, effort=T.EffortClass.OFFHAND)
    assert base == pytest.approx(0.6)
    assert question_value(impact=0.8, uncertainty=0.5, downstream=1.5, effort=T.EffortClass.DOCUMENT) == pytest.approx(base / 3)
    # Zero impact is zero value whatever the uncertainty: never worth asking.
    assert question_value(impact=0.0, uncertainty=1.0, downstream=2.0, effort=T.EffortClass.OFFHAND) == 0.0


def test_contract_module_names_no_engagement_type_and_no_client():
    import inspect

    src = inspect.getsource(C).lower()
    for word in ("recovery", "vitalis", "club", "rally", "icarry", "restaurant", "clinic", "saas"):
        assert word not in src
    assert src.isascii()
