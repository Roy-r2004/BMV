"""roadmap - sequence, not schedule (design 7.3 row roadmap): WHEN/HOW on
WORKSTREAM or MILESTONE, temporal.

DETERMINISTIC, so M1 holds and no model is called: a topological order is
arithmetic over declared edges, and asking a model for one would be asking it
to guess an answer the registry already determines.

This module also owns the acyclic-graph law for the whole design family
(systems_data_map imports `closes_a_cycle` and `topological` from here): the
law belongs with the method whose subject is sequencing, and one
implementation means one mutation kills both tests.

Laws this module enforces, each in the docstring of the thing enforcing it:

  RD1 the dependency graph is acyclic. An edge that would close a cycle is
      not written and the refusal is a Finding: a plan whose steps wait on
      each other is not a plan, and silently dropping the edge would hide
      that the engagement believes two contradictory things (closes_a_cycle,
      _v_acyclic).
  RD2 no step is scheduled before what it depends on. A registered sequence
      that contradicts a registered dependency is a forward dependency and a
      Finding, never quietly re-sorted: the two statements disagree and the
      disagreement is the finding (forward_dependencies, _v_no_forward_dependency).
  RD3 a plan carries horizons, not dates. A calendar date may appear only
      where a DEADLINE owns it - a DEADLINE is the client's, a horizon is the
      consultant's, and printing a date the client never gave turns an
      estimate into a commitment (dates_not_owned, _v_dates_owned_by_deadline).
  RD4 a MILESTONE is written per workstream that has work in it, with the
      horizon its own actions carry; nothing here fixes how many milestones a
      plan has (design 20: never a fixed count per engagement).
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Iterable, Mapping, Sequence

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
    fresh_ids,
    live,
    require_citations,
    with_id,
)


# =============================================================================
# The acyclic-graph law (RD1/RD2), shared with systems_data_map
# =============================================================================

def closes_a_cycle(edges: Mapping[str, set[str]], from_id: str, to_id: str) -> bool:
    """Whether adding from_id -> to_id would close a cycle in `edges`
    (depth-first reachability, the pattern of app/pipeline/structural.py:306).

    RD1: the check runs before the edge is added, so a graph that was acyclic
    stays acyclic and the refused edge is named. A cycle discovered after the
    fact could only be reported as "somewhere in here", which no one can fix.
    """
    if from_id == to_id:
        return True
    seen: set[str] = set()
    frontier = [to_id]
    while frontier:
        node = frontier.pop()
        if node == from_id:
            return True
        if node in seen:
            continue
        seen.add(node)
        frontier.extend(sorted(edges.get(node, ())))
    return False


def topological(nodes: Sequence[str], edges: Mapping[str, set[str]]) -> list[str] | None:
    """A deterministic topological order of `nodes` (Kahn, ties broken by id so
    two runs over one registry produce one order), or None when the graph has
    a cycle. Edges point from a node to what it depends on, so a dependency
    comes out first."""
    incoming: dict[str, int] = {n: 0 for n in nodes}
    outgoing: dict[str, list[str]] = {n: [] for n in nodes}
    for n in nodes:
        for dep in edges.get(n, ()):  # n depends on dep: dep must come first
            if dep in incoming:
                incoming[n] += 1
                outgoing[dep].append(n)
    ready = sorted(n for n in nodes if incoming[n] == 0)
    order: list[str] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for nxt in sorted(outgoing[node]):
            incoming[nxt] -= 1
            if incoming[nxt] == 0:
                ready.append(nxt)
        ready.sort()
    return order if len(order) == len(nodes) else None


def declared_edges(entities: Sequence[T.Entity], dependencies: Sequence[T.Entity]) -> dict[str, set[str]]:
    """Every dependency the registry declares among `entities`, from both
    places one can be written: a payload's `depends_on` and a DEPENDENCY row.
    Both are read; a plan that is acyclic in one and cyclic in the other is
    cyclic."""
    known = {e.id for e in entities}
    edges: dict[str, set[str]] = {e.id: set() for e in entities}
    for e in entities:
        for dep in getattr(e.payload, "depends_on", ()) or ():
            if dep in known:
                edges[e.id].add(dep)
    for d in dependencies:
        p = d.payload
        if p.from_id in known and p.to_id in known:
            edges[p.from_id].add(p.to_id)
    return edges


def forward_dependencies(entities: Sequence[T.Entity],
                         edges: Mapping[str, set[str]]) -> list[tuple[str, str]]:
    """RD2: (step, dependency) pairs where the registered sequence puts a step
    at or before something it depends on. Only entities that carry a sequence
    are judged: an unsequenced step is unknown, and unknown is not a defect
    (spec section 7)."""
    pos = {e.id: e.payload.sequence for e in entities
           if getattr(e.payload, "sequence", None) is not None}
    out: list[tuple[str, str]] = []
    for eid, at in sorted(pos.items()):
        for dep in sorted(edges.get(eid, ())):
            if dep in pos and pos[dep] >= at:
                out.append((eid, dep))
    return out


# =============================================================================
# The dates law (RD3)
# =============================================================================

# Calendar shapes only: an ISO date, a slashed date, a quarter and a bare
# year. This is calendar vocabulary, not engagement vocabulary - no word in it
# comes from any client, case or engagement type.
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\bQ[1-4]\s*/?\s*\d{2,4}\b|\b(?:19|20)\d{2}\b")


def date_tokens(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(m.group(0) for m in _DATE_RE.finditer(text or "")))


def dates_not_owned(text: str, owners: Iterable[T.Entity]) -> tuple[str, ...]:
    """RD3: the calendar tokens in `text` that nothing in `owners` accounts for.

    A DEADLINE is a client preference - the client owns when things must
    happen. A plan step owns only a Horizon. So a date printed on a step is
    lawful exactly when a DEADLINE already carries it, or when the step cites
    the entity the token came out of; an unaccounted one is the engine
    promising a date on the client's behalf.
    """
    owned = " ".join((getattr(o.payload, "date", None) or "") + " " + display_text(o) for o in owners)
    return tuple(t for t in date_tokens(text) if t not in owned)


def date_owners(view, e: T.Entity, deadlines: Sequence[T.Entity]) -> list[T.Entity]:
    """Everything that could lawfully account for a date on `e`: every live
    DEADLINE, plus the entities `e` itself cites (a token that came out of a
    registered source came from the engagement, not from the plan-maker)."""
    cited = [view.get(i) for i in e.provenance.derived_from]
    return list(deadlines) + [c for c in cited if c is not None]


# =============================================================================
# The method
# =============================================================================

_HORIZON_ORDER: tuple[T.Horizon, ...] = (T.Horizon.DAYS, T.Horizon.WEEKS, T.Horizon.MONTHS)


def widest_horizon(actions: Sequence[T.Entity]) -> T.Horizon:
    """The horizon a milestone inherits: the widest its own actions carry. A
    gate cannot be reached sooner than the slowest thing it waits on, and
    picking anything else here would be an estimate no action supports."""
    best = 0
    for a in actions:
        best = max(best, _HORIZON_ORDER.index(a.payload.horizon))
    return _HORIZON_ORDER[best]


class Roadmap:
    spec = MethodSpec(
        id="roadmap", version=1,
        applicability=(
            QuestionShape(T.Interrogative.WHEN, T.Kind.WORKSTREAM, temporal=True),
            QuestionShape(T.Interrogative.WHEN, T.Kind.MILESTONE, temporal=True),
            QuestionShape(T.Interrogative.HOW, T.Kind.WORKSTREAM, temporal=True),
            QuestionShape(T.Interrogative.HOW, T.Kind.MILESTONE, temporal=True),
        ),
        answers=(T.Interrogative.WHEN, T.Interrogative.HOW),
        required_inputs=(
            InputSpec("workstreams", T.Kind.WORKSTREAM, why_needed="the lanes a roadmap sequences"),
            InputSpec("actions", T.Kind.ACTION, why_needed="the work a roadmap orders"),
        ),
        optional_inputs=(
            InputSpec("initiatives", T.Kind.INITIATIVE, min_count=0, why_needed="the groupings actions belong to"),
            InputSpec("dependencies", T.Kind.DEPENDENCY, min_count=0, why_needed="edges already declared"),
            InputSpec("deadlines", T.Kind.DEADLINE, min_count=0,
                      why_needed="the only entity a calendar date may live on"),
        ),
        execution=T.ExecutionType.DETERMINISTIC,
        output_kinds=(T.Kind.MILESTONE, T.Kind.DEPENDENCY, T.Kind.INITIATIVE),
        output_schema=None,
        evidence=EvidenceRequirement(),
        limitations=("sequences by declared dependencies and states horizons; it never dates a step, "
                     "and it never invents a dependency the engagement did not declare",),
        validators=(),
        cost_class=1, max_model_calls=0)

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        workstreams = live(view, T.Kind.WORKSTREAM)
        initiatives = live(view, T.Kind.INITIATIVE)
        actions = live(view, T.Kind.ACTION)
        deps = live(view, T.Kind.DEPENDENCY)
        deadlines = live(view, T.Kind.DEADLINE)
        dec = view.central_decision()
        decision_id = dec.id if dec is not None else None
        weight = T.SENSITIVITY[T.RelationToCentralDecision.INFORMS]

        findings: list[T.Finding] = []
        deltas: list[T.EntityDelta] = []

        action_edges = declared_edges(actions, deps)
        order = topological([a.id for a in actions], action_edges)
        if order is None:
            # RD1, fail closed (design 1.4): a cyclic plan produces no ordering,
            # no derived initiative edges and no milestones. Emitting a partial
            # sequence would print an order the dependencies contradict.
            findings.append(T.Finding(
                law="M.roadmap.dependency_cycle", where=ctx.issue_ids[0] if ctx.issue_ids else self.spec.id,
                issue="the action dependency graph contains a cycle; no sequence exists",
                fix="remove one of the dependencies that close the loop, then re-run the roadmap",
                entity_ids=tuple(sorted(action_edges))))
            return MethodResult(findings=tuple(findings))

        for eid, dep in forward_dependencies(actions, action_edges):
            findings.append(T.Finding(
                law="M.roadmap.forward_dependency", where=eid,
                issue=f"{eid} is sequenced at or before {dep}, which it depends on",
                fix="re-sequence the two steps, or withdraw the dependency between them",
                entity_ids=(eid, dep)))

        for e in list(actions) + list(initiatives) + live(view, T.Kind.MILESTONE):
            loose = dates_not_owned(display_text(e), date_owners(view, e, deadlines))
            if loose:
                findings.append(T.Finding(
                    law="M.roadmap.date_not_owned_by_deadline", where=e.id,
                    issue=f"the calendar date(s) {', '.join(loose)} appear on a plan step that no DEADLINE owns",
                    fix="state a horizon, or register the DEADLINE that carries the date",
                    entity_ids=(e.id,)))

        # Initiative ordering (RD1 again on the coarser graph): an action's
        # dependency on an action in another initiative is a dependency between
        # the initiatives. The edge is derived from ids the registry already
        # holds, never proposed.
        of_initiative = {a.id: a.payload.initiative_id for a in actions}
        known_initiatives = {i.id for i in initiatives}
        initiative_edges = declared_edges(initiatives, deps)
        derived: list[tuple[str, str]] = []
        for aid in sorted(action_edges):
            src = of_initiative.get(aid)
            if src not in known_initiatives:
                continue
            for dep in sorted(action_edges[aid]):
                dst = of_initiative.get(dep)
                if dst not in known_initiatives or dst == src:
                    continue
                if dst in initiative_edges[src]:
                    continue
                if closes_a_cycle(initiative_edges, src, dst):
                    findings.append(T.Finding(
                        law="M.roadmap.dependency_cycle", where=src,
                        issue=f"{src} cannot depend on {dst}: the edge closes a cycle between initiatives",
                        fix="re-group the actions, or withdraw the action dependency that forces the loop",
                        entity_ids=(src, dst)))
                    continue
                initiative_edges[src].add(dst)
                derived.append((src, dst))

        dep_ids = iter(fresh_ids(view, T.Kind.DEPENDENCY, len(derived)))
        by_id = {i.id: i for i in initiatives}
        added: dict[str, list[str]] = {}
        for src, dst in derived:
            did = next(dep_ids, None)
            payload = T.DependencyPayload(from_id=src, to_id=dst, kind="requires")
            e = new_entity(ctx, T.Kind.DEPENDENCY, payload, derived_from=(src, dst),
                           relation=T.RelationToCentralDecision.DEPENDS_ON,
                           confidence=T.Confidence(None), decision_id=decision_id, weight=weight)
            deltas.append(T.Add(with_id(e, did) if did else e))
            added.setdefault(src, []).append(dst)

        for src, dsts in sorted(added.items()):
            old = by_id[src]
            merged = tuple(dict.fromkeys(tuple(old.payload.depends_on) + tuple(dsts)))
            new_payload = replace(old.payload, depends_on=merged)
            e = new_entity(ctx, T.Kind.INITIATIVE, new_payload,
                           derived_from=tuple(dict.fromkeys(old.provenance.derived_from + tuple(dsts))),
                           relation=old.relation, confidence=old.confidence,
                           decision_id=old.relevance.decision_id, weight=old.relevance.weight,
                           status=old.status)
            deltas.append(T.Supersede(old.id, with_id(e, old.id)))

        # RD4: one milestone per workstream that actually has work in it - a
        # count that follows the plan rather than a number fixed here.
        rank = {aid: i for i, aid in enumerate(order)}
        mil_targets: list[tuple[T.Entity, list[T.Entity]]] = []
        for ws in workstreams:
            ws_initiatives = {i.id for i in initiatives if i.payload.workstream_id == ws.id}
            ws_actions = [a for a in actions if a.payload.initiative_id in ws_initiatives]
            if ws_actions:
                mil_targets.append((ws, sorted(ws_actions, key=lambda a: rank.get(a.id, 0))))
        mil_ids = iter(fresh_ids(view, T.Kind.MILESTONE, len(mil_targets)))
        existing = {m.payload.text for m in live(view, T.Kind.MILESTONE)}
        for ws, ws_actions in mil_targets:
            text = f"{display_text(ws)}: every step in this workstream is complete"
            mid = next(mil_ids, None)
            if text in existing:
                continue
            criteria = tuple(dict.fromkeys(c for a in ws_actions for c in a.payload.done_when))
            payload = T.MilestonePayload(
                text=text, horizon=widest_horizon(ws_actions), gate=True, criteria=criteria,
                # RD3: a milestone carries a date only by naming the DEADLINE
                # that owns it. This method names none, so the date stays the
                # client's to give.
                deadline_id=None)
            e = new_entity(ctx, T.Kind.MILESTONE, payload,
                           derived_from=(ws.id,) + tuple(a.id for a in ws_actions),
                           relation=T.RelationToCentralDecision.INFORMS,
                           confidence=T.Confidence(None), decision_id=decision_id, weight=weight)
            deltas.append(T.Add(with_id(e, mid) if mid else e))

        return MethodResult(deltas=tuple(deltas), findings=tuple(findings))


def _v_acyclic(view, result: MethodResult) -> list[T.Finding]:
    """RD1 re-checked on the finished result: the DEPENDENCY rows a result
    writes, taken together with the ones already registered, are acyclic. The
    law holds on the result, not on the courtesy of the producer."""
    written = [d.entity for d in result.deltas
               if getattr(d, "entity", None) is not None and d.entity.kind is T.Kind.DEPENDENCY]
    if not written:
        return []
    edges: dict[str, set[str]] = {}
    for d in list(view.query(T.Kind.DEPENDENCY)) + written:
        if d.status in T.TERMINAL_STATUSES:
            continue
        edges.setdefault(d.payload.from_id, set()).add(d.payload.to_id)
        edges.setdefault(d.payload.to_id, set())
    nodes = sorted(edges)
    if topological(nodes, edges) is not None:
        return []
    return [T.Finding(law="M.roadmap.dependency_cycle", where="dependency",
                      issue="the dependency rows in this result close a cycle",
                      fix="drop the edge that closes the loop", entity_ids=tuple(nodes))]


def _v_no_forward_dependency(view, result: MethodResult) -> list[T.Finding]:
    """RD2 re-checked on the plan as the result would leave it: the live steps
    with whatever the result rewrites, against every declared edge including
    the ones the result adds."""
    written = {d.entity.id: d.entity for d in result.deltas
               if getattr(d, "entity", None) is not None}
    actions = [written.get(a.id, a) for a in view.query(T.Kind.ACTION)
               if a.status not in T.TERMINAL_STATUSES]
    actions += [e for _, e in sorted(written.items())
                if e.kind is T.Kind.ACTION and view.get(e.id) is None]
    deps = [written.get(d.id, d) for d in view.query(T.Kind.DEPENDENCY)
            if d.status not in T.TERMINAL_STATUSES]
    deps += [e for _, e in sorted(written.items())
             if e.kind is T.Kind.DEPENDENCY and view.get(e.id) is None]
    edges = declared_edges(actions, deps)
    return [T.Finding(law="M.roadmap.forward_dependency", where=eid,
                      issue=f"{eid} is sequenced at or before {dep}, which it depends on",
                      fix="re-sequence the two steps, or withdraw the dependency",
                      entity_ids=(eid, dep))
            for eid, dep in forward_dependencies(actions, edges)]


def _v_dates_owned_by_deadline(view, result: MethodResult) -> list[T.Finding]:
    """RD3 re-checked: no plan step this result writes prints a calendar date
    that no live DEADLINE owns. Removing this check is the named mutation
    "allow date strings on actions"."""
    deadlines = [d for d in view.query(T.Kind.DEADLINE) if d.status not in T.TERMINAL_STATUSES]
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind not in (T.Kind.ACTION, T.Kind.MILESTONE, T.Kind.INITIATIVE):
            continue
        owners = date_owners(view, e, deadlines)
        if e.kind is T.Kind.MILESTONE and e.payload.deadline_id:
            named = view.get(e.payload.deadline_id)
            if named is not None and named.kind is T.Kind.DEADLINE:
                owners.append(named)
        loose = dates_not_owned(display_text(e), owners)
        if loose:
            out.append(T.Finding(
                law="M.roadmap.date_not_owned_by_deadline", where=e.id or e.kind.value,
                issue=f"the calendar date(s) {', '.join(loose)} are printed on a plan step no DEADLINE owns",
                fix="state a horizon instead, or register the DEADLINE that carries the date",
                entity_ids=(e.id,) if e.id else ()))
    return out


Roadmap.spec = replace(Roadmap.spec, validators=(require_citations("roadmap"),
                                                 _v_acyclic,
                                                 _v_no_forward_dependency,
                                                 _v_dates_owned_by_deadline))
register(Roadmap)
