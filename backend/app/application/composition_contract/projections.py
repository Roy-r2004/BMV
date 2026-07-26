"""Deterministic PagePurpose, BusinessComponent, and Interaction projections."""
from __future__ import annotations

import hashlib
import json
import re

from app.application.composition_contract.collection_derivation import (
    resolve_tier1_collection_decision,
)
from app.application.composition_contract.context import CompositionContext
from app.domain.schemas.business_component_plan import (
    ActionTriggerBinding,
    BusinessComponent,
    BusinessComponentPlan,
    ComponentStateBinding,
    PageComponentComposition,
)
from app.domain.schemas.composition_contract import CompositionArtifactRef
from app.domain.schemas.content_data_plan import (
    ActionInputBinding,
    CollectionProjectionEvidence,
    ContentDataPlan,
    ContentItem,
    DataCollection,
    DerivedEntity,
    DerivedEntityField,
    EntityRoleEvidence,
    EvidenceBinding,
    SeedFieldValue,
    SeedRecord,
    StatePayload,
)
from app.domain.schemas.interaction_contract import (
    BrowserAssertionProjection,
    InteractionContract,
    InteractionProjection,
    ProjectedStateEffect,
    ProjectedTransition,
)
from app.domain.schemas.page_purpose_contract import (
    ImmutablePageConstraints,
    PagePurpose,
    PagePurposeContract,
    ProjectedDesignConstraints,
)

_WORD = re.compile(r"[a-z0-9]+")
_BLOCKED_DOMAIN_WORDS = {
    "action",
    "business",
    "component",
    "content",
    "data",
    "display",
    "information",
    "page",
    "show",
    "user",
}


class CompositionProjectionError(ValueError):
    """Canonical projection cannot be completed without invention."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


def project_page_purpose(
    context: CompositionContext,
    *,
    tier_number: int = 1,
) -> PagePurposeContract:
    spec = context.app_spec
    tier = context.tier(tier_number)
    refs = tier.references
    tier_pages = set(refs.page_ids)
    tier_requirements = set(refs.requirement_ids)
    tier_capabilities = set(refs.capability_ids)
    tier_states = set(refs.state_ids)
    tier_actions = set(refs.action_ids)
    tier_transitions = set(refs.transition_ids)
    tier_evidence = set(refs.evidence_ids)
    tier_journeys = set(refs.journey_ids)
    tier_tests = set(refs.acceptance_test_ids)
    ia_pages = {
        page.page_id: page
        for page in context.information_architecture.pages
    }
    trace = {
        item.requirement_id: item for item in spec.traceability
    }
    pages: list[PagePurpose] = []
    immutable = ImmutablePageConstraints(
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
    for page in spec.pages:
        if page.id not in tier_pages:
            continue
        architecture = ia_pages.get(page.id)
        if architecture is None:
            raise CompositionProjectionError(
                f"IA is missing Tier 1 page {page.id}."
            )
        requirement_ids = tuple(
            requirement.id
            for requirement in spec.requirements
            if requirement.id in tier_requirements
            and page.id in trace[requirement.id].page_ids
        )
        action_ids = tuple(
            action_id
            for action_id in page.action_ids
            if action_id in tier_actions
        )
        transition_ids = tuple(
            transition.id
            for transition in spec.transitions
            if transition.id in tier_transitions
            and transition.action_id in action_ids
        )
        journey_ids = tuple(
            journey.id
            for journey in spec.journeys
            if journey.id in tier_journeys
            and (
                journey.start_page_id == page.id
                or any(
                    step.expected_page_id == page.id
                    for step in journey.steps
                )
            )
        )
        test_ids = tuple(
            test.id
            for test in spec.acceptance_tests
            if test.id in tier_tests
            and (
                bool(set(test.requirement_ids) & set(requirement_ids))
                or test.journey_id in journey_ids
            )
        )
        if (
            (tier_number in (1, 2) and not requirement_ids)
            or (tier_number in (1, 2) and not test_ids)
            or (tier_number == 1 and not journey_ids)
            or (tier_number in (1, 2) and action_ids and not journey_ids)
        ):
            raise CompositionProjectionError(
                f"Tier {tier_number} page {page.id} lacks closed references."
            )
        pages.append(
            PagePurpose(
                page_id=page.id,
                route=page.route,
                surface=page.surface,
                goal=architecture.purpose,
                role_ids=tuple(
                    role_id
                    for role_id in page.role_ids
                    if role_id in refs.role_ids
                ),
                requirement_ids=requirement_ids,
                outcome_requirement_ids=tuple(
                    requirement_id
                    for requirement_id
                    in architecture.required_outcome_requirement_ids
                    if requirement_id in tier_requirements
                ),
                capability_ids=tuple(
                    item
                    for item in page.capability_ids
                    if item in tier_capabilities
                ),
                state_ids=tuple(
                    item for item in page.state_ids if item in tier_states
                ),
                action_ids=action_ids,
                transition_ids=transition_ids,
                evidence_ids=tuple(
                    item for item in page.evidence_ids if item in tier_evidence
                ),
                journey_ids=journey_ids,
                acceptance_test_ids=test_ids,
                navigation_visibility=(
                    architecture.navigation_visibility
                ),
                deep_link_reason=architecture.deep_link_reason,
                mobile=architecture.mobile,
                immutable=immutable,
            )
        )
    return PagePurposeContract(
        contract_refs=context.refs,
        primary_outcome_requirement_id=(
            context.product_strategy_v2.primary_outcome_requirement_id
        ),
        mobile_global_behavior=(
            context.information_architecture.mobile_global_behavior
        ),
        design_constraints=ProjectedDesignConstraints(
            composition_hierarchy=(
                context.design_dna.composition.hierarchy
            ),
            composition_emphasis=context.design_dna.composition.emphasis,
            public_surface_density=(
                context.design_dna.density.public_surface
            ),
            operations_surface_density=(
                context.design_dna.density.operations_surface
            ),
            motion_character=context.design_dna.motion.character,
            reduced_motion=context.design_dna.motion.reduced_motion,
            avoid_list=context.design_dna.avoid_list,
        ),
        pages=tuple(pages),
    )


def _domain_words(*sources: str) -> tuple[str, ...]:
    words: list[str] = []
    for source in sources:
        for word in _WORD.findall(source.casefold()):
            if (
                len(word) >= 4
                and word not in _BLOCKED_DOMAIN_WORDS
                and word not in words
            ):
                words.append(word)
            if len(words) >= 4:
                return tuple(words)
    return tuple(words) or ("workflow",)


def project_business_component_plan(
    context: CompositionContext,
    *,
    page_purpose: PagePurposeContract,
    page_purpose_ref: CompositionArtifactRef,
) -> BusinessComponentPlan:
    """Build a Tier-1-valid component plan from page purpose + AppSpec."""

    spec = context.app_spec
    capabilities = {item.id: item for item in spec.capabilities}
    actions = {item.id: item for item in spec.actions}
    states = {item.id: item for item in spec.states}
    components: list[BusinessComponent] = []
    compositions: list[PageComponentComposition] = []
    component_by_page: dict[str, str] = {}

    for page in page_purpose.pages:
        suffix = page.page_id.removeprefix("PAGE-")
        component_id = f"COMP-{suffix}"
        component_by_page[page.page_id] = component_id
        linked_caps = [
            capabilities[item]
            for item in page.capability_ids
            if item in capabilities
        ]
        entity_ids: list[str] = []
        for capability in linked_caps:
            for entity_id in capability.entity_ids:
                if entity_id not in entity_ids:
                    entity_ids.append(entity_id)
        for action_id in page.action_ids:
            action = actions.get(action_id)
            if action is None or not action.entity_id:
                continue
            if action.entity_id not in entity_ids:
                entity_ids.append(action.entity_id)
        language = _domain_words(
            " ".join(item.name for item in linked_caps),
            " ".join(
                actions[item].name
                for item in page.action_ids
                if item in actions
            ),
            page.goal,
        )
        purpose_terms = " and ".join(language[:2])
        components.append(
            BusinessComponent(
                component_id=component_id,
                name=f"{suffix.replace('-', ' ').title()} Workspace",
                purpose=(
                    f"Coordinate the {purpose_terms} workflow and make its "
                    "canonical outcome visibly complete."
                ),
                component_kind=(
                    "business_action" if page.action_ids else "business_content"
                ),
                domain_language=language,
                page_ids=(page.page_id,),
                role_ids=page.role_ids,
                requirement_ids=page.requirement_ids
                or page.outcome_requirement_ids,
                entity_ids=tuple(entity_ids),
                capability_ids=page.capability_ids,
                state_ids=page.state_ids,
                action_ids=page.action_ids,
                evidence_ids=page.evidence_ids,
                content_responsibilities=(
                    f"Explain the next {language[0]} decision clearly.",
                ),
                data_responsibilities=(
                    f"Show the current {language[0]} status and details.",
                ),
                interaction_responsibilities=(
                    (f"Submit the canonical {language[0]} action.",)
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

    state_bindings: list[ComponentStateBinding] = []
    for page in page_purpose.pages:
        component_id = component_by_page[page.page_id]
        for state_id in page.state_ids:
            state = states.get(state_id)
            if state is None:
                continue
            evidence_ids = tuple(
                item
                for item in state.evidence_ids
                if item in page.evidence_ids
            )
            if evidence_ids:
                state_bindings.append(
                    ComponentStateBinding(
                        component_id=component_id,
                        state_id=state_id,
                        visible_evidence_ids=evidence_ids,
                    )
                )

    action_bindings = tuple(
        ActionTriggerBinding(
            action_id=action_id,
            component_id=component_by_page[actions[action_id].page_id],
            trigger_label=_sanitize_content_value(actions[action_id].name)[
                :240
            ],
        )
        for action_id in context.tier_1.references.action_ids
        if action_id in actions
        and actions[action_id].page_id in component_by_page
    )

    return BusinessComponentPlan(
        contract_refs=context.refs,
        page_purpose_ref=page_purpose_ref,
        components=tuple(components),
        page_compositions=tuple(compositions),
        action_trigger_bindings=action_bindings,
        component_state_bindings=tuple(state_bindings),
    )


_FORBIDDEN_CONTENT_MARKERS = (
    "<div",
    "<section",
    "<main",
    "classname=",
    "function ",
    "const ",
    "=>",
    "@/ui",
    "tailwind",
    "tsx",
    "jsx",
)


def _sanitize_content_value(value: str) -> str:
    cleaned = value
    for marker in _FORBIDDEN_CONTENT_MARKERS:
        idx = cleaned.casefold().find(marker)
        while idx >= 0:
            cleaned = cleaned[:idx] + " " + cleaned[idx + len(marker) :]
            idx = cleaned.casefold().find(marker)
    return " ".join(cleaned.split()) or "Business workflow support"


def _stable_content_id(prefix: str, raw: str) -> str:
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _seed_value(field) -> object:
    if field.type == "enum":
        if field.enum_values:
            return field.enum_values[0]
        return _sanitize_content_value(f"Realistic {field.name} value")
    if field.type == "boolean":
        return True
    if field.type == "integer":
        return 1
    if field.type == "number":
        return 125.0
    if field.type == "date":
        return "2026-08-15"
    if field.type == "datetime":
        return "2026-08-15T10:00:00Z"
    if field.type == "reference":
        return "BOOKING-REFERENCE-01"
    if field.type == "list":
        return ("consultation", "follow-up")
    return _sanitize_content_value(f"Realistic {field.name} value")


def project_content_data_plan(
    context: CompositionContext,
    *,
    page_purpose: PagePurposeContract,
    page_purpose_ref: CompositionArtifactRef,
    component_plan: BusinessComponentPlan,
    component_plan_ref: CompositionArtifactRef,
) -> ContentDataPlan:
    """Build a Tier-1-valid content/data plan from page + component contracts."""

    spec = context.app_spec
    tier = context.tier_1.references
    tier_evidence_ids = set(tier.evidence_ids)
    tier_state_ids = set(tier.state_ids)
    tier_action_ids = set(tier.action_ids)
    page_ids = {page.page_id for page in page_purpose.pages}
    page_contract = {page.page_id: page for page in page_purpose.pages}
    components = {
        item.component_id: item for item in component_plan.components
    }
    if not components:
        raise CompositionProjectionError(
            "Tier 1 content projection needs at least one business component."
        )
    default_component_id = next(iter(components))
    component_for_page: dict[str, str] = {}
    for component in component_plan.components:
        for page_id in component.page_ids:
            component_for_page.setdefault(page_id, component.component_id)

    content_items: list[ContentItem] = []
    content_by_evidence: dict[str, str] = {}
    used_content_ids: set[str] = set()
    for evidence in spec.evidence:
        if evidence.id not in tier_evidence_ids:
            continue
        if evidence.page_id not in page_ids:
            continue
        content_id = _stable_content_id("CONTENT-E", evidence.id)
        used_content_ids.add(content_id)
        content_by_evidence[evidence.id] = content_id
        page = page_contract[evidence.page_id]
        content_items.append(
            ContentItem(
                content_id=content_id,
                semantic_kind=(
                    "success"
                    if "confirmation" in evidence.name.casefold()
                    or "success" in evidence.name.casefold()
                    else "instruction"
                ),
                value=_sanitize_content_value(evidence.description),
                provenance="canonical_contract",
                page_ids=(evidence.page_id,),
                component_ids=(
                    component_for_page.get(
                        evidence.page_id, default_component_id
                    ),
                ),
                requirement_ids=page.requirement_ids
                or page.outcome_requirement_ids,
            )
        )

    # Pages can enter Tier 1 without page-local evidence. State payloads cannot
    # be empty, so every page needs at least one content anchor.
    pages_with_content = {
        page_id for item in content_items for page_id in item.page_ids
    }
    for page in page_purpose.pages:
        if page.page_id in pages_with_content:
            continue
        content_id = _stable_content_id("CONTENT-P", page.page_id)
        while content_id in used_content_ids:
            content_id = _stable_content_id(
                "CONTENT-P", f"{page.page_id}:{content_id}"
            )
        used_content_ids.add(content_id)
        content_items.append(
            ContentItem(
                content_id=content_id,
                semantic_kind="instruction",
                value=_sanitize_content_value(page.goal),
                provenance="canonical_contract",
                page_ids=(page.page_id,),
                component_ids=(
                    component_for_page.get(page.page_id, default_component_id),
                ),
                requirement_ids=page.requirement_ids
                or page.outcome_requirement_ids,
            )
        )
    if not content_items:
        raise CompositionProjectionError(
            "Tier 1 content projection needs at least one content item."
        )

    entity_ids: list[str] = []
    for component in components.values():
        for entity_id in component.entity_ids:
            if entity_id not in entity_ids:
                entity_ids.append(entity_id)
    if not entity_ids:
        entity_ids = list(tier.entity_ids)
    entities = {item.id: item for item in spec.entities}
    collections: list[DataCollection] = []
    collection_by_entity: dict[str, str] = {}

    def _append_collection(entity_id: str) -> None:
        entity = entities.get(entity_id)
        if entity is None or not entity.fields or entity_id in collection_by_entity:
            return
        collection_id = _stable_content_id("DATA", entity_id)
        collection_by_entity[entity_id] = collection_id
        component_ids = tuple(
            component.component_id
            for component in components.values()
            if entity_id in component.entity_ids
        ) or tuple(components)
        linked_pages = tuple(
            dict.fromkeys(
                page_id
                for component_id in component_ids
                for page_id in components[component_id].page_ids
                if page_id in page_ids
            )
        ) or tuple(page_contract)
        field_ids = tuple(field.id for field in entity.fields)
        collections.append(
            DataCollection(
                collection_id=collection_id,
                entity_id=entity_id,
                purpose=_sanitize_content_value(
                    f"Provide realistic {entity.name} records "
                    "for the accepted Tier 1 workflow."
                ),
                page_ids=linked_pages,
                component_ids=component_ids,
                field_ids=field_ids,
                seed_records=(
                    SeedRecord(
                        record_id=_stable_content_id("RECORD", entity_id),
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
        )

    for entity_id in entity_ids:
        _append_collection(entity_id)
    # Do not auto-append out-of-tier AppSpec entities here. Derivation may
    # restore only when Tier 1 business meaning unambiguously matches.

    before_hash = hashlib.sha256(
        json.dumps(
            [item.model_dump(mode="json") for item in collections],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    decision = resolve_tier1_collection_decision(
        context,
        page_purpose=page_purpose,
        component_plan=component_plan,
        existing_collections=collections,
        before_projection_hash=before_hash,
        heal_allowed=True,
    )
    if decision.collection is not None and not collections:
        collections.append(decision.collection)
        collection_by_entity[decision.collection.entity_id] = (
            decision.collection.collection_id
        )
    if not collections and decision.code != "collection_not_required":
        raise CompositionProjectionError(
            (
                f"Tier 1 content projection collection decision "
                f"{decision.code}: {decision.reason}"
            ),
            code=decision.code,
        )

    collection_projection = CollectionProjectionEvidence(
        policy_revision=decision.policy_revision,
        decision=decision.code,
        reason=decision.reason,
        required=decision.required,
        derived=decision.derived,
        heal_applied=decision.heal_applied,
        entity_type=decision.entity_type,
        source_references=tuple(decision.source_references[:80]),
        collection_schema_hash=decision.collection_schema_hash,
        seed_hash=decision.seed_hash,
        before_projection_hash=decision.before_projection_hash,
        after_projection_hash=decision.after_projection_hash or before_hash,
        app_spec_sha256=decision.app_spec_sha256,
        tier1_contract_hash=decision.tier1_contract_hash,
        collection_id=(
            decision.collection.collection_id if decision.collection else None
        ),
        minimum_seed_count=(
            len(decision.collection.seed_records) if decision.collection else 0
        ),
        derived_entities=(
            (
                DerivedEntity(
                    id=decision.derived_entity.id,
                    name=decision.derived_entity.name,
                    description=decision.derived_entity.description,
                    fields=tuple(
                        DerivedEntityField(
                            id=field.id,
                            name=field.name,
                            type=field.type,  # type: ignore[arg-type]
                            required=field.required,
                        )
                        for field in decision.derived_entity.fields
                    ),
                ),
            )
            if decision.derived_entity is not None
            else ()
        ),
        result_code=decision.result_code,
        decision_hash=decision.decision_hash,
        entity_roles=tuple(
            EntityRoleEvidence(
                entity_type=str(item.get("entity_type") or ""),
                normalized_entity_type=str(
                    item.get("normalized_entity_type")
                    or item.get("entity_type")
                    or ""
                ),
                roles=tuple(str(role) for role in (item.get("roles") or ())),
                positive_signals=tuple(
                    str(signal) for signal in (item.get("positive_signals") or ())
                ),
                negative_signals=tuple(
                    str(signal) for signal in (item.get("negative_signals") or ())
                ),
                score=int(item.get("score") or 0),
                source_references=tuple(
                    str(ref) for ref in (item.get("source_references") or ())
                )[:40],
                result_code=str(item.get("result_code") or "supporting_entity_excluded"),
                eligible_primary=bool(item.get("eligible_primary")),
            )
            for item in (decision.entity_roles or [])[:40]
            if item.get("entity_type")
        ),
        excluded_transaction_entity_types=tuple(
            decision.excluded_transaction_entity_types or ()
        ),
        ambiguity_candidates_after_classification=tuple(
            decision.ambiguity_candidates_after_classification or ()
        ),
        transactional_entities=tuple(
            DerivedEntity(
                id=entity.id,
                name=entity.name,
                description=entity.description,
                fields=tuple(
                    DerivedEntityField(
                        id=field.id,
                        name=field.name,
                        type=field.type,  # type: ignore[arg-type]
                        required=field.required,
                    )
                    for field in entity.fields
                ),
            )
            for entity in (decision.transactional_entities or ())
        ),
        selected_primary_collection=decision.selected_primary_collection,
    )

    component_state = {
        (binding.component_id, binding.state_id, evidence_id)
        for binding in component_plan.component_state_bindings
        for evidence_id in binding.visible_evidence_ids
    }
    evidence_bindings: list[EvidenceBinding] = []
    for evidence in spec.evidence:
        if evidence.id not in tier_evidence_ids:
            continue
        if evidence.page_id not in page_ids:
            continue
        content_id = content_by_evidence[evidence.id]
        component_id = component_for_page.get(
            evidence.page_id, default_component_id
        )
        state_id = next(
            (
                state.id
                for state in spec.states
                if state.page_id == evidence.page_id
                and (component_id, state.id, evidence.id) in component_state
            ),
            None,
        )
        if state_id is not None:
            evidence_bindings.append(
                EvidenceBinding(
                    evidence_id=evidence.id,
                    binding_kind="component_state",
                    content_ids=(),
                    collection_ids=(),
                    component_id=component_id,
                    state_id=state_id,
                )
            )
        else:
            evidence_bindings.append(
                EvidenceBinding(
                    evidence_id=evidence.id,
                    binding_kind="content",
                    content_ids=(content_id,),
                    collection_ids=(),
                    component_id=None,
                    state_id=None,
                )
            )
    if not evidence_bindings:
        raise CompositionProjectionError(
            "Tier 1 content projection needs evidence on an in-tier page."
        )

    content_ids_by_page = {
        page.page_id: tuple(
            item.content_id
            for item in content_items
            if page.page_id in item.page_ids
        )
        for page in page_purpose.pages
    }
    state_payloads: list[StatePayload] = []
    for state in spec.states:
        if state.id not in tier_state_ids or state.page_id not in page_ids:
            continue
        page_id = state.page_id
        content_ids = content_ids_by_page.get(page_id, ())
        collection_ids = tuple(
            item.collection_id
            for item in collections
            if page_id in item.page_ids
        )
        evidence_ids = tuple(
            evidence_id
            for evidence_id in state.evidence_ids
            if evidence_id in tier_evidence_ids
        )
        if not content_ids and not collection_ids and not evidence_ids:
            content_ids = content_ids_by_page.get(page_id) or (
                (content_items[0].content_id,)
            )
        state_payloads.append(
            StatePayload(
                state_id=state.id,
                page_id=page_id,
                content_ids=content_ids,
                collection_ids=collection_ids,
                component_ids=(
                    component_for_page.get(page_id, default_component_id),
                ),
                evidence_ids=evidence_ids,
            )
        )
    if not state_payloads:
        raise CompositionProjectionError(
            "Tier 1 content projection needs at least one state payload."
        )

    action_bindings: list[ActionInputBinding] = []
    for action in spec.actions:
        if action.id not in tier_action_ids:
            continue
        if action.entity_id is not None:
            collection_id = collection_by_entity.get(action.entity_id)
            if collection_id is None:
                continue
        elif action.kind in {"fill", "select", "submit"}:
            if not collections:
                continue
            collection_id = next(
                (
                    item.collection_id
                    for item in collections
                    if action.page_id in item.page_ids
                ),
                collections[0].collection_id,
            )
        else:
            continue
        collection = next(
            item for item in collections if item.collection_id == collection_id
        )
        action_bindings.append(
            ActionInputBinding(
                action_id=action.id,
                collection_ids=(collection_id,),
                field_ids=collection.field_ids,
            )
        )

    return ContentDataPlan(
        contract_refs=context.refs,
        page_purpose_ref=page_purpose_ref,
        business_component_plan_ref=component_plan_ref,
        content_items=tuple(content_items),
        data_collections=tuple(collections),
        relationships=(),
        state_payloads=tuple(state_payloads),
        evidence_bindings=tuple(evidence_bindings),
        action_input_bindings=tuple(action_bindings),
        collection_projection=collection_projection,
    )


def _success_evidence_ids(
    context: CompositionContext,
    *,
    transition_id: str,
    to_state_id: str,
    tier_number: int = 1,
) -> tuple[str, ...]:
    tier = context.tier(tier_number)
    allowed = set(tier.references.evidence_ids)
    gathered: set[str] = set()
    for journey in context.app_spec.journeys:
        if journey.id not in tier.references.journey_ids:
            continue
        for step in journey.steps:
            if step.transition_id == transition_id:
                gathered.update(step.evidence_ids)
    for state in context.app_spec.states:
        if state.id == to_state_id:
            gathered.update(state.evidence_ids)
    return tuple(
        evidence.id
        for evidence in context.app_spec.evidence
        if evidence.id in allowed and evidence.id in gathered
    )


def project_interactions(
    context: CompositionContext,
    *,
    page_purpose: PagePurposeContract,
    page_purpose_ref: CompositionArtifactRef,
    component_plan: BusinessComponentPlan,
    component_plan_ref: CompositionArtifactRef,
    content_data_plan: ContentDataPlan,
    content_data_plan_ref: CompositionArtifactRef,
    tier_number: int = 1,
) -> InteractionContract:
    spec = context.app_spec
    trigger_by_action = {
        item.action_id: item.component_id
        for item in component_plan.action_trigger_bindings
    }
    input_by_action = {
        item.action_id: item
        for item in content_data_plan.action_input_bindings
    }
    page_map = {page.id: page for page in spec.pages}
    tests = {
        test.id: test
        for test in spec.acceptance_tests
        if test.id in context.tier(tier_number).references.acceptance_test_ids
    }
    journeys = {
        journey.id: journey
        for journey in spec.journeys
        if journey.id in context.tier(tier_number).references.journey_ids
    }
    tier_action_ids = set(context.tier(tier_number).references.action_ids)
    interactions: list[InteractionProjection] = []
    for action in spec.actions:
        if action.id not in tier_action_ids:
            continue
        page = page_map.get(action.page_id)
        if page is None:
            continue
        trigger_id = trigger_by_action.get(action.id)
        if trigger_id is None:
            continue
        input_binding = input_by_action.get(action.id)
        needs_data = (
            action.entity_id is not None
            and action.entity_id in {
                item.entity_id for item in content_data_plan.data_collections
            }
        ) or action.kind in {"fill", "select", "submit"}
        if needs_data and input_binding is None:
            continue
        action_transitions = tuple(
            transition
            for transition in spec.transitions
            if transition.id
            in context.tier(tier_number).references.transition_ids
            and transition.action_id == action.id
        )
        if not action_transitions:
            continue
        journey_ids = tuple(
            journey.id
            for journey in journeys.values()
            if any(step.action_id == action.id for step in journey.steps)
        )
        test_ids = tuple(
            test.id
            for test in tests.values()
            if test.journey_id in journey_ids
        )
        if not journey_ids or not test_ids:
            continue
        projected_transitions: list[ProjectedTransition] = []
        for transition in action_transitions:
            success_evidence = _success_evidence_ids(
                context,
                transition_id=transition.id,
                to_state_id=transition.to_state_id,
                tier_number=tier_number,
            )
            if not success_evidence:
                continue
            projected_transitions.append(
                ProjectedTransition(
                    transition_id=transition.id,
                    from_state_id=transition.from_state_id,
                    to_state_id=transition.to_state_id,
                    description=transition.description,
                    preconditions=transition.preconditions,
                    postconditions=transition.postconditions,
                    effects=tuple(
                        ProjectedStateEffect(
                            entity_id=effect.entity_id,
                            field_id=effect.field_id,
                            operation=effect.operation,
                            value=effect.value,
                        )
                        for effect in transition.effects
                    ),
                    success_evidence_ids=success_evidence,
                )
            )
        if not projected_transitions:
            continue
        browser_assertions = tuple(
            BrowserAssertionProjection(
                acceptance_test_id=test.id,
                assertion_index=index,
                kind=assertion.kind,
                description=assertion.description,
                page_id=assertion.page_id,
                route=(
                    page_map[assertion.page_id].route
                    if assertion.page_id and assertion.page_id in page_map
                    else None
                ),
                state_id=assertion.state_id,
                evidence_id=assertion.evidence_id,
                expected=assertion.expected,
            )
            for test_id in test_ids
            for test in (tests[test_id],)
            for index, assertion in enumerate(test.assertions)
        )
        interactions.append(
            InteractionProjection(
                action_id=action.id,
                page_id=action.page_id,
                route=page.route,
                role_id=action.role_id,
                action_kind=action.kind,
                entity_id=action.entity_id,
                trigger_component_id=trigger_id,
                input_collection_ids=(
                    input_binding.collection_ids if input_binding else ()
                ),
                input_field_ids=(
                    input_binding.field_ids if input_binding else ()
                ),
                transitions=tuple(projected_transitions),
                journey_ids=journey_ids,
                acceptance_test_ids=test_ids,
                browser_assertions=browser_assertions,
            )
        )
    if not interactions:
        raise CompositionProjectionError(
            "Tier 1 interaction projection needs at least one proven action."
        )
    return InteractionContract(
        contract_refs=context.refs,
        page_purpose_ref=page_purpose_ref,
        business_component_plan_ref=component_plan_ref,
        content_data_plan_ref=content_data_plan_ref,
        interactions=tuple(interactions),
    )


__all__ = [
    "CompositionProjectionError",
    "project_business_component_plan",
    "project_content_data_plan",
    "project_interactions",
    "project_page_purpose",
]
