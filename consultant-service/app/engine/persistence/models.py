"""The engine's seven tables, on app.database.Base (design 16.1).

They ride the exact machinery the r30 tables ride: `init_db` creates them
with create_all (app/database.py:49) and forward-migrates added columns with
`_ensure_columns` (:56), and structured values live as JSON in Text columns
the way app/models.py stores every pipeline artifact. Nothing here touches
the r30 tables: the `requests` table gains no column, no foreign key points
at it, and importing this module only registers new tables on Base.

The one law this module carries in its schema: `engagement_entities` is the
append-only row history of a registry. UNIQUE(engagement_id, entity_id,
version) makes "a new version is a new row" a database fact — a writer that
tried to reuse a version could only UPDATE, and the store never issues one —
and the (engagement_id, entity_id) index is what makes lineage reads
(every version of one entity) cheap enough to serve on every GET.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Engagement(Base):
    """One engagement: the mutable header row. Everything the engagement
    KNOWS lives in engagement_entities; this row holds only address,
    ownership, lifecycle and progress — the fields _shared.emit mutates on
    Request, mirrored here so emit_engine can reuse the same shape."""

    __tablename__ = "engagements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The engine-side engagement id ("E-..."): every Entity.engagement_id and
    # every child row's engagement_id column holds this string, and URLs use
    # it, so a numeric database id never leaks into provenance.
    public_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    owner_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)

    phase: Mapped[str | None] = mapped_column(String(50), nullable=True)
    central_decision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    charter_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # registry.content_hash() at last save: clock-blind (MF3.7), so two saves
    # of identical knowledge agree whatever the wall clock said.
    registry_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Lifecycle: working | idle | failed | released.
    status: Mapped[str] = mapped_column(String(50), default="idle")
    is_working: Mapped[bool] = mapped_column(Boolean, default=False)
    is_failed: Mapped[bool] = mapped_column(Boolean, default=False)
    stage: Mapped[str] = mapped_column(String(50), default="queued")
    stage_label: Mapped[str] = mapped_column(String(200), default="Queued")
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    progress_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Human review gate, same vocabulary as Request.review_status.
    review_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # r30 Request ids the legacy adapter ran for this engagement, as a JSON
    # list. A JSON column, not a foreign key: the frozen `requests` table
    # must not acquire a relationship it never had.
    legacy_request_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EngagementEntity(Base):
    """One version of one entity — the registry's append-only history.

    The store only ever INSERTs here: a SetStatus, a Supersede, anything
    that moves an entity, lands as a fresh (entity_id, version) row and the
    old row keeps saying what it always said. That is what makes lineage a
    query instead of a reconstruction, and it is why the unique constraint
    below exists: an UPDATE-shaped writer would need to reuse a version.
    """

    __tablename__ = "engagement_entities"
    __table_args__ = (
        UniqueConstraint("engagement_id", "entity_id", "version", name="uq_engagement_entity_version"),
        Index("ix_engagement_entities_entity", "engagement_id", "entity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    engagement_id: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)

    # Scalar envelope fields, denormalised for filtering; the authoritative
    # serialisation is the *_json columns through Entity.to_json/from_json.
    kind: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50))
    info_type: Mapped[str] = mapped_column(String(50))
    authority: Mapped[str] = mapped_column(String(50))
    relation: Mapped[str] = mapped_column(String(50))

    payload_json: Mapped[str] = mapped_column(Text)
    provenance_json: Mapped[str] = mapped_column(Text)
    confidence_json: Mapped[str] = mapped_column(Text)
    relevance_json: Mapped[str] = mapped_column(Text)

    supersedes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    labels_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Entity.content_hash() of this row: recorded at write time so a later
    # reader can prove a stored row still decodes to what was written.
    entity_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EngagementTurn(Base):
    """One conversation turn, verbatim. The registry's client-stated facts
    cite turns (I2 checks the statement against this text), so the turn is
    stored exactly as received, never normalised."""

    __tablename__ = "engagement_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    engagement_id: Mapped[str] = mapped_column(String(64), index=True)
    n: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20))                  # client | partner
    text: Mapped[str] = mapped_column(Text)
    # EVIDENCE_SOURCE entity id minted for a client turn, when one was.
    source_entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attachments_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EngagementDocument(Base):
    """One uploaded document: the original bytes live on disk under
    uploads/engagements/<id>/ (gitignored — the repo is public and client
    payloads never land in it); the row holds the sha256 that document-
    verified facts are checked against, and the extracted text."""

    __tablename__ = "engagement_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    engagement_id: Mapped[str] = mapped_column(String(64), index=True)
    source_entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    stored_path: Mapped[str] = mapped_column(String(500))
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EngagementModelCall(Base):
    """The model-call ledger, one row per call, success or failure — the
    engine-side twin of AiUsageEvent (which llm.py still writes on its own,
    so the cost ledger never depends on this table existing). call_id is the
    primary key llm.py mints (prompt_hash[:16] + "-" + n) and the string
    Provenance.model_call_id points at."""

    __tablename__ = "engagement_model_calls"

    call_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    engagement_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    schema_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    response_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EngagementArtifact(Base):
    """One rendered file of one work product: its sha256, the registry hash
    it was rendered FROM (so staleness is a comparison, not a guess), and
    the presentation findings recorded against exactly this artifact."""

    __tablename__ = "engagement_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    engagement_id: Mapped[str] = mapped_column(String(64), index=True)
    work_product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fmt: Mapped[str | None] = mapped_column(String(20), nullable=True)   # pdf | pptx | md | csv
    path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64))
    registry_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    presentation_findings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EngagementRelease(Base):
    """One release revision: the full release record as JSON, chained by
    parent_revision so a revision's lineage is explicit (design 12.4)."""

    __tablename__ = "engagement_releases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    engagement_id: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    parent_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    record_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="final")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


ENGINE_TABLES: tuple[str, ...] = (
    "engagements", "engagement_entities", "engagement_turns", "engagement_documents",
    "engagement_model_calls", "engagement_artifacts", "engagement_releases",
)
