"""Addresses for the rendered screens a browser fetches without signing in.

An <img> tag cannot carry the session, so these pictures have to be reachable
by address alone, and the address used to be a counting number. Each address
the server hands out now carries a key tied to its engagement. The routes that
hand them out already check who is asking, so holding the address means having
been let in. Nothing is stored: the key is worked out again on each request.
"""
import hashlib
import hmac
import re

from app.config import settings


def _key_for(engagement: str) -> str:
    secret = hashlib.sha256(b"uploads-images:" + settings.OPENROUTER_API_KEY.encode()).digest()
    return hmac.new(secret, engagement.encode(), hashlib.sha256).hexdigest()[:32]


def signed(address: str | None) -> str | None:
    """`/uploads/images/7/a.png?v=1` with its key added. Anything else unchanged."""
    if not address:
        return address
    found = re.match(r"/uploads/images/([^/?]+)/", address)
    if not found:
        return address
    return f"{address}{'&' if '?' in address else '?'}k={_key_for(found.group(1))}"


def key_is_right(path: str, key: str) -> bool:
    """`path` is the part after /uploads/images/: `7/a.png`, or `7\\a.png` on Windows."""
    engagement = re.split(r"[\\/]", path, maxsplit=1)[0]
    return bool(key) and hmac.compare_digest(key, _key_for(engagement))
