from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AdminLoginRequest(BaseModel):
    password: str


class AdminLoginResponse(BaseModel):
    success: bool
    message: str


class RequestListItem(BaseModel):
    id: int
    business_name: str
    industry: Optional[str] = None
    email: str
    whatsapp: Optional[str] = None
    status: str
    created_at: datetime
    business_fit_score: Optional[int] = None
    build_requested: bool = False

    class Config:
        from_attributes = True


class RequestDetail(BaseModel):
    id: int
    business_name: str
    industry: Optional[str] = None
    business_description: str
    target_customers: Optional[str] = None
    main_problem: Optional[str] = None
    reference_url: Optional[str] = None
    reference_file_path: Optional[str] = None
    what_you_like: Optional[str] = None
    desired_outcome: Optional[str] = None
    needs_ai: Optional[str] = None
    budget_range: Optional[str] = None
    timeline: Optional[str] = None
    email: str
    whatsapp: Optional[str] = None
    status: str
    admin_notes: Optional[str] = None
    screenshot_analysis: Optional[str] = None
    mvp_blueprint: Optional[str] = None
    visual_demo_json: Optional[str] = None
    technical_plan: Optional[str] = None
    proposal_draft: Optional[str] = None
    business_fit_score: Optional[int] = None
    concept_name: Optional[str] = None
    preview_summary: Optional[str] = None
    preview_features: Optional[str] = None
    reference_metadata: Optional[str] = None
    build_requested: bool = False
    build_requested_at: Optional[datetime] = None
    visual_demo_generated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RequestUpdate(BaseModel):
    status: Optional[str] = None
    admin_notes: Optional[str] = None
    proposal_draft: Optional[str] = None
    mvp_blueprint: Optional[str] = None
    technical_plan: Optional[str] = None
    visual_demo_json: Optional[str] = None
