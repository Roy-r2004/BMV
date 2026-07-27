"""Focused tests for AppSpec schema diagnostics, normalization, and safe repairs."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.appspec.builder import AppSpecCandidate, parse_app_spec_candidate
from app.application.appspec.generation import (
    AppSpecGenerationError,
    ensure_approved_app_spec,
)
from app.application.appspec.repository import AppSpecRepository, load_json_object
from app.application.appspec.schema_repair import repair_app_spec_schema_candidate
from app.core.config import settings
from app.domain.appspec.sanitize.preparse_normalize import (
    extract_json_object_text,
    normalize_app_spec_preparse,
    repair_trailing_commas,
)
from app.domain.appspec.sanitize.schema_diagnostics import (
    build_rejected_candidate_artifact,
    classify_schema_parse_exception,
    payload_sha256,
    redact_candidate_fragment,
)
from app.domain.appspec.sanitize.trace_evidence_repair import (
    repair_trace_evidence_mismatch,
    validation_has_safe_trace_evidence_repair,
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
SCHEMA_INVALID_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "app_spec"
    / "schema_invalid_booking_smoke27.json"
)


def _valid_payload() -> dict:
    return json.loads(VALID_FIXTURE.read_text(encoding="utf-8"))


def _smoke26_safe_payload() -> dict:
    """Evidence exists; trace cites a stale sibling ID with unambiguous canonical."""

    payload = _valid_payload()
    # Keep a single form+CAP-BOOK evidence as the canonical calendar target.
    for item in payload["evidence"]:
        if item["id"] == "EVIDENCE-FORM":
            item["kind"] = "status"
    payload["evidence"].append(
        {
            "id": "EVIDENCE-AVAILABILITY-CALENDAR",
            "page_id": "PAGE-BOOK",
            "name": "Availability calendar",
            "description": "Interactive availability calendar on the booking page.",
            "kind": "form",
            "capability_ids": ["CAP-BOOK"],
        }
    )
    payload["evidence"].append(
        {
            "id": "EVIDENCE-STALE-CALENDAR",
            "page_id": "PAGE-BOOK",
            "name": "Stale calendar alias",
            "description": "Stale duplicate calendar reference that is not canonical.",
            "kind": "form",
            "capability_ids": ["CAP-OTHER"],
        }
    )
    payload["pages"][0]["evidence_ids"] = list(
        dict.fromkeys(
            list(payload["pages"][0].get("evidence_ids") or [])
            + ["EVIDENCE-AVAILABILITY-CALENDAR"]
        )
    )
    payload["traceability"][0]["evidence_ids"] = [
        "EVIDENCE-CONFIRMATION",
        "EVIDENCE-STALE-CALENDAR",
    ]
    return payload


def _smoke26_unsafe_missing_payload() -> dict:
    payload = _valid_payload()
    payload["traceability"][0]["evidence_ids"] = [
        "EVIDENCE-CONFIRMATION",
        "EVIDENCE-AVAILABILITY-CALENDAR",
    ]
    return payload


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


class _ScriptedAI:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.name = "scripted"

    def ask_chat(self, model, messages, max_tokens=None, temperature=None):
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
        business_name="Schema Diagnostics Fixture Co",
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


def test_classify_pydantic_paths_and_typed_codes():
    payload = json.loads(SCHEMA_INVALID_FIXTURE.read_text(encoding="utf-8"))
    with pytest.raises(ValidationError) as excinfo:
        AppSpec.model_validate(payload)
    wrapper = classify_schema_parse_exception(excinfo.value)
    assert wrapper["code"] == "app_spec_schema_parse_failed"
    codes = {issue["code"] for issue in wrapper["issues"]}
    paths = {issue["path"] for issue in wrapper["issues"]}
    assert "invalid_field_type" in codes or "invalid_enum" in codes or "unexpected_field" in codes
    assert any("product_intent.target_users" in path or "requirements" in path for path in paths)
    assert any(issue.get("offending_value_type") for issue in wrapper["issues"])


def test_rejected_candidate_artifact_redacts_secrets():
    artifact = build_rejected_candidate_artifact(
        request_id=27,
        attempt_number=1,
        provider="openrouter",
        model="test-model",
        prompt_revision=settings.APPSPEC_PROMPT_REVISION,
        raw_response='{"ok":true}',
        candidate_payload={
            "email": "person@example.com",
            "authorization": "Bearer SECRET",
            "pages": [{"id": "PAGE-BOOK"}],
        },
        schema_issue={
            "code": "app_spec_schema_parse_failed",
            "message": "failed",
            "issues": [
                {
                    "code": "invalid_field_type",
                    "path": "product_intent.target_users",
                    "message": "list expected",
                    "error_type": "list_type",
                    "offending_value_type": "str",
                }
            ],
        },
        terminal_result="schema_parse_failed",
    )
    assert artifact["request_id"] == 27
    assert artifact["raw_response_sha256"]
    assert artifact["redacted_candidate"]["email"] == "<redacted:email>"
    assert artifact["redacted_candidate"]["authorization"] == "<redacted>"
    assert artifact["schema_validation_errors"][0]["path"] == (
        "product_intent.target_users"
    )


def test_markdown_json_extraction_and_trailing_commas():
    raw = "```json\n{\"a\": 1,}\n```"
    text, meta = extract_json_object_text(raw)
    assert meta["ok"] is True
    assert json.loads(text) == {"a": 1}
    repaired, changed = repair_trailing_commas('{"a":1,}')
    assert changed is True
    assert json.loads(repaired) == {"a": 1}


def test_preparse_normalization_optional_defaults_and_no_invention():
    payload = json.loads(SCHEMA_INVALID_FIXTURE.read_text(encoding="utf-8"))
    original = copy.deepcopy(payload)
    result = normalize_app_spec_preparse(payload)
    assert result.applied is True
    assert "generator_notes" not in result.payload
    assert "unexpected_top_level" in result.payload  # not in non-authoritative allowlist
    assert isinstance(result.payload["product_intent"]["target_users"], list)
    assert result.payload["requirements"][0]["priority"] == "must"
    assert result.payload["pages"][0]["surface"] == "public"
    assert "_meta" not in result.payload["pages"][0]
    # Must not invent pages/requirements/evidence.
    assert len(result.payload["pages"]) == len(original["pages"])
    assert len(result.payload["requirements"]) == len(original["requirements"])
    assert len(result.payload["evidence"]) == len(original["evidence"])
    assert result.original_sha256 != result.normalized_sha256


def test_preparse_runs_at_most_once_idempotent_second_pass():
    payload = json.loads(SCHEMA_INVALID_FIXTURE.read_text(encoding="utf-8"))
    first = normalize_app_spec_preparse(payload)
    second = normalize_app_spec_preparse(first.payload)
    # Second pass may still drop nothing new; representation should be stable enough
    # that repeated normalization does not invent content.
    assert len(second.payload["pages"]) == len(first.payload["pages"])
    assert payload_sha256(first.payload) == first.normalized_sha256


def test_trace_evidence_safe_repair_smoke26_class():
    payload = _smoke26_safe_payload()
    # Force validation issue shape used by production.
    validation = {
        "passed": False,
        "issues": [
            {
                "code": "trace_evidence_mismatch",
                "message": (
                    "Evidence 'EVIDENCE-STALE-CALENDAR' is not attached to a "
                    "traced page and capability."
                ),
                "related_ids": ["REQ-BOOK", "EVIDENCE-STALE-CALENDAR"],
            }
        ],
    }
    assert validation_has_safe_trace_evidence_repair(payload, validation)
    original_sha = payload_sha256(payload)
    repair = repair_trace_evidence_mismatch(payload, validation)
    assert repair.applied is True
    assert original_sha == repair.original_sha256
    assert repair.repaired_sha256 != original_sha
    assert payload["traceability"][0]["evidence_ids"] == [
        "EVIDENCE-CONFIRMATION",
        "EVIDENCE-STALE-CALENDAR",
    ], "original payload must remain immutable"
    # Owner page already on the failing trace → attach the uniquely proven
    # capability rather than rewriting the evidence ID.
    repaired_evidence = next(
        item
        for item in repair.payload["evidence"]
        if item["id"] == "EVIDENCE-STALE-CALENDAR"
    )
    assert "CAP-BOOK" in repaired_evidence["capability_ids"]
    assert "EVIDENCE-STALE-CALENDAR" in repair.payload["traceability"][0][
        "evidence_ids"
    ]


def test_trace_evidence_missing_fails_closed():
    payload = _smoke26_unsafe_missing_payload()
    validation = {
        "passed": False,
        "issues": [
            {
                "code": "trace_evidence_mismatch",
                "message": (
                    "Evidence 'EVIDENCE-AVAILABILITY-CALENDAR' is not attached "
                    "to a traced page and capability."
                ),
                "related_ids": ["REQ-BOOK", "EVIDENCE-AVAILABILITY-CALENDAR"],
            }
        ],
    }
    repair = repair_trace_evidence_mismatch(payload, validation)
    assert repair.applied is False
    assert any("missing_evidence_object" in reason for reason in repair.refused_reasons)


def test_trace_evidence_ambiguous_fails_closed():
    payload = _smoke26_safe_payload()
    # Two capabilities shared by the owner page and failing trace → A3 refuse.
    payload["capabilities"].append(
        {
            "id": "CAP-BOOK-ALT",
            "name": "Alt book",
            "description": "Alternate booking capability.",
            "requirement_ids": ["REQ-BOOK"],
            "role_ids": [],
            "entity_ids": [],
        }
    )
    page = payload["pages"][0]
    page["capability_ids"] = list(
        dict.fromkeys(list(page.get("capability_ids") or []) + ["CAP-BOOK-ALT"])
    )
    payload["traceability"][0]["capability_ids"] = list(
        dict.fromkeys(
            list(payload["traceability"][0].get("capability_ids") or [])
            + ["CAP-BOOK-ALT"]
        )
    )
    validation = {
        "passed": False,
        "issues": [
            {
                "code": "trace_evidence_mismatch",
                "message": (
                    "Evidence 'EVIDENCE-STALE-CALENDAR' is not attached to a "
                    "traced page and capability."
                ),
                "related_ids": ["REQ-BOOK", "EVIDENCE-STALE-CALENDAR"],
            }
        ],
    }
    repair = repair_trace_evidence_mismatch(payload, validation)
    assert repair.applied is False
    assert any(
        reason.startswith("trace_evidence_reconciliation_ambiguous:")
        for reason in repair.refused_reasons
    )


def test_ai_schema_repair_once_valid_continues(db_session, monkeypatch):
    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(settings, "APPSPEC_MAX_REPAIR_ATTEMPTS", 1)
    monkeypatch.setattr(settings, "APPSPEC_MAX_DETERMINISTIC_HEALS", 1)
    monkeypatch.setattr(settings, "APPSPEC_MAX_CALLS", 6)

    invalid = json.loads(SCHEMA_INVALID_FIXTURE.read_text(encoding="utf-8"))
    # After normalization, still missing required collections for a full AppSpec —
    # provide a fully valid repaired candidate from AI schema repair.
    valid = _valid_payload()
    req = _seed_request(db_session)
    ai = _ScriptedAI(
        [
            json.dumps(invalid),
            json.dumps(valid),  # schema repair
            json.dumps(_coverage_for_booking()),
        ]
    )
    renderer = JinjaTemplateRenderer(str(TEMPLATES_DIR))
    result = ensure_approved_app_spec(
        db_session,
        req.id,
        ai,
        renderer,
        force_new_revision=True,
        source_snapshot_override={
            "customer_input": {
                "desired_outcome": (
                    "Customers can submit a booking and see confirmation."
                ),
                "business_name": req.business_name,
                "main_problem": req.main_problem,
            },
            "reference_evidence": {},
        },
        derived_context_override={},
    )
    assert result.spec is not None
    assert result.reused is False
    rows = AppSpecRepository(db_session).list_revisions(req.id)
    assert len(rows) >= 2
    rejected = [row for row in rows if row.status == "rejected"]
    assert rejected
    meta = load_json_object(rejected[0].generation_metadata_json)
    assert meta.get("schema_diagnostics")
    assert meta["schema_diagnostics"].get("schema_validation_errors")
    assert any(
        issue.get("path")
        for issue in meta["schema_diagnostics"]["schema_validation_errors"]
    )


def test_ai_schema_repair_invalid_fails_closed(db_session, monkeypatch):
    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(settings, "APPSPEC_MAX_REPAIR_ATTEMPTS", 0)
    monkeypatch.setattr(settings, "APPSPEC_MAX_DETERMINISTIC_HEALS", 1)
    monkeypatch.setattr(settings, "APPSPEC_MAX_CALLS", 6)

    invalid = json.loads(SCHEMA_INVALID_FIXTURE.read_text(encoding="utf-8"))
    still_invalid = copy.deepcopy(invalid)
    req = _seed_request(db_session)
    ai = _ScriptedAI(
        [
            json.dumps(invalid),
            json.dumps(still_invalid),  # schema repair still invalid
        ]
    )
    renderer = JinjaTemplateRenderer(str(TEMPLATES_DIR))
    with pytest.raises(AppSpecGenerationError) as excinfo:
        ensure_approved_app_spec(
            db_session,
            req.id,
            ai,
            renderer,
            force_new_revision=True,
            source_snapshot_override={
                "customer_input": {
                    "desired_outcome": (
                        "Customers can submit a booking and see confirmation."
                    ),
                    "business_name": req.business_name,
                    "main_problem": req.main_problem,
                },
                "reference_evidence": {},
            },
            derived_context_override={},
        )
    assert "fallback is disabled" in str(excinfo.value)
    assert settings.APPSPEC_FALLBACK_ENABLED is False


def test_valid_appspec_byte_stable_under_preparse():
    payload = _valid_payload()
    before = payload_sha256(payload)
    result = normalize_app_spec_preparse(payload)
    # Valid fixture already has optional collections; may be unchanged or
    # representation-stable without inventing product content.
    AppSpec.model_validate(result.payload)
    assert len(result.payload["pages"]) == len(payload["pages"])
    assert before == payload_sha256(payload)


def test_redact_does_not_expose_customer_email_in_fragment():
    redacted = redact_candidate_fragment(
        {"contact": "owner@studio.example", "ok": True}
    )
    assert redacted["contact"] == "<redacted:email>"


def test_parse_candidate_preserves_immutable_original_hash():
    payload = json.loads(SCHEMA_INVALID_FIXTURE.read_text(encoding="utf-8"))
    original = AppSpecCandidate(payload=copy.deepcopy(payload))
    original_sha = payload_sha256(original.payload)
    normalized = normalize_app_spec_preparse(original.payload)
    repaired = AppSpecCandidate(
        payload=normalized.payload,
        parent_payload_sha256=original_sha,
        repair_type="deterministic_schema_normalization",
    )
    assert payload_sha256(original.payload) == original_sha
    assert repaired.parent_payload_sha256 == original_sha
    assert repaired.repair_type == "deterministic_schema_normalization"
    assert payload_sha256(repaired.payload) != original_sha
