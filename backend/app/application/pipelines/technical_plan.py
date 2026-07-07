from datetime import datetime

from sqlalchemy.orm import Session

from app.application.prompts import PromptTemplate
from app.application.pipelines._shared import get_request
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer


def generate_technical_plan(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> str:
    req = get_request(db, request_id)
    if not req.mvp_blueprint:
        raise ValueError("MVP blueprint must be generated first.")

    prompt = template_renderer.render(PromptTemplate.TECHNICAL_PLAN, mvp_blueprint=req.mvp_blueprint)
    try:
        result = ai_provider.ask_chat(settings.CODER_MODEL, [{"role": "user", "content": prompt}])
    except Exception:
        result = ai_provider.ask_chat(settings.TEXT_MODEL, [{"role": "user", "content": prompt}])
    req.technical_plan = result
    req.updated_at = datetime.utcnow()
    db.commit()
    return result
