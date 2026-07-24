"""Two-call Phase 3B immutable Tier 1 candidate boundary."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.application.appspec.source import canonical_json
from app.application.candidate_generation.builder import (
    CandidateStageError,
    build_ai_batch,
    combine_generation_and_repair_metrics,
    repair_ai_batch,
)
from app.application.candidate_generation.cache import (
    candidate_cache_key,
    candidate_upstream_sha256,
    canonical_sha256,
    sha256_text,
)
from app.application.candidate_generation.context import (
    CandidateContext,
    load_candidate_context,
)
from app.application.candidate_generation.deterministic import (
    CandidateSourceFile,
    build_data_sources,
    build_foundation_sources,
    build_route_sources,
    dependency_lock_sha256,
    page_export_symbol,
    source_manifest,
)
from app.application.candidate_generation.policy import (
    CandidateStagePolicy,
    repair_policy,
    resolve_candidate_stage_policy,
)
from app.application.candidate_generation.repository import (
    CandidateRepository,
    candidate_cache_hit_metrics,
)
from app.application.candidate_generation.validation import (
    APPROVED_RUNTIME_PACKAGES,
    batch_sources,
    deterministic_repair_batch,
    validate_candidate_workspace,
    validate_generated_batch,
)
from app.application.candidate_generation.workspace import (
    CandidateWorkspace,
    checkpoint_workspace,
    freeze_candidate_workspace,
    open_candidate_workspace,
    source_file_manifest,
    workspace_relpath,
    write_sources,
)
from app.application.prompts import PromptTemplate
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models import CandidateArtifactRecord, Request
from app.domain.schemas.preview_candidate import (
    CANDIDATE_POLICY_REVISION,
    CANDIDATE_SCHEMA_VERSION,
    CandidateArtifactManifest,
    CandidateStageMetrics,
    CandidateValidationIssue,
    CandidateValidationReport,
    GeneratedCandidateBatch,
)


V2_CANDIDATE_BUILD_PENDING = "candidate_build_pending"


class CandidateContractError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        issues: tuple[CandidateValidationIssue, ...],
    ) -> None:
        super().__init__(message)
        self.issues = issues


@dataclass
class _Stage:
    artifact: BaseModel
    sources: tuple[CandidateSourceFile, ...]
    cache_key: str
    provenance_sha256: str
    metrics: CandidateStageMetrics
    row: CandidateArtifactRecord | None = None
    repair_used: bool = False


def _ensure_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise CandidateStageError(
            "Phase 3B exceeded its 600-second wall deadline.",
            stage="candidate_generation",
        )


def _deterministic_metrics(
    policy: CandidateStagePolicy,
    *,
    started: float,
    cache_hit: bool,
) -> CandidateStageMetrics:
    return CandidateStageMetrics(
        stage=policy.stage,
        effective_model=policy.model,
        provider="local",
        model_family=policy.model_family,
        prompt_revision=policy.prompt_revision,
        cache_hit=cache_hit,
        provider_call_count=0,
        repair_call_count=0,
        repair_reason=None,
        transport_retry_count=0,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        cost_usd=0.0,
        latency_ms=int((time.monotonic() - started) * 1000),
    )


def _stage_provenance(input_hashes: tuple[str, ...]) -> str:
    return canonical_sha256(list(input_hashes))


def _load_deterministic_stage(
    *,
    repository: CandidateRepository,
    context: CandidateContext,
    artifact_kind: str,
    sources: tuple[CandidateSourceFile, ...],
    dependency_sha: str,
    input_hashes: tuple[str, ...],
    parent_row: CandidateArtifactRecord | None,
) -> _Stage:
    started = time.monotonic()
    policy = resolve_candidate_stage_policy(artifact_kind)
    manifest = source_manifest(
        artifact_kind=artifact_kind,
        input_hashes=input_hashes,
        sources=sources,
    )
    cache_key = candidate_cache_key(
        stage=artifact_kind,
        schema_version=CANDIDATE_SCHEMA_VERSION,
        prompt_revision=policy.prompt_revision,
        effective_model=policy.model,
        model_family=policy.model_family,
        max_tokens=0,
        temperature=0.0,
        dependency_lock_sha256=dependency_sha,
        input_hashes=input_hashes,
    )
    provenance = _stage_provenance(input_hashes)
    row = (
        repository.find_cache(
            request_id=context.refs.request_id,
            artifact_kind=artifact_kind,
            cache_key=cache_key,
        )
        if parent_row is not None or artifact_kind == "foundation"
        else None
    )
    if row is not None:
        cached = repository.load_cached(
            row,
            schema=CandidateArtifactManifest,
            request_id=context.refs.request_id,
            provenance_sha256=provenance,
            parent_artifact_id=parent_row.id if parent_row else None,
        )
        if cached != manifest:
            raise ValueError("Deterministic candidate cache is not reproducible.")
        metrics = candidate_cache_hit_metrics(
            row,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
    else:
        metrics = _deterministic_metrics(
            policy,
            started=started,
            cache_hit=False,
        )
    return _Stage(
        artifact=manifest,
        sources=sources,
        cache_key=cache_key,
        provenance_sha256=provenance,
        metrics=metrics,
        row=row,
    )


def _common_prompt_inputs(context: CandidateContext) -> dict[str, Any]:
    return {
        "canonical_app_spec": context.composition.app_spec.model_dump(
            mode="json"
        ),
        "product_strategy_v2": (
            context.composition.product_strategy_v2.model_dump(mode="json")
        ),
        "information_architecture": (
            context.composition.information_architecture.model_dump(mode="json")
        ),
        "design_dna": context.composition.design_dna.model_dump(mode="json"),
        "page_purpose_contract": context.page_purpose.model_dump(mode="json"),
        "business_component_plan": context.business_components.model_dump(
            mode="json"
        ),
        "content_data_plan": context.content_data.model_dump(mode="json"),
        "interaction_contract": context.interactions.model_dump(mode="json"),
        "component_dependency_graph": context.dependency_graph.model_dump(
            mode="json"
        ),
        "allowed_dependencies": sorted(APPROVED_RUNTIME_PACKAGES),
        "deterministic_data_export_paths": [
            "src/generated/content-data.ts",
            "src/generated/content-data.json",
            "src/generated/canonical-contracts.ts",
        ],
    }


def _ai_stage_input_hashes(
    *,
    context: CandidateContext,
    stage: str,
    dependency_sha: str,
    parent_artifact_sha: str,
) -> tuple[str, ...]:
    refs = context.refs
    repair = repair_policy()
    repair_provenance = canonical_sha256(
        {
            "model": repair.model,
            "family": repair.model_family,
            "prompt_revision": repair.prompt_revision,
            "max_tokens": repair.max_tokens,
        }
    )
    design_refs = refs.composition_contract_refs
    if stage == "business_components":
        return (
            refs.page_purpose_ref.sha256,
            refs.business_component_plan_ref.sha256,
            refs.content_data_plan_ref.sha256,
            refs.interaction_contract_ref.sha256,
            refs.component_dependency_graph_ref.sha256,
            design_refs.product_strategy_v2_ref.sha256,
            design_refs.information_architecture_ref.sha256,
            design_refs.design_dna_ref.sha256,
            dependency_sha,
            parent_artifact_sha,
            repair_provenance,
        )
    return (
        refs.page_purpose_ref.sha256,
        refs.business_component_plan_ref.sha256,
        refs.content_data_plan_ref.sha256,
        refs.interaction_contract_ref.sha256,
        design_refs.information_architecture_ref.sha256,
        design_refs.design_dna_ref.sha256,
        dependency_sha,
        parent_artifact_sha,
        repair_provenance,
    )


def _load_or_generate_ai_stage(
    *,
    repository: CandidateRepository,
    context: CandidateContext,
    stage: str,
    dependency_sha: str,
    parent_row: CandidateArtifactRecord | None,
    parent_artifact_sha: str,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    phase_deadline: float,
    component_batch: GeneratedCandidateBatch | None = None,
) -> _Stage:
    started = time.monotonic()
    policy = resolve_candidate_stage_policy(stage)
    input_hashes = _ai_stage_input_hashes(
        context=context,
        stage=stage,
        dependency_sha=dependency_sha,
        parent_artifact_sha=parent_artifact_sha,
    )
    cache_key = candidate_cache_key(
        stage=stage,
        schema_version=CANDIDATE_SCHEMA_VERSION,
        prompt_revision=policy.prompt_revision,
        effective_model=policy.model,
        model_family=policy.model_family,
        max_tokens=policy.max_tokens,
        temperature=policy.temperature,
        dependency_lock_sha256=dependency_sha,
        input_hashes=input_hashes,
    )
    provenance = _stage_provenance(input_hashes)
    row = (
        repository.find_cache(
            request_id=context.refs.request_id,
            artifact_kind=stage,
            cache_key=cache_key,
        )
        if parent_row is not None
        else None
    )
    if row is not None:
        batch = repository.load_cached(
            row,
            schema=GeneratedCandidateBatch,
            request_id=context.refs.request_id,
            provenance_sha256=provenance,
            parent_artifact_id=parent_row.id,
        )
        issues = validate_generated_batch(batch, context=context)
        if issues:
            raise ValueError("Cached AI candidate batch is invalid.")
        return _Stage(
            artifact=batch,
            sources=batch_sources(batch),
            cache_key=cache_key,
            provenance_sha256=provenance,
            metrics=candidate_cache_hit_metrics(
                row,
                latency_ms=int((time.monotonic() - started) * 1000),
            ),
            row=row,
        )

    prompt_inputs = _common_prompt_inputs(context)
    if stage == "pages":
        if component_batch is None:
            raise ValueError("Page generation requires the component batch.")
        prompt_inputs["generated_business_components"] = (
            component_batch.model_dump(mode="json")
        )
        prompt_inputs["required_page_exports"] = {
            page.page_id: page_export_symbol(page.page_id)
            for page in context.page_purpose.pages
        }
    built = build_ai_batch(
        request_id=context.refs.request_id,
        policy=policy,
        prompt_template=(
            PromptTemplate.V2_CANDIDATE_COMPONENTS
            if stage == "business_components"
            else PromptTemplate.V2_CANDIDATE_PAGES
        ),
        prompt_values={
            "candidate_inputs_json": canonical_json(prompt_inputs),
        },
        ai_provider=ai_provider,
        template_renderer=template_renderer,
        phase_deadline=phase_deadline,
    )
    batch = deterministic_repair_batch(built.batch)
    issues = validate_generated_batch(batch, context=context)
    repair_used = False
    metrics = built.metrics
    if issues:
        repair = repair_policy()
        repaired = repair_ai_batch(
            request_id=context.refs.request_id,
            batch_stage=stage,
            policy=repair,
            batch=batch,
            diagnostics=tuple(
                canonical_json(item.model_dump(mode="json"))
                for item in issues
            ),
            canonical_bindings={
                "page_purpose_contract": context.page_purpose.model_dump(
                    mode="json"
                ),
                "business_component_plan": (
                    context.business_components.model_dump(mode="json")
                ),
                "interaction_contract": context.interactions.model_dump(
                    mode="json"
                ),
            },
            ai_provider=ai_provider,
            template_renderer=template_renderer,
            prompt_template=PromptTemplate.V2_CANDIDATE_REPAIR,
            phase_deadline=phase_deadline,
        )
        batch = deterministic_repair_batch(repaired.batch)
        issues = validate_generated_batch(batch, context=context)
        if issues:
            raise CandidateContractError(
                f"{stage} failed strict batch validation.",
                issues=issues,
            )
        metrics = combine_generation_and_repair_metrics(
            metrics,
            repaired.metrics,
        )
        repair_used = True
    return _Stage(
        artifact=batch,
        sources=batch_sources(batch),
        cache_key=cache_key,
        provenance_sha256=provenance,
        metrics=metrics,
        row=None,
        repair_used=repair_used,
    )


def _check_usage(metrics: tuple[CandidateStageMetrics, ...]) -> None:
    calls = sum(item.provider_call_count for item in metrics)
    cost = sum(item.cost_usd for item in metrics)
    if calls > settings.V2_CANDIDATE_MAX_CALLS:
        raise CandidateStageError(
            "Phase 3B exceeded its provider-call budget.",
            stage="candidate_generation",
        )
    if cost > settings.V2_CANDIDATE_MAX_COST_USD:
        raise CandidateStageError(
            "Phase 3B exceeded its cost budget.",
            stage="candidate_generation",
        )


def _gate_issues_for_stage(
    report: CandidateValidationReport,
    stage: str,
) -> tuple[CandidateValidationIssue, ...]:
    prefix = (
        "src/components/business/"
        if stage == "business_components"
        else "src/pages/"
    )
    semantic_codes = (
        {
            "canonical_interaction_omitted",
            "canonical_evidence_omitted",
            "missing_component_contract_hook",
        }
        if stage == "business_components"
        else {
            "missing_page_hook",
            "missing_acceptance_hook",
            "missing_mobile_binding",
            "missing_business_component_usage",
        }
    )
    return tuple(
        item
        for item in report.issues
        if item.code in semantic_codes
        or item.path.startswith(prefix)
        or prefix in item.message
    )


def _repair_stage_after_gate(
    *,
    stage: _Stage,
    stage_name: str,
    context: CandidateContext,
    report: CandidateValidationReport,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    phase_deadline: float,
) -> bool:
    issues = _gate_issues_for_stage(report, stage_name)
    if not issues or stage.repair_used or stage.metrics.cache_hit:
        return False
    repair = repair_policy()
    repaired = repair_ai_batch(
        request_id=context.refs.request_id,
        batch_stage=stage_name,
        policy=repair,
        batch=stage.artifact,
        diagnostics=tuple(
            canonical_json(item.model_dump(mode="json")) for item in issues
        ),
        canonical_bindings={
            "page_purpose_contract": context.page_purpose.model_dump(
                mode="json"
            ),
            "business_component_plan": context.business_components.model_dump(
                mode="json"
            ),
            "interaction_contract": context.interactions.model_dump(
                mode="json"
            ),
        },
        ai_provider=ai_provider,
        template_renderer=template_renderer,
        prompt_template=PromptTemplate.V2_CANDIDATE_REPAIR,
        phase_deadline=phase_deadline,
    )
    batch = deterministic_repair_batch(repaired.batch)
    batch_issues = validate_generated_batch(batch, context=context)
    if batch_issues:
        raise CandidateContractError(
            f"{stage_name} repair violated canonical batch contracts.",
            issues=batch_issues,
        )
    stage.artifact = batch
    stage.sources = batch_sources(batch)
    stage.metrics = combine_generation_and_repair_metrics(
        stage.metrics,
        repaired.metrics,
    )
    stage.repair_used = True
    stage.row = None
    return True


def _model_manifest() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, factory, configured_model in (
        (
            "business_components",
            lambda: resolve_candidate_stage_policy("business_components"),
            settings.V2_CANDIDATE_COMPONENT_MODEL,
        ),
        (
            "pages",
            lambda: resolve_candidate_stage_policy("pages"),
            settings.V2_CANDIDATE_PAGE_MODEL,
        ),
        (
            "repair",
            repair_policy,
            settings.V2_CANDIDATE_REPAIR_MODEL,
        ),
    ):
        try:
            result[name] = factory().__dict__
        except Exception as exc:
            result[name] = {
                "model": configured_model,
                "model_family": "unknown",
                "policy_error": str(exc)[:1000],
            }
    return result


def _failure_payload(
    exc: Exception,
    *,
    kind: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": kind,
        "error_type": type(exc).__name__,
        "message": str(exc)[:4000],
    }
    if isinstance(exc, CandidateContractError):
        payload["issues"] = [
            item.model_dump(mode="json") for item in exc.issues
        ]
    if isinstance(exc, CandidateStageError):
        payload["stage"] = exc.stage
        payload["diagnostics"] = list(exc.diagnostics)
    return payload


def _persist_failure(
    *,
    db: Session,
    repository: CandidateRepository,
    req: Request,
    context: CandidateContext,
    workspace: CandidateWorkspace,
    dependency_sha: str,
    phase3a_summary: dict[str, Any],
    metrics: tuple[CandidateStageMetrics, ...],
    exc: Exception,
    contract_failure: bool,
) -> dict:
    final_path = (
        freeze_candidate_workspace(workspace)
        if workspace.staging_path.exists()
        else workspace.final_path
    )
    manifest = source_file_manifest(final_path)
    failure = _failure_payload(
        exc,
        kind="contract_validation" if contract_failure else "generation",
    )
    try:
        _row, summary = repository.persist_revision(
            req=req,
            revision_uuid=workspace.revision_uuid,
            status=(
                "candidate_contract_failed"
                if contract_failure
                else "candidate_failed"
            ),
            refs=context.refs,
            dependency_lock_sha256=dependency_sha,
            model_manifest=_model_manifest(),
            workspace_relpath=workspace_relpath(final_path),
            file_manifest=manifest,
            artifact_rows=(None, None, None, None, None, None),
            failure=failure,
            metrics=metrics,
            summary_base=phase3a_summary,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"preview_contract": summary}


def build_v2_candidate_revision(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    *,
    req: Request,
    phase3a_result: dict[str, Any],
) -> dict:
    """Generate, statically validate, freeze, and persist one Tier 1 candidate."""

    if settings.V2_CANDIDATE_POLICY_REVISION != CANDIDATE_POLICY_REVISION:
        raise ValueError(
            "Configured Phase 3B policy revision is unsupported."
        )
    phase_started = time.monotonic()
    phase_deadline = phase_started + settings.V2_CANDIDATE_TIMEOUT_SECONDS
    context = load_candidate_context(
        db,
        request_id=request_id,
        phase3a_result=phase3a_result,
    )
    repository = CandidateRepository(db)
    dependency_sha = dependency_lock_sha256(settings.PREVIEW_TEMPLATE_DIR)
    upstream_sha = candidate_upstream_sha256(context.refs)
    workspace = open_candidate_workspace(
        request_id=request_id,
        upstream_sha256=upstream_sha,
    )
    phase3a_summary = dict(phase3a_result.get("preview_contract") or {})
    completed: dict[str, str] = {}
    stages: list[_Stage] = []
    try:
        foundation_sources = build_foundation_sources(
            settings.PREVIEW_TEMPLATE_DIR
        )
        foundation_input_hashes = (
            dependency_sha,
            canonical_sha256(
                [
                    {
                        "path": item.path,
                        "sha256": canonical_sha256(item.source),
                    }
                    for item in foundation_sources
                ]
            ),
        )
        foundation = _load_deterministic_stage(
            repository=repository,
            context=context,
            artifact_kind="foundation",
            sources=foundation_sources,
            dependency_sha=dependency_sha,
            input_hashes=foundation_input_hashes,
            parent_row=None,
        )
        stages.append(foundation)
        write_sources(workspace, foundation.sources)
        completed.update(
            {item.path: sha256_text(item.source) for item in foundation.sources}
        )
        checkpoint_workspace(
            workspace,
            upstream_sha256=upstream_sha,
            completed_artifacts=completed,
        )
        _ensure_deadline(phase_deadline)

        data_sources = build_data_sources(context)
        data_input_hashes = (
            context.refs.content_data_plan_ref.sha256,
            context.refs.page_purpose_ref.sha256,
            context.refs.interaction_contract_ref.sha256,
        )
        data = _load_deterministic_stage(
            repository=repository,
            context=context,
            artifact_kind="data_exports",
            sources=data_sources,
            dependency_sha=dependency_sha,
            input_hashes=data_input_hashes,
            parent_row=foundation.row,
        )
        stages.append(data)
        write_sources(workspace, data.sources)
        _ensure_deadline(phase_deadline)

        components = _load_or_generate_ai_stage(
            repository=repository,
            context=context,
            stage="business_components",
            dependency_sha=dependency_sha,
            parent_row=data.row,
            parent_artifact_sha=canonical_sha256(
                {
                    "artifact_sha256": canonical_sha256(data.artifact),
                    "cache_key": data.cache_key,
                }
            ),
            ai_provider=ai_provider,
            template_renderer=template_renderer,
            phase_deadline=phase_deadline,
        )
        stages.append(components)
        write_sources(workspace, components.sources)
        _check_usage(tuple(item.metrics for item in stages))
        _ensure_deadline(phase_deadline)

        pages = _load_or_generate_ai_stage(
            repository=repository,
            context=context,
            stage="pages",
            dependency_sha=dependency_sha,
            parent_row=components.row,
            parent_artifact_sha=canonical_sha256(
                {
                    "artifact_sha256": canonical_sha256(
                        components.artifact
                    ),
                    "cache_key": components.cache_key,
                }
            ),
            ai_provider=ai_provider,
            template_renderer=template_renderer,
            phase_deadline=phase_deadline,
            component_batch=components.artifact,
        )
        stages.append(pages)
        write_sources(workspace, pages.sources)
        _check_usage(tuple(item.metrics for item in stages))
        _ensure_deadline(phase_deadline)

        route_sources = build_route_sources(context, pages.sources)
        route_input_hashes = (
            context.refs.composition_contract_refs.design_contract_refs.app_spec_ref.sha256,
            context.refs.composition_contract_refs.design_contract_refs.tier_refs[0].sha256,
            context.refs.composition_contract_refs.information_architecture_ref.sha256,
            canonical_sha256(pages.artifact),
            pages.cache_key,
        )
        routes = _load_deterministic_stage(
            repository=repository,
            context=context,
            artifact_kind="routes",
            sources=route_sources,
            dependency_sha=dependency_sha,
            input_hashes=route_input_hashes,
            parent_row=pages.row,
        )
        stages.append(routes)
        write_sources(workspace, routes.sources)

        expected_sources = tuple(
            source for stage in stages for source in stage.sources
        )
        report = validate_candidate_workspace(
            workspace,
            context=context,
            expected_sources=expected_sources,
            data_sources=data.sources,
            route_sources=routes.sources,
        )
        _ensure_deadline(phase_deadline)
        repaired_components = _repair_stage_after_gate(
            stage=components,
            stage_name="business_components",
            context=context,
            report=report,
            ai_provider=ai_provider,
            template_renderer=template_renderer,
            phase_deadline=phase_deadline,
        )
        repaired_pages = _repair_stage_after_gate(
            stage=pages,
            stage_name="pages",
            context=context,
            report=report,
            ai_provider=ai_provider,
            template_renderer=template_renderer,
            phase_deadline=phase_deadline,
        )
        if repaired_components or repaired_pages:
            if repaired_components:
                page_policy = resolve_candidate_stage_policy("pages")
                page_hashes = _ai_stage_input_hashes(
                    context=context,
                    stage="pages",
                    dependency_sha=dependency_sha,
                    parent_artifact_sha=canonical_sha256(
                        {
                            "artifact_sha256": canonical_sha256(
                                components.artifact
                            ),
                            "cache_key": components.cache_key,
                        }
                    ),
                )
                pages.cache_key = candidate_cache_key(
                    stage="pages",
                    schema_version=CANDIDATE_SCHEMA_VERSION,
                    prompt_revision=page_policy.prompt_revision,
                    effective_model=page_policy.model,
                    model_family=page_policy.model_family,
                    max_tokens=page_policy.max_tokens,
                    temperature=page_policy.temperature,
                    dependency_lock_sha256=dependency_sha,
                    input_hashes=page_hashes,
                )
                pages.provenance_sha256 = _stage_provenance(page_hashes)
                pages.row = None
            write_sources(workspace, components.sources)
            write_sources(workspace, pages.sources)
            route_sources = build_route_sources(context, pages.sources)
            route_input_hashes = (
                context.refs.composition_contract_refs.design_contract_refs.app_spec_ref.sha256,
                context.refs.composition_contract_refs.design_contract_refs.tier_refs[0].sha256,
                context.refs.composition_contract_refs.information_architecture_ref.sha256,
                canonical_sha256(pages.artifact),
                pages.cache_key,
            )
            route_policy = resolve_candidate_stage_policy("routes")
            routes.sources = route_sources
            routes.artifact = source_manifest(
                artifact_kind="routes",
                input_hashes=route_input_hashes,
                sources=route_sources,
            )
            routes.cache_key = candidate_cache_key(
                stage="routes",
                schema_version=CANDIDATE_SCHEMA_VERSION,
                prompt_revision=route_policy.prompt_revision,
                effective_model=route_policy.model,
                model_family=route_policy.model_family,
                max_tokens=0,
                temperature=0.0,
                dependency_lock_sha256=dependency_sha,
                input_hashes=route_input_hashes,
            )
            routes.provenance_sha256 = _stage_provenance(route_input_hashes)
            routes.row = None
            write_sources(workspace, routes.sources)
            expected_sources = tuple(
                source for stage in stages for source in stage.sources
            )
            report = validate_candidate_workspace(
                workspace,
                context=context,
                expected_sources=expected_sources,
                data_sources=data.sources,
                route_sources=routes.sources,
            )
            _check_usage(tuple(item.metrics for item in stages))
            _ensure_deadline(phase_deadline)
        if not report.passed:
            raise CandidateContractError(
                "Candidate failed deterministic pre-build validation.",
                issues=report.issues,
            )
        validation_policy = resolve_candidate_stage_policy("validation")
        validation_input_hashes = tuple(
            canonical_sha256(
                {
                    "artifact_sha256": canonical_sha256(item.artifact),
                    "cache_key": item.cache_key,
                }
            )
            for item in stages
        )
        validation_stage = _Stage(
            artifact=report,
            sources=(),
            cache_key=candidate_cache_key(
                stage="validation",
                schema_version=CANDIDATE_SCHEMA_VERSION,
                prompt_revision=validation_policy.prompt_revision,
                effective_model=validation_policy.model,
                model_family=validation_policy.model_family,
                max_tokens=0,
                temperature=0.0,
                dependency_lock_sha256=dependency_sha,
                input_hashes=validation_input_hashes,
            ),
            provenance_sha256=_stage_provenance(validation_input_hashes),
            metrics=_deterministic_metrics(
                validation_policy,
                started=phase_started,
                cache_hit=False,
            ),
        )
        existing_validation = (
            repository.find_cache(
                request_id=request_id,
                artifact_kind="validation",
                cache_key=validation_stage.cache_key,
            )
            if routes.row is not None
            else None
        )
        if existing_validation is not None:
            cached_report = repository.load_cached(
                existing_validation,
                schema=CandidateValidationReport,
                request_id=request_id,
                provenance_sha256=validation_stage.provenance_sha256,
                parent_artifact_id=routes.row.id,
            )
            if cached_report != report:
                raise ValueError("Candidate validation cache is inconsistent.")
            validation_stage.row = existing_validation
            validation_stage.metrics = candidate_cache_hit_metrics(
                existing_validation,
                latency_ms=validation_stage.metrics.latency_ms,
            )
        stages.append(validation_stage)

        parent_row: CandidateArtifactRecord | None = None
        for stage in stages:
            if stage.row is None:
                stage.row = repository.stage_artifact(
                    artifact=stage.artifact,
                    refs=context.refs,
                    provenance_sha256=stage.provenance_sha256,
                    cache_key=stage.cache_key,
                    metrics=stage.metrics,
                    parent_artifact_id=parent_row.id if parent_row else None,
                    validation={
                        "passed": True,
                        "stage": stage.metrics.stage,
                    },
                    validation_passed=True,
                )
            elif stage.row.parent_artifact_id != (
                parent_row.id if parent_row else None
            ):
                raise ValueError("Candidate cache parent chain changed.")
            parent_row = stage.row

        manifest = source_file_manifest(workspace.staging_path)
        final_path = freeze_candidate_workspace(workspace)
        metrics = tuple(item.metrics for item in stages)
        _row, summary = repository.persist_revision(
            req=req,
            revision_uuid=workspace.revision_uuid,
            status=V2_CANDIDATE_BUILD_PENDING,
            refs=context.refs,
            dependency_lock_sha256=dependency_sha,
            model_manifest=_model_manifest(),
            workspace_relpath=workspace_relpath(final_path),
            file_manifest=manifest,
            artifact_rows=tuple(item.row for item in stages),
            failure={},
            metrics=metrics,
            summary_base={
                **phase3a_summary,
                "candidate_lifecycle": [
                    "candidate_generated",
                    "candidate_build_pending",
                ],
                "candidate_resumed": workspace.resumed,
            },
        )
        db.commit()
        return {"preview_contract": summary}
    except CandidateContractError as exc:
        db.rollback()
        return _persist_failure(
            db=db,
            repository=CandidateRepository(db),
            req=req,
            context=context,
            workspace=workspace,
            dependency_sha=dependency_sha,
            phase3a_summary=phase3a_summary,
            metrics=tuple(item.metrics for item in stages),
            exc=exc,
            contract_failure=True,
        )
    except Exception as exc:
        db.rollback()
        return _persist_failure(
            db=db,
            repository=CandidateRepository(db),
            req=req,
            context=context,
            workspace=workspace,
            dependency_sha=dependency_sha,
            phase3a_summary=phase3a_summary,
            metrics=tuple(item.metrics for item in stages),
            exc=exc,
            contract_failure=False,
        )


__all__ = [
    "CandidateContractError",
    "V2_CANDIDATE_BUILD_PENDING",
    "build_v2_candidate_revision",
]
