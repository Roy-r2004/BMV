"""Public site guide chatbot."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import get_ai_provider_dep
from app.application.services.site_chat import rate_limit_ok, reply_site_chat
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider

router = APIRouter(tags=["site-chat"])


class SiteChatMessage(BaseModel):
    role: str
    content: str


class SiteChatRequest(BaseModel):
    messages: list[SiteChatMessage] = Field(default_factory=list, max_length=12)
    page_path: str | None = Field(default=None, max_length=200)


class SiteChatResponse(BaseModel):
    reply: str


@router.post("/api/site-chat", response_model=SiteChatResponse)
def site_chat(
    body: SiteChatRequest,
    request: Request,
    ai: AIProvider = Depends(get_ai_provider_dep),
):
    if not settings.SITE_CHAT_ENABLED:
        raise HTTPException(status_code=503, detail="Site chat is temporarily unavailable.")

    client = request.client.host if request.client else "unknown"
    if not rate_limit_ok(client):
        raise HTTPException(status_code=429, detail="Too many messages — wait a moment and try again.")

    messages = [m.model_dump() for m in body.messages]
    reply = reply_site_chat(ai, messages=messages, page_path=body.page_path)
    return SiteChatResponse(reply=reply)
