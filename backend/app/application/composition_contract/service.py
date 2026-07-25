"""Two-call Phase 3A composition-contract boundary."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.application.appspec.repository import load_json_object
from app.application.appspec.source import canonical_json
from app.application.composition_contract.builder import (
    CompositionStageError,
    build_ai_composition_artifact,
)
from app.application.composition_contract.cache import (
    composition_artifact_sha256,
    composition_cache_key,
)
from app.application.composition_contract.context import (
    CompositionContext,
    load_composition_context,
)
from app.application.composition_contract.graph import (
    build_component_dependency_graph,
)
from app.application.composition_contract.policy import (
    CompositionStagePolicy,
    resolve_composition_stage_policy,
)
from app.application.composition_contract.normalize import (
    normalize_business_component_plan,
    normalize_content_data_plan,
)
from app.application.composition_contract.projections import (
    project_business_component_plan,
    project_content_data_plan,
    project_interactions,
    project_page_purpose,
)
from app.application.composition_contract.repository import (
    CompositionContractRepository,
    composition_artifact_ref,
    composition_cache_hit_metrics,
)
from app.application.composition_contract.validation import (
    validate_business_component_plan,
    validate_component_dependency_graph,
    validate_content_data_plan,
    validate_interaction_contract,
    validate_page_purpose_contract,
)
from app.application.prompts import PromptTemplate
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models import CompositionContractArtifactRecord, Request
from app.domain.schemas.business_component_plan import (
    BUSINESS_COMPONENT_PLAN_SCHEMA_VERSION,
    BusinessComponentPlan,
)
from app.domain.schemas.component_dependency_graph import (
    COMPONENT_DEPENDENCY_GRAPH_SCHEMA_VERSION,
    ComponentDependencyGraph,
)
from app.domain.schemas.composition_contract import (
    COMPOSITION_CONTRACT_POLICY_REVISION,
    CompositionArtifactRef,
    CompositionStageMetrics,
    CompositionValidationReport,
)
from app.domain.schemas.content_data_plan import (
    CONTENT_DATA_PLAN_SCHEMA_VERSION,
    ContentDataPlan,
)
from app.domain.schemas.interaction_contract import (
    INTERACTION_CONTRACT_SCHEMA_VERSION,
    InteractionContract,
)
from app.domain.schemas.page_purpose_contract import (
    PAGE_PURPOSE_SCHEMA_VERSION,
    PagePurposeContract,
)


V2_COMPOSITION_CONTRACT_READY = "composition_contract_ready"
ArtifactT = TypeVar("ArtifactT", bound=BaseModel)


@dataclass(frozen=True)
class ResolvedCompositionArtifact:
    artifact: BaseModel
    row: CompositionContractArtifactRecord
    ref: CompositionArtifactRef
    metrics: CompositionStageMetrics


def _ensure_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise CompositionStageError(
            "The composition-contract phase exceeded its wall timeout.",
            stage="composition_contract",
        )


def _deterministic_metrics(
    policy: CompositionStagePolicy,
    *,
    started: float,
) -> CompositionStageMetrics:
    return CompositionStageMetrics(
        stage=policy.stage,
        effective_model=policy.model,
        provider="local",
        model_family=policy.model_family,
        prompt_revision=policy.prompt_revision,
        cache_hit=False,
        provider_call_count=0,
        validation_retry_count=0,
        validation_retry_reasons=(),
        transport_retry_count=0,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        cost_usd=0.0,
        latency_ms=int((time.monotonic() - started) * 1000),
    )


def _cached_or_none(
    *,
    repository: CompositionContractRepository,
    context: CompositionContext,
    schema: type[ArtifactT],
    policy: CompositionStagePolicy,
    cache_key: str,
    parent_artifact_id: int | None,
    validator: Callable[[ArtifactT], CompositionValidationReport],
) -> ResolvedCompositionArtifact | None:
    started = time.monotonic()
    row = repository.find_cache(
        request_id=context.refs.request_id,
        artifact_kind=policy.stage,
        cache_key=cache_key,
    )
    if row is None:
        return None
    repository.validate_cached_row_refs(row, refs=context.refs)
    if (
        row.policy_revision != COMPOSITION_CONTRACT_POLICY_REVISION
        or row.prompt_revision != policy.prompt_revision
        or row.effective_model != policy.model
        or row.model_family != policy.model_family
        or row.parent_artifact_id != parent_artifact_id
    ):
        raise ValueError("Matching composition cache metadata is inconsistent.")
    artifact = schema.model_validate(repository.load_artifact_json(row))
    if composition_artifact_sha256(artifact) != row.artifact_sha256:
        raise ValueError("Cached composition artifact hash is corrupt.")
    validation = validator(artifact)
    if not validation.passed:
        raise ValueError("Cached composition artifact failed revalidation.")
    if (
        not row.validation_passed
        or load_json_object(row.validation_json)
        != validation.model_dump(mode="json")
    ):
        raise ValueError("Cached composition validation is inconsistent.")
    return ResolvedCompositionArtifact(
        artifact=artifact,
        row=row,
        ref=composition_artifact_ref(row),
        metrics=composition_cache_hit_metrics(
            row,
            latency_ms=int((time.monotonic() - started) * 1000),
        ),
    )


def _resolve_deterministic(
    *,
    repository: CompositionContractRepository,
    context: CompositionContext,
    schema: type[ArtifactT],
    schema_version: str,
    policy: CompositionStagePolicy,
    upstream_hashes: tuple[str, ...],
    parent_artifact_id: int | None,
    factory: Callable[[], ArtifactT],
    validator: Callable[[ArtifactT], CompositionValidationReport],
) -> ResolvedCompositionArtifact:
    cache_key = composition_cache_key(
        refs=context.refs,
        policy=policy,
        schema_version=schema_version,
        upstream_hashes=upstream_hashes,
    )
    cached = _cached_or_none(
        repository=repository,
        context=context,
        schema=schema,
        policy=policy,
        cache_key=cache_key,
        parent_artifact_id=parent_artifact_id,
        validator=validator,
    )
    if cached is not None:
        return cached
    started = time.monotonic()
    artifact = factory()
    validation = validator(artifact)
    if not validation.passed:
        raise CompositionStageError(
            f"{policy.stage} failed deterministic projection validation.",
            stage=policy.stage,
        )
    metrics = _deterministic_metrics(policy, started=started)
    persisted = repository.stage_artifact(
        artifact_kind=policy.stage,
        artifact=artifact,
        refs=context.refs,
        cache_key=cache_key,
        metrics=metrics,
        validation=validation,
        parent_artifact_id=parent_artifact_id,
    )
    return ResolvedCompositionArtifact(
        artifact=artifact,
        row=persisted.row,
        ref=composition_artifact_ref(persisted.row),
        metrics=metrics,
    )


def _resolve_ai(
    *,
    repository: CompositionContractRepository,
    context: CompositionContext,
    schema: type[ArtifactT],
    schema_version: str,
    policy: CompositionStagePolicy,
    upstream_hashes: tuple[str, ...],
    parent_artifact_id: int,
    stage_input_json: str,
    prompt_template: str,
    validator: Callable[[ArtifactT], CompositionValidationReport],
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    deadline: float,
    normalize: Callable[[ArtifactT], ArtifactT] | None = None,
    deterministic_fallback: Callable[[], ArtifactT] | None = None,
) -> ResolvedCompositionArtifact:
    cache_key = composition_cache_key(
        refs=context.refs,
        policy=policy,
        schema_version=schema_version,
        upstream_hashes=upstream_hashes,
    )
    cached = _cached_or_none(
        repository=repository,
        context=context,
        schema=schema,
        policy=policy,
        cache_key=cache_key,
        parent_artifact_id=parent_artifact_id,
        validator=validator,
    )
    if cached is not None:
        return cached
    try:
        built = build_ai_composition_artifact(
            request_id=context.refs.request_id,
            policy=policy,
            schema=schema,
            prompt_template=prompt_template,
            prompt_values={"stage_input_json": stage_input_json},
            validator=validator,
            ai_provider=ai_provider,
            template_renderer=template_renderer,
            phase_deadline=deadline,
            normalize=normalize,
        )
    except CompositionStageError as exc:
        if deterministic_fallback is None:
            raise
        message = str(exc).casefold()
        # Never mask phase/stage deadline or hard timeouts with a fallback.
        if "deadline" in message or "timeout" in message:
            raise
        started = time.monotonic()
        artifact = deterministic_fallback()
        validation = validator(artifact)
        if not validation.passed:
            raise CompositionStageError(
                f"{policy.stage} deterministic fallback failed validation "
                f"issues={[issue.code for issue in validation.issues[:8]]}.",
                stage=policy.stage,
            ) from None
        metrics = CompositionStageMetrics(
            stage=policy.stage,
            effective_model=policy.model,
            provider="deterministic_fallback",
            model_family=policy.model_family,
            prompt_revision=policy.prompt_revision,
            cache_hit=False,
            provider_call_count=0,
            validation_retry_count=0,
            validation_retry_reasons=(),
            transport_retry_count=0,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=0.0,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        persisted = repository.stage_artifact(
            artifact_kind=policy.stage,
            artifact=artifact,
            refs=context.refs,
            cache_key=cache_key,
            metrics=metrics,
            validation=validation,
            parent_artifact_id=parent_artifact_id,
        )
        return ResolvedCompositionArtifact(
            artifact=artifact,
            row=persisted.row,
            ref=composition_artifact_ref(persisted.row),
            metrics=metrics,
        )
    persisted = repository.stage_artifact(
        artifact_kind=policy.stage,
        artifact=built.artifact,
        refs=context.refs,
        cache_key=cache_key,
        metrics=built.metrics,
        validation=built.validation,
        parent_artifact_id=parent_artifact_id,
    )
    return ResolvedCompositionArtifact(
        artifact=built.artifact,
        row=persisted.row,
        ref=composition_artifact_ref(persisted.row),
        metrics=built.metrics,
    )


def _stage_input(
    context: CompositionContext,
    **artifacts: BaseModel | CompositionArtifactRef,
) -> str:
    return canonical_json(
        {
            "composition_contract_refs": (
                context.refs.model_dump(mode="json")
            ),
            "customer_source": context.source.model_dump(mode="json"),
            "canonical_app_spec": context.app_spec.model_dump(mode="json"),
            "tier_1": context.tier_1.model_dump(mode="json"),
            "product_strategy_v2": (
                context.product_strategy_v2.model_dump(mode="json")
            ),
            "information_architecture": (
                context.information_architecture.model_dump(mode="json")
            ),
            "design_dna": context.design_dna.model_dump(mode="json"),
            **{
                name: artifact.model_dump(mode="json")
                for name, artifact in artifacts.items()
            },
        }
    )


def _check_usage(
    db: Session,
    metrics: tuple[CompositionStageMetrics, ...],
) -> None:
    calls = sum(item.provider_call_count for item in metrics)
    if calls > settings.V2_COMPOSITION_CONTRACT_MAX_CALLS:
        db.rollback()
        raise CompositionStageError(
            "Phase 3A exceeded its provider-call budget.",
            stage="composition_contract",
        )
    cost = sum(item.cost_usd for item in metrics)
    if cost > settings.V2_COMPOSITION_CONTRACT_MAX_COST_USD:
        db.rollback()
        raise CompositionStageError(
            "Phase 3A exceeded its cost budget.",
            stage="composition_contract",
        )


def _bundle(req: Request) -> dict[str, Any]:
    if not req.generated_pages:
        return {}
    try:
        payload = json.loads(req.generated_pages)
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def build_v2_composition_contract(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    *,
    req: Request,
    phase2_result: dict[str, Any],
) -> dict[str, Any]:
    """Build only Tier 1 composition artifacts, then stop."""

    context = load_composition_context(
        db,
        request_id=request_id,
        phase2_result=phase2_result,
    )
    repository = CompositionContractRepository(db)
    deadline = (
        time.monotonic()
        + settings.V2_COMPOSITION_CONTRACT_TIMEOUT_SECONDS
    )

    page_policy = resolve_composition_stage_policy(
        "page_purpose_contract"
    )
    page = _resolve_deterministic(
        repository=repository,
        context=context,
        schema=PagePurposeContract,
        schema_version=PAGE_PURPOSE_SCHEMA_VERSION,
        policy=page_policy,
        upstream_hashes=(),
        parent_artifact_id=None,
        factory=lambda: project_page_purpose(context),
        validator=lambda artifact: validate_page_purpose_contract(
            artifact,
            context=context,
        ),
    )
    if not page.metrics.cache_hit:
        db.commit()
    _ensure_deadline(deadline)

    component_policy = resolve_composition_stage_policy(
        "business_component_plan"
    )
    component = _resolve_ai(
        repository=repository,
        context=context,
        schema=BusinessComponentPlan,
        schema_version=BUSINESS_COMPONENT_PLAN_SCHEMA_VERSION,
        policy=component_policy,
        upstream_hashes=(page.ref.sha256, page.row.cache_key),
        parent_artifact_id=page.row.id,
        stage_input_json=_stage_input(
            context,
            page_purpose_contract=page.artifact,
            page_purpose_ref=page.ref,
        ),
        prompt_template=PromptTemplate.V2_BUSINESS_COMPONENT_PLAN,
        validator=lambda artifact: validate_business_component_plan(
            artifact,
            context=context,
            page_purpose=page.artifact,
            page_purpose_ref=page.ref,
        ),
        ai_provider=ai_provider,
        template_renderer=template_renderer,
        deadline=deadline,
        normalize=lambda artifact: normalize_business_component_plan(
            artifact,
            context=context,
            page_purpose=page.artifact,
            page_purpose_ref=page.ref,
        ),
        deterministic_fallback=lambda: project_business_component_plan(
            context,
            page_purpose=page.artifact,
            page_purpose_ref=page.ref,
        ),
    )
    _check_usage(db, (page.metrics, component.metrics))
    if not component.metrics.cache_hit:
        db.commit()
    _ensure_deadline(deadline)

    content_policy = resolve_composition_stage_policy("content_data_plan")
    content = _resolve_ai(
        repository=repository,
        context=context,
        schema=ContentDataPlan,
        schema_version=CONTENT_DATA_PLAN_SCHEMA_VERSION,
        policy=content_policy,
        upstream_hashes=(
            page.ref.sha256,
            page.row.cache_key,
            component.ref.sha256,
            component.row.cache_key,
        ),
        parent_artifact_id=component.row.id,
        stage_input_json=_stage_input(
            context,
            page_purpose_contract=page.artifact,
            page_purpose_ref=page.ref,
            business_component_plan=component.artifact,
            business_component_plan_ref=component.ref,
        ),
        prompt_template=PromptTemplate.V2_CONTENT_DATA_PLAN,
        validator=lambda artifact: validate_content_data_plan(
            artifact,
            context=context,
            page_purpose=page.artifact,
            page_purpose_ref=page.ref,
            component_plan=component.artifact,
            component_plan_ref=component.ref,
        ),
        ai_provider=ai_provider,
        template_renderer=template_renderer,
        deadline=deadline,
        normalize=lambda artifact: normalize_content_data_plan(
            artifact,
            context=context,
            page_purpose=page.artifact,
            page_purpose_ref=page.ref,
            component_plan=component.artifact,
            component_plan_ref=component.ref,
        ),
        deterministic_fallback=lambda: project_content_data_plan(
            context,
            page_purpose=page.artifact,
            page_purpose_ref=page.ref,
            component_plan=component.artifact,
            component_plan_ref=component.ref,
        ),
    )
    _check_usage(db, (page.metrics, component.metrics, content.metrics))
    if not content.metrics.cache_hit:
        db.commit()
    _ensure_deadline(deadline)

    interaction_policy = resolve_composition_stage_policy(
        "interaction_contract"
    )
    interaction = _resolve_deterministic(
        repository=repository,
        context=context,
        schema=InteractionContract,
        schema_version=INTERACTION_CONTRACT_SCHEMA_VERSION,
        policy=interaction_policy,
        upstream_hashes=(
            page.ref.sha256,
            page.row.cache_key,
            component.ref.sha256,
            component.row.cache_key,
            content.ref.sha256,
            content.row.cache_key,
        ),
        parent_artifact_id=content.row.id,
        factory=lambda: project_interactions(
            context,
            page_purpose=page.artifact,
            page_purpose_ref=page.ref,
            component_plan=component.artifact,
            component_plan_ref=component.ref,
            content_data_plan=content.artifact,
            content_data_plan_ref=content.ref,
        ),
        validator=lambda artifact: validate_interaction_contract(
            artifact,
            context=context,
            page_purpose=page.artifact,
            page_purpose_ref=page.ref,
            component_plan=component.artifact,
            component_plan_ref=component.ref,
            content_data_plan=content.artifact,
            content_data_plan_ref=content.ref,
        ),
    )
    if not interaction.metrics.cache_hit:
        db.commit()
    _ensure_deadline(deadline)

    graph_policy = resolve_composition_stage_policy(
        "component_dependency_graph"
    )
    graph = _resolve_deterministic(
        repository=repository,
        context=context,
        schema=ComponentDependencyGraph,
        schema_version=COMPONENT_DEPENDENCY_GRAPH_SCHEMA_VERSION,
        policy=graph_policy,
        upstream_hashes=(
            page.ref.sha256,
            page.row.cache_key,
            component.ref.sha256,
            component.row.cache_key,
            content.ref.sha256,
            content.row.cache_key,
            interaction.ref.sha256,
            interaction.row.cache_key,
        ),
        parent_artifact_id=interaction.row.id,
        factory=lambda: build_component_dependency_graph(
            refs=context.refs,
            page_purpose=page.artifact,
            page_purpose_ref=page.ref,
            component_plan=component.artifact,
            component_plan_ref=component.ref,
            content_data_plan=content.artifact,
            content_data_plan_ref=content.ref,
            interaction_contract=interaction.artifact,
            interaction_contract_ref=interaction.ref,
        ),
        validator=lambda artifact: validate_component_dependency_graph(
            artifact,
            context=context,
            page_purpose=page.artifact,
            page_purpose_ref=page.ref,
            component_plan=component.artifact,
            component_plan_ref=component.ref,
            content_data_plan=content.artifact,
            content_data_plan_ref=content.ref,
            interaction_contract=interaction.artifact,
            interaction_contract_ref=interaction.ref,
        ),
    )
    metrics = (
        page.metrics,
        component.metrics,
        content.metrics,
        interaction.metrics,
        graph.metrics,
    )
    _check_usage(db, metrics)
    try:
        _ensure_deadline(deadline)
    except Exception:
        db.rollback()
        raise

    phase2_summary = dict(phase2_result.get("preview_contract") or {})
    summary = {
        **phase2_summary,
        "status": V2_COMPOSITION_CONTRACT_READY,
        "composition_artifact_refs": {
            item.ref.artifact_kind: item.ref.model_dump(mode="json")
            for item in (page, component, content, interaction, graph)
        },
        "composition_stage_metrics": {
            item.stage: item.model_dump(mode="json") for item in metrics
        },
        "composition_contract_totals": {
            "provider_call_count": sum(
                item.provider_call_count for item in metrics
            ),
            "prompt_tokens": sum(item.prompt_tokens for item in metrics),
            "completion_tokens": sum(
                item.completion_tokens for item in metrics
            ),
            "total_tokens": sum(item.total_tokens for item in metrics),
            "cost_usd": sum(item.cost_usd for item in metrics),
            "latency_ms": sum(item.latency_ms for item in metrics),
        },
    }
    bundle = _bundle(req)
    bundle["preview_contract"] = summary
    req.generated_pages = json.dumps(bundle, ensure_ascii=False)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"preview_contract": summary}


__all__ = [
    "V2_COMPOSITION_CONTRACT_READY",
    "build_v2_composition_contract",
]
