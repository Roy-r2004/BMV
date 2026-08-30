"""C6-ingest: app/engine/partner/ingest.py.

Pins (work_breakdown C6-ingest): an extracted fact is PROPOSED with basis
document_extracted; a quote not verbatim in the document stays
document_extracted; a verbatim quote becomes document_verified with the
locator; a client fact whose statement is not a substring of the turn is
refused by the registry; sha256 recorded; two equal-rank documents on one
measure open a provenance question; a fact attaches to an existing MEASURE id
when the model chose one; nothing ingested is CONFIRMED; a 'don't know'
answer sets unknown=True and the question is never re-asked.

Named mutations: write CONFIRMED on extraction; promote on a similarity
match; confirm record_class from the model's proposal.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest

from app.engine import types as T
from app.engine.partner import ingest as I

MESSAGE = "We take 120 orders a week and a third arrive late."
DOC_TEXT = "weekly orders: 120\nRevenue was EUR 250000 in FY25\n"


# --- scenario helpers -------------------------------------------------------

def _turn_json(*candidates) -> str:
    return json.dumps({"candidates": list(candidates)})


def _doc_json(record_class: str = "management_report", facts=()) -> str:
    return json.dumps({"record_class": record_class, "record_class_reason": "the header",
                       "facts": list(facts)})


def _fact_candidate(quote: str, **extra) -> dict:
    return {"kind": "fact", "quote": quote, "text": quote, **extra}


def _add_measure(reg, name: str = "orders per week",
                 family: T.UnitFamily = T.UnitFamily.CAPACITY) -> T.Entity:
    return reg.apply(T.Add(T.make_entity(
        kind=T.Kind.MEASURE, engagement_id=reg.engagement_id,
        payload=T.MeasurePayload(name=name, unit_family=family),
        provenance=T.Provenance(T.Actor.PARTNER, "partner:setup"),
        confidence=T.Confidence(None), relevance=T.Relevance(None, 0.0),
        relation=T.RelationToCentralDecision.UNKNOWN, status=T.Status.PROPOSED)))


def _add_open_question(reg, text: str = "How many orders per week?") -> T.Entity:
    return reg.apply(T.Add(T.make_entity(
        kind=T.Kind.QUESTION, engagement_id=reg.engagement_id,
        payload=T.QuestionPayload(text=text),
        provenance=T.Provenance(T.Actor.PARTNER, "partner:turn:0"),
        confidence=T.Confidence(None), relevance=T.Relevance(None, 0.0),
        relation=T.RelationToCentralDecision.UNKNOWN, status=T.Status.OPEN)))


def _ingest_doc(reg, fake, text: bytes = DOC_TEXT.encode(), name: str = "orders.txt", turn: int = 1):
    return I.ingest_document(reg, fake, name=name, data=text, turn_number=turn)


# --- turn ingestion ---------------------------------------------------------

def test_turn_row_carries_the_message_text(registry, fake_provider):
    reg = registry()
    fake = fake_provider(script={"extract_turn": [_turn_json()]})
    outcome = I.ingest_turn(reg, fake, MESSAGE, turn_number=1)
    src = reg.get(outcome.source.id)
    assert src.kind is T.Kind.EVIDENCE_SOURCE
    assert src.payload.source_kind is T.SourceKind.CONVERSATION_TURN
    assert src.payload.text == MESSAGE
    assert reg.source_text(src.id) == MESSAGE


def test_turn_candidates_are_proposed_and_none_refused(registry, fake_provider):
    # Mutation 'write CONFIRMED on extraction': a candidate written CONFIRMED
    # is either refused by I1 (refused non-empty) or lands CONFIRMED (status
    # check fails) - both assertions below break.
    reg = registry()
    fake = fake_provider(script={"extract_turn": [_turn_json(
        _fact_candidate("We take 120 orders a week"),
        {"kind": "objective", "quote": "a third arrive late", "text": "a third arrive late"},
    )]})
    outcome = I.ingest_turn(reg, fake, MESSAGE, turn_number=1)
    assert outcome.refused == ()
    assert outcome.failure is None
    assert len(outcome.created) == 2
    for row in reg.rows():
        assert row.status not in (T.Status.CONFIRMED, T.Status.APPROVED)
    fact = next(e for e in outcome.created if e.kind is T.Kind.FACT)
    assert fact.status is T.Status.PROPOSED
    assert fact.payload.basis is T.FactBasis.CLIENT_STATED
    assert fact.provenance.derived_from == (outcome.source.id,)
    assert fact.provenance.source_locator == "We take 120 orders a week"
    assert fact.payload.quantity is not None
    assert fact.payload.quantity.value == Decimal("120")


def test_client_fact_restated_is_refused_by_registry(registry, fake_provider):
    # The law lives in the registry (I2), not in a pre-filter here: the
    # refusal message names the invariant and no FACT row exists.
    reg = registry()
    fake = fake_provider(script={"extract_turn": [_turn_json(
        _fact_candidate("Order intake stands at one hundred and twenty weekly"),
    )]})
    outcome = I.ingest_turn(reg, fake, MESSAGE, turn_number=1)
    assert len(outcome.refused) == 1
    assert outcome.refused[0].startswith("I2")
    assert reg.query(T.Kind.FACT) == []


def test_decision_on_turn_one_is_the_stated_request(registry, fake_provider):
    reg = registry()
    fake = fake_provider(script={"extract_turn": [_turn_json(
        {"kind": "decision", "quote": MESSAGE, "text": MESSAGE, "role": "central"},
    )]})
    outcome = I.ingest_turn(reg, fake, MESSAGE, turn_number=1)
    decision = next(e for e in outcome.created if e.kind is T.Kind.DECISION)
    # extraction never seats a central decision, whatever the model claimed
    assert decision.payload.role is T.DecisionRole.STATED_REQUEST


def test_fact_attaches_to_registered_measure_id(registry, fake_provider):
    reg = registry()
    measure = _add_measure(reg)
    fake = fake_provider(script={"extract_turn": [_turn_json(
        _fact_candidate("We take 120 orders a week", measure_id=measure.id),
    )]})
    outcome = I.ingest_turn(reg, fake, MESSAGE, turn_number=1)
    fact = next(e for e in outcome.created if e.kind is T.Kind.FACT)
    assert fact.payload.measure_id == measure.id


def test_unregistered_measure_id_is_not_guessed_into_a_match(registry, fake_provider):
    reg = registry()
    fake = fake_provider(script={"extract_turn": [_turn_json(
        _fact_candidate("We take 120 orders a week", measure_id="MEA-99"),
    )]})
    outcome = I.ingest_turn(reg, fake, MESSAGE, turn_number=1)
    fact = next(e for e in outcome.created if e.kind is T.Kind.FACT)
    assert fact.payload.measure_id is None


def test_new_measure_is_proposed_and_fact_attached(registry, fake_provider):
    reg = registry()
    fake = fake_provider(script={"extract_turn": [_turn_json(
        _fact_candidate("We take 120 orders a week", measure_name="orders per week"),
    )]})
    outcome = I.ingest_turn(reg, fake, MESSAGE, turn_number=1)
    measures = reg.query(T.Kind.MEASURE)
    assert len(measures) == 1
    assert measures[0].status is T.Status.PROPOSED
    assert measures[0].payload.name == "orders per week"
    fact = next(e for e in outcome.created if e.kind is T.Kind.FACT)
    assert fact.payload.measure_id == measures[0].id


# --- answers ----------------------------------------------------------------

def test_answer_is_recorded_in_answer_entity_ids(registry, fake_provider):
    reg = registry()
    q = _add_open_question(reg)
    fake = fake_provider(script={"extract_turn": [_turn_json(
        _fact_candidate("We take 120 orders a week", answers=[q.id]),
    )]})
    outcome = I.ingest_turn(reg, fake, MESSAGE, turn_number=2)
    fact = next(e for e in outcome.created if e.kind is T.Kind.FACT)
    assert outcome.answered == (q.id,)
    assert fact.id in reg.get(q.id).payload.answer_entity_ids


def test_dont_know_sets_unknown_and_is_never_reasked(registry, fake_provider):
    reg = registry()
    q = _add_open_question(reg)
    fake = fake_provider(script={"extract_turn": [
        _turn_json({"kind": "fact", "quote": "We do not know", "answers": [q.id], "unknown": True}),
        _turn_json(),
    ]})
    outcome = I.ingest_turn(reg, fake, "We do not know our order count.", turn_number=2)
    assert outcome.answered == (q.id,)
    row = reg.get(q.id)
    assert row.payload.unknown is True
    assert row.status is T.Status.RESOLVED
    assert I.open_questions(reg) == []
    # the next turn's prompt no longer offers the question
    I.ingest_turn(reg, fake, "Anything else?", turn_number=3)
    prompt = fake.calls[-1].messages[0]["content"]
    assert q.id not in prompt


# --- document ingestion -----------------------------------------------------

def test_document_row_carries_sha256_size_and_text_ref(registry, fake_provider):
    reg = registry()
    data = DOC_TEXT.encode()
    fake = fake_provider(script={"extract_document": [_doc_json()]})
    outcome = _ingest_doc(reg, fake, data)
    src = reg.get(outcome.source.id)
    digest = hashlib.sha256(data).hexdigest()
    assert src.payload.sha256 == digest
    assert src.payload.byte_size == len(data)
    assert src.payload.text_ref == f"sha256:{digest}"
    assert src.payload.text is None                      # documents use text_ref, not text
    assert reg.source_text(src.id) == DOC_TEXT


def test_verbatim_quote_promotes_to_document_verified_with_locator(registry, fake_provider):
    reg = registry()
    fake = fake_provider(script={"extract_document": [_doc_json(facts=[
        {"quote": "weekly orders: 120", "statement": "weekly orders: 120"},
    ])]})
    outcome = _ingest_doc(reg, fake)
    fact = next(e for e in outcome.created if e.kind is T.Kind.FACT)
    assert fact.status is T.Status.PROPOSED
    assert fact.payload.basis is T.FactBasis.DOCUMENT_VERIFIED
    assert fact.provenance.source_locator == "weekly orders: 120"
    assert outcome.refused == ()


def test_non_verbatim_quote_stays_document_extracted(registry, fake_provider):
    # Mutation 'promote on a similarity match': a case-folded quote would be
    # promoted, then refused by I2 (the locator is not verbatim), and the
    # extracted fact below would not exist.
    reg = registry()
    fake = fake_provider(script={"extract_document": [_doc_json(facts=[
        {"quote": "WEEKLY ORDERS: 120", "statement": "weekly orders 120"},
    ])]})
    outcome = _ingest_doc(reg, fake)
    fact = next(e for e in outcome.created if e.kind is T.Kind.FACT)
    assert fact.payload.basis is T.FactBasis.DOCUMENT_EXTRACTED
    assert fact.status is T.Status.PROPOSED
    assert outcome.refused == ()


def test_verify_quote_is_verbatim_only():
    assert I.verify_quote("weekly orders: 120", DOC_TEXT) is True
    assert I.verify_quote("WEEKLY ORDERS: 120", DOC_TEXT) is False
    assert I.verify_quote("weekly  orders: 120", DOC_TEXT) is False
    assert I.verify_quote("", DOC_TEXT) is False


def test_record_class_stays_a_proposal(registry, fake_provider):
    # Mutation 'confirm record_class from the model's proposal': the flag
    # below flips to True and this pin fails. `is False`, never falsily.
    reg = registry()
    fake = fake_provider(script={"extract_document": [_doc_json("management_report")]})
    outcome = _ingest_doc(reg, fake)
    src = reg.get(outcome.source.id)
    assert src.payload.record_class is T.RecordClass.MANAGEMENT_REPORT
    assert src.payload.record_class_confirmed_by_client is False


def test_equal_rank_documents_on_one_measure_open_one_provenance_question(registry, fake_provider):
    reg = registry()
    measure = _add_measure(reg)
    fact = [{"quote": "weekly orders: 120", "statement": "weekly orders: 120",
             "measure_id": measure.id}]
    fake = fake_provider(script={"extract_document": [
        _doc_json("management_report", fact), _doc_json("management_report", fact),
        _doc_json("management_report", fact),
    ]})
    first = _ingest_doc(reg, fake, name="a.txt")
    assert first.questions == ()                          # one document is no tie
    second = _ingest_doc(reg, fake, name="b.txt")
    assert len(second.questions) == 1
    q = second.questions[0]
    assert q.status is T.Status.OPEN
    assert q.payload.effort is T.EffortClass.OFFHAND
    assert q.payload.strategy is T.FillStrategy.ASK_CLIENT
    assert measure.id in q.provenance.derived_from
    assert first.source.id in q.provenance.derived_from
    assert second.source.id in q.provenance.derived_from
    third = _ingest_doc(reg, fake, name="c.txt")
    assert third.questions == ()                          # asked at most once per measure
    assert len(reg.query(T.Kind.QUESTION)) == 1


def test_nothing_ingested_is_confirmed(registry, fake_provider):
    reg = registry()
    fake = fake_provider(script={
        "extract_turn": [_turn_json(_fact_candidate("We take 120 orders a week",
                                                    measure_name="orders per week"))],
        "extract_document": [_doc_json("management_report", [
            {"quote": "weekly orders: 120", "statement": "weekly orders: 120"}])],
    })
    t = I.ingest_turn(reg, fake, MESSAGE, turn_number=1)
    d = _ingest_doc(reg, fake)
    assert t.refused == () and d.refused == ()
    for row in reg.rows():
        assert row.status not in (T.Status.CONFIRMED, T.Status.APPROVED)


# --- extraction formats -----------------------------------------------------

def test_csv_text_is_deterministic_lines(registry, fake_provider):
    reg = registry()
    data = b"week,orders\r\n1,118\r\n2,122\r\n"
    fake = fake_provider(script={"extract_document": [_doc_json(facts=[
        {"quote": "1,118", "statement": "week 1 orders 118"}])]})
    outcome = _ingest_doc(reg, fake, text=data, name="ledger.csv")
    src = reg.get(outcome.source.id)
    assert src.payload.source_kind is T.SourceKind.DATASET
    assert reg.source_text(src.id) == "week,orders\n1,118\n2,122"
    fact = next(e for e in outcome.created if e.kind is T.Kind.FACT)
    assert fact.payload.basis is T.FactBasis.DOCUMENT_VERIFIED


def test_pdf_text_is_extracted_with_pymupdf(registry, fake_provider):
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Revenue was EUR 250000 in FY25")
    data = doc.tobytes()
    doc.close()
    text, kind, refusal = I.extract_text("report.pdf", data)
    assert refusal is None
    assert kind is T.SourceKind.DOCUMENT
    assert "Revenue was EUR 250000 in FY25" in text


def test_xlsx_is_refused_with_a_question_and_no_model_call(registry, fake_provider):
    reg = registry()
    data = b"PK\x03\x04 not a real workbook"
    fake = fake_provider()
    outcome = _ingest_doc(reg, fake, text=data, name="book.xlsx")
    src = reg.get(outcome.source.id)
    assert src.payload.sha256 == hashlib.sha256(data).hexdigest()
    assert src.payload.text is None and src.payload.text_ref is None
    assert reg.source_text(src.id) is None
    assert fake.calls == []                               # nothing to read, nothing asked of a model
    assert len(outcome.questions) == 1
    q = outcome.questions[0]
    assert q.payload.strategy is T.FillStrategy.REQUEST_DOCUMENT
    assert q.payload.effort is T.EffortClass.DOCUMENT
    assert src.id in q.provenance.derived_from
    assert outcome.created == ()


def test_model_failure_keeps_the_turn_row_and_reports(registry, fake_provider):
    reg = registry()
    fake = fake_provider(script={"extract_turn": [RuntimeError("outage")]})
    outcome = I.ingest_turn(reg, fake, MESSAGE, turn_number=1)
    assert outcome.failure is not None
    assert outcome.created == ()
    assert reg.get(outcome.source.id) is not None
