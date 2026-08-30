"""operating_model - how the work runs once the capabilities exist (design 7.3
row operating_model): HOW on CAPABILITY of class PROCESS or
GOVERNANCE_AND_CONTROL.

MODEL_ASSISTED with two calls, through the shared plumbing in org_design.py.

Laws this module enforces, each in the docstring of the thing enforcing it:

  OM1 an ACTION carries the class of a capability it cites, never the model's
      word for it (MF1.3). The class is what the process/people predicates in
      the work-product plan read; letting a model set it would let prose
      decide which deliverables an engagement gets (class_of_cited,
      _v_action_class_from_inputs).
  OM2 a WORKSTREAM's capability_classes are the classes of the capabilities it
      cites - a lane covers what it was built out of, and nothing else
      (run(), _v_workstream_classes_from_inputs).
  OM3 every output cites its inputs and coins no figure: an operating model
      that states a volume, a headcount or a cost the engagement never
      recorded is inventing the very thing it claims to describe.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Sequence

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


_DECLARED: tuple[T.CapabilityClass, ...] = (T.CapabilityClass.PROCESS,
                                            T.CapabilityClass.GOVERNANCE_AND_CONTROL)

_INSTRUCTIONS = """Design how this work runs day to day, out of the capabilities above.
- "workstream" outputs group the capabilities into lanes of work. fields: "name",
  "ref" (a short label like W1 so other outputs can point at this lane).
- "action" outputs are the steps that stand a lane up. fields: "horizon"
  (days | weeks | months), "workstream" (the ref of a lane above).
- "governance" outputs say how the lanes are steered. fields: "forum", "cadence".
Every output cites the capability ids it rests on. State no volume, headcount, cost
or duration that no input carries; if the design needs one, ask for it as a question."""


def class_of_cited(ids: Sequence[str], by_id: dict[str, T.Entity],
                   fallback: T.CapabilityClass) -> T.CapabilityClass:
    """OM1: the capability class an output inherits - the class of the first
    CAPABILITY it cites, in citation order, and the shape's own class when it
    cites none. Derived from ids, so scrambling every text field leaves it
    unchanged; a model that writes "capability_class": "financial" on a
    process step changes nothing."""
    for i in ids:
        e = by_id.get(i)
        if e is not None and e.kind is T.Kind.CAPABILITY:
            return e.payload.capability_class
    return fallback


class OperatingModel:
    spec = MethodSpec(
        id="operating_model", version=1,
        applicability=(
            QuestionShape(T.Interrogative.HOW, T.Kind.CAPABILITY,
                          capability_class=T.CapabilityClass.PROCESS),
            QuestionShape(T.Interrogative.HOW, T.Kind.CAPABILITY,
                          capability_class=T.CapabilityClass.GOVERNANCE_AND_CONTROL),
        ),
        answers=(T.Interrogative.HOW,),
        required_inputs=(
            # Two, because an operating model is how capabilities work
            # together; one capability is a capability, not a model.
            InputSpec("capabilities", T.Kind.CAPABILITY, min_count=2,
                      why_needed="an operating model arranges capabilities; it needs more than one"),
        ),
        optional_inputs=(
            InputSpec("owners", T.Kind.OWNER, min_count=0, why_needed="who runs the lanes"),
            InputSpec("process_steps", T.Kind.PROCESS_STEP, min_count=0,
                      why_needed="how the work runs today"),
        ),
        execution=T.ExecutionType.MODEL_ASSISTED,
        output_kinds=(T.Kind.WORKSTREAM, T.Kind.GOVERNANCE, T.Kind.ACTION),
        output_schema=GenericReply,
        evidence=EvidenceRequirement(),
        limitations=("arranges the registered capabilities into lanes and governance; "
                     "it sizes nothing and staffs nothing",),
        validators=(),
        cost_class=2, max_model_calls=2)

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        issue, decision_id, weight = issue_frame(ctx)
        fallback = _DECLARED[0]
        if issue is not None and issue.payload.capability_class is not None:
            fallback = issue.payload.capability_class

        caps = live(view, T.Kind.CAPABILITY)
        owners = live(view, T.Kind.OWNER)
        steps = live(view, T.Kind.PROCESS_STEP)
        if len(caps) < 2:
            # An operating model over one capability would be an arrangement
            # of nothing; the hole is asked rather than filled with a shape.
            q = T.QuestionPayload(
                text="Which other capabilities does this one have to work with?",
                asks_for=(T.AsksFor(T.Kind.CAPABILITY),), issue_ids=ctx.issue_ids,
                why="an operating model arranges capabilities; it needs more than one",
                effort=T.EffortClass.OFFHAND, strategy=T.FillStrategy.ASK_CLIENT)
            return MethodResult(questions=(q,))

        inputs = caps + owners + steps
        reply, call_id, fails = propose(
            ctx, self.spec, purpose="arrange the registered capabilities into lanes, steps and governance",
            inputs=inputs, instructions=_INSTRUCTIONS)
        if reply is None:
            return MethodResult(findings=fails)

        permitted = frozenset(e.id for e in inputs)
        by_id = {e.id: e for e in inputs}
        findings: list[T.Finding] = []
        deltas: list[T.EntityDelta] = []

        ws_outputs = [o for o in reply.outputs if o.kind == "workstream"]
        ws_ids = fresh_ids(view, T.Kind.WORKSTREAM, len(ws_outputs))
        refmap: dict[str, str] = {}
        for out, wid in zip(ws_outputs, ws_ids):
            ref = str(out.fields.get("ref") or "").strip()
            if ref:
                refmap[ref] = wid

        cursor = iter(ws_ids)
        for out in reply.outputs:
            ids = cited(out, permitted)
            if not ids:
                findings.append(refusal(self.spec.id, "uncited_output", out.kind or "output",
                                        "the model cited no registered input"))
                if out.kind == "workstream":
                    next(cursor, None)          # keep refs aligned with pre-assigned ids
                continue
            texts = [out.text] + [str(v) for k, v in out.fields.items()
                                  if k in ("name", "forum", "cadence")]
            coined = coined_figures(texts, [display_text(by_id.get(i)) for i in ids])
            if coined:
                findings.append(refusal(self.spec.id, "invented_figure", out.kind or "output",
                                        f"figure(s) {', '.join(coined)} appear in no cited input"))
                if out.kind == "workstream":
                    next(cursor, None)
                continue
            if out.kind == "workstream":
                wid = next(cursor, None)
                # OM2: the lane covers the classes of the capabilities it was
                # built out of, in a deterministic order.
                classes = tuple(dict.fromkeys(
                    by_id[i].payload.capability_class for i in ids
                    if by_id.get(i) is not None and by_id[i].kind is T.Kind.CAPABILITY))
                payload = T.WorkstreamPayload(name=str(out.fields.get("name") or out.text),
                                              purpose=out.text, capability_classes=classes)
                e = new_entity(ctx, T.Kind.WORKSTREAM, payload, derived_from=ids,
                               relation=T.RelationToCentralDecision.INFORMS,
                               confidence=T.Confidence(None, "model_estimate"),
                               decision_id=decision_id, weight=weight, model_call_id=call_id)
                deltas.append(T.Add(with_id(e, wid) if wid else e))
            elif out.kind == "action":
                payload = T.ActionPayload(
                    text=out.text,
                    capability_class=class_of_cited(ids, by_id, fallback),
                    horizon=parse_enum(T.Horizon, out.fields.get("horizon"), T.Horizon.WEEKS))
                deltas.append(T.Add(new_entity(ctx, T.Kind.ACTION, payload, derived_from=ids,
                                               relation=T.RelationToCentralDecision.INFORMS,
                                               confidence=T.Confidence(None, "model_estimate"),
                                               decision_id=decision_id, weight=weight,
                                               model_call_id=call_id)))
            elif out.kind == "governance":
                payload = T.GovernancePayload(text=out.text, forum=str(out.fields.get("forum") or ""),
                                              cadence=str(out.fields.get("cadence") or ""))
                deltas.append(T.Add(new_entity(ctx, T.Kind.GOVERNANCE, payload, derived_from=ids,
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


def _v_action_class_from_inputs(view, result: MethodResult) -> list[T.Finding]:
    """OM1 re-checked: every ACTION written carries a CapabilityClass member,
    and where it cites a CAPABILITY the class is that capability's. The type
    system requires a class; this law requires the cited one."""
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not T.Kind.ACTION:
            continue
        if not isinstance(e.payload.capability_class, T.CapabilityClass):
            out.append(T.Finding(law="M.operating_model.action_class", where=e.id or "action",
                                 issue="an action carries no capability class",
                                 fix="take the class from a capability the action cites"))
            continue
        classes = {c.payload.capability_class for c in
                   (view.get(i) for i in e.provenance.derived_from)
                   if c is not None and c.kind is T.Kind.CAPABILITY}
        if classes and e.payload.capability_class not in classes:
            out.append(T.Finding(
                law="M.operating_model.action_class", where=e.id or "action",
                issue=f"the action is filed as {e.payload.capability_class.value}, "
                      f"which no capability it cites carries",
                fix="take the class from a capability the action cites"))
    return out


def _v_workstream_classes_from_inputs(view, result: MethodResult) -> list[T.Finding]:
    """OM2 re-checked: a lane covers exactly the classes of the capabilities it
    cites. A class nothing in the lane supports would put work in the plan that
    the engagement never established was in scope."""
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not T.Kind.WORKSTREAM:
            continue
        cited_classes = {c.payload.capability_class for c in
                         (view.get(i) for i in e.provenance.derived_from)
                         if c is not None and c.kind is T.Kind.CAPABILITY}
        extra = sorted(c.value for c in e.payload.capability_classes if c not in cited_classes)
        if cited_classes and extra:
            out.append(T.Finding(
                law="M.operating_model.workstream_class", where=e.id or "workstream",
                issue=f"the lane claims {', '.join(extra)}, which no capability it cites carries",
                fix="list only the classes of the capabilities the lane is built from"))
    return out


OperatingModel.spec = replace(OperatingModel.spec, validators=(require_citations("operating_model"),
                                                               _v_action_class_from_inputs,
                                                               _v_workstream_classes_from_inputs))
register(OperatingModel)
