from fastapi import APIRouter

from app.application.services.ai_status import get_ai_status

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health():
    return {"status": "ok"}


@router.get("/api/ai/status")
def ai_status():
    return get_ai_status()
