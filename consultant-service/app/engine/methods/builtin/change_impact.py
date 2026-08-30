"""change_impact - what the plan does to the people in it (design 7.3 row
change_impact): WHAT on STAKEHOLDER or RISK.

MODEL_ASSISTED with one call, through the shared plumbing in org_design.py.

Laws this module enforces, each in the docstring of the thing enforcing it:

  CH1 an impact is an impact on somebody: every RISK this method writes names
      a registered stakeholder as the party that feels it, resolved from an id
      (bearer_of, reused from risk_control), and every output cites the action
      that causes it. A change-impact assessment with no named parties is a
      paragraph about change in general.
  CH2 every ACTION this method writes is PEOPLE_AND_ORGANISATION (MF1.3) -
      the mitigation for a people impact is people work, and that class is the
      method's declared subject, never the model's choice
      (_v_actions_people_class).
  CH3 no coined figure: a proportion of staff affected, a training cost, a
      productivity dip - none of them may appear unless an input carries them.
"""
from __future__ import annotations

from dataclasses import replace

from app.engine import types as T
from app.engine.methods.contract import (
    EvidenceRequirement,
    InputSpec,
    MethodContext,
    MethodResult,
    MethodSpec,
    QuestionShape,
    new_entity,
    register,
)
from app.engine.methods.builtin.org_design import (
    GenericReply,
    cited,
    coined_figures,
    display_text,
    fresh_ids,
    issue_frame,
    live,
    parse_enum,
    propose,
    refusal,
    reply_questions,
    require_citations,
    with_id,
)
from app.engine.methods.builtin.risk_control import BEARER_KINDS, bearer_of, level_or_unknown


_INSTRUCTIONS = """Say what the planned actions above do to the people named above.
- "risk" outputs are impacts somebody feels. fields: "who_feels_it" (the id of a
  stakeholder or owner from the inputs), "likelihood" and "impact"
  (high | medium | low | unknown - say unknown when the inputs do not tell you).
- "action" outputs are the people-and-organisation steps that answer an impact.
  fields: "horizon" (days | weeks | months), "owner_id" (who does it, from the inputs).
Cite the planned action each impact comes from. State no proportion, cost or
duration that no input carries; ask for it as a question instead."""


class ChangeImpact:
    spec = MethodSpec(
        id="change_impact", version=1,
        applicability=(
            QuestionShape(T.Interrogative.WHAT, T.Kind.STAKEHOLDER),
            QuestionShape(T.Interrogative.WHAT, T.Kind.RISK),
        ),
        answers=(T.Interrogative.WHAT,),
        required_inputs=(
            # Two, because an impact assessment is about who is affected
            # differently; one party is a party, not an impact map.
            InputSpec("stakeholders", T.Kind.STAKEHOLDER, min_count=2,
                      why_needed="a change impact falls differently on different parties"),
            InputSpec("actions", T.Kind.ACTION,
                      why_needed="the planned work whose impact is being assessed"),
        ),
        optional_inputs=(
            InputSpec("owners", T.Kind.OWNER, min_count=0, why_needed="who could answer an impact"),
            InputSpec("process_steps", T.Kind.PROCESS_STEP, min_count=0,
                      why_needed="how the work runs today, which is what changes"),
        ),
        execution=T.ExecutionType.MODEL_ASSISTED,
        output_kinds=(T.Kind.RISK, T.Kind.ACTION),
        output_schema=GenericReply,
        evidence=EvidenceRequirement(),
        limitations=("assesses impact on the parties the engagement has registered; "
                     "it sizes no population and prices no change programme",),
        validators=(),
        cost_class=2, max_model_calls=1)

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        _, decision_id, weight = issue_frame(ctx)
        actions = live(view, T.Kind.ACTION)
        parties: list[T.Entity] = []
        for kind in BEARER_KINDS:
            parties.extend(live(view, kind))
        if not actions or not parties:
            # Absence is a typed hole: without planned work there is no change,
            # and without registered parties there is nobody to feel it.
            asks = T.Kind.ACTION if not actions else T.Kind.STAKEHOLDER
            q = T.QuestionPayload(
                text="Who is affected by the planned changes, and what exactly is planned?",
                asks_for=(T.AsksFor(asks),), issue_ids=ctx.issue_ids,
                why="a change impact needs both the change and the people it lands on",
                effort=T.EffortClass.OFFHAND, strategy=T.FillStrategy.ASK_CLIENT)
            return MethodResult(questions=(q,))

        inputs = actions + parties + live(view, T.Kind.PROCESS_STEP)
        reply, call_id, fails = propose(
            ctx, self.spec, purpose="assess what the planned actions do to the registered parties",
            inputs=inputs, instructions=_INSTRUCTIONS)
        if reply is None:
            return MethodResult(findings=fails)

        permitted = frozenset(e.id for e in inputs)
        by_id = {e.id: e for e in inputs}
        findings: list[T.Finding] = []
        deltas: list[T.EntityDelta] = []

        risk_outputs = [o for o in reply.outputs if o.kind == "risk"]
        risk_ids = iter(fresh_ids(view, T.Kind.RISK, len(risk_outputs)))
        for out in reply.outputs:
            ids = cited(out, permitted)
            if not ids:
                findings.append(refusal(self.spec.id, "uncited_output", out.kind or "output",
                                        "the model cited no registered input"))
                if out.kind == "risk":
                    next(risk_ids, None)
                continue
            coined = coined_figures([out.text], [display_text(by_id.get(i)) for i in ids])
            if coined:
                findings.append(refusal(self.spec.id, "invented_figure", out.kind or "output",
                                        f"figure(s) {', '.join(coined)} appear in no cited input"))
                if out.kind == "risk":
                    next(risk_ids, None)
                continue
            if out.kind == "risk":
                rid = next(risk_ids, None)
                bearer = bearer_of(out.fields.get("who_feels_it"), by_id)
                if bearer is None:
                    findings.append(refusal(self.spec.id, "impact_without_bearer", rid or out.text or "risk",
                                            "the impact names no registered party that feels it"))
                    continue
                payload = T.RiskPayload(text=out.text, who_feels_it=bearer,
                                        likelihood=level_or_unknown(out.fields.get("likelihood")),
                                        impact=level_or_unknown(out.fields.get("impact")))
                e = new_entity(ctx, T.Kind.RISK, payload, derived_from=ids,
                               relation=T.RelationToCentralDecision.CONSTRAINS,
                               confidence=T.Confidence(None, "model_estimate"),
                               decision_id=decision_id, weight=weight, model_call_id=call_id)
                deltas.append(T.Add(with_id(e, rid) if rid else e))
            elif out.kind == "action":
                owner = by_id.get(str(out.fields.get("owner_id") or "").strip())
                payload = T.ActionPayload(
                    text=out.text,
                    # CH2: answering a people impact is people work. The class
                    # is the method's declared subject, not the model's word.
                    capability_class=T.CapabilityClass.PEOPLE_AND_ORGANISATION,
                    horizon=parse_enum(T.Horizon, out.fields.get("horizon"), T.Horizon.WEEKS),
                    owner_id=owner.id if owner is not None and owner.kind is T.Kind.OWNER else None)
                deltas.append(T.Add(new_entity(ctx, T.Kind.ACTION, payload, derived_from=ids,
                                               relation=T.RelationToCentralDecision.INFORMS,
                                               confidence=T.Confidence(None, "model_estimate"),
                                               decision_id=decision_id, weight=weight,
                                               model_call_id=call_id)))
            else:
                findings.append(refusal(self.spec.id, "undeclared_kind", out.kind or "output",
                                        "an output outside the declared kinds is dropped"))
        return MethodResult(deltas=tuple(deltas), questions=reply_questions(reply, ctx),
                            findings=tuple(findings),
                            model_call_ids=(call_id,) if call_id else ())


def _v_impact_names_a_bearer(view, result: MethodResult) -> list[T.Finding]:
    """CH1 re-checked: no impact lands without the party that feels it."""
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not T.Kind.RISK:
            continue
        if not (e.payload.who_feels_it or "").strip():
            out.append(T.Finding(law="M.change_impact.impact_without_bearer", where=e.id or "risk",
                                 issue="a change impact names nobody who feels it",
                                 fix="name the registered party the impact lands on"))
    return out


def _v_actions_people_class(view, result: MethodResult) -> list[T.Finding]:
    """CH2 re-checked: every ACTION this method wrote is people-and-organisation
    work. The type system requires a class; this law requires the right one, so
    the process/people predicates that plan work products keep reading truth."""
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is not None and e.kind is T.Kind.ACTION \
                and e.payload.capability_class is not T.CapabilityClass.PEOPLE_AND_ORGANISATION:
            out.append(T.Finding(law="M.change_impact.action_class", where=e.id or "action",
                                 issue="a change-impact action must be people_and_organisation",
                                 fix="set capability_class to the method's declared subject"))
    return out


ChangeImpact.spec = replace(ChangeImpact.spec, validators=(require_citations("change_impact"),
                                                            _v_impact_names_a_bearer,
                                                            _v_actions_people_class))
register(ChangeImpact)
