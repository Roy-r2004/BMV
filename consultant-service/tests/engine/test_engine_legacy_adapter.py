"""The legacy r30 adapter (design 13): selection by shape, inputs composed
only from registry entities, outputs imported as typed rows, and a Request
row the engine reads and never writes.

Every law in `app/engine/legacy/` and in the adapter method has a failing
fixture, a passing one and a named mutation here.
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.engine import types as T
from app.engine.calc.arith import DecimalCalculator
from app.engine.legacy import mapping as legacy_mapping
from app.engine.legacy import r30_adapter as adapter
from app.engine.methods import builtin as _builtin  # noqa: F401  (registration by import)
from app.engine.methods.contract import METHODS, MethodContext, QuestionShape, select_methods
from app.engine.registry import EngagementRegistry
from app.pipeline import integrity as r30_integrity
from app.pipeline import pilot_gate as r30_pilot_gate

METHOD_ID = "legacy_r30_technology_blueprint"

TURN_TEXT = ("We run a same-day courier operation out of Rotterdam. "
             "We move 40 deliveries a day and roughly one in six comes back undelivered.")
CLIENT_FACT = "40 deliveries a day"


# ---------------------------------------------------------------------------
# The engagement
# ---------------------------------------------------------------------------

def _entity(kind, payload, *, entity_id, actor=T.Actor.PARTNER, derived_from=("EVI-1",),
            status=T.Status.PROPOSED, locator=None, relation=T.RelationToCentralDecision.INFORMS,
            engagement_id="E-1"):
    return T.make_entity(
        kind=kind, engagement_id=engagement_id, payload=payload,
        provenance=T.Provenance(actor=actor, actor_ref=f"{actor.value}:1",
                                derived_from=tuple(derived_from), source_locator=locator),
        confidence=T.Confidence(None), relevance=T.Relevance("DEC-1", 0.6),
        relation=relation, status=status, entity_id=entity_id)


def _qty(value, unit="deliveries", family=T.UnitFamily.COUNT):
    return T.Quantity(Decimal(str(value)), unit, family,
                      T.Dimensions(period="day", period_basis="day"))


def seed(reg: EngagementRegistry, *, workstreams: bool = True) -> EngagementRegistry:
    """One small engagement that would reach the adapter: a software-system
    issue, the client's own words, one stated number, one objective."""
    eid = reg.engagement_id

    def add(*args, **kwargs):
        kwargs.setdefault("engagement_id", eid)
        reg.apply(T.Add(_entity(*args, **kwargs)))

    add(T.Kind.EVIDENCE_SOURCE,
        T.EvidenceSourcePayload(name="turn 1", source_kind=T.SourceKind.CONVERSATION_TURN,
                                text=TURN_TEXT, received_at="2026-01-01T00:00:00+00:00"),
        entity_id="EVI-1", derived_from=(), actor=T.Actor.CLIENT)
    add(T.Kind.DECISION,
        T.DecisionPayload(statement="how we stop failed deliveries", role=T.DecisionRole.CENTRAL),
        entity_id="DEC-1", relation=T.RelationToCentralDecision.DEFINES)
    add(T.Kind.BUSINESS_CONTEXT,
        T.BusinessContextPayload(text="a same-day courier operation out of Rotterdam",
                                 aspect="what_it_does"),
        entity_id="BCX-1", actor=T.Actor.CLIENT)
    add(T.Kind.BUSINESS_CONTEXT,
        T.BusinessContextPayload(text="same-day courier and last-mile logistics", aspect="market"),
        entity_id="BCX-2")
    add(T.Kind.OBJECTIVE, T.ObjectivePayload(text="cut failed deliveries by a quarter"),
        entity_id="OBJ-1", actor=T.Actor.CLIENT)
    add(T.Kind.MEASURE, T.MeasurePayload(name="deliveries a day", unit_family=T.UnitFamily.COUNT),
        entity_id="MEA-1", actor=T.Actor.CLIENT)
    add(T.Kind.FACT,
        T.FactPayload(statement=CLIENT_FACT, basis=T.FactBasis.CLIENT_STATED, measure_id="MEA-1",
                      quantity=_qty(40), topic="deliveries"),
        entity_id="FCT-1", actor=T.Actor.CLIENT, locator=CLIENT_FACT,
        relation=T.RelationToCentralDecision.EVIDENCES)
    add(T.Kind.DECISION_OWNER,
        T.DecisionOwnerPayload(name="Marije de Wit", role="managing director"),
        entity_id="DOW-1", actor=T.Actor.CLIENT)
    add(T.Kind.ISSUE,
        T.IssuePayload(text="how the dispatch desk should run on software",
                       interrogative=T.Interrogative.HOW, target_kind=T.Kind.CAPABILITY,
                       capability_class=T.CapabilityClass.SOFTWARE_SYSTEM, decisive_for=("DEC-1",)),
        entity_id="ISS-1")
    if workstreams:
        add(T.Kind.WORKSTREAM,
            T.WorkstreamPayload(name="dispatch software",
                                capability_classes=(T.CapabilityClass.SOFTWARE_SYSTEM,)),
            entity_id="WKS-1")
        add(T.Kind.WORKSTREAM,
            T.WorkstreamPayload(name="the operation itself",
                                capability_classes=(T.CapabilityClass.SOFTWARE_SYSTEM,
                                                    T.CapabilityClass.PROCESS,
                                                    T.CapabilityClass.PEOPLE_AND_ORGANISATION)),
            entity_id="WKS-2")
    return reg


@pytest.fixture
def engagement(registry):
    return seed(registry("E-1"))


@pytest.fixture
def calc():
    return DecimalCalculator()


# ---------------------------------------------------------------------------
# The r30 package
# ---------------------------------------------------------------------------

GATE = {"id": "PG-01", "primary_metric": "Failed delivery rate", "direction": "fall",
        "target_value": 5, "target_unit": "points", "change_kind": "percentage_point",
        "duration_value": 4, "duration_unit": "week",
        "approval_status": "consultant_proposed - client approval required"}

GATE_SENTENCE = r30_pilot_gate.canonical_sentence(GATE)


def _claim(cid, ctype, value, unit, *, provenance, approval, source, text, **extra):
    c = {"id": cid, "type": ctype, "value": value, "unit": unit, "time_basis": "day",
         "population": "n/a", "scope": "engagement", "phase": "all", "provenance": provenance,
         "approval_status": approval, "source": source, "allowed_sections": ["*"], "text": text}
    c.update(extra)
    return c


def r30_registry_dict():
    """A package in the shape `app/pipeline/registry.py` builds: claims with
    r30's four provenance words, typed modules, and the pilot gate."""
    return {
        "version": 2,
        "monthly_identity": "operating_30_day_month",
        "claims": [
            _claim("CF-01", "client_fact", 40, "deliveries", provenance="client_input",
                   approval="client_stated", source="discovery: How many deliveries a day?",
                   text=CLIENT_FACT, question="How many deliveries a day?"),
            _claim("DV-01", "derived_value", 480, "deliveries", provenance="machine_computed",
                   approval="machine_verified", source="CF-01 x 12", text="480 deliveries"),
            _claim("DV-02", "derived_value", 999, "deliveries", provenance="machine_computed",
                   approval="machine_verified", source="CF-01 x 12", text="999 deliveries"),
            _claim("DV-03", "derived_value", 2080, "hours", provenance="machine_computed",
                   approval="machine_verified",
                   source="financial_model.lines[0]: 40 hours x 52 weeks = 2,080 hours",
                   text="2,080 hours"),
            _claim("SA-01", "scenario_assumption", 0.2, "ratio", provenance="consultant_proposed",
                   approval="consultant_proposed - client approval required",
                   source="financial_model.scenarios[base].assumption",
                   text="20% (base scenario assumption)"),
            _claim("MK-m1-gate", "module_kpi", 5, "points", provenance="canonical_gate",
                   approval=GATE["approval_status"], source="pilot_gate", text=GATE_SENTENCE,
                   maps_to="PG"),
            _claim("MK-m2-01", "module_kpi", 12, "minutes", provenance="consultant_proposed",
                   approval="consultant_proposed - client approval required",
                   source="spec.kpis[0]", text="Time to assign a run: 12 minutes"),
        ],
        "modules": [
            {"id": "m1", "client_facing_name": "Dispatch Pilot", "phase": "PILOT", "pilot": True,
             "automation_level": "rules", "dependencies": [], "kpi_claim_ids": ["MK-m1-gate"]},
            {"id": "m2", "client_facing_name": "Route Board", "phase": "FUTURE", "pilot": False,
             "automation_level": "rules", "dependencies": ["m1"], "kpi_claim_ids": ["MK-m2-01"]},
        ],
        "pilot_gate": GATE,
        "pilot_gate_sentence": GATE_SENTENCE,
    }


class FakeRequestRow:
    """A Request row as r30 leaves it. Not a database object: every reader the
    adapter uses (`integrity.load`, `registry.registry_for`,
    `export_pdf.release_status`) reads attributes, and a plain object proves
    the adapter reads attributes rather than issuing queries of its own."""

    def __init__(self, **overrides):
        self.id = 57
        self.status = "done"
        self.is_failed = False
        self.is_generating = False
        self.business_name = "Rotterdam Courier"
        self.business_description = "a same-day courier operation out of Rotterdam"
        self.main_problem = "how the dispatch desk should run on software"
        self.desired_outcome = "cut failed deliveries by a quarter"
        self.revenue_today = None
        self.concept_name = None
        self.mvp_blueprint = "The dispatch desk gets one queue and one owner."
        self.technical_plan = "One queue, one board, one owner."
        self.ops_numbers_json = json.dumps([{"question": "How many deliveries a day?",
                                             "answer": CLIENT_FACT}])
        self.registry_json = json.dumps(r30_registry_dict())
        self.modules_json = json.dumps([{"id": "m1", "name": "Dispatch Pilot"}])
        self.business_case_json = json.dumps({"build_order": ["m1", "m2"]})
        self.procedures_json = json.dumps({"procedures": [
            {"name": "Taking a booking", "phase": "pilot", "trigger": "a call comes in",
             "steps": [{"actor": "you", "step": "Write the drop address on the day sheet"},
                       {"actor": "you", "step": "Read the address back to the caller"}],
             "exceptions": [{"when": "the caller has no address", "then": "book a callback"}]}]})
        self.checklists_json = json.dumps({"checklists": [
            {"name": "End of shift", "when": "before the last van leaves",
             "items": ["Every run closed", "Every failed drop written down"]}], "forms": []})
        self.scoreboard_json = json.dumps([
            {"metric": "Failed deliveries", "baseline": "measure in week 1",
             "target": "fewer, week on week", "owner": "you", "review": "weekly",
             "formula": "failed drops over drops"}])
        self.risks_json = json.dumps([
            {"risk": "the desk keeps its own paper list beside the queue",
             "mitigation": "one queue, checked at handover",
             "who_feels_it": "the dispatcher"}])
        self.journey_json = json.dumps({"stages": [
            {"stage": "Booking", "customer_action": "calls the desk", "frontstage": "a voice",
             "backstage_modules": ["m1"]}]})
        self.org_json = json.dumps({"roles": [
            {"role": "Dispatcher", "type": "human", "responsibilities": ["runs the queue"],
             "decides_alone": "which van takes a run", "hands_off": "to the owner for refunds"}],
            "change_impact": []})
        self.playbook_json = None
        self.qa_report_json = json.dumps({"checks": [{"label": "numbers", "passed": True}],
                                          "findings": []})
        self.document_owner = None
        self.document_approver = None
        self.integrity_report_json = None
        self.updated_at = None
        for k, v in overrides.items():
            setattr(self, k, v)

    def freeze_integrity(self, findings=()):
        """The r30 integrity report, computed on the content this row holds -
        which is what `integrity.current_report` checks (`:1230`)."""
        content = r30_integrity.load(self)
        self.integrity_report_json = json.dumps({
            "version": r30_integrity.VERSION,
            "content_hash": r30_integrity.content_hash(content),
            "findings": list(findings),
        })
        return self


@pytest.fixture
def r30_row():
    return FakeRequestRow().freeze_integrity()


@pytest.fixture
def outputs(r30_row):
    return adapter.load_outputs(r30_row)


@pytest.fixture
def inputs(engagement):
    return adapter.compose_inputs(engagement, business_name="Rotterdam Courier",
                                  owner_email="owner@example.com",
                                  issue_id="ISS-1", workstream_id="WKS-1")


# ===========================================================================
# 1. Selection is by shape, and by nothing else
# ===========================================================================

def test_the_adapter_is_a_registered_method_like_any_other():
    assert METHOD_ID in [m.spec.id for m in METHODS.all()]


def test_the_adapter_is_selected_for_a_software_system_capability_issue(engagement):
    issue = engagement.get("ISS-1")
    chosen = [s.method_id for s in select_methods([issue], engagement, max_per_issue=8)]
    assert METHOD_ID in chosen


@pytest.mark.parametrize("shape", [
    dict(interrogative=T.Interrogative.HOW, target_kind=T.Kind.CAPABILITY,
         capability_class=T.CapabilityClass.PROCESS),
    dict(interrogative=T.Interrogative.WHAT, target_kind=T.Kind.CAPABILITY,
         capability_class=T.CapabilityClass.SOFTWARE_SYSTEM),
    dict(interrogative=T.Interrogative.HOW, target_kind=T.Kind.PROCESS_STEP,
         capability_class=T.CapabilityClass.SOFTWARE_SYSTEM),
    dict(interrogative=T.Interrogative.HOW, target_kind=T.Kind.CAPABILITY, capability_class=None),
])
def test_the_adapter_is_not_selected_for_any_other_shape(engagement, shape):
    """The negative control the whole design rests on: no engagement type
    reaches the pipeline, only a shape does."""
    issue = _entity(T.Kind.ISSUE, T.IssuePayload(text="something else", **shape), entity_id="ISS-9")
    engagement.apply(T.Add(issue))
    chosen = [s.method_id for s in select_methods([engagement.get("ISS-9")], engagement, max_per_issue=20)]
    assert METHOD_ID not in chosen


def test_selection_reads_no_text(engagement):
    """Scrambling every word of the issue leaves the selection identical: the
    adapter cannot be reached by naming a technology engagement."""
    before = [s.method_id for s in select_methods([engagement.get("ISS-1")], engagement, max_per_issue=8)]
    scrambled = T.make_entity(
        kind=T.Kind.ISSUE, engagement_id="E-1",
        payload=T.IssuePayload(text="qqq zzz technology transformation acquisition",
                               interrogative=T.Interrogative.HOW, target_kind=T.Kind.CAPABILITY,
                               capability_class=T.CapabilityClass.SOFTWARE_SYSTEM),
        provenance=T.Provenance(actor=T.Actor.PARTNER, actor_ref="partner:1", derived_from=("EVI-1",)),
        confidence=T.Confidence(None), relevance=T.Relevance("DEC-1", 0.6),
        relation=T.RelationToCentralDecision.INFORMS, status=T.Status.PROPOSED, entity_id="ISS-8")
    engagement.apply(T.Add(scrambled))
    after = [s.method_id for s in select_methods([engagement.get("ISS-8")], engagement, max_per_issue=8)]
    assert before == after


def test_the_declared_shape_is_the_designed_one():
    spec = METHODS.get(METHOD_ID).spec
    assert spec.applicability == (QuestionShape(T.Interrogative.HOW, T.Kind.CAPABILITY,
                                                capability_class=T.CapabilityClass.SOFTWARE_SYSTEM),)
    required = {i.kind for i in spec.required_inputs}
    assert required == {T.Kind.BUSINESS_CONTEXT, T.Kind.OBJECTIVE, T.Kind.FACT}


# ===========================================================================
# 2. Inputs are composed from registry entities and nothing else
# ===========================================================================

def test_inputs_are_composed_only_from_registry_entities(engagement, inputs):
    """Every text the pipeline is told is the text of an entity the inputs
    cite, and the citation list names them."""
    assert inputs.main_problem == engagement.get("ISS-1").payload.text
    assert inputs.industry == engagement.get("BCX-2").payload.text
    assert engagement.get("BCX-1").payload.text in inputs.business_description
    assert inputs.desired_outcome == engagement.get("OBJ-1").payload.text
    assert [(p.question, p.answer, p.entity_id) for p in inputs.ops_numbers] == [
        ("deliveries a day", CLIENT_FACT, "FCT-1")]
    for eid in ("BCX-1", "BCX-2", "OBJ-1", "MEA-1", "FCT-1", "ISS-1", "DOW-1", "WKS-1"):
        assert eid in inputs.source_entity_ids
    # The one mechanical statement of the law, on the finished object.
    adapter.check_composed(inputs, engagement)


def test_a_coined_input_is_refused(engagement, inputs):
    """The mutation partner for A1: a composer that filled a hole with a
    default would send the pipeline a sentence the client never said."""
    coined = adapter.R30Inputs(**{**inputs.__dict__,
                                 "main_problem": "improve operational efficiency across the business"})
    with pytest.raises(adapter.LegacyInputsCoined):
        adapter.check_composed(coined, engagement)


def test_the_client_number_reaches_the_pipeline_verbatim(inputs):
    """`registry.client_fact_claims` (`app/pipeline/registry.py:325`) reads
    the answer character for character, so the answer is the client's own
    statement and the sanitiser r30 owns is the only thing that trims it."""
    pairs = json.loads(inputs.ops_numbers_json())
    assert pairs == [{"question": "deliveries a day", "answer": CLIENT_FACT}]


def test_document_control_comes_from_the_decision_owner(inputs):
    assert inputs.document_owner == "Marije de Wit (managing director)"
    assert inputs.document_approver is None      # one owner named, so no approver is invented


def test_an_engagement_with_no_business_context_composes_nothing_it_was_not_given(registry):
    """Absence is absence: an empty description, not a filler sentence."""
    reg = registry("E-2")
    reg.apply(T.Add(_entity(T.Kind.EVIDENCE_SOURCE,
                            T.EvidenceSourcePayload(name="turn 1", source_kind=T.SourceKind.CONVERSATION_TURN,
                                                    text=TURN_TEXT),
                            entity_id="EVI-1", derived_from=(), engagement_id="E-2")))
    composed = adapter.compose_inputs(reg, business_name="x", owner_email="o@example.com")
    assert composed.business_description == ""
    assert composed.industry is None
    assert composed.ops_numbers == ()


# ===========================================================================
# 3. engagement_type is a structural predicate
# ===========================================================================

def test_engagement_type_is_capability_on_a_proper_slice(engagement):
    """WKS-1 carries software alone; the engagement as a whole also carries
    process and people. A proper subset is a capability engagement."""
    assert adapter.engagement_type_for(engagement, "WKS-1") == adapter.ENGAGEMENT_CAPABILITY


def test_engagement_type_is_full_on_the_whole_business(engagement):
    """WKS-2 carries every class the engagement knows: not a slice of it."""
    assert adapter.engagement_type_for(engagement, "WKS-2") == adapter.ENGAGEMENT_FULL


def test_engagement_type_is_full_with_one_workstream(registry):
    reg = seed(registry("E-3"), workstreams=False)
    reg.apply(T.Add(_entity(T.Kind.WORKSTREAM,
                            T.WorkstreamPayload(name="only one",
                                                capability_classes=(T.CapabilityClass.SOFTWARE_SYSTEM,)),
                            entity_id="WKS-1", engagement_id="E-3")))
    assert adapter.engagement_type_for(reg, "WKS-1") == adapter.ENGAGEMENT_FULL


def test_engagement_type_is_full_when_no_workstream_is_named(engagement):
    assert adapter.engagement_type_for(engagement, None) == adapter.ENGAGEMENT_FULL


def test_engagement_type_reaches_the_request_row(engagement):
    slice_inputs = adapter.compose_inputs(engagement, business_name="x", owner_email="o@example.com",
                                          issue_id="ISS-1", workstream_id="WKS-1")
    whole_inputs = adapter.compose_inputs(engagement, business_name="x", owner_email="o@example.com",
                                          issue_id="ISS-1", workstream_id="WKS-2")
    assert slice_inputs.request_fields()["engagement_type"] == adapter.ENGAGEMENT_CAPABILITY
    assert whole_inputs.request_fields()["engagement_type"] == adapter.ENGAGEMENT_FULL


def test_needs_ai_is_maybe_until_the_registry_says_otherwise(engagement, inputs):
    assert inputs.needs_ai == adapter.NEEDS_AI_YES        # a software workstream is in scope
    engagement.apply(T.Add(_entity(
        T.Kind.CONSTRAINT, T.ConstraintPayload(text="no automated decisions on customer data",
                                               kind="policy", hard=True),
        entity_id="CST-1", actor=T.Actor.CLIENT)))
    refused = adapter.compose_inputs(engagement, business_name="x", owner_email="o@example.com",
                                     issue_id="ISS-1", workstream_id="WKS-1")
    assert refused.needs_ai == adapter.NEEDS_AI_NO


# ===========================================================================
# 4. The request row: created by the intake's own fields, then never touched
# ===========================================================================

def test_the_request_row_is_built_from_the_intake_constructor_fields(inputs):
    """Every key `create_request` sets, and no key it does not
    (`app/routers/requests.py:199-224`)."""
    import inspect

    from app.routers.requests import create_request

    accepted = set(inspect.signature(create_request).parameters)
    fields = inputs.request_fields()
    unknown = set(fields) - accepted - {"owner_email", "ops_numbers_json"}
    assert unknown == set(), f"the adapter invents intake fields: {sorted(unknown)}"
    assert fields["business_name"] == "Rotterdam Courier"
    assert fields["email"] == fields["owner_email"] == "owner@example.com"


def test_run_technology_blueprint_creates_one_row_and_runs_the_orchestrator(monkeypatch, inputs):
    """`orchestrator.run` is monkeypatched exactly as `tests/test_discovery.py:34`
    does: the pipeline itself is never started from a test."""
    from app.database import Base, SessionLocal, engine
    from app.pipeline import orchestrator

    Base.metadata.create_all(bind=engine)
    ran: list[int] = []
    monkeypatch.setattr(orchestrator, "run", lambda request_id: ran.append(request_id))

    db = SessionLocal()
    try:
        out = adapter.run_technology_blueprint(db, inputs)
        assert ran == [out.request_id]
        row = out.row
        assert row.public_id and len(row.public_id) >= 8
        assert row.engagement_type == adapter.ENGAGEMENT_CAPABILITY
        assert json.loads(row.ops_numbers_json) == [{"question": "deliveries a day", "answer": CLIENT_FACT}]
        assert row.owner_email == "owner@example.com"
    finally:
        db.close()


def test_the_request_row_is_unchanged_by_every_engine_operation(engagement, inputs, outputs, calc, r30_row):
    """A3 / M5. The content hash r30 computes over the row, and the row's own
    stored integrity report, are identical before and after the import.

    Mutation: write to the Request row in mapping."""
    before_hash = r30_integrity.content_hash(r30_integrity.load(r30_row))
    before_report = r30_row.integrity_report_json

    imported = legacy_mapping.import_r30(outputs, engagement, inputs=inputs, calc=calc,
                                         engagement_id="E-1", decision_id="DEC-1", weight=0.6)
    engagement.apply_all(imported.deltas)
    legacy_mapping.release_findings(outputs)
    adapter.row_content_hash(r30_row)

    assert r30_integrity.content_hash(r30_integrity.load(r30_row)) == before_hash
    assert r30_row.integrity_report_json == before_report


def test_a_write_to_the_request_row_is_refused(r30_row):
    """The law's own failing fixture: `assert_row_untouched` is what makes the
    test above a law and not an observation."""
    before = adapter.snapshot(r30_row)
    r30_row.mvp_blueprint = "someone edited the legacy package"
    with pytest.raises(adapter.LegacyRowWritten):
        adapter.assert_row_untouched(r30_row, before)


def test_a_write_to_the_stored_report_is_refused(r30_row):
    before = adapter.snapshot(r30_row)
    r30_row.integrity_report_json = None
    with pytest.raises(adapter.LegacyRowWritten):
        adapter.assert_row_untouched(r30_row, before)


# ===========================================================================
# 5. The import
# ===========================================================================

@pytest.fixture
def imported(engagement, inputs, outputs, calc):
    result = legacy_mapping.import_r30(outputs, engagement, inputs=inputs, calc=calc,
                                       engagement_id="E-1", decision_id="DEC-1", weight=0.6)
    engagement.apply_all(result.deltas)
    return result


def _of_kind(reg, kind):
    return [e for e in reg.query(kind) if e.status not in T.TERMINAL_STATUSES]


def test_the_package_lands_as_typed_rows(engagement, imported):
    kinds = {e.kind for e in imported.entities}
    for expected in (T.Kind.INITIATIVE, T.Kind.DEPENDENCY, T.Kind.SUCCESS_CRITERION, T.Kind.ASSUMPTION,
                     T.Kind.ACTION, T.Kind.OWNER, T.Kind.PROCESS_STEP, T.Kind.RISK, T.Kind.CONTROL,
                     T.Kind.WORK_PRODUCT, T.Kind.DECISION, T.Kind.STATEMENT, T.Kind.FACT):
        assert expected in kinds, f"{expected.value} never arrived"
    assert all(e.provenance.actor is T.Actor.LEGACY_R30 for e in imported.entities)
    assert all(e.provenance.actor_ref.startswith("r30:request:57:") for e in imported.entities)


def test_the_workstream_records_which_request_delivered_it(engagement, imported):
    ws = engagement.get("WKS-1")
    assert ws.payload.legacy_request_id == 57
    assert ws.payload.initiative_ids, "the delivered initiatives are named on the workstream"
    # `work_products/decl.py:253` counts exactly this flag
    assert ws.field("has_legacy_request") is True


def test_modules_become_initiatives_with_their_dependencies(engagement, imported):
    initiatives = {e.payload.name: e for e in _of_kind(engagement, T.Kind.INITIATIVE)}
    assert set(initiatives) == {"Dispatch Pilot", "Route Board"}
    edges = [(d.payload.from_id, d.payload.to_id) for d in _of_kind(engagement, T.Kind.DEPENDENCY)]
    assert (initiatives["Route Board"].id, initiatives["Dispatch Pilot"].id) in edges


def test_consultant_proposed_claims_arrive_unapproved(engagement, imported):
    """M2. Every consultant-proposed r30 number is an ASSUMPTION, UNAPPROVED,
    PROPOSED, and keeps r30's own approval wording as a label."""
    assumptions = _of_kind(engagement, T.Kind.ASSUMPTION)
    assert assumptions, "the scenario assumption never arrived"
    for a in assumptions:
        assert a.payload.approval is T.ApprovalState.UNAPPROVED
        assert a.status is T.Status.PROPOSED
        assert a.authority is T.Authority.CONSULTANT
        assert any(label.startswith("legacy_approval:") for label in a.labels)
    assert any("20%" in a.payload.statement for a in assumptions)


def test_a_client_number_is_not_duplicated(engagement, imported):
    """M3. The client's figure exists once: the claim resolves to the FACT the
    client stated, and no second copy is written."""
    assert imported.entity_by_claim["CF-01"] == "FCT-1"
    client_facts = [e for e in _of_kind(engagement, T.Kind.FACT)
                    if e.payload.basis is T.FactBasis.CLIENT_STATED]
    assert [e.id for e in client_facts] == ["FCT-1"]


def test_a_machine_computed_claim_that_recomputes_becomes_a_confirmed_calculated_fact(
        engagement, imported, calc):
    """M1, the passing half. 40 x 12 is 480, so the engine's own calculator
    confirms it and the row's authority is the deterministic engine."""
    eid = imported.entity_by_claim["DV-01"]
    fact = engagement.get(eid)
    assert fact.payload.basis is T.FactBasis.CALCULATED
    assert fact.payload.formula == "FCT-1 * 12"
    assert fact.payload.inputs == ("FCT-1",)
    assert fact.status is T.Status.CONFIRMED
    assert fact.authority is T.Authority.DETERMINISTIC_ENGINE
    assert fact.confirmed_by.startswith("calculator:")
    assert calc.recompute(fact, engagement) is True


def test_a_machine_computed_claim_that_does_not_recompute_becomes_a_finding(engagement, imported):
    """M1, the failing half. 40 x 12 is not 999: the number stays PROPOSED and
    a blocking L13 finding names it.

    Mutation: import an unverified claim as CONFIRMED."""
    eid = imported.entity_by_claim["DV-02"]
    fact = engagement.get(eid)
    assert fact.status is T.Status.PROPOSED
    blocking = [f for f in imported.findings if f.blocks_final and eid in f.entity_ids]
    assert blocking, "a legacy calculation that does not reproduce its value passed silently"
    assert blocking[0].law == legacy_mapping.LAW_LEGACY_NOT_FINAL


def test_arithmetic_the_engine_cannot_restate_is_recorded_but_not_called_a_defect(imported):
    """Absent evidence is not evidence of a defect (owner constraint): r30
    computed DV-03 from a financial-model line the engine has no formula for.
    It is not imported as a checked calculation and it does not block."""
    assert "DV-03" not in imported.entity_by_claim
    records = [f for f in imported.findings if f.where == "DV-03"]
    assert len(records) == 1
    assert records[0].blocks_final is False
    assert records[0].severity is T.Severity.LOW


def test_no_legacy_row_is_born_confirmed(imported):
    """LG3. CONFIRMED is a transition the calculator makes, never a status a
    producer writes."""
    born = [e for e in imported.entities if e.status in (T.Status.CONFIRMED, T.Status.APPROVED)]
    assert born == []
    confirmations = [d for d in imported.deltas if isinstance(d, T.SetStatus)]
    assert confirmations and all(d.by.actor is T.Actor.CALCULATOR for d in confirmations)


def test_the_canonical_gate_sentence_appears_verbatim(engagement, imported):
    """M4. The gate is a subordinate decision, a success criterion and one
    STATEMENT whose text is `pilot_gate.canonical_sentence` character for
    character - the sentence every engine product renders by token."""
    statements = _of_kind(engagement, T.Kind.STATEMENT)
    assert [s.payload.text for s in statements] == [GATE_SENTENCE]
    criterion = engagement.get(statements[0].payload.of_entity_id)
    assert criterion.kind is T.Kind.SUCCESS_CRITERION
    assert criterion.payload.text == GATE_SENTENCE
    subordinate = [d for d in _of_kind(engagement, T.Kind.DECISION)
                   if d.payload.role is T.DecisionRole.SUBORDINATE]
    assert [d.payload.statement for d in subordinate] == [GATE_SENTENCE]
    assert statements[0].payload.token.startswith("[[STMT:")


def test_the_gate_sentence_is_not_paraphrased_anywhere(engagement, imported):
    """The gate claim is mapped once, by the gate path: no second rendering of
    it exists to drift from the first."""
    texts = [e.payload.text for e in _of_kind(engagement, T.Kind.SUCCESS_CRITERION)
             if e.payload.text == GATE_SENTENCE]
    assert len(texts) == 1


def test_module_kpis_become_success_criteria_on_their_initiative(engagement, imported):
    eid = imported.entity_by_claim["MK-m2-01"]
    criterion = engagement.get(eid)
    assert criterion.kind is T.Kind.SUCCESS_CRITERION
    assert criterion.payload.text == "Time to assign a run: 12 minutes"
    initiative_ids = {e.id for e in _of_kind(engagement, T.Kind.INITIATIVE)}
    assert set(criterion.provenance.derived_from) & initiative_ids


def test_the_operations_layers_land_in_their_declared_kinds(engagement, imported):
    assert [a.payload.text for a in _of_kind(engagement, T.Kind.ACTION)] == [
        "Write the drop address on the day sheet", "Read the address back to the caller"]
    assert [o.payload.name for o in _of_kind(engagement, T.Kind.OWNER)] == ["Dispatcher"]
    assert [p.payload.perspective for p in _of_kind(engagement, T.Kind.PROCESS_STEP)] == [
        T.StepPerspective.CUSTOMER]
    assert [r.payload.who_feels_it for r in _of_kind(engagement, T.Kind.RISK)] == ["the dispatcher"]
    assert [c.payload.text for c in _of_kind(engagement, T.Kind.CONTROL)] == [
        "End of shift before the last van leaves"]


def test_the_three_volumes_are_declared_work_products(engagement, imported):
    products = _of_kind(engagement, T.Kind.WORK_PRODUCT)
    assert len(products) == len(adapter.VOLUME_KINDS)
    assert {p.payload.product_id for p in products} == {"legacy_volume"}
    assert {p.payload.title for p in products} == {"dispatch software"}
    for kind in adapter.VOLUME_KINDS:
        assert any(kind in p.payload.planned_because for p in products)
    assert set(imported.volume_ids) == {p.id for p in products}


def test_every_imported_row_cites_what_it_rests_on(imported):
    for e in imported.entities:
        assert e.provenance.derived_from, f"{e.kind.value} {e.id} cites nothing"


# ===========================================================================
# 6. What r30 says about its own package
# ===========================================================================

def test_a_released_package_blocks_nothing(outputs):
    """The negative control: r30 says final, the engine adds no L13 finding."""
    assert outputs.release["status"] in adapter.R30_RELEASED, outputs.release["reasons"]
    assert legacy_mapping.release_findings(outputs) == ()


def test_a_draft_package_blocks_the_engine_release():
    """M6. Every reason r30 gives for withholding its own release becomes a
    blocking engine finding: the engine cannot release around it."""
    row = FakeRequestRow(qa_report_json=None).freeze_integrity()
    findings = legacy_mapping.release_findings(adapter.load_outputs(row))
    assert findings and all(f.blocks_final for f in findings)
    assert all(f.law == legacy_mapping.LAW_LEGACY_NOT_FINAL for f in findings)


def test_an_r30_integrity_finding_blocks_the_engine_release():
    row = FakeRequestRow().freeze_integrity(findings=[{
        "law": "R30.example", "where": "modules[0]", "issue": "a coined number",
        "fix": "register the claim"}])
    findings = legacy_mapping.release_findings(adapter.load_outputs(row))
    assert any("coined number" in f.issue for f in findings)
    assert all(f.blocks_final for f in findings)


def test_a_package_with_no_current_report_is_not_treated_as_clean():
    """A missing audit is a missing audit, never a pass."""
    row = FakeRequestRow(integrity_report_json=None)
    findings = legacy_mapping.release_findings(adapter.load_outputs(row))
    assert any("integrity report" in f.issue for f in findings)


def test_a_run_that_never_finished_imports_nothing(engagement, inputs, calc):
    row = FakeRequestRow(status="failed", is_failed=True).freeze_integrity()
    result = legacy_mapping.import_r30(adapter.load_outputs(row), engagement, inputs=inputs,
                                       calc=calc, engagement_id="E-1")
    assert result.deltas == ()
    assert result.findings and all(f.blocks_final for f in result.findings)


# ===========================================================================
# 7. The method: the decision comes first
# ===========================================================================

def _ctx(engagement, calc, fake_provider, **settings):
    return MethodContext(registry=engagement, provider=fake_provider(), calc=calc,
                         actor=T.Actor.METHOD, actor_ref=f"method:{METHOD_ID}@1",
                         issue_ids=("ISS-1",), settings=settings)


def test_the_method_writes_the_commissioning_decision_first(engagement, calc, fake_provider):
    """LG1. The first run of a costed step is a decision for the client, not
    a purchase."""
    result = METHODS.get(METHOD_ID).run(_ctx(engagement, calc, fake_provider))
    assert len(result.deltas) == 1
    decision = result.deltas[0].entity
    assert decision.kind is T.Kind.DECISION_REQUIRED
    assert decision.payload.text == adapter.COMMISSION_TEXT
    assert decision.payload.from_authority is T.Authority.CLIENT
    assert decision.status is T.Status.OPEN


def test_the_method_does_nothing_while_the_decision_is_open(engagement, calc, fake_provider):
    engagement.apply_all(METHODS.get(METHOD_ID).run(_ctx(engagement, calc, fake_provider)).deltas)
    spent = {"n": 0}

    def commission(_inputs):
        spent["n"] += 1
        raise AssertionError("the pipeline ran without the client's decision")

    result = METHODS.get(METHOD_ID).run(
        _ctx(engagement, calc, fake_provider, legacy_r30_commission=commission))
    assert result.deltas == () and spent["n"] == 0


def _resolve_commission(engagement, calc, fake_provider):
    deltas = METHODS.get(METHOD_ID).run(_ctx(engagement, calc, fake_provider)).deltas
    decision = engagement.apply_all(deltas)[0]      # the registry names the row
    engagement.apply(T.SetStatus(decision.id, T.Status.RESOLVED,
                                 by=T.Provenance(actor=T.Actor.CLIENT, actor_ref="client:1")))
    return decision


def test_the_method_runs_the_pipeline_once_the_client_resolves_it(engagement, calc, fake_provider, outputs):
    """The whole path: decision resolved, inputs composed by query, package
    imported as typed rows."""
    _resolve_commission(engagement, calc, fake_provider)
    seen: list[adapter.R30Inputs] = []

    def commission(composed):
        seen.append(composed)
        return outputs

    result = METHODS.get(METHOD_ID).run(
        _ctx(engagement, calc, fake_provider, legacy_r30_commission=commission,
             legacy_r30_business_name="Rotterdam Courier", legacy_r30_owner_email="owner@example.com"))
    assert len(seen) == 1
    assert seen[0].engagement_type == adapter.ENGAGEMENT_CAPABILITY
    assert seen[0].workstream_id == "WKS-1"
    engagement.apply_all(result.deltas)
    assert {e.kind for e in _of_kind(engagement, T.Kind.INITIATIVE)} == {T.Kind.INITIATIVE}


def test_the_method_says_so_when_it_cannot_commission(engagement, calc, fake_provider):
    """No seam, no package - and no silence about it."""
    _resolve_commission(engagement, calc, fake_provider)
    result = METHODS.get(METHOD_ID).run(
        _ctx(engagement, calc, fake_provider, legacy_r30_business_name="x",
             legacy_r30_owner_email="o@example.com"))
    assert result.deltas == ()
    assert [f.law for f in result.findings] == [f"M.{METHOD_ID}.no_commissioning_seam"]


def test_the_methods_validators_catch_an_approved_assumption(engagement, calc, fake_provider, outputs,
                                                             inputs):
    """LG4's failing fixture, built by hand: an ASSUMPTION that arrived
    approved is refused by the validator whatever produced it."""
    spec = METHODS.get(METHOD_ID).spec
    approved = T.make_entity(
        kind=T.Kind.ASSUMPTION, engagement_id="E-1",
        payload=T.AssumptionPayload(statement="20%", approval=T.ApprovalState.APPROVED),
        provenance=T.Provenance(actor=T.Actor.LEGACY_R30, actor_ref="r30:request:57:claim:SA-01",
                                derived_from=("FCT-1",)),
        confidence=T.Confidence(None), relevance=T.Relevance("DEC-1", 0.6),
        relation=T.RelationToCentralDecision.INFORMS, status=T.Status.PROPOSED)
    result = legacy_mapping.LegacyImport(deltas=(T.Add(approved),))
    findings = [f for v in spec.validators for f in v(engagement, result)]
    assert any(f.law.endswith("approved_assumption") for f in findings)


def test_the_methods_validators_pass_a_clean_import(engagement, calc, fake_provider, outputs, inputs):
    """The negative control for the validators."""
    spec = METHODS.get(METHOD_ID).spec
    imported = legacy_mapping.import_r30(outputs, engagement, inputs=inputs, calc=calc,
                                         engagement_id="E-1", decision_id="DEC-1", weight=0.6)
    from app.engine.methods.contract import MethodResult

    result = MethodResult(deltas=imported.deltas)
    assert [f for v in spec.validators for f in v(engagement, result)] == []


# ===========================================================================
# 8. The seams to the rest of the engine
# ===========================================================================

def test_the_law_the_adapter_reports_under_is_the_gates_own_law():
    """`mapping.LAW_LEGACY_NOT_FINAL` is a frozen literal so the adapter can
    name its findings without importing the gate package. This is the pin
    that keeps the two from drifting apart the day L13 is renamed."""
    laws = pytest.importorskip("app.engine.gates.laws")
    assert legacy_mapping.LAW_LEGACY_NOT_FINAL == laws.LawId.L13.value


def test_the_workstream_flag_is_the_one_the_gate_and_the_planner_count(engagement, imported):
    """`gates/laws.legacy_request_ids` and `work_products/decl.py:253` both
    find a delivered package through `legacy_request_id` on a WORKSTREAM."""
    laws = pytest.importorskip("app.engine.gates.laws")
    assert laws.legacy_request_ids(engagement) == [57]


def test_compose_inputs_checks_itself(engagement, monkeypatch):
    """A1's call site, not only A1: a composer that stopped checking would be
    free to coin, so the check is pinned where it runs."""
    monkeypatch.setattr(adapter._Composed, "take",
                        lambda self, e: "a sentence nobody in this engagement said")
    with pytest.raises(adapter.LegacyInputsCoined):
        adapter.compose_inputs(engagement, business_name="x", owner_email="o@example.com",
                               issue_id="ISS-1", workstream_id="WKS-1")


def test_the_volume_files_are_built_by_r30s_own_renderer(outputs, monkeypatch):
    """MF2.7: `export_pdf.build_pdf` is called unchanged, so a legacy volume
    carries the same faces, footers and DRAFT stamp as every r30 volume."""
    from app.pipeline import export_pdf

    seen = []
    monkeypatch.setattr(export_pdf, "build_pdf", lambda row, kind: seen.append((row.id, kind)) or f"/x/{kind}.pdf")
    assert adapter.volume_path(outputs, "blueprint") == "/x/blueprint.pdf"
    assert seen == [(57, "blueprint")]


def test_a_client_figure_r30_mined_from_prose_is_recorded_not_manufactured(engagement, inputs, calc):
    """r30 also mines numbers out of the free text it was given. The engine
    holds those as prose, not as FACT rows, and says so rather than inventing
    a client fact the client never stated as one."""
    reg = r30_registry_dict()
    reg["claims"].append(_claim("CF-02", "client_fact", 6, "customers", provenance="client_input",
                                approval="client_stated", source="free_text: business_description",
                                text="one in six comes back undelivered"))
    row = FakeRequestRow(registry_json=json.dumps(reg)).freeze_integrity()
    result = legacy_mapping.import_r30(adapter.load_outputs(row), engagement, inputs=inputs,
                                       calc=calc, engagement_id="E-1")
    assert "CF-02" not in result.entity_by_claim
    record = [f for f in result.findings if f.where == "CF-02"]
    assert len(record) == 1 and record[0].blocks_final is False


def test_an_unknown_provenance_is_not_guessed_at(engagement, inputs, calc):
    """A provenance word the engine has no authority table for is the one case
    where importing would invent an authority. It is left out and recorded."""
    reg = r30_registry_dict()
    reg["claims"].append(_claim("XX-01", "derived_value", 3, "vans", provenance="somewhere_else",
                                approval="unknown", source="?", text="three vans"))
    row = FakeRequestRow(registry_json=json.dumps(reg)).freeze_integrity()
    result = legacy_mapping.import_r30(adapter.load_outputs(row), engagement, inputs=inputs,
                                       calc=calc, engagement_id="E-1")
    assert "XX-01" not in result.entity_by_claim
    assert any(f.where == "XX-01" and not f.blocks_final for f in result.findings)
