"""Shared FastAPI dependencies for the v1 API routers."""
from fastapi import Header, HTTPException

from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.infrastructure.ai_providers.factory import get_ai_provider
from app.infrastructure.db.session import get_db
from app.infrastructure.templating.renderer import get_template_renderer

__all__ = ["get_db", "verify_admin", "get_ai_provider_dep", "get_template_renderer_dep"]


def verify_admin(x_admin_password: str = Header(...)) -> bool:
    if x_admin_password != settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin password")
    return True


def get_ai_provider_dep() -> AIProvider:
    return get_ai_provider()


def get_template_renderer_dep() -> TemplateRenderer:
    return get_template_renderer()
