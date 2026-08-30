"""app/engine/types.py - the frozen contracts of the universal consultancy engine.

Adopted verbatim from the judged synthesis (contracts.py sections 1-4, 6 and 16):
the closed vocabularies, exact quantities, the shared envelope, the 41 typed
payloads, the structural field surface (TEXT_FIELDS / FILTERABLE_FIELDS,
payload_field, validate_payload), info_type_of, Entity with its deltas and
findings, and the BOUNDS names. The authority tables and may_advance live in
app/engine/authority.py; method/registry contracts live in
app/engine/methods/contract.py and app/engine/registry.py.

Every law the registry, the selector, the runner or a gate enforces is stated
in the docstring of the thing that enforces it, with its id:

  I1..I8  registry write invariants          (EngagementRegistry.apply)
  M1..M4  method registration laws           (MethodSpec.__post_init__, MethodRegistry)
  S1..S6  specialist admission rules         (ADMISSION_RULES; runner applies all-or-nothing)
  P1..P3  work-product declaration laws      (WorkProductDecl.__post_init__, Predicate)
  L1..L14 release laws                       (LawId; bodies live in app/engine/gates/laws.py)

Nothing in this module can express an engagement type. The only vocabularies
are kinds of information, classes of source, structural shapes of questions
and the relation of a thing to the central decision. Changing anything here
after C0 is a new SCHEMA_VERSION and a migration through Entity.from_json.
"""
from __future__ import annotations

import hashlib
import json
import types as _types
from dataclasses import dataclass, field, fields, is_dataclass, replace
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Callable, ClassVar, Iterable, Mapping, Protocol, Sequence, Union, get_args, get_origin, get_type_hints, runtime_checkable

SCHEMA_VERSION = 2


# =============================================================================
# 1. Closed vocabularies (the only strings control flow may compare against)
# =============================================================================

class Kind(str, Enum):
    BUSINESS_CONTEXT = "business_context"
    DECISION = "decision"                  # payload.role: CENTRAL | SUBORDINATE | STATED_REQUEST
    DECISION_OWNER = "decision_owner"
    STAKEHOLDER = "stakeholder"
    OBJECTIVE = "objective"
    SUCCESS_CRITERION = "success_criterion"
    CONSTRAINT = "constraint"
    DEADLINE = "deadline"
    MEASURE = "measure"                    # the registered key two facts must share to be reconciled (MF1.6)
    FACT = "fact"                          # payload.basis discriminates the spec's evidence categories
    ASSUMPTION = "assumption"
    CONFLICT = "conflict"
    QUESTION = "question"
    ISSUE = "issue"                        # issue-tree node carrying a QuestionShape
    HYPOTHESIS = "hypothesis"
    ANALYSIS = "analysis"                  # a planned or executed method run
    OPTION = "option"
    EVALUATION_CRITERION = "evaluation_criterion"
    TRADE_OFF = "trade_off"
    RECOMMENDATION = "recommendation"
    CAPABILITY = "capability"
    PROCESS_STEP = "process_step"          # process-map / journey output (perspective: INTERNAL | CUSTOMER)
    WORKSTREAM = "workstream"
    INITIATIVE = "initiative"
    ACTION = "action"
    MILESTONE = "milestone"
    DEPENDENCY = "dependency"
    OWNER = "owner"
    COST = "cost"
    BENEFIT = "benefit"
    RISK = "risk"
    CONTROL = "control"
    GOVERNANCE = "governance"
    DECISION_REQUIRED = "decision_required"
    EXPECTED_OUTCOME = "expected_outcome"
    WORK_PRODUCT = "work_product"
    EVIDENCE_SOURCE = "evidence_source"    # document, dataset, link or conversation turn
    STATEMENT = "statement"                # the one canonical sentence for a repeated claim
    REGULATED_MATTER = "regulated_matter"
    SPECIALIST_ASSIGNMENT = "specialist_assignment"
    CHARTER = "charter"


ID_PREFIX: Mapping[Kind, str] = {
    Kind.BUSINESS_CONTEXT: "BCX", Kind.DECISION: "DEC", Kind.DECISION_OWNER: "DOW", Kind.STAKEHOLDER: "STK",
    Kind.OBJECTIVE: "OBJ", Kind.SUCCESS_CRITERION: "SUC", Kind.CONSTRAINT: "CST", Kind.DEADLINE: "DDL",
    Kind.MEASURE: "MEA", Kind.FACT: "FCT", Kind.ASSUMPTION: "ASM", Kind.CONFLICT: "CFL", Kind.QUESTION: "QST",
    Kind.ISSUE: "ISS", Kind.HYPOTHESIS: "HYP", Kind.ANALYSIS: "ANA", Kind.OPTION: "OPT",
    Kind.EVALUATION_CRITERION: "CRI", Kind.TRADE_OFF: "TRD", Kind.RECOMMENDATION: "REC", Kind.CAPABILITY: "CAP",
    Kind.PROCESS_STEP: "PST", Kind.WORKSTREAM: "WKS", Kind.INITIATIVE: "INI", Kind.ACTION: "ACT",
    Kind.MILESTONE: "MIL", Kind.DEPENDENCY: "DEP", Kind.OWNER: "OWN", Kind.COST: "COS", Kind.BENEFIT: "BEN",
    Kind.RISK: "RSK", Kind.CONTROL: "CTL", Kind.GOVERNANCE: "GOV", Kind.DECISION_REQUIRED: "DRQ",
    Kind.EXPECTED_OUTCOME: "EXO", Kind.WORK_PRODUCT: "WPR", Kind.EVIDENCE_SOURCE: "EVI", Kind.STATEMENT: "STA",
    Kind.REGULATED_MATTER: "REG", Kind.SPECIALIST_ASSIGNMENT: "SPE", Kind.CHARTER: "CHA",
}
assert set(ID_PREFIX) == set(Kind) and len(set(ID_PREFIX.values())) == len(Kind), "one unique id prefix per kind"


class FactBasis(str, Enum):
    CLIENT_STATED = "client_stated"             # the client's exact words, from a conversation turn
    DOCUMENT_EXTRACTED = "document_extracted"   # a model read it; the quote is NOT yet verified in the text
    DOCUMENT_VERIFIED = "document_verified"     # the locator quote is a verbatim substring of the hashed document
    EXTERNAL_SOURCED = "external_sourced"
    CALCULATED = "calculated"
    INFERRED = "inferred"


class RecordClass(str, Enum):
    """What a document IS decides how much of the current state it owns."""
    SYSTEM_OF_RECORD = "system_of_record"
    MANAGEMENT_REPORT = "management_report"
    CORRESPONDENCE = "correspondence"
    THIRD_PARTY_SUMMARY = "third_party_summary"
    OPINION = "opinion"
    UNKNOWN = "unknown"


# Precedence among sources of ONE current-state fact, highest first. Equal rank
# never resolves automatically; a strictly higher rank resolves visibly, and only
# when the winning document's record class was confirmed by the client (MF2.3).
CURRENT_STATE_PRECEDENCE: tuple[str, ...] = (
    "document_verified:system_of_record",
    "document_verified:management_report",
    "document_verified:correspondence",
    "client_stated",
    "document_verified:third_party_summary",
    "document_verified:opinion",
    "inferred",
)


class Actor(str, Enum):
    CLIENT = "client"
    PARTNER = "partner"                      # the one visible engagement partner (model-assisted)
    METHOD = "method"                        # a DETERMINISTIC / CALCULATION method run by the partner
    SPECIALIST = "specialist"                # a RESEARCH / MODEL_ASSISTED method run under an Assignment
    CALCULATOR = "calculator"                # the deterministic arithmetic engine; never a model
    DOCUMENT = "document"                    # a verified record
    EXTERNAL_SOURCE = "external_source"
    QUALIFIED_PROFESSIONAL = "qualified_professional"
    DECISION_OWNER = "decision_owner"
    LEGACY_R30 = "legacy_r30"                # the technology pipeline behind the typed adapter
    SYSTEM = "system"


class Authority(str, Enum):
    CLIENT = "client"                        # preferences: objectives, priorities, constraints, risk tolerance
    CLIENT_STATED = "client_stated"          # the client's recollection of a current-state fact (MF2.1 / S8)
    VERIFIED_RECORD = "verified_record"
    CITED_SOURCE = "cited_source"
    DETERMINISTIC_ENGINE = "deterministic_engine"
    CONSULTANT = "consultant"
    QUALIFIED_PROFESSIONAL = "qualified_professional"
    DECISION_OWNER = "decision_owner"
    PARTNER = "partner"                      # process records: charters, questions, assignments, statements


class InfoType(str, Enum):
    CLIENT_PREFERENCE = "client_preference"
    CLIENT_RECOLLECTION = "client_recollection"      # a client_stated current-state fact
    CURRENT_STATE_FACT = "current_state_fact"        # document-verified / extracted / inferred current state
    EXTERNAL_FACT = "external_fact"
    ARITHMETIC = "arithmetic"
    CONSULTANT_JUDGEMENT = "consultant_judgement"
    LICENSED_INTERPRETATION = "licensed_interpretation"
    MATERIAL_TRADE_OFF = "material_trade_off"
    PROCESS_RECORD = "process_record"


class Status(str, Enum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    APPROVED = "approved"        # assumptions and recommendations: the owning authority accepted them
    ROUTED = "routed"            # regulated matters: handed to a qualified adviser, never answered here
    OPEN = "open"                # questions, conflicts, decisions required
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


TERMINAL_STATUSES: frozenset[Status] = frozenset({Status.SUPERSEDED, Status.REJECTED, Status.WITHDRAWN})


class RelationToCentralDecision(str, Enum):
    DEFINES = "defines"
    CONSTRAINS = "constrains"
    RESOLVES = "resolves"
    EVIDENCES = "evidences"
    INFORMS = "informs"
    DEPENDS_ON = "depends_on"
    UNRELATED = "unrelated"
    UNKNOWN = "unknown"


# sensitivity of a question to the decision, by the relation of the issue node it serves
SENSITIVITY: Mapping[RelationToCentralDecision, float] = {
    RelationToCentralDecision.DEFINES: 1.0, RelationToCentralDecision.RESOLVES: 1.0,
    RelationToCentralDecision.CONSTRAINS: 0.6, RelationToCentralDecision.EVIDENCES: 0.6,
    RelationToCentralDecision.INFORMS: 0.3, RelationToCentralDecision.DEPENDS_ON: 0.3,
    RelationToCentralDecision.UNRELATED: 0.0, RelationToCentralDecision.UNKNOWN: 0.0,
}


class EffortClass(str, Enum):
    OFFHAND = "offhand"          # the client knows it
    LOOKUP = "lookup"            # someone has to look it up
    DOCUMENT = "document"        # a document or dataset must be produced
    THIRD_PARTY = "third_party"  # a counterparty or adviser must be asked


EFFORT_WEIGHT: Mapping[EffortClass, float] = {
    EffortClass.OFFHAND: 1.0, EffortClass.LOOKUP: 2.0, EffortClass.DOCUMENT: 3.0, EffortClass.THIRD_PARTY: 4.0,
}


class FillStrategy(str, Enum):
    """How a typed gap is closed. Derived mechanically from the InputSpec that
    is unmet (S1 graft): never chosen by a model, never marked by hand."""
    ASK_CLIENT = "ask_client"
    REQUEST_DOCUMENT = "request_document"
    SPAWN_SPECIALIST = "spawn_specialist"
    RECORD_UNKNOWN = "record_unknown"


class Interrogative(str, Enum):
    WHY = "why"
    WHAT = "what"
    HOW_MUCH = "how_much"
    WHICH = "which"
    WHETHER = "whether"
    HOW = "how"
    WHEN = "when"
    WHO = "who"


class CapabilityClass(str, Enum):
    """The class of thing an issue asks to be designed. Structural, not an engagement type."""
    SOFTWARE_SYSTEM = "software_system"
    DATA_AND_INTEGRATION = "data_and_integration"
    PROCESS = "process"
    PEOPLE_AND_ORGANISATION = "people_and_organisation"
    COMMERCIAL = "commercial"
    PHYSICAL_ASSET = "physical_asset"
    FINANCIAL = "financial"
    GOVERNANCE_AND_CONTROL = "governance_and_control"
    EXTERNAL_RELATIONSHIP = "external_relationship"


class RegulatedDomain(str, Enum):
    """Licensed professions, not engagement types."""
    LEGAL_CONTRACT = "legal_contract"
    EMPLOYMENT_LAW = "employment_law"
    TAX = "tax"
    FINANCIAL_REGULATION = "financial_regulation"
    MEDICAL = "medical"
    DATA_PROTECTION = "data_protection"
    ENVIRONMENTAL_PERMITTING = "environmental_permitting"
    LICENSING_AND_CERTIFICATION = "licensing_and_certification"
    COMPANY_LAW_AND_GOVERNANCE = "company_law_and_governance"
    COMPETITION_AND_TRADE = "competition_and_trade"


class UnitFamily(str, Enum):
    MONEY = "money"
    COUNT = "count"
    TIME = "time"
    RATE = "rate"          # dimensionless ratio or percentage
    CAPACITY = "capacity"  # units per period
    DISTANCE_AREA_MASS = "distance_area_mass"
    OTHER = "other"


class ConflictKind(str, Enum):
    """Typed reconciliation (S7 graft): a definition difference is a question to
    pin, a value conflict is a conflict; neither is ever averaged."""
    VALUE = "value"
    DEFINITION = "definition"
    OBJECTIVE_VS_FEASIBILITY = "objective_vs_feasibility"
    SPECIALIST_DISAGREEMENT = "specialist_disagreement"
    CLIENT_VS_RECORD = "client_vs_record"
    ASSUMPTION_VS_EVIDENCE = "assumption_vs_evidence"


class ExecutionType(str, Enum):
    DETERMINISTIC = "deterministic"
    RESEARCH = "research"
    CALCULATION = "calculation"
    MODEL_ASSISTED = "model_assisted"


# execution types that run under a scoped SpecialistAssignment, never directly (MF1.2)
ASSIGNMENT_EXECUTION: frozenset[ExecutionType] = frozenset({ExecutionType.RESEARCH, ExecutionType.MODEL_ASSISTED})
FREE_EXECUTION: frozenset[ExecutionType] = frozenset({ExecutionType.DETERMINISTIC, ExecutionType.CALCULATION})


class DecisionRole(str, Enum):
    CENTRAL = "central"
    SUBORDINATE = "subordinate"
    STATED_REQUEST = "stated_request"


class ApprovalState(str, Enum):
    UNAPPROVED = "unapproved"
    APPROVED = "approved"
    REJECTED = "rejected"


class StepPerspective(str, Enum):
    INTERNAL = "internal"
    CUSTOMER = "customer"


class DeadlineOrigin(str, Enum):
    CONTRACT = "contract"
    REGULATOR = "regulator"
    BOARD = "board"
    SELF_IMPOSED = "self_imposed"
    UNKNOWN = "unknown"


class Horizon(str, Enum):
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"


class GapState(str, Enum):
    MISSING = "missing"
    PARTIAL = "partial"
    PRESENT_UNUSED = "present_unused"
    PRESENT = "present"


class Feasibility(str, Enum):
    UNTESTED = "untested"
    FEASIBLE = "feasible"
    INFEASIBLE_ON_FACTS = "infeasible_on_facts"


class AnalysisState(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    DONE = "done"
    BLOCKED = "blocked"


class SourceKind(str, Enum):
    DOCUMENT = "document"
    DATASET = "dataset"
    LINK = "link"
    CONVERSATION_TURN = "conversation_turn"


class Phase(str, Enum):
    OPENING = "opening"
    DISCOVERY = "discovery"
    CHARTER_PROPOSED = "charter_proposed"
    CHARTER_CONFIRMED = "charter_confirmed"
    ANALYSIS = "analysis"
    PAUSED_FOR_DISCOVERY = "paused_for_discovery"
    SYNTHESIS = "synthesis"
    DELIVERABLES = "deliverables"
    EXECUTION_SUPPORT = "execution_support"


PHASE_TRANSITIONS: Mapping[Phase, frozenset[Phase]] = {
    Phase.OPENING: frozenset({Phase.DISCOVERY}),
    Phase.DISCOVERY: frozenset({Phase.CHARTER_PROPOSED}),
    Phase.CHARTER_PROPOSED: frozenset({Phase.DISCOVERY, Phase.CHARTER_CONFIRMED}),
    Phase.CHARTER_CONFIRMED: frozenset({Phase.ANALYSIS}),
    Phase.ANALYSIS: frozenset({Phase.PAUSED_FOR_DISCOVERY, Phase.SYNTHESIS, Phase.CHARTER_PROPOSED}),
    Phase.PAUSED_FOR_DISCOVERY: frozenset({Phase.ANALYSIS}),
    Phase.SYNTHESIS: frozenset({Phase.DELIVERABLES, Phase.PAUSED_FOR_DISCOVERY}),
    Phase.DELIVERABLES: frozenset({Phase.EXECUTION_SUPPORT, Phase.SYNTHESIS}),
    Phase.EXECUTION_SUPPORT: frozenset({Phase.ANALYSIS}),
}


class Severity(str, Enum):
    HIGH = "high"
    LOW = "low"


# =============================================================================
# 2. Quantities: exact, dimensioned, never coined
# =============================================================================

def _decimal(v: Any) -> Decimal:
    """A quantity value is exact. A float is refused - its printed form is not
    its value, and the recompute law (L7) demands equality, not closeness."""
    if isinstance(v, bool):
        raise TypeError("a quantity value cannot be a bool")
    if isinstance(v, Decimal):
        return v
    if isinstance(v, int):
        return Decimal(v)
    if isinstance(v, str):
        try:
            return Decimal(v)
        except InvalidOperation as exc:
            raise ValueError(f"not a decimal literal: {v!r}") from exc
    if isinstance(v, float):
        raise TypeError("a quantity value must be Decimal/int/str, never float")
    raise TypeError(f"unsupported quantity value {type(v).__name__}")


@dataclass(frozen=True)
class Dimensions:
    """The population and basis a number covers. None means UNKNOWN (never a
    default); pinned_for() tests `is not None`, so absence stays absence."""
    currency: str | None = None
    period: str | None = None          # "FY25", "2026-06", "trailing_12m"
    period_basis: str | None = None    # "year" | "month" | "week" | "day" | "point_in_time"
    scope: str | None = None           # "NL entity, permanent staff"
    as_of: str | None = None           # ISO date the value is true at
    definition: str | None = None      # "heads, not FTE, incl. agency"

    DIMENSION_NAMES: ClassVar[tuple[str, ...]] = ("currency", "period", "period_basis", "scope", "as_of", "definition")

    def pinned_for(self, names: Iterable[str]) -> bool:
        return all(getattr(self, n) is not None for n in names)

    def unpinned(self) -> tuple[str, ...]:
        return tuple(n for n in self.DIMENSION_NAMES if getattr(self, n) is None)


@dataclass(frozen=True)
class Quantity:
    value: Decimal
    unit: str                              # "EUR", "heads", "FTE", "%", "days", "tonnes"
    unit_family: UnitFamily
    dimensions: Dimensions = field(default_factory=Dimensions)
    precision: int = 2                     # decimal places the value is quantised to

    def __post_init__(self):
        object.__setattr__(self, "value", _decimal(self.value))
        if not isinstance(self.unit_family, UnitFamily):
            raise TypeError("unit_family must be a UnitFamily")
        if not self.unit:
            raise ValueError("a quantity carries its unit")


# =============================================================================
# 3. The shared envelope
# =============================================================================

@dataclass(frozen=True)
class Provenance:
    actor: Actor
    actor_ref: str                          # "turn:12" | "doc:EVI-3" | "method:root_cause@1" | "specialist:SPE-2" | "r30:request:57:claim:MK-1"
    derived_from: tuple[str, ...] = ()      # entity ids this rests on
    source_locator: str | None = None       # exact quote, page/cell/line, url fragment
    model_call_id: str | None = None        # engine_model_calls.call_id; None whenever no model was involved
    recorded_at: str = ""                   # ISO-8601, set by the registry clock, never by the producer; excluded from hashes


@dataclass(frozen=True)
class Confidence:
    """None means unknown. It is never coerced to 0; a ranking that needs a
    number uses a declared prior (UNKNOWN_CONFIDENCE_PRIOR) and leaves the
    stored value None."""
    value: float | None
    basis: str = "unknown"                  # "stated" | "verified" | "computed" | "model_estimate" | "unknown"

    def __post_init__(self):
        if self.value is not None and not 0.0 <= float(self.value) <= 1.0:
            raise ValueError("confidence outside [0,1]")


UNKNOWN_CONFIDENCE_PRIOR = 0.25


@dataclass(frozen=True)
class Relevance:
    decision_id: str | None                 # the DECISION this bears on (None == not yet attached)
    weight: float = 0.0                     # 0..1, how much this can move that decision
    rationale: str = ""

    def __post_init__(self):
        if not 0.0 <= float(self.weight) <= 1.0:
            raise ValueError("relevance weight outside [0,1]")


# =============================================================================
# 4. Typed payloads (frozen dataclasses; enum-typed fields are checked at write)
# =============================================================================

@dataclass(frozen=True)
class BusinessContextPayload:
    text: str
    aspect: str = "other"                  # "what_it_does" | "size" | "structure" | "market" | "history" | "other"


@dataclass(frozen=True)
class DecisionPayload:
    statement: str
    role: DecisionRole
    origin: str = "client_request"         # "client_request" | "partner_inferred" | "method:<id>" | "charter_amendment"
    symptom_of: str | None = None          # DECISION id this request is a symptom of, when detected
    option_ids: tuple[str, ...] = ()
    owner_id: str | None = None


@dataclass(frozen=True)
class DecisionOwnerPayload:
    name: str
    role: str
    resolves: tuple[str, ...] = ()


@dataclass(frozen=True)
class StakeholderPayload:
    name: str
    role: str
    interest: str = ""
    influence: str = "unknown"             # "high" | "medium" | "low" | "unknown"


@dataclass(frozen=True)
class ObjectivePayload:
    text: str
    priority: int | None = None
    measure_id: str | None = None
    target: Quantity | None = None
    feasibility: Feasibility = Feasibility.UNTESTED


@dataclass(frozen=True)
class SuccessCriterionPayload:
    text: str
    measure_id: str | None = None
    target: Quantity | None = None
    baseline: Quantity | None = None
    baseline_source: str = "unknown"       # "client_fact" | "record" | "measure_first" | "unknown"


@dataclass(frozen=True)
class ConstraintPayload:
    text: str
    kind: str = "other"                    # "financial" | "time" | "legal" | "people" | "physical" | "policy" | "other"
    hard: bool = False


@dataclass(frozen=True)
class DeadlinePayload:
    text: str
    date: str | None = None
    what_happens: str = ""
    origin: DeadlineOrigin = DeadlineOrigin.UNKNOWN
    starts_clock: bool = False             # True: the date STARTS a period (a completion, a go-live), not ends one


@dataclass(frozen=True)
class MeasurePayload:
    name: str                              # display name; free text
    unit_family: UnitFamily
    definition: str = ""
    confirmed_by_client: bool = False      # the client agreed two wordings mean this one measure


@dataclass(frozen=True)
class FactPayload:
    statement: str                         # the fact in the source's own words (client facts remain exact)
    basis: FactBasis
    measure_id: str | None = None          # MEASURE entity id; reconciliation joins on this, never on text (MF1.6)
    quantity: Quantity | None = None
    record_class: RecordClass | None = None
    formula: str | None = None             # basis == CALCULATED: the arithmetic over input entity ids
    inputs: tuple[str, ...] = ()
    topic: str | None = None


@dataclass(frozen=True)
class AssumptionPayload:
    statement: str
    rationale: str = ""
    quantity: Quantity | None = None
    approval: ApprovalState = ApprovalState.UNAPPROVED
    used_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConflictConclusion:
    entity_id: str
    statement: str
    evidence: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    consequence: str = ""


@dataclass(frozen=True)
class ConflictPayload:
    """The typed conflict of spec section 5. `material` is a rendering snapshot;
    the gate recomputes materiality from the live support graph (MF2.4)."""
    kind: ConflictKind
    subject_id: str                        # MEASURE / ISSUE / DECISION entity id the conflict is about
    conclusions: tuple[ConflictConclusion, ...]
    relation_to_central_decision: RelationToCentralDecision
    authority_required: Authority
    material: bool = False
    recommended_resolution: str | None = None       # entity id of the recommended winner, or None
    recommendation_basis: str | None = None         # "CURRENT_STATE_PRECEDENCE: system_of_record > client_stated"
    resolution_chosen: str | None = None
    resolution_by: str | None = None                # actor_ref of the resolver
    resolution_rationale: str = ""


@dataclass(frozen=True)
class AsksFor:
    kind: Kind
    filter: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QuestionPayload:
    text: str
    asks_for: tuple[AsksFor, ...] = ()
    issue_ids: tuple[str, ...] = ()
    why: str = ""                          # rendered from the issue/decision it informs
    effort: EffortClass = EffortClass.OFFHAND
    strategy: FillStrategy = FillStrategy.ASK_CLIENT
    material: bool = False                 # blocks FINAL while open
    value: float | None = None
    answer_entity_ids: tuple[str, ...] = ()
    unknown: bool = False                  # the client said they do not know: never re-asked


@dataclass(frozen=True)
class IssuePayload:
    text: str
    interrogative: Interrogative
    target_kind: Kind
    parent_id: str | None = None
    quantified: bool = False
    comparative: bool = False
    causal: bool = False
    temporal: bool = False
    capability_class: CapabilityClass | None = None
    weight_to_parent: float = 1.0          # edge weight used by path_impact (S2 graft)
    decisive_for: tuple[str, ...] = ()
    evidence_needed: tuple[AsksFor, ...] = ()
    answered_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class HypothesisPayload:
    text: str
    issue_id: str
    causes: tuple[str, ...] = ()
    predicts: tuple[str, ...] = ()
    verdict: str = "untested"              # "supported" | "refuted" | "untested"


@dataclass(frozen=True)
class AnalysisPayload:
    method_id: str
    method_version: int
    issue_ids: tuple[str, ...]
    state: AnalysisState = AnalysisState.PLANNED
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    assignment_id: str | None = None
    blocked_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class OptionPayload:
    text: str
    decision_id: str
    mechanism: str = ""
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluationCriterionPayload:
    text: str
    decision_id: str
    weight: float | None = None
    weight_set_by: Authority | None = None # CLIENT weights rank; CONSULTANT weights only list


@dataclass(frozen=True)
class Score:
    option_id: str
    criterion_id: str
    score: Decimal
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class TradeOffPayload:
    decision_id: str
    option_ids: tuple[str, ...]
    gives_up: str = ""
    gains: str = ""
    scores: tuple[Score, ...] = ()
    material: bool = False


@dataclass(frozen=True)
class RecommendationPayload:
    statement: str
    decision_id: str
    option_id: str | None = None
    supports: tuple[str, ...] = ()         # FACT confirmed / ASSUMPTION approved / calculated FACT; never empty at APPROVED
    conditional_on: tuple[str, ...] = ()   # open question ids: renders as conditional while any is open
    licensed_interpretation: bool = False  # advice a licensed professional must give; blocks until ROUTED


@dataclass(frozen=True)
class CapabilityPayload:
    text: str
    capability_class: CapabilityClass
    gap: GapState = GapState.MISSING
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProcessStepPayload:
    text: str
    perspective: StepPerspective
    sequence: int
    actor_id: str | None = None
    system_ids: tuple[str, ...] = ()
    pain_point: bool = False
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkstreamPayload:
    name: str
    purpose: str = ""
    capability_classes: tuple[CapabilityClass, ...] = ()
    initiative_ids: tuple[str, ...] = ()
    owner_id: str | None = None
    legacy_request_id: int | None = None   # set when the r30 adapter delivered it


@dataclass(frozen=True)
class InitiativePayload:
    name: str
    workstream_id: str
    capability_class: CapabilityClass      # MF1.3
    purpose: str = ""
    action_ids: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionPayload:
    text: str
    capability_class: CapabilityClass      # MF1.3: process/people predicates read this, never text
    horizon: Horizon = Horizon.WEEKS       # never a calendar date unless a DEADLINE owns it
    initiative_id: str | None = None
    owner_id: str | None = None
    sequence: int | None = None
    depends_on: tuple[str, ...] = ()
    done_when: tuple[str, ...] = ()


@dataclass(frozen=True)
class MilestonePayload:
    text: str
    horizon: Horizon = Horizon.MONTHS
    gate: bool = False
    criteria: tuple[str, ...] = ()
    deadline_id: str | None = None


@dataclass(frozen=True)
class DependencyPayload:
    from_id: str
    to_id: str
    kind: str = "requires"                 # "requires" | "informs" | "blocks"


@dataclass(frozen=True)
class OwnerPayload:
    name: str
    role: str
    owns: tuple[str, ...] = ()
    reports_to: str | None = None          # OWNER id; an org structure exists when set


@dataclass(frozen=True)
class CostPayload:
    text: str
    basis: str = "unknown"                 # "client_fact" | "quote" | "calculated" | "assumption" | "unknown"
    quantity: Quantity | None = None
    for_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class BenefitPayload:
    text: str
    basis: str = "unknown"
    quantity: Quantity | None = None
    for_ids: tuple[str, ...] = ()
    conditional_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskPayload:
    text: str
    likelihood: str = "unknown"            # "high" | "medium" | "low" | "unknown"
    impact: str = "unknown"
    who_feels_it: str = ""
    control_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ControlPayload:
    text: str
    owner_id: str | None = None
    risk_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RaciRow:
    action_id: str
    responsible: str
    accountable: str
    consulted: tuple[str, ...] = ()
    informed: tuple[str, ...] = ()


@dataclass(frozen=True)
class GovernancePayload:
    text: str
    forum: str = ""
    cadence: str = ""
    decides: tuple[str, ...] = ()
    raci: tuple[RaciRow, ...] = ()


@dataclass(frozen=True)
class DecisionRequiredPayload:
    text: str
    from_authority: Authority
    decision_id: str | None = None
    options: tuple[str, ...] = ()
    by_when: str | None = None
    chosen: str | None = None


@dataclass(frozen=True)
class ExpectedOutcomePayload:
    text: str
    measure_id: str | None = None
    quantity: Quantity | None = None
    basis: str = "unknown"                 # "calculated" | "assumption" | "unknown"
    supports: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkProductPayload:
    product_id: str
    title: str
    planned_because: str                   # the structural verdict, rendered from counts
    section_ids: tuple[str, ...] = ()      # sections planned (section-level applicability, MF1.1)
    consumes: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceSourcePayload:
    name: str
    source_kind: SourceKind
    record_class: RecordClass = RecordClass.UNKNOWN
    record_class_confirmed_by_client: bool = False
    produced_by: str | None = None
    sha256: str | None = None
    byte_size: int | None = None
    received_at: str = ""
    text: str | None = None                # conversation turns carry their text; documents use text_ref
    text_ref: str | None = None


@dataclass(frozen=True)
class StatementPayload:
    text: str                              # produced by statement_text(entity), never by a model
    of_entity_id: str
    token: str                             # "[[STMT:STA-12]]"
    rendered_in: tuple[str, ...] = ()


CANNOT_ANSWER_STATEMENT = ("This matter requires a qualified professional. The engine has identified it and "
                           "routed it for qualified review; it does not state an interpretation.")


@dataclass(frozen=True)
class RegulatedMatterPayload:
    text: str
    domain: RegulatedDomain
    adviser_class: str
    why_regulated: str = ""
    touches: tuple[str, ...] = ()
    withheld_interpretation: str = ""      # the exact interpretation the engine refused to state (S11 graft)
    cannot_answer_statement: str = CANNOT_ANSWER_STATEMENT


@dataclass(frozen=True)
class AssumptionGrant:
    kind: Kind
    unit_family: UnitFamily | None = None
    must_cite: bool = True


@dataclass(frozen=True)
class Budget:
    max_model_calls: int
    max_tokens: int
    max_deltas: int


@dataclass(frozen=True)
class SpecialistAssignmentPayload:
    question: str
    issue_id: str
    method_id: str
    permitted_evidence: tuple[str, ...]
    output_kinds: tuple[Kind, ...]
    allowed_assumptions: tuple[AssumptionGrant, ...] = ()
    forbidden_decisions: tuple[str, ...] = ()
    validation: tuple[str, ...] = ()
    budget: Budget = Budget(2, 8000, 60)
    outcome: str | None = None             # "done" | "blocked" | "rejected"
    rejection_rule: str | None = None      # "S3" etc. when rejected


@dataclass(frozen=True)
class CharterPayload:
    """Fourteen lists of entity ids assembled by registry queries (spec section 2)."""
    situation: tuple[str, ...] = ()
    central_decision: str | None = None
    decision_owner: str | None = None
    objectives: tuple[str, ...] = ()
    scope: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    evidence_available: tuple[str, ...] = ()
    evidence_required: tuple[str, ...] = ()
    key_questions: tuple[str, ...] = ()
    initial_hypotheses: tuple[str, ...] = ()
    planned_analyses: tuple[str, ...] = ()
    proposed_work_products: tuple[str, ...] = ()
    open_decisions: tuple[str, ...] = ()
    amends: str | None = None


PAYLOAD_TYPES: Mapping[Kind, type] = {
    Kind.BUSINESS_CONTEXT: BusinessContextPayload, Kind.DECISION: DecisionPayload,
    Kind.DECISION_OWNER: DecisionOwnerPayload, Kind.STAKEHOLDER: StakeholderPayload,
    Kind.OBJECTIVE: ObjectivePayload, Kind.SUCCESS_CRITERION: SuccessCriterionPayload,
    Kind.CONSTRAINT: ConstraintPayload, Kind.DEADLINE: DeadlinePayload, Kind.MEASURE: MeasurePayload,
    Kind.FACT: FactPayload, Kind.ASSUMPTION: AssumptionPayload, Kind.CONFLICT: ConflictPayload,
    Kind.QUESTION: QuestionPayload, Kind.ISSUE: IssuePayload, Kind.HYPOTHESIS: HypothesisPayload,
    Kind.ANALYSIS: AnalysisPayload, Kind.OPTION: OptionPayload,
    Kind.EVALUATION_CRITERION: EvaluationCriterionPayload, Kind.TRADE_OFF: TradeOffPayload,
    Kind.RECOMMENDATION: RecommendationPayload, Kind.CAPABILITY: CapabilityPayload,
    Kind.PROCESS_STEP: ProcessStepPayload, Kind.WORKSTREAM: WorkstreamPayload,
    Kind.INITIATIVE: InitiativePayload, Kind.ACTION: ActionPayload, Kind.MILESTONE: MilestonePayload,
    Kind.DEPENDENCY: DependencyPayload, Kind.OWNER: OwnerPayload, Kind.COST: CostPayload,
    Kind.BENEFIT: BenefitPayload, Kind.RISK: RiskPayload, Kind.CONTROL: ControlPayload,
    Kind.GOVERNANCE: GovernancePayload, Kind.DECISION_REQUIRED: DecisionRequiredPayload,
    Kind.EXPECTED_OUTCOME: ExpectedOutcomePayload, Kind.WORK_PRODUCT: WorkProductPayload,
    Kind.EVIDENCE_SOURCE: EvidenceSourcePayload, Kind.STATEMENT: StatementPayload,
    Kind.REGULATED_MATTER: RegulatedMatterPayload,
    Kind.SPECIALIST_ASSIGNMENT: SpecialistAssignmentPayload, Kind.CHARTER: CharterPayload,
}
assert set(PAYLOAD_TYPES) == set(Kind), "every kind has a typed payload"

# Free-text payload fields. The vocabulary-blind tests scramble exactly these;
# no InputSpec filter, no Predicate and no selector may read them.
TEXT_FIELDS: frozenset[str] = frozenset({
    "text", "statement", "name", "purpose", "rationale", "why", "mechanism", "gives_up", "gains",
    "interest", "what_happens", "topic", "definition", "subject", "aspect", "who_feels_it", "forum",
    "cadence", "why_regulated", "question", "title", "planned_because", "adviser_class",
    "withheld_interpretation", "consequence", "resolution_rationale",
})

# Fields an InputSpec / Predicate / query filter may read: closed enums, booleans,
# small ints and derived structural flags.
FILTERABLE_FIELDS: frozenset[str] = frozenset({
    "basis", "record_class", "approval", "role", "interrogative", "target_kind", "quantified",
    "comparative", "causal", "temporal", "capability_class", "unit_family", "has_quantity",
    "material", "gap", "domain", "state", "feasibility", "hard", "gate", "kind", "perspective",
    "origin", "starts_clock", "horizon", "source_kind", "record_class_confirmed_by_client",
    "licensed_interpretation", "strategy", "effort", "verdict", "from_authority", "weight_set_by",
    "pain_point", "has_reports_to", "has_raci", "has_date", "has_measure", "has_formula", "unknown",
    "confirmed_by_client", "has_legacy_request", "authority_required", "conflict_kind", "has_deadline",
})
assert not (FILTERABLE_FIELDS & TEXT_FIELDS), "a filterable field is never a text field"


def _norm(v: Any) -> Any:
    if isinstance(v, Enum):
        return v.value
    return v


def payload_field(payload: Any, key: str) -> Any:
    """Structural read of a payload field by name. Derived flags are computed
    here so that predicates read one closed vocabulary."""
    if key == "has_quantity":
        return getattr(payload, "quantity", None) is not None
    if key == "unit_family":
        q = getattr(payload, "quantity", None)
        if q is not None:
            return q.unit_family.value
        uf = getattr(payload, "unit_family", None)
        return _norm(uf)
    if key == "has_reports_to":
        return getattr(payload, "reports_to", None) is not None
    if key == "has_raci":
        return bool(getattr(payload, "raci", ()))
    if key == "has_date":
        return getattr(payload, "date", None) is not None
    if key == "has_measure":
        return getattr(payload, "measure_id", None) is not None
    if key == "has_formula":
        return bool(getattr(payload, "formula", None))
    if key == "has_legacy_request":
        return getattr(payload, "legacy_request_id", None) is not None
    if key == "has_deadline":
        return getattr(payload, "deadline_id", None) is not None
    if key == "conflict_kind":
        return _norm(getattr(payload, "kind", None))
    return _norm(getattr(payload, key, None))


def _enum_of(hint: Any) -> type[Enum] | None:
    if isinstance(hint, type) and issubclass(hint, Enum):
        return hint
    if get_origin(hint) in (Union, _types.UnionType):
        for a in get_args(hint):
            if isinstance(a, type) and issubclass(a, Enum):
                return a
    return None


_HINTS: dict[type, dict[str, Any]] = {}


def _hints(cls: type) -> dict[str, Any]:
    if cls not in _HINTS:
        _HINTS[cls] = get_type_hints(cls, globalns=globals())
    return _HINTS[cls]


def validate_payload(kind: Kind, payload: Any) -> None:
    """A payload is the frozen dataclass registered for its kind, and every
    enum-typed field holds a member of that enum (not a string)."""
    cls = PAYLOAD_TYPES[kind]
    if not isinstance(payload, cls):
        raise TypeError(f"{kind.value} payload must be {cls.__name__}, got {type(payload).__name__}")
    for f in fields(cls):
        enum_cls = _enum_of(_hints(cls).get(f.name))
        if enum_cls is None:
            continue
        v = getattr(payload, f.name)
        if v is not None and not isinstance(v, enum_cls):
            raise TypeError(f"{cls.__name__}.{f.name} must be {enum_cls.__name__}, got {v!r}")



# =============================================================================
# 5. Information type (ownership tables and may_advance: app/engine/authority.py)
# =============================================================================

def info_type_of(kind: Kind, payload: Any) -> InfoType:
    """Which class of source owns an entity is a function of what kind of
    information it is - never of who happened to produce it."""
    if kind in (Kind.OBJECTIVE, Kind.SUCCESS_CRITERION, Kind.CONSTRAINT, Kind.DECISION_OWNER,
                Kind.DEADLINE, Kind.STAKEHOLDER, Kind.BUSINESS_CONTEXT, Kind.MEASURE):
        return InfoType.CLIENT_PREFERENCE
    if kind == Kind.FACT:
        basis = payload.basis
        if basis == FactBasis.CALCULATED:
            return InfoType.ARITHMETIC
        if basis == FactBasis.EXTERNAL_SOURCED:
            return InfoType.EXTERNAL_FACT
        if basis == FactBasis.CLIENT_STATED:
            return InfoType.CLIENT_RECOLLECTION
        return InfoType.CURRENT_STATE_FACT
    if kind == Kind.REGULATED_MATTER:
        return InfoType.LICENSED_INTERPRETATION
    if kind == Kind.RECOMMENDATION and payload.licensed_interpretation is True:
        return InfoType.LICENSED_INTERPRETATION
    if kind == Kind.TRADE_OFF and payload.material is True:
        return InfoType.MATERIAL_TRADE_OFF
    if kind in (Kind.DECISION, Kind.HYPOTHESIS, Kind.ANALYSIS, Kind.OPTION, Kind.EVALUATION_CRITERION,
                Kind.TRADE_OFF, Kind.RECOMMENDATION, Kind.CAPABILITY, Kind.PROCESS_STEP, Kind.WORKSTREAM,
                Kind.INITIATIVE, Kind.ACTION, Kind.MILESTONE, Kind.DEPENDENCY, Kind.OWNER, Kind.COST,
                Kind.BENEFIT, Kind.RISK, Kind.CONTROL, Kind.GOVERNANCE, Kind.EXPECTED_OUTCOME,
                Kind.ASSUMPTION, Kind.ISSUE, Kind.CONFLICT, Kind.DECISION_REQUIRED):
        return InfoType.CONSULTANT_JUDGEMENT
    return InfoType.PROCESS_RECORD


# =============================================================================
# 6. Entity, deltas, findings
# =============================================================================

def _encode(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _encode(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Decimal):
        return {"$decimal": str(obj)}
    if isinstance(obj, (list, tuple)):
        return [_encode(x) for x in obj]
    if isinstance(obj, Mapping):
        return {str(k): _encode(v) for k, v in obj.items()}
    return obj


def _decode(hint: Any, data: Any) -> Any:
    if data is None:
        return None
    origin = get_origin(hint)
    if origin in (Union, _types.UnionType):
        for a in get_args(hint):
            if a is type(None):
                continue
            return _decode(a, data)
    if isinstance(hint, type) and issubclass(hint, Enum):
        return hint(data)
    if hint is Decimal or (isinstance(data, dict) and "$decimal" in data):
        return Decimal(data["$decimal"]) if isinstance(data, dict) else Decimal(str(data))
    if isinstance(hint, type) and is_dataclass(hint):
        h = _hints(hint)
        return hint(**{f.name: _decode(h[f.name], data.get(f.name)) for f in fields(hint) if f.name in data})
    if origin is tuple:
        args = get_args(hint)
        inner = args[0] if args else Any
        return tuple(_decode(inner, x) for x in data)
    if origin in (Mapping, dict) or hint is Mapping:
        return dict(data)
    return data


@dataclass(frozen=True)
class Entity:
    """One row of the registry. `authority` and `info_type` are derived at write
    time (I7): a producer cannot choose who owns what it wrote."""
    id: str                                 # "<PREFIX>-<n>", stable across versions; "" until the registry assigns it
    kind: Kind
    engagement_id: str
    payload: Any                            # PAYLOAD_TYPES[kind] instance
    provenance: Provenance
    authority: Authority
    info_type: InfoType
    confidence: Confidence
    relevance: Relevance
    relation: RelationToCentralDecision
    status: Status
    version: int = 1
    supersedes: int | None = None           # previous version number when this row supersedes one
    confirmed_by: str | None = None         # actor_ref of the authority that confirmed/approved/resolved
    labels: tuple[str, ...] = ()            # rendering labels: "assumption:unapproved", "superseded_by_record", ...

    def __post_init__(self):
        validate_payload(self.kind, self.payload)
        expected = info_type_of(self.kind, self.payload)
        if self.info_type != expected:
            raise ValueError(f"I7: info_type must be derived ({expected.value}), got {self.info_type.value}")
        # authority.py imports this module at top level; the table is reached
        # at call time so the two halves of the contract stay in one package.
        from app.engine.authority import owner_of
        if self.authority != owner_of(expected):
            raise ValueError(f"I7: authority is derived from information type; {self.authority.value} is not the owner")

    def field(self, key: str) -> Any:
        return payload_field(self.payload, key)

    def to_json(self) -> dict:
        d = _encode(self)
        d["kind"] = self.kind.value
        return d

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> "Entity":
        kind = Kind(d["kind"])
        payload = _decode(PAYLOAD_TYPES[kind], d["payload"])
        return cls(
            id=d["id"], kind=kind, engagement_id=d["engagement_id"], payload=payload,
            provenance=_decode(Provenance, d["provenance"]), authority=Authority(d["authority"]),
            info_type=InfoType(d["info_type"]), confidence=_decode(Confidence, d["confidence"]),
            relevance=_decode(Relevance, d["relevance"]), relation=RelationToCentralDecision(d["relation"]),
            status=Status(d["status"]), version=int(d.get("version", 1)), supersedes=d.get("supersedes"),
            confirmed_by=d.get("confirmed_by"), labels=tuple(d.get("labels") or ()),
        )

    def content_hash(self) -> str:
        """sha256 of the row with recorded_at blanked (MF3.7): identical content
        hashes identically whatever the clock said."""
        body = replace(self, provenance=replace(self.provenance, recorded_at="")).to_json()
        return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def with_status(self, status: Status, by: str | None) -> "Entity":
        return replace(self, status=status, confirmed_by=by)


def make_entity(*, kind: Kind, engagement_id: str, payload: Any, provenance: Provenance,
                confidence: Confidence, relevance: Relevance, relation: RelationToCentralDecision,
                status: Status, entity_id: str = "", labels: tuple[str, ...] = ()) -> Entity:
    """The only constructor producers use: authority and info type are derived."""
    from app.engine.authority import owner_of
    # Checked before info_type_of reads payload fields, so a payload of the
    # wrong class fails with the typed message rather than an AttributeError.
    validate_payload(kind, payload)
    it = info_type_of(kind, payload)
    return Entity(id=entity_id, kind=kind, engagement_id=engagement_id, payload=payload, provenance=provenance,
                  authority=owner_of(it), info_type=it, confidence=confidence, relevance=relevance,
                  relation=relation, status=status, labels=labels)


@dataclass(frozen=True)
class Add:
    entity: Entity


@dataclass(frozen=True)
class Supersede:
    old_id: str
    entity: Entity                          # same id; the registry sets version+1 and supersedes


@dataclass(frozen=True)
class SetStatus:
    entity_id: str
    status: Status
    by: Provenance                          # who asserts the change; the registry checks may_advance
    labels: tuple[str, ...] = ()


EntityDelta = Add | Supersede | SetStatus


class RegistryError(ValueError):
    def __init__(self, invariant: str, message: str):
        super().__init__(f"{invariant}: {message}")
        self.invariant = invariant


@dataclass(frozen=True)
class Finding:
    law: str                     # "L2.unsupported_recommendation", "SPE.admission.S3", "M.root_cause.uncited_cause"
    where: str                   # entity id or "<product>:<section>"
    issue: str
    fix: str
    severity: Severity = Severity.HIGH
    entity_ids: tuple[str, ...] = ()
    blocks_final: bool = True

    def as_dict(self) -> dict:
        d = _encode(self)
        d["source"] = "engine.integrity"
        return d



# =============================================================================
# 16. Bounds (settings names; values live in app/config.py, never fixed counts)
# =============================================================================

BOUNDS: Mapping[str, Any] = {
    "MIN_QUESTIONS_PER_TURN": 1, "MAX_QUESTIONS_PER_TURN": 3, "MIN_QUESTION_VALUE": 0.05,
    "ASK_FLOOR": 0.10, "MAX_FANOUT": 6, "SYMPTOM_MARGIN": 0.25, "CHARTER_MIN_WEIGHT": 0.45,
    "CHARTER_MIN_MARGIN": 0.15, "MAX_DISCOVERY_TURNS": 12, "MAX_ANALYSIS_ROUNDS": 6,
    "MIN_WORK_PRODUCTS": 2, "MAX_WORK_PRODUCTS": 16, "MAX_SPECIALISTS_PER_ROUND": 4,
    "MIN_REVEALED_CHANGERS": 3, "MIN_DISTINCT_DELIVERABLE_SETS": 4, "MIN_DISTINCT_SECTION_SIGNATURES": 8,
    "RENDERED_RESTATEMENT_TOLERANCE": 0.005, "MAX_NARRATIVE_REGENERATIONS": 1,
}



__all__ = [n for n in dir() if not n.startswith("_")]
