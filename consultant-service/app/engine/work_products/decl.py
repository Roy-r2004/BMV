"""Work-product declarations: the closed applicability algebra and the 21
products (contracts.py section 13; design 10.1).

The laws this module enforces, each in the docstring of the thing that
enforces it:

  P1  applicability is a Predicate built only from InputSpecs and counts, so
      a predicate that reads text cannot be constructed and a callable is
      not a predicate (a lambda could branch on anything, including a client
      name)
  P2  every section query is an InputSpec, filter-checked at construction
  P3  a mandatory product declares Always() and nothing else is fixed: the
      planned set varies per registry within MIN..MAX_WORK_PRODUCTS

A product's identity varies through entity fields ({central_decision},
{deadline}, {workstream}) rendered into `title_template`, never through an
engagement label: the same 21 declarations serve a market entry and a
turnaround, and which of them plan is a function of counts over enums only.
The named minimum counts (MIN_DIAG_FACTS, MIN_CALC, MIN_ORG, MIN_STEPS,
MIN_ACTIONS) are read from settings, never written as literals in a
predicate, so no count that should vary per operator is fixed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Mapping, TYPE_CHECKING

from app.engine.methods.contract import InputSpec
from app.engine.types import (
    BOUNDS,
    CapabilityClass,
    DecisionRole,
    FactBasis,
    GapState,
    Horizon,
    Kind,
    SourceKind,
    Status,
    StepPerspective,
    UnitFamily,
)

if TYPE_CHECKING:  # the read-side protocol lives with the registry; never imported at runtime here
    from app.engine.registry import RegistryView


# =============================================================================
# Planning bounds (design section 20)
# =============================================================================

# Defaults for the planning minima the design names. They belong in
# types.BOUNDS / Settings ENGINE_* like every other bound; until that pair
# carries them, this table is the declared default and _bound() prefers the
# live setting whenever one exists, so an operator can move them without
# touching a predicate.
PLANNING_BOUNDS: Mapping[str, int] = {
    "MIN_DIAG_FACTS": 4, "MIN_CALC": 2, "MIN_ORG": 3, "MIN_STEPS": 3, "MIN_ACTIONS": 3,
}


def _bound(name: str) -> int:
    """The live value of a named planning bound: the ENGINE_<name> setting
    when the config module is importable and carries it, else the declared
    default. A predicate never holds a literal count (dynamic-not-hardcoded);
    it holds the name's current value."""
    try:
        from app.config import settings
        v = getattr(settings, f"ENGINE_{name}", None)
        if v is not None:
            return int(v)
    except Exception:
        pass
    if name in BOUNDS:
        return int(BOUNDS[name])
    return int(PLANNING_BOUNDS[name])


# =============================================================================
# The predicate algebra (P1)
# =============================================================================

class Predicate:
    """Closed applicability algebra: built only from InputSpecs and counts,
    so a predicate cannot read text (P1) - the InputSpec constructor already
    refuses a filter outside FILTERABLE_FIELDS. evaluate() returns
    (holds, because) with `because` composed from counts, which is what a
    WORK_PRODUCT's planned_because and the Integrity Record's unplanned
    verdicts render."""

    def evaluate(self, view: "RegistryView") -> tuple[bool, str]:
        raise NotImplementedError


@dataclass(frozen=True)
class Count(Predicate):
    spec: InputSpec
    min_count: int = 1

    def evaluate(self, view: "RegistryView") -> tuple[bool, str]:
        n = sum(1 for e in view.query(self.spec.kind) if self.spec.matches(e))
        return n >= self.min_count, f"{n} {self.spec.name}"


@dataclass(frozen=True)
class AllOf(Predicate):
    parts: tuple[Predicate, ...]

    def evaluate(self, view: "RegistryView") -> tuple[bool, str]:
        results = [p.evaluate(view) for p in self.parts]
        return all(r[0] for r in results), ", ".join(r[1] for r in results)


@dataclass(frozen=True)
class AnyOf(Predicate):
    parts: tuple[Predicate, ...]

    def evaluate(self, view: "RegistryView") -> tuple[bool, str]:
        results = [p.evaluate(view) for p in self.parts]
        return any(r[0] for r in results), ", ".join(r[1] for r in results)


@dataclass(frozen=True)
class Always(Predicate):
    def evaluate(self, view: "RegistryView") -> tuple[bool, str]:
        return True, "mandatory"


# =============================================================================
# Sections, rendering rules, the declaration (P2, P3)
# =============================================================================

@dataclass(frozen=True)
class SectionDecl:
    id: str
    title: str
    query: tuple[InputSpec, ...]
    renderer: str                            # "statement_list" | "table" | "tree" | "narrative" | "label_list" | "evidence_table" | "calc_table"
    required: bool = False                   # False: dropped when its query matches nothing (section-level applicability)

    RENDERERS: ClassVar[frozenset[str]] = frozenset({"statement_list", "table", "tree", "narrative", "label_list",
                                                     "evidence_table", "calc_table"})

    def __post_init__(self):
        if self.renderer not in self.RENDERERS:
            raise ValueError(f"unknown renderer {self.renderer!r}")


@dataclass(frozen=True)
class RenderingRules:
    label_unapproved_assumptions: bool = True
    unknown_text: str = "not yet known"
    cite_provenance: bool = True
    statements_by_token: bool = True
    conditional_recommendations_marked: bool = True
    numbers_must_trace: bool = True
    client_facts_verbatim: bool = True       # MF2.6: client fact spans are masked from every mapping


@dataclass(frozen=True)
class WorkProductDecl:
    """P1: applicability is a Predicate (cannot read text). P2: every section
    query is an InputSpec (filter-checked). P3: a mandatory product has Always()
    applicability; nothing else is fixed - the planned set varies per registry
    within MIN_WORK_PRODUCTS..MAX_WORK_PRODUCTS. `title_template` may reference
    entity fields ({central_decision}) so identity varies without branching."""
    id: str
    title_template: str
    applicability: Predicate
    sections: tuple[SectionDecl, ...]
    rules: RenderingRules = RenderingRules()
    mandatory: bool = False
    formats: tuple[str, ...] = ("md", "pdf")

    def __post_init__(self):
        if not isinstance(self.applicability, Predicate):
            raise TypeError(f"P1: {self.id} applicability must be a Predicate, not a callable")
        if self.mandatory and not isinstance(self.applicability, Always):
            raise ValueError(f"P3: mandatory product {self.id} must declare Always()")
        for s in self.sections:
            for q in s.query:
                if not isinstance(q, InputSpec):
                    raise TypeError(f"P2: section {s.id} query must be InputSpecs")


@dataclass(frozen=True)
class PlanVerdict:
    product_id: str
    planned: bool
    because: str
    section_ids: tuple[str, ...] = ()


class WorkProductRegistry:
    def __init__(self) -> None:
        self._products: dict[str, WorkProductDecl] = {}

    def register(self, decl: WorkProductDecl) -> WorkProductDecl:
        if decl.id in self._products:
            raise ValueError(f"work product {decl.id!r} already registered")
        self._products[decl.id] = decl
        return decl

    def all(self) -> list[WorkProductDecl]:
        return list(self._products.values())

    def get(self, product_id: str) -> WorkProductDecl:
        return self._products[product_id]


WORK_PRODUCTS = WorkProductRegistry()


def register_product(decl: WorkProductDecl) -> WorkProductDecl:
    return WORK_PRODUCTS.register(decl)


def plan_sections(decl: WorkProductDecl, view: "RegistryView") -> tuple[str, ...]:
    """Section-level applicability (MF1.1): a non-required section whose query
    matches nothing is dropped, so a rendered product never carries an empty
    heading standing in for evidence that does not exist."""
    out = []
    for s in decl.sections:
        if s.required or any(q.matches(e) for q in s.query for e in view.query(q.kind)):
            out.append(s.id)
    return tuple(out)


# =============================================================================
# The 21 declarations (design 10.1): counts over enums, titles over entity fields
# =============================================================================

def _spec(name: str, kind: Kind, flt: Mapping[str, Any] | None = None, *,
          min_status: Status = Status.PROPOSED) -> InputSpec:
    return InputSpec(name=name, kind=kind, filter=dict(flt or {}), min_status=min_status)


def _sec(sid: str, title: str, renderer: str, *specs: InputSpec, required: bool = False) -> SectionDecl:
    return SectionDecl(id=sid, title=title, query=tuple(specs), renderer=renderer, required=required)


# Shared specs the declarations count and the sections re-query.
_CENTRAL = _spec("central decision", Kind.DECISION, {"role": DecisionRole.CENTRAL})
_CALC_MONEY = _spec("calculated money facts", Kind.FACT, {"basis": FactBasis.CALCULATED, "unit_family": UnitFamily.MONEY})
_CAP_GAP = _spec("capability gaps", Kind.CAPABILITY, {"gap": (GapState.MISSING, GapState.PARTIAL)})
_DATA_GAP = _spec("data and integration gaps", Kind.CAPABILITY,
                  {"capability_class": CapabilityClass.DATA_AND_INTEGRATION, "gap": (GapState.MISSING, GapState.PARTIAL)})
_CLOCK_DEADLINE = _spec("clock-starting dated deadlines", Kind.DEADLINE, {"starts_clock": True, "has_date": True})
_GATE_MILESTONE = _spec("gate milestones", Kind.MILESTONE, {"gate": True})
_DAY_ACTIONS = _spec("day-horizon actions", Kind.ACTION, {"horizon": Horizon.DAYS})
_INTERNAL_STEPS = _spec("internal process steps", Kind.PROCESS_STEP, {"perspective": StepPerspective.INTERNAL})
_CUSTOMER_STEPS = _spec("customer process steps", Kind.PROCESS_STEP, {"perspective": StepPerspective.CUSTOMER})
_RACI_GOVERNANCE = _spec("governance with raci", Kind.GOVERNANCE, {"has_raci": True})
_LEGACY_WORKSTREAMS = _spec("legacy-delivered workstreams", Kind.WORKSTREAM, {"has_legacy_request": True})


def _declare() -> None:
    """Registration by module import, exactly like the method registry: adding
    a product never touches the planner. Order here is registration order,
    which plan_work_products preserves so plans are deterministic."""
    P = register_product

    P(WorkProductDecl(
        id="executive_decision_brief",
        title_template="Decision Brief: {central_decision}",
        applicability=Always(), mandatory=True,
        sections=(
            _sec("the_decision", "The decision", "statement_list", _CENTRAL, required=True),
            _sec("recommendations", "Recommendations", "statement_list", _spec("recommendations", Kind.RECOMMENDATION), required=True),
            _sec("key_facts", "What the evidence shows", "evidence_table", _spec("facts", Kind.FACT)),
            # What the client said the answer has to live within. No product
            # read a CONSTRAINT at all before this: the limits a client states
            # are the first thing that makes a recommendation wrong, and the
            # brief that states the recommendation was not stating them. The
            # section is planned only where the engagement holds one, so a
            # brief on an engagement that declared no limits does not carry an
            # empty heading claiming there are none.
            _sec("constraints", "What the answer must live within", "label_list",
                 _spec("constraints", Kind.CONSTRAINT)),
            _sec("open_questions", "Open questions", "label_list", _spec("questions", Kind.QUESTION)),
            _sec("risks", "Risks", "label_list", _spec("risks", Kind.RISK)),
        )))

    P(WorkProductDecl(
        id="integrity_record",
        title_template="Integrity Record",
        applicability=Always(), mandatory=True,
        sections=(
            _sec("planned_products", "Planned and unplanned work products", "table", _spec("work products", Kind.WORK_PRODUCT), required=True),
            _sec("sources", "Evidence sources", "evidence_table", _spec("sources", Kind.EVIDENCE_SOURCE)),
            _sec("assumptions", "Assumptions", "table", _spec("assumptions", Kind.ASSUMPTION)),
            _sec("conflicts", "Conflicts", "table", _spec("conflicts", Kind.CONFLICT)),
            _sec("regulated_matters", "Regulated matters routed", "table", _spec("regulated matters", Kind.REGULATED_MATTER)),
        )))

    P(WorkProductDecl(
        id="diagnostic_evidence_report",
        title_template="Diagnostic and Evidence Report",
        applicability=AllOf((
            Count(_spec("confirmed facts", Kind.FACT, min_status=Status.CONFIRMED), _bound("MIN_DIAG_FACTS")),
            Count(_spec("hypotheses", Kind.HYPOTHESIS)),
        )),
        sections=(
            _sec("findings", "Findings", "statement_list", _spec("confirmed facts", Kind.FACT, min_status=Status.CONFIRMED), required=True),
            _sec("hypotheses", "Hypotheses and verdicts", "tree", _spec("hypotheses", Kind.HYPOTHESIS), required=True),
            _sec("evidence", "Evidence", "evidence_table", _spec("sources", Kind.EVIDENCE_SOURCE)),
        )))

    P(WorkProductDecl(
        id="evidence_book",
        title_template="Evidence Book",
        applicability=Count(_spec("document sources", Kind.EVIDENCE_SOURCE,
                                  {"source_kind": (SourceKind.DOCUMENT, SourceKind.DATASET, SourceKind.LINK)})),
        sections=(
            _sec("sources", "Sources", "evidence_table",
                 _spec("document sources", Kind.EVIDENCE_SOURCE,
                       {"source_kind": (SourceKind.DOCUMENT, SourceKind.DATASET, SourceKind.LINK)}), required=True),
            _sec("extracted_facts", "Facts drawn from the record", "table",
                 _spec("document facts", Kind.FACT,
                       {"basis": (FactBasis.DOCUMENT_EXTRACTED, FactBasis.DOCUMENT_VERIFIED)})),
        )))

    P(WorkProductDecl(
        id="options_tradeoff_assessment",
        title_template="Options and Trade-offs: {central_decision}",
        applicability=AllOf((Count(_spec("options", Kind.OPTION), 2), Count(_spec("trade-offs", Kind.TRADE_OFF)))),
        sections=(
            _sec("options", "The options", "table", _spec("options", Kind.OPTION), required=True),
            _sec("tradeoffs", "Trade-offs", "table", _spec("trade-offs", Kind.TRADE_OFF), required=True),
            _sec("criteria", "Evaluation criteria", "table", _spec("criteria", Kind.EVALUATION_CRITERION)),
        )))

    P(WorkProductDecl(
        id="business_case_financial_model",
        title_template="Financial Model: {central_decision}",
        applicability=AllOf((
            Count(_CALC_MONEY, _bound("MIN_CALC")),
            AnyOf((Count(_spec("costs", Kind.COST)), Count(_spec("benefits", Kind.BENEFIT)))),
        )),
        sections=(
            _sec("calculations", "Calculations", "calc_table", _CALC_MONEY, required=True),
            _sec("costs", "Costs", "table", _spec("costs", Kind.COST)),
            _sec("benefits", "Benefits", "table", _spec("benefits", Kind.BENEFIT)),
            _sec("assumptions", "Assumptions used", "table", _spec("assumptions", Kind.ASSUMPTION)),
        )))

    P(WorkProductDecl(
        id="recommended_target_state",
        title_template="Recommended Target State",
        applicability=AllOf((
            Count(_CAP_GAP),
            AnyOf((Count(_spec("governance", Kind.GOVERNANCE)),
                   Count(_spec("process actions", Kind.ACTION, {"capability_class": CapabilityClass.PROCESS})))),
        )),
        sections=(
            _sec("capability_gaps", "Capability gaps", "table", _CAP_GAP, required=True),
            _sec("governance", "Governance", "table", _spec("governance", Kind.GOVERNANCE)),
            _sec("actions", "Actions to close the gaps", "table", _spec("actions", Kind.ACTION)),
        )))

    P(WorkProductDecl(
        id="organization_design",
        title_template="Organization and Responsibility Design",
        applicability=AnyOf((
            Count(_spec("owners with a reporting line", Kind.OWNER, {"has_reports_to": True}), _bound("MIN_ORG")),
            Count(_RACI_GOVERNANCE),
        )),
        sections=(
            _sec("org_chart", "Organization chart", "tree", _spec("owners with a reporting line", Kind.OWNER, {"has_reports_to": True})),
            _sec("raci", "Responsibilities", "table", _RACI_GOVERNANCE),
            _sec("owners", "Owners", "table", _spec("owners", Kind.OWNER), required=True),
        )))

    P(WorkProductDecl(
        id="process_redesign",
        title_template="Process Redesign",
        applicability=AllOf((
            Count(_INTERNAL_STEPS, _bound("MIN_STEPS")),
            Count(_spec("process actions", Kind.ACTION, {"capability_class": CapabilityClass.PROCESS})),
        )),
        sections=(
            _sec("current_process", "The process as it runs today", "table", _INTERNAL_STEPS, required=True),
            _sec("pain_points", "Pain points", "table", _spec("pain points", Kind.PROCESS_STEP, {"pain_point": True})),
            _sec("redesign_actions", "Redesign actions", "table",
                 _spec("process actions", Kind.ACTION, {"capability_class": CapabilityClass.PROCESS}), required=True),
        )))

    P(WorkProductDecl(
        id="customer_journeys",
        title_template="Customer Journeys",
        applicability=Count(_CUSTOMER_STEPS, _bound("MIN_STEPS")),
        sections=(
            _sec("journey", "The journey", "table", _CUSTOMER_STEPS, required=True),
            _sec("pain_points", "Where it hurts", "table",
                 _spec("customer pain points", Kind.PROCESS_STEP,
                       {"perspective": StepPerspective.CUSTOMER, "pain_point": True})),
        )))

    P(WorkProductDecl(
        id="systems_and_data_map",
        title_template="Systems and Data Map",
        applicability=AllOf((
            Count(_spec("systems", Kind.CAPABILITY,
                        {"capability_class": (CapabilityClass.SOFTWARE_SYSTEM, CapabilityClass.DATA_AND_INTEGRATION)}), 2),
            Count(_spec("dependencies", Kind.DEPENDENCY)),
        )),
        sections=(
            _sec("systems", "Systems", "table",
                 _spec("systems", Kind.CAPABILITY,
                       {"capability_class": (CapabilityClass.SOFTWARE_SYSTEM, CapabilityClass.DATA_AND_INTEGRATION)}), required=True),
            _sec("dependencies", "Dependencies", "table", _spec("dependencies", Kind.DEPENDENCY), required=True),
        )))

    P(WorkProductDecl(
        id="systems_migration_plan",
        title_template="Systems Migration Plan",
        applicability=AllOf((
            Count(_DATA_GAP, 2),
            Count(_spec("technology initiatives", Kind.INITIATIVE,
                        {"capability_class": (CapabilityClass.SOFTWARE_SYSTEM, CapabilityClass.DATA_AND_INTEGRATION)})),
            Count(_spec("dependencies", Kind.DEPENDENCY)),
        )),
        sections=(
            _sec("gaps", "What must move", "table", _DATA_GAP, required=True),
            _sec("initiatives", "Migration initiatives", "table",
                 _spec("technology initiatives", Kind.INITIATIVE,
                       {"capability_class": (CapabilityClass.SOFTWARE_SYSTEM, CapabilityClass.DATA_AND_INTEGRATION)}), required=True),
            _sec("sequencing", "Sequencing", "table", _spec("dependencies", Kind.DEPENDENCY)),
            _sec("risks", "Migration risks", "table", _spec("risks", Kind.RISK)),
        )))

    P(WorkProductDecl(
        id="transformation_roadmap",
        title_template="Roadmap: {central_decision}",
        applicability=AllOf((Count(_spec("workstreams", Kind.WORKSTREAM)),
                             Count(_spec("actions", Kind.ACTION)),
                             Count(_spec("milestones", Kind.MILESTONE)))),
        sections=(
            _sec("workstreams", "Workstreams", "table", _spec("workstreams", Kind.WORKSTREAM), required=True),
            _sec("milestones", "Milestones", "table", _spec("milestones", Kind.MILESTONE), required=True),
            _sec("actions", "Actions", "table", _spec("actions", Kind.ACTION)),
        )))

    P(WorkProductDecl(
        id="implementation_plan",
        title_template="Implementation Plan",
        applicability=AllOf((Count(_spec("workstreams", Kind.WORKSTREAM)),
                             Count(_spec("actions", Kind.ACTION), _bound("MIN_ACTIONS")))),
        sections=(
            _sec("workstreams", "Workstreams", "table", _spec("workstreams", Kind.WORKSTREAM), required=True),
            _sec("actions", "Actions", "table", _spec("actions", Kind.ACTION), required=True),
            _sec("owners", "Who owns what", "table", _spec("owners", Kind.OWNER)),
            _sec("dependencies", "Dependencies", "table", _spec("dependencies", Kind.DEPENDENCY)),
        )))

    P(WorkProductDecl(
        id="dated_event_plan",
        title_template="{deadline}: first 100 days",
        applicability=AllOf((Count(_CLOCK_DEADLINE), Count(_GATE_MILESTONE), Count(_DAY_ACTIONS))),
        sections=(
            _sec("the_event", "The event that starts the clock", "table", _CLOCK_DEADLINE, required=True),
            _sec("gates", "Gates", "table", _GATE_MILESTONE, required=True),
            _sec("immediate_actions", "Immediate actions", "table", _DAY_ACTIONS, required=True),
        )))

    P(WorkProductDecl(
        id="risk_register",
        title_template="Risk Register",
        applicability=Count(_spec("risks", Kind.RISK)),
        sections=(
            _sec("risks", "Risks", "table", _spec("risks", Kind.RISK), required=True),
            _sec("controls", "Controls", "table", _spec("controls", Kind.CONTROL)),
        )))

    P(WorkProductDecl(
        id="governance_raci",
        title_template="Governance and RACI",
        applicability=Count(_RACI_GOVERNANCE),
        sections=(
            _sec("forums", "Forums and cadence", "table", _spec("governance", Kind.GOVERNANCE), required=True),
            _sec("raci", "RACI", "table", _RACI_GOVERNANCE, required=True),
        )))

    P(WorkProductDecl(
        id="change_communication_plan",
        title_template="Change and Communication Plan",
        applicability=AllOf((
            Count(_spec("stakeholders", Kind.STAKEHOLDER), 2),
            Count(_spec("people actions", Kind.ACTION, {"capability_class": CapabilityClass.PEOPLE_AND_ORGANISATION})),
        )),
        sections=(
            _sec("stakeholders", "Stakeholders", "table", _spec("stakeholders", Kind.STAKEHOLDER), required=True),
            _sec("actions", "Change actions", "table",
                 _spec("people actions", Kind.ACTION, {"capability_class": CapabilityClass.PEOPLE_AND_ORGANISATION}), required=True),
            _sec("risks", "Adoption risks", "table", _spec("risks", Kind.RISK)),
        )))

    P(WorkProductDecl(
        id="kpi_framework",
        title_template="KPI Framework",
        applicability=Count(_spec("measured success criteria", Kind.SUCCESS_CRITERION, {"has_measure": True})),
        sections=(
            _sec("criteria", "Success criteria", "table",
                 _spec("measured success criteria", Kind.SUCCESS_CRITERION, {"has_measure": True}), required=True),
            _sec("measures", "Measure definitions", "table", _spec("measures", Kind.MEASURE)),
            _sec("baselines", "Baselines", "table", _spec("measured facts", Kind.FACT, {"has_measure": True})),
        )))

    P(WorkProductDecl(
        id="decision_deck",
        title_template="Decision Deck: {central_decision}",
        applicability=AllOf((Count(_spec("trade-offs", Kind.TRADE_OFF)),
                             Count(_spec("recommendations", Kind.RECOMMENDATION)))),
        formats=("pptx",),
        sections=(
            _sec("decision", "The decision", "statement_list", _CENTRAL, required=True),
            _sec("tradeoffs", "Trade-offs", "table", _spec("trade-offs", Kind.TRADE_OFF), required=True),
            _sec("recommendation", "Recommendation", "statement_list", _spec("recommendations", Kind.RECOMMENDATION), required=True),
        )))

    P(WorkProductDecl(
        id="legacy_volume",
        title_template="{workstream}",
        applicability=Count(_LEGACY_WORKSTREAMS),
        formats=("pdf",),
        sections=(
            _sec("volume", "Delivered volume", "label_list", _LEGACY_WORKSTREAMS, required=True),
        )))


_declare()
