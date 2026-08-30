"""C20-persistence: the seven tables and the append-only RegistryStore.

Laws pinned here, each mutation-proof:

* save/load round trip preserves every entity's content_hash for a registry
  holding all 41 kinds (the serialisation IS the registry, or lineage lies).
* A SetStatus lands as a NEW version row; the stored history is never
  UPDATEd (mutation: update-in-place on status change).
* Decimal survives the round trip exactly, as {"$decimal": string}
  (mutation: encode Decimal as float).
* create_all on a fresh database creates all seven engine tables and leaves
  the r30 tables exactly as app/models.py declares them.
* _ensure_columns forward-migrates a column added to an engine table.
"""
from __future__ import annotations

import hashlib
import os
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.engine import types as T
from app.engine.persistence import ENGINE_TABLES, RegistryStore, emit_engine
from app.engine.persistence.models import (
    Engagement,
    EngagementEntity,
    EngagementModelCall,
    EngagementTurn,
)

from tests.engine.conftest import FIXED_CLOCK, sample_entity, sample_payload


@pytest.fixture
def db_env(tmp_path, monkeypatch):
    """A fresh sqlite database wired into app.database's module globals, so
    init_db() and _ensure_columns() run against a file this test owns and
    the shared session-wide test database is never mutated."""
    import app.database as database

    eng = create_engine("sqlite:///" + str(tmp_path / "engine-test.db"))
    Session = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    monkeypatch.setattr(database, "engine", eng)
    monkeypatch.setattr(database, "SessionLocal", Session)
    database.init_db()
    return database, eng, Session


@pytest.fixture
def store(db_env):
    _, _, Session = db_env
    return RegistryStore(session_factory=Session)


def _all_kinds_registry(engagement_id: str = "E-1") -> "T.Any":
    """A registry holding one entity of every kind, rebuilt through
    from_rows (derivation is checked; transition laws were the writer's
    problem) so this test pins serialisation, not admission."""
    from app.engine.registry import EngagementRegistry

    rows = [sample_entity(k, recorded_at=FIXED_CLOCK, engagement_id=engagement_id) for k in T.Kind]
    return EngagementRegistry.from_rows(engagement_id, rows, clock=lambda: FIXED_CLOCK)


def _registry_with_client_fact(engagement_id: str = "E-1"):
    """A registry built through apply(): the cited turn first, then the
    client-stated fact whose statement is verbatim in it."""
    from app.engine.registry import EngagementRegistry

    reg = EngagementRegistry(engagement_id, clock=lambda: FIXED_CLOCK)
    reg.apply(T.Add(sample_entity(T.Kind.EVIDENCE_SOURCE, engagement_id=engagement_id)))
    reg.apply(T.Add(sample_entity(T.Kind.FACT, engagement_id=engagement_id)))
    return reg


# ---------------------------------------------------------------------------
# Round trip
# ---------------------------------------------------------------------------

def test_round_trip_preserves_content_hash_for_every_kind(store):
    reg = _all_kinds_registry()
    before = {e.id: e.content_hash() for e in reg.rows()}
    inserted = store.save(reg)
    assert inserted == len(list(T.Kind))

    loaded = store.load("E-1", clock=lambda: FIXED_CLOCK)
    after = {e.id: e.content_hash() for e in loaded.rows()}
    assert after == before
    # The registry-level hash (sorted, clock-blind) agrees too: what the
    # store returns IS what the engagement knew.
    assert loaded.content_hash() == reg.content_hash()
    # And the payloads decode to the same dataclasses, not lookalike dicts.
    for e in loaded.rows():
        assert type(e.payload) is T.PAYLOAD_TYPES[e.kind]


def test_decimal_survives_round_trip_exactly(store):
    # 25 significant digits and a trailing zero: both die in a float.
    exact = Decimal("1234567890.1234567890123456789")
    trailing = Decimal("1250.50")
    qty = T.Quantity(exact, "EUR", T.UnitFamily.MONEY,
                     T.Dimensions(currency="EUR", period="FY25", period_basis="year",
                                  scope=None, as_of="2025-12-31", definition=None))
    fact = sample_entity(T.Kind.FACT, sample_payload(T.Kind.FACT, quantity=qty),
                         recorded_at=FIXED_CLOCK, engagement_id="E-D")
    cost = sample_entity(T.Kind.COST, recorded_at=FIXED_CLOCK, engagement_id="E-D")  # holds Decimal("900")
    obj = sample_entity(T.Kind.OBJECTIVE, sample_payload(
        T.Kind.OBJECTIVE, target=T.Quantity(trailing, "EUR", T.UnitFamily.MONEY, T.Dimensions())),
        recorded_at=FIXED_CLOCK, engagement_id="E-D")

    from app.engine.registry import EngagementRegistry
    reg = EngagementRegistry.from_rows("E-D", [fact, cost, obj], clock=lambda: FIXED_CLOCK)
    store.save(reg)
    loaded = store.load("E-D", clock=lambda: FIXED_CLOCK)

    got = loaded.get("FCT-1").payload.quantity.value
    assert isinstance(got, Decimal)
    # == alone would call 1250.5 equal to 1250.50; the string is the pin.
    assert str(got) == str(exact)
    assert str(loaded.get("OBJ-1").payload.target.value) == "1250.50"
    # The stored JSON itself carries the typed form, never a bare float.
    session = store._session()
    try:
        row = (session.query(EngagementEntity)
               .filter_by(engagement_id="E-D", entity_id="FCT-1").one())
        assert '{"$decimal": "1234567890.1234567890123456789"}' in row.payload_json
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Append-only: a status change is a new row
# ---------------------------------------------------------------------------

def test_set_status_inserts_new_version_row_and_never_updates(store):
    reg = _registry_with_client_fact()
    store.save(reg)

    reg.apply(T.SetStatus("FCT-1", T.Status.CONFIRMED,
                          by=T.Provenance(actor=T.Actor.CLIENT, actor_ref="client:turn:2")))
    assert store.save(reg) == 1  # exactly the new version row, nothing rewritten

    session = store._session()
    try:
        rows = (session.query(EngagementEntity)
                .filter_by(engagement_id="E-1", entity_id="FCT-1")
                .order_by(EngagementEntity.version).all())
        assert [r.version for r in rows] == [1, 2]
        # The old row still says what it always said: an UPDATE-shaped save
        # would have rewritten version 1's status and history would lie.
        assert rows[0].status == T.Status.PROPOSED.value
        assert rows[0].confirmed_by is None
        assert rows[1].status == T.Status.CONFIRMED.value
        assert rows[1].confirmed_by == "client:turn:2"
        assert rows[1].supersedes == 1
    finally:
        session.close()

    # Idempotence: saving the same registry again writes nothing.
    assert store.save(reg) == 0
    # And the reloaded registry replays the full lineage.
    loaded = store.load("E-1", clock=lambda: FIXED_CLOCK)
    assert [r.version for r in loaded.lineage("FCT-1")] == [1, 2]
    assert loaded.get("FCT-1").status == T.Status.CONFIRMED


def test_duplicate_version_row_is_refused_by_the_schema(store):
    """UNIQUE(engagement_id, entity_id, version) is the database-level half
    of append-only: reusing a version cannot be an INSERT."""
    reg = _registry_with_client_fact("E-U")
    store.save(reg)
    session = store._session()
    try:
        first = (session.query(EngagementEntity)
                 .filter_by(engagement_id="E-U", entity_id="FCT-1", version=1).one())
        session.add(EngagementEntity(
            engagement_id="E-U", entity_id="FCT-1", version=1,
            kind=first.kind, status="confirmed", info_type=first.info_type,
            authority=first.authority, relation=first.relation,
            payload_json=first.payload_json, provenance_json=first.provenance_json,
            confidence_json=first.confidence_json, relevance_json=first.relevance_json,
            entity_hash=first.entity_hash))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    finally:
        session.close()


def test_load_refuses_a_row_that_no_longer_hashes(store):
    """A stored row that decodes to a different content hash is a corrupted
    or hand-edited row; loading it silently would launder the edit into
    lineage."""
    reg = _registry_with_client_fact("E-H")
    store.save(reg)
    session = store._session()
    try:
        row = (session.query(EngagementEntity)
               .filter_by(engagement_id="E-H", entity_id="FCT-1").one())
        row.payload_json = row.payload_json.replace("we have 40 people", "we have 41 people")
        session.commit()
    finally:
        session.close()
    with pytest.raises(ValueError, match="no longer holds"):
        store.load("E-H", clock=lambda: FIXED_CLOCK)


# ---------------------------------------------------------------------------
# Schema: seven tables, r30 untouched, forward migration
# ---------------------------------------------------------------------------

def test_create_all_creates_seven_engine_tables_and_r30_unchanged(db_env):
    _, eng, _ = db_env
    names = set(inspect(eng).get_table_names())
    assert set(ENGINE_TABLES) <= names
    assert len(ENGINE_TABLES) == 7
    # The r30 tables ride along untouched: present, and `requests` holds
    # exactly the columns app/models.py declares -- the engine adds none.
    assert {"requests", "ai_usage_events"} <= names
    from app import models as r30
    declared = {c.name for c in r30.Request.__table__.columns}
    in_db = {c["name"] for c in inspect(eng).get_columns("requests")}
    assert in_db == declared


def test_ensure_columns_adds_a_new_nullable_column_to_an_engine_table(db_env):
    """The forward-migration path: a column added to an engine model after a
    deployment's database was first created must be ADD COLUMNed by
    _ensure_columns, exactly as the r30 tables are migrated."""
    from sqlalchemy import Column, String

    database, eng, _ = db_env
    table = EngagementTurn.__table__
    probe = Column("migration_probe", String(20), nullable=True)
    table.append_column(probe)
    try:
        database._ensure_columns()
        cols = {c["name"] for c in inspect(eng).get_columns("engagement_turns")}
        assert "migration_probe" in cols
    finally:
        # The shared metadata must not keep the probe: other tests (and the
        # real schema) never declared it.
        table._columns.remove(probe)


# ---------------------------------------------------------------------------
# The model-call ledger callback (llm.py's RecordCallback)
# ---------------------------------------------------------------------------

def test_record_model_call_inserts_one_ledger_row(store):
    record = {
        "call_id": "abcd1234abcd1234-1", "engagement_id": "E-1", "purpose": "extract_turn",
        "model": "test/model", "schema_version": 2, "prompt_hash": "p" * 64,
        "response_hash": "r" * 64, "max_tokens": 800, "finish_reason": "stop",
        "prompt_tokens": 100, "completion_tokens": 50, "cost_usd": 0.0021,
        "success": True, "error": None,
        # A newer llm.py may add keys; the ledger keeps counting calls
        # rather than crashing on vocabulary it does not know.
        "future_key": "ignored",
    }
    store.record_model_call(record)
    session = store._session()
    try:
        row = session.get(EngagementModelCall, "abcd1234abcd1234-1")
        assert row is not None
        assert row.purpose == "extract_turn"
        assert row.cost_usd == pytest.approx(0.0021)
        assert row.success is True
    finally:
        session.close()


def test_record_model_call_keeps_failures(store):
    """A failed call is still a call: without the row an outage looks like
    zero spend and zero attempts."""
    store.record_model_call({"call_id": "ffff0000ffff0000-1", "engagement_id": "E-1",
                             "success": False, "error": "upstream 502"})
    session = store._session()
    try:
        row = session.get(EngagementModelCall, "ffff0000ffff0000-1")
        assert row.success is False
        assert row.error == "upstream 502"
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Documents and progress
# ---------------------------------------------------------------------------

def test_store_document_writes_original_and_row(store, tmp_uploads):
    content = b"%PDF-1.4 not really"
    row = store.store_document("E-1", "../weird name?.pdf", content,
                               content_type="application/pdf",
                               extracted_text="hello world", source_entity_id="EVI-9")
    assert row.sha256 == hashlib.sha256(content).hexdigest()
    assert row.size_bytes == len(content)
    # Original bytes land under the engagement's own gitignored directory;
    # the hostile filename cannot walk out of it.
    assert os.path.dirname(row.stored_path) == os.path.join(str(tmp_uploads), "engagements", "E-1")
    assert ".." not in os.path.basename(row.stored_path)
    with open(row.stored_path, "rb") as f:
        assert f.read() == content
    # load() re-registers the extracted text against the source entity id,
    # so document-verified locators stay checkable after a restart.
    loaded = store.load("E-1", clock=lambda: FIXED_CLOCK)
    assert loaded.source_text("EVI-9") == "hello world"


def test_emit_engine_mirrors_shared_emit(store):
    reg = _registry_with_client_fact("E-P")
    store.save(reg)  # creates the header row and stamps registry_hash
    session = store._session()
    try:
        emit_engine(session, "E-P", "analysis", "Running analyses", 40, "round 1")
        row = session.query(Engagement).filter_by(public_id="E-P").one()
        assert (row.stage, row.stage_label, row.progress_pct, row.progress_detail) == \
            ("analysis", "Running analyses", 40, "round 1")
        assert row.registry_hash == reg.content_hash()
        # An unknown engagement is a no-op, never an error: progress
        # reporting must not kill the work it reports on.
        emit_engine(session, "E-NOPE", "x", "y", 1)
    finally:
        session.close()
