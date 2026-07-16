"""Tests for deterministic AppSpec payload sanitization."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.services.app_spec_sanitize import sanitize_app_spec_payload
from app.application.services.app_spec_builder import parse_app_spec_candidate
from app.domain.schemas.app_spec import AppSpec


def _source_snapshot() -> dict:
    return {
        "customer_input": {
            "desired_outcome": "Customers can book appointments online.",
            "business_description": "A studio booking product.",
        },
        "reference_evidence": {},
    }


def test_strips_derived_context_refs_and_defers_blueprint_requirements() -> None:
    payload = {
        "schema_version": "1.0",
        "product_intent": {
            "name": "Studio",
            "summary": "Booking studio",
            "problem": "Manual booking",
            "desired_outcome": "Online booking",
            "target_users": ["Customers"],
            "success_metrics": ["Bookings confirmed"],
        },
        "requirements": [
            {
                "id": "REQ-ONLINE-PAYMENT",
                "title": "Online payment",
                "description": "Collect payment during booking.",
                "priority": "must",
                "verification_mode": "integration",
                "source_refs": ["derived_context.mvp_blueprint"],
            }
        ],
        "assumptions": [],
        "open_questions": [],
        "roles": [
            {
                "id": "ROLE-CUSTOMER",
                "name": "Customer",
                "description": "Books appointments.",
                "goals": ["Book"],
                "default_page_id": "PAGE-BOOK",
            }
        ],
        "entities": [],
        "capabilities": [
            {
                "id": "CAP-BOOK",
                "name": "Book",
                "description": "Book appointments.",
                "requirement_ids": ["REQ-ONLINE-PAYMENT"],
                "role_ids": ["ROLE-CUSTOMER"],
                "entity_ids": [],
            }
        ],
        "pages": [
            {
                "id": "PAGE-BOOK",
                "name": "Book",
                "purpose": "Book an appointment.",
                "route": "/book",
                "surface": "public",
                "primary": True,
                "role_ids": ["ROLE-CUSTOMER"],
                "capability_ids": ["CAP-BOOK"],
                "state_ids": ["STATE-BOOK"],
                "action_ids": [],
                "evidence_ids": ["EVIDENCE-BOOK"],
            }
        ],
        "states": [
            {
                "id": "STATE-BOOK",
                "page_id": "PAGE-BOOK",
                "name": "Ready",
                "description": "Ready to book.",
                "initial": True,
                "terminal": False,
                "evidence_ids": [],
            }
        ],
        "actions": [],
        "transitions": [],
        "evidence": [
            {
                "id": "EVIDENCE-BOOK",
                "page_id": "PAGE-BOOK",
                "name": "Booking form",
                "description": "Booking form is visible.",
                "kind": "form",
                "capability_ids": ["CAP-BOOK"],
            }
        ],
        "journeys": [],
        "acceptance_tests": [
            {
                "id": "TEST-BOOK",
                "name": "Book",
                "description": "Booking works.",
                "requirement_ids": ["REQ-ONLINE-PAYMENT"],
                "journey_id": None,
                "assertions": [
                    {
                        "kind": "visible",
                        "description": "Form visible",
                        "page_id": "PAGE-BOOK",
                        "state_id": "STATE-BOOK",
                        "evidence_id": "EVIDENCE-BOOK",
                        "expected": "Book",
                    }
                ],
            }
        ],
        "traceability": [
            {
                "requirement_id": "REQ-ONLINE-PAYMENT",
                "capability_ids": ["CAP-BOOK"],
                "page_ids": ["PAGE-BOOK"],
                "evidence_ids": ["EVIDENCE-BOOK"],
                "journey_ids": [],
                "acceptance_test_ids": ["TEST-BOOK"],
            }
        ],
        "deferred_scope": [],
    }
    sanitized = sanitize_app_spec_payload(payload, _source_snapshot())
    spec = parse_app_spec_candidate(sanitized)
    assert isinstance(spec, AppSpec)
    requirement = spec.requirements[0]
    assert requirement.priority == "should"
    assert requirement.source_refs == ("customer_input.desired_outcome",)
    assert len(spec.deferred_scope) == 1
    assert spec.deferred_scope[0].requirement_ids == ("REQ-ONLINE-PAYMENT",)
    assert spec.traceability == ()


def test_adds_page_evidence_when_missing() -> None:
    payload = {
        "schema_version": "1.0",
        "product_intent": {
            "name": "Studio",
            "summary": "Booking studio",
            "problem": "Manual booking",
            "desired_outcome": "Online booking",
            "target_users": ["Customers"],
            "success_metrics": ["Bookings confirmed"],
        },
        "requirements": [
            {
                "id": "REQ-LOGIN",
                "title": "Admin login",
                "description": "Staff can sign in.",
                "priority": "must",
                "verification_mode": "interaction",
                "source_refs": ["customer_input.desired_outcome"],
            }
        ],
        "assumptions": [],
        "open_questions": [],
        "roles": [
            {
                "id": "ROLE-ADMIN",
                "name": "Admin",
                "description": "Staff member.",
                "goals": ["Sign in"],
                "default_page_id": "PAGE-ADMIN-LOGIN",
            }
        ],
        "entities": [],
        "capabilities": [
            {
                "id": "CAP-LOGIN",
                "name": "Login",
                "description": "Authenticate staff.",
                "requirement_ids": ["REQ-LOGIN"],
                "role_ids": ["ROLE-ADMIN"],
                "entity_ids": [],
            }
        ],
        "pages": [
            {
                "id": "PAGE-ADMIN-LOGIN",
                "name": "Admin login",
                "purpose": "Authenticate staff.",
                "route": "/admin/login",
                "surface": "ops",
                "primary": True,
                "role_ids": ["ROLE-ADMIN"],
                "capability_ids": ["CAP-LOGIN"],
                "state_ids": ["STATE-LOGIN"],
                "action_ids": [],
                "evidence_ids": [],
            }
        ],
        "states": [
            {
                "id": "STATE-LOGIN",
                "page_id": "PAGE-ADMIN-LOGIN",
                "name": "Login form",
                "description": "Credentials can be entered.",
                "initial": True,
                "terminal": False,
                "evidence_ids": [],
            }
        ],
        "actions": [],
        "transitions": [],
        "evidence": [],
        "journeys": [],
        "acceptance_tests": [
            {
                "id": "TEST-LOGIN",
                "name": "Login",
                "description": "Staff can sign in.",
                "requirement_ids": ["REQ-LOGIN"],
                "journey_id": None,
                "assertions": [
                    {
                        "kind": "route",
                        "description": "Login route loads.",
                        "page_id": "PAGE-ADMIN-LOGIN",
                        "state_id": "STATE-LOGIN",
                        "evidence_id": None,
                        "expected": "/admin/login",
                    }
                ],
            }
        ],
        "traceability": [
            {
                "requirement_id": "REQ-LOGIN",
                "capability_ids": ["CAP-LOGIN"],
                "page_ids": ["PAGE-ADMIN-LOGIN"],
                "evidence_ids": ["EVIDENCE-ADMIN-LOGIN-SURFACE"],
                "journey_ids": [],
                "acceptance_test_ids": ["TEST-LOGIN"],
            }
        ],
        "deferred_scope": [],
    }
    sanitized = sanitize_app_spec_payload(payload, _source_snapshot())
    spec = parse_app_spec_candidate(sanitized)
    page = spec.pages[0]
    assert page.evidence_ids
    assert len(spec.evidence) == 1
    assert spec.evidence[0].page_id == "PAGE-ADMIN-LOGIN"


def test_repairs_empty_capability_requirement_ids() -> None:
    payload = {
        "schema_version": "1.0",
        "product_intent": {
            "name": "Studio",
            "summary": "Booking studio",
            "problem": "Manual booking",
            "desired_outcome": "Online booking",
            "target_users": ["Customers"],
            "success_metrics": ["Bookings confirmed"],
        },
        "requirements": [
            {
                "id": "REQ-STAFF-SCHEDULE-001",
                "title": "Staff schedule",
                "description": "Staff can view the schedule.",
                "priority": "must",
                "verification_mode": "content",
                "source_refs": ["customer_input.desired_outcome"],
            }
        ],
        "assumptions": [],
        "open_questions": [],
        "roles": [
            {
                "id": "ROLE-RECEPTION",
                "name": "Reception",
                "description": "Staff member.",
                "goals": ["Manage schedule"],
                "default_page_id": "PAGE-ADMIN-LOGIN",
            }
        ],
        "entities": [],
        "capabilities": [
            {
                "id": "CAP-ADMIN-LOGIN",
                "name": "Admin login",
                "description": "Authenticate staff.",
                "requirement_ids": [],
                "role_ids": ["ROLE-RECEPTION"],
                "entity_ids": [],
            }
        ],
        "pages": [
            {
                "id": "PAGE-ADMIN-LOGIN",
                "name": "Admin login",
                "purpose": "Authenticate staff.",
                "route": "/admin/login",
                "surface": "ops",
                "primary": True,
                "role_ids": ["ROLE-RECEPTION"],
                "capability_ids": ["CAP-ADMIN-LOGIN"],
                "state_ids": ["STATE-LOGIN"],
                "action_ids": [],
                "evidence_ids": ["EVIDENCE-LOGIN-FORM"],
            }
        ],
        "states": [
            {
                "id": "STATE-LOGIN",
                "page_id": "PAGE-ADMIN-LOGIN",
                "name": "Login form",
                "description": "Credentials can be entered.",
                "initial": True,
                "terminal": False,
                "evidence_ids": [],
            }
        ],
        "actions": [],
        "transitions": [],
        "evidence": [
            {
                "id": "EVIDENCE-LOGIN-FORM",
                "page_id": "PAGE-ADMIN-LOGIN",
                "name": "Login form",
                "description": "Login form is visible.",
                "kind": "form",
                "capability_ids": ["CAP-ADMIN-LOGIN"],
            }
        ],
        "journeys": [],
        "acceptance_tests": [
            {
                "id": "TEST-STAFF-SCHEDULE",
                "name": "Schedule",
                "description": "Staff can view schedule.",
                "requirement_ids": ["REQ-STAFF-SCHEDULE-001"],
                "journey_id": None,
                "assertions": [
                    {
                        "kind": "visible",
                        "description": "Schedule visible",
                        "page_id": "PAGE-ADMIN-LOGIN",
                        "state_id": "STATE-LOGIN",
                        "evidence_id": "EVIDENCE-LOGIN-FORM",
                        "expected": "Login",
                    }
                ],
            }
        ],
        "traceability": [
            {
                "requirement_id": "REQ-STAFF-SCHEDULE-001",
                "capability_ids": ["CAP-ADMIN-LOGIN"],
                "page_ids": ["PAGE-ADMIN-LOGIN"],
                "evidence_ids": ["EVIDENCE-LOGIN-FORM"],
                "journey_ids": [],
                "acceptance_test_ids": ["TEST-STAFF-SCHEDULE"],
            }
        ],
        "deferred_scope": [],
    }
    sanitized = sanitize_app_spec_payload(payload, _source_snapshot())
    spec = parse_app_spec_candidate(sanitized)
    assert spec.capabilities[0].requirement_ids == ("REQ-STAFF-SCHEDULE-001",)


def test_normalizes_invalid_evidence_and_assertion_kinds() -> None:
    payload = {
        "schema_version": "1.0",
        "product_intent": {
            "name": "Studio",
            "summary": "Booking studio",
            "problem": "Manual booking",
            "desired_outcome": "Online booking",
            "target_users": ["Customers"],
            "success_metrics": ["Bookings confirmed"],
        },
        "requirements": [
            {
                "id": "REQ-BOOK",
                "title": "Book",
                "description": "Book online.",
                "priority": "must",
                "verification_mode": "interaction",
                "source_refs": ["customer_input.desired_outcome"],
            }
        ],
        "assumptions": [],
        "open_questions": [],
        "roles": [
            {
                "id": "ROLE-CUSTOMER",
                "name": "Customer",
                "description": "Books appointments.",
                "goals": ["Book"],
                "default_page_id": "PAGE-BOOK",
            }
        ],
        "entities": [],
        "capabilities": [
            {
                "id": "CAP-BOOK",
                "name": "Book",
                "description": "Book appointments.",
                "requirement_ids": ["REQ-BOOK"],
                "role_ids": ["ROLE-CUSTOMER"],
                "entity_ids": [],
            }
        ],
        "pages": [
            {
                "id": "PAGE-BOOK",
                "name": "Book",
                "purpose": "Book an appointment.",
                "route": "/book",
                "surface": "public",
                "primary": True,
                "role_ids": ["ROLE-CUSTOMER"],
                "capability_ids": ["CAP-BOOK"],
                "state_ids": ["STATE-BOOK"],
                "action_ids": [],
                "evidence_ids": ["EVIDENCE-BOOK"],
            }
        ],
        "states": [
            {
                "id": "STATE-BOOK",
                "page_id": "PAGE-BOOK",
                "name": "Ready",
                "description": "Ready to book.",
                "initial": True,
                "terminal": False,
                "evidence_ids": [],
            }
        ],
        "actions": [],
        "transitions": [],
        "evidence": [
            {
                "id": "EVIDENCE-BOOK",
                "page_id": "PAGE-BOOK",
                "name": "Confirmation email",
                "description": "Email sent.",
                "kind": "data",
                "capability_ids": ["CAP-BOOK"],
            }
        ],
        "journeys": [],
        "acceptance_tests": [
            {
                "id": "TEST-BOOK",
                "name": "Book",
                "description": "Booking works.",
                "requirement_ids": ["REQ-BOOK"],
                "journey_id": None,
                "assertions": [
                    {
                        "kind": "list",
                        "description": "List visible",
                        "page_id": "PAGE-BOOK",
                        "state_id": "STATE-BOOK",
                        "evidence_id": "EVIDENCE-BOOK",
                        "expected": "Book",
                    }
                ],
            }
        ],
        "traceability": [
            {
                "requirement_id": "REQ-BOOK",
                "capability_ids": ["CAP-BOOK"],
                "page_ids": ["PAGE-BOOK"],
                "evidence_ids": ["EVIDENCE-BOOK"],
                "journey_ids": [],
                "acceptance_test_ids": ["TEST-BOOK"],
            }
        ],
        "deferred_scope": [],
    }
    sanitized = sanitize_app_spec_payload(payload, _source_snapshot())
    spec = parse_app_spec_candidate(sanitized)
    assert spec.evidence[0].kind == "status"
    assert spec.acceptance_tests[0].assertions[0].kind == "visible"


def test_repairs_entity_fields_and_deferred_scope_gaps() -> None:
    payload = {
        "schema_version": "1.0",
        "product_intent": {
            "name": "Studio",
            "summary": "Booking studio",
            "problem": "Manual booking",
            "desired_outcome": "Online booking",
            "target_users": ["Customers"],
            "success_metrics": ["Bookings confirmed"],
        },
        "requirements": [
            {
                "id": "REQ-ONLINE-PAYMENT",
                "title": "Online payment",
                "description": "Collect payment during booking.",
                "priority": "should",
                "verification_mode": "integration",
                "source_refs": ["customer_input.desired_outcome"],
            }
        ],
        "assumptions": [],
        "open_questions": [],
        "roles": [
            {
                "id": "ROLE-CUSTOMER",
                "name": "Customer",
                "description": "Books appointments.",
                "goals": ["Book"],
                "default_page_id": "PAGE-BOOK",
            }
        ],
        "entities": [
            {
                "id": "ENTITY-BOOKING",
                "name": "Booking",
                "description": "A booking record.",
                "fields": [
                    {
                        "id": "FIELD-BOOKING-CUSTOMER-PHONE",
                        "type": "string",
                    }
                ],
            }
        ],
        "capabilities": [
            {
                "id": "CAP-BOOK",
                "name": "Book",
                "description": "Book appointments.",
                "requirement_ids": ["REQ-ONLINE-PAYMENT"],
                "role_ids": ["ROLE-CUSTOMER"],
                "entity_ids": ["ENTITY-BOOKING"],
            }
        ],
        "pages": [
            {
                "id": "PAGE-BOOK",
                "name": "Book",
                "purpose": "Book an appointment.",
                "route": "/book",
                "surface": "public",
                "primary": True,
                "role_ids": ["ROLE-CUSTOMER"],
                "capability_ids": ["CAP-BOOK"],
                "state_ids": ["STATE-BOOK"],
                "action_ids": [],
                "evidence_ids": ["EVIDENCE-BOOK"],
            }
        ],
        "states": [
            {
                "id": "STATE-BOOK",
                "page_id": "PAGE-BOOK",
                "name": "Ready",
                "description": "Ready to book.",
                "initial": True,
                "terminal": False,
                "evidence_ids": [],
            }
        ],
        "actions": [],
        "transitions": [],
        "evidence": [
            {
                "id": "EVIDENCE-BOOK",
                "page_id": "PAGE-BOOK",
                "name": "Booking form",
                "description": "Booking form is visible.",
                "kind": "form",
                "capability_ids": ["CAP-BOOK"],
            }
        ],
        "journeys": [],
        "acceptance_tests": [
            {
                "id": "TEST-BOOK",
                "name": "Book",
                "description": "Booking works.",
                "requirement_ids": ["REQ-ONLINE-PAYMENT"],
                "journey_id": None,
                "assertions": [
                    {
                        "kind": "visible",
                        "description": "Form visible",
                        "page_id": "PAGE-BOOK",
                        "state_id": "STATE-BOOK",
                        "evidence_id": "EVIDENCE-BOOK",
                        "expected": "Book",
                    }
                ],
            }
        ],
        "traceability": [],
        "deferred_scope": [
            {
                "id": "DEFERRED-ONLINE-PAYMENT",
                "name": "Online payment",
                "description": "Deferred payment integration.",
                "reason": "Not in MVP.",
                "requirement_ids": [],
                "target_release": "Phase 2",
            }
        ],
    }
    sanitized = sanitize_app_spec_payload(payload, _source_snapshot())
    spec = parse_app_spec_candidate(sanitized)
    assert spec.entities[0].fields[0].name == "Booking Customer Phone"
    assert spec.deferred_scope[0].requirement_ids == ("REQ-ONLINE-PAYMENT",)


def test_repairs_graph_journey_and_trace_mismatches() -> None:
    from app.application.services.app_spec_validation import validate_app_spec

    fixture = Path(__file__).parent / "data" / "tmp_rev11.json"
    if not fixture.is_file():
        fixture = Path(__file__).resolve().parents[1] / "data" / "tmp_rev11.json"
    if not fixture.is_file():
        print("skip graph fixture: tmp_rev11.json missing")
        return
    payload = json.loads(fixture.read_text(encoding="utf-8"))["app_spec"]
    source = {
        "customer_input": {
            "desired_outcome": payload["product_intent"]["desired_outcome"],
            "main_problem": payload["product_intent"]["problem"],
            "business_description": payload["product_intent"].get("summary", "studio"),
        },
        "reference_evidence": {},
    }
    sanitized = sanitize_app_spec_payload(payload, source)
    spec = parse_app_spec_candidate(sanitized)
    report = validate_app_spec(spec)
    assert report.is_valid, [issue.code for issue in report.issues]


if __name__ == "__main__":
    test_strips_derived_context_refs_and_defers_blueprint_requirements()
    test_adds_page_evidence_when_missing()
    test_repairs_empty_capability_requirement_ids()
    test_normalizes_invalid_evidence_and_assertion_kinds()
    test_repairs_entity_fields_and_deferred_scope_gaps()
    test_repairs_graph_journey_and_trace_mismatches()
    print("AppSpec sanitize tests passed (6 tests)")
