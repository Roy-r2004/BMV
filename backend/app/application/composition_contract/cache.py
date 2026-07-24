"""Canonical hashes and provenance-aware Phase 3A cache keys."""
from __future__ import annotations

import hashlib

from pydantic import BaseModel

from app.application.appspec.source import canonical_json
from app.application.composition_contract.policy import (
    CompositionStagePolicy,
)
from app.domain.schemas.composition_contract import (
    COMPOSITION_CONTRACT_POLICY_REVISION,
    CompositionContractRefs,
)


def composition_artifact_sha256(artifact: BaseModel) -> str:
    raw = canonical_json(artifact.model_dump(mode="json"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def composition_cache_key(
    *,
    refs: CompositionContractRefs,
    policy: CompositionStagePolicy,
    schema_version: str,
    upstream_hashes: tuple[str, ...] = (),
) -> str:
    payload = {
        "stage": policy.stage,
        "target_tier": refs.target_tier,
        "schema_version": schema_version,
        "policy_revision": COMPOSITION_CONTRACT_POLICY_REVISION,
        "prompt_revision": policy.prompt_revision,
        "effective_model": policy.model,
        "model_family": policy.model_family,
        "max_tokens": policy.max_tokens,
        "temperature": policy.temperature,
        "source_sha256": (
            refs.design_contract_refs.customer_source_ref.sha256
        ),
        "product_strategy_seed_sha256": (
            refs.design_contract_refs.product_strategy_seed_ref.sha256
        ),
        "app_spec_sha256": refs.design_contract_refs.app_spec_ref.sha256,
        "tier_hashes": [
            ref.sha256 for ref in refs.design_contract_refs.tier_refs
        ],
        "tier_policy_revision": (
            refs.design_contract_refs.tier_refs[
                0
            ].selection_policy_revision
        ),
        "product_strategy_v2": (
            refs.product_strategy_v2_ref.model_dump(mode="json")
        ),
        "information_architecture": (
            refs.information_architecture_ref.model_dump(mode="json")
        ),
        "design_dna": refs.design_dna_ref.model_dump(mode="json"),
        "upstream_hashes": list(upstream_hashes),
    }
    raw = canonical_json(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


__all__ = [
    "composition_artifact_sha256",
    "composition_cache_key",
]
