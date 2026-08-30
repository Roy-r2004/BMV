"""RegistryStore: the append-only bridge between EngagementRegistry and the
seven tables (design 16.1).

Three laws live here, each with a mutation-proof test:

* save() only ever INSERTs entity rows. A SetStatus, a Supersede, any move
  of any entity is a new (entity_id, version) row; the version that was
  already on disk is never touched again. Lineage is therefore the table
  itself — an UPDATE-shaped save would silently rewrite history and no
  later query could tell.
* Rows serialise through Entity.to_json/from_json exactly. Decimal stays
  {"$decimal": "<string>"}: a float here rounds the client's own numbers
  ("1250.50" becomes 1250.5, and 0.1 becomes whatever IEEE754 says), which
  the exactness principle (spec section 7: client facts remain exact)
  forbids. The stored entity_hash is re-proven on load, so a row that no
  longer decodes to what was written fails loudly, never silently.
* The store never re-runs transition laws on load: an older row is not
  condemned by a law that did not exist when it was recorded. Rebuilding
  goes through EngagementRegistry.from_rows, which checks only derivation.

This module is the ONLY place that turns llm.py's ModelCallRecord dicts into
engagement_model_calls rows (the RecordCallback seam), and the only place
that writes engagement document originals to disk (uploads/engagements/<id>/,
gitignored — the repository is public and client payloads never enter it).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from typing import Any, Callable, Mapping

from app.engine.registry import EngagementRegistry
from app.engine.types import Entity

from app.engine.persistence.models import (
    Engagement,
    EngagementDocument,
    EngagementEntity,
    EngagementModelCall,
)


def _dumps(obj: Any) -> str:
    """One canonical JSON form for every stored fragment: sorted keys so the
    same content is the same bytes, allow_nan=False so a NaN that somehow
    reached a payload fails at write time instead of producing JSON no
    strict parser reads back."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _entity_document(e: Entity) -> dict:
    """The JSON body a row stores, exactly as Entity.to_json defines it.

    Kept as its own seam because it IS the serialisation law: Decimal must
    leave here as {"$decimal": "<string>"} (types._encode), never as a float
    — the round-trip test proves content_hash survives, and a float cannot
    carry "1250.50" or 25 significant digits back out of the database.
    """
    return e.to_json()


class RegistryStore:
    """load/save for one engagement's registry, plus the two side stores
    (documents on disk, the model-call ledger) that hang off it.

    session_factory: zero-arg callable returning a SQLAlchemy Session;
    defaults to app.database.SessionLocal. Every method also accepts an
    explicit db session so request handlers can keep one transaction.
    """

    def __init__(self, session_factory: Callable[[], Any] | None = None):
        self._session_factory = session_factory

    def _session(self):
        if self._session_factory is not None:
            return self._session_factory()
        from app.database import SessionLocal
        return SessionLocal()

    # -- registry ------------------------------------------------------------

    def save(self, registry: EngagementRegistry, db: Any | None = None) -> int:
        """Persist every row of `registry` that is not already on disk.

        Append-only by construction: the set of stored (entity_id, version)
        pairs is read first and only missing pairs are INSERTed, in the
        registry's own write order. Nothing is ever UPDATEd or DELETEd —
        a pair that exists is already immutable history, and the registry
        itself never re-issues a version (UNIQUE would refuse it anyway).
        Returns the number of rows inserted and stamps the engagement row
        with the clock-blind registry hash.
        """
        own = db is None
        session = self._session() if own else db
        try:
            eid = registry.engagement_id
            stored = {
                (entity_id, version)
                for entity_id, version in session.query(
                    EngagementEntity.entity_id, EngagementEntity.version
                ).filter(EngagementEntity.engagement_id == eid)
            }
            inserted = 0
            for e in registry.rows():
                if (e.id, e.version) in stored:
                    continue
                session.add(self._row_for(e))
                stored.add((e.id, e.version))
                inserted += 1
            self._stamp_engagement(session, eid, registry.content_hash())
            session.commit()
            return inserted
        except Exception:
            session.rollback()
            raise
        finally:
            if own:
                session.close()

    def load(self, engagement_id: str, db: Any | None = None,
             clock: Callable[[], str] | None = None) -> EngagementRegistry:
        """Rebuild the registry from its stored row history, in write order.

        Each row is decoded through Entity.from_json and its stored
        entity_hash is re-proven against the decoded row: a mismatch means
        the bytes on disk no longer say what was written (a bad migration,
        a hand edit) and is an error, never a silent repair. Source texts
        are re-registered from EVIDENCE_SOURCE payloads by from_rows's
        fallback and from stored documents' extracted text here.
        """
        own = db is None
        session = self._session() if own else db
        try:
            rows: list[Entity] = []
            for stored in (
                session.query(EngagementEntity)
                .filter(EngagementEntity.engagement_id == engagement_id)
                .order_by(EngagementEntity.id)
            ):
                e = Entity.from_json(self._document_for(stored))
                got = e.content_hash()
                if got != stored.entity_hash:
                    raise ValueError(
                        f"stored row {stored.entity_id} v{stored.version} decodes to "
                        f"{got[:12]}..., was written as {stored.entity_hash[:12]}...: "
                        "the database no longer holds what the registry wrote"
                    )
                rows.append(e)
            source_texts: dict[str, str] = {}
            for doc in (
                session.query(EngagementDocument)
                .filter(EngagementDocument.engagement_id == engagement_id)
                .order_by(EngagementDocument.id)
            ):
                if doc.source_entity_id and doc.extracted_text is not None:
                    source_texts[doc.source_entity_id] = doc.extracted_text
            return EngagementRegistry.from_rows(
                engagement_id, rows, clock=clock, source_texts=source_texts
            )
        finally:
            if own:
                session.close()

    def _row_for(self, e: Entity) -> EngagementEntity:
        d = _entity_document(e)
        return EngagementEntity(
            engagement_id=e.engagement_id,
            entity_id=e.id,
            version=e.version,
            kind=e.kind.value,
            status=e.status.value,
            info_type=e.info_type.value,
            authority=e.authority.value,
            relation=e.relation.value,
            payload_json=_dumps(d["payload"]),
            provenance_json=_dumps(d["provenance"]),
            confidence_json=_dumps(d["confidence"]),
            relevance_json=_dumps(d["relevance"]),
            supersedes=e.supersedes,
            confirmed_by=e.confirmed_by,
            labels_json=_dumps(list(e.labels)) if e.labels else None,
            entity_hash=e.content_hash(),
        )

    @staticmethod
    def _document_for(row: EngagementEntity) -> dict:
        """The Entity.from_json input, reassembled from the row's columns.
        The scalar columns are the same values again — from_json reads the
        dict, so the JSON fragments are the authority and the scalars are
        the filterable copies."""
        return {
            "id": row.entity_id,
            "kind": row.kind,
            "engagement_id": row.engagement_id,
            "payload": json.loads(row.payload_json),
            "provenance": json.loads(row.provenance_json),
            "authority": row.authority,
            "info_type": row.info_type,
            "confidence": json.loads(row.confidence_json),
            "relevance": json.loads(row.relevance_json),
            "relation": row.relation,
            "status": row.status,
            "version": row.version,
            "supersedes": row.supersedes,
            "confirmed_by": row.confirmed_by,
            "labels": json.loads(row.labels_json) if row.labels_json else [],
        }

    @staticmethod
    def _stamp_engagement(session: Any, engagement_id: str, registry_hash: str) -> None:
        """The engagements header row is the one mutable row the store
        touches: created if missing so a registry can be saved before the
        API has dressed the engagement, and stamped with the current
        registry hash so staleness of any artifact is a comparison."""
        row = session.query(Engagement).filter(Engagement.public_id == engagement_id).first()
        if row is None:
            row = Engagement(public_id=engagement_id)
            session.add(row)
        row.registry_hash = registry_hash
        row.updated_at = datetime.utcnow()

    # -- model-call ledger (the RecordCallback llm.py takes) -----------------

    def record_model_call(self, record: Mapping[str, Any]) -> None:
        """The persistence half of the model-call ledger: one INSERTed row
        per ModelCallRecord dict, success or failure alike. Unknown keys
        from a newer llm.py are dropped, not fatal — the ledger must keep
        counting calls across component versions."""
        columns = {c.name for c in EngagementModelCall.__table__.columns}
        payload = {k: v for k, v in record.items() if k in columns}
        session = self._session()
        try:
            session.add(EngagementModelCall(**payload))
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # -- document originals --------------------------------------------------

    def store_document(self, engagement_id: str, filename: str, content: bytes, *,
                       content_type: str | None = None, extracted_text: str | None = None,
                       source_entity_id: str | None = None, db: Any | None = None) -> EngagementDocument:
        """Write the original bytes under uploads/engagements/<id>/ and the
        row that document-verified facts hash against. The stored name is
        sha-prefixed: two uploads named identically never overwrite each
        other, and a hostile filename cannot walk out of the directory."""
        own = db is None
        session = self._session() if own else db
        try:
            sha = hashlib.sha256(content).hexdigest()
            directory = documents_dir(engagement_id)
            os.makedirs(directory, exist_ok=True)
            safe = _safe_filename(filename)
            path = os.path.join(directory, f"{sha[:12]}-{safe}")
            with open(path, "wb") as f:
                f.write(content)
            row = EngagementDocument(
                engagement_id=engagement_id, source_entity_id=source_entity_id,
                filename=safe, content_type=content_type, sha256=sha,
                size_bytes=len(content), stored_path=path, extracted_text=extracted_text,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row
        except Exception:
            session.rollback()
            raise
        finally:
            if own:
                session.close()


def documents_dir(engagement_id: str) -> str:
    """uploads/engagements/<id>/ under Settings.UPLOADS_DIR (tests point the
    setting at a throwaway root). The id component is sanitised too: an
    engagement id is engine-minted, but defence costs one call."""
    from app.config import settings
    return os.path.join(settings.UPLOADS_DIR, "engagements", _safe_filename(engagement_id))


def _safe_filename(name: str) -> str:
    """basename, then a conservative character set: enough for real client
    filenames, nothing a path parser interprets."""
    base = os.path.basename(name.replace("\\", "/")) or "file"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:120] or "file"


def record_model_call(record: Mapping[str, Any]) -> None:
    """Module-level RecordCallback for the default wiring:
    OpenRouterProvider(record_call=store.record_model_call)."""
    RegistryStore().record_model_call(record)


def emit_engine(db: Any, engagement_id: str, stage: str, label: str, pct: int,
                detail: str | None = None) -> None:
    """Progress on the engagement header row — the same contract as
    _shared.emit on Request (app/pipeline/_shared.py:73): silently a no-op
    for an unknown engagement, because progress reporting must never be the
    thing that kills the work it reports on."""
    row = db.query(Engagement).filter(Engagement.public_id == engagement_id).first()
    if row is None:
        return
    row.stage = stage
    row.stage_label = label
    row.progress_pct = pct
    row.progress_detail = detail
    row.updated_at = datetime.utcnow()
    db.commit()
