import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.application.prompts import PromptTemplate
from app.application.pipelines._shared import fallback_visual_demo, get_request
from app.application.services.ai_context import ai_call
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.application.services.preview_parser import parse_preview_features
from app.application.services.visual_demo_enrichment import enrich_visual_demo
from app.application.appspec.projection import brand_projection
from app.domain.schemas.app_spec import AppSpec
from app.shared.json_utils import extract_json_from_text


def _business_info_block(req) -> str:
    from app.application.pipelines._shared import business_info

    return business_info(req)


def generate_visual_demo(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    *,
    app_spec: AppSpec | None = None,
) -> dict:
    req = get_request(db, request_id)
    if not req.mvp_blueprint:
        raise ValueError("MVP blueprint must be generated first.")

    features = parse_preview_features(req.preview_features)
    features_block = "\n".join(f"- {f}" for f in features) if features else "None yet"

    prompt = template_renderer.render(
        PromptTemplate.VISUAL_DEMO,
        business_information=_business_info_block(req),
        mvp_blueprint=req.mvp_blueprint,
        preview_features=features_block,
        app_spec_projection_json=(
            json.dumps(brand_projection(app_spec), ensure_ascii=False)
            if app_spec
            else ""
        ),
    )

    try:
        with ai_call(stage="demo", writer="visual_demo"):
            response = ai_provider.ask_chat(
                settings.CODER_MODEL, [{"role": "user", "content": prompt}]
            )
        demo = extract_json_from_text(response)
    except Exception:
        demo = fallback_visual_demo(req)

    demo = enrich_visual_demo(demo, req)
    from app.application.preview_app.brand_brief import ensure_brand_brief

    demo = ensure_brand_brief(
        demo,
        business_name=req.business_name or req.concept_name,
        industry=req.industry,
        business_description=getattr(req, "business_description", None),
        seed=request_id,
    )

    req.visual_demo_json = json.dumps(demo)
    req.visual_demo_generated_at = datetime.utcnow()
    req.updated_at = datetime.utcnow()
    db.commit()
    return demo
