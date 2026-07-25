"""Pydantic schemas for commercial Expanded Preview workflow."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CustomerStatus = Literal[
    "requested",
    "under_review",
    "approved",
    "generating",
    "ready",
    "rejected",
    "failed",
]

ExpandedPreviewStatus = Literal[
    "requested",
    "approved",
    "rejected",
    "generation_started",
    "generation_completed",
    "generation_failed",
    "review_accepted",
    "review_rejected",
    "published",
]

CommercialRole = Literal[
    "expanded_preview_viewer",
    "expanded_preview_operator",
    "expanded_preview_admin",
]


class TrustedCommercialActor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str = Field(min_length=1, max_length=128)
    roles: tuple[CommercialRole, ...]
    auth_source: str


class ExpandedPreviewCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=2000)
    requested_changes: str | None = Field(default=None, max_length=4000)
    contact_preference: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, max_length=128)


class ExpandedPreviewCustomerView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expanded_preview_id: int
    request_id: int
    status: CustomerStatus
    lifecycle_status: ExpandedPreviewStatus
    reason: str | None = None
    requested_changes: str | None = None
    contact_preference: str | None = None
    created_at: datetime
    updated_at: datetime
    published_preview_url: str | None = None
    can_open_published: bool = False


class ExpandedPreviewApproveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=2000)
    internal_notes: str | None = Field(default=None, max_length=4000)


class ExpandedPreviewRejectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)
    internal_notes: str | None = Field(default=None, max_length=4000)


class ExpandedPreviewStartBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=2000)
    confirm: bool = False


class ExpandedPreviewReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["review_accepted", "review_rejected"]
    reason: str | None = Field(default=None, max_length=2000)
    internal_notes: str | None = Field(default=None, max_length=4000)
    confirm: bool = False


class ExpandedPreviewPublishBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=2000)
    confirm: bool = False


class ExpandedPreviewStatusEventView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    from_status: str | None
    to_status: str
    actor_id: str
    actor_role: str
    reason: str | None
    internal_notes: str | None = None
    created_at: datetime
    event_sha256: str


class ExpandedPreviewAdminView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    expanded_preview_uuid: str
    request_id: int
    current_status: ExpandedPreviewStatus
    customer_reason: str | None
    requested_changes: str | None
    contact_preference: str | None
    actor_id: str
    accepted_tier_1_revision_id: int | None
    tier_2_candidate_revision_id: int | None
    published_candidate_revision_id: int | None
    generation_error: str | None
    generation_started_at: datetime | None
    generation_finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    business_name: str | None = None
    customer_email: str | None = None
    tier_1_preview_url: str | None = None
    tier_2_preview_url: str | None = None
    published_preview_url: str | None = None
    phase4_status: str | None = None
    phase5_status: str | None = None
    routes: list[str] = Field(default_factory=list)
    screenshot_count: int = 0
    warning_count: int = 0
    blocking_finding_count: int = 0
    timeline: list[ExpandedPreviewStatusEventView] = Field(default_factory=list)


class ExpandedPreviewListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    request_id: int
    current_status: ExpandedPreviewStatus
    business_name: str | None
    customer_email: str | None
    created_at: datetime
    updated_at: datetime


__all__ = [
    "CommercialRole",
    "CustomerStatus",
    "ExpandedPreviewAdminView",
    "ExpandedPreviewApproveBody",
    "ExpandedPreviewCreateBody",
    "ExpandedPreviewCustomerView",
    "ExpandedPreviewListItem",
    "ExpandedPreviewPublishBody",
    "ExpandedPreviewRejectBody",
    "ExpandedPreviewReviewBody",
    "ExpandedPreviewStartBody",
    "ExpandedPreviewStatus",
    "ExpandedPreviewStatusEventView",
    "TrustedCommercialActor",
]
