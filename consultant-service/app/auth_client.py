"""Resolving the caller's account against the main backend.

The main app owns users and sessions (opaque DB-backed bearer tokens);
this service never sees passwords or the session table. A caller's token
is resolved by introspecting the main backend's /api/auth/me, with a
short in-memory cache so a browsing session doesn't hammer it.

Fail-closed by design: an unreachable main backend means "not signed
in" — a paid engagement must never leak because an upstream was down.
"""

import threading
import time
import urllib.request

from app.config import settings

_CACHE: dict[str, tuple[float, dict]] = {}
_LOCK = threading.Lock()
_TTL_SECONDS = 300
_CACHE_MAX = 500


def resolve_user(authorization: str | None) -> dict | None:
    """Bearer token -> {"email", "name"} or None. Cached ~5 minutes."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return None

    now = time.time()
    with _LOCK:
        hit = _CACHE.get(token)
        if hit and hit[0] > now:
            return hit[1]

    try:
        req = urllib.request.Request(
            settings.MAIN_API_URL.rstrip("/") + "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            import json

            data = json.load(resp)
        user = data.get("user") or {}
        email = user.get("email")
        if not email:
            return None
        resolved = {"email": email, "name": user.get("name")}
        with _LOCK:
            if len(_CACHE) > _CACHE_MAX:
                _CACHE.clear()
            _CACHE[token] = (now + _TTL_SECONDS, resolved)
        return resolved
    except Exception:
        return None
