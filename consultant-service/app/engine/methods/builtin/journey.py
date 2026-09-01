"""journey - HOW on a PROCESS_STEP, from outside: the steps a stakeholder
lives through, in the order the evidence puts them.

Same shape as process_map, same shared step builder, one difference that
matters everywhere downstream: the perspective. A journey is what somebody
outside the organisation experiences, so this method additionally requires a
registered STAKEHOLDER - a journey with nobody living it is a process map
with a friendlier heading, and the customer_journeys work product would
count it as evidence of an experience the engagement never established
(design 10.1).

The laws:

  J1  the perspective is CUSTOMER, stamped by step_deltas() and re-checked by
      perspective_validator. Mutation partner: removing that validator lets a
      doctored result file internal steps as a customer journey.
  J2  steps are sequential and cited (sequential_steps_validator), on the
      same terms as process_map: a step that states no place is refused, and
      the survivors are numbered 1..n.
  J3  the person whose journey it is comes from the registry. `actor_id`
      survives only when it names a row this run was shown; an invented actor
      would put a name on an experience nobody reported.
"""
from __future__ import annotations

import dataclasses
from app.engine import types as T
from app.engine.methods.builtin.capability_gap import (
    ProposalSheet,
    added_of,
    admitted,
    cites_validator,
    copied_quantity_validator,
    model_proposals,
    new_evidence_remains,
    perspective_validator,
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
from typing import Any

PERSPECTIVE = T.StepPerspective.CUSTOMER


def _v_pain_points_are_cited(view, result: MethodResult) -> list[T.Finding]:
    """A step marked as a pain point is an accusation about the client's
    business; it rests on the rows the step itself cites, and the payload's
    evidence tuple must be inside them so the rendered journey can never
    point at facts the step did not rest on."""
    out: list[T.Finding] = []
    for s in added_of(result, T.Kind.PROCESS_STEP):
        if not s.payload.pain_point:
            continue
        cited = set(s.provenance.derived_from)
        if not s.payload.evidence or not set(s.payload.evidence) <= cited:
            out.append(T.Finding(law="M.journey.uncited_pain_point", where=s.id or s.kind.value,
                                 issue="a step is marked a pain point without evidence among its own citations",
                                 fix="mark a pain point only where a cited input shows it",
                                 entity_ids=(s.id,) if s.id else ()))
    return out


SPEC = MethodSpec(
    id="journey",
    version=1,
    applicability=(QuestionShape(T.Interrogative.HOW, T.Kind.PROCESS_STEP),),
    answers=(T.Interrogative.HOW,),
    required_inputs=(
        InputSpec("facts", T.Kind.FACT, min_count=1, effort=T.EffortClass.OFFHAND,
                  why_needed="a journey is drawn from what is registered about the experience today"),
        InputSpec("stakeholders", T.Kind.STAKEHOLDER, min_count=1, effort=T.EffortClass.OFFHAND,
                  why_needed="a journey is somebody's; without a registered stakeholder there is nobody living it"),
    ),
    optional_inputs=(
        InputSpec("capabilities", T.Kind.CAPABILITY, min_count=1),
        InputSpec("steps", T.Kind.PROCESS_STEP, min_count=1),
    ),
    execution=T.ExecutionType.MODEL_ASSISTED,
    output_kinds=(T.Kind.PROCESS_STEP, T.Kind.QUESTION),
    output_schema=ProposalSheet,
    evidence=EvidenceRequirement(),
    limitations=("describes the journey the registered facts support; it does not redesign it",),
    validators=(
        cites_validator("journey"),
        copied_quantity_validator("journey"),
        sequential_steps_validator("journey"),
        perspective_validator("journey", PERSPECTIVE),
        _v_pain_points_are_cited,
    ),
    cost_class=2,
    max_model_calls=2,
)

_INSTRUCTIONS = (
    "Propose the steps a registered stakeholder lives through, one output per step, each with "
    "fields 'sequence' (a positive integer giving its place), optionally 'actor_id' (the cited "
    "STAKEHOLDER id whose journey this is), 'system_ids' (cited CAPABILITY ids the step runs "
    "through) and 'pain_point' (true only where a cited input shows the pain). A step whose "
    "place the inputs do not settle is a question, not a guessed position."
)


def pending(view: Any) -> bool:
    """Whether this method still has anything to conclude here.

    a stage and its pain points are read from the facts and steps this method has
    not already turned into a journey.

    `new_evidence_remains` asks that in one place for every method that words
    a conclusion through the shared admission law, because it is that law -
    the door that refuses a restatement and an output citing rows it was not
    shown - that decides what a further call could keep.
    """
    return new_evidence_remains(SPEC, view)


SPEC = dataclasses.replace(SPEC, pending=pending)


@register
class JourneyMethod:
    spec = SPEC

    def run(self, ctx: MethodContext) -> MethodResult:
        proposal = model_proposals(
            ctx, self.spec, "describe the journey a registered stakeholder lives through today", _INSTRUCTIONS)
        if proposal.failure is not None:
            return proposal.failure
        findings: list[T.Finding] = []
        rows = list(admitted(self.spec, proposal, findings))
        deltas = step_deltas(ctx, self.spec, proposal, rows, PERSPECTIVE, findings)
        return MethodResult(deltas=tuple(deltas), questions=tuple(question_payloads(proposal)),
                            findings=tuple(findings), model_call_ids=(proposal.response.call_id,))


__all__ = ["SPEC", "JourneyMethod", "PERSPECTIVE"]
