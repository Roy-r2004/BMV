"""Two-call Phase 3B immutable Tier 1 candidate boundary."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.application.appspec.source import canonical_json
from app.application.candidate_generation.builder import (
    BuiltCandidateBatch,
    CandidateStageError,
    build_ai_batch,
    combine_generation_and_repair_metrics,
    repair_ai_batch,
)
from app.application.candidate_generation.call_budget import (
    CandidateCallBudget,
    CandidateProviderAttempt,
    CandidateStageCheckpoint,
)
from app.infrastructure.ai_providers.response_parser import ProviderGenerationError
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
from app.application.candidate_generation.component_registry import (
    bindings_prompt_block,
    build_business_component_registry,
    build_required_business_component_bindings,
)
from app.application.candidate_generation.deterministic import (
    CandidateSourceFile,
    build_data_sources,
    build_foundation_sources,
    build_route_sources,
    component_export_symbol,
    dependency_lock_sha256,
    page_export_symbol,
    source_manifest,
)
from app.application.candidate_generation.page_skeleton import (
    build_page_skeleton_source,
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
from app.application.candidate_generation.usage_validation import (
    build_usage_evidence,
    heal_missing_business_component_usage,
    validate_business_component_usage,
)
from app.application.candidate_generation.validation import (
    APPROVED_RUNTIME_PACKAGES,
    batch_sources,
    deterministic_repair_batch,
    heal_missing_transition_hooks,
    validate_candidate_workspace,
    validate_generated_batch,
)
from app.application.candidate_generation.workspace import (
    CandidateWorkspace,
    checkpoint_workspace,
    freeze_candidate_workspace,
    open_candidate_workspace,
    read_source,
    source_file_manifest,
    workspace_relpath,
    write_sources,
)
from app.application.prompts import PromptTemplate
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models import CandidateArtifactRecord, Request
from app.domain.schemas.business_component_usage import (
    BusinessComponentUsageEvidence,
    RequiredBusinessComponentBinding,
)
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
        usage_evidence: BusinessComponentUsageEvidence | None = None,
    ) -> None:
        super().__init__(message)
        self.issues = issues
        self.usage_evidence = usage_evidence


@dataclass
class _Stage:
    artifact: BaseModel
    sources: tuple[CandidateSourceFile, ...]
    cache_key: str
    provenance_sha256: str
    metrics: CandidateStageMetrics
    row: CandidateArtifactRecord | None = None
    repair_used: bool = False
    usage_evidence: BusinessComponentUsageEvidence | None = None
    deterministic_usage_heal_used: bool = False
    required_bindings: tuple[RequiredBusinessComponentBinding, ...] = ()
    resumed_from_checkpoint: bool = False


def _merge_completed_artifacts(
    completed: dict[str, str],
    sources: tuple[CandidateSourceFile, ...],
) -> dict[str, str]:
    merged = dict(completed)
    merged.update({item.path: sha256_text(item.source) for item in sources})
    return merged


def _record_stage_checkpoint(
    *,
    call_budget: CandidateCallBudget,
    stage_name: str,
    provenance_sha256: str,
    artifact: BaseModel | None,
    candidate_revision_uuid: str,
    status: str,
    provider_attempt_id: str = "",
    idempotency_key: str = "",
) -> None:
    call_budget.record_checkpoint(
        CandidateStageCheckpoint(
            substage=stage_name,
            input_hash=provenance_sha256,
            output_hash=canonical_sha256(artifact) if artifact is not None else "",
            status=status,
            provider_attempt_id=provider_attempt_id,
            idempotency_key=(
                idempotency_key
                or f"{candidate_revision_uuid}:{stage_name}:{status}"
            ),
        )
    )


def _serialize_stage_resume_state(stage: _Stage) -> dict[str, Any]:
    return {
        "status": "completed",
        "artifact": stage.artifact.model_dump(mode="json"),
        "cache_key": stage.cache_key,
        "provenance_sha256": stage.provenance_sha256,
        "metrics": stage.metrics.model_dump(mode="json"),
        "repair_used": stage.repair_used,
        "deterministic_usage_heal_used": (
            stage.deterministic_usage_heal_used
        ),
        "provider_attempt_id": "",
        "idempotency_key": "",
        "source_hashes": {
            item.path: sha256_text(item.source) for item in stage.sources
        },
    }


def _persist_in_flight_ai_stage(
    *,
    workspace: CandidateWorkspace,
    upstream_sha: str,
    completed_artifacts: dict[str, str],
    completed_stage_state: dict[str, Any],
    call_budget: CandidateCallBudget,
    stage_name: str,
    cache_key: str,
    provenance_sha256: str,
    provider_attempt_id: str,
    idempotency_key: str,
    provider: str,
    model: str,
) -> None:
    _record_stage_checkpoint(
        call_budget=call_budget,
        stage_name=stage_name,
        provenance_sha256=provenance_sha256,
        artifact=None,
        candidate_revision_uuid=workspace.revision_uuid,
        status="in_flight",
        provider_attempt_id=provider_attempt_id,
        idempotency_key=idempotency_key,
    )
    completed_stage_state[stage_name] = {
        "status": "in_flight",
        "cache_key": cache_key,
        "provenance_sha256": provenance_sha256,
        "provider_attempt_id": provider_attempt_id,
        "idempotency_key": idempotency_key,
        "provider": provider,
        "model": model,
    }
    checkpoint_workspace(
        workspace,
        upstream_sha256=upstream_sha,
        completed_artifacts=completed_artifacts,
        completed_stage_state=completed_stage_state,
        candidate_call_ledger=call_budget.snapshot(),
        candidate_provider_attempts=call_budget.attempts_snapshot(),
    )


def _persist_completed_ai_stage(
    *,
    workspace: CandidateWorkspace,
    upstream_sha: str,
    completed_artifacts: dict[str, str],
    completed_stage_state: dict[str, Any],
    call_budget: CandidateCallBudget,
    stage: _Stage,
    status: str,
    provider_attempt_id: str = "",
    idempotency_key: str = "",
) -> None:
    existing = completed_stage_state.get(stage.metrics.stage) or {}
    provider_attempt_id = provider_attempt_id or str(
        existing.get("provider_attempt_id") or ""
    )
    idempotency_key = idempotency_key or str(
        existing.get("idempotency_key") or ""
    )
    _record_stage_checkpoint(
        call_budget=call_budget,
        stage_name=stage.metrics.stage,
        provenance_sha256=stage.provenance_sha256,
        artifact=stage.artifact,
        candidate_revision_uuid=workspace.revision_uuid,
        status=status,
        provider_attempt_id=provider_attempt_id,
        idempotency_key=idempotency_key,
    )
    payload = _serialize_stage_resume_state(stage)
    payload["status"] = status
    payload["provider_attempt_id"] = provider_attempt_id
    payload["idempotency_key"] = idempotency_key
    if status != "completed":
        payload["source_hashes"] = {}
    completed_stage_state[stage.metrics.stage] = payload
    checkpoint_workspace(
        workspace,
        upstream_sha256=upstream_sha,
        completed_artifacts=completed_artifacts,
        completed_stage_state=completed_stage_state,
        candidate_call_ledger=call_budget.snapshot(),
        candidate_provider_attempts=call_budget.attempts_snapshot(),
    )


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
        try:
            cached = repository.load_cached(
                row,
                schema=CandidateArtifactManifest,
                request_id=context.refs.request_id,
                provenance_sha256=provenance,
                parent_artifact_id=parent_row.id if parent_row else None,
            )
        except ValueError:
            # Stale or provenance-mismatched row under the same cache key.
            row.cacheable = False
            repository.db.flush()
            row = None
            cached = None
        else:
            if cached != manifest:
                # Builder output changed under an unchanged cache key (for
                # example after a local deterministic fix). Invalidate and
                # rebuild instead of failing the whole candidate attempt.
                row.cacheable = False
                repository.db.flush()
                row = None
                cached = None
        if row is not None and cached is not None:
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
    """Lean candidate inputs.

    Smoke #34 showed dumping the full AppSpec + strategy + IA into the
    business_components prompt produced ~38k input tokens against DeepSeek's
    32k context. Keep authoritative Tier-1 contracts only; omit narrative
    documents already projected into those contracts.
    """

    design_dna = context.composition.design_dna
    design_tokens = {
        "composition_hierarchy": design_dna.composition.hierarchy,
        "composition_emphasis": design_dna.composition.emphasis,
        "public_surface_density": design_dna.density.public_surface,
        "operations_surface_density": design_dna.density.operations_surface,
        "motion_character": design_dna.motion.character,
        "reduced_motion": design_dna.motion.reduced_motion,
        "avoid_list": list(design_dna.avoid_list),
        "color_tokens": [
            {
                "semantic_role": token.semantic_role,
                "direction": token.direction,
                "contrast_intent": token.contrast_intent,
            }
            for token in design_dna.color_tokens
        ],
        "typography": {
            "voice": design_dna.typography.voice,
            "display_direction": design_dna.typography.display_direction,
            "body_direction": design_dna.typography.body_direction,
        },
    }
    return {
        "page_purpose_contract": context.page_purpose.model_dump(mode="json"),
        "business_component_plan": context.business_components.model_dump(
            mode="json"
        ),
        "content_data_plan": context.content_data.model_dump(mode="json"),
        "interaction_contract": context.interactions.model_dump(mode="json"),
        "component_dependency_graph": context.dependency_graph.model_dump(
            mode="json"
        ),
        "design_dna_tokens": design_tokens,
        "allowed_dependencies": sorted(APPROVED_RUNTIME_PACKAGES),
        "deterministic_data_export_paths": [
            "src/generated/content-data.ts",
            "src/generated/content-data.json",
            "src/generated/canonical-contracts.ts",
        ],
        "prompt_projection_meta": {
            "revision": "2026-07-26.candidate-prompt.2",
            "omitted_sections": [
                "full_raw_app_spec",
                "product_strategy_v2_narrative",
                "full_information_architecture",
                "full_design_dna_document",
            ],
            "source_refs": {
                "app_spec_sha256": (
                    context.refs.composition_contract_refs.design_contract_refs.app_spec_ref.sha256
                ),
                "page_purpose_sha256": context.refs.page_purpose_ref.sha256,
                "business_component_plan_sha256": (
                    context.refs.business_component_plan_ref.sha256
                ),
                "content_data_plan_sha256": (
                    context.refs.content_data_plan_ref.sha256
                ),
                "interaction_contract_sha256": (
                    context.refs.interaction_contract_ref.sha256
                ),
                "component_dependency_graph_sha256": (
                    context.refs.component_dependency_graph_ref.sha256
                ),
            },
        },
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


def _page_bindings_for_component_batch(
    *,
    context: CandidateContext,
    component_batch: GeneratedCandidateBatch,
) -> tuple[
    tuple[RequiredBusinessComponentBinding, ...],
    dict[str, Any],
]:
    registry, registry_issues = build_business_component_registry(
        context=context,
        component_batch=component_batch,
    )
    if registry_issues or registry is None:
        raise CandidateContractError(
            "Business-component registry failed before page generation.",
            issues=registry_issues,
        )
    bindings, binding_issues = build_required_business_component_bindings(
        context=context,
        registry=registry,
    )
    if binding_issues:
        raise CandidateContractError(
            "Required business-component bindings are invalid.",
            issues=binding_issues,
        )
    page_skeletons = {
        page.page_id: build_page_skeleton_source(
            page=page,
            bindings=tuple(
                item for item in bindings if item.page_id == page.page_id
            ),
        )
        for page in context.page_purpose.pages
    }
    prompt_extras = {
        "business_component_registry": registry.model_dump(mode="json"),
        "required_business_component_bindings": bindings_prompt_block(bindings),
        "page_skeletons": page_skeletons,
        "required_component_exports": {
            item.component_id: component_export_symbol(item.component_id)
            for item in context.business_components.components
        },
    }
    return bindings, prompt_extras


def _apply_page_usage_guards(
    *,
    batch: GeneratedCandidateBatch,
    context: CandidateContext,
    bindings: tuple[RequiredBusinessComponentBinding, ...],
    candidate_revision_uuid: str,
    ai_repair_used: bool,
    allow_deterministic_heal: bool,
) -> tuple[
    GeneratedCandidateBatch,
    tuple[CandidateValidationIssue, ...],
    BusinessComponentUsageEvidence,
    bool,
]:
    component_paths = {item.component_module_path for item in bindings}
    evidence_items, usage_issues = validate_business_component_usage(
        batch=batch,
        bindings=bindings,
        component_paths=component_paths,
        repair_attempt=0,
    )
    heal_used = False
    if (
        allow_deterministic_heal
        and usage_issues
        and any(
            item.code == "missing_business_component_usage"
            for item in usage_issues
        )
    ):
        batch, before_hashes, heal_used = heal_missing_business_component_usage(
            batch=batch,
            bindings=bindings,
            evidence=evidence_items,
        )
        if heal_used:
            evidence_items, usage_issues = validate_business_component_usage(
                batch=batch,
                bindings=bindings,
                component_paths=component_paths,
                repair_attempt=1,
                previous_hashes=before_hashes,
            )

    other_issues = [
        item
        for item in validate_generated_batch(
            batch,
            context=context,
            required_bindings=bindings,
        )
        if item.code != "missing_business_component_usage"
        and not item.code.startswith("business_component_usage_")
    ]
    merged = list(other_issues) + list(usage_issues)

    evidence = build_usage_evidence(
        request_id=context.refs.request_id,
        candidate_revision_uuid=candidate_revision_uuid,
        component_plan_hash=context.refs.business_component_plan_ref.sha256,
        bindings=bindings,
        items=evidence_items,
        deterministic_heal_used=heal_used,
        ai_repair_used=ai_repair_used,
    )
    return batch, tuple(merged), evidence, heal_used


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
    workspace: CandidateWorkspace,
    upstream_sha: str,
    completed_artifacts: dict[str, str],
    completed_stage_state: dict[str, Any],
    component_batch: GeneratedCandidateBatch | None = None,
    candidate_revision_uuid: str = "",
    call_budget: CandidateCallBudget | None = None,
    resume_stage_state: dict[str, Any] | None = None,
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
    page_bindings: tuple[RequiredBusinessComponentBinding, ...] = ()
    page_prompt_extras: dict[str, Any] = {}
    if stage == "pages":
        if component_batch is None:
            raise ValueError("Page generation requires the component batch.")
        page_bindings, page_prompt_extras = _page_bindings_for_component_batch(
            context=context,
            component_batch=component_batch,
        )

    resume_checkpoint = (
        call_budget.snapshot().get("checkpoints", {}).get(stage)
        if call_budget is not None
        else None
    )
    resume_status = (
        str(resume_stage_state.get("status") or "")
        if isinstance(resume_stage_state, dict)
        else ""
    )
    if (
        resume_status == "in_flight"
        and isinstance(resume_stage_state, dict)
        and resume_stage_state.get("cache_key") == cache_key
        and resume_stage_state.get("provenance_sha256") == provenance
    ):
        raise CandidateStageError(
            (
                f"{stage} found an in-flight paid provider attempt without a "
                "durable output checkpoint; refusing to retry ambiguously."
            ),
            stage=stage,
            provider_error_code="candidate_provider_attempt_in_flight",
        )
    if (
        isinstance(resume_stage_state, dict)
        and resume_stage_state.get("cache_key") == cache_key
        and resume_stage_state.get("provenance_sha256") == provenance
        and resume_status == "completed"
    ):
        batch = GeneratedCandidateBatch.model_validate(
            resume_stage_state.get("artifact") or {}
        )
        checkpoint_output_hash = str(
            (resume_checkpoint or {}).get("output_hash") or ""
        )
        if checkpoint_output_hash != canonical_sha256(batch):
            raise CandidateStageError(
                f"{stage} checkpoint output hash is corrupt.",
                stage=stage,
                provider_error_code="candidate_checkpoint_corrupt",
            )
        metrics = CandidateStageMetrics.model_validate(
            resume_stage_state.get("metrics") or {}
        )
        source_hashes = dict(resume_stage_state.get("source_hashes") or {})
        for source in batch_sources(batch):
            expected_sha = source_hashes.get(source.path) or completed_artifacts.get(
                source.path
            )
            if not expected_sha or sha256_text(
                read_source(workspace, source.path)
            ) != expected_sha:
                raise CandidateStageError(
                    f"{stage} checkpoint source hash is corrupt.",
                    stage=stage,
                    provider_error_code="candidate_checkpoint_corrupt",
                )
        if stage == "pages":
            batch, issues, evidence, _heal_used = _apply_page_usage_guards(
                batch=batch,
                context=context,
                bindings=page_bindings,
                candidate_revision_uuid=candidate_revision_uuid,
                ai_repair_used=bool(resume_stage_state.get("repair_used")),
                allow_deterministic_heal=False,
            )
            heal_used = bool(
                resume_stage_state.get("deterministic_usage_heal_used")
            )
            heal_used = heal_used or _heal_used
        else:
            issues = validate_generated_batch(batch, context=context)
            evidence = None
            heal_used = False
        if issues:
            raise ValueError("Checkpointed AI candidate batch is invalid.")
        return _Stage(
            artifact=batch,
            sources=batch_sources(batch),
            cache_key=cache_key,
            provenance_sha256=provenance,
            metrics=metrics,
            row=None,
            repair_used=bool(resume_stage_state.get("repair_used")),
            usage_evidence=evidence,
            deterministic_usage_heal_used=heal_used,
            required_bindings=page_bindings,
            resumed_from_checkpoint=True,
        )

    resume_built: Any | None = None
    if (
        isinstance(resume_stage_state, dict)
        and resume_stage_state.get("cache_key") == cache_key
        and resume_stage_state.get("provenance_sha256") == provenance
        and resume_status == "parsed_output"
    ):
        batch = GeneratedCandidateBatch.model_validate(
            resume_stage_state.get("artifact") or {}
        )
        checkpoint_output_hash = str(
            (resume_checkpoint or {}).get("output_hash") or ""
        )
        if checkpoint_output_hash != canonical_sha256(batch):
            raise CandidateStageError(
                f"{stage} parsed-output checkpoint is corrupt.",
                stage=stage,
                provider_error_code="candidate_checkpoint_corrupt",
            )
        resume_built = {
            "batch": batch,
            "metrics": CandidateStageMetrics.model_validate(
                resume_stage_state.get("metrics") or {}
            ),
            "provider_attempt_id": str(
                resume_stage_state.get("provider_attempt_id") or ""
            ),
            "idempotency_key": str(
                resume_stage_state.get("idempotency_key") or ""
            ),
        }

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
        if stage == "pages":
            batch, issues, evidence, heal_used = _apply_page_usage_guards(
                batch=batch,
                context=context,
                bindings=page_bindings,
                candidate_revision_uuid=candidate_revision_uuid,
                ai_repair_used=False,
                allow_deterministic_heal=True,
            )
        else:
            issues = validate_generated_batch(batch, context=context)
            evidence = None
            heal_used = False
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
            usage_evidence=evidence,
            deterministic_usage_heal_used=heal_used,
            required_bindings=page_bindings,
        )

    prompt_inputs = _common_prompt_inputs(context)
    if stage == "pages":
        prompt_inputs["generated_business_components"] = (
            component_batch.model_dump(mode="json")
        )
        prompt_inputs["required_page_exports"] = {
            page.page_id: page_export_symbol(page.page_id)
            for page in context.page_purpose.pages
        }
        prompt_inputs.update(page_prompt_extras)
    elif stage == "business_components":
        prompt_inputs["required_component_exports"] = {
            item.component_id: component_export_symbol(item.component_id)
            for item in context.business_components.components
        }
        prompt_inputs["required_component_modules"] = {
            item.component_id: (
                f"src/components/business/"
                f"{component_export_symbol(item.component_id)}.tsx"
            )
            for item in context.business_components.components
        }
    if resume_built is None:
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
            call_budget=call_budget,
            candidate_revision_uuid=candidate_revision_uuid,
            on_in_flight=(
                None
                if call_budget is None
                else lambda payload: _persist_in_flight_ai_stage(
                    workspace=workspace,
                    upstream_sha=upstream_sha,
                    completed_artifacts=completed_artifacts,
                    completed_stage_state=completed_stage_state,
                    call_budget=call_budget,
                    stage_name=stage,
                    cache_key=cache_key,
                    provenance_sha256=provenance,
                    provider_attempt_id=str(payload.get("attempt_id") or ""),
                    idempotency_key=str(
                        payload.get("idempotency_key") or ""
                    ),
                    provider=str(payload.get("provider") or ""),
                    model=str(payload.get("model") or ""),
                )
            ),
        )
        parsed_stage = _Stage(
            artifact=built.batch,
            sources=batch_sources(built.batch),
            cache_key=cache_key,
            provenance_sha256=provenance,
            metrics=built.metrics,
        )
        if call_budget is not None:
            _persist_completed_ai_stage(
                workspace=workspace,
                upstream_sha=upstream_sha,
                completed_artifacts=completed_artifacts,
                completed_stage_state=completed_stage_state,
                call_budget=call_budget,
                stage=parsed_stage,
                status="parsed_output",
                provider_attempt_id=built.provider_attempt_id,
                idempotency_key=built.idempotency_key,
            )
    else:
        built = BuiltCandidateBatch(**resume_built)
    batch = deterministic_repair_batch(built.batch)
    repair_used = False
    metrics = built.metrics
    heal_used = False
    evidence: BusinessComponentUsageEvidence | None = None

    if stage == "pages":
        batch, issues, evidence, heal_used = _apply_page_usage_guards(
            batch=batch,
            context=context,
            bindings=page_bindings,
            candidate_revision_uuid=candidate_revision_uuid,
            ai_repair_used=False,
            allow_deterministic_heal=True,
        )
    else:
        batch, transition_heal_used = heal_missing_transition_hooks(
            batch,
            context=context,
        )
        heal_used = transition_heal_used
        issues = validate_generated_batch(batch, context=context)

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
                "required_business_component_bindings": (
                    bindings_prompt_block(page_bindings)
                    if stage == "pages"
                    else {}
                ),
            },
            ai_provider=ai_provider,
            template_renderer=template_renderer,
            prompt_template=PromptTemplate.V2_CANDIDATE_REPAIR,
            phase_deadline=phase_deadline,
            call_budget=call_budget,
            candidate_revision_uuid=candidate_revision_uuid,
        )
        batch = deterministic_repair_batch(repaired.batch)
        repair_used = True
        if stage == "pages":
            batch, issues, evidence, post_heal = _apply_page_usage_guards(
                batch=batch,
                context=context,
                bindings=page_bindings,
                candidate_revision_uuid=candidate_revision_uuid,
                ai_repair_used=True,
                allow_deterministic_heal=not heal_used,
            )
            heal_used = heal_used or post_heal
        else:
            batch, transition_heal_used = heal_missing_transition_hooks(
                batch,
                context=context,
            )
            heal_used = heal_used or transition_heal_used
            issues = validate_generated_batch(batch, context=context)
        if issues:
            raise CandidateContractError(
                f"{stage} failed strict batch validation.",
                issues=issues,
                usage_evidence=evidence,
            )
        metrics = combine_generation_and_repair_metrics(
            metrics,
            repaired.metrics,
        )
    return _Stage(
        artifact=batch,
        sources=batch_sources(batch),
        cache_key=cache_key,
        provenance_sha256=provenance,
        metrics=metrics,
        row=None,
        repair_used=repair_used,
        usage_evidence=evidence,
        deterministic_usage_heal_used=heal_used,
        required_bindings=page_bindings,
        resumed_from_checkpoint=False,
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
            "business_component_usage_missing_props",
            "business_component_usage_ambiguous_usage",
            "business_component_usage_invalid_binding",
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
    candidate_revision_uuid: str = "",
    call_budget: CandidateCallBudget | None = None,
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
            "required_business_component_bindings": (
                bindings_prompt_block(stage.required_bindings)
                if stage_name == "pages"
                else {}
            ),
        },
        ai_provider=ai_provider,
        template_renderer=template_renderer,
        prompt_template=PromptTemplate.V2_CANDIDATE_REPAIR,
        phase_deadline=phase_deadline,
        call_budget=call_budget,
        candidate_revision_uuid=candidate_revision_uuid,
    )
    batch = deterministic_repair_batch(repaired.batch)
    if stage_name == "pages" and stage.required_bindings:
        batch, batch_issues, evidence, heal_used = _apply_page_usage_guards(
            batch=batch,
            context=context,
            bindings=stage.required_bindings,
            candidate_revision_uuid=candidate_revision_uuid,
            ai_repair_used=True,
            allow_deterministic_heal=not stage.deterministic_usage_heal_used,
        )
        stage.usage_evidence = evidence
        stage.deterministic_usage_heal_used = (
            stage.deterministic_usage_heal_used or heal_used
        )
    else:
        if stage_name == "business_components":
            batch, transition_heal_used = heal_missing_transition_hooks(
                batch,
                context=context,
            )
            stage.deterministic_usage_heal_used = (
                stage.deterministic_usage_heal_used or transition_heal_used
            )
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
        "phase4_ran": False,
    }
    if isinstance(exc, CandidateContractError):
        payload["issues"] = [
            item.model_dump(mode="json") for item in exc.issues
        ]
    if isinstance(exc, CandidateStageError):
        payload["stage"] = exc.stage
        payload["diagnostics"] = list(exc.diagnostics)
        if exc.provider_error_code:
            payload["provider_error_code"] = exc.provider_error_code
            payload["root_cause"] = "candidate_provider_failure"
            payload["phase4_note"] = (
                "Phase 4 did not run; phase4_status_precondition is only a "
                "downstream guard if orchestration incorrectly continues."
            )
        if exc.provider_diagnostics:
            payload["provider_diagnostics"] = exc.provider_diagnostics
    if isinstance(exc, ProviderGenerationError):
        payload.update(exc.to_failure_dict())
    return payload


def _persist_completed_stage_rows(
    *,
    repository: CandidateRepository,
    context: CandidateContext,
    stages: list[_Stage],
) -> tuple[CandidateArtifactRecord | None, ...]:
    """Persist completed substages so a later resume can reuse them."""
    parent_row: CandidateArtifactRecord | None = None
    rows: list[CandidateArtifactRecord | None] = []
    for stage in stages:
        if stage.row is None:
            try:
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
                        "checkpoint": True,
                    },
                    validation_passed=True,
                )
            except Exception:
                rows.append(None)
                continue
        rows.append(stage.row)
        parent_row = stage.row
    padded: list[CandidateArtifactRecord | None] = list(rows)
    while len(padded) < 6:
        padded.append(None)
    return tuple(padded[:6])


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
    usage_evidence: BusinessComponentUsageEvidence | None = None,
    stages: list[_Stage] | None = None,
    call_budget: CandidateCallBudget | None = None,
) -> dict:
    # Keep staging + .attempt.json so parsed AI output remains resumable.
    # Freezing on failure previously deleted attempt metadata and forced
    # paid provider stages to re-run under a fresh call budget.
    final_path = (
        workspace.staging_path
        if workspace.staging_path.exists()
        else workspace.final_path
    )
    manifest = source_file_manifest(final_path)
    failure = _failure_payload(
        exc,
        kind="contract_validation" if contract_failure else "generation",
    )
    try:
        artifact_rows: tuple[CandidateArtifactRecord | None, ...] = (
            None,
            None,
            None,
            None,
            None,
            None,
        )
        if stages:
            artifact_rows = _persist_completed_stage_rows(
                repository=repository,
                context=context,
                stages=stages,
            )
        summary_base = dict(phase3a_summary)
        summary_base["candidate_resumed"] = workspace.resumed
        if usage_evidence is not None:
            summary_base["business_component_usage_evidence"] = (
                usage_evidence.model_dump(mode="json")
            )
        if call_budget is not None:
            summary_base["candidate_call_ledger"] = call_budget.snapshot()
            summary_base["candidate_provider_attempts"] = (
                call_budget.attempts_snapshot()
            )
            summary_base["candidate_stage_checkpoints"] = call_budget.snapshot().get(
                "checkpoints"
            )
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
            artifact_rows=artifact_rows,
            failure=failure,
            metrics=metrics,
            summary_base=summary_base,
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
    resume_state = workspace.resume_state or {}
    completed_stage_state = dict(
        resume_state.get("completed_stage_state") or {}
    )
    in_flight_stage = next(
        (
            name
            for name, payload in completed_stage_state.items()
            if isinstance(payload, dict)
            and str(payload.get("status") or "") == "in_flight"
        ),
        "",
    )
    completed: dict[str, str] = dict(
        resume_state.get("completed_artifacts") or {}
    )
    stages: list[_Stage] = []
    call_budget = CandidateCallBudget.create()
    try:
        if workspace.resume_invalid_reason:
            mismatch_stage = "candidate_generation"
            if "src/pages/" in workspace.resume_invalid_reason:
                mismatch_stage = "pages"
            elif "src/components/business/" in workspace.resume_invalid_reason:
                mismatch_stage = "business_components"
            raise CandidateStageError(
                (
                    "Candidate attempt checkpoint is unreadable or corrupt."
                    if workspace.resume_invalid_reason
                    == "attempt_checkpoint_unreadable"
                    else "Candidate checkpoint source hashes are corrupt."
                ),
                stage=mismatch_stage,
                provider_error_code="candidate_checkpoint_corrupt",
            )
        if in_flight_stage:
            raise CandidateStageError(
                (
                    f"{in_flight_stage} has an in-flight paid provider call "
                    "without a durable output checkpoint."
                ),
                stage=in_flight_stage,
                provider_error_code="candidate_provider_attempt_in_flight",
            )
        call_budget = CandidateCallBudget.restore(
            snapshot=resume_state.get("candidate_call_ledger"),
            attempts=resume_state.get("candidate_provider_attempts"),
        )
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
        completed = _merge_completed_artifacts(
            completed, foundation.sources
        )
        call_budget.record_checkpoint(
            CandidateStageCheckpoint(
                substage="foundation",
                input_hash=canonical_sha256(list(foundation_input_hashes)),
                output_hash=canonical_sha256(foundation.artifact),
                status="completed",
                idempotency_key=f"{workspace.revision_uuid}:foundation",
            )
        )
        checkpoint_workspace(
            workspace,
            upstream_sha256=upstream_sha,
            completed_artifacts=completed,
            completed_stage_state=completed_stage_state,
            candidate_call_ledger=call_budget.snapshot(),
            candidate_provider_attempts=call_budget.attempts_snapshot(),
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
        completed = _merge_completed_artifacts(completed, data.sources)
        call_budget.record_checkpoint(
            CandidateStageCheckpoint(
                substage="data_exports",
                input_hash=canonical_sha256(list(data_input_hashes)),
                output_hash=canonical_sha256(data.artifact),
                status="completed",
                idempotency_key=f"{workspace.revision_uuid}:data_exports",
            )
        )
        checkpoint_workspace(
            workspace,
            upstream_sha256=upstream_sha,
            completed_artifacts=completed,
            completed_stage_state=completed_stage_state,
            candidate_call_ledger=call_budget.snapshot(),
            candidate_provider_attempts=call_budget.attempts_snapshot(),
        )
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
            workspace=workspace,
            upstream_sha=upstream_sha,
            completed_artifacts=completed,
            completed_stage_state=completed_stage_state,
            candidate_revision_uuid=workspace.revision_uuid,
            call_budget=call_budget,
            resume_stage_state=completed_stage_state.get(
                "business_components"
            ),
        )
        stages.append(components)
        write_sources(workspace, components.sources)
        completed = _merge_completed_artifacts(completed, components.sources)
        _persist_completed_ai_stage(
            workspace=workspace,
            upstream_sha=upstream_sha,
            completed_artifacts=completed,
            completed_stage_state=completed_stage_state,
            call_budget=call_budget,
            stage=components,
            status="completed",
        )
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
            workspace=workspace,
            upstream_sha=upstream_sha,
            completed_artifacts=completed,
            completed_stage_state=completed_stage_state,
            component_batch=components.artifact,
            candidate_revision_uuid=workspace.revision_uuid,
            call_budget=call_budget,
            resume_stage_state=completed_stage_state.get("pages"),
        )
        stages.append(pages)
        write_sources(workspace, pages.sources)
        completed = _merge_completed_artifacts(completed, pages.sources)
        _persist_completed_ai_stage(
            workspace=workspace,
            upstream_sha=upstream_sha,
            completed_artifacts=completed,
            completed_stage_state=completed_stage_state,
            call_budget=call_budget,
            stage=pages,
            status="completed",
        )
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
            candidate_revision_uuid=workspace.revision_uuid,
            call_budget=call_budget,
        )
        repaired_pages = _repair_stage_after_gate(
            stage=pages,
            stage_name="pages",
            context=context,
            report=report,
            ai_provider=ai_provider,
            template_renderer=template_renderer,
            phase_deadline=phase_deadline,
            candidate_revision_uuid=workspace.revision_uuid,
            call_budget=call_budget,
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
        usage_evidence = next(
            (
                item.usage_evidence
                for item in stages
                if item.usage_evidence is not None
            ),
            None,
        )
        summary_base = {
            **phase3a_summary,
            "candidate_lifecycle": [
                "candidate_generated",
                "candidate_build_pending",
            ],
            "candidate_resumed": workspace.resumed,
            "candidate_call_ledger": call_budget.snapshot(),
            "candidate_provider_attempts": call_budget.attempts_snapshot(),
            "candidate_stage_checkpoints": call_budget.snapshot().get(
                "checkpoints"
            ),
        }
        if usage_evidence is not None:
            summary_base["business_component_usage_evidence"] = (
                usage_evidence.model_dump(mode="json")
            )
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
            summary_base=summary_base,
        )
        db.commit()
        return {"preview_contract": summary}
    except CandidateContractError as exc:
        db.rollback()
        usage_evidence = exc.usage_evidence or next(
            (
                item.usage_evidence
                for item in stages
                if item.usage_evidence is not None
            ),
            None,
        )
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
            usage_evidence=usage_evidence,
            stages=stages,
            call_budget=call_budget,
        )
    except Exception as exc:
        db.rollback()
        usage_evidence = next(
            (
                item.usage_evidence
                for item in stages
                if item.usage_evidence is not None
            ),
            None,
        )
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
            usage_evidence=usage_evidence,
            stages=stages,
            call_budget=call_budget,
        )


__all__ = [
    "CandidateContractError",
    "V2_CANDIDATE_BUILD_PENDING",
    "build_v2_candidate_revision",
]
