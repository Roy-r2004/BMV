import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.application.prompts import PromptTemplate
from app.application.pipelines._shared import get_request
from app.application.services.ai_features import extract_ai_features_from_blueprint
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.application.services.preview_parser import extract_preview_from_blueprint


def generate_mvp_blueprint(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> str:
    req = get_request(db, request_id)

    prompt = template_renderer.render(
        PromptTemplate.MVP_BLUEPRINT,
        project_type=getattr(req, 'project_type', None) or 'new',
        existing_product_url=getattr(req, 'existing_product_url', None) or 'N/A',
        business_name=req.business_name,
        industry=req.industry or "N/A",
        business_description=req.business_description,
        target_customers=req.target_customers or "N/A",
        main_problem=req.main_problem or "N/A",
        reference_url=req.reference_url or "N/A",
        reference_metadata=req.reference_metadata or "N/A",
        what_you_like=req.what_you_like or "N/A",
        desired_outcome=req.desired_outcome or "N/A",
        needs_ai=req.needs_ai or "N/A",
        budget_range=req.budget_range or "N/A",
        timeline=req.timeline or "N/A",
        screenshot_analysis=req.screenshot_analysis or "No screenshot analysis available.",
    )

    result = ai_provider.ask_chat(settings.TEXT_MODEL, [{"role": "user", "content": prompt}])
    req.mvp_blueprint = result

    preview = extract_preview_from_blueprint(result, ai_provider, template_renderer)
    req.business_fit_score = preview["business_fit_score"]
    req.concept_name = preview["concept_name"]
    req.preview_summary = preview["preview_summary"]
    req.preview_features = json.dumps(preview["preview_features"])
    needs = str(getattr(req, "needs_ai", None) or "").strip().lower()
    if needs == "no":
        req.ai_features = json.dumps([])
    else:
        req.ai_features = json.dumps(extract_ai_features_from_blueprint(result))
    req.updated_at = datetime.utcnow()
    db.commit()
    return result
