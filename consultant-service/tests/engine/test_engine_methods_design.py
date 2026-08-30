"""C12 design-and-plan methods: org_design, make_buy_partner, operating_model,
systems_data_map, risk_control, prioritization, roadmap, raci_governance,
change_impact, kpi_design.

Each test names the law it pins. The four named mutations of the work
breakdown are caught here:

  remove the cycle check       -> test_roadmap_refuses_a_cyclic_plan
                                  test_systems_map_refuses_the_edge_that_closes_a_cycle
                                  test_validator_catches_a_cycle_in_a_doctored_result
  allow date strings on actions-> test_an_action_dated_by_nobody_is_a_finding
                                  test_a_dated_step_in_a_doctored_result_is_a_finding
  allow an invented baseline   -> test_an_invented_kpi_baseline_is_refused
                                  test_a_baseline_claiming_a_source_it_has_not_got_is_refused
  allow zero accountables      -> test_an_action_with_no_accountable_is_a_finding

The negative control for each is the passing fixture beside it: a plan that is
acyclic, a date a DEADLINE owns, a baseline copied from a registered fact, a
table with exactly one accountable.
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.engine import types as T
from app.engine.llm import FakeProvider
from app.engine.methods.contract import METHODS, MethodContext, QuestionShape, select_methods

import app.engine.methods.builtin  # noqa: F401  (registration by import)
from app.engine.methods.builtin import kpi_design as KPI
from app.engine.methods.builtin import prioritization as PRI
from app.engine.methods.builtin import raci_governance as RACI
from app.engine.methods.builtin import roadmap as RM
from app.engine.methods.builtin import systems_data_map as SDM


DESIGN_METHODS = ("org_design", "make_buy_partner", "operating_model", "systems_data_map",
                  "risk_control", "prioritization", "roadmap", "raci_governance",
                  "change_impact", "kpi_design")


# ---------------------------------------------------------------------------
# helpers: a registry the methods can be run against, and a scripted provider
# ---------------------------------------------------------------------------

def add(reg, kind, payload, *, derived_from=("EVI-1",), actor=T.Actor.PARTNER,
        status=T.Status.PROPOSED, locator=None):
    e = T.make_entity(
        kind=kind, engagement_id=reg.engagement_id, payload=payload,
        provenance=T.Provenance(actor=actor, actor_ref=f"{actor.value}:1", derived_from=tuple(derived_from),
                                source_locator=locator),
        confidence=T.Confidence(None), relevance=T.Relevance("DEC-1", 0.5),
        relation=T.RelationToCentralDecision.INFORMS, status=status)
    return reg.apply(T.Add(e))


def with_decision(registry):
    reg = registry()
    add(reg, T.Kind.DECISION, T.DecisionPayload(statement="which way", role=T.DecisionRole.CENTRAL))
    return reg


def ctx_for(reg, provider=None, *, method_id="test", issue_ids=("ISS-1",)):
    return MethodContext(registry=reg, provider=provider, calc=None, actor=T.Actor.METHOD,
                         actor_ref=f"method:{method_id}@1", issue_ids=issue_ids)


def run(reg, method_id, provider=None):
    return METHODS.get(method_id).run(ctx_for(reg, provider, method_id=method_id))


def scripted(method_id, *outputs, questions=()):
    body = json.dumps({"outputs": list(outputs), "questions": list(questions)})
    return FakeProvider(script={f"method:{method_id}": [body]})


def out(kind, text, *, cites=("FCT-1",), **fields):
    return {"kind": kind, "text": text, "fields": fields, "derived_from": list(cites)}


def written(result, kind):
    return [d.entity for d in result.deltas
            if getattr(d, "entity", None) is not None and d.entity.kind is kind]


def laws(result):
    return [f.law for f in result.findings]


def validate(method_id, view, result):
    findings = []
    for v in METHODS.get(method_id).spec.validators:
        findings.extend(v(view, result))
    return findings


# ---------------------------------------------------------------------------
# the contract every method in the family satisfies (M1-M4, design 7.1)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method_id", DESIGN_METHODS)
def test_every_design_method_is_registered_and_declares_a_lawful_spec(method_id):
    spec = METHODS.get(method_id).spec
    assert spec.applicability and spec.answers                       # M3/M4
    assert all(s.interrogative in spec.answers for s in spec.applicability)
    if spec.execution in T.FREE_EXECUTION:
        assert spec.max_model_calls == 0, "M1: a deterministic method asks a model for nothing"
    assert spec.output_kinds and spec.validators


@pytest.mark.parametrize("method_id", DESIGN_METHODS)
def test_no_input_spec_reads_a_text_field(method_id):
    """M2 at the family level: selection may not turn on prose, which is why
    scrambling every text field cannot change which analysis runs."""
    spec = METHODS.get(method_id).spec
    for inp in spec.required_inputs + spec.optional_inputs:
        assert not (set(inp.filter) & T.TEXT_FIELDS)
        assert set(inp.filter) <= T.FILTERABLE_FIELDS


def test_selection_reaches_a_design_method_by_shape_alone(registry):
    """Design 7.2: an issue node's shape selects the method; no orchestrator
    edit, no engagement type and no wording is involved."""
    reg = with_decision(registry)
    issue = add(reg, T.Kind.ISSUE, T.IssuePayload(
        text="", interrogative=T.Interrogative.WHO, target_kind=T.Kind.GOVERNANCE))
    picked = {s.method_id for s in select_methods([issue], reg, max_per_issue=4)}
    assert "raci_governance" in picked


# ---------------------------------------------------------------------------
# roadmap RD1: the plan is acyclic, and a cyclic one produces nothing
# ---------------------------------------------------------------------------

def plan(registry, *, sequences=(None, None), texts=("stand up intake", "switch over"),
         horizons=(T.Horizon.WEEKS, T.Horizon.MONTHS)):
    reg = with_decision(registry)
    ws = add(reg, T.Kind.WORKSTREAM, T.WorkstreamPayload(name="delivery", purpose="p"))
    ini = add(reg, T.Kind.INITIATIVE, T.InitiativePayload(
        name="first wave", workstream_id=ws.id, capability_class=T.CapabilityClass.PROCESS))
    acts = []
    for text, seq, horizon in zip(texts, sequences, horizons):
        acts.append(add(reg, T.Kind.ACTION, T.ActionPayload(
            text=text, capability_class=T.CapabilityClass.PROCESS, horizon=horizon,
            initiative_id=ini.id, sequence=seq)))
    return reg, ws, ini, acts


def edge(reg, from_id, to_id, kind="requires"):
    return add(reg, T.Kind.DEPENDENCY, T.DependencyPayload(from_id=from_id, to_id=to_id, kind=kind))


def test_roadmap_refuses_a_cyclic_plan(registry):
    """RD1: two steps waiting on each other is not a plan. The finding names
    the law and nothing at all is written - a partial sequence would print an
    order the dependencies contradict (design 1.2, fail closed)."""
    reg, _, _, acts = plan(registry)
    edge(reg, acts[0].id, acts[1].id)
    edge(reg, acts[1].id, acts[0].id)
    result = run(reg, "roadmap")
    assert "M.roadmap.dependency_cycle" in laws(result)
    assert result.deltas == ()


def test_an_acyclic_plan_is_sequenced_and_gets_its_milestone(registry):
    """Negative control for RD1/RD4: the same shape of plan without the loop
    produces a milestone per workstream that has work in it, with the widest
    horizon its own actions carry, and no cycle finding."""
    reg, ws, _, acts = plan(registry)
    edge(reg, acts[1].id, acts[0].id)
    result = run(reg, "roadmap")
    assert "M.roadmap.dependency_cycle" not in laws(result)
    (milestone,) = written(result, T.Kind.MILESTONE)
    assert milestone.payload.horizon is T.Horizon.MONTHS and milestone.payload.gate is True
    assert ws.id in milestone.provenance.derived_from
    # RD3: the milestone owns a horizon, and no date at all.
    assert milestone.payload.deadline_id is None
    assert RM.date_tokens(milestone.payload.text) == ()


def test_the_milestone_count_follows_the_plan_not_a_constant(registry):
    """Design 20: nothing here fixes how many milestones an engagement gets.
    A second workstream with work in it produces a second milestone; a
    workstream with no actions produces none."""
    reg, _, _, acts = plan(registry)
    ws2 = add(reg, T.Kind.WORKSTREAM, T.WorkstreamPayload(name="second lane", purpose="p"))
    ini2 = add(reg, T.Kind.INITIATIVE, T.InitiativePayload(
        name="second wave", workstream_id=ws2.id, capability_class=T.CapabilityClass.PROCESS))
    add(reg, T.Kind.WORKSTREAM, T.WorkstreamPayload(name="empty lane", purpose="p"))
    add(reg, T.Kind.ACTION, T.ActionPayload(text="run the pilot",
                                            capability_class=T.CapabilityClass.PROCESS,
                                            initiative_id=ini2.id))
    result = run(reg, "roadmap")
    assert len(written(result, T.Kind.MILESTONE)) == 2


def test_initiative_ordering_is_derived_from_the_actions_that_depend(registry):
    """RD1 on the coarser graph: an action depending on an action in another
    initiative is a dependency between the initiatives, derived from ids the
    registry already holds and never proposed."""
    reg, ws, ini, acts = plan(registry)
    ini2 = add(reg, T.Kind.INITIATIVE, T.InitiativePayload(
        name="second wave", workstream_id=ws.id, capability_class=T.CapabilityClass.PROCESS))
    other = add(reg, T.Kind.ACTION, T.ActionPayload(
        text="cut over", capability_class=T.CapabilityClass.PROCESS, initiative_id=ini2.id))
    edge(reg, acts[0].id, other.id)
    result = run(reg, "roadmap")
    deps = written(result, T.Kind.DEPENDENCY)
    assert [(d.payload.from_id, d.payload.to_id) for d in deps] == [(ini.id, ini2.id)]
    (superseded,) = [d for d in result.deltas if isinstance(d, T.Supersede)]
    assert superseded.entity.payload.depends_on == (ini2.id,)


def test_validator_catches_a_cycle_in_a_doctored_result(registry):
    """RD1 re-checked on the result: the law holds on what is written, not on
    the courtesy of the producer."""
    reg, _, _, acts = plan(registry)
    edge(reg, acts[0].id, acts[1].id)
    from app.engine.methods.contract import MethodResult, new_entity
    ctx = ctx_for(reg, method_id="roadmap")
    bad = new_entity(ctx, T.Kind.DEPENDENCY,
                     T.DependencyPayload(from_id=acts[1].id, to_id=acts[0].id),
                     derived_from=(acts[0].id, acts[1].id),
                     relation=T.RelationToCentralDecision.DEPENDS_ON,
                     confidence=T.Confidence(None), decision_id="DEC-1", weight=0.3)
    findings = validate("roadmap", reg, MethodResult(deltas=(T.Add(bad),)))
    assert any(f.law == "M.roadmap.dependency_cycle" for f in findings)


# ---------------------------------------------------------------------------
# roadmap RD2: nothing is scheduled before what it waits on
# ---------------------------------------------------------------------------

def test_a_forward_dependency_is_a_finding(registry):
    """RD2: a registered sequence that contradicts a registered dependency is
    two statements disagreeing. The disagreement is the finding; it is never
    quietly re-sorted away."""
    reg, _, _, acts = plan(registry, sequences=(1, 2))
    edge(reg, acts[0].id, acts[1].id)         # the first step waits on the second
    result = run(reg, "roadmap")
    forward = [f for f in result.findings if f.law == "M.roadmap.forward_dependency"]
    assert forward and forward[0].entity_ids == (acts[0].id, acts[1].id)


def test_a_sequence_that_respects_its_dependencies_is_not_a_finding(registry):
    """Negative control for RD2."""
    reg, _, _, acts = plan(registry, sequences=(2, 1))
    edge(reg, acts[0].id, acts[1].id)
    assert "M.roadmap.forward_dependency" not in laws(run(reg, "roadmap"))


# ---------------------------------------------------------------------------
# roadmap RD3: horizons, not dates
# ---------------------------------------------------------------------------

def test_an_action_dated_by_nobody_is_a_finding(registry):
    """RD3: a DEADLINE is the client's and a Horizon is the consultant's, so a
    calendar date printed on a plan step that no DEADLINE owns is the engine
    promising a date on the client's behalf."""
    reg, _, _, _ = plan(registry, texts=("go live on 2026-06-30", "switch over"))
    result = run(reg, "roadmap")
    dated = [f for f in result.findings if f.law == "M.roadmap.date_not_owned_by_deadline"]
    assert dated and "2026-06-30" in dated[0].issue


def test_a_date_a_deadline_owns_is_lawful(registry):
    """Negative control for RD3: the same text, with the DEADLINE that carries
    the date registered, is not a finding."""
    reg, _, _, _ = plan(registry, texts=("go live on 2026-06-30", "switch over"))
    add(reg, T.Kind.DEADLINE, T.DeadlinePayload(text="contracted go-live", date="2026-06-30",
                                                origin=T.DeadlineOrigin.CONTRACT))
    assert "M.roadmap.date_not_owned_by_deadline" not in laws(run(reg, "roadmap"))


def test_a_dated_step_in_a_doctored_result_is_a_finding(registry):
    """RD3 re-checked on the result: removing this check is the named mutation
    "allow date strings on actions"."""
    reg, _, _, _ = plan(registry)
    from app.engine.methods.contract import MethodResult, new_entity
    ctx = ctx_for(reg, method_id="roadmap")
    bad = new_entity(ctx, T.Kind.ACTION,
                     T.ActionPayload(text="ship it by 2027-01-01",
                                     capability_class=T.CapabilityClass.PROCESS),
                     derived_from=("DEC-1",), relation=T.RelationToCentralDecision.INFORMS,
                     confidence=T.Confidence(None), decision_id="DEC-1", weight=0.3)
    findings = validate("roadmap", reg, MethodResult(deltas=(T.Add(bad),)))
    assert any(f.law == "M.roadmap.date_not_owned_by_deadline" for f in findings)


def test_date_tokens_reads_calendar_shapes_only():
    """The date scan is calendar vocabulary, not engagement vocabulary: no word
    in it comes from any client, case or engagement type."""
    assert RM.date_tokens("go live 2026-06-30 then Q3 2027 then 01/02/2028") == (
        "2026-06-30", "Q3 2027", "01/02/2028")
    assert RM.date_tokens("in the third week, once volumes settle") == ()


# ---------------------------------------------------------------------------
# systems_data_map SD1: the map is a graph, not a loop
# ---------------------------------------------------------------------------

def systems_registry(registry):
    reg = with_decision(registry)
    add(reg, T.Kind.FACT, T.FactPayload(statement="orders arrive by email and are keyed in",
                                        basis=T.FactBasis.DOCUMENT_EXTRACTED))
    return reg


def test_systems_map_refuses_the_edge_that_closes_a_cycle(registry):
    """SD1: the first edge of a loop is lawful; the one that closes it is
    refused before it is written and named, so the model's contradiction is
    shown rather than silently dropped."""
    reg = systems_registry(registry)
    provider = scripted(
        "systems_data_map",
        out("capability", "order intake system", ref="S1", capability_class="software_system", gap="present"),
        out("capability", "customer data store", ref="S2", capability_class="data_and_integration", gap="present"),
        out("dependency", "intake needs the store", **{"from": "S1", "to": "S2"}),
        out("dependency", "the store needs intake", **{"from": "S2", "to": "S1"}),
    )
    result = run(reg, "systems_data_map", provider)
    assert len(written(result, T.Kind.CAPABILITY)) == 2
    assert len(written(result, T.Kind.DEPENDENCY)) == 1
    assert "M.systems_data_map.dependency_cycle" in laws(result)


def test_an_acyclic_systems_map_keeps_every_edge(registry):
    """Negative control for SD1."""
    reg = systems_registry(registry)
    provider = scripted(
        "systems_data_map",
        out("capability", "order intake system", ref="S1", capability_class="software_system"),
        out("capability", "customer data store", ref="S2", capability_class="data_and_integration"),
        out("capability", "billing ledger", ref="S3", capability_class="software_system"),
        out("dependency", "intake needs the store", **{"from": "S1", "to": "S2"}),
        out("dependency", "the ledger needs the store", **{"from": "S3", "to": "S2"}),
    )
    result = run(reg, "systems_data_map", provider)
    assert len(written(result, T.Kind.DEPENDENCY)) == 2
    assert "M.systems_data_map.dependency_cycle" not in laws(result)


def test_an_edge_endpoint_that_names_nothing_is_refused(registry):
    """SD3: an endpoint that is neither a cited input nor a system written in
    this run is a name, not a system."""
    reg = systems_registry(registry)
    provider = scripted(
        "systems_data_map",
        out("capability", "order intake system", ref="S1", capability_class="software_system"),
        out("dependency", "intake needs the mainframe", **{"from": "S1", "to": "the mainframe"}),
    )
    result = run(reg, "systems_data_map", provider)
    assert written(result, T.Kind.DEPENDENCY) == []
    assert "M.systems_data_map.unknown_endpoint" in laws(result)


def test_a_system_is_filed_under_the_declared_subject_not_the_models_word(registry):
    """SD2: the method was selected for a shape, and the shape says which lane
    its outputs belong to. A class outside the two it covers falls back rather
    than widening the remit."""
    reg = systems_registry(registry)
    provider = scripted(
        "systems_data_map",
        out("capability", "order intake system", ref="S1", capability_class="financial"),
    )
    (cap,) = written(run(reg, "systems_data_map", provider), T.Kind.CAPABILITY)
    assert cap.payload.capability_class in SDM._DECLARED


# ---------------------------------------------------------------------------
# every ACTION carries a capability_class (MF1.3)
# ---------------------------------------------------------------------------

def people_registry(registry):
    reg = with_decision(registry)
    add(reg, T.Kind.CAPABILITY, T.CapabilityPayload(
        text="nobody owns intake end to end", capability_class=T.CapabilityClass.PEOPLE_AND_ORGANISATION,
        gap=T.GapState.MISSING))
    add(reg, T.Kind.STAKEHOLDER, T.StakeholderPayload(name="operations lead", role="runs intake"))
    add(reg, T.Kind.OWNER, T.OwnerPayload(name="Head of Operations", role="operations"))
    return reg


def test_org_design_actions_carry_the_people_class(registry):
    """MF1.3: the work-product plan reads capability_class, never prose. Letting
    a model relabel a people action would let wording decide which deliverables
    an engagement gets."""
    reg = people_registry(registry)
    provider = scripted(
        "org_design",
        out("action", "appoint an intake owner", cites=("CAP-1",),
            horizon="weeks", capability_class="financial"),
    )
    (action,) = written(run(reg, "org_design", provider), T.Kind.ACTION)
    assert action.payload.capability_class is T.CapabilityClass.PEOPLE_AND_ORGANISATION


def test_change_impact_actions_carry_the_people_class(registry):
    """MF1.3 again: answering a people impact is people work."""
    reg = with_decision(registry)
    add(reg, T.Kind.STAKEHOLDER, T.StakeholderPayload(name="intake team", role="keys orders"))
    add(reg, T.Kind.STAKEHOLDER, T.StakeholderPayload(name="account managers", role="sells"))
    add(reg, T.Kind.ACTION, T.ActionPayload(text="move intake to the new system",
                                            capability_class=T.CapabilityClass.PROCESS))
    provider = scripted(
        "change_impact",
        out("risk", "the intake team loses its familiar route", cites=("ACT-1",),
            who_feels_it="STK-1", likelihood="high", impact="medium"),
        out("action", "run intake training before cut over", cites=("ACT-1",),
            horizon="weeks", capability_class="software_system"),
    )
    result = run(reg, "change_impact", provider)
    (action,) = written(result, T.Kind.ACTION)
    assert action.payload.capability_class is T.CapabilityClass.PEOPLE_AND_ORGANISATION
    (risk,) = written(result, T.Kind.RISK)
    assert risk.payload.who_feels_it == "intake team"


def test_operating_model_takes_the_action_class_from_the_cited_capability(registry):
    """OM1: the class is the cited capability's, so scrambling every text field
    leaves it unchanged."""
    reg = with_decision(registry)
    add(reg, T.Kind.CAPABILITY, T.CapabilityPayload(text="intake runs on memory",
                                                    capability_class=T.CapabilityClass.PROCESS))
    add(reg, T.Kind.CAPABILITY, T.CapabilityPayload(text="nobody signs off exceptions",
                                                    capability_class=T.CapabilityClass.GOVERNANCE_AND_CONTROL))
    provider = scripted(
        "operating_model",
        out("workstream", "run intake as one lane", cites=("CAP-1", "CAP-2"), ref="W1", name="intake"),
        out("action", "write down the intake steps", cites=("CAP-1",), horizon="weeks",
            capability_class="financial"),
    )
    result = run(reg, "operating_model", provider)
    (action,) = written(result, T.Kind.ACTION)
    assert action.payload.capability_class is T.CapabilityClass.PROCESS
    (lane,) = written(result, T.Kind.WORKSTREAM)
    assert set(lane.payload.capability_classes) == {T.CapabilityClass.PROCESS,
                                                    T.CapabilityClass.GOVERNANCE_AND_CONTROL}


def test_an_org_design_that_invents_a_headcount_is_refused(registry):
    """The r30 organisation rule generalised: a figure in an output that
    appears in no cited input is refused, because an invented number on an org
    chart is a claim the engagement never established."""
    reg = people_registry(registry)
    provider = scripted(
        "org_design",
        out("owner", "intake supervisor", cites=("CAP-1",), name="intake supervisor",
            role="runs a team of 12"),
    )
    result = run(reg, "org_design", provider)
    assert written(result, T.Kind.OWNER) == []
    assert "M.org_design.invented_figure" in laws(result)


# ---------------------------------------------------------------------------
# raci_governance GV1: exactly one accountable per action
# ---------------------------------------------------------------------------

def owned_plan(registry):
    reg = with_decision(registry)
    owner = add(reg, T.Kind.OWNER, T.OwnerPayload(name="Head of Operations", role="operations"))
    action = add(reg, T.Kind.ACTION, T.ActionPayload(
        text="stand up intake", capability_class=T.CapabilityClass.PROCESS, owner_id=owner.id))
    return reg, owner, action


def test_one_accountable_per_action_is_read_off_the_registered_plan(registry):
    """Negative control for GV1: the plan says who owns the step, so the table
    says so too - and it says it once."""
    reg, owner, action = owned_plan(registry)
    result = run(reg, "raci_governance")
    (gov,) = written(result, T.Kind.GOVERNANCE)
    assert [r.action_id for r in gov.payload.raci] == [action.id]
    assert gov.payload.raci[0].accountable == owner.payload.name
    assert result.findings == ()


def test_an_action_with_two_accountables_is_a_finding(registry):
    """GV1: two accountables is nobody accountable. The method reports and
    writes nothing - choosing between two candidate owners is the decision
    owner's call, not the engine's."""
    reg, owner, action = owned_plan(registry)
    add(reg, T.Kind.GOVERNANCE, T.GovernancePayload(
        text="existing table", raci=(T.RaciRow(action_id=action.id, responsible="Someone Else",
                                               accountable="Someone Else"),)))
    result = run(reg, "raci_governance")
    assert "M.raci_governance.multiple_accountable" in laws(result)
    assert written(result, T.Kind.GOVERNANCE) == []


def test_an_action_with_no_accountable_is_a_finding(registry):
    """GV1, the other half: zero accountables is the same failure written
    differently. Removing this check is the named mutation "allow zero
    accountables"."""
    reg, _, action = owned_plan(registry)
    from app.engine.methods.contract import MethodResult, new_entity
    ctx = ctx_for(reg, method_id="raci_governance")
    bad = new_entity(ctx, T.Kind.GOVERNANCE,
                     T.GovernancePayload(text="table",
                                         raci=(T.RaciRow(action_id=action.id, responsible="Head of Operations",
                                                         accountable=""),)),
                     derived_from=(action.id,), relation=T.RelationToCentralDecision.INFORMS,
                     confidence=T.Confidence(None), decision_id="DEC-1", weight=0.3)
    findings = validate("raci_governance", reg, MethodResult(deltas=(T.Add(bad),)))
    assert any(f.law == "M.raci_governance.no_accountable" for f in findings)


def test_zero_and_two_accountables_are_two_named_laws():
    """GV1 at the helper both the run and the validator go through: an empty
    accountable and a contested one are distinct failures with distinct names,
    so a report says which one happened."""
    rows = (T.RaciRow("ACT-1", "a", ""), T.RaciRow("ACT-2", "a", "A"), T.RaciRow("ACT-2", "b", "B"))
    found = {f.law for f in RACI.accountable_findings(rows, "governance")}
    assert found == {"M.raci_governance.no_accountable", "M.raci_governance.multiple_accountable"}
    assert RACI.accountable_findings((T.RaciRow("ACT-3", "a", "A"),), "governance") == []


def test_an_action_nobody_owns_becomes_a_question_not_a_default_owner(registry):
    """GV3: assigning accountability on the client's behalf is the one thing a
    governance design must never do."""
    reg = with_decision(registry)
    add(reg, T.Kind.OWNER, T.OwnerPayload(name="Head of Operations", role="operations"))
    orphan = add(reg, T.Kind.ACTION, T.ActionPayload(text="agree the exception policy",
                                                     capability_class=T.CapabilityClass.PROCESS))
    result = run(reg, "raci_governance")
    assert written(result, T.Kind.GOVERNANCE) == []
    assert result.questions and orphan.id in result.questions[0].text
    assert result.questions[0].asks_for == (T.AsksFor(T.Kind.OWNER),)


def test_a_raci_row_naming_an_unregistered_party_is_a_finding(registry):
    """GV2: accountability to a name nobody recognises is accountability to
    nobody."""
    reg, _, action = owned_plan(registry)
    from app.engine.methods.contract import MethodResult, new_entity
    ctx = ctx_for(reg, method_id="raci_governance")
    bad = new_entity(ctx, T.Kind.GOVERNANCE,
                     T.GovernancePayload(text="table",
                                         raci=(T.RaciRow(action_id=action.id, responsible="A Ghost",
                                                         accountable="A Ghost"),)),
                     derived_from=(action.id,), relation=T.RelationToCentralDecision.INFORMS,
                     confidence=T.Confidence(None), decision_id="DEC-1", weight=0.3)
    findings = validate("raci_governance", reg, MethodResult(deltas=(T.Add(bad),)))
    assert any(f.law == "M.raci_governance.unregistered_party" for f in findings)


# ---------------------------------------------------------------------------
# kpi_design KP1: a baseline is registered, or it is measured first
# ---------------------------------------------------------------------------

def kpi_registry(registry, *, with_client_fact=False, with_record=False):
    reg = with_decision(registry)
    turn = add(reg, T.Kind.EVIDENCE_SOURCE, T.EvidenceSourcePayload(
        name="turn 1", source_kind=T.SourceKind.CONVERSATION_TURN,
        text="we push out about forty orders a day"))
    doc = add(reg, T.Kind.EVIDENCE_SOURCE, T.EvidenceSourcePayload(
        name="ops report", source_kind=T.SourceKind.DOCUMENT, record_class=T.RecordClass.SYSTEM_OF_RECORD,
        record_class_confirmed_by_client=True, text="daily despatch averaged fifty-five orders"))
    measure = add(reg, T.Kind.MEASURE, T.MeasurePayload(
        name="orders despatched per day", unit_family=T.UnitFamily.CAPACITY, confirmed_by_client=True))
    add(reg, T.Kind.OBJECTIVE, T.ObjectivePayload(
        text="despatch more each day", measure_id=measure.id,
        target=T.Quantity(Decimal("80"), "orders/day", T.UnitFamily.CAPACITY)))
    if with_client_fact:
        add(reg, T.Kind.FACT, T.FactPayload(
            statement="we push out about forty orders a day", basis=T.FactBasis.CLIENT_STATED,
            measure_id=measure.id, quantity=T.Quantity(Decimal("40"), "orders/day", T.UnitFamily.CAPACITY)),
            derived_from=(turn.id,))
    if with_record:
        add(reg, T.Kind.FACT, T.FactPayload(
            statement="daily despatch averaged fifty-five orders", basis=T.FactBasis.DOCUMENT_VERIFIED,
            measure_id=measure.id, record_class=T.RecordClass.SYSTEM_OF_RECORD,
            quantity=T.Quantity(Decimal("55"), "orders/day", T.UnitFamily.CAPACITY)),
            derived_from=(doc.id,), locator="daily despatch averaged fifty-five orders")
    return reg, measure


def test_a_baseline_is_copied_from_the_client_fact_that_carries_it(registry):
    """KP1, negative control: the figure on the criterion is the figure on the
    registered fact, copied by id, and the source says which of the three it
    came from."""
    reg, measure = kpi_registry(registry, with_client_fact=True)
    (criterion,) = written(run(reg, "kpi_design"), T.Kind.SUCCESS_CRITERION)
    assert criterion.payload.baseline_source == KPI.CLIENT_FACT
    assert criterion.payload.baseline.value == Decimal("40")
    assert criterion.payload.measure_id == measure.id
    # KP2: the target is the client's own, off the objective, never derived.
    assert criterion.payload.target.value == Decimal("80")


def test_a_record_outranks_the_client_recollection_for_the_baseline(registry):
    """KP1 with CURRENT_STATE_PRECEDENCE: a verified system of record carries
    the current state ahead of what the client remembered."""
    reg, _ = kpi_registry(registry, with_client_fact=True, with_record=True)
    (criterion,) = written(run(reg, "kpi_design"), T.Kind.SUCCESS_CRITERION)
    assert criterion.payload.baseline_source == KPI.RECORD
    assert criterion.payload.baseline.value == Decimal("55")


def test_with_nothing_registered_the_baseline_is_measured_first(registry):
    """KP1: absence is a typed answer, not a placeholder for a number. The
    criterion says measure_first and a question goes out for the figure."""
    reg, _ = kpi_registry(registry)
    result = run(reg, "kpi_design")
    (criterion,) = written(result, T.Kind.SUCCESS_CRITERION)
    assert criterion.payload.baseline is None
    assert criterion.payload.baseline_source == KPI.MEASURE_FIRST
    assert result.questions


def test_an_invented_kpi_baseline_is_refused(registry):
    """KP1 re-checked on the result: a figure matching no registered fact the
    criterion cites is refused. Removing this check is the named mutation
    "allow an invented baseline"."""
    reg, measure = kpi_registry(registry, with_client_fact=True)
    from app.engine.methods.contract import MethodResult, new_entity
    ctx = ctx_for(reg, method_id="kpi_design")
    bad = new_entity(ctx, T.Kind.SUCCESS_CRITERION,
                     T.SuccessCriterionPayload(
                         text="orders per day", measure_id=measure.id,
                         baseline=T.Quantity(Decimal("38"), "orders/day", T.UnitFamily.CAPACITY),
                         baseline_source=KPI.CLIENT_FACT),
                     derived_from=("OBJ-1", measure.id, "FCT-1"),
                     relation=T.RelationToCentralDecision.DEFINES,
                     confidence=T.Confidence(None), decision_id="DEC-1", weight=0.3)
    findings = validate("kpi_design", reg, MethodResult(deltas=(T.Add(bad),)))
    assert any(f.law == "M.kpi_design.invented_baseline" for f in findings)


def test_a_baseline_claiming_a_source_it_has_not_got_is_refused(registry):
    """KP1: the three sources are the whole vocabulary, and each of them makes
    a claim the criterion has to be able to keep."""
    reg, measure = kpi_registry(registry)
    from app.engine.methods.contract import MethodResult, new_entity
    ctx = ctx_for(reg, method_id="kpi_design")
    cases = (
        T.SuccessCriterionPayload(text="x", measure_id=measure.id, baseline=None,
                                  baseline_source=KPI.RECORD),
        T.SuccessCriterionPayload(text="x", measure_id=measure.id, baseline=None,
                                  baseline_source="unknown"),
        T.SuccessCriterionPayload(
            text="x", measure_id=measure.id,
            baseline=T.Quantity(Decimal("1"), "orders/day", T.UnitFamily.CAPACITY),
            baseline_source=KPI.MEASURE_FIRST),
    )
    for payload in cases:
        bad = new_entity(ctx, T.Kind.SUCCESS_CRITERION, payload, derived_from=("OBJ-1",),
                         relation=T.RelationToCentralDecision.DEFINES,
                         confidence=T.Confidence(None), decision_id="DEC-1", weight=0.3)
        findings = validate("kpi_design", reg, MethodResult(deltas=(T.Add(bad),)))
        assert any(f.law == "M.kpi_design.invented_baseline" for f in findings), payload.baseline_source


def test_an_objective_with_no_registered_measure_becomes_a_question(registry):
    """KP3: reconciliation joins on measure_id and on nothing else, so naming a
    measure here would invent the very key it depends on."""
    reg = with_decision(registry)
    add(reg, T.Kind.OBJECTIVE, T.ObjectivePayload(text="be quicker"))
    add(reg, T.Kind.MEASURE, T.MeasurePayload(name="cycle time", unit_family=T.UnitFamily.TIME))
    result = run(reg, "kpi_design")
    assert written(result, T.Kind.SUCCESS_CRITERION) == []
    assert result.questions and result.questions[0].asks_for == (T.AsksFor(T.Kind.MEASURE),)


# ---------------------------------------------------------------------------
# prioritization PR1/PR2: the client's weights rank, and nothing else does
# ---------------------------------------------------------------------------

def priority_registry(registry, *, weight_set_by):
    reg = with_decision(registry)
    a1 = add(reg, T.Kind.ACTION, T.ActionPayload(text="fix intake",
                                                 capability_class=T.CapabilityClass.PROCESS))
    a2 = add(reg, T.Kind.ACTION, T.ActionPayload(text="retire the spreadsheet",
                                                 capability_class=T.CapabilityClass.SOFTWARE_SYSTEM))
    cri = add(reg, T.Kind.EVALUATION_CRITERION, T.EvaluationCriterionPayload(
        text="effect on despatch", decision_id="DEC-1", weight=0.8, weight_set_by=weight_set_by))
    add(reg, T.Kind.TRADE_OFF, T.TradeOffPayload(
        decision_id="DEC-1", option_ids=(a1.id, a2.id),
        scores=(T.Score(a1.id, cri.id, Decimal("2"), evidence=("EVI-1",)),
                T.Score(a2.id, cri.id, Decimal("5"), evidence=("EVI-1",)))))
    return reg, a1, a2, cri


def test_client_weights_rank_the_work(registry):
    """PR1, negative control: the relative importance of two objectives is a
    client preference, and when the client has set it the order follows."""
    reg, a1, a2, cri = priority_registry(registry, weight_set_by=T.Authority.CLIENT)
    result = run(reg, "prioritization")
    sequenced = {d.entity.id: d.entity.payload.sequence for d in result.deltas
                 if isinstance(d, T.Supersede)}
    assert sequenced == {a2.id: 1, a1.id: 2}
    (trade_off,) = written(result, T.Kind.TRADE_OFF)
    assert trade_off.payload.option_ids == (a2.id, a1.id)
    assert all(s.evidence for s in trade_off.payload.scores)


def test_a_consultant_weight_lists_but_does_not_rank(registry):
    """PR1: the authority table gives the client every objective and success
    criterion, so a consultant-set weight lists the dimension and moves
    nothing. The gap goes to the one authority that can close it."""
    reg, _, _, _ = priority_registry(registry, weight_set_by=T.Authority.CONSULTANT)
    result = run(reg, "prioritization")
    assert [d for d in result.deltas if isinstance(d, T.Supersede)] == []
    assert result.questions and result.questions[0].material is True
    assert result.questions[0].asks_for[0].kind is T.Kind.EVALUATION_CRITERION


def test_an_unscored_step_is_left_unsequenced_and_asked_about(registry):
    """PR2: a rank with no scoring behind it would be a preference presented as
    arithmetic, so the step stays unsequenced and the hole is named."""
    reg, a1, a2, _ = priority_registry(registry, weight_set_by=T.Authority.CLIENT)
    a3 = add(reg, T.Kind.ACTION, T.ActionPayload(text="tidy the shared drive",
                                                 capability_class=T.CapabilityClass.DATA_AND_INTEGRATION))
    result = run(reg, "prioritization")
    sequenced = {d.entity.id for d in result.deltas if isinstance(d, T.Supersede)}
    assert a3.id not in sequenced
    assert any(a3.id in q.text for q in result.questions)


def test_a_sequence_written_without_a_client_weight_is_a_finding(registry):
    """PR1 re-checked: a priority order that cites no client-weighted criterion
    reads the authority table backwards."""
    reg, a1, _, _ = priority_registry(registry, weight_set_by=T.Authority.CONSULTANT)
    from app.engine.methods.contract import MethodResult, new_entity
    ctx = ctx_for(reg, method_id="prioritization")
    bad = new_entity(ctx, T.Kind.ACTION,
                     T.ActionPayload(text="fix intake", capability_class=T.CapabilityClass.PROCESS,
                                     sequence=1),
                     derived_from=("DEC-1",), relation=T.RelationToCentralDecision.INFORMS,
                     confidence=T.Confidence(None), decision_id="DEC-1", weight=0.3)
    findings = validate("prioritization", reg, MethodResult(deltas=(T.Supersede(a1.id, bad),)))
    assert any(f.law == "M.prioritization.sequence_without_client_weight" for f in findings)


def test_weighted_totals_are_exact_decimal_and_skip_the_unscored():
    """PR2/PR3 as arithmetic: absence is absence, not zero, and the totals are
    Decimal so two runs produce one order."""
    scores = {("ACT-1", "CRI-1"): (T.Score("ACT-1", "CRI-1", Decimal("2"), ("EVI-1",)), "TRD-1")}
    totals = PRI.weighted_totals(["ACT-1", "ACT-2"], {"CRI-1": Decimal("0.5")}, scores)
    assert totals == {"ACT-1": Decimal("1.0")}
    assert isinstance(totals["ACT-1"], Decimal)


# ---------------------------------------------------------------------------
# risk_control RK1/RK2
# ---------------------------------------------------------------------------

def risk_registry(registry):
    reg = with_decision(registry)
    add(reg, T.Kind.ACTION, T.ActionPayload(text="move intake to the new system",
                                            capability_class=T.CapabilityClass.PROCESS))
    add(reg, T.Kind.STAKEHOLDER, T.StakeholderPayload(name="intake team", role="keys orders"))
    return reg


def test_a_risk_nobody_bears_is_refused(registry):
    """RK1: a risk with no named bearer cannot be owned, mitigated or accepted."""
    reg = risk_registry(registry)
    provider = scripted(
        "risk_control",
        out("risk", "reputational damage", cites=("ACT-1",), who_feels_it="everyone"),
        out("risk", "the intake team loses its route in", cites=("ACT-1",), ref="R1",
            who_feels_it="STK-1", likelihood="high"),
    )
    result = run(reg, "risk_control", provider)
    (risk,) = written(result, T.Kind.RISK)
    assert risk.payload.who_feels_it == "intake team" and risk.payload.likelihood == "high"
    assert "M.risk_control.risk_without_bearer" in laws(result)


def test_a_control_that_answers_no_risk_is_refused(registry):
    """RK2: a control floating free of a risk is a control for nothing."""
    reg = risk_registry(registry)
    provider = scripted(
        "risk_control",
        out("risk", "the intake team loses its route in", cites=("ACT-1",), ref="R1",
            who_feels_it="STK-1"),
        out("control", "a weekly review", cites=("ACT-1",), risks="R1"),
        out("control", "general vigilance", cites=("ACT-1",)),
    )
    result = run(reg, "risk_control", provider)
    controls = written(result, T.Kind.CONTROL)
    assert len(controls) == 1 and controls[0].payload.risk_ids
    assert "M.risk_control.control_without_risk" in laws(result)


def test_an_unknown_likelihood_stays_unknown(registry):
    """Spec section 7: unknown information remains unknown. A model's guess at
    a probability is not evidence of one."""
    reg = risk_registry(registry)
    provider = scripted(
        "risk_control",
        out("risk", "the intake team loses its route in", cites=("ACT-1",),
            who_feels_it="STK-1", likelihood="quite likely really"),
    )
    (risk,) = written(run(reg, "risk_control", provider), T.Kind.RISK)
    assert risk.payload.likelihood == "unknown" and risk.payload.impact == "unknown"


# ---------------------------------------------------------------------------
# make_buy_partner MB1/MB2
# ---------------------------------------------------------------------------

def sourcing_registry(registry):
    reg = with_decision(registry)
    add(reg, T.Kind.CAPABILITY, T.CapabilityPayload(
        text="despatch scheduling", capability_class=T.CapabilityClass.SOFTWARE_SYSTEM,
        gap=T.GapState.MISSING))
    return reg


def test_every_sourcing_route_is_put_on_the_table_and_none_is_preferred(registry):
    """MB1/MB2: the method completes the option set for an open gap and scores
    nothing - the routes stand side by side and the reader chooses."""
    reg = sourcing_registry(registry)
    result = run(reg, "make_buy_partner")
    options = written(result, T.Kind.OPTION)
    assert len(options) == len(set(o.payload.mechanism for o in options)) == 3
    assert all(o.payload.evidence == ("CAP-1",) for o in options)
    (trade_off,) = written(result, T.Kind.TRADE_OFF)
    assert set(trade_off.payload.option_ids) == {o.id for o in options}
    assert trade_off.payload.scores == ()


def test_the_sourcing_method_adds_nothing_to_a_gap_already_covered(registry):
    """MB1: coverage is read from ids, so re-running the method over its own
    output adds nothing."""
    reg = sourcing_registry(registry)
    reg.apply_all(run(reg, "make_buy_partner").deltas)
    assert run(reg, "make_buy_partner").deltas == ()


def covered_gap(registry):
    """A capability two registered options already cover: the method writes no
    route for it, and the trade-off it does write is over those options."""
    reg = sourcing_registry(registry)
    build = add(reg, T.Kind.OPTION, T.OptionPayload(
        text="build it here", decision_id="DEC-1", mechanism="make", evidence=("CAP-1",)))
    buy = add(reg, T.Kind.OPTION, T.OptionPayload(
        text="license one", decision_id="DEC-1", mechanism="buy", evidence=("CAP-1",)))
    return reg, build, buy


def test_a_trade_off_renders_its_sides_from_registered_rows(registry):
    """MB3: what a route gives up and gains is rendered from the COST and
    BENEFIT rows that name it; nothing is phrased by the method, and a side
    with nothing registered reads empty rather than reassuring."""
    reg, build, buy = covered_gap(registry)
    add(reg, T.Kind.COST, T.CostPayload(text="a year of build time", for_ids=(build.id,)))
    result = run(reg, "make_buy_partner")
    assert written(result, T.Kind.OPTION) == []          # MB1: the gap is covered
    (trade_off,) = written(result, T.Kind.TRADE_OFF)
    assert set(trade_off.payload.option_ids) == {build.id, buy.id}
    assert trade_off.payload.gives_up == "a year of build time"
    assert trade_off.payload.gains == ""


def test_an_uncited_score_never_reaches_a_written_trade_off(registry):
    """MB2: a comparison may not inherit a number nothing stands behind. The
    cited scoring is carried forward; the bare one is dropped and named."""
    reg, build, buy = covered_gap(registry)
    add(reg, T.Kind.TRADE_OFF, T.TradeOffPayload(
        decision_id="DEC-1", option_ids=(build.id,),
        scores=(T.Score(build.id, "CRI-9", Decimal("4")),)))
    add(reg, T.Kind.TRADE_OFF, T.TradeOffPayload(
        decision_id="DEC-1", option_ids=(buy.id,),
        scores=(T.Score(buy.id, "CRI-9", Decimal("2"), evidence=("EVI-1",)),)))
    result = run(reg, "make_buy_partner")
    (trade_off,) = written(result, T.Kind.TRADE_OFF)
    assert [s.option_id for s in trade_off.payload.scores] == [buy.id]
    assert "M.make_buy_partner.uncited_score" in laws(result)


# ---------------------------------------------------------------------------
# universality: no method in the family branches on prose or on a client name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method_id", DESIGN_METHODS)
def test_selection_is_blind_to_wording(method_id, registry):
    """Design 1: scrambling every TEXT_FIELDS value yields identical
    selections. The method's applicability is enums and booleans, so a
    capability called anything at all selects the same way."""
    spec = METHODS.get(method_id).spec
    reg = with_decision(registry)
    plain = add(reg, T.Kind.ISSUE, T.IssuePayload(
        text="how do we run this?", interrogative=spec.applicability[0].interrogative,
        target_kind=spec.applicability[0].target_kind,
        quantified=spec.applicability[0].quantified, comparative=spec.applicability[0].comparative,
        causal=spec.applicability[0].causal, temporal=spec.applicability[0].temporal,
        capability_class=spec.applicability[0].capability_class))
    scrambled = add(reg, T.Kind.ISSUE, T.IssuePayload(
        text="zzz qqq wwww", interrogative=spec.applicability[0].interrogative,
        target_kind=spec.applicability[0].target_kind,
        quantified=spec.applicability[0].quantified, comparative=spec.applicability[0].comparative,
        causal=spec.applicability[0].causal, temporal=spec.applicability[0].temporal,
        capability_class=spec.applicability[0].capability_class))
    assert QuestionShape.of(plain) == QuestionShape.of(scrambled)
    a = {s.method_id for s in select_methods([plain], reg, max_per_issue=6)}
    b = {s.method_id for s in select_methods([scrambled], reg, max_per_issue=6)}
    assert a == b and method_id in a
