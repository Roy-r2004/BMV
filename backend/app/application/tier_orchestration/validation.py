"""Tier 2 delta ownership and lower-tier regression gates."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from app.application.candidate_generation.deterministic import (
    page_export_symbol,
)
from app.domain.schemas.preview_candidate import GeneratedCandidateBatch
from app.domain.schemas.tier_orchestration import (
    Tier2PreservationManifest,
    Tier2Projection,
    Tier3PreservationManifest,
    Tier3Projection,
)


class Tier2GenerationContractError(ValueError):
    def __init__(self, message: str, *, diagnostics: tuple[str, ...] = ()):
        super().__init__(message)
        self.diagnostics = diagnostics


def validate_delta_batch(
    batch: GeneratedCandidateBatch,
    *,
    projection: Tier2Projection | Tier3Projection,
    new_component_ids: tuple[str, ...],
    allowed_ai_edit_paths: tuple[str, ...],
    existing_paths: tuple[str, ...],
) -> None:
    existing = set(existing_paths)
    allowed_edits = set(allowed_ai_edit_paths)
    diagnostics: list[str] = []
    if batch.batch_kind == "business_components":
        expected_ids = set(new_component_ids)
        prefix = "src/components/business/"
    else:
        expected_ids = set(
            (
                *projection.delta.page_ids,
                *projection.lower_tier_integration_page_ids,
            )
        )
        prefix = "src/pages/"
    counts: Counter[str] = Counter()
    for item in batch.files:
        if not item.path.startswith(prefix):
            diagnostics.append(f"wrong_namespace:{item.path}")
        if item.path in existing and item.path not in allowed_edits:
            diagnostics.append(f"immutable_edit:{item.path}")
        owners = set(item.owner_contract_ids)
        unexpected = owners - expected_ids
        if unexpected:
            diagnostics.append(
                f"out_of_delta_owner:{item.path}:{sorted(unexpected)}"
            )
        for owner in owners & expected_ids:
            counts[owner] += 1
        lowered = item.source.casefold()
        if any(
            marker in lowered
            for marker in (
                "@/ui",
                "skeleton_id",
                "catalogue slot",
                "fixed dashboard",
                "fixed hero",
            )
        ):
            diagnostics.append(f"prohibited_scaffold:{item.path}")
        if batch.batch_kind == "pages":
            page_owners = owners & expected_ids
            if len(page_owners) != 1:
                diagnostics.append(f"page_owner_cardinality:{item.path}")
            elif page_export_symbol(next(iter(page_owners))) not in item.source:
                diagnostics.append(f"missing_page_export:{item.path}")
    for expected_id in expected_ids:
        if counts[expected_id] != 1:
            diagnostics.append(
                f"owner_file_cardinality:{expected_id}:{counts[expected_id]}"
            )
    if diagnostics:
        raise Tier2GenerationContractError(
            "Tier 2 AI batch escaped its deterministic delta contract",
            diagnostics=tuple(diagnostics),
        )


def verify_preservation_after_generation(
    *,
    initial: Tier2PreservationManifest | Tier3PreservationManifest,
    final: Tier2PreservationManifest | Tier3PreservationManifest,
) -> None:
    before = {item.path: item for item in initial.entries}
    after = {item.path: item for item in final.entries}
    if set(before) != set(after):
        raise Tier2GenerationContractError(
            "Preservation audit changed accepted path membership"
        )
    diagnostics = []
    for path, original in before.items():
        current = after[path]
        if (
            original.classification == "immutable"
            and current.final_sha256 != original.original_sha256
        ):
            diagnostics.append(f"immutable_changed:{path}")
        if (
            current.final_sha256 != original.original_sha256
            and original.edit_authority == "none"
        ):
            diagnostics.append(f"unjustified_edit:{path}")
    if diagnostics:
        raise Tier2GenerationContractError(
            "Tier 1 byte preservation failed",
            diagnostics=tuple(diagnostics),
        )


def assert_accepted_workspace_unchanged(
    accepted_workspace: Path,
    *,
    expected_manifest_sha256: str,
) -> None:
    from app.application.candidate_generation.cache import canonical_sha256
    from app.application.candidate_generation.workspace import (
        source_file_manifest,
    )

    if canonical_sha256(
        source_file_manifest(accepted_workspace)
    ) != expected_manifest_sha256:
        raise Tier2GenerationContractError(
            "Accepted Tier 1 workspace was modified"
        )


__all__ = [
    "Tier2GenerationContractError",
    "assert_accepted_workspace_unchanged",
    "validate_delta_batch",
    "verify_preservation_after_generation",
]
