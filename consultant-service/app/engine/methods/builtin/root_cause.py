"""root_cause - WHY on a FACT or an OBJECTIVE, causal: propose the causes the
registered evidence can carry, and ask for what would test them.

The family's shared machinery lives in capability_gap.py (design 2 ships one
file per method); this module adds the three laws that are specific to causal
reasoning, because a cause is the one output a reader will act on without
being able to see what it rests on:

  R1  a cause is a registered FACT this run was shown, by id. A hypothesis
      whose "causes" are words is a story: nothing can later confirm or
      refute it, and no gate can trace the recommendation that rests on it
      (spec section 7: every recommendation traces to evidence).
  R2  two hypotheses may not rest on the identical set of causes. One issue
      explained twice by the same facts is one hypothesis worded twice; kept
      as two it doubles that explanation's apparent weight in every count
      and every page that ranks causes.
  R3  a figure in the hypothesis prose that appears in no cited input is
      refused. HypothesisPayload carries no Quantity, so the typed
      forbid_new_quantities door does not apply here - the number would ride
      out in the sentence instead. Mutation partner: deleting the
      coined_figures check lets root_cause emit a coined number.

Every hypothesis is written verdict "untested": a method that could rule its
own hypothesis supported would be its own judge. The typed hole that leaves
is asked - one QUESTION per untested hypothesis, naming the causes whose
evidence would settle it (design 7.3, "untested -> question").
"""
from __future__ import annotations

from app.engine import types as T
from app.engine.methods.builtin.capability_gap import (
    ProposedOutput,
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


def _cause_ids(o: ProposedOutput, cited: tuple[str, ...], inputs: dict[str, T.Entity]) -> tuple[str, ...]:
    """The causes a proposal names, kept only where they are FACT ids this run
    was shown AND ids the output itself cites (R1). A cause the output did not
    cite would put the fact behind the claim outside its own lineage, so
    support_closure could never reach it."""
    raw = o.fields.get("causes")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        raw = []
    return tuple(dict.fromkeys(
        c for c in raw
        if isinstance(c, str) and c in cited and (e := inputs.get(c)) is not None and e.kind is T.Kind.FACT))


def _v_causes_are_registered_facts(view, result: MethodResult) -> list[T.Finding]:
    """R1, re-checked on the finished result: every cause is a live FACT the
    row also cites. Absence decides nothing here - a cause id the view cannot
    resolve (a scoped specialist window hides rows) is not condemned; only a
    cause that resolves to something other than a fact, or that the row never
    cited, is a finding."""
    out: list[T.Finding] = []
    for h in added_of(result, T.Kind.HYPOTHESIS):
        cited = set(h.provenance.derived_from)
        if not h.payload.causes:
            out.append(T.Finding(law="M.root_cause.uncited_cause", where=h.id or h.kind.value,
                                 issue="a hypothesis names no cause among the entities it cites",
                                 fix="name the registered fact ids the cause rests on, or write a question instead",
                                 entity_ids=(h.id,) if h.id else ()))
            continue
        for c in h.payload.causes:
            resolved = view.get(c)
            if c not in cited or (resolved is not None and resolved.kind is not T.Kind.FACT):
                out.append(T.Finding(law="M.root_cause.uncited_cause", where=h.id or h.kind.value,
                                     issue=f"cause {c!r} is not a registered fact this hypothesis cites",
                                     fix="a cause is a FACT id in the hypothesis' own derived_from",
                                     entity_ids=(h.id,) if h.id else ()))
    return out


def _v_distinct_cause_sets(view, result: MethodResult) -> list[T.Finding]:
    """R2. Compared against the hypotheses already live on the same issue as
    well as against each other, so a second run cannot re-propose the first
    run's explanation under new words."""
    seen: dict[tuple[str, frozenset], str] = {}
    for e in view.query(T.Kind.HYPOTHESIS):
        if e.status not in T.TERMINAL_STATUSES and e.payload.causes:
            seen.setdefault((e.payload.issue_id, frozenset(e.payload.causes)), e.id)
    out: list[T.Finding] = []
    for h in added_of(result, T.Kind.HYPOTHESIS):
        key = (h.payload.issue_id, frozenset(h.payload.causes))
        if not h.payload.causes:
            continue
        first = seen.get(key)
        if first is not None:
            out.append(T.Finding(law="M.root_cause.duplicate_cause_set", where=h.id or h.kind.value,
                                 issue=f"the same causes already explain this issue in {first}",
                                 fix="one explanation is one hypothesis; word it once or name different causes",
                                 entity_ids=tuple(x for x in (h.id, first) if x)))
        else:
            seen[key] = h.id or "this result"
    return out


SPEC = MethodSpec(
    id="root_cause",
    version=1,
    # Causal only: a WHY node that is not marked causal is asking for a
    # rationale, not a mechanism, and this method would answer the wrong
    # question with the right shape.
    applicability=(QuestionShape(T.Interrogative.WHY, T.Kind.FACT, causal=True),
                   QuestionShape(T.Interrogative.WHY, T.Kind.OBJECTIVE, causal=True)),
    answers=(T.Interrogative.WHY,),
    required_inputs=(
        # Two evidenced facts, not one: a single fact is the symptom, and a
        # cause proposed from it alone rests on nothing but the model's prior.
        InputSpec("evidenced_facts", T.Kind.FACT,
                  filter={"basis": [T.FactBasis.CLIENT_STATED, T.FactBasis.DOCUMENT_VERIFIED]},
                  min_count=2, effort=T.EffortClass.OFFHAND,
                  why_needed="a cause is proposed from what the client stated or a document verifies, never from prose"),
    ),
    optional_inputs=(
        InputSpec("objectives", T.Kind.OBJECTIVE, min_count=1),
        InputSpec("hypotheses", T.Kind.HYPOTHESIS, min_count=1),
    ),
    execution=T.ExecutionType.MODEL_ASSISTED,
    output_kinds=(T.Kind.HYPOTHESIS, T.Kind.QUESTION),
    output_schema=ProposalSheet,
    evidence=EvidenceRequirement(),
    limitations=("proposes causes and what would test them; it never rules one supported",),
    validators=(
        cites_validator("root_cause"),
        copied_quantity_validator("root_cause"),
        _v_causes_are_registered_facts,
        _v_distinct_cause_sets,
    ),
    cost_class=2,
    max_model_calls=2,
)

_INSTRUCTIONS = (
    "Propose one hypothesis per distinct causal mechanism the inputs can carry. Each output's "
    "fields carry 'causes': the list of FACT ids that show the cause, all of which must also "
    "appear in that output's derived_from. Two hypotheses may not name the same set of causes. "
    "Where the inputs cannot carry a cause, return a question naming the evidence that would "
    "settle it instead of a hypothesis."
)


def _test_question(issue: T.Entity, hypothesis_text: str, causes: tuple[str, ...]) -> T.QuestionPayload:
    """The typed hole an untested hypothesis leaves. Naming the causes makes
    the ask answerable: the client is asked for the evidence that would settle
    this explanation, not for an opinion on whether it is right."""
    named = ", ".join(causes)
    return T.QuestionPayload(
        text=f"What evidence would confirm or refute this cause: {hypothesis_text}",
        asks_for=(T.AsksFor(T.Kind.FACT),),
        issue_ids=(issue.id,),
        why=f"the hypothesis is untested; it rests on {named}",
        effort=T.EffortClass.LOOKUP,
        strategy=T.FillStrategy.ASK_CLIENT)


@register
class RootCauseMethod:
    spec = SPEC

    def run(self, ctx: MethodContext) -> MethodResult:
        proposal = model_proposals(
            ctx, self.spec,
            "propose the causes the registered evidence can carry, and what would test them",
            _INSTRUCTIONS)
        if proposal.failure is not None:
            return proposal.failure
        findings: list[T.Finding] = []
        deltas: list[T.Add] = []
        questions: list[T.QuestionPayload] = list(question_payloads(proposal))
        by_id = proposal.inputs_by_id
        issue = proposal.issue
        # R2 at source as well as in the validator: the run refuses to write
        # the duplicate at all, so the registry never holds two rows one
        # supersession would have to untangle.
        seen: set[frozenset] = {frozenset(e.payload.causes) for e in ctx.registry.query(T.Kind.HYPOTHESIS)
                                if e.status not in T.TERMINAL_STATUSES and e.payload.issue_id == issue.id
                                and e.payload.causes}
        for i, o, kind, derived, _q in admitted(self.spec, proposal, findings):
            if kind is not T.Kind.HYPOTHESIS:
                continue
            text = o.text.strip()
            if not text:
                findings.append(dropped(self.spec.id, i, "a hypothesis without wording says nothing"))
                continue
            causes = _cause_ids(o, derived, by_id)
            if not causes:
                # R1: no registered fact behind the claim, so there is nothing
                # to confirm or refute. The words are refused, not softened.
                findings.append(dropped(self.spec.id, i, "no cause among the cited facts", law="uncited_cause"))
                continue
            coined = coined_figures([text], [wording(by_id[c]) for c in derived if c in by_id])
            if coined:
                # R3: the figure exists nowhere upstream. Dropping the whole
                # hypothesis is deliberate - stripping the number would leave
                # a sentence the model did not write.
                findings.append(dropped(self.spec.id, i,
                                        f"figure(s) {', '.join(coined)} appear in no cited input",
                                        law="coined_quantity"))
                continue
            key = frozenset(causes)
            if key in seen:
                findings.append(dropped(self.spec.id, i, "these causes already explain this issue",
                                        law="duplicate_cause_set"))
                continue
            seen.add(key)
            payload = T.HypothesisPayload(text=text, issue_id=issue.id, causes=causes,
                                          predicts=(), verdict="untested")
            deltas.append(T.Add(proposed_entity(ctx, issue, kind, payload, derived,
                                                proposal.response.call_id)))
            questions.append(_test_question(issue, text, causes))
        return MethodResult(deltas=tuple(deltas), questions=tuple(questions), findings=tuple(findings),
                            model_call_ids=(proposal.response.call_id,))


__all__ = ["SPEC", "RootCauseMethod"]
