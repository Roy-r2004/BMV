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
    """One row per AI API call (success or failure)."""

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
