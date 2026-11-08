"""The assistant on the public site."""
from __future__ import annotations

from ipaddress import ip_address

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import get_ai_provider_dep
from app.application.services.admin_ops import ai_is_allowed
from app.application.services.site_chat import rate_limit_ok, reply_site_chat
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider

router = APIRouter(tags=["site-chat"])


class SiteChatMessage(BaseModel):
    role: str
    content: str


class SiteChatRequest(BaseModel):
    messages: list[SiteChatMessage] = Field(default_factory=list, max_length=24)
    page_path: str | None = Field(default=None, max_length=200)


class SiteChatResponse(BaseModel):
    reply: str


def client_key(request: Request) -> str:
    """Who a message counts against. Behind the proxy every connection comes from
    the proxy, so the address is the last one it recorded: earlier entries in the
    header are whatever the visitor sent. The header is believed only from a peer
    on a private network, so a direct connection cannot forge it to dodge the limit."""
    peer = request.client.host if request.client else "unknown"
    try:
        behind_proxy = ip_address(peer).is_private
    except ValueError:
        behind_proxy = False
    if behind_proxy:
        last_hop = request.headers.get("x-forwarded-for", "").split(",")[-1].strip()
        if last_hop:
            return last_hop
    return peer


@router.post("/api/site-chat", response_model=SiteChatResponse)
def site_chat(
    body: SiteChatRequest,
    request: Request,
    ai: AIProvider = Depends(get_ai_provider_dep),
):
    if not settings.SITE_CHAT_ENABLED:
        raise HTTPException(status_code=503, detail="Site chat is temporarily unavailable.")

    allowed, _reason = ai_is_allowed("site_chat")
    if not allowed:
        # the reason can name internal spend, so the public gets a plain sentence
        raise HTTPException(status_code=503, detail="The assistant is paused right now.")

    if not rate_limit_ok(client_key(request)):
        raise HTTPException(status_code=429, detail="Too many messages — wait a moment and try again.")

    messages = [m.model_dump() for m in body.messages]
    reply = reply_site_chat(ai, messages=messages, page_path=body.page_path)
    return SiteChatResponse(reply=reply)
