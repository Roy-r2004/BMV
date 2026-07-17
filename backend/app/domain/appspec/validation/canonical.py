"""AppSpec canonical JSON hashing."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.domain.schemas.app_spec import AppSpec

def canonical_app_spec_json(spec: AppSpec) -> str:
    """Serialize an AppSpec canonically for comparison, storage, and hashing."""

    return json.dumps(
        spec.model_dump(mode="json", by_alias=True, exclude_none=False),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )

def app_spec_sha256(spec: AppSpec) -> str:
    """Return the lowercase SHA-256 digest of canonical AppSpec JSON."""

    return hashlib.sha256(canonical_app_spec_json(spec).encode("utf-8")).hexdigest()
