"""Bounded ownership-derived refinement plan and immutable candidate lineage."""
from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.application.appspec.repository import load_json_object
from app.application.appspec.source import canonical_json
from app.application.candidate_generation.cache import canonical_sha256, sha256_text
from app.application.candidate_generation.deterministic import CandidateSourceFile
from app.application.candidate_generation.validation import (
    validate_candidate_workspace,
)
from app.application.candidate_generation.workspace import (
    freeze_candidate_workspace,
    open_candidate_workspace,
    source_file_manifest,
    workspace_relpath,
    write_sources,
)
from app.application.runtime_validation.cache import artifact_sha256
from app.application.visual_evaluation.context import VisualEvaluationContext
from app.application.visual_evaluation.evidence import evidence_absolute_paths
from app.domain.models import CandidateArtifactRecord, CandidateRevisionRecord
from app.domain.schemas.preview_candidate import (
    CandidateArtifactManifest,
    CandidateValidationReport,
    GeneratedCandidateBatch,
)
from app.domain.schemas.visual_evaluation import (
    RefinementOutput,
    RefinementPlan,
    RefinementPlanItem,
    VisualEvidenceBundle,
    VisualFinding,
)


_REPAIRABLE_ISSUES = {
    "visual_hierarchy",
    "design_dna_alignment",
    "copy_credibility",
    "spacing_density",
    "evidence_visibility",
    "conversion_clarity",
    "responsive_layout",
    "interaction_clarity",
    "content_credibility",
}
_IMMUTABLE_CONSTRAINTS = (
    "exact routes and navigation",
    "canonical actions, states, transitions, evidence, and acceptance tests",
    "dependencies, package files, generated data, foundation, infrastructure",
    "all files outside the explicit allowlist",
    "the accepted DesignDNA",
)
_VALIDATIONS = (
    "unchanged file set and unaffected hashes",
    "Phase 3B TypeScript/import/dependency/route/contract static gate",
    "complete Phase 4 build, routes, journeys, accessibility, screenshots",
    "Phase 5 absolute thresholds and blind original/refined comparison",
)


class StaticValidationFailure(ValueError):
    """Refinement compiled/validated incorrectly and may get one repair."""


@dataclass(frozen=True)
class DerivedCandidate:
    revision: CandidateRevisionRecord
    phase3b_result: dict
    static_report: CandidateValidationReport
    allowed_before: tuple[tuple[str, str], ...]
    allowed_after: tuple[tuple[str, str], ...]
    unaffected_before: str
    unaffected_after: str
    technical_repair_count: int


def _artifact_manifests(
    db: Session,
    candidate: CandidateRevisionRecord,
) -> dict[str, CandidateArtifactManifest | GeneratedCandidateBatch]:
    result = {}
    for kind, artifact_id in (
        ("foundation", candidate.foundation_artifact_id),
        ("data_exports", candidate.data_artifact_id),
        ("business_components", candidate.component_artifact_id),
        ("pages", candidate.page_artifact_id),
        ("routes", candidate.route_artifact_id),
    ):
        row = db.get(CandidateArtifactRecord, artifact_id)
        if (
            row is None
            or row.request_id != candidate.request_id
            or row.artifact_kind != kind
            or not row.validation_passed
        ):
            raise ValueError("Candidate artifact ownership chain is invalid")
        schema = (
            GeneratedCandidateBatch
            if kind in {"business_components", "pages"}
            else CandidateArtifactManifest
        )
        artifact = schema.model_validate(load_json_object(row.artifact_json))
        if artifact_sha256(artifact) != row.artifact_sha256:
            raise ValueError("Candidate artifact manifest hash is corrupt")
        result[kind] = artifact
    return result


def classify_and_build_plan(
    db: Session,
    context: VisualEvaluationContext,
    *,
    findings: tuple[VisualFinding, ...],
    bundle: VisualEvidenceBundle,
    limits,
) -> tuple[str, RefinementPlan | None]:
    actionable = tuple(
        item
        for item in findings
        if item.severity in {"major", "blocking"}
    )
    if (
        not actionable
        or any(item.issue_type not in _REPAIRABLE_ISSUES for item in actionable)
    ):
        return "rejected_not_repairable", None
    manifests = _artifact_manifests(db, context.candidate)
    owned_files: dict[str, list[str]] = {}
    for kind in ("business_components", "pages"):
        for descriptor in manifests[kind].files:
            for owner in descriptor.owner_contract_ids:
                owned_files.setdefault(owner, []).append(descriptor.path)
    manifest_hashes = {
        item["path"]: item["sha256"]
        for item in context.candidate_file_manifest
    }
    route_by_page = {
        item.page_id: item.route
        for item in context.contracts.page_purpose.pages
    }
    evidence_ids = {
        item.evidence_id for item in bundle.ordered_screenshots
    }
    items = []
    all_files: list[str] = []
    all_pages: list[str] = []
    for priority, finding in enumerate(actionable, start=1):
        if not set(finding.evidence_ids).issubset(evidence_ids):
            return "rejected_not_repairable", None
        files = []
        for owner in (*finding.page_ids, *finding.component_ids):
            files.extend(owned_files.get(owner, ()))
        files = list(dict.fromkeys(files))
        if not files or any(
            not (
                path.startswith("src/pages/")
                or path.startswith("src/components/business/")
            )
            for path in files
        ):
            return "rejected_not_repairable", None
        pages = tuple(
            page_id
            for page_id in finding.page_ids
            if page_id in route_by_page
        )
        if not pages:
            return "rejected_not_repairable", None
        page_id = pages[0]
        hashes = tuple((path, manifest_hashes[path]) for path in files)
        items.append(
            RefinementPlanItem(
                finding_id=finding.finding_id,
                page_id=page_id,
                routes=tuple(
                    dict.fromkeys(
                        route_by_page[item]
                        for item in pages
                    )
                ),
                component_ids=finding.component_ids,
                allowed_files=tuple(files),
                original_hashes=hashes,
                issue_type=finding.issue_type,
                objective=(
                    f"Resolve {finding.issue_type} using only the cited "
                    f"evidence while preserving every canonical contract."
                ),
                evidence_ids=finding.evidence_ids,
                immutable_constraints=_IMMUTABLE_CONSTRAINTS,
                validation_requirements=_VALIDATIONS,
                priority=priority,
                expected_dimension_impact=finding.dimension_ids,
            )
        )
        all_files.extend(files)
        all_pages.extend(pages)
    allowed_files = tuple(
        path
        for path in manifest_hashes
        if path in set(all_files)
    )
    affected_pages = tuple(
        page.page_id
        for page in context.contracts.page_purpose.pages
        if page.page_id in set(all_pages)
    )
    if (
        len(allowed_files) > limits.max_refinement_files
        or len(affected_pages) > limits.max_refinement_pages
    ):
        return "rejected_not_repairable", None
    plan_key = canonical_sha256(
        {
            "refs": context.refs.model_dump(mode="json"),
            "findings": [item.model_dump(mode="json") for item in actionable],
            "allowed_files": [
                (path, manifest_hashes[path]) for path in allowed_files
            ],
            "policy_revision": "2026-07-24.1",
        }
    )
    return (
        "rejected_repairable",
        RefinementPlan(
            refs=context.refs,
            cache_key=plan_key,
            repairability="rejected_repairable",
            items=tuple(items),
            allowed_files=allowed_files,
            affected_page_ids=affected_pages,
        ),
    )


def refinement_prompt_values(
    context: VisualEvaluationContext,
    plan: RefinementPlan,
    findings: tuple[VisualFinding, ...],
) -> dict:
    sources = [
        {
            "path": path,
            "sha256": dict(
                pair
                for item in plan.items
                for pair in item.original_hashes
            )[path],
            "source": (context.candidate_workspace / path).read_text(
                encoding="utf-8"
            ),
        }
        for path in plan.allowed_files
    ]
    composition = context.contracts.composition
    contracts = {
        "design_dna": composition.design_dna.model_dump(mode="json"),
        "page_purpose": context.contracts.page_purpose.model_dump(mode="json"),
        "business_components": (
            context.contracts.business_components.model_dump(mode="json")
        ),
        "interactions": context.contracts.interactions.model_dump(mode="json"),
    }
    return {
        "refinement_plan_json": canonical_json(plan.model_dump(mode="json")),
        "allowed_sources_json": canonical_json(sources),
        "contracts_json": canonical_json(contracts),
        "findings_json": canonical_json(
            [item.model_dump(mode="json") for item in findings]
        ),
    }


def refinement_images(
    bundle: VisualEvidenceBundle,
    plan: RefinementPlan,
) -> tuple[Path, ...]:
    ids = tuple(
        dict.fromkeys(
            evidence_id
            for item in plan.items
            for evidence_id in item.evidence_ids
        )
    )
    return evidence_absolute_paths(bundle, ids)


def _candidate_sources(
    db: Session,
    context: VisualEvaluationContext,
) -> tuple[
    tuple[CandidateSourceFile, ...],
    tuple[CandidateSourceFile, ...],
    tuple[CandidateSourceFile, ...],
]:
    manifests = _artifact_manifests(db, context.candidate)
    all_sources = []
    data_sources = []
    route_sources = []
    seen = set()
    for kind, manifest in manifests.items():
        for descriptor in manifest.files:
            if descriptor.path in seen:
                continue
            seen.add(descriptor.path)
            source = (context.candidate_workspace / descriptor.path).read_text(
                encoding="utf-8"
            )
            item = CandidateSourceFile(
                path=descriptor.path,
                file_kind=descriptor.file_kind,
                owner_contract_ids=descriptor.owner_contract_ids,
                source=source,
            )
            all_sources.append(item)
            if kind == "data_exports":
                data_sources.append(item)
            if kind == "routes":
                route_sources.append(item)
    return tuple(all_sources), tuple(data_sources), tuple(route_sources)


def _validate_output(
    output: RefinementOutput,
    *,
    allowed_hashes: dict[str, str],
    current_hashes: dict[str, str],
) -> None:
    paths = tuple(item.path for item in output.files)
    if set(paths) != set(allowed_hashes) or len(paths) != len(allowed_hashes):
        raise ValueError("Refinement did not return exactly the allowed files")
    for item in output.files:
        if (
            item.original_sha256 != current_hashes[item.path]
            or item.original_sha256 != allowed_hashes[item.path]
        ):
            raise ValueError("Refinement original file hash is stale")


def derive_candidate(
    db: Session,
    context: VisualEvaluationContext,
    *,
    plan: RefinementPlan,
    output: RefinementOutput,
    technical_output: RefinementOutput | None = None,
) -> DerivedCandidate:
    original_hashes = {
        item["path"]: item["sha256"]
        for item in context.candidate_file_manifest
    }
    allowed_hashes = {
        path: digest
        for item in plan.items
        for path, digest in item.original_hashes
    }
    allowed_hashes = {
        path: allowed_hashes[path] for path in plan.allowed_files
    }
    _validate_output(
        output,
        allowed_hashes=allowed_hashes,
        current_hashes=original_hashes,
    )
    upstream = canonical_sha256(
        {
            "original_candidate": context.refs.candidate_manifest_sha256,
            "plan": artifact_sha256(plan),
            "output": artifact_sha256(output),
            "technical_output": (
                artifact_sha256(technical_output)
                if technical_output
                else None
            ),
        }
    )
    workspace = open_candidate_workspace(
        request_id=context.refs.request_id,
        upstream_sha256=upstream,
        policy_revision=context.candidate.policy_revision,
    )
    if workspace.resumed:
        shutil.rmtree(workspace.staging_path)
        workspace.staging_path.mkdir(parents=True)
    shutil.copytree(
        context.candidate_workspace,
        workspace.staging_path,
        dirs_exist_ok=True,
        copy_function=shutil.copy2,
    )
    sources, data_sources, route_sources = _candidate_sources(db, context)
    source_map = {item.path: item for item in sources}
    changed = []
    for item in output.files:
        original = source_map[item.path]
        replacement = CandidateSourceFile(
            path=item.path,
            file_kind=original.file_kind,
            owner_contract_ids=original.owner_contract_ids,
            source=item.source,
        )
        source_map[item.path] = replacement
        changed.append(replacement)
    write_sources(workspace, tuple(changed))
    report = validate_candidate_workspace(
        workspace,
        context=context.contracts,
        expected_sources=tuple(source_map[item.path] for item in sources),
        data_sources=data_sources,
        route_sources=route_sources,
    )
    repair_count = 0
    if not report.passed and technical_output is not None:
        current_hashes = {
            path: sha256_text(
                (workspace.staging_path / path).read_text(encoding="utf-8")
            )
            for path in plan.allowed_files
        }
        _validate_output(
            technical_output,
            allowed_hashes=current_hashes,
            current_hashes=current_hashes,
        )
        repaired = []
        for item in technical_output.files:
            original = source_map[item.path]
            replacement = CandidateSourceFile(
                path=item.path,
                file_kind=original.file_kind,
                owner_contract_ids=original.owner_contract_ids,
                source=item.source,
            )
            source_map[item.path] = replacement
            repaired.append(replacement)
        write_sources(workspace, tuple(repaired))
        report = validate_candidate_workspace(
            workspace,
            context=context.contracts,
            expected_sources=tuple(source_map[item.path] for item in sources),
            data_sources=data_sources,
            route_sources=route_sources,
        )
        repair_count = 1
    if not report.passed:
        raise StaticValidationFailure(
            "Refined candidate failed Phase 3B static validation: "
            + canonical_json(
                [item.model_dump(mode="json") for item in report.issues]
            )[:4000]
        )
    final_path = freeze_candidate_workspace(workspace)
    manifest = source_file_manifest(final_path)
    manifest_hashes = {item["path"]: item["sha256"] for item in manifest}
    unaffected_before = canonical_sha256(
        [
            item
            for item in context.candidate_file_manifest
            if item["path"] not in set(plan.allowed_files)
        ]
    )
    unaffected_after = canonical_sha256(
        [item for item in manifest if item["path"] not in set(plan.allowed_files)]
    )
    if unaffected_before != unaffected_after:
        raise ValueError("Refinement changed a non-allowlisted file")
    revision_number = int(
        db.query(func.max(CandidateRevisionRecord.revision))
        .filter(CandidateRevisionRecord.request_id == context.refs.request_id)
        .scalar()
        or 0
    ) + 1
    row = CandidateRevisionRecord(
        revision_uuid=workspace.revision_uuid,
        request_id=context.refs.request_id,
        revision=revision_number,
        target_tier=context.candidate.target_tier,
        status="candidate_build_pending",
        generator_version="v2-phase5-refined",
        policy_revision="2026-07-24.1",
        upstream_manifest_json=context.candidate.upstream_manifest_json,
        upstream_manifest_sha256=context.candidate.upstream_manifest_sha256,
        dependency_lock_sha256=context.candidate.dependency_lock_sha256,
        model_manifest_json=canonical_json(
            {
                "phase": "phase5_refinement",
                "parent_candidate_revision_id": context.candidate.id,
                "refinement_plan_sha256": artifact_sha256(plan),
                "refinement_output_sha256": artifact_sha256(output),
                "technical_repair_count": repair_count,
            }
        ),
        workspace_relpath=workspace_relpath(final_path),
        file_manifest_json=canonical_json(manifest),
        file_manifest_sha256=canonical_sha256(manifest),
        foundation_artifact_id=context.candidate.foundation_artifact_id,
        data_artifact_id=context.candidate.data_artifact_id,
        component_artifact_id=context.candidate.component_artifact_id,
        page_artifact_id=context.candidate.page_artifact_id,
        route_artifact_id=context.candidate.route_artifact_id,
        validation_artifact_id=context.candidate.validation_artifact_id,
        failure_json="{}",
        provider_call_count=0,
        repair_call_count=repair_count,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        cost_usd=0.0,
        latency_ms=0,
        completed_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    if row.file_manifest_sha256 != canonical_sha256(manifest):
        raise ValueError("Derived candidate manifest hash changed")
    phase3b = dict(context.phase4_summary)
    phase3b["status"] = "candidate_build_pending"
    phase3b["candidate_revision"] = {
        "id": row.id,
        "revision_uuid": row.revision_uuid,
        "revision": row.revision,
        "target_tier": context.candidate.target_tier,
        "workspace_relpath": row.workspace_relpath,
        "file_manifest_sha256": row.file_manifest_sha256,
    }
    for key in (
        "runtime_validation_summary",
        "runtime_build",
        "runtime_validation_workspace",
        "runtime_validation",
        "visual_evaluation_summary",
    ):
        phase3b.pop(key, None)
    return DerivedCandidate(
        revision=row,
        phase3b_result={"preview_contract": phase3b},
        static_report=report,
        allowed_before=tuple(
            (path, original_hashes[path]) for path in plan.allowed_files
        ),
        allowed_after=tuple(
            (path, manifest_hashes[path]) for path in plan.allowed_files
        ),
        unaffected_before=unaffected_before,
        unaffected_after=unaffected_after,
        technical_repair_count=repair_count,
    )


__all__ = [
    "DerivedCandidate",
    "StaticValidationFailure",
    "classify_and_build_plan",
    "derive_candidate",
    "refinement_images",
    "refinement_prompt_values",
]
