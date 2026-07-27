"""Request 42: evidence listed on a navigation trace without capability attachment."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.appspec.builder import parse_app_spec_candidate
from app.core.config import settings
from app.domain.appspec.sanitize.trace_evidence_repair import (
    repair_trace_evidence_mismatch,
    validation_has_safe_trace_evidence_repair,
)
from app.domain.appspec.validation import validate_app_spec

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "app_spec"
    / "request42_trace_evidence_mismatch.json"
)

REQUEST42_BOOKING_EVIDENCE = (
    "EVIDENCE-BOOKING-CALENDAR",
    "EVIDENCE-BOOKING-CUSTOMER-FORM",
    "EVIDENCE-BOOKING-SUBMIT-BUTTON",
)


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _mismatch_issues(report) -> list:
    return [
        issue
        for issue in report.issues
        if issue.code == "trace_evidence_mismatch"
    ]


def _validation_payload(report) -> dict:
    return {
        "passed": report.is_valid,
        "issues": [
            {
                "code": issue.code,
                "message": issue.message,
                "path": list(issue.path),
                "related_ids": list(issue.related_ids),
            }
            for issue in report.issues
        ],
    }


def _single_mismatch_validation(requirement_id: str, evidence_id: str) -> dict:
    return {
        "passed": False,
        "issues": [
            {
                "code": "trace_evidence_mismatch",
                "message": (
                    f"Evidence '{evidence_id}' is not attached to a "
                    "traced page and capability."
                ),
                "related_ids": [requirement_id, evidence_id],
            }
        ],
    }


def test_request42_reproduces_trace_evidence_mismatch_before_reconciliation() -> None:
    payload = _load_fixture()
    report = validate_app_spec(parse_app_spec_candidate(payload))
    mismatches = _mismatch_issues(report)
    assert len(mismatches) == 7
    related = {
        issue.related_ids[1]
        for issue in mismatches
        if len(issue.related_ids) > 1
    }
    assert set(REQUEST42_BOOKING_EVIDENCE) <= related
    for evidence_id in REQUEST42_BOOKING_EVIDENCE:
        evidence = next(
            item for item in payload["evidence"] if item["id"] == evidence_id
        )
        assert evidence["page_id"] == "PAGE-BOOKING"
        assert "CAP-NAVIGATE" not in evidence["capability_ids"]
        page = next(item for item in payload["pages"] if item["id"] == "PAGE-BOOKING")
        assert evidence_id in page["evidence_ids"]
        # Exact missing backlink: evidence → CAP-NAVIGATE on REQ-NAVIGATION-001.
        nav = next(
            item
            for item in payload["traceability"]
            if item["requirement_id"] == "REQ-NAVIGATION-001"
        )
        assert evidence_id in nav["evidence_ids"]
        assert "PAGE-BOOKING" in nav["page_ids"]
        assert nav["capability_ids"] == ["CAP-NAVIGATE"]


def test_request42_reconciliation_attaches_unique_navigate_capability() -> None:
    payload = _load_fixture()
    before = validate_app_spec(parse_app_spec_candidate(payload))
    validation = _validation_payload(before)
    assert validation_has_safe_trace_evidence_repair(payload, validation)

    original = copy.deepcopy(payload)
    repair = repair_trace_evidence_mismatch(payload, validation)
    assert repair.applied is True
    assert repair.refused_reasons == []
    assert repair.original_sha256 != repair.repaired_sha256
    assert payload == original
    assert all(
        action.startswith("add_capability_to_evidence:") for action in repair.actions
    )

    nav = next(
        item
        for item in repair.payload["traceability"]
        if item["requirement_id"] == "REQ-NAVIGATION-001"
    )
    for evidence_id in REQUEST42_BOOKING_EVIDENCE:
        assert evidence_id in nav["evidence_ids"]
        evidence = next(
            item for item in repair.payload["evidence"] if item["id"] == evidence_id
        )
        assert "CAP-NAVIGATE" in evidence["capability_ids"]
        assert evidence["page_id"] == "PAGE-BOOKING"

    after = validate_app_spec(parse_app_spec_candidate(repair.payload))
    assert after.is_valid
    assert _mismatch_issues(after) == []
    booking = {
        item["evidence_id"]: item
        for item in repair.reconciliations
        if item["evidence_id"] in REQUEST42_BOOKING_EVIDENCE
    }
    assert set(booking) == set(REQUEST42_BOOKING_EVIDENCE)
    for item in booking.values():
        assert item["page_id"] == "PAGE-BOOKING"
        assert item["capability_id"] == "CAP-NAVIGATE"
        assert item["links_added"] == ["evidence_capability"]
        assert item["before_sha256"] == repair.original_sha256
        assert item["after_sha256"] == repair.repaired_sha256


def test_missing_capability_backlink_with_existing_page_membership() -> None:
    payload = _load_fixture()
    evidence_id = "EVIDENCE-BOOKING-CALENDAR"
    page = next(item for item in payload["pages"] if item["id"] == "PAGE-BOOKING")
    assert evidence_id in page["evidence_ids"]
    repair = repair_trace_evidence_mismatch(
        payload,
        _single_mismatch_validation("REQ-NAVIGATION-001", evidence_id),
    )
    assert repair.applied is True
    repaired = next(
        item for item in repair.payload["evidence"] if item["id"] == evidence_id
    )
    assert "CAP-NAVIGATE" in repaired["capability_ids"]
    assert repair.reconciliations[0]["links_added"] == ["evidence_capability"]


def test_missing_page_backlink_with_unique_proven_capability() -> None:
    payload = _load_fixture()
    evidence_id = "EVIDENCE-BOOKING-CALENDAR"
    page = next(item for item in payload["pages"] if item["id"] == "PAGE-BOOKING")
    page["evidence_ids"] = [
        item for item in page["evidence_ids"] if item != evidence_id
    ]
    repair = repair_trace_evidence_mismatch(
        payload,
        _single_mismatch_validation("REQ-NAVIGATION-001", evidence_id),
    )
    assert repair.applied is True
    repaired_page = next(
        item for item in repair.payload["pages"] if item["id"] == "PAGE-BOOKING"
    )
    repaired_evidence = next(
        item for item in repair.payload["evidence"] if item["id"] == evidence_id
    )
    assert evidence_id in repaired_page["evidence_ids"]
    assert "CAP-NAVIGATE" in repaired_evidence["capability_ids"]
    assert set(repair.reconciliations[0]["links_added"]) == {
        "evidence_capability",
        "page_evidence",
    }


def test_both_backlinks_missing_with_uniquely_proven_trace() -> None:
    payload = _load_fixture()
    evidence_id = "EVIDENCE-BOOKING-SUBMIT-BUTTON"
    evidence = next(item for item in payload["evidence"] if item["id"] == evidence_id)
    evidence["capability_ids"] = ["CAP-SUBMIT-BOOKING"]
    page = next(item for item in payload["pages"] if item["id"] == "PAGE-BOOKING")
    page["evidence_ids"] = [
        item for item in page["evidence_ids"] if item != evidence_id
    ]
    repair = repair_trace_evidence_mismatch(
        payload,
        _single_mismatch_validation("REQ-NAVIGATION-001", evidence_id),
    )
    assert repair.applied is True
    repaired_evidence = next(
        item for item in repair.payload["evidence"] if item["id"] == evidence_id
    )
    repaired_page = next(
        item for item in repair.payload["pages"] if item["id"] == "PAGE-BOOKING"
    )
    assert "CAP-NAVIGATE" in repaired_evidence["capability_ids"]
    assert evidence_id in repaired_page["evidence_ids"]


def test_complete_trace_remains_byte_stable() -> None:
    payload = _load_fixture()
    repaired = repair_trace_evidence_mismatch(
        payload,
        _validation_payload(validate_app_spec(parse_app_spec_candidate(payload))),
    ).payload
    report = validate_app_spec(parse_app_spec_candidate(repaired))
    assert report.is_valid
    again = repair_trace_evidence_mismatch(repaired, _validation_payload(report))
    assert again.applied is False
    assert again.payload == repaired


def test_request42_reconciliation_is_idempotent() -> None:
    payload = _load_fixture()
    first = repair_trace_evidence_mismatch(
        payload,
        _validation_payload(validate_app_spec(parse_app_spec_candidate(payload))),
    )
    second = repair_trace_evidence_mismatch(
        first.payload,
        _validation_payload(
            validate_app_spec(parse_app_spec_candidate(first.payload))
        ),
    )
    assert first.applied is True
    assert second.applied is False
    assert first.repaired_sha256 == second.original_sha256


def test_conflicting_mapping_fails_closed() -> None:
    payload = _load_fixture()
    evidence = next(
        item for item in payload["evidence"] if item["id"] == "EVIDENCE-BOOKING-CALENDAR"
    )
    # Keep page ownership, but remove the uniquely proven navigate capability
    # from the page so the page↔trace pair no longer proves CAP-NAVIGATE.
    page = next(item for item in payload["pages"] if item["id"] == "PAGE-BOOKING")
    page["capability_ids"] = [
        item for item in page["capability_ids"] if item != "CAP-NAVIGATE"
    ]
    repair = repair_trace_evidence_mismatch(
        payload,
        _single_mismatch_validation("REQ-NAVIGATION-001", evidence["id"]),
    )
    assert repair.applied is False
    assert any(
        reason.startswith("trace_evidence_reconciliation_ambiguous:")
        for reason in repair.refused_reasons
    )


def test_multiple_possible_capabilities_fail_closed() -> None:
    payload = _load_fixture()
    nav = next(
        item
        for item in payload["traceability"]
        if item["requirement_id"] == "REQ-NAVIGATION-001"
    )
    nav["capability_ids"] = ["CAP-NAVIGATE", "CAP-SUBMIT-BOOKING"]
    evidence = next(
        item for item in payload["evidence"] if item["id"] == "EVIDENCE-BOOKING-CALENDAR"
    )
    evidence["capability_ids"] = ["CAP-SELECT-AVAILABILITY"]
    repair = repair_trace_evidence_mismatch(
        payload,
        _single_mismatch_validation("REQ-NAVIGATION-001", evidence["id"]),
    )
    assert repair.applied is False
    assert any(
        reason.startswith("trace_evidence_reconciliation_ambiguous:")
        for reason in repair.refused_reasons
    )


def test_multiple_possible_pages_fail_closed() -> None:
    payload = _load_fixture()
    evidence = next(
        item for item in payload["evidence"] if item["id"] == "EVIDENCE-BOOKING-CALENDAR"
    )
    # Clear ownership: without an explicit page_id, do not invent PAGE-BOOKING
    # from the evidence id wording.
    evidence["page_id"] = ""
    repair = repair_trace_evidence_mismatch(
        payload,
        _single_mismatch_validation("REQ-NAVIGATION-001", evidence["id"]),
    )
    assert repair.applied is False
    assert repair.refused_reasons


def test_no_inference_from_evidence_id_wording() -> None:
    payload = _load_fixture()
    evidence = next(
        item for item in payload["evidence"] if item["id"] == "EVIDENCE-BOOKING-CALENDAR"
    )
    evidence["page_id"] = "PAGE-HOME"
    home = next(item for item in payload["pages"] if item["id"] == "PAGE-HOME")
    if "EVIDENCE-BOOKING-CALENDAR" not in home["evidence_ids"]:
        home["evidence_ids"] = list(home["evidence_ids"]) + [
            "EVIDENCE-BOOKING-CALENDAR"
        ]
    repair = repair_trace_evidence_mismatch(
        payload,
        _single_mismatch_validation("REQ-NAVIGATION-001", evidence["id"]),
    )
    assert repair.applied is True
    repaired = next(
        item
        for item in repair.payload["evidence"]
        if item["id"] == "EVIDENCE-BOOKING-CALENDAR"
    )
    assert repaired["page_id"] == "PAGE-HOME"
    assert repaired["page_id"] != "PAGE-BOOKING"


def test_unknown_evidence_remains_failure() -> None:
    payload = _load_fixture()
    repair = repair_trace_evidence_mismatch(
        payload,
        _single_mismatch_validation("REQ-NAVIGATION-001", "EVIDENCE-DOES-NOT-EXIST"),
    )
    assert repair.applied is False
    assert any("missing_evidence_object" in reason for reason in repair.refused_reasons)


def test_appspec_fallback_remains_disabled() -> None:
    assert settings.APPSPEC_FALLBACK_ENABLED is False
