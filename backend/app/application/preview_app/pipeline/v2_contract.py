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
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models.request import Request


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
    return validate_v2_candidate_runtime(
        db,
        request_id,
        req=req,
        phase3b_result=phase3b_result,
    )


__all__ = ["run_v2_contract_boundary"]
