"""A hundred dollars a month, counted from the ledger."""
from datetime import datetime

from app.models import AiUsageEvent
from app.outreach import budget

NOW = datetime(2026, 11, 20, 12, 0)


def _event(db, purpose, cost, when=NOW):
    db.add(AiUsageEvent(provider="openrouter", model="m", purpose=purpose, cost_usd=cost, created_at=when))
    db.commit()


def test_unpriced_calls_count_at_the_fallback(db):
    for _ in range(3):
        _event(db, "outreach:write", None)
    assert round(budget.spent_this_month(db, NOW), 4) == 0.06


def test_other_purposes_and_last_month_do_not_count(db):
    _event(db, "diagnose", 5.0)
    _event(db, "outreach:find", 1.0, datetime(2026, 10, 31, 23, 0))
    _event(db, "outreach:find", 0.5)
    assert budget.spent_this_month(db, NOW) == 0.5


def test_spending_stops_at_the_cap(db):
    assert budget.can_spend(db, NOW)
    _event(db, "outreach:find", 100.0)
    assert not budget.can_spend(db, NOW)
