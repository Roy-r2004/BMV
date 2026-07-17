"""AppSpec application services — generation, projection, persistence.

Pure contract rules live in ``app.domain.appspec`` (validation, sanitize).
"""

from app.application.appspec.generation import (
    AppSpecCallBudgetExceeded,
    AppSpecGenerationError,
    AppSpecGenerationResult,
    app_spec_is_required,
    app_spec_mode,
    app_spec_should_run,
    app_spec_should_run_for_request,
    ensure_approved_app_spec,
)
from app.application.appspec.projection import (
    PreviewScope,
    PreviewScopeError,
    brand_projection,
    merge_architecture_enrichment,
    merge_experience_plan_enrichment,
    select_preview_scope,
    to_architecture_seed,
    to_experience_plan_seed,
)
from app.application.appspec.repository import AppSpecRepository, app_spec_provenance
from app.application.appspec.workspace_validation import validate_app_spec_workspace
from app.domain.appspec import (
    ValidationReport,
    sanitize_app_spec_payload,
    validate_app_spec,
)

__all__ = [
    "AppSpecCallBudgetExceeded",
    "AppSpecGenerationError",
    "AppSpecGenerationResult",
    "AppSpecRepository",
    "PreviewScope",
    "PreviewScopeError",
    "app_spec_is_required",
    "app_spec_mode",
    "app_spec_provenance",
    "app_spec_should_run",
    "app_spec_should_run_for_request",
    "brand_projection",
    "ensure_approved_app_spec",
    "merge_architecture_enrichment",
    "merge_experience_plan_enrichment",
    "select_preview_scope",
    "to_architecture_seed",
    "to_experience_plan_seed",
    "validate_app_spec",
    "validate_app_spec_workspace",
    "ValidationReport",
    "sanitize_app_spec_payload",
]
