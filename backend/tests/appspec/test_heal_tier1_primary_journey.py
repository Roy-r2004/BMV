from __future__ import annotations

from app.domain.appspec.sanitize.heal import heal_app_spec_payload


def test_heal_marks_terminal_and_adds_visible_assertion() -> None:
    payload = {
        "schema_version": "1.0",
        "requirements": [
            {
                "id": "REQ-BOOK",
                "verification_mode": "interaction",
                "priority": "must",
                "source_refs": ["customer_input.desired_outcome"],
            }
        ],
        "journeys": [
            {
                "id": "JOURNEY-1",
                "requirement_ids": ["REQ-BOOK"],
                "steps": [
                    {
                        "id": "STEP-1",
                        "action_id": "ACT-1",
                        "transition_id": "TR-1",
                        "expected_page_id": "PAGE-1",
                        "expected_state_id": "STATE-1",
                        "evidence_ids": ["EV-1"],
                    }
                ],
            }
        ],
        "states": [
            {
                "id": "STATE-1",
                "page_id": "PAGE-1",
                "name": "Done",
                "description": "Done",
                "terminal": False,
                "evidence_ids": [],
            }
        ],
        "evidence": [
            {
                "id": "EV-1",
                "page_id": "PAGE-1",
                "name": "Confirm",
                "description": "Confirm",
                "kind": "status",
                "capability_ids": ["CAP-1"],
            }
        ],
        "acceptance_tests": [
            {
                "id": "TEST-1",
                "requirement_ids": ["REQ-BOOK"],
                "journey_id": "JOURNEY-1",
                "assertions": [
                    {
                        "kind": "route",
                        "description": "Landed",
                        "page_id": "PAGE-1",
                    }
                ],
            }
        ],
        "traceability": [
            {
                "requirement_id": "REQ-BOOK",
                "capability_ids": ["CAP-1"],
                "page_ids": ["PAGE-1"],
                "evidence_ids": ["EV-1"],
                "journey_ids": ["JOURNEY-1"],
                "acceptance_test_ids": ["TEST-1"],
            }
        ],
        "deferred_scope": [],
    }
    healed, actions = heal_app_spec_payload(
        payload,
        {
            "passed": False,
            "issues": [
                {
                    "code": "tier1_primary_journey_incomplete",
                    "message": "missing primary journey",
                }
            ],
        },
    )
    assert actions
    assert healed["states"][0]["terminal"] is True
    assert "EV-1" in healed["states"][0]["evidence_ids"]
    assert any(
        assertion.get("kind") == "visible"
        and assertion.get("evidence_id") == "EV-1"
        for assertion in healed["acceptance_tests"][0]["assertions"]
    )
