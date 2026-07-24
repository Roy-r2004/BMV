"""Canonical Phase 3B hashes and provenance-aware cache keys."""
from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel

from app.application.appspec.source import canonical_json
from app.domain.schemas.preview_candidate import (
    CANDIDATE_POLICY_REVISION,
    CandidateUpstreamRefs,
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def canonical_sha256(value: BaseModel | dict | list | tuple) -> str:
    payload: Any = (
        value.model_dump(mode="json")
        if isinstance(value, BaseModel)
        else value
    )
    return sha256_text(canonical_json(payload))


def candidate_upstream_sha256(refs: CandidateUpstreamRefs) -> str:
    return canonical_sha256(refs)


def candidate_cache_key(
    *,
    stage: str,
    schema_version: str,
    prompt_revision: str,
    effective_model: str,
    model_family: str,
    max_tokens: int,
    temperature: float,
    dependency_lock_sha256: str,
    input_hashes: tuple[str, ...],
) -> str:
    return canonical_sha256(
        {
            "stage": stage,
            "schema_version": schema_version,
            "policy_revision": CANDIDATE_POLICY_REVISION,
            "prompt_revision": prompt_revision,
            "effective_model": effective_model,
            "model_family": model_family,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "dependency_lock_sha256": dependency_lock_sha256,
            "input_hashes": list(input_hashes),
        }
    )


__all__ = [
    "candidate_cache_key",
    "candidate_upstream_sha256",
    "canonical_sha256",
    "sha256_bytes",
    "sha256_text",
]
