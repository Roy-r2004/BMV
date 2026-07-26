"""Entity-role classification and primary-collection selection (smoke #30)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.application.composition_contract.collection_derivation import (
    COLLECTION_PROJECTION_POLICY_REVISION,
    detect_collection_entity_types,
    resolve_tier1_collection_decision,
)
from app.application.composition_contract.entity_role_classification import (
    ENTITY_ROLE_POLICY_REVISION,
    classify_entity_candidates,
    select_primary_collection_types,
)
from app.application.composition_contract.projections import (
    CompositionProjectionError,
    project_content_data_plan,
)
from app.application.composition_contract.validation import (
    validate_content_data_plan,
)
from app.domain.appspec.validation import validate_app_spec
from app.domain.schemas.app_spec import AppSpec
from tests.composition_contract.test_entity_collection_projection import (
    build_harness,
)


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "app_spec"
SMOKE30 = FIXTURES / "booking_service_appointment_smoke30.json"
PRODUCT_ORDER = FIXTURES / "product_order_catalog_transaction.json"
COURSE_ENROLL = FIXTURES / "course_enrollment_catalog_transaction.json"
PROPERTY_VIEW = FIXTURES / "property_viewing_catalog_transaction.json"
EVENT_REG = FIXTURES / "event_registration_catalog_transaction.json"
JOB_APP = FIXTURES / "job_application_catalog_transaction.json"
DUAL = FIXTURES / "provider_service_dual_catalog_ambiguous.json"
APPT_HISTORY = FIXTURES / "appointment_history_collection.json"
STATIC_BOOK = FIXTURES / "static_booking_landing_no_services.json"
SMOKE28 = FIXTURES / "booking_no_entities_smoke28.json"


def _load_spec(path: Path) -> AppSpec:
    payload = json.loads(path.read_text(encoding="utf-8"))
    spec = AppSpec.model_validate(payload)
    report = validate_app_spec(spec)
    assert report.is_valid, report.model_dump(mode="json")
    return spec


def test_request_30_raw_candidates_include_service_and_appointment() -> None:
    """Reproduce #30 false ambiguity: both nouns appear in Tier 1 signals."""

    spec = _load_spec(SMOKE30)
    context, page_purpose, _, component_plan, _ = build_harness(
        spec, request_id=3001
    )
    from app.application.composition_contract.collection_derivation import (
        _gather_signal_text,
    )

    signal_text, _ = _gather_signal_text(context, page_purpose, component_plan)
    raw = detect_collection_entity_types(signal_text)
    assert "service" in raw
    assert "appointment" in raw


def test_request_30_service_outranks_appointment_no_ambiguity() -> None:
    spec = _load_spec(SMOKE30)
    original = copy.deepcopy(spec.model_dump(mode="json"))
    context, page_purpose, page_ref, component_plan, component_ref = build_harness(
        spec, request_id=3002
    )
    projected = project_content_data_plan(
        context,
        page_purpose=page_purpose,
        page_purpose_ref=page_ref,
        component_plan=component_plan,
        component_plan_ref=component_ref,
    )
    evidence = projected.collection_projection
    assert evidence is not None
    assert evidence.decision == "collection_derived"
    assert evidence.entity_type == "service"
    assert evidence.result_code == "primary_collection_selected"
    assert "appointment" in (evidence.excluded_transaction_entity_types or ())
    assert evidence.ambiguity_candidates_after_classification == ()
    assert evidence.decision_hash
    assert evidence.policy_revision == COLLECTION_PROJECTION_POLICY_REVISION
    assert ENTITY_ROLE_POLICY_REVISION in evidence.reason or evidence.entity_roles
    assert len(projected.data_collections) == 1
    assert projected.data_collections[0].entity_id == "ENTITY-SERVICE"
    # No fake appointment seed collection.
    assert all(
        item.entity_id != "ENTITY-APPOINTMENT"
        for item in projected.data_collections
    )
    # Transactional entity retained as schema without seeds.
    txn_ids = {item.id for item in (evidence.transactional_entities or ())}
    assert "ENTITY-APPOINTMENT" in txn_ids or "ENTITY-BOOKING" in txn_ids
    assert context.app_spec.model_dump(mode="json") == original
    report = validate_content_data_plan(
        projected,
        context=context,
        page_purpose=page_purpose,
        page_purpose_ref=page_ref,
        component_plan=component_plan,
        component_plan_ref=component_ref,
    )
    assert report.passed, report.model_dump(mode="json")


@pytest.mark.parametrize(
    "path_name,catalog,transaction",
    [
        ("product_order_catalog_transaction.json", "product", "order"),
        ("course_enrollment_catalog_transaction.json", "course", "enrollment"),
        ("property_viewing_catalog_transaction.json", "property", "viewing"),
        ("event_registration_catalog_transaction.json", "event", "registration"),
        ("job_application_catalog_transaction.json", "job", "application"),
    ],
)
def test_generic_catalog_outranks_transaction(
    path_name: str, catalog: str, transaction: str
) -> None:
    path = FIXTURES / path_name
    spec = _load_spec(path)
    context, page_purpose, _, component_plan, _ = build_harness(
        spec, request_id=3010
    )
    decision = resolve_tier1_collection_decision(
        context,
        page_purpose=page_purpose,
        component_plan=component_plan,
        existing_collections=[],
    )
    assert decision.code == "collection_derived"
    assert decision.entity_type == catalog
    assert transaction in (decision.excluded_transaction_entity_types or ())
    assert decision.collection is not None
    assert decision.collection.entity_id.startswith("ENTITY-")
    assert decision.collection.entity_id != f"ENTITY-{transaction.upper()}"


def test_appointment_history_may_be_primary_collection() -> None:
    spec = _load_spec(APPT_HISTORY)
    context, page_purpose, _, component_plan, _ = build_harness(
        spec, request_id=3020
    )
    decision = resolve_tier1_collection_decision(
        context,
        page_purpose=page_purpose,
        component_plan=component_plan,
        existing_collections=[],
    )
    assert decision.code == "collection_derived"
    assert decision.entity_type == "appointment"
    assert decision.collection is not None
    assert decision.collection.entity_id == "ENTITY-APPOINTMENT"
    assert decision.collection.seed_records


def test_customer_form_availability_confirmation_do_not_compete() -> None:
    spec = _load_spec(SMOKE30)
    context, page_purpose, _, component_plan, _ = build_harness(
        spec, request_id=3021
    )
    ranking = classify_entity_candidates(
        context, page_purpose=page_purpose, component_plan=component_plan
    )
    types = {item.entity_type for item in ranking.candidates}
    assert "customer" not in types
    assert "availability" not in types
    assert "confirmation" not in types
    primary = select_primary_collection_types(ranking)
    assert primary == ("service",)


def test_genuine_dual_catalog_still_ambiguous() -> None:
    spec = _load_spec(DUAL)
    context, page_purpose, page_ref, component_plan, component_ref = build_harness(
        spec, request_id=3022
    )
    with pytest.raises(CompositionProjectionError) as raised:
        project_content_data_plan(
            context,
            page_purpose=page_purpose,
            page_purpose_ref=page_ref,
            component_plan=component_plan,
            component_plan_ref=component_ref,
        )
    assert raised.value.code == "collection_ambiguous"
    decision = resolve_tier1_collection_decision(
        context,
        page_purpose=page_purpose,
        component_plan=component_plan,
        existing_collections=[],
    )
    assert decision.result_code == "genuine_primary_collection_ambiguity"
    assert set(decision.ambiguity_candidates_after_classification or ()) >= {
        "provider",
        "service",
    }


def test_static_booking_landing_does_not_invent_services() -> None:
    spec = _load_spec(STATIC_BOOK)
    context, page_purpose, _, component_plan, _ = build_harness(
        spec, request_id=3023
    )
    decision = resolve_tier1_collection_decision(
        context,
        page_purpose=page_purpose,
        component_plan=component_plan,
        existing_collections=[],
    )
    assert decision.code == "collection_not_required"
    assert decision.collection is None
    assert decision.result_code in {
        "no_primary_collection_required",
        "collection_not_required",
    }


def test_ranking_is_deterministic() -> None:
    spec = _load_spec(SMOKE30)
    context, page_purpose, _, component_plan, _ = build_harness(
        spec, request_id=3024
    )
    first = classify_entity_candidates(
        context, page_purpose=page_purpose, component_plan=component_plan
    )
    second = classify_entity_candidates(
        context, page_purpose=page_purpose, component_plan=component_plan
    )
    assert first.decision_hash == second.decision_hash
    assert [c.model_dump() for c in first.candidates] == [
        c.model_dump() for c in second.candidates
    ]


def test_existing_explicit_collection_remains_byte_stable() -> None:
    from app.domain.schemas.content_data_plan import DataCollection, SeedFieldValue, SeedRecord

    spec = _load_spec(SMOKE28)
    context, page_purpose, _, component_plan, _ = build_harness(
        spec, request_id=3025
    )
    existing = DataCollection(
        collection_id="DATA-EXISTING-SERVICES",
        entity_id="ENTITY-SERVICE",
        purpose="Provide realistic Service records for the accepted Tier 1 workflow.",
        page_ids=tuple(page.id for page in spec.pages),
        component_ids=("COMP-HOME",),
        field_ids=("FIELD-NAME",),
        seed_records=(
            SeedRecord(
                record_id="RECORD-EXISTING",
                values=(SeedFieldValue(field_id="FIELD-NAME", value="Cut"),),
            ),
        ),
    )
    first = resolve_tier1_collection_decision(
        context,
        page_purpose=page_purpose,
        component_plan=component_plan,
        existing_collections=[existing],
    )
    second = resolve_tier1_collection_decision(
        context,
        page_purpose=page_purpose,
        component_plan=component_plan,
        existing_collections=[existing],
    )
    assert first.code == "collection_reused"
    assert first.collection.model_dump(mode="json") == existing.model_dump(
        mode="json"
    )
    assert second.collection.model_dump(mode="json") == first.collection.model_dump(
        mode="json"
    )


def test_smoke30_composition_reaches_validated_content_plan() -> None:
    """Composition continues after Services is selected (usage validation gate)."""

    spec = _load_spec(SMOKE30)
    context, page_purpose, page_ref, component_plan, component_ref = build_harness(
        spec, request_id=3026
    )
    projected = project_content_data_plan(
        context,
        page_purpose=page_purpose,
        page_purpose_ref=page_ref,
        component_plan=component_plan,
        component_plan_ref=component_ref,
    )
    report = validate_content_data_plan(
        projected,
        context=context,
        page_purpose=page_purpose,
        page_purpose_ref=page_ref,
        component_plan=component_plan,
        component_plan_ref=component_ref,
    )
    assert report.passed
    assert projected.data_collections[0].entity_id == "ENTITY-SERVICE"
