"""systems_data_map - what the systems are and what they depend on (design 7.3
row systems_data_map): HOW/WHAT on CAPABILITY of class SOFTWARE_SYSTEM or
DATA_AND_INTEGRATION.

MODEL_ASSISTED with one call: naming what a set of facts describes is wording
work. Deciding whether the resulting graph is a graph at all is not, so the
acyclic law is imported from roadmap.py - one implementation, so one mutation
kills both methods' tests.

Laws this module enforces, each in the docstring of the thing enforcing it:

  SD1 the dependency graph stays acyclic. An edge that would close a cycle is
      refused before it is written, named in a Finding, and the rest of the
      map still lands: a loop between two systems is a statement the model
      made that the engagement cannot hold, and it is shown rather than
      quietly dropped (run(), _v_acyclic_map).
  SD2 a system this method writes carries the class its declared subject
      names - SOFTWARE_SYSTEM or DATA_AND_INTEGRATION, resolved from the
      cited input, never from the model's own word for it (_class_for,
      _v_declared_classes).
  SD3 an edge joins two systems that exist: an endpoint that is neither a
      cited input nor a capability written in this same run is not a
      dependency, it is a name (run()).
  SD4 no figure appears that no cited input carries (coined_figures), and
      every output cites its inputs (require_citations).
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
    parse_enum,
    propose,
    refusal,
    reply_questions,
    require_citations,
    with_id,
)
from app.engine.methods.builtin.roadmap import closes_a_cycle


# The two classes this method's subject covers. A model-supplied class outside
# them is not admitted: the method was selected for a shape, and the shape says
# which lane its outputs belong to.
_DECLARED: tuple[T.CapabilityClass, ...] = (T.CapabilityClass.SOFTWARE_SYSTEM,
                                            T.CapabilityClass.DATA_AND_INTEGRATION)

_INSTRUCTIONS = """Map the systems and data flows the facts above describe.
- "capability" outputs are one system or one data set each. fields: "capability_class"
  (software_system | data_and_integration), "ref" (a short label like S1 so a dependency
  can point at this output), "gap" (missing | partial | present_unused | present).
- "dependency" outputs are edges. fields: "from" and "to" (each a ref of a capability
  output above or the id of a CAPABILITY input), "kind" (requires | informs | blocks).
Name only systems the facts mention. Do not invent an integration nobody described,
and do not state a volume, a cost or a count that no input carries."""


def _class_for(value: Any, fallback: T.CapabilityClass) -> T.CapabilityClass:
    """SD2: the class of a system this method writes. A model string is read
    only as a choice between the two the declared subject covers; anything
    else - a misspelling, a lane this method was not selected for - falls back
    to the shape's own class rather than widening the method's remit."""
    parsed = parse_enum(T.CapabilityClass, value)
    return parsed if parsed in _DECLARED else fallback


class SystemsDataMap:
    spec = MethodSpec(
        id="systems_data_map", version=1,
        applicability=(
            QuestionShape(T.Interrogative.HOW, T.Kind.CAPABILITY,
                          capability_class=T.CapabilityClass.SOFTWARE_SYSTEM),
            QuestionShape(T.Interrogative.WHAT, T.Kind.CAPABILITY,
                          capability_class=T.CapabilityClass.SOFTWARE_SYSTEM),
            QuestionShape(T.Interrogative.HOW, T.Kind.CAPABILITY,
                          capability_class=T.CapabilityClass.DATA_AND_INTEGRATION),
            QuestionShape(T.Interrogative.WHAT, T.Kind.CAPABILITY,
                          capability_class=T.CapabilityClass.DATA_AND_INTEGRATION),
        ),
        answers=(T.Interrogative.HOW, T.Interrogative.WHAT),
        required_inputs=(
            InputSpec("facts", T.Kind.FACT,
                      why_needed="a systems map describes what the engagement has recorded, not what is typical"),
        ),
        optional_inputs=(
            InputSpec("systems", T.Kind.CAPABILITY, min_count=0,
                      filter={"capability_class": [T.CapabilityClass.SOFTWARE_SYSTEM,
                                                   T.CapabilityClass.DATA_AND_INTEGRATION]},
                      why_needed="systems already registered"),
            InputSpec("dependencies", T.Kind.DEPENDENCY, min_count=0, why_needed="edges already declared"),
        ),
        execution=T.ExecutionType.MODEL_ASSISTED,
        output_kinds=(T.Kind.CAPABILITY, T.Kind.DEPENDENCY),
        output_schema=GenericReply,
        evidence=EvidenceRequirement(),
        limitations=("maps what the registered facts describe; it never infers an integration "
                     "from what systems of this kind usually have",),
        validators=(),
        cost_class=2, max_model_calls=1)

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        issue, decision_id, weight = issue_frame(ctx)
        fallback = _DECLARED[0]
        if issue is not None and issue.payload.capability_class in _DECLARED:
            fallback = issue.payload.capability_class

        facts = live(view, T.Kind.FACT)
        systems = [c for c in live(view, T.Kind.CAPABILITY) if c.payload.capability_class in _DECLARED]
        edges_now = live(view, T.Kind.DEPENDENCY)
        inputs = facts + systems
        if not facts:
            q = T.QuestionPayload(
                text="Which systems and data sets does this part of the business run on today?",
                asks_for=(T.AsksFor(T.Kind.FACT),), issue_ids=ctx.issue_ids,
                why="a systems map is a map of what is there, and nothing is recorded yet",
                effort=T.EffortClass.LOOKUP, strategy=T.FillStrategy.ASK_CLIENT)
            return MethodResult(questions=(q,))

        reply, call_id, fails = propose(
            ctx, self.spec, purpose="map the systems and data dependencies the registered facts describe",
            inputs=inputs, instructions=_INSTRUCTIONS)
        if reply is None:
            return MethodResult(findings=fails)

        permitted = frozenset(e.id for e in inputs)
        by_id = {e.id: e for e in inputs}
        findings: list[T.Finding] = []
        deltas: list[T.EntityDelta] = []

        cap_outputs = [o for o in reply.outputs if o.kind == "capability"]
        cap_ids = fresh_ids(view, T.Kind.CAPABILITY, len(cap_outputs))
        refmap: dict[str, str] = {}
        for out, cid in zip(cap_outputs, cap_ids):
            ref = str(out.fields.get("ref") or "").strip()
            if ref:
                refmap[ref] = cid

        # The graph the run starts from: every edge already registered among
        # the systems the engagement holds. New edges are tested against it.
        edges: dict[str, set[str]] = {}
        for s in systems:
            edges.setdefault(s.id, set())
        for cid in cap_ids:
            edges.setdefault(cid, set())
        for d in edges_now:
            if d.payload.from_id in edges and d.payload.to_id in edges:
                edges[d.payload.from_id].add(d.payload.to_id)

        def endpoint(value: Any) -> str | None:
            """SD3: a ref of a system written in this run, or the id of a
            system input. A name that is neither is not an endpoint."""
            v = str(value or "").strip()
            if v in refmap:
                return refmap[v]
            e = by_id.get(v)
            return v if e is not None and e.kind is T.Kind.CAPABILITY else None

        cursor = iter(cap_ids)
        pending_edges: list[tuple[Any, str, str, tuple[str, ...]]] = []
        for out in reply.outputs:
            ids = cited(out, permitted)
            if not ids:
                findings.append(refusal(self.spec.id, "uncited_output", out.kind or "output",
                                        "the model cited no registered input"))
                if out.kind == "capability":
                    next(cursor, None)          # keep refs aligned with pre-assigned ids
                continue
            coined = coined_figures([out.text], [display_text(by_id.get(i)) for i in ids])
            if coined:
                findings.append(refusal(self.spec.id, "invented_figure", out.kind or "output",
                                        f"figure(s) {', '.join(coined)} appear in no cited input"))
                if out.kind == "capability":
                    next(cursor, None)
                continue
            if out.kind == "capability":
                cid = next(cursor, None)
                payload = T.CapabilityPayload(
                    text=out.text,
                    capability_class=_class_for(out.fields.get("capability_class"), fallback),
                    gap=parse_enum(T.GapState, out.fields.get("gap"), T.GapState.PRESENT),
                    evidence=ids)
                e = new_entity(ctx, T.Kind.CAPABILITY, payload, derived_from=ids,
                               relation=T.RelationToCentralDecision.INFORMS,
                               confidence=T.Confidence(None, "model_estimate"),
                               decision_id=decision_id, weight=weight, model_call_id=call_id)
                deltas.append(T.Add(with_id(e, cid) if cid else e))
            elif out.kind == "dependency":
                src, dst = endpoint(out.fields.get("from")), endpoint(out.fields.get("to"))
                if src is None or dst is None:
                    findings.append(refusal(self.spec.id, "unknown_endpoint", out.text or "dependency",
                                            "an edge endpoint names no registered or newly written system"))
                    continue
                pending_edges.append((out, src, dst, ids))
            else:
                findings.append(refusal(self.spec.id, "undeclared_kind", out.kind or "output",
                                        "an output outside the declared kinds is dropped"))

        # SD1: edges are admitted one at a time, in the order the model gave
        # them, each against the graph as it stands. The first edge of a loop
        # is lawful; the one that closes it is refused and named.
        dep_ids = iter(fresh_ids(view, T.Kind.DEPENDENCY, len(pending_edges)))
        for out, src, dst, ids in pending_edges:
            did = next(dep_ids, None)
            if dst in edges.get(src, set()):
                continue                        # already declared; a re-run adds nothing
            if closes_a_cycle(edges, src, dst):
                findings.append(T.Finding(
                    law="M.systems_data_map.dependency_cycle", where=did or src,
                    issue=f"{src} cannot depend on {dst}: the edge closes a cycle in the systems map",
                    fix="drop one edge of the loop, or split the system that appears on both sides",
                    # Nothing unsafe landed - the edge was refused before it was
                    # written - so the record is visible without blocking FINAL.
                    entity_ids=(src, dst), blocks_final=False))
                continue
            edges.setdefault(src, set()).add(dst)
            payload = T.DependencyPayload(from_id=src, to_id=dst,
                                          kind=str(out.fields.get("kind") or "requires"))
            e = new_entity(ctx, T.Kind.DEPENDENCY, payload, derived_from=ids,
                           relation=T.RelationToCentralDecision.DEPENDS_ON,
                           confidence=T.Confidence(None, "model_estimate"),
                           decision_id=decision_id, weight=weight, model_call_id=call_id)
            deltas.append(T.Add(with_id(e, did) if did else e))

        return MethodResult(deltas=tuple(deltas), questions=reply_questions(reply, ctx),
                            findings=tuple(findings),
                            model_call_ids=(call_id,) if call_id else ())


def _v_acyclic_map(view, result: MethodResult) -> list[T.Finding]:
    """SD1 re-checked on the finished result: the edges it writes, taken with
    the ones already registered, close no cycle. Removing this check is the
    named mutation "remove the cycle check"."""
    written = [d.entity for d in result.deltas
               if getattr(d, "entity", None) is not None and d.entity.kind is T.Kind.DEPENDENCY]
    if not written:
        return []
    edges: dict[str, set[str]] = {}
    rows = [d for d in view.query(T.Kind.DEPENDENCY) if d.status not in T.TERMINAL_STATUSES]
    for d in rows:
        edges.setdefault(d.payload.from_id, set()).add(d.payload.to_id)
        edges.setdefault(d.payload.to_id, set())
    out: list[T.Finding] = []
    for d in written:
        src, dst = d.payload.from_id, d.payload.to_id
        edges.setdefault(src, set())
        edges.setdefault(dst, set())
        if closes_a_cycle(edges, src, dst):
            out.append(T.Finding(
                law="M.systems_data_map.dependency_cycle", where=d.id or "dependency",
                issue=f"{src} -> {dst} closes a cycle in the systems map",
                fix="drop one edge of the loop", entity_ids=(src, dst)))
            continue
        edges[src].add(dst)
    return out


def _v_declared_classes(view, result: MethodResult) -> list[T.Finding]:
    """SD2 re-checked: every CAPABILITY this method wrote sits in one of the
    two lanes its declared subject covers, as an enum member. A system filed
    under another class would answer a shape this method was never selected
    for."""
    out: list[T.Finding] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is None or e.kind is not T.Kind.CAPABILITY:
            continue
        if e.payload.capability_class not in _DECLARED:
            out.append(T.Finding(
                law="M.systems_data_map.undeclared_class", where=e.id or "capability",
                issue=f"a systems-map capability is filed as {e.payload.capability_class.value}",
                fix="file it under software_system or data_and_integration, the method's declared subject"))
    return out


SystemsDataMap.spec = replace(SystemsDataMap.spec, validators=(require_citations("systems_data_map"),
                                                               _v_acyclic_map,
                                                               _v_declared_classes))
register(SystemsDataMap)
