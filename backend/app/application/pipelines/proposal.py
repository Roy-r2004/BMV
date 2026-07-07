from datetime import datetime

from sqlalchemy.orm import Session

from app.application.prompts import PromptTemplate
from app.application.pipelines._shared import get_request
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer


def generate_proposal(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> str:
    req = get_request(db, request_id)
    if not req.mvp_blueprint:
        raise ValueError("MVP blueprint must be generated first.")

    prompt = template_renderer.render(
        PromptTemplate.PROPOSAL,
        business_name=req.business_name,
        industry=req.industry or "N/A",
        business_description=req.business_description,
        main_problem=req.main_problem or "N/A",
        desired_outcome=req.desired_outcome or "N/A",
        budget_range=req.budget_range or "N/A",
        timeline=req.timeline or "N/A",
        mvp_blueprint=req.mvp_blueprint,
        technical_plan=req.technical_plan or "Technical plan not yet generated.",
    )

    result = ai_provider.ask_chat(settings.TEXT_MODEL, [{"role": "user", "content": prompt}])
    req.proposal_draft = result
    req.updated_at = datetime.utcnow()
    db.commit()
    return result
