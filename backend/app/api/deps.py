"""Shared FastAPI dependencies for the v1 API routers."""
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.application.services.user_auth import get_user_by_token
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models import User
from app.infrastructure.ai_providers.factory import get_ai_provider
from app.infrastructure.db.session import get_db
from app.infrastructure.templating.renderer import get_template_renderer

__all__ = ["get_db", "verify_admin", "get_current_user", "get_ai_provider_dep", "get_template_renderer_dep"]


def _bearer_token(authorization: str | None = Header(default=None)) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def verify_admin(
    db: Session = Depends(get_db),
    x_admin_password: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> bool:
    """Allow shared ADMIN_PASSWORD header or a logged-in is_admin user session."""
    if x_admin_password and x_admin_password == settings.ADMIN_PASSWORD:
        return True

    token = _bearer_token(authorization)
    user = get_user_by_token(db, token)
    if user and bool(getattr(user, "is_admin", False)):
        return True

    raise HTTPException(status_code=401, detail="Invalid admin credentials")


def get_current_user(
    db: Session = Depends(get_db),
    token: str | None = Depends(_bearer_token),
) -> User:
    user = get_user_by_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return user


def get_ai_provider_dep() -> AIProvider:
    return get_ai_provider()


def get_template_renderer_dep() -> TemplateRenderer:
    return get_template_renderer()
