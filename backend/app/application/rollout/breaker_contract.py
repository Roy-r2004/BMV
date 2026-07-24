"""Circuit-breaker contracts for Phase 7A — define only, never execute."""
from __future__ import annotations

import hashlib
import json

from app.domain.schemas.rollout import CircuitBreakerPolicyContract


DEFAULT_BREAKER_POLICY = CircuitBreakerPolicyContract()


def breaker_policy_canonical_json(policy: CircuitBreakerPolicyContract) -> str:
    payload = policy.model_dump(mode="json")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def breaker_policy_sha256(policy: CircuitBreakerPolicyContract) -> str:
    return hashlib.sha256(breaker_policy_canonical_json(policy).encode("utf-8")).hexdigest()


def metric_classes_are_separate(policy: CircuitBreakerPolicyContract) -> bool:
    required = {
        "generation_failure",
        "visual_rejection",
        "operator_rejection",
        "promotion_write_failure",
        "serving_health_failure",
    }
    return required.issubset(set(policy.metric_classes))


__all__ = [
    "DEFAULT_BREAKER_POLICY",
    "breaker_policy_canonical_json",
    "breaker_policy_sha256",
    "metric_classes_are_separate",
]
