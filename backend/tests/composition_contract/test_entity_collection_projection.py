"""Focused Tier 1 entity-collection projection tests (smoke #28 class)."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.application.composition_contract.collection_derivation import (
    COLLECTION_PROJECTION_POLICY_REVISION,
    collection_is_required,
    detect_collection_entity_types,
    resolve_tier1_collection_decision,
)
from app.application.composition_contract.context import CompositionContext
from app.application.composition_contract.projections import (
    CompositionProjectionError,
    project_content_data_plan,
)
from app.application.composition_contract.validation import (
    validate_content_data_plan,
)
from app.domain.appspec.validation import validate_app_spec
from app.domain.schemas.app_spec import AppSpec
from app.domain.schemas.business_component_plan import (
    BusinessComponent,
    BusinessComponentPlan,
    ComponentStateBinding,
    PageComponentComposition,
)
from app.domain.schemas.composition_contract import (
    CompositionArtifactRef,
    CompositionContractRefs,
)
from app.domain.schemas.content_data_plan import DataCollection, SeedRecord
from app.domain.schemas.design_contract import (
    DesignArtifactRef,
    DesignContractRefs,
    TierArtifactRef,
)
from app.domain.schemas.page_purpose_contract import (
    ImmutablePageConstraints,
    PagePurpose,
    PagePurposeContract,
    ProjectedDesignConstraints,
)
from app.domain.schemas.preview_tier import (
    CanonicalAppSpecRef,
    CustomerSourceRef,
    PreviewTierArtifact,
    PrimaryJourneyProof,
    ProductStrategyRef,
    RequirementCompletionProof,
    TIER_SELECTION_POLICY_REVISION,
    TierReferenceSet,
)


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "app_spec"
SMOKE28 = FIXTURES / "booking_no_entities_smoke28.json"
STATIC = FIXTURES / "static_marketing_no_collection.json"
AMBIGUOUS = FIXTURES / "ambiguous_marketplace_collections.json"


def _load_spec(path: Path) -> AppSpec:
    payload = json.loads(path.read_text(encoding="utf-8"))
    spec = AppSpec.model_validate(payload)
    report = validate_app_spec(spec)
    assert report.is_valid, report.model_dump(mode="json")
    return spec


def _refs(request_id: int = 2801) -> CompositionContractRefs:
    digest = "a" * 64
    design = DesignContractRefs(
        request_id=request_id,
        customer_source_ref=CustomerSourceRef(id=1, sha256=digest),
        product_strategy_seed_ref=ProductStrategyRef(
            id=2, revision=1, sha256=digest
        ),
        app_spec_ref=CanonicalAppSpecRef(
            id=3,
            revision=1,
            schema_version="1.0",
            sha256=digest,
        ),
        tier_refs=(
            TierArtifactRef(
                id=11,
                tier=1,
                sha256=digest,
                selection_policy_revision=TIER_SELECTION_POLICY_REVISION,
            ),
            TierArtifactRef(
                id=12,
                tier=2,
                sha256=digest,
                selection_policy_revision=TIER_SELECTION_POLICY_REVISION,
            ),
            TierArtifactRef(
                id=13,
                tier=3,
                sha256=digest,
                selection_policy_revision=TIER_SELECTION_POLICY_REVISION,
            ),
        ),
    )
    return CompositionContractRefs(
        request_id=request_id,
        target_tier=1,
        design_contract_refs=design,
        product_strategy_v2_ref=DesignArtifactRef(
            id=21,
            artifact_kind="product_strategy_v2",
            schema_version="1.0",
            sha256=digest,
        ),
        information_architecture_ref=DesignArtifactRef(
            id=22,
            artifact_kind="information_architecture",
            schema_version="1.0",
            sha256=digest,
        ),
        design_dna_ref=DesignArtifactRef(
            id=23,
            artifact_kind="design_dna",
            schema_version="1.0",
            sha256=digest,
        ),
    )


def _tier_refs_for_spec(
    spec: AppSpec,
    *,
    entity_ids: tuple[str, ...] | None = None,
) -> TierReferenceSet:
    return TierReferenceSet(
        requirement_ids=tuple(item.id for item in spec.requirements),
        role_ids=tuple(item.id for item in spec.roles),
        entity_ids=(
            entity_ids
            if entity_ids is not None
            else tuple(item.id for item in spec.entities)
        ),
        capability_ids=tuple(item.id for item in spec.capabilities),
        page_ids=tuple(item.id for item in spec.pages),
        state_ids=tuple(item.id for item in spec.states),
        action_ids=tuple(item.id for item in spec.actions),
        transition_ids=tuple(item.id for item in spec.transitions),
        evidence_ids=tuple(item.id for item in spec.evidence),
        journey_ids=tuple(item.id for item in spec.journeys),
        acceptance_test_ids=tuple(item.id for item in spec.acceptance_tests),
    )


def _preview_tier(
    *,
    request_id: int,
    tier: int,
    refs: TierReferenceSet,
    journey_id: str,
    requirement_id: str,
    page_ids: tuple[str, ...],
    action_ids: tuple[str, ...],
    transition_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
    acceptance_test_id: str,
) -> PreviewTierArtifact:
    digest = "a" * 64
    intent = {
        1: "primary_outcome",
        2: "all_must_requirements",
        3: "full_active_contract",
    }[tier]
    extends = {1: None, 2: 1, 3: 2}[tier]
    return PreviewTierArtifact(
        selection_policy_revision=TIER_SELECTION_POLICY_REVISION,
        tier=tier,  # type: ignore[arg-type]
        intent=intent,  # type: ignore[arg-type]
        request_id=request_id,
        extends_tier=extends,  # type: ignore[arg-type]
        customer_source_ref=CustomerSourceRef(id=1, sha256=digest),
        product_strategy_ref=ProductStrategyRef(
            id=2, revision=1, sha256=digest
        ),
        app_spec_ref=CanonicalAppSpecRef(
            id=3,
            revision=1,
            schema_version="1.0",
            sha256=digest,
        ),
        primary_journey_proof=PrimaryJourneyProof(
            requirement_id=requirement_id,
            journey_id=journey_id,
            page_ids=page_ids,
            action_ids=action_ids,
            transition_ids=transition_ids,
            success_evidence_ids=evidence_ids,
            acceptance_test_id=acceptance_test_id,
        ),
        references=refs,
        completion_proofs=(
            RequirementCompletionProof(
                requirement_id=requirement_id,
                evidence_ids=evidence_ids,
                journey_ids=(journey_id,),
                acceptance_test_ids=(acceptance_test_id,),
            ),
        ),
    )


def _immutable() -> ImmutablePageConstraints:
    return ImmutablePageConstraints(
        route_locked=True,
        roles_locked=True,
        requirements_locked=True,
        actions_locked=True,
        transitions_locked=True,
        evidence_locked=True,
        journeys_locked=True,
        acceptance_tests_locked=True,
        invented_behavior_forbidden=True,
    )


def build_harness(
    spec: AppSpec,
    *,
    request_id: int = 2801,
    tier1_entity_ids: tuple[str, ...] | None = None,
    include_tier2_entity_ids: tuple[str, ...] = (),
):
    """Build composition context + page/component contracts for projection."""

    refs = _refs(request_id=request_id)
    tier1_refs = _tier_refs_for_spec(spec, entity_ids=tier1_entity_ids)
    journey = spec.journeys[0]
    requirement_id = spec.requirements[0].id
    tier1 = _preview_tier(
        request_id=request_id,
        tier=1,
        refs=tier1_refs,
        journey_id=journey.id,
        requirement_id=requirement_id,
        page_ids=tuple(item.id for item in spec.pages),
        action_ids=tuple(item.id for item in spec.actions) or (
            journey.steps[0].action_id,
        ),
        transition_ids=tuple(item.id for item in spec.transitions)
        or (journey.steps[0].transition_id,),
        evidence_ids=tuple(item.id for item in spec.evidence)[:3]
        or journey.steps[0].evidence_ids,
        acceptance_test_id=spec.acceptance_tests[0].id,
    )
    tier2_entity_ids = tuple(
        dict.fromkeys(
            list(tier1_refs.entity_ids) + list(include_tier2_entity_ids)
        )
    )
    tier2_refs = tier1_refs.model_copy(update={"entity_ids": tier2_entity_ids})
    tier2 = _preview_tier(
        request_id=request_id,
        tier=2,
        refs=tier2_refs,
        journey_id=journey.id,
        requirement_id=requirement_id,
        page_ids=tier1.primary_journey_proof.page_ids,
        action_ids=tier1.primary_journey_proof.action_ids,
        transition_ids=tier1.primary_journey_proof.transition_ids,
        evidence_ids=tier1.primary_journey_proof.success_evidence_ids,
        acceptance_test_id=spec.acceptance_tests[0].id,
    )
    tier3 = _preview_tier(
        request_id=request_id,
        tier=3,
        refs=tier2_refs,
        journey_id=journey.id,
        requirement_id=requirement_id,
        page_ids=tier1.primary_journey_proof.page_ids,
        action_ids=tier1.primary_journey_proof.action_ids,
        transition_ids=tier1.primary_journey_proof.transition_ids,
        evidence_ids=tier1.primary_journey_proof.success_evidence_ids,
        acceptance_test_id=spec.acceptance_tests[0].id,
    )
    context = CompositionContext(
        refs=refs,
        source=MagicMock(),
        app_spec=spec,
        tiers=(tier1, tier2, tier3),
        product_strategy_v2=MagicMock(),
        information_architecture=MagicMock(),
        design_dna=MagicMock(),
        design_rows=(MagicMock(), MagicMock(), MagicMock()),
    )
    page_purpose = PagePurposeContract(
        contract_refs=refs,
        primary_outcome_requirement_id=requirement_id,
        mobile_global_behavior="Keep primary actions reachable on small screens.",
        design_constraints=ProjectedDesignConstraints(
            composition_hierarchy="Primary journey pages lead the composition.",
            composition_emphasis="Emphasize the accepted Tier 1 outcome.",
            public_surface_density="balanced",
            operations_surface_density="balanced",
            motion_character="Quiet transitions between journey steps.",
            reduced_motion="Disable nonessential motion under reduced-motion.",
            avoid_list=("stock collage", "generic dashboard", "purple glow"),
        ),
        pages=tuple(
            PagePurpose(
                page_id=page.id,
                route=page.route,
                surface=page.surface,
                goal=page.purpose,
                role_ids=page.role_ids,
                requirement_ids=(requirement_id,),
                outcome_requirement_ids=(requirement_id,),
                capability_ids=page.capability_ids,
                state_ids=page.state_ids,
                action_ids=page.action_ids,
                transition_ids=tuple(
                    item.id
                    for item in spec.transitions
                    if item.action_id in set(page.action_ids)
                ),
                evidence_ids=page.evidence_ids,
                journey_ids=(journey.id,),
                acceptance_test_ids=(spec.acceptance_tests[0].id,),
                navigation_visibility=(
                    "primary" if page.primary else "secondary"
                ),
                deep_link_reason=None,
                mobile={
                    "navigation": "persistent",
                    "primary_action": "inline",
                    "content_priority": ("outcome", "evidence"),
                    "data_presentation": "stacked_cards",
                    "density_adjustment": "preserve",
                },
                immutable=_immutable(),
            )
            for page in spec.pages
        ),
    )
    page_ref = CompositionArtifactRef(
        id=91,
        artifact_kind="page_purpose_contract",
        schema_version="1.0",
        sha256="b" * 64,
    )
    components = []
    compositions = []
    state_bindings = []
    for page in page_purpose.pages:
        component_id = f"COMP-{page.page_id.removeprefix('PAGE-')}"
        components.append(
            BusinessComponent(
                component_id=component_id,
                name=f"{page.page_id}Panel",
                purpose=f"Present the {page.goal}",
                component_kind=(
                    "business_action" if page.action_ids else "business_content"
                ),
                domain_language=("studio", "journey"),
                page_ids=(page.page_id,),
                role_ids=page.role_ids,
                requirement_ids=page.requirement_ids,
                entity_ids=(),
                capability_ids=page.capability_ids,
                state_ids=page.state_ids,
                action_ids=page.action_ids,
                evidence_ids=page.evidence_ids,
                content_responsibilities=("Explain the page outcome.",),
                data_responsibilities=("Show accepted journey details.",),
                interaction_responsibilities=(
                    ("Advance the accepted journey.",)
                    if page.action_ids
                    else ()
                ),
                requires_component_ids=(),
                shared_across_pages=False,
            )
        )
        compositions.append(
            PageComponentComposition(
                page_id=page.page_id,
                ordered_component_ids=(component_id,),
            )
        )
        for state_id in page.state_ids:
            evidence_ids = tuple(
                item
                for item in page.evidence_ids
                if any(
                    state.id == state_id and item in state.evidence_ids
                    for state in spec.states
                )
            )
            if evidence_ids:
                state_bindings.append(
                    ComponentStateBinding(
                        component_id=component_id,
                        state_id=state_id,
                        visible_evidence_ids=evidence_ids,
                    )
                )
    component_plan = BusinessComponentPlan(
        contract_refs=refs,
        page_purpose_ref=page_ref,
        components=tuple(components),
        page_compositions=tuple(compositions),
        action_trigger_bindings=(),
        component_state_bindings=tuple(state_bindings),
    )
    component_ref = CompositionArtifactRef(
        id=92,
        artifact_kind="business_component_plan",
        schema_version="1.0",
        sha256="c" * 64,
    )
    return context, page_purpose, page_ref, component_plan, component_ref


def test_smoke28_fixture_is_valid_appspec_without_entities() -> None:
    spec = _load_spec(SMOKE28)
    assert spec.entities == ()
    assert [page.name for page in spec.pages] == [
        "Home",
        "Service Detail",
        "Booking",
        "Confirmation",
    ]


def test_collection_not_required_for_every_tier1_product() -> None:
    assert collection_is_required(
        entity_types=(),
        signal_text="home about contact narrative story",
        page_purpose=MagicMock(pages=[MagicMock(page_id="PAGE-HOME")]),
    ) is False


def test_booking_flow_derives_services_collection() -> None:
    spec = _load_spec(SMOKE28)
    original = copy.deepcopy(spec.model_dump(mode="json"))
    context, page_purpose, page_ref, component_plan, component_ref = build_harness(
        spec
    )
    projected = project_content_data_plan(
        context,
        page_purpose=page_purpose,
        page_purpose_ref=page_ref,
        component_plan=component_plan,
        component_plan_ref=component_ref,
    )
    assert projected.collection_projection is not None
    assert projected.collection_projection.decision == "collection_derived"
    assert projected.collection_projection.entity_type == "service"
    assert projected.collection_projection.heal_applied is True
    assert projected.collection_projection.policy_revision == (
        COLLECTION_PROJECTION_POLICY_REVISION
    )
    assert len(projected.data_collections) == 1
    collection = projected.data_collections[0]
    assert collection.entity_id == "ENTITY-SERVICE"
    assert collection.seed_records
    assert projected.collection_projection.after_projection_hash
    assert projected.collection_projection.seed_hash
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


def test_static_marketing_collection_not_required() -> None:
    spec = _load_spec(STATIC)
    context, page_purpose, page_ref, component_plan, component_ref = build_harness(
        spec, request_id=2802
    )
    projected = project_content_data_plan(
        context,
        page_purpose=page_purpose,
        page_purpose_ref=page_ref,
        component_plan=component_plan,
        component_plan_ref=component_ref,
    )
    assert projected.collection_projection is not None
    assert projected.collection_projection.decision == "collection_not_required"
    assert projected.data_collections == ()
    report = validate_content_data_plan(
        projected,
        context=context,
        page_purpose=page_purpose,
        page_purpose_ref=page_ref,
        component_plan=component_plan,
        component_plan_ref=component_ref,
    )
    assert report.passed, report.model_dump(mode="json")


def test_ambiguous_marketplace_fails_closed() -> None:
    spec = _load_spec(AMBIGUOUS)
    context, page_purpose, page_ref, component_plan, component_ref = build_harness(
        spec, request_id=2803
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


def test_singleton_static_confirmation_customer_calendar_not_collections() -> None:
    signal = (
        "confirmation message customer info form availability calendar "
        "business profile settings narrative"
    )
    assert detect_collection_entity_types(signal) == ()
    page_purpose = MagicMock(
        pages=[
            MagicMock(page_id="PAGE-HOME"),
            MagicMock(page_id="PAGE-CONFIRMATION"),
        ]
    )
    assert collection_is_required(
        entity_types=(),
        signal_text=signal,
        page_purpose=page_purpose,
    ) is False


def test_existing_valid_collection_preserved_byte_stably() -> None:
    spec = _load_spec(SMOKE28)
    context, page_purpose, page_ref, component_plan, component_ref = build_harness(
        spec, request_id=2804
    )
    from app.domain.schemas.content_data_plan import SeedFieldValue

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
    assert second.code == "collection_reused"
    assert first.collection.model_dump(mode="json") == existing.model_dump(
        mode="json"
    )
    assert second.collection.model_dump(mode="json") == first.collection.model_dump(
        mode="json"
    )


def test_filtered_tier1_collection_restored_when_valid() -> None:
    payload = json.loads(SMOKE28.read_text(encoding="utf-8"))
    payload["entities"] = [
        {
            "id": "ENTITY-SERVICE",
            "name": "Service",
            "description": "A selectable studio service.",
            "fields": [
                {
                    "id": "FIELD-NAME",
                    "name": "Name",
                    "description": "Service name.",
                    "type": "string",
                    "required": True,
                    "enum_values": [],
                    "reference_entity_id": None,
                }
            ],
        }
    ]
    spec = AppSpec.model_validate(payload)
    assert validate_app_spec(spec).is_valid
    context, page_purpose, page_ref, component_plan, component_ref = build_harness(
        spec,
        request_id=2805,
        tier1_entity_ids=(),
    )
    projected = project_content_data_plan(
        context,
        page_purpose=page_purpose,
        page_purpose_ref=page_ref,
        component_plan=component_plan,
        component_plan_ref=component_ref,
    )
    assert projected.collection_projection is not None
    assert (
        projected.collection_projection.decision
        == "collection_filtered_out_of_tier"
    )
    assert projected.data_collections[0].entity_id == "ENTITY-SERVICE"


def test_tier2_only_collection_does_not_leak_into_tier1() -> None:
    payload = json.loads(STATIC.read_text(encoding="utf-8"))
    payload["entities"] = [
        {
            "id": "ENTITY-SELLER",
            "name": "Seller",
            "description": "Marketplace seller records for Tier 2 ops.",
            "fields": [
                {
                    "id": "FIELD-SELLER-NAME",
                    "name": "Seller name",
                    "description": "Display name.",
                    "type": "string",
                    "required": True,
                    "enum_values": [],
                    "reference_entity_id": None,
                }
            ],
        }
    ]
    spec = AppSpec.model_validate(payload)
    context, page_purpose, page_ref, component_plan, component_ref = build_harness(
        spec,
        request_id=2806,
        tier1_entity_ids=(),
        include_tier2_entity_ids=("ENTITY-SELLER",),
    )
    projected = project_content_data_plan(
        context,
        page_purpose=page_purpose,
        page_purpose_ref=page_ref,
        component_plan=component_plan,
        component_plan_ref=component_ref,
    )
    assert projected.collection_projection.decision == "collection_not_required"
    assert projected.data_collections == ()
    assert all(
        item.entity_id != "ENTITY-SELLER" for item in projected.data_collections
    )


def test_ambiguous_derivation_and_missing_fields_fail_closed() -> None:
    spec = _load_spec(AMBIGUOUS)
    context, page_purpose, _, component_plan, _ = build_harness(
        spec, request_id=2807
    )
    decision = resolve_tier1_collection_decision(
        context,
        page_purpose=page_purpose,
        component_plan=component_plan,
        existing_collections=[],
    )
    assert decision.code == "collection_ambiguous"

    from types import SimpleNamespace

    booking = _load_spec(SMOKE28)
    ctx2, page2, _, plan2, _ = build_harness(booking, request_id=2808)
    fieldless = SimpleNamespace(
        id="ENTITY-SERVICE",
        name="Service",
        description="A selectable studio service.",
        fields=(),
    )
    mocked_spec = SimpleNamespace(
        entities=(fieldless,),
        pages=booking.pages,
        actions=booking.actions,
        requirements=booking.requirements,
        acceptance_tests=booking.acceptance_tests,
        journeys=booking.journeys,
        evidence=booking.evidence,
        states=booking.states,
        capabilities=booking.capabilities,
        roles=booking.roles,
    )
    ctx2 = CompositionContext(
        refs=ctx2.refs,
        source=ctx2.source,
        app_spec=mocked_spec,  # type: ignore[arg-type]
        tiers=ctx2.tiers,
        product_strategy_v2=ctx2.product_strategy_v2,
        information_architecture=ctx2.information_architecture,
        design_dna=ctx2.design_dna,
        design_rows=ctx2.design_rows,
    )
    decision2 = resolve_tier1_collection_decision(
        ctx2,
        page_purpose=page2,
        component_plan=plan2,
        existing_collections=[],
    )
    assert decision2.code == "collection_missing_required_fields"


def test_unseedable_and_heal_at_most_once() -> None:
    spec = _load_spec(SMOKE28)
    context, page_purpose, _, component_plan, _ = build_harness(
        spec, request_id=2809
    )
    first = resolve_tier1_collection_decision(
        context,
        page_purpose=page_purpose,
        component_plan=component_plan,
        existing_collections=[],
        heal_allowed=True,
    )
    assert first.code == "collection_derived"
    second = resolve_tier1_collection_decision(
        context,
        page_purpose=page_purpose,
        component_plan=component_plan,
        existing_collections=[],
        heal_allowed=False,
    )
    assert second.code == "collection_missing_required"
    bare_plan = MagicMock()
    bare_plan.components = ()
    unseedable = resolve_tier1_collection_decision(
        context,
        page_purpose=page_purpose,
        component_plan=bare_plan,
        existing_collections=[],
        heal_allowed=True,
    )
    assert unseedable.code == "collection_unseedable"


def test_derived_projection_lineage_and_candidate_ready_collection() -> None:
    spec = _load_spec(SMOKE28)
    context, page_purpose, page_ref, component_plan, component_ref = build_harness(
        spec, request_id=2810
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
    assert evidence.derived is True
    assert evidence.app_spec_sha256 == "a" * 64
    assert evidence.tier1_contract_hash == "a" * 64
    assert evidence.before_projection_hash != evidence.after_projection_hash
    assert evidence.collection_schema_hash
    assert evidence.source_references
    # Downstream candidate generation receives the validated collection.
    assert projected.data_collections[0].seed_records
    assert projected.data_collections[0].field_ids == (
        "FIELD-NAME",
        "FIELD-DESCRIPTION",
        "FIELD-DURATION",
    )


def test_request_28_failure_class_reproducible_without_heal_disabled() -> None:
    """Without derivation heal, empty entities still fail like production #28."""

    spec = _load_spec(SMOKE28)
    context, page_purpose, _, component_plan, _ = build_harness(
        spec, request_id=2811
    )
    decision = resolve_tier1_collection_decision(
        context,
        page_purpose=page_purpose,
        component_plan=component_plan,
        existing_collections=[],
        heal_allowed=False,
    )
    assert decision.required is True
    assert decision.code == "collection_missing_required"
