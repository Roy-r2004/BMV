"""issue_tree - decomposes a decision into the ISSUE nodes that must be
settled to make it (design 6.3, 7.3 row one).

MODEL_ASSISTED, two declared calls: structured_call issues the prompt once
and retries once with the validation errors appended. The model chooses each
node's shape from a catalogue rendered from the enums; method selection is a
function of those shapes alone, so the laws this module enforces are the
ones that keep free text out of the analysis-choosing path:

  * catalogue only  - a node whose interrogative, target kind or capability
    class is not an enum member is dropped: an off-catalogue shape could
    never be matched by a declared applicability and would sit in the tree
    as an unanswerable question that still counted as coverage.
  * every node cites - derived_from must name registered, live entities;
    a node resting on nothing (or on an id the model coined) is the model
    inventing structure, which the registry would render as if evidenced.
  * no method names  - a node that names a registered method is free text
    choosing the analysis, the exact thing universality forbids (design 1).
  * weight in [0,1]  - weight_to_parent is a share of the parent; a value
    outside the declared scale is not a judgement on that scale and is
    dropped rather than clamped (clamping would silently coin a judgement
    the model never made).
  * supersede, never duplicate - a returned node whose shape and parent
    match a live node restates it: the old row is superseded (lineage keeps
    it) instead of a twin being added, so re-running the method converges
    instead of growing the tree without bound.

Every drop is a Finding, never a silent omission: absence of an admitted
node is a first-class, visible state.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Iterable, Mapping

from app.engine import templating
from app.engine.llm import ModelCall, StructuredFailure, structured_call
from app.engine.methods.contract import (
    METHODS,
    EvidenceRequirement,
    InputSpec,
    MethodContext,
    MethodResult,
    MethodSpec,
    QuestionShape,
    new_entity,
    register,
)
from app.engine.types import (
    BOUNDS,
    FILTERABLE_FIELDS,
    TERMINAL_STATUSES,
    Add,
    AsksFor,
    CapabilityClass,
    Confidence,
    Entity,
    EntityDelta,
    ExecutionType,
    Finding,
    Interrogative,
    IssuePayload,
    Kind,
    RelationToCentralDecision,
    Severity,
    Supersede,
)
from app.ui_spec import _Tolerant

_PURPOSE = "issue_tree"


# =============================================================================
# Output schema. Fields are deliberately loose (strings, not enums): an
# off-catalogue value must REACH the validator and be dropped as one bad node,
# not fail pydantic validation and burn the whole response's retry (the
# design says the validator drops off-catalogue shapes, node by node).
# =============================================================================

class _NodeModel(_Tolerant):
    text: str = ""
    parent_id: str | None = None
    temp_id: str | None = None
    interrogative: str = ""
    target_kind: str = ""
    capability_class: str | None = None
    quantified: bool = False
    comparative: bool = False
    causal: bool = False
    temporal: bool = False
    weight_to_parent: float | None = None
    derived_from: list[str] = []
    decisive_for: list[str] = []
    evidence_needed: list[dict] = []


class IssueTreeModel(_Tolerant):
    nodes: list[_NodeModel] = []


# =============================================================================
# The laws, as small named checks shared by run() (pre-admission, where a bad
# node cannot even be constructed as an IssuePayload) and by the spec's
# declared validators (re-checking a finished MethodResult for the runner).
# =============================================================================

def _shape_of(node: _NodeModel) -> QuestionShape | None:
    """The catalogue check: every shape value must be an enum member. None
    means off-catalogue; the caller drops the node with a Finding."""
    try:
        interrogative = Interrogative(node.interrogative)
        target_kind = Kind(node.target_kind)
        cap = None if node.capability_class in (None, "", "null") else CapabilityClass(node.capability_class)
    except ValueError:
        return None
    return QuestionShape(interrogative, target_kind, bool(node.quantified), bool(node.comparative),
                         bool(node.causal), bool(node.temporal), cap)


def _cited(view, ids: Iterable[str]) -> bool:
    """Every cited id must resolve to a live registered entity. One coined id
    among real ones is still invention: all or nothing."""
    ids = tuple(ids)
    if not ids:
        return False
    for i in ids:
        e = view.get(i)
        if e is None or e.status in TERMINAL_STATUSES:
            return False
    return True


def _names_a_method(text: str) -> bool:
    """A node naming a registered method is free text steering selection.
    Both the id and its spaced form are checked: the model writes prose."""
    lowered = (text or "").lower()
    for m in METHODS.all():
        mid = m.spec.id.lower()
        if mid in lowered or mid.replace("_", " ") in lowered:
            return True
    return False


def _weight_ok(w: float | None) -> bool:
    return w is not None and 0.0 <= float(w) <= 1.0


def _asks_for(raw: Iterable[Any]) -> tuple[AsksFor, ...]:
    """evidence_needed as typed AsksFor. A filter key outside
    FILTERABLE_FIELDS is stripped (M2 at the output side: a question may not
    select evidence on prose either); an off-catalogue kind drops the entry."""
    out: list[AsksFor] = []
    for item in raw or ():
        if not isinstance(item, Mapping):
            continue
        try:
            kind = Kind(item.get("kind"))
        except ValueError:
            continue
        filt = item.get("filter")
        filt = dict(filt) if isinstance(filt, Mapping) else {}
        out.append(AsksFor(kind, {k: v for k, v in filt.items() if k in FILTERABLE_FIELDS}))
    return tuple(out)


def _node_key(shape: QuestionShape, parent_id: str | None) -> tuple:
    """What makes two nodes the same node: the structural shape and the place
    in the tree. Text is deliberately absent - a reworded restatement is
    still a restatement, and matching on prose would make convergence depend
    on the model's phrasing."""
    return (shape.interrogative, shape.target_kind, shape.quantified, shape.comparative,
            shape.causal, shape.temporal, shape.capability_class, parent_id)


def decomposed(existing: Iterable[Entity]) -> bool:
    """Whether this decision already carries a decomposition.

    A decision is decomposed ONCE. This method is the only writer of an ISSUE
    and `select_methods` reads its domain from open ISSUE rows, so every node
    it places that a declared shape takes on becomes another selection of this
    same method, which places another subtree, and so on: the producer feeds
    its own selection domain. Measured before this law: three hundred and
    seventy eight nodes on one engagement, four levels deep, from sixteen
    expansions of one decision, and the capability register and the option set
    are both linear in that number - so it was the tree that ran the engine
    past every ceiling it publishes, until the registry door refused a row.

    The stopping condition is the question's own, not a ceiling: "how does this
    decision break down" has been answered, and the answer is the tree. Read
    from the tree's own shape - a live node with a parent, the root being the
    decision restated rather than part of its own decomposition - and never
    from a count, a round number or a method name.

    What it changes is only what a later run may ADD: restatement still lands
    (Supersede, which is how the tree converges and how a re-run keeps its
    lineage), so nothing is truncated and a run that restates the tree exactly
    writes exactly what it wrote before.
    """
    return any(n.payload.parent_id for n in existing)


def _issues_in(result: MethodResult) -> list[Entity]:
    out: list[Entity] = []
    for d in result.deltas:
        e = getattr(d, "entity", None)
        if e is not None and e.kind == Kind.ISSUE:
            out.append(e)
    return out


def _finding(reason: str, detail: str) -> Finding:
    # A dropped candidate never entered the registry, so there is nothing for
    # the release gate to block on: the finding is the visible record of the
    # drop, not an open defect.
    return Finding(law=f"M.{_PURPOSE}.{reason}", where=_PURPOSE, issue=detail,
                   fix="the node was dropped; nothing was written for it",
                   severity=Severity.LOW, blocks_final=False)


# -- the spec's declared validators (re-check a finished result) --------------

def validate_catalogue(view, result: MethodResult) -> list[Finding]:
    """Every emitted node carries a catalogue shape and a bounded weight."""
    findings: list[Finding] = []
    for e in _issues_in(result):
        try:
            QuestionShape.of(e)
        except Exception:
            findings.append(_finding("off_catalogue", f"{e.id or e.payload.text[:60]}: shape is not from the catalogue"))
        if not _weight_ok(e.payload.weight_to_parent):
            findings.append(_finding("weight_out_of_bounds", f"{e.id or '?'}: weight_to_parent outside [0,1]"))
    return findings


def validate_citations(view, result: MethodResult) -> list[Finding]:
    """Every emitted node cites live registered entities."""
    return [_finding("uncited", f"{e.id or '?'}: derived_from does not resolve to live entities")
            for e in _issues_in(result) if not _cited(view, e.provenance.derived_from)]


def validate_no_method_names(view, result: MethodResult) -> list[Finding]:
    """No emitted node names a registered method."""
    return [_finding("names_a_method", f"{e.id or '?'}: node text names a method")
            for e in _issues_in(result) if _names_a_method(e.payload.text)]


# =============================================================================
# The spec (design 7.3): six interrogatives on DECISION, DECISION >= 1 and
# OBJECTIVE >= 1 required, ISSUE out, two model calls.
# =============================================================================

_SHAPES = tuple(QuestionShape(i, Kind.DECISION) for i in (
    Interrogative.WHAT, Interrogative.WHY, Interrogative.HOW,
    Interrogative.WHICH, Interrogative.HOW_MUCH, Interrogative.WHETHER))

SPEC = MethodSpec(
    id="issue_tree",
    version=1,
    applicability=_SHAPES,
    answers=tuple(s.interrogative for s in _SHAPES),
    required_inputs=(
        InputSpec("decision", Kind.DECISION, why_needed="the decision is the thing decomposed"),
        InputSpec("objective", Kind.OBJECTIVE, why_needed="objectives say what a settled issue must move"),
    ),
    optional_inputs=(),
    execution=ExecutionType.MODEL_ASSISTED,
    output_kinds=(Kind.ISSUE,),
    output_schema=IssueTreeModel,
    evidence=EvidenceRequirement(),
    limitations=(
        "weight_to_parent is a structuring judgement, not a probability and not a measurement",
        "the tree proposes questions; it settles nothing and coins no number",
    ),
    validators=(validate_catalogue, validate_citations, validate_no_method_names),
    cost_class=2,
    max_model_calls=2,
)


def _live(view, kind: Kind | None = None) -> list[Entity]:
    return [e for e in view.query(kind) if e.status not in TERMINAL_STATUSES]


def _wording(e: Entity) -> str:
    for attr in ("text", "statement", "name", "question", "title"):
        v = getattr(e.payload, attr, None)
        if v:
            return str(v)
    return ""


def _issue_ids(view, count: int) -> list[str]:
    """Ids are pre-assigned so a child payload can carry its parent's real id
    before the batch lands.

    They come from the registry's own counter (`reserve_ids`), not from the
    highest id this view happens to show: a specialist's window holds only its
    declared inputs, so an id counted off it collides with an ISSUE the
    assignment was never shown and I6 refuses the whole tree - which is what
    retired the second and every later expansion of the tree.
    """
    return view.reserve_ids(Kind.ISSUE, count)


@register
class IssueTreeMethod:
    spec = SPEC

    def run(self, ctx: MethodContext) -> MethodResult:
        view = ctx.registry
        decisions = _live(view, Kind.DECISION)
        objectives = _live(view, Kind.OBJECTIVE)
        existing = _live(view, Kind.ISSUE)
        # A decision is decomposed ONCE, and after that a run of this method
        # RESTATES the tree rather than growing it (`decomposed`).
        already_decomposed = decomposed(existing)
        # Everything live except the tree itself is citable context; the
        # prompt tells the model these ids are the only ones it may cite.
        citable = [e for e in _live(view) if e.kind != Kind.ISSUE]

        # The fanout ceiling comes from settings (ENGINE_MAX_FANOUT), never a
        # constant: no fixed count of anything per engagement.
        max_fanout = int(ctx.settings.get("MAX_FANOUT", BOUNDS["MAX_FANOUT"]))

        prompt = templating.render(
            "issue_tree.j2",
            decisions=[{"id": d.id, "role": d.payload.role.value, "text": _wording(d)} for d in decisions],
            objectives=[{"id": o.id, "text": _wording(o)} for o in objectives],
            entities=[{"id": e.id, "kind": e.kind.value, "text": _wording(e)} for e in citable],
            existing_nodes=[{"id": n.id, "parent_id": n.payload.parent_id, "text": _wording(n)} for n in existing],
            max_fanout=max_fanout,
        )
        call = ModelCall(purpose=_PURPOSE, messages=({"role": "user", "content": prompt},),
                         schema=IssueTreeModel, schema_version=SPEC.output_schema_version,
                         engagement_id=view.engagement_id)
        try:
            parsed, response = structured_call(ctx.provider, call)
        except StructuredFailure as exc:
            # No schema-valid tree is a blocked analysis, never a defaulted
            # one: the finding records it and nothing is written.
            return MethodResult(findings=(
                Finding(law=f"M.{_PURPOSE}.model_failure", where=_PURPOSE, issue=str(exc)[:300],
                        fix="re-run the analysis; the model produced no schema-valid tree",
                        severity=Severity.HIGH, blocks_final=False),))

        findings: list[Finding] = []
        candidates: list[tuple[_NodeModel, QuestionShape]] = []
        for node in parsed.nodes:
            text = (node.text or "").strip()
            if not text:
                findings.append(_finding("blank_text", "a node with no question text was dropped"))
                continue
            shape = _shape_of(node)
            if shape is None:
                findings.append(_finding("off_catalogue", f"{text[:80]!r}: shape values are not from the catalogue"))
                continue
            if _names_a_method(text):
                findings.append(_finding("names_a_method", f"{text[:80]!r}: node text names a method"))
                continue
            if not _cited(view, node.derived_from):
                findings.append(_finding("uncited", f"{text[:80]!r}: derived_from does not resolve to live entities"))
                continue
            if not _weight_ok(node.weight_to_parent):
                findings.append(_finding("weight_out_of_bounds", f"{text[:80]!r}: weight_to_parent outside [0,1]"))
                continue
            candidates.append((node, shape))

        # -- placement: resolve parents, then supersede-or-add by node key ---
        live_issue_ids = {n.id for n in existing}
        existing_by_key = {_node_key(QuestionShape.of(n), n.payload.parent_id): n for n in existing}
        central = view.central_decision()
        live_decisions = {d.id for d in decisions}
        fresh = iter(_issue_ids(view, len(candidates)))

        deltas: list[EntityDelta] = []
        real_of_temp: dict[str, str] = {}
        emitted_keys: dict[tuple, str] = {}
        batch_temps = {n.temp_id for n, _ in candidates if n.temp_id}
        pending = list(candidates)
        # Worklist rounds: a child resolves only after its parent has a real
        # id, whatever order the model listed them in. A parent that never
        # resolves (unknown id, or a cycle of temp ids) takes its subtree
        # with it - a node whose place in the tree is unknowable is not
        # placed somewhere else instead.
        progress = True
        while pending and progress:
            progress = False
            still: list[tuple[_NodeModel, QuestionShape]] = []
            for node, shape in pending:
                parent_raw = node.parent_id or None
                if parent_raw is None:
                    parent_real = None
                elif parent_raw in live_issue_ids:
                    parent_real = parent_raw
                elif parent_raw in real_of_temp:
                    parent_real = real_of_temp[parent_raw]
                elif parent_raw in batch_temps:
                    still.append((node, shape))       # parent not landed yet
                    continue
                else:
                    findings.append(_finding("unresolvable_parent",
                                             f"{node.text[:80]!r}: parent {parent_raw!r} is no known node"))
                    batch_temps.discard(node.temp_id)
                    progress = True
                    continue

                progress = True
                key = _node_key(shape, parent_real)
                if key in emitted_keys:
                    # The batch restated one of its own nodes: children of the
                    # twin attach to the survivor instead of being orphaned.
                    if node.temp_id:
                        real_of_temp[node.temp_id] = emitted_keys[key]
                    findings.append(_finding("duplicate", f"{node.text[:80]!r}: restates a node from this batch"))
                    continue
                old = existing_by_key.get(key)
                if old is not None and old.provenance.actor_ref != ctx.actor_ref:
                    # The node is already on the tree, placed by another run.
                    # Restating it would be a Supersede against a row this
                    # assignment does not own, which S1 refuses - and S1 is
                    # right: one role does not edit another's record. The node
                    # already says what this batch wanted to say, so the
                    # children attach to it and the restatement is recorded.
                    if node.temp_id:
                        real_of_temp[node.temp_id] = old.id
                    emitted_keys[key] = old.id
                    findings.append(_finding("duplicate",
                                             f"{node.text[:80]!r}: restates a node another run placed"))
                    continue
                if old is not None:
                    real_id = old.id
                elif already_decomposed:
                    # The decision is decomposed and this node is not on the
                    # tree: it is a NEW question, and a new question at this
                    # point grows the tree instead of restating it.
                    #
                    # This method is the only writer of an ISSUE, and
                    # `select_methods` reads its domain from open ISSUE rows -
                    # so every node it places that a declared shape takes on
                    # becomes another selection of this same method, which
                    # places another subtree, and so on. Measured before this
                    # law: three hundred and seventy eight nodes on one
                    # engagement, four levels deep, from sixteen expansions of
                    # one decision, and the capability register and the option
                    # set are both linear in that number - so it was the tree
                    # that ran the engine past every ceiling it publishes,
                    # until the registry door refused a row.
                    #
                    # The stopping condition is the question's own: "how does
                    # this decision break down" has been answered, and the
                    # answer is the tree. Restatement still lands (the branch
                    # above), so a second run converges rather than being
                    # refused; only growth stops. The drop is recorded and the
                    # subtree beneath it goes with it, because a node whose
                    # place in the tree is not admitted has no place for its
                    # children either.
                    findings.append(_finding(
                        "already_decomposed",
                        f"{node.text[:80]!r}: the decision is already decomposed; "
                        "a node the tree does not carry is not added"))
                    batch_temps.discard(node.temp_id)
                    continue
                else:
                    reserved = next(fresh, None)
                    if reserved is None:               # pragma: no cover - one id per candidate
                        reserved = _issue_ids(view, 1)[0]
                    real_id = reserved

                decisive = tuple(i for i in node.decisive_for if i in live_decisions)
                payload = IssuePayload(
                    text=node.text.strip(), interrogative=shape.interrogative, target_kind=shape.target_kind,
                    parent_id=parent_real, quantified=shape.quantified, comparative=shape.comparative,
                    causal=shape.causal, temporal=shape.temporal, capability_class=shape.capability_class,
                    weight_to_parent=float(node.weight_to_parent), decisive_for=decisive,
                    evidence_needed=_asks_for(node.evidence_needed))
                entity = new_entity(
                    ctx, Kind.ISSUE, payload,
                    derived_from=tuple(node.derived_from),
                    relation=RelationToCentralDecision.INFORMS,
                    confidence=Confidence(None),
                    decision_id=decisive[0] if decisive else (central.id if central is not None else None),
                    # Until path_impact refines it, the node's share of its
                    # parent is the best available statement of how much it
                    # can move the decision.
                    weight=payload.weight_to_parent,
                    model_call_id=response.call_id)
                entity = dataclasses.replace(entity, id=real_id)
                deltas.append(Supersede(old.id, entity) if old is not None else Add(entity))
                emitted_keys[key] = real_id
                if node.temp_id:
                    real_of_temp[node.temp_id] = real_id
            pending = still
        for node, _ in pending:
            findings.append(_finding("unresolvable_parent",
                                     f"{node.text[:80]!r}: parent reference never resolved (temp-id cycle)"))

        return MethodResult(deltas=tuple(deltas), findings=tuple(findings),
                            model_call_ids=(response.call_id,))
