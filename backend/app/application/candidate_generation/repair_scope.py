"""Scope Phase 3B repair prompts to invalid files and compact contracts."""
from __future__ import annotations

import json
from typing import Any

from app.application.candidate_generation.deterministic import (
    component_export_symbol,
)
from app.domain.schemas.preview_candidate import (
    GeneratedCandidateBatch,
    GeneratedCandidateFile,
)


def _parse_diagnostic(item: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    try:
        parsed = json.loads(item)
    except (TypeError, json.JSONDecodeError):
        return {"message": str(item)[:1000]}
    return parsed if isinstance(parsed, dict) else {"message": str(item)[:1000]}


def collect_repair_targets(
    *,
    batch: GeneratedCandidateBatch,
    diagnostics: tuple[str, ...] | list[str] | list[dict[str, Any]],
) -> tuple[tuple[GeneratedCandidateFile, ...], tuple[dict[str, Any], ...]]:
    """Return invalid files (preserving batch order) and parsed diagnostics."""

    parsed = tuple(_parse_diagnostic(item) for item in diagnostics)
    path_hits: set[str] = set()
    owner_hits: set[str] = set()
    for item in parsed:
        path = str(item.get("path") or "").strip()
        if path:
            path_hits.add(path)
        related = item.get("related_ids") or []
        if isinstance(related, (list, tuple)):
            owner_hits.update(str(value) for value in related if value)

    selected: list[GeneratedCandidateFile] = []
    for file_item in batch.files:
        owners = set(file_item.owner_contract_ids or ())
        if file_item.path in path_hits or owners.intersection(owner_hits):
            selected.append(file_item)

    if not selected:
        # Fail-closed fallback: keep full batch so repair can still run.
        selected = list(batch.files)
    return tuple(selected), parsed


def compact_component_contract(
    *,
    batch_stage: str,
    selected_files: tuple[GeneratedCandidateFile, ...],
    diagnostics: tuple[dict[str, Any], ...],
    canonical_bindings: dict[str, Any],
) -> dict[str, Any]:
    """Build a compact repair contract without unrelated upstream dumps."""

    owner_ids: set[str] = set()
    for file_item in selected_files:
        owner_ids.update(str(value) for value in (file_item.owner_contract_ids or ()))
    for item in diagnostics:
        related = item.get("related_ids") or []
        if isinstance(related, (list, tuple)):
            owner_ids.update(str(value) for value in related if value)

    plan = canonical_bindings.get("business_component_plan") or {}
    components = plan.get("components") if isinstance(plan, dict) else None
    compact_components: list[dict[str, Any]] = []
    if isinstance(components, list):
        for component in components:
            if not isinstance(component, dict):
                continue
            component_id = str(component.get("component_id") or "")
            if owner_ids and component_id not in owner_ids:
                continue
            symbol = component_export_symbol(component_id) if component_id else ""
            compact_components.append(
                {
                    "component_id": component_id,
                    "export_symbol": symbol,
                    "module_path": (
                        f"src/components/business/{symbol}.tsx" if symbol else ""
                    ),
                    "purpose": str(component.get("purpose") or "")[:240],
                    "required_props": component.get("required_props") or [],
                }
            )

    page_bindings = canonical_bindings.get(
        "required_business_component_bindings"
    ) or {}
    return {
        "batch_kind": batch_stage,
        "validation_error_count": len(diagnostics),
        "files_included_count": len(selected_files),
        "required_component_exports": compact_components,
        "required_business_component_bindings": page_bindings
        if batch_stage == "pages"
        else {},
    }


def scoped_failed_batch(
    *,
    batch: GeneratedCandidateBatch,
    selected_files: tuple[GeneratedCandidateFile, ...],
) -> GeneratedCandidateBatch:
    return GeneratedCandidateBatch(
        schema_version=batch.schema_version,
        batch_kind=batch.batch_kind,
        files=list(selected_files),
    )


def merge_repaired_files(
    *,
    original: GeneratedCandidateBatch,
    repaired: GeneratedCandidateBatch,
) -> GeneratedCandidateBatch:
    """Merge repaired subset files back into the original batch path set."""

    if repaired.batch_kind != original.batch_kind:
        raise ValueError("repaired batch_kind mismatch")
    repaired_by_path = {item.path: item for item in repaired.files}
    original_paths = {item.path for item in original.files}
    unknown = set(repaired_by_path) - original_paths
    if unknown:
        raise ValueError(f"repair introduced unknown paths: {sorted(unknown)}")
    merged = [
        repaired_by_path.get(item.path, item) for item in original.files
    ]
    return GeneratedCandidateBatch(
        schema_version=original.schema_version,
        batch_kind=original.batch_kind,
        files=merged,
    )


__all__ = [
    "collect_repair_targets",
    "compact_component_contract",
    "merge_repaired_files",
    "scoped_failed_batch",
]
