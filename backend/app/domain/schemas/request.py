from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict


class RequestCreateResponse(BaseModel):
    id: int
    status: str
    customer_access_token: str | None = None


CustomerLifecycleStatus = Literal[
    "queued",
    "planning",
    "generating",
    "validating",
    "reviewing",
    "ready",
    "failed",
    "expanded_preview_requested",
    "expanded_preview_in_progress",
]


class CustomerPreviewApp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str


class CustomerGeneratedPages(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_app: CustomerPreviewApp


class CustomerAIFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    name: str
    description: str | None = None
    category: str | None = None
    surface: str | None = None


class CustomerPreviewResponse(BaseModel):
    """Allowlisted customer projection; never accepts internal preview metadata."""

    model_config = ConfigDict(extra="forbid")

    id: int
    request_id: int
    business_name: str
    business_fit_score: Optional[int] = None
    concept_name: Optional[str] = None
    preview_summary: Optional[str] = None
    preview_features: list[str] = []
    ai_features: list[CustomerAIFeature] = []
    status: CustomerLifecycleStatus
    stage_label: str
    progress_percentage: int
    error_message: str | None = None
    preview_url: str | None = None
    generated_pages: CustomerGeneratedPages | None = None
    visual_demo_status: Literal["pending", "available", "failed"]
    expanded_preview_status: str | None = None
    tier2_request_state: str | None = None
    is_generating: bool = False
    industry: Optional[str] = None
    timeline: Optional[str] = None
    budget_range: Optional[str] = None
    desired_outcome: Optional[str] = None
    main_problem: Optional[str] = None
    reference_url: Optional[str] = None
    what_you_like: Optional[str] = None
    build_requested: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CustomerProgressResponse(BaseModel):
    """Allowlisted progress projection with public-only stages and messages."""

    model_config = ConfigDict(extra="forbid")

    request_id: int
    status: CustomerLifecycleStatus
    stage_label: str
    progress_percentage: int
    error_message: str | None = None
    preview_url: str | None = None
    visual_demo_status: Literal["pending", "available", "failed"]
    expanded_preview_status: str | None = None
    tier2_request_state: str | None = None
    updated_at: datetime | str | None = None
    is_generating: bool
    is_failed: bool
    # Safe compatibility aliases for existing customer clients.
    stage: CustomerLifecycleStatus
    label: str
    pct: int
    request_status: CustomerLifecycleStatus


class AdminPreviewDiagnostics(BaseModel):
    """Trusted operational projection used only behind admin authorization."""

    model_config = ConfigDict(extra="forbid")

    request_id: int
    status: str | None = None
    candidate_call_ledger: dict[str, Any] | None = None
    candidate_stage_checkpoints: list[dict[str, Any]] | dict[str, Any] | None = None
    candidate_provider_attempts: list[dict[str, Any]] = []
    failure: dict[str, Any] = {}


class AdminProgressDiagnostics(BaseModel):
    """Trusted raw progress projection used only behind admin authorization."""

    model_config = ConfigDict(extra="forbid")

    request_id: int
    request_status: str
    progress: dict[str, Any]
    preview_contract: dict[str, Any] | None = None


class BuildRequestResponse(BaseModel):
    id: int
    build_requested: bool
    status: str


class BuildRequestBody(BaseModel):
    contact_name: str
    email: str
    whatsapp: Optional[str] = None
    notes: Optional[str] = None
    package_id: Optional[str] = None
    addon_ids: Optional[list[str]] = None
    estimate_from_usd: Optional[int] = None
