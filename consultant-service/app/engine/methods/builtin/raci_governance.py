"""raci_governance - who is accountable for each step (design 7.3 row
raci_governance): WHO on GOVERNANCE.

DETERMINISTIC, so M1 holds and no model is called: accountability is read off
the plan the engagement already registered - an action's owner - and where the
plan does not say, the answer is a question to the client, never a guess.

Laws this module enforces, each in the docstring of the thing enforcing it:

  GV1 exactly one accountable per action. Two accountables is nobody
      accountable, and zero is the same thing written differently; both are
      Findings, and neither is repaired by picking one (accountable_findings,
      _v_exactly_one_accountable).
  GV2 an accountable is a registered party. A RACI row naming somebody the
      registry has never heard of cannot be honoured by anyone
      (rows_for, _v_raci_names_registered_parties).
  GV3 an action whose owner the plan never named gets a question, not a
      default owner: assigning accountability on the client's behalf is the
      one thing a governance design must never do (run()).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Sequence

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
    display_text,
    live,
    require_citations,
)
from app.engine.methods.builtin.risk_control import BEARER_KINDS


def accountable_findings(rows: Iterable[T.RaciRow], where: str) -> list[T.Finding]:
    """GV1: the two ways an accountability table fails, as two named laws.

    An empty accountable is zero accountables; two distinct accountables for
    one action is a disagreement about who answers for it. Neither is fixed
    here - the method reports and refuses, because choosing between two
    candidate owners is the decision owner's call, not the engine's.
    """
    by_action: dict[str, list[str]] = {}
    out: list[T.Finding] = []
    for r in rows:
        name = (r.accountable or "").strip()
        if not name:
            out.append(T.Finding(
                law="M.raci_governance.no_accountable", where=where,
                issue=f"the RACI row for {r.action_id} names no accountable",
                fix="name the one party who answers for the step, or ask the client who it is",
                entity_ids=(r.action_id,)))
            continue
        by_action.setdefault(r.action_id, [])
        if name not in by_action[r.action_id]:
            by_action[r.action_id].append(name)
    for action_id, names in sorted(by_action.items()):
        if len(names) > 1:
            out.append(T.Finding(
                law="M.raci_governance.multiple_accountable", where=where,
                issue=f"{action_id} has {len(names)} accountables ({', '.join(names)}); it may have exactly one",
                fix="the decision owner names the single party accountable for the step",
                entity_ids=(action_id,)))
    return out


def rows_for(actions: Sequence[T.Entity], parties: dict[str, T.Entity]) -> tuple[tuple[T.RaciRow, ...],
                                                                                tuple[str, ...]]:
    """GV2: one RACI row per action whose owner the plan names, and the ids of
    the actions it does not. The accountable is the action's registered owner -
    read from `owner_id`, so scrambling every text field leaves the table's
    structure identical and only the rendered names change."""
    rows: list[T.RaciRow] = []
    unowned: list[str] = []
    for a in sorted(actions, key=lambda e: e.id):
        owner = parties.get(a.payload.owner_id or "")
        if owner is None:
            unowned.append(a.id)
            continue
        name = display_text(owner) or owner.id
        rows.append(T.RaciRow(action_id=a.id, responsible=name, accountable=name))
    return tuple(rows), tuple(unowned)


class RaciGovernance:
    spec = MethodSpec(
        id="raci_governance", version=1,
        applicability=(QuestionShape(T.Interrogative.WHO, T.Kind.GOVERNANCE),),
        answers=(T.Interrogative.WHO,),
        required_inputs=(
            InputSpec("actions", T.Kind.ACTION, why_needed="the steps accountability attaches to"),
            InputSpec("owners", T.Kind.OWNER, why_needed="the parties who can be accountable"),
        ),
        optional_inputs=(
            InputSpec("governance", T.Kind.GOVERNANCE, min_count=0,
                      why_needed="accountability already recorded elsewhere"),
            InputSpec("decision_owners", T.Kind.DECISION_OWNER, min_count=0,
                      why_needed="who answers for the decision itself"),
        ),
        execution=T.ExecutionType.DETERMINISTIC,
        output_kinds=(T.Kind.GOVERNANCE,),
        output_schema=None,
        evidence=EvidenceRequirement(),
        limitations=("reads accountability off the registered plan; it never assigns an owner the "
                     "engagement has not named",),
        validators=(),
        cost_class=1, max_model_calls=0)

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        dec = view.central_decision()
        decision_id = dec.id if dec is not None else None
        actions = live(view, T.Kind.ACTION)
        parties: dict[str, T.Entity] = {}
        for kind in BEARER_KINDS:
            for p in live(view, kind):
                parties[p.id] = p
        if not actions or not parties:
            return MethodResult()

        rows, unowned = rows_for(actions, parties)
        existing = [r for g in live(view, T.Kind.GOVERNANCE) for r in g.payload.raci]
        findings = accountable_findings(tuple(existing) + rows, ctx.issue_ids[0] if ctx.issue_ids else self.spec.id)

        questions: list[T.QuestionPayload] = []
        if unowned:
            # GV3: the plan does not say, so the engine does not either.
            questions.append(T.QuestionPayload(
                text=f"Who is accountable for {', '.join(unowned)}? "
                     "Nothing is assigned until you say.",
                asks_for=(T.AsksFor(T.Kind.OWNER),), issue_ids=ctx.issue_ids,
                why="exactly one party answers for each step, and only the client can name them",
                effort=T.EffortClass.OFFHAND, strategy=T.FillStrategy.ASK_CLIENT, material=True))

        deltas: list[T.EntityDelta] = []
        if rows and not any(f.law == "M.raci_governance.multiple_accountable" for f in findings):
            covered = {r.action_id for g in live(view, T.Kind.GOVERNANCE) for r in g.payload.raci}
            fresh = tuple(r for r in rows if r.action_id not in covered)
            if fresh:
                payload = T.GovernancePayload(
                    text="Accountability for the registered plan steps",
                    forum="", cadence="",
                    decides=(decision_id,) if decision_id else (),
                    raci=fresh)
                deltas.append(T.Add(new_entity(
                    ctx, T.Kind.GOVERNANCE, payload,
                    derived_from=tuple(dict.fromkeys([r.action_id for r in fresh]
                                                     + [a.payload.owner_id for a in actions
                                                        if a.payload.owner_id in parties])),
                    relation=T.RelationToCentralDecision.INFORMS, confidence=T.Confidence(None),
                    decision_id=decision_id,
                    weight=T.SENSITIVITY[T.RelationToCentralDecision.INFORMS])))
        return MethodResult(deltas=tuple(deltas), questions=tuple(questions), findings=tuple(findings))


def _v_exactly_one_accountable(view, result: MethodResult) -> list[T.Finding]:
    """GV1 re-checked on the finished result, against the accountability the
    registry already holds: across the result and the live GOVERNANCE rows,
    every action named has exactly one accountable. Removing this check is the
    named mutation "allow zero accountables"."""
    rows: list[T.RaciRow] = []
    written_ids: set[str] = set()
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is not None and e.kind is T.Kind.GOVERNANCE:
            rows.extend(e.payload.raci)
            if e.id:
                written_ids.add(e.id)
    if not rows:
        return []
    for g in view.query(T.Kind.GOVERNANCE):
        if g.status not in T.TERMINAL_STATUSES and g.id not in written_ids:
            rows.extend(g.payload.raci)
    return accountable_findings(rows, "governance")


def _v_raci_names_registered_parties(view, result: MethodResult) -> list[T.Finding]:
    """GV2 re-checked: the responsible and accountable of every row this result
    writes name a party the registry holds. Accountability to a name nobody
    recognises is accountability to nobody."""
    known = {display_text(p) for kind in BEARER_KINDS for p in view.query(kind)
             if p.status not in T.TERMINAL_STATUSES}
    known |= {p.id for kind in BEARER_KINDS for p in view.query(kind)
              if p.status not in T.TERMINAL_STATUSES}
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not T.Kind.GOVERNANCE:
            continue
        for r in e.payload.raci:
            for role, name in (("accountable", r.accountable), ("responsible", r.responsible)):
                if (name or "").strip() and name not in known:
                    out.append(T.Finding(
                        law="M.raci_governance.unregistered_party", where=e.id or "governance",
                        issue=f"the {role} for {r.action_id} is not a party the registry holds",
                        fix="name a registered owner, stakeholder or decision owner",
                        entity_ids=(r.action_id,)))
    return out


RaciGovernance.spec = replace(RaciGovernance.spec,
                              validators=(require_citations("raci_governance"),
                                          _v_exactly_one_accountable,
                                          _v_raci_names_registered_parties))
register(RaciGovernance)
