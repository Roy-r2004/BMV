"""The prospect record: what a business is, where we read it, and its token."""
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.config import settings


def test_a_prospect_is_stored_with_an_unguessable_token(db):
    from app.models import Prospect
    from app.outreach import new_token

    a, b = new_token(), new_token()
    assert len(a) >= 22 and a != b
    db.add(Prospect(token=a, name="Glow", city="Dubai", kind="salon", key="name:glow|dubai"))
    db.commit()
    stored = db.query(Prospect).one()
    assert stored.status == "found" and stored.opens == 0


def test_one_run_per_day(db):
    from app.models import OutreachRun

    db.add(OutreachRun(day=date(2026, 11, 11)))
    db.commit()
    db.add(OutreachRun(day=date(2026, 11, 11)))
    with pytest.raises(IntegrityError):
        db.commit()


def test_the_settings_have_the_agreed_defaults():
    assert settings.OUTREACH_DAILY == 30
    assert settings.OUTREACH_MONTHLY_USD == 100.0
    assert settings.OUTREACH_UNPRICED_CALL_USD == 0.02
    assert settings.OUTREACH_CITIES[0] == "Dubai"
    assert "salon" in settings.OUTREACH_KINDS
    assert settings.OUTREACH_MIN_SCORE == 30
