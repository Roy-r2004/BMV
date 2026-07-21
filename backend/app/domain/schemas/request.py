from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class RequestCreateResponse(BaseModel):
    id: int
    status: str


class PreviewResponse(BaseModel):
    id: int
    business_name: str
    business_fit_score: Optional[int] = None
    concept_name: Optional[str] = None
    preview_summary: Optional[str] = None
    preview_features: list[str] = []
    ai_features: list[dict[str, Any]] = []
    visual_demo: Optional[dict[str, Any]] = None
    generated_pages: Optional[dict[str, Any]] = None
    app_spec: Optional[dict[str, Any]] = None
    status: str
    is_generating: bool = False
    industry: Optional[str] = None
    timeline: Optional[str] = None
    budget_range: Optional[str] = None
    desired_outcome: Optional[str] = None
    main_problem: Optional[str] = None
    screenshot_analysis: Optional[str] = None
    reference_analysis: Optional[str] = None
    reference_url: Optional[str] = None
    what_you_like: Optional[str] = None
    mvp_blueprint: Optional[str] = None
    technical_plan: Optional[str] = None
    # Intentionally omitted from client preview: proposal_draft (admin-only).
    build_plans: Optional[dict[str, Any]] = None
    build_requested: bool = False


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
