"""Strict Phase 6 contracts for cumulative Tier 2 and Tier 3 orchestration."""
from __future__ import annotations

from typing import Literal, Tuple

from pydantic import Field, StrictBool, StrictFloat, StrictInt, model_validator

from app.domain.schemas.business_component_plan import BusinessComponentPlan
from app.domain.schemas.component_dependency_graph import ComponentDependencyGraph
from app.domain.schemas.content_data_plan import ContentDataPlan
from app.domain.schemas.design_contract import Sha256, StrictDesignModel
from app.domain.schemas.interaction_contract import InteractionContract
from app.domain.schemas.page_purpose_contract import PagePurposeContract
from app.domain.schemas.preview_tier import TierReferenceSet


TIER_ORCHESTRATION_SCHEMA_VERSION = "1.0"
TIER_2_GENERATION_POLICY_REVISION = "2026-07-24.1"
TIER_2_COMPONENT_PROMPT_REVISION = "2026-07-24.1"
TIER_2_PAGE_PROMPT_REVISION = "2026-07-24.1"
TIER_3_GENERATION_POLICY_REVISION = "2026-07-24.1"
TIER_3_COMPONENT_PROMPT_REVISION = "2026-07-24.1"
TIER_3_PAGE_PROMPT_REVISION = "2026-07-24.1"

Tier2Status = Literal[
    "tier_2_accepted",
    "tier_2_failed_serving_tier_1",
]
Tier3Status = Literal[
    "tier_3_accepted",
    "tier_3_failed_serving_tier_2",
]


class TierReferenceDelta(StrictDesignModel):
    requirement_ids: Tuple[str, ...] = ()
    role_ids: Tuple[str, ...] = ()
    entity_ids: Tuple[str, ...] = ()
    capability_ids: Tuple[str, ...] = ()
    page_ids: Tuple[str, ...] = ()
    state_ids: Tuple[str, ...] = ()
    action_ids: Tuple[str, ...] = ()
    transition_ids: Tuple[str, ...] = ()
    evidence_ids: Tuple[str, ...] = ()
    journey_ids: Tuple[str, ...] = ()
    acceptance_test_ids: Tuple[str, ...] = ()

    @model_validator(mode="after")
    def _unique(self) -> "TierReferenceDelta":
        for name in type(self).model_fields:
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"{name} cannot contain duplicate IDs")
        return self


class Tier2Projection(StrictDesignModel):
    schema_version: str = Field(
        default=TIER_ORCHESTRATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    request_id: StrictInt = Field(ge=1)
    accepted_tier_1_revision_id: StrictInt = Field(ge=1)
    accepted_tier_1_manifest_sha256: Sha256
    accepted_tier_1_visual_summary_id: StrictInt = Field(ge=1)
    tier_1_closure_sha256: Sha256
    tier_2_closure_sha256: Sha256
    delta_sha256: Sha256
    tier_1_references: TierReferenceSet
    tier_2_references: TierReferenceSet
    delta: TierReferenceDelta
    inherited_dependency_ids: Tuple[str, ...] = ()
    lower_tier_integration_page_ids: Tuple[str, ...] = ()
    integration_justifications: Tuple[str, ...] = ()

    @model_validator(mode="after")
    def _proper_delta(self) -> "Tier2Projection":
        for name in type(self.delta).model_fields:
            lower = set(getattr(self.tier_1_references, name))
            upper = set(getattr(self.tier_2_references, name))
            delta = tuple(getattr(self.delta, name))
            if not lower.issubset(upper):
                raise ValueError(f"Tier 2 is not cumulative for {name}")
            canonical = tuple(
                item
                for item in getattr(self.tier_2_references, name)
                if item not in lower
            )
            if delta != canonical:
                raise ValueError(f"Tier 2 delta is not canonical for {name}")
        if not self.delta.page_ids and not self.delta.requirement_ids:
            raise ValueError("Tier 2 delta cannot be empty")
        if len(self.lower_tier_integration_page_ids) != len(
            self.integration_justifications
        ):
            raise ValueError("Every lower-tier integration point needs a reason")
        return self


class Tier3Projection(StrictDesignModel):
    schema_version: str = Field(
        default=TIER_ORCHESTRATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    request_id: StrictInt = Field(ge=1)
    accepted_tier_1_revision_id: StrictInt = Field(ge=1)
    accepted_tier_1_visual_summary_id: StrictInt = Field(ge=1)
    accepted_tier_2_revision_id: StrictInt = Field(ge=1)
    accepted_tier_2_manifest_sha256: Sha256
    accepted_tier_2_visual_summary_id: StrictInt = Field(ge=1)
    accepted_tier_2_effective_summary_id: StrictInt = Field(ge=1)
    accepted_tier_2_effective_summary_sha256: Sha256
    tier_1_closure_sha256: Sha256
    tier_2_closure_sha256: Sha256
    tier_3_closure_sha256: Sha256
    delta_sha256: Sha256
    tier_2_references: TierReferenceSet
    tier_3_references: TierReferenceSet
    delta: TierReferenceDelta
    inherited_dependency_ids: Tuple[str, ...] = ()
    lower_tier_integration_page_ids: Tuple[str, ...] = ()
    integration_justifications: Tuple[str, ...] = ()

    @model_validator(mode="after")
    def _proper_delta(self) -> "Tier3Projection":
        for name in type(self.delta).model_fields:
            lower = set(getattr(self.tier_2_references, name))
            upper = set(getattr(self.tier_3_references, name))
            delta = tuple(getattr(self.delta, name))
            if not lower.issubset(upper):
                raise ValueError(f"Tier 3 is not cumulative for {name}")
            canonical = tuple(
                item
                for item in getattr(self.tier_3_references, name)
                if item not in lower
            )
            if delta != canonical:
                raise ValueError(f"Tier 3 delta is not canonical for {name}")
        if not self.delta.page_ids and not self.delta.requirement_ids:
            raise ValueError("Tier 3 delta cannot be empty")
        if len(self.lower_tier_integration_page_ids) != len(
            self.integration_justifications
        ):
            raise ValueError("Every lower-tier integration point needs a reason")
        return self


class Tier2ExtensionContracts(StrictDesignModel):
    projection: Tier2Projection
    page_purpose: PagePurposeContract
    business_components: BusinessComponentPlan
    content_data: ContentDataPlan
    interactions: InteractionContract
    dependency_graph: ComponentDependencyGraph
    page_purpose_sha256: Sha256
    business_components_sha256: Sha256
    content_data_sha256: Sha256
    interactions_sha256: Sha256
    dependency_graph_sha256: Sha256


class Tier3ExtensionContracts(StrictDesignModel):
    projection: Tier3Projection
    page_purpose: PagePurposeContract
    business_components: BusinessComponentPlan
    content_data: ContentDataPlan
    interactions: InteractionContract
    dependency_graph: ComponentDependencyGraph
    page_purpose_sha256: Sha256
    business_components_sha256: Sha256
    content_data_sha256: Sha256
    interactions_sha256: Sha256
    dependency_graph_sha256: Sha256


class Tier2FilePreservationEntry(StrictDesignModel):
    path: str = Field(min_length=1, max_length=500)
    classification: Literal["immutable", "extendable"]
    original_sha256: Sha256
    final_sha256: Sha256 | None = None
    owner_ids: Tuple[str, ...] = ()
    dependency_path: Tuple[str, ...] = ()
    justification: str = Field(min_length=1, max_length=2000)
    edit_authority: Literal["none", "ai", "deterministic"]

    @model_validator(mode="after")
    def _classification_rules(self) -> "Tier2FilePreservationEntry":
        if self.classification == "immutable" and self.edit_authority != "none":
            raise ValueError("Immutable files cannot be editable")
        if self.edit_authority == "ai" and not (
            self.path.startswith("src/pages/")
            or self.path.startswith("src/components/business/")
        ):
            raise ValueError("AI edits are limited to pages/business components")
        return self


class Tier2PreservationManifest(StrictDesignModel):
    accepted_tier_1_revision_id: StrictInt = Field(ge=1)
    accepted_manifest_sha256: Sha256
    extension_contract_sha256: Sha256
    entries: Tuple[Tier2FilePreservationEntry, ...] = Field(min_length=1)
    manifest_sha256: Sha256

    @model_validator(mode="after")
    def _paths_unique(self) -> "Tier2PreservationManifest":
        paths = tuple(item.path for item in self.entries)
        if len(paths) != len(set(paths)):
            raise ValueError("Preservation manifest paths cannot repeat")
        return self


class Tier3PreservationManifest(StrictDesignModel):
    accepted_tier_1_revision_id: StrictInt = Field(ge=1)
    accepted_tier_2_revision_id: StrictInt = Field(ge=1)
    accepted_manifest_sha256: Sha256
    accepted_tier_2_effective_summary_sha256: Sha256
    extension_contract_sha256: Sha256
    entries: Tuple[Tier2FilePreservationEntry, ...] = Field(min_length=1)
    manifest_sha256: Sha256

    @model_validator(mode="after")
    def _paths_unique(self) -> "Tier3PreservationManifest":
        paths = tuple(item.path for item in self.entries)
        if len(paths) != len(set(paths)):
            raise ValueError("Preservation manifest paths cannot repeat")
        return self


class Tier2Budget(StrictDesignModel):
    max_calls: StrictInt = Field(default=10, ge=4, le=10)
    max_output_tokens: StrictInt = Field(default=118_000, ge=1)
    max_cost_usd: StrictFloat = Field(default=1.75, gt=0)
    max_wall_seconds: StrictInt = Field(default=2400, ge=1)
    mandatory_calls: StrictInt = Field(default=4, ge=4, le=4)


class Tier2Telemetry(StrictDesignModel):
    provider_call_count: StrictInt = Field(ge=0, le=10)
    output_tokens: StrictInt = Field(ge=0)
    cost_usd: StrictFloat = Field(ge=0)
    latency_ms: StrictInt = Field(ge=0)
    generation_call_count: StrictInt = Field(ge=0, le=4)
    visual_call_count: StrictInt = Field(ge=0, le=6)
    cache_hits: StrictInt = Field(ge=0)


class Tier3VisualImagePlan(StrictDesignModel):
    ordinal: StrictInt = Field(ge=0)
    page_id: str = Field(min_length=1, max_length=160)
    route: str = Field(min_length=1, max_length=500)
    viewport: Literal["mobile", "tablet", "desktop"]
    comparison_mode: Literal["candidate_only", "matched_tier_2"]
    planned_bytes: StrictInt = Field(ge=1)


class Tier3VisualGroupPlan(StrictDesignModel):
    actor: Literal["critic", "reviewer"]
    group_index: StrictInt = Field(ge=0)
    candidate_image_ordinals: Tuple[int, ...] = Field(min_length=1)
    comparison_image_count: StrictInt = Field(ge=0)
    total_provider_images: StrictInt = Field(ge=1)
    total_provider_bytes: StrictInt = Field(ge=1)


class Tier3VisualCallPlan(StrictDesignModel):
    available_page_ids: Tuple[str, ...] = Field(min_length=1)
    selected_page_ids: Tuple[str, ...] = Field(min_length=1)
    excluded_page_reasons: Tuple[str, ...] = ()
    images: Tuple[Tier3VisualImagePlan, ...] = Field(min_length=1)
    groups: Tuple[Tier3VisualGroupPlan, ...] = Field(min_length=1)
    screenshot_count: StrictInt = Field(ge=1)
    total_planned_bytes: StrictInt = Field(ge=1)
    generation_calls: Literal[2] = 2
    critic_group_calls: StrictInt = Field(ge=1)
    reviewer_group_calls: StrictInt = Field(ge=1)
    aggregation_calls: StrictInt = Field(ge=0)
    mandatory_calls: StrictInt = Field(ge=4)
    optional_call_reserve: StrictInt = Field(ge=0)
    critic_model: str = Field(min_length=1, max_length=200)
    reviewer_model: str = Field(min_length=1, max_length=200)
    critic_max_images: StrictInt = Field(ge=1)
    reviewer_max_images: StrictInt = Field(ge=1)
    critic_max_image_bytes: StrictInt = Field(ge=1)
    reviewer_max_image_bytes: StrictInt = Field(ge=1)
    grouping_sha256: Sha256

    @model_validator(mode="after")
    def _counts_match(self) -> "Tier3VisualCallPlan":
        if self.screenshot_count != len(self.images):
            raise ValueError("Screenshot count does not match image plan")
        if self.total_planned_bytes != sum(
            item.planned_bytes for item in self.images
        ):
            raise ValueError("Planned byte count does not match images")
        critic_groups = tuple(
            item for item in self.groups if item.actor == "critic"
        )
        reviewer_groups = tuple(
            item for item in self.groups if item.actor == "reviewer"
        )
        if self.critic_group_calls != len(critic_groups):
            raise ValueError("Critic group count does not match manifest")
        if self.reviewer_group_calls != len(reviewer_groups):
            raise ValueError("Reviewer group count does not match manifest")
        if tuple(item.group_index for item in critic_groups) != tuple(
            range(len(critic_groups))
        ) or tuple(item.group_index for item in reviewer_groups) != tuple(
            range(len(reviewer_groups))
        ):
            raise ValueError("Visual group indices are not canonical")
        expected = (
            self.generation_calls
            + self.critic_group_calls
            + self.reviewer_group_calls
            + self.aggregation_calls
        )
        if self.mandatory_calls != expected:
            raise ValueError("Mandatory call reservation is not exact")
        return self


class Tier3Budget(StrictDesignModel):
    max_calls: StrictInt = Field(default=12, ge=4, le=12)
    max_output_tokens: StrictInt = Field(default=168_000, ge=1)
    max_cost_usd: StrictFloat = Field(default=2.50, gt=0)
    max_wall_seconds: StrictInt = Field(default=3600, ge=1)
    mandatory_calls: StrictInt = Field(ge=4, le=12)
    optional_call_reserve: StrictInt = Field(default=0, ge=0, le=8)
    aggregate_phase6_max_calls: Literal[22] = 22
    aggregate_phase6_max_output_tokens: Literal[286000] = 286000
    aggregate_phase6_max_cost_usd: StrictFloat = 4.25
    aggregate_phase6_max_wall_seconds: Literal[6000] = 6000


class Tier3Telemetry(StrictDesignModel):
    provider_call_count: StrictInt = Field(ge=0, le=12)
    output_tokens: StrictInt = Field(ge=0)
    cost_usd: StrictFloat = Field(ge=0)
    latency_ms: StrictInt = Field(ge=0)
    generation_call_count: StrictInt = Field(ge=0, le=4)
    visual_call_count: StrictInt = Field(ge=0, le=10)
    cache_hits: StrictInt = Field(ge=0)
    phase6_provider_call_count: StrictInt = Field(ge=0, le=22)
    phase6_output_tokens: StrictInt = Field(ge=0, le=286000)
    phase6_cost_usd: StrictFloat = Field(ge=0, le=4.25)
    phase6_latency_ms: StrictInt = Field(ge=0, le=6_000_000)


class Tier2EffectiveSummary(StrictDesignModel):
    schema_version: str = Field(
        default=TIER_ORCHESTRATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    status: Tier2Status
    request_id: StrictInt = Field(ge=1)
    target_tier: Literal[2] = 2
    accepted_tier_1_revision_id: StrictInt = Field(ge=1)
    accepted_tier_1_visual_summary_id: StrictInt = Field(ge=1)
    orchestration_attempt_id: StrictInt = Field(ge=1)
    tier_2_extension_manifest_id: StrictInt | None = Field(default=None, ge=1)
    preservation_audit_id: StrictInt | None = Field(default=None, ge=1)
    tier_generation_result_id: StrictInt = Field(ge=1)
    tier_validation_result_id: StrictInt = Field(ge=1)
    tier_visual_outcome_id: StrictInt = Field(ge=1)
    derived_candidate_revision_id: StrictInt | None = Field(default=None, ge=1)
    phase4_validation_summary_id: StrictInt | None = Field(default=None, ge=1)
    phase5_visual_summary_id: StrictInt | None = Field(default=None, ge=1)
    highest_accepted_tier: Literal[1, 2]
    last_accepted_candidate_revision_id: StrictInt = Field(ge=1)
    failure_stage: str | None = Field(default=None, max_length=80)
    fallback_reason: str | None = Field(default=None, max_length=4000)
    tier_2_closure_sha256: Sha256
    delta_sha256: Sha256
    preservation_audit_sha256: Sha256 | None = None
    generation_policy_revision: str = Field(min_length=1, max_length=64)
    telemetry: Tier2Telemetry
    phase3b_reused: Literal[True] = True
    phase4_reused: StrictBool
    phase5_reused: StrictBool
    serving_pointer_changed: Literal[False] = False
    promoted: Literal[False] = False
    tier_3_invoked: Literal[False] = False

    @model_validator(mode="after")
    def _outcome_consistent(self) -> "Tier2EffectiveSummary":
        if self.status == "tier_2_accepted":
            if (
                self.highest_accepted_tier != 2
                or self.last_accepted_candidate_revision_id
                != self.derived_candidate_revision_id
                or not self.phase4_validation_summary_id
                or not self.phase5_visual_summary_id
                or self.failure_stage
                or self.fallback_reason
            ):
                raise ValueError("Accepted Tier 2 summary is incomplete")
        elif (
            self.highest_accepted_tier != 1
            or self.last_accepted_candidate_revision_id
            != self.accepted_tier_1_revision_id
            or not self.failure_stage
            or not self.fallback_reason
        ):
            raise ValueError("Failed Tier 2 must fall back to accepted Tier 1")
        return self


class Tier3EffectiveSummary(StrictDesignModel):
    schema_version: str = Field(
        default=TIER_ORCHESTRATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    status: Tier3Status
    request_id: StrictInt = Field(ge=1)
    target_tier: Literal[3] = 3
    accepted_tier_1_revision_id: StrictInt = Field(ge=1)
    accepted_tier_1_visual_summary_id: StrictInt = Field(ge=1)
    accepted_tier_2_revision_id: StrictInt = Field(ge=1)
    accepted_tier_2_visual_summary_id: StrictInt = Field(ge=1)
    accepted_tier_2_effective_summary_id: StrictInt = Field(ge=1)
    accepted_tier_2_effective_summary_sha256: Sha256
    orchestration_attempt_id: StrictInt = Field(ge=1)
    tier_3_extension_manifest_id: StrictInt | None = Field(default=None, ge=1)
    preservation_audit_id: StrictInt | None = Field(default=None, ge=1)
    tier_generation_result_id: StrictInt = Field(ge=1)
    tier_validation_result_id: StrictInt = Field(ge=1)
    tier_visual_outcome_id: StrictInt = Field(ge=1)
    derived_candidate_revision_id: StrictInt | None = Field(default=None, ge=1)
    phase4_validation_summary_id: StrictInt | None = Field(default=None, ge=1)
    phase5_visual_summary_id: StrictInt | None = Field(default=None, ge=1)
    highest_accepted_tier: Literal[2, 3]
    last_accepted_candidate_revision_id: StrictInt = Field(ge=1)
    failure_stage: str | None = Field(default=None, max_length=80)
    fallback_reason: str | None = Field(default=None, max_length=4000)
    tier_1_closure_sha256: Sha256
    tier_2_closure_sha256: Sha256
    tier_3_closure_sha256: Sha256
    delta_sha256: Sha256
    preservation_audit_sha256: Sha256 | None = None
    tier_2_generation_policy_revision: str = Field(min_length=1, max_length=64)
    generation_policy_revision: str = Field(min_length=1, max_length=64)
    visual_call_plan: Tier3VisualCallPlan
    telemetry: Tier3Telemetry
    phase3b_reused: Literal[True] = True
    phase4_reused: StrictBool
    phase5_reused: StrictBool
    serving_pointer_changed: Literal[False] = False
    promoted: Literal[False] = False
    phase_7_invoked: Literal[False] = False

    @model_validator(mode="after")
    def _outcome_consistent(self) -> "Tier3EffectiveSummary":
        if self.status == "tier_3_accepted":
            if (
                self.highest_accepted_tier != 3
                or self.last_accepted_candidate_revision_id
                != self.derived_candidate_revision_id
                or not self.phase4_validation_summary_id
                or not self.phase5_visual_summary_id
                or self.failure_stage
                or self.fallback_reason
            ):
                raise ValueError("Accepted Tier 3 summary is incomplete")
        elif (
            self.highest_accepted_tier != 2
            or self.last_accepted_candidate_revision_id
            != self.accepted_tier_2_revision_id
            or not self.failure_stage
            or not self.fallback_reason
        ):
            raise ValueError("Failed Tier 3 must fall back to accepted Tier 2")
        return self


__all__ = [
    "TIER_2_COMPONENT_PROMPT_REVISION",
    "TIER_2_GENERATION_POLICY_REVISION",
    "TIER_2_PAGE_PROMPT_REVISION",
    "TIER_3_COMPONENT_PROMPT_REVISION",
    "TIER_3_GENERATION_POLICY_REVISION",
    "TIER_3_PAGE_PROMPT_REVISION",
    "TIER_ORCHESTRATION_SCHEMA_VERSION",
    "Tier2Budget",
    "Tier2EffectiveSummary",
    "Tier2ExtensionContracts",
    "Tier2FilePreservationEntry",
    "Tier2PreservationManifest",
    "Tier2Projection",
    "Tier2Status",
    "Tier2Telemetry",
    "Tier3Budget",
    "Tier3EffectiveSummary",
    "Tier3ExtensionContracts",
    "Tier3PreservationManifest",
    "Tier3Projection",
    "Tier3Status",
    "Tier3Telemetry",
    "Tier3VisualCallPlan",
    "Tier3VisualGroupPlan",
    "Tier3VisualImagePlan",
    "TierReferenceDelta",
]
