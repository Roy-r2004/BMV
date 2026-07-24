"""Registry mapping logical prompt names to their Jinja2 template paths.

Replaces the old 1195-line `app/prompts.py` module of raw triple-quoted
`.format()` strings. Every prompt now lives as a `.j2` file under
`app/templates/prompts/`; this class just gives call sites a typed,
discoverable name instead of a magic string.

Usage:
    from app.application.prompts import PromptTemplate
    from app.infrastructure.templating.renderer import get_template_renderer

    renderer = get_template_renderer()
    prompt = renderer.render(PromptTemplate.MVP_BLUEPRINT, business_name=..., ...)
"""


class PromptTemplate:
    SCREENSHOT_ANALYSIS = "prompts/screenshot_analysis.j2"
    REFERENCE_URL_ANALYSIS = "prompts/reference_url_analysis.j2"
    APP_SPEC = "prompts/app_spec.j2"
    APP_SPEC_REPAIR = "prompts/app_spec_repair.j2"
    APP_SPEC_COVERAGE = "prompts/app_spec_coverage.j2"
    V2_PRODUCT_STRATEGY = "prompts/v2_product_strategy.j2"
    V2_INFORMATION_ARCHITECTURE = "prompts/v2_information_architecture.j2"
    V2_DESIGN_DNA = "prompts/v2_design_dna.j2"
    TECHNICAL_PLAN = "prompts/technical_plan.j2"
    MVP_BLUEPRINT = "prompts/mvp_blueprint.j2"
    VISUAL_DEMO = "prompts/visual_demo.j2"
    PROPOSAL = "prompts/proposal.j2"
    BUILD_PLANS = "prompts/build_plans.j2"
    PREVIEW_EXTRACTION = "prompts/preview_extraction.j2"
    PREVIEW_REFINEMENT = "prompts/preview_refinement.j2"
    HTML_PAGE = "prompts/html_page.j2"
    UI_EXPERIENCE_PLAN = "prompts/ui_experience_plan.j2"
    DESIGN_MANIFEST = "prompts/design_manifest.j2"
    PLAN_VALIDATION = "prompts/plan_validation.j2"
    PLAN_EXPANSION = "prompts/plan_expansion.j2"
    PAGE_QA = "prompts/page_qa.j2"
    PAGE_FIX = "prompts/page_fix.j2"
    PREVIEW_APP_ARCHITECT = "prompts/preview_app_architect.j2"
    PREVIEW_APP_FILE = "prompts/preview_app_file.j2"
    PREVIEW_APP_UTILITY_CONTENT = "prompts/preview_app_utility_content.j2"
    PREVIEW_APP_SLOT_FILL = "prompts/preview_app_slot_fill.j2"
    PREVIEW_APP_CRITIC = "prompts/preview_app_critic.j2"
    PREVIEW_APP_VISUAL_CRITIC = "prompts/preview_app_visual_critic.j2"
    PREVIEW_APP_REFINE = "prompts/preview_app_refine.j2"
    PREVIEW_APP_FIX = "prompts/preview_app_fix.j2"
    PREVIEW_APP_MOCK_ENRICH = "prompts/preview_app_mock_enrich.j2"
    PREVIEW_APP_MOCK_SYNTHESIZE = "prompts/preview_app_mock_synthesize.j2"
    PREVIEW_APP_CHAT_REFINEMENT = "prompts/preview_app_chat_refinement.j2"
