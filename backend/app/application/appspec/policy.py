"""AppSpec generation policies and deterministic model-family separation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.core.config import settings


class ModelFamilyPolicyError(ValueError):
    """A strict AppSpec model assignment is unknown or self-reviewing."""


@dataclass(frozen=True)
class ModelFamilyAssignment:
    author: str
    repair: str
    coverage: str


@dataclass(frozen=True)
class AppSpecGenerationPolicy:
    """Policy overrides; legacy defaults deliberately preserve v1 behavior."""

    name: str = "legacy_v1"
    allow_fallback: bool | None = None
    require_complete: bool = False
    require_distinct_coverage_family: bool = False
    author_model: str | None = None
    repair_model: str | None = None
    coverage_model: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


_PROVIDER_FAMILIES = {
    "anthropic": "anthropic",
    "cohere": "cohere",
    "deepseek": "deepseek",
    "google": "google",
    "meta-llama": "meta-llama",
    "mistralai": "mistral",
    "openai": "openai",
    "qwen": "qwen",
    "x-ai": "x-ai",
    "z-ai": "z-ai",
}
_MODEL_MARKERS = (
    ("claude", "anthropic"),
    ("gemini", "google"),
    ("deepseek", "deepseek"),
    ("qwen", "qwen"),
    ("llama", "meta-llama"),
    ("mistral", "mistral"),
    ("command-r", "cohere"),
    ("gpt-", "openai"),
    ("chatgpt", "openai"),
    ("o1", "openai"),
    ("o3", "openai"),
    ("o4", "openai"),
    ("glm", "z-ai"),
    ("grok", "x-ai"),
)


def model_family(model: str) -> str | None:
    """Return a normalized family or ``None`` when identity is ambiguous."""

    normalized = str(model or "").strip().casefold()
    if not normalized:
        return None
    if "/" in normalized:
        provider = normalized.split("/", 1)[0]
        if provider in _PROVIDER_FAMILIES:
            return _PROVIDER_FAMILIES[provider]
    for marker, family in _MODEL_MARKERS:
        if marker in normalized:
            return family
    return None


def resolve_model_assignment(
    policy: AppSpecGenerationPolicy,
) -> tuple[str, str, str, ModelFamilyAssignment | None]:
    author_model = policy.author_model or settings.APPSPEC_MODEL
    repair_model = policy.repair_model or settings.APPSPEC_REPAIR_MODEL
    coverage_model = policy.coverage_model or settings.APPSPEC_COVERAGE_MODEL
    if not policy.require_distinct_coverage_family:
        return author_model, repair_model, coverage_model, None

    author_family = model_family(author_model)
    repair_family = model_family(repair_model)
    coverage_family = model_family(coverage_model)
    unknown = [
        label
        for label, family in (
            ("author", author_family),
            ("repair", repair_family),
            ("coverage", coverage_family),
        )
        if family is None
    ]
    if unknown:
        raise ModelFamilyPolicyError(
            "Unknown AppSpec model family for "
            + ", ".join(unknown)
            + "; v2 fails closed before provider calls."
        )
    if coverage_family in {author_family, repair_family}:
        raise ModelFamilyPolicyError(
            "The v2 AppSpec coverage reviewer must use a different model "
            "family from every AppSpec author/repair model."
        )
    return (
        author_model,
        repair_model,
        coverage_model,
        ModelFamilyAssignment(
            author=author_family,
            repair=repair_family,
            coverage=coverage_family,
        ),
    )


def v2_app_spec_policy(
    *,
    source_artifact_id: int,
    product_strategy_revision_id: int,
    product_strategy_sha256: str,
) -> AppSpecGenerationPolicy:
    return AppSpecGenerationPolicy(
        name="v2_strict",
        allow_fallback=False,
        require_complete=True,
        require_distinct_coverage_family=True,
        coverage_model=settings.APPSPEC_V2_COVERAGE_MODEL,
        metadata={
            "generator_version": "v2",
            "customer_source_artifact_id": source_artifact_id,
            "product_strategy_revision_id": product_strategy_revision_id,
            "product_strategy_sha256": product_strategy_sha256,
        },
    )


__all__ = [
    "AppSpecGenerationPolicy",
    "ModelFamilyAssignment",
    "ModelFamilyPolicyError",
    "model_family",
    "resolve_model_assignment",
    "v2_app_spec_policy",
]
