"""R6: every ask row self-describing — analyze/blueprint/demo carried none.

Telemetry census over requests >= 129: analyze (2/2 rows), blueprint (24/24)
and demo (7/7) were the ONLY stages still stamped by the `record_usage`
fallback (`writer IS NULL AND attempt=1 AND stage=purpose`) — those stages
made every ask outside any `ai_call` scope. These tests call the REAL stage
functions with a provider that captures `current_ai_call()` at ask time, so an
unwired scope (the fallback signature returning) fails here.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.pipelines.blueprint import generate_mvp_blueprint
from app.application.pipelines.reference_analysis import generate_reference_analysis
from app.application.pipelines.visual_demo import generate_visual_demo
from app.application.services.ai_context import current_ai_call
from app.domain.models.request import Request
from app.infrastructure.db.base import Base
from app.infrastructure.templating.renderer import JinjaTemplateRenderer

TEMPLATES_DIR = BACKEND_DIR / "app" / "templates"


class _CapturingAI:
    """Records the ai_call scope active at the moment of each ask."""

    def __init__(self, response: str = "{}") -> None:
        self.scopes: list[tuple[str | None, str | None, int | None]] = []
        self.response = response
        self.name = "capturing"

    def _capture(self) -> None:
        call = current_ai_call()
        self.scopes.append(
            (call.stage, call.writer, call.attempt) if call else (None, None, None)
        )

    def ask_chat(self, model, messages, **_kwargs):
        self._capture()
        return self.response

    def ask_vision(self, model, prompt, image_path, **_kwargs):
        self._capture()
        return self.response


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _seed_request(session, **overrides) -> Request:
    fields = dict(
        business_name="Scope Fixture Co",
        industry="Personal Care",
        business_description="Small booking studio",
        project_type="new",
        email="fixture@example.invalid",
        status="new",
    )
    fields.update(overrides)
    req = Request(**fields)
    session.add(req)
    session.commit()
    session.refresh(req)
    return req


def test_reference_analysis_ask_carries_stage_and_writer(db_session) -> None:
    req = _seed_request(db_session, reference_url="https://example.invalid/")
    ai = _CapturingAI(response="Reference analysis text.")
    generate_reference_analysis(
        db_session, req.id, ai, JinjaTemplateRenderer(str(TEMPLATES_DIR))
    )
    assert ai.scopes == [("analyze", "reference_url_analysis", 1)]


def test_blueprint_asks_carry_stage_and_writer(db_session) -> None:
    req = _seed_request(db_session)
    ai = _CapturingAI(response="A blueprint without extractable fields.")
    generate_mvp_blueprint(
        db_session, req.id, ai, JinjaTemplateRenderer(str(TEMPLATES_DIR))
    )
    assert ai.scopes[0] == ("blueprint", "mvp_blueprint", 1)
    # The fit-score extraction fires on this fixture (nothing parseable in the
    # blueprint text) and must be its own self-describing ask.
    assert ("blueprint", "preview_extraction", 1) in ai.scopes[1:]
    assert all(scope[0] == "blueprint" for scope in ai.scopes)


def test_visual_demo_ask_carries_stage_and_writer(db_session) -> None:
    req = _seed_request(db_session)
    req.mvp_blueprint = "A blueprint."
    db_session.commit()
    ai = _CapturingAI(response='{"tagline": "Test"}')
    generate_visual_demo(
        db_session, req.id, ai, JinjaTemplateRenderer(str(TEMPLATES_DIR))
    )
    assert ai.scopes == [("demo", "visual_demo", 1)]
