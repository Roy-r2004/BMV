"""Unreachable states must be pruned so AppSpec can approve."""
from __future__ import annotations

from app.domain.appspec.sanitize import sanitize_app_spec_payload


def test_sanitize_drops_unreachable_payment_failed_state() -> None:
    payload = {
        "schema_version": "1.0",
        "product_intent": {
            "name": "Studio",
            "summary": "Booking",
            "problem": "Manual",
            "desired_outcome": "Book online",
            "target_users": ["Customers"],
            "success_metrics": ["Booked"],
        },
        "requirements": [
            {
                "id": "REQ-BOOK",
                "title": "Book",
                "description": "Book a class",
                "priority": "must",
                "verification_mode": "content",
                "source_refs": ["customer_input.desired_outcome"],
            }
        ],
        "assumptions": [],
        "open_questions": [],
        "roles": [
            {
                "id": "ROLE-CUSTOMER",
                "name": "Customer",
                "description": "Books",
                "goals": ["Book"],
                "default_page_id": "PAGE-BOOK",
            }
        ],
        "entities": [],
        "capabilities": [
            {
                "id": "CAP-BOOK",
                "name": "Book",
                "description": "Book",
                "requirement_ids": ["REQ-BOOK"],
                "role_ids": ["ROLE-CUSTOMER"],
                "entity_ids": [],
            }
        ],
        "pages": [
            {
                "id": "PAGE-BOOK",
                "name": "Book",
                "purpose": "Book",
                "route": "/book",
                "surface": "public",
                "primary": True,
                "role_ids": ["ROLE-CUSTOMER"],
                "capability_ids": ["CAP-BOOK"],
                "state_ids": ["STATE-READY", "STATE-PAYMENT-FAILED"],
                "action_ids": ["ACTION-SUBMIT"],
                "evidence_ids": [],
            }
        ],
        "states": [
            {
                "id": "STATE-READY",
                "page_id": "PAGE-BOOK",
                "name": "Ready",
                "initial": True,
                "terminal": False,
            },
            {
                "id": "STATE-PAYMENT-FAILED",
                "page_id": "PAGE-BOOK",
                "name": "Payment failed",
                "initial": False,
                "terminal": True,
            },
        ],
        "actions": [
            {
                "id": "ACTION-SUBMIT",
                "page_id": "PAGE-BOOK",
                "name": "Submit",
                "kind": "submit",
                "capability_ids": ["CAP-BOOK"],
            }
        ],
        "transitions": [
            {
                "id": "TR-SUBMIT",
                "from_state_id": "STATE-READY",
                "to_state_id": "STATE-READY",
                "action_id": "ACTION-SUBMIT",
                "effects": [],
            }
        ],
        "journeys": [],
        "evidence": [],
        "acceptance_tests": [],
        "traceability": [],
        "deferred_scope": [],
    }
    source = {"customer_input": {"desired_outcome": "Book online"}, "reference_evidence": {}}
    out = sanitize_app_spec_payload(payload, source)
    state_ids = {s["id"] for s in out.get("states") or []}
    assert "STATE-READY" in state_ids
    assert "STATE-PAYMENT-FAILED" not in state_ids
