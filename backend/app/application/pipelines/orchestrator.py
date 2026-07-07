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

from app.application.pipelines import blueprint, proposal, reference_analysis, role_pages, technical_plan, visual_demo
from app.application.pipelines._shared import fallback_visual_demo, get_request
from app.application.preview_app import generate_preview_app
from app.application.services.progress import emit as _emit
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.infrastructure.ai_providers.factory import get_ai_provider
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

    def run(self, db: Session, request_id: int) -> dict:
        req = get_request(db, request_id)

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

        try:
            _emit(db, request_id, "demo", "Generating visual theme...", 24)
            visual_demo.generate_visual_demo(db, request_id, self.ai_provider, self.template_renderer)
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
            generate_preview_app(db, request_id, self.ai_provider, self.template_renderer)
        except Exception as e:
            # The pipeline already self-heals build failures internally (safe-stub
            # fallback). If it still raised, the failure was likely transient
            # (flaky AI call, workspace race) — retry the whole generation once
            # from a fresh workspace before falling back to the lesser role-pages mode.
            print(f"preview app generation failed ({e}) — retrying once...", flush=True)
            _emit(db, request_id, "codegen", "Retrying preview generation...", 28,
                  detail="First attempt hit an error — trying again")
            try:
                generate_preview_app(db, request_id, self.ai_provider, self.template_renderer)
            except Exception:
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
            _emit(db, request_id, "proposal", "Writing build proposal...", 95,
                  detail="Cost estimate, timeline, and next steps")
            proposal.generate_proposal(db, request_id, self.ai_provider, self.template_renderer)
        except Exception:
            pass

        _emit(db, request_id, "done", "Generation complete!", 100)

        req = get_request(db, request_id)
        return {
            "business_fit_score": req.business_fit_score,
            "concept_name": req.concept_name,
            "preview_summary": req.preview_summary,
            "preview_features": json.loads(req.preview_features) if req.preview_features else [],
            "visual_demo_generated": bool(req.visual_demo_json),
        }


def generate_full_pipeline(db: Session, request_id: int) -> dict:
    """Backward-compatible module function preserving the original call signature."""
    return GenerationPipeline().run(db, request_id)
