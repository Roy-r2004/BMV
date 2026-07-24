"""Preview adapter for the Phase 3A composition-contract boundary."""
from sqlalchemy.orm import Session

from app.application.composition_contract.service import (
    build_v2_composition_contract,
)
from app.application.design_contract.service import build_v2_design_contract
from app.application.preview_contract.service import build_v2_app_spec_contract
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
    return build_v2_composition_contract(
        db,
        request_id,
        ai_provider,
        template_renderer,
        req=req,
        phase2_result=phase2_result,
    )


__all__ = ["run_v2_contract_boundary"]
