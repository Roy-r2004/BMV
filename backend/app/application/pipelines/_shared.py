"""Small helpers shared across the generation pipeline modules."""
from sqlalchemy.orm import Session

from app.application.services.preview_parser import parse_preview_features
from app.application.services.reference_formatter import format_reference_analysis
from app.domain.models.request import Request


def get_request(db: Session, request_id: int) -> Request:
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise ValueError(f"Request {request_id} not found")
    return req


def business_info(req: Request) -> str:
    ref_analysis = format_reference_analysis(req) or ""
    extra = ""
    if req.screenshot_analysis:
        extra += f"\nScreenshot analysis:\n{req.screenshot_analysis[:2000]}"
    if ref_analysis:
        extra += f"\nReference analysis:\n{ref_analysis[:2000]}"
    return f"""Business Name: {req.business_name}
Industry: {req.industry or 'N/A'}
Description: {req.business_description}
Target Customers: {req.target_customers or 'N/A'}
Main Problem: {req.main_problem or 'N/A'}
Reference URL: {req.reference_url or 'N/A'}
What They Like: {req.what_you_like or 'N/A'}
Desired Outcome: {req.desired_outcome or 'N/A'}
Needs AI: {req.needs_ai or 'N/A'}
Budget: {req.budget_range or 'N/A'}
Timeline: {req.timeline or 'N/A'}{extra}"""


def fallback_visual_demo(req: Request) -> dict:
    name = req.concept_name or f"{req.business_name} MVP"
    features = parse_preview_features(req.preview_features)
    cards = [
        {"title": f, "description": f"{f} for {req.business_name}.", "icon": "sparkles"}
        for f in features[:4]
    ] if features else [
        {"title": "Client portal", "description": "Your branded hub for clients.", "icon": "users"},
        {"title": "Progress tracking", "description": "Habits, metrics, and check-ins.", "icon": "chart"},
        {"title": "Plan delivery", "description": "Meal and workout plans in one place.", "icon": "sparkles"},
        {"title": "Messaging", "description": "Unified inbox for client communication.", "icon": "bell"},
    ]
    return {
        "product_name": name,
        "visual_theme": {
            "style": "modern",
            "primary_color": "#2563eb",
            "secondary_color": "#0d9488",
            "background_color": "#f8fafc",
            "font_style": "sans-serif",
        },
        "hero": {
            "headline": f"Welcome to your custom {req.industry or 'business'} solution",
            "subheadline": req.preview_summary or "A tailored MVP designed for your business.",
            "primary_cta": "Get Started",
            "secondary_cta": "Learn More",
        },
        "feature_cards": cards,
        "user_journey": [
            {"step": 1, "title": "Customer visits", "description": "A potential client discovers your service."},
            {"step": 2, "title": "AI helps them", "description": "The assistant answers questions and recommends services."},
            {"step": 3, "title": "Lead captured", "description": "Contact details are collected seamlessly."},
            {"step": 4, "title": "You get notified", "description": "You receive a summary and can follow up."},
        ],
        "screen_mockups": [
            {
                "screen_name": "Landing Page",
                "screen_type": "landing",
                "description": "Main entry point for customers.",
                "visible_elements": ["Hero section", "Feature highlights", "CTA button"],
            },
            {
                "screen_name": "AI Chat",
                "screen_type": "chat",
                "description": "Interactive assistant for customer questions.",
                "visible_elements": ["Chat messages", "Quick replies", "Contact form"],
            },
        ],
        "admin_dashboard_preview": {
            "should_show": True,
            "cards": [
                {"title": "New Leads", "value": "12", "description": "This week"},
                {"title": "Pending", "value": "5", "description": "Awaiting follow-up"},
                {"title": "Conversion", "value": "34%", "description": "Lead to booking"},
            ],
            "recent_activity": ["New lead from Instagram", "Booking confirmed", "AI handled 8 inquiries"],
        },
        "ai_workflow": [
            {"step": 1, "title": "Customer asks", "description": "A question comes in via chat or form."},
            {"step": 2, "title": "AI understands", "description": "The assistant identifies intent and needs."},
            {"step": 3, "title": "AI recommends", "description": "Relevant services or next steps are suggested."},
            {"step": 4, "title": "Lead captured", "description": "Details are collected and summarized for you."},
        ],
        "final_cta": {
            "headline": "Ready to build this for your business?",
            "description": "Roy can turn this concept into a working MVP.",
            "button_text": "Request Roy to Build This",
        },
    }


# `strip_fences` used to live here: a fence stripper anchored at position 0, so
# prose before the fence defeated it. It had no importer in `app/` or `tests/` —
# the `_strip_fences` used throughout codegen, critic, fix_agent and safety is a
# different function in `preview_app/text_utils.py`, and that one already routes
# JSON through the shared extractor. Removed rather than fixed: a corrected
# duplicate is still a duplicate, and this one had no caller to serve.
