"""AppSpec application services — generation, projection, persistence.

Pure contract rules live in ``app.domain.appspec`` (validation, sanitize).
"""

from app.application.appspec.hooks import (
    ensure_workspace_appspec_hooks,
    inject_appspec_contract_hooks,
    attr_bound,
    page_hooks_present,
)
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
from app.application.appspec.policy import (
    AppSpecGenerationPolicy,
    ModelFamilyPolicyError,
    model_family,
    v2_app_spec_policy,
)
from app.application.appspec.repository import (
    AppSpecRepository,
    app_spec_provenance,
    app_spec_revision_is_complete,
)
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
    "AppSpecGenerationPolicy",
    "AppSpecRepository",
    "ModelFamilyPolicyError",
    "PreviewScope",
    "PreviewScopeError",
    "app_spec_is_required",
    "app_spec_mode",
    "app_spec_provenance",
    "app_spec_revision_is_complete",
    "app_spec_should_run",
    "app_spec_should_run_for_request",
    "attr_bound",
    "brand_projection",
    "ensure_approved_app_spec",
    "ensure_workspace_appspec_hooks",
    "inject_appspec_contract_hooks",
    "merge_architecture_enrichment",
    "merge_experience_plan_enrichment",
    "model_family",
    "page_hooks_present",
    "select_preview_scope",
    "to_architecture_seed",
    "to_experience_plan_seed",
    "validate_app_spec",
    "validate_app_spec_workspace",
    "v2_app_spec_policy",
    "ValidationReport",
    "sanitize_app_spec_payload",
]
