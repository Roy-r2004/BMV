"""market_sizing - RESEARCH followed by a CALCULATION step: how big the
market or the opportunity is, in numbers the calculator produced.

The division of labour is the point (design 1, consequence 3). The model may
say WHICH registered figures multiply to a size - it names entity ids, a
closed choice among rows that already exist. It may not say WHAT the size is:
every number this method registers is a CalcResult from ctx.calc, with the
formula over those ids and the ids themselves, so L7 can recompute it
exactly. External claims the research turns up are written as facts with
their citation, under the same law market_competitor states (R1/R2, imported
rather than restated, so one deletion breaks both methods' tests).

Laws this module enforces:

  MS1 a sizing figure is a CalcResult or it does not exist. The chain the
      model names is fed to the Calculator; the Calculator's refusals are
      recorded as questions and findings, never worked around. A market size
      typed by a model is a number with no lineage - exactly what r30 learned
      prompt law cannot prevent.
  MS2 the unit of a product is read from the chain, never from the model: a
      chain with a money leg lands in that currency, a chain without one
      cannot become money (the Calculator refuses capacity -> money without a
      price fact, and nothing here can ask it to).
  MS3 a chain of one entity is refused. Restating a registered figure under a
      new id would give the same number two lineages and two lives.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Sequence

from app.engine import types as T
from app.engine.calc import IncomparableInputs
from app.engine.calc.arith import quantity_of
from app.engine.methods.builtin.capability_gap import (
    admitted,
    cites_validator,
    dropped,
    model_proposals,
    new_evidence_remains,
    question_payloads,
)
from app.engine.methods.builtin.cost_benefit import (
    calculated_fact,
    calculated_traceable,
    known_formulas,
    pin_question,
)
from app.engine.methods.builtin.market_competitor import citation_of, external_fact_validator, source_question
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

# The basis a proposal claims for itself. Two words, closed: anything else is
# neither a citable external claim nor a calculation over registered ids, so
# there is no third thing for a proposal to be.
CALCULATED = "calculated"
EXTERNAL = "external_sourced"

# A product needs at least this many legs to be a calculation rather than a
# restatement of one registered figure (MS3).
MIN_CHAIN = 2


def chain_unit(chain: Sequence[T.Entity]) -> tuple[str, T.UnitFamily]:
    """The unit and family a sizing product lands in, read from the chain
    (MS2). A money leg makes the product money in that currency; otherwise
    the first leg that is not a fraction sets the unit. A chain of fractions
    alone sizes nothing and returns no unit."""
    for e in chain:
        q = quantity_of(e)
        if q is not None and q.unit_family is T.UnitFamily.MONEY:
            return q.unit, T.UnitFamily.MONEY
    for e in chain:
        q = quantity_of(e)
        if q is not None and q.unit_family is not T.UnitFamily.RATE:
            return q.unit, q.unit_family
    return "", T.UnitFamily.OTHER


SPEC = MethodSpec(
    id="market_sizing",
    version=1,
    applicability=(
        QuestionShape(T.Interrogative.HOW_MUCH, T.Kind.BENEFIT, quantified=True),
        QuestionShape(T.Interrogative.HOW_MUCH, T.Kind.EXPECTED_OUTCOME, quantified=True),
    ),
    answers=(T.Interrogative.HOW_MUCH,),
    required_inputs=(
        InputSpec("context", T.Kind.BUSINESS_CONTEXT, min_count=1, effort=T.EffortClass.OFFHAND,
                  why_needed="a size is a size of something: the context says of what"),
        InputSpec("quantities", T.Kind.FACT, filter={"has_quantity": True}, min_count=1,
                  effort=T.EffortClass.LOOKUP,
                  why_needed="the sizing chain multiplies registered figures; without one there is nothing to size"),
    ),
    optional_inputs=(
        InputSpec("assumptions", T.Kind.ASSUMPTION, min_count=1),
        InputSpec("measures", T.Kind.MEASURE, min_count=1),
    ),
    execution=T.ExecutionType.RESEARCH,
    output_kinds=(T.Kind.FACT, T.Kind.QUESTION),
    output_schema=None,
    evidence=EvidenceRequirement(),
    limitations=(
        "sizes only what registered figures can multiply; a missing leg is a question, never an estimate",
        "does not verify that a cited external source says what the research claims",
    ),
    validators=(cites_validator("market_sizing"), external_fact_validator("market_sizing"), calculated_traceable),
    cost_class=3,
    max_model_calls=3,
)

_INSTRUCTIONS = (
    "Two kinds of proposal are admitted, and the fields must say which by carrying "
    f"'basis': '{EXTERNAL}' or '{CALCULATED}'. "
    f"For '{EXTERNAL}', also carry 'citation': the exact passage the claim comes from. "
    f"For '{CALCULATED}', 'derived_from' IS the sizing chain: list the registered input ids whose "
    "quantities multiply to the size, in order. You do not compute the product and you do not state "
    "a number; the calculator multiplies the ids you name and records the formula."
)


def pending(view: Any) -> bool:
    """Whether this method still has anything to conclude here.

    a size is a product of REGISTERED figures, and a figure already multiplied
    into a live sizing fact sizes nothing twice.

    `new_evidence_remains` asks that in one place for every method that words
    a conclusion through the shared admission law, because it is that law -
    the door that refuses a restatement and an output citing rows it was not
    shown - that decides what a further call could keep.
    """
    return new_evidence_remains(SPEC, view)


SPEC = dataclasses.replace(SPEC, pending=pending)


@register
class MarketSizingMethod:
    spec = SPEC

    def run(self, ctx: MethodContext) -> MethodResult:
        proposal = model_proposals(
            ctx, self.spec, "size the opportunity from cited external facts and registered figures", _INSTRUCTIONS)
        if proposal.failure is not None:
            return proposal.failure
        view = ctx.registry
        findings: list[T.Finding] = []
        deltas: list = []
        questions: list[T.QuestionPayload] = list(question_payloads(proposal))
        seen = known_formulas(view)
        by_id = proposal.inputs_by_id
        issue = proposal.issue
        for i, o, kind, derived, quantity in admitted(self.spec, proposal, findings):
            if kind is not T.Kind.FACT:
                findings.append(dropped(self.spec.id, i, f"{kind.value} is not a sizing output"))
                continue
            text = o.text.strip()
            basis = o.fields.get("basis")
            if basis == CALCULATED:
                chain = [by_id[c] for c in derived if quantity_of(by_id[c]) is not None]
                if len(chain) < MIN_CHAIN:
                    # MS3: one figure re-registered is the same figure twice.
                    findings.append(dropped(self.spec.id, i,
                                            f"a sizing chain needs at least {MIN_CHAIN} registered quantities",
                                            law="short_chain"))
                    continue
                unit, family = chain_unit(chain)
                if not unit:
                    findings.append(dropped(self.spec.id, i, "a chain of fractions alone sizes nothing",
                                            law="no_base_quantity"))
                    continue
                try:
                    cr = ctx.calc.product(chain, unit=unit, unit_family=family)
                except IncomparableInputs as exc:
                    # The dimensions do not join: the hole is asked, never filled.
                    questions.append(pin_question(
                        ctx, tuple(e.id for e in chain), tuple(getattr(exc, "unpinned", ()) or ()),
                        why="a sizing product is only lawful over figures that share every pinned dimension"))
                    continue
                except ValueError as exc:
                    # A share nobody with authority stated, or a leg with no
                    # registered quantity: recorded as a refusal and asked for,
                    # so the run stays auditable and nothing is estimated.
                    findings.append(dropped(self.spec.id, i, str(exc)[:200], law="refused_chain"))
                    questions.append(source_question(
                        ctx, text or ", ".join(e.id for e in chain),
                        why="the calculator refused the chain; the missing figure must be stated by someone who owns it"))
                    continue
                if cr.formula in seen:
                    continue
                seen.add(cr.formula)
                # PROPOSED, not CONFIRMED: a RESEARCH method runs under a
                # specialist assignment, whose admission takes every Add as a
                # proposal (design 8, S2). The formula and the inputs are
                # already on the row, so the confirming actor re-runs the
                # arithmetic rather than trusting the producer.
                deltas.append(calculated_fact(ctx, self.spec.id, cr, statement=text or None,
                                              status=T.Status.PROPOSED))
                continue
            if basis == EXTERNAL:
                if not text:
                    findings.append(dropped(self.spec.id, i, "a fact without wording states nothing"))
                    continue
                locator = citation_of(o.fields)
                if not locator:
                    findings.append(dropped(self.spec.id, i, "external fact carries no citation locator",
                                            law="uncited_external_fact"))
                    questions.append(source_question(
                        ctx, text, why="an external fact is owned by the source that states it"))
                    continue
                payload = T.FactPayload(statement=text, basis=T.FactBasis.EXTERNAL_SOURCED, quantity=quantity)
                deltas.append(T.Add(new_entity(
                    ctx, T.Kind.FACT, payload, derived_from=derived,
                    relation=T.RelationToCentralDecision.INFORMS, confidence=T.Confidence(None),
                    decision_id=issue.relevance.decision_id, weight=issue.relevance.weight,
                    status=T.Status.PROPOSED, locator=locator, model_call_id=proposal.response.call_id)))
                continue
            findings.append(dropped(self.spec.id, i, f"basis {basis!r} is neither {EXTERNAL!r} nor {CALCULATED!r}",
                                    law="unknown_basis"))
        return MethodResult(deltas=tuple(deltas), questions=tuple(questions), findings=tuple(findings),
                            model_call_ids=(proposal.response.call_id,))
