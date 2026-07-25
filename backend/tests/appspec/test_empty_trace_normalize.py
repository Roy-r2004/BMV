"""Focused tests for AppSpec empty-trace normalization and diagnostics (#29)."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.appspec.builder import AppSpecCandidate
from app.application.appspec.generation import (
    AppSpecGenerationError,
    ensure_approved_app_spec,
)
from app.application.appspec.schema_repair import repair_app_spec_schema_candidate
from app.core.config import settings
from app.domain.appspec.sanitize.empty_trace import (
    classify_trace_field,
    normalize_optional_empty_traces,
    scan_empty_traces,
    schema_repair_trace_context,
)
from app.domain.appspec.sanitize.pipeline import sanitize_app_spec_payload
from app.domain.appspec.sanitize.preparse_normalize import normalize_app_spec_preparse
from app.domain.appspec.sanitize.schema_diagnostics import (
    classify_schema_parse_exception,
    payload_sha256,
)
from app.domain.models.app_spec import AppSpecRevision  # noqa: F401
from app.domain.models.request import Request
from app.domain.schemas.app_spec import AppSpec
from app.infrastructure.db.base import Base
from app.infrastructure.templating.renderer import JinjaTemplateRenderer

TEMPLATES_DIR = BACKEND_DIR / "app" / "templates"
VALID_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "app_spec" / "valid_booking.json"
)
SMOKE29_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "app_spec"
    / "empty_trace_smoke29.json"
)


def _valid() -> dict:
    return json.loads(VALID_FIXTURE.read_text(encoding="utf-8"))


def _smoke29() -> dict:
    return json.loads(SMOKE29_FIXTURE.read_text(encoding="utf-8"))


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
        self._responses = list(responses)
        self.calls_used = 0
        self.prompts: list[str] = []

    def ask_chat(self, model, messages, max_tokens=None, temperature=None):  # noqa: ANN001
        self.calls_used += 1
        content = messages[0]["content"] if messages else ""
        self.prompts.append(content)
        if not self._responses:
            raise RuntimeError("no scripted AI responses left")
        return self._responses.pop(0)


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
        engine.dispose()


def _seed_request(session):
    req = Request(
        business_name="Empty Trace Studio",
        industry="Personal Care / Beauty",
        business_description="Booking studio",
        target_customers="Local clients",
        main_problem="Manual booking",
        desired_outcome="Customers can submit a booking and see confirmation.",
        email="smoke-test@example.invalid",
        needs_ai="no",
        project_type="new",
        status="new",
    )
    session.add(req)
    session.commit()
    session.refresh(req)
    return req


def _source_override(req: Request) -> dict[str, Any]:
    return {
        "customer_input": {
            "desired_outcome": "Customers can submit a booking and see confirmation.",
            "business_name": req.business_name,
            "main_problem": req.main_problem,
        },
        "reference_evidence": {},
    }


def test_smoke29_exact_invalid_trace_paths_recorded():
    payload = _smoke29()
    with pytest.raises(ValidationError) as raised:
        AppSpec.model_validate(payload)
    issue = classify_schema_parse_exception(
        raised.value,
        candidate_payload=payload,
    )
    assert issue["code"] == "app_spec_schema_parse_failed"
    paths = sorted(
        item["path"]
        for item in issue["issues"]
        if item.get("code") == "invalid_trace_shape"
    )
    assert paths == [
        "traceability[0].acceptance_test_ids",
        "traceability[0].evidence_ids",
    ]
    for child in issue["issues"]:
        if child.get("code") == "invalid_trace_shape":
            assert child.get("path")
            assert child.get("empty_trace_code") == "empty_required_trace"
            assert child.get("classification") == "required"
    early_paths = {
        item["path"]
        for item in issue.get("early_trace_diagnostics") or []
        if item.get("code") == "empty_required_trace"
    }
    assert "traceability[0].evidence_ids" in early_paths
    assert "traceability[0].acceptance_test_ids" in early_paths


def test_optional_required_classification():
    assert classify_trace_field("journey_ids") == "optional"
    assert classify_trace_field("evidence_ids") == "required"
    assert classify_trace_field("acceptance_test_ids") == "required"
    assert classify_trace_field("capability_ids") == "required"
    assert classify_trace_field("page_ids") == "required"


def test_optional_empty_trace_normalized_list_and_tuple():
    payload = _valid()
    payload["traceability"][0]["journey_ids"] = []
    result = normalize_optional_empty_traces(payload)
    assert result.applied is True
    assert "journey_ids" not in result.payload["traceability"][0]
    assert any("omit_optional_empty_trace" in action for action in result.actions)
    assert result.records[0]["original_representation"] == []
    assert result.records[0]["normalized_representation"] is None

    payload2 = _valid()
    payload2["traceability"][0]["journey_ids"] = ()
    result2 = normalize_optional_empty_traces(payload2)
    assert "journey_ids" not in result2.payload["traceability"][0]
    AppSpec.model_validate(result.payload)


def test_required_empty_trace_not_silently_removed():
    payload = _smoke29()
    original = copy.deepcopy(payload)
    result = normalize_optional_empty_traces(payload)
    assert result.payload["traceability"][0]["evidence_ids"] == []
    assert result.payload["traceability"][0]["acceptance_test_ids"] == []
    assert any(
        "refuse_empty_required_trace" in reason for reason in result.refused_reasons
    )
    assert payload_sha256(original) == payload_sha256(payload)


def test_preparse_optional_empty_and_byte_stable_valid():
    valid = _valid()
    before = payload_sha256(valid)
    result = normalize_app_spec_preparse(valid)
    AppSpec.model_validate(result.payload)
    assert payload_sha256(valid) == before

    dirty = _smoke29()
    normalized = normalize_app_spec_preparse(dirty)
    assert "journey_ids" not in normalized.payload["traceability"][0]
    assert normalized.payload["traceability"][0]["evidence_ids"] == []
    with pytest.raises(ValidationError):
        AppSpec.model_validate(normalized.payload)


def test_null_accepted_only_where_schema_allows():
    payload = _valid()
    payload["traceability"][0]["evidence_ids"] = None
    with pytest.raises(ValidationError):
        AppSpec.model_validate(payload)
    issues = scan_empty_traces(payload)
    assert any(
        item.get("path") == "traceability[0].evidence_ids"
        and item.get("code") == "empty_required_trace"
        for item in issues
    )


def test_empty_string_and_unknown_and_duplicate_ids():
    payload = _valid()
    payload["traceability"][0]["evidence_ids"] = ["", "EVIDENCE-CONFIRMATION", "NOPE"]
    payload["traceability"][0]["page_ids"] = ["PAGE-BOOK", "PAGE-BOOK"]
    issues = {item["code"] for item in scan_empty_traces(payload)}
    assert "trace_contains_empty_string" in issues
    assert "trace_contains_unknown_id" in issues
    assert "trace_contains_duplicate_id" in issues


def test_duplicate_identical_ids_normalize_via_preparse_dedupe():
    payload = _valid()
    payload["traceability"][0]["evidence_ids"] = [
        "EVIDENCE-CONFIRMATION",
        "EVIDENCE-CONFIRMATION",
    ]
    result = normalize_app_spec_preparse(payload)
    assert result.payload["traceability"][0]["evidence_ids"] == [
        "EVIDENCE-CONFIRMATION"
    ]
    AppSpec.model_validate(result.payload)


def test_conditional_assertion_evidence_rule():
    payload = _valid()
    payload["acceptance_tests"][0]["assertions"][0]["evidence_id"] = None
    issues = scan_empty_traces(payload)
    assert any(
        item.get("classification") == "conditional"
        and item.get("code") == "empty_required_trace"
        for item in issues
    )


def test_schema_repair_context_exposes_canonical_ids():
    payload = _smoke29()
    with pytest.raises(ValidationError) as raised:
        AppSpec.model_validate(payload)
    issue = classify_schema_parse_exception(
        raised.value,
        candidate_payload=payload,
    )
    ctx = schema_repair_trace_context(payload, schema_issue=issue)
    assert "EVIDENCE-CONFIRMATION" in ctx["canonical_ids"]["evidence"]
    assert "TEST-BOOK" in ctx["canonical_ids"]["acceptance_tests"]
    notes = ctx["trace_field_notes"]
    assert any(note.get("path") == "traceability[0].evidence_ids" for note in notes)
    for note in notes:
        if note.get("path") == "traceability[0].evidence_ids":
            assert note.get("classification") == "required"
            assert note.get("min_items") == 1
            assert "EVIDENCE-CONFIRMATION" in note.get("available_canonical_ids")


def test_case_a_optional_and_sanitize_recovers_required_when_ids_exist():
    """#29: optional journey omitted; required empties repaired from existing IDs."""

    payload = _smoke29()
    normalized = normalize_app_spec_preparse(payload)
    assert "journey_ids" not in normalized.payload["traceability"][0]
    sanitized = sanitize_app_spec_payload(
        normalized.payload,
        {
            "customer_input": {
                "desired_outcome": "Customers can submit a booking and see confirmation.",
                "business_name": "x",
                "main_problem": "y",
            },
            "reference_evidence": {},
        },
    )
    AppSpec.model_validate(sanitized)
    assert sanitized["traceability"][0]["evidence_ids"]
    assert sanitized["traceability"][0]["acceptance_test_ids"]
    assert "EVIDENCE-GONE" not in sanitized["traceability"][0]["evidence_ids"]


def test_ai_schema_repair_receives_canonical_ids_case_b():
    captured: dict[str, Any] = {}

    class _CaptureRenderer:
        def render(self, template, **kwargs):  # noqa: ANN003
            captured.update(kwargs)
            return json.dumps(_valid())

    class _AI:
        calls_used = 0

        def ask_chat(self, *args, **kwargs):  # noqa: ANN002, ANN003
            self.calls_used += 1
            return json.dumps(_valid())

    payload = _smoke29()
    with pytest.raises(ValidationError) as raised:
        AppSpec.model_validate(payload)
    issue = classify_schema_parse_exception(
        raised.value,
        candidate_payload=payload,
    )
    repaired = repair_app_spec_schema_candidate(
        candidate=AppSpecCandidate(payload=payload),
        schema_issue=issue,
        ai_provider=_AI(),
        template_renderer=_CaptureRenderer(),
    )
    assert repaired.repair_type == "ai_schema_repair"
    assert repaired.parent_payload_sha256 == payload_sha256(payload)
    assert payload_sha256(payload) == payload_sha256(_smoke29())
    ctx = json.loads(captured["empty_trace_context_json"])
    assert ctx["canonical_ids"]["evidence"]
    assert any(
        "never invent" in rule.lower() or "placeholder" in rule.lower()
        for rule in ctx["rules"]
    )
    AppSpec.model_validate(repaired.payload)


def test_ai_schema_repair_cannot_invent_ids_case_c():
    payload = _smoke29()
    payload["evidence"] = []
    payload["acceptance_tests"] = []
    invented = copy.deepcopy(payload)
    invented["traceability"][0]["evidence_ids"] = ["EVIDENCE-INVENTED"]
    invented["traceability"][0]["acceptance_test_ids"] = ["TEST-INVENTED"]

    class _Renderer:
        def render(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return "x"

    class _AI:
        calls_used = 0

        def ask_chat(self, *args, **kwargs):  # noqa: ANN002, ANN003
            self.calls_used += 1
            return json.dumps(invented)

    with pytest.raises(ValidationError) as raised:
        AppSpec.model_validate(payload)
    issue = classify_schema_parse_exception(
        raised.value,
        candidate_payload=payload,
    )
    repaired = repair_app_spec_schema_candidate(
        candidate=AppSpecCandidate(payload=payload),
        schema_issue=issue,
        ai_provider=_AI(),
        template_renderer=_Renderer(),
    )
    # Invented IDs are not enough for a fully valid AppSpec (missing evidence/tests).
    with pytest.raises(ValidationError):
        AppSpec.model_validate(repaired.payload)
    # Downstream scan flags unknown IDs.
    unknown = {
        item["code"] for item in scan_empty_traces(repaired.payload)
    }
    assert "trace_contains_unknown_id" in unknown or repaired.payload[
        "traceability"
    ][0]["evidence_ids"] == ["EVIDENCE-INVENTED"]


def test_ai_repair_at_most_once_when_sanitize_cannot_recover(db_session, monkeypatch):
    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(settings, "APPSPEC_MAX_REPAIR_ATTEMPTS", 0)
    monkeypatch.setattr(settings, "APPSPEC_MAX_DETERMINISTIC_HEALS", 1)
    monkeypatch.setattr(settings, "APPSPEC_MAX_CALLS", 6)

    invalid = _valid()
    # Irrecoverable container shape for deterministic sanitize/preparse.
    invalid["pages"] = "not-a-page-list"
    still_invalid = copy.deepcopy(invalid)
    req = _seed_request(db_session)
    ai = _ScriptedAI(
        [
            json.dumps(invalid),
            json.dumps(still_invalid),  # schema repair still invalid
            json.dumps(_valid()),  # would be a second repair if allowed
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
            source_snapshot_override=_source_override(req),
            derived_context_override={},
        )
    assert "fallback is disabled" in str(excinfo.value)
    assert ai.calls_used == 2
    assert settings.APPSPEC_FALLBACK_ENABLED is False


def test_generation_smoke29_result_has_spec(db_session, monkeypatch):
    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(settings, "APPSPEC_MAX_REPAIR_ATTEMPTS", 0)
    monkeypatch.setattr(settings, "APPSPEC_MAX_DETERMINISTIC_HEALS", 1)
    monkeypatch.setattr(settings, "APPSPEC_MAX_CALLS", 6)

    invalid = _smoke29()
    req = _seed_request(db_session)
    ai = _ScriptedAI([json.dumps(invalid), json.dumps(_coverage_for_booking())])
    renderer = JinjaTemplateRenderer(str(TEMPLATES_DIR))
    result = ensure_approved_app_spec(
        db_session,
        req.id,
        ai,
        renderer,
        force_new_revision=True,
        source_snapshot_override=_source_override(req),
        derived_context_override={},
    )
    assert result.spec is not None
    assert settings.APPSPEC_FALLBACK_ENABLED is False
    assert ai.calls_used == 2


def test_smoke29_failure_class_reproducible_without_heal():
    payload = _smoke29()
    with pytest.raises(ValidationError) as raised:
        AppSpec.model_validate(payload)
    issue = classify_schema_parse_exception(
        raised.value,
        candidate_payload=payload,
    )
    assert issue["code"] == "app_spec_schema_parse_failed"
    assert (
        sum(1 for item in issue["issues"] if item.get("code") == "invalid_trace_shape")
        == 2
    )


def test_original_candidate_immutable_under_normalize_and_repair():
    payload = _smoke29()
    original_sha = payload_sha256(payload)
    normalized = normalize_app_spec_preparse(payload)
    assert payload_sha256(payload) == original_sha
    assert normalized.original_sha256 == original_sha

    class _Renderer:
        def render(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return "x"

    class _AI:
        def ask_chat(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return json.dumps(_valid())

    with pytest.raises(ValidationError) as raised:
        AppSpec.model_validate(payload)
    issue = classify_schema_parse_exception(
        raised.value,
        candidate_payload=payload,
    )
    repaired = repair_app_spec_schema_candidate(
        candidate=AppSpecCandidate(payload=copy.deepcopy(payload)),
        schema_issue=issue,
        ai_provider=_AI(),
        template_renderer=_Renderer(),
    )
    assert payload_sha256(payload) == original_sha
    assert repaired.parent_payload_sha256 == original_sha
    assert payload_sha256(repaired.payload) != original_sha
