"""mapping - the r30 package as engine entities (design 13.3).

Everything r30 produced arrives here as data and leaves as typed rows with
`Actor.LEGACY_R30` provenance and an `actor_ref` that names the exact place
it came from (`r30:request:<id>:<path>`), so a reader of any engine artifact
can walk back to the claim, the module or the layer that says it.

The laws this module enforces, each in the docstring of the thing that
enforces it:

  M1  a machine-computed number is CONFIRMED only after the engine's own
      calculator recomputes it EXACTLY. A number whose arithmetic the engine
      can express and disagrees with is a blocking Finding; one whose
      arithmetic it cannot express is a non-blocking record and is not
      imported at all - absent evidence is not evidence of a defect
      (`_machine_computed`, `confirmations`).
  M2  a consultant-proposed number arrives as an UNAPPROVED ASSUMPTION
      carrying r30's own approval label, never as a fact (`_consultant_proposed`).
  M3  a client number is not duplicated: the claim resolves to the FACT the
      client already stated, by exact question-and-answer identity
      (`_client_input`).
  M4  the canonical gate sentence is `pilot_gate.canonical_sentence` verbatim -
      the engine restates it, never rewrites it (`_canonical_gate`).
  M5  the Request row is read-only throughout: `import_r30` measures it before
      and after and refuses its own output if it changed (design 13.4, A3).
  M6  an r30 package that is not FINAL blocks the engine's FINAL, through
      L13 findings built from r30's own release reasons and integrity report
      (`release_findings`).

No branch test in this module compares against a string constant: r30's
vocabulary lives in the declared tables below and is reached by lookup
(design 18.2).
"""
from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field, replace
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Sequence

from app.engine import types as T
from app.engine.calc.units import canonical_unit, family_of
from app.engine.legacy.r30_adapter import (
    VOLUME_KINDS,
    R30Inputs,
    R30Outputs,
    assert_row_untouched,
    snapshot,
)
from app.engine.work_products.statements import token_for
from app.pipeline import pilot_gate as _pilot_gate
from app.pipeline import registry as _r30_registry

# The law this component reports under. LawId lives in gates/laws.py (design
# section 3); the literal is stated here so the adapter can name its findings
# before that module lands, and the frozen value is the one LawId.L13 holds.
LAW_LEGACY_NOT_FINAL = "L13.legacy_r30_not_final"

# r30's four provenance words (`app/pipeline/registry.py:93`). A table, not a
# chain of comparisons: the vocabulary is data the engine looks up.
PROVENANCE_CLIENT = "client_input"
PROVENANCE_MACHINE = "machine_computed"
PROVENANCE_GATE = "canonical_gate"
PROVENANCE_PROPOSED = "consultant_proposed"

# The operators r30 writes into a derived claim's `source` ("DV-01 / 365 x 30")
# mapped to the engine's formula grammar (`calc/arith.evaluate`).
_OPERATORS: Mapping[str, str] = {"/": "/", "*": "*", "x": "*", "X": "*", "+": "+", "-": "-"}

# r30 rounds its derived values to two decimals (`app/pipeline/registry.py:380`).
_PRECISION = 2

# The layer names `integrity.load` puts on the row's JSON columns
# (`app/pipeline/integrity.py:70`). The engine reads the loaded content by
# these keys rather than the column names, so a column rename inside r30
# cannot silently empty a layer here.


class LegacyImportError(RuntimeError):
    """The import produced rows the engine may not keep."""


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LegacyImport:
    """Deltas to apply, findings to report, and the claim-to-entity map the
    caller needs to trace a rendered number back to r30."""
    deltas: tuple[T.EntityDelta, ...] = ()
    findings: tuple[T.Finding, ...] = ()
    # claim id -> engine entity id, so a rendered number traces back to the
    # r30 claim that carries it. A client claim maps to the FACT the client
    # already stated, never to a copy of it.
    entity_by_claim: Mapping[str, str] = dataclass_field(default_factory=dict)
    workstream_id: str | None = None
    volume_ids: tuple[str, ...] = ()

    @property
    def entities(self) -> tuple[T.Entity, ...]:
        return tuple(d.entity for d in self.deltas if getattr(d, "entity", None) is not None)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _live(view, kind: T.Kind) -> list[T.Entity]:
    return [e for e in view.query(kind) if e.status not in T.TERMINAL_STATUSES]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _joined_text(*parts: Any) -> str:
    """r30's own strings laid end to end, nothing added. Used where one engine
    field holds what r30 kept in two (a risk and its counter-move, a metric
    and its target): the words are r30's, the order is r30's."""
    return " ".join(p for p in (_text(x) for x in parts) if p)


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


class _Reserver:
    """Ids assigned ahead of the registry so rows written in one batch can
    reference each other (an initiative names its workstream, a criterion its
    initiative). Computed past every id visible in the view; a hidden higher
    id makes the registry refuse the whole batch (I6), which is an admission
    failure and never a silent overwrite.

    It is not `methods/builtin/org_design.fresh_ids`: importing a builtin
    method module here would make `app.engine.legacy` depend on the whole
    registration sweep, and the sweep imports this package."""

    def __init__(self, view):
        self._next: dict[T.Kind, int] = {}
        self._view = view

    def take(self, kind: T.Kind) -> str:
        top = self._next.get(kind)
        if top is None:
            top = 0
            for e in self._view.query(kind):
                _, _, num = e.id.rpartition("-")
                if num.isdigit():
                    top = max(top, int(num))
        top += 1
        self._next[kind] = top
        return f"{T.ID_PREFIX[kind]}-{top}"


class _Pending:
    """A read side over the registry plus the rows this import has not written
    yet, so `calc.recompute` can check a calculated fact against the inputs
    that arrive in the same batch. `get` is the only method the calculator
    uses; nothing else is offered, because nothing else would be true."""

    def __init__(self, view):
        self._view = view
        self._new: dict[str, T.Entity] = {}

    def add(self, e: T.Entity) -> None:
        if e.id:
            self._new[e.id] = e

    def get(self, entity_id: str) -> T.Entity | None:
        e = self._new.get(entity_id)
        return e if e is not None else self._view.get(entity_id)

    def has(self, entity_id: str) -> bool:
        return self.get(entity_id) is not None


# ---------------------------------------------------------------------------
# The importer
# ---------------------------------------------------------------------------

class _Import:
    """One import run. Holds the reserved ids, the pending rows and the
    findings; every mapper below is a method on it so the actor_ref, the
    decision the rows attach to and the citation rules are stated once."""

    def __init__(self, outputs: R30Outputs, view, *, inputs: R30Inputs, calc: Any,
                 engagement_id: str, decision_id: str | None, weight: float):
        self.out = outputs
        self.view = view
        self.inputs = inputs
        self.calc = calc
        self.engagement_id = engagement_id
        self.decision_id = decision_id
        self.weight = weight
        self.ids = _Reserver(view)
        self.pending = _Pending(view)
        self.deltas: list[T.EntityDelta] = []
        self.findings: list[T.Finding] = []
        self.by_claim: dict[str, str] = {}
        self.consumed: set[str] = set()
        self.workstream_id: str | None = None
        self.initiative_by_module: dict[str, str] = {}
        self.volume_ids: list[str] = []
        # The client's own numbers, keyed the way r30 will restate them, so a
        # client_input claim resolves to the FACT the client stated (M3).
        self.fact_by_answer: dict[tuple[str, str], str] = {
            (p.question, p.answer): p.entity_id for p in inputs.ops_numbers}

    # -- construction -------------------------------------------------------
    def ref(self, path: str) -> str:
        return f"r30:request:{self.out.request_id}:{path}"

    def add(self, kind: T.Kind, payload: Any, *, path: str, derived_from: Sequence[str],
            entity_id: str | None = None, relation: T.RelationToCentralDecision | None = None,
            confidence: T.Confidence | None = None, status: T.Status = T.Status.PROPOSED,
            labels: tuple[str, ...] = ()) -> str:
        """One row. A legacy row cites what it rests on exactly as a method
        output does: the entities that commissioned the run, and whatever it
        was derived from inside the package."""
        cites = tuple(dict.fromkeys([c for c in derived_from if c]))
        if not cites:
            raise LegacyImportError(f"{kind.value} from {path} cites nothing")
        eid = entity_id or self.ids.take(kind)
        e = T.make_entity(
            kind=kind, engagement_id=self.engagement_id, payload=payload,
            provenance=T.Provenance(actor=T.Actor.LEGACY_R30, actor_ref=self.ref(path), derived_from=cites),
            confidence=confidence or T.Confidence(None),
            relevance=T.Relevance(decision_id=self.decision_id, weight=self.weight),
            relation=relation or T.RelationToCentralDecision.INFORMS,
            status=status, entity_id=eid, labels=labels)
        self.deltas.append(T.Add(e))
        self.pending.add(e)
        return eid

    def finding(self, where: str, issue: str, fix: str, *, blocks: bool,
                entity_ids: tuple[str, ...] = ()) -> None:
        self.findings.append(T.Finding(
            law=LAW_LEGACY_NOT_FINAL, where=where, issue=issue, fix=fix,
            severity=T.Severity.HIGH if blocks else T.Severity.LOW,
            entity_ids=entity_ids, blocks_final=blocks))

    @property
    def commissioned_by(self) -> tuple[str, ...]:
        """The entities that caused this run. Every legacy row rests on them,
        so deleting the engagement's evidence orphans the legacy package
        rather than leaving it floating."""
        return tuple(self.inputs.source_entity_ids)

    # -- 1. the workstream --------------------------------------------------
    def workstream(self) -> None:
        """The technology workstream the package was delivered under: the one
        the caller named, or a fresh one named by the issue this run settles.
        Either way `close_workstream` records the request that delivered it -
        `has_legacy_request` is what the work-product planner counts
        (`work_products/decl.py:253`) and what the gate reads to find the
        package (`gates/laws.legacy_request_ids`)."""
        target = self.view.get(self.inputs.workstream_id) if self.inputs.workstream_id else None
        if target is not None and target.kind is T.Kind.WORKSTREAM:
            self.workstream_id = target.id
            return
        name = self.inputs.main_problem or self.inputs.business_description
        payload = T.WorkstreamPayload(name=name, purpose=self.inputs.desired_outcome,
                                      capability_classes=(T.CapabilityClass.SOFTWARE_SYSTEM,),
                                      legacy_request_id=self.out.request_id)
        self.workstream_id = self.add(T.Kind.WORKSTREAM, payload, path="workstream",
                                      derived_from=self.commissioned_by,
                                      relation=T.RelationToCentralDecision.DEPENDS_ON)

    def close_workstream(self) -> None:
        """The workstream row, last: it names every initiative the package
        delivered and the request that delivered them. An existing workstream
        is superseded (the old row stays in lineage) and the new row is
        PROPOSED, because it says something new that no authority has yet
        confirmed; a fresh one is rewritten in place before it is applied,
        because it was never written."""
        if self.workstream_id is None:
            return
        initiative_ids = tuple(self.initiative_by_module.values())
        target = self.view.get(self.workstream_id)
        for i, d in enumerate(self.deltas):
            e = getattr(d, "entity", None)
            if e is not None and e.id == self.workstream_id:
                payload = replace(e.payload, initiative_ids=tuple(e.payload.initiative_ids) + initiative_ids)
                self.deltas[i] = T.Add(replace(e, payload=payload))
                self.pending.add(self.deltas[i].entity)
                return
        if target is None:
            return
        payload = replace(target.payload,
                          legacy_request_id=self.out.request_id,
                          initiative_ids=tuple(dict.fromkeys(
                              tuple(target.payload.initiative_ids) + initiative_ids)))
        e = T.make_entity(
            kind=T.Kind.WORKSTREAM, engagement_id=self.engagement_id, payload=payload,
            provenance=T.Provenance(actor=T.Actor.LEGACY_R30, actor_ref=self.ref("workstream"),
                                    derived_from=tuple(dict.fromkeys(
                                        target.provenance.derived_from + self.commissioned_by))),
            confidence=target.confidence, relevance=target.relevance, relation=target.relation,
            status=T.Status.PROPOSED, entity_id=target.id, labels=target.labels)
        self.deltas.append(T.Supersede(target.id, e))
        self.pending.add(e)

    # -- 2. modules ---------------------------------------------------------
    def modules(self) -> None:
        """Every module the package designed becomes an INITIATIVE under the
        workstream, and every declared dependency an ordinary DEPENDENCY row:
        the technology work sits beside the rest of the roadmap rather than in
        a compartment of its own (design 13.4)."""
        if self.workstream_id is None:
            return
        for m in self.out.modules:
            mid = _text(m.get("id"))
            name = _text(m.get("client_facing_name")) or _text(m.get("display_name")) or mid
            if not mid or not name:
                continue
            payload = T.InitiativePayload(name=name, workstream_id=self.workstream_id,
                                          capability_class=T.CapabilityClass.SOFTWARE_SYSTEM,
                                          purpose=_text(m.get("phase")))
            self.initiative_by_module[mid] = self.add(
                T.Kind.INITIATIVE, payload, path=f"module:{mid}",
                derived_from=(self.workstream_id,) + self.commissioned_by,
                relation=T.RelationToCentralDecision.DEPENDS_ON)
        for m in self.out.modules:
            mid = _text(m.get("id"))
            here = self.initiative_by_module.get(mid)
            if here is None:
                continue
            for dep in (m.get("dependencies") or m.get("depends_on") or []):
                there = self.initiative_by_module.get(_text(dep))
                if there is None or there == here:
                    continue
                self.add(T.Kind.DEPENDENCY,
                         T.DependencyPayload(from_id=here, to_id=there),
                         path=f"module:{mid}:depends_on:{_text(dep)}",
                         derived_from=(here, there),
                         relation=T.RelationToCentralDecision.DEPENDS_ON)

    # -- 3. the canonical gate ---------------------------------------------
    def canonical_gate(self) -> None:
        """M4. The pilot gate is a subordinate decision with a success
        criterion and one STATEMENT whose text is
        `pilot_gate.canonical_sentence` (`app/pipeline/pilot_gate.py:413`)
        character for character. Every restatement of the gate anywhere in the
        engine's products renders that statement's token, so a paraphrase is
        structurally impossible rather than merely discouraged."""
        gate = self.out.registry.get("pilot_gate")
        sentence = _pilot_gate.canonical_sentence(gate if isinstance(gate, Mapping) else None)
        if not sentence:
            return
        claims = [c for c in self.out.claims if _text(c.get("provenance")) == PROVENANCE_GATE]
        self.consumed.update(_text(c.get("id")) for c in claims)
        cites = tuple(self.initiative_by_module.values()) + self.commissioned_by

        decision_id = self.add(
            T.Kind.DECISION,
            T.DecisionPayload(statement=sentence, role=T.DecisionRole.SUBORDINATE),
            path="pilot_gate", derived_from=cites,
            relation=T.RelationToCentralDecision.RESOLVES)

        target = None
        unit = ""
        if isinstance(gate, Mapping):
            target = _decimal(gate.get("target_value"))
            unit = _text(gate.get("target_unit"))
        criterion = T.SuccessCriterionPayload(
            text=sentence,
            target=T.Quantity(target, canonical_unit(unit) or unit or "count",
                              family_of(unit), precision=_PRECISION) if target is not None and unit else None)
        criterion_id = self.add(T.Kind.SUCCESS_CRITERION, criterion, path="pilot_gate:criterion",
                                derived_from=(decision_id,) + cites,
                                relation=T.RelationToCentralDecision.DEFINES)
        for c in claims:
            self.by_claim[_text(c.get("id"))] = criterion_id

        statement_id = self.ids.take(T.Kind.STATEMENT)
        self.add(T.Kind.STATEMENT,
                 T.StatementPayload(text=sentence, of_entity_id=criterion_id,
                                    token=token_for(statement_id)),
                 path="pilot_gate:statement", derived_from=(criterion_id,),
                 entity_id=statement_id)

    # -- 4. module KPIs -----------------------------------------------------
    def module_kpis(self) -> None:
        """A module's KPI claims become SUCCESS_CRITERIONs on that module's
        initiative. The claim keeps its own approval word, so a proposed
        threshold stays visibly proposed wherever it is rendered."""
        for m in self.out.modules:
            mid = _text(m.get("id"))
            initiative = self.initiative_by_module.get(mid)
            if initiative is None:
                continue
            for claim_id in (m.get("kpi_claim_ids") or []):
                claim = self._claim(_text(claim_id))
                if claim is None or _text(claim.get("id")) in self.consumed:
                    continue
                self.consumed.add(_text(claim.get("id")))
                text = _text(claim.get("text"))
                if not text:
                    continue
                payload = T.SuccessCriterionPayload(text=text, target=self._quantity(claim))
                eid = self.add(T.Kind.SUCCESS_CRITERION, payload,
                               path=f"claim:{_text(claim.get('id'))}",
                               derived_from=(initiative,) + self.commissioned_by,
                               relation=T.RelationToCentralDecision.DEFINES,
                               labels=self._approval_labels(claim))
                self.by_claim[_text(claim.get("id"))] = eid

    # -- 5. the remaining claims -------------------------------------------
    def claims(self) -> None:
        """Every claim r30 registered, dispatched on its provenance word. A
        claim whose provenance is not one of r30's four is not guessed at: it
        is left out and recorded, because an unknown provenance is exactly the
        case where importing would invent an authority."""
        handlers: Mapping[str, Callable[[Mapping[str, Any]], None]] = {
            PROVENANCE_CLIENT: self._client_input,
            PROVENANCE_MACHINE: self._machine_computed,
            PROVENANCE_PROPOSED: self._consultant_proposed,
            PROVENANCE_GATE: self._already_done,
        }
        for claim in self.out.claims:
            cid = _text(claim.get("id"))
            if not cid or cid in self.consumed:
                continue
            self.consumed.add(cid)
            handler = handlers.get(_text(claim.get("provenance")))
            if handler is None:
                self.finding(where=cid, blocks=False,
                             issue=f"r30 claim {cid} carries provenance "
                                   f"{_text(claim.get('provenance'))!r}, which the engine has no authority for",
                             fix="import it by hand, or add the provenance to the adapter's table")
                continue
            handler(claim)

    def _claim(self, claim_id: str) -> Mapping[str, Any] | None:
        for c in self.out.claims:
            if _text(c.get("id")) == claim_id:
                return c
        return None

    def _quantity(self, claim: Mapping[str, Any]) -> T.Quantity | None:
        value = _decimal(claim.get("value"))
        unit = _text(claim.get("unit"))
        if value is None or not unit:
            return None
        # The time basis r30 states is the period the number covers; anything
        # it did not state stays unpinned, which is a question, not a default.
        basis = _text(claim.get("time_basis")) or None
        dims = T.Dimensions(period=basis, definition=_text(claim.get("population")) or None)
        return T.Quantity(value, canonical_unit(unit) or unit, family_of(unit),
                          dimensions=dims, precision=_PRECISION)

    def _approval_labels(self, claim: Mapping[str, Any]) -> tuple[str, ...]:
        """r30's own approval word, kept on the row. `registry.PROPOSED_LABEL`
        (`app/pipeline/registry.py:52`) is what the legacy volumes print; the
        engine keeps the word rather than re-deciding what it meant."""
        word = _text(claim.get("approval_status"))
        return (f"legacy_approval:{word}",) if word else ()

    def _already_done(self, claim: Mapping[str, Any]) -> None:
        """The gate claims were mapped with the gate itself."""
        return None

    def _client_input(self, claim: Mapping[str, Any]) -> None:
        """M3. A client number is already in the registry - it is what was sent
        to the pipeline. The claim resolves to that FACT by exact identity of
        the answer text; nothing new is written, so the client's figure exists
        once and only once.

        r30 also mines numbers out of the free-text fields it was given
        (`registry.client_fact_claims` `app/pipeline/registry.py:341`). Those
        resolve to no FACT row because the engagement holds them as prose, and
        that is recorded rather than repaired: the engine will not manufacture
        a client fact the client never stated as one."""
        cid, answer = _text(claim.get("id")), _text(claim.get("text"))
        eid = self.fact_by_answer.get((_text(claim.get("question")), answer))
        if eid is None:
            eid = next((v for (_q, a), v in self.fact_by_answer.items() if a == answer), None)
        if eid is None:
            eid = next((f.id for f in _live(self.view, T.Kind.FACT)
                        if f.payload.basis is T.FactBasis.CLIENT_STATED
                        and f.payload.statement == answer), None)
        if eid is None:
            self.finding(where=cid, blocks=False,
                         issue=f"r30 registered client figure {cid} from prose the engagement holds no "
                               f"FACT row for",
                         fix="record the figure as a client fact so it can be reconciled, or leave it as prose")
            return
        self.by_claim[cid] = eid

    def _formula(self, claim: Mapping[str, Any]) -> tuple[str, tuple[str, ...]] | None:
        """The claim's arithmetic in the engine's formula grammar, or None when
        it cannot be expressed. r30 writes a derived claim's source as its own
        machine-built expression ("DV-01 / 365 x 30",
        `app/pipeline/registry.py:381`); every token must be a claim already
        mapped to a registered entity, a literal, or one of the four
        operators. One unreadable token means no formula - the engine does not
        half-parse arithmetic it is about to confirm."""
        tokens = _text(claim.get("source")).split()
        if not tokens:
            return None
        parts: list[str] = []
        inputs: list[str] = []
        for tok in tokens:
            op = _OPERATORS.get(tok)
            if op is not None:
                parts.append(op)
                continue
            eid = self.by_claim.get(tok)
            if eid is not None and self.pending.has(eid):
                parts.append(eid)
                inputs.append(eid)
                continue
            if _decimal(tok) is not None:
                parts.append(tok)
                continue
            return None
        if not inputs:
            return None
        return " ".join(parts), tuple(dict.fromkeys(inputs))

    def _machine_computed(self, claim: Mapping[str, Any]) -> None:
        """M1. A machine-computed number becomes a calculated FACT, PROPOSED
        at birth; `confirmations()` confirms it only when the engine's own
        calculator reproduces it exactly.

        A claim the engine cannot express arithmetically is NOT imported and
        NOT called a defect: r30 computed it, the engine simply has no formula
        to check, and absent evidence is not evidence of a defect. A claim it
        CAN express and disagrees with is a defect and blocks FINAL."""
        cid = _text(claim.get("id"))
        quantity = self._quantity(claim)
        formula = self._formula(claim)
        if quantity is None or formula is None:
            self.finding(where=cid, blocks=False,
                         issue=f"r30 computed {cid} by arithmetic the engine cannot restate, so it is "
                               f"not imported as a checked calculation",
                         fix="state the claim's arithmetic over registered claim ids, or record it as a client fact")
            return
        expression, inputs = formula
        payload = T.FactPayload(statement=_text(claim.get("text")) or expression,
                                basis=T.FactBasis.CALCULATED, quantity=quantity,
                                formula=expression, inputs=inputs,
                                topic=_text(claim.get("type")) or None)
        eid = self.add(T.Kind.FACT, payload, path=f"claim:{cid}", derived_from=inputs,
                       relation=T.RelationToCentralDecision.EVIDENCES,
                       confidence=T.Confidence(None, "computed"))
        self.by_claim[cid] = eid

    def _consultant_proposed(self, claim: Mapping[str, Any]) -> None:
        """M2. A consultant-proposed threshold is an ASSUMPTION, UNAPPROVED,
        carrying r30's own approval label. It is never a fact and it never
        outranks a verified record, because authority follows the information
        type and not the producer (design 13.4)."""
        cid = _text(claim.get("id"))
        text = _text(claim.get("text"))
        if not text:
            return
        payload = T.AssumptionPayload(statement=text, rationale=_text(claim.get("source")),
                                      quantity=self._quantity(claim),
                                      approval=T.ApprovalState.UNAPPROVED)
        eid = self.add(T.Kind.ASSUMPTION, payload, path=f"claim:{cid}",
                       derived_from=self.commissioned_by,
                       relation=T.RelationToCentralDecision.INFORMS,
                       labels=self._approval_labels(claim))
        self.by_claim[cid] = eid

    # -- 6. the operations layers ------------------------------------------
    def layers(self) -> None:
        """The structured layers r30 produced, each layer one engine kind
        (design 13.3). Every builder reads r30's own field names and writes
        r30's own words; nothing is summarised on the way through."""
        content = self.out.content
        # One table, one row per layer: adding a layer is a row here and never
        # a branch anywhere else.
        for layer, builder in (("procedures", self._procedures), ("org", self._org),
                               ("journey", self._journey), ("scoreboard", self._scoreboard),
                               ("risks", self._risks), ("checklists", self._checklists)):
            data = content.get(layer)
            if data:
                builder(data)

    def _items(self, data: Any, key: str) -> list[Mapping[str, Any]]:
        if isinstance(data, Mapping):
            data = data.get(key)
        return [x for x in (data or []) if isinstance(x, Mapping)]

    def _procedures(self, data: Any) -> None:
        for i, proc in enumerate(self._items(data, "procedures"), 1):
            name = _text(proc.get("name"))
            for j, step in enumerate(self._items(proc.get("steps"), "steps"), 1):
                text = _text(step.get("step"))
                if not text:
                    continue
                self.add(T.Kind.ACTION,
                         T.ActionPayload(text=text, capability_class=T.CapabilityClass.PROCESS,
                                         horizon=T.Horizon.WEEKS, sequence=j),
                         path=f"procedures[{i}]:{name}:step[{j}]",
                         derived_from=self.commissioned_by)

    def _org(self, data: Any) -> None:
        for i, role in enumerate(self._items(data, "roles"), 1):
            name = _text(role.get("role"))
            if not name:
                continue
            # `role` carries r30's own role class (human or ai); the engine
            # keeps the word rather than deciding what a role "really" is.
            self.add(T.Kind.OWNER, T.OwnerPayload(name=name, role=_text(role.get("type"))),
                     path=f"org:roles[{i}]", derived_from=self.commissioned_by)

    def _journey(self, data: Any) -> None:
        for i, stage in enumerate(self._items(data, "stages"), 1):
            text = _joined_text(stage.get("stage"), stage.get("customer_action"))
            if not text:
                continue
            self.add(T.Kind.PROCESS_STEP,
                     T.ProcessStepPayload(text=text, perspective=T.StepPerspective.CUSTOMER, sequence=i),
                     path=f"journey:stages[{i}]", derived_from=self.commissioned_by)

    def _scoreboard(self, data: Any) -> None:
        for i, row in enumerate(self._items(data, "scoreboard"), 1):
            text = _joined_text(row.get("metric"), row.get("target"))
            if not text:
                continue
            self.add(T.Kind.SUCCESS_CRITERION, T.SuccessCriterionPayload(text=text),
                     path=f"scoreboard[{i}]", derived_from=self.commissioned_by,
                     relation=T.RelationToCentralDecision.DEFINES)

    def _risks(self, data: Any) -> None:
        for i, row in enumerate(self._items(data, "risks"), 1):
            text = _joined_text(row.get("risk"), row.get("mitigation"))
            if not text:
                continue
            self.add(T.Kind.RISK,
                     T.RiskPayload(text=text, who_feels_it=_text(row.get("who_feels_it"))),
                     path=f"risks[{i}]", derived_from=self.commissioned_by)

    def _checklists(self, data: Any) -> None:
        for i, row in enumerate(self._items(data, "checklists"), 1):
            text = _joined_text(row.get("name"), row.get("when"))
            if not text:
                continue
            self.add(T.Kind.CONTROL, T.ControlPayload(text=text),
                     path=f"checklists[{i}]", derived_from=self.commissioned_by)

    # -- 7. the volumes -----------------------------------------------------
    def volumes(self) -> None:
        """The three volumes r30 renders, as WORK_PRODUCTs of the declared
        `legacy_volume` product (`work_products/decl.py:512`). The file itself
        is built on demand by `r30_adapter.volume_path`; the row exists as
        soon as the package does, so the plan can count it."""
        if self.workstream_id is None:
            return
        workstream = self.pending.get(self.workstream_id)
        name = _text(workstream.payload.name) if workstream is not None else ""
        for kind in VOLUME_KINDS:
            payload = T.WorkProductPayload(
                product_id="legacy_volume", title=name,
                planned_because=f"delivered by the legacy technology pipeline as the {kind} volume",
                section_ids=("volume",), consumes=(self.workstream_id,))
            self.volume_ids.append(self.add(
                T.Kind.WORK_PRODUCT, payload, path=f"volume:{kind}",
                derived_from=(self.workstream_id,)))

    # -- 8. what r30 says about itself -------------------------------------
    def release(self) -> None:
        """M6. r30's own verdict on its own package, as engine findings: every
        release reason and every open finding of its current integrity report.
        A DRAFT r30 package therefore blocks the engine's FINAL, and a package
        r30 never audited blocks it too - a missing report is a missing audit,
        not a clean one."""
        for reason in (self.out.release.get("reasons") or []):
            self.finding(where=f"r30:request:{self.out.request_id}", blocks=True,
                         issue=f"the legacy technology package is not released: {_text(reason)}",
                         fix="finish or re-commission the r30 run; the engine cannot release around it")
        report = self.out.report
        if report is None:
            self.finding(where=f"r30:request:{self.out.request_id}", blocks=True,
                         issue="the legacy package holds no current integrity report for the content it carries",
                         fix="re-run the r30 integrity pass so the report describes the content on the row")
            return
        for f in (report.get("findings") or []):
            if not isinstance(f, Mapping):
                continue
            self.finding(where=_text(f.get("where")) or f"r30:request:{self.out.request_id}", blocks=True,
                         issue=_text(f.get("issue")) or _text(f.get("law")),
                         fix=_text(f.get("fix")) or "resolve the finding inside the r30 package")


def confirmations(imported: LegacyImport, view, calc: Any) -> tuple[tuple[T.EntityDelta, ...], tuple[T.Finding, ...]]:
    """M1's second half, on the finished batch: every calculated FACT this
    import wrote is confirmed by the CALCULATOR only when
    `calc.recompute(fact, view)` is exact. One that does not recompute is left
    PROPOSED and reported as a blocking L13 finding - the number r30 printed
    and the number its own formula yields are not the same number.

    The confirmation is a SetStatus by `Actor.CALCULATOR`, not a status chosen
    at birth: authority over arithmetic belongs to the deterministic engine
    (I1), and the engine has to do the arithmetic to hold it. Removing the
    `recompute` test here is the mutation "import an unverified claim as
    CONFIRMED"."""
    deltas: list[T.EntityDelta] = []
    findings: list[T.Finding] = []
    for e in imported.entities:
        if e.kind is not T.Kind.FACT or e.payload.basis is not T.FactBasis.CALCULATED:
            continue
        if calc.recompute(e, view):
            deltas.append(T.SetStatus(
                e.id, T.Status.CONFIRMED,
                by=T.Provenance(actor=T.Actor.CALCULATOR, actor_ref=f"calculator:{e.id}",
                                derived_from=e.payload.inputs)))
            continue
        findings.append(T.Finding(
            law=LAW_LEGACY_NOT_FINAL, where=e.id,
            issue=f"the legacy calculation {e.payload.formula} does not reproduce {e.payload.quantity.value}"
                  if e.payload.quantity is not None else "the legacy calculation does not reproduce its value",
            fix="correct the arithmetic inside the r30 package and re-commission the run",
            entity_ids=(e.id,) + tuple(e.payload.inputs), blocks_final=True))
    return tuple(deltas), tuple(findings)


def import_r30(outputs: R30Outputs, view, *, inputs: R30Inputs, calc: Any,
               engagement_id: str, decision_id: str | None = None,
               weight: float = 0.0) -> LegacyImport:
    """The whole mapping, as deltas the caller applies (design 13.3).

    M5: the Request row is measured before and after. The engine never writes
    to it - a correction re-commissions a new request and keeps the old one as
    lineage - so a changed content hash or integrity report means the engine
    edited the legacy package, and the import refuses its own output rather
    than hand back rows built on a row it damaged."""
    row = outputs.row
    before = snapshot(row) if row is not None else None

    if not outputs.delivered:
        # A run that never finished holds nothing to import. It is still said
        # out loud: silence about a paid run that failed is the worst answer.
        findings = (T.Finding(
            law=LAW_LEGACY_NOT_FINAL, where=f"r30:request:{outputs.request_id}",
            issue="the legacy technology run did not complete, so it delivered nothing to import",
            fix="re-commission the run once the failure is understood", blocks_final=True),)
        if before is not None:
            assert_row_untouched(row, before)
        return LegacyImport(findings=findings)

    run = _Import(outputs, view, inputs=inputs, calc=calc, engagement_id=engagement_id,
                  decision_id=decision_id, weight=weight)
    run.workstream()
    run.modules()
    run.canonical_gate()
    run.module_kpis()
    run.claims()
    run.layers()
    run.volumes()
    run.close_workstream()
    run.release()

    imported = LegacyImport(deltas=tuple(run.deltas), findings=tuple(run.findings),
                            entity_by_claim=dict(run.by_claim), workstream_id=run.workstream_id,
                            volume_ids=tuple(run.volume_ids))
    # The arithmetic check runs against the batch as it will stand once
    # applied, so a calculation whose inputs arrive in the same import is
    # checked against them rather than against a registry that has not seen
    # them yet.
    confirm_deltas, confirm_findings = confirmations(imported, run.pending, calc)
    imported = replace(imported, deltas=imported.deltas + confirm_deltas,
                       findings=imported.findings + confirm_findings)
    if before is not None:
        assert_row_untouched(row, before)
    return imported


def release_findings(outputs: R30Outputs) -> tuple[T.Finding, ...]:
    """M6 on its own, for the gate: the L13 findings of a delivered package
    without importing it again."""
    run = _Import(outputs, _EmptyView(), inputs=R30Inputs(
        business_name="", business_description="", main_problem="", desired_outcome="",
        engagement_type="", needs_ai="", owner_email=""), calc=None,
        engagement_id="", decision_id=None, weight=0.0)
    run.release()
    return tuple(run.findings)


class _EmptyView:
    """A view of nothing, for the queries `release_findings` never makes."""

    def get(self, entity_id: str) -> T.Entity | None:
        return None

    def query(self, kind: T.Kind | None = None, **_: Any) -> list[T.Entity]:
        return []


def claims_of(row: Any) -> list[Mapping[str, Any]]:
    """The claims on a Request row, through r30's own reader
    (`registry.registry_for` `app/pipeline/registry.py:2815`)."""
    reg = _r30_registry.registry_for(row) or {}
    return [c for c in (reg.get("claims") or []) if isinstance(c, Mapping)]


__all__ = [n for n in dir() if not n.startswith("_")]
