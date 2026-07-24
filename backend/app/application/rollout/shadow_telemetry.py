"""Strict shadow telemetry hashing helpers."""
from __future__ import annotations

import hashlib
import json

from app.domain.schemas.shadow_evaluation import ShadowTelemetry


def telemetry_canonical_json(telemetry: ShadowTelemetry) -> str:
    return json.dumps(telemetry.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def telemetry_sha256(telemetry: ShadowTelemetry) -> str:
    return hashlib.sha256(telemetry_canonical_json(telemetry).encode("utf-8")).hexdigest()


__all__ = ["telemetry_canonical_json", "telemetry_sha256"]
