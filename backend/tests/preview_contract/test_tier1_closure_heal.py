"""Focused tests for bounded Tier 1 page-closure heal (PAGE-AI-FEATURES)."""
from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

import pytest

from app.application.appspec.source import (
    canonical_json,
    capture_request_source_v2,
)
from app.application.preview_contract.product_strategy import (
    project_product_strategy,
)
from app.application.preview_contract.tier_validation import (
    validate_preview_tiers,
)
from app.application.preview_contract.tier1_closure_heal import (
    Tier1ClosureHealError,
    heal_tier1_page_closure,
)
from app.application.preview_contract.tiers import (
    TierBuildError,
    TierContractContext,
    build_preview_tiers,
    build_preview_tiers_result,
    expand_tier_graph,
)
from app.application.services.ai_features import (
    PAGE_AI_HUB_ID,
    bind_ai_features_to_app_spec,
)
from app.domain.appspec.validation import validate_app_spec
from app.domain.models.request import Request
from app.domain.schemas.app_spec import AppSpec
from app.domain.schemas.preview_tier import (
    CanonicalAppSpecRef,
    CustomerSourceRef,
    PrimaryJourneyProof,
    ProductStrategyRef,
    TIER_SELECTION_POLICY_REVISION,
)


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "app_spec"
    / "valid_booking.json"
)


def _request() -> Request:
    return Request(
        id=923,
        business_name="AI Studio",
        industry="Wellness",
        business_description="AI-powered booking recommendations for studio clients.",
        target_customers="Studio customers",
        main_problem="Appointments are coordinated manually.",
        desired_outcome="Customers can book online with AI help.",
        project_type="new",
        email="owner@example.com",
        needs_ai="yes",
        mvp_blueprint="A derived booking workflow with confirmation.",
        concept_name="AI Studio Booking",
        preview_summary="A polished booking workflow.",
        preview_features=json.dumps(["Appointment booking", "AI features"]),
        created_at=datetime(2026, 7, 25, 12, 0, 0),
    )


def _context():
    req = _request()
    source = capture_request_source_v2(req)
    strategy = project_product_strategy(req, source)
    context = TierContractContext(
        request_id=923,
        customer_source_ref=CustomerSourceRef(
            id=11,
            sha256=strategy.source_sha256,
        ),
        product_strategy_ref=ProductStrategyRef(
            id=12,
            revision=1,
            sha256="b" * 64,
        ),
        app_spec_ref=CanonicalAppSpecRef(
            id=13,
            revision=1,
            schema_version="1.0",
            sha256="c" * 64,
        ),
    )
    return req, source, strategy, context


def _base_payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _bind_ai(payload: dict) -> dict:
    features = [
        {
            "id": "booking-reco",
            "name": "Booking recommendations",
            "description": "Suggests appointment slots.",
            "category": "recommend",
        }
    ]
    return bind_ai_features_to_app_spec(payload, features)


def _ai_ids(payload: dict) -> tuple[str, str, str]:
    req_id = next(
        req["id"]
        for req in payload["requirements"]
        if str(req["id"]).startswith("REQ-AI")
    )
    test_id = next(
        test["id"]
        for test in payload["acceptance_tests"]
        if str(test["id"]).startswith("TEST-AI")
    )
    evidence_id = next(
        item["id"]
        for item in payload["evidence"]
        if str(item["id"]).startswith("EVIDENCE-AI")
    )
    return req_id, test_id, evidence_id


def _ensure_ai_hub_interaction(payload: dict) -> str:
    """Add a no-op interaction on the AI hub so journeys can have a step."""

    action_id = "ACTION-VIEW-AI"
    transition_id = "TRANSITION-VIEW-AI"
    if not any(item["id"] == action_id for item in payload["actions"]):
        payload["actions"].append(
            {
                "id": action_id,
                "page_id": PAGE_AI_HUB_ID,
                "role_id": "ROLE-CUSTOMER",
                "name": "View AI features",
                "description": "Customer reviews AI feature cards.",
                "kind": "click",
                "capability_ids": [
                    next(
                        cap["id"]
                        for cap in payload["capabilities"]
                        if str(cap["id"]).startswith("CAP-AI")
                    )
                ],
                "entity_id": None,
                "input_label": None,
            }
        )
    if not any(item["id"] == transition_id for item in payload["transitions"]):
        payload["transitions"].append(
            {
                "id": transition_id,
                "action_id": action_id,
                "from_state_id": "STATE-AI-HUB-READY",
                "to_state_id": "STATE-AI-HUB-READY",
                "description": "AI hub remains ready after viewing features.",
                "preconditions": [],
                "postconditions": ["AI features remain visible"],
                "effects": [],
            }
        )
    hub = next(page for page in payload["pages"] if page["id"] == PAGE_AI_HUB_ID)
    hub_actions = list(hub.get("action_ids") or [])
    if action_id not in hub_actions:
        hub_actions.append(action_id)
    hub["action_ids"] = hub_actions
    return action_id


def _attach_closed_ai_journey(payload: dict) -> dict:
    """Add a Tier-1-capable AI hub journey with requirement + acceptance proof."""

    req_id, test_id, evidence_id = _ai_ids(payload)
    action_id = _ensure_ai_hub_interaction(payload)
    payload["journeys"].append(
        {
            "id": "JOURNEY-AI",
            "name": "Explore AI features",
            "description": "Customer opens the AI features hub.",
            "role_id": "ROLE-CUSTOMER",
            "requirement_ids": [req_id],
            "start_page_id": PAGE_AI_HUB_ID,
            "start_state_id": "STATE-AI-HUB-READY",
            "steps": [
                {
                    "id": "STEP-VIEW-AI",
                    "action_id": action_id,
                    "transition_id": "TRANSITION-VIEW-AI",
                    "expected_page_id": PAGE_AI_HUB_ID,
                    "expected_state_id": "STATE-AI-HUB-READY",
                    "evidence_ids": [evidence_id],
                }
            ],
        }
    )
    for test in payload["acceptance_tests"]:
        if test["id"] == test_id:
            test["journey_id"] = "JOURNEY-AI"
            test["requirement_ids"] = [req_id]
    for link in payload["traceability"]:
        if link["requirement_id"] == req_id:
            link["journey_ids"] = ["JOURNEY-AI"]
            link["acceptance_test_ids"] = [test_id]
            link["page_ids"] = [PAGE_AI_HUB_ID]
            link["evidence_ids"] = [evidence_id]
    # Pull the AI journey into Tier 1 via the primary booking journey.
    payload["journeys"][0]["requirement_ids"] = ["REQ-BOOK", req_id]
    return payload


def test_generic_ai_bind_does_not_add_ai_hub_to_tier1() -> None:
    payload = _bind_ai(_base_payload())
    original = copy.deepcopy(payload)
    spec = AppSpec.model_validate(payload)
    assert validate_app_spec(spec).is_valid
    _, _, strategy, context = _context()
    result = build_preview_tiers_result(
        spec=spec,
        strategy=strategy,
        context=context,
    )
    assert PAGE_AI_HUB_ID not in result.tiers[0].references.page_ids
    assert PAGE_AI_HUB_ID in result.tiers[1].references.page_ids
    assert PAGE_AI_HUB_ID in result.tiers[2].references.page_ids
    assert payload == original
    assert result.tier1_closure_heal["heal_passes"] == 1
    assert result.tier1_closure_heal["decision_hash"]


def test_requirement_trace_cannot_pull_ai_hub_without_journey() -> None:
    payload = _bind_ai(_base_payload())
    spec = AppSpec.model_validate(payload)
    assert validate_app_spec(spec).is_valid
    ai_req, ai_test, _ = _ai_ids(payload)
    refs = expand_tier_graph(
        spec,
        {
            "requirement_ids": {"REQ-BOOK", ai_req},
            "acceptance_test_ids": {"TEST-BOOK", ai_test},
            "journey_ids": {"JOURNEY-BOOK"},
            "page_ids": {"PAGE-BOOK"},
            "action_ids": set(),
            "transition_ids": set(),
            "evidence_ids": set(),
            "role_ids": set(),
            "entity_ids": set(),
            "capability_ids": set(),
            "state_ids": set(),
        },
        require_journey_page_closure=True,
    )
    assert PAGE_AI_HUB_ID not in refs["page_ids"]
    assert "PAGE-BOOK" in refs["page_ids"]


def test_role_default_alone_does_not_retain_ai_hub() -> None:
    payload = _bind_ai(_base_payload())
    payload["roles"][0]["default_page_id"] = PAGE_AI_HUB_ID
    spec = AppSpec.model_validate(payload)
    _, _, strategy, context = _context()
    tiers = build_preview_tiers(spec=spec, strategy=strategy, context=context)
    assert PAGE_AI_HUB_ID not in tiers[0].references.page_ids


def test_acceptance_assertion_without_journey_does_not_retain_ai_hub() -> None:
    payload = _bind_ai(_base_payload())
    spec = AppSpec.model_validate(payload)
    assert validate_app_spec(spec).is_valid
    _, ai_test, _ = _ai_ids(payload)
    refs = expand_tier_graph(
        spec,
        {
            "acceptance_test_ids": {ai_test},
            "requirement_ids": set(),
            "journey_ids": set(),
            "page_ids": set(),
            "action_ids": set(),
            "transition_ids": set(),
            "evidence_ids": set(),
            "role_ids": set(),
            "entity_ids": set(),
            "capability_ids": set(),
            "state_ids": set(),
        },
        require_journey_page_closure=True,
    )
    assert PAGE_AI_HUB_ID not in refs["page_ids"]


def test_optional_seeded_ai_hub_is_excluded_by_heal() -> None:
    payload = _bind_ai(_base_payload())
    spec = AppSpec.model_validate(payload)
    _, _, strategy, context = _context()
    seeds = {
        "requirement_ids": {"REQ-BOOK"},
        "journey_ids": {"JOURNEY-BOOK"},
        "page_ids": {"PAGE-BOOK", PAGE_AI_HUB_ID},
        "action_ids": {"ACTION-SUBMIT"},
        "transition_ids": {"TRANSITION-SUBMIT"},
        "evidence_ids": {"EVIDENCE-CONFIRMATION"},
        "acceptance_test_ids": {"TEST-BOOK"},
        "role_ids": set(),
        "entity_ids": set(),
        "capability_ids": set(),
        "state_ids": set(),
    }
    closed = expand_tier_graph(
        spec,
        seeds,
        require_journey_page_closure=True,
    )
    assert PAGE_AI_HUB_ID in closed["page_ids"]
    primary = build_preview_tiers(spec=spec, strategy=strategy, context=context)[
        0
    ].primary_journey_proof
    healed, audit = heal_tier1_page_closure(
        spec,
        closed,
        primary_proof=primary,
        request_id=923,
        app_spec_revision=1,
    )
    assert PAGE_AI_HUB_ID not in healed["page_ids"]
    decision = next(
        item
        for item in audit["page_decisions"]
        if item["page_id"] == PAGE_AI_HUB_ID
    )
    assert decision["decision"] in {
        "excluded_optional_unclosed",
        "excluded_unused",
    }
    assert decision["classification"] == "optional"
    assert "PAGE-BOOK" in healed["page_ids"]


def test_explicit_closed_ai_hub_journey_is_retained() -> None:
    payload = _attach_closed_ai_journey(_bind_ai(_base_payload()))
    spec = AppSpec.model_validate(payload)
    assert validate_app_spec(spec).is_valid, validate_app_spec(spec).model_dump()
    _, _, strategy, context = _context()
    result = build_preview_tiers_result(
        spec=spec,
        strategy=strategy,
        context=context,
    )
    assert PAGE_AI_HUB_ID in result.tiers[0].references.page_ids
    decision = next(
        item
        for item in result.tier1_closure_heal["page_decisions"]
        if item["page_id"] == PAGE_AI_HUB_ID
    )
    assert decision["decision"] == "retained"
    assert "JOURNEY-AI" in decision["supporting_journey_ids"]


def test_mandatory_incomplete_ai_hub_journey_fails_closed() -> None:
    """Covered by direct heal rejection; build path uses the same error type."""

    payload = _bind_ai(_base_payload())
    action_id = _ensure_ai_hub_interaction(payload)
    evidence_id = _ai_ids(payload)[2]
    # Strip AI requirement graph so the hub can be journey-required without
    # a closing requirement trace (composition would also fail closed).
    payload["requirements"] = [
        req
        for req in payload["requirements"]
        if not str(req["id"]).startswith("REQ-AI")
    ]
    payload["capabilities"] = [
        cap
        for cap in payload["capabilities"]
        if not str(cap["id"]).startswith("CAP-AI")
    ]
    payload["acceptance_tests"] = [
        test
        for test in payload["acceptance_tests"]
        if not str(test["id"]).startswith("TEST-AI")
    ]
    payload["traceability"] = [
        link
        for link in payload["traceability"]
        if not str(link["requirement_id"]).startswith("REQ-AI")
    ]
    hub = next(page for page in payload["pages"] if page["id"] == PAGE_AI_HUB_ID)
    hub["capability_ids"] = ["CAP-BOOK"]
    hub["evidence_ids"] = [evidence_id]
    for action in payload["actions"]:
        if action["id"] == action_id:
            action["capability_ids"] = ["CAP-BOOK"]
    for evidence in payload["evidence"]:
        if evidence["id"] == evidence_id:
            evidence["capability_ids"] = ["CAP-BOOK"]
    payload["journeys"].append(
        {
            "id": "JOURNEY-AI",
            "name": "Explore AI features",
            "description": "Customer opens the AI features hub.",
            "role_id": "ROLE-CUSTOMER",
            "requirement_ids": ["REQ-BOOK"],
            "start_page_id": PAGE_AI_HUB_ID,
            "start_state_id": "STATE-AI-HUB-READY",
            "steps": [
                {
                    "id": "STEP-VIEW-AI",
                    "action_id": action_id,
                    "transition_id": "TRANSITION-VIEW-AI",
                    "expected_page_id": PAGE_AI_HUB_ID,
                    "expected_state_id": "STATE-AI-HUB-READY",
                    "evidence_ids": [evidence_id],
                }
            ],
        }
    )
    payload["acceptance_tests"].append(
        {
            "id": "TEST-AI-JOURNEY",
            "name": "AI journey exists",
            "description": "Journey reaches the AI hub.",
            "requirement_ids": ["REQ-BOOK"],
            "journey_id": "JOURNEY-AI",
            "assertions": [
                {
                    "kind": "visible",
                    "description": "Booking confirmation remains visible.",
                    "page_id": "PAGE-BOOK",
                    "state_id": "STATE-CONFIRMED",
                    "evidence_id": "EVIDENCE-CONFIRMATION",
                    "expected": "confirmed",
                }
            ],
        }
    )
    for link in payload["traceability"]:
        if link["requirement_id"] == "REQ-BOOK":
            link["journey_ids"] = list(
                dict.fromkeys([*(link.get("journey_ids") or []), "JOURNEY-AI"])
            )
            link["acceptance_test_ids"] = list(
                dict.fromkeys(
                    [*(link.get("acceptance_test_ids") or []), "TEST-AI-JOURNEY"]
                )
            )
    spec = AppSpec.model_validate(payload)
    assert validate_app_spec(spec).is_valid, validate_app_spec(spec).model_dump()
    _, _, strategy, context = _context()
    with pytest.raises(TierBuildError, match="PAGE-AI-FEATURES"):
        build_preview_tiers(spec=spec, strategy=strategy, context=context)


def test_heal_rejects_mandatory_unclosed_directly() -> None:
    payload = _bind_ai(_base_payload())
    action_id = _ensure_ai_hub_interaction(payload)
    evidence_id = _ai_ids(payload)[2]
    refs = {
        "requirement_ids": {"REQ-BOOK"},
        "role_ids": {"ROLE-CUSTOMER"},
        "entity_ids": set(),
        "capability_ids": {"CAP-BOOK"},
        "page_ids": {"PAGE-BOOK", PAGE_AI_HUB_ID},
        "state_ids": {"STATE-DRAFT"},
        "action_ids": {"ACTION-SUBMIT"},
        "transition_ids": {"TRANSITION-SUBMIT"},
        "evidence_ids": {"EVIDENCE-CONFIRMATION"},
        "journey_ids": {"JOURNEY-BOOK", "JOURNEY-AI"},
        "acceptance_test_ids": {"TEST-BOOK"},
    }
    # Synthetic journey map: pretend JOURNEY-AI requires the hub.
    payload["journeys"].append(
        {
            "id": "JOURNEY-AI",
            "name": "Explore AI features",
            "description": "Customer opens the AI features hub.",
            "role_id": "ROLE-CUSTOMER",
            "requirement_ids": ["REQ-BOOK"],
            "start_page_id": PAGE_AI_HUB_ID,
            "start_state_id": "STATE-AI-HUB-READY",
            "steps": [
                {
                    "id": "STEP-VIEW-AI",
                    "action_id": action_id,
                    "transition_id": "TRANSITION-VIEW-AI",
                    "expected_page_id": PAGE_AI_HUB_ID,
                    "expected_state_id": "STATE-AI-HUB-READY",
                    "evidence_ids": [evidence_id],
                }
            ],
        }
    )
    payload["acceptance_tests"].append(
        {
            "id": "TEST-AI-JOURNEY",
            "name": "AI journey exists",
            "description": "Journey reaches the AI hub.",
            "requirement_ids": ["REQ-BOOK"],
            "journey_id": "JOURNEY-AI",
            "assertions": [
                {
                    "kind": "visible",
                    "description": "Booking confirmation remains visible.",
                    "page_id": "PAGE-BOOK",
                    "state_id": "STATE-CONFIRMED",
                    "evidence_id": "EVIDENCE-CONFIRMATION",
                    "expected": "confirmed",
                }
            ],
        }
    )
    refs["acceptance_test_ids"].add("TEST-AI-JOURNEY")
    spec = AppSpec.model_validate(payload)
    primary = PrimaryJourneyProof(
        requirement_id="REQ-BOOK",
        journey_id="JOURNEY-BOOK",
        page_ids=("PAGE-BOOK",),
        action_ids=("ACTION-SUBMIT",),
        transition_ids=("TRANSITION-SUBMIT",),
        success_evidence_ids=("EVIDENCE-CONFIRMATION",),
        acceptance_test_id="TEST-BOOK",
    )
    with pytest.raises(Tier1ClosureHealError, match="PAGE-AI-FEATURES"):
        heal_tier1_page_closure(
            spec,
            refs,
            primary_proof=primary,
            request_id=923,
            app_spec_revision=1,
        )


def test_tier2_must_ai_requirements_do_not_force_hub_into_tier1() -> None:
    payload = _bind_ai(_base_payload())
    spec = AppSpec.model_validate(payload)
    _, _, strategy, context = _context()
    tiers = build_preview_tiers(spec=spec, strategy=strategy, context=context)
    assert PAGE_AI_HUB_ID not in tiers[0].references.page_ids
    assert any(
        item.startswith("REQ-AI") for item in tiers[1].references.requirement_ids
    )


def test_appspec_remains_immutable_and_hub_stays_in_full_contract() -> None:
    payload = _bind_ai(_base_payload())
    original = copy.deepcopy(payload)
    spec = AppSpec.model_validate(payload)
    _, _, strategy, context = _context()
    tiers = build_preview_tiers(spec=spec, strategy=strategy, context=context)
    assert payload == original
    assert PAGE_AI_HUB_ID in {page.id for page in spec.pages}
    assert PAGE_AI_HUB_ID in tiers[2].references.page_ids


def test_healed_tier1_is_byte_stable_and_validates() -> None:
    payload = _bind_ai(_base_payload())
    spec = AppSpec.model_validate(payload)
    _, _, strategy, context = _context()
    first = build_preview_tiers(spec=spec, strategy=strategy, context=context)
    second = build_preview_tiers(spec=spec, strategy=strategy, context=context)
    assert first[0].model_dump(mode="json") == second[0].model_dump(mode="json")
    assert first[0].selection_policy_revision == TIER_SELECTION_POLICY_REVISION
    report = validate_preview_tiers(
        first,
        spec=spec,
        strategy=strategy,
        context=context,
    )
    assert report.passed


def test_admin_dashboard_role_default_regression_still_holds() -> None:
    payload = _base_payload()
    payload["roles"].append(
        {
            "id": "ROLE-ADMIN",
            "name": "Admin",
            "description": "Studio operator.",
            "goals": ["Review bookings"],
            "default_page_id": "PAGE-ADMIN-DASHBOARD",
        }
    )
    payload["capabilities"][0]["role_ids"] = ["ROLE-CUSTOMER", "ROLE-ADMIN"]
    payload["pages"].append(
        {
            "id": "PAGE-ADMIN-DASHBOARD",
            "name": "Admin dashboard",
            "purpose": "Operator overview without a Tier 1 journey.",
            "route": "/admin",
            "surface": "ops",
            "primary": False,
            "role_ids": ["ROLE-ADMIN"],
            "capability_ids": ["CAP-BOOK"],
            "state_ids": ["STATE-ADMIN-READY"],
            "action_ids": [],
            "evidence_ids": ["EVIDENCE-ADMIN"],
        }
    )
    payload["states"].append(
        {
            "id": "STATE-ADMIN-READY",
            "page_id": "PAGE-ADMIN-DASHBOARD",
            "name": "Ready",
            "description": "Dashboard is ready.",
            "initial": True,
            "terminal": True,
            "evidence_ids": ["EVIDENCE-ADMIN"],
        }
    )
    payload["evidence"].append(
        {
            "id": "EVIDENCE-ADMIN",
            "page_id": "PAGE-ADMIN-DASHBOARD",
            "name": "Admin summary",
            "description": "Operator summary is visible.",
            "kind": "text",
            "capability_ids": ["CAP-BOOK"],
        }
    )
    spec = AppSpec.model_validate(payload)
    _, _, strategy, context = _context()
    tiers = build_preview_tiers(spec=spec, strategy=strategy, context=context)
    assert "PAGE-ADMIN-DASHBOARD" not in tiers[0].references.page_ids


def test_derived_tier1_contract_excludes_hub_while_tier3_keeps_it() -> None:
    payload = _bind_ai(_base_payload())
    spec = AppSpec.model_validate(payload)
    _, _, strategy, context = _context()
    result = build_preview_tiers_result(
        spec=spec,
        strategy=strategy,
        context=context,
    )
    tier1_json = canonical_json(result.tiers[0].model_dump(mode="json"))
    tier3_json = canonical_json(result.tiers[2].model_dump(mode="json"))
    assert PAGE_AI_HUB_ID not in result.tiers[0].references.page_ids
    assert PAGE_AI_HUB_ID in result.tiers[2].references.page_ids
    assert PAGE_AI_HUB_ID not in tier1_json or '"PAGE-AI-FEATURES"' not in (
        # primary proof / references should not list the hub in Tier 1
        json.dumps(list(result.tiers[0].references.page_ids))
    )
    assert '"PAGE-AI-FEATURES"' in tier3_json
