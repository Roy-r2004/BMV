"""Preview pipeline — AppSpec resolve/enforce gate + brand brief/images prep."""
from __future__ import annotations

import json

from app.application.appspec import (
    AppSpecGenerationError,
    app_spec_is_required,
    app_spec_mode,
    app_spec_should_run_for_request,
    ensure_approved_app_spec,
)
from app.application.appspec.projection import PreviewScopeError, select_preview_scope
from app.application.services.industry_images import get_images_for_industry
from app.application.services.progress import emit as _emit
from app.core.config import settings
from app.infrastructure.logging import get_logger
from app.infrastructure.logging.diagnostics import dump_appspec_failure
from app.application.preview_app.pipeline.context import PipelineContext

log = get_logger("PreviewPipeline")


def resolve_industry(ctx: PipelineContext) -> str:
    """The industry every later stage reads — declared, derived, or loudly absent.

    `industry` is an optional form field (`requests.py:202` is
    `industry: str = Form(None)`), and requests 66, 67 and 68 arrived without it.
    Each one resolved to `generic` in silence and shipped camera-lens packaging, a
    sales-volume chart and an audio-editing timeline to a fine-art gallery whose
    own `business_description` opens *"An independent fine-art gallery … original
    oil paintings"*. Request 70 is the same description with the field set: it
    logged `imagery subject=art` and shipped paintings.

    So this runs before the first `req.industry` read in the pipeline, and every
    later stage takes `ctx.industry` rather than the raw column. Two rules:

    * a blank field is **derived** from the description, deterministically, with
      no model call — the derivation is on the critical path;
    * a blank field that still resolves to `generic` **warns with the request id
      and emits a progress event**, because that combination is the exact shape of
      the four runs above and it must never again be something only a reader who
      already knew to look could find.
    """
    from app.application.services.industry_images import (
        industry_or_derived,
        resolve_industry_category,
    )

    declared = (ctx.req.industry or "").strip()
    if declared:
        return declared

    derived = industry_or_derived(declared, getattr(ctx.req, "business_description", None))
    if derived:
        log.info(
            "    industry: form field empty on request %s — derived %r "
            "(subject=%s) from the business description",
            ctx.request_id,
            derived,
            resolve_industry_category(derived),
        )
        _emit(
            ctx.db,
            ctx.request_id,
            "analyze",
            "Industry read from the business description",
            26,
            detail=(
                f"industry field was empty; derived={derived!r}; "
                f"imagery subject={resolve_industry_category(derived)}"
            ),
        )
        return derived

    log.warning(
        "    industry: request %s has no industry field and none could be derived "
        "from its business description — imagery and packs fall back to generic",
        ctx.request_id,
    )
    _emit(
        ctx.db,
        ctx.request_id,
        "analyze",
        "No industry — imagery falls back to generic",
        26,
        detail=(
            "industry field empty and the business description names no trade "
            "this pipeline recognises; imagery subject=generic"
        ),
    )
    return ""


def run_appspec_gate(ctx: PipelineContext) -> None:
    db = ctx.db
    request_id = ctx.request_id
    req = ctx.req

    ctx.industry = resolve_industry(ctx)

    mode = app_spec_mode()
    prior_bundle: dict = {}
    if req.generated_pages:
        try:
            prior_bundle = json.loads(req.generated_pages)
        except Exception:
            prior_bundle = {}
    prior_app_spec_ref = prior_bundle.get("app_spec_ref") or {}
    is_new_request = not bool(req.generated_pages) or bool(
        prior_app_spec_ref.get("enforced")
    )
    enforce_app_spec = app_spec_is_required(
        is_new_request=is_new_request,
        mode=mode,
    )
    app_spec_result = None
    app_spec_scope = None
    run_app_spec = app_spec_should_run_for_request(
        mode=mode,
        is_new_request=is_new_request,
    )
    if run_app_spec:
        _emit(
            db,
            request_id,
            "appspec",
            "Confirming the product contract...",
            27,
            detail="Validating requirements, journeys, states, actions, and evidence",
        )
        try:
            app_spec_result = ensure_approved_app_spec(
                db,
                request_id,
                ctx.ai_provider,
                ctx.template_renderer,
            )
            if (
                ctx.app_spec_revision_id is not None
                and app_spec_result.revision_record.id != ctx.app_spec_revision_id
                and enforce_app_spec
            ):
                raise AppSpecGenerationError(
                    "The approved AppSpec changed before preview generation; retry with the current revision."
                )
            if enforce_app_spec:
                app_spec_scope = select_preview_scope(
                    app_spec_result.spec,
                    target_pages=settings.APPSPEC_PREVIEW_TARGET_PAGES,
                    max_pages=settings.APPSPEC_PREVIEW_MAX_PAGES,
                )
            _emit(
                db,
                request_id,
                "appspec",
                f"Product contract accepted — revision {app_spec_result.revision_record.revision}",
                29,
                detail=(
                    f"coverage={app_spec_result.revision_record.coverage_score}; "
                    f"mode={mode}; reused={app_spec_result.reused}"
                ),
            )
        except (AppSpecGenerationError, PreviewScopeError) as exc:
            _emit(
                db,
                request_id,
                "appspec_failed",
                "Product contract needs attention before UI generation",
                27,
                detail=str(exc)[:300],
            )
            log.error("AppSpec failed for request %s: %s", request_id, exc)
            try:
                from app.application.preview_app.workspace import get_workspace

                ws = get_workspace(request_id)
                if ws.exists():
                    dump_appspec_failure(ws, request_id=request_id, exc=exc, phase="preview-pipeline")
            except Exception as dump_exc:
                log.warning("could not dump AppSpec failure artifact: %s", dump_exc)
            if enforce_app_spec:
                raise
            log.error("  AppSpec shadow pass failed: %s", exc)
            app_spec_result = None
            app_spec_scope = None

    demo: dict = {}
    if req.visual_demo_json:
        try:
            demo = json.loads(req.visual_demo_json)
        except Exception:
            pass

    from app.application.preview_app.brand_brief import ensure_brand_brief

    demo = ensure_brand_brief(
        demo,
        business_name=req.business_name or req.concept_name,
        industry=ctx.industry,
        business_description=getattr(req, "business_description", None),
        seed=request_id,
    )
    try:
        req.visual_demo_json = json.dumps(demo)
        db.commit()
    except Exception:
        db.rollback()
    brand_brief = demo.get("brand_brief") or {}
    theme = demo.get("visual_theme", {})
    primary = (brand_brief.get("palette") or {}).get("primary") or theme.get(
        "primary_color", "#0f766e"
    )
    secondary = (brand_brief.get("palette") or {}).get("secondary") or theme.get(
        "secondary_color", "#134e4a"
    )
    ref_meta: dict = {}
    if req.reference_metadata:
        try:
            ref_meta = json.loads(req.reference_metadata)
        except Exception:
            ref_meta = {}
    images = get_images_for_industry(
        ctx.industry,
        seed=request_id,
        hero_override=ref_meta.get("og_image") or None,
        business_name=req.business_name,
    )

    ctx.enforce_app_spec = enforce_app_spec
    ctx.app_spec_result = app_spec_result
    ctx.app_spec_scope = app_spec_scope
    ctx.demo = demo
    ctx.brand_brief = brand_brief
    ctx.primary = primary
    ctx.secondary = secondary
    ctx.images = images
