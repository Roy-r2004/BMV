"""Canonical typed API contract for the generated content-data module.

Phase 3B emits ``src/generated/content-data.ts`` deterministically from the
accepted ContentDataPlan. Business components and pages consume that module
through ``@/generated/content-data``. This manifest is the single authority for
which symbols that module exports, what each symbol's TypeScript signature is,
and which ContentDataPlan collection each symbol came from.

The manifest is handed to the generation prompts and to deterministic
pre-build validation so generated code cannot invent exports.
"""
from __future__ import annotations

from typing import Annotated, Literal, Optional, Tuple

from pydantic import Field, StrictBool, StringConstraints

from app.domain.schemas.design_contract import (
    Identifier,
    Sha256,
    StrictDesignModel,
)


GENERATED_DATA_API_SCHEMA_VERSION = "1.0"
GENERATED_DATA_API_POLICY_REVISION = "2026-07-27.generated-data-api.1"
GENERATED_DATA_API_MODULE_PATH = "src/generated/content-data.ts"
GENERATED_DATA_API_MODULE_SPECIFIER = "@/generated/content-data"

TypeScriptSymbol = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z_$][A-Za-z0-9_$]*$",
    ),
]
TypeScriptType = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=512),
]
TypeScriptSignature = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1024),
]
PropertyName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
OptionalPropertyName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=128),
]


class GeneratedDataFieldSignature(StrictDesignModel):
    """One property on a generated record interface."""

    field_id: Identifier
    property_name: PropertyName
    typescript_type: TypeScriptType
    optional: StrictBool = False
    alias_of: OptionalPropertyName = ""
    reference_collection_id: Optional[Identifier] = None
    reference_field_id: Optional[Identifier] = None


class GeneratedDataCollectionApi(StrictDesignModel):
    """Canonical export surface for one seedable ContentDataPlan collection."""

    collection_id: Identifier
    entity_id: Identifier
    record_type_symbol: TypeScriptSymbol
    seed_value_symbol: TypeScriptSymbol
    accessor_symbol: TypeScriptSymbol
    seed_record_count: int = Field(ge=0, le=1000)
    field_signatures: Tuple[GeneratedDataFieldSignature, ...] = Field(
        default=(),
        max_length=400,
    )


class GeneratedDataExport(StrictDesignModel):
    """One exported symbol of the generated content-data module."""

    symbol: TypeScriptSymbol
    export_kind: Literal["type", "const", "function"]
    typescript_signature: TypeScriptSignature
    collection_id: Optional[Identifier] = None


class GeneratedDataApiManifest(StrictDesignModel):
    """Deterministic description of the generated content-data module API."""

    schema_version: str = Field(
        default=GENERATED_DATA_API_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    api_policy_revision: str = Field(min_length=1, max_length=64)
    module_path: str = Field(min_length=1, max_length=200)
    module_specifier: str = Field(min_length=1, max_length=200)
    content_data_plan_sha256: Sha256
    generated_file_sha256: str = Field(default="", pattern=r"^([a-f0-9]{64})?$")
    collections: Tuple[GeneratedDataCollectionApi, ...] = Field(
        default=(),
        max_length=200,
    )
    exports: Tuple[GeneratedDataExport, ...] = Field(
        default=(),
        max_length=1000,
    )

    def symbols(self) -> Tuple[str, ...]:
        return tuple(item.symbol for item in self.exports)


__all__ = [
    "GENERATED_DATA_API_MODULE_PATH",
    "GENERATED_DATA_API_MODULE_SPECIFIER",
    "GENERATED_DATA_API_POLICY_REVISION",
    "GENERATED_DATA_API_SCHEMA_VERSION",
    "GeneratedDataApiManifest",
    "GeneratedDataCollectionApi",
    "GeneratedDataExport",
    "GeneratedDataFieldSignature",
]
