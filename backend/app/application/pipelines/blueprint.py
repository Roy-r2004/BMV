import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.application.prompts import PromptTemplate
from app.application.pipelines._shared import get_request
from app.application.services.ai_context import ai_call
from app.application.services.ai_features import extract_ai_features_from_blueprint
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.infrastructure.ai_providers.response_parser import ProviderGenerationError
from app.infrastructure.logging import get_logger
from app.application.services.preview_parser import extract_preview_from_blueprint

log = get_logger("Blueprint")


def _is_blueprint_transport_cut(error: Exception | None, result: str | None) -> bool:
    """Transport class only: a retryable provider raise or an empty-cut body.

    Refusal-class (non-retryable) raises are not weather and never re-asked;
    a non-empty answer is accepted as-is — the blueprint has no quality judge,
    and quality never takes a model fallback anywhere in this repo.
    """

    if error is not None:
        return isinstance(error, ProviderGenerationError) and error.retryable
    return not (result or "").strip()


def _ask_blueprint_with_transport_ladder(
    ai_provider: AIProvider, prompt: str
) -> str:
    """The R1 ladder at the pipeline's last naked MANDATORY ask (session 24).

    Attempt 1 and one bounded same-model re-ask on TEXT_MODEL, then ONE ask on
    the cross-provider fallback slot, then fail closed exactly as before the
    ladder existed. Every ask is its own telemetry row (attempt 1/2/3 under
    writer=mvp_blueprint), so firings are queryable like every other rung's.
    """

    messages = [{"role": "user", "content": prompt}]
    last_error: Exception | None = None
    for attempt, model in (
        (1, settings.TEXT_MODEL),
        (2, settings.TEXT_MODEL),
        (3, settings.BLUEPRINT_TRANSPORT_FALLBACK_MODEL),
    ):
        error: Exception | None = None
        result = ""
        with ai_call(stage="blueprint", writer="mvp_blueprint", attempt=attempt):
            try:
                result = ai_provider.ask_chat(model, messages)
            except Exception as exc:  # classified below; never silently eaten
                error = exc
        if not _is_blueprint_transport_cut(error, result):
            if error is not None:
                raise error
            return result
        last_error = error
        if attempt < 3:
            log.warning(
                "blueprint ask transport-cut on %s (attempt %s) — %s",
                model,
                attempt,
                "trying the cross-provider rung"
                if attempt == 2
                else "one bounded re-ask",
            )
    if last_error is not None:
        raise last_error
    raise RuntimeError(
        "blueprint ask returned an empty body on the primary and fallback models"
    )


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

    result = _ask_blueprint_with_transport_ladder(ai_provider, prompt)
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
