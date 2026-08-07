"""The collapse guard (owner-ruled, session 24): a repair that empties what
its parent populated is rejected deterministically, parent kept, fail closed.

Request 143 rev 1: the ai_appspec_repair call replaced a 6-page authored spec
(ONE fixable validator error) with a 503-byte fragment — a single
acceptance-test object with empty `pages`/`states` — and revisions 2-4 died
reconciling nothing. The taught anti-collapse line (772ac82) is the
model-facing half; this guard is the code half. Both top-level collections
carry min_length=1, so a collapsed output can never validate — rejecting it
invents nothing and only skips a provably doomed spiral.

Scope pinned here: a shrink that keeps `pages`/`states` populated is never a
collapse (repairs legitimately drop faulted objects), and a parent that never
had the collection cannot be collapsed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.application.appspec.generation as generation_mod
from app.application.appspec.builder import AppSpecCandidate
from app.application.appspec.generation import (
    AppSpecGenerationError,
    _repair_collapsed_spec,
    ensure_approved_app_spec,
)
from app.core.config import settings
from app.infrastructure.db.base import Base
from app.domain.models.app_spec import AppSpecRevision  # noqa: F401
from app.domain.models.request import Request
from app.infrastructure.templating.renderer import JinjaTemplateRenderer

TEMPLATES_DIR = BACKEND_DIR / "app" / "templates"
VALID_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "app_spec" / "valid_booking.json"
)

#: Request 143 rev 1's mined shape — one acceptance-test object masquerading
#: as the whole spec, every collection empty.
FRAGMENT = {
    "actions": [],
    "assertions": [],
    "deferred_scope": [],
    "description": "Ensure the current weekly menu is correctly displayed.",
    "id": "TEST-MENU-001",
    "name": "Verify Weekly Menu Display",
    "pages": [],
    "requirement_ids": ["REQ-MENU-001"],
    "requirements": [],
    "states": [],
    "traceability": [],
    "transitions": [],
}


def _valid_payload() -> dict:
    return json.loads(VALID_FIXTURE.read_text(encoding="utf-8"))


def _invalid_but_parsing_payload() -> dict:
    payload = _valid_payload()
    payload["pages"][0]["capability_ids"] = list(
        payload["pages"][0].get("capability_ids") or []
    ) + ["Capability1"]
    return payload


class _ScriptedAI:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.name = "scripted"

    def ask_chat(self, model, messages, **_kwargs):
        self.calls += 1
        if not self.responses:
            raise RuntimeError("No scripted AI responses left")
        return self.responses.pop(0)


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


def _run(db_session, ai):
    req = Request(
        business_name="Collapse Guard Fixture Co",
        industry="Personal Care",
        business_description="Small booking studio",
        target_customers="Local clients",
        main_problem="Phone booking is messy",
        desired_outcome="Customers can submit a booking and see confirmation.",
        project_type="new",
        needs_ai="no",
        email="fixture@example.invalid",
        status="new",
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)
    return ensure_approved_app_spec(
        db_session,
        req.id,
        ai,
        JinjaTemplateRenderer(str(TEMPLATES_DIR)),
        force_new_revision=True,
        source_snapshot_override={
            "customer_input": {
                "desired_outcome": (
                    "Customers can submit a booking and see confirmation."
                ),
                "business_name": "Collapse Guard Fixture Co",
                "main_problem": "Phone booking is messy",
            },
            "reference_evidence": {},
        },
        derived_context_override={},
    )


def _patch_repair_to_return(monkeypatch, payload: dict) -> dict:
    counter = {"repairs": 0}

    def _fragment_repair(*, candidate, **_kwargs):
        counter["repairs"] += 1
        return AppSpecCandidate(payload=dict(payload), repair_type="ai_appspec_repair")

    monkeypatch.setattr(generation_mod, "repair_app_spec_candidate", _fragment_repair)
    return counter


def test_validation_repair_collapse_fails_closed(db_session, monkeypatch):
    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(settings, "APPSPEC_MAX_REPAIR_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "APPSPEC_MAX_CALLS", 8)
    counter = _patch_repair_to_return(monkeypatch, FRAGMENT)

    ai = _ScriptedAI([json.dumps(_invalid_but_parsing_payload())])
    with pytest.raises(AppSpecGenerationError) as excinfo:
        _run(db_session, ai)

    assert "repair_collapsed_parent_spec" in str(excinfo.value)
    # The guard fires on the FIRST collapsed output — no spiral through
    # normalize/heal/schema-repair on a fragment (143 paid three revisions).
    assert counter["repairs"] == 1


def test_coverage_repair_collapse_fails_closed(db_session, monkeypatch):
    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(settings, "APPSPEC_MAX_REPAIR_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "APPSPEC_MAX_CALLS", 8)
    counter = _patch_repair_to_return(monkeypatch, FRAGMENT)

    failing_review = {
        "verdict": "repair",
        "score": 10,
        "summary": "The spec misses the explicit booking goal.",
        "goal_coverage": [],
        "omissions": [],
        "contradictions": [],
        "unsupported_additions": [],
        "mislabeled_assumptions": [],
        "open_question_gaps": [],
    }
    ai = _ScriptedAI([json.dumps(_valid_payload()), json.dumps(failing_review)])
    with pytest.raises(AppSpecGenerationError) as excinfo:
        _run(db_session, ai)

    assert "repair_collapsed_parent_spec" in str(excinfo.value)
    assert counter["repairs"] == 1


def test_populated_shrink_is_never_a_collapse(db_session, monkeypatch):
    """A repair that keeps pages/states populated proceeds normally — here all
    the way to acceptance. Catches the over-fire mutation (any shrink)."""

    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(settings, "APPSPEC_MAX_REPAIR_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "APPSPEC_MAX_CALLS", 8)
    counter = _patch_repair_to_return(monkeypatch, _valid_payload())

    coverage = {
        "verdict": "pass",
        "score": 100,
        "summary": "The explicit booking goal is represented and traceable.",
        "goal_coverage": [
            {
                "source_path": "customer_input.desired_outcome",
                "source_excerpt": (
                    "Customers can submit a booking and see confirmation."
                ),
                "covered": True,
                "requirement_ids": ["REQ-BOOK"],
                "evidence_ids": ["EVIDENCE-CONFIRMATION"],
                "acceptance_test_ids": ["TEST-BOOK"],
                "notes": "",
            }
        ],
        "omissions": [],
        "contradictions": [],
        "unsupported_additions": [],
        "mislabeled_assumptions": [],
        "open_question_gaps": [],
    }
    ai = _ScriptedAI(
        [json.dumps(_invalid_but_parsing_payload()), json.dumps(coverage)]
    )
    result = _run(db_session, ai)

    assert result.spec is not None
    assert counter["repairs"] == 1


def test_schema_repair_collapse_fails_closed(db_session, monkeypatch):
    """The schema-repair rung is guarded too: a parent with populated pages
    and an unhealable empty required trace, echoed back as the fragment."""

    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(settings, "APPSPEC_MAX_REPAIR_ATTEMPTS", 0)
    monkeypatch.setattr(settings, "APPSPEC_MAX_SCHEMA_REPAIR_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "APPSPEC_MAX_CALLS", 8)

    counter = {"repairs": 0}

    def _fragment_schema_repair(*, candidate, **_kwargs):
        counter["repairs"] += 1
        return AppSpecCandidate(payload=dict(FRAGMENT), repair_type="ai_schema_repair")

    monkeypatch.setattr(
        generation_mod, "repair_app_spec_schema_candidate", _fragment_schema_repair
    )

    broken = _valid_payload()
    # An invalid surface enum is a pydantic parse failure no deterministic
    # rung corrects (enum correction is the AI schema rung's own job), and it
    # leaves pages/states fully populated — the collapse has something to eat.
    broken["pages"][0]["surface"] = "cosmic"

    ai = _ScriptedAI([json.dumps(broken)])
    with pytest.raises(AppSpecGenerationError) as excinfo:
        _run(db_session, ai)

    assert "repair_collapsed_parent_spec" in str(excinfo.value)
    assert counter["repairs"] == 1


def test_collapse_predicate_edges() -> None:
    populated = {"pages": [{"id": "PAGE-A"}], "states": [{"id": "STATE-A"}]}
    assert _repair_collapsed_spec(populated, {"pages": [], "states": []})
    assert _repair_collapsed_spec(populated, {})  # missing keys are empty
    assert _repair_collapsed_spec(
        populated, {"pages": [{"id": "PAGE-A"}], "states": []}
    )
    # A parent that never had the collection cannot be collapsed.
    assert not _repair_collapsed_spec({"pages": [], "states": []}, FRAGMENT)
    # Populated stays populated — shrink is not collapse.
    assert not _repair_collapsed_spec(
        {"pages": [{"a": 1}, {"b": 2}], "states": [{"c": 3}]},
        {"pages": [{"a": 1}], "states": [{"c": 3}]},
    )
    assert not _repair_collapsed_spec(None, {})
    assert not _repair_collapsed_spec(populated, None)
