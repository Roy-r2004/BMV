"""Request 143: a nested fragment must never be accepted as the document.

An unescaped quote desynchronised the outer object of a 31,303-char authoring
response. Every strict path failed, and the span fallback surfaced one balanced
414-char acceptance-test object — 1.3 % of what the model wrote — which then
consumed the run's repairs as if it were the spec. The guard classifies that
shape as a failed parse (a re-ask is a legal move; repairing a fragment has
none) while leaving small-document extraction untouched.
"""
from __future__ import annotations

import json

import app.application.appspec  # noqa: F401  — break the domain↔application cycle
from app.domain.appspec.authoring_parser import (
    AUTHORING_JSON_SYNTAX_INVALID,
    AUTHORING_JSON_TRUNCATED,
    _is_fragment_extraction,
    parse_appspec_authoring_output,
)


_FRAGMENT = json.dumps(
    {
        "id": "TEST-MENU-001",
        "name": "Verify Weekly Menu Display",
        "assertions": [{"kind": "route", "page_id": "PAGE-MENU"}],
        "requirement_ids": ["REQ-MENU-001"],
    }
)


def _desynchronised_large_raw() -> str:
    # The outer object never closes for a string-aware scanner: the body drifts
    # out of escaping (bare quote), so the closing braces read as in-string.
    body = '{"schema_version": "1.0", "product_intent": {"summary": "a bare " quote'
    filler = " menu text" * 3000  # ~30k chars of swallowed document
    return body + filler + "\n" + _FRAGMENT


def test_request143_fragment_is_rejected_not_adopted() -> None:
    raw = _desynchronised_large_raw()
    assert len(raw) > 30000
    result = parse_appspec_authoring_output(raw, finish_reason="stop")
    assert not result.ok
    assert result.error_code in {
        AUTHORING_JSON_SYNTAX_INVALID,
        AUTHORING_JSON_TRUNCATED,
    }
    # The fragment itself must not be the candidate.
    assert result.payload is None


def test_fragment_guard_boundary_is_ratio_and_floor() -> None:
    # Below the raw floor the guard never fires — small-document extraction
    # (prose-wrapped objects, first-object policy) keeps working.
    assert not _is_fragment_extraction(1999, 10)
    # At scale, less than half the response is a fragment.
    assert _is_fragment_extraction(31303, 414)
    assert _is_fragment_extraction(20000, 9999)
    assert not _is_fragment_extraction(20000, 10000)


def test_a_tiny_complete_first_object_in_a_large_response_is_refused() -> None:
    # The balanced scan finds a complete first object; at 30k raw chars a
    # sub-2 % object is a fragment whichever path surfaced it.
    raw = _FRAGMENT + "\n" + ("prose about the menu " * 1500)
    assert len(raw) > 30000
    result = parse_appspec_authoring_output(raw, finish_reason="stop")
    assert not result.ok
    assert result.error_code == AUTHORING_JSON_SYNTAX_INVALID
    assert result.parser_error == "fragment_extracted"


def test_large_prose_wrapped_document_still_extracts() -> None:
    # A legitimate big document with prose on both sides clears the ratio.
    doc = json.dumps(
        {
            "schema_version": "1.0",
            "product_intent": {"summary": "booking"},
            "requirements": [
                {"id": f"REQ-{i}", "title": "t" * 200} for i in range(40)
            ],
        }
    )
    raw = "Sure, here is the document.\n" + doc + "\nDone."
    assert len(raw) > 2000
    result = parse_appspec_authoring_output(raw, finish_reason="stop")
    assert result.ok
    assert result.strategy == "balanced_scan"
    assert result.payload["product_intent"]["summary"] == "booking"
