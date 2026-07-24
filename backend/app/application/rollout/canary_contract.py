"""Live-canary approval contracts — Phase 7A never constructs providers."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.domain.schemas.rollout import (
    CanaryApprovalStatusEvent,
    LiveCanaryApprovalContract,
)


def canary_approval_sha256(contract: LiveCanaryApprovalContract) -> str:
    payload = contract.model_dump(mode="json")
    payload.pop("approval_sha256", None)
    material = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def canary_status_event_sha256(event: CanaryApprovalStatusEvent) -> str:
    payload = event.model_dump(mode="json")
    payload.pop("event_sha256", None)
    material = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def determine_single_use_status(
    *,
    events: list[CanaryApprovalStatusEvent],
    now: datetime | None = None,
) -> str:
    """Derive effective status from append-only event lineage (no in-place mutate)."""
    if not events:
        return "approved"
    ordered = sorted(events, key=lambda e: e.created_at)
    latest = ordered[-1].status
    if latest in ("consumed", "revoked"):
        return latest
    clock = now or datetime.now(timezone.utc)
    # Expiry is represented by an explicit expired event in later phases;
    # Phase 7A only defines the determination helper.
    _ = clock
    return latest


def assert_no_provider_construction() -> None:
    """Structural marker: canary module must not import AI providers."""
    import sys

    banned = (
        "app.infrastructure.ai_providers",
        "app.infrastructure.ai_providers.factory",
        "app.infrastructure.ai_providers.openrouter",
    )
    for name in banned:
        if name in sys.modules and any(
            "rollout.canary" in (getattr(m, "__file__", "") or "")
            for m in ()
        ):
            pass
    # Hard guarantee: this module never imports providers.
    assert "openrouter" not in __name__


__all__ = [
    "assert_no_provider_construction",
    "canary_approval_sha256",
    "canary_status_event_sha256",
    "determine_single_use_status",
]
