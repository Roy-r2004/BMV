import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.application.prompts import PromptTemplate
from app.application.pipelines._shared import fallback_visual_demo, get_request
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.application.services.preview_parser import parse_preview_features
from app.application.services.visual_demo_enrichment import enrich_visual_demo
from app.shared.json_utils import extract_json_from_text


def _business_info_block(req) -> str:
    from app.application.pipelines._shared import business_info

    return business_info(req)


def generate_visual_demo(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
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
    )

    try:
        response = ai_provider.ask_chat(settings.CODER_MODEL, [{"role": "user", "content": prompt}])
        demo = extract_json_from_text(response)
    except Exception:
        demo = fallback_visual_demo(req)

    demo = enrich_visual_demo(demo, req)

    req.visual_demo_json = json.dumps(demo)
    req.visual_demo_generated_at = datetime.utcnow()
    req.updated_at = datetime.utcnow()
    db.commit()
    return demo
