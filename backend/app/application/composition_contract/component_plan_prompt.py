"""Reduced prompt projection + deterministic skeleton for BCP."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from app.application.appspec.source import canonical_json
from app.application.composition_contract.context import CompositionContext
from app.application.composition_contract.projections import (
    project_business_component_plan,
)
from app.domain.schemas.business_component_plan import BusinessComponentPlan
from app.domain.schemas.composition_contract import CompositionArtifactRef
from app.domain.schemas.page_purpose_contract import PagePurposeContract


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_obj(payload: Any) -> str:
    return _sha256_text(canonical_json(payload))


@dataclass(frozen=True)
class ComponentPlanPromptProjection:
    stage_input: dict[str, Any]
    stage_input_json: str
    prompt_projection_hash: str
    source_hashes: dict[str, str]
    estimated_input_tokens: int
    input_chars: int
    omitted_sections: tuple[str, ...]
    skeleton: dict[str, Any]
    skeleton_plan: BusinessComponentPlan


def build_component_plan_skeleton(
    context: CompositionContext,
    *,
    page_purpose: PagePurposeContract,
    page_purpose_ref: CompositionArtifactRef,
) -> tuple[dict[str, Any], BusinessComponentPlan]:
    """Deterministic obligation skeleton; model may enrich, not invent scope."""

    plan = project_business_component_plan(
        context,
        page_purpose=page_purpose,
        page_purpose_ref=page_purpose_ref,
    )
    pages: list[dict[str, Any]] = []
    for page in page_purpose.pages:
        pages.append(
            {
                "page_id": page.page_id,
                "page_purpose": page.goal,
                "route": page.route,
                "journey_ids": list(page.journey_ids),
                "mandatory_action_ids": list(page.action_ids),
                "mandatory_state_ids": list(page.state_ids),
                "evidence_ids": list(page.evidence_ids),
                "requirement_ids": list(page.requirement_ids),
                "acceptance_test_ids": list(page.acceptance_test_ids),
                "navigation_visibility": page.navigation_visibility,
                "minimum_component_slots": 1,
                "content_obligations": [
                    "Make the page outcome visibly complete.",
                    "Preserve canonical action and evidence bindings.",
                ],
            }
        )
    skeleton = {
        "schema_version": plan.schema_version,
        "pages": pages,
        "required_page_ids": [page.page_id for page in page_purpose.pages],
        "required_action_ids": sorted(
            {
                action_id
                for page in page_purpose.pages
                for action_id in page.action_ids
            }
        ),
        "required_state_ids": sorted(
            {
                state_id
                for page in page_purpose.pages
                for state_id in page.state_ids
            }
        ),
        "required_evidence_ids": sorted(
            {
                evidence_id
                for page in page_purpose.pages
                for evidence_id in page.evidence_ids
            }
        ),
        "projected_component_ids": [
            item.component_id for item in plan.components
        ],
        "model_authority": {
            "may": [
                "component_type_selection",
                "layout_grouping",
                "interaction_presentation",
                "content_framing",
                "visual_hierarchy",
            ],
            "must_not": [
                "remove_mandatory_pages",
                "remove_required_actions",
                "change_ownership",
                "invent_tier_2_3_dependencies",
                "change_acceptance_test_meaning",
            ],
        },
    }
    return skeleton, plan


def project_business_component_plan_prompt(
    context: CompositionContext,
    *,
    page_purpose: PagePurposeContract,
    page_purpose_ref: CompositionArtifactRef,
) -> ComponentPlanPromptProjection:
    """Build the smallest sufficient Tier-1 contract for the BCP stage."""

    tier_pages = set(context.tier_1.references.page_ids)
    tier_actions = set(context.tier_1.references.action_ids)
    tier_states = set(context.tier_1.references.state_ids)
    tier_evidence = set(context.tier_1.references.evidence_ids)
    tier_requirements = set(context.tier_1.references.requirement_ids)
    tier_tests = set(context.tier_1.references.acceptance_test_ids)
    tier_journeys = set(context.tier_1.references.journey_ids)
    tier_capabilities = set(context.tier_1.references.capability_ids)
    tier_entities = set(context.tier_1.references.entity_ids)
    tier_roles = set(context.tier_1.references.role_ids)

    spec = context.app_spec
    actions = [
        item.model_dump(mode="json")
        for item in spec.actions
        if item.id in tier_actions
    ]
    states = [
        item.model_dump(mode="json")
        for item in spec.states
        if item.id in tier_states
    ]
    evidence = [
        item.model_dump(mode="json")
        for item in spec.evidence
        if item.id in tier_evidence
    ]
    requirements = [
        {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "priority": item.priority,
        }
        for item in spec.requirements
        if item.id in tier_requirements
    ]
    journeys = [
        {
            "id": item.id,
            "name": item.name,
            "start_page_id": item.start_page_id,
            "steps": [
                {
                    "id": step.id,
                    "action_id": step.action_id,
                    "expected_page_id": step.expected_page_id,
                }
                for step in item.steps
            ],
        }
        for item in spec.journeys
        if item.id in tier_journeys
    ]
    acceptance_tests = [
        {
            "id": item.id,
            "journey_id": item.journey_id,
            "requirement_ids": [
                req_id
                for req_id in item.requirement_ids
                if req_id in tier_requirements
            ],
        }
        for item in spec.acceptance_tests
        if item.id in tier_tests
    ]
    capabilities = [
        {
            "id": item.id,
            "name": item.name,
            "entity_ids": [
                entity_id
                for entity_id in item.entity_ids
                if entity_id in tier_entities
            ],
        }
        for item in spec.capabilities
        if item.id in tier_capabilities
    ]
    entities = [
        {"id": item.id, "name": item.name}
        for item in spec.entities
        if item.id in tier_entities
    ]
    roles = [
        {"id": item.id, "name": item.name}
        for item in spec.roles
        if item.id in tier_roles
    ]
    pages = [
        {
            "id": item.id,
            "route": item.route,
            "surface": item.surface,
            "action_ids": [
                action_id
                for action_id in item.action_ids
                if action_id in tier_actions
            ],
            "state_ids": [
                state_id
                for state_id in item.state_ids
                if state_id in tier_states
            ],
            "evidence_ids": [
                evidence_id
                for evidence_id in item.evidence_ids
                if evidence_id in tier_evidence
            ],
            "capability_ids": [
                capability_id
                for capability_id in item.capability_ids
                if capability_id in tier_capabilities
            ],
            "role_ids": [
                role_id for role_id in item.role_ids if role_id in tier_roles
            ],
        }
        for item in spec.pages
        if item.id in tier_pages
    ]

    design_dna = context.design_dna
    design_tokens = {
        "composition_hierarchy": design_dna.composition.hierarchy,
        "composition_emphasis": design_dna.composition.emphasis,
        "public_surface_density": design_dna.density.public_surface,
        "operations_surface_density": design_dna.density.operations_surface,
        "motion_character": design_dna.motion.character,
        "reduced_motion": design_dna.motion.reduced_motion,
        "avoid_list": list(design_dna.avoid_list),
        "color_tokens": [
            {
                "semantic_role": token.semantic_role,
                "direction": token.direction,
                "contrast_intent": token.contrast_intent,
            }
            for token in design_dna.color_tokens
        ],
        "typography": {
            "voice": design_dna.typography.voice,
            "display_direction": design_dna.typography.display_direction,
            "body_direction": design_dna.typography.body_direction,
        },
    }

    skeleton, skeleton_plan = build_component_plan_skeleton(
        context,
        page_purpose=page_purpose,
        page_purpose_ref=page_purpose_ref,
    )

    # Fixture-compatible reduced AppSpec slice (Tier 1 only).
    canonical_slice = {
        "pages": pages,
        "roles": roles,
        "entities": entities,
        "capabilities": capabilities,
        "actions": actions,
        "states": states,
        "evidence": evidence,
        "requirements": requirements,
        "journeys": journeys,
        "acceptance_tests": acceptance_tests,
    }

    omitted = (
        "full_raw_app_spec",
        "tier_2_pages",
        "tier_3_pages",
        "unrelated_admin_capabilities",
        "product_strategy_narrative",
        "full_information_architecture",
        "full_design_dna_document",
        "prior_model_transcripts",
        "visual_evaluation_evidence",
        "duplicate_customer_source_blob",
    )

    source_hashes = {
        "tier_1": _sha256_obj(context.tier_1.model_dump(mode="json")),
        "page_purpose_contract": _sha256_obj(
            page_purpose.model_dump(mode="json")
        ),
        "page_purpose_ref": page_purpose_ref.sha256,
        "design_dna": _sha256_obj(design_dna.model_dump(mode="json")),
        "app_spec_revision": context.refs.design_contract_refs.app_spec_ref.sha256,
    }

    stage_input = {
        "composition_contract_refs": context.refs.model_dump(mode="json"),
        "page_purpose_contract": page_purpose.model_dump(mode="json"),
        "page_purpose_ref": page_purpose_ref.model_dump(mode="json"),
        "tier_1_page_ids": sorted(tier_pages),
        "canonical_app_spec": canonical_slice,
        "design_dna_tokens": design_tokens,
        "component_plan_skeleton": skeleton,
        "prompt_projection_meta": {
            "source_artifact_hashes": source_hashes,
            "omitted_sections": list(omitted),
            "includes_tier_2_3_pages": False,
        },
    }
    stage_input_json = canonical_json(stage_input)
    return ComponentPlanPromptProjection(
        stage_input=stage_input,
        stage_input_json=stage_input_json,
        prompt_projection_hash=_sha256_text(stage_input_json),
        source_hashes=source_hashes,
        estimated_input_tokens=estimate_tokens(stage_input_json),
        input_chars=len(stage_input_json),
        omitted_sections=omitted,
        skeleton=skeleton,
        skeleton_plan=skeleton_plan,
    )


def repair_prompt_values(
    projection: ComponentPlanPromptProjection,
    *,
    prior_reason: str,
    missing_page_ids: tuple[str, ...],
) -> dict[str, Any]:
    """Smaller recovery payload: skeleton + only missing/invalid sections."""

    pages = [
        page
        for page in projection.stage_input["page_purpose_contract"]["pages"]
        if not missing_page_ids or page["page_id"] in missing_page_ids
    ]
    skeleton_pages = [
        page
        for page in projection.skeleton["pages"]
        if not missing_page_ids or page["page_id"] in missing_page_ids
    ]
    repair_input = {
        "composition_contract_refs": projection.stage_input[
            "composition_contract_refs"
        ],
        "page_purpose_ref": projection.stage_input["page_purpose_ref"],
        "page_purpose_contract": {
            **projection.stage_input["page_purpose_contract"],
            "pages": pages,
        },
        "component_plan_skeleton": {
            **projection.skeleton,
            "pages": skeleton_pages,
        },
        "canonical_app_spec": projection.stage_input["canonical_app_spec"],
        "design_dna_tokens": projection.stage_input["design_dna_tokens"],
        "repair_scope": {
            "mode": "missing_or_invalid_sections_only",
            "missing_page_ids": list(missing_page_ids),
            "prior_failure_kind": prior_reason[:500],
        },
        "prompt_projection_meta": {
            **projection.stage_input["prompt_projection_meta"],
            "recovery_attempt": True,
        },
    }
    return {
        "stage_input_json": canonical_json(repair_input),
        "repair_input": repair_input,
    }


__all__ = [
    "ComponentPlanPromptProjection",
    "build_component_plan_skeleton",
    "estimate_tokens",
    "project_business_component_plan_prompt",
    "repair_prompt_values",
]
