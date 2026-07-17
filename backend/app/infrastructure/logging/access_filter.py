"""Downgrade or hide noisy uvicorn access-log lines at non-trace levels."""
from __future__ import annotations

import logging

from app.infrastructure.logging.bmv_logger import TRACE_LEVEL

# Polling / health endpoints that flood logs during long AI runs.
_QUIET_ACCESS_MARKERS = (
    "GET /api/ai/status",
    "GET /docs",
    "GET /api/requests/",
)


class UvicornAccessTraceFilter(logging.Filter):
    """Hide polling access lines unless LOG_LEVEL=trace.

    Matches uvicorn access log format:
      192.168.1.1:1234 - "GET /api/ai/status HTTP/1.1" 200 OK
    """

    def __init__(self, min_level: int = logging.INFO) -> None:
        super().__init__()
        self.min_level = min_level

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if not any(marker in msg for marker in _QUIET_ACCESS_MARKERS):
            return True
        if self.min_level > TRACE_LEVEL:
            return False
        record.levelno = TRACE_LEVEL
        record.levelname = "TRACE"
        return True


def attach_uvicorn_access_filter(min_level: int) -> None:
    for name in ("uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        # Remove duplicate filters from hot reload / re-init.
        logger.filters = [
            f for f in logger.filters if not isinstance(f, UvicornAccessTraceFilter)
        ]
        logger.addFilter(UvicornAccessTraceFilter(min_level))
