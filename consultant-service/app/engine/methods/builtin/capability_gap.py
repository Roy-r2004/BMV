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
  path from prose to a coined figure; coined_figures() closes the other
  direction, refusing a figure that the proposed PROSE states and no cited
  input contains.
* what a method declares about its own outputs is not a model field:
  step_deltas() stamps the method's perspective and numbers the steps, and
  perspective_validator re-checks it on a doctored result.
* every model candidate is written PROPOSED: the model words things, the
  registry decides things (design 1, consequence 3).
* a model failure returns a finding and zero deltas. Absent evidence is not
  evidence of a defect; a blocked analysis is never defaulted.
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Iterator, Sequence

from pydantic import Field

from app.engine import types as T
from app.engine.authority import MAY_CONFIRM
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
    concluded_about,
    gather_inputs,
    new_entity,
    register,
    unmet_over,
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




def unconcluded_first(spec: MethodSpec, view: Any, inputs: Sequence[T.Entity]) -> list[T.Entity]:
    """The window, led by the rows this analysis has not concluded about yet.

    A call's answer is bounded by its token budget, so a window wider than the
    budget is answered from the FRONT of it. The window was the registry's own
    order, which is the order rows were written - so a second run of a method
    was handed the same first rows it had already concluded about, spent a
    model call restating them, and had every restatement refused. The rows that
    arrived since, which are the only ones that could have yielded anything
    new, were past the end of what the budget reached.

    "Concluded about" is `concluded_about`, the same reading the selector uses
    when it decides whether to offer the method at all, so the window and the
    decision to open it cannot disagree. Order only - nothing is dropped,
    because a row already concluded about is still context for the ones that
    are not, and a method that could no longer see its own earlier evidence
    would start contradicting itself.
    """
    spent = spent_reading(spec, view)
    fresh = [e for e in inputs if not spent(e)]
    return fresh + [e for e in inputs if spent(e)]


def spent_reading(spec: MethodSpec, view: Any) -> Callable[[T.Entity], bool]:
    """Whether a further conclusion drawn from a row would land where one
    already is. Two readings, and the second is the one the ADMISSION law
    itself uses: the row is already cited by a conclusion of this method's
    kind, or its own wording is already the wording of one. The second matters
    because two rows can carry one sentence, and a conclusion drawn from the
    second is refused as a restatement of the conclusion drawn from the first -
    so the window and the door have to read the same thing or the window keeps
    offering what the door refuses.

    Built once per run and returned as a predicate, because all three callers -
    the window that orders the prompt (`unconcluded_first`), the selector that
    decides whether to open the call at all (`new_evidence_remains`) and the
    door that refuses the restatement (`admitted`) - must be reading one rule.
    """
    concluded = concluded_about(spec, view)
    held = registered_wordings(view, spec.output_kinds)
    kinds = tuple(k for k in spec.output_kinds if k is not T.Kind.QUESTION)

    def spent(e: T.Entity) -> bool:
        if e.id in concluded:
            return True
        said = _norm_wording(wording(e))
        return bool(said) and any((kind, said) in held for kind in kinds)

    return spent


def unconcluded(spec: MethodSpec, view: Any) -> list[T.Entity]:
    """This method's window, less every row it has already concluded from."""
    spent = spent_reading(spec, view)
    return [e for e in gather_inputs(spec, view) if not spent(e)]


def new_evidence_remains(spec: MethodSpec, view: Any) -> bool:
    """`MethodSpec.pending` for every method that asks a model to word a
    conclusion over the shared admission law: whether the register still holds
    evidence this method has not already concluded from.

    `input_state` asks whether the register holds what the method declared it
    needs. That question is answered the same way on round one and on round
    nine, because the rows it counts do not leave. The question the SPEND turns
    on is the narrower one - whether what it needs is there in rows this
    analysis has not already drawn its kind of conclusion from - and it is
    asked with the same `min_count` rule, over the unconcluded subset.

    Why a required slot and not simply "any unconcluded row": every row the
    window shows is context, but only a row that fills a DECLARED requirement
    is one the method can conclude FROM. Measured over fifteen engagements,
    every model call that generated candidates and kept every one of them
    refused was made over a window in this state: `capability_gap` was shown
    forty-eight rows and not one of them unconcluded; `root_cause` was shown a
    fresh remainder that was OBJECTIVE rows only, and a cause is a FACT;
    `market_sizing`, whose chain is registered figures, was shown thirty-eight
    unconcluded rows carrying no quantity between them. In each the register
    could have said so before the call, and this is it saying so.

    A method that has never run is unaffected: nothing has been concluded, so
    every row is unconcluded and the reading is `input_state`'s.
    """
    return not unmet_over(spec, unconcluded(spec, view))


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
    # The registry this round was proposed against, so admission can ask what
    # the engagement already holds. None only on the failure paths, which
    # admit nothing anyway.
    view: Any = None

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
        return Proposal(None, None, (), None, MethodResult(findings=(f,)), ctx.registry)
    inputs = tuple(unconcluded_first(spec, ctx.registry, gather_inputs(spec, ctx.registry)))
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
        return Proposal(None, None, inputs, issue, MethodResult(findings=(f,)), ctx.registry)
    return Proposal(sheet, response, inputs, issue, None, ctx.registry)


def _norm_wording(text: Any) -> str:
    """A conclusion's wording, compared exactly once whitespace and case are
    normalised. Not a similarity measure: two conclusions are the same here
    only when they are the same words."""
    return " ".join(str(text or "").split()).casefold()


def registered_wordings(view: Any, kinds: Sequence[T.Kind]) -> set[tuple[T.Kind, str]]:
    """What the engagement already concluded, as (kind, wording) pairs.

    Read through `query()` and filtered here: RegistryView promises only
    `query`, so a narrower view (a specialist's window, a probe) answers this
    the same way the registry does.
    """
    out: set[tuple[T.Kind, str]] = set()
    if view is None:
        return out
    for kind in kinds:
        for row in view.query(kind):
            if row.status not in T.TERMINAL_STATUSES:
                out.add((kind, _norm_wording(wording(row))))
    return out


def admitted(spec: MethodSpec, proposal: Proposal,
             findings: list[T.Finding]) -> Iterator[tuple[int, ProposedOutput, T.Kind, tuple[str, ...], T.Quantity | None]]:
    """The outputs that pass the shared admission law, with their resolved
    citations and (when quantity_from resolves) the copied registered
    quantity. Everything refused lands in `findings` with the reason."""
    by_id = proposal.inputs_by_id
    held = registered_wordings(proposal.view, spec.output_kinds)
    for i, o in enumerate(proposal.sheet.outputs if proposal.sheet else []):
        try:
            kind = T.Kind(o.kind)
        except ValueError:
            kind = None
        if kind is None or kind not in spec.output_kinds:
            findings.append(dropped(spec.id, i, f"kind {o.kind!r} is outside the declared output kinds"))
            continue
        said = (kind, _norm_wording(o.text))
        if said in held:
            # The engagement already holds this conclusion. A method that runs
            # on twenty issue nodes proposes the same capability from twenty
            # angles, and registering each one makes the row count a measure of
            # how many nodes ran rather than of what the analysis found: the
            # counts every plan predicate reads stop meaning anything, and two
            # engagements that found different things come out looking alike
            # because both simply filled up. Restating is not finding.
            findings.append(dropped(spec.id, i, "restates a conclusion the engagement already holds",
                                    law="restatement"))
            continue
        held.add(said)
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


def flag_of(value: Any) -> bool:
    """A boolean the model stated, and nothing else. `bool("false")` is True,
    which is how a model's word for absence becomes a claim of presence; the
    closed list below is the only thing that sets a flag."""
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.strip().lower() in ("true", "yes", "1")


def int_of(value: Any) -> int | None:
    """A positive integer the model stated, or None. None is a typed hole the
    caller refuses; it is never replaced by a position the method invented."""
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return n if n >= 1 else None


# Registry ids ("FCT-3", "CAP-12") carry digits that are names, not figures;
# they are cut out before the figure scan so a citation never reads as an
# invented number.
_ID_TOKEN_RE = re.compile(r"\b[A-Z]{2,4}-\d+\b")
_FIGURE_RE = re.compile(r"\d+(?:[.,]\d+)*")


def coined_figures(texts: Iterable[str], cited_texts: Iterable[str]) -> tuple[str, ...]:
    """Figures in proposed prose that appear in no cited input.

    forbid_new_quantities closes the typed door: a Quantity reaches a payload
    only by copy or calculation. This closes the prose door beside it. A
    hypothesis that reads "the backlog costs 250 hours a month" states a
    figure the engagement never recorded just as surely as a Quantity field
    would, and it renders into a page the same way (spec section 7: unknown
    information remains unknown).
    """
    haystack = " ".join(t or "" for t in cited_texts).replace(",", "")
    out: list[str] = []
    for t in texts:
        for tok in _FIGURE_RE.findall(_ID_TOKEN_RE.sub(" ", t or "")):
            if tok.replace(",", "") not in haystack:
                out.append(tok)
    return tuple(dict.fromkeys(out))


def evidenced_status(view: Any, requirement: EvidenceRequirement, cited: Sequence[str],
                     actor: T.Actor, authority: T.Authority) -> T.Status:
    """PROPOSED unless the evidence requirement is met AND `actor` is one the
    row's owning authority lets confirm (I1).

    Two independent gates, because they answer different questions. The
    requirement asks whether what this rests on is strong enough
    (min_authority_for_confirmed, and each input settled rather than merely
    proposed); may_advance asks whether this producer is allowed to say so at
    all - which is why a method summarising client facts still writes a
    current-state FACT as PROPOSED: a method is not a record.

    Absence decides downwards. An input the view cannot resolve leaves the
    output PROPOSED rather than condemning or promoting it: unseen evidence
    is not strong evidence, and a scoped specialist view legitimately hides
    rows (design 8.1).
    """
    if not cited:
        return T.Status.PROPOSED
    for cid in cited:
        src = view.get(cid)
        if src is None or src.authority not in requirement.min_authority_for_confirmed:
            return T.Status.PROPOSED
        if src.status not in (T.Status.CONFIRMED, T.Status.APPROVED):
            return T.Status.PROPOSED
    return T.Status.CONFIRMED if actor in MAY_CONFIRM[authority] else T.Status.PROPOSED


def step_deltas(ctx: MethodContext, spec: MethodSpec, proposal: Proposal,
                rows: Sequence[tuple[int, ProposedOutput, T.Kind, tuple[str, ...], T.Quantity | None]],
                perspective: T.StepPerspective, findings: list[T.Finding]) -> list[T.Add]:
    """The PROCESS_STEP rows of one admitted proposal, in one evidenced order.

    Two laws are enforced here rather than left to the model:

    * the perspective is the METHOD's declared subject, never a field the
      model fills. process_map and journey answer the same
      HOW-on-PROCESS_STEP shape and differ only in what they look at; if the
      model could choose, a run could file a customer journey as an internal
      process and the customer-journey product would count steps nobody ever
      saw from the customer's side.
    * a step that states no place in the sequence is refused, and the
      surviving steps are numbered 1..n in the order the model stated. An
      unplaced step given a position would be an ordering the evidence never
      supported; renumbering closes the gap a refusal leaves, so the drawn
      sequence is always 1..n (sequential_steps_validator re-checks it).
    """
    placed: list[tuple[int, int, ProposedOutput, tuple[str, ...]]] = []
    by_id = proposal.inputs_by_id
    for i, o, kind, derived, _q in rows:
        if kind is not T.Kind.PROCESS_STEP:
            continue
        text = o.text.strip()
        if not text:
            findings.append(dropped(spec.id, i, "a process step without wording says nothing"))
            continue
        seq = int_of(o.fields.get("sequence"))
        if seq is None:
            findings.append(dropped(spec.id, i, "the step states no place in the sequence", law="unplaced_step"))
            continue
        placed.append((seq, i, o, derived))
    placed.sort(key=lambda row: (row[0], row[1]))
    out: list[T.Add] = []
    for position, (_seq, _i, o, derived) in enumerate(placed, start=1):
        actor_id = o.fields.get("actor_id")
        systems = o.fields.get("system_ids")
        payload = T.ProcessStepPayload(
            text=o.text.strip(),
            perspective=perspective,
            sequence=position,
            # An actor or a system named by an id the run was never shown is
            # not a reference, it is a guess; the step still stands without it.
            actor_id=actor_id if isinstance(actor_id, str) and actor_id in by_id else None,
            system_ids=tuple(s for s in (systems if isinstance(systems, (list, tuple)) else ())
                             if isinstance(s, str) and by_id.get(s) is not None
                             and by_id[s].kind is T.Kind.CAPABILITY),
            pain_point=flag_of(o.fields.get("pain_point")),
            evidence=derived)
        out.append(T.Add(proposed_entity(ctx, proposal.issue, T.Kind.PROCESS_STEP, payload, derived,
                                         proposal.response.call_id if proposal.response else None)))
    return out


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


def perspective_validator(spec_id: str, perspective: T.StepPerspective) -> Validator:
    """Every step a method writes carries the perspective that method
    declared. The work-product plan counts PROCESS_STEP rows by perspective
    (design 10.1, customer_journeys), so a step filed under the wrong one
    silently changes which deliverables an engagement gets - and prints an
    internal handover as something the customer experienced."""
    def _v(view: Any, result: MethodResult) -> list[T.Finding]:
        return [T.Finding(law=f"M.{spec_id}.wrong_perspective", where=s.id or s.kind.value,
                          issue=f"a step of {spec_id} carries perspective "
                                f"{s.payload.perspective.value}, not {perspective.value}",
                          fix="the perspective is the method's declared subject, never a model field",
                          entity_ids=(s.id,) if s.id else ())
                for s in added_of(result, T.Kind.PROCESS_STEP) if s.payload.perspective is not perspective]
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
                   QuestionShape(T.Interrogative.HOW, T.Kind.CAPABILITY),
                   # "Which way do we go?" asked of the decision is answered
                   # first by what the organisation can and cannot do: a
                   # capability gap is the distance between an objective and
                   # the evidenced current state, and this method reads both
                   # off the register rather than off the node. Carried only by
                   # a CAPABILITY-shaped node before, this was the first link
                   # of the CAPABILITY -> OPTION -> RECOMMENDATION chain, and a
                   # tree that happened not to propose one left the engagement
                   # with nothing to source, nothing to compare and nothing to
                   # advise - measured on five of fifteen engagements, decided
                   # by which shapes one expansion of the tree happened to
                   # draw. The decision node is the one node every engagement
                   # has, and asking what it turns on there is the same
                   # question, not a wider one.
                   QuestionShape(T.Interrogative.WHICH, T.Kind.DECISION, comparative=True)),
    answers=(T.Interrogative.WHAT, T.Interrogative.HOW, T.Interrogative.WHICH),
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


def pending(view: Any) -> bool:
    """Whether this method still has anything to conclude here.

    a capability is named from the objectives it serves and the facts that show its
    state; where every such row is already cited by a live capability, the next
    run can only re-word the register.

    `new_evidence_remains` asks that in one place for every method that words
    a conclusion through the shared admission law, because it is that law -
    the door that refuses a restatement and an output citing rows it was not
    shown - that decides what a further call could keep.
    """
    return new_evidence_remains(SPEC, view)


SPEC = dataclasses.replace(SPEC, pending=pending)


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
