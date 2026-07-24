"""Immutable v2 customer-source contract.

The v2 source snapshot contains only customer-authored input and captured
reference evidence. Inferred product decisions live in ProductStrategy and
must never be written back into this contract.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


CUSTOMER_SOURCE_SCHEMA_VERSION = "2.0"


class _FrozenSourceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class CustomerInputV2(_FrozenSourceModel):
    business_name: StrictStr = Field(min_length=1)
    industry: StrictStr | None = None
    business_description: StrictStr = Field(min_length=1)
    target_customers: StrictStr | None = None
    main_problem: StrictStr | None = None
    reference_url: StrictStr | None = None
    what_you_like: StrictStr | None = None
    desired_outcome: StrictStr | None = None
    project_type: StrictStr | None = None
    existing_product_url: StrictStr | None = None
    needs_ai: StrictStr | None = None
    budget_range: StrictStr | None = None
    timeline: StrictStr | None = None


class UploadedFileEvidenceV2(_FrozenSourceModel):
    filename: StrictStr
    available_at_capture: bool
    sha256: StrictStr | None = None
    size_bytes: StrictInt | None = Field(default=None, ge=0)


class ReferenceEvidenceV2(_FrozenSourceModel):
    reference_metadata: Any = None
    screenshot_analysis: StrictStr | None = None
    uploaded_file: UploadedFileEvidenceV2 | None = None


class CustomerSourceSnapshotV2(_FrozenSourceModel):
    source_schema_version: str = Field(
        default=CUSTOMER_SOURCE_SCHEMA_VERSION,
        pattern=r"^2\.0$",
    )
    request_id: StrictInt
    request_created_at: datetime | None = None
    customer_input: CustomerInputV2
    reference_evidence: ReferenceEvidenceV2


__all__ = [
    "CUSTOMER_SOURCE_SCHEMA_VERSION",
    "CustomerInputV2",
    "CustomerSourceSnapshotV2",
    "ReferenceEvidenceV2",
    "UploadedFileEvidenceV2",
]
