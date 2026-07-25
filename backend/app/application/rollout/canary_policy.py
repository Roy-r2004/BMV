"""Trusted server-side canary policy identity (never client authority)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.core import config as app_config
from app.domain.schemas.shadow_evaluation import SHADOW_COMPARISON_POLICY_REVISION


@dataclass(frozen=True)
class CanaryPolicyIdentity:
    policy_revision: str
    rollout_salt: str
    provider_manifest_sha256: str
    generation_policy_sha256: str
    prompt_policy_sha256: str
    runtime_policy_sha256: str
    comparison_policy_revision: str
    budget_policy_sha256: str
    policy_identity_sha256: str


def _sha(material: str) -> str:
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def provider_manifest_sha256() -> str:
    """Trusted server manifest — not client-supplied models/credentials."""
    s = app_config.settings
    payload = {
        "openrouter_model": getattr(s, "OPENROUTER_MODEL", "") or "",
        "ai_provider": getattr(s, "AI_PROVIDER", "openrouter") or "openrouter",
        "canary_lane": "phase7f.live_canary",
    }
    return _sha(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def generation_policy_sha256() -> str:
    s = app_config.settings
    payload = {
        "policy_revision": s.V2_PHASE7_POLICY_REVISION,
        "preview_skip_critic": bool(getattr(s, "PREVIEW_SKIP_CRITIC", False)),
        "parallel_workers": int(getattr(s, "PREVIEW_PARALLEL_WORKERS", 4)),
    }
    return _sha(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def prompt_policy_sha256() -> str:
    s = app_config.settings
    payload = {
        "policy_revision": s.V2_PHASE7_POLICY_REVISION,
        "prompt_lane": "phase7f.v2",
    }
    return _sha(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def runtime_policy_sha256() -> str:
    s = app_config.settings
    payload = {
        "policy_revision": s.V2_PHASE7_POLICY_REVISION,
        "toolchain": "preview-template",
        "runtime_lane": "phase7f",
    }
    return _sha(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def budget_policy_sha256(
    *,
    max_calls: int,
    max_input_tokens: int,
    max_output_tokens: int,
    max_cost_usd: float,
    max_wall_seconds: int,
    max_retries: int,
    per_call_timeout_seconds: int,
) -> str:
    payload = {
        "max_calls": max_calls,
        "max_input_tokens": max_input_tokens,
        "max_output_tokens": max_output_tokens,
        "max_cost_usd": max_cost_usd,
        "max_wall_seconds": max_wall_seconds,
        "max_retries": max_retries,
        "per_call_timeout_seconds": per_call_timeout_seconds,
        "concurrent_canaries": 1,
    }
    return _sha(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def compute_policy_identity() -> CanaryPolicyIdentity:
    """Active rollout-policy identity from trusted server defaults.

    Per-approval tighter ceilings do not change policy identity; they only
    constrain that approval's execution budgets.
    """
    s = app_config.settings
    provider = provider_manifest_sha256()
    generation = generation_policy_sha256()
    prompt = prompt_policy_sha256()
    runtime = runtime_policy_sha256()
    comparison = SHADOW_COMPARISON_POLICY_REVISION
    budget = budget_policy_sha256(
        max_calls=s.V2_PHASE7_CANARY_MAX_CALLS,
        max_input_tokens=s.V2_PHASE7_CANARY_MAX_INPUT_TOKENS,
        max_output_tokens=s.V2_PHASE7_CANARY_MAX_OUTPUT_TOKENS,
        max_cost_usd=s.V2_PHASE7_CANARY_MAX_COST_USD,
        max_wall_seconds=s.V2_PHASE7_CANARY_MAX_WALL_SECONDS,
        max_retries=s.V2_PHASE7_CANARY_MAX_RETRIES,
        per_call_timeout_seconds=s.V2_PHASE7_CANARY_PER_CALL_TIMEOUT_SECONDS,
    )
    identity_payload = {
        "policy_revision": s.V2_PHASE7_POLICY_REVISION,
        "rollout_salt": s.V2_PHASE7_ROLLOUT_SALT,
        "provider_manifest_sha256": provider,
        "generation_policy_sha256": generation,
        "prompt_policy_sha256": prompt,
        "runtime_policy_sha256": runtime,
        "comparison_policy_revision": comparison,
        "budget_policy_sha256": budget,
    }
    return CanaryPolicyIdentity(
        policy_revision=s.V2_PHASE7_POLICY_REVISION,
        rollout_salt=s.V2_PHASE7_ROLLOUT_SALT,
        provider_manifest_sha256=provider,
        generation_policy_sha256=generation,
        prompt_policy_sha256=prompt,
        runtime_policy_sha256=runtime,
        comparison_policy_revision=comparison,
        budget_policy_sha256=budget,
        policy_identity_sha256=_sha(
            json.dumps(identity_payload, sort_keys=True, separators=(",", ":"))
        ),
    )


__all__ = [
    "CanaryPolicyIdentity",
    "budget_policy_sha256",
    "compute_policy_identity",
    "generation_policy_sha256",
    "prompt_policy_sha256",
    "provider_manifest_sha256",
    "runtime_policy_sha256",
]
