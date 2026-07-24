"""Deterministic cumulative Tier 2 contract projection."""
from __future__ import annotations

import hashlib
from dataclasses import replace

from app.application.appspec.source import canonical_json
from app.application.candidate_generation.cache import canonical_sha256
from app.application.composition_contract.context import CompositionContext
from app.application.composition_contract.graph import (
    build_component_dependency_graph,
)
from app.application.composition_contract.projections import (
    project_interactions,
    project_page_purpose,
)
from app.domain.schemas.business_component_plan import (
    ActionTriggerBinding,
    BusinessComponent,
    BusinessComponentPlan,
    ComponentStateBinding,
    PageComponentComposition,
)
from app.domain.schemas.composition_contract import (
    COMPOSITION_CONTRACT_SCHEMA_VERSION,
    CompositionArtifactRef,
)
from app.domain.schemas.content_data_plan import (
    ActionInputBinding,
    ContentDataPlan,
    ContentItem,
    DataCollection,
    EvidenceBinding,
    SeedFieldValue,
    SeedRecord,
    StatePayload,
)
from app.domain.schemas.preview_candidate import CandidateUpstreamRefs
from app.domain.schemas.tier_orchestration import (
    Tier2ExtensionContracts,
    Tier2Projection,
    TierReferenceDelta,
)


def _ordered_delta(upper: tuple[str, ...], lower: tuple[str, ...]) -> tuple[str, ...]:
    lower_set = set(lower)
    return tuple(item for item in upper if item not in lower_set)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _artifact_ref(
    *,
    record_id: int,
    kind: str,
    artifact,
) -> CompositionArtifactRef:
    return CompositionArtifactRef(
        id=record_id,
        artifact_kind=kind,
        schema_version=COMPOSITION_CONTRACT_SCHEMA_VERSION,
        sha256=canonical_sha256(artifact),
    )


def project_tier_2_delta(
    context: CompositionContext,
    *,
    accepted_tier_1_revision_id: int,
    accepted_tier_1_manifest_sha256: str,
    accepted_tier_1_visual_summary_id: int,
) -> Tier2Projection:
    lower = context.tiers[0]
    upper = context.tiers[1]
    fields = type(upper.references).model_fields
    delta = TierReferenceDelta(
        **{
            name: _ordered_delta(
                getattr(upper.references, name),
                getattr(lower.references, name),
            )
            for name in fields
        }
    )
    delta_sha = canonical_sha256(delta)
    lower_pages = set(lower.references.page_ids)
    delta_ids = (
        set(delta.requirement_ids)
        | set(delta.action_ids)
        | set(delta.evidence_ids)
        | set(delta.state_ids)
    )
    integration_page_ids: list[str] = []
    reasons: list[str] = []
    spec = context.app_spec
    trace = {item.requirement_id: item for item in spec.traceability}
    for page in spec.pages:
        if page.id not in lower_pages:
            continue
        linked = (
            set(page.action_ids)
            | set(page.evidence_ids)
            | set(page.state_ids)
            | {
                requirement_id
                for requirement_id, item in trace.items()
                if page.id in item.page_ids
            }
        )
        if linked & delta_ids:
            integration_page_ids.append(page.id)
            reasons.append(
                "Tier 2 canonical closure adds behavior or evidence to "
                f"accepted Tier 1 page {page.id}."
            )
    inherited = tuple(
        item
        for name in fields
        for item in getattr(lower.references, name)
        if (
            name != "page_ids"
            or item in integration_page_ids
            or item == lower.primary_journey_proof.page_ids[0]
        )
    )
    return Tier2Projection(
        request_id=context.refs.request_id,
        accepted_tier_1_revision_id=accepted_tier_1_revision_id,
        accepted_tier_1_manifest_sha256=accepted_tier_1_manifest_sha256,
        accepted_tier_1_visual_summary_id=(
            accepted_tier_1_visual_summary_id
        ),
        tier_1_closure_sha256=canonical_sha256(lower),
        tier_2_closure_sha256=canonical_sha256(upper),
        delta_sha256=delta_sha,
        tier_1_references=lower.references,
        tier_2_references=upper.references,
        delta=delta,
        inherited_dependency_ids=inherited,
        lower_tier_integration_page_ids=tuple(integration_page_ids),
        integration_justifications=tuple(reasons),
    )


def _seed_value(field):
    if field.enum_values:
        return field.enum_values[0]
    return {
        "string": f"Verified {field.name}",
        "integer": 1,
        "number": 1.0,
        "boolean": True,
        "date": "2026-07-24",
        "datetime": "2026-07-24T09:00:00Z",
        "enum": "active",
        "reference": "related-record",
        "list": ("verified",),
    }[field.type]


def _extend_components(
    context: CompositionContext,
    inherited: BusinessComponentPlan,
    *,
    page_purpose,
    page_ref,
    projection: Tier2Projection,
) -> BusinessComponentPlan:
    spec = context.app_spec
    refs = page_purpose.contract_refs
    page_map = {item.id: item for item in spec.pages}
    requirements = {item.id: item for item in spec.requirements}
    evidence = {item.id: item for item in spec.evidence}
    actions = {item.id: item for item in spec.actions}
    purpose_map = {item.page_id: item for item in page_purpose.pages}
    relevant_pages = tuple(
        item.page_id
        for item in page_purpose.pages
        if item.page_id in projection.delta.page_ids
        or item.page_id in projection.lower_tier_integration_page_ids
    )
    components = [
        item.model_copy()
        for item in inherited.components
    ]
    compositions = {
        item.page_id: list(item.ordered_component_ids)
        for item in inherited.page_compositions
    }
    triggers = list(inherited.action_trigger_bindings)
    states = list(inherited.component_state_bindings)
    for page_id in relevant_pages:
        purpose = purpose_map[page_id]
        page = page_map[page_id]
        action_ids = tuple(
            item for item in purpose.action_ids
            if item in projection.delta.action_ids
        )
        evidence_ids = tuple(
            item for item in purpose.evidence_ids
            if item in projection.delta.evidence_ids
        ) or purpose.evidence_ids
        requirement_ids = tuple(
            item for item in purpose.requirement_ids
            if item in projection.delta.requirement_ids
        ) or purpose.requirement_ids
        component_id = _stable_id("COMP-T2", page_id, *requirement_ids)
        domain_language: list[str] = [page.name]
        domain_language.extend(requirements[item].title for item in requirement_ids)
        domain_language.extend(actions[item].name for item in action_ids)
        domain_language.extend(evidence[item].name for item in evidence_ids)
        unique_language = tuple(dict.fromkeys(domain_language))
        entity_ids = tuple(
            dict.fromkeys(
                actions[item].entity_id
                for item in action_ids
                if actions[item].entity_id
            )
        )
        component = BusinessComponent(
            component_id=component_id,
            name=f"{page.name} Tier 2 capability",
            purpose=(
                f"Expose the canonical Tier 2 outcomes for {page.name}, "
                "including its domain evidence and executable behavior."
            ),
            component_kind=(
                "business_action"
                if action_ids
                else "business_evidence"
            ),
            domain_language=unique_language[:20],
            page_ids=(page_id,),
            role_ids=purpose.role_ids,
            requirement_ids=requirement_ids,
            entity_ids=entity_ids,
            capability_ids=purpose.capability_ids,
            state_ids=purpose.state_ids,
            action_ids=action_ids,
            evidence_ids=evidence_ids,
            content_responsibilities=tuple(
                evidence[item].name for item in evidence_ids
            ),
            data_responsibilities=tuple(
                f"Canonical data for {item}" for item in entity_ids
            ),
            interaction_responsibilities=tuple(
                actions[item].name for item in action_ids
            ),
            requires_component_ids=(),
            shared_across_pages=False,
        )
        components.append(component)
        compositions.setdefault(page_id, []).append(component_id)
        triggers.extend(
            ActionTriggerBinding(
                action_id=action_id,
                component_id=component_id,
                trigger_label=actions[action_id].name,
            )
            for action_id in action_ids
        )
        for state_id in purpose.state_ids:
            state_evidence = tuple(
                item.id
                for item in spec.evidence
                if item.id in evidence_ids
                and item.page_id == page_id
            )
            if state_evidence:
                states.append(
                    ComponentStateBinding(
                        component_id=component_id,
                        state_id=state_id,
                        visible_evidence_ids=state_evidence,
                    )
                )
    return BusinessComponentPlan(
        contract_refs=refs,
        page_purpose_ref=page_ref,
        components=tuple(components),
        page_compositions=tuple(
            PageComponentComposition(
                page_id=page.page_id,
                ordered_component_ids=tuple(compositions[page.page_id]),
            )
            for page in page_purpose.pages
        ),
        action_trigger_bindings=tuple(triggers),
        component_state_bindings=tuple(states),
    )


def _extend_content_data(
    context: CompositionContext,
    inherited: ContentDataPlan,
    *,
    page_purpose,
    page_ref,
    component_plan,
    component_ref,
    projection: Tier2Projection,
) -> ContentDataPlan:
    spec = context.app_spec
    refs = page_purpose.contract_refs
    components_by_page = {
        page.page_id: page.ordered_component_ids[-1]
        for page in component_plan.page_compositions
    }
    content_items = list(inherited.content_items)
    collections = list(inherited.data_collections)
    state_payloads = list(inherited.state_payloads)
    evidence_bindings = list(inherited.evidence_bindings)
    action_bindings = list(inherited.action_input_bindings)
    existing_content = {item.content_id for item in content_items}
    existing_collections = {item.entity_id: item for item in collections}
    existing_states = {item.state_id for item in state_payloads}
    existing_evidence = {item.evidence_id for item in evidence_bindings}
    existing_actions = {item.action_id for item in action_bindings}
    purpose_by_page = {item.page_id: item for item in page_purpose.pages}
    evidence_map = {item.id: item for item in spec.evidence}
    requirement_map = {item.id: item for item in spec.requirements}
    entity_map = {item.id: item for item in spec.entities}
    action_map = {item.id: item for item in spec.actions}

    for evidence_id in projection.delta.evidence_ids:
        item = evidence_map[evidence_id]
        component_id = components_by_page[item.page_id]
        content_id = _stable_id("CONTENT-T2", evidence_id)
        if content_id not in existing_content:
            page_requirements = purpose_by_page[item.page_id].requirement_ids
            content_items.append(
                ContentItem(
                    content_id=content_id,
                    semantic_kind=(
                        "success" if item.kind == "status" else "supporting_fact"
                    ),
                    value=f"{item.name}: {item.description}",
                    provenance="canonical_contract",
                    page_ids=(item.page_id,),
                    component_ids=(component_id,),
                    requirement_ids=page_requirements,
                )
            )
            existing_content.add(content_id)
        if evidence_id not in existing_evidence:
            evidence_bindings.append(
                EvidenceBinding(
                    evidence_id=evidence_id,
                    binding_kind="content",
                    content_ids=(content_id,),
                )
            )
            existing_evidence.add(evidence_id)

    for requirement_id in projection.delta.requirement_ids:
        trace = next(
            item
            for item in spec.traceability
            if item.requirement_id == requirement_id
        )
        page_id = trace.page_ids[0]
        content_id = _stable_id("CONTENT-T2-REQ", requirement_id)
        if content_id not in existing_content:
            requirement = requirement_map[requirement_id]
            content_items.append(
                ContentItem(
                    content_id=content_id,
                    semantic_kind="description",
                    value=f"{requirement.title}: {requirement.description}",
                    provenance="canonical_contract",
                    page_ids=(page_id,),
                    component_ids=(components_by_page[page_id],),
                    requirement_ids=(requirement_id,),
                )
            )
            existing_content.add(content_id)

    needed_entities = tuple(
        dict.fromkeys(
            action_map[action_id].entity_id
            for action_id in projection.tier_2_references.action_ids
            if action_map[action_id].entity_id
        )
    )
    for entity_id in needed_entities:
        if entity_id in existing_collections:
            continue
        entity = entity_map[entity_id]
        relevant_pages = tuple(
            page.page_id
            for page in page_purpose.pages
            if any(
                action_map[action_id].entity_id == entity_id
                for action_id in page.action_ids
            )
        ) or (page_purpose.pages[0].page_id,)
        collection = DataCollection(
            collection_id=_stable_id("DATA-T2", entity_id),
            entity_id=entity_id,
            purpose=f"Canonical Tier 2 records for {entity.name}.",
            page_ids=relevant_pages,
            component_ids=tuple(
                dict.fromkeys(components_by_page[item] for item in relevant_pages)
            ),
            field_ids=tuple(field.id for field in entity.fields),
            seed_records=(
                SeedRecord(
                    record_id=_stable_id("RECORD-T2", entity_id),
                    values=tuple(
                        SeedFieldValue(
                            field_id=field.id,
                            value=_seed_value(field),
                        )
                        for field in entity.fields
                    ),
                ),
            ),
        )
        collections.append(collection)
        existing_collections[entity_id] = collection

    for state_id in projection.delta.state_ids:
        if state_id in existing_states:
            continue
        state = next(item for item in spec.states if item.id == state_id)
        page = purpose_by_page[state.page_id]
        content_ids = tuple(
            item.content_id
            for item in content_items
            if state.page_id in item.page_ids
        )
        collection_ids = tuple(
            item.collection_id
            for item in collections
            if state.page_id in item.page_ids
        )
        state_payloads.append(
            StatePayload(
                state_id=state_id,
                page_id=state.page_id,
                content_ids=content_ids,
                collection_ids=collection_ids,
                component_ids=(components_by_page[state.page_id],),
                evidence_ids=tuple(
                    item for item in state.evidence_ids
                    if item in page.evidence_ids
                ),
            )
        )
        existing_states.add(state_id)

    fallback_collection_id = collections[0].collection_id
    for action_id in projection.delta.action_ids:
        if action_id in existing_actions:
            continue
        action = action_map[action_id]
        needs_data = action.entity_id is not None or action.kind in {
            "fill",
            "select",
            "submit",
        }
        if not needs_data:
            continue
        collection = (
            existing_collections[action.entity_id]
            if action.entity_id
            else None
        )
        action_bindings.append(
            ActionInputBinding(
                action_id=action_id,
                collection_ids=(
                    (collection.collection_id,)
                    if collection
                    else (fallback_collection_id,)
                ),
                field_ids=(
                    collection.field_ids if collection else ()
                ),
            )
        )
        existing_actions.add(action_id)
    return ContentDataPlan(
        contract_refs=refs,
        page_purpose_ref=page_ref,
        business_component_plan_ref=component_ref,
        content_items=tuple(content_items),
        data_collections=tuple(collections),
        relationships=inherited.relationships,
        state_payloads=tuple(state_payloads),
        evidence_bindings=tuple(evidence_bindings),
        action_input_bindings=tuple(action_bindings),
    )


def build_tier_2_extension_contracts(
    context: CompositionContext,
    *,
    inherited_page_purpose,
    inherited_components,
    inherited_content_data,
    projection: Tier2Projection,
    artifact_record_id: int,
) -> tuple[Tier2ExtensionContracts, CandidateUpstreamRefs]:
    tier_refs = context.refs.model_copy(update={"target_tier": 2})
    tier_context = replace(context, refs=tier_refs)
    page_purpose = project_page_purpose(tier_context, tier_number=2)
    page_ref = _artifact_ref(
        record_id=artifact_record_id,
        kind="page_purpose_contract",
        artifact=page_purpose,
    )
    components = _extend_components(
        tier_context,
        inherited_components,
        page_purpose=page_purpose,
        page_ref=page_ref,
        projection=projection,
    )
    component_ref = _artifact_ref(
        record_id=artifact_record_id,
        kind="business_component_plan",
        artifact=components,
    )
    content_data = _extend_content_data(
        tier_context,
        inherited_content_data,
        page_purpose=page_purpose,
        page_ref=page_ref,
        component_plan=components,
        component_ref=component_ref,
        projection=projection,
    )
    content_ref = _artifact_ref(
        record_id=artifact_record_id,
        kind="content_data_plan",
        artifact=content_data,
    )
    interactions = project_interactions(
        tier_context,
        page_purpose=page_purpose,
        page_purpose_ref=page_ref,
        component_plan=components,
        component_plan_ref=component_ref,
        content_data_plan=content_data,
        content_data_plan_ref=content_ref,
        tier_number=2,
    )
    interaction_ref = _artifact_ref(
        record_id=artifact_record_id,
        kind="interaction_contract",
        artifact=interactions,
    )
    graph = build_component_dependency_graph(
        refs=tier_refs,
        page_purpose=page_purpose,
        page_purpose_ref=page_ref,
        component_plan=components,
        component_plan_ref=component_ref,
        content_data_plan=content_data,
        content_data_plan_ref=content_ref,
        interaction_contract=interactions,
        interaction_contract_ref=interaction_ref,
    )
    graph_ref = _artifact_ref(
        record_id=artifact_record_id,
        kind="component_dependency_graph",
        artifact=graph,
    )
    contracts = Tier2ExtensionContracts(
        projection=projection,
        page_purpose=page_purpose,
        business_components=components,
        content_data=content_data,
        interactions=interactions,
        dependency_graph=graph,
        page_purpose_sha256=page_ref.sha256,
        business_components_sha256=component_ref.sha256,
        content_data_sha256=content_ref.sha256,
        interactions_sha256=interaction_ref.sha256,
        dependency_graph_sha256=graph_ref.sha256,
    )
    refs = CandidateUpstreamRefs(
        request_id=context.refs.request_id,
        target_tier=2,
        composition_contract_refs=tier_refs,
        page_purpose_ref=page_ref,
        business_component_plan_ref=component_ref,
        content_data_plan_ref=content_ref,
        interaction_contract_ref=interaction_ref,
        component_dependency_graph_ref=graph_ref,
    )
    return contracts, refs


def extension_contract_sha256(contracts: Tier2ExtensionContracts) -> str:
    return hashlib.sha256(
        canonical_json(contracts.model_dump(mode="json")).encode("utf-8")
    ).hexdigest()


__all__ = [
    "build_tier_2_extension_contracts",
    "extension_contract_sha256",
    "project_tier_2_delta",
]
