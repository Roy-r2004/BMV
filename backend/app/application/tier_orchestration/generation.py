"""Byte-preserving cumulative Tier 2 candidate generation."""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from app.application.appspec.source import canonical_json
from app.application.candidate_generation.builder import (
    build_ai_batch,
    combine_generation_and_repair_metrics,
    repair_ai_batch,
)
from app.application.candidate_generation.cache import (
    canonical_sha256,
    sha256_text,
)
from app.application.candidate_generation.context import CandidateContext
from app.application.candidate_generation.deterministic import (
    CandidateSourceFile,
    build_data_sources,
    build_route_sources,
    source_manifest,
)
from app.application.candidate_generation.repository import (
    CandidateRepository,
    candidate_cache_hit_metrics,
)
from app.application.candidate_generation.validation import (
    batch_sources,
    deterministic_repair_batch,
    validate_candidate_workspace,
)
from app.application.candidate_generation.workspace import (
    checkpoint_workspace,
    freeze_candidate_workspace,
    open_candidate_workspace,
    source_file_manifest,
    workspace_relpath,
    write_sources,
)
from app.application.prompts import PromptTemplate
from app.application.tier_orchestration.policy import (
    tier_2_generation_policy,
    tier_2_static_repair_policy,
    tier_3_generation_policy,
    tier_3_static_repair_policy,
)
from app.application.tier_orchestration.preservation import (
    finalize_preservation_audit,
)
from app.application.tier_orchestration.validation import (
    Tier2GenerationContractError,
    assert_accepted_workspace_unchanged,
    validate_delta_batch,
    verify_preservation_after_generation,
)
from app.core.config import settings
from app.domain.models import (
    CandidateArtifactRecord,
    CandidateRevisionRecord,
    Request,
)
from app.domain.schemas.preview_candidate import (
    CandidateArtifactManifest,
    CandidateStageMetrics,
    CandidateUpstreamRefs,
    GeneratedCandidateBatch,
    GeneratedCandidateFile,
)
from app.domain.schemas.tier_orchestration import (
    Tier2ExtensionContracts,
    Tier2PreservationManifest,
    Tier3ExtensionContracts,
    Tier3PreservationManifest,
)


@dataclass(frozen=True)
class BuiltTier2Candidate:
    candidate: CandidateRevisionRecord
    summary: dict
    context: CandidateContext
    preservation: Tier2PreservationManifest | Tier3PreservationManifest
    validation_report: object
    metrics: tuple[CandidateStageMetrics, ...]
    resumed: bool
    generation_cache_hits: int


BuiltTier3Candidate = BuiltTier2Candidate


@dataclass(frozen=True)
class _TierGenerationProfile:
    target_tier: int
    policy_revision: str
    component_model: str
    page_model: str
    repair_model: str
    component_prompt_revision: str
    page_prompt_revision: str
    max_output_tokens: int
    max_cost_usd: float
    max_calls: int
    max_wall_seconds: int
    component_prompt: PromptTemplate
    page_prompt: PromptTemplate


def _generation_profile(target_tier: int) -> _TierGenerationProfile:
    if target_tier == 2:
        return _TierGenerationProfile(
            target_tier=2,
            policy_revision=settings.V2_TIER2_GENERATION_POLICY_REVISION,
            component_model=settings.V2_TIER2_COMPONENT_MODEL,
            page_model=settings.V2_TIER2_PAGE_MODEL,
            repair_model=settings.V2_TIER2_REPAIR_MODEL,
            component_prompt_revision=(
                settings.V2_TIER2_COMPONENT_PROMPT_REVISION
            ),
            page_prompt_revision=settings.V2_TIER2_PAGE_PROMPT_REVISION,
            max_output_tokens=settings.V2_TIER2_MAX_OUTPUT_TOKENS,
            max_cost_usd=settings.V2_TIER2_MAX_COST_USD,
            max_calls=settings.V2_TIER2_MAX_CALLS,
            max_wall_seconds=settings.V2_TIER2_MAX_WALL_SECONDS,
            component_prompt=PromptTemplate.V2_TIER2_COMPONENTS,
            page_prompt=PromptTemplate.V2_TIER2_PAGES,
        )
    if target_tier == 3:
        return _TierGenerationProfile(
            target_tier=3,
            policy_revision=settings.V2_TIER3_GENERATION_POLICY_REVISION,
            component_model=settings.V2_TIER3_COMPONENT_MODEL,
            page_model=settings.V2_TIER3_PAGE_MODEL,
            repair_model=settings.V2_TIER3_REPAIR_MODEL,
            component_prompt_revision=(
                settings.V2_TIER3_COMPONENT_PROMPT_REVISION
            ),
            page_prompt_revision=settings.V2_TIER3_PAGE_PROMPT_REVISION,
            max_output_tokens=settings.V2_TIER3_MAX_OUTPUT_TOKENS,
            max_cost_usd=settings.V2_TIER3_MAX_COST_USD,
            max_calls=settings.V2_TIER3_MAX_CALLS,
            max_wall_seconds=settings.V2_TIER3_MAX_WALL_SECONDS,
            component_prompt=PromptTemplate.V2_TIER3_COMPONENTS,
            page_prompt=PromptTemplate.V2_TIER3_PAGES,
        )
    raise ValueError("Cumulative generation target must be Tier 2 or Tier 3")


def _metric(
    stage: str,
    started: float,
    profile: _TierGenerationProfile,
) -> CandidateStageMetrics:
    return CandidateStageMetrics(
        stage=stage,
        effective_model="deterministic",
        provider="deterministic",
        model_family="deterministic",
        prompt_revision=profile.policy_revision,
        cache_hit=False,
        provider_call_count=0,
        repair_call_count=0,
        repair_reason=None,
        transport_retry_count=0,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        cost_usd=0.0,
        latency_ms=max(0, int((time.monotonic() - started) * 1000)),
    )


def _artifact_rows(
    db,
    revision: CandidateRevisionRecord,
) -> tuple[CandidateArtifactRecord, ...]:
    ids = (
        revision.foundation_artifact_id,
        revision.data_artifact_id,
        revision.component_artifact_id,
        revision.page_artifact_id,
        revision.route_artifact_id,
        revision.validation_artifact_id,
    )
    rows = tuple(db.get(CandidateArtifactRecord, item) for item in ids)
    if any(row is None for row in rows):
        raise ValueError("Accepted Tier 1 artifact chain is incomplete")
    typed = tuple(rows)
    if (
        typed[0].parent_artifact_id is not None
        or any(
            row.parent_artifact_id != typed[index - 1].id
            for index, row in enumerate(typed[1:], start=1)
        )
    ):
        raise ValueError("Accepted Tier 1 artifact chain is invalid")
    return typed


def _source_metadata(
    rows: tuple[CandidateArtifactRecord, ...],
) -> dict[str, tuple[str, tuple[str, ...]]]:
    result: dict[str, tuple[str, tuple[str, ...]]] = {}
    for row in rows:
        payload = json.loads(row.artifact_json)
        try:
            manifest = CandidateArtifactManifest.model_validate(payload)
            for item in manifest.files:
                result[item.path] = (
                    item.file_kind,
                    item.owner_contract_ids,
                )
            continue
        except Exception:
            pass
        try:
            batch = GeneratedCandidateBatch.model_validate(payload)
        except Exception:
            continue
        for item in batch.files:
            result[item.path] = (
                item.file_kind,
                item.owner_contract_ids,
            )
    return result


def _accepted_sources(
    workspace: Path,
    rows: tuple[CandidateArtifactRecord, ...],
) -> tuple[CandidateSourceFile, ...]:
    metadata = _source_metadata(rows)
    sources = []
    for item in source_file_manifest(workspace):
        path = item["path"]
        file_kind, owners = metadata.get(
            path,
            (
                "runtime" if path.startswith("src/runtime/") else "infrastructure",
                ("FOUNDATION",),
            ),
        )
        sources.append(
            CandidateSourceFile(
                path=path,
                file_kind=file_kind,
                owner_contract_ids=owners,
                source=(workspace / path).read_text(encoding="utf-8"),
            )
        )
    return tuple(sources)


def _full_batch(
    *,
    kind: str,
    accepted_sources: tuple[CandidateSourceFile, ...],
    delta: GeneratedCandidateBatch,
) -> GeneratedCandidateBatch:
    prefix = (
        "src/components/business/"
        if kind == "business_components"
        else "src/pages/"
    )
    files = {
        item.path: GeneratedCandidateFile(
            path=item.path,
            file_kind=item.file_kind,
            owner_contract_ids=item.owner_contract_ids,
            source=item.source,
        )
        for item in accepted_sources
        if item.path.startswith(prefix)
    }
    files.update({item.path: item for item in delta.files})
    return GeneratedCandidateBatch(
        batch_kind=kind,
        files=tuple(files[path] for path in sorted(files)),
    )


def _delta_batch_from_full(
    *,
    kind: str,
    full: GeneratedCandidateBatch,
    accepted_sources: tuple[CandidateSourceFile, ...],
) -> GeneratedCandidateBatch:
    accepted = {item.path: item.source for item in accepted_sources}
    files = tuple(
        item
        for item in full.files
        if accepted.get(item.path) != item.source
    )
    if not files:
        raise Tier2GenerationContractError(
            f"Cumulative {kind} repair has no delta-owned files"
        )
    return GeneratedCandidateBatch(batch_kind=kind, files=files)


def _repair_issues(report, *, stage: str, owner_ids: set[str]):
    prefix = (
        "src/components/business/"
        if stage == "business_components"
        else "src/pages/"
    )
    semantic_codes = {
        "missing_action_trigger",
        "missing_evidence_marker",
        "missing_state_marker",
        "missing_journey_marker",
        "missing_acceptance_hook",
        "missing_mobile_binding",
        "missing_business_component_usage",
    }
    return tuple(
        item
        for item in report.issues
        if item.path.startswith(prefix)
        or bool(set(item.related_ids) & owner_ids)
        or item.code in semantic_codes
    )


def _cache_key(
    stage: str,
    payload: dict,
    profile: _TierGenerationProfile,
) -> str:
    return canonical_sha256(
        {
            "stage": stage,
            "schema_version": "1.0",
            "generation_policy_revision": (
                profile.policy_revision
            ),
            **payload,
        }
    )


def _stage_provenance(payload: dict) -> str:
    return canonical_sha256(payload)


def _prompt_inputs(
    context: CandidateContext,
    *,
    contracts: Tier2ExtensionContracts | Tier3ExtensionContracts,
    accepted_sources: tuple[CandidateSourceFile, ...],
    preservation: Tier2PreservationManifest | Tier3PreservationManifest,
    profile: _TierGenerationProfile,
    stage: str,
    component_delta: GeneratedCandidateBatch | None,
) -> dict:
    allowed_edits = tuple(
        item.path
        for item in preservation.entries
        if item.edit_authority == "ai"
        and (
            (stage == "pages" and item.path.startswith("src/pages/"))
            or (
                stage == "business_components"
                and item.path.startswith("src/components/business/")
            )
        )
    )
    new_component_ids = tuple(
        item.component_id
        for item in context.business_components.components
        if item.component_id.startswith(f"COMP-T{profile.target_tier}-")
    )
    allowed_new = (
        tuple(
            f"src/components/business/{item}.tsx"
            for item in new_component_ids
        )
        if stage == "business_components"
        else tuple(
            f"src/pages/{item}.tsx"
            for item in contracts.projection.delta.page_ids
        )
    )
    readonly = {
        item.path: item.source
        for item in accepted_sources
        if item.path.startswith("src/")
    }
    payload = {
        "target_tier": profile.target_tier,
        "page_purpose_contract": context.page_purpose.model_dump(mode="json"),
        "business_component_plan": context.business_components.model_dump(
            mode="json"
        ),
        "content_data_plan": context.content_data.model_dump(mode="json"),
        "interaction_contract": context.interactions.model_dump(mode="json"),
        "component_dependency_graph": context.dependency_graph.model_dump(
            mode="json"
        ),
        "allowed_new_paths": allowed_new,
        "allowed_ai_edit_paths": allowed_edits,
    }
    if profile.target_tier == 2:
        payload.update(
            {
                "tier_2_delta": (
                    contracts.projection.delta.model_dump(mode="json")
                ),
                "tier_2_projection": (
                    contracts.projection.model_dump(mode="json")
                ),
                "accepted_tier_1_readonly_sources": readonly,
                "generated_tier_2_components": (
                    component_delta.model_dump(mode="json")
                    if component_delta
                    else None
                ),
            }
        )
    else:
        payload.update(
            {
                "tier_delta": (
                    contracts.projection.delta.model_dump(mode="json")
                ),
                "tier_projection": (
                    contracts.projection.model_dump(mode="json")
                ),
                "accepted_lower_tier_readonly_sources": readonly,
                "generated_tier_components": (
                    component_delta.model_dump(mode="json")
                    if component_delta
                    else None
                ),
            }
        )
    return payload


def _build_tier_candidate(
    db,
    *,
    req: Request,
    accepted: CandidateRevisionRecord,
    accepted_workspace: Path,
    inherited_context: CandidateContext,
    contracts: Tier2ExtensionContracts | Tier3ExtensionContracts,
    refs: CandidateUpstreamRefs,
    preservation: Tier2PreservationManifest | Tier3PreservationManifest,
    extension_manifest_ref: dict,
    ai_provider,
    template_renderer,
    phase5_summary: dict,
    phase_deadline: float,
    profile: _TierGenerationProfile,
) -> BuiltTier2Candidate:
    started = time.monotonic()
    target_label = f"Tier {profile.target_tier}"
    closure_sha = (
        contracts.projection.tier_3_closure_sha256
        if profile.target_tier == 3
        else contracts.projection.tier_2_closure_sha256
    )
    repository = CandidateRepository(db)
    accepted_rows = _artifact_rows(db, accepted)
    accepted_sources = _accepted_sources(accepted_workspace, accepted_rows)
    upstream = canonical_sha256(
        {
            "accepted_revision_id": accepted.id,
            "accepted_manifest_sha256": accepted.file_manifest_sha256,
            "tier_1_visual_summary_id": (
                contracts.projection.accepted_tier_1_visual_summary_id
            ),
            "tier_closure_sha256": closure_sha,
            "delta_sha256": contracts.projection.delta_sha256,
            "extension_manifest_ref": extension_manifest_ref,
            "preservation_sha256": preservation.manifest_sha256,
            "dependency_lock_sha256": accepted.dependency_lock_sha256,
            "generation_policy_revision": (
                profile.policy_revision
            ),
            "component_model": profile.component_model,
            "page_model": profile.page_model,
            "repair_model": profile.repair_model,
            "repair_prompt_revision": (
                settings.V2_CANDIDATE_REPAIR_PROMPT_REVISION
            ),
            "repair_max_tokens": settings.V2_CANDIDATE_REPAIR_MAX_TOKENS,
            "repair_timeout_seconds": (
                settings.V2_CANDIDATE_REPAIR_TIMEOUT_SECONDS
            ),
            "component_prompt_revision": (
                profile.component_prompt_revision
            ),
            "page_prompt_revision": profile.page_prompt_revision,
            "budget": {
                "calls": profile.max_calls,
                "tokens": profile.max_output_tokens,
                "cost": profile.max_cost_usd,
                "wall": profile.max_wall_seconds,
            },
        }
    )
    workspace = open_candidate_workspace(
        request_id=req.id,
        upstream_sha256=upstream,
        policy_revision=profile.policy_revision,
    )
    if not workspace.resumed:
        shutil.copytree(
            accepted_workspace,
            workspace.staging_path,
            dirs_exist_ok=True,
        )
    assert_accepted_workspace_unchanged(
        accepted_workspace,
        expected_manifest_sha256=accepted.file_manifest_sha256,
    )
    cumulative_context = CandidateContext(
        composition=inherited_context.composition,
        refs=refs,
        page_purpose=contracts.page_purpose,
        business_components=contracts.business_components,
        content_data=contracts.content_data,
        interactions=contracts.interactions,
        dependency_graph=contracts.dependency_graph,
        rows=(),
    )
    completed: dict[str, str] = {}
    metrics: list[CandidateStageMetrics] = []
    foundation_metric = _metric("foundation", started, profile)
    metrics.append(foundation_metric)
    foundation_row = accepted_rows[0]

    projected_data_sources = build_data_sources(cumulative_context)
    accepted_by_path = {item.path: item for item in accepted_sources}
    # The accepted generated canonical-contract source remains an immutable
    # Tier 1 artifact. Cumulative truth lives in the typed Phase 6 extension
    # record; only structured data receives a deterministic source extension.
    data_sources = tuple(
        (
            accepted_by_path[item.path]
            if item.path == "src/generated/canonical-contracts.ts"
            else item
        )
        for item in projected_data_sources
    )
    data_inputs = {
        "accepted_manifest": accepted.file_manifest_sha256,
        "content": refs.content_data_plan_ref.sha256,
        "interactions": refs.interaction_contract_ref.sha256,
        "delta": contracts.projection.delta_sha256,
        "dependency_lock": accepted.dependency_lock_sha256,
    }
    data_cache = _cache_key("data_exports", data_inputs, profile)
    data_provenance = _stage_provenance(data_inputs)
    data_manifest = source_manifest(
        artifact_kind="data_exports",
        input_hashes=tuple(str(value) for value in data_inputs.values()),
        sources=data_sources,
    )
    data_row = repository.find_cache(
        request_id=req.id,
        artifact_kind="data_exports",
        cache_key=data_cache,
    )
    data_metric = _metric("data_exports", started, profile)
    if data_row is not None:
        cached = repository.load_cached(
            data_row,
            schema=CandidateArtifactManifest,
            request_id=req.id,
            provenance_sha256=data_provenance,
            parent_artifact_id=foundation_row.id,
        )
        if cached != data_manifest:
            raise ValueError(f"{target_label} data cache is inconsistent")
        data_metric = candidate_cache_hit_metrics(
            data_row,
            latency_ms=data_metric.latency_ms,
        )
    else:
        data_row = repository.stage_artifact(
            artifact=data_manifest,
            refs=refs,
            provenance_sha256=data_provenance,
            cache_key=data_cache,
            metrics=data_metric,
            parent_artifact_id=foundation_row.id,
            validation={"passed": True, "deterministic": True},
            validation_passed=True,
            policy_revision=profile.policy_revision,
        )
    metrics.append(data_metric)
    write_sources(workspace, data_sources)
    completed.update({item.path: sha256_text(item.source) for item in data_sources})

    existing_paths = tuple(item.path for item in accepted_sources)
    allowed_ai_edits = tuple(
        item.path
        for item in preservation.entries
        if item.edit_authority == "ai"
    )
    inherited_component_ids = {
        item.component_id
        for item in inherited_context.business_components.components
    }
    new_component_ids = tuple(
        item.component_id
        for item in cumulative_context.business_components.components
        if item.component_id not in inherited_component_ids
    )
    component_policy = (
        tier_3_generation_policy("business_components")
        if profile.target_tier == 3
        else tier_2_generation_policy("business_components")
    )
    component_inputs = {
        "accepted_revision": accepted.id,
        "accepted_manifest": accepted.file_manifest_sha256,
        "extension": extension_manifest_ref["sha256"],
        "preservation": preservation.manifest_sha256,
        "model": component_policy.model,
        "family": component_policy.model_family,
        "prompt": component_policy.prompt_revision,
        "max_tokens": component_policy.max_tokens,
        "dependency_lock": accepted.dependency_lock_sha256,
    }
    component_cache = _cache_key(
        "business_components",
        component_inputs,
        profile,
    )
    component_provenance = _stage_provenance(component_inputs)
    component_row = repository.find_cache(
        request_id=req.id,
        artifact_kind="business_components",
        cache_key=component_cache,
    )
    component_delta = None
    if component_row is not None:
        component_full = repository.load_cached(
            component_row,
            schema=GeneratedCandidateBatch,
            request_id=req.id,
            provenance_sha256=component_provenance,
            parent_artifact_id=data_row.id,
        )
        component_metric = candidate_cache_hit_metrics(
            component_row,
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        )
    else:
        built = build_ai_batch(
            request_id=req.id,
            policy=component_policy,
            prompt_template=profile.component_prompt,
            prompt_values={
                "candidate_inputs_json": canonical_json(
                    _prompt_inputs(
                        cumulative_context,
                        contracts=contracts,
                        accepted_sources=accepted_sources,
                        preservation=preservation,
                        profile=profile,
                        stage="business_components",
                        component_delta=None,
                    )
                )
            },
            ai_provider=ai_provider,
            template_renderer=template_renderer,
            phase_deadline=phase_deadline,
        )
        component_delta = deterministic_repair_batch(built.batch)
        validate_delta_batch(
            component_delta,
            projection=contracts.projection,
            new_component_ids=new_component_ids,
            allowed_ai_edit_paths=allowed_ai_edits,
            existing_paths=existing_paths,
        )
        component_full = _full_batch(
            kind="business_components",
            accepted_sources=accepted_sources,
            delta=component_delta,
        )
        component_metric = built.metrics
        component_row = repository.stage_artifact(
            artifact=component_full,
            refs=refs,
            provenance_sha256=component_provenance,
            cache_key=component_cache,
            metrics=component_metric,
            parent_artifact_id=data_row.id,
            validation={
                "passed": True,
                "delta_owner_ids": list(new_component_ids),
                "full_product_regeneration": False,
            },
            validation_passed=True,
            policy_revision=profile.policy_revision,
        )
    metrics.append(component_metric)
    if component_delta is None:
        component_delta = _delta_batch_from_full(
            kind="business_components",
            full=component_full,
            accepted_sources=accepted_sources,
        )
    component_sources = batch_sources(component_full)
    accepted_source_text = {
        item.path: item.source for item in accepted_sources
    }
    component_writes = tuple(
        item
        for item in component_sources
        if accepted_source_text.get(item.path) != item.source
    )
    write_sources(workspace, component_writes)
    checkpoint_workspace(
        workspace,
        upstream_sha256=upstream,
        completed_artifacts={
            item.path: sha256_text(item.source)
            for item in (*data_sources, *component_writes)
        },
        policy_revision=profile.policy_revision,
    )

    page_policy = (
        tier_3_generation_policy("pages")
        if profile.target_tier == 3
        else tier_2_generation_policy("pages")
    )
    page_inputs = {
        **component_inputs,
        "component_artifact": component_row.artifact_sha256,
        "model": page_policy.model,
        "family": page_policy.model_family,
        "prompt": page_policy.prompt_revision,
        "max_tokens": page_policy.max_tokens,
    }
    page_cache = _cache_key("pages", page_inputs, profile)
    page_provenance = _stage_provenance(page_inputs)
    page_row = repository.find_cache(
        request_id=req.id,
        artifact_kind="pages",
        cache_key=page_cache,
    )
    if page_row is not None:
        page_full = repository.load_cached(
            page_row,
            schema=GeneratedCandidateBatch,
            request_id=req.id,
            provenance_sha256=page_provenance,
            parent_artifact_id=component_row.id,
        )
        page_metric = candidate_cache_hit_metrics(
            page_row,
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        )
    else:
        built = build_ai_batch(
            request_id=req.id,
            policy=page_policy,
            prompt_template=profile.page_prompt,
            prompt_values={
                "candidate_inputs_json": canonical_json(
                    _prompt_inputs(
                        cumulative_context,
                        contracts=contracts,
                        accepted_sources=accepted_sources,
                        preservation=preservation,
                        profile=profile,
                        stage="pages",
                        component_delta=component_delta,
                    )
                )
            },
            ai_provider=ai_provider,
            template_renderer=template_renderer,
            phase_deadline=phase_deadline,
        )
        page_delta = deterministic_repair_batch(built.batch)
        validate_delta_batch(
            page_delta,
            projection=contracts.projection,
            new_component_ids=new_component_ids,
            allowed_ai_edit_paths=allowed_ai_edits,
            existing_paths=existing_paths,
        )
        page_full = _full_batch(
            kind="pages",
            accepted_sources=accepted_sources,
            delta=page_delta,
        )
        page_metric = built.metrics
        page_row = repository.stage_artifact(
            artifact=page_full,
            refs=refs,
            provenance_sha256=page_provenance,
            cache_key=page_cache,
            metrics=page_metric,
            parent_artifact_id=component_row.id,
            validation={
                "passed": True,
                "delta_page_ids": list(contracts.projection.delta.page_ids),
                "integration_page_ids": list(
                    contracts.projection.lower_tier_integration_page_ids
                ),
                "full_product_regeneration": False,
            },
            validation_passed=True,
            policy_revision=profile.policy_revision,
        )
    metrics.append(page_metric)
    page_sources = batch_sources(page_full)
    page_writes = tuple(
        item
        for item in page_sources
        if accepted_source_text.get(item.path) != item.source
    )
    write_sources(workspace, page_writes)

    route_sources = build_route_sources(cumulative_context, page_sources)
    write_sources(workspace, route_sources)

    preservation_final = finalize_preservation_audit(
        preservation,
        final_workspace=workspace.staging_path,
    )
    verify_preservation_after_generation(
        initial=preservation,
        final=preservation_final,
    )
    source_by_path = {item.path: item for item in accepted_sources}
    for item in (*data_sources, *component_sources, *page_sources, *route_sources):
        source_by_path[item.path] = item
    expected_sources = tuple(
        source_by_path[path] for path in sorted(source_by_path)
    )
    report = validate_candidate_workspace(
        workspace,
        context=cumulative_context,
        expected_sources=expected_sources,
        data_sources=data_sources,
        route_sources=route_sources,
    )
    if not report.passed:
        repair_policy = (
            tier_3_static_repair_policy()
            if profile.target_tier == 3
            else tier_2_static_repair_policy()
        )
        component_issues = _repair_issues(
            report,
            stage="business_components",
            owner_ids=set(new_component_ids),
        )
        page_owner_ids = set(
            (
                *contracts.projection.delta.page_ids,
                *contracts.projection.lower_tier_integration_page_ids,
            )
        )
        page_issues = _repair_issues(
            report,
            stage="pages",
            owner_ids=page_owner_ids,
        )
        if not component_issues and not page_issues:
            raise Tier2GenerationContractError(
                f"Cumulative Tier 1..{profile.target_tier} static "
                "validation failed outside "
                "the narrow AI repair scope",
                diagnostics=tuple(
                    canonical_json(item.model_dump(mode="json"))
                    for item in report.issues
                ),
            )
        canonical_bindings = {
            "tier_projection": contracts.projection.model_dump(mode="json"),
            "page_purpose_contract": (
                cumulative_context.page_purpose.model_dump(mode="json")
            ),
            "business_component_plan": (
                cumulative_context.business_components.model_dump(mode="json")
            ),
            "content_data_plan": (
                cumulative_context.content_data.model_dump(mode="json")
            ),
            "interaction_contract": (
                cumulative_context.interactions.model_dump(mode="json")
            ),
            "immutable_preservation_manifest": (
                preservation.model_dump(mode="json")
            ),
        }
        component_repaired = False
        if component_issues:
            if component_metric.cache_hit:
                raise Tier2GenerationContractError(
                    f"A cached {target_label} component batch failed "
                    "static validation"
                )
            component_diagnostics = tuple(
                canonical_json(item.model_dump(mode="json"))
                for item in component_issues
            )
            component_repair_inputs = {
                "failed_artifact": component_row.artifact_sha256,
                "diagnostics": canonical_sha256(component_diagnostics),
                "repair_model": repair_policy.model,
                "repair_family": repair_policy.model_family,
                "repair_prompt": repair_policy.prompt_revision,
                "repair_max_tokens": repair_policy.max_tokens,
            }
            component_repair_cache = _cache_key(
                "business_components_repair",
                component_repair_inputs,
                profile,
            )
            component_repair_provenance = _stage_provenance(
                component_repair_inputs
            )
            repaired_component_row = repository.find_cache(
                request_id=req.id,
                artifact_kind="business_components",
                cache_key=component_repair_cache,
            )
            if repaired_component_row is not None:
                component_full = repository.load_cached(
                    repaired_component_row,
                    schema=GeneratedCandidateBatch,
                    request_id=req.id,
                    provenance_sha256=component_repair_provenance,
                    parent_artifact_id=data_row.id,
                )
                component_metric = candidate_cache_hit_metrics(
                    repaired_component_row,
                    latency_ms=max(
                        0,
                        int((time.monotonic() - started) * 1000),
                    ),
                )
                component_row = repaired_component_row
            else:
                component_delta_for_repair = _delta_batch_from_full(
                    kind="business_components",
                    full=component_full,
                    accepted_sources=accepted_sources,
                )
                repaired = repair_ai_batch(
                    request_id=req.id,
                    batch_stage="business_components",
                    policy=repair_policy,
                    batch=component_delta_for_repair,
                    diagnostics=component_diagnostics,
                    canonical_bindings=canonical_bindings,
                    ai_provider=ai_provider,
                    template_renderer=template_renderer,
                    prompt_template=PromptTemplate.V2_CANDIDATE_REPAIR,
                    phase_deadline=phase_deadline,
                )
                repaired_delta = deterministic_repair_batch(repaired.batch)
                validate_delta_batch(
                    repaired_delta,
                    projection=contracts.projection,
                    new_component_ids=new_component_ids,
                    allowed_ai_edit_paths=allowed_ai_edits,
                    existing_paths=existing_paths,
                )
                component_full = _full_batch(
                    kind="business_components",
                    accepted_sources=accepted_sources,
                    delta=repaired_delta,
                )
                component_metric = combine_generation_and_repair_metrics(
                    component_metric,
                    repaired.metrics,
                )
                component_row = repository.stage_artifact(
                    artifact=component_full,
                    refs=refs,
                    provenance_sha256=component_repair_provenance,
                    cache_key=component_repair_cache,
                    metrics=component_metric,
                    parent_artifact_id=data_row.id,
                    validation={
                        "passed": True,
                        "narrow_static_repair": True,
                        "diagnostics": list(component_diagnostics),
                    },
                    validation_passed=True,
                    policy_revision=(
                        profile.policy_revision
                    ),
                )
            component_repaired = True
            metrics[2] = component_metric
            component_sources = batch_sources(component_full)
            write_sources(
                workspace,
                tuple(
                    item
                    for item in component_sources
                    if accepted_source_text.get(item.path) != item.source
                ),
            )
        if page_issues:
            if page_metric.cache_hit:
                raise Tier2GenerationContractError(
                    f"A cached {target_label} page batch failed static "
                    "validation"
                )
            page_diagnostics = tuple(
                canonical_json(item.model_dump(mode="json"))
                for item in page_issues
            )
            page_repair_inputs = {
                "failed_artifact": page_row.artifact_sha256,
                "component_artifact": component_row.artifact_sha256,
                "diagnostics": canonical_sha256(page_diagnostics),
                "repair_model": repair_policy.model,
                "repair_family": repair_policy.model_family,
                "repair_prompt": repair_policy.prompt_revision,
                "repair_max_tokens": repair_policy.max_tokens,
            }
            page_repair_cache = _cache_key(
                "pages_repair",
                page_repair_inputs,
                profile,
            )
            page_repair_provenance = _stage_provenance(page_repair_inputs)
            repaired_page_row = repository.find_cache(
                request_id=req.id,
                artifact_kind="pages",
                cache_key=page_repair_cache,
            )
            if repaired_page_row is not None:
                page_full = repository.load_cached(
                    repaired_page_row,
                    schema=GeneratedCandidateBatch,
                    request_id=req.id,
                    provenance_sha256=page_repair_provenance,
                    parent_artifact_id=component_row.id,
                )
                page_metric = candidate_cache_hit_metrics(
                    repaired_page_row,
                    latency_ms=max(
                        0,
                        int((time.monotonic() - started) * 1000),
                    ),
                )
                page_row = repaired_page_row
            else:
                page_delta_for_repair = _delta_batch_from_full(
                    kind="pages",
                    full=page_full,
                    accepted_sources=accepted_sources,
                )
                repaired = repair_ai_batch(
                    request_id=req.id,
                    batch_stage="pages",
                    policy=repair_policy,
                    batch=page_delta_for_repair,
                    diagnostics=page_diagnostics,
                    canonical_bindings=canonical_bindings,
                    ai_provider=ai_provider,
                    template_renderer=template_renderer,
                    prompt_template=PromptTemplate.V2_CANDIDATE_REPAIR,
                    phase_deadline=phase_deadline,
                )
                repaired_delta = deterministic_repair_batch(repaired.batch)
                validate_delta_batch(
                    repaired_delta,
                    projection=contracts.projection,
                    new_component_ids=new_component_ids,
                    allowed_ai_edit_paths=allowed_ai_edits,
                    existing_paths=existing_paths,
                )
                page_full = _full_batch(
                    kind="pages",
                    accepted_sources=accepted_sources,
                    delta=repaired_delta,
                )
                page_metric = combine_generation_and_repair_metrics(
                    page_metric,
                    repaired.metrics,
                )
                page_row = repository.stage_artifact(
                    artifact=page_full,
                    refs=refs,
                    provenance_sha256=page_repair_provenance,
                    cache_key=page_repair_cache,
                    metrics=page_metric,
                    parent_artifact_id=component_row.id,
                    validation={
                        "passed": True,
                        "narrow_static_repair": True,
                        "diagnostics": list(page_diagnostics),
                    },
                    validation_passed=True,
                    policy_revision=(
                        profile.policy_revision
                    ),
                )
            metrics[3] = page_metric
            page_sources = batch_sources(page_full)
            write_sources(
                workspace,
                tuple(
                    item
                    for item in page_sources
                    if accepted_source_text.get(item.path) != item.source
                ),
            )
        elif component_repaired:
            # Preserve an exact parent chain without charging another AI call.
            relink_inputs = {
                "source_artifact": page_row.artifact_sha256,
                "component_artifact": component_row.artifact_sha256,
                "deterministic_relink": True,
            }
            relink_metric = candidate_cache_hit_metrics(
                page_row,
                latency_ms=max(
                    0,
                    int((time.monotonic() - started) * 1000),
                ),
            )
            page_row = repository.stage_artifact(
                artifact=page_full,
                refs=refs,
                provenance_sha256=_stage_provenance(relink_inputs),
                cache_key=_cache_key(
                    "pages_relink",
                    relink_inputs,
                    profile,
                ),
                metrics=relink_metric,
                parent_artifact_id=component_row.id,
                validation={
                    "passed": True,
                    "deterministic_parent_relink": True,
                },
                validation_passed=True,
                policy_revision=profile.policy_revision,
            )
        route_sources = build_route_sources(cumulative_context, page_sources)
        write_sources(workspace, route_sources)
        preservation_final = finalize_preservation_audit(
            preservation,
            final_workspace=workspace.staging_path,
        )
        verify_preservation_after_generation(
            initial=preservation,
            final=preservation_final,
        )
        source_by_path = {item.path: item for item in accepted_sources}
        for item in (
            *data_sources,
            *component_sources,
            *page_sources,
            *route_sources,
        ):
            source_by_path[item.path] = item
        expected_sources = tuple(
            source_by_path[path] for path in sorted(source_by_path)
        )
        report = validate_candidate_workspace(
            workspace,
            context=cumulative_context,
            expected_sources=expected_sources,
            data_sources=data_sources,
            route_sources=route_sources,
        )
        if not report.passed:
            raise Tier2GenerationContractError(
                f"Cumulative Tier 1..{profile.target_tier} static "
                "validation failed after the "
                "single narrow repair pass",
                diagnostics=tuple(
                    canonical_json(item.model_dump(mode="json"))
                    for item in report.issues
                ),
            )

    route_inputs = {
        "accepted_manifest": accepted.file_manifest_sha256,
        "page_artifact": page_row.artifact_sha256,
        "ia": refs.composition_contract_refs.information_architecture_ref.sha256,
        "tier_closure": closure_sha,
        "dependency_lock": accepted.dependency_lock_sha256,
    }
    route_cache = _cache_key("routes", route_inputs, profile)
    route_provenance = _stage_provenance(route_inputs)
    route_manifest = source_manifest(
        artifact_kind="routes",
        input_hashes=tuple(str(value) for value in route_inputs.values()),
        sources=route_sources,
    )
    route_row = repository.find_cache(
        request_id=req.id,
        artifact_kind="routes",
        cache_key=route_cache,
    )
    route_metric = _metric("routes", started, profile)
    if route_row is not None:
        cached = repository.load_cached(
            route_row,
            schema=CandidateArtifactManifest,
            request_id=req.id,
            provenance_sha256=route_provenance,
            parent_artifact_id=page_row.id,
        )
        if cached != route_manifest:
            raise ValueError(f"{target_label} route cache is inconsistent")
        route_metric = candidate_cache_hit_metrics(
            route_row,
            latency_ms=route_metric.latency_ms,
        )
    else:
        route_row = repository.stage_artifact(
            artifact=route_manifest,
            refs=refs,
            provenance_sha256=route_provenance,
            cache_key=route_cache,
            metrics=route_metric,
            parent_artifact_id=page_row.id,
            validation={"passed": True, "deterministic": True},
            validation_passed=True,
            policy_revision=profile.policy_revision,
        )
    metrics.append(route_metric)
    validation_inputs = {
        "candidate_manifest": report.file_manifest_sha256,
        "data": report.content_data_sha256,
        "routes": report.route_manifest_sha256,
        "preservation": preservation_final.manifest_sha256,
        "policy": profile.policy_revision,
    }
    validation_cache = _cache_key("validation", validation_inputs, profile)
    validation_provenance = _stage_provenance(validation_inputs)
    validation_row = repository.find_cache(
        request_id=req.id,
        artifact_kind="validation",
        cache_key=validation_cache,
    )
    validation_metric = _metric("validation", started, profile)
    if validation_row is not None:
        cached = repository.load_cached(
            validation_row,
            schema=type(report),
            request_id=req.id,
            provenance_sha256=validation_provenance,
            parent_artifact_id=route_row.id,
        )
        if cached != report:
            raise ValueError(
                f"{target_label} static validation cache is inconsistent"
            )
        validation_metric = candidate_cache_hit_metrics(
            validation_row,
            latency_ms=validation_metric.latency_ms,
        )
    else:
        validation_row = repository.stage_artifact(
            artifact=report,
            refs=refs,
            provenance_sha256=validation_provenance,
            cache_key=validation_cache,
            metrics=validation_metric,
            parent_artifact_id=route_row.id,
            validation={
                "passed": True,
                "target_tier": profile.target_tier,
                "lower_tier_regression_checks": True,
            },
            validation_passed=True,
            policy_revision=profile.policy_revision,
        )
    metrics.append(validation_metric)
    calls = sum(item.provider_call_count for item in metrics)
    tokens = sum(item.completion_tokens for item in metrics)
    cost = sum(item.cost_usd for item in metrics)
    if (
        calls > 4
        or tokens > profile.max_output_tokens
        or cost > profile.max_cost_usd
        or time.monotonic() > phase_deadline
    ):
        raise Tier2GenerationContractError(
            f"{target_label} generation exceeded aggregate limits"
        )
    manifest = source_file_manifest(workspace.staging_path)
    final_path = freeze_candidate_workspace(workspace)
    phase_summary = dict(phase5_summary)
    phase_summary.update(
        {
            "target_tier": profile.target_tier,
            "tier_extension_manifest_ref": extension_manifest_ref,
            "candidate_lifecycle": [
                f"tier_{profile.target_tier}_delta_projected",
                "candidate_generated",
                "candidate_build_pending",
            ],
            "candidate_resumed": workspace.resumed,
        }
    )
    if profile.target_tier == 3:
        lower_extension = phase5_summary.get(
            "accepted_tier_2_extension_manifest_ref"
        )
        if not lower_extension:
            raise Tier2GenerationContractError(
                "Tier 3 generation is missing its Tier 2 extension lineage"
            )
        phase_summary["accepted_tier_2_extension_manifest_ref"] = (
            lower_extension
        )
    candidate, summary = repository.persist_revision(
        req=req,
        revision_uuid=workspace.revision_uuid,
        status="candidate_build_pending",
        refs=refs,
        dependency_lock_sha256=accepted.dependency_lock_sha256,
        model_manifest={
            "business_components": {
                "model": profile.component_model,
                "prompt_revision": profile.component_prompt_revision,
            },
            "pages": {
                "model": profile.page_model,
                "prompt_revision": profile.page_prompt_revision,
            },
            "repair": {
                "model": profile.repair_model,
                "invoked": any(
                    item.repair_call_count for item in metrics
                ),
            },
        },
        workspace_relpath=workspace_relpath(final_path),
        file_manifest=manifest,
        artifact_rows=(
            foundation_row,
            data_row,
            component_row,
            page_row,
            route_row,
            validation_row,
        ),
        failure={},
        metrics=tuple(metrics),
        summary_base=phase_summary,
        target_tier=profile.target_tier,
        generator_version=(
            "v2-phase6a-tier2"
            if profile.target_tier == 2
            else "v2-phase6b-tier3"
        ),
        policy_revision=profile.policy_revision,
        update_request_bundle=False,
    )
    db.commit()
    assert_accepted_workspace_unchanged(
        accepted_workspace,
        expected_manifest_sha256=accepted.file_manifest_sha256,
    )
    return BuiltTier2Candidate(
        candidate=candidate,
        summary=summary,
        context=cumulative_context,
        preservation=preservation_final,
        validation_report=report,
        metrics=tuple(metrics),
        resumed=workspace.resumed,
        generation_cache_hits=sum(1 for item in metrics if item.cache_hit),
    )


def build_tier_2_candidate(
    db,
    **kwargs,
) -> BuiltTier2Candidate:
    return _build_tier_candidate(
        db,
        **kwargs,
        profile=_generation_profile(2),
    )


def build_tier_3_candidate(
    db,
    **kwargs,
) -> BuiltTier3Candidate:
    return _build_tier_candidate(
        db,
        **kwargs,
        profile=_generation_profile(3),
    )


__all__ = [
    "BuiltTier2Candidate",
    "BuiltTier3Candidate",
    "build_tier_2_candidate",
    "build_tier_3_candidate",
]
