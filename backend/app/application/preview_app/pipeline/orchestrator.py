"""Preview pipeline — Orchestrator.

Thin wiring layer: builds the shared `PipelineContext` and runs each phase
in order. See the individual phase modules for behavior:
  appspec_gate  -> plan_phase -> codegen_phase -> polish_phase -> build_phase -> finalize
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.application.preview_app.ai_budget import request_mutation_boundary
from app.application.services.ai_context import ai_run_scope
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models.request import Request
from app.application.preview_app.pipeline.appspec_gate import run_appspec_gate
from app.application.preview_app.pipeline.build_phase import run_build_phase
from app.application.preview_app.pipeline.codegen_phase import run_codegen_phase
from app.application.preview_app.pipeline.context import PipelineContext
from app.application.preview_app.pipeline.errors import PreviewAppContractError
from app.application.preview_app.pipeline.finalize import run_finalize
from app.application.preview_app.pipeline.plan_phase import run_plan_phase
from app.application.preview_app.pipeline.polish_phase import run_polish_phase
from app.application.preview_app.pipeline.versioning import (
    GENERATOR_V1,
    dispatch_preview_generator,
    select_preview_generator,
)
from app.application.preview_app.pipeline.v2_contract import (
    run_v2_contract_boundary,
)
from app.core.config import settings
from app.infrastructure.logging import WatchBmv, get_logger

log = get_logger("PreviewPipeline")


@request_mutation_boundary
def generate_preview_app(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    app_spec_revision_id: int | None = None,
) -> dict:
    with ai_run_scope(request_id, purpose="codegen"):
        return _generate_preview_app_inner(
            db,
            request_id,
            ai_provider,
            template_renderer,
            app_spec_revision_id=app_spec_revision_id,
        )


def _generate_preview_app_inner(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    app_spec_revision_id: int | None = None,
) -> dict:
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise ValueError(f"Request {request_id} not found")
    if not req.mvp_blueprint:
        raise ValueError("MVP blueprint must be generated first.")

    selection = select_preview_generator(
        req,
        v2_enabled=settings.PREVIEW_GENERATOR_V2,
    )
    return dispatch_preview_generator(
        selection,
        run_v1=lambda: _run_v1_pipeline(
            db,
            request_id,
            ai_provider,
            template_renderer,
            app_spec_revision_id=app_spec_revision_id,
            req=req,
            generator_version=GENERATOR_V1,
        ),
        run_v2=lambda: _run_v2_boundary(
            db,
            request_id,
            ai_provider,
            template_renderer,
            app_spec_revision_id=app_spec_revision_id,
            req=req,
        ),
    )


def _run_v2_boundary(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    *,
    app_spec_revision_id: int | None,
    req: Request,
) -> dict:
    """Phase 3A v2 entrypoint: persist composition contracts and stop."""

    log.info(
        "Preview generator v2 selected for request %s; building contract only",
        request_id,
    )
    return run_v2_contract_boundary(
        db,
        request_id,
        ai_provider,
        template_renderer,
        app_spec_revision_id=app_spec_revision_id,
        req=req,
    )


def _run_v1_pipeline(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    *,
    app_spec_revision_id: int | None,
    req: Request,
    generator_version: str,
) -> dict:
    """Run the frozen v1 phase sequence.

    The v2 contract boundary never calls this function. Keeping this sequence
    isolated protects legacy preview generation from v2 contract changes.
    """

    log.info("Starting preview pipeline for request %s", request_id)
    pipeline_watch = WatchBmv(f"preview request={request_id}", log).start()

    ctx = PipelineContext(
        db=db,
        request_id=request_id,
        ai_provider=ai_provider,
        template_renderer=template_renderer,
        app_spec_revision_id=app_spec_revision_id,
        req=req,
        generator_version=generator_version,
        pipeline_watch=pipeline_watch,
    )

    try:
        run_appspec_gate(ctx)
        run_plan_phase(ctx)
        run_codegen_phase(ctx)
        run_polish_phase(ctx)
        run_build_phase(ctx)
        result = run_finalize(ctx)
        return result
    except Exception:
        raise


__all__ = ["generate_preview_app", "PreviewAppContractError"]
