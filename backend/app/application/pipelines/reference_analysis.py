import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.application.prompts import PromptTemplate
from app.application.pipelines._shared import get_request
from app.application.services.ai_context import ai_call
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.infrastructure.storage.file_service import is_image_file
from app.infrastructure.web.reference_scraper import fetch_reference_metadata


def fetch_and_save_reference_metadata(db: Session, request_id: int) -> dict:
    req = get_request(db, request_id)
    if not req.reference_url:
        return {}
    metadata = fetch_reference_metadata(req.reference_url)
    req.reference_metadata = json.dumps(metadata)
    req.updated_at = datetime.utcnow()
    db.commit()
    return metadata


def generate_reference_analysis(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> str:
    req = get_request(db, request_id)
    if req.screenshot_analysis:
        return req.screenshot_analysis
    if not req.reference_url:
        return "No reference URL available."

    meta: dict = {}
    if req.reference_metadata:
        try:
            meta = json.loads(req.reference_metadata)
        except Exception:
            meta = {}

    prompt = template_renderer.render(
        PromptTemplate.REFERENCE_URL_ANALYSIS,
        reference_url=req.reference_url,
        what_you_like=req.what_you_like or "Not specified",
        title=meta.get("title", ""),
        description=meta.get("description", ""),
        visible_text_snippet=meta.get("visible_text_snippet", ""),
    )
    with ai_call(stage="analyze", writer="reference_url_analysis"):
        result = ai_provider.ask_chat(
            settings.TEXT_MODEL, [{"role": "user", "content": prompt}]
        )
    req.screenshot_analysis = result
    req.updated_at = datetime.utcnow()
    db.commit()
    return result


def analyze_screenshot(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> str:
    req = get_request(db, request_id)
    if not req.reference_file_path or not is_image_file(req.reference_file_path):
        return "No image file available for analysis."

    prompt = template_renderer.render(PromptTemplate.SCREENSHOT_ANALYSIS)
    with ai_call(stage="analyze", writer="screenshot_analysis"):
        result = ai_provider.ask_vision(
            settings.VISION_MODEL, prompt, req.reference_file_path
        )
    req.screenshot_analysis = result
    req.updated_at = datetime.utcnow()
    db.commit()
    return result
