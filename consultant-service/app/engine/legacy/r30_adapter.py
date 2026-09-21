"""r30_adapter - the typed seam between the engine and the technology
pipeline behind `app/pipeline` (design 13).

There is no "technology engagement" switch anywhere. The pipeline is reached
only by an ordinary registered method selected on an issue's shape
(`methods/builtin/legacy_r30_technology_blueprint.py`), and everything it is
told is composed here, by query, from entities the engagement already holds.

The laws this module enforces, each in the docstring of the thing that
enforces it:

  A1  every text handed to the pipeline is the text of a registry entity this
      run cites; nothing is coined, defaulted or read from anywhere else
      (`compose_inputs`, `_Composed.take`).
  A2  `engagement_type` is a structural predicate - "capability" exactly when
      the target workstream's capability classes are a PROPER subset of the
      classes across every workstream, else "full". A slice of a business is
      a slice because its classes are fewer, not because someone said so
      (`engagement_type_for`).
  A3  the Request row is created once, through the fields the intake
      constructor uses (`app/routers/requests.py:199-224`), and is never
      written again by the engine. `assert_row_untouched` is the check, and
      `mapping.import_r30` runs it around every import (design 13.4).
  A4  the pipeline is a costed step: the caller runs it only behind a
      DECISION_REQUIRED the client resolved (`COMMISSION_TEXT`, enforced in
      the method).

Absence stays absence: a field the registry does not hold is None or the
declared "maybe", never a guess (spec section 7).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from app.engine import types as T
from app.pipeline import export_pdf as _export_pdf
from app.pipeline import integrity as _integrity
from app.pipeline import registry as _r30_registry
from app.pipeline.phase2_bridge import _joined


# ---------------------------------------------------------------------------
# r30's own vocabularies, named once
# ---------------------------------------------------------------------------
# These are r30's strings, not the engine's. They live in named constants and
# named sets because no branch test under app/engine may compare against a
# string constant (design 18.2): the engine's control flow reads enums,
# booleans and membership of a declared table, never a word.

# app/routers/requests.py:25 `_ALLOWED_ENGAGEMENTS`
ENGAGEMENT_FULL = "full"
ENGAGEMENT_CAPABILITY = "capability"
# indexed by "is a proper slice of the business", so the choice is a bool
_ENGAGEMENT_BY_SLICE: tuple[str, str] = (ENGAGEMENT_FULL, ENGAGEMENT_CAPABILITY)

# app/pipeline/_shared.py:58-63 branches on "no" and "maybe"; anything else
# reads as "yes". "maybe" is the answer when the registry says nothing.
NEEDS_AI_YES = "yes"
NEEDS_AI_NO = "no"
NEEDS_AI_MAYBE = "maybe"

# The one CONSTRAINT shape that records "the client's policy rules this class
# of solution out". ConstraintPayload.kind is r30-free text with a closed
# comment list; it is read as a filter value, never as a branch test.
_POLICY_CONSTRAINT_KIND = "policy"
# BusinessContextPayload.aspect values that name the market the business is in
_INDUSTRY_ASPECTS: frozenset[str] = frozenset({"market"})

# r30's terminal run status (`app/pipeline/orchestrator.py`) and the release
# states that are not DRAFT (`export_pdf.release_status` :628).
R30_DONE: frozenset[str] = frozenset({"done"})
R30_RELEASED: frozenset[str] = frozenset({"final", "client_approved"})

# The three volumes r30 renders (`export_pdf.build_pdf` :1747).
VOLUME_KINDS: tuple[str, ...] = ("blueprint", "technical", "operations")

# The decision the client resolves before a single dollar is spent (A4).
COMMISSION_TEXT = "commission technology blueprint"


class LegacyRowWritten(RuntimeError):
    """A3: the engine wrote to a Request row it may only read."""


class LegacyInputsCoined(ValueError):
    """A1: a composed input was not the text of a cited registry entity."""


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def _display(e: T.Entity | None) -> str:
    """The one human wording a payload carries, whichever field holds it.
    Same reading order the method library uses, so the text this adapter
    cites is the text the rest of the engine shows."""
    if e is None:
        return ""
    for name in ("text", "statement", "name", "question"):
        v = getattr(e.payload, name, None)
        if v:
            return str(v)
    return ""


def _texts_of(e: T.Entity | None) -> list[str]:
    """Every text one entity carries that this adapter is allowed to send: the
    payload's wording, and the FACT `topic` a client number is filed under.
    A1 measures composed text against this list, so widening it is a visible
    decision rather than a quiet one."""
    if e is None:
        return []
    out = [_display(e)]
    topic = getattr(e.payload, "topic", None)
    if topic:
        out.append(str(topic))
    return [t for t in out if t]


def _live(view, kind: T.Kind, *, where: Mapping[str, Any] | None = None) -> list[T.Entity]:
    """The engagement's current position for one kind. RegistryView has
    query() but not live(), so the retirement filter lives here once."""
    return [e for e in view.query(kind, where=where) if e.status not in T.TERMINAL_STATUSES]


def _client_first(entities: Sequence[T.Entity]) -> list[T.Entity]:
    """The client's own words first, always - theirs are the true ones
    (`phase2_bridge._joined` `app/pipeline/phase2_bridge.py:196`). Write order
    is kept inside each group, so the join is byte-identical across runs."""
    ordered = list(entities)
    return [ordered[i] for i in sorted(
        range(len(ordered)),
        key=lambda i: (0 if ordered[i].provenance.actor is T.Actor.CLIENT else 1, i))]


@dataclass
class _Composed:
    """A1's ledger. Every text that reaches the pipeline is taken from an
    entity through `take()`, which records the id it came from and refuses a
    text the entity does not carry. A coined default cannot pass through it,
    which is the whole point: the pipeline is expensive and it believes what
    it is told."""
    cited: list[str] = field(default_factory=list)

    def take(self, e: T.Entity | None) -> str:
        if e is None:
            return ""
        text = _display(e)
        if not text:
            return ""
        if e.id and e.id not in self.cited:
            self.cited.append(e.id)
        return text

    def join(self, entities: Iterable[T.Entity]) -> str:
        out = ""
        for e in entities:
            out = _joined(out, self.take(e))
        return out


@dataclass(frozen=True)
class OpsPair:
    """One discovery number as r30 reads it, with the FACT it came from kept
    beside it. `registry.client_fact_claims` (`app/pipeline/registry.py:325`)
    reads `answer` character for character, so `answer` is the client fact's
    statement verbatim and nothing else."""
    question: str
    answer: str
    entity_id: str


@dataclass(frozen=True)
class R30Inputs:
    """Everything the intake constructor needs, composed by query. Frozen:
    what was sent is what is kept for lineage."""
    business_name: str
    business_description: str
    main_problem: str
    desired_outcome: str
    engagement_type: str
    needs_ai: str
    owner_email: str
    ops_numbers: tuple[OpsPair, ...] = ()
    industry: str | None = None
    document_owner: str | None = None
    document_approver: str | None = None
    workstream_id: str | None = None
    issue_id: str | None = None
    source_entity_ids: tuple[str, ...] = ()

    def ops_numbers_json(self) -> str:
        """The `[{question, answer}]` list, through r30's own sanitiser so the
        bound on count and length is r30's and cannot drift from it
        (`_sanitize_ops_numbers` `app/routers/requests.py:134`)."""
        from app.routers.requests import _sanitize_ops_numbers

        raw = json.dumps([{"question": p.question, "answer": p.answer} for p in self.ops_numbers])
        return _sanitize_ops_numbers(raw) or ""

    def request_fields(self) -> dict:
        """Exactly the constructor fields `create_request` sets
        (`app/routers/requests.py:199-224`), minus the ones the row generates
        for itself (public_id, status, is_generating)."""
        return {
            "business_name": self.business_name,
            "business_description": self.business_description,
            "email": self.owner_email,
            "industry": self.industry,
            "target_customers": None,
            "main_problem": self.main_problem,
            "reference_url": None,
            "what_you_like": None,
            "desired_outcome": self.desired_outcome,
            "needs_ai": self.needs_ai,
            "budget_range": None,
            "timeline": None,
            "whatsapp": None,
            "site_url": None,
            "revenue_today": None,
            "operating_stage": None,
            "engagement_type": self.engagement_type,
            "ops_numbers_json": self.ops_numbers_json() or None,
            "document_owner": self.document_owner,
            "document_approver": self.document_approver,
            "owner_email": self.owner_email,
        }


def engagement_type_for(view, workstream_id: str | None) -> str:
    """A2. "capability" exactly when the target workstream's capability
    classes are a PROPER subset of the classes across every live workstream -
    the structural reading of "one capability inside an existing operation".
    A registry with one workstream, or a target that carries every class the
    engagement knows, is the whole business: "full".

    `_shared.build_engagement_register` (`app/pipeline/_shared.py:38`)
    branches on the answer inside r30; the engine states the fact and never
    the branch."""
    workstreams = _live(view, T.Kind.WORKSTREAM)
    target = view.get(workstream_id) if workstream_id else None
    if target is None or target.kind is not T.Kind.WORKSTREAM:
        return ENGAGEMENT_FULL
    mine = set(target.payload.capability_classes)
    everything: set[T.CapabilityClass] = set()
    for w in workstreams:
        everything.update(w.payload.capability_classes)
    is_slice = bool(mine) and mine < everything
    return _ENGAGEMENT_BY_SLICE[int(is_slice)]


def _needs_ai(view, workstream_id: str | None) -> str:
    """The AI appetite, from typed fields only. A hard CONSTRAINT the client
    recorded under the policy kind is the one typed way this registry can say
    "our policy rules that out"; a software-system class in scope is the one
    typed way it can say software is wanted. Neither present is "maybe":
    absence of an appetite is not a refusal, and r30 treats "no" as an
    instruction to recommend none (`_shared.py:58`), so "no" is never
    inferred from silence."""
    if _live(view, T.Kind.CONSTRAINT, where={"kind": _POLICY_CONSTRAINT_KIND, "hard": True}):
        return NEEDS_AI_NO
    target = view.get(workstream_id) if workstream_id else None
    classes: set[T.CapabilityClass] = set()
    if target is not None and target.kind is T.Kind.WORKSTREAM:
        classes.update(target.payload.capability_classes)
    for e in _live(view, T.Kind.INITIATIVE):
        classes.add(e.payload.capability_class)
    if T.CapabilityClass.SOFTWARE_SYSTEM in classes:
        return NEEDS_AI_YES
    return NEEDS_AI_MAYBE


def _ops_pairs(view, took: _Composed, *, issue: T.Entity | None) -> tuple[OpsPair, ...]:
    """The discovery numbers: every live client-stated FACT that carries a
    quantity, answer verbatim. The question is the MEASURE the fact is
    attached to, else the fact's own topic, else the issue this run settles -
    three registered texts, so no label is invented for a client's number."""
    pairs: list[OpsPair] = []
    for f in _live(view, T.Kind.FACT, where={"basis": T.FactBasis.CLIENT_STATED, "has_quantity": True}):
        answer = took.take(f)
        if not answer:
            continue
        measure = view.get(f.payload.measure_id) if f.payload.measure_id else None
        question = took.take(measure) or (f.payload.topic or "") or took.take(issue)
        if not question:
            continue
        pairs.append(OpsPair(question=question, answer=answer, entity_id=f.id))
    return tuple(pairs)


def _document_control(view, took: _Composed) -> tuple[str | None, str | None]:
    """Document owner and approver from the DECISION_OWNER rows the client
    named. Two distinct owners give an owner and an approver; one gives an
    owner and no approver; none gives neither. A missing approver is a
    missing approver - r30 downgrades the manual for it, which is correct."""
    owners = _live(view, T.Kind.DECISION_OWNER)
    names: list[str] = []
    for o in owners:
        label = took.take(o)
        role = getattr(o.payload, "role", "") or ""
        full = f"{label} ({role})" if (label and role) else label
        if full and full not in names:
            names.append(full)
    owner = names[0] if names else None
    approver = names[1] if len(names) > 1 else None
    return owner, approver


def compose_inputs(view, *, business_name: str, owner_email: str,
                   issue_id: str | None = None, workstream_id: str | None = None) -> R30Inputs:
    """A1. Compose what the pipeline is told, entirely from registry
    entities. `business_name` and `owner_email` are engagement-row properties
    (the client's account and the name the engagement is filed under), not
    claims about the business, and are passed in by the caller that owns
    them; every other field is a query, and `source_entity_ids` names each
    entity that contributed.

    Raises LegacyInputsCoined when a composed text is not the text of a cited
    entity - the check that a default can never be sent to a paid pipeline as
    if the client had said it."""
    took = _Composed()
    issue = view.get(issue_id) if issue_id else None

    contexts = _live(view, T.Kind.BUSINESS_CONTEXT)
    description = took.join(_client_first(contexts))
    industry_rows = [c for c in contexts if (getattr(c.payload, "aspect", "") in _INDUSTRY_ASPECTS)]
    industry = took.take(industry_rows[0]) if industry_rows else None

    main_problem = took.take(issue)
    desired_outcome = took.join(_live(view, T.Kind.OBJECTIVE))
    ops = _ops_pairs(view, took, issue=issue)
    document_owner, document_approver = _document_control(view, took)

    workstream = view.get(workstream_id) if workstream_id else None
    if workstream is not None and workstream.id and workstream.id not in took.cited:
        took.cited.append(workstream.id)

    inputs = R30Inputs(
        business_name=business_name,
        business_description=description,
        main_problem=main_problem,
        desired_outcome=desired_outcome,
        engagement_type=engagement_type_for(view, workstream_id),
        needs_ai=_needs_ai(view, workstream_id),
        owner_email=owner_email,
        ops_numbers=ops,
        industry=industry,
        document_owner=document_owner,
        document_approver=document_approver,
        workstream_id=workstream_id,
        issue_id=issue_id,
        source_entity_ids=tuple(took.cited),
    )
    check_composed(inputs, view)
    return inputs


def check_composed(inputs: R30Inputs, view) -> None:
    """A1, restated on the finished object so the law holds on the result
    rather than on the courtesy of the composer. Every composed text is
    covered by the texts of the entities the inputs cite; the engagement's
    own name and the account's email are the two declared exceptions, because
    neither is a claim about the business.

    Removing this check is the mutation "compose a default when the registry
    holds nothing"."""
    cited_texts: list[str] = []
    for i in inputs.source_entity_ids:
        cited_texts.extend(_texts_of(view.get(i)))
    # Single-entity fields are one entity's text exactly.
    single = [inputs.main_problem, inputs.industry or ""]
    single.extend(p.answer for p in inputs.ops_numbers)
    single.extend(p.question for p in inputs.ops_numbers)
    for text in single:
        if text and not any(text == t for t in cited_texts):
            raise LegacyInputsCoined(f"composed text {text[:60]!r} is the text of no cited entity")
    # Joined fields are cited texts laid end to end: every cited text they
    # claim to join must be findable in them, and nothing else may be there.
    for joined in (inputs.business_description, inputs.desired_outcome):
        remainder = joined
        for t in cited_texts:
            remainder = remainder.replace(t, "")
        if joined and remainder.strip():
            raise LegacyInputsCoined(f"joined field carries {remainder.strip()[:60]!r}, which no cited entity says")


# ---------------------------------------------------------------------------
# Outputs (read-only)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class R30Outputs:
    """What r30 produced, read back through r30's own public functions:
    `integrity.load` (`app/pipeline/integrity.py:83`),
    `registry.registry_for` (`app/pipeline/registry.py:2815`),
    `integrity.current_report` (`:1230`) and `export_pdf.release_status`
    (`app/pipeline/export_pdf.py:628`). Every field is a copy; `row` is kept
    only so the volumes can be rendered and the untouched check can run, and
    it is never written to (A3)."""
    request_id: int
    status: str
    is_failed: bool
    content: Mapping[str, Any]
    registry: Mapping[str, Any]
    report: Mapping[str, Any] | None
    release: Mapping[str, Any]
    content_hash: str
    report_json: str | None
    row: Any = None

    @property
    def claims(self) -> list[Mapping[str, Any]]:
        return [c for c in (self.registry.get("claims") or []) if isinstance(c, Mapping)]

    @property
    def modules(self) -> list[Mapping[str, Any]]:
        return [m for m in (self.registry.get("modules") or []) if isinstance(m, Mapping)]

    @property
    def delivered(self) -> bool:
        """True only when the run finished. A run that never completed holds
        no outputs at all - not an empty package, no package."""
        return self.status in R30_DONE and not self.is_failed

    @property
    def released(self) -> bool:
        return str(self.release.get("status") or "") in R30_RELEASED


def row_content_hash(row: Any) -> str:
    """The r30 content hash of a Request row, through r30's own functions.
    A3's before/after measurement."""
    return _integrity.content_hash(_integrity.load(row))


def assert_row_untouched(row: Any, before: tuple[str, str | None]) -> None:
    """A3. The engine reads the legacy package; it never edits it. A
    correction re-commissions a new Request with revised inputs and keeps the
    old one as lineage (design 13.4), so any change to the row's content hash
    or to its stored integrity report while the engine held it is a bug in
    the engine, not a new fact about the business.

    Removing this raises nothing when a mapper writes to the row: it is the
    mutation "write to the Request row in mapping"."""
    now = (row_content_hash(row), getattr(row, "integrity_report_json", None))
    if now != tuple(before):
        raise LegacyRowWritten(
            f"the engine changed r30 request {getattr(row, 'id', '?')}: the legacy package is read-only")


def snapshot(row: Any) -> tuple[str, str | None]:
    """The pair `assert_row_untouched` compares against."""
    return (row_content_hash(row), getattr(row, "integrity_report_json", None))


def load_outputs(row: Any) -> R30Outputs:
    """Read the finished package. Nothing here writes, and every reader is
    r30's own: a shape the engine invented would drift from what r30 ships."""
    content = _integrity.load(row)
    report = _integrity.current_report(row)
    return R30Outputs(
        request_id=int(getattr(row, "id", 0) or 0),
        status=str(getattr(row, "status", "") or ""),
        is_failed=bool(getattr(row, "is_failed", False)),
        content=content,
        registry=_r30_registry.registry_for(row) or {},
        report=report,
        release=_export_pdf.release_status(row),
        content_hash=_integrity.content_hash(content),
        report_json=getattr(row, "integrity_report_json", None),
        row=row,
    )


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def build_request(db, inputs: R30Inputs):
    """A3 (first half): one Request row, through exactly the constructor
    fields the intake uses, with the same generated public_id
    (`app/routers/requests.py:199-224`). `requests.py` stays untouched, which
    is why the fields are restated here rather than the endpoint called: an
    HTTP round trip would need the client's bearer token, and the engine acts
    for an engagement, not for a browser."""
    # Imported here, not at module scope: composing inputs and importing a
    # finished package are pure functions of their arguments, and neither
    # should pull the ORM in behind them.
    import secrets

    from app.models import Request

    row = Request(**inputs.request_fields(), public_id=secrets.token_urlsafe(9),
                  status="new", is_generating=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def run_technology_blueprint(db, inputs: R30Inputs) -> R30Outputs:
    """Commission one r30 run and read the result back.

    The calls are `orchestrator.run` then `orchestrator.run_build` on THIS
    thread, not a new one: the engine's analysis round already runs in a
    background thread and owns this session, and a second daemon thread would
    outlive it. Tests monkeypatch `orchestrator.run` exactly as
    `tests/test_discovery.py:34` does.

    Two calls because r30 now halts at a client approval gate. The engine has
    already made and recorded that decision before it commissions a build —
    this call IS the approval — so it presses through rather than exposing a
    second gate the engine's own client would answer twice.

    A4 is the caller's: this function spends money and assumes the
    DECISION_REQUIRED behind it was resolved."""
    from app.pipeline import orchestrator

    row = build_request(db, inputs)
    orchestrator.run(row.id)
    db.refresh(row)
    if row.status == orchestrator.AWAITING_APPROVAL:
        orchestrator.run_build(row.id)
        db.refresh(row)
    return load_outputs(row)


def volume_path(outputs: R30Outputs, kind: str) -> str:
    """One legacy volume as a file, through `export_pdf.build_pdf`
    (`app/pipeline/export_pdf.py:1747`) unchanged - same faces, same footer,
    same DRAFT stamp (MF2.7). Building reads the row; it never writes it."""
    return _export_pdf.build_pdf(outputs.row, kind)


__all__ = [n for n in dir() if not n.startswith("_")]
