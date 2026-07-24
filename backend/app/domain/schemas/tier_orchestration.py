"""Strict Phase 6A contracts for cumulative Tier 2 orchestration."""
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

Tier2Status = Literal[
    "tier_2_accepted",
    "tier_2_failed_serving_tier_1",
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


__all__ = [
    "TIER_2_COMPONENT_PROMPT_REVISION",
    "TIER_2_GENERATION_POLICY_REVISION",
    "TIER_2_PAGE_PROMPT_REVISION",
    "TIER_ORCHESTRATION_SCHEMA_VERSION",
    "Tier2Budget",
    "Tier2EffectiveSummary",
    "Tier2ExtensionContracts",
    "Tier2FilePreservationEntry",
    "Tier2PreservationManifest",
    "Tier2Projection",
    "Tier2Status",
    "Tier2Telemetry",
    "TierReferenceDelta",
]
