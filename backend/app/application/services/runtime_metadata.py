"""Authenticated, non-secret production build and configuration metadata."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from app.core.config import appspec_fallback_configuration
from app.domain.schemas.generated_data_api import (
    GENERATED_DATA_API_POLICY_REVISION,
)


_PROCESS_STARTED_AT = datetime.now(timezone.utc).isoformat()
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


def _environment_value(*names: str) -> str:
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def _phase7_flags(settings: Any) -> dict[str, bool]:
    return {
        "rollout": bool(settings.V2_PHASE7_ROLLOUT_ENABLED),
        "canary": bool(settings.V2_PHASE7_LIVE_CANARY_ENABLED),
        "serving": bool(settings.V2_PHASE7_PERCENT_SERVE_ENABLED),
        "promotion": bool(settings.V2_PHASE7_PROMOTE_ENABLED),
        "shadow": bool(settings.V2_PHASE7_SHADOW_ENABLED),
        "auto_rollback": bool(settings.V2_PHASE7_AUTO_ROLLBACK_ENABLED),
    }


def _approved_configuration(settings: Any) -> dict[str, Any]:
    """Non-secret configuration an operator can verify against a release.

    The candidate-generation and design-contract entries were removed with
    preview generator v2. The phase7 rollout flags remain because the rollout
    control plane is still present and still gates the serving path.
    """

    return {
        "preview_generator": "v1",
        "appspec_fallback_enabled": bool(settings.APPSPEC_FALLBACK_ENABLED),
        "phase7": _phase7_flags(settings),
        "generated_data_api_policy_revision": (
            GENERATED_DATA_API_POLICY_REVISION
        ),
    }


def production_build_info(
    settings: Any,
    *,
    process_started_at: str = _PROCESS_STARTED_AT,
) -> dict[str, Any]:
    """Return the admin-safe metadata needed to verify a running release."""

    revision = _environment_value(
        "APP_GIT_REVISION",
        "GIT_SHA",
        "COMMIT_SHA",
        "BUILD_REVISION",
        "SOURCE_VERSION",
    )
    revision_verified = bool(_REVISION_RE.fullmatch(revision))
    image_digest = _environment_value("APP_IMAGE_DIGEST", "IMAGE_DIGEST")
    approved = _approved_configuration(settings)
    encoded = json.dumps(
        approved,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    safety = appspec_fallback_configuration(settings)
    return {
        "application_version": (
            _environment_value("APP_VERSION") or None
        ),
        "revision": revision if revision_verified else None,
        "revision_verified": revision_verified,
        "image_digest": image_digest or None,
        "build_timestamp": _environment_value("APP_BUILD_TIMESTAMP") or None,
        "process_started_at": process_started_at,
        **approved,
        "configuration_safety": {
            "appspec_fallback": safety,
            "configuration_fingerprint": hashlib.sha256(encoded).hexdigest(),
        },
        "configuration_fingerprint": hashlib.sha256(encoded).hexdigest(),
    }


__all__ = ["production_build_info"]
