"""Serving-health contract definitions — Phase 7A define only."""
from __future__ import annotations

from app.domain.schemas.rollout import ServingHealthCheckContract


DEFAULT_SERVING_HEALTH_CONTRACT = ServingHealthCheckContract()


__all__ = ["DEFAULT_SERVING_HEALTH_CONTRACT"]
