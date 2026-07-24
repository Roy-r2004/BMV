"""Deterministic sticky-bucket targeting for Phase 7A.

Uses SHA-256 over UTF-8(salt + ':' + request_id), taking the first 8 bytes as
a big-endian unsigned integer modulo 100. Python process hash randomization
has no effect.
"""
from __future__ import annotations

import hashlib

from app.domain.schemas.rollout import StickyBucketResult


class StickyBucketError(ValueError):
    """Malformed sticky-bucket inputs."""


def normalize_salt(salt: str) -> str:
    if not isinstance(salt, str):
        raise StickyBucketError("salt must be a UTF-8 string")
    normalized = salt.strip()
    if not normalized:
        raise StickyBucketError("salt must be non-empty after trim")
    return normalized


def normalize_request_id(request_id: int | str) -> str:
    if isinstance(request_id, bool):
        raise StickyBucketError("request_id must be an integer or digit string")
    if isinstance(request_id, int):
        if request_id < 1:
            raise StickyBucketError("request_id must be a positive integer")
        return str(request_id)
    if not isinstance(request_id, str):
        raise StickyBucketError("request_id must be an integer or digit string")
    normalized = request_id.strip()
    if not normalized:
        raise StickyBucketError("request_id must be non-empty after trim")
    # Canonical persisted request IDs are decimal integer strings; no case fold.
    if not normalized.isdigit() or int(normalized) < 1:
        raise StickyBucketError("request_id must be a positive integer string")
    return str(int(normalized))


def normalize_percent(percent: int) -> int:
    if isinstance(percent, bool) or not isinstance(percent, int):
        raise StickyBucketError("rollout_percent must be an integer 0–100")
    if percent < 0 or percent > 100:
        raise StickyBucketError("rollout_percent must be an integer 0–100")
    return percent


def compute_sticky_bucket(
    *,
    salt: str,
    request_id: int | str,
    rollout_percent: int,
) -> StickyBucketResult:
    """Return sticky bucket and percent eligibility.

    Eligibility: bucket < rollout_percent
    - 0% selects nobody
    - 100% selects everybody
    """
    norm_salt = normalize_salt(salt)
    norm_request = normalize_request_id(request_id)
    percent = normalize_percent(rollout_percent)
    material = f"{norm_salt}:{norm_request}".encode("utf-8")
    digest = hashlib.sha256(material).digest()
    first8 = digest[:8]
    value = int.from_bytes(first8, "big")
    bucket = value % 100
    return StickyBucketResult(
        salt=norm_salt,
        request_id=norm_request,
        digest_first8_hex=first8.hex(),
        bucket=bucket,
        rollout_percent=percent,
        percent_eligible=bucket < percent,
    )


# Frozen vectors for salt=2026-07-25.1 (published in architecture note + tests).
FROZEN_STICKY_VECTORS: tuple[tuple[str, str, str, int], ...] = (
    ("2026-07-25.1", "1", "f6cad4035b48872f", 23),
    ("2026-07-25.1", "42", "4ceb7e209e8260a1", 89),
    ("2026-07-25.1", "100", "54de3fb01b9a3816", 74),
    ("2026-07-25.1", "999", "1d3ecfbd7f8c1c69", 37),
    ("2026-07-25.1", "23104", "2d1c6c7da625a71e", 66),
)


__all__ = [
    "FROZEN_STICKY_VECTORS",
    "StickyBucketError",
    "compute_sticky_bucket",
    "normalize_percent",
    "normalize_request_id",
    "normalize_salt",
]
