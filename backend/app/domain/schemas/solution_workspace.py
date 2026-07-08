from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class SolutionWorkspaceResponse(BaseModel):
    solution_id: str
    overlay: dict[str, Any]
    updated_at: Optional[datetime] = None


class SolutionEditMessageOut(BaseModel):
    id: int
    role: str
    content: str
    attachment_name: Optional[str] = None
    created_at: datetime


class SolutionChatHistoryResponse(BaseModel):
    messages: list[SolutionEditMessageOut]
    overlay: dict[str, Any]


class SolutionChatSendRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class SolutionChatSendResponse(BaseModel):
    reply: str
    changes_made: list[str] = []
    overlay: dict[str, Any]
    workspace_updated: bool = False


class AIFeatureCatalogItemOut(BaseModel):
    id: str
    title: str
    description: str
    category: str
    icon: str


class AIFeatureCatalogResponse(BaseModel):
    features: list[AIFeatureCatalogItemOut]


class IntegrateFeatureResponse(BaseModel):
    reply: str
    changes_made: list[str] = []
    overlay: dict[str, Any]
    feature_id: str
    integrated: bool = True
