"""Precise business-component usage validation and bounded deterministic heal."""
from __future__ import annotations

import re
from typing import Iterable

from app.application.candidate_generation.cache import (
    canonical_sha256,
    sha256_text,
)
from app.application.candidate_generation.page_skeleton import (
    ensure_protected_business_component_region,
)
from app.domain.schemas.business_component_usage import (
    BusinessComponentUsageEvidence,
    BusinessComponentUsageEvidenceItem,
    RequiredBusinessComponentBinding,
    UsageMountKind,
    UsageValidationResult,
)
from app.domain.schemas.preview_candidate import (
    CandidateValidationIssue,
    GeneratedCandidateBatch,
    GeneratedCandidateFile,
)


_IMPORT_NAMED_RE = re.compile(
    r"""import\s*\{([^}]+)\}\s*from\s*["']([^"']+)["']"""
)
_IMPORT_DEFAULT_RE = re.compile(
    r"""import\s+([A-Za-z_][A-Za-z0-9_]*)\s+from\s*["']([^"']+)["']"""
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


def _normalize_module(specifier: str) -> str:
    cleaned = specifier.strip().replace("\\", "/")
    if cleaned.startswith("@/"):
        return "src/" + cleaned[2:]
    if cleaned.startswith("../components/business/"):
        return "src/components/business/" + cleaned.rsplit("/", 1)[-1]
    if cleaned.startswith("./") or cleaned.startswith("../"):
        return cleaned
    return cleaned


def _module_matches(specifier: str, expected_path: str) -> bool:
    expected_stem = expected_path.removesuffix(".tsx").removesuffix(".ts")
    normalized = _normalize_module(specifier)
    if normalized.endswith((".tsx", ".ts")):
        candidate = "src/" + normalized.removeprefix("src/") if not normalized.startswith("src/") else normalized
        if normalized.startswith("../") or normalized.startswith("./"):
            # Relative imports from src/pages resolve to business components.
            leaf = normalized.rsplit("/", 1)[-1].removesuffix(".tsx").removesuffix(".ts")
            return expected_stem.endswith("/" + leaf) or expected_stem.endswith(leaf)
        return candidate.removesuffix(".tsx").removesuffix(".ts") == expected_stem
    leaf = normalized.rsplit("/", 1)[-1]
    return expected_stem.endswith("/" + leaf) or expected_path.endswith(
        "/" + leaf + ".tsx"
    )


def _find_named_import(
    source: str,
    *,
    symbol: str,
    expected_path: str,
) -> tuple[bool, str]:
    for names, specifier in _IMPORT_NAMED_RE.findall(source):
        imported = {part.strip() for part in names.split(",") if part.strip()}
        # Support `Foo as Bar`.
        resolved = set()
        for part in imported:
            if " as " in part:
                original, alias = [bit.strip() for bit in part.split(" as ", 1)]
                resolved.add(alias or original)
                resolved.add(original)
            else:
                resolved.add(part)
        if symbol in resolved and _module_matches(specifier, expected_path):
            return True, specifier
    return False, ""


def _jsx_mount_count(source: str, symbol: str) -> int:
    pattern = re.compile(rf"<{re.escape(symbol)}(?:\s|>|/)")
    return len(pattern.findall(source))


def _registry_mount(source: str, component_id: str, symbol: str) -> bool:
    markers = (
        f'resolveBusinessComponent("{component_id}")',
        f"resolveBusinessComponent('{component_id}')",
        f'BusinessComponentRegistry["{component_id}"]',
        f"BusinessComponentRegistry['{component_id}']",
        f"<{symbol}",
    )
    return any(marker in source for marker in markers[:4]) and (
        f"<{symbol}" in source or component_id in source
    )


def validate_binding_against_source(
    *,
    source: str,
    binding: RequiredBusinessComponentBinding,
    component_file_exists: bool,
    repair_attempt: int = 0,
    before_file_hash: str | None = None,
    after_file_hash: str | None = None,
) -> BusinessComponentUsageEvidenceItem:
    if not component_file_exists:
        return BusinessComponentUsageEvidenceItem(
            page_id=binding.page_id,
            business_component_id=binding.business_component_id,
            expected_symbol=binding.component_symbol,
            expected_module=binding.component_module_path,
            component_file_exists=False,
            import_found=False,
            mount_found=False,
            required_props_present=False,
            obligations_represented=False,
            result="missing_file",
            repair_attempt=repair_attempt,
            before_file_hash=before_file_hash,
            after_file_hash=after_file_hash,
        )

    import_found, actual_module = _find_named_import(
        source,
        symbol=binding.component_symbol,
        expected_path=binding.component_module_path,
    )
    mount_count = _jsx_mount_count(source, binding.component_symbol)
    registry_mount = _registry_mount(
        source,
        binding.business_component_id,
        binding.component_symbol,
    )
    mount_found = mount_count >= binding.required_usage_count or registry_mount
    mount_kind: UsageMountKind | None = None
    usage_location = ""
    if mount_count >= binding.required_usage_count:
        mount_kind = "direct_jsx"
        match = re.search(
            rf"<{re.escape(binding.component_symbol)}(?:\s|>|/)",
            source,
        )
        if match:
            usage_location = f"jsx:{match.start()}"
    elif registry_mount:
        mount_kind = "registry_lookup"
        usage_location = "registry"

    props_ok = True
    for prop in binding.required_props:
        # Require JSX prop presence when declared; otherwise fail closed.
        if f"{prop}=" not in source and f"{prop} =" not in source:
            props_ok = False
            break

    obligations_ok = mount_found  # component owns action/state/evidence hooks

    result: UsageValidationResult
    if not import_found and not mount_found:
        result = "missing_import"
    elif not import_found:
        result = "missing_import"
    elif not mount_found:
        result = "missing_mount"
    elif not props_ok:
        result = "missing_props"
    elif mount_count > binding.required_usage_count * 3:
        result = "ambiguous_usage"
    else:
        result = "satisfied"

    return BusinessComponentUsageEvidenceItem(
        page_id=binding.page_id,
        business_component_id=binding.business_component_id,
        expected_symbol=binding.component_symbol,
        expected_module=binding.component_module_path,
        actual_symbol=binding.component_symbol if import_found else "",
        actual_module=actual_module,
        component_file_exists=True,
        import_found=import_found,
        mount_found=mount_found,
        mount_kind=mount_kind,
        usage_location=usage_location,
        required_props_present=props_ok,
        obligations_represented=obligations_ok,
        result=result,
        repair_attempt=repair_attempt,
        before_file_hash=before_file_hash,
        after_file_hash=after_file_hash or sha256_text(source),
    )


def validate_business_component_usage(
    *,
    batch: GeneratedCandidateBatch,
    bindings: tuple[RequiredBusinessComponentBinding, ...],
    component_paths: set[str],
    repair_attempt: int = 0,
    previous_hashes: dict[str, str] | None = None,
) -> tuple[
    tuple[BusinessComponentUsageEvidenceItem, ...],
    tuple[CandidateValidationIssue, ...],
]:
    page_sources: dict[str, GeneratedCandidateFile] = {}
    for item in batch.files:
        for owner_id in item.owner_contract_ids:
            page_sources.setdefault(owner_id, item)

    evidence: list[BusinessComponentUsageEvidenceItem] = []
    issues: list[CandidateValidationIssue] = []
    previous_hashes = previous_hashes or {}

    for binding in bindings:
        page_file = page_sources.get(binding.page_id)
        source = page_file.source if page_file is not None else ""
        path = page_file.path if page_file is not None else ""
        item = validate_binding_against_source(
            source=source,
            binding=binding,
            component_file_exists=binding.component_module_path in component_paths,
            repair_attempt=repair_attempt,
            before_file_hash=previous_hashes.get(path),
            after_file_hash=sha256_text(source) if source else None,
        )
        evidence.append(item)
        if item.result == "satisfied":
            continue
        code = (
            "missing_business_component_usage"
            if item.result
            in {"missing_import", "missing_mount", "missing_file"}
            else f"business_component_usage_{item.result}"
        )
        issues.append(
            _issue(
                code,
                (
                    f"{binding.page_id} must mount {binding.business_component_id} "
                    f"via {binding.component_symbol} from {binding.component_module_path} "
                    f"({item.result})."
                ),
                path=path,
                related_ids=(binding.page_id, binding.business_component_id),
            )
        )
    return tuple(evidence), tuple(issues)


def heal_missing_business_component_usage(
    *,
    batch: GeneratedCandidateBatch,
    bindings: tuple[RequiredBusinessComponentBinding, ...],
    evidence: tuple[BusinessComponentUsageEvidenceItem, ...],
) -> tuple[GeneratedCandidateBatch, dict[str, str], bool]:
    """Insert missing imports/mounts once when bindings are unambiguous.

    Returns (batch, before_hashes_by_path, healed).
    """

    failing = {
        (item.page_id, item.business_component_id)
        for item in evidence
        if item.result in {"missing_import", "missing_mount"}
    }
    if not failing:
        return batch, {}, False

    # Fail closed when any binding for a page is invalid/ambiguous/missing props/file.
    blocked_pages = {
        item.page_id
        for item in evidence
        if item.result
        in {
            "missing_file",
            "missing_props",
            "ambiguous_usage",
            "invalid_binding",
        }
    }
    bindings_by_page: dict[str, list[RequiredBusinessComponentBinding]] = {}
    for binding in bindings:
        bindings_by_page.setdefault(binding.page_id, []).append(binding)

    before_hashes: dict[str, str] = {}
    repaired_files: list[GeneratedCandidateFile] = []
    healed = False
    for item in batch.files:
        page_ids = [
            owner
            for owner in item.owner_contract_ids
            if owner in bindings_by_page
        ]
        if not page_ids or any(page_id in blocked_pages for page_id in page_ids):
            repaired_files.append(item)
            continue
        page_id = page_ids[0]
        page_bindings = tuple(bindings_by_page[page_id])
        needs_heal = any(
            (page_id, binding.business_component_id) in failing
            for binding in page_bindings
        )
        if not needs_heal:
            repaired_files.append(item)
            continue
        # Ambiguous ownership across multiple page IDs fails closed.
        if len(page_ids) != 1:
            repaired_files.append(item)
            continue
        before_hashes[item.path] = sha256_text(item.source)
        healed_source = ensure_protected_business_component_region(
            source=item.source,
            bindings=page_bindings,
        )
        if healed_source != item.source:
            healed = True
        repaired_files.append(item.model_copy(update={"source": healed_source}))
    if not healed:
        return batch, before_hashes, False
    return (
        batch.model_copy(update={"files": tuple(repaired_files)}),
        before_hashes,
        True,
    )


def build_usage_evidence(
    *,
    request_id: int,
    candidate_revision_uuid: str,
    component_plan_hash: str,
    bindings: tuple[RequiredBusinessComponentBinding, ...],
    items: tuple[BusinessComponentUsageEvidenceItem, ...],
    deterministic_heal_used: bool,
    ai_repair_used: bool,
) -> BusinessComponentUsageEvidence:
    decision_hash = canonical_sha256(
        {
            "request_id": request_id,
            "candidate_revision_uuid": candidate_revision_uuid,
            "component_plan_hash": component_plan_hash,
            "deterministic_heal_used": deterministic_heal_used,
            "ai_repair_used": ai_repair_used,
            "items": [item.model_dump(mode="json") for item in items],
        }
    )
    return BusinessComponentUsageEvidence(
        request_id=request_id,
        candidate_revision_uuid=candidate_revision_uuid,
        component_plan_hash=component_plan_hash,
        deterministic_heal_used=deterministic_heal_used,
        ai_repair_used=ai_repair_used,
        decision_hash=decision_hash,
        bindings=bindings,
        items=items,
    )


__all__ = [
    "build_usage_evidence",
    "heal_missing_business_component_usage",
    "validate_binding_against_source",
    "validate_business_component_usage",
]
