"""Customer access checks for Expanded Preview endpoints."""
from __future__ import annotations

import hmac

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.application.expanded_preview.service import ensure_customer_access_token
from app.application.services.user_auth import get_user_by_token
from app.domain.models import Request


def secrets_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def resolve_customer_actor(
    db: Session,
    *,
    req: Request,
    authorization: str | None,
    x_request_access_token: str | None,
) -> str:
    """Authorize via request access token or matching signed-in customer email."""
    expected = ensure_customer_access_token(req)
    if db.is_modified(req):
        db.commit()

    token = (x_request_access_token or "").strip()
    if token and secrets_compare(token, expected):
        return f"customer:access-token:{req.id}"

    bearer = None
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            bearer = parts[1].strip()
    user = get_user_by_token(db, bearer) if bearer else None
    if user and (user.email or "").strip().lower() == (req.email or "").strip().lower():
        return f"customer:user:{user.id}"

    raise HTTPException(
        status_code=403,
        detail="Valid request access token or matching customer session required",
    )


__all__ = ["resolve_customer_actor", "secrets_compare"]
