"""Immutable Tier 1 business-component usage bindings and evidence."""
from __future__ import annotations

from typing import Literal, Tuple

from pydantic import Field, StrictBool, StrictInt, model_validator

from app.domain.schemas.composition_contract import Identifier, ShortText
from app.domain.schemas.design_contract import Sha256, StrictDesignModel


BUSINESS_COMPONENT_USAGE_SCHEMA_VERSION = "1.0"

UsageValidationResult = Literal[
    "satisfied",
    "missing_file",
    "missing_import",
    "missing_mount",
    "missing_props",
    "ambiguous_usage",
    "invalid_binding",
]

UsageMountKind = Literal[
    "direct_jsx",
    "registry_lookup",
    "composition_wrapper",
]


class RequiredBusinessComponentBinding(StrictDesignModel):
    page_id: Identifier
    business_component_id: Identifier
    component_symbol: ShortText
    component_module_path: str = Field(
        min_length=1,
        max_length=240,
        pattern=r"^src/components/business/[A-Za-z0-9_./-]+\.tsx$",
    )
    required_usage_count: StrictInt = Field(ge=1, le=20)
    required_props: Tuple[ShortText, ...] = ()
    action_ids: Tuple[Identifier, ...] = ()
    state_ids: Tuple[Identifier, ...] = ()
    evidence_ids: Tuple[Identifier, ...] = ()
    source_plan_revision: ShortText
    source_plan_hash: Sha256


class BusinessComponentRegistryEntry(StrictDesignModel):
    business_component_id: Identifier
    exported_symbol: ShortText
    file_path: str = Field(
        min_length=1,
        max_length=240,
        pattern=r"^src/components/business/[A-Za-z0-9_./-]+\.tsx$",
    )
    owning_page_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=100)
    required_props: Tuple[ShortText, ...] = ()
    source_plan_hash: Sha256
    generated_file_hash: Sha256


class BusinessComponentRegistry(StrictDesignModel):
    schema_version: str = Field(
        default=BUSINESS_COMPONENT_USAGE_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    source_plan_hash: Sha256
    entries: Tuple[BusinessComponentRegistryEntry, ...] = Field(
        min_length=1,
        max_length=300,
    )

    @model_validator(mode="after")
    def _unique_ids(self) -> "BusinessComponentRegistry":
        ids = tuple(item.business_component_id for item in self.entries)
        if len(ids) != len(set(ids)):
            raise ValueError("Registry component IDs must be unique")
        paths = tuple(item.file_path for item in self.entries)
        if len(paths) != len(set(paths)):
            raise ValueError("Registry file paths must be unique")
        return self


class BusinessComponentUsageEvidenceItem(StrictDesignModel):
    page_id: Identifier
    business_component_id: Identifier
    expected_symbol: ShortText
    expected_module: str = Field(min_length=1, max_length=240)
    actual_symbol: str = Field(default="", max_length=240)
    actual_module: str = Field(default="", max_length=240)
    component_file_exists: StrictBool
    import_found: StrictBool
    mount_found: StrictBool
    mount_kind: UsageMountKind | None = None
    usage_location: str = Field(default="", max_length=300)
    required_props_present: StrictBool
    obligations_represented: StrictBool
    result: UsageValidationResult
    repair_attempt: StrictInt = Field(ge=0, le=2)
    before_file_hash: Sha256 | None = None
    after_file_hash: Sha256 | None = None


class BusinessComponentUsageEvidence(StrictDesignModel):
    schema_version: str = Field(
        default=BUSINESS_COMPONENT_USAGE_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    request_id: StrictInt = Field(ge=1)
    candidate_revision_uuid: str = Field(default="", max_length=64)
    component_plan_hash: Sha256
    deterministic_heal_used: StrictBool = False
    ai_repair_used: StrictBool = False
    decision_hash: Sha256
    bindings: Tuple[RequiredBusinessComponentBinding, ...] = ()
    items: Tuple[BusinessComponentUsageEvidenceItem, ...] = ()


__all__ = [
    "BUSINESS_COMPONENT_USAGE_SCHEMA_VERSION",
    "BusinessComponentRegistry",
    "BusinessComponentRegistryEntry",
    "BusinessComponentUsageEvidence",
    "BusinessComponentUsageEvidenceItem",
    "RequiredBusinessComponentBinding",
    "UsageMountKind",
    "UsageValidationResult",
]
