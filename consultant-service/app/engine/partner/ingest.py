"""app/engine/partner/ingest.py - turn and document ingestion (design 6.2 step 1).

The client's message becomes an EVIDENCE_SOURCE conversation-turn row carrying
its text; an attachment becomes an EVIDENCE_SOURCE document/dataset row carrying
sha256, byte_size and a text_ref, with the extracted text registered on the
registry so I2 has something to check locators against. One structured model
call per source (extract_turn.j2 / extract_document.j2) words candidates; the
registry decides them. The laws this module lives by:

  * Nothing ingested is ever CONFIRMED by ingestion. Every candidate is written
    PROPOSED (questions OPEN) by Actor.PARTNER; confirmation is the client's
    recorded act, later. The one construction site is _proposed().
  * verify_quote() is verbatim substring or nothing. No case folding, no
    whitespace collapse, no similarity: a promoted quote that is not the
    document's exact bytes would print as a record the document never made,
    and I2 would have nothing real to re-check.
  * The registry, not this module, refuses a client fact that restates the
    client (I2). Candidates are applied one by one; a refusal is recorded in
    IngestOutcome.refused and the rest of the turn still lands - one
    hallucinated quote must not cost the client their whole message.
  * A record class is a proposal. The model's choice is written onto the
    source row with record_class_confirmed_by_client=False; precedence between
    documents (design 5.4) only ever runs on a class the CLIENT confirmed, so
    confirming it here would let extraction decide conflicts.
  * Two documents of equal proposed rank carrying one measure is a provenance
    QUESTION (OFFHAND), not a resolution: equal rank never resolves (design 5.4).
  * "Don't know" is an answer. It sets QuestionPayload.unknown=True and
    resolves the question by the client's own actor; open_questions() excludes
    it, so the client is never asked again (RECORD_UNKNOWN, design 6.5).
  * A number never comes from the model. Quantities are parsed by calc.units
    from the quoted span; the model's value field is ignored, so a figure that
    is not in the source does not exist.
  * xlsx is refused with a QUESTION asking for a CSV or PDF export (design 22,
    MF3.8): a workbook read through a guessed parser would be a record nobody
    can verify.
"""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, replace
from typing import Any

from pydantic import BaseModel

from app.engine.calc.units import parse_quantity
from app.engine.llm import ModelCall, ModelProvider, StructuredFailure, structured_call
from app.engine.registry import EngagementRegistry
from app.engine.templating import render
from app.engine.types import (
    TERMINAL_STATUSES, Actor, Add, AsksFor, BusinessContextPayload, Confidence, ConstraintPayload,
    DeadlinePayload, DecisionOwnerPayload, DecisionPayload, DecisionRole, Dimensions, EffortClass,
    Entity, EvidenceSourcePayload, FactBasis, FactPayload, FillStrategy, Kind, MeasurePayload,
    ObjectivePayload, Provenance, Quantity, QuestionPayload, RecordClass, RegistryError, Relevance,
    RelationToCentralDecision, SourceKind, StakeholderPayload, Status, Supersede, UnitFamily,
    make_entity,
)

__all__ = [
    "IngestOutcome",
    "TURN_CANDIDATE_KINDS",
    "TurnExtraction",
    "DocumentExtraction",
    "extract_text",
    "ingest_document",
    "ingest_turn",
    "open_questions",
    "verify_quote",
]

# The kinds one conversation turn may propose (design 6.2 step 1). A closed
# list rendered into the prompt; anything else the model returns is dropped.
TURN_CANDIDATE_KINDS: tuple[Kind, ...] = (
    Kind.BUSINESS_CONTEXT, Kind.DECISION, Kind.OBJECTIVE, Kind.CONSTRAINT, Kind.DEADLINE,
    Kind.DECISION_OWNER, Kind.STAKEHOLDER, Kind.MEASURE, Kind.FACT,
)

# Workbook formats are refused, never parsed (MF3.8): there is no openpyxl in
# the frozen requirements, and a guessed reading of a workbook would produce
# text no locator can be verified against.
_REFUSED_SUFFIXES: tuple[str, ...] = (".xlsx", ".xlsm", ".xls")
_TABLE_SUFFIXES: tuple[str, ...] = (".csv", ".tsv")


# =============================================================================
# 1. What the model returns (validated by structured_call; extras ignored)
# =============================================================================

class _QtyIn(BaseModel):
    """The model's reading of a figure. Only the DIMENSIONS are used: the
    value is re-parsed from the quoted span by calc.units, so a number the
    source did not write cannot enter the registry through this shape."""
    value: Any = None
    unit: str | None = None
    currency: str | None = None
    period: str | None = None


class _TurnCandidate(BaseModel):
    kind: str = ""
    quote: str = ""
    text: str = ""
    quantity: _QtyIn | None = None
    measure_id: str | None = None
    measure_name: str | None = None
    role: str | None = None
    answers: tuple[str, ...] = ()
    unknown: bool = False


class TurnExtraction(BaseModel):
    candidates: tuple[_TurnCandidate, ...] = ()


class _DocumentFact(BaseModel):
    quote: str = ""
    statement: str = ""
    quantity: _QtyIn | None = None
    measure_id: str | None = None
    measure_name: str | None = None
    definition: str | None = None
    as_of: str | None = None


class DocumentExtraction(BaseModel):
    record_class: str = RecordClass.UNKNOWN.value
    record_class_reason: str = ""
    facts: tuple[_DocumentFact, ...] = ()


@dataclass(frozen=True)
class IngestOutcome:
    """What one ingestion did, for the Partner reply to render. `refused`
    carries the registry's own words (a refusal is a fact about the turn,
    shown to the client as such, never silently swallowed)."""
    source: Entity
    created: tuple[Entity, ...] = ()
    questions: tuple[Entity, ...] = ()
    refused: tuple[str, ...] = ()
    answered: tuple[str, ...] = ()
    failure: str | None = None


# =============================================================================
# 2. The two local laws with teeth
# =============================================================================

def verify_quote(quote: str, text: str) -> bool:
    """Verbatim substring, or not verified. This is the ONLY promotion test
    (document_extracted -> document_verified): no normalisation and no
    similarity, because I2 will re-check the locator against the hashed text
    character for character, and a 'close enough' quote is a record the
    document never made."""
    return bool(quote) and quote in text


def open_questions(registry: EngagementRegistry) -> list[Entity]:
    """The questions a turn prompt may show and the client may answer. A
    question the client answered 'don't know' carries unknown=True and is
    excluded - never re-asked (RECORD_UNKNOWN). The check is `is True`, not
    truthiness, so an older row whose flag a newer normaliser left unset is
    not condemned by absence."""
    return [q for q in registry.query(Kind.QUESTION, status=Status.OPEN)
            if q.payload.unknown is not True]


# =============================================================================
# 3. Construction: one site writes PROPOSED, one site writes OPEN
# =============================================================================

def _proposed(engagement_id: str, kind: Kind, payload: Any, *, actor_ref: str,
              derived_from: tuple[str, ...], locator: str | None = None,
              model_call_id: str | None = None) -> Entity:
    """Every entity ingestion writes is a proposal: nothing ingested is ever
    CONFIRMED by ingestion - confirmation is an authority's recorded act, and
    extraction is not an authority over anything."""
    return make_entity(
        kind=kind, engagement_id=engagement_id, payload=payload,
        provenance=Provenance(actor=Actor.PARTNER, actor_ref=actor_ref, derived_from=derived_from,
                              source_locator=locator, model_call_id=model_call_id),
        confidence=Confidence(None), relevance=Relevance(None, 0.0),
        relation=RelationToCentralDecision.UNKNOWN,
        status=Status.PROPOSED,
    )


def _open_question(engagement_id: str, payload: QuestionPayload, *, actor_ref: str,
                   derived_from: tuple[str, ...]) -> Entity:
    return make_entity(
        kind=Kind.QUESTION, engagement_id=engagement_id, payload=payload,
        provenance=Provenance(actor=Actor.PARTNER, actor_ref=actor_ref, derived_from=derived_from),
        confidence=Confidence(None), relevance=Relevance(None, 0.0),
        relation=RelationToCentralDecision.UNKNOWN,
        status=Status.OPEN,
    )


def _quantity_of(quote: str, statement: str, qty: _QtyIn | None, *,
                 as_of: str | None = None, definition: str | None = None) -> Quantity | None:
    """The quantity of a candidate: parsed from the quoted span (the digits
    the source wrote), dimensioned by what the model read AS WRITTEN. A
    dimension the source did not state stays None - a typed hole that becomes
    a QUESTION, never a default."""
    dims = Dimensions(
        currency=(qty.currency or None) if qty else None,
        period=(qty.period or None) if qty else None,
        as_of=as_of or None,
        definition=definition or None,
    )
    text = quote or statement
    if not text:
        return None
    return parse_quantity(text, context=f"{quote} {statement}", dimensions=dims)


def _resolve_measure(registry: EngagementRegistry, measure_id: str | None, measure_name: str | None,
                     family: UnitFamily | None, batch: dict[str, str], *, actor_ref: str,
                     derived_from: tuple[str, ...], locator: str | None,
                     model_call_id: str | None) -> tuple[str | None, Entity | None]:
    """Attachment is a closed choice: the id must name a live registered
    MEASURE (the model chose it from the rendered list); an id the registry
    does not know is not a match - never guessed into one. Otherwise a named
    new measure is PROPOSED once per batch and the fact attaches to it."""
    if measure_id:
        existing = registry.get(measure_id)
        if existing is not None and existing.kind is Kind.MEASURE \
                and existing.status not in TERMINAL_STATUSES:
            return existing.id, None
    name = (measure_name or "").strip()
    if not name:
        return None, None
    key = name.lower()
    if key in batch:
        return batch[key], None
    entity = _proposed(registry.engagement_id, Kind.MEASURE,
                       MeasurePayload(name=name, unit_family=family or UnitFamily.OTHER),
                       actor_ref=actor_ref, derived_from=derived_from, locator=locator,
                       model_call_id=model_call_id)
    row = registry.apply(Add(entity))
    batch[key] = row.id
    return row.id, row


def _turn_kind(value: str) -> Kind | None:
    try:
        kind = Kind(value)
    except ValueError:
        return None
    return kind if kind in TURN_CANDIDATE_KINDS else None


def _turn_payload(kind: Kind, cand: _TurnCandidate, *, turn_number: int,
                  quantity: Quantity | None, measure_id: str | None) -> Any | None:
    """The typed payload for one turn candidate. A FACT's statement is the
    quoted span itself: the registry (I2) will hold it against the turn text,
    so restating here would only manufacture a refusal."""
    text = (cand.text or cand.quote).strip()
    if not text:
        return None
    if kind is Kind.BUSINESS_CONTEXT:
        return BusinessContextPayload(text=text)
    if kind is Kind.DECISION:
        # Turn 1 states the request; later decision candidates are subordinate.
        # CENTRAL is never proposed by extraction - the hypothesis loop and the
        # client's charter confirmation decide what is central (design 6.4).
        role = DecisionRole.STATED_REQUEST if turn_number == 1 else DecisionRole.SUBORDINATE
        return DecisionPayload(statement=text, role=role)
    if kind is Kind.OBJECTIVE:
        return ObjectivePayload(text=text, measure_id=measure_id, target=quantity)
    if kind is Kind.CONSTRAINT:
        return ConstraintPayload(text=text)
    if kind is Kind.DEADLINE:
        return DeadlinePayload(text=text)
    if kind is Kind.DECISION_OWNER:
        return DecisionOwnerPayload(name=text, role="")
    if kind is Kind.STAKEHOLDER:
        return StakeholderPayload(name=text, role="")
    if kind is Kind.FACT:
        return FactPayload(statement=cand.quote, basis=FactBasis.CLIENT_STATED,
                           measure_id=measure_id, quantity=quantity)
    return None


# =============================================================================
# 4. Answers: recorded on the question, 'don't know' resolved by the client
# =============================================================================

def _record_answer(registry: EngagementRegistry, question_id: str, entity_id: str, *,
                   actor_ref: str, turn_id: str) -> None:
    q = registry.get(question_id)
    if q is None or q.kind is not Kind.QUESTION:
        return
    if entity_id in q.payload.answer_entity_ids:
        return
    entity = replace(
        q,
        payload=replace(q.payload, answer_entity_ids=q.payload.answer_entity_ids + (entity_id,)),
        provenance=Provenance(actor=Actor.PARTNER, actor_ref=actor_ref,
                              derived_from=tuple(dict.fromkeys(q.provenance.derived_from + (turn_id, entity_id)))),
    )
    registry.apply(Supersede(q.id, entity))


def _record_unknown(registry: EngagementRegistry, question_id: str, *, turn_number: int,
                    turn_id: str) -> str | None:
    """'Don't know' is an answer: unknown=True, resolved by the CLIENT's own
    actor (MAY_RESOLVE admits the client). The flag survives on the resolved
    row, so every product can label the unknown, and open_questions() never
    shows it again."""
    q = registry.get(question_id)
    if q is None or q.kind is not Kind.QUESTION or q.payload.unknown is True:
        return None
    entity = replace(
        q,
        status=Status.RESOLVED,
        payload=replace(q.payload, unknown=True),
        provenance=Provenance(actor=Actor.CLIENT, actor_ref=f"client:turn:{turn_number}",
                              derived_from=tuple(dict.fromkeys(q.provenance.derived_from + (turn_id,)))),
    )
    registry.apply(Supersede(q.id, entity))
    return q.id


# =============================================================================
# 5. Text extraction (pymupdf for PDF, csv for tables, plain text; xlsx refused)
# =============================================================================

def _decode(data: bytes) -> str:
    for encoding in ("utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract_text(name: str, data: bytes) -> tuple[str | None, SourceKind, str | None]:
    """(text, source_kind, refusal). The text returned here is the text the
    model is shown AND the text register_source_text hashes locators against:
    one extraction, one truth, so a verified quote is verifiable forever."""
    lower = (name or "").lower()
    if lower.endswith(_REFUSED_SUFFIXES):
        return None, SourceKind.DOCUMENT, "workbook files are not read here"
    if lower.endswith(".pdf"):
        try:
            import pymupdf
            doc = pymupdf.open(stream=data, filetype="pdf")
            try:
                text = "\n".join(page.get_text() for page in doc)
            finally:
                doc.close()
        except Exception as exc:  # a corrupt PDF is a refusal, not a guess
            return None, SourceKind.DOCUMENT, f"the PDF could not be read: {str(exc)[:160]}"
        return text, SourceKind.DOCUMENT, None
    if lower.endswith(_TABLE_SUFFIXES):
        delimiter = "\t" if lower.endswith(".tsv") else ","
        rows = list(csv.reader(io.StringIO(_decode(data)), delimiter=delimiter))
        return "\n".join(",".join(cells) for cells in rows), SourceKind.DATASET, None
    return _decode(data), SourceKind.DOCUMENT, None


# =============================================================================
# 6. The provenance question (equal proposed rank on one measure, design 6.2)
# =============================================================================

def _measure_already_questioned(registry: EngagementRegistry, measure_id: str) -> bool:
    # Any question that cites the measure - open, resolved or answered
    # 'don't know' - counts: the client is asked about a measure's provenance
    # at most once.
    for q in registry.query(Kind.QUESTION):
        if measure_id in q.provenance.derived_from:
            return True
    return False


def _provenance_questions(registry: EngagementRegistry, *, actor_ref: str) -> list[Entity]:
    """One OFFHAND question per measure carried by two or more documents of
    EQUAL proposed record class. Equal rank never resolves automatically
    (design 5.4); only the client's confirmation of what each document IS can
    break the tie, so the engine asks instead of choosing."""
    created: list[Entity] = []
    document_bases = (FactBasis.DOCUMENT_EXTRACTED, FactBasis.DOCUMENT_VERIFIED)
    for measure_id, facts in registry.facts_by_measure().items():
        if _measure_already_questioned(registry, measure_id):
            continue
        sources: dict[str, RecordClass] = {}
        for f in facts:
            if f.payload.basis not in document_bases:
                continue
            for sid in f.provenance.derived_from:
                src = registry.get(sid)
                if src is None or src.kind is not Kind.EVIDENCE_SOURCE:
                    continue
                if src.payload.source_kind is SourceKind.CONVERSATION_TURN:
                    continue
                # A class the client already confirmed is settled provenance;
                # the explicit `is True` keeps an older row's absent flag from
                # reading as either settled or contested.
                if src.payload.record_class_confirmed_by_client is True:
                    continue
                sources[sid] = src.payload.record_class
        classes = list(sources.values())
        if len(sources) < 2 or not any(classes.count(c) >= 2 for c in set(classes)):
            continue
        payload = QuestionPayload(
            text=("Two of the attached documents carry the same measure with the same proposed "
                  "record class. Which document is the authoritative record for this measure?"),
            asks_for=(AsksFor(Kind.EVIDENCE_SOURCE, {"record_class_confirmed_by_client": True}),),
            why="which document is the record decides precedence when their figures disagree",
            effort=EffortClass.OFFHAND,
            strategy=FillStrategy.ASK_CLIENT,
        )
        q = _open_question(registry.engagement_id, payload, actor_ref=actor_ref,
                           derived_from=(measure_id,) + tuple(sorted(sources)))
        created.append(registry.apply(Add(q)))
    return created


# =============================================================================
# 7. Turn ingestion
# =============================================================================

def _measures_context(registry: EngagementRegistry) -> list[dict[str, str]]:
    return [{"id": m.id, "name": m.payload.name, "unit_family": m.payload.unit_family.value}
            for m in registry.live(Kind.MEASURE)]


def ingest_turn(registry: EngagementRegistry, provider: ModelProvider, message: str, *,
                turn_number: int) -> IngestOutcome:
    """One client message -> one EVIDENCE_SOURCE turn row -> PROPOSED
    candidates citing it. The registry refuses what breaks its laws; the
    refusals are the outcome's to show, never this module's to hide."""
    actor_ref = f"partner:turn:{turn_number}"
    source = registry.apply(Add(_proposed(
        registry.engagement_id, Kind.EVIDENCE_SOURCE,
        EvidenceSourcePayload(name=f"turn {turn_number}", source_kind=SourceKind.CONVERSATION_TURN,
                              text=message),
        actor_ref=actor_ref, derived_from=())))
    askable = open_questions(registry)
    prompt = render(
        "extract_turn.j2",
        turn_id=source.id, turn_number=turn_number, message=message,
        open_questions=[{"id": q.id, "text": q.payload.text} for q in askable],
        registered_measures=_measures_context(registry),
        candidate_kinds=list(TURN_CANDIDATE_KINDS),
    )
    try:
        extraction, response = structured_call(provider, ModelCall(
            purpose="extract_turn", messages=({"role": "user", "content": prompt},),
            schema=TurnExtraction, engagement_id=registry.engagement_id))
    except StructuredFailure as exc:
        # The turn is recorded; the reading failed. Candidates can be retried
        # on the next turn - nothing is fabricated to fill the gap.
        return IngestOutcome(source=source, failure=str(exc))

    askable_ids = {q.id for q in askable}
    created: list[Entity] = []
    refused: list[str] = []
    answered: list[str] = []
    batch: dict[str, str] = {}
    for cand in extraction.candidates:
        answers = tuple(qid for qid in cand.answers if qid in askable_ids)
        if cand.unknown is True:
            for qid in answers:
                if _record_unknown(registry, qid, turn_number=turn_number, turn_id=source.id):
                    answered.append(qid)
            continue
        kind = _turn_kind(cand.kind)
        if kind is None:
            refused.append(f"dropped: {cand.kind!r} is not a kind a turn may propose")
            continue
        quantity = _quantity_of(cand.quote, cand.text, cand.quantity)
        family = quantity.unit_family if quantity is not None else None
        measure_name = cand.measure_name or (cand.text or cand.quote if kind is Kind.MEASURE else None)
        try:
            measure_id, measure_row = _resolve_measure(
                registry, cand.measure_id, measure_name, family, batch, actor_ref=actor_ref,
                derived_from=(source.id,), locator=cand.quote or None, model_call_id=response.call_id)
        except RegistryError as exc:
            refused.append(str(exc))
            continue
        if measure_row is not None:
            created.append(measure_row)
        if kind is Kind.MEASURE:
            continue  # the measure itself was the candidate
        payload = _turn_payload(kind, cand, turn_number=turn_number, quantity=quantity,
                                measure_id=measure_id)
        if payload is None:
            continue
        entity = _proposed(registry.engagement_id, kind, payload, actor_ref=actor_ref,
                           derived_from=(source.id,), locator=cand.quote or None,
                           model_call_id=response.call_id)
        try:
            row = registry.apply(Add(entity))
        except RegistryError as exc:
            refused.append(str(exc))
            continue
        created.append(row)
        for qid in answers:
            _record_answer(registry, qid, row.id, actor_ref=actor_ref, turn_id=source.id)
            answered.append(qid)
    return IngestOutcome(source=source, created=tuple(created), refused=tuple(refused),
                         answered=tuple(dict.fromkeys(answered)))


# =============================================================================
# 8. Document ingestion
# =============================================================================

def _proposed_record_class(value: str) -> RecordClass:
    try:
        return RecordClass(value)
    except ValueError:
        return RecordClass.UNKNOWN


def ingest_document(registry: EngagementRegistry, provider: ModelProvider, *, name: str,
                    data: bytes, turn_number: int) -> IngestOutcome:
    """One attachment -> one hashed EVIDENCE_SOURCE row (sha256, byte_size,
    text_ref), its extracted text registered for I2, and candidate FACTs whose
    basis is decided by verify_quote() alone."""
    actor_ref = f"partner:turn:{turn_number}"
    digest = hashlib.sha256(data).hexdigest()
    text, source_kind, refusal = extract_text(name, data)
    source = registry.apply(Add(_proposed(
        registry.engagement_id, Kind.EVIDENCE_SOURCE,
        EvidenceSourcePayload(name=name, source_kind=source_kind, sha256=digest,
                              byte_size=len(data),
                              text_ref=f"sha256:{digest}" if text is not None else None),
        actor_ref=actor_ref, derived_from=())))
    if refusal is not None:
        # The attachment is on the record (hashed), its content is not: the
        # gap is a typed question asking for a readable export, not a parse
        # the engine cannot stand behind.
        payload = QuestionPayload(
            text=("The attached file could not be read here. Please export it as CSV or PDF "
                  "and attach that instead."),
            asks_for=(AsksFor(Kind.EVIDENCE_SOURCE,
                              {"source_kind": (SourceKind.DATASET.value, SourceKind.DOCUMENT.value)}),),
            why=refusal,
            effort=EffortClass.DOCUMENT,
            strategy=FillStrategy.REQUEST_DOCUMENT,
        )
        question = registry.apply(Add(_open_question(
            registry.engagement_id, payload, actor_ref=actor_ref, derived_from=(source.id,))))
        return IngestOutcome(source=source, questions=(question,), failure=refusal)

    registry.register_source_text(source.id, text)
    prompt = render(
        "extract_document.j2",
        document_id=source.id, document_name=name, document_kind=source_kind.value,
        extracted_text=text, registered_measures=_measures_context(registry),
    )
    try:
        extraction, response = structured_call(provider, ModelCall(
            purpose="extract_document", messages=({"role": "user", "content": prompt},),
            schema=DocumentExtraction, engagement_id=registry.engagement_id))
    except StructuredFailure as exc:
        return IngestOutcome(source=source, failure=str(exc))

    record_class = _proposed_record_class(extraction.record_class)
    if record_class is not RecordClass.UNKNOWN and source.payload.record_class is not record_class:
        # The proposal lands on the source row; confirmation stays the
        # client's: extraction never decides what a document IS, because that
        # ranking decides conflicts (design 5.4).
        proposed_payload = replace(source.payload, record_class=record_class,
                                   record_class_confirmed_by_client=False)
        source = registry.apply(Supersede(source.id, replace(
            source, payload=proposed_payload,
            provenance=Provenance(actor=Actor.PARTNER, actor_ref=actor_ref,
                                  derived_from=source.provenance.derived_from,
                                  model_call_id=response.call_id))))

    created: list[Entity] = []
    refused: list[str] = []
    batch: dict[str, str] = {}
    for f in extraction.facts:
        if not (f.quote or f.statement):
            continue  # no quote, no fact
        verified = verify_quote(f.quote, text)
        basis = FactBasis.DOCUMENT_VERIFIED if verified else FactBasis.DOCUMENT_EXTRACTED
        quantity = _quantity_of(f.quote, f.statement, f.quantity, as_of=f.as_of,
                                definition=f.definition)
        family = quantity.unit_family if quantity is not None else None
        try:
            measure_id, measure_row = _resolve_measure(
                registry, f.measure_id, f.measure_name, family, batch, actor_ref=actor_ref,
                derived_from=(source.id,), locator=f.quote or None, model_call_id=response.call_id)
        except RegistryError as exc:
            refused.append(str(exc))
            continue
        if measure_row is not None:
            created.append(measure_row)
        payload = FactPayload(statement=(f.statement or f.quote).strip(), basis=basis,
                              measure_id=measure_id, quantity=quantity, record_class=record_class)
        entity = _proposed(registry.engagement_id, Kind.FACT, payload, actor_ref=actor_ref,
                           derived_from=(source.id,), locator=f.quote or None,
                           model_call_id=response.call_id)
        try:
            created.append(registry.apply(Add(entity)))
        except RegistryError as exc:
            refused.append(str(exc))
    questions = _provenance_questions(registry, actor_ref=actor_ref)
    return IngestOutcome(source=source, created=tuple(created), questions=tuple(questions),
                         refused=tuple(refused))
