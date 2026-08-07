"""A repair that reproduces its parent's identical validator error set fails then.

Request 143 (session 22): revision 5 re-recorded revision 4's candidate with the
byte-identical validator error set; request 138 (session 21): the repair model
returned rev 2 with the identical error at the identical path, and the loop
would have spent every remaining `APPSPEC_MAX_REPAIR_ATTEMPTS` re-asking the
question it had just watched fail. R2 says a retry must be a different ask —
and a repair whose output reproduces its input's verdict proves the next ask
would be the same ask. The loop now fails closed with
`repair_reproduced_parent_errors` instead of spending the remaining budget.

Scope pinned here: the stop compares only across an AI repair (schema or
general); a repair that changes the error set — even to a different failure —
is progress and never trips it.
"""
from __future__ import annotations

import copy
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
from app.application.appspec.generation import (
    AppSpecGenerationError,
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


def _valid_payload() -> dict:
    return json.loads(VALID_FIXTURE.read_text(encoding="utf-8"))


def _placeholder_reference_payload() -> dict:
    """Parses fine, fails deterministic validation: a page cites an undeclared
    placeholder capability — request 143 rev 4's mined shape, minus the
    schema-parse half so the general repair rung owns it."""

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


def _seed_request(session) -> Request:
    req = Request(
        business_name="Identical Error Stop Fixture Co",
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
    session.add(req)
    session.commit()
    session.refresh(req)
    return req


def _run(db_session, ai):
    return ensure_approved_app_spec(
        db_session,
        _seed_request(db_session).id,
        ai,
        JinjaTemplateRenderer(str(TEMPLATES_DIR)),
        force_new_revision=True,
        source_snapshot_override={
            "customer_input": {
                "desired_outcome": (
                    "Customers can submit a booking and see confirmation."
                ),
                "business_name": "Identical Error Stop Fixture Co",
                "main_problem": "Phone booking is messy",
            },
            "reference_evidence": {},
        },
        derived_context_override={},
    )


def _patch_repair_to_return_input(monkeypatch) -> dict:
    """The general AI repair hands back its input candidate untouched — the
    request-138 shape. Counted so the tests can prove exactly one was spent."""

    counter = {"repairs": 0}

    def _echo_repair(*, candidate, **_kwargs):
        counter["repairs"] += 1
        return candidate

    monkeypatch.setattr(generation_mod, "repair_app_spec_candidate", _echo_repair)
    return counter


def test_identical_repair_output_fails_then_not_after_the_budget(
    db_session, monkeypatch
):
    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(settings, "APPSPEC_MAX_REPAIR_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "APPSPEC_MAX_CALLS", 8)
    counter = _patch_repair_to_return_input(monkeypatch)

    ai = _ScriptedAI([json.dumps(_placeholder_reference_payload())])
    with pytest.raises(AppSpecGenerationError) as excinfo:
        _run(db_session, ai)

    # The reason names the class, and the loop spent ONE repair on it — not
    # the remaining APPSPEC_MAX_REPAIR_ATTEMPTS.
    assert "repair_reproduced_parent_errors" in str(excinfo.value)
    assert counter["repairs"] == 1
    assert ai.calls == 1  # authoring only; the echoed repair asks nothing new


def test_a_repair_that_changes_the_error_set_is_progress_not_a_stop(
    db_session, monkeypatch
):
    """Different errors after repair 1, valid after repair 2 — the run accepts.

    Pins the guard's scope: an error set that CHANGES (even to a different
    failure) never trips the stop. Catches the over-fire mutation that would
    stop on any post-repair failure."""

    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(settings, "APPSPEC_MAX_REPAIR_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "APPSPEC_MAX_CALLS", 8)

    first = _placeholder_reference_payload()
    second = _valid_payload()
    second["pages"][0]["capability_ids"] = list(
        second["pages"][0].get("capability_ids") or []
    ) + ["CAP-NOPE"]

    responses = [copy.deepcopy(second), _valid_payload()]

    def _scripted_repair(*, candidate, **_kwargs):
        from app.application.appspec.builder import AppSpecCandidate

        return AppSpecCandidate(
            payload=responses.pop(0), repair_type="ai_appspec_repair"
        )

    monkeypatch.setattr(generation_mod, "repair_app_spec_candidate", _scripted_repair)

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
    ai = _ScriptedAI([json.dumps(first), json.dumps(coverage)])

    result = _run(db_session, ai)

    assert result.spec is not None
    assert not responses  # both scripted repairs were consumed


def test_the_schema_repair_rung_is_guarded_too(db_session, monkeypatch):
    """An AI schema repair that echoes its input trips the same stop —
    request 143 revs 3-4's rung."""

    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(settings, "APPSPEC_MAX_REPAIR_ATTEMPTS", 0)
    monkeypatch.setattr(settings, "APPSPEC_MAX_SCHEMA_REPAIR_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "APPSPEC_MAX_DETERMINISTIC_HEALS", 1)
    monkeypatch.setattr(settings, "APPSPEC_MAX_CALLS", 8)

    counter = {"repairs": 0}

    def _echo_schema_repair(*, candidate, **_kwargs):
        counter["repairs"] += 1
        return candidate

    monkeypatch.setattr(
        generation_mod, "repair_app_spec_schema_candidate", _echo_schema_repair
    )

    # Request 143 rev 3's mined shape: pages emptied outright. (An empty
    # `state_ids` beside a populated `states` array is deterministically
    # reconciled from the siblings and never reaches the AI rung — 143 failed
    # precisely because its states existed NOWHERE, and empty `pages` is the
    # same nothing-to-reconcile-from class.)
    broken = _valid_payload()
    broken["pages"] = []

    ai = _ScriptedAI([json.dumps(broken)])
    with pytest.raises(AppSpecGenerationError) as excinfo:
        _run(db_session, ai)

    assert "repair_reproduced_parent_errors" in str(excinfo.value)
    assert counter["repairs"] == 1
