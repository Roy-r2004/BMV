"""Thin FastAPI application factory.

All actual behavior (routes, business logic, models) lives in the layered
`app/{api,application,domain,infrastructure}` packages. This module only
wires the pieces together: DB bootstrap, CORS, router mounting, and optional
SPA static file serving.
"""
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.api_router import api_router
from app.core.config import settings
from app.domain.models import AppSpecRevision, PreviewChatMessage, Request, SolutionEditMessage, SolutionWorkspace, User, UserSession  # noqa: F401
from app.infrastructure.db.base import Base
from app.infrastructure.db.migrations import run_sqlite_migrations
from app.infrastructure.db.session import engine
from app.infrastructure.storage.file_service import ensure_upload_dir
from app.application.services.demo_seed import seed_demo_if_empty

# Never block process start — Render kills deploys that don't bind $PORT in time.
try:
    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations()
    ensure_upload_dir()
    seed_demo_if_empty()
except Exception:
    import logging

    logging.getLogger(__name__).exception(
        "DB bootstrap failed (DATABASE_URL=%s) — app will still start",
        settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else settings.DATABASE_URL,
    )

# Visibility for Render logs: codegen dies without a template / node.
print(
    f"[boot] PREVIEW_TEMPLATE_DIR={settings.PREVIEW_TEMPLATE_DIR} "
    f"exists={settings.PREVIEW_TEMPLATE_DIR.is_dir()}",
    flush=True,
)

app = FastAPI(title="BuildMyVersion AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


_static_dir = os.getenv("STATIC_DIR")
if _static_dir and Path(_static_dir).is_dir():
    _static_path = Path(_static_dir)
    _assets_dir = _static_path / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="Not found")

        if full_path in ("", "favicon.ico"):
            return FileResponse(_static_path / "index.html")

        target = _static_path / full_path
        if target.is_file():
            return FileResponse(target)

        return FileResponse(_static_path / "index.html")
