"""stakeholder - WHO on a STAKEHOLDER or a DECISION_OWNER: name the people
the decision runs through, and only the ones the record already contains.

The family's shared machinery lives in capability_gap.py. Two laws are
specific to naming people, because a named person is the output a reader is
least able to check and most likely to act on:

  K1  a name traces to a source the engagement holds - a conversation turn or
      a document - through the entities the output cites. A model asked who
      the stakeholders are will always produce a plausible cast; a page that
      prints an invented head of operations is the same failure as an
      invented number, minus the digits (spec section 7: unknown information
      remains unknown). Mutation partner: _v_named_from_a_source.
      Absence decides nothing: when a cited id does not resolve in this view
      (a scoped specialist window legitimately hides rows) the row is left
      alone rather than condemned.
  K2  influence is one of a closed list. StakeholderPayload.influence is a
      string field, so nothing in the type system stops "very high" or
      "kingmaker" from reaching a page and being sorted against "high"; the
      vocabulary is enforced here and re-checked by a validator.

Everything the model returns is PROPOSED, as with every model-assisted
method: a stakeholder map is a claim about the client's organisation, and the
client is the authority on it (AUTHORITY_OF: CLIENT_PREFERENCE).
"""
from __future__ import annotations

from typing import Any

from app.engine import types as T
from app.engine.methods.builtin.capability_gap import (
    ProposalSheet,
    added_of,
    admitted,
    cites_validator,
    coined_figures,
    copied_quantity_validator,
    dropped,
    model_proposals,
    proposed_entity,
    question_payloads,
    wording,
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

# The closed vocabulary of StakeholderPayload.influence (types.py:519). Held
# here as a tuple rather than an enum because the payload is frozen contract:
# the vocabulary is enforced at the only place that writes the field.
INFLUENCE_VALUES: tuple[str, ...] = ("high", "medium", "low", "unknown")

# The kinds that ARE the record: a name is traceable when the row it cites is
# one of these, or rests on one.
_SOURCE_KINDS: frozenset[T.Kind] = frozenset({T.Kind.EVIDENCE_SOURCE})


def influence_of(value: Any) -> str:
    """The stated influence, or "unknown". Unknown is a real answer and the
    payload's own default; a model's unrecognised word is absence, never a
    rank the engagement gets to sort by (K2)."""
    text = str(value).strip().lower() if value is not None else ""
    return text if text in INFLUENCE_VALUES else "unknown"


def _reaches_a_source(view, entity: T.Entity) -> bool | None:
    """Whether the row traces to an EVIDENCE_SOURCE through what it cites, or
    None when this view cannot tell. One hop is enough: the objectives and
    context a stakeholder analysis is given were themselves written citing
    the turn or document they came from, so a name resting on them rests on
    the record."""
    unresolved = False
    for cid in entity.provenance.derived_from:
        cited = view.get(cid)
        if cited is None:
            unresolved = True
            continue
        if cited.kind in _SOURCE_KINDS:
            return True
        for parent_id in cited.provenance.derived_from:
            parent = view.get(parent_id)
            if parent is None:
                unresolved = True
            elif parent.kind in _SOURCE_KINDS:
                return True
    return None if unresolved else False


def _v_named_from_a_source(view, result: MethodResult) -> list[T.Finding]:
    """K1 on the finished result: a person this method names traces to a turn
    or a document. A row whose lineage this view cannot follow is left
    alone - absent evidence is not evidence of a defect."""
    out: list[T.Finding] = []
    for e in added_of(result, T.Kind.STAKEHOLDER) + added_of(result, T.Kind.OWNER):
        if _reaches_a_source(view, e) is False:
            out.append(T.Finding(law="M.stakeholder.name_without_source", where=e.id or e.kind.value,
                                 issue="a person is named by rows that rest on no turn and no document",
                                 fix="name only people the record contains; otherwise ask who they are",
                                 entity_ids=(e.id,) if e.id else ()))
    return out


def _v_influence_vocabulary(view, result: MethodResult) -> list[T.Finding]:
    """K2 on the finished result. A word outside the list is not a stronger
    ranking, it is an unsortable one."""
    return [T.Finding(law="M.stakeholder.influence_vocabulary", where=e.id or e.kind.value,
                      issue=f"influence {e.payload.influence!r} is outside {list(INFLUENCE_VALUES)}",
                      fix="influence is one of the closed list, and unknown when the inputs do not settle it",
                      entity_ids=(e.id,) if e.id else ())
            for e in added_of(result, T.Kind.STAKEHOLDER) if e.payload.influence not in INFLUENCE_VALUES]


SPEC = MethodSpec(
    id="stakeholder",
    version=1,
    applicability=(QuestionShape(T.Interrogative.WHO, T.Kind.STAKEHOLDER),
                   QuestionShape(T.Interrogative.WHO, T.Kind.DECISION_OWNER)),
    answers=(T.Interrogative.WHO,),
    required_inputs=(
        InputSpec("context", T.Kind.BUSINESS_CONTEXT, min_count=1, effort=T.EffortClass.OFFHAND,
                  why_needed="who matters is a function of what the organisation does and how it is structured"),
        InputSpec("decisions", T.Kind.DECISION, min_count=1, effort=T.EffortClass.OFFHAND,
                  why_needed="a stakeholder map is drawn around a decision, not around an organisation chart"),
    ),
    optional_inputs=(
        InputSpec("sources", T.Kind.EVIDENCE_SOURCE, min_count=1),
        InputSpec("stakeholders", T.Kind.STAKEHOLDER, min_count=1),
        InputSpec("owners", T.Kind.OWNER, min_count=1),
    ),
    execution=T.ExecutionType.MODEL_ASSISTED,
    output_kinds=(T.Kind.STAKEHOLDER, T.Kind.OWNER, T.Kind.QUESTION),
    output_schema=ProposalSheet,
    evidence=EvidenceRequirement(),
    limitations=("names people the record already contains; it does not assess them",),
    validators=(
        cites_validator("stakeholder"),
        copied_quantity_validator("stakeholder"),
        _v_named_from_a_source,
        _v_influence_vocabulary,
    ),
    cost_class=1,
    max_model_calls=1,
)

_INSTRUCTIONS = (
    "Name only people the cited inputs already contain. Each output's fields carry 'name', "
    "'role', 'interest' and 'influence' (one of: " + " | ".join(INFLUENCE_VALUES) + "). Where a "
    "role clearly matters but the inputs name nobody in it, return a question asking who holds "
    "it rather than an output naming a person."
)


@register
class StakeholderMethod:
    spec = SPEC

    def run(self, ctx: MethodContext) -> MethodResult:
        proposal = model_proposals(
            ctx, self.spec, "name the people the decision runs through, from the record only", _INSTRUCTIONS)
        if proposal.failure is not None:
            return proposal.failure
        findings: list[T.Finding] = []
        deltas: list[T.Add] = []
        by_id = proposal.inputs_by_id
        for i, o, kind, derived, _q in admitted(self.spec, proposal, findings):
            name = str(o.fields.get("name") or o.text).strip()
            role = str(o.fields.get("role") or "").strip()
            if not name:
                findings.append(dropped(self.spec.id, i, "a person without a name is not a stakeholder"))
                continue
            coined = coined_figures([name, role, o.text], [wording(by_id[c]) for c in derived if c in by_id])
            if coined:
                # A headcount or a budget riding out on a role line is a claim
                # the engagement never established, exactly as it would be in a
                # quantity field (no path from prose to a coined figure).
                findings.append(dropped(self.spec.id, i,
                                        f"figure(s) {', '.join(coined)} appear in no cited input",
                                        law="coined_quantity"))
                continue
            if kind is T.Kind.STAKEHOLDER:
                payload: Any = T.StakeholderPayload(name=name, role=role,
                                                    interest=str(o.fields.get("interest") or "").strip(),
                                                    influence=influence_of(o.fields.get("influence")))
            elif kind is T.Kind.OWNER:
                reports_to = o.fields.get("reports_to")
                payload = T.OwnerPayload(
                    name=name, role=role,
                    # A reporting line to somebody this run was never shown is
                    # a structure the engagement never recorded; the owner
                    # stands, the invented line does not.
                    reports_to=reports_to if isinstance(reports_to, str) and reports_to in by_id else None)
            else:
                continue
            candidate = proposed_entity(ctx, proposal.issue, kind, payload, derived, proposal.response.call_id)
            if _reaches_a_source(ctx.registry, candidate) is False:
                # K1 at source: the name rests on rows that rest on no turn and
                # no document, so the record does not contain this person. The
                # proposal is refused here as well as in the validator - a
                # person the engagement never heard of must not reach a page
                # even as a PROPOSED row somebody could later confirm.
                findings.append(dropped(self.spec.id, i,
                                        "the cited rows rest on no conversation turn and no document",
                                        law="name_without_source"))
                continue
            deltas.append(T.Add(candidate))
        return MethodResult(deltas=tuple(deltas), questions=tuple(question_payloads(proposal)),
                            findings=tuple(findings), model_call_ids=(proposal.response.call_id,))


__all__ = ["SPEC", "StakeholderMethod", "INFLUENCE_VALUES", "influence_of"]
