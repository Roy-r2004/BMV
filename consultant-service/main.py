import logging
import os
import threading
from urllib.parse import parse_qs

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.database import init_db
from app.engine.api import router as engine_router
from app.engine.api.startup import engine_startup
from app.routers import discovery as discovery_router
from app.routers import requests as requests_router
from app.routers import shared as shared_router
from app.serving import key_is_right

# Nothing in this service configured logging, so the root logger sat at
# WARNING and every logger.info the pipeline writes went nowhere. That is
# most of its telemetry: which stage is running, which model answered, and
# why a stage fell back. Found on request 68 — the first end-to-end run
# through the public path — where the console showed HTTP lines and not one
# word about the run itself. The warnings did arrive, via logging's
# last-resort handler, which is why it went unnoticed: failures were
# visible and successes were not.
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
    # Downloads are fetched as blobs (the routes are auth-gated, so plain
    # link navigation can't carry the session); without this the browser
    # may not read the filename we set and falls back to a generic one.
    expose_headers=["Content-Disposition"],
)



class RenderedPictures(StaticFiles):
    """The one part of the uploads folder a browser fetches without signing in:
    the rendered screens, because an <img> tag cannot carry the session. Each
    address the server hands out carries a key, so they cannot be counted through.

    Everything else in that folder is a client's: packages stored under a
    sequential id (exports/), their documents (engagements/). Those leave only
    through the routes that check who is asking. Each screen's metadata sits
    beside its picture, so the folder alone is not enough: only pictures go out.
    """

    async def get_response(self, path, scope):
        query = parse_qs(scope.get("query_string", b"").decode())
        key, version = query.get("k", [""])[0], query.get("v", [""])[0]
        if not path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) or not key_is_right(path, key, version):
            raise StarletteHTTPException(status_code=404)
        return await super().get_response(path, scope)


images_dir = os.path.join(settings.UPLOADS_DIR, "images")
os.makedirs(images_dir, exist_ok=True)
app.mount("/uploads/images", RenderedPictures(directory=images_dir), name="uploads-images")

app.include_router(requests_router.router)
app.include_router(discovery_router.router)
app.include_router(shared_router.router)
# Importing the engine router registered its seven tables on Base, so the
# init_db() below creates them; the engine's own startup sweep is called
# AFTER init_db, never from the router (MF3.2 - a router startup handler runs
# before this function and would query engagements on a table-less database).
app.include_router(engine_router.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    _fail_stranded_requests()
    engine_startup()
    _warn_if_mail_is_not_configured()
    from app.outreach.run import start_daily

    start_daily()


MAIL_NOT_CONFIGURED = "Mail is not configured: failures, stalls and ready notices will not be emailed."
_mail_warned = False


def _warn_if_mail_is_not_configured() -> None:
    """Say so once, at startup, when mail cannot be sent. Every notice still
    reads honestly without it (nobody is told "we have been told"), but the
    team would hear of no failed run, no stall and no ready package, and the
    only sign of it would be silence."""
    global _mail_warned
    from app import mailer

    if _mail_warned or mailer.enabled():
        return
    _mail_warned = True
    logging.getLogger("consultant.startup").warning(MAIL_NOT_CONFIGURED)


def _fail_stranded_requests() -> threading.Thread | None:
    """Generation runs on a daemon thread — a process restart (a deploy, a
    crash, a uvicorn dev reload) kills it silently, stranding requests at
    is_generating=true forever. Each is stopped the way any failed run is: a
    failure record, the client's plain sentence, and one mail to the team for
    the whole sweep. The mail goes on a thread of its own, returned for a
    caller that must wait, so startup never waits on SMTP. Never raises: a
    sweep that breaks must not keep the service from starting."""
    from app.database import SessionLocal
    from app.pipeline import failure

    db = SessionLocal()
    try:
        stranded = failure.fail_interrupted_runs(db)
    except Exception:
        logging.getLogger("consultant.startup").exception("could not stop the runs a restart left generating")
        return None
    finally:
        db.close()
    if not stranded:
        return None
    thread = threading.Thread(target=failure.tell_team_of_restart, args=(stranded,), daemon=True)
    thread.start()
    return thread


@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)
