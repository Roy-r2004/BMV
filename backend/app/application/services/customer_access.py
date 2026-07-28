"""Customer preview-access tokens.

These helpers gate a customer's access to their own generated preview. They are
generic to the request/preview flow and are used on the request-creation path.

They previously lived in ``app.application.expanded_preview.service``, which was
removed along with preview generator v2 — the Expanded Preview feature was built
entirely on the v2 Tier 1 -> Tier 2 orchestration. Nothing here is v2-specific.

Storage contract: ``Request.customer_access_token`` holds the SHA-256 *digest*
of the token, never the token itself. The raw token is returned to the caller
once, at issue time. Legacy rows that stored a raw token are upgraded to a
digest on first successful verification.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from sqlalchemy.orm import Session

from app.domain.models.request import Request


def customer_access_token_digest(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _looks_like_customer_access_token_digest(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return len(normalized) == 64 and all(ch in "0123456789abcdef" for ch in normalized)


def issue_customer_access_token(req: Request) -> str:
    """Mint a token, store only its digest, and return the raw token once."""

    token = secrets.token_urlsafe(32)
    req.customer_access_token = customer_access_token_digest(token)
    return token


def verify_customer_access_token(
    db: Session | None,
    *,
    req: Request,
    token: str | None,
) -> bool:
    """Constant-time check of a presented token against the stored digest.

    A legacy row holding a raw token is migrated to its digest on first match,
    so old links keep working exactly once more and are then stored hashed.
    """

    candidate = str(token or "").strip()
    stored = str(getattr(req, "customer_access_token", None) or "").strip()
    if not candidate or not stored:
        return False
    candidate_digest = customer_access_token_digest(candidate)
    if _looks_like_customer_access_token_digest(stored):
        return hmac.compare_digest(candidate_digest, stored)
    matched = hmac.compare_digest(candidate, stored)
    if matched and db is not None:
        req.customer_access_token = candidate_digest
        db.commit()
    return matched


def ensure_customer_access_token(req: Request) -> str:
    token = (getattr(req, "customer_access_token", None) or "").strip()
    if token:
        return token
    return issue_customer_access_token(req)


__all__ = [
    "customer_access_token_digest",
    "ensure_customer_access_token",
    "issue_customer_access_token",
    "verify_customer_access_token",
]
