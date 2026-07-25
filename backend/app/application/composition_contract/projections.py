"""Deterministic PagePurpose, BusinessComponent, and Interaction projections."""
from __future__ import annotations

import re

from app.application.composition_contract.context import CompositionContext
from app.domain.schemas.business_component_plan import (
    ActionTriggerBinding,
    BusinessComponent,
    BusinessComponentPlan,
    ComponentStateBinding,
    PageComponentComposition,
)
from app.domain.schemas.composition_contract import CompositionArtifactRef
from app.domain.schemas.content_data_plan import ContentDataPlan
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
            trigger_label=actions[action_id].name,
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
        trigger_id = trigger_by_action.get(action.id)
        if trigger_id is None:
            raise CompositionProjectionError(
                f"Action {action.id} has no trigger component binding."
            )
        input_binding = input_by_action.get(action.id)
        needs_data = action.entity_id is not None or action.kind in {
            "fill",
            "select",
            "submit",
        }
        if needs_data and input_binding is None:
            raise CompositionProjectionError(
                f"Action {action.id} has no content/data input binding."
            )
        action_transitions = tuple(
            transition
            for transition in spec.transitions
            if transition.id
            in context.tier(tier_number).references.transition_ids
            and transition.action_id == action.id
        )
        if not action_transitions:
            raise CompositionProjectionError(
                f"Action {action.id} has no canonical transition."
            )
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
            raise CompositionProjectionError(
                f"Action {action.id} lacks a journey-backed acceptance test."
            )
        projected_transitions: list[ProjectedTransition] = []
        for transition in action_transitions:
            success_evidence = _success_evidence_ids(
                context,
                transition_id=transition.id,
                to_state_id=transition.to_state_id,
                tier_number=tier_number,
            )
            if not success_evidence:
                raise CompositionProjectionError(
                    f"Transition {transition.id} lacks visible success evidence."
                )
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
        browser_assertions = tuple(
            BrowserAssertionProjection(
                acceptance_test_id=test.id,
                assertion_index=index,
                kind=assertion.kind,
                description=assertion.description,
                page_id=assertion.page_id,
                route=(
                    page_map[assertion.page_id].route
                    if assertion.page_id
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
                route=page_map[action.page_id].route,
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
    "project_interactions",
    "project_page_purpose",
]
