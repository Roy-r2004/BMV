"""The monthly cap on what outreach spends, counted from the cost ledger.

Every outreach model call is on the ledger under a purpose starting
"outreach:". A call the provider did not price counts at a fixed fallback, so an
unpriced month can never look free.
"""
from __future__ import annotations

from datetime import datetime

from app.config import settings
from app.models import AiUsageEvent


def spent_this_month(db, now: datetime | None = None) -> float:
    now = now or datetime.utcnow()
    start = datetime(now.year, now.month, 1)
    rows = (db.query(AiUsageEvent.cost_usd)
            .filter(AiUsageEvent.purpose.like("outreach:%"), AiUsageEvent.created_at >= start,
                    AiUsageEvent.created_at <= now)
            .all())
    return float(sum(r.cost_usd if r.cost_usd is not None else settings.OUTREACH_UNPRICED_CALL_USD for r in rows))


def can_spend(db, now: datetime | None = None) -> bool:
    return spent_this_month(db, now) < settings.OUTREACH_MONTHLY_USD


