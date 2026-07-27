"""Request 38: actions.entity_id wrongly holds evidence IDs (missing_reference ×6)."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.appspec.builder import parse_app_spec_candidate
from app.core.config import settings
from app.domain.appspec.sanitize import heal_app_spec_payload, sanitize_app_spec_payload
from app.domain.appspec.sanitize.reference_integrity import (
    reconcile_reference_integrity,
)
from app.domain.appspec.validation import validate_app_spec

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "app_spec"
    / "request38_misplaced_evidence_entity_refs.json"
)

REQUEST38_EVIDENCE_IDS = (
    "EVIDENCE-HOME-BROWSE-BUTTON",
    "EVIDENCE-SERVICE-LIST-ITEMS",
    "EVIDENCE-SERVICE-DETAIL-BOOK-BUTTON",
    "EVIDENCE-BOOKING-CALENDAR",
    "EVIDENCE-BOOKING-FORM-FIELDS",
    "EVIDENCE-BOOKING-SUBMIT-BUTTON",
)


def _source_snapshot() -> dict:
    return {
        "customer_input": {
            "desired_outcome": "A clear five-page booking journey ending in confirmation.",
            "business_description": (
                "Home, Service List, Service Detail, Booking, and Confirmation."
            ),
        },
        "reference_evidence": {},
    }


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _missing_entity_refs(report) -> list:
    return [
        issue
        for issue in report.issues
        if issue.code == "missing_reference"
        and list(issue.path[:1]) == ["actions"]
        and list(issue.path[-1:]) == ["entity_id"]
    ]


def test_request38_fixture_reproduces_six_missing_reference_before_repair() -> None:
    # Raw fixture encodes the production failure shape before integrity repair.
    payload = _load_fixture()
    assert [a.get("entity_id") for a in payload["actions"]] == list(
        REQUEST38_EVIDENCE_IDS
    )
    evidence_ids = {item["id"] for item in payload["evidence"]}
    assert evidence_ids.isdisjoint(REQUEST38_EVIDENCE_IDS)
    spec = parse_app_spec_candidate(payload)
    report = validate_app_spec(spec)
    missing = _missing_entity_refs(report)
    assert len(missing) == 6
    related = {issue.related_ids[0] for issue in missing}
    assert related == set(REQUEST38_EVIDENCE_IDS)


def test_request38_reference_integrity_resolves_all_six_evidence_refs() -> None:
    raw = _load_fixture()
    repaired, result = reconcile_reference_integrity(raw)
    assert result.applied
    assert not result.provider_called
    evidence_ids = {item["id"] for item in repaired["evidence"]}
    for evidence_id in REQUEST38_EVIDENCE_IDS:
        assert evidence_id in evidence_ids
    for action in repaired["actions"]:
        assert action.get("entity_id") not in REQUEST38_EVIDENCE_IDS
        assert action.get("entity_id") is None or not str(
            action.get("entity_id")
        ).upper().startswith("EVIDENCE-")

    # Pages that own the actions must list the reconstructed evidence.
    pages = {p["id"]: p for p in repaired["pages"]}
    assert "EVIDENCE-HOME-BROWSE-BUTTON" in pages["PAGE-HOME"]["evidence_ids"]
    assert "EVIDENCE-SERVICE-LIST-ITEMS" in pages["PAGE-SERVICE-LIST"]["evidence_ids"]
    assert (
        "EVIDENCE-SERVICE-DETAIL-BOOK-BUTTON"
        in pages["PAGE-SERVICE-DETAIL"]["evidence_ids"]
    )
    booking_evidence = set(pages["PAGE-BOOKING"]["evidence_ids"])
    assert {
        "EVIDENCE-BOOKING-CALENDAR",
        "EVIDENCE-BOOKING-FORM-FIELDS",
        "EVIDENCE-BOOKING-SUBMIT-BUTTON",
    } <= booking_evidence

    final = sanitize_app_spec_payload(repaired, _source_snapshot())
    spec = parse_app_spec_candidate(final)
    report = validate_app_spec(spec)
    assert _missing_entity_refs(report) == []
    assert report.is_valid, [i.code + ":" + i.message for i in report.issues]
    assert result.integrity_hash
    assert all(d.get("referencing_field") for d in result.diagnostics)


def test_heal_missing_reference_reconstructs_evidence_without_provider() -> None:
    payload = _load_fixture()
    spec = parse_app_spec_candidate(payload)
    report = validate_app_spec(spec)
    assert len(_missing_entity_refs(report)) == 6
    validation_payload = {
        "passed": False,
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
    healed, actions = heal_app_spec_payload(payload, validation_payload, {})
    assert any("reference_integrity:" in a for a in actions)
    assert all("provider" not in a.lower() for a in actions)
    for evidence_id in REQUEST38_EVIDENCE_IDS:
        assert evidence_id in {item["id"] for item in healed["evidence"]}
    resanitized = sanitize_app_spec_payload(healed, _source_snapshot())
    report2 = validate_app_spec(parse_app_spec_candidate(resanitized))
    assert _missing_entity_refs(report2) == []
    assert report2.is_valid, [i.code + ":" + i.message for i in report2.issues]

def test_unknown_entity_reference_still_fails_closed() -> None:
    payload = _load_fixture()
    payload["actions"][0]["entity_id"] = "ENTITY-DOES-NOT-EXIST"
    repaired, result = reconcile_reference_integrity(payload)
    assert repaired["actions"][0]["entity_id"] == "ENTITY-DOES-NOT-EXIST"
    assert not any(
        d.get("missing_reference_id") == "ENTITY-DOES-NOT-EXIST"
        and d.get("repair_result") == "reconstructed"
        for d in result.diagnostics
    )
    report = validate_app_spec(parse_app_spec_candidate(repaired))
    assert any(
        issue.code == "missing_reference"
        and "ENTITY-DOES-NOT-EXIST" in issue.message
        for issue in report.issues
    )


def test_removed_evidence_cannot_leave_page_references() -> None:
    payload = _load_fixture()
    repaired, _ = reconcile_reference_integrity(payload)
    # Drop one reconstructed evidence object while leaving the page reference.
    drop_id = "EVIDENCE-HOME-BROWSE-BUTTON"
    repaired["evidence"] = [
        item for item in repaired["evidence"] if item.get("id") != drop_id
    ]
    cleaned, result = reconcile_reference_integrity(repaired)
    # Either reconstruct again from action data or strip dangling page refs.
    evidence_ids = {item["id"] for item in cleaned["evidence"]}
    page_refs = set(cleaned["pages"][0]["evidence_ids"])
    if drop_id in page_refs:
        assert drop_id in evidence_ids
    assert result.integrity_hash


def test_normalization_preserves_canonical_evidence_ids() -> None:
    payload = _load_fixture()
    repaired, _ = reconcile_reference_integrity(payload)
    again = sanitize_app_spec_payload(repaired, _source_snapshot())
    evidence_ids = {item["id"] for item in again["evidence"]}
    assert set(REQUEST38_EVIDENCE_IDS) <= evidence_ids


def test_appspec_fallback_remains_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPSPEC_FALLBACK_ENABLED", "false")
    # Reload is not required; settings already default false in production tests.
    assert settings.APPSPEC_FALLBACK_ENABLED is False


def test_sanitize_pipeline_runs_reference_integrity_pass() -> None:
    payload = sanitize_app_spec_payload(_load_fixture(), _source_snapshot())
    # After the pipeline includes the integrity pass, misplaced evidence entity
    # refs must already be repaired.
    for action in payload["actions"]:
        assert action.get("entity_id") not in REQUEST38_EVIDENCE_IDS
    evidence_ids = {item["id"] for item in payload["evidence"]}
    assert set(REQUEST38_EVIDENCE_IDS) <= evidence_ids
    report = validate_app_spec(parse_app_spec_candidate(payload))
    assert _missing_entity_refs(report) == []
