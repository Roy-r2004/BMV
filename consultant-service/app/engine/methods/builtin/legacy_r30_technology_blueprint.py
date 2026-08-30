"""legacy_r30_technology_blueprint - the r30 technology pipeline as an
ordinary registered method (design 13.1).

There is no "technology engagement" anywhere in the engine. This method is
selected the way every other method is selected: an issue node whose shape is
HOW on a CAPABILITY of class SOFTWARE_SYSTEM, with the inputs it declares. A
client who never asks a software question never reaches it, and a client who
does reaches it without anyone naming an engagement type.

Laws this module enforces, each in the docstring of the thing enforcing it:

  LG1 the pipeline is a costed step and runs only behind a DECISION_REQUIRED
      the client resolved. Without one, the method writes the decision and
      stops; with one still open, it does nothing at all (`run`).
  LG2 everything the pipeline is told is composed from registry entities
      (`r30_adapter.compose_inputs`, law A1 there).
  LG3 nothing this method writes is born CONFIRMED. A legacy number earns
      CONFIRMED only from the engine's calculator, after an exact recompute
      (`mapping.confirmations`, `_v_nothing_born_confirmed`).
  LG4 every ASSUMPTION it writes is UNAPPROVED: a consultant-proposed
      threshold stays visibly proposed (`_v_assumptions_unapproved`).

The commissioning seam is `ctx.settings[COMMISSION_KEY]`: a callable that
takes R30Inputs and returns R30Outputs, bound by whoever owns the database
session (the analysis round). Absent, the method still does its structural
work - the decision, and the composed inputs it would send - and says why it
went no further, rather than pretending a package exists.
"""
from __future__ import annotations

from dataclasses import replace

from app.engine import types as T
from app.engine.legacy import mapping as legacy_mapping
from app.engine.legacy.r30_adapter import COMMISSION_TEXT, R30Outputs, compose_inputs
from app.engine.methods.builtin.org_design import issue_frame, live, refusal, require_citations
from app.engine.methods.contract import (
    EvidenceRequirement,
    InputSpec,
    MethodContext,
    MethodResult,
    MethodSpec,
    QuestionShape,
    register,
)

# The key the analysis round hangs the commissioning callable on. A method
# never opens a database session of its own: it is a pure function of its
# context, and the session belongs to the thread that owns the engagement.
COMMISSION_KEY = "legacy_r30_commission"

# What the caller must supply beside the callable, because neither is a claim
# about the business and so neither is a registry entity: the name the
# engagement is filed under, and the account that pays for the run.
BUSINESS_NAME_KEY = "legacy_r30_business_name"
OWNER_EMAIL_KEY = "legacy_r30_owner_email"


def _commission_decision(view) -> T.Entity | None:
    """The one DECISION_REQUIRED that licenses the spend. Matched on the
    declared text constant, so a second commissioning decision is the same
    decision and not a new one."""
    for d in live(view, T.Kind.DECISION_REQUIRED):
        if d.payload.text == COMMISSION_TEXT:
            return d
    return None


class LegacyR30TechnologyBlueprint:
    spec = MethodSpec(
        id="legacy_r30_technology_blueprint", version=1,
        applicability=(
            QuestionShape(T.Interrogative.HOW, T.Kind.CAPABILITY,
                          capability_class=T.CapabilityClass.SOFTWARE_SYSTEM),
        ),
        answers=(T.Interrogative.HOW,),
        required_inputs=(
            InputSpec("context", T.Kind.BUSINESS_CONTEXT,
                      why_needed="the pipeline is told what the business does in the client's own words"),
            InputSpec("objectives", T.Kind.OBJECTIVE,
                      why_needed="a build with no stated outcome is a build with no way to be wrong"),
            InputSpec("client_numbers", T.Kind.FACT,
                      filter={"basis": T.FactBasis.CLIENT_STATED, "has_quantity": True},
                      effort=T.EffortClass.LOOKUP,
                      why_needed="every number the package computes starts from one the client stated"),
        ),
        optional_inputs=(
            InputSpec("workstream", T.Kind.WORKSTREAM, min_count=0,
                      why_needed="the workstream the delivered package belongs to"),
            InputSpec("decision_owner", T.Kind.DECISION_OWNER, min_count=0,
                      why_needed="document owner and approver for the delivered volumes"),
        ),
        execution=T.ExecutionType.MODEL_ASSISTED,
        output_kinds=(T.Kind.DECISION_REQUIRED, T.Kind.WORKSTREAM, T.Kind.INITIATIVE, T.Kind.DEPENDENCY,
                      T.Kind.DECISION, T.Kind.SUCCESS_CRITERION, T.Kind.STATEMENT, T.Kind.FACT,
                      T.Kind.ASSUMPTION, T.Kind.ACTION, T.Kind.OWNER, T.Kind.PROCESS_STEP,
                      T.Kind.RISK, T.Kind.CONTROL, T.Kind.WORK_PRODUCT),
        output_schema=None,
        evidence=EvidenceRequirement(),
        limitations=("delivers the r30 technology package unchanged: its analysis is the pipeline's, "
                     "and the engine imports it, checks its arithmetic and reports its own verdict on it",
                     "a correction re-commissions a new run; the delivered package is never edited"),
        validators=(),
        # The most expensive step in the system: it ranks last among methods
        # that match equally well, and it declares no engine model calls
        # because it makes none - the spend happens inside r30, behind LG1.
        cost_class=3, max_model_calls=0)

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        issue, decision_id, weight = issue_frame(ctx)

        # LG1: the decision first. Nothing is composed, nothing is spent and
        # nothing is imported until the client has said yes in writing.
        decision = _commission_decision(view)
        if decision is None:
            payload = T.DecisionRequiredPayload(
                text=COMMISSION_TEXT, from_authority=T.Authority.CLIENT,
                decision_id=decision_id,
                by_when=None)
            e = T.make_entity(
                kind=T.Kind.DECISION_REQUIRED, engagement_id=view.engagement_id, payload=payload,
                provenance=T.Provenance(actor=ctx.actor, actor_ref=ctx.actor_ref,
                                        derived_from=tuple(i for i in ctx.issue_ids if i)),
                confidence=T.Confidence(None), relevance=T.Relevance(decision_id=decision_id, weight=weight),
                relation=T.RelationToCentralDecision.DEPENDS_ON, status=T.Status.OPEN)
            return MethodResult(deltas=(T.Add(e),))
        if decision.status is not T.Status.RESOLVED:
            # Open, and honestly open: the round ends with nothing rather than
            # with a package the client did not authorise.
            return MethodResult()

        commission = ctx.settings.get(COMMISSION_KEY)
        business_name = str(ctx.settings.get(BUSINESS_NAME_KEY) or "")
        owner_email = str(ctx.settings.get(OWNER_EMAIL_KEY) or "")

        workstreams = live(view, T.Kind.WORKSTREAM)
        workstream_id = None
        if issue is not None:
            workstream_id = next((w.id for w in workstreams
                                  if T.CapabilityClass.SOFTWARE_SYSTEM in w.payload.capability_classes), None)
        if workstream_id is None and workstreams:
            workstream_id = workstreams[0].id

        inputs = compose_inputs(view, business_name=business_name, owner_email=owner_email,
                                issue_id=issue.id if issue is not None else None,
                                workstream_id=workstream_id)

        if commission is None:
            return MethodResult(findings=(refusal(
                self.spec.id, "no_commissioning_seam", decision.id,
                "the analysis round supplied no way to run the technology pipeline, so nothing was "
                "commissioned"),))

        outputs = commission(inputs)
        if not isinstance(outputs, R30Outputs):
            return MethodResult(findings=(refusal(
                self.spec.id, "unreadable_package", decision.id,
                "the commissioning seam returned something that is not an r30 package"),))

        imported = legacy_mapping.import_r30(
            outputs, view, inputs=inputs, calc=ctx.calc,
            engagement_id=view.engagement_id, decision_id=decision_id, weight=weight)
        return MethodResult(deltas=imported.deltas, findings=imported.findings)


def _v_assumptions_unapproved(view, result: MethodResult) -> list[T.Finding]:
    """LG4 re-checked on the result: every ASSUMPTION the legacy import writes
    is UNAPPROVED and PROPOSED. An r30 threshold that arrived approved would
    be a consultant's proposal wearing the client's authority, which is the
    one thing the whole authority table exists to prevent."""
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not T.Kind.ASSUMPTION:
            continue
        if e.payload.approval is not T.ApprovalState.UNAPPROVED or e.status is not T.Status.PROPOSED:
            out.append(T.Finding(
                law="M.legacy_r30_technology_blueprint.approved_assumption", where=e.id or "assumption",
                issue="a consultant-proposed legacy threshold arrived already approved",
                fix="import it unapproved; only the client approves an assumption"))
    return out


def _v_nothing_born_confirmed(view, result: MethodResult) -> list[T.Finding]:
    """LG3 re-checked: no row of a legacy import is born CONFIRMED. A
    calculated fact reaches CONFIRMED only through a SetStatus by the
    CALCULATOR, which happens after `calc.recompute` reproduced it exactly."""
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None:
            continue
        if e.status in (T.Status.CONFIRMED, T.Status.APPROVED):
            out.append(T.Finding(
                law="M.legacy_r30_technology_blueprint.confirmed_at_birth", where=e.id or e.kind.value,
                issue=f"a legacy {e.kind.value} was written as {e.status.value} without an authority confirming it",
                fix="write it PROPOSED; the calculator confirms arithmetic and the client confirms the rest"))
    return out


def _v_legacy_actor(view, result: MethodResult) -> list[T.Finding]:
    """Every legacy row says where it came from: actor LEGACY_R30 and an
    actor_ref naming the request and the path inside its package. A row that
    does not is untraceable to the pipeline that produced it."""
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is T.Kind.DECISION_REQUIRED:
            continue
        if e.provenance.actor is not T.Actor.LEGACY_R30:
            out.append(T.Finding(
                law="M.legacy_r30_technology_blueprint.unattributed_row", where=e.id or e.kind.value,
                issue=f"a legacy row is attributed to {e.provenance.actor.value}, not to the pipeline",
                fix="attribute imported rows to LEGACY_R30 with the r30:request:<id>:<path> reference"))
    return out


LegacyR30TechnologyBlueprint.spec = replace(
    LegacyR30TechnologyBlueprint.spec,
    validators=(require_citations("legacy_r30_technology_blueprint"),
                _v_assumptions_unapproved,
                _v_nothing_born_confirmed,
                _v_legacy_actor))
register(LegacyR30TechnologyBlueprint)
