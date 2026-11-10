import pytest


@pytest.fixture
def db():
    from app import models  # noqa: F401 - the tables must be known before they are made
    from app.database import Base, SessionLocal, engine

    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.rollback()
    from app.models import AiUsageEvent, OutreachRun, Prospect

    session.query(Prospect).delete()
    session.query(OutreachRun).delete()
    session.query(AiUsageEvent).filter(AiUsageEvent.purpose.like("outreach:%")).delete(synchronize_session=False)
    session.commit()
    session.close()
