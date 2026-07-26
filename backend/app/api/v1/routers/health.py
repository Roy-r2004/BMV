from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.application.bootstrap.startup import (
    database_reachable,
    redact_database_url,
    verify_schema_ready,
)
from app.application.services.ai_status import get_ai_status
from app.core.config import appspec_fallback_configuration, settings
from app.infrastructure.db.session import engine

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health():
    """Backward-compatible liveness alias."""
    return {"status": "ok"}


@router.get("/api/health/live")
def health_live():
    return {"status": "ok", "live": True}


@router.get("/api/health/ready")
def health_ready():
    config_safety = appspec_fallback_configuration(settings)
    if config_safety["safety_assertion"] != "passed":
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "ready": False,
                "configuration_error": config_safety["safety_code"],
            },
        )
    if not database_reachable(engine):
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "ready": False,
                "database": "unreachable",
                "database_locator": redact_database_url(settings.DATABASE_URL),
            },
        )
    result = verify_schema_ready(engine)
    payload = {
        "status": "ready" if result.ready else "not_ready",
        "ready": result.ready,
        "schema_versions_found": result.schema_versions_found,
        "required_versions_expected": result.required_versions_expected,
        "missing_versions": result.missing_versions,
        "missing_tables": result.missing_tables,
        "database_locator": redact_database_url(settings.DATABASE_URL),
    }
    if not result.ready:
        return JSONResponse(status_code=503, content=payload)
    return payload


@router.get("/api/ai/status")
def ai_status():
    return get_ai_status()
