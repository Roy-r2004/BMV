"""Session debug NDJSON sink for Cursor debug mode (request pipeline)."""
from __future__ import annotations

import json
import time
from pathlib import Path

_DEBUG_LOG = Path("/Users/maurice/Documents/Dev/BMV/.cursor/debug-796af6.log")


def agent_dbg(
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict | None = None,
    *,
    run_id: str = "preview-run",
) -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": "796af6",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
            "fixVersion": "post-fix",
        }
        _DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _DEBUG_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion
