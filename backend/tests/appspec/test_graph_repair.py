"""Focused tests for bounded AppSpec membership graph repair."""
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

from app.application.appspec.generation import (
    AppSpecGenerationError,
    ensure_approved_app_spec,
)
from app.application.appspec.repository import AppSpecRepository, load_json_object
from app.core.config import settings
from app.domain.appspec.sanitize.graph_repair import (
    repair_app_spec_graph,
    validation_has_repairable_graph_issues,
)
from app.domain.appspec.validation import validate_app_spec
from app.domain.models.app_spec import AppSpecRevision  # noqa: F401
from app.domain.models.request import Request
from app.domain.schemas.app_spec import AppSpec
from app.infrastructure.db.base import Base
from app.infrastructure.templating.renderer import JinjaTemplateRenderer

TEMPLATES_DIR = BACKEND_DIR / "app" / "templates"
VALID_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "app_spec" / "valid_booking.json"
)


def _two_page_mismatch_payload() -> tuple[dict, str, str, str]:
    """ACTION-SUBMIT owned by PAGE-BOOK but listed only on PAGE-SERVICE-DETAIL."""

    payload = json.loads(VALID_FIXTURE.read_text(encoding="utf-8"))
    action_id = "ACTION-SUBMIT"
    owner_page_id = "PAGE-BOOK"
    wrong_page_id = "PAGE-SERVICE-DETAIL"
    payload["pages"].append(
        {
            "id": wrong_page_id,
            "name": "Service detail",
            "purpose": "Show a service before booking.",
            "route": "/services/detail",
            "surface": "public",
            "primary": False,
            "role_ids": ["ROLE-CUSTOMER"],
            "capability_ids": ["CAP-BOOK"],
            "state_ids": ["STATE-SERVICE-READY"],
            "action_ids": [action_id],
            "evidence_ids": ["EVIDENCE-SERVICE"],
        }
    )
    payload["states"].append(
        {
            "id": "STATE-SERVICE-READY",
            "page_id": wrong_page_id,
            "name": "Ready",
            "description": "Service details are visible.",
            "initial": True,
            "terminal": True,
            "evidence_ids": ["EVIDENCE-SERVICE"],
        }
    )
    payload["evidence"].append(
        {
            "id": "EVIDENCE-SERVICE",
            "page_id": wrong_page_id,
            "name": "Service summary",
            "description": "The selected service summary is visible.",
            "kind": "text",
            "capability_ids": ["CAP-BOOK"],
        }
    )
    book_page = next(page for page in payload["pages"] if page["id"] == owner_page_id)
    book_page["action_ids"] = [
        item for item in book_page.get("action_ids", []) if item != action_id
    ]
    return payload, action_id, owner_page_id, wrong_page_id


def _coverage_for_booking() -> dict:
    return {
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


class _SequenceAI:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0

    @property
    def name(self) -> str:
        return "graph-repair-fixture"

    def ask_chat(self, _model: str, messages: list[dict], **_kwargs) -> str:
        self.calls += 1
        if not self.responses:
            raise AssertionError("Unexpected extra AI call")
        return self.responses.pop(0)

    def ask_vision(self, *_args, **_kwargs) -> str:
        raise AssertionError("vision unused")

    def is_available(self) -> bool:
        return True


def test_mismatched_page_membership_is_repaired() -> None:
    payload, action_id, owner_page_id, wrong_page_id = _two_page_mismatch_payload()
    original = copy.deepcopy(payload)
    report = {
        "passed": False,
        "issues": [
            {
                "code": "page_membership_mismatch",
                "message": "mismatch",
                "related_ids": [wrong_page_id, action_id, owner_page_id],
            }
        ],
    }
    assert validation_has_repairable_graph_issues(report)
    repair = repair_app_spec_graph(payload, report)
    assert repair.applied
    assert repair.result_label == "repaired"
    assert repair.original_sha256 != repair.repaired_sha256
    assert original == payload

    pages = {page["id"]: page for page in repair.payload["pages"]}
    assert action_id not in pages[wrong_page_id]["action_ids"]
    assert action_id in pages[owner_page_id]["action_ids"]
    action = next(
        item for item in repair.payload["actions"] if item["id"] == action_id
    )
    assert action["page_id"] == owner_page_id
    assert validate_app_spec(AppSpec.model_validate(repair.payload)).is_valid


def test_duplicate_membership_references_are_normalized() -> None:
    payload, action_id, owner_page_id, _wrong = _two_page_mismatch_payload()
    owner = next(page for page in payload["pages"] if page["id"] == owner_page_id)
    owner["action_ids"] = [action_id, action_id]
    repair = repair_app_spec_graph(
        payload,
        {"issues": [{"code": "page_membership_mismatch"}]},
    )
    assert repair.applied
    owner_after = next(
        page for page in repair.payload["pages"] if page["id"] == owner_page_id
    )
    assert owner_after["action_ids"].count(action_id) == 1


def test_missing_canonical_page_fails_closed() -> None:
    payload, action_id, _owner, _wrong = _two_page_mismatch_payload()
    action = next(item for item in payload["actions"] if item["id"] == action_id)
    action["page_id"] = "PAGE-DOES-NOT-EXIST"
    repair = repair_app_spec_graph(
        payload,
        {"issues": [{"code": "page_membership_mismatch"}]},
    )
    assert not repair.applied
    assert repair.result_label == "rejected"
    assert any(
        reason.startswith("missing_canonical_owner:")
        for reason in repair.refused_reasons
    )


def test_ambiguous_ownership_fails_closed() -> None:
    payload, action_id, _owner, _wrong = _two_page_mismatch_payload()
    action = next(item for item in payload["actions"] if item["id"] == action_id)
    action["page_id"] = ""
    repair = repair_app_spec_graph(
        payload,
        {"issues": [{"code": "page_membership_mismatch"}]},
    )
    assert not repair.applied
    assert any(
        reason.startswith("ambiguous_action_ownership:")
        for reason in repair.refused_reasons
    )


def test_valid_appspec_unchanged_byte_for_byte() -> None:
    payload = json.loads(VALID_FIXTURE.read_text(encoding="utf-8"))
    before = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    repair = repair_app_spec_graph(payload, {"passed": True, "issues": []})
    after = json.dumps(repair.payload, sort_keys=True, separators=(",", ":"))
    assert before == after
    assert not repair.applied
    assert repair.result_label == "unchanged"


def test_generation_persists_immutable_original_and_repaired_revision() -> None:
    payload, action_id, owner_page_id, wrong_page_id = _two_page_mismatch_payload()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    previous_fallback = settings.APPSPEC_FALLBACK_ENABLED
    previous_repairs = settings.APPSPEC_MAX_REPAIR_ATTEMPTS
    settings.APPSPEC_FALLBACK_ENABLED = False
    settings.APPSPEC_MAX_REPAIR_ATTEMPTS = 3
    try:
        req = Request(
            business_name="Graph Repair Studio",
            business_description="A studio appointment booking product.",
            target_customers="Studio customers",
            main_problem="Appointments are arranged manually.",
            desired_outcome="Customers can submit a booking and see confirmation.",
            email="private@example.com",
            mvp_blueprint="Derived suggestion: add a booking flow.",
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        ai = _SequenceAI(
            [json.dumps(payload), json.dumps(_coverage_for_booking())]
        )
        result = ensure_approved_app_spec(
            db,
            req.id,
            ai,
            JinjaTemplateRenderer(TEMPLATES_DIR),
        )
        assert result.revision_record.status == "accepted"
        metadata = load_json_object(result.revision_record.generation_metadata_json)
        assert metadata.get("used_fallback") is False
        audit = metadata.get("graph_repair") or {}
        assert audit.get("repair_type") == "deterministic_graph_repair"
        assert audit.get("result") == "repaired"
        assert audit.get("original_sha256")
        assert audit.get("repaired_sha256")
        assert audit["original_sha256"] != audit["repaired_sha256"]
        assert any(
            "remove_action_from_non_owner" in item for item in audit.get("actions", [])
        )
        # Sanitize may already restore owner membership before graph repair;
        # require either an explicit add or a clean post-repair owner list.
        assert action_id in {
            item
            for page in load_json_object(result.revision_record.app_spec_json)[
                "pages"
            ]
            if page["id"] == owner_page_id
            for item in page["action_ids"]
        }

        revisions = AppSpecRepository(db).list_revisions(req.id)
        assert len(revisions) >= 2
        original = next(
            row
            for row in revisions
            if load_json_object(row.generation_metadata_json).get("terminal_reason")
            == "pre_graph_repair"
        )
        assert original.status == "rejected"
        original_spec = load_json_object(original.app_spec_json)
        pages = {page["id"]: page for page in original_spec["pages"]}
        # Pre-repair revision keeps the mismatched membership (immutable).
        assert action_id in pages[wrong_page_id]["action_ids"]

        accepted = result.revision_record
        assert accepted.parent_revision_id == original.id
        accepted_spec = load_json_object(accepted.app_spec_json)
        pages = {page["id"]: page for page in accepted_spec["pages"]}
        assert action_id not in pages[wrong_page_id]["action_ids"]
        assert action_id in pages[owner_page_id]["action_ids"]
        # Author + coverage only — no AI repair after successful graph repair.
        assert ai.calls == 2
    finally:
        settings.APPSPEC_FALLBACK_ENABLED = previous_fallback
        settings.APPSPEC_MAX_REPAIR_ATTEMPTS = previous_repairs
        db.close()


def test_graph_repair_runs_once_then_one_ai_repair_without_fallback() -> None:
    payload, action_id, _owner, _wrong = _two_page_mismatch_payload()
    action = next(item for item in payload["actions"] if item["id"] == action_id)
    action["page_id"] = "PAGE-MISSING-OWNER"
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    previous_fallback = settings.APPSPEC_FALLBACK_ENABLED
    previous_repairs = settings.APPSPEC_MAX_REPAIR_ATTEMPTS
    settings.APPSPEC_FALLBACK_ENABLED = False
    settings.APPSPEC_MAX_REPAIR_ATTEMPTS = 3
    try:
        req = Request(
            business_name="Refuse Repair Studio",
            business_description="A studio appointment booking product.",
            target_customers="Studio customers",
            main_problem="Appointments are arranged manually.",
            desired_outcome="Customers can submit a booking and see confirmation.",
            email="private@example.com",
            mvp_blueprint="Derived suggestion: add a booking flow.",
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        # Author once, then one AI repair that returns the same invalid payload.
        ai = _SequenceAI([json.dumps(payload), json.dumps(payload)])
        with pytest.raises(AppSpecGenerationError, match="fallback is disabled"):
            ensure_approved_app_spec(
                db,
                req.id,
                ai,
                JinjaTemplateRenderer(TEMPLATES_DIR),
            )
        assert ai.calls == 2
        metadata_rows = [
            load_json_object(row.generation_metadata_json)
            for row in AppSpecRepository(db).list_revisions(req.id)
        ]
        assert all(item.get("used_fallback") is not True for item in metadata_rows)
        assert any(
            (item.get("graph_repair") or {}).get("result") == "rejected"
            for item in metadata_rows
            if item.get("graph_repair")
        )
    finally:
        settings.APPSPEC_FALLBACK_ENABLED = previous_fallback
        settings.APPSPEC_MAX_REPAIR_ATTEMPTS = previous_repairs
        db.close()
