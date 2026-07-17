"""Executable PR1 contract tests for the canonical AppSpec and validator."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from pydantic import ValidationError


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.domain.appspec.validation import (  # noqa: E402
    app_spec_sha256,
    canonical_app_spec_json,
    validate_app_spec,
)
from app.domain.schemas.app_spec import AppSpec  # noqa: E402


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "app_spec" / "valid_booking.json"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _codes(payload: dict) -> set[str]:
    return {issue.code for issue in validate_app_spec(AppSpec.model_validate(payload)).issues}


def test_valid_fixture_and_stable_serialization() -> None:
    payload = _payload()
    spec = AppSpec.model_validate(payload)
    report = validate_app_spec(spec)
    assert report.is_valid is True, report.model_dump(mode="json")
    assert report.passed is True
    assert report.issues == ()
    canonical = canonical_app_spec_json(spec)
    assert canonical == canonical_app_spec_json(AppSpec.model_validate(json.loads(canonical)))
    assert app_spec_sha256(spec) == app_spec_sha256(AppSpec.model_validate(payload))
    assert len(app_spec_sha256(spec)) == 64


def test_schema_is_versioned_strict_and_has_no_design_fields() -> None:
    payload = _payload()
    payload["schema_version"] = "2.0"
    try:
        AppSpec.model_validate(payload)
    except ValidationError:
        pass
    else:
        raise AssertionError("unsupported schema version was accepted")

    payload = _payload()
    payload["pages"][0]["skeleton_id"] = "marketing-shell"
    try:
        AppSpec.model_validate(payload)
    except ValidationError:
        pass
    else:
        raise AssertionError("design-only Page field was accepted")

    payload = _payload()
    payload["pages"][0]["primary"] = "true"
    try:
        AppSpec.model_validate(payload)
    except ValidationError:
        pass
    else:
        raise AssertionError("coercive boolean was accepted")

    payload = _payload()
    del payload["requirements"][0]["verification_mode"]
    try:
        AppSpec.model_validate(payload)
    except ValidationError:
        pass
    else:
        raise AssertionError("requirement without verification_mode was accepted")

    payload = _payload()
    payload["requirements"][0]["source_refs"] = []
    try:
        AppSpec.model_validate(payload)
    except ValidationError:
        pass
    else:
        raise AssertionError("requirement without source_refs was accepted")

    payload = _payload()
    payload["requirements"][0]["source_refs"] = [
        "derived_context.mvp_blueprint"
    ]
    try:
        AppSpec.model_validate(payload)
    except ValidationError:
        pass
    else:
        raise AssertionError("derived analysis was accepted as authoritative source")


def test_global_ids_are_unique_case_insensitively() -> None:
    payload = _payload()
    payload["capabilities"][0]["id"] = "req-book"
    payload["pages"][0]["capability_ids"] = ["req-book"]
    payload["actions"][0]["capability_ids"] = ["req-book"]
    for item in payload["evidence"]:
        item["capability_ids"] = ["req-book"]
    payload["traceability"][0]["capability_ids"] = ["req-book"]
    assert "duplicate_global_id" in _codes(payload)


def test_broken_references_graph_and_journey_are_rejected() -> None:
    payload = _payload()
    payload["roles"][0]["default_page_id"] = "page-book"
    payload["states"][0]["terminal"] = True
    payload["transitions"][0]["from_state_id"] = "STATE-CONFIRMED"
    codes = _codes(payload)
    assert "reference_case_mismatch" in codes
    assert "journey_step_chain_broken" in codes
    assert "nonterminal_state_dead_end" not in codes


def test_effect_types_and_traceability_are_enforced() -> None:
    payload = _payload()
    payload["entities"][0]["fields"][0]["type"] = "integer"
    payload["entities"][0]["fields"][0]["enum_values"] = []
    payload["transitions"][0]["effects"][0]["value"] = "not-a-number"
    assert "set_effect_type_mismatch" in _codes(payload)

    payload = _payload()
    payload["traceability"] = []
    payload["deferred_scope"] = [
        {
            "id": "DEFER-BOOK",
            "name": "Later booking",
            "description": "Move booking to a future release.",
            "reason": "The dependency is not currently available.",
            "requirement_ids": ["REQ-BOOK"],
            "target_release": "Later",
        }
    ]
    codes = _codes(payload)
    assert "must_requirement_cannot_be_deferred" in codes


def test_reports_are_deterministic_and_block_open_questions() -> None:
    payload = _payload()
    payload["open_questions"] = [
        {
            "id": "QUESTION-PAYMENT",
            "question": "Which payment provider is approved?",
            "rationale": "Integration behavior depends on this decision.",
            "blocking": True,
        }
    ]
    spec = AppSpec.model_validate(payload)
    first = validate_app_spec(spec)
    second = validate_app_spec(spec)
    assert first == second
    assert first.is_valid is False
    assert "blocking_open_question" in {issue.code for issue in first.issues}
    dumped = first.model_dump(mode="json")
    assert dumped["is_valid"] is False
    assert "passed" not in dumped


def main() -> None:
    tests = (
        test_valid_fixture_and_stable_serialization,
        test_schema_is_versioned_strict_and_has_no_design_fields,
        test_global_ids_are_unique_case_insensitively,
        test_broken_references_graph_and_journey_are_rejected,
        test_effect_types_and_traceability_are_enforced,
        test_reports_are_deterministic_and_block_open_questions,
    )
    for test in tests:
        test()
    print(f"AppSpec contract tests passed ({len(tests)} tests)")


if __name__ == "__main__":
    main()
