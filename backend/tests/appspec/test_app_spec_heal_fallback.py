"""Tests for AppSpec deterministic heal + fallback safety net."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.appspec.builder import parse_app_spec_candidate
from app.application.appspec.fallback import (
    build_fallback_app_spec,
    build_fallback_coverage_payload,
)
from app.domain.appspec.sanitize import heal_app_spec_payload, sanitize_app_spec_payload
from app.domain.appspec.validation import validate_app_spec


def test_heal_strips_extra_assertion_fields_from_parse_report() -> None:
    payload = {
        "schema_version": "1.0",
        "acceptance_tests": [
            {
                "id": "TEST-1",
                "assertions": [
                    {
                        "kind": "data",
                        "description": "Order updated",
                        "entity_id": "ENTITY-ORDER",
                    }
                ],
            }
        ],
    }
    report = {
        "passed": False,
        "issues": [
            {
                "code": "app_spec_schema_parse_failed",
                "detail": [
                    {
                        "type": "extra_forbidden",
                        "loc": ["acceptance_tests", 0, "assertions", 0, "entity_id"],
                        "msg": "Extra inputs are not permitted",
                        "input": "ENTITY-ORDER",
                    }
                ],
            }
        ],
    }
    healed, actions = heal_app_spec_payload(payload, report, {})
    assert any(a.startswith("strip_extra:") for a in actions)
    assert "entity_id" not in healed["acceptance_tests"][0]["assertions"][0]


def test_heal_coerces_reference_entity_not_allowed() -> None:
    payload = {
        "entities": [
            {
                "id": "ENTITY-ORDER",
                "fields": [
                    {
                        "id": "orderAssetId",
                        "type": "string",
                        "reference_entity_id": "ENTITY-ASSET",
                    }
                ],
            }
        ]
    }
    report = {
        "issues": [
            {
                "code": "reference_entity_not_allowed",
                "path": ["entities", 0, "fields", 0, "reference_entity_id"],
            }
        ]
    }
    healed, actions = heal_app_spec_payload(payload, report, {})
    assert healed["entities"][0]["fields"][0]["type"] == "reference"
    assert actions


def test_fallback_app_spec_is_always_valid() -> None:
    source = {
        "customer_input": {
            "business_name": "TradeForge",
            "business_description": "Stock trading desk",
            "main_problem": "Fragmented tools",
            "desired_outcome": "Place orders and track P&L",
            "target_customers": "Retail traders",
        },
        "reference_evidence": {},
    }
    spec = build_fallback_app_spec(source)
    report = validate_app_spec(spec)
    assert report.is_valid, [i.code for i in report.issues]
    coverage = build_fallback_coverage_payload(spec, source)
    assert coverage["passed"] is True
    assert coverage["verdict"] == "pass"


def test_sanitize_plus_heal_recovers_reference_mismatch() -> None:
    source = {
        "customer_input": {
            "desired_outcome": "Place orders",
            "business_description": "Trading",
            "main_problem": "Chaos",
        },
        "reference_evidence": {},
    }
    payload = {
        "schema_version": "1.0",
        "product_intent": {
            "name": "TradeForge",
            "summary": "Trading desk",
            "problem": "Fragmented order flow",
            "desired_outcome": "Place orders",
            "target_users": ["Traders"],
            "success_metrics": ["Orders filled"],
        },
        "requirements": [
            {
                "id": "REQ-ORDER",
                "title": "Place order",
                "description": "Place simulated order.",
                "priority": "must",
                "verification_mode": "interaction",
                "source_refs": ["customer_input.desired_outcome"],
            }
        ],
        "assumptions": [],
        "open_questions": [],
        "roles": [
            {
                "id": "ROLE-TRADER",
                "name": "Trader",
                "description": "Places orders.",
                "goals": ["Trade"],
                "default_page_id": "PAGE-DESK",
            }
        ],
        "entities": [
            {
                "id": "ENTITY-ASSET",
                "name": "Asset",
                "description": "Asset",
                "fields": [{"id": "symbol", "name": "Symbol", "type": "string"}],
            },
            {
                "id": "ENTITY-ORDER",
                "name": "Order",
                "description": "Order",
                "fields": [
                    {
                        "id": "orderAssetId",
                        "name": "Asset",
                        "type": "string",
                        "reference_entity_id": "ENTITY-ASSET",
                    }
                ],
            },
        ],
        "capabilities": [
            {
                "id": "CAP-ORDER",
                "name": "Order",
                "description": "Orders",
                "requirement_ids": ["REQ-ORDER"],
                "role_ids": ["ROLE-TRADER"],
                "entity_ids": ["ENTITY-ORDER", "ENTITY-ASSET"],
            }
        ],
        "pages": [
            {
                "id": "PAGE-DESK",
                "name": "Desk",
                "purpose": "Desk",
                "route": "/desk",
                "surface": "ops",
                "primary": True,
                "role_ids": ["ROLE-TRADER"],
                "capability_ids": ["CAP-ORDER"],
                "state_ids": ["STATE-READY"],
                "action_ids": [],
                "evidence_ids": ["EVIDENCE-DESK"],
            }
        ],
        "states": [
            {
                "id": "STATE-READY",
                "page_id": "PAGE-DESK",
                "name": "Ready",
                "description": "Ready",
                "initial": True,
                "terminal": False,
                "evidence_ids": [],
            }
        ],
        "actions": [],
        "transitions": [],
        "evidence": [
            {
                "id": "EVIDENCE-DESK",
                "page_id": "PAGE-DESK",
                "name": "Ticket",
                "description": "Ticket visible",
                "kind": "form",
                "capability_ids": ["CAP-ORDER"],
            }
        ],
        "journeys": [],
        "acceptance_tests": [
            {
                "id": "TEST-ORDER",
                "name": "Order",
                "description": "Order works",
                "requirement_ids": ["REQ-ORDER"],
                "assertions": [
                    {
                        "kind": "visible",
                        "description": "Visible",
                        "page_id": "PAGE-DESK",
                        "evidence_id": "EVIDENCE-DESK",
                    }
                ],
            }
        ],
        "traceability": [
            {
                "requirement_id": "REQ-ORDER",
                "capability_ids": ["CAP-ORDER"],
                "page_ids": ["PAGE-DESK"],
                "evidence_ids": ["EVIDENCE-DESK"],
                "journey_ids": [],
                "acceptance_test_ids": ["TEST-ORDER"],
            }
        ],
        "deferred_scope": [],
    }
    sanitized = sanitize_app_spec_payload(payload, source)
    spec = parse_app_spec_candidate(sanitized)
    report = validate_app_spec(spec)
    assert report.is_valid, [i.code for i in report.issues]


if __name__ == "__main__":
    test_heal_strips_extra_assertion_fields_from_parse_report()
    test_heal_coerces_reference_entity_not_allowed()
    test_fallback_app_spec_is_always_valid()
    test_sanitize_plus_heal_recovers_reference_mismatch()
    print("heal/fallback tests passed")
