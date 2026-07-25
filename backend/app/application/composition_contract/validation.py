"""Deterministic validation for every Phase 3A artifact."""
from __future__ import annotations

import json
import re
from collections.abc import Iterable

from pydantic import BaseModel

from app.application.composition_contract.context import CompositionContext
from app.application.composition_contract.graph import (
    build_component_dependency_graph,
)
from app.application.composition_contract.projections import (
    project_interactions,
    project_page_purpose,
)
from app.domain.schemas.business_component_plan import BusinessComponentPlan
from app.domain.schemas.component_dependency_graph import (
    ComponentDependencyGraph,
)
from app.domain.schemas.composition_contract import (
    CompositionArtifactRef,
    CompositionValidationIssue,
    CompositionValidationReport,
)
from app.domain.schemas.content_data_plan import ContentDataPlan, DataValue
from app.domain.schemas.interaction_contract import InteractionContract
from app.domain.schemas.page_purpose_contract import PagePurposeContract


_WORD = re.compile(r"[a-z0-9]+")
_GENERIC_DOMAIN_WORDS = {
    "about",
    "action",
    "business",
    "card",
    "component",
    "content",
    "dashboard",
    "data",
    "details",
    "display",
    "feature",
    "hero",
    "information",
    "item",
    "layout",
    "list",
    "page",
    "panel",
    "section",
    "show",
    "status",
    "user",
    "view",
}
_FORBIDDEN_COMPOSITION_MARKERS = (
    "@/ui",
    "catalogue slot",
    "catalog slot",
    "skeleton_id",
    "fixed hero",
    "fixed dashboard",
    "fixed layout",
    "ops shell",
    "tailwind",
    "tsx",
    "jsx",
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
_PLACEHOLDER_VALUES = {
    "item 1",
    "item one",
    "lorem ipsum",
    "placeholder",
    "sample",
    "tbd",
    "todo",
}


def _issue(
    code: str,
    *,
    path: str = "",
    ids: Iterable[str] = (),
    message: str = "",
) -> CompositionValidationIssue:
    return CompositionValidationIssue(
        code=code,
        path=path,
        related_ids=tuple(ids),
        message=message,
    )


def _report(
    issues: list[CompositionValidationIssue],
) -> CompositionValidationReport:
    return CompositionValidationReport(
        passed=not issues,
        issues=tuple(issues),
    )


def _validate_common_refs(
    artifact: BaseModel,
    *,
    context: CompositionContext,
) -> list[CompositionValidationIssue]:
    if getattr(artifact, "contract_refs", None) != context.refs:
        return [
            _issue(
                "composition_refs_mismatch",
                path="contract_refs",
                message="Artifact references do not match the accepted inputs.",
            )
        ]
    return []


def _validate_artifact_ref(
    actual: CompositionArtifactRef,
    expected: CompositionArtifactRef,
    *,
    path: str,
) -> list[CompositionValidationIssue]:
    if actual == expected:
        return []
    return [
        _issue(
            "composition_artifact_ref_mismatch",
            path=path,
            message="Upstream composition artifact reference is not exact.",
        )
    ]


def validate_page_purpose_contract(
    artifact: PagePurposeContract,
    *,
    context: CompositionContext,
) -> CompositionValidationReport:
    issues = _validate_common_refs(artifact, context=context)
    expected = project_page_purpose(context)
    if artifact != expected:
        issues.append(
            _issue(
                "page_purpose_not_canonical_projection",
                message=(
                    "PagePurposeContract must exactly equal its deterministic "
                    "AppSpec/Tier/IA/strategy/DesignDNA projection."
                ),
            )
        )
    if len(artifact.pages) != len(context.tier_1.references.page_ids):
        issues.append(
            _issue(
                "page_purpose_cardinality",
                path="pages",
                message="Every Tier 1 page needs exactly one page contract.",
            )
        )
    return _report(issues)


def _known_sets(context: CompositionContext) -> dict[str, set[str]]:
    spec = context.app_spec
    return {
        "page_ids": {item.id for item in spec.pages},
        "role_ids": {item.id for item in spec.roles},
        "requirement_ids": {item.id for item in spec.requirements},
        "entity_ids": {item.id for item in spec.entities},
        "capability_ids": {item.id for item in spec.capabilities},
        "state_ids": {item.id for item in spec.states},
        "action_ids": {item.id for item in spec.actions},
        "evidence_ids": {item.id for item in spec.evidence},
    }


def _component_domain_tokens(
    component,
    *,
    context: CompositionContext,
) -> set[str]:
    spec = context.app_spec
    linked: list[str] = []
    collections = (
        (spec.entities, set(component.entity_ids)),
        (spec.capabilities, set(component.capability_ids)),
        (spec.actions, set(component.action_ids)),
        (spec.evidence, set(component.evidence_ids)),
        (spec.states, set(component.state_ids)),
        (spec.requirements, set(component.requirement_ids)),
    )
    for items, ids in collections:
        for item in items:
            if item.id in ids:
                linked.extend(
                    [
                        str(getattr(item, "name", "")),
                        str(getattr(item, "title", "")),
                        str(getattr(item, "description", "")),
                    ]
                )
    tokens = set(_WORD.findall(" ".join(linked).casefold()))
    return {
        token
        for token in tokens
        if len(token) >= 4 and token not in _GENERIC_DOMAIN_WORDS
    }


def validate_business_component_plan(
    artifact: BusinessComponentPlan,
    *,
    context: CompositionContext,
    page_purpose: PagePurposeContract,
    page_purpose_ref: CompositionArtifactRef,
) -> CompositionValidationReport:
    issues = _validate_common_refs(artifact, context=context)
    issues.extend(
        _validate_artifact_ref(
            artifact.page_purpose_ref,
            page_purpose_ref,
            path="page_purpose_ref",
        )
    )
    known = _known_sets(context)
    tier = context.tier_1.references
    allowed = {
        "page_ids": set(tier.page_ids),
        "role_ids": set(tier.role_ids),
        "requirement_ids": set(tier.requirement_ids),
        "entity_ids": set(tier.entity_ids),
        "capability_ids": set(tier.capability_ids),
        "state_ids": set(tier.state_ids),
        "action_ids": set(tier.action_ids),
        "evidence_ids": set(tier.evidence_ids),
    }
    components = {
        component.component_id: component
        for component in artifact.components
    }
    raw = json.dumps(artifact.model_dump(mode="json")).casefold()
    for marker in _FORBIDDEN_COMPOSITION_MARKERS:
        if marker in raw:
            issues.append(
                _issue(
                    "forbidden_component_prescription",
                    message=f"Component plan contains forbidden marker {marker!r}.",
                )
            )
    for index, component in enumerate(artifact.components):
        for field_name, permitted in allowed.items():
            values = set(getattr(component, field_name))
            if not values <= permitted or not values <= known[field_name]:
                issues.append(
                    _issue(
                        "component_reference_outside_tier",
                        path=f"components.{index}.{field_name}",
                        ids=values - permitted,
                    )
                )
        missing_dependencies = (
            set(component.requires_component_ids) - set(components)
        )
        if missing_dependencies:
            issues.append(
                _issue(
                    "component_dependency_missing",
                    path=f"components.{index}.requires_component_ids",
                    ids=missing_dependencies,
                )
            )
        canonical_tokens = _component_domain_tokens(
            component,
            context=context,
        )
        declared_tokens = set(
            _WORD.findall(
                " ".join(component.domain_language).casefold()
            )
        )
        purpose_tokens = set(_WORD.findall(component.purpose.casefold()))
        # When linked names are all generic/short, require purpose ∩ language.
        if canonical_tokens:
            semantic_overlap = (
                canonical_tokens & declared_tokens & purpose_tokens
            )
        else:
            semantic_overlap = declared_tokens & purpose_tokens
        if not semantic_overlap:
            issues.append(
                _issue(
                    "component_not_business_specific",
                    path=f"components.{index}",
                    ids=(component.component_id,),
                    message=(
                        "Domain specificity must be evident in purpose, "
                        "canonical references, and domain language."
                    ),
                )
            )

    expected_pages = tuple(page.page_id for page in page_purpose.pages)
    actual_pages = tuple(
        composition.page_id
        for composition in artifact.page_compositions
    )
    if actual_pages != expected_pages:
        issues.append(
            _issue(
                "page_composition_order_or_coverage",
                path="page_compositions",
                message="Page compositions must match Tier 1 page order.",
            )
        )
    for composition in artifact.page_compositions:
        page_components = [
            components.get(component_id)
            for component_id in composition.ordered_component_ids
        ]
        if any(component is None for component in page_components):
            issues.append(
                _issue(
                    "page_composition_component_missing",
                    path=f"page_compositions.{composition.page_id}",
                )
            )
            continue
        if any(
            composition.page_id not in component.page_ids
            for component in page_components
        ):
            issues.append(
                _issue(
                    "page_component_scope_mismatch",
                    path=f"page_compositions.{composition.page_id}",
                )
            )
        page = next(
            item
            for item in page_purpose.pages
            if item.page_id == composition.page_id
        )
        covered = {
            requirement_id
            for component in page_components
            for requirement_id in component.requirement_ids
        }
        missing = set(page.outcome_requirement_ids) - covered
        if missing:
            issues.append(
                _issue(
                    "page_outcome_not_covered",
                    path=f"page_compositions.{composition.page_id}",
                    ids=missing,
                )
            )

    action_map = {action.id: action for action in context.app_spec.actions}
    purpose_page_ids = {page.page_id for page in page_purpose.pages}
    expected_actions = tuple(
        action_id
        for action_id in context.tier_1.references.action_ids
        if action_id in action_map
        and action_map[action_id].page_id in purpose_page_ids
    )
    actual_actions = tuple(
        binding.action_id for binding in artifact.action_trigger_bindings
    )
    if actual_actions != expected_actions:
        issues.append(
            _issue(
                "action_trigger_binding_coverage",
                path="action_trigger_bindings",
                message=(
                    "Every executable Tier 1 action on an in-tier page needs "
                    "exactly one binding in canonical order."
                ),
            )
        )
    for binding in artifact.action_trigger_bindings:
        component = components.get(binding.component_id)
        action = action_map.get(binding.action_id)
        if (
            component is None
            or action is None
            or binding.action_id not in component.action_ids
            or action.page_id not in component.page_ids
        ):
            issues.append(
                _issue(
                    "invalid_action_trigger_component",
                    path=f"action_trigger_bindings.{binding.action_id}",
                    ids=(binding.action_id, binding.component_id),
                )
            )
    for binding in artifact.component_state_bindings:
        component = components.get(binding.component_id)
        if (
            component is None
            or binding.state_id not in component.state_ids
            or not set(binding.visible_evidence_ids)
            <= set(component.evidence_ids)
        ):
            issues.append(
                _issue(
                    "invalid_component_state_binding",
                    ids=(binding.component_id, binding.state_id),
                )
            )
    return _report(issues)


def _value_matches_field(value: DataValue, field) -> bool:
    if value is None:
        return not field.required
    if field.type == "boolean":
        return type(value) is bool
    if field.type == "integer":
        return type(value) is int
    if field.type == "number":
        return type(value) in {int, float}
    if field.type == "enum":
        return isinstance(value, str) and value in field.enum_values
    if field.type in {"string", "date", "datetime", "reference"}:
        return isinstance(value, str) and bool(value.strip())
    if field.type == "list":
        return isinstance(value, tuple) and bool(value)
    return False


def validate_content_data_plan(
    artifact: ContentDataPlan,
    *,
    context: CompositionContext,
    page_purpose: PagePurposeContract,
    page_purpose_ref: CompositionArtifactRef,
    component_plan: BusinessComponentPlan,
    component_plan_ref: CompositionArtifactRef,
) -> CompositionValidationReport:
    issues = _validate_common_refs(artifact, context=context)
    issues.extend(
        _validate_artifact_ref(
            artifact.page_purpose_ref,
            page_purpose_ref,
            path="page_purpose_ref",
        )
    )
    issues.extend(
        _validate_artifact_ref(
            artifact.business_component_plan_ref,
            component_plan_ref,
            path="business_component_plan_ref",
        )
    )
    pages = {page.page_id for page in page_purpose.pages}
    requirements = set(context.tier_1.references.requirement_ids)
    states = set(context.tier_1.references.state_ids)
    evidence = set(context.tier_1.references.evidence_ids)
    components = {
        item.component_id: item for item in component_plan.components
    }
    content = {item.content_id: item for item in artifact.content_items}
    collections = {
        item.collection_id: item for item in artifact.data_collections
    }
    entities = {entity.id: entity for entity in context.app_spec.entities}
    derived_entities = {
        entity.id: entity
        for entity in (
            (artifact.collection_projection.derived_entities)
            if artifact.collection_projection is not None
            else ()
        )
    }
    field_map = {
        (entity.id, field.id): field
        for entity in context.app_spec.entities
        for field in entity.fields
    }
    for entity in derived_entities.values():
        for field in entity.fields:
            field_map[(entity.id, field.id)] = field
    decision = (
        artifact.collection_projection.decision
        if artifact.collection_projection is not None
        else None
    )
    if (
        not artifact.data_collections
        and decision not in {None, "collection_not_required"}
    ):
        issues.append(
            _issue(
                decision or "collection_missing_required",
                message=(
                    artifact.collection_projection.reason
                    if artifact.collection_projection is not None
                    else "Tier 1 content projection needs an entity collection."
                ),
            )
        )
    raw = json.dumps(artifact.model_dump(mode="json")).casefold()
    for marker in _FORBIDDEN_CONTENT_MARKERS:
        if marker in raw:
            issues.append(
                _issue(
                    "generated_code_in_content_data",
                    message=f"Content/data includes forbidden marker {marker!r}.",
                )
            )
    for index, item in enumerate(artifact.content_items):
        if (
            not set(item.page_ids) <= pages
            or not set(item.component_ids) <= set(components)
            or not set(item.requirement_ids) <= requirements
        ):
            issues.append(
                _issue(
                    "content_reference_invalid",
                    path=f"content_items.{index}",
                    ids=(item.content_id,),
                )
            )
        if item.value.casefold().strip() in _PLACEHOLDER_VALUES:
            issues.append(
                _issue(
                    "placeholder_content",
                    path=f"content_items.{index}.value",
                    ids=(item.content_id,),
                )
            )
    for index, collection in enumerate(artifact.data_collections):
        entity = entities.get(collection.entity_id) or derived_entities.get(
            collection.entity_id
        )
        if (
            entity is None
            or not set(collection.page_ids) <= pages
            or not set(collection.component_ids) <= set(components)
        ):
            issues.append(
                _issue(
                    "data_collection_reference_invalid",
                    path=f"data_collections.{index}",
                    ids=(collection.collection_id,),
                )
            )
            continue
        canonical_fields = {field.id for field in entity.fields}
        if not set(collection.field_ids) <= canonical_fields:
            issues.append(
                _issue(
                    "data_collection_field_invalid",
                    path=f"data_collections.{index}.field_ids",
                    ids=set(collection.field_ids) - canonical_fields,
                )
            )
        for record in collection.seed_records:
            record_fields = tuple(item.field_id for item in record.values)
            if record_fields != collection.field_ids:
                issues.append(
                    _issue(
                        "seed_record_field_order_or_coverage",
                        path=(
                            f"data_collections.{index}."
                            f"seed_records.{record.record_id}"
                        ),
                    )
                )
                continue
            for item in record.values:
                field = field_map.get((entity.id, item.field_id))
                if field is None or not _value_matches_field(item.value, field):
                    issues.append(
                        _issue(
                            "seed_value_type_invalid",
                            ids=(collection.collection_id, item.field_id),
                        )
                    )
                if (
                    isinstance(item.value, str)
                    and item.value.casefold().strip() in _PLACEHOLDER_VALUES
                ):
                    issues.append(
                        _issue(
                            "placeholder_seed_value",
                            ids=(collection.collection_id, item.field_id),
                        )
                    )
    for relationship in artifact.relationships:
        source = collections.get(relationship.from_collection_id)
        target = collections.get(relationship.to_collection_id)
        if (
            source is None
            or target is None
            or relationship.from_field_id not in source.field_ids
            or relationship.to_field_id not in target.field_ids
        ):
            issues.append(
                _issue(
                    "relationship_reference_invalid",
                    ids=(relationship.relationship_id,),
                )
            )
    expected_states = tuple(
        state.id
        for state in context.app_spec.states
        if state.id in states and state.page_id in pages
    )
    if tuple(item.state_id for item in artifact.state_payloads) != expected_states:
        issues.append(
            _issue(
                "state_payload_coverage_or_order",
                path="state_payloads",
            )
        )
    for payload in artifact.state_payloads:
        if (
            payload.page_id not in pages
            or not set(payload.content_ids) <= set(content)
            or not set(payload.collection_ids) <= set(collections)
            or not set(payload.component_ids) <= set(components)
            or not set(payload.evidence_ids) <= evidence
        ):
            issues.append(
                _issue(
                    "state_payload_reference_invalid",
                    ids=(payload.state_id,),
                )
            )
    expected_evidence = tuple(
        item.id
        for item in context.app_spec.evidence
        if item.id in evidence and item.page_id in pages
    )
    if (
        tuple(item.evidence_id for item in artifact.evidence_bindings)
        != expected_evidence
    ):
        issues.append(
            _issue(
                "evidence_binding_coverage_or_order",
                path="evidence_bindings",
            )
        )
    component_state_keys = {
        (item.component_id, item.state_id, evidence_id)
        for item in component_plan.component_state_bindings
        for evidence_id in item.visible_evidence_ids
    }
    evidence_map = {
        item.id: item for item in context.app_spec.evidence
    }
    state_map = {item.id: item for item in context.app_spec.states}
    for binding in artifact.evidence_bindings:
        canonical_evidence = evidence_map[binding.evidence_id]
        if binding.binding_kind == "content":
            targets = [content.get(item) for item in binding.content_ids]
            valid = (
                all(item is not None for item in targets)
                and all(
                    canonical_evidence.page_id in item.page_ids
                    for item in targets
                )
            )
        elif binding.binding_kind == "data":
            targets = [
                collections.get(item) for item in binding.collection_ids
            ]
            valid = (
                all(item is not None for item in targets)
                and all(
                    canonical_evidence.page_id in item.page_ids
                    for item in targets
                )
            )
        else:
            valid = (
                binding.component_id,
                binding.state_id,
                binding.evidence_id,
            ) in component_state_keys and (
                state_map[binding.state_id].page_id
                == canonical_evidence.page_id
            )
        if not valid:
            issues.append(
                _issue(
                    "evidence_binding_target_invalid",
                    ids=(binding.evidence_id,),
                )
            )
    action_map = {action.id: action for action in context.app_spec.actions}
    entities_with_fields = {
        entity.id
        for entity in context.app_spec.entities
        if entity.fields
    }
    required_inputs = tuple(
        action.id
        for action in context.app_spec.actions
        if action.id in context.tier_1.references.action_ids
        and (
            (
                action.entity_id is not None
                and action.entity_id in entities_with_fields
            )
            or (
                action.entity_id is None
                and action.kind in {"fill", "select", "submit"}
            )
        )
    )
    if (
        tuple(item.action_id for item in artifact.action_input_bindings)
        != required_inputs
    ):
        issues.append(
            _issue(
                "action_input_binding_coverage_or_order",
                path="action_input_bindings",
            )
        )
    for binding in artifact.action_input_bindings:
        action = action_map.get(binding.action_id)
        bound = [collections.get(item) for item in binding.collection_ids]
        if action is None or any(item is None for item in bound):
            issues.append(
                _issue(
                    "action_input_binding_invalid",
                    ids=(binding.action_id,),
                )
            )
            continue
        if action.entity_id and not any(
            item.entity_id == action.entity_id for item in bound
        ):
            issues.append(
                _issue(
                    "action_input_entity_mismatch",
                    ids=(binding.action_id, action.entity_id),
                )
            )
        allowed_fields = {
            field_id for item in bound for field_id in item.field_ids
        }
        if not set(binding.field_ids) <= allowed_fields:
            issues.append(
                _issue(
                    "action_input_field_invalid",
                    ids=set(binding.field_ids) - allowed_fields,
                )
            )
    success_evidence = set(
        context.tier_1.primary_journey_proof.success_evidence_ids
    )
    bound_evidence = {
        binding.evidence_id for binding in artifact.evidence_bindings
    }
    missing_success = success_evidence - bound_evidence
    if missing_success:
        issues.append(
            _issue(
                "success_evidence_unbound",
                ids=missing_success,
            )
        )
    return _report(issues)


def validate_interaction_contract(
    artifact: InteractionContract,
    *,
    context: CompositionContext,
    page_purpose: PagePurposeContract,
    page_purpose_ref: CompositionArtifactRef,
    component_plan: BusinessComponentPlan,
    component_plan_ref: CompositionArtifactRef,
    content_data_plan: ContentDataPlan,
    content_data_plan_ref: CompositionArtifactRef,
) -> CompositionValidationReport:
    issues = _validate_common_refs(artifact, context=context)
    expected = project_interactions(
        context,
        page_purpose=page_purpose,
        page_purpose_ref=page_purpose_ref,
        component_plan=component_plan,
        component_plan_ref=component_plan_ref,
        content_data_plan=content_data_plan,
        content_data_plan_ref=content_data_plan_ref,
    )
    if artifact != expected:
        issues.append(
            _issue(
                "interaction_not_canonical_projection",
                message=(
                    "Actions, transitions, evidence, journeys, tests, and "
                    "browser assertions must be deterministic projections."
                ),
            )
        )
    return _report(issues)


def validate_component_dependency_graph(
    artifact: ComponentDependencyGraph,
    *,
    context: CompositionContext,
    page_purpose: PagePurposeContract,
    page_purpose_ref: CompositionArtifactRef,
    component_plan: BusinessComponentPlan,
    component_plan_ref: CompositionArtifactRef,
    content_data_plan: ContentDataPlan,
    content_data_plan_ref: CompositionArtifactRef,
    interaction_contract: InteractionContract,
    interaction_contract_ref: CompositionArtifactRef,
) -> CompositionValidationReport:
    issues = _validate_common_refs(artifact, context=context)
    expected = build_component_dependency_graph(
        refs=context.refs,
        page_purpose=page_purpose,
        page_purpose_ref=page_purpose_ref,
        component_plan=component_plan,
        component_plan_ref=component_plan_ref,
        content_data_plan=content_data_plan,
        content_data_plan_ref=content_data_plan_ref,
        interaction_contract=interaction_contract,
        interaction_contract_ref=interaction_contract_ref,
    )
    if artifact != expected:
        issues.append(
            _issue(
                "dependency_graph_not_canonical",
                message=(
                    "The dependency DAG and topological order must equal the "
                    "deterministic contract projection."
                ),
            )
        )
    forbidden_kinds = {
        "layout",
        "skeleton",
        "catalogue",
        "template",
    }
    if any(node.kind in forbidden_kinds for node in artifact.nodes):
        issues.append(
            _issue(
                "mandatory_template_node",
                path="nodes",
            )
        )
    return _report(issues)


__all__ = [
    "validate_business_component_plan",
    "validate_component_dependency_graph",
    "validate_content_data_plan",
    "validate_interaction_contract",
    "validate_page_purpose_contract",
]
