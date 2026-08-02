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
        from app.application.services.request_deadline import request_deadline_scope

        # The user's ten minutes starts when they submit, so the deadline is
        # armed here rather than inside `generate_preview_app`: reference intake
        # and the blueprint are p50 124 s of it, and a budget that excludes them
        # cannot close against a 600 s cap.
        from app.application.services.request_deadline import publish_degradations

        with ai_run_scope(request_id, purpose="pipeline"), request_deadline_scope(request_id):
            try:
                return self._run_inner(db, request_id)
            finally:
                # Published here, not in `finalize`. `finalize` runs inside
                # `generate_preview_app`, and `tech`/`proposal`/`build_plans`
                # are skipped *after* it returns — so the stored marker was
                # always missing exactly the degradations the deadline most
                # often causes. Requests 73, 75 and 76 each degraded three
                # stages and each stored `degraded: []`. The scope that armed
                # the clock is the only place the list is complete.
                publish_degradations(db, request_id)

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
                    # Overflow demotes ops/AI under the cap (public face first);
                    # select_preview_scope hard-fails only when no viable face fits.
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
            # A retry needs runway. Without this check the second attempt runs
            # on whatever time is left *and then some* — the cap would only ever
            # bound one attempt, so a failing run could spend 94 + 540 + 540.
            from app.application.services.request_deadline import (
                MIN_RETRY_RUNWAY_SECONDS,
                has_retry_runway,
                record_degradation,
                remaining_seconds,
            )

            if not has_retry_runway():
                record_degradation("codegen", "retry_skipped_no_runway")
                self.log.warning(
                    "request %s: skipping the generation retry — %.0fs left, need %.0fs",
                    request_id,
                    remaining_seconds(0.0) or 0.0,
                    MIN_RETRY_RUNWAY_SECONDS,
                )
                if require_app_spec:
                    # A required contract must never degrade into independently
                    # generated role-pages that are not traceable to it.
                    raise
                try:
                    role_pages.generate_role_pages(
                        db, request_id, self.ai_provider, self.template_renderer
                    )
                except Exception:
                    pass
            else:
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

        # The preview is the thing the user is waiting for. These three documents
        # are internal artifacts they never see on this screen, and they cost
        # 21-63 s of model time each — measured serially *before* `done`, so the
        # spinner ran for work the user had no stake in, and they ate the 60 s
        # the deadline reserves for the post-gate smoke pass.
        #
        # Marked complete first, then written. They are elective: past the
        # deadline they are skipped and recorded, never silently dropped.
        #
        # Deliberately still serial. `db` is a SQLAlchemy Session and is not
        # thread-safe; running these concurrently needs a session per worker,
        # which is a larger change than the saving justifies now that they are
        # off the path the user waits on.
        _emit(db, request_id, "done", "Generation complete!", 100)

        from app.application.services.request_deadline import should_skip_elective

        for stage, detail, generate_document in (
            ("tech", "Engineering roadmap and architecture",
             technical_plan.generate_technical_plan),
            ("proposal", "Internal proposal for the team",
             proposal.generate_proposal),
            ("build_plans", "Launch / Growth / Custom from your preview",
             build_plans.generate_build_plans),
        ):
            if should_skip_elective(stage):
                self.log.info(
                    "request %s: skipping %s — past deadline, preview already delivered",
                    request_id,
                    stage,
                )
                continue
            try:
                # Progress stays at 100: the preview is done. Regressing the bar
                # to 90 after announcing completion reads as a stalled run.
                _emit(db, request_id, "done", "Generation complete!", 100, detail=detail)
                generate_document(db, request_id, self.ai_provider, self.template_renderer)
            except Exception:
                pass

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
