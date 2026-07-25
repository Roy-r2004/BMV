"""Aggregates and mounts every v1 router — the single include point for `main.py`."""
from fastapi import APIRouter

from app.api.v1.routers import (
    admin,
    auth,
    demos,
    expanded_preview_admin,
    expanded_preview_customer,
    health,
    preview_apps,
    requests,
    rollout_diagnostics,
    site_chat,
    solution_workspaces,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(requests.router)
api_router.include_router(expanded_preview_customer.router)
api_router.include_router(expanded_preview_admin.router)
api_router.include_router(admin.router)
api_router.include_router(demos.router)
api_router.include_router(preview_apps.router)
api_router.include_router(solution_workspaces.router)
api_router.include_router(site_chat.router)
api_router.include_router(rollout_diagnostics.router)
