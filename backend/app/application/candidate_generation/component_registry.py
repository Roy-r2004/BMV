"""Deterministic business-component registry and required page bindings."""
from __future__ import annotations

import re
from typing import Iterable

from app.application.candidate_generation.cache import (
    canonical_sha256,
    sha256_text,
)
from app.application.candidate_generation.context import CandidateContext
from app.application.candidate_generation.deterministic import (
    component_export_symbol,
)
from app.domain.schemas.business_component_usage import (
    BusinessComponentRegistry,
    BusinessComponentRegistryEntry,
    RequiredBusinessComponentBinding,
)
from app.domain.schemas.preview_candidate import (
    CandidateValidationIssue,
    GeneratedCandidateBatch,
)


_EXPORT_FUNCTION_RE = re.compile(
    r"export\s+function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("
)
_EXPORT_CONST_RE = re.compile(
    r"export\s+(?:const|let)\s+([A-Za-z_][A-Za-z0-9_]*)\s*="
)


def _issue(
    code: str,
    message: str,
    *,
    path: str = "",
    related_ids: Iterable[str] = (),
) -> CandidateValidationIssue:
    return CandidateValidationIssue(
        code=code,
        path=path,
        related_ids=tuple(related_ids),
        message=message,
    )


def extract_exported_symbols(source: str) -> tuple[str, ...]:
    symbols = list(_EXPORT_FUNCTION_RE.findall(source))
    symbols.extend(_EXPORT_CONST_RE.findall(source))
    return tuple(dict.fromkeys(symbols))


def expected_component_module_path(component_id: str) -> str:
    return f"src/components/business/{component_export_symbol(component_id)}.tsx"


def build_business_component_registry(
    *,
    context: CandidateContext,
    component_batch: GeneratedCandidateBatch,
) -> tuple[BusinessComponentRegistry | None, tuple[CandidateValidationIssue, ...]]:
    plan_hash = context.refs.business_component_plan_ref.sha256
    plan_components = {
        item.component_id: item for item in context.business_components.components
    }
    issues: list[CandidateValidationIssue] = []
    entries: list[BusinessComponentRegistryEntry] = []
    owned_files: dict[str, list] = {component_id: [] for component_id in plan_components}
    for item in component_batch.files:
        for owner_id in item.owner_contract_ids:
            if owner_id in owned_files:
                owned_files[owner_id].append(item)

    for component_id, component in plan_components.items():
        files = owned_files.get(component_id) or []
        if not files:
            issues.append(
                _issue(
                    "missing_registry_entry",
                    "Required business component file is missing from the batch.",
                    related_ids=(component_id,),
                )
            )
            continue
        if len(files) != 1:
            issues.append(
                _issue(
                    "ambiguous_registry_entry",
                    "Business component ownership is ambiguous across files.",
                    related_ids=(component_id,),
                )
            )
            continue
        file_item = files[0]
        expected_symbol = component_export_symbol(component_id)
        expected_path = expected_component_module_path(component_id)
        exports = extract_exported_symbols(file_item.source)
        if expected_symbol not in exports:
            issues.append(
                _issue(
                    "component_symbol_mismatch",
                    (
                        f"Component must export {expected_symbol!r}; "
                        f"found {list(exports)!r}."
                    ),
                    path=file_item.path,
                    related_ids=(component_id,),
                )
            )
            continue
        if file_item.path != expected_path:
            issues.append(
                _issue(
                    "component_module_mismatch",
                    (
                        f"Component module must be {expected_path!r}; "
                        f"got {file_item.path!r}."
                    ),
                    path=file_item.path,
                    related_ids=(component_id,),
                )
            )
            continue
        page_ids = tuple(
            page_id
            for page_id in component.page_ids
            if page_id in {page.page_id for page in context.page_purpose.pages}
        )
        if not page_ids:
            # Still register; Tier 1 composition may list it via page_compositions.
            page_ids = tuple(component.page_ids)
        entries.append(
            BusinessComponentRegistryEntry(
                business_component_id=component_id,
                exported_symbol=expected_symbol,
                file_path=file_item.path,
                owning_page_ids=page_ids or tuple(component.page_ids),
                required_props=(),
                source_plan_hash=plan_hash,
                generated_file_hash=sha256_text(file_item.source),
            )
        )

    if issues:
        return None, tuple(issues)
    if not entries:
        return None, (
            _issue(
                "empty_component_registry",
                "No business components were registered for candidate pages.",
            ),
        )
    return (
        BusinessComponentRegistry(
            source_plan_hash=plan_hash,
            entries=tuple(entries),
        ),
        (),
    )


def build_required_business_component_bindings(
    *,
    context: CandidateContext,
    registry: BusinessComponentRegistry,
) -> tuple[
    tuple[RequiredBusinessComponentBinding, ...],
    tuple[CandidateValidationIssue, ...],
]:
    plan_hash = context.refs.business_component_plan_ref.sha256
    plan_revision = context.business_components.schema_version
    registry_by_id = {
        item.business_component_id: item for item in registry.entries
    }
    plan_by_id = {
        item.component_id: item for item in context.business_components.components
    }
    tier_page_ids = {page.page_id for page in context.page_purpose.pages}
    composition_by_page = {
        item.page_id: item.ordered_component_ids
        for item in context.business_components.page_compositions
        if item.page_id in tier_page_ids
    }
    issues: list[CandidateValidationIssue] = []
    bindings: list[RequiredBusinessComponentBinding] = []

    for page_id in sorted(tier_page_ids):
        ordered = composition_by_page.get(page_id)
        if not ordered:
            issues.append(
                _issue(
                    "missing_page_composition",
                    "Tier 1 page has no business-component composition.",
                    related_ids=(page_id,),
                )
            )
            continue
        seen: set[str] = set()
        for component_id in ordered:
            if component_id in seen:
                issues.append(
                    _issue(
                        "ambiguous_page_binding",
                        "Duplicate business component binding on one page.",
                        related_ids=(page_id, component_id),
                    )
                )
                continue
            seen.add(component_id)
            entry = registry_by_id.get(component_id)
            component = plan_by_id.get(component_id)
            if entry is None or component is None:
                issues.append(
                    _issue(
                        "invalid_binding",
                        "Page composition references an unregistered component.",
                        related_ids=(page_id, component_id),
                    )
                )
                continue
            bindings.append(
                RequiredBusinessComponentBinding(
                    page_id=page_id,
                    business_component_id=component_id,
                    component_symbol=entry.exported_symbol,
                    component_module_path=entry.file_path,
                    required_usage_count=1,
                    required_props=entry.required_props,
                    action_ids=component.action_ids,
                    state_ids=component.state_ids,
                    evidence_ids=component.evidence_ids,
                    source_plan_revision=plan_revision,
                    source_plan_hash=plan_hash,
                )
            )

    if issues:
        return (), tuple(issues)
    return tuple(bindings), ()


def bindings_prompt_block(
    bindings: tuple[RequiredBusinessComponentBinding, ...],
) -> dict[str, list[dict]]:
    by_page: dict[str, list[dict]] = {}
    for item in bindings:
        by_page.setdefault(item.page_id, []).append(
            {
                "business_component_id": item.business_component_id,
                "symbol": item.component_symbol,
                "import": (
                    "@/components/business/"
                    + item.component_module_path.rsplit("/", 1)[-1].removesuffix(
                        ".tsx"
                    )
                ),
                "module_path": item.component_module_path,
                "must_mount": True,
                "required_usage_count": item.required_usage_count,
                "required_props": list(item.required_props),
                "obligations": {
                    "action_ids": list(item.action_ids),
                    "state_ids": list(item.state_ids),
                    "evidence_ids": list(item.evidence_ids),
                },
                "source_plan_hash": item.source_plan_hash,
            }
        )
    return by_page


def registry_decision_hash(
    *,
    registry: BusinessComponentRegistry,
    bindings: tuple[RequiredBusinessComponentBinding, ...],
) -> str:
    return canonical_sha256(
        {
            "registry": registry.model_dump(mode="json"),
            "bindings": [item.model_dump(mode="json") for item in bindings],
        }
    )


__all__ = [
    "bindings_prompt_block",
    "build_business_component_registry",
    "build_required_business_component_bindings",
    "expected_component_module_path",
    "extract_exported_symbols",
    "registry_decision_hash",
]
