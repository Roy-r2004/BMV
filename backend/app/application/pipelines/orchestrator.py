"""Top-level orchestrator for the full "new request -> finished preview" pipeline.

`GenerationPipeline` is constructed with an `AIProvider` and `TemplateRenderer`
(defaulting to the factory-selected singletons) and threads them through every
pipeline step. This is the DI seam for code that runs on a background thread
(outside FastAPI's request scope, so `Depends` doesn't apply).
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.application.pipelines import (
    blueprint,
    build_plans,
    proposal,
    reference_analysis,
    role_pages,
    technical_plan,
    visual_demo,
)
from app.application.pipelines._shared import fallback_visual_demo, get_request
from app.application.preview_app import generate_preview_app
from app.application.preview_app.pipeline.versioning import (
    GENERATOR_V2,
    select_preview_generator,
)
from app.application.appspec import (
    AppSpecGenerationError,
    app_spec_is_required,
    app_spec_mode,
    app_spec_should_run_for_request,
    ensure_approved_app_spec,
    select_preview_scope,
)
from app.application.services.progress import emit as _emit
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.infrastructure.ai_providers.factory import get_ai_provider
from app.infrastructure.logging import WatchBmv, get_logger
from app.infrastructure.logging.diagnostics import dump_exception, summarize_workspace_debug
from app.infrastructure.storage.file_service import is_image_file
from app.infrastructure.templating.renderer import get_template_renderer

class GenerationPipeline:
    """Orchestrates every generation step for one `Request` end-to-end."""

    def __init__(
        self,
        ai_provider: AIProvider | None = None,
        template_renderer: TemplateRenderer | None = None,
    ) -> None:
        self.ai_provider = ai_provider or get_ai_provider()
        self.template_renderer = template_renderer or get_template_renderer()
        self.log = get_logger(self.__class__)

    def run(self, db: Session, request_id: int) -> dict:
        from app.application.services.ai_context import ai_run_scope

        with ai_run_scope(request_id, purpose="pipeline"):
            return self._run_inner(db, request_id)

    def _run_inner(self, db: Session, request_id: int) -> dict:
        req = get_request(db, request_id)
        if getattr(req, "generation_cancel", False):
            req.generation_cancel = False
            db.commit()
        self.log.info("Starting full generation pipeline for request %s (%s)", request_id, req.business_name)
        pipeline_watch = WatchBmv(f"generation-pipeline request={request_id}", self.log).start()

        _emit(db, request_id, "analyze", "Reading your business...", 2,
              detail=f"Analyzing {req.business_name}")

        if req.reference_url and not req.reference_metadata:
            reference_analysis.fetch_and_save_reference_metadata(db, request_id)

        if req.reference_file_path and is_image_file(req.reference_file_path) and not req.screenshot_analysis:
            try:
                _emit(db, request_id, "analyze", "Analyzing your reference screenshot...", 5)
                reference_analysis.analyze_screenshot(db, request_id, self.ai_provider, self.template_renderer)
            except Exception:
                pass
        elif req.reference_url and not req.screenshot_analysis:
            try:
                _emit(db, request_id, "analyze", f"Studying reference: {req.reference_url}", 5)
                reference_analysis.generate_reference_analysis(db, request_id, self.ai_provider, self.template_renderer)
            except Exception:
                pass

        _emit(db, request_id, "blueprint", "Writing your MVP blueprint...", 10,
              detail="AI is mapping features, roles, and user journeys")
        blueprint.generate_mvp_blueprint(db, request_id, self.ai_provider, self.template_renderer)
        req = get_request(db, request_id)
        _emit(db, request_id, "blueprint",
              f"Blueprint complete — {req.concept_name or req.business_name}", 22,
              detail=f"Concept named: {req.concept_name or 'processing...'}")

        generator_selection = select_preview_generator(
            req,
            v2_enabled=settings.PREVIEW_GENERATOR_V2,
        )
        if generator_selection.version == GENERATOR_V2:
            _emit(
                db,
                request_id,
                "appspec",
                "Defining the v2 product contract...",
                23,
                detail=(
                    "Immutable source, inferred strategy, and independently "
                    "reviewed AppSpec"
                ),
            )
            contract = generate_preview_app(
                db,
                request_id,
                self.ai_provider,
                self.template_renderer,
            )
            _emit(
                db,
                request_id,
                "contract_ready",
                "V2 cumulative contract ready",
                100,
                detail=(
                    "Phase 1B stops before planning, codegen, workspace, or build"
                ),
            )
            pipeline_watch.stop()
            return contract

        approved_app_spec = None
        mode = app_spec_mode()
        require_app_spec = app_spec_is_required(
            is_new_request=not bool(req.generated_pages),
            mode=mode,
        )
        run_app_spec = app_spec_should_run_for_request(
            mode=mode,
            is_new_request=not bool(req.generated_pages),
        )
        if run_app_spec:
            _emit(
                db,
                request_id,
                "appspec",
                "Defining the product contract...",
                23,
                detail="Requirements → journeys → states → actions → proof",
            )
            try:
                approved_app_spec = ensure_approved_app_spec(
                    db,
                    request_id,
                    self.ai_provider,
                    self.template_renderer,
                )
                if require_app_spec:
                    # Scope overflow is a product decision, not permission to
                    # truncate a journey later in the UI pipeline.
                    select_preview_scope(
                        approved_app_spec.spec,
                        target_pages=settings.APPSPEC_PREVIEW_TARGET_PAGES,
                        max_pages=settings.APPSPEC_PREVIEW_MAX_PAGES,
                    )
                _emit(
                    db,
                    request_id,
                    "appspec",
                    f"Product contract accepted — revision {approved_app_spec.revision_record.revision}",
                    24,
                    detail=f"coverage={approved_app_spec.revision_record.coverage_score}; mode={mode}",
                )
            except Exception as exc:
                _emit(
                    db,
                    request_id,
                    "appspec_failed",
                    "Product contract could not be approved",
                    23,
                    detail=str(exc)[:300],
                )
                if require_app_spec:
                    req = get_request(db, request_id)
                    req.status = "failed"
                    db.commit()
                    if isinstance(exc, AppSpecGenerationError):
                        raise
                    raise AppSpecGenerationError(
                        f"AppSpec preview scope failed: {exc}"
                    ) from exc
                self.log.warning("AppSpec shadow pass failed: %s", exc)
                approved_app_spec = None

        try:
            _emit(db, request_id, "demo", "Generating visual theme...", 24)
            visual_demo.generate_visual_demo(
                db,
                request_id,
                self.ai_provider,
                self.template_renderer,
                app_spec=(
                    approved_app_spec.spec
                    if require_app_spec and approved_app_spec
                    else None
                ),
            )
            _emit(db, request_id, "demo", "Visual theme ready", 26)
        except Exception:
            demo = fallback_visual_demo(req)
            req = get_request(db, request_id)
            req.visual_demo_json = json.dumps(demo)
            req.visual_demo_generated_at = datetime.utcnow()
            db.commit()

        try:
            _emit(db, request_id, "codegen", "Launching UI generation pipeline...", 28,
                  detail="Planning agent designing pages and roles")
            generate_preview_app(
                db,
                request_id,
                self.ai_provider,
                self.template_renderer,
                app_spec_revision_id=(
                    approved_app_spec.revision_record.id
                    if approved_app_spec
                    else None
                ),
            )
        except Exception as e:
            # The pipeline already self-heals build failures internally (safe-stub
            # fallback). If it still raised, the failure was likely transient
            # (flaky AI call, workspace race) — retry the whole generation once
            # from a fresh workspace before falling back to the lesser role-pages mode.
            self.log.warning("preview app generation failed (%s) — retrying once...", e)
            try:
                from app.application.preview_app.workspace import get_workspace

                ws = get_workspace(request_id)
                if ws.exists():
                    dump_exception(ws, "pipeline", f"preview-gen-attempt-1-{request_id}", e)
            except Exception:
                pass
            _emit(db, request_id, "build", "Retrying preview generation...", 86,
                  detail="First attempt hit an error — trying again")
            try:
                generate_preview_app(
                    db,
                    request_id,
                    self.ai_provider,
                    self.template_renderer,
                    app_spec_revision_id=(
                        approved_app_spec.revision_record.id
                        if approved_app_spec
                        else None
                    ),
                )
            except Exception as retry_exc:
                try:
                    from app.application.preview_app.workspace import get_workspace

                    ws = get_workspace(request_id)
                    if ws.exists():
                        dump_exception(ws, "pipeline", f"preview-gen-attempt-2-{request_id}", retry_exc)
                        report = summarize_workspace_debug(ws)
                        for issue in report.get("top_issues", [])[:10]:
                            self.log.error("request %s debug: %s", request_id, issue)
                except Exception:
                    pass
                if require_app_spec:
                    # A required contract must never degrade into independently
                    # generated role-pages that are not traceable to it.
                    raise
                try:
                    role_pages.generate_role_pages(db, request_id, self.ai_provider, self.template_renderer)
                except Exception:
                    pass

        try:
            _emit(db, request_id, "tech", "Writing technical plan...", 90,
                  detail="Engineering roadmap and architecture")
            technical_plan.generate_technical_plan(db, request_id, self.ai_provider, self.template_renderer)
        except Exception:
            pass

        try:
            _emit(db, request_id, "proposal", "Writing build proposal...", 93,
                  detail="Internal proposal for the team")
            proposal.generate_proposal(db, request_id, self.ai_provider, self.template_renderer)
        except Exception:
            pass

        try:
            _emit(db, request_id, "build_plans", "Writing build packages...", 97,
                  detail="Launch / Growth / Custom from your preview")
            build_plans.generate_build_plans(db, request_id, self.ai_provider, self.template_renderer)
        except Exception:
            pass

        _emit(db, request_id, "done", "Generation complete!", 100)

        req = get_request(db, request_id)
        pipeline_watch.stop()
        self.log.info("Generation pipeline finished for request %s", request_id)
        from app.application.services.ai_features import ai_features_from_request

        return {
            "business_fit_score": req.business_fit_score,
            "concept_name": req.concept_name,
            "preview_summary": req.preview_summary,
            "preview_features": json.loads(req.preview_features) if req.preview_features else [],
            "ai_features": ai_features_from_request(req),
            "visual_demo_generated": bool(req.visual_demo_json),
        }

def generate_full_pipeline(db: Session, request_id: int) -> dict:
    """Backward-compatible module function preserving the original call signature."""
    return GenerationPipeline().run(db, request_id)
