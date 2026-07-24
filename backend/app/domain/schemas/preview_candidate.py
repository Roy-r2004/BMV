"""Strict Phase 3B contracts for immutable Tier 1 candidate revisions."""
from __future__ import annotations

from typing import Literal, Tuple

from pydantic import Field, StrictBool, StrictFloat, StrictInt, model_validator

from app.domain.schemas.composition_contract import (
    CompositionArtifactRef,
    CompositionContractRefs,
    Identifier,
)
from app.domain.schemas.design_contract import (
    Sha256,
    StrictDesignModel,
)


CANDIDATE_GENERATOR_VERSION = "v2-phase3b"
CANDIDATE_POLICY_REVISION = "2026-07-24.1"
CANDIDATE_SCHEMA_VERSION = "1.0"

CandidateStatus = Literal[
    "candidate_generated",
    "candidate_contract_failed",
    "candidate_build_pending",
    "candidate_failed",
]
CandidateArtifactKind = Literal[
    "foundation",
    "data_exports",
    "business_components",
    "pages",
    "routes",
    "validation",
]
CandidateBatchKind = Literal["business_components", "pages"]
CandidateFileKind = Literal[
    "infrastructure",
    "runtime",
    "data",
    "contract",
    "business_component",
    "page",
    "route",
    "navigation",
]


class CandidateUpstreamRefs(StrictDesignModel):
    request_id: StrictInt = Field(ge=1)
    target_tier: Literal[1] = 1
    composition_contract_refs: CompositionContractRefs
    page_purpose_ref: CompositionArtifactRef
    business_component_plan_ref: CompositionArtifactRef
    content_data_plan_ref: CompositionArtifactRef
    interaction_contract_ref: CompositionArtifactRef
    component_dependency_graph_ref: CompositionArtifactRef

    @model_validator(mode="after")
    def _kinds_and_request(self) -> "CandidateUpstreamRefs":
        if self.request_id != self.composition_contract_refs.request_id:
            raise ValueError("Candidate and composition request IDs must match")
        expected = (
            (self.page_purpose_ref, "page_purpose_contract"),
            (self.business_component_plan_ref, "business_component_plan"),
            (self.content_data_plan_ref, "content_data_plan"),
            (self.interaction_contract_ref, "interaction_contract"),
            (
                self.component_dependency_graph_ref,
                "component_dependency_graph",
            ),
        )
        if any(ref.artifact_kind != kind for ref, kind in expected):
            raise ValueError("Candidate composition reference kinds are invalid")
        return self


class GeneratedCandidateFile(StrictDesignModel):
    path: str = Field(
        min_length=1,
        max_length=240,
        pattern=r"^src/[A-Za-z0-9_./-]+\.(?:ts|tsx|css|json)$",
    )
    file_kind: CandidateFileKind
    owner_contract_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=400,
    )
    source: str = Field(min_length=1, max_length=500_000)

    @model_validator(mode="after")
    def _safe_unique_owners(self) -> "GeneratedCandidateFile":
        parts = tuple(part for part in self.path.split("/") if part)
        if ".." in parts or "\\" in self.path:
            raise ValueError("Generated paths must be normalized and contained")
        if len(self.owner_contract_ids) != len(set(self.owner_contract_ids)):
            raise ValueError("File owner IDs cannot repeat")
        return self


class GeneratedCandidateBatch(StrictDesignModel):
    schema_version: str = Field(
        default=CANDIDATE_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    batch_kind: CandidateBatchKind
    files: Tuple[GeneratedCandidateFile, ...] = Field(
        min_length=1,
        max_length=200,
    )

    @model_validator(mode="after")
    def _unique_paths(self) -> "GeneratedCandidateBatch":
        paths = tuple(item.path for item in self.files)
        if len(paths) != len(set(paths)):
            raise ValueError("A candidate batch cannot repeat file paths")
        return self


class CandidateFileDescriptor(StrictDesignModel):
    path: str = Field(min_length=1, max_length=240)
    file_kind: CandidateFileKind
    owner_contract_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=400,
    )
    sha256: Sha256
    byte_count: StrictInt = Field(ge=1)


class CandidateArtifactManifest(StrictDesignModel):
    schema_version: str = Field(
        default=CANDIDATE_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    artifact_kind: CandidateArtifactKind
    input_hashes: Tuple[Sha256, ...] = Field(min_length=1, max_length=40)
    files: Tuple[CandidateFileDescriptor, ...] = Field(
        min_length=1,
        max_length=500,
    )

    @model_validator(mode="after")
    def _unique_paths(self) -> "CandidateArtifactManifest":
        paths = tuple(item.path for item in self.files)
        if len(paths) != len(set(paths)):
            raise ValueError("Candidate artifact file paths cannot repeat")
        return self


class CandidateValidationIssue(StrictDesignModel):
    code: str = Field(min_length=1, max_length=96)
    path: str = Field(default="", max_length=300)
    related_ids: Tuple[Identifier, ...] = Field(default=(), max_length=400)
    message: str = Field(min_length=1, max_length=4000)


class CandidateValidationReport(StrictDesignModel):
    schema_version: str = Field(
        default=CANDIDATE_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    passed: StrictBool
    checks: Tuple[str, ...] = Field(min_length=1, max_length=100)
    issues: Tuple[CandidateValidationIssue, ...] = ()
    file_manifest_sha256: Sha256
    content_data_sha256: Sha256
    route_manifest_sha256: Sha256

    @model_validator(mode="after")
    def _consistent(self) -> "CandidateValidationReport":
        if self.passed and self.issues:
            raise ValueError("A passing candidate report cannot contain issues")
        if not self.passed and not self.issues:
            raise ValueError("A failing candidate report needs issues")
        return self


class CandidateStageMetrics(StrictDesignModel):
    stage: CandidateArtifactKind
    effective_model: str = Field(min_length=1, max_length=240)
    provider: str = Field(min_length=1, max_length=80)
    model_family: str = Field(min_length=1, max_length=80)
    prompt_revision: str = Field(min_length=1, max_length=64)
    cache_hit: StrictBool
    provider_call_count: StrictInt = Field(ge=0, le=2)
    repair_call_count: StrictInt = Field(ge=0, le=1)
    repair_reason: str | None = Field(default=None, max_length=4000)
    transport_retry_count: StrictInt = Field(ge=0)
    prompt_tokens: StrictInt = Field(ge=0)
    completion_tokens: StrictInt = Field(ge=0)
    total_tokens: StrictInt = Field(ge=0)
    cost_usd: StrictFloat = Field(ge=0)
    latency_ms: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def _consistent(self) -> "CandidateStageMetrics":
        if self.total_tokens < self.prompt_tokens + self.completion_tokens:
            raise ValueError("Candidate token totals are inconsistent")
        if self.repair_call_count and not self.repair_reason:
            raise ValueError("AI repair requires a concrete reason")
        if self.provider_call_count != (
            (0 if self.cache_hit else 1) + self.repair_call_count
        ) and self.stage in {"business_components", "pages"}:
            raise ValueError("AI stage call accounting is inconsistent")
        deterministic = {"foundation", "data_exports", "routes", "validation"}
        if self.stage in deterministic and (
            self.provider_call_count
            or self.repair_call_count
            or self.transport_retry_count
            or self.total_tokens
            or self.cost_usd
        ):
            raise ValueError("Deterministic candidate stages cannot use AI")
        if self.cache_hit and (
            self.provider_call_count
            or self.repair_call_count
            or self.transport_retry_count
            or self.total_tokens
            or self.cost_usd
        ):
            raise ValueError("Candidate cache hits cannot record provider usage")
        return self


__all__ = [
    "CANDIDATE_GENERATOR_VERSION",
    "CANDIDATE_POLICY_REVISION",
    "CANDIDATE_SCHEMA_VERSION",
    "CandidateArtifactKind",
    "CandidateArtifactManifest",
    "CandidateBatchKind",
    "CandidateFileDescriptor",
    "CandidateFileKind",
    "CandidateStageMetrics",
    "CandidateStatus",
    "CandidateUpstreamRefs",
    "CandidateValidationIssue",
    "CandidateValidationReport",
    "GeneratedCandidateBatch",
    "GeneratedCandidateFile",
]
