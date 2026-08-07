"""Request #47 — bounded reconciliation of empty AppSpec traceability references.

Production request #47 authored ten traceability rows. Rows 6–9 (the four
``REQ-NO-*`` exclusion requirements) carried ``capability_ids: []`` and
``evidence_ids: []``, so all three revisions died on ``invalid_trace_shape``
before Design, candidates, TypeScript, Phase 4, or Phase 5 were reached.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

# Import the application package first: the sanitize package and the application
# package import each other, so the domain-first order raises a circular import.
import app.application.appspec  # noqa: F401
from app.core.config import settings
from app.domain.appspec.sanitize.empty_trace import schema_repair_trace_context
from app.domain.appspec.sanitize.pipeline import sanitize_app_spec_payload
from app.domain.appspec.sanitize.schema_diagnostics import (
    TYPED_SCHEMA_ISSUE_CODES,
    classify_schema_parse_exception,
)
from app.domain.appspec.sanitize.trace_reference_reconcile import (
    CAPABILITIES_UNRESOLVED,
    EVIDENCE_UNRESOLVED,
    REFS_AMBIGUOUS,
    reconcile_trace_references,
    unresolved_trace_reference_issues,
)
from app.domain.appspec.validation import validate_app_spec
from app.domain.schemas.app_spec import AppSpec

FIXTURE = Path(__file__).parent / "request47_appspec_candidate.json"

# The four exclusion rows that failed in production.
REQUEST47_EMPTY_ROWS = (6, 7, 8, 9)
REQUEST47_EMPTY_REQUIREMENTS = (
    "REQ-NO-ADMIN-DASHBOARD",
    "REQ-NO-MARKETPLACE",
    "REQ-NO-PAYMENT-CHECKOUT",
    "REQ-NO-AI-FEATURES",
)
REQUEST47_JSON_PATHS = tuple(
    f"traceability[{index}].{field}"
    for index in REQUEST47_EMPTY_ROWS
    for field in ("capability_ids", "evidence_ids")
)


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@pytest.fixture()
def request47_candidate() -> dict[str, Any]:
    """The exact sanitized AppSpec payload persisted for request #47 revision 3."""

    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Minimal synthetic payloads for the individual reconciliation rules.
# ---------------------------------------------------------------------------


def _minimal_payload() -> dict[str, Any]:
    """One page, one capability, one evidence item, one acceptance test."""

    return {
        "schema_version": "1.0",
        "requirements": [{"id": "REQ-A"}, {"id": "REQ-B"}],
        "capabilities": [
            {"id": "CAP-A", "requirement_ids": ["REQ-A"]},
        ],
        "pages": [
            {
                "id": "PAGE-A",
                "capability_ids": ["CAP-A"],
                "evidence_ids": ["EV-A"],
            }
        ],
        "evidence": [
            {"id": "EV-A", "page_id": "PAGE-A", "capability_ids": ["CAP-A"]},
        ],
        "acceptance_tests": [
            {
                "id": "TEST-A",
                "requirement_ids": ["REQ-A"],
                "assertions": [{"kind": "route", "page_id": "PAGE-A"}],
            }
        ],
        "traceability": [
            {
                "requirement_id": "REQ-A",
                "capability_ids": ["CAP-A"],
                "page_ids": ["PAGE-A"],
                "evidence_ids": ["EV-A"],
                "acceptance_test_ids": ["TEST-A"],
            }
        ],
    }


def _two_capability_payload() -> dict[str, Any]:
    """One page carrying two unrelated capabilities and two evidence items."""

    payload = _minimal_payload()
    payload["capabilities"].append({"id": "CAP-B", "requirement_ids": ["REQ-B"]})
    payload["pages"][0]["capability_ids"] = ["CAP-A", "CAP-B"]
    payload["pages"][0]["evidence_ids"] = ["EV-A", "EV-B"]
    payload["evidence"].append(
        {"id": "EV-B", "page_id": "PAGE-A", "capability_ids": ["CAP-B"]}
    )
    return payload


def _trace(payload: dict[str, Any], index: int = 0) -> dict[str, Any]:
    return payload["traceability"][index]


# ---------------------------------------------------------------------------
# 1. Request #47 exact regression — before / after.
# ---------------------------------------------------------------------------


def test_before_request47_reproduces_four_empty_rows(
    request47_candidate: dict[str, Any],
) -> None:
    """The fixture must still carry the production defect."""

    rows = request47_candidate["traceability"]
    assert len(rows) == 10
    for index, requirement_id in zip(
        REQUEST47_EMPTY_ROWS, REQUEST47_EMPTY_REQUIREMENTS
    ):
        row = rows[index]
        assert row["requirement_id"] == requirement_id
        assert row["page_ids"] == ["PAGE-HOME"]
        assert row["capability_ids"] == []
        assert row["evidence_ids"] == []
    for index in range(6):
        assert rows[index]["capability_ids"]
        assert rows[index]["evidence_ids"]


def test_before_request47_reproduces_invalid_trace_shape(
    request47_candidate: dict[str, Any],
) -> None:
    """Strict validation must reject the untouched fixture on the production paths."""

    with pytest.raises(Exception) as excinfo:
        AppSpec.model_validate(request47_candidate)
    issue = classify_schema_parse_exception(
        excinfo.value, candidate_payload=request47_candidate
    )
    assert issue["code"] == "app_spec_schema_parse_failed"
    shape_paths = [
        str(child.get("path"))
        for child in issue["issues"]
        if child.get("code") == "invalid_trace_shape"
    ]
    assert shape_paths == list(REQUEST47_JSON_PATHS)


def test_after_request47_reconciles_every_empty_row(
    request47_candidate: dict[str, Any],
) -> None:
    """All four rows resolve, and only those four rows change."""

    before = copy.deepcopy(request47_candidate)
    result = reconcile_trace_references(request47_candidate)

    assert result.applied is True
    assert result.unresolved == []
    rows = result.payload["traceability"]

    for index in REQUEST47_EMPTY_ROWS:
        assert rows[index]["capability_ids"] == ["CAP-BROWSE-SERVICES"]
        assert rows[index]["evidence_ids"] == ["EVIDENCE-SERVICE-LIST"]

    # No unrelated trace row changes.
    for index in range(6):
        assert rows[index] == before["traceability"][index]

    # Nothing outside traceability moves.
    for key in ("capabilities", "evidence", "pages", "requirements", "acceptance_tests"):
        assert result.payload[key] == before[key]


def test_after_request47_every_reconciled_id_exists(
    request47_candidate: dict[str, Any],
) -> None:
    result = reconcile_trace_references(request47_candidate)
    payload = result.payload
    known = {
        "capability_ids": {item["id"] for item in payload["capabilities"]},
        "page_ids": {item["id"] for item in payload["pages"]},
        "evidence_ids": {item["id"] for item in payload["evidence"]},
        "acceptance_test_ids": {item["id"] for item in payload["acceptance_tests"]},
    }
    for row in payload["traceability"]:
        for field_name, allowed in known.items():
            assert row[field_name], f"{field_name} must be non-empty"
            assert set(row[field_name]) <= allowed


def test_after_request47_passes_schema_and_deterministic_validation(
    request47_candidate: dict[str, Any],
) -> None:
    """The full acceptance chain for request #47."""

    sanitized = sanitize_app_spec_payload(request47_candidate, {})

    for row in sanitized["traceability"]:
        assert row["capability_ids"]
        assert row["evidence_ids"]

    spec = AppSpec.model_validate(sanitized)
    report = validate_app_spec(spec)
    assert report.is_valid, [
        (getattr(issue, "code", None), getattr(issue, "message", None))
        for issue in (report.issues or [])
    ]


def test_after_request47_records_one_row_per_repair(
    request47_candidate: dict[str, Any],
) -> None:
    """Persistence payload carries index, requirement, fields, IDs, source, hashes."""

    result = reconcile_trace_references(request47_candidate)
    assert len(result.records) == len(REQUEST47_EMPTY_ROWS)
    for record, index, requirement_id in zip(
        result.records, REQUEST47_EMPTY_ROWS, REQUEST47_EMPTY_REQUIREMENTS
    ):
        assert record["trace_index"] == index
        assert record["requirement_id"] == requirement_id
        assert record["fields_repaired"] == ["capability_ids", "evidence_ids"]
        assert record["ids_added"] == {
            "capability_ids": ["CAP-BROWSE-SERVICES"],
            "evidence_ids": ["EVIDENCE-SERVICE-LIST"],
        }
        assert record["reconciliation_source"] == {
            "capability_ids": "page_capability",
            "evidence_ids": "capability_page_evidence",
        }
        assert record["before_sha256"] == result.original_sha256
        assert record["after_sha256"] == result.result_sha256
        assert record["before_sha256"] != record["after_sha256"]


def test_after_request47_pipeline_exposes_one_reconciliation_record(
    request47_candidate: dict[str, Any],
) -> None:
    """The sanitize pipeline surfaces a single per-attempt audit record."""

    diagnostics: dict[str, Any] = {}
    sanitize_app_spec_payload(request47_candidate, {}, diagnostics=diagnostics)
    audit = diagnostics["trace_reference_reconciliation"]
    assert audit["result"] == "reconciled"
    assert audit["unresolved_codes"] == []
    assert [record["trace_index"] for record in audit["records"]] == list(
        REQUEST47_EMPTY_ROWS
    )


# ---------------------------------------------------------------------------
# 2. Unique resolution per field.
# ---------------------------------------------------------------------------


def test_empty_capability_ids_uniquely_resolved_from_requirement_link() -> None:
    """A capability that already claims the requirement wins over the page anchor."""

    payload = _two_capability_payload()
    _trace(payload)["capability_ids"] = []

    result = reconcile_trace_references(payload)

    assert result.applied is True
    assert result.unresolved == []
    assert _trace(result.payload)["capability_ids"] == ["CAP-A"]
    assert result.records[0]["reconciliation_source"]["capability_ids"] == (
        "requirement_capability"
    )


def test_empty_capability_ids_uniquely_resolved_from_page_assignment() -> None:
    """With no requirement link, a single page-assigned capability is enough."""

    payload = _minimal_payload()
    payload["capabilities"][0]["requirement_ids"] = ["REQ-B"]
    _trace(payload)["capability_ids"] = []

    result = reconcile_trace_references(payload)

    assert _trace(result.payload)["capability_ids"] == ["CAP-A"]
    assert result.records[0]["reconciliation_source"]["capability_ids"] == (
        "page_capability"
    )


def test_empty_evidence_ids_uniquely_resolved_from_assertion() -> None:
    """The row's own acceptance-test assertion is the strongest evidence proof."""

    payload = _two_capability_payload()
    payload["acceptance_tests"][0]["assertions"] = [
        {"kind": "visible", "evidence_id": "EV-B"}
    ]
    _trace(payload)["evidence_ids"] = []

    result = reconcile_trace_references(payload)

    assert _trace(result.payload)["evidence_ids"] == ["EV-B"]
    assert result.records[0]["reconciliation_source"]["evidence_ids"] == (
        "acceptance_test_assertion_evidence"
    )


def test_empty_evidence_ids_uniquely_resolved_from_capability_page_link() -> None:
    payload = _two_capability_payload()
    _trace(payload)["evidence_ids"] = []

    result = reconcile_trace_references(payload)

    assert _trace(result.payload)["evidence_ids"] == ["EV-A"]
    assert result.records[0]["reconciliation_source"]["evidence_ids"] == (
        "capability_page_evidence"
    )


def test_both_fields_empty_and_uniquely_resolved() -> None:
    payload = _minimal_payload()
    _trace(payload)["capability_ids"] = []
    _trace(payload)["evidence_ids"] = []

    result = reconcile_trace_references(payload)

    assert result.unresolved == []
    assert _trace(result.payload)["capability_ids"] == ["CAP-A"]
    assert _trace(result.payload)["evidence_ids"] == ["EV-A"]
    assert result.records[0]["fields_repaired"] == ["capability_ids", "evidence_ids"]


# ---------------------------------------------------------------------------
# 3. Normalization: blanks, duplicates, unknown IDs.
# ---------------------------------------------------------------------------


def test_empty_strings_are_removed() -> None:
    payload = _minimal_payload()
    _trace(payload)["capability_ids"] = ["", "CAP-A", "   "]

    result = reconcile_trace_references(payload)

    assert _trace(result.payload)["capability_ids"] == ["CAP-A"]
    assert any(action.startswith("drop_blank_trace_id:") for action in result.actions)


def test_duplicates_are_removed_and_order_is_stable() -> None:
    payload = _two_capability_payload()
    _trace(payload)["capability_ids"] = ["CAP-B", "CAP-A", "CAP-B", "CAP-A"]

    result = reconcile_trace_references(payload)

    assert _trace(result.payload)["capability_ids"] == ["CAP-B", "CAP-A"]
    assert any(action.startswith("dedupe_trace_ids:") for action in result.actions)


def test_unknown_ids_are_rejected() -> None:
    payload = _minimal_payload()
    _trace(payload)["evidence_ids"] = ["EV-A", "EV-DOES-NOT-EXIST"]

    result = reconcile_trace_references(payload)

    assert _trace(result.payload)["evidence_ids"] == ["EV-A"]
    assert (
        "drop_unknown_trace_id:traceability[0].evidence_ids:EV-DOES-NOT-EXIST"
        in result.actions
    )


def test_unknown_ids_only_falls_back_to_reconciliation() -> None:
    """Dropping every unknown ID empties the field, which then reconciles."""

    payload = _minimal_payload()
    _trace(payload)["capability_ids"] = ["CAP-GHOST"]

    result = reconcile_trace_references(payload)

    assert _trace(result.payload)["capability_ids"] == ["CAP-A"]
    assert (
        "drop_unknown_trace_id:traceability[0].capability_ids:CAP-GHOST"
        in result.actions
    )


# ---------------------------------------------------------------------------
# 4. Fail closed.
# ---------------------------------------------------------------------------


def test_ambiguous_capabilities_fail_closed() -> None:
    """Two equally proven page capabilities and no requirement link → refuse."""

    payload = _two_capability_payload()
    payload["capabilities"][0]["requirement_ids"] = ["REQ-Z"]
    payload["capabilities"][1]["requirement_ids"] = ["REQ-Z"]
    _trace(payload)["capability_ids"] = []

    result = reconcile_trace_references(payload)

    assert _trace(result.payload)["capability_ids"] == []
    codes = result.unresolved_codes
    assert REFS_AMBIGUOUS in codes
    entry = next(item for item in result.unresolved if item["code"] == REFS_AMBIGUOUS)
    assert entry["path"] == "traceability[0].capability_ids"
    assert entry["requirement_id"] == "REQ-A"
    assert sorted(entry["candidates"]) == ["CAP-A", "CAP-B"]


def test_ambiguous_evidence_fails_closed() -> None:
    """Two evidence items on the same page and capability → refuse."""

    payload = _minimal_payload()
    payload["pages"][0]["evidence_ids"] = ["EV-A", "EV-A2"]
    payload["evidence"].append(
        {"id": "EV-A2", "page_id": "PAGE-A", "capability_ids": ["CAP-A"]}
    )
    _trace(payload)["evidence_ids"] = []

    result = reconcile_trace_references(payload)

    assert _trace(result.payload)["evidence_ids"] == []
    entry = next(item for item in result.unresolved if item["code"] == REFS_AMBIGUOUS)
    assert entry["field"] == "evidence_ids"
    assert sorted(entry["candidates"]) == ["EV-A", "EV-A2"]


def test_no_candidate_capability_fails_closed_with_unresolved_code() -> None:
    """No requirement link and no page capability → unresolved, not ambiguous."""

    payload = _minimal_payload()
    payload["pages"][0]["capability_ids"] = []
    payload["capabilities"][0]["requirement_ids"] = ["REQ-B"]
    _trace(payload)["capability_ids"] = []

    result = reconcile_trace_references(payload)

    assert _trace(result.payload)["capability_ids"] == []
    assert result.unresolved_codes == [CAPABILITIES_UNRESOLVED]


def test_no_candidate_evidence_fails_closed_with_unresolved_code() -> None:
    payload = _minimal_payload()
    payload["evidence"][0]["page_id"] = "PAGE-OTHER"
    payload["pages"][0]["evidence_ids"] = []
    _trace(payload)["evidence_ids"] = []

    result = reconcile_trace_references(payload)

    assert _trace(result.payload)["evidence_ids"] == []
    assert result.unresolved_codes == [EVIDENCE_UNRESOLVED]


def test_no_id_wording_inference() -> None:
    """Matching names never substitute for an explicit relationship."""

    payload = _minimal_payload()
    payload["requirements"].append({"id": "REQ-BOOKING"})
    payload["capabilities"].append(
        {
            "id": "CAP-BOOKING",
            "name": "Booking",
            "requirement_ids": ["REQ-A"],
        }
    )
    payload["evidence"].append(
        {
            "id": "EVIDENCE-BOOKING",
            "name": "Booking",
            "page_id": "PAGE-BOOKING",
            "capability_ids": ["CAP-BOOKING"],
        }
    )
    payload["pages"].append(
        {"id": "PAGE-BOOKING", "capability_ids": [], "evidence_ids": []}
    )
    payload["traceability"].append(
        {
            "requirement_id": "REQ-BOOKING",
            "capability_ids": [],
            "page_ids": ["PAGE-BOOKING"],
            "evidence_ids": [],
            "acceptance_test_ids": ["TEST-A"],
        }
    )

    result = reconcile_trace_references(payload)

    row = _trace(result.payload, 1)
    assert row["capability_ids"] == []
    assert CAPABILITIES_UNRESOLVED in result.unresolved_codes


# ---------------------------------------------------------------------------
# 5. Non-destructive + idempotent.
# ---------------------------------------------------------------------------


def test_valid_trace_rows_remain_unchanged() -> None:
    payload = _minimal_payload()
    before = copy.deepcopy(payload)

    result = reconcile_trace_references(payload)

    assert result.applied is False
    assert result.records == []
    assert result.unresolved == []
    assert result.payload == before
    assert result.original_sha256 == result.result_sha256


def test_reconciliation_is_idempotent(request47_candidate: dict[str, Any]) -> None:
    first = reconcile_trace_references(request47_candidate)
    second = reconcile_trace_references(first.payload)
    third = reconcile_trace_references(second.payload)

    assert first.applied is True
    assert second.applied is False
    assert third.applied is False
    assert _canonical_sha256(first.payload) == _canonical_sha256(second.payload)
    assert _canonical_sha256(second.payload) == _canonical_sha256(third.payload)


def test_sanitize_pipeline_is_idempotent(request47_candidate: dict[str, Any]) -> None:
    once = sanitize_app_spec_payload(request47_candidate, {})
    twice = sanitize_app_spec_payload(once, {})
    assert _canonical_sha256(once) == _canonical_sha256(twice)


def test_reconciliation_never_creates_objects() -> None:
    """Object collections keep their exact membership through reconciliation."""

    payload = _minimal_payload()
    _trace(payload)["capability_ids"] = []
    _trace(payload)["evidence_ids"] = []
    before = copy.deepcopy(payload)

    result = reconcile_trace_references(payload)

    for key in (
        "requirements",
        "capabilities",
        "pages",
        "evidence",
        "acceptance_tests",
    ):
        assert result.payload[key] == before[key]
    assert len(result.payload["traceability"]) == len(before["traceability"])


# ---------------------------------------------------------------------------
# 6. Typed diagnostics and retry correction.
# ---------------------------------------------------------------------------


def test_unresolved_codes_are_registered_typed_issue_codes() -> None:
    for code in (CAPABILITIES_UNRESOLVED, EVIDENCE_UNRESOLVED, REFS_AMBIGUOUS):
        assert code in TYPED_SCHEMA_ISSUE_CODES


def test_unresolved_refs_surface_as_typed_blocking_issues() -> None:
    payload = _minimal_payload()
    payload["pages"][0]["capability_ids"] = []
    payload["capabilities"][0]["requirement_ids"] = ["REQ-B"]
    _trace(payload)["capability_ids"] = []

    issues = unresolved_trace_reference_issues(payload)

    assert len(issues) == 1
    assert issues[0]["code"] == CAPABILITIES_UNRESOLVED
    assert issues[0]["severity"] == "blocking"
    assert issues[0]["path"] == "traceability[0].capability_ids"
    assert issues[0]["related_ids"] == ["REQ-A"]


def test_retry_context_carries_compact_correction(
    request47_candidate: dict[str, Any],
) -> None:
    """The retry instruction is a short directive, not the malformed response."""

    context = schema_repair_trace_context(request47_candidate)

    assert context["correction"] == [
        "return the complete AppSpec JSON object",
        "populate capability_ids and evidence_ids for every traceability row",
        "use only IDs that already exist in this candidate",
        "no empty arrays",
        "no prose or markdown",
    ]
    assert any("capability_id and one evidence_id" in rule for rule in context["rules"])


def test_appspec_prompt_revision_records_the_authoring_change() -> None:
    # 2026-08-07.1: sessions 18-19's reject shapes taught (exactly-one initial
    # state, per-kind assertion references, declare-before-cite, the minItems
    # floor outside traceability, trace-or-defer). Previously 2026-07-28.2 for
    # rule 8a. The stamp rides every revision's provenance, so reject rates are
    # queryable per prompt revision.
    assert settings.APPSPEC_PROMPT_REVISION == "2026-08-07.1"


def test_authoring_prompt_forbids_empty_trace_arrays() -> None:
    template = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "templates"
        / "prompts"
        / "app_spec.j2"
    ).read_text(encoding="utf-8")

    assert "empty `capability_ids` or `evidence_ids`" in template
    assert "requirement_ids` includes that row's" in template


def test_schema_repair_prompt_carries_the_correction_block() -> None:
    template = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "templates"
        / "prompts"
        / "app_spec_schema_repair.j2"
    ).read_text(encoding="utf-8")

    assert "CORRECTION REQUIRED:" in template
    assert "Populate `capability_ids` and `evidence_ids` for every traceability row." in (
        template
    )


# ---------------------------------------------------------------------------
# 7. Fallback safety.
# ---------------------------------------------------------------------------


def test_appspec_fallback_remains_disabled() -> None:
    assert settings.APPSPEC_FALLBACK_ENABLED is False
    assert settings.APPSPEC_FALLBACK_SAFETY_CODE == "ok"


def test_reconciliation_never_reaches_for_the_fallback_spec(
    request47_candidate: dict[str, Any],
) -> None:
    """Request #47 now resolves deterministically, so no fallback path is needed."""

    sanitized = sanitize_app_spec_payload(request47_candidate, {})
    spec = AppSpec.model_validate(sanitized)
    assert validate_app_spec(spec).is_valid
    assert settings.APPSPEC_FALLBACK_ENABLED is False
