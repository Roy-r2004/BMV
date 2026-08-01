"""Admin ops models — runtime settings + AI usage / cost events + alerts."""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from app.infrastructure.db.base import Base


class AdminSettings(Base):
    """Singleton row (id=1) for runtime ops toggles."""

    __tablename__ = "admin_settings"

    id = Column(Integer, primary_key=True, default=1)
    ai_enabled = Column(Boolean, nullable=False, default=True)
    site_chat_enabled = Column(Boolean, nullable=False, default=True)
    daily_budget_usd = Column(Float, nullable=True)  # None = no cap
    request_budget_usd = Column(Float, nullable=True)  # hard stop per request
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AiUsageEvent(Base):
    """One row per AI API call (success or failure).

    `success` and `usable` are deliberately different questions.

    * `success` is the transport verdict: the provider answered and the envelope
      parsed. It is what the cost ledger and the budget guard read.
    * `usable` is the pipeline verdict: something downstream could act on the
      output. A 200 carrying JSON no extractor can read is `success = true,
      usable = false` — request 67 recorded two such fix-agent calls as plain
      successes, and the ~90 s they each cost stayed invisible for sessions.

    Never collapse them back into one column. Cost follows `success`; latency
    attribution and the Phase 0.6 census follow `usable`.
    """

    __tablename__ = "ai_usage_events"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    provider = Column(String, nullable=False, default="openrouter")
    model = Column(String, nullable=False, default="unknown")
    purpose = Column(String, nullable=False, default="unknown", index=True)
    request_id = Column(Integer, nullable=True, index=True)

    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=True)

    success = Column(Boolean, nullable=False, default=True)
    error = Column(Text, nullable=True)
    latency_ms = Column(Integer, nullable=True)

    # --- Phase 0.6 call census ------------------------------------------------
    #: Pipeline stage the call belongs to (planning / architect / codegen /
    #: refine / vision / fix_agent / quality_repair / appspec / blueprint / …).
    #: Falls back to `purpose` when no `ai_call` scope named one.
    stage = Column(String, nullable=True, index=True)
    #: Which writer or sub-purpose inside the stage issued the ask.
    writer = Column(String, nullable=True)
    #: Attempt index of this ask within its logical call (1-based).
    attempt = Column(Integer, nullable=True)
    #: Provider `finish_reason` — `length` is how truncation shows up.
    finish_reason = Column(String, nullable=True)
    #: Characters of assistant text returned. 0 with `success` is a silent empty.
    output_chars = Column(Integer, nullable=True)
    #: Could the pipeline act on this output? NULL only for rows written before
    #: the census landed.
    usable = Column(Boolean, nullable=True, index=True)
    #: Why not, when `usable` is false: transport / empty / truncated /
    #: unparseable / rejected.
    unusable_reason = Column(String, nullable=True)
    #: Repair writers only: file operations this call's plan actually applied.
    #: 0 is the number that matters — request 68 spent 882 s to reach it.
    ops_applied = Column(Integer, nullable=True)


class AdminAlert(Base):
    """In-app ops alerts (budget, failures, build requests, etc.)."""

    __tablename__ = "admin_alerts"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    kind = Column(String, nullable=False, index=True)
    severity = Column(String, nullable=False, default="info")  # info|warn|critical
    title = Column(String, nullable=False)
    body = Column(Text, nullable=True)
    request_id = Column(Integer, nullable=True, index=True)
    acknowledged = Column(Boolean, nullable=False, default=False)
