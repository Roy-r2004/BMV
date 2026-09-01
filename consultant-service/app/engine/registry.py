"""app/engine/registry.py - the engagement registry: the only state.

Adopted from contracts.py section 15, with the read-side protocol and the
calculator boundary of section 8 (RegistryView, Calculator, CalcResult,
IncomparableInputs, Reconciliation), which live with the thing they read.
One typed, append-only, hash-addressed
store of every entity of every kind. The Partner, every method, every
specialist, synthesis and every renderer is a pure function
RegistryView -> deltas (Add | Supersede | SetStatus); nothing edits a row in
place, so lineage is the row history and a release hash is a fact about the
rows, not about who wrote them.

Why a registry and not a document: r30 (app/pipeline/registry.py) proved that
prompt law does not hold -- a number the model coined, a label it dropped, a
client fact it restated, each existed nowhere as a record before it was
printed. Here every write is refused at the door unless the row satisfies the
laws below, so no gate downstream has to guess what a sentence meant.

Invariants (every raise names its id; every branch has a test that fails when
the branch is deleted):

  I1  a status advances only by an actor may_advance() allows (MAY_CONFIRM /
      APPROVAL_OWNER / MAY_RESOLVE). A row written at an accepted status --
      by Add or by Supersede -- is an advance and is checked the same way;
      otherwise Supersede is a back door around I1.
  I2  a client_stated FACT's statement is a verbatim substring of the turn it
      cites; a document_verified FACT's locator is a verbatim substring of the
      document text; only Actor.CLIENT (or a visible precedence resolution by
      Actor.DOCUMENT carrying the label SUPERSEDED_BY_RECORD) supersedes a
      client fact. Client facts remain exact (spec section 7).
  I3  a RECOMMENDATION reaches APPROVED only with non-empty supports, each a
      CONFIRMED FACT or an APPROVED ASSUMPTION and not superseded: every
      recommendation traces to evidence, an approved assumption or a
      calculation (spec section 7).
  I4  a REGULATED_MATTER is ROUTED only from inside the engine and is never
      CONFIRMED or APPROVED by anyone; it is born unresolved.
  I5  Actor.SPECIALIST may not supersede or set status on an entity whose
      provenance.actor_ref differs from its own (spec section 4: no specialist
      silently changes client facts, objectives or another specialist's
      conclusions).
  I6  ids are assigned by the registry from ID_PREFIX and name their kind;
      every version is a new row; nothing is updated in place; a terminal
      status is reached by a recorded transition, never at birth.
  I7  authority and info_type are derived from the information type
      (Entity.__post_init__); the registry re-derives them at the door, on
      write and on reload, so a row that did not come through make_entity
      cannot smuggle an owner in.
  I8  a calculated FACT carries formula and inputs, and every input id exists.

Read side: query(where=...) reads FILTERABLE_FIELDS only -- a text key raises,
so a filter on prose (the way an engagement type would creep in) cannot be
constructed. Materiality is recomputed from the live support graph
(is_material, MF2.4); the stored ConflictPayload.material is a rendering
snapshot the gate never reads. Approval of an assumption is its APPROVED
status -- the transition I1 checked -- never the payload's approval field,
which any producer can set. content_hash() is over the latest rows sorted by
id with recorded_at blanked (MF3.7): identical content hashes identically
whatever the clock said and in whatever order the rows were written or
reloaded.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence, runtime_checkable

from app.engine.authority import may_advance, owner_of
from app.engine.types import (
    ANALYSIS_KINDS, BOUNDS, FILTERABLE_FIELDS, ID_PREFIX, TERMINAL_STATUSES, Actor, Add, ConflictKind,
    DecisionRole, Entity,
    EntityDelta, FactBasis, Feasibility, InfoType, Kind, Quantity, RegistryError, RelationToCentralDecision,
    SetStatus, SourceKind, Status, Supersede, UnitFamily, _norm, info_type_of,
)

# The one label that lets a record, not the client, retire a client fact:
# synthesis/resolve.py writes it when a client-confirmed record class of
# strictly higher rank carries the same measure (design 9.4). A Name at every
# comparison, never a literal, so the whitelist AST law (design 18) sees no
# string inside a branch test.
SUPERSEDED_BY_RECORD = "superseded_by_record"

# Writing a row at one of these statuses means an authority accepted it: the
# write is an advance and must pass may_advance whether it arrives by Add or by
# Supersede (I1).
_AUTHORITY_GATED: frozenset[Status] = frozenset({Status.CONFIRMED, Status.APPROVED, Status.RESOLVED, Status.ROUTED})

# A licensed interpretation never reaches these inside the engine (I4).
_LICENSED_NEVER: frozenset[Status] = frozenset({Status.CONFIRMED, Status.APPROVED})

# A conclusion in one of these relations moves the central decision on its own.
_DECISIVE_RELATIONS: frozenset[RelationToCentralDecision] = frozenset({
    RelationToCentralDecision.DEFINES, RelationToCentralDecision.CONSTRAINS, RelationToCentralDecision.RESOLVES,
})

# Conflict kinds that are material by construction: an objective the facts
# show infeasible is the client's decision whatever it touches.
_MATERIAL_KINDS: frozenset[ConflictKind] = frozenset({ConflictKind.OBJECTIVE_VS_FEASIBILITY})


def _default_clock() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _licensed_refusal(e: Entity, status: Status, *, at_birth: bool) -> bool:
    """I4 as one question. A licensed interpretation -- a REGULATED_MATTER, or
    a RECOMMENDATION flagged licensed (its info type moves with the flag,
    design 9.6) -- is never CONFIRMED or APPROVED inside the engine, whatever
    the actor tables would allow by kind: the engine identifies and routes,
    it does not answer. A matter is not born RESOLVED either; RESOLVED is a
    qualified professional's recorded act on a matter that already exists."""
    if e.info_type != InfoType.LICENSED_INTERPRETATION:
        return False
    if status in _LICENSED_NEVER:
        return True
    return at_birth and e.kind == Kind.REGULATED_MATTER and status == Status.RESOLVED


def _is_support(s: Entity) -> bool:
    """What a recommendation may rest on (I3, L2). A CONFIRMED FACT of any
    basis counts -- a client-stated fact the client confirmed is the
    document-less path to a supported recommendation (MF2.1) -- and an
    ASSUMPTION only once APPROVED, by the status transition I1 checked."""
    return (s.kind == Kind.FACT and s.status == Status.CONFIRMED) or \
           (s.kind == Kind.ASSUMPTION and s.status == Status.APPROVED)


def _wanted(v: Any) -> Any:
    """A query filter value, normalised the way InputSpec freezes its filter:
    enum members become their values; a list/set of them becomes a tuple the
    field value must be a member of."""
    if isinstance(v, (list, tuple, set, frozenset)):
        return tuple(_norm(x) for x in v)
    return _norm(v)


def _field_matches(e: Entity, key: str, want: Any) -> bool:
    have = e.field(key)
    if isinstance(want, tuple):
        return have in want
    return have == want


@runtime_checkable
class RegistryView(Protocol):
    """Read-only, possibly scoped (a specialist sees only its permitted
    evidence). Everything that reads the registry -- selection, planning,
    rendering, the gates -- is typed against this and never against the
    registry class, so a scoped window and the whole registry are
    interchangeable to a method."""
    engagement_id: str

    def get(self, entity_id: str) -> Entity | None: ...
    def query(self, kind: Kind | None = None, *, status: Status | None = None,
              where: Mapping[str, Any] | None = None) -> list[Entity]: ...
    def lineage(self, entity_id: str) -> list[Entity]: ...
    def content_hash(self) -> str: ...
    def central_decision(self) -> Entity | None: ...
    def supports_of(self, entity_id: str) -> list[Entity]: ...
    def source_text(self, source_id: str) -> str | None: ...
    def reserve_ids(self, kind: Kind, count: int) -> list[str]: ...


# -- the calculator boundary (contracts.py section 8) --------------------------
# The read-side protocol and the calculator boundary are one section of the
# contracts and live together: the calculator reads a RegistryView and is the
# only producer of a numeric value the registry will store as CALCULATED (I8).
# One definition, imported from here by calc/ and methods/, so an except
# clause written against IncomparableInputs catches what arith.py raises.

class IncomparableInputs(Exception):
    """Raised by the calculator when two comparable facts on one measure carry
    different values. There is no mean, blend or pick: the caller emits a CONFLICT."""


@dataclass(frozen=True)
class CalcResult:
    quantity: Quantity
    formula: str                            # arithmetic over entity ids, e.g. "FCT-3 * FCT-7 / 12"
    inputs: tuple[str, ...]


@runtime_checkable
class Calculator(Protocol):
    """The only producer of a numeric value (frozen signature, MF3.4).

    Runtime-checkable like RegistryView so a MethodContext can be verified
    against the boundary it was typed with, not against a copy: contract.py
    and calc/ import these two names from here (C4/C5 follow-up).

    product / total / ratio / convert_period compute a CalcResult whose value
    is exact Decimal arithmetic quantised to the declared precision. Each
    refuses (raises IncomparableInputs or ValueError) rather than guesses when:
    capacity -> money without a price fact; a share the client never gave;
    currencies or periods differ without a registered conversion FACT; a
    dimension is unknown (None) where comparison needs it.
    """

    def product(self, inputs: Sequence[Entity], *, unit: str, unit_family: UnitFamily, period_step: int = 1) -> CalcResult: ...
    def total(self, inputs: Sequence[Entity]) -> CalcResult: ...
    def ratio(self, numerator: Entity, denominator: Entity) -> CalcResult: ...
    def convert_period(self, fact: Entity, to_basis: str) -> CalcResult: ...
    def recompute(self, calculated: Entity, registry: RegistryView) -> bool: ...
    def comparable(self, a: Quantity, b: Quantity) -> str: ...      # "comparable" | "incomparable" | "unknown_dimension"


@dataclass(frozen=True)
class Reconciliation:
    """Outcome of reconciling two facts that share a MEASURE (calc/reconcile.py)."""
    outcome: str                            # "conflict" | "question" | "distinct" | "same"
    conflict_kind: ConflictKind | None = None
    unpinned: tuple[str, ...] = ()


class EngagementRegistry:
    """Typed, append-only, hash-addressed store of every entity of one
    engagement. The invariants I1-I8 are stated in the module docstring; the
    method that enforces each names it in the RegistryError it raises."""

    def __init__(self, engagement_id: str, *, clock: Callable[[], str] | None = None):
        if not engagement_id:
            raise ValueError("a registry belongs to one engagement")
        self.engagement_id = engagement_id
        # Injectable so a fixed clock yields byte-identical rows across runs
        # (design 17.4) and so the clock-blind content hash (MF3.7) can be
        # proven against a clock that moves.
        self._clock = clock or _default_clock
        self._rows: list[Entity] = []
        self._latest: dict[str, Entity] = {}
        self._counters: dict[Kind, int] = {}
        self._source_texts: dict[str, str] = {}

    @classmethod
    def from_rows(cls, engagement_id: str, rows: Iterable[Entity], *, clock: Callable[[], str] | None = None,
                  source_texts: Mapping[str, str] | None = None) -> "EngagementRegistry":
        """Rebuild from the append-only row history the store persisted, in
        the order it was written. Transition laws (I1-I6, I8) were checked
        when each row was written and are not re-run -- an older row is not
        condemned by a law that did not exist when it was recorded -- but the
        derivation I7 is, because a mis-migrated row is exactly the row that
        never passed through make_entity. recorded_at is kept as stored."""
        reg = cls(engagement_id, clock=clock)
        seen: set[tuple[str, int]] = set()
        for r in rows:
            if r.engagement_id != engagement_id:
                raise RegistryError("I6", f"row {r.id} belongs to another engagement")
            if not r.id or (r.id, r.version) in seen:
                raise RegistryError("I6", f"row {r.id!r} v{r.version} is unnamed or recorded twice")
            reg._check_derived(r)
            seen.add((r.id, r.version))
            reg._note_id(r.kind, r.id)
            reg._rows.append(r)
            cur = reg._latest.get(r.id)
            if cur is None or r.version > cur.version:
                reg._latest[r.id] = r
        for sid, text in (source_texts or {}).items():
            reg.register_source_text(sid, text)
        return reg

    # -- write side ----------------------------------------------------------
    def register_source_text(self, source_id: str, text: str) -> None:
        """The hashed text of a document/dataset/link source, the only thing a
        document-verified fact's locator may be checked against (I2)."""
        if not isinstance(text, str):
            raise TypeError("a source text is a str")
        self._source_texts[source_id] = text

    def source_texts(self) -> dict[str, str]:
        return dict(self._source_texts)

    def source_text(self, source_id: str) -> str | None:
        e = self._latest.get(source_id)
        if e is not None and e.kind == Kind.EVIDENCE_SOURCE and e.payload.text is not None:
            return e.payload.text
        return self._source_texts.get(source_id)

    def apply(self, delta: EntityDelta) -> Entity:
        if isinstance(delta, Add):
            return self._add(delta.entity)
        if isinstance(delta, Supersede):
            return self._supersede(delta)
        if isinstance(delta, SetStatus):
            return self._set_status(delta)
        raise TypeError(f"unknown delta {type(delta).__name__}")

    def apply_all(self, deltas: Iterable[EntityDelta]) -> list[Entity]:
        """A batch is one decision: when any delta is refused nothing of the
        batch lands, so a producer never leaves half a result behind (the
        registry-side half of the runner's all-or-nothing admission)."""
        rows_before = len(self._rows)
        latest_before = dict(self._latest)
        counters_before = dict(self._counters)
        out: list[Entity] = []
        try:
            for d in deltas:
                out.append(self.apply(d))
        except Exception:
            del self._rows[rows_before:]
            self._latest = latest_before
            self._counters = counters_before
            raise
        return out

    def _note_id(self, kind: Kind, entity_id: str) -> None:
        """An explicit id names its kind and moves the counter past itself,
        so an id the registry assigns later can never collide with it (I6)."""
        prefix, _, num = entity_id.rpartition("-")
        if prefix != ID_PREFIX[kind] or not num.isdigit() or int(num) < 1 or num != str(int(num)):
            raise RegistryError("I6", f"{entity_id!r} is not a {ID_PREFIX[kind]}-<n> id, which is what a {kind.value} is called")
        self._counters[kind] = max(self._counters.get(kind, 0), int(num))

    def reserve_ids(self, kind: Kind, count: int) -> list[str]:
        """Ids a producer may put on rows it has not written yet, taken from
        the registry's own counter rather than counted off the rows a producer
        can see.

        A specialist writes under a ScopedView, and a window narrower than the
        engagement cannot see the highest id already assigned; ids counted off
        it collide with rows the specialist was never shown, and I6 refuses
        the whole batch for a reason that is about the window and not about
        the analysis. Reservation moves the counter, so the same id is never
        offered twice however narrow the window was - and the ids are the
        registry's to give, which is why asking for one is not reading
        somebody else's record.
        """
        out: list[str] = []
        for _ in range(max(0, int(count))):
            out.append(self._next_id(kind))
        return out

    def _next_id(self, kind: Kind) -> str:
        n = self._counters.get(kind, 0)
        while True:
            n += 1
            candidate = f"{ID_PREFIX[kind]}-{n}"
            if candidate not in self._latest:
                self._counters[kind] = n
                return candidate

    def _check_derived(self, e: Entity) -> None:
        expected = info_type_of(e.kind, e.payload)
        if e.info_type != expected or e.authority != owner_of(expected):
            raise RegistryError("I7", f"{e.id or e.kind.value}: authority and info_type are derived from the information type, never chosen")

    def _cited_texts(self, e: Entity, *, turns: bool) -> list[str]:
        """Texts of the sources a row cites, split by whether they are
        conversation turns: a client fact must come from what the client said
        and a document fact from what the document says, never the other way
        round -- that is the difference between a recollection and a record."""
        out: list[str] = []
        for sid in e.provenance.derived_from:
            src = self._latest.get(sid)
            is_turn = src is not None and src.kind == Kind.EVIDENCE_SOURCE \
                and src.payload.source_kind == SourceKind.CONVERSATION_TURN
            text = self.source_text(sid)
            if text is not None and is_turn == turns:
                out.append(text)
        return out

    def _check_fact(self, e: Entity) -> None:
        if e.kind != Kind.FACT:
            return
        p = e.payload
        if p.basis == FactBasis.CLIENT_STATED:
            # Two distinct failures, two distinct refusals: nothing cited that
            # the client said, or the client's words restated.
            turns = self._cited_texts(e, turns=True)
            if not turns:
                raise RegistryError("I2", "a client fact must cite the conversation turn it was said in")
            elif not p.statement or not any(p.statement in t for t in turns):
                raise RegistryError("I2", "a client fact must be a verbatim substring of the turn text; the client's words are never restated")
        if p.basis == FactBasis.DOCUMENT_VERIFIED:
            loc = e.provenance.source_locator or ""
            if not loc or not any(loc in t for t in self._cited_texts(e, turns=False)):
                raise RegistryError("I2", "a document-verified fact must quote a verbatim locator from the hashed document text")
        if p.basis == FactBasis.CALCULATED:
            if not p.formula or not p.inputs:
                raise RegistryError("I8", "a calculated fact carries its formula and inputs")
            missing = [i for i in p.inputs if i not in self._latest]
            if missing:
                raise RegistryError("I8", f"calculated fact inputs not registered: {missing}")

    def _check_supports(self, rec: Entity) -> None:
        sup = rec.payload.supports
        if not sup:
            raise RegistryError("I3", "a recommendation is approved only with supports")
        for sid in sup:
            s = self._latest.get(sid)
            if s is None or s.status in TERMINAL_STATUSES:
                raise RegistryError("I3", f"support {sid} is missing or superseded")
            if not _is_support(s):
                raise RegistryError("I3", f"support {sid} is {s.kind.value}:{s.status.value}, not a confirmed fact or an approved assumption")

    def _check_row(self, e: Entity) -> None:
        """The laws a row must satisfy to be written at all, by Add or as the
        replacement in a Supersede. The actor judged is the row's own
        provenance actor: a producer cannot write in someone else's name."""
        actor = e.provenance.actor
        if e.engagement_id != self.engagement_id:
            raise RegistryError("I6", "entity belongs to another engagement")
        if e.status in TERMINAL_STATUSES:
            raise RegistryError("I6", f"a row is never born {e.status.value}; a terminal status is a recorded transition")
        self._check_derived(e)
        if _licensed_refusal(e, e.status, at_birth=True):
            raise RegistryError("I4", f"a licensed interpretation is never {e.status.value} inside the engine; it is identified and routed")
        if e.status in _AUTHORITY_GATED and not may_advance(e, e.status, actor):
            raise RegistryError("I1", f"{actor.value} may not write a {e.kind.value} as {e.status.value}")
        if e.kind == Kind.RECOMMENDATION and e.status == Status.APPROVED:
            self._check_supports(e)
        self._check_fact(e)

    def _stamp(self, e: Entity, **changes: Any) -> Entity:
        """A row as the registry records it: the clock is the registry's, and
        confirmed_by names the actor only when the status is one an authority
        accepted -- otherwise it is None, never a producer's claim."""
        by = e.provenance.actor_ref if e.status in _AUTHORITY_GATED else None
        return replace(e, confirmed_by=by, provenance=replace(e.provenance, recorded_at=self._clock()), **changes)

    def _capacity(self) -> int:
        """MAX_ENTITIES_PER_ANALYSIS_KIND, live. The operator's value when
        there is one, the frozen default otherwise - never a literal here."""
        try:
            from app.config import settings
            value = getattr(settings, "ENGINE_MAX_ENTITIES_PER_ANALYSIS_KIND", None)
            if value is not None:
                return int(value)
        except Exception:                     # pragma: no cover - settings optional
            pass
        return int(BOUNDS["MAX_ENTITIES_PER_ANALYSIS_KIND"])

    def _check_capacity(self, e: Entity) -> None:
        """I9: an engagement holds at most MAX_ENTITIES_PER_ANALYSIS_KIND live
        rows of any one analysis kind.

        Every other bound caps how much WORK may run - rounds, specialists per
        round, methods per node, branches per expansion - and none of them
        capped what the work leaves behind. So an engagement could hold six
        hundred routes to a single decision and still satisfy every bound the
        engine published, and every distinctness count over those rows was
        cheap: divergence is easy when production is unbounded. The ceiling is
        derived from the bounds that were already there (every round, running
        flat out, opening every branch), so it is not a new opinion about how
        much analysis is enough - it is the existing opinion, added up.

        Only conclusions are rationed. Evidence the client handed over is not
        the engine's to ration, and the records it keeps to be audited by -
        questions, analysis rows - are not conclusions.

        Refusing here rather than dropping the row is what keeps a result
        whole: `apply_all` rolls the batch back, and the producer is recorded
        as blocked with the reason. A silently dropped row would leave the
        conclusions that cited it pointing at nothing.
        """
        if e.kind not in ANALYSIS_KINDS:
            return
        ceiling = self._capacity()
        if len(self.live(e.kind)) >= ceiling:
            raise RegistryError(
                "I9", f"the engagement already holds {ceiling} live {e.kind.value} rows, which is "
                      f"MAX_ENTITIES_PER_ANALYSIS_KIND; a further one is production, not analysis")

    def _add(self, e: Entity) -> Entity:
        if e.id and e.id in self._latest:
            raise RegistryError("I6", f"{e.id} already exists; supersede it")
        self._check_capacity(e)
        self._check_row(e)
        if e.id:
            self._note_id(e.kind, e.id)
        row = self._stamp(e, id=e.id or self._next_id(e.kind), version=1, supersedes=None)
        self._rows.append(row)
        self._latest[row.id] = row
        return row

    def _supersede(self, d: Supersede) -> Entity:
        old = self._latest.get(d.old_id)
        if old is None:
            raise RegistryError("I6", f"{d.old_id} does not exist")
        new = d.entity
        if new.id != old.id or new.kind != old.kind:
            raise RegistryError("I6", "a supersession keeps the id and the kind")
        actor = new.provenance.actor
        by_record = actor == Actor.DOCUMENT and SUPERSEDED_BY_RECORD in new.labels
        if old.kind == Kind.FACT and old.payload.basis == FactBasis.CLIENT_STATED and actor != Actor.CLIENT and not by_record:
            raise RegistryError("I2", "only the client (or a visible precedence resolution by a record) supersedes a client fact")
        if actor == Actor.SPECIALIST and old.provenance.actor_ref != new.provenance.actor_ref:
            raise RegistryError("I5", "a specialist may not supersede what it did not create")
        self._check_row(new)
        # The retirement is its own row: the loser stays in lineage, visibly
        # retired, and says why when a record retired it.
        retired_labels = old.labels + ((SUPERSEDED_BY_RECORD,) if by_record else ())
        retired = replace(old, status=Status.SUPERSEDED, version=old.version + 1, supersedes=old.version,
                          labels=tuple(dict.fromkeys(retired_labels)),
                          provenance=replace(old.provenance, recorded_at=self._clock()))
        row = self._stamp(new, version=old.version + 2, supersedes=old.version)
        self._rows.extend([retired, row])
        self._latest[row.id] = row
        return row

    def _set_status(self, d: SetStatus) -> Entity:
        cur = self._latest.get(d.entity_id)
        if cur is None:
            raise RegistryError("I6", f"{d.entity_id} does not exist")
        if cur.status in TERMINAL_STATUSES:
            raise RegistryError("I6", f"{d.entity_id} is {cur.status.value}; supersede instead")
        actor = d.by.actor
        if _licensed_refusal(cur, d.status, at_birth=False):
            raise RegistryError("I4", f"a licensed interpretation is never {d.status.value} inside the engine; it is identified and routed")
        if actor == Actor.SPECIALIST and cur.provenance.actor_ref != d.by.actor_ref:
            raise RegistryError("I5", "a specialist may not set status on what it did not create")
        if not may_advance(cur, d.status, actor):
            raise RegistryError("I1", f"{actor.value} may not set {cur.kind.value} {cur.id} to {d.status.value}")
        if cur.kind == Kind.RECOMMENDATION and d.status == Status.APPROVED:
            self._check_supports(cur)
        row = replace(cur, status=d.status, confirmed_by=d.by.actor_ref, version=cur.version + 1,
                      supersedes=cur.version, labels=tuple(dict.fromkeys(cur.labels + d.labels)),
                      provenance=replace(cur.provenance, recorded_at=self._clock()))
        self._rows.append(row)
        self._latest[row.id] = row
        return row

    # -- read side -----------------------------------------------------------
    def get(self, entity_id: str) -> Entity | None:
        return self._latest.get(entity_id)

    def query(self, kind: Kind | None = None, *, status: Status | None = None,
              where: Mapping[str, Any] | None = None) -> list[Entity]:
        """Latest version of every entity, in first-write order. `where`
        reads FILTERABLE_FIELDS only: a text key raises, so no caller can
        select on prose (M2/P1 at the registry)."""
        bad = set(where or ()) - FILTERABLE_FIELDS
        if bad:
            raise ValueError(f"query filters on non-structural field(s) {sorted(bad)}")
        wanted = {k: _wanted(v) for k, v in (where or {}).items()}
        out: list[Entity] = []
        for e in self._latest.values():
            if kind is not None and e.kind != kind:
                continue
            if status is not None and e.status != status:
                continue
            if wanted and not all(_field_matches(e, k, v) for k, v in wanted.items()):
                continue
            out.append(e)
        return out

    def live(self, kind: Kind | None = None, *, where: Mapping[str, Any] | None = None) -> list[Entity]:
        """query() without the retired: superseded, rejected and withdrawn
        rows stay addressable by get()/lineage() but are not the engagement's
        current position."""
        return [e for e in self.query(kind, where=where) if e.status not in TERMINAL_STATUSES]

    def rows(self) -> list[Entity]:
        return list(self._rows)

    def lineage(self, entity_id: str) -> list[Entity]:
        return [r for r in self._rows if r.id == entity_id]

    def content_hash(self) -> str:
        """sha256 over the latest rows' content hashes, sorted by id: a fact
        about what the registry holds, not about the clock (MF3.7) or about
        the order rows were written or reloaded."""
        h = hashlib.sha256()
        for e in sorted(self._latest.values(), key=lambda x: x.id):
            h.update(e.content_hash().encode())
        return h.hexdigest()

    def central_decision(self) -> Entity | None:
        for e in self.live(Kind.DECISION):
            if e.payload.role == DecisionRole.CENTRAL:
                return e
        return None

    def supports_of(self, entity_id: str) -> list[Entity]:
        e = self._latest.get(entity_id)
        if e is None or e.kind != Kind.RECOMMENDATION:
            return []
        return [s for s in (self._latest.get(i) for i in e.payload.supports) if s is not None]

    def support_closure(self) -> set[str]:
        """Every entity id some live RECOMMENDATION rests on, transitively
        through derived_from and calculation inputs."""
        out: set[str] = set()
        frontier = [i for r in self.live(Kind.RECOMMENDATION) for i in r.payload.supports]
        while frontier:
            i = frontier.pop()
            if i in out:
                continue
            out.add(i)
            e = self._latest.get(i)
            if e is not None:
                frontier.extend(e.provenance.derived_from)
                frontier.extend(getattr(e.payload, "inputs", ()) or ())
        return out

    # -- the queries the gates need ------------------------------------------
    def is_material(self, conflict: Entity) -> bool:
        """Materiality recomputed from the live graph at the moment of asking
        (MF2.4): a conclusion that defines, constrains or resolves the central
        decision, or that a live recommendation rests on, makes the conflict
        material. The stored flag is a rendering snapshot and is never read
        here -- a flag written before the recommendation existed would
        otherwise wave a material conflict through."""
        if conflict.kind != Kind.CONFLICT:
            raise TypeError(f"is_material expects a CONFLICT, got {conflict.kind.value}")
        closure = self.support_closure()
        for c in conflict.payload.conclusions:
            e = self._latest.get(c.entity_id)
            if e is None:
                continue
            if e.relation in _DECISIVE_RELATIONS or e.id in closure:
                return True
        return conflict.payload.kind in _MATERIAL_KINDS

    def open_material_conflicts(self) -> list[Entity]:
        return [c for c in self.query(Kind.CONFLICT, status=Status.OPEN) if self.is_material(c)]

    def unsupported_recommendations(self) -> list[tuple[Entity, str]]:
        """Every live recommendation with a reason it does not yet trace to
        evidence (L2). Listed, never waved through: no rule proves it false,
        it stays open."""
        out: list[tuple[Entity, str]] = []
        for r in self.live(Kind.RECOMMENDATION):
            if not r.payload.supports:
                out.append((r, "no supports"))
                continue
            for sid in r.payload.supports:
                s = self._latest.get(sid)
                if s is None or s.status in TERMINAL_STATUSES:
                    out.append((r, f"support {sid} missing or superseded"))
                elif not _is_support(s):
                    out.append((r, f"support {sid} is {s.kind.value}:{s.status.value}"))
        return out

    def unapproved_assumptions(self) -> list[Entity]:
        """Live assumptions the client has not APPROVED. Read from the
        status, never from payload.approval: the status is the transition I1
        checked against APPROVAL_OWNER, the payload field is whatever the
        producer wrote."""
        return [a for a in self.live(Kind.ASSUMPTION) if a.status != Status.APPROVED]

    def unrouted_regulated_matters(self) -> list[Entity]:
        """A matter not yet handed to a qualified adviser. REJECTED counts as
        unrouted: nothing inside the engine can un-regulate a matter."""
        return [m for m in self.query(Kind.REGULATED_MATTER)
                if m.status not in (Status.ROUTED, Status.RESOLVED, Status.WITHDRAWN)]

    def licensed_recommendations(self) -> list[Entity]:
        return [r for r in self.live(Kind.RECOMMENDATION) if r.payload.licensed_interpretation is True]

    def open_material_questions(self) -> list[Entity]:
        return [q for q in self.query(Kind.QUESTION, status=Status.OPEN) if q.payload.material is True]

    def calculated_facts(self) -> list[Entity]:
        return [f for f in self.live(Kind.FACT) if f.payload.basis == FactBasis.CALCULATED]

    def facts_by_measure(self) -> dict[str, list[Entity]]:
        """Live facts grouped by the MEASURE they are attached to -- the only
        join reconciliation is allowed (MF1.6); a fact with no measure is in
        no group."""
        out: dict[str, list[Entity]] = {}
        for f in self.live(Kind.FACT):
            if f.payload.measure_id is None:
                continue
            out.setdefault(f.payload.measure_id, []).append(f)
        return out

    def infeasible_objectives_without_decision(self) -> list[Entity]:
        """An objective the facts show infeasible must have been put to the
        client as a DECISION_REQUIRED (L12). A decision that was rejected or
        withdrawn no longer counts as asked."""
        asked: set[str] = set()
        for d in self.live(Kind.DECISION_REQUIRED):
            asked.update(d.provenance.derived_from)
            asked.update(d.payload.options)
            if d.payload.decision_id is not None:
                asked.add(d.payload.decision_id)
        return [o for o in self.live(Kind.OBJECTIVE)
                if o.payload.feasibility == Feasibility.INFEASIBLE_ON_FACTS and o.id not in asked]

    def client_facts_confirmed(self) -> list[Entity]:
        return [f for f in self.query(Kind.FACT, status=Status.CONFIRMED) if f.payload.basis == FactBasis.CLIENT_STATED]

    def live_summary(self) -> dict:
        """Ids grouped by query, recomputed on every read and never stored:
        the reply renders it, so there is no summary prose to drift."""
        open_questions = self.query(Kind.QUESTION, status=Status.OPEN)
        # Ranking only: an unknown value sorts last and stays None in the row.
        ranked = sorted(open_questions, key=lambda q: -(q.payload.value if q.payload.value is not None else 0.0))
        return {
            "confirmed_facts": [f.id for f in self.query(Kind.FACT, status=Status.CONFIRMED)],
            "assumptions_approved": [a.id for a in self.query(Kind.ASSUMPTION, status=Status.APPROVED)],
            "assumptions_unapproved": [a.id for a in self.unapproved_assumptions()],
            "missing": [q.id for q in ranked],
            "risks": [r.id for r in self.live(Kind.RISK)],
            "conflicts": [c.id for c in self.query(Kind.CONFLICT, status=Status.OPEN)],
            "decisions_required": [d.id for d in self.query(Kind.DECISION_REQUIRED, status=Status.OPEN)],
            "regulated_matters": [m.id for m in self.query(Kind.REGULATED_MATTER, status=Status.ROUTED)],
        }


class ScopedView:
    """A specialist's window: get()/query() outside the permitted set return
    None/[] -- a specialist cannot read what it was not given, so it cannot
    cite it either (S5). Every CONFIRMED client preference is in the window
    whatever the assignment listed: objectives, constraints and deadlines are
    the frame every analysis works inside. The window is fixed at
    construction, the moment the assignment is issued."""

    def __init__(self, registry: EngagementRegistry, permitted: Iterable[str]):
        self._r = registry
        self.engagement_id = registry.engagement_id
        prefs = {e.id for e in registry.query(status=Status.CONFIRMED) if e.info_type == InfoType.CLIENT_PREFERENCE}
        self.permitted: frozenset[str] = frozenset(permitted) | frozenset(prefs)

    def get(self, entity_id: str) -> Entity | None:
        return self._r.get(entity_id) if entity_id in self.permitted else None

    def query(self, kind: Kind | None = None, *, status: Status | None = None,
              where: Mapping[str, Any] | None = None) -> list[Entity]:
        return [e for e in self._r.query(kind, status=status, where=where) if e.id in self.permitted]

    def live(self, kind: Kind | None = None, *, where: Mapping[str, Any] | None = None) -> list[Entity]:
        return [e for e in self.query(kind, where=where) if e.status not in TERMINAL_STATUSES]

    def lineage(self, entity_id: str) -> list[Entity]:
        return self._r.lineage(entity_id) if entity_id in self.permitted else []

    def content_hash(self) -> str:
        h = hashlib.sha256()
        for i in sorted(self.permitted):
            e = self._r.get(i)
            if e is not None:
                h.update(e.content_hash().encode())
        return h.hexdigest()

    def central_decision(self) -> Entity | None:
        c = self._r.central_decision()
        return c if c is not None and c.id in self.permitted else None

    def supports_of(self, entity_id: str) -> list[Entity]:
        if entity_id not in self.permitted:
            return []
        return [s for s in self._r.supports_of(entity_id) if s.id in self.permitted]

    def source_text(self, source_id: str) -> str | None:
        return self._r.source_text(source_id) if source_id in self.permitted else None

    def reserve_ids(self, kind: Kind, count: int) -> list[str]:
        """Forwarded whole. An id is not evidence: withholding the counter
        would not narrow what a specialist may read, it would only make it
        collide with rows outside its window (I6)."""
        return self._r.reserve_ids(kind, count)


__all__ = [
    "EngagementRegistry", "RegistryView", "ScopedView", "SUPERSEDED_BY_RECORD",
    "Calculator", "CalcResult", "IncomparableInputs", "Reconciliation",
]
