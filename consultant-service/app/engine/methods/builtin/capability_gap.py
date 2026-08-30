"""capability_gap - WHAT/HOW on CAPABILITY: name the capabilities the
objectives demand and state, with evidence, how present each one is.

This module also hosts the shared law of the diagnostic method family
(current_state, journey, process_map, root_cause and stakeholder import it).
The component ships exactly one file per method (design 2), so the common
machinery lives in the family's alphabetically first module, which the
registration package imports before every sibling; a separate shared module
would either be discovered as a method module or fall outside the
component's closed file list.

The shared law, in one place so a single deletion breaks every diagnostic
method's tests at once:

* the model sees only registered inputs and the closed list of declared
  output kinds (method_generic.j2). An output whose kind is undeclared, or
  whose citations do not all resolve to inputs it was shown, is refused with
  a Finding that documents the refusal without blocking release - a refused
  proposal is the law working, not a page defect.
* a Quantity reaches an output only by copying a cited input's registered
  quantity through quantity_from (EvidenceRequirement.forbid_new_quantities).
  No builder reads a number out of the free-text fields dict, so there is no
  path from prose to a coined figure.
* every model candidate is written PROPOSED: the model words things, the
  registry decides things (design 1, consequence 3).
* a model failure returns a finding and zero deltas. Absent evidence is not
  evidence of a defect; a blocked analysis is never defaulted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from pydantic import Field

from app.engine import types as T
from app.engine.calc.units import format_quantity
from app.engine.llm import ModelCall, ModelResponse, StructuredFailure, structured_call
from app.engine.methods.contract import (
    EvidenceRequirement,
    InputSpec,
    MethodContext,
    MethodResult,
    MethodSpec,
    QuestionShape,
    Validator,
    new_entity,
    register,
)
from app.engine.templating import render
from app.ui_spec import _Tolerant

# =============================================================================
# The output schema every diagnostic MODEL_ASSISTED method validates against.
# _Tolerant (extra keys ignored) so a chatty model degrades to fewer outputs,
# never to a crash; defaults are empty lists because an empty list is a real
# answer (templating.EMPTY_LIST_MARKER), never a reason to invent.
# =============================================================================

class ProposedOutput(_Tolerant):
    kind: str = ""
    text: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)
    quantity_from: str | None = None
    derived_from: list[str] = Field(default_factory=list)


class ProposedQuestion(_Tolerant):
    text: str = ""
    asks_for_kind: str = ""
    issue_id: str = ""


class ProposalSheet(_Tolerant):
    outputs: list[ProposedOutput] = Field(default_factory=list)
    questions: list[ProposedQuestion] = Field(default_factory=list)


# =============================================================================
# Shared machinery
# =============================================================================

def wording(e: T.Entity) -> str:
    """The one display string of an entity for a prompt. Read-only prose: the
    selector never sees this, only the model does, so scrambling it cannot
    change what runs (design 1)."""
    for name in ("text", "statement", "name", "question"):
        v = getattr(e.payload, name, None)
        if isinstance(v, str) and v:
            return v
    return e.kind.value


def gather_inputs(spec: MethodSpec, view: Any) -> list[T.Entity]:
    """Every live entity a declared InputSpec (required or optional) matches,
    first-seen order, deduplicated by id. InputSpec.matches already excludes
    terminal rows and enforces min_status and dimension pins, so the inputs a
    method sees are exactly what its declaration asked for - no more."""
    out: dict[str, T.Entity] = {}
    for inp in spec.required_inputs + spec.optional_inputs:
        for e in view.query(inp.kind):
            if inp.matches(e):
                out.setdefault(e.id, e)
    return list(out.values())


def dropped(spec_id: str, index: int, why: str, *, law: str = "dropped_output") -> T.Finding:
    """A refused model proposal. LOW and non-blocking on purpose: the refusal
    IS the enforcement; recording it keeps the run auditable without turning
    the absence of an output into a page defect."""
    return T.Finding(law=f"M.{spec_id}.{law}", where=f"{spec_id}:output:{index}", issue=why,
                     fix="the model may cite registered input ids and propose declared kinds only",
                     severity=T.Severity.LOW, blocks_final=False)


@dataclass(frozen=True)
class Proposal:
    """What one model round yielded, or why it could not."""
    sheet: ProposalSheet | None
    response: ModelResponse | None
    inputs: tuple[T.Entity, ...]
    issue: T.Entity | None
    failure: MethodResult | None

    @property
    def inputs_by_id(self) -> dict[str, T.Entity]:
        return {e.id: e for e in self.inputs}


def model_proposals(ctx: MethodContext, spec: MethodSpec, purpose: str, instructions: str) -> Proposal:
    """One structured model round over the generic method prompt.

    The prompt is rendered from the registered inputs and the issue node only;
    the closed output-kind list excludes QUESTION because questions have their
    own channel in the JSON shape. A StructuredFailure becomes a finding and
    no deltas: the analysis is blocked upstream, never filled in here."""
    issue = ctx.registry.get(ctx.issue_ids[0]) if ctx.issue_ids else None
    if issue is None:
        f = T.Finding(law=f"M.{spec.id}.no_issue", where=spec.id,
                      issue="run invoked without a registered issue node",
                      fix="select the method through select_methods, which binds an issue id",
                      severity=T.Severity.LOW, blocks_final=False)
        return Proposal(None, None, (), None, MethodResult(findings=(f,)))
    inputs = tuple(gather_inputs(spec, ctx.registry))
    prompt = render(
        "method_generic.j2",
        method_id=spec.id,
        method_purpose=purpose,
        issue={"id": issue.id, "text": wording(issue),
               "interrogative": issue.payload.interrogative.value,
               "target_kind": issue.payload.target_kind.value},
        inputs=[{"id": e.id, "kind": e.kind.value, "text": wording(e),
                 "quantity": (format_quantity(q) if (q := getattr(e.payload, "quantity", None)) is not None else None)}
                for e in inputs],
        assumption_grants=[],
        output_kinds=[k for k in spec.output_kinds if k is not T.Kind.QUESTION],
        instructions=instructions,
    )
    call = ModelCall(purpose=f"method_{spec.id}", messages=({"role": "user", "content": prompt},),
                     schema_version=spec.output_schema_version, engagement_id=ctx.registry.engagement_id)
    try:
        sheet, response = structured_call(ctx.provider, call, ProposalSheet)
    except StructuredFailure as exc:
        f = T.Finding(law=f"M.{spec.id}.model_failure", where=spec.id, issue=str(exc)[:300],
                      fix="the analysis is blocked, not defaulted; the partner retries or records the gap",
                      severity=T.Severity.LOW, blocks_final=False)
        return Proposal(None, None, inputs, issue, MethodResult(findings=(f,)))
    return Proposal(sheet, response, inputs, issue, None)


def admitted(spec: MethodSpec, proposal: Proposal,
             findings: list[T.Finding]) -> Iterator[tuple[int, ProposedOutput, T.Kind, tuple[str, ...], T.Quantity | None]]:
    """The outputs that pass the shared admission law, with their resolved
    citations and (when quantity_from resolves) the copied registered
    quantity. Everything refused lands in `findings` with the reason."""
    by_id = proposal.inputs_by_id
    for i, o in enumerate(proposal.sheet.outputs if proposal.sheet else []):
        try:
            kind = T.Kind(o.kind)
        except ValueError:
            kind = None
        if kind is None or kind not in spec.output_kinds:
            findings.append(dropped(spec.id, i, f"kind {o.kind!r} is outside the declared output kinds"))
            continue
        cited = tuple(dict.fromkeys(x for x in o.derived_from if isinstance(x, str) and x))
        if not cited or any(c not in by_id for c in cited):
            # An output citing nothing, or citing an id it was never shown,
            # has fabricated its own provenance; it cannot enter the registry.
            findings.append(dropped(spec.id, i, "output does not cite input ids it was shown", law="uncited_output"))
            continue
        quantity: T.Quantity | None = None
        if o.quantity_from:
            src = by_id.get(o.quantity_from)
            quantity = getattr(src.payload, "quantity", None) if src is not None else None
            if quantity is None:
                # The reference resolves to no registered quantity: the number
                # is refused, the words may still stand as PROPOSED.
                findings.append(dropped(spec.id, i, f"quantity_from {o.quantity_from!r} names no registered quantity",
                                        law="coined_quantity"))
        yield i, o, kind, cited, quantity


def proposed_entity(ctx: MethodContext, issue: T.Entity, kind: T.Kind, payload: Any,
                    derived: tuple[str, ...], call_id: str | None) -> T.Entity:
    """A model candidate as the registry will see it: PROPOSED, always. The
    model words things; the registry decides things (design 1.3) - a method
    that could mark its own model output CONFIRMED would be its own judge."""
    return new_entity(ctx, kind, payload, derived_from=derived,
                      relation=T.RelationToCentralDecision.INFORMS, confidence=T.Confidence(None),
                      decision_id=issue.relevance.decision_id, weight=issue.relevance.weight,
                      status=T.Status.PROPOSED, model_call_id=call_id)


def question_payloads(proposal: Proposal, *, effort: T.EffortClass = T.EffortClass.OFFHAND) -> list[T.QuestionPayload]:
    """The model's own questions, typed. An unknown asks_for kind is dropped
    from the ask, not guessed; the question text still stands."""
    out: list[T.QuestionPayload] = []
    if proposal.sheet is None or proposal.issue is None:
        return out
    for q in proposal.sheet.questions:
        text = q.text.strip()
        if not text:
            continue
        try:
            asks: tuple[T.AsksFor, ...] = (T.AsksFor(T.Kind(q.asks_for_kind)),)
        except ValueError:
            asks = ()
        out.append(T.QuestionPayload(text=text, asks_for=asks, issue_ids=(proposal.issue.id,),
                                     effort=effort, strategy=T.FillStrategy.ASK_CLIENT))
    return out


def gap_of(value: Any) -> T.GapState | None:
    """The GapState a model named, or None. Never a default: GapState has no
    unknown member, so a gap the model did not state is a refused output, not
    a silently coined judgement."""
    try:
        return T.GapState(value)
    except ValueError:
        return None


def capability_class_of(value: Any) -> T.CapabilityClass | None:
    try:
        return T.CapabilityClass(value)
    except ValueError:
        return None


# =============================================================================
# Shared validators (factories, so every finding names its method)
# =============================================================================

def added_of(result: MethodResult, kind: T.Kind) -> list[T.Entity]:
    return [d.entity for d in result.deltas if isinstance(d, T.Add) and d.entity.kind == kind]


def cites_validator(spec_id: str) -> Validator:
    """Every output cites the entities it rests on (spec section 7: every
    recommendation traces to evidence). A QUESTION is the one exception - it
    is the typed hole itself."""
    def _v(view: Any, result: MethodResult) -> list[T.Finding]:
        out: list[T.Finding] = []
        for d in result.deltas:
            if isinstance(d, T.Add) and d.entity.kind != T.Kind.QUESTION and not d.entity.provenance.derived_from:
                out.append(T.Finding(law=f"M.{spec_id}.uncited_output", where=d.entity.id or d.entity.kind.value,
                                     issue="a method output cites nothing",
                                     fix="derive the output from registered entities or do not write it",
                                     entity_ids=(d.entity.id,) if d.entity.id else ()))
        return out
    return _v


def copied_quantity_validator(spec_id: str) -> Validator:
    """No Quantity that is not copied from a cited input or calculated with a
    recorded formula (EvidenceRequirement.forbid_new_quantities). Checked by
    value against the cited rows, so a number that exists nowhere upstream
    cannot ride out on any payload."""
    def _v(view: Any, result: MethodResult) -> list[T.Finding]:
        out: list[T.Finding] = []
        for d in result.deltas:
            if not isinstance(d, T.Add):
                continue
            e = d.entity
            q = getattr(e.payload, "quantity", None)
            if q is None:
                continue
            if getattr(e.payload, "basis", None) == T.FactBasis.CALCULATED and getattr(e.payload, "formula", None):
                continue
            sources = [view.get(i) for i in e.provenance.derived_from]
            if not any(s is not None and getattr(s.payload, "quantity", None) == q for s in sources):
                out.append(T.Finding(law=f"M.{spec_id}.coined_quantity", where=e.id or e.kind.value,
                                     issue="a quantity matches no cited input and no calculation",
                                     fix="copy the quantity from a cited entity or route it through the Calculator",
                                     entity_ids=(e.id,) if e.id else ()))
        return out
    return _v


def sequential_steps_validator(spec_id: str) -> Validator:
    """Process steps are sequential and cited: sequences are exactly 1..n (a
    gap or a duplicate means an order the page cannot honestly draw) and each
    step rests on evidence."""
    def _v(view: Any, result: MethodResult) -> list[T.Finding]:
        out: list[T.Finding] = []
        steps = added_of(result, T.Kind.PROCESS_STEP)
        if steps:
            seqs = sorted(s.payload.sequence for s in steps)
            if seqs != list(range(1, len(steps) + 1)):
                out.append(T.Finding(law=f"M.{spec_id}.non_sequential_steps", where=spec_id,
                                     issue=f"step sequences {seqs} are not 1..{len(steps)}",
                                     fix="number the steps consecutively in their evidenced order"))
        for s in steps:
            if not s.provenance.derived_from:
                out.append(T.Finding(law=f"M.{spec_id}.uncited_step", where=s.id or s.kind.value,
                                     issue="a process step cites no evidence",
                                     fix="derive every step from registered facts"))
        return out
    return _v


# =============================================================================
# The capability_gap method itself
# =============================================================================

def _v_capability_evidence(view: Any, result: MethodResult) -> list[T.Finding]:
    """A stated gap names its evidence: the payload's evidence tuple is
    non-empty and a subset of the row's own citations, so the rendered gap
    can never point at facts the analysis did not rest on."""
    out: list[T.Finding] = []
    for e in added_of(result, T.Kind.CAPABILITY):
        cited = set(e.provenance.derived_from)
        if not e.payload.evidence or not set(e.payload.evidence) <= cited:
            out.append(T.Finding(law="M.capability_gap.gap_without_evidence", where=e.id or e.kind.value,
                                 issue="a capability gap does not name evidence from its own citations",
                                 fix="set payload.evidence to the cited fact ids that show the gap",
                                 entity_ids=(e.id,) if e.id else ()))
    return out


SPEC = MethodSpec(
    id="capability_gap",
    version=1,
    applicability=(QuestionShape(T.Interrogative.WHAT, T.Kind.CAPABILITY),
                   QuestionShape(T.Interrogative.HOW, T.Kind.CAPABILITY)),
    answers=(T.Interrogative.WHAT, T.Interrogative.HOW),
    required_inputs=(
        InputSpec("objectives", T.Kind.OBJECTIVE, min_count=1, effort=T.EffortClass.OFFHAND,
                  why_needed="a gap is the distance between an objective and the evidenced current state"),
        InputSpec("facts", T.Kind.FACT, min_count=1, effort=T.EffortClass.OFFHAND,
                  why_needed="without registered facts there is no current state to hold the objective against"),
    ),
    optional_inputs=(InputSpec("capabilities", T.Kind.CAPABILITY, min_count=1),),
    execution=T.ExecutionType.MODEL_ASSISTED,
    output_kinds=(T.Kind.CAPABILITY,),
    output_schema=ProposalSheet,
    evidence=EvidenceRequirement(),
    limitations=("states how present a capability is; it does not design the capability",),
    validators=(
        cites_validator("capability_gap"),
        _v_capability_evidence,
    ),
    cost_class=1,
    max_model_calls=1,
)

_INSTRUCTIONS = (
    "For each capability the objectives require, propose one capability output whose "
    "fields carry 'gap' (one of: " + " | ".join(g.value for g in T.GapState) + ") and "
    "'capability_class' (one of: " + " | ".join(c.value for c in T.CapabilityClass) + "). "
    "State a gap only where cited inputs show it; where the inputs cannot settle a gap, "
    "return a question instead of a guess."
)


@register
class CapabilityGapMethod:
    spec = SPEC

    def run(self, ctx: MethodContext) -> MethodResult:
        proposal = model_proposals(ctx, self.spec, "name capability gaps between the objectives and the evidenced current state", _INSTRUCTIONS)
        if proposal.failure is not None:
            return proposal.failure
        findings: list[T.Finding] = []
        deltas: list[T.Add] = []
        for i, o, kind, derived, _q in admitted(self.spec, proposal, findings):
            text = o.text.strip()
            if not text:
                findings.append(dropped(self.spec.id, i, "a capability without wording says nothing"))
                continue
            gap = gap_of(o.fields.get("gap"))
            if gap is None:
                # No default gap exists to fall back to: an unstated gap is a
                # refused output, never a coined judgement (dynamic law).
                findings.append(dropped(self.spec.id, i, "gap is not a GapState member", law="gap_vocabulary"))
                continue
            cls = capability_class_of(o.fields.get("capability_class")) or proposal.issue.payload.capability_class
            if cls is None:
                findings.append(dropped(self.spec.id, i, "no capability class stated and none on the issue node"))
                continue
            payload = T.CapabilityPayload(text=text, capability_class=cls, gap=gap, evidence=derived)
            deltas.append(T.Add(proposed_entity(ctx, proposal.issue, kind, payload, derived,
                                                proposal.response.call_id)))
        return MethodResult(deltas=tuple(deltas), questions=tuple(question_payloads(proposal)),
                            findings=tuple(findings), model_call_ids=(proposal.response.call_id,))
