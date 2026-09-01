"""market_competitor - RESEARCH: what the market and the competitors are,
as external facts that each name the source they came from.

This module also hosts the shared law of the research family (market_sizing
imports it): an external fact carries a citation locator or it is not
written. The component ships one file per method (design 2), so the shared
piece lives in the family's alphabetically first module, which the
registration package imports before its sibling.

Laws this module enforces, and the failure each prevents:

  R1  an external fact is written only with a citation locator - the exact
      passage, page or address the claim came from. Authority for an
      EXTERNAL_FACT is CITED_SOURCE (authority.py: AUTHORITY_OF); a claim
      with no locator names no source, so nothing could ever confirm or
      refute it. It is refused, and the gap becomes a QUESTION for the
      source rather than a page that asserts an unfindable number.
  R2  an external fact is born PROPOSED. Only Actor.EXTERNAL_SOURCE may
      confirm what CITED_SOURCE owns (MAY_CONFIRM), and no actor inside a
      method run is that source: research proposes, the citation decides.
      A method that could confirm its own research would be its own referee.
  R3  a quantity reaches an output only by copying a registered input's
      quantity (admitted() enforces quantity_from), so a market figure the
      model typed into prose never becomes a registered number.

The method reads only registered inputs and writes only FACT and QUESTION,
so a run with nothing to cite writes nothing - absence of external evidence
is a typed hole, never a defect and never a default.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Mapping

from app.engine import types as T
from app.engine.methods.builtin.capability_gap import (
    added_of,
    admitted,
    cites_validator,
    dropped,
    model_proposals,
    new_evidence_remains,
    question_payloads,
)
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

# The closed set of field names a model may hand a citation under. A closed
# list, not a scan of every field: a locator picked out of arbitrary prose
# would be the engine guessing which sentence was a source.
CITATION_FIELDS: tuple[str, ...] = ("citation", "source_locator", "locator", "source", "url")

# How much of a proposed claim is echoed back inside a question. Long enough
# to be recognisable, short enough that the question stays one line.
_ECHO = 160


def citation_of(fields: Mapping[str, Any]) -> str:
    """The citation locator a proposal carries, or "" when it carries none.
    Empty and whitespace-only strings are the same absence as a missing key:
    a blank citation is not a citation (R1)."""
    for name in CITATION_FIELDS:
        value = fields.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def source_question(ctx: MethodContext, claim: str, *, why: str) -> T.QuestionPayload:
    """The typed hole an uncited claim leaves: which source states this?
    Asked as a document request, because a citation is a record, not a
    recollection - the client cannot confirm an external fact by memory."""
    return T.QuestionPayload(
        text=f"Which source states this, and where exactly: \"{claim[:_ECHO]}\"?",
        asks_for=(T.AsksFor(T.Kind.EVIDENCE_SOURCE),),
        issue_ids=ctx.issue_ids, why=why,
        effort=T.EffortClass.LOOKUP, strategy=T.FillStrategy.REQUEST_DOCUMENT)


def external_fact_validator(spec_id: str) -> Validator:
    """R1 and R2 as a check on the finished result, so a future edit to any
    research method's run() is caught by its own declared validators even if
    the write path changes."""
    def _v(view: Any, result: MethodResult) -> list[T.Finding]:
        out: list[T.Finding] = []
        for e in added_of(result, T.Kind.FACT):
            if e.payload.basis is not T.FactBasis.EXTERNAL_SOURCED:
                continue
            if not (e.provenance.source_locator or "").strip():
                out.append(T.Finding(
                    law=f"M.{spec_id}.external_fact_without_locator", where=e.id or e.kind.value,
                    issue="an external fact names no source passage; nothing could confirm or refute it",
                    fix="record the citation locator on the fact, or ask for the source instead of writing it",
                    entity_ids=(e.id,) if e.id else ()))
            if e.status is not T.Status.PROPOSED:
                out.append(T.Finding(
                    law=f"M.{spec_id}.external_fact_not_proposed", where=e.id or e.kind.value,
                    issue=f"an external fact was written {e.status.value}; only a cited source confirms one",
                    fix="write external facts PROPOSED and let the citation, not the method, confirm them",
                    entity_ids=(e.id,) if e.id else ()))
        return out
    return _v


SPEC = MethodSpec(
    id="market_competitor",
    version=1,
    # WHAT on FACT: the same node shape the deterministic current-state method
    # takes on. Selection separates them by cost, not by any flag on the node:
    # research is the expensive way to answer a WHAT the registry cannot.
    applicability=(QuestionShape(T.Interrogative.WHAT, T.Kind.FACT),),
    answers=(T.Interrogative.WHAT,),
    required_inputs=(
        InputSpec("context", T.Kind.BUSINESS_CONTEXT, min_count=1, effort=T.EffortClass.OFFHAND,
                  why_needed="external facts are only relevant against a stated business context"),
        # The records a citation can point INTO. R1 says an external fact is
        # owned by the source that states it, and `model_proposals` renders the
        # prompt from registered inputs and the issue node only - so a research
        # method in this engine cannot reach a source the engagement does not
        # hold. Declaring the record it must cite is the method saying what its
        # own law already requires; leaving it undeclared let the method be
        # offered a window with no citable record in it, propose claims it
        # could only have recalled, and refuse every one of them.
        #
        # A conversation turn is excluded by the same law the refusal states: a
        # citation is a record, not a recollection. Where the engagement holds
        # no record, this input is unmet and the question pass raises the typed
        # document request - the same ask `source_question` makes, for no call.
        InputSpec("records", T.Kind.EVIDENCE_SOURCE,
                  filter={"source_kind": (T.SourceKind.DOCUMENT.value, T.SourceKind.DATASET.value,
                                          T.SourceKind.LINK.value)},
                  min_count=1, effort=T.EffortClass.THIRD_PARTY,
                  why_needed="an external claim is owned by the record that states it, and a citation is a record"),
    ),
    optional_inputs=(
        InputSpec("objectives", T.Kind.OBJECTIVE, min_count=1),
        InputSpec("facts", T.Kind.FACT, min_count=1),
    ),
    execution=T.ExecutionType.RESEARCH,
    output_kinds=(T.Kind.FACT, T.Kind.QUESTION),
    output_schema=None,
    evidence=EvidenceRequirement(),
    limitations=(
        "states external claims with their sources; it does not verify that a cited source says what is claimed",
        "writes no quantity of its own: a market figure enters only by copying a registered input",
    ),
    validators=(cites_validator("market_competitor"), external_fact_validator("market_competitor")),
    cost_class=3,
    max_model_calls=3,
)

_INSTRUCTIONS = (
    "Propose external market and competitor facts that bear on the cited business context. "
    "Every fact's fields must carry 'citation': the exact passage, page or address the claim "
    "comes from. A claim you cannot cite is a question, not a fact: return it under 'questions'. "
    "Do not state a figure of your own; a number enters only through 'quantity_from' naming a "
    "registered input id."
)


def pending(view: Any) -> bool:
    """Whether this method still has anything to conclude here.

    an external claim is proposed about a context and objectives the research has
    not already answered; once every one of them carries a live fact, there is
    nothing further to look up here.

    `new_evidence_remains` asks that in one place for every method that words
    a conclusion through the shared admission law, because it is that law -
    the door that refuses a restatement and an output citing rows it was not
    shown - that decides what a further call could keep.
    """
    return new_evidence_remains(SPEC, view)


SPEC = dataclasses.replace(SPEC, pending=pending)


@register
class MarketCompetitorMethod:
    spec = SPEC

    def run(self, ctx: MethodContext) -> MethodResult:
        proposal = model_proposals(
            ctx, self.spec, "state the external market and competitor facts, each with its source", _INSTRUCTIONS)
        if proposal.failure is not None:
            return proposal.failure
        findings: list[T.Finding] = []
        deltas: list[T.Add] = []
        questions: list[T.QuestionPayload] = list(question_payloads(proposal))
        issue = proposal.issue
        for i, o, kind, derived, quantity in admitted(self.spec, proposal, findings):
            if kind is not T.Kind.FACT:
                findings.append(dropped(self.spec.id, i, f"{kind.value} is not an external fact"))
                continue
            text = o.text.strip()
            if not text:
                findings.append(dropped(self.spec.id, i, "a fact without wording states nothing"))
                continue
            locator = citation_of(o.fields)
            if not locator:
                # R1: the refusal IS the enforcement. The claim is not lost -
                # it leaves as a question for the source, so the engagement
                # can still get the fact, with its citation, next turn.
                findings.append(dropped(self.spec.id, i, "external fact carries no citation locator",
                                        law="uncited_external_fact"))
                questions.append(source_question(
                    ctx, text, why="an external fact is owned by the source that states it"))
                continue
            topic = o.fields.get("topic")
            payload = T.FactPayload(
                statement=text, basis=T.FactBasis.EXTERNAL_SOURCED, quantity=quantity,
                topic=topic if isinstance(topic, str) and topic else None)
            deltas.append(T.Add(new_entity(
                ctx, T.Kind.FACT, payload, derived_from=derived,
                relation=T.RelationToCentralDecision.INFORMS, confidence=T.Confidence(None),
                decision_id=issue.relevance.decision_id, weight=issue.relevance.weight,
                # R2: PROPOSED, always. The citation confirms it, not the run.
                status=T.Status.PROPOSED, locator=locator,
                model_call_id=proposal.response.call_id)))
        return MethodResult(deltas=tuple(deltas), questions=tuple(questions), findings=tuple(findings),
                            model_call_ids=(proposal.response.call_id,))
