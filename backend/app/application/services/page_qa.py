"""Multi-agent page quality assurance — validates against the planner's page spec."""
import json
from dataclasses import dataclass, field

from app.application.prompts import PromptTemplate
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.application.services.page_experience import page_required_sections


@dataclass
class QAResult:
    score: int = 0
    passes: bool = False
    critical_issues: list[str] = field(default_factory=list)
    sections_found: list[str] = field(default_factory=list)
    sections_missing: list[str] = field(default_factory=list)


def check_page(
    html: str,
    page_spec: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> QAResult:
    required = page_required_sections(page_spec)
    features = page_spec.get("features_to_showcase") or []
    page_spec_json = json.dumps(page_spec, ensure_ascii=False, indent=2)

    prompt = template_renderer.render(
        PromptTemplate.PAGE_QA,
        page_spec_json=page_spec_json,
        page_type=page_spec.get("page_type", page_spec.get("title", "Page")),
        page_purpose=page_spec.get("purpose", ""),
        required_sections="\n".join(f"- {s}" for s in required) or "- (see page spec)",
        features_to_showcase="\n".join(f"- {f}" for f in features) or "- none listed",
        html_preview=html[:6000],
    )
    try:
        raw = ai_provider.ask_chat(settings.HTML_MODEL, [{"role": "user", "content": prompt}], max_tokens=1000)
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
            return QAResult(
                score=int(data.get("score", 0)),
                passes=bool(data.get("passes", False)),
                critical_issues=data.get("critical_issues", []),
                sections_found=data.get("sections_found", []),
                sections_missing=data.get("sections_missing", []),
            )
    except Exception:
        pass
    return QAResult(score=0, passes=False, critical_issues=["QA agent failed to parse"])


def fix_page(
    html: str,
    page_spec: dict,
    qa: QAResult,
    manifest: dict,
    plan: dict,
    role_spec: dict,
    current_page_id: str,
    accent: str,
    images: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> str:
    design_system = plan.get("design_system") or manifest.get("design_system") or {}
    prompt = template_renderer.render(
        PromptTemplate.PAGE_FIX,
        page_spec_json=json.dumps(page_spec, ensure_ascii=False, indent=2),
        design_system_json=json.dumps(design_system, ensure_ascii=False, indent=2),
        role_navigation_json=json.dumps(role_spec.get("navigation") or {}, ensure_ascii=False, indent=2),
        current_page_id=current_page_id,
        manifest=json.dumps(manifest, ensure_ascii=False),
        img_hero=images.get("hero", ""),
        img_card1=images.get("card1", ""),
        img_card2=images.get("card2", ""),
        img_card3=images.get("card3", ""),
        issues="\n".join(f"- {i}" for i in qa.critical_issues) or "None",
        missing_sections="\n".join(f"- {s}" for s in qa.sections_missing) or "None",
        current_html=html,
    )
    raw = ai_provider.ask_chat(settings.HTML_MODEL, [{"role": "user", "content": prompt}], max_tokens=12000)
    raw = raw.strip()
    for fence in ("```html", "```"):
        if raw.startswith(fence):
            raw = raw[len(fence):]
        if raw.endswith("```"):
            raw = raw[:-3]
    return raw.strip()
