import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routers import requests as requests_router

# Nothing in this service configured logging, so the root logger sat at
# WARNING and every logger.info the pipeline writes went nowhere. That is
# most of its telemetry: which composition variant won, what each candidate
# scored, which model produced it, when the text-truth gate rejected one.
# Found on request 68 — the first end-to-end run through the public path —
# where the console showed HTTP lines and not one word about the images.
# The warnings did arrive, via logging's last-resort handler, which is why
# it went unnoticed: failures were visible and successes were not.
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title="BMV Consultant Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    # Vite hops ports (5173 → 5174 → …) when one is taken; any localhost
    # port is fine in dev, FRONTEND_ORIGIN stays the explicit prod origin.
    allow_origin_regex=r"http://localhost:\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOADS_DIR), name="uploads")

app.include_router(requests_router.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    _fail_stranded_requests()


def _fail_stranded_requests() -> None:
    """Generation runs on a daemon thread — a process restart (including
    uvicorn dev reloads) kills it silently, stranding requests at
    is_generating=true forever. Sweep them into a clean failed state at
    startup so the frontend shows a retryable failure instead of an
    eternal spinner (found in review)."""
    from app.database import SessionLocal
    from app.models import Request

    db = SessionLocal()
    try:
        stranded = db.query(Request).filter(Request.is_generating.is_(True)).all()
        for req in stranded:
            req.status = "failed"
            req.is_failed = True
            req.is_generating = False
            req.stage = "failed"
            req.stage_label = "Generation was interrupted by a service restart"
        if stranded:
            db.commit()
    finally:
        db.close()


@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)
