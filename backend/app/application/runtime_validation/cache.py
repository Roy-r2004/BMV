"""Canonical hashes and independent Phase 4 cache keys."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.application.candidate_generation.cache import canonical_sha256


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_cache_key(stage: str, payload: dict[str, Any]) -> str:
    return canonical_sha256({"stage": stage, **payload})


def artifact_sha256(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return canonical_sha256(value)


__all__ = [
    "artifact_sha256",
    "runtime_cache_key",
    "sha256_bytes",
    "sha256_file",
]
