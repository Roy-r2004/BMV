"""C9 issue_tree: the model proposes ISSUE nodes; the validator admits only
catalogue shapes, cited nodes, method-free text and bounded weights, and a
re-run supersedes rather than duplicates. Each test names the law it pins;
the three named mutations of the work breakdown are caught here:

  accept a method name from the model  -> test_a_node_naming_a_method_is_rejected
  drop the catalogue validator         -> test_off_catalogue_shapes_are_dropped
  allow uncited nodes                  -> test_every_node_cites_registered_entities
"""
from __future__ import annotations

import json

from app.engine import types as T
from app.engine.llm import FakeProvider
from app.engine.methods.contract import METHODS, MethodContext, QuestionShape

import app.engine.methods.builtin  # noqa: F401  (registration by import)
from app.engine.methods.builtin import issue_tree as IT

from conftest import sample_entity, sample_payload


# ---------------------------------------------------------------------------
# fixtures: a registry holding one central decision, one objective and two
# citable context entities; a scripted provider keyed on the method's purpose
# ---------------------------------------------------------------------------

def seeded(registry):
    reg = registry()
    reg.apply(T.Add(sample_entity(T.Kind.DECISION)))       # DEC-1, role CENTRAL
    reg.apply(T.Add(sample_entity(T.Kind.OBJECTIVE)))      # OBJ-1
    reg.apply(T.Add(sample_entity(T.Kind.BUSINESS_CONTEXT)))  # BCX-1
    reg.apply(T.Add(sample_entity(
        T.Kind.FACT, sample_payload(T.Kind.FACT, basis=T.FactBasis.DOCUMENT_EXTRACTED))))  # FCT-1
    return reg


def node(text="what would settle the choice?", temp_id=None, parent_id=None, interrogative="what",
         target_kind="fact", weight=0.6, derived_from=("FCT-1",), decisive_for=("DEC-1",),
         capability_class=None, evidence_needed=None, **flags):
    d = {"text": text, "temp_id": temp_id, "parent_id": parent_id,
         "interrogative": interrogative, "target_kind": target_kind,
         "capability_class": capability_class,
         "quantified": False, "comparative": False, "causal": False, "temporal": False,
         "weight_to_parent": weight,
         "derived_from": list(derived_from), "decisive_for": list(decisive_for),
         "evidence_needed": evidence_needed if evidence_needed is not None else []}
    d.update(flags)
    return d


def provider_for(*nodes, times=1):
    body = json.dumps({"nodes": list(nodes)})
    return FakeProvider(script={"issue_tree": [body] * times})


def ctx_for(reg, provider, **settings):
    return MethodContext(registry=reg, provider=provider, calc=None, actor=T.Actor.PARTNER,
                         actor_ref="method:issue_tree@1", issue_ids=("ISS-0",), settings=settings)


def run(reg, provider, **settings):
    return METHODS.get("issue_tree").run(ctx_for(reg, provider, **settings))


def issues(result):
    return [d.entity for d in result.deltas
            if isinstance(d, (T.Add, T.Supersede)) and d.entity.kind == T.Kind.ISSUE]


# ---------------------------------------------------------------------------
# the spec (design 7.3 row one)
# ---------------------------------------------------------------------------

def test_spec_pins_applicability_inputs_execution_and_outputs():
    spec = METHODS.get("issue_tree").spec
    assert spec.execution == T.ExecutionType.MODEL_ASSISTED and spec.max_model_calls == 2
    assert spec.output_kinds == (T.Kind.ISSUE,)
    covered = {(s.interrogative, s.target_kind) for s in spec.applicability}
    assert covered == {(i, T.Kind.DECISION) for i in (
        T.Interrogative.WHAT, T.Interrogative.WHY, T.Interrogative.HOW,
        T.Interrogative.WHICH, T.Interrogative.HOW_MUCH, T.Interrogative.WHETHER)}
    required = {(i.kind, i.min_count) for i in spec.required_inputs}
    assert required == {(T.Kind.DECISION, 1), (T.Kind.OBJECTIVE, 1)}
    assert spec.output_schema is IT.IssueTreeModel
    # the three laws are declared on the spec, so the runner re-checks them
    assert set(spec.validators) == {IT.validate_catalogue, IT.validate_citations, IT.validate_no_method_names}


# ---------------------------------------------------------------------------
# catalogue law (mutation: drop the catalogue validator)
# ---------------------------------------------------------------------------

def test_off_catalogue_shapes_are_dropped_and_kept_nodes_answer_to_QuestionShape(registry):
    reg = seeded(registry)
    result = run(reg, provider_for(
        node(text="what evidence settles it?"),
        node(text="wherefore the delay?", interrogative="wherefore", target_kind="fact"),
        node(text="which capability?", interrogative="which", target_kind="capability",
             capability_class="sorcery", comparative=True),
    ))
    emitted = issues(result)
    assert len(emitted) == 1 and emitted[0].payload.text == "what evidence settles it?"
    # QuestionShape.of works on every emitted node: the shape the selector
    # reads is exactly the one admitted from the catalogue.
    for e in emitted:
        shape = QuestionShape.of(e)
        assert isinstance(shape.interrogative, T.Interrogative) and isinstance(shape.target_kind, T.Kind)
    assert sum(1 for f in result.findings if f.law == "M.issue_tree.off_catalogue") == 2


def test_evidence_needed_becomes_typed_asks_for_on_structural_fields_only(registry):
    reg = seeded(registry)
    result = run(reg, provider_for(node(evidence_needed=[
        {"kind": "fact", "filter": {"has_quantity": True, "statement": "prose key must go"}},
        {"kind": "wizardry", "filter": {}},
    ])))
    (emitted,) = issues(result)
    assert emitted.payload.evidence_needed == (T.AsksFor(T.Kind.FACT, {"has_quantity": True}),)


# ---------------------------------------------------------------------------
# citation law (mutation: allow uncited nodes)
# ---------------------------------------------------------------------------

def test_every_node_cites_registered_entities(registry):
    reg = seeded(registry)
    result = run(reg, provider_for(
        node(text="what does the record show?", derived_from=("FCT-1", "BCX-1")),
        node(text="why the backlog?", interrogative="why", causal=True, derived_from=()),
        node(text="how much slack?", interrogative="how_much", quantified=True, derived_from=("FCT-99",)),
    ))
    emitted = issues(result)
    assert [e.payload.text for e in emitted] == ["what does the record show?"]
    assert all(reg.get(i) is not None for e in emitted for i in e.provenance.derived_from)
    assert sum(1 for f in result.findings if f.law == "M.issue_tree.uncited") == 2
    # decisive_for is filtered the same way: a coined decision id never lands
    result2 = run(reg, provider_for(node(text="what else?", interrogative="whether",
                                         decisive_for=("DEC-1", "DEC-99"))))
    assert issues(result2)[0].payload.decisive_for == ("DEC-1",)


# ---------------------------------------------------------------------------
# no-method-names law (mutation: accept a method name from the model)
# ---------------------------------------------------------------------------

def test_a_node_naming_a_method_is_rejected(registry):
    reg = seeded(registry)
    # issue_tree itself is registered by importing this module's package, so
    # the check has a guaranteed method id whatever else this wave landed.
    result = run(reg, provider_for(
        node(text="what would settle the choice?"),
        node(text="run issue_tree over the suppliers", interrogative="why", causal=True),
        node(text="build an issue tree of the costs", interrogative="how"),
    ))
    emitted = issues(result)
    assert [e.payload.text for e in emitted] == ["what would settle the choice?"]
    assert sum(1 for f in result.findings if f.law == "M.issue_tree.names_a_method") == 2


# ---------------------------------------------------------------------------
# weight law
# ---------------------------------------------------------------------------

def test_weight_to_parent_is_bounded_to_unit_interval(registry):
    reg = seeded(registry)
    result = run(reg, provider_for(
        node(text="overweighted", weight=1.7),
        node(text="negative", interrogative="why", causal=True, weight=-0.2),
        node(text="kept", interrogative="how_much", target_kind="cost", quantified=True, weight=0.6),
    ))
    emitted = issues(result)
    assert [e.payload.text for e in emitted] == ["kept"]
    assert all(0.0 <= e.payload.weight_to_parent <= 1.0 for e in emitted)
    assert sum(1 for f in result.findings if f.law == "M.issue_tree.weight_out_of_bounds") == 2


# ---------------------------------------------------------------------------
# tree placement: temp ids resolve to real ids; unknown parents drop
# ---------------------------------------------------------------------------

def test_temp_id_parents_resolve_to_real_ids_and_orphans_drop(registry):
    reg = seeded(registry)
    result = run(reg, provider_for(
        # the child is listed FIRST: resolution must not depend on list order
        node(text="why is it late?", temp_id="n2", parent_id="n1", interrogative="why",
             target_kind="hypothesis", causal=True),
        node(text="what drives the choice?", temp_id="n1"),
        node(text="orphan", temp_id="n3", parent_id="n9", interrogative="how"),
    ))
    reg.apply_all(result.deltas)
    live = {e.payload.text: e for e in reg.live(T.Kind.ISSUE)}
    assert set(live) == {"why is it late?", "what drives the choice?"}
    parent = live["what drives the choice?"]
    child = live["why is it late?"]
    assert parent.payload.parent_id is None
    assert child.payload.parent_id == parent.id and parent.id.startswith("ISS-")
    assert any(f.law == "M.issue_tree.unresolvable_parent" for f in result.findings)


# ---------------------------------------------------------------------------
# incremental rebuild: supersede, never duplicate
# ---------------------------------------------------------------------------

def test_rerunning_supersedes_matching_nodes_rather_than_duplicating(registry):
    reg = seeded(registry)
    provider = provider_for(
        node(text="what drives the choice?", temp_id="n1"),
        node(text="why is it late?", temp_id="n2", parent_id="n1", interrogative="why",
             target_kind="hypothesis", causal=True),
        times=2)
    first = run(reg, provider)
    reg.apply_all(first.deltas)
    before = {e.id for e in reg.live(T.Kind.ISSUE)}
    assert len(before) == 2 and all(isinstance(d, T.Add) for d in first.deltas)

    second = run(reg, provider)
    assert second.deltas and all(isinstance(d, T.Supersede) for d in second.deltas)
    reg.apply_all(second.deltas)
    after = reg.live(T.Kind.ISSUE)
    # same ids, same count, higher versions: the tree converged, lineage grew
    assert {e.id for e in after} == before
    assert all(e.version > 1 for e in after)


def test_a_batch_that_restates_its_own_node_emits_it_once(registry):
    reg = seeded(registry)
    result = run(reg, provider_for(
        node(text="what drives the choice?", temp_id="n1"),
        node(text="what drives the choice, reworded?", temp_id="n1b"),  # same shape, same parent
    ))
    assert len(issues(result)) == 1
    assert any(f.law == "M.issue_tree.duplicate" for f in result.findings)


# ---------------------------------------------------------------------------
# bounds come from settings, never a constant in the module
# ---------------------------------------------------------------------------

def test_max_fanout_is_read_from_settings_not_hardcoded(registry):
    reg = seeded(registry)
    provider = provider_for(node())
    run(reg, provider, MAX_FANOUT=4)
    assert "at most 4 children" in provider.calls[0].messages[0]["content"]
    provider2 = provider_for(node())
    run(seeded(registry), provider2)  # no setting: the declared BOUNDS default
    assert f"at most {T.BOUNDS['MAX_FANOUT']} children" in provider2.calls[0].messages[0]["content"]


# ---------------------------------------------------------------------------
# a model that never yields a valid tree blocks visibly, writes nothing
# ---------------------------------------------------------------------------

def test_model_failure_yields_a_finding_and_no_deltas(registry):
    reg = seeded(registry)
    provider = FakeProvider(script={"issue_tree": ["not json", "still not json"]})
    result = run(reg, provider)
    assert result.deltas == ()
    assert [f.law for f in result.findings] == ["M.issue_tree.model_failure"]
    # both declared calls were spent on the retry, none beyond the declaration
    assert len(provider.calls) == 2 <= METHODS.get("issue_tree").spec.max_model_calls


# ---------------------------------------------------------------------------
# the declared validators re-check a finished result (the runner's path)
# ---------------------------------------------------------------------------

def test_spec_validators_flag_a_doctored_result(registry):
    reg = seeded(registry)
    result = run(reg, provider_for(node()))
    assert not [f for v in METHODS.get("issue_tree").spec.validators for f in v(reg, result)]
    # forge an uncited citation by pointing the same entity at a coined id
    import dataclasses
    e = issues(result)[0]
    forged = dataclasses.replace(e, provenance=dataclasses.replace(e.provenance, derived_from=("FCT-99",)))
    bad = dataclasses.replace(result, deltas=(T.Add(forged),))
    assert [f.law for f in IT.validate_citations(reg, bad)] == ["M.issue_tree.uncited"]
