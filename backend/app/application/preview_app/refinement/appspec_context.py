"""Canonical AppSpec contract resolution and deterministic projections for a refinement."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.application.appspec import app_spec_mode
from app.application.appspec.projection import (
    PreviewScope,
    browser_projection,
    merge_architecture_enrichment,
    merge_experience_plan_enrichment,
    page_contract,
    runtime_projection,
    select_preview_scope,
    to_architecture_seed,
    to_experience_plan_seed,
)
from app.application.appspec.repository import (
    AppSpecRepository,
    load_json_object,
)
from app.application.preview_app.refinement.workspace_patch import _architect_from_generated
from app.core.config import settings
from app.domain.models.app_spec import APP_SPEC_STATUS_ACCEPTED, AppSpecRevision
from app.domain.schemas.app_spec import AppSpec


@dataclass(frozen=True)
class AppSpecRefinementContext:
    """Canonical contract and deterministic projections for one refinement."""

    revision: AppSpecRevision
    spec: AppSpec
    scope: PreviewScope
    plan_seed: dict[str, Any]
    plan: dict[str, Any]
    architecture_seed: dict[str, Any]
    architect: dict[str, Any]
    selected_contracts: dict[str, Any]


def _app_spec_ref_is_enforced(generated_pages: Mapping[str, Any]) -> bool:
    """When AppSpec is on, persisted provenance becomes a hard gate."""

    return bool(generated_pages.get("app_spec_ref")) and app_spec_mode() == "on"


def _load_app_spec_refinement_context(
    db: Session,
    request_id: int,
    generated_pages: Mapping[str, Any],
    *,
    experience_plan: Mapping[str, Any] | None = None,
    architect: Mapping[str, Any] | None = None,
) -> AppSpecRefinementContext | None:
    """Resolve an exact accepted same-request AppSpec and rebuild its seeds.

    The provenance reference is treated as a capability: every persisted value
    (row id, revision, schema and digest) must match before refinement can touch
    the workspace. This prevents a stale or cross-request contract from being
    used merely because its JSON happens to parse.
    """

    if not _app_spec_ref_is_enforced(generated_pages):
        return None
    ref = generated_pages.get("app_spec_ref")
    if not isinstance(ref, Mapping):
        raise ValueError("Required AppSpec provenance is malformed.")
    try:
        revision_number = int(ref["revision"])
        revision_id = int(ref["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Required AppSpec provenance is incomplete.") from exc

    row = AppSpecRepository(db).get_revision(request_id, revision_number)
    if (
        row is None
        or row.id != revision_id
        or row.request_id != request_id
        or row.status != APP_SPEC_STATUS_ACCEPTED
        or not row.validation_passed
        or not row.coverage_passed
    ):
        raise ValueError(
            "The preview's AppSpec reference is not an accepted revision for this request."
        )
    if ref.get("schema_version") and ref.get("schema_version") != row.schema_version:
        raise ValueError("The preview's AppSpec schema reference is stale.")
    if ref.get("sha256") and ref.get("sha256") != row.app_spec_sha256:
        raise ValueError("The preview's AppSpec digest does not match its accepted revision.")

    spec = AppSpec.model_validate(load_json_object(row.app_spec_json))
    scope = select_preview_scope(
        spec,
        target_pages=settings.APPSPEC_PREVIEW_TARGET_PAGES,
        max_pages=settings.APPSPEC_PREVIEW_MAX_PAGES,
    )
    plan_seed = to_experience_plan_seed(spec, scope)
    enriched_plan = merge_experience_plan_enrichment(
        plan_seed,
        experience_plan or generated_pages.get("experience_plan") or {},
    )
    architecture_seed = to_architecture_seed(spec, scope)
    stored_architect = architect or _architect_from_generated(
        dict(generated_pages), enriched_plan
    )
    enriched_architect = merge_architecture_enrichment(
        architecture_seed,
        stored_architect,
    )
    selected_contracts = {
        "scope": scope.as_dict(),
        "pages": {
            page_id: page_contract(spec, page_id)
            for page_id in scope.selected_page_ids
        },
        "runtime": runtime_projection(spec, scope),
        "browser": browser_projection(spec, scope),
    }
    return AppSpecRefinementContext(
        revision=row,
        spec=spec,
        scope=scope,
        plan_seed=plan_seed,
        plan=enriched_plan,
        architecture_seed=architecture_seed,
        architect=enriched_architect,
        selected_contracts=selected_contracts,
    )


def _merge_app_spec_refinement_enrichment(
    context: AppSpecRefinementContext,
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Discard semantic AI drift and retain only allow-listed design choices."""

    plan = merge_experience_plan_enrichment(
        context.plan_seed,
        payload.get("experience_plan") or context.plan,
    )
    architect = merge_architecture_enrichment(
        context.architecture_seed,
        payload.get("architect") or context.architect,
    )
    return plan, architect
