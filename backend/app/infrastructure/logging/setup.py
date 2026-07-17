"""Configure stdlib logging from application settings."""
from __future__ import annotations

import logging
import sys

from app.infrastructure.logging.bmv_logger import TRACE_LEVEL
from app.infrastructure.logging.access_filter import attach_uvicorn_access_filter

_LEVEL_MAP = {
    "trace": TRACE_LEVEL,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


def resolve_log_level(name: str) -> int:
    return _LEVEL_MAP.get((name or "info").strip().lower(), logging.INFO)


def configure_logging(level: str = "info") -> None:
    """Idempotent logging bootstrap — safe to call from main and scripts."""
    numeric = resolve_log_level(level)
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(numeric)
        logging.getLogger("bmv").setLevel(numeric)
        attach_uvicorn_access_filter(numeric)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(levelname)-5s | %(name)s | %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(numeric)
    logging.getLogger("bmv").setLevel(numeric)
    attach_uvicorn_access_filter(numeric)
    # Quiet noisy third-party loggers unless we're in trace/debug.
    if numeric > logging.DEBUG:
        for noisy in ("urllib3", "httpx", "httpcore", "PIL", "playwright"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
