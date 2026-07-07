from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DemoListItem(BaseModel):
    id: int
    business_name: str
    concept_name: str
    industry: Optional[str] = None
    business_fit_score: Optional[int] = None
    preview_summary: Optional[str] = None
    preview_features: list[str] = []
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    reference_url: Optional[str] = None
    created_at: datetime


class DemoListResponse(BaseModel):
    demos: list[DemoListItem]
