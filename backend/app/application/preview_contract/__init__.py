"""Contract-only preview generator v2 application services."""

from __future__ import annotations

from typing import Any

from app.application.preview_contract.product_strategy import (
    project_product_strategy,
)
from app.application.preview_contract.tier_validation import (
    validate_preview_tiers,
)
from app.application.preview_contract.tiers import (
    TierBuildError,
    TierContractContext,
    build_preview_tiers,
    expand_tier_graph,
    select_primary_journey_proof,
)

# Do NOT import .service at module import time — it depends on appspec.generation,
# and appspec.generation may import tiers for the Tier-1 primary-journey gate.

__all__ = [
    "V2_APPSPEC_CONTRACT_READY",
    "V2_CONTRACT_READY",
    "TierBuildError",
    "TierContractContext",
    "build_v2_app_spec_contract",
    "build_preview_tiers",
    "expand_tier_graph",
    "project_product_strategy",
    "select_primary_journey_proof",
    "validate_preview_tiers",
]


def __getattr__(name: str) -> Any:
    if name in {
        "V2_APPSPEC_CONTRACT_READY",
        "V2_CONTRACT_READY",
        "build_v2_app_spec_contract",
    }:
        from app.application.preview_contract import service as _service

        return getattr(_service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
