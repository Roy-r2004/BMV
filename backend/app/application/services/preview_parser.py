import json
import re
from typing import Optional

from app.application.prompts import PromptTemplate
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.shared.json_utils import extract_json_from_text


def extract_preview_from_blueprint(
    blueprint: str,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> dict:
    """Extract preview fields from blueprint text using regex and AI fallback."""
    preview = {
        "business_fit_score": None,
        "concept_name": None,
        "preview_summary": None,
        "preview_features": [],
    }

    score_match = re.search(
        r"business[- ]fit score[^0-9]*(\d{1,3})",
        blueprint,
        re.IGNORECASE,
    )
    if score_match:
        preview["business_fit_score"] = min(100, int(score_match.group(1)))

    concept_match = re.search(
        r"(?:custom MVP concept name|concept name)[:\s]*\**([^*\n]+)\**",
        blueprint,
        re.IGNORECASE,
    )
    if concept_match:
        preview["concept_name"] = concept_match.group(1).strip()

    summary_match = re.search(
        r"(?:free preview summary|preview summary)[:\s]*\**([^*\n]+(?:\n(?![0-9]+\.)[^*\n]+)*)",
        blueprint,
        re.IGNORECASE,
    )
    if summary_match:
        preview["preview_summary"] = summary_match.group(1).strip()

    features_section = re.search(
        r"(?:top 5 preview features|must-have MVP features)[:\s]*([\s\S]*?)(?=\n[0-9]+\.|\n\n|\Z)",
        blueprint,
        re.IGNORECASE,
    )
    if features_section:
        lines = features_section.group(1).strip().split("\n")
        features = []
        for line in lines:
            cleaned = re.sub(r"^[-*•\d.]+\s*", "", line.strip())
            if cleaned and len(cleaned) > 2:
                features.append(cleaned)
        preview["preview_features"] = features[:5]

    if not preview["business_fit_score"] or not preview["concept_name"]:
        try:
            prompt = template_renderer.render(PromptTemplate.PREVIEW_EXTRACTION, mvp_blueprint=blueprint)
            response = ai_provider.ask_chat(settings.TEXT_MODEL, [{"role": "user", "content": prompt}])
            extracted = extract_json_from_text(response)
            if extracted.get("business_fit_score"):
                preview["business_fit_score"] = extracted["business_fit_score"]
            if extracted.get("concept_name"):
                preview["concept_name"] = extracted["concept_name"]
            if extracted.get("preview_summary"):
                preview["preview_summary"] = extracted["preview_summary"]
            if extracted.get("preview_features"):
                preview["preview_features"] = extracted["preview_features"][:5]
        except Exception:
            pass

    if not preview["business_fit_score"]:
        preview["business_fit_score"] = 75
    if not preview["concept_name"]:
        preview["concept_name"] = "Custom Business MVP"
    if not preview["preview_summary"]:
        preview["preview_summary"] = "A custom MVP designed for your business needs."
    if not preview["preview_features"]:
        preview["preview_features"] = [
            "Lead capture",
            "Customer dashboard",
            "AI assistant",
            "Admin panel",
            "Automated workflows",
        ]

    return preview


def parse_preview_features(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    return [f.strip() for f in raw.split("\n") if f.strip()]
