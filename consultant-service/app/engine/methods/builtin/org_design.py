"""org_design - organisation design on the people side of a capability gap
(design 7.3 row org_design), plus the shared plumbing every design-and-plan
MODEL_ASSISTED method in this family uses (operating_model, systems_data_map,
risk_control, change_impact import from here rather than re-implementing the
same reply handling five times).

Laws this module enforces, each in the docstring of the thing enforcing it:

  - no headcount or salary invention (app/prompts/organization.j2:16 rule,
    generalised): a figure in an output that appears in no cited input is
    refused, because an invented number on an org chart is a claim the
    engagement never established (coined_figures / _lawful_output).
  - every output cites the inputs it rests on (new_entity refuses an empty
    derived_from; require_citations() re-checks a doctored result).
  - every ACTION carries a capability_class member (MF1.3): this method
    writes PEOPLE_AND_ORGANISATION unconditionally - the class is the
    method's declared subject, never the model's choice.

The model words the design; the registry decides it. Everything the model
returns lands as PROPOSED under the method's own provenance.
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Iterable, Mapping, Sequence

from pydantic import Field

from app.engine import types as T
from app.engine.llm import ModelCall, StructuredFailure, structured_call
from app.engine.methods.contract import (
    InputSpec,
    MethodContext,
    MethodResult,
    MethodSpec,
    QuestionShape,
    register,
    new_entity,
    EvidenceRequirement,
)
from app.engine.templating import render
from app.ui_spec import _Tolerant


# =============================================================================
# Shared plumbing for the design-and-plan model-assisted methods
# =============================================================================

class ProposedOutput(_Tolerant):
    """One output row of the method_generic.j2 JSON shape. Tolerant: extra
    keys a model adds are ignored, absent keys stay at their empty defaults
    and the mapping code treats emptiness as absence, never as a value."""
    kind: str = ""
    text: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)
    quantity_from: str | None = None
    derived_from: list[str] = Field(default_factory=list)


class ProposedQuestion(_Tolerant):
    text: str = ""
    asks_for_kind: str = ""
    issue_id: str = ""


class GenericReply(_Tolerant):
    outputs: list[ProposedOutput] = Field(default_factory=list)
    questions: list[ProposedQuestion] = Field(default_factory=list)


def live(view, kind: T.Kind) -> list[T.Entity]:
    """The engagement's current position for one kind. Methods are typed
    against RegistryView, which has query() but not live(); the retirement
    filter therefore lives here, once, instead of in every method body."""
    return [e for e in view.query(kind) if e.status not in T.TERMINAL_STATUSES]


def display_text(e: T.Entity | None) -> str:
    """The one human wording a payload carries, whichever field holds it."""
    if e is None:
        return ""
    for name in ("text", "statement", "name", "question"):
        v = getattr(e.payload, name, None)
        if v:
            return str(v)
    return ""


def prompt_inputs(entities: Sequence[T.Entity]) -> list[dict]:
    out = []
    for e in entities:
        q = getattr(e.payload, "quantity", None)
        out.append({"id": e.id, "kind": e.kind.value, "text": display_text(e),
                    "quantity": f"{q.value} {q.unit}" if q is not None else None})
    return out


def issue_frame(ctx: MethodContext) -> tuple[T.Entity | None, str | None, float]:
    """The issue this run settles, and the decision/weight its outputs attach
    to. When the issue is outside a scoped view the outputs still attach to
    the central decision with the declared INFORMS prior - absence of the
    issue row is never a reason to attach nothing."""
    view = ctx.registry
    issue = view.get(ctx.issue_ids[0]) if ctx.issue_ids else None
    dec = view.central_decision()
    decision_id = dec.id if dec is not None else None
    weight = T.SENSITIVITY[T.RelationToCentralDecision.INFORMS]
    if issue is not None:
        decision_id = issue.relevance.decision_id or decision_id
        weight = issue.relevance.weight or weight
    return issue, decision_id, weight


def _issue_ctx(issue: T.Entity | None, spec: MethodSpec, ctx: MethodContext) -> dict:
    if issue is not None:
        p = issue.payload
        return {"id": issue.id, "text": p.text,
                "interrogative": p.interrogative.value, "target_kind": p.target_kind.value}
    d = spec.applicability[0]
    return {"id": ctx.issue_ids[0] if ctx.issue_ids else "", "text": "",
            "interrogative": d.interrogative.value, "target_kind": d.target_kind.value}


def propose(ctx: MethodContext, spec: MethodSpec, *, purpose: str, inputs: Sequence[T.Entity],
            instructions: str) -> tuple[GenericReply | None, str | None, tuple[T.Finding, ...]]:
    """One structured model call through the shared method_generic prompt.
    A StructuredFailure is a finding, never a default: the run produced
    nothing and says so, and the ANALYSIS row stays where it was."""
    issue, _, _ = issue_frame(ctx)
    prompt = render("method_generic.j2", method_id=spec.id, method_purpose=purpose,
                    issue=_issue_ctx(issue, spec, ctx), inputs=prompt_inputs(inputs),
                    assumption_grants=[], output_kinds=spec.output_kinds, instructions=instructions)
    call = ModelCall(purpose=f"method:{spec.id}", messages=({"role": "user", "content": prompt},),
                     schema=GenericReply, schema_version=spec.output_schema_version,
                     engagement_id=ctx.registry.engagement_id)
    try:
        reply, response = structured_call(ctx.provider, call)
    except StructuredFailure as exc:
        f = T.Finding(law=f"M.{spec.id}.model_failure", where=ctx.issue_ids[0] if ctx.issue_ids else spec.id,
                      issue=f"the model produced no schema-valid reply: {exc}",
                      fix="re-run the analysis; nothing was written",
                      severity=T.Severity.LOW, blocks_final=False)
        return None, None, (f,)
    return reply, response.call_id, ()


def reply_questions(reply: GenericReply, ctx: MethodContext) -> tuple[T.QuestionPayload, ...]:
    out: list[T.QuestionPayload] = []
    for q in reply.questions:
        if not q.text:
            continue
        kind = parse_enum(T.Kind, q.asks_for_kind)
        out.append(T.QuestionPayload(
            text=q.text, asks_for=(T.AsksFor(kind),) if kind is not None else (),
            issue_ids=ctx.issue_ids, why="a design method found a needed input missing",
            effort=T.EffortClass.OFFHAND, strategy=T.FillStrategy.ASK_CLIENT))
    return tuple(out)


def parse_enum(enum_cls, value, default=None):
    """A model-supplied enum string, or the default. Never raises: an enum the
    model misspells is absence, and absence gets the declared default, not a
    crash and not a coined member."""
    try:
        return enum_cls(str(value))
    except (ValueError, TypeError):
        return default


def cited(out: ProposedOutput, permitted: frozenset[str]) -> tuple[str, ...]:
    """The derived_from ids that actually name inputs this run was given.
    Anything else - a hallucinated id, an id outside the scope - is silently
    not a citation; an output left with none is dropped by the caller."""
    return tuple(i for i in out.derived_from if i in permitted)


# Registry-style ids ("OWN-3") carry digits that are names, not figures; their
# spans are skipped by the figure scan so a reporting line never reads as an
# invented number. The spans are skipped rather than substituted away: no
# module outside corrections.py rewrites text, so this file reads and never
# re-renders (design 14, "broad regex and prose replacement are prohibited").
_ID_TOKEN_RE = re.compile(r"\b[A-Z]{2,4}-\d+\b")
_FIGURE_RE = re.compile(r"\d+(?:[.,]\d+)*")


def coined_figures(texts: Iterable[str], cited_texts: Iterable[str]) -> tuple[str, ...]:
    """Figures in the output prose that appear in no cited input. The org
    chart law (no headcount, no salary invention) is a special case of spec
    section 7: unknown information remains unknown - a number the engagement
    never recorded cannot appear because a model found it plausible."""
    haystack = " ".join(t or "" for t in cited_texts).replace(",", "")
    out: list[str] = []
    for t in texts:
        t = t or ""
        id_spans = [m.span() for m in _ID_TOKEN_RE.finditer(t)]
        for m in _FIGURE_RE.finditer(t):
            if any(start <= m.start() < end for start, end in id_spans):
                continue
            tok = m.group(0)
            if tok.replace(",", "") not in haystack:
                out.append(tok)
    return tuple(dict.fromkeys(out))


def fresh_ids(view, kind: T.Kind, count: int) -> list[str]:
    """Explicit ids assigned ahead of the registry, so outputs created in one
    batch can reference each other (a control cites the risk it mitigates, a
    reporting line names its manager). Computed past every id visible in the
    view; under a scoped view a hidden higher id can collide, in which case
    the registry refuses the whole batch (I6) and the run is redone - an
    admission failure, never a silent overwrite."""
    prefix = T.ID_PREFIX[kind]
    top = 0
    for e in view.query(kind):
        _, _, num = e.id.rpartition("-")
        if num.isdigit():
            top = max(top, int(num))
    return [f"{prefix}-{top + 1 + i}" for i in range(count)]


def with_id(entity: T.Entity, entity_id: str) -> T.Entity:
    return replace(entity, id=entity_id)


def require_citations(method_id: str):
    """Validator: every non-QUESTION Add cites at least one input. new_entity
    already refuses an empty derived_from at construction; this re-checks a
    result assembled some other way, so the law holds on the result, not on
    the courtesy of the producer."""
    def _v(view, result: MethodResult) -> list[T.Finding]:
        out: list[T.Finding] = []
        for d in result.deltas:
            e = getattr(d, "entity", None)
            if e is not None and e.kind != T.Kind.QUESTION and not e.provenance.derived_from:
                out.append(T.Finding(law=f"M.{method_id}.uncited_output", where=e.id or e.kind.value,
                                     issue="an output cites no inputs",
                                     fix="cite the entity ids the output rests on"))
        return out
    return _v


def refusal(method_id: str, slug: str, where: str, issue: str) -> T.Finding:
    """A record that an output was refused before it could land. LOW and
    non-blocking: nothing unsafe was written, and the record exists so the
    refusal is visible instead of silent."""
    return T.Finding(law=f"M.{method_id}.{slug}", where=where, issue=issue,
                     fix="the output was dropped; re-run with better inputs",
                     severity=T.Severity.LOW, blocks_final=False)


# =============================================================================
# The org_design method
# =============================================================================

_INSTRUCTIONS = """Design the people side of the capability gaps above: who owns what, and
what changes for the people already named.
- "owner" outputs are roles on one reporting chart. fields: "name" (the role title,
  or a person already named in the inputs), "role" (what the role covers), "ref"
  (a short label like R1 so other outputs can point at this role), "reports_to"
  (the ref of another owner output, or the id of an OWNER input). Never invent
  hires, headcounts or salaries; a figure that appears in no input is refused.
- "action" outputs are the people-and-organisation steps that stand the chart up.
  fields: "horizon" (days | weeks | months), "owner_id" (the ref or id of the
  responsible owner).
- "governance" outputs say how the chart decides. fields: "forum", "cadence".
Assign work only to roles on the chart or people in the inputs."""


class OrgDesign:
    spec = MethodSpec(
        id="org_design",
        version=1,
        applicability=(QuestionShape(T.Interrogative.HOW, T.Kind.CAPABILITY,
                                     capability_class=T.CapabilityClass.PEOPLE_AND_ORGANISATION),),
        answers=(T.Interrogative.HOW,),
        required_inputs=(
            InputSpec("people_capabilities", T.Kind.CAPABILITY,
                      filter={"capability_class": T.CapabilityClass.PEOPLE_AND_ORGANISATION},
                      why_needed="the gaps the organisation must close"),
        ),
        optional_inputs=(
            InputSpec("owners", T.Kind.OWNER, min_count=0, why_needed="people already accountable"),
            InputSpec("stakeholders", T.Kind.STAKEHOLDER, min_count=0, why_needed="people the design affects"),
        ),
        execution=T.ExecutionType.MODEL_ASSISTED,
        output_kinds=(T.Kind.OWNER, T.Kind.ACTION, T.Kind.GOVERNANCE),
        output_schema=GenericReply,
        evidence=EvidenceRequirement(),
        limitations=("designs roles and reporting lines only; never headcounts, salaries or named hires",),
        validators=(),
        cost_class=2,
        max_model_calls=2,
    )

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        caps = [c for c in live(view, T.Kind.CAPABILITY)
                if c.payload.capability_class is T.CapabilityClass.PEOPLE_AND_ORGANISATION]
        owners = live(view, T.Kind.OWNER)
        stakeholders = live(view, T.Kind.STAKEHOLDER)
        if not owners and not stakeholders:
            # An org design with nobody in it would be pure invention; the
            # gap is a question, never a default cast of characters.
            q = T.QuestionPayload(text="Who currently runs or is affected by this part of the business?",
                                  asks_for=(T.AsksFor(T.Kind.STAKEHOLDER),), issue_ids=ctx.issue_ids,
                                  why="an organisation design needs the people it is for",
                                  effort=T.EffortClass.OFFHAND, strategy=T.FillStrategy.ASK_CLIENT)
            return MethodResult(questions=(q,))

        inputs = caps + owners + stakeholders
        reply, call_id, fails = propose(
            ctx, self.spec, purpose="design roles, reporting lines and governance for the capability gaps",
            inputs=inputs, instructions=_INSTRUCTIONS)
        if reply is None:
            return MethodResult(findings=fails)

        _, decision_id, weight = issue_frame(ctx)
        permitted = frozenset(e.id for e in inputs)
        by_id = {e.id: e for e in inputs}
        findings: list[T.Finding] = []
        deltas: list[T.EntityDelta] = []

        owner_outputs = [o for o in reply.outputs if o.kind == "owner"]
        owner_ids = fresh_ids(view, T.Kind.OWNER, len(owner_outputs))
        refmap: dict[str, str] = {}
        for o, oid in zip(owner_outputs, owner_ids):
            ref = str(o.fields.get("ref") or "").strip()
            if ref:
                refmap[ref] = oid

        def resolve_owner(value: Any) -> str | None:
            v = str(value or "").strip()
            if v in refmap:
                return refmap[v]
            e = by_id.get(v)
            return v if e is not None and e.kind == T.Kind.OWNER else None

        owner_cursor = iter(owner_ids)
        for out in reply.outputs:
            ids = cited(out, permitted)
            if not ids:
                findings.append(refusal(self.spec.id, "uncited_output", out.kind or "output",
                                        "the model cited no registered input"))
                continue
            texts = [out.text] + [str(v) for k, v in out.fields.items()
                                  if k in ("name", "role", "forum", "cadence")]
            coined = coined_figures(texts, [display_text(by_id.get(i)) for i in ids])
            if coined:
                findings.append(refusal(self.spec.id, "invented_figure", out.kind or "output",
                                        f"figure(s) {', '.join(coined)} appear in no cited input; "
                                        "headcounts and salaries are never invented"))
                if out.kind == "owner":
                    next(owner_cursor, None)  # keep refs aligned with pre-assigned ids
                continue
            if out.kind == "owner":
                oid = next(owner_cursor, None)
                payload = T.OwnerPayload(name=str(out.fields.get("name") or out.text),
                                         role=str(out.fields.get("role") or ""),
                                         reports_to=resolve_owner(out.fields.get("reports_to")))
                e = new_entity(ctx, T.Kind.OWNER, payload, derived_from=ids,
                               relation=T.RelationToCentralDecision.INFORMS,
                               confidence=T.Confidence(None, "model_estimate"),
                               decision_id=decision_id, weight=weight, model_call_id=call_id)
                deltas.append(T.Add(with_id(e, oid) if oid else e))
            elif out.kind == "action":
                payload = T.ActionPayload(
                    text=out.text,
                    # MF1.3: the class is the method's declared subject. A model
                    # cannot relabel a people action into another lane.
                    capability_class=T.CapabilityClass.PEOPLE_AND_ORGANISATION,
                    horizon=parse_enum(T.Horizon, out.fields.get("horizon"), T.Horizon.WEEKS),
                    owner_id=resolve_owner(out.fields.get("owner_id")))
                deltas.append(T.Add(new_entity(ctx, T.Kind.ACTION, payload, derived_from=ids,
                                               relation=T.RelationToCentralDecision.INFORMS,
                                               confidence=T.Confidence(None, "model_estimate"),
                                               decision_id=decision_id, weight=weight, model_call_id=call_id)))
            elif out.kind == "governance":
                payload = T.GovernancePayload(text=out.text, forum=str(out.fields.get("forum") or ""),
                                              cadence=str(out.fields.get("cadence") or ""))
                deltas.append(T.Add(new_entity(ctx, T.Kind.GOVERNANCE, payload, derived_from=ids,
                                               relation=T.RelationToCentralDecision.INFORMS,
                                               confidence=T.Confidence(None, "model_estimate"),
                                               decision_id=decision_id, weight=weight, model_call_id=call_id)))
            else:
                findings.append(refusal(self.spec.id, "undeclared_kind", out.kind or "output",
                                        "an output outside the declared kinds is dropped"))
        return MethodResult(deltas=tuple(deltas), questions=reply_questions(reply, ctx),
                            findings=tuple(findings),
                            model_call_ids=(call_id,) if call_id else ())


def _v_actions_people_class(view, result: MethodResult) -> list[T.Finding]:
    """Every ACTION this method wrote carries the PEOPLE_AND_ORGANISATION
    class as an enum member. The type system requires *a* class; this law
    requires the right one, so process/people predicates keep reading truth."""
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is not None and e.kind == T.Kind.ACTION \
                and e.payload.capability_class is not T.CapabilityClass.PEOPLE_AND_ORGANISATION:
            out.append(T.Finding(law="M.org_design.action_class", where=e.id or "action",
                                 issue="an org-design action must be people_and_organisation",
                                 fix="set capability_class to the method's declared subject"))
    return out


def _v_no_invented_figures(view, result: MethodResult) -> list[T.Finding]:
    """Re-check the headcount/salary law on the finished result: any figure in
    an output's prose must exist in something the output cites."""
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None:
            continue
        srcs = [display_text(view.get(i)) for i in e.provenance.derived_from]
        coined = coined_figures([display_text(e)], srcs)
        if coined:
            out.append(T.Finding(law="M.org_design.invented_figure", where=e.id or e.kind.value,
                                 issue=f"figure(s) {', '.join(coined)} appear in no cited input",
                                 fix="remove the figure or register the fact that carries it"))
    return out


OrgDesign.spec = replace(OrgDesign.spec, validators=(require_citations("org_design"),
                                                     _v_actions_people_class,
                                                     _v_no_invented_figures))
register(OrgDesign)
