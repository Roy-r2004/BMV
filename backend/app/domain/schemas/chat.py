from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class ChatMessage(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessage]


class ChatSendRequest(BaseModel):
    message: str


class ChatSendResponse(BaseModel):
    reply: str
    changes_made: list[str] = []
    preview_updated: bool = False
    concept_name: Optional[str] = None
    preview_summary: Optional[str] = None
    preview_features: list[str] = []
    business_fit_score: Optional[int] = None
    visual_demo: Optional[dict[str, Any]] = None
