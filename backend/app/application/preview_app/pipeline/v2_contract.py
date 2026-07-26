"""Preview adapter for the Phase 3B immutable-candidate boundary."""
from sqlalchemy.orm import Session

from app.application.candidate_generation.service import (
    build_v2_candidate_revision,
)
from app.application.composition_contract.service import (
    build_v2_composition_contract,
)
from app.application.design_contract.service import build_v2_design_contract
from app.application.preview_contract.service import build_v2_app_spec_contract
from app.application.runtime_validation.service import (
    validate_v2_candidate_runtime,
)
from app.application.visual_evaluation.service import (
    evaluate_v2_candidate_visuals,
)
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models.request import Request


class Phase4StatusPreconditionError(ValueError):
    """Raised when orchestration would invoke Phase 4 on a non-pending candidate."""


def ensure_phase4_entry_status(phase3b_result: dict) -> None:
    """Fail closed before Phase 4 when the Phase 3B terminal status is wrong."""

    summary = dict(phase3b_result.get("preview_contract") or {})
    status = summary.get("status")
    if status != "candidate_build_pending":
        raise Phase4StatusPreconditionError(
            "phase4_status_precondition: Phase 4 requires "
            f"candidate_build_pending; got {status!r}"
        )


def run_v2_contract_boundary(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    *,
    req: Request,
    app_spec_revision_id: int | None,
) -> dict:
    phase1_result = build_v2_app_spec_contract(
        db,
        request_id,
        ai_provider,
        template_renderer,
        req=req,
        app_spec_revision_id=app_spec_revision_id,
    )
    phase2_result = build_v2_design_contract(
        db,
        request_id,
        ai_provider,
        template_renderer,
        req=req,
        phase1_result=phase1_result,
    )
    phase3a_result = build_v2_composition_contract(
        db,
        request_id,
        ai_provider,
        template_renderer,
        req=req,
        phase2_result=phase2_result,
    )
    phase3b_result = build_v2_candidate_revision(
        db,
        request_id,
        ai_provider,
        template_renderer,
        req=req,
        phase3a_result=phase3a_result,
    )
    if not settings.V2_RUNTIME_VALIDATION_ENABLED:
        return phase3b_result
    ensure_phase4_entry_status(phase3b_result)
    phase4_result = validate_v2_candidate_runtime(
        db,
        request_id,
        req=req,
        phase3b_result=phase3b_result,
    )
    if (
        not settings.V2_VISUAL_EVALUATION_ENABLED
        or (phase4_result.get("preview_contract") or {}).get("status")
        != "candidate_runtime_validated"
    ):
        return phase4_result
    phase5_result = evaluate_v2_candidate_visuals(
        db,
        request_id,
        ai_provider,
        template_renderer,
        req=req,
        phase4_result=phase4_result,
    )
    if (
        (phase5_result.get("preview_contract") or {}).get("status")
        != "candidate_visual_accepted"
    ):
        return phase5_result
    # Commercial gate: Tier 2/3 never auto-start after Tier 1 visual acceptance.
    # Tier 2 runs only via an approved Expanded Preview admin start action.
    # Tier 3 remains separately admin-controlled and is not invoked here.
    return phase5_result


__all__ = [
    "Phase4StatusPreconditionError",
    "ensure_phase4_entry_status",
    "run_v2_contract_boundary",
]
