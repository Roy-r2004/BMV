"""Classify and verify accepted Tier 1 files before Tier 2 extension."""
from __future__ import annotations

import json
from pathlib import Path

from app.application.candidate_generation.cache import (
    canonical_sha256,
    sha256_bytes,
)
from app.application.candidate_generation.context import CandidateContext
from app.application.candidate_generation.workspace import source_file_manifest
from app.domain.models import CandidateArtifactRecord, CandidateRevisionRecord
from app.domain.schemas.preview_candidate import CandidateArtifactManifest
from app.domain.schemas.preview_candidate import GeneratedCandidateBatch
from app.domain.schemas.tier_orchestration import (
    Tier2FilePreservationEntry,
    Tier2PreservationManifest,
    Tier2Projection,
    Tier3PreservationManifest,
    Tier3Projection,
)


_DETERMINISTIC_EXTENSIONS = {
    "src/App.tsx",
    "src/generated/content-data.json",
    "src/generated/content-data.ts",
    "src/generated/navigation.ts",
    "src/generated/route-manifest.ts",
}


def _artifact_owner_map(
    rows: tuple[CandidateArtifactRecord, ...],
) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for row in rows:
        try:
            artifact = CandidateArtifactManifest.model_validate(
                json.loads(row.artifact_json)
            )
        except Exception:
            try:
                artifact = GeneratedCandidateBatch.model_validate(
                    json.loads(row.artifact_json)
                )
            except Exception:
                continue
        for item in artifact.files:
            previous = result.get(item.path, ())
            result[item.path] = tuple(
                dict.fromkeys((*previous, *item.owner_contract_ids))
            )
    return result


def classify_tier_1_files(
    *,
    accepted: CandidateRevisionRecord,
    accepted_workspace: Path,
    artifact_rows: tuple[CandidateArtifactRecord, ...],
    inherited_context: CandidateContext,
    projection: Tier2Projection,
    extension_contract_sha256: str,
) -> Tier2PreservationManifest:
    if accepted.target_tier != 1 or not accepted.file_manifest_sha256:
        raise ValueError("Preservation requires a frozen Tier 1 revision")
    actual = source_file_manifest(accepted_workspace)
    if canonical_sha256(actual) != accepted.file_manifest_sha256:
        raise ValueError("Accepted Tier 1 workspace changed before extension")
    owner_map = _artifact_owner_map(artifact_rows)
    integration_pages = set(projection.lower_tier_integration_page_ids)
    compositions = {
        item.page_id: set(item.ordered_component_ids)
        for item in inherited_context.business_components.page_compositions
    }
    integration_components = set().union(
        *(compositions.get(page_id, set()) for page_id in integration_pages)
    ) if integration_pages else set()
    entries: list[Tier2FilePreservationEntry] = []
    for item in actual:
        path = item["path"]
        owners = owner_map.get(path, ())
        classification = "immutable"
        authority = "none"
        justification = (
            "Accepted Tier 1 file is outside the deterministic Tier 2 "
            "dependency closure."
        )
        if path in _DETERMINISTIC_EXTENSIONS:
            classification = "extendable"
            authority = "deterministic"
            justification = (
                "Cumulative Tier 2 data, route, navigation, or application "
                "wiring is projected deterministically."
            )
        elif path.startswith("src/pages/") and integration_pages.intersection(
            owners
        ):
            classification = "extendable"
            authority = "ai"
            justification = (
                "The page is an explicit lower-tier integration point in "
                "the canonical Tier 2 dependency closure."
            )
        elif (
            path.startswith("src/components/business/")
            and integration_components.intersection(owners)
        ):
            classification = "extendable"
            authority = "ai"
            justification = (
                "The business component belongs to an explicit lower-tier "
                "integration page in the canonical Tier 2 closure."
            )
        entries.append(
            Tier2FilePreservationEntry(
                path=path,
                classification=classification,
                original_sha256=item["sha256"],
                owner_ids=owners,
                dependency_path=(
                    tuple(projection.lower_tier_integration_page_ids)
                    if classification == "extendable"
                    else ()
                ),
                justification=justification,
                edit_authority=authority,
            )
        )
    digest_payload = {
        "accepted_tier_1_revision_id": accepted.id,
        "accepted_manifest_sha256": accepted.file_manifest_sha256,
        "extension_contract_sha256": extension_contract_sha256,
        "entries": [item.model_dump(mode="json") for item in entries],
    }
    return Tier2PreservationManifest(
        **digest_payload,
        manifest_sha256=canonical_sha256(digest_payload),
    )


def classify_tier_2_files(
    *,
    accepted: CandidateRevisionRecord,
    accepted_workspace: Path,
    artifact_rows: tuple[CandidateArtifactRecord, ...],
    inherited_context: CandidateContext,
    projection: Tier3Projection,
    extension_contract_sha256: str,
) -> Tier3PreservationManifest:
    if accepted.target_tier != 2 or not accepted.file_manifest_sha256:
        raise ValueError("Preservation requires a frozen Tier 2 revision")
    if accepted.id != projection.accepted_tier_2_revision_id:
        raise ValueError("Tier 3 projection references a different Tier 2")
    actual = source_file_manifest(accepted_workspace)
    if canonical_sha256(actual) != accepted.file_manifest_sha256:
        raise ValueError("Accepted Tier 2 workspace changed before extension")
    owner_map = _artifact_owner_map(artifact_rows)
    integration_pages = set(projection.lower_tier_integration_page_ids)
    compositions = {
        item.page_id: set(item.ordered_component_ids)
        for item in inherited_context.business_components.page_compositions
    }
    integration_components = (
        set().union(
            *(
                compositions.get(page_id, set())
                for page_id in integration_pages
            )
        )
        if integration_pages
        else set()
    )
    entries: list[Tier2FilePreservationEntry] = []
    for item in actual:
        path = item["path"]
        owners = owner_map.get(path, ())
        classification = "immutable"
        authority = "none"
        justification = (
            "Accepted Tier 2 file is outside the deterministic Tier 3 "
            "dependency closure."
        )
        if path in _DETERMINISTIC_EXTENSIONS:
            classification = "extendable"
            authority = "deterministic"
            justification = (
                "Cumulative Tier 3 data, route, navigation, or application "
                "wiring is projected deterministically."
            )
        elif path.startswith("src/pages/") and integration_pages.intersection(
            owners
        ):
            classification = "extendable"
            authority = "ai"
            justification = (
                "The page is an explicit accepted-Tier-2 integration point "
                "in the canonical Tier 3 closure."
            )
        elif (
            path.startswith("src/components/business/")
            and integration_components.intersection(owners)
        ):
            classification = "extendable"
            authority = "ai"
            justification = (
                "The business component belongs to an explicit lower-tier "
                "integration page in the canonical Tier 3 closure."
            )
        entries.append(
            Tier2FilePreservationEntry(
                path=path,
                classification=classification,
                original_sha256=item["sha256"],
                owner_ids=owners,
                dependency_path=(
                    tuple(projection.lower_tier_integration_page_ids)
                    if classification == "extendable"
                    else ()
                ),
                justification=justification,
                edit_authority=authority,
            )
        )
    payload = {
        "accepted_tier_1_revision_id": (
            projection.accepted_tier_1_revision_id
        ),
        "accepted_tier_2_revision_id": accepted.id,
        "accepted_manifest_sha256": accepted.file_manifest_sha256,
        "accepted_tier_2_effective_summary_sha256": (
            projection.accepted_tier_2_effective_summary_sha256
        ),
        "extension_contract_sha256": extension_contract_sha256,
        "entries": [item.model_dump(mode="json") for item in entries],
    }
    return Tier3PreservationManifest(
        **payload,
        manifest_sha256=canonical_sha256(payload),
    )


def finalize_preservation_audit(
    manifest: Tier2PreservationManifest | Tier3PreservationManifest,
    *,
    final_workspace: Path,
) -> Tier2PreservationManifest | Tier3PreservationManifest:
    actual = {
        item["path"]: item
        for item in source_file_manifest(final_workspace)
    }
    entries: list[Tier2FilePreservationEntry] = []
    for entry in manifest.entries:
        final = actual.get(entry.path)
        if final is None:
            raise ValueError(
                f"Accepted lower-tier file was removed: {entry.path}"
            )
        final_sha = final["sha256"]
        if (
            entry.classification == "immutable"
            and final_sha != entry.original_sha256
        ):
            raise ValueError(
                f"Immutable lower-tier file changed: {entry.path}"
            )
        entries.append(entry.model_copy(update={"final_sha256": final_sha}))
    # New files must be confined to the two generated source namespaces.
    original_paths = {item.path for item in manifest.entries}
    for path in set(actual) - original_paths:
        if not (
            path.startswith("src/pages/")
            or path.startswith("src/components/business/")
        ):
            raise ValueError(
                f"Tier orchestration added an unauthorized path: {path}"
            )
    payload = {
        "accepted_tier_1_revision_id": (
            manifest.accepted_tier_1_revision_id
        ),
        "accepted_manifest_sha256": manifest.accepted_manifest_sha256,
        "extension_contract_sha256": manifest.extension_contract_sha256,
        "entries": [item.model_dump(mode="json") for item in entries],
    }
    if isinstance(manifest, Tier3PreservationManifest):
        payload.update(
            {
                "accepted_tier_2_revision_id": (
                    manifest.accepted_tier_2_revision_id
                ),
                "accepted_tier_2_effective_summary_sha256": (
                    manifest.accepted_tier_2_effective_summary_sha256
                ),
            }
        )
        return Tier3PreservationManifest(
            **payload,
            manifest_sha256=canonical_sha256(payload),
        )
    return Tier2PreservationManifest(
        **payload,
        manifest_sha256=canonical_sha256(payload),
    )


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


__all__ = [
    "classify_tier_1_files",
    "classify_tier_2_files",
    "file_sha256",
    "finalize_preservation_audit",
]
