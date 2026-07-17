"""Preview pipeline — Orchestrator.

Thin wiring layer: builds the shared `PipelineContext` and runs each phase
in order. See the individual phase modules for behavior:
  appspec_gate  -> plan_phase -> codegen_phase -> polish_phase -> build_phase -> finalize
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.application.preview_app.ai_budget import request_mutation_boundary
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
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise ValueError(f"Request {request_id} not found")
    if not req.mvp_blueprint:
        raise ValueError("MVP blueprint must be generated first.")

    log.info("Starting preview pipeline for request %s", request_id)
    pipeline_watch = WatchBmv(f"preview request={request_id}", log).start()

    # #region agent log
    from app.application.preview_app.pipeline.debug_ndjson import agent_dbg

    agent_dbg(
        "E",
        "orchestrator.py:start",
        "pipeline start",
        {
            "request_id": request_id,
            "industry": getattr(req, "industry", None),
            "business_name": getattr(req, "business_name", None),
            "has_blueprint": bool(req.mvp_blueprint),
        },
    )
    # #endregion

    ctx = PipelineContext(
        db=db,
        request_id=request_id,
        ai_provider=ai_provider,
        template_renderer=template_renderer,
        app_spec_revision_id=app_spec_revision_id,
        req=req,
        pipeline_watch=pipeline_watch,
    )

    try:
        run_appspec_gate(ctx)
        run_plan_phase(ctx)
        run_codegen_phase(ctx)
        run_polish_phase(ctx)
        run_build_phase(ctx)
        result = run_finalize(ctx)
        # #region agent log
        agent_dbg(
            "E",
            "orchestrator.py:success",
            "pipeline finished",
            {
                "request_id": request_id,
                "preview_url": (result or {}).get("preview_url")
                or (result or {}).get("url"),
                "keys": sorted((result or {}).keys())[:20],
            },
        )
        # #endregion
        return result
    except Exception as exc:
        # #region agent log
        agent_dbg(
            "E",
            "orchestrator.py:error",
            "pipeline exception",
            {
                "request_id": request_id,
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
            },
        )
        # #endregion
        raise


__all__ = ["generate_preview_app", "PreviewAppContractError"]
