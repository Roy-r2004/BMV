"""Engine test fixtures (tests/engine/*).

tests/conftest.py is an ancestor conftest and already points DATABASE_URL at
a throwaway SQLite file and stubs the sign-in gate; the guard is repeated here
so an engine test collected on its own (pytest tests/engine/...) can never
reach the developer's real database either.

Every fixture that touches a module another component owns (registry, llm)
imports it inside the fixture body: a wave that has not landed those modules
yet still collects this directory, and only the tests that ask for them fail.
"""
from __future__ import annotations

import os
import sys
import tempfile
from decimal import Decimal

_SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _SERVICE_ROOT not in sys.path:
    sys.path.insert(0, _SERVICE_ROOT)

if "bmv-consultant-tests-" not in os.environ.get("DATABASE_URL", ""):
    os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(
        tempfile.mkdtemp(prefix="bmv-consultant-tests-"), "test.db")

import pytest  # noqa: E402

from app.engine import types as T  # noqa: E402

# One instant, everywhere. Byte-identical bundles across runs (design 17.4)
# need every recorded_at to be the same string, and a content hash that
# ignores the clock (MF3.7) must be provable against a clock that never moves.
FIXED_CLOCK = "2026-01-01T00:00:00+00:00"


@pytest.fixture
def fixed_clock():
    return lambda: FIXED_CLOCK


@pytest.fixture
def registry(fixed_clock):
    """Factory: registry(engagement_id="E-1") -> EngagementRegistry on the fixed clock."""
    from app.engine.registry import EngagementRegistry

    def make(engagement_id: str = "E-1", *, clock=None):
        return EngagementRegistry(engagement_id, clock=clock or fixed_clock)

    return make


@pytest.fixture
def fake_provider():
    """Factory: fake_provider(script=None, oracle=None) -> FakeProvider (records every call)."""
    from app.engine.llm import FakeProvider

    def make(script=None, oracle=None):
        return FakeProvider(script=script, oracle=oracle)

    return make


@pytest.fixture
def tmp_uploads(tmp_path, monkeypatch):
    """A throwaway uploads root, wired into Settings.UPLOADS_DIR for the test.
    Engagement documents and benchmark bundles never land under the real,
    gitignored uploads/ tree from a test."""
    from app.config import settings

    root = tmp_path / "uploads"
    (root / "engagements").mkdir(parents=True)
    (root / "benchmarks").mkdir(parents=True)
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(root))
    return root


# ---------------------------------------------------------------------------
# One well-formed payload per kind. Every enum-typed field holds a member,
# every Decimal is exact, every optional structure is populated at least once
# somewhere in the table -- so a round-trip over this table exercises every
# encoder branch (_encode / _decode) the persistence layer relies on.
# ---------------------------------------------------------------------------

def _qty(value: str = "1250.50", unit: str = "EUR", family: T.UnitFamily = T.UnitFamily.MONEY) -> T.Quantity:
    return T.Quantity(Decimal(value), unit, family,
                      T.Dimensions(currency="EUR", period="FY25", period_basis="year", scope=None,
                                   as_of="2025-12-31", definition=None))


def sample_payload(kind: T.Kind, **overrides):
    """A valid payload for `kind`; keyword overrides replace fields."""
    K = T.Kind
    table = {
        K.BUSINESS_CONTEXT: lambda: T.BusinessContextPayload(text="what it does", aspect="what_it_does"),
        K.DECISION: lambda: T.DecisionPayload(statement="which path", role=T.DecisionRole.CENTRAL,
                                              option_ids=("OPT-1",), owner_id="DOW-1"),
        K.DECISION_OWNER: lambda: T.DecisionOwnerPayload(name="owner", role="managing director", resolves=("DEC-1",)),
        K.STAKEHOLDER: lambda: T.StakeholderPayload(name="s", role="r", interest="i", influence="high"),
        K.OBJECTIVE: lambda: T.ObjectivePayload(text="o", priority=1, measure_id="MEA-1", target=_qty(),
                                                feasibility=T.Feasibility.UNTESTED),
        K.SUCCESS_CRITERION: lambda: T.SuccessCriterionPayload(text="sc", measure_id="MEA-1", target=_qty("10"),
                                                               baseline=_qty("4"), baseline_source="client_fact"),
        K.CONSTRAINT: lambda: T.ConstraintPayload(text="c", kind="financial", hard=True),
        K.DEADLINE: lambda: T.DeadlinePayload(text="d", date="2026-06-30", what_happens="w",
                                              origin=T.DeadlineOrigin.CONTRACT, starts_clock=True),
        K.MEASURE: lambda: T.MeasurePayload(name="m", unit_family=T.UnitFamily.COUNT, definition="heads",
                                            confirmed_by_client=True),
        K.FACT: lambda: T.FactPayload(statement="we have 40 people", basis=T.FactBasis.CLIENT_STATED,
                                      measure_id="MEA-1", quantity=_qty("40", "heads", T.UnitFamily.COUNT),
                                      record_class=None, topic="headcount"),
        K.ASSUMPTION: lambda: T.AssumptionPayload(statement="a", rationale="r", quantity=_qty("0.1", "%", T.UnitFamily.RATE),
                                                  approval=T.ApprovalState.UNAPPROVED, used_by=("REC-1",)),
        K.CONFLICT: lambda: T.ConflictPayload(
            kind=T.ConflictKind.VALUE, subject_id="MEA-1",
            conclusions=(T.ConflictConclusion("FCT-1", "40", evidence=("EVI-1",), assumptions=(), consequence="c"),
                         T.ConflictConclusion("FCT-2", "45", evidence=("EVI-2",))),
            relation_to_central_decision=T.RelationToCentralDecision.DEFINES,
            authority_required=T.Authority.CLIENT, material=True, recommended_resolution="FCT-2",
            recommendation_basis="CURRENT_STATE_PRECEDENCE: system_of_record > client_stated"),
        K.QUESTION: lambda: T.QuestionPayload(text="q", asks_for=(T.AsksFor(K.FACT, {"basis": "client_stated"}),),
                                              issue_ids=("ISS-1",), why="w", effort=T.EffortClass.LOOKUP,
                                              strategy=T.FillStrategy.ASK_CLIENT, material=True, value=0.4),
        K.ISSUE: lambda: T.IssuePayload(text="i", interrogative=T.Interrogative.HOW_MUCH, target_kind=K.COST,
                                        parent_id=None, quantified=True, capability_class=T.CapabilityClass.FINANCIAL,
                                        weight_to_parent=0.7, decisive_for=("DEC-1",),
                                        evidence_needed=(T.AsksFor(K.FACT),)),
        K.HYPOTHESIS: lambda: T.HypothesisPayload(text="h", issue_id="ISS-1", causes=("FCT-1",), verdict="untested"),
        K.ANALYSIS: lambda: T.AnalysisPayload(method_id="root_cause", method_version=1, issue_ids=("ISS-1",),
                                              state=T.AnalysisState.PLANNED),
        K.OPTION: lambda: T.OptionPayload(text="o", decision_id="DEC-1", mechanism="m", evidence=("FCT-1",)),
        K.EVALUATION_CRITERION: lambda: T.EvaluationCriterionPayload(text="e", decision_id="DEC-1", weight=0.5,
                                                                     weight_set_by=T.Authority.CLIENT),
        K.TRADE_OFF: lambda: T.TradeOffPayload(decision_id="DEC-1", option_ids=("OPT-1", "OPT-2"), gives_up="g",
                                               gains="g2", scores=(T.Score("OPT-1", "CRI-1", Decimal("3.5"), ("FCT-1",)),),
                                               material=False),
        K.RECOMMENDATION: lambda: T.RecommendationPayload(statement="r", decision_id="DEC-1", option_id="OPT-1",
                                                          supports=("FCT-1",), conditional_on=("QST-1",),
                                                          licensed_interpretation=False),
        K.CAPABILITY: lambda: T.CapabilityPayload(text="c", capability_class=T.CapabilityClass.PROCESS,
                                                  gap=T.GapState.PARTIAL, evidence=("FCT-1",)),
        K.PROCESS_STEP: lambda: T.ProcessStepPayload(text="p", perspective=T.StepPerspective.CUSTOMER, sequence=2,
                                                     actor_id="OWN-1", system_ids=("CAP-1",), pain_point=True),
        K.WORKSTREAM: lambda: T.WorkstreamPayload(name="w", purpose="p", capability_classes=(T.CapabilityClass.PROCESS,),
                                                  initiative_ids=("INI-1",), owner_id="OWN-1", legacy_request_id=57),
        K.INITIATIVE: lambda: T.InitiativePayload(name="i", workstream_id="WKS-1",
                                                  capability_class=T.CapabilityClass.SOFTWARE_SYSTEM, action_ids=("ACT-1",)),
        K.ACTION: lambda: T.ActionPayload(text="a", capability_class=T.CapabilityClass.PEOPLE_AND_ORGANISATION,
                                          horizon=T.Horizon.DAYS, initiative_id="INI-1", owner_id="OWN-1", sequence=1,
                                          depends_on=("ACT-0",), done_when=("SUC-1",)),
        K.MILESTONE: lambda: T.MilestonePayload(text="m", horizon=T.Horizon.MONTHS, gate=True, criteria=("SUC-1",),
                                                deadline_id="DDL-1"),
        K.DEPENDENCY: lambda: T.DependencyPayload(from_id="ACT-1", to_id="ACT-2", kind="blocks"),
        K.OWNER: lambda: T.OwnerPayload(name="o", role="r", owns=("ACT-1",), reports_to="OWN-0"),
        K.COST: lambda: T.CostPayload(text="c", basis="quote", quantity=_qty("900"), for_ids=("INI-1",)),
        K.BENEFIT: lambda: T.BenefitPayload(text="b", basis="calculated", quantity=_qty("1200"), for_ids=("INI-1",),
                                            conditional_on=("ASM-1",)),
        K.RISK: lambda: T.RiskPayload(text="r", likelihood="high", impact="low", who_feels_it="ops", control_ids=("CTL-1",)),
        K.CONTROL: lambda: T.ControlPayload(text="c", owner_id="OWN-1", risk_ids=("RSK-1",)),
        K.GOVERNANCE: lambda: T.GovernancePayload(text="g", forum="steerco", cadence="weekly", decides=("DEC-1",),
                                                  raci=(T.RaciRow("ACT-1", "OWN-1", "OWN-2", ("STK-1",), ("STK-2",)),)),
        K.DECISION_REQUIRED: lambda: T.DecisionRequiredPayload(text="d", from_authority=T.Authority.CLIENT,
                                                               decision_id="DEC-1", options=("OPT-1",), by_when="2026-03-01"),
        K.EXPECTED_OUTCOME: lambda: T.ExpectedOutcomePayload(text="e", measure_id="MEA-1", quantity=_qty("5"),
                                                             basis="calculated", supports=("FCT-1",)),
        K.WORK_PRODUCT: lambda: T.WorkProductPayload(product_id="decision_brief", title="t", planned_because="mandatory",
                                                     section_ids=("s1",), consumes=("REC-1",), artifact_ids=()),
        K.EVIDENCE_SOURCE: lambda: T.EvidenceSourcePayload(name="turn 1", source_kind=T.SourceKind.CONVERSATION_TURN,
                                                           record_class=T.RecordClass.UNKNOWN,
                                                           record_class_confirmed_by_client=False, text="we have 40 people",
                                                           received_at="2026-01-01T00:00:00+00:00"),
        K.STATEMENT: lambda: T.StatementPayload(text="s", of_entity_id="FCT-1", token="[[STMT:STA-1]]", rendered_in=("WPR-1",)),
        K.REGULATED_MATTER: lambda: T.RegulatedMatterPayload(text="m", domain=T.RegulatedDomain.TAX, adviser_class="tax adviser",
                                                             why_regulated="w", touches=("REC-1",), withheld_interpretation="x"),
        K.SPECIALIST_ASSIGNMENT: lambda: T.SpecialistAssignmentPayload(
            question="q", issue_id="ISS-1", method_id="root_cause", permitted_evidence=("FCT-1",),
            output_kinds=(K.HYPOTHESIS, K.QUESTION),
            allowed_assumptions=(T.AssumptionGrant(K.ASSUMPTION, T.UnitFamily.RATE, True),),
            forbidden_decisions=("DEC-1",), validation=("cites",), budget=T.Budget(2, 8000, 60), outcome="done"),
        K.CHARTER: lambda: T.CharterPayload(situation=("BCX-1",), central_decision="DEC-1", decision_owner="DOW-1",
                                            objectives=("OBJ-1",), scope=("ISS-1",), constraints=("CST-1",),
                                            evidence_available=("EVI-1",), key_questions=("ISS-1",),
                                            planned_analyses=("ANA-1",), proposed_work_products=("WPR-1",)),
    }
    payload = table[kind]()
    if overrides:
        from dataclasses import replace
        payload = replace(payload, **overrides)
    return payload


@pytest.fixture
def payload_of():
    return sample_payload


def sample_entity(kind: T.Kind, payload=None, *, actor: T.Actor = T.Actor.PARTNER, status: T.Status = T.Status.PROPOSED,
                  recorded_at: str = "", engagement_id: str = "E-1") -> T.Entity:
    """A well-formed entity through the only constructor producers use."""
    payload = sample_payload(kind) if payload is None else payload
    return T.make_entity(
        kind=kind, engagement_id=engagement_id, payload=payload,
        provenance=T.Provenance(actor=actor, actor_ref=f"{actor.value}:1", derived_from=("EVI-1",),
                                source_locator="we have 40 people", recorded_at=recorded_at),
        confidence=T.Confidence(None), relevance=T.Relevance("DEC-1", 0.5, "why"),
        relation=T.RelationToCentralDecision.INFORMS, status=status, entity_id=f"{T.ID_PREFIX[kind]}-1")


@pytest.fixture
def entity_of():
    return sample_entity
