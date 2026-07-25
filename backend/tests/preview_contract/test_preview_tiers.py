from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.application.appspec.source import (
    canonical_json,
    capture_request_source_v2,
)
from app.application.preview_contract.product_strategy import (
    project_product_strategy,
)
from app.application.preview_contract.repository import (
    PartialTierSetError,
    PreviewContractRepository,
    TierPolicyRevisionMismatch,
    tier_artifact_sha256,
)
from app.application.preview_contract.tier_validation import (
    validate_preview_tiers,
)
from app.application.preview_contract.tiers import (
    TierBuildError,
    TierContractContext,
    build_preview_tiers,
    expand_tier_graph,
)
from app.domain.appspec.validation import app_spec_sha256, validate_app_spec
from app.domain.models import (
    AppSpecRevision,
    PreviewTierArtifactRecord,
    Request,
)
from app.domain.schemas.app_spec import AppSpec
from app.domain.schemas.preview_tier import (
    CanonicalAppSpecRef,
    CustomerSourceRef,
    PreviewTierArtifact,
    ProductStrategyRef,
    TIER_SELECTION_POLICY_REVISION,
)
from app.infrastructure.db.base import Base


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "app_spec"
    / "valid_booking.json"
)
REFERENCE_FIELDS = (
    "requirement_ids",
    "role_ids",
    "entity_ids",
    "capability_ids",
    "page_ids",
    "state_ids",
    "action_ids",
    "transition_ids",
    "evidence_ids",
    "journey_ids",
    "acceptance_test_ids",
)


def _request(request_id: int = 901) -> Request:
    return Request(
        id=request_id,
        business_name="Lumina Studio",
        industry="Wellness",
        business_description="Customers book treatments online.",
        target_customers="Studio customers",
        main_problem="Appointments are coordinated manually.",
        desired_outcome="Customers can book online.",
        project_type="new",
        email="owner@example.com",
        mvp_blueprint="A derived booking workflow with confirmation.",
        concept_name="Lumina Booking",
        preview_summary="A polished booking workflow.",
        preview_features=json.dumps(["Appointment booking"]),
        created_at=datetime(2026, 7, 24, 12, 0, 0),
    )


def _add_content_requirement(
    payload: dict,
    *,
    suffix: str,
    priority: str,
    route: str,
) -> None:
    requirement_id = f"REQ-{suffix}"
    capability_id = f"CAP-{suffix}"
    page_id = f"PAGE-{suffix}"
    state_id = f"STATE-{suffix}"
    evidence_id = f"EVIDENCE-{suffix}"
    test_id = f"TEST-{suffix}"
    payload["requirements"].append(
        {
            "id": requirement_id,
            "title": f"{suffix.title()} information",
            "description": f"Customers can review {suffix.lower()} information.",
            "priority": priority,
            "verification_mode": "content",
            "source_refs": ["customer_input.business_description"],
        }
    )
    payload["capabilities"].append(
        {
            "id": capability_id,
            "name": f"{suffix.title()} information",
            "description": f"Present {suffix.lower()} information.",
            "requirement_ids": [requirement_id],
            "role_ids": ["ROLE-CUSTOMER"],
            "entity_ids": [],
        }
    )
    payload["pages"].append(
        {
            "id": page_id,
            "name": suffix.title(),
            "purpose": f"Show {suffix.lower()} information.",
            "route": route,
            "surface": "public",
            "primary": False,
            "role_ids": ["ROLE-CUSTOMER"],
            "capability_ids": [capability_id],
            "state_ids": [state_id],
            "action_ids": [],
            "evidence_ids": [evidence_id],
        }
    )
    payload["states"].append(
        {
            "id": state_id,
            "page_id": page_id,
            "name": "Ready",
            "description": f"The {suffix.lower()} content is ready.",
            "initial": True,
            "terminal": True,
            "evidence_ids": [evidence_id],
        }
    )
    payload["evidence"].append(
        {
            "id": evidence_id,
            "page_id": page_id,
            "name": f"{suffix.title()} content",
            "description": f"The {suffix.lower()} content is visible.",
            "kind": "text",
            "capability_ids": [capability_id],
        }
    )
    payload["acceptance_tests"].append(
        {
            "id": test_id,
            "name": f"{suffix.title()} content is visible",
            "description": f"Prove {suffix.lower()} content is present.",
            "requirement_ids": [requirement_id],
            "journey_id": None,
            "assertions": [
                {
                    "kind": "visible",
                    "description": f"The {suffix.lower()} content is visible.",
                    "page_id": page_id,
                    "state_id": state_id,
                    "evidence_id": evidence_id,
                    "expected": suffix.lower(),
                }
            ],
        }
    )
    payload["traceability"].append(
        {
            "requirement_id": requirement_id,
            "capability_ids": [capability_id],
            "page_ids": [page_id],
            "evidence_ids": [evidence_id],
            "journey_ids": [],
            "acceptance_test_ids": [test_id],
        }
    )


def _tiered_spec(*, page_count: int = 3) -> AppSpec:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    _add_content_requirement(
        payload,
        suffix="POLICY",
        priority="must",
        route="/policy",
    )
    _add_content_requirement(
        payload,
        suffix="GUIDE",
        priority="should",
        route="/guide",
    )
    while len(payload["pages"]) < page_count:
        number = len(payload["pages"]) + 1
        page_id = f"PAGE-SUPPORT-{number:02d}"
        state_id = f"STATE-SUPPORT-{number:02d}"
        evidence_id = f"EVIDENCE-SUPPORT-{number:02d}"
        payload["pages"].append(
            {
                "id": page_id,
                "name": f"Support {number}",
                "purpose": "Expose another canonical support surface.",
                "route": f"/support-{number:02d}",
                "surface": "public",
                "primary": False,
                "role_ids": ["ROLE-CUSTOMER"],
                "capability_ids": ["CAP-GUIDE"],
                "state_ids": [state_id],
                "action_ids": [],
                "evidence_ids": [evidence_id],
            }
        )
        payload["states"].append(
            {
                "id": state_id,
                "page_id": page_id,
                "name": "Ready",
                "description": "The support content is ready.",
                "initial": True,
                "terminal": True,
                "evidence_ids": [evidence_id],
            }
        )
        payload["evidence"].append(
            {
                "id": evidence_id,
                "page_id": page_id,
                "name": f"Support evidence {number}",
                "description": "The support content is visible.",
                "kind": "text",
                "capability_ids": ["CAP-GUIDE"],
            }
        )
    spec = AppSpec.model_validate(payload)
    report = validate_app_spec(spec)
    assert report.is_valid, report.model_dump(mode="json")
    return spec


def _strategy_and_context(
    *,
    request_id: int = 901,
    source_id: int = 11,
    strategy_id: int = 12,
    app_spec_id: int = 13,
):
    req = _request(request_id)
    source = capture_request_source_v2(req)
    strategy = project_product_strategy(req, source)
    context = TierContractContext(
        request_id=request_id,
        customer_source_ref=CustomerSourceRef(
            id=source_id,
            sha256=strategy.source_sha256,
        ),
        product_strategy_ref=ProductStrategyRef(
            id=strategy_id,
            revision=1,
            sha256="b" * 64,
        ),
        app_spec_ref=CanonicalAppSpecRef(
            id=app_spec_id,
            revision=1,
            schema_version="1.0",
            sha256="c" * 64,
        ),
    )
    return req, source, strategy, context


def _build(
    *,
    page_count: int = 3,
    selection_policy_revision: str = TIER_SELECTION_POLICY_REVISION,
):
    spec = _tiered_spec(page_count=page_count)
    _, _, strategy, context = _strategy_and_context()
    tiers = build_preview_tiers(
        spec=spec,
        strategy=strategy,
        context=context,
        selection_policy_revision=selection_policy_revision,
    )
    validation = validate_preview_tiers(
        tiers,
        spec=spec,
        strategy=strategy,
        context=context,
        selection_policy_revision=selection_policy_revision,
    )
    return spec, strategy, context, tiers, validation


def _db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _persist_contract_inputs(
    db: Session,
    *,
    request_id: int = 901,
    page_count: int = 3,
):
    req = _request(request_id)
    db.add(req)
    db.commit()
    source = capture_request_source_v2(req)
    strategy = project_product_strategy(req, source)
    repository = PreviewContractRepository(db)
    inputs = repository.stage_inputs(source=source, strategy=strategy)
    spec = _tiered_spec(page_count=page_count)
    spec_json = canonical_json(spec.model_dump(mode="json"))
    revision = AppSpecRevision(
        request_id=request_id,
        revision=1,
        schema_version=spec.schema_version,
        status="accepted",
        source_snapshot_json=canonical_json(source.model_dump(mode="json")),
        source_sha256=inputs.source.sha256,
        app_spec_json=spec_json,
        app_spec_sha256=app_spec_sha256(spec),
        deterministic_validation_json=canonical_json({"passed": True}),
        validation_passed=True,
        semantic_coverage_json=canonical_json({"verdict": "pass"}),
        coverage_passed=True,
        coverage_score=100,
        generation_metadata_json=canonical_json(
            {
                "complete": True,
                "customer_source_artifact_id": inputs.source.id,
                "product_strategy_revision_id": inputs.strategy.id,
                "product_strategy_sha256": inputs.strategy.strategy_sha256,
            }
        ),
    )
    db.add(revision)
    db.commit()
    context = TierContractContext(
        request_id=request_id,
        customer_source_ref=CustomerSourceRef(
            id=inputs.source.id,
            sha256=inputs.source.sha256,
        ),
        product_strategy_ref=ProductStrategyRef(
            id=inputs.strategy.id,
            revision=inputs.strategy.revision,
            sha256=inputs.strategy.strategy_sha256,
        ),
        app_spec_ref=CanonicalAppSpecRef(
            id=revision.id,
            revision=revision.revision,
            schema_version=revision.schema_version,
            sha256=revision.app_spec_sha256,
        ),
    )
    return repository, spec, strategy, context


def test_tiers_are_reference_only_and_reject_embedded_contract_content() -> None:
    _, _, _, tiers, _ = _build()
    for forbidden_key, forbidden_value in (
        ("app_spec", {"pages": []}),
        ("page_definitions", [{"id": "PAGE-X"}]),
        ("prompt", "Generate a polished interface"),
        ("generated_content", "<main>content</main>"),
    ):
        payload = tiers[0].model_dump(mode="json")
        payload[forbidden_key] = forbidden_value
        with pytest.raises(ValidationError):
            PreviewTierArtifact.model_validate(payload)


def test_tier_1_proves_an_executable_primary_journey() -> None:
    _, _, _, tiers, validation = _build()
    proof = tiers[0].primary_journey_proof
    assert validation.passed
    assert proof.requirement_id == "REQ-BOOK"
    assert proof.journey_id == "JOURNEY-BOOK"
    assert proof.page_ids == ("PAGE-BOOK",)
    assert proof.action_ids == ("ACTION-SUBMIT",)
    assert proof.transition_ids == ("TRANSITION-SUBMIT",)
    assert proof.success_evidence_ids == ("EVIDENCE-CONFIRMATION",)
    assert proof.acceptance_test_id == "TEST-BOOK"


def test_noninteraction_requirement_cannot_qualify_tier_1() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["requirements"][0]["verification_mode"] = "content"
    spec = AppSpec.model_validate(payload)
    _, _, strategy, context = _strategy_and_context()
    with pytest.raises(TierBuildError, match="interaction requirement"):
        build_preview_tiers(spec=spec, strategy=strategy, context=context)


def test_tier_2_and_tier_3_are_complete_supersets_in_canonical_order() -> None:
    spec, _, _, tiers, validation = _build()
    assert validation.passed
    for field in REFERENCE_FIELDS:
        one = set(getattr(tiers[0].references, field))
        two = set(getattr(tiers[1].references, field))
        three = set(getattr(tiers[2].references, field))
        assert one <= two <= three
        canonical = [
            item.id
            for item in getattr(
                spec,
                {
                    "requirement_ids": "requirements",
                    "role_ids": "roles",
                    "entity_ids": "entities",
                    "capability_ids": "capabilities",
                    "page_ids": "pages",
                    "state_ids": "states",
                    "action_ids": "actions",
                    "transition_ids": "transitions",
                    "evidence_ids": "evidence",
                    "journey_ids": "journeys",
                    "acceptance_test_ids": "acceptance_tests",
                }[field],
            )
            if item.id in three
        ]
        assert list(getattr(tiers[2].references, field)) == canonical
    assert {"REQ-BOOK", "REQ-POLICY"} <= set(
        tiers[1].references.requirement_ids
    )
    assert {"REQ-BOOK", "REQ-POLICY", "REQ-GUIDE"} <= set(
        tiers[2].references.requirement_ids
    )


def test_graph_closure_reaches_a_fixed_point_from_acceptance_test() -> None:
    spec = _tiered_spec()
    refs = expand_tier_graph(
        spec,
        {"acceptance_test_ids": {"TEST-BOOK"}},
    )
    assert "REQ-BOOK" in refs["requirement_ids"]
    assert "JOURNEY-BOOK" in refs["journey_ids"]
    assert "PAGE-BOOK" in refs["page_ids"]
    assert "ACTION-SUBMIT" in refs["action_ids"]
    assert "TRANSITION-SUBMIT" in refs["transition_ids"]
    assert "EVIDENCE-CONFIRMATION" in refs["evidence_ids"]
    assert expand_tier_graph(spec, refs) == refs


def test_role_default_page_without_journey_stays_out_of_tier1() -> None:
    """Role entry pages must not leak into Tier 1 without closed journey proof.

    Production smoke failed when an admin default dashboard entered Tier 1 via
    role expansion, then composition rejected it for missing closed references.
    """

    payload = _tiered_spec().model_dump(mode="json")
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
    assert validate_app_spec(spec).is_valid
    _, _, strategy, context = _strategy_and_context()
    tiers = build_preview_tiers(
        spec=spec,
        strategy=strategy,
        context=context,
    )
    assert "ROLE-ADMIN" in tiers[0].references.role_ids
    assert "PAGE-ADMIN-DASHBOARD" not in tiers[0].references.page_ids


def test_orphan_navigate_action_stays_out_of_tier1() -> None:
    """Navigate actions on Tier 1 pages must not enter without a journey step.

    Production smoke failed when ACTION-NAVIGATE-ADMIN-DASHBOARD expanded from
    a journey page into Tier 1, then interaction projection required a
    journey-backed acceptance test that did not exist.
    """

    payload = _tiered_spec().model_dump(mode="json")
    payload["pages"].append(
        {
            "id": "PAGE-ADMIN-DASHBOARD",
            "name": "Admin dashboard",
            "purpose": "Operator overview.",
            "route": "/admin",
            "surface": "ops",
            "primary": False,
            "role_ids": ["ROLE-CUSTOMER"],
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
    payload["actions"].append(
        {
            "id": "ACTION-NAVIGATE-ADMIN-DASHBOARD",
            "page_id": "PAGE-BOOK",
            "role_id": "ROLE-CUSTOMER",
            "name": "Open admin dashboard",
            "description": "Jump to the operator dashboard.",
            "kind": "navigate",
            "capability_ids": ["CAP-BOOK"],
            "entity_id": None,
            "input_label": None,
        }
    )
    payload["transitions"].append(
        {
            "id": "TRANSITION-NAVIGATE-ADMIN",
            "action_id": "ACTION-NAVIGATE-ADMIN-DASHBOARD",
            "from_state_id": "STATE-DRAFT",
            "to_state_id": "STATE-ADMIN-READY",
            "description": "Navigate to the operator dashboard.",
            "preconditions": [],
            "postconditions": ["Admin dashboard is visible"],
            "effects": [],
        }
    )
    payload["pages"][0]["action_ids"] = [
        "ACTION-SUBMIT",
        "ACTION-NAVIGATE-ADMIN-DASHBOARD",
    ]
    spec = AppSpec.model_validate(payload)
    assert validate_app_spec(spec).is_valid, validate_app_spec(spec).model_dump()
    _, _, strategy, context = _strategy_and_context()
    tiers = build_preview_tiers(
        spec=spec,
        strategy=strategy,
        context=context,
    )
    assert "ACTION-SUBMIT" in tiers[0].references.action_ids
    assert "ACTION-NAVIGATE-ADMIN-DASHBOARD" not in tiers[0].references.action_ids
    assert "PAGE-ADMIN-DASHBOARD" not in tiers[0].references.page_ids


def test_graph_closure_fails_closed_for_unknown_and_deferred_references() -> None:
    spec = _tiered_spec()
    with pytest.raises(TierBuildError, match="unknown canonical IDs"):
        expand_tier_graph(spec, {"page_ids": {"PAGE-NOT-CANONICAL"}})

    invalid_payload = spec.model_dump(mode="json")
    invalid_payload["pages"][0]["action_ids"] = ["ACTION-NOT-CANONICAL"]
    invalid_spec = AppSpec.model_validate(invalid_payload)
    _, _, strategy, context = _strategy_and_context()
    with pytest.raises(TierBuildError, match="valid canonical AppSpec"):
        build_preview_tiers(
            spec=invalid_spec,
            strategy=strategy,
            context=context,
        )

    payload = spec.model_dump(mode="json")
    payload["deferred_scope"] = [
        {
            "id": "DEFER-GUIDE",
            "name": "Guide later",
            "description": "Defer the guide requirement.",
            "reason": "Not active in this contract.",
            "requirement_ids": ["REQ-GUIDE"],
            "target_release": "Later",
        }
    ]
    deferred_spec = AppSpec.model_validate(payload)
    with pytest.raises(TierBuildError, match="Deferred requirements"):
        expand_tier_graph(
            deferred_spec,
            {"requirement_ids": {"REQ-GUIDE"}},
        )


def test_tier_3_includes_all_13_pages_without_legacy_truncation() -> None:
    spec, _, _, tiers, validation = _build(page_count=13)
    assert validation.passed
    assert len(spec.pages) == 13
    assert tiers[2].references.page_ids == tuple(page.id for page in spec.pages)


def test_outputs_and_hashes_are_deterministic() -> None:
    spec, strategy, context, tiers, _ = _build(page_count=13)
    rebuilt = build_preview_tiers(
        spec=spec,
        strategy=strategy,
        context=context,
    )
    assert [tier.model_dump(mode="json") for tier in tiers] == [
        tier.model_dump(mode="json") for tier in rebuilt
    ]
    assert [tier_artifact_sha256(tier) for tier in tiers] == [
        tier_artifact_sha256(tier) for tier in rebuilt
    ]


def test_transaction_failure_rolls_back_all_three_tiers() -> None:
    db = _db()
    repository, spec, strategy, context = _persist_contract_inputs(db)
    tiers = build_preview_tiers(
        spec=spec,
        strategy=strategy,
        context=context,
    )
    validation = validate_preview_tiers(
        tiers,
        spec=spec,
        strategy=strategy,
        context=context,
    )

    def fail_tier_two(_mapper, _connection, target) -> None:
        if target.tier == 2:
            raise RuntimeError("forced tier-two insert failure")

    event.listen(PreviewTierArtifactRecord, "before_insert", fail_tier_two)
    try:
        with pytest.raises(RuntimeError, match="forced tier-two"):
            repository.stage_tiers(tiers=tiers, validation=validation)
        assert db.query(PreviewTierArtifactRecord).count() == 0
    finally:
        event.remove(PreviewTierArtifactRecord, "before_insert", fail_tier_two)
        db.close()


def test_partial_existing_tier_set_fails_closed_without_repair() -> None:
    db = _db()
    try:
        repository, spec, strategy, context = _persist_contract_inputs(db)
        tiers = build_preview_tiers(
            spec=spec,
            strategy=strategy,
            context=context,
        )
        validation = validate_preview_tiers(
            tiers,
            spec=spec,
            strategy=strategy,
            context=context,
        )
        first = tiers[0]
        db.add(
            PreviewTierArtifactRecord(
                request_id=first.request_id,
                tier=1,
                schema_version=first.tier_schema_version,
                selection_policy_revision=first.selection_policy_revision,
                source_artifact_id=first.customer_source_ref.id,
                product_strategy_revision_id=first.product_strategy_ref.id,
                app_spec_revision_id=first.app_spec_ref.id,
                parent_tier_artifact_id=None,
                artifact_json=canonical_json(first.model_dump(mode="json")),
                artifact_sha256=tier_artifact_sha256(first),
                validation_json=canonical_json(
                    validation.model_dump(mode="json")
                ),
                validation_passed=True,
            )
        )
        db.commit()
        with pytest.raises(PartialTierSetError):
            repository.stage_tiers(tiers=tiers, validation=validation)
        assert db.query(PreviewTierArtifactRecord).count() == 1
    finally:
        db.close()


def test_complete_tier_set_is_idempotently_reused_with_parent_links() -> None:
    db = _db()
    try:
        repository, spec, strategy, context = _persist_contract_inputs(db)
        tiers = build_preview_tiers(
            spec=spec,
            strategy=strategy,
            context=context,
        )
        validation = validate_preview_tiers(
            tiers,
            spec=spec,
            strategy=strategy,
            context=context,
        )
        inserted = repository.stage_tiers(tiers=tiers, validation=validation)
        db.commit()
        reused = repository.stage_tiers(tiers=tiers, validation=validation)
        assert inserted.reused is False
        assert reused.reused is True
        assert [reused.tier_1.id, reused.tier_2.id, reused.tier_3.id] == [
            inserted.tier_1.id,
            inserted.tier_2.id,
            inserted.tier_3.id,
        ]
        assert reused.tier_1.parent_tier_artifact_id is None
        assert reused.tier_2.parent_tier_artifact_id == reused.tier_1.id
        assert reused.tier_3.parent_tier_artifact_id == reused.tier_2.id
        assert db.query(PreviewTierArtifactRecord).count() == 3
    finally:
        db.close()


def test_policy_revision_change_never_silently_reuses_old_artifacts() -> None:
    db = _db()
    try:
        repository, spec, strategy, context = _persist_contract_inputs(db)
        old_tiers = build_preview_tiers(
            spec=spec,
            strategy=strategy,
            context=context,
        )
        old_validation = validate_preview_tiers(
            old_tiers,
            spec=spec,
            strategy=strategy,
            context=context,
        )
        repository.stage_tiers(tiers=old_tiers, validation=old_validation)
        db.commit()

        new_revision = "2026-07-24.2"
        new_tiers = build_preview_tiers(
            spec=spec,
            strategy=strategy,
            context=context,
            selection_policy_revision=new_revision,
        )
        new_validation = validate_preview_tiers(
            new_tiers,
            spec=spec,
            strategy=strategy,
            context=context,
            selection_policy_revision=new_revision,
        )
        with pytest.raises(TierPolicyRevisionMismatch):
            repository.stage_tiers(
                tiers=new_tiers,
                validation=new_validation,
            )
        assert {
            row.selection_policy_revision
            for row in db.query(PreviewTierArtifactRecord).all()
        } == {TIER_SELECTION_POLICY_REVISION}
    finally:
        db.close()


def test_cross_request_contract_references_fail_before_insert() -> None:
    db = _db()
    try:
        repository, spec, strategy, context = _persist_contract_inputs(db)
        wrong_context = TierContractContext(
            request_id=context.request_id + 1,
            customer_source_ref=context.customer_source_ref,
            product_strategy_ref=context.product_strategy_ref,
            app_spec_ref=context.app_spec_ref,
        )
        tiers = build_preview_tiers(
            spec=spec,
            strategy=strategy,
            context=wrong_context,
        )
        validation = validate_preview_tiers(
            tiers,
            spec=spec,
            strategy=strategy,
            context=wrong_context,
        )
        with pytest.raises(ValueError, match="same request"):
            repository.stage_tiers(tiers=tiers, validation=validation)
        assert db.query(PreviewTierArtifactRecord).count() == 0
    finally:
        db.close()
