"""Deterministic heals for Phase 3A AI artifacts before strict validation."""
from __future__ import annotations

from app.application.composition_contract.context import CompositionContext
from app.application.composition_contract.projections import (
    project_business_component_plan,
    project_content_data_plan,
)
from app.domain.schemas.business_component_plan import (
    BusinessComponent,
    BusinessComponentPlan,
)
from app.domain.schemas.composition_contract import CompositionArtifactRef
from app.domain.schemas.content_data_plan import ContentDataPlan, ContentItem
from app.domain.schemas.page_purpose_contract import PagePurposeContract

_FORBIDDEN_MARKERS = (
    "<div",
    "<section",
    "<main",
    "classname=",
    "function ",
    "const ",
    "=>",
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


def _clean_text(value: str) -> str:
    cleaned = value
    lowered = value.casefold()
    for marker in _FORBIDDEN_MARKERS:
        if marker in lowered:
            cleaned = cleaned.replace(marker, " ").replace(
                marker.upper(), " "
            )
            # case-insensitive wipe for mixed casing
            idx = cleaned.casefold().find(marker)
            while idx >= 0:
                cleaned = cleaned[:idx] + " " + cleaned[idx + len(marker) :]
                idx = cleaned.casefold().find(marker)
    return " ".join(cleaned.split()) or "Business workflow support"


def normalize_business_component_plan(
    artifact: BusinessComponentPlan,
    *,
    context: CompositionContext,
    page_purpose: PagePurposeContract,
    page_purpose_ref: CompositionArtifactRef,
) -> BusinessComponentPlan:
    """Force Tier-1 coverage/bindings from AppSpec; keep authored voice.

    Authors routinely miss page/action coverage or invent out-of-tier IDs.
    Those fields are deterministic from page purpose and must not burn retries.
    """

    projected = project_business_component_plan(
        context,
        page_purpose=page_purpose,
        page_purpose_ref=page_purpose_ref,
    )
    authored_by_page: dict[str, BusinessComponent] = {}
    for component in artifact.components:
        for page_id in component.page_ids:
            authored_by_page.setdefault(page_id, component)

    components: list[BusinessComponent] = []
    for projected_component in projected.components:
        page_id = projected_component.page_ids[0]
        authored = authored_by_page.get(page_id)
        if authored is None:
            components.append(projected_component)
            continue
        purpose = _clean_text(authored.purpose)
        domain_language = tuple(
            _clean_text(item) for item in authored.domain_language if item.strip()
        ) or projected_component.domain_language
        # Ensure semantic overlap tokens from the projected skeleton remain.
        merged_language = list(domain_language)
        for token in projected_component.domain_language:
            if token not in merged_language:
                merged_language.append(token)
        if not any(
            token.casefold() in purpose.casefold()
            for token in projected_component.domain_language
        ):
            purpose = (
                f"{purpose} Focus on "
                f"{' and '.join(projected_component.domain_language[:2])}."
            )
        components.append(
            BusinessComponent(
                component_id=projected_component.component_id,
                name=_clean_text(authored.name)[:240]
                or projected_component.name,
                purpose=purpose[:4000],
                component_kind=authored.component_kind
                if authored.component_kind
                else projected_component.component_kind,
                domain_language=tuple(merged_language[:20]),
                page_ids=projected_component.page_ids,
                role_ids=projected_component.role_ids,
                requirement_ids=projected_component.requirement_ids,
                entity_ids=projected_component.entity_ids,
                capability_ids=projected_component.capability_ids,
                state_ids=projected_component.state_ids,
                action_ids=projected_component.action_ids,
                evidence_ids=projected_component.evidence_ids,
                content_responsibilities=(
                    tuple(
                        _clean_text(item)
                        for item in authored.content_responsibilities
                    )
                    or projected_component.content_responsibilities
                ),
                data_responsibilities=(
                    tuple(
                        _clean_text(item)
                        for item in authored.data_responsibilities
                    )
                    or projected_component.data_responsibilities
                ),
                interaction_responsibilities=(
                    tuple(
                        _clean_text(item)
                        for item in authored.interaction_responsibilities
                    )
                    or projected_component.interaction_responsibilities
                ),
                requires_component_ids=(),
                shared_across_pages=False,
            )
        )

    return BusinessComponentPlan(
        schema_version=projected.schema_version,
        contract_refs=context.refs,
        page_purpose_ref=page_purpose_ref,
        components=tuple(components),
        page_compositions=projected.page_compositions,
        action_trigger_bindings=projected.action_trigger_bindings,
        component_state_bindings=projected.component_state_bindings,
    )


def normalize_content_data_plan(
    artifact: ContentDataPlan,
    *,
    context: CompositionContext,
    page_purpose: PagePurposeContract,
    page_purpose_ref: CompositionArtifactRef,
    component_plan: BusinessComponentPlan,
    component_plan_ref: CompositionArtifactRef,
) -> ContentDataPlan:
    """Force Tier-1 content/data coverage from AppSpec; keep authored copy.

    Binding order, seed shapes, and evidence coverage are deterministic and
    should not burn Phase 3A retries.
    """

    projected = project_content_data_plan(
        context,
        page_purpose=page_purpose,
        page_purpose_ref=page_purpose_ref,
        component_plan=component_plan,
        component_plan_ref=component_plan_ref,
    )
    authored = {
        item.content_id: item for item in artifact.content_items
    }
    content_items: list[ContentItem] = []
    for item in projected.content_items:
        prior = authored.get(item.content_id)
        if prior is None:
            content_items.append(
                ContentItem(
                    content_id=item.content_id,
                    semantic_kind=item.semantic_kind,
                    value=_clean_text(item.value)[:4000],
                    provenance=item.provenance,
                    page_ids=item.page_ids,
                    component_ids=item.component_ids,
                    requirement_ids=item.requirement_ids,
                )
            )
            continue
        value = _clean_text(prior.value)
        if value.casefold().strip() in {
            "item 1",
            "item one",
            "lorem ipsum",
            "placeholder",
            "sample",
            "tbd",
            "todo",
        }:
            value = _clean_text(item.value)
        content_items.append(
            ContentItem(
                content_id=item.content_id,
                semantic_kind=prior.semantic_kind or item.semantic_kind,
                value=value[:4000],
                provenance=prior.provenance or item.provenance,
                page_ids=item.page_ids,
                component_ids=item.component_ids,
                requirement_ids=item.requirement_ids,
            )
        )

    return ContentDataPlan(
        schema_version=projected.schema_version,
        contract_refs=context.refs,
        page_purpose_ref=page_purpose_ref,
        business_component_plan_ref=component_plan_ref,
        content_items=tuple(content_items),
        data_collections=projected.data_collections,
        relationships=projected.relationships,
        state_payloads=projected.state_payloads,
        evidence_bindings=projected.evidence_bindings,
        action_input_bindings=projected.action_input_bindings,
    )


__all__ = [
    "normalize_business_component_plan",
    "normalize_content_data_plan",
]
