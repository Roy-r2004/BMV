"""process_map - HOW on a PROCESS_STEP, from the inside: the steps the
organisation performs today, in the order the evidence puts them, and the
process capabilities they reveal.

process_map and journey answer the same HOW-on-PROCESS_STEP shape. Nothing
branches between them: they are separated by what each one requires (this
method needs two registered facts; journey additionally needs a stakeholder,
because a journey without whose journey it is describes nobody) and by the
perspective each declares. When both are fully supplied they tie, both run,
and the engagement gets the process from both sides - which is the intended
outcome, not a collision (design 7.2).

The laws, and the failures they prevent:

  P1  the perspective is this method's declared subject. It is stamped by
      step_deltas() and re-checked by perspective_validator: an internal
      handover filed as something a customer experienced would count towards
      the customer-journey product and print as an experience nobody had.
  P2  steps are sequential and cited. A step that states no place is refused
      and the survivors are numbered 1..n, so the sequence a page draws has
      no gap and no duplicate. Mutation partner: sequential_steps_validator.
  P3  a capability this method proposes is a PROCESS capability. The class is
      the method's declared subject too; a model relabelling a process step
      into a software system would route the finding to the wrong lane of
      every downstream plan.
"""
from __future__ import annotations

from app.engine import types as T
from app.engine.methods.builtin.capability_gap import (
    ProposalSheet,
    added_of,
    admitted,
    cites_validator,
    copied_quantity_validator,
    dropped,
    gap_of,
    model_proposals,
    perspective_validator,
    proposed_entity,
    question_payloads,
    sequential_steps_validator,
    step_deltas,
)
from app.engine.methods.contract import (
    EvidenceRequirement,
    InputSpec,
    MethodContext,
    MethodResult,
    MethodSpec,
    QuestionShape,
    register,
)

PERSPECTIVE = T.StepPerspective.INTERNAL
CAPABILITY_CLASS = T.CapabilityClass.PROCESS


def _v_process_capability_class(view, result: MethodResult) -> list[T.Finding]:
    """P3 on the finished result: every capability this method writes is a
    PROCESS capability."""
    return [T.Finding(law="M.process_map.wrong_capability_class", where=c.id or c.kind.value,
                      issue=f"a process map proposed a {c.payload.capability_class.value} capability",
                      fix="the capability class is the method's declared subject, never a model field",
                      entity_ids=(c.id,) if c.id else ())
            for c in added_of(result, T.Kind.CAPABILITY) if c.payload.capability_class is not CAPABILITY_CLASS]


SPEC = MethodSpec(
    id="process_map",
    version=1,
    applicability=(QuestionShape(T.Interrogative.HOW, T.Kind.PROCESS_STEP),),
    answers=(T.Interrogative.HOW,),
    required_inputs=(
        # Two facts, not one: a single fact describes a moment, and a sequence
        # drawn from it would be an order the evidence never stated.
        InputSpec("facts", T.Kind.FACT, min_count=2, effort=T.EffortClass.OFFHAND,
                  why_needed="a process is drawn from what is registered about how the work runs today"),
    ),
    optional_inputs=(
        InputSpec("owners", T.Kind.OWNER, min_count=1),
        InputSpec("stakeholders", T.Kind.STAKEHOLDER, min_count=1),
        InputSpec("capabilities", T.Kind.CAPABILITY, min_count=1),
        InputSpec("steps", T.Kind.PROCESS_STEP, min_count=1),
    ),
    execution=T.ExecutionType.MODEL_ASSISTED,
    output_kinds=(T.Kind.PROCESS_STEP, T.Kind.CAPABILITY, T.Kind.QUESTION),
    output_schema=ProposalSheet,
    evidence=EvidenceRequirement(),
    limitations=("maps the process as the registered facts describe it; it does not redesign it",),
    validators=(
        cites_validator("process_map"),
        copied_quantity_validator("process_map"),
        sequential_steps_validator("process_map"),
        perspective_validator("process_map", PERSPECTIVE),
        _v_process_capability_class,
    ),
    cost_class=2,
    max_model_calls=2,
)

_INSTRUCTIONS = (
    "Propose the steps the organisation performs, one output per step, each with fields "
    "'sequence' (a positive integer giving its place), optionally 'actor_id' (a cited OWNER or "
    "STAKEHOLDER id), 'system_ids' (cited CAPABILITY ids the step runs through) and 'pain_point' "
    "(true only where a cited input shows the pain). A step whose place the inputs do not settle "
    "is a question, not a guessed position. Propose a capability output only where the steps "
    "themselves show a process capability, with a 'gap' field (one of: "
    + " | ".join(g.value for g in T.GapState) + ")."
)


@register
class ProcessMapMethod:
    spec = SPEC

    def run(self, ctx: MethodContext) -> MethodResult:
        proposal = model_proposals(
            ctx, self.spec, "map the steps the organisation performs today, in evidenced order", _INSTRUCTIONS)
        if proposal.failure is not None:
            return proposal.failure
        findings: list[T.Finding] = []
        rows = list(admitted(self.spec, proposal, findings))
        deltas: list[T.Add] = step_deltas(ctx, self.spec, proposal, rows, PERSPECTIVE, findings)
        for i, o, kind, derived, _q in rows:
            if kind is not T.Kind.CAPABILITY:
                continue
            text = o.text.strip()
            if not text:
                findings.append(dropped(self.spec.id, i, "a capability without wording says nothing"))
                continue
            gap = gap_of(o.fields.get("gap"))
            if gap is None:
                # GapState has no unknown member: an unstated gap is a refused
                # output, never a coined judgement.
                findings.append(dropped(self.spec.id, i, "gap is not a GapState member", law="gap_vocabulary"))
                continue
            payload = T.CapabilityPayload(text=text, capability_class=CAPABILITY_CLASS, gap=gap, evidence=derived)
            deltas.append(T.Add(proposed_entity(ctx, proposal.issue, kind, payload, derived,
                                                proposal.response.call_id)))
        return MethodResult(deltas=tuple(deltas), questions=tuple(question_payloads(proposal)),
                            findings=tuple(findings), model_call_ids=(proposal.response.call_id,))


__all__ = ["SPEC", "ProcessMapMethod", "PERSPECTIVE"]
