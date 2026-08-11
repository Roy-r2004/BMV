"""The hardening pass: no run with a viable candidate dies without one last
full deterministic pass, and a repair can no longer silently drop unfaulted
trace rows.

Three mechanisms, each pinned here:

1. `restore_dropped_trace_links` — request 130's death class. A whole-document
   repair kept the requirement and dropped its traceability row; restoration
   is strictly proven per row against the repaired document.
2. `_heal_exact_duplicate_objects` — the only mechanically safe slice of
   `duplicate_global_id`: byte-identical re-emissions are dropped, conflicting
   objects stay with the model.
3. `_terminal_salvage_pass` — at every deterministic fatal exit, the
   code-driven heals and unbindable-assertion drops run once more, uncapped,
   before the run is discarded. Progress means a changed document.
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
from app.application.appspec.generation import ensure_approved_app_spec
from app.core.config import settings
from app.domain.appspec.sanitize.heal import (
    heal_app_spec_payload,
    restore_dropped_trace_links,
)
from app.domain.models.app_spec import AppSpecRevision  # noqa: F401
from app.domain.models.request import Request
from app.infrastructure.db.base import Base
from app.infrastructure.templating.renderer import JinjaTemplateRenderer

TEMPLATES_DIR = BACKEND_DIR / "app" / "templates"
VALID_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "app_spec" / "valid_booking.json"
)


def _valid_payload() -> dict:
    return json.loads(VALID_FIXTURE.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# 1. restore_dropped_trace_links


def _parent_and_repaired() -> tuple[dict, dict]:
    parent = _valid_payload()
    repaired = copy.deepcopy(parent)
    dropped = repaired["traceability"].pop(0)
    assert dropped["requirement_id"]
    return parent, repaired


def test_request130_shape_a_dropped_unfaulted_trace_row_is_restored() -> None:
    parent, repaired = _parent_and_repaired()
    restored, actions = restore_dropped_trace_links(parent, repaired)
    assert len(actions) == 1
    assert actions[0].startswith("restore_dropped_trace_link:")
    assert len(restored["traceability"]) == len(parent["traceability"])
    req_ids = {t["requirement_id"] for t in restored["traceability"]}
    assert parent["traceability"][0]["requirement_id"] in req_ids


def test_a_requirement_the_repair_also_dropped_is_not_retraced() -> None:
    parent, repaired = _parent_and_repaired()
    dropped_req = parent["traceability"][0]["requirement_id"]
    repaired["requirements"] = [
        r for r in repaired["requirements"] if r["id"] != dropped_req
    ]
    _restored, actions = restore_dropped_trace_links(parent, repaired)
    assert actions == []


def test_a_row_with_a_dangling_reference_is_not_restored() -> None:
    parent, repaired = _parent_and_repaired()
    dropped = parent["traceability"][0]
    # The repair also removed the evidence the row cites.
    repaired["evidence"] = [
        e for e in repaired["evidence"] if e["id"] not in dropped["evidence_ids"]
    ]
    _restored, actions = restore_dropped_trace_links(parent, repaired)
    assert actions == []


def test_a_duplicate_link_fix_is_never_fought() -> None:
    # The repaired doc still has A row for the requirement — restoration must
    # not add a second one back.
    parent, _ = _parent_and_repaired()
    repaired = copy.deepcopy(parent)  # nothing dropped
    _restored, actions = restore_dropped_trace_links(parent, repaired)
    assert actions == []


def test_a_row_whose_capability_no_longer_claims_the_requirement_stays_dropped() -> None:
    parent, repaired = _parent_and_repaired()
    dropped = parent["traceability"][0]
    for cap in repaired["capabilities"]:
        if cap["id"] in dropped["capability_ids"]:
            cap["requirement_ids"] = [
                r for r in cap["requirement_ids"] if r != dropped["requirement_id"]
            ]
    _restored, actions = restore_dropped_trace_links(parent, repaired)
    assert actions == []


def test_inputs_are_never_mutated() -> None:
    parent, repaired = _parent_and_repaired()
    parent_before = copy.deepcopy(parent)
    repaired_before = copy.deepcopy(repaired)
    restore_dropped_trace_links(parent, repaired)
    assert parent == parent_before
    assert repaired == repaired_before


# --------------------------------------------------------------------------- #
# 2. exact-duplicate heal


def test_a_byte_identical_duplicate_is_dropped() -> None:
    payload = _valid_payload()
    payload["evidence"].append(copy.deepcopy(payload["evidence"][0]))
    healed, actions = heal_app_spec_payload(
        payload,
        {"issues": [{"code": "duplicate_global_id", "path": ["evidence", 1, "id"]}]},
    )
    assert any(a.startswith("drop_exact_duplicate:evidence:") for a in actions)
    ids = [e["id"] for e in healed["evidence"]]
    assert len(ids) == len(set(ids))


def test_two_different_objects_under_one_id_stay_for_the_model() -> None:
    payload = _valid_payload()
    clone = copy.deepcopy(payload["evidence"][0])
    clone["description"] = "a genuinely different object"
    payload["evidence"].append(clone)
    healed, actions = heal_app_spec_payload(
        payload,
        {"issues": [{"code": "duplicate_global_id", "path": ["evidence", 1, "id"]}]},
    )
    assert not any(a.startswith("drop_exact_duplicate:") for a in actions)
    assert len(healed["evidence"]) == len(payload["evidence"])


def test_the_duplicate_heal_needs_the_code_to_fire() -> None:
    payload = _valid_payload()
    payload["evidence"].append(copy.deepcopy(payload["evidence"][0]))
    healed, actions = heal_app_spec_payload(payload, {"issues": []})
    assert not any(a.startswith("drop_exact_duplicate:") for a in actions)
    assert len(healed["evidence"]) == len(payload["evidence"])


# --------------------------------------------------------------------------- #
# 3. terminal salvage — a run that used to die now ships its own document


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
        business_name="Terminal Salvage Fixture Co",
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
                "business_name": "Terminal Salvage Fixture Co",
                "main_problem": "Phone booking is messy",
            },
            "reference_evidence": {},
        },
        derived_context_override={},
    )


def test_a_mechanical_failure_with_no_repairs_left_ships_via_terminal_salvage(
    db_session, monkeypatch
):
    """Repair budget zero (the deadline-stopped shape: `_appspec_may_call_model`
    false means `ai_budget = 0` and the loop falls straight to the death line)
    with an unbindable state assertion in the document. Before: the 149/154/155
    salvage never ran — it is wired to the identical-signature branch, which
    needs a repair to have happened — and the run died
    `deterministic_validation_failed`. Now: the terminal pass drops the
    unprovable claim, the loop revalidates clean, and the run ships the
    model's own document."""

    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(settings, "APPSPEC_MAX_REPAIR_ATTEMPTS", 0)
    monkeypatch.setattr(settings, "APPSPEC_MAX_DETERMINISTIC_HEALS", 0)
    monkeypatch.setattr(settings, "APPSPEC_MAX_CALLS", 8)
    # Isolate the death line: the sanitize pipeline binds a null state_id when
    # the page has exactly one state, which fixes this document before the
    # validator ever sees it. Production's 149/154/155 documents were ones
    # sanitize could NOT fix; identity-sanitize simulates exactly that class.
    monkeypatch.setattr(
        generation_mod,
        "sanitize_app_spec_payload",
        lambda payload, source_snapshot, diagnostics=None: copy.deepcopy(
            dict(payload)
        ),
    )

    broken = _valid_payload()
    target_test = broken["acceptance_tests"][0]
    target_test["assertions"] = list(target_test["assertions"]) + [
        {
            "kind": "state",
            "description": "the booking is confirmed",
            "page_id": target_test["assertions"][0].get("page_id"),
            "state_id": None,
            "evidence_id": None,
            "expected": "confirmed",
        }
    ]

    coverage = {
        "verdict": "pass",
        "score": 95,
        "summary": "The explicit booking goal is represented and traceable.",
        "goal_coverage": [
            {
                "source_path": "customer_input.desired_outcome",
                "source_excerpt": "Customers can submit a booking",
                "covered": True,
                "requirement_ids": [broken["requirements"][0]["id"]],
                "evidence_ids": [broken["evidence"][0]["id"]],
                "acceptance_test_ids": [broken["acceptance_tests"][0]["id"]],
                "notes": "",
            }
        ],
        "omissions": [],
        "contradictions": [],
        "unsupported_additions": [],
        "mislabeled_assumptions": [],
        "open_question_gaps": [],
    }
    ai = _ScriptedAI([json.dumps(broken), json.dumps(coverage)])
    result = _run(db_session, ai)
    assert result.revision_record.status == "accepted"
    metadata = json.loads(result.revision_record.generation_metadata_json)
    assert any(
        a.startswith("drop_unbindable_state_assertion:")
        for a in metadata.get("heal_actions") or []
    ), metadata.get("heal_actions")


def test_a_repair_that_drops_an_unfaulted_trace_row_gets_it_restored(
    db_session, monkeypatch
):
    """The attrition guard, wired: authoring fails validation, the scripted
    repair returns a valid document minus one traceability row it was never
    asked to touch. With the guard the row is restored and the run accepts on
    that repair; without it the loop would spend another repair on
    `requirement_unaccounted_for` and find no scripted response."""

    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(settings, "APPSPEC_MAX_REPAIR_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "APPSPEC_MAX_CALLS", 8)

    first = _valid_payload()
    first["pages"][0]["capability_ids"] = list(
        first["pages"][0].get("capability_ids") or []
    ) + ["Capability1"]

    repaired = _valid_payload()
    dropped = repaired["traceability"].pop(0)

    def _scripted_repair(*, candidate, **_kwargs):
        from app.application.appspec.builder import AppSpecCandidate

        return AppSpecCandidate(payload=copy.deepcopy(repaired), repair_type="ai_appspec_repair")

    monkeypatch.setattr(generation_mod, "repair_app_spec_candidate", _scripted_repair)

    coverage = {
        "verdict": "pass",
        "score": 95,
        "summary": "The explicit booking goal is represented and traceable.",
        "goal_coverage": [
            {
                "source_path": "customer_input.desired_outcome",
                "source_excerpt": "Customers can submit a booking",
                "covered": True,
                "requirement_ids": [repaired["requirements"][0]["id"]],
                "evidence_ids": [repaired["evidence"][0]["id"]],
                "acceptance_test_ids": [repaired["acceptance_tests"][0]["id"]],
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
    assert result.revision_record.status == "accepted"
    metadata = json.loads(result.revision_record.generation_metadata_json)
    assert any(
        a == f"restore_dropped_trace_link:{dropped['requirement_id']}"
        for a in metadata.get("heal_actions") or []
    ), metadata.get("heal_actions")


def test_an_unsalvageable_failure_still_dies_exactly_as_before(
    db_session, monkeypatch
):
    """The salvage must not soften real fatality: an undeclared capability
    reference nothing can wire deterministically still fails closed."""

    from app.application.appspec.generation import AppSpecGenerationError

    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(settings, "APPSPEC_MAX_REPAIR_ATTEMPTS", 0)
    monkeypatch.setattr(settings, "APPSPEC_MAX_DETERMINISTIC_HEALS", 0)
    monkeypatch.setattr(settings, "APPSPEC_MAX_CALLS", 8)

    broken = _valid_payload()
    broken["pages"][0]["capability_ids"] = list(
        broken["pages"][0].get("capability_ids") or []
    ) + ["Capability1"]

    ai = _ScriptedAI([json.dumps(broken)])
    with pytest.raises(AppSpecGenerationError) as excinfo:
        _run(db_session, ai)
    assert "deterministic_validation_failed" in str(excinfo.value)
