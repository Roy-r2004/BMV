"""Structured content and entity-backed data plan for Phase 3A."""
from __future__ import annotations

from typing import Literal, Optional, Tuple, Union

from pydantic import (
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

from app.domain.schemas.composition_contract import (
    CompositionArtifactRef,
    CompositionContractRefs,
    Identifier,
    LongText,
    ShortText,
)
from app.domain.schemas.design_contract import StrictDesignModel


CONTENT_DATA_PLAN_SCHEMA_VERSION = "1.0"
DataScalar = Union[StrictBool, StrictInt, StrictFloat, StrictStr, None]
DataValue = Union[DataScalar, Tuple[DataScalar, ...]]


class ContentItem(StrictDesignModel):
    content_id: Identifier
    semantic_kind: Literal[
        "headline",
        "description",
        "instruction",
        "label",
        "empty_state",
        "success",
        "error",
        "status",
        "supporting_fact",
    ]
    value: LongText
    provenance: Literal[
        "customer_source",
        "canonical_contract",
        "strategy_derived",
        "domain_safe_seed",
    ]
    page_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=100)
    component_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=300,
    )
    requirement_ids: Tuple[Identifier, ...] = Field(
        default=(),
        max_length=100,
    )


class SeedFieldValue(StrictDesignModel):
    field_id: Identifier
    value: DataValue


class SeedRecord(StrictDesignModel):
    record_id: Identifier
    values: Tuple[SeedFieldValue, ...] = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def _unique_fields(self) -> "SeedRecord":
        ids = tuple(item.field_id for item in self.values)
        if len(ids) != len(set(ids)):
            raise ValueError("Seed records cannot repeat field IDs")
        return self


class DataCollection(StrictDesignModel):
    collection_id: Identifier
    entity_id: Identifier
    purpose: LongText
    page_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=100)
    component_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=300,
    )
    field_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=80)
    seed_records: Tuple[SeedRecord, ...] = Field(min_length=1, max_length=100)


class DataRelationship(StrictDesignModel):
    relationship_id: Identifier
    from_collection_id: Identifier
    from_field_id: Identifier
    to_collection_id: Identifier
    to_field_id: Identifier
    cardinality: Literal[
        "one_to_one",
        "one_to_many",
        "many_to_one",
        "many_to_many",
    ]


class StatePayload(StrictDesignModel):
    state_id: Identifier
    page_id: Identifier
    content_ids: Tuple[Identifier, ...] = Field(default=(), max_length=300)
    collection_ids: Tuple[Identifier, ...] = Field(default=(), max_length=100)
    component_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=300,
    )
    evidence_ids: Tuple[Identifier, ...] = Field(default=(), max_length=400)

    @model_validator(mode="after")
    def _has_payload(self) -> "StatePayload":
        if not (self.content_ids or self.collection_ids or self.evidence_ids):
            raise ValueError("State payloads cannot be empty")
        return self


class EvidenceBinding(StrictDesignModel):
    evidence_id: Identifier
    binding_kind: Literal["content", "data", "component_state"]
    content_ids: Tuple[Identifier, ...] = Field(default=(), max_length=300)
    collection_ids: Tuple[Identifier, ...] = Field(default=(), max_length=100)
    component_id: Identifier | None = None
    state_id: Identifier | None = None

    @model_validator(mode="after")
    def _binding_shape(self) -> "EvidenceBinding":
        populated = {
            "content": bool(self.content_ids),
            "data": bool(self.collection_ids),
            "component_state": bool(self.component_id and self.state_id),
        }
        if not populated[self.binding_kind]:
            raise ValueError("Evidence binding lacks its required target")
        if self.binding_kind != "content" and self.content_ids:
            raise ValueError("Only content bindings may include content IDs")
        if self.binding_kind != "data" and self.collection_ids:
            raise ValueError("Only data bindings may include collection IDs")
        if self.binding_kind != "component_state" and (
            self.component_id or self.state_id
        ):
            raise ValueError("Only component-state bindings may name a state")
        return self


class ActionInputBinding(StrictDesignModel):
    action_id: Identifier
    collection_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=100,
    )
    field_ids: Tuple[Identifier, ...] = Field(default=(), max_length=100)


class DerivedEntityField(StrictDesignModel):
    id: Identifier
    name: ShortText
    type: Literal[
        "string",
        "integer",
        "number",
        "boolean",
        "date",
        "datetime",
        "enum",
        "reference",
        "list",
    ]
    required: StrictBool = False


class DerivedEntity(StrictDesignModel):
    id: Identifier
    name: ShortText
    description: LongText
    fields: Tuple[DerivedEntityField, ...] = Field(min_length=1, max_length=80)


class CollectionProjectionEvidence(StrictDesignModel):
    """Immutable lineage for Tier 1 collection reuse/derivation decisions."""

    policy_revision: str = Field(min_length=1, max_length=64)
    decision: Literal[
        "collection_not_required",
        "collection_reused",
        "collection_derived",
        "collection_missing_required",
        "collection_ambiguous",
        "collection_missing_required_fields",
        "collection_unseedable",
        "collection_filtered_out_of_tier",
    ]
    reason: LongText
    required: StrictBool = False
    derived: StrictBool = False
    heal_applied: StrictBool = False
    entity_type: Optional[ShortText] = None
    source_references: Tuple[ShortText, ...] = Field(default=(), max_length=80)
    collection_schema_hash: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    seed_hash: Optional[str] = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    before_projection_hash: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    after_projection_hash: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    app_spec_sha256: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    tier1_contract_hash: Optional[str] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    collection_id: Optional[Identifier] = None
    minimum_seed_count: StrictInt = Field(default=0, ge=0, le=100)
    derived_entities: Tuple[DerivedEntity, ...] = Field(default=(), max_length=20)


class ContentDataPlan(StrictDesignModel):
    schema_version: str = Field(
        default=CONTENT_DATA_PLAN_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    contract_refs: CompositionContractRefs
    page_purpose_ref: CompositionArtifactRef
    business_component_plan_ref: CompositionArtifactRef
    content_items: Tuple[ContentItem, ...] = Field(
        min_length=1,
        max_length=1000,
    )
    data_collections: Tuple[DataCollection, ...] = Field(
        default=(),
        max_length=200,
    )
    relationships: Tuple[DataRelationship, ...] = Field(
        default=(),
        max_length=300,
    )
    state_payloads: Tuple[StatePayload, ...] = Field(
        min_length=1,
        max_length=300,
    )
    evidence_bindings: Tuple[EvidenceBinding, ...] = Field(
        min_length=1,
        max_length=400,
    )
    action_input_bindings: Tuple[ActionInputBinding, ...] = Field(
        default=(),
        max_length=400,
    )
    collection_projection: Optional[CollectionProjectionEvidence] = None

    @model_validator(mode="after")
    def _unique_local_keys_and_kinds(self) -> "ContentDataPlan":
        if self.page_purpose_ref.artifact_kind != "page_purpose_contract":
            raise ValueError("page_purpose_ref has the wrong artifact kind")
        if (
            self.business_component_plan_ref.artifact_kind
            != "business_component_plan"
        ):
            raise ValueError(
                "business_component_plan_ref has the wrong artifact kind"
            )
        groups = (
            (
                "content_items",
                tuple(item.content_id for item in self.content_items),
            ),
            (
                "data_collections",
                tuple(item.collection_id for item in self.data_collections),
            ),
            (
                "relationships",
                tuple(item.relationship_id for item in self.relationships),
            ),
            (
                "state_payloads",
                tuple(item.state_id for item in self.state_payloads),
            ),
            (
                "evidence_bindings",
                tuple(item.evidence_id for item in self.evidence_bindings),
            ),
            (
                "action_input_bindings",
                tuple(item.action_id for item in self.action_input_bindings),
            ),
        )
        for name, values in groups:
            if len(values) != len(set(values)):
                raise ValueError(f"{name} cannot contain duplicate keys")
        decision = (
            self.collection_projection.decision
            if self.collection_projection is not None
            else None
        )
        if not self.data_collections and decision not in {
            None,
            "collection_not_required",
        }:
            raise ValueError(
                "data_collections may be empty only when collection_not_required"
            )
        return self


__all__ = [
    "ActionInputBinding",
    "CONTENT_DATA_PLAN_SCHEMA_VERSION",
    "CollectionProjectionEvidence",
    "ContentDataPlan",
    "ContentItem",
    "DataCollection",
    "DataRelationship",
    "DataScalar",
    "DataValue",
    "DerivedEntity",
    "DerivedEntityField",
    "EvidenceBinding",
    "SeedFieldValue",
    "SeedRecord",
    "StatePayload",
]
