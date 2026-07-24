from __future__ import annotations

import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.application.appspec.source import (
    capture_request_source_v2,
    source_sha256,
)
from app.application.preview_contract.product_strategy import (
    project_product_strategy,
)
from app.domain.models.request import Request


def _request() -> Request:
    return Request(
        id=501,
        business_name="Lumina Studio",
        industry="Wellness",
        business_description="Customers book treatments with the studio.",
        target_customers="Busy professionals",
        main_problem="Bookings arrive through private messages.",
        desired_outcome="Customers can book and reschedule online.",
        project_type="new",
        needs_ai="yes",
        email="private@example.com",
        whatsapp="+961000000",
        admin_notes="internal only",
        mvp_blueprint="Derived booking and staff operations blueprint",
        concept_name="Lumina Flow",
        preview_summary="A polished booking service for studio customers.",
        preview_features=json.dumps(["Booking", "Rescheduling"]),
        ai_features=json.dumps(
            [
                {
                    "id": "smart-reminders",
                    "name": "Smart reminders",
                    "description": "Suggest reminder timing.",
                    "surface": "ops",
                }
            ]
        ),
        created_at=datetime(2026, 7, 24, 9, 0, 0),
    )


def test_v2_source_is_frozen_and_excludes_inferred_and_private_fields() -> None:
    req = _request()
    source = capture_request_source_v2(req)
    payload = source.model_dump(mode="json")
    serialized = json.dumps(payload)

    assert payload["source_schema_version"] == "2.0"
    assert "ai_features" not in payload["customer_input"]
    for forbidden in (
        "private@example.com",
        "+961000000",
        "internal only",
        "Derived booking",
        "Lumina Flow",
        "Smart reminders",
    ):
        assert forbidden not in serialized

    with pytest.raises(ValidationError):
        source.customer_input.business_name = "Mutated"  # type: ignore[misc]


def test_derived_strategy_can_change_without_mutating_customer_source() -> None:
    req = _request()
    source = capture_request_source_v2(req)
    source_digest = source_sha256(source.model_dump(mode="json"))
    strategy = project_product_strategy(req, source)

    req.concept_name = "Lumina Operations"
    req.preview_summary = "An operations-led scheduling workspace."
    req.preview_features = json.dumps(["Capacity dashboard"])

    source_after = capture_request_source_v2(req)
    strategy_after = project_product_strategy(req, source_after)

    assert source_sha256(source_after.model_dump(mode="json")) == source_digest
    assert strategy.source_sha256 == source_digest
    assert strategy_after.source_sha256 == source_digest
    assert strategy_after.product_name != strategy.product_name
    assert (
        strategy_after.capability_hypotheses
        != strategy.capability_hypotheses
    )


def test_customer_authored_change_changes_source_and_strategy_provenance() -> None:
    req = _request()
    before = capture_request_source_v2(req)
    req.desired_outcome = "Customers can book, pay, and reschedule online."
    after = capture_request_source_v2(req)

    before_digest = source_sha256(before.model_dump(mode="json"))
    after_digest = source_sha256(after.model_dump(mode="json"))
    assert after_digest != before_digest
    assert project_product_strategy(req, after).source_sha256 == after_digest
