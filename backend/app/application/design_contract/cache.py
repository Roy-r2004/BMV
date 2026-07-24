"""Canonical hashes and cache keys for immutable Phase 2 artifacts."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from app.application.appspec.source import canonical_json
from app.application.design_contract.policy import DesignStagePolicy
from app.domain.schemas.design_contract import (
    DESIGN_CONTRACT_POLICY_REVISION,
    DesignContractRefs,
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def artifact_sha256(artifact: BaseModel) -> str:
    raw = canonical_json(artifact.model_dump(mode="json"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def design_cache_key(
    *,
    refs: DesignContractRefs,
    policy: DesignStagePolicy,
    schema_version: str,
    upstream_hashes: tuple[str, ...] = (),
) -> str:
    payload = {
        "stage": policy.stage,
        "schema_version": schema_version,
        "policy_revision": DESIGN_CONTRACT_POLICY_REVISION,
        "prompt_revision": policy.prompt_revision,
        "effective_model": policy.model,
        "model_family": policy.model_family,
        "max_tokens": policy.max_tokens,
        "temperature": policy.temperature,
        "use_vision": policy.use_vision,
        "source_sha256": refs.customer_source_ref.sha256,
        "product_strategy_seed_sha256": (
            refs.product_strategy_seed_ref.sha256
        ),
        "app_spec_sha256": refs.app_spec_ref.sha256,
        "tier_hashes": [ref.sha256 for ref in refs.tier_refs],
        "tier_policy_revision": (
            refs.tier_refs[0].selection_policy_revision
        ),
        "upstream_hashes": list(upstream_hashes),
    }
    raw = canonical_json(_jsonable(payload))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


__all__ = ["artifact_sha256", "design_cache_key"]
