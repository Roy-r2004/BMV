"""risk_control - what could go wrong with what has been proposed, and what
would catch it (design 7.3 row risk_control): WHAT on RISK or CONTROL.

MODEL_ASSISTED with one call, through the shared plumbing in org_design.py.

Laws this module enforces, each in the docstring of the thing enforcing it:

  RK1 every risk names who feels it, and the bearer is somebody the
      engagement has registered - a stakeholder, an owner, the decision
      owner. "Reputational damage" with nobody attached is a sentence, not a
      risk: it cannot be owned, mitigated or accepted (bearer_of,
      _v_risk_names_a_bearer).
  RK2 every control cites the risk it answers. A control floating free of a
      risk is a control for nothing, and it is exactly how a mitigation list
      grows longer than the risk register it is supposed to cover
      (run(), _v_control_cites_a_risk).
  RK3 the subject is what the engagement has actually proposed: risks are
      raised against registered RECOMMENDATIONs and ACTIONs, never against a
      generic idea of the industry.

The declared required input is ACTION: design 7.3 reads "RECOMMENDATION or
ACTION >= 1", and an InputSpec set is a conjunction, so the disjunction is
expressed as one required input plus one optional - the method still runs on
a registry that holds only recommendations, it just ranks lower for a node
that has neither (design 7.2).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

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
    propose,
    refusal,
    reply_questions,
    require_citations,
    with_id,
)


# The kinds that can be a bearer of a risk: a party the engagement registered.
BEARER_KINDS: tuple[T.Kind, ...] = (T.Kind.STAKEHOLDER, T.Kind.OWNER, T.Kind.DECISION_OWNER)

_INSTRUCTIONS = """Raise the risks in what has been proposed above, and the controls that
would catch them.
- "risk" outputs. fields: "who_feels_it" (the id of a stakeholder, owner or decision
  owner from the inputs - a risk nobody bears is not a risk), "likelihood" and
  "impact" (high | medium | low | unknown; say unknown when the inputs do not tell you),
  "ref" (a short label like R1 so a control can point at this risk).
- "control" outputs. fields: "risks" (a comma-separated list of risk refs above or RISK
  ids from the inputs), "owner_id" (who runs the control, from the inputs).
Raise risks about the proposals in the inputs only. State no probability, cost or
frequency that no input carries."""


def bearer_of(value: Any, by_id: dict[str, T.Entity]) -> str | None:
    """RK1: the name of the party that feels a risk, resolved from a registered
    entity id. A model's own phrase for a bearer is not accepted: the risk must
    point at somebody the engagement can actually talk to, and the wording of
    the register is then a rendering of registered names, not of prose."""
    e = by_id.get(str(value or "").strip())
    if e is not None and e.kind in BEARER_KINDS:
        return display_text(e) or e.id
    return None


def _split_refs(value: Any) -> list[str]:
    return [part.strip() for part in str(value or "").replace(";", ",").split(",") if part.strip()]


class RiskControl:
    spec = MethodSpec(
        id="risk_control", version=1,
        applicability=(
            QuestionShape(T.Interrogative.WHAT, T.Kind.RISK),
            QuestionShape(T.Interrogative.WHAT, T.Kind.CONTROL),
        ),
        answers=(T.Interrogative.WHAT,),
        required_inputs=(
            InputSpec("actions", T.Kind.ACTION,
                      why_needed="risk is raised against what the engagement has proposed to do"),
        ),
        optional_inputs=(
            InputSpec("recommendations", T.Kind.RECOMMENDATION, min_count=0,
                      why_needed="the other half of what has been proposed"),
            InputSpec("stakeholders", T.Kind.STAKEHOLDER, min_count=0, why_needed="who could feel a risk"),
            InputSpec("owners", T.Kind.OWNER, min_count=0, why_needed="who could run a control"),
        ),
        execution=T.ExecutionType.MODEL_ASSISTED,
        output_kinds=(T.Kind.RISK, T.Kind.CONTROL),
        output_schema=GenericReply,
        evidence=EvidenceRequirement(),
        limitations=("raises risk against what the engagement has proposed; it scores no probability "
                     "and prices no exposure",),
        validators=(),
        cost_class=2, max_model_calls=1)

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        _, decision_id, weight = issue_frame(ctx)
        subjects: list[T.Entity] = live(view, T.Kind.ACTION) + live(view, T.Kind.RECOMMENDATION)
        parties: list[T.Entity] = []
        for kind in BEARER_KINDS:
            parties.extend(live(view, kind))
        if not subjects:
            # RK3: nothing has been proposed, so there is nothing to be at risk
            # of. A generic risk list here would be about the industry, not the
            # engagement.
            q = T.QuestionPayload(
                text="What has been decided or planned so far that a risk could attach to?",
                asks_for=(T.AsksFor(T.Kind.ACTION),), issue_ids=ctx.issue_ids,
                why="risk is raised against what the engagement has proposed, not in general",
                effort=T.EffortClass.OFFHAND, strategy=T.FillStrategy.ASK_CLIENT)
            return MethodResult(questions=(q,))

        inputs = subjects + parties + live(view, T.Kind.RISK)
        reply, call_id, fails = propose(
            ctx, self.spec, purpose="raise the risks in what has been proposed and the controls that catch them",
            inputs=inputs, instructions=_INSTRUCTIONS)
        if reply is None:
            return MethodResult(findings=fails)

        permitted = frozenset(e.id for e in inputs)
        by_id = {e.id: e for e in inputs}
        findings: list[T.Finding] = []
        deltas: list[T.EntityDelta] = []

        risk_outputs = [o for o in reply.outputs if o.kind == "risk"]
        risk_ids = fresh_ids(view, T.Kind.RISK, len(risk_outputs))
        refmap: dict[str, str] = {}
        for out, rid in zip(risk_outputs, risk_ids):
            ref = str(out.fields.get("ref") or "").strip()
            if ref:
                refmap[ref] = rid

        cursor = iter(risk_ids)
        for out in reply.outputs:
            ids = cited(out, permitted)
            if not ids:
                findings.append(refusal(self.spec.id, "uncited_output", out.kind or "output",
                                        "the model cited no registered input"))
                if out.kind == "risk":
                    next(cursor, None)          # keep refs aligned with pre-assigned ids
                continue
            coined = coined_figures([out.text], [display_text(by_id.get(i)) for i in ids])
            if coined:
                findings.append(refusal(self.spec.id, "invented_figure", out.kind or "output",
                                        f"figure(s) {', '.join(coined)} appear in no cited input"))
                if out.kind == "risk":
                    next(cursor, None)
                continue
            if out.kind == "risk":
                rid = next(cursor, None)
                bearer = bearer_of(out.fields.get("who_feels_it"), by_id)
                if bearer is None:
                    findings.append(refusal(self.spec.id, "risk_without_bearer", rid or out.text or "risk",
                                            "the risk names no registered party that feels it"))
                    continue
                payload = T.RiskPayload(
                    text=out.text, who_feels_it=bearer,
                    # An unknown likelihood stays "unknown": a model's guess at
                    # a probability is not evidence of one (spec section 7).
                    likelihood=level_or_unknown(out.fields.get("likelihood")),
                    impact=level_or_unknown(out.fields.get("impact")))
                e = new_entity(ctx, T.Kind.RISK, payload, derived_from=ids,
                               relation=T.RelationToCentralDecision.CONSTRAINS,
                               confidence=T.Confidence(None, "model_estimate"),
                               decision_id=decision_id, weight=weight, model_call_id=call_id)
                deltas.append(T.Add(with_id(e, rid) if rid else e))
            elif out.kind == "control":
                # RK2: the risks a control answers, resolved from refs written
                # in this run or RISK ids already registered.
                named = [refmap.get(r, r) for r in _split_refs(out.fields.get("risks"))]
                risks = tuple(dict.fromkeys(
                    r for r in named
                    if r in refmap.values() or (by_id.get(r) is not None and by_id[r].kind is T.Kind.RISK)))
                if not risks:
                    findings.append(refusal(self.spec.id, "control_without_risk", out.text or "control",
                                            "the control names no risk it answers"))
                    continue
                owner = by_id.get(str(out.fields.get("owner_id") or "").strip())
                payload = T.ControlPayload(text=out.text, risk_ids=risks,
                                           owner_id=owner.id if owner is not None
                                           and owner.kind in BEARER_KINDS else None)
                deltas.append(T.Add(new_entity(ctx, T.Kind.CONTROL, payload,
                                               derived_from=tuple(dict.fromkeys(ids)),
                                               relation=T.RelationToCentralDecision.CONSTRAINS,
                                               confidence=T.Confidence(None, "model_estimate"),
                                               decision_id=decision_id, weight=weight,
                                               model_call_id=call_id)))
            else:
                findings.append(refusal(self.spec.id, "undeclared_kind", out.kind or "output",
                                        "an output outside the declared kinds is dropped"))
        return MethodResult(deltas=tuple(deltas), questions=reply_questions(reply, ctx),
                            findings=tuple(findings),
                            model_call_ids=(call_id,) if call_id else ())


LEVELS: tuple[str, ...] = ("high", "medium", "low")


def level_or_unknown(value: Any) -> str:
    """A likelihood or impact band. Not an enum in the payload contract, so the
    closed set is applied here; anything else is "unknown", which is what the
    inputs actually said."""
    v = str(value or "").strip().lower()
    return v if v in LEVELS else "unknown"


def _v_risk_names_a_bearer(view, result: MethodResult) -> list[T.Finding]:
    """RK1 re-checked on the finished result: no RISK lands with an empty
    bearer. A risk nobody feels cannot be owned, mitigated or accepted."""
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not T.Kind.RISK:
            continue
        if not (e.payload.who_feels_it or "").strip():
            out.append(T.Finding(law="M.risk_control.risk_without_bearer", where=e.id or "risk",
                                 issue="a risk names nobody who feels it",
                                 fix="name the registered stakeholder, owner or decision owner who bears it"))
    return out


def _v_control_cites_a_risk(view, result: MethodResult) -> list[T.Finding]:
    """RK2 re-checked: every CONTROL names at least one risk, and every risk it
    names is a RISK - registered already or written in this same result."""
    written = {d.entity.id: d.entity for d in result.deltas
               if getattr(d, "entity", None) is not None and d.entity.id}
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not T.Kind.CONTROL:
            continue
        if not e.payload.risk_ids:
            out.append(T.Finding(law="M.risk_control.control_without_risk", where=e.id or "control",
                                 issue="a control answers no risk",
                                 fix="cite the RISK the control is there to catch"))
            continue
        for rid in e.payload.risk_ids:
            target = written.get(rid) or view.get(rid)
            if target is None or target.kind is not T.Kind.RISK:
                out.append(T.Finding(law="M.risk_control.control_without_risk", where=e.id or "control",
                                     issue=f"the control names {rid}, which is not a registered risk",
                                     fix="cite a RISK the registry holds"))
    return out


RiskControl.spec = replace(RiskControl.spec, validators=(require_citations("risk_control"),
                                                         _v_risk_names_a_bearer,
                                                         _v_control_cites_a_risk))
register(RiskControl)
