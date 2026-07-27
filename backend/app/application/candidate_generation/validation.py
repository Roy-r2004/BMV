"""Fail-closed Phase 3B batch and deterministic pre-build validation."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from app.application.appspec.source import canonical_json
from app.application.candidate_generation.cache import (
    canonical_sha256,
    sha256_text,
)
from app.application.candidate_generation.context import CandidateContext
from app.application.candidate_generation.deterministic import (
    CandidateSourceFile,
    build_content_data_module,
    component_export_symbol,
)
from app.application.candidate_generation.generated_data_api import (
    exported_symbols,
    heal_generated_data_record_shapes,
    heal_generated_data_symbols,
    validate_generated_data_imports,
)
from app.application.candidate_generation.component_registry import (
    build_business_component_registry,
    build_required_business_component_bindings,
)
from app.application.candidate_generation.usage_validation import (
    validate_business_component_usage,
)
from app.application.candidate_generation.workspace import (
    CandidateWorkspace,
    read_source,
    source_file_manifest,
)
from app.core.config import settings
from app.domain.schemas.business_component_usage import (
    RequiredBusinessComponentBinding,
)
from app.domain.schemas.preview_candidate import (
    CandidateValidationIssue,
    CandidateValidationReport,
    GeneratedCandidateBatch,
    GeneratedCandidateFile,
)


APPROVED_RUNTIME_PACKAGES = {
    "@radix-ui/react-dialog",
    "@radix-ui/react-select",
    "@radix-ui/react-tabs",
    "@radix-ui/react-tooltip",
    "@tanstack/react-table",
    "animejs",
    "class-variance-authority",
    "clsx",
    "date-fns",
    "lucide-react",
    "motion",
    "react",
    "react-dom",
    "react-router-dom",
    "recharts",
    "sonner",
    "tailwind-merge",
}
_DEV_PACKAGES = {
    "@tailwindcss/vite",
    "@vitejs/plugin-react",
    "vite",
}
_PROHIBITED_MARKERS = (
    "@/ui",
    "SkeletonComposer",
    "MarketingHero",
    "FeatureBento",
    "ProductShowcase",
    "OpsShell",
    "StatCard",
    "DataTable",
    "ChartCard",
    "catalogue",
)
_IMPORT_RE = re.compile(
    r"""(?:import|export)\s+(?:[\s\S]*?\s+from\s+)?["']([^"']+)["']"""
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


def batch_sources(
    batch: GeneratedCandidateBatch,
) -> tuple[CandidateSourceFile, ...]:
    return tuple(
        CandidateSourceFile(
            path=item.path,
            file_kind=item.file_kind,
            owner_contract_ids=item.owner_contract_ids,
            source=item.source,
        )
        for item in batch.files
    )


def deterministic_repair_batch(
    batch: GeneratedCandidateBatch,
) -> GeneratedCandidateBatch:
    repaired = []
    for item in batch.files:
        source = item.source.strip()
        if source.startswith("```") and source.endswith("```"):
            source = re.sub(r"^```(?:tsx?|typescript)?\s*", "", source)
            source = re.sub(r"\s*```$", "", source)
        source = source.replace("\\\\", "/")
        repaired.append(item.model_copy(update={"source": source}))
    return batch.model_copy(update={"files": tuple(repaired)})


def _inject_transition_hook(
    source: str,
    *,
    transition_id: str,
    action_id: str,
) -> str:
    marker = f'data-bmv-transition-id="{transition_id}"'
    if marker in source:
        return source
    action_marker = f'data-bmv-action-id="{action_id}"'
    action_idx = source.find(action_marker)
    if action_idx >= 0:
        tag_end = source.find(">", action_idx)
        if tag_end >= 0 and marker not in source[action_idx:tag_end]:
            return (
                source[:action_idx]
                + f"{action_marker} {marker}"
                + source[action_idx + len(action_marker) :]
            )
    button_match = re.search(r"<button\b([^>]*)>", source)
    if button_match is not None:
        attrs = button_match.group(1)
        if marker not in attrs:
            replaced = (
                f"<button{attrs} {marker}>"
                if attrs.strip()
                else f"<button {marker}>"
            )
            return (
                source[: button_match.start()]
                + replaced
                + source[button_match.end() :]
            )
    sentinel = f'      <span hidden {marker} />\n'
    close_idx = source.rfind("</")
    if close_idx >= 0:
        return source[:close_idx] + sentinel + source[close_idx:]
    return source + "\n" + sentinel


def heal_missing_transition_hooks(
    batch: GeneratedCandidateBatch,
    *,
    context: CandidateContext,
) -> tuple[GeneratedCandidateBatch, bool]:
    """Inject omitted canonical transition hooks into trigger components."""

    if batch.batch_kind != "business_components":
        return batch, False
    combined = "\n".join(item.source for item in batch.files)
    missing_by_component: dict[str, list[tuple[str, str]]] = {}
    for interaction in context.interactions.interactions:
        for transition in interaction.transitions:
            marker = f'data-bmv-transition-id="{transition.transition_id}"'
            if marker in combined:
                continue
            missing_by_component.setdefault(
                interaction.trigger_component_id,
                [],
            ).append((interaction.action_id, transition.transition_id))
    if not missing_by_component:
        return batch, False

    repaired_files: list[GeneratedCandidateFile] = []
    healed = False
    for item in batch.files:
        injections: list[tuple[str, str]] = []
        for owner in item.owner_contract_ids:
            injections.extend(missing_by_component.get(owner) or ())
        if not injections:
            repaired_files.append(item)
            continue
        source = item.source
        for action_id, transition_id in injections:
            updated = _inject_transition_hook(
                source,
                transition_id=transition_id,
                action_id=action_id,
            )
            if updated != source:
                healed = True
                source = updated
        repaired_files.append(item.model_copy(update={"source": source}))
    if not healed:
        return batch, False
    return batch.model_copy(update={"files": tuple(repaired_files)}), True


def heal_invented_generated_data_imports(
    batch: GeneratedCandidateBatch,
    *,
    context: CandidateContext,
) -> tuple[GeneratedCandidateBatch, tuple[str, ...]]:
    """Rewrite near-miss generated-data imports onto their canonical symbols.

    The canonical API is deterministic, so an invented accessor such as
    ``getServicesSeedData`` resolves to exactly one exported symbol. Rewriting
    it here keeps the failure out of tsc without spending a repair call.
    """

    module_source, manifest = build_content_data_module(context)
    allowed = exported_symbols(module_source)
    healed_files: list[GeneratedCandidateFile] = []
    applied: list[str] = []
    for item in batch.files:
        if item.file_kind not in {"business_component", "page"}:
            healed_files.append(item)
            continue
        source, rewrites = heal_generated_data_symbols(
            item.source,
            manifest=manifest,
            allowed_symbols=allowed,
        )
        if not rewrites:
            healed_files.append(item)
            continue
        applied.extend(
            f"{item.path}:{invented}->{canonical}"
            for invented, canonical in rewrites
        )
        healed_files.append(item.model_copy(update={"source": source}))
    if not applied:
        return batch, ()
    return (
        batch.model_copy(update={"files": tuple(healed_files)}),
        tuple(applied),
    )


def heal_generated_data_record_shapes_in_batch(
    batch: GeneratedCandidateBatch,
    *,
    context: CandidateContext,
) -> tuple[
    GeneratedCandidateBatch,
    tuple[dict[str, object], ...],
    tuple[CandidateValidationIssue, ...],
]:
    """Flatten only compiler-AST-proven legacy record wrappers once per batch."""

    module_source, manifest = build_content_data_module(context)
    healed_files: list[GeneratedCandidateFile] = []
    evidence: list[dict[str, object]] = []
    issues: list[CandidateValidationIssue] = []
    for item in batch.files:
        if item.file_kind not in {"business_component", "page"}:
            healed_files.append(item)
            continue
        source, file_evidence, file_issues = heal_generated_data_record_shapes(
            item.source,
            path=item.path,
            manifest=manifest,
            content_data_module=module_source,
        )
        evidence.extend(file_evidence)
        issues.extend(
            _issue(
                str(issue["code"]),
                str(issue["message"]),
                path=item.path,
            )
            for issue in file_issues
        )
        healed_files.append(item.model_copy(update={"source": source}))
    if issues:
        return batch, (), tuple(issues)
    if not evidence:
        return batch, (), ()
    return (
        batch.model_copy(update={"files": tuple(healed_files)}),
        tuple(evidence),
        (),
    )


def _validate_generated_data_api(
    workspace: CandidateWorkspace,
    *,
    context: CandidateContext,
    expected_sources: tuple[CandidateSourceFile, ...],
) -> list[CandidateValidationIssue]:
    """Fail closed when generated code imports a symbol that does not exist."""

    module_source = read_source(
        workspace,
        "src/generated/content-data.ts",
    )
    if not module_source:
        return []
    allowed = exported_symbols(module_source)
    _emitted, manifest = build_content_data_module(context)
    issues: list[CandidateValidationIssue] = []
    for item in expected_sources:
        if item.file_kind not in {"business_component", "page"}:
            continue
        source = read_source(workspace, item.path)
        if not source:
            continue
        for invented in validate_generated_data_imports(
            path=item.path,
            source=source,
            manifest=manifest,
            allowed_symbols=allowed,
        ):
            suggestion = invented["suggestion"]
            hint = (
                f" Use {suggestion!r} instead."
                if suggestion
                else " Import only symbols declared by the generated-data API."
            )
            issues.append(
                _issue(
                    "generated_data_api_unknown_export",
                    (
                        f"{manifest.module_specifier} does not export "
                        f"{invented['symbol']!r}.{hint}"
                    ),
                    path=item.path,
                    related_ids=(),
                )
            )
    return issues


def validate_generated_batch(
    batch: GeneratedCandidateBatch,
    *,
    context: CandidateContext,
    required_bindings: tuple[RequiredBusinessComponentBinding, ...] | None = None,
) -> tuple[CandidateValidationIssue, ...]:
    issues: list[CandidateValidationIssue] = []
    component_ids = {
        item.component_id for item in context.business_components.components
    }
    page_ids = {item.page_id for item in context.page_purpose.pages}
    expected_ids = (
        component_ids if batch.batch_kind == "business_components" else page_ids
    )
    expected_prefix = (
        "src/components/business/"
        if batch.batch_kind == "business_components"
        else "src/pages/"
    )
    expected_kind = (
        "business_component"
        if batch.batch_kind == "business_components"
        else "page"
    )
    owned: list[str] = []
    for item in batch.files:
        owners = expected_ids.intersection(item.owner_contract_ids)
        owned.extend(owners)
        if (
            not item.path.startswith(expected_prefix)
            or not item.path.endswith(".tsx")
            or item.file_kind != expected_kind
        ):
            issues.append(
                _issue(
                    "batch_path_scope",
                    f"{batch.batch_kind} cannot own {item.path}.",
                    path=item.path,
                    related_ids=item.owner_contract_ids,
                )
            )
        unknown_owners = set(item.owner_contract_ids) - expected_ids
        if unknown_owners:
            issues.append(
                _issue(
                    "unknown_batch_owner",
                    "AI output contains non-batch contract owners.",
                    path=item.path,
                    related_ids=sorted(unknown_owners),
                )
            )
        for marker in _PROHIBITED_MARKERS:
            if marker.casefold() in item.source.casefold():
                issues.append(
                    _issue(
                        "legacy_scaffold",
                        f"Prohibited legacy marker {marker!r}.",
                        path=item.path,
                    )
                )
    missing = expected_ids - set(owned)
    duplicates = {item for item in owned if owned.count(item) > 1}
    if missing:
        issues.append(
            _issue(
                "missing_batch_nodes",
                "The AI batch omitted canonical DAG nodes.",
                related_ids=sorted(missing),
            )
        )
    if duplicates:
        issues.append(
            _issue(
                "duplicate_batch_nodes",
                "Canonical DAG nodes must have one owning file.",
                related_ids=sorted(duplicates),
            )
        )

    combined = "\n".join(item.source for item in batch.files)
    if batch.batch_kind == "business_components":
        for component in context.business_components.components:
            owned_files = [
                item
                for item in batch.files
                if component.component_id in item.owner_contract_ids
            ]
            owned_sources = "\n".join(item.source for item in owned_files)
            expected_symbol = component_export_symbol(component.component_id)
            expected_path = (
                f"src/components/business/{expected_symbol}.tsx"
            )
            if component.component_id not in owned_sources:
                issues.append(
                    _issue(
                        "missing_component_hook",
                        "Component ID is not exposed in its owned source.",
                        related_ids=(component.component_id,),
                    )
                )
            if len(owned_files) == 1 and owned_files[0].path != expected_path:
                issues.append(
                    _issue(
                        "component_module_mismatch",
                        (
                            f"Component module must be {expected_path!r}; "
                            f"got {owned_files[0].path!r}."
                        ),
                        path=owned_files[0].path,
                        related_ids=(component.component_id,),
                    )
                )
            if (
                f"export function {expected_symbol}" not in owned_sources
                and f"export const {expected_symbol}" not in owned_sources
            ):
                issues.append(
                    _issue(
                        "component_symbol_mismatch",
                        f"Component must export {expected_symbol!r}.",
                        related_ids=(component.component_id,),
                    )
                )
            for attribute, ids in (
                ("data-bmv-action-id", component.action_ids),
                ("data-bmv-state-id", component.state_ids),
                ("data-bmv-evidence-id", component.evidence_ids),
            ):
                for canonical_id in ids:
                    if attribute not in owned_sources or canonical_id not in owned_sources:
                        issues.append(
                            _issue(
                                "missing_component_contract_hook",
                                f"{attribute} does not expose {canonical_id}.",
                                related_ids=(component.component_id, canonical_id),
                            )
                        )
        for interaction in context.interactions.interactions:
            for transition in interaction.transitions:
                if (
                    "data-bmv-transition-id" not in combined
                    or transition.transition_id not in combined
                ):
                    issues.append(
                        _issue(
                            "missing_transition_hook",
                            "Component batch omitted a canonical transition.",
                            related_ids=(transition.transition_id,),
                        )
                    )
    else:
        for page in context.page_purpose.pages:
            owned_sources = "\n".join(
                item.source
                for item in batch.files
                if page.page_id in item.owner_contract_ids
            )
            if (
                "data-bmv-page-id" not in owned_sources
                or page.page_id not in owned_sources
            ):
                issues.append(
                    _issue(
                        "missing_page_hook",
                        "Page source does not expose its canonical page ID.",
                        related_ids=(page.page_id,),
                    )
                )
            for acceptance_id in page.acceptance_test_ids:
                if (
                    "data-bmv-acceptance-test-id" not in owned_sources
                    or acceptance_id not in owned_sources
                ):
                    issues.append(
                        _issue(
                            "missing_acceptance_hook",
                            "Page omitted an acceptance-test marker.",
                            related_ids=(page.page_id, acceptance_id),
                        )
                    )
            mobile_values = (
                page.mobile.navigation,
                page.mobile.primary_action,
                page.mobile.data_presentation,
                page.mobile.density_adjustment,
            )
            for value in mobile_values:
                if value not in owned_sources:
                    issues.append(
                        _issue(
                            "missing_mobile_binding",
                            "Page omitted an IA mobile contract value.",
                            related_ids=(page.page_id,),
                        )
                    )
        if required_bindings is not None:
            component_paths = {
                item.component_module_path for item in required_bindings
            }
            _evidence, usage_issues = validate_business_component_usage(
                batch=batch,
                bindings=required_bindings,
                component_paths=component_paths,
            )
            issues.extend(usage_issues)
        else:
            # Fail closed when the service forgot to supply bindings.
            issues.append(
                _issue(
                    "missing_business_component_usage",
                    "Tier 1 pages require explicit business-component bindings.",
                )
            )
    return tuple(issues)


def _package_root(specifier: str) -> str:
    if specifier.startswith("@"):
        return "/".join(specifier.split("/")[:2])
    return specifier.split("/", 1)[0]


def _resolve_local_import(
    workspace: Path,
    source_path: Path,
    specifier: str,
) -> bool:
    if specifier.startswith("@/"):
        candidate = workspace / "src" / specifier[2:]
    else:
        candidate = source_path.parent / specifier
    choices = (
        candidate,
        candidate.with_suffix(".ts"),
        candidate.with_suffix(".tsx"),
        candidate.with_suffix(".json"),
        candidate / "index.ts",
        candidate / "index.tsx",
    )
    return any(path.is_file() for path in choices)


def _validate_imports(workspace: Path) -> list[CandidateValidationIssue]:
    issues: list[CandidateValidationIssue] = []
    for path in sorted(
        item
        for item in (workspace / "src").rglob("*")
        if item.suffix in {".ts", ".tsx"}
    ):
        relpath = str(path.relative_to(workspace)).replace("\\", "/")
        source = path.read_text(encoding="utf-8")
        for specifier in _IMPORT_RE.findall(source):
            if specifier.startswith((".", "@/")):
                if not _resolve_local_import(workspace, path, specifier):
                    issues.append(
                        _issue(
                            "unresolved_local_import",
                            f"Import {specifier!r} does not resolve.",
                            path=relpath,
                        )
                    )
                continue
            package = _package_root(specifier)
            if package not in APPROVED_RUNTIME_PACKAGES:
                issues.append(
                    _issue(
                        "unapproved_dependency",
                        f"Package import {specifier!r} is not approved.",
                        path=relpath,
                    )
                )
    return issues


def _typescript_no_emit(workspace: Path) -> list[CandidateValidationIssue]:
    node = shutil.which("node")
    script = Path(__file__).parent / "typescript" / "validate_candidate.mjs"
    typescript = (
        settings.PREVIEW_TEMPLATE_DIR
        / "node_modules"
        / "typescript"
        / "lib"
        / "typescript.js"
    )
    if not node or not typescript.is_file():
        return [
            _issue(
                "typescript_unavailable",
                "Checked-in TypeScript compiler runtime is unavailable.",
            )
        ]
    try:
        result = subprocess.run(
            [node, str(script), str(workspace), str(typescript)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        payload = json.loads(result.stdout or "{}")
    except Exception as exc:
        return [_issue("typescript_gate_error", str(exc)[:2000])]
    if payload.get("passed") is True and result.returncode == 0:
        return []
    return [
        _issue("typescript_no_emit", str(item)[:3500])
        for item in (payload.get("diagnostics") or [result.stderr or "tsc failed"])
    ][:50]


def validate_candidate_workspace(
    workspace: CandidateWorkspace,
    *,
    context: CandidateContext,
    expected_sources: tuple[CandidateSourceFile, ...],
    data_sources: tuple[CandidateSourceFile, ...],
    route_sources: tuple[CandidateSourceFile, ...],
) -> CandidateValidationReport:
    checks = (
        "dag_file_manifest",
        "typescript_parse_and_no_emit",
        "allowed_dependencies",
        "import_resolution",
        "required_exports",
        "exact_routes",
        "role_access",
        "canonical_interaction_hooks",
        "acceptance_test_markers",
        "content_data_hash",
        "generated_data_api_contract",
        "ia_mobile_bindings",
        "legacy_scaffold_absence",
        "business_component_usage",
    )
    issues: list[CandidateValidationIssue] = []
    expected_by_path = {item.path: item for item in expected_sources}
    actual_manifest = source_file_manifest(workspace.staging_path)
    actual_paths = {item["path"] for item in actual_manifest}
    expected_paths = set(expected_by_path)
    if actual_paths != expected_paths:
        issues.append(
            _issue(
                "file_manifest_mismatch",
                "Actual files do not exactly match the DAG-derived manifest.",
            )
        )
    for relpath, expected in expected_by_path.items():
        actual = read_source(workspace, relpath)
        if not actual:
            continue
        if expected.file_kind not in {"business_component", "page"} and (
            sha256_text(actual) != sha256_text(expected.source)
        ):
            issues.append(
                _issue(
                    "deterministic_file_changed",
                    "A deterministic file differs from its projection.",
                    path=relpath,
                )
            )
    issues.extend(_validate_imports(workspace.staging_path))
    issues.extend(
        _validate_generated_data_api(
            workspace,
            context=context,
            expected_sources=expected_sources,
        )
    )
    issues.extend(_typescript_no_emit(workspace.staging_path))

    generated_sources = "\n".join(
        read_source(workspace, item.path)
        for item in expected_sources
        if item.file_kind in {"business_component", "page"}
    )
    for marker in _PROHIBITED_MARKERS:
        if marker.casefold() in generated_sources.casefold():
            issues.append(
                _issue(
                    "legacy_scaffold",
                    f"Generated source contains {marker!r}.",
                )
            )
    for interaction in context.interactions.interactions:
        for attribute, canonical_id in (
            ("data-bmv-action-id", interaction.action_id),
            *(
                ("data-bmv-transition-id", item.transition_id)
                for item in interaction.transitions
            ),
        ):
            if attribute not in generated_sources or canonical_id not in generated_sources:
                issues.append(
                    _issue(
                        "canonical_interaction_omitted",
                        f"{attribute} omitted {canonical_id}.",
                        related_ids=(canonical_id,),
                    )
                )
        evidence_ids = {
            evidence_id
            for transition in interaction.transitions
            for evidence_id in transition.success_evidence_ids
        }
        for evidence_id in evidence_ids:
            if (
                "data-bmv-evidence-id" not in generated_sources
                or evidence_id not in generated_sources
            ):
                issues.append(
                    _issue(
                        "canonical_evidence_omitted",
                        "Generated source omitted visible success evidence.",
                        related_ids=(evidence_id,),
                    )
                )

    content_json = read_source(
        workspace,
        "src/generated/content-data.json",
    ).strip()
    expected_content_json = canonical_json(
        context.content_data.model_dump(mode="json")
    )
    if content_json != expected_content_json:
        issues.append(
            _issue(
                "content_data_mismatch",
                "Generated data does not exactly match ContentDataPlan.",
            )
        )
    route_manifest_source = read_source(
        workspace,
        "src/generated/route-manifest.ts",
    )
    expected_route_source = next(
        item.source
        for item in route_sources
        if item.path == "src/generated/route-manifest.ts"
    )
    if route_manifest_source != expected_route_source:
        issues.append(
            _issue(
                "route_manifest_mismatch",
                "Routes or role bindings differ from deterministic projection.",
            )
        )

    component_batch = GeneratedCandidateBatch(
        batch_kind="business_components",
        files=tuple(
            GeneratedCandidateFile(
                path=item.path,
                file_kind="business_component",
                owner_contract_ids=item.owner_contract_ids,
                source=read_source(workspace, item.path) or item.source,
            )
            for item in expected_sources
            if item.file_kind == "business_component"
        ),
    )
    page_batch = GeneratedCandidateBatch(
        batch_kind="pages",
        files=tuple(
            GeneratedCandidateFile(
                path=item.path,
                file_kind="page",
                owner_contract_ids=item.owner_contract_ids,
                source=read_source(workspace, item.path) or item.source,
            )
            for item in expected_sources
            if item.file_kind == "page"
        ),
    )
    if component_batch.files and page_batch.files:
        registry, registry_issues = build_business_component_registry(
            context=context,
            component_batch=component_batch,
        )
        issues.extend(registry_issues)
        if registry is not None:
            bindings, binding_issues = build_required_business_component_bindings(
                context=context,
                registry=registry,
            )
            issues.extend(binding_issues)
            if bindings and not binding_issues:
                _evidence, usage_issues = validate_business_component_usage(
                    batch=page_batch,
                    bindings=bindings,
                    component_paths={
                        item.component_module_path for item in bindings
                    },
                )
                issues.extend(usage_issues)

    return CandidateValidationReport(
        passed=not issues,
        checks=checks,
        issues=tuple(issues),
        file_manifest_sha256=canonical_sha256(actual_manifest),
        content_data_sha256=sha256_text(expected_content_json + "\n"),
        route_manifest_sha256=sha256_text(expected_route_source),
    )


__all__ = [
    "APPROVED_RUNTIME_PACKAGES",
    "batch_sources",
    "deterministic_repair_batch",
    "heal_invented_generated_data_imports",
    "heal_generated_data_record_shapes_in_batch",
    "heal_missing_transition_hooks",
    "validate_candidate_workspace",
    "validate_generated_batch",
]
