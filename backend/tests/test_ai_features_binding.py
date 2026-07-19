"""Plan AI features → structured inventory → AppSpec / preview coverage."""
from __future__ import annotations

import json
from pathlib import Path

from app.application.preview_app.ai_feature_surfaces import inject_ai_panel_into_page
from app.application.services.ai_features import (
    PAGE_AI_HUB_ID,
    assign_feature_placements,
    bind_ai_features_to_app_spec,
    build_business_demo_scripts,
    enrich_feature,
    extract_ai_features_from_blueprint,
    missing_ai_feature_ids_in_workspace,
    parse_ai_features,
)
from app.domain.appspec.validation import validate_app_spec
from app.domain.schemas.app_spec import AppSpec


BLUEPRINT = """
1. Business summary
Studio pottery shop.

11. AI features that add real value
- Studio FAQ assistant: answers glaze and firing questions for shoppers
- Class waitlist AI: predicts no-shows and fills open seats
- Owner daily digest: summarizes orders and kiln status each morning

12. Screens/pages needed
- Home
- Classes
"""


def test_extract_ai_features_from_blueprint_section_11():
    features = extract_ai_features_from_blueprint(BLUEPRINT)
    assert len(features) == 3
    assert features[0]["id"] == "studio-faq-assistant"
    assert "glaze" in features[0]["description"].lower()
    assert features[1]["category"] in {"scheduling", "automation", "scoring", "ops", "chat", "digest"}
    assert features[2]["category"] == "digest"


def test_parse_ai_features_roundtrip():
    raw = json.dumps(extract_ai_features_from_blueprint(BLUEPRINT))
    parsed = parse_ai_features(raw)
    assert [f["id"] for f in parsed] == [
        "studio-faq-assistant",
        "class-waitlist-ai",
        "owner-daily-digest",
    ]


def test_bind_ai_features_to_app_spec_adds_must_hub(tmp_path: Path):
    fixture = Path(__file__).resolve().parent / "fixtures" / "app_spec" / "valid_booking.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    features = extract_ai_features_from_blueprint(BLUEPRINT)
    bound = bind_ai_features_to_app_spec(payload, features)

    req_ids = [r["id"] for r in bound["requirements"] if str(r["id"]).startswith("REQ-AI")]
    assert len(req_ids) == 3
    for req in bound["requirements"]:
        if str(req["id"]).startswith("REQ-AI"):
            assert req["priority"] == "must"
            assert "customer_input.ai_features" in req["source_refs"]
            assert req["verification_mode"] == "content"

    hub = next(p for p in bound["pages"] if p["id"] == PAGE_AI_HUB_ID)
    assert hub["route"] == "/ai-features"
    assert hub["surface"] == "public"
    assert len(hub["capability_ids"]) >= 3
    assert len(hub["evidence_ids"]) >= 3

    # Not deferred-only
    deferred_names = " ".join(str(d.get("name") or "") for d in bound.get("deferred_scope") or [])
    assert "Studio FAQ assistant" not in deferred_names

    spec = AppSpec.model_validate(bound)
    report = validate_app_spec(spec)
    assert report.is_valid, [i.message for i in report.issues]


def test_missing_ai_feature_ids_detects_gap():
    features = extract_ai_features_from_blueprint(BLUEPRINT)
    blob = 'data-ai-feature="studio-faq-assistant"'
    missing = missing_ai_feature_ids_in_workspace(blob, features)
    assert "class-waitlist-ai" in missing
    assert "owner-daily-digest" in missing
    assert "studio-faq-assistant" not in missing


def test_assign_feature_placements_picks_workflow_routes():
    features = extract_ai_features_from_blueprint(BLUEPRINT)
    routes = [
        {"path": "/", "title": "Home", "component_file": "src/pages/HomePage.tsx", "purpose": "marketing"},
        {"path": "/faq", "title": "FAQ", "component_file": "src/pages/FaqPage.tsx", "purpose": "assistant answers"},
        {"path": "/classes/book", "title": "Book", "component_file": "src/pages/BookingPage.tsx", "purpose": "booking"},
        {"path": "/owner/waitlists", "title": "Waitlists", "component_file": "src/pages/owner/WaitlistsPage.tsx", "purpose": "waitlist automation"},
        {"path": "/owner/dashboard", "title": "Dashboard", "component_file": "src/pages/owner/DashboardPage.tsx", "purpose": "ops dashboard"},
    ]
    placed = assign_feature_placements(features, routes)
    by_id = {f["id"]: f for f in placed}
    assert by_id["studio-faq-assistant"]["placement_path"] == "/faq"
    assert by_id["owner-daily-digest"]["placement_path"] == "/owner/dashboard"
    assert by_id["class-waitlist-ai"]["placement_path"] in {"/owner/waitlists", "/classes/book"}
    assert by_id["studio-faq-assistant"]["demo_prompts"]


POTTERY_CONTEXT = {
    "business_name": "Clay & Kiln",
    "industry": "pottery studio",
    "business_description": "Studio pottery shop with glaze recipes and kiln firing classes",
    "main_problem": "Shoppers ask the same glaze and firing questions all day",
    "desired_outcome": "Instant answers about glaze, firing, and class seats",
    "concept_name": "The Kiln Keeper",
    "mvp_blueprint": "FAQ covers glaze chemistry and kiln schedules for beginners",
}


def test_business_demo_scripts_use_domain_terms_not_generic_hours():
    feature = {
        "id": "studio-faq-assistant",
        "name": "Studio FAQ assistant",
        "description": "answers glaze and firing questions for shoppers",
        "category": "chat",
    }
    scripts = build_business_demo_scripts(feature, POTTERY_CONTEXT)
    joined = " ".join(scripts["demo_prompts"]).lower()
    assert "what are your hours" not in joined
    assert "how does pricing work" not in joined
    assert any(term in joined for term in ("glaze", "firing", "pottery", "kiln", "clay"))
    assert "clay & kiln" in joined or "pottery" in joined
    assert scripts["demo_results"]
    for prompt in scripts["demo_prompts"]:
        assert prompt in scripts["demo_results"]
        assert "clay & kiln" in scripts["demo_results"][prompt].lower()


def test_enrich_feature_with_context_overwrites_generic_demos():
    feature = {
        "id": "studio-faq-assistant",
        "name": "Studio FAQ assistant",
        "description": "answers glaze and firing questions for shoppers",
        "category": "chat",
        "demo_prompts": ["What are your hours this week?"],
    }
    enriched = enrich_feature(feature, context=POTTERY_CONTEXT)
    joined = " ".join(enriched["demo_prompts"]).lower()
    assert "what are your hours this week" not in joined
    assert any(term in joined for term in ("glaze", "firing", "pottery", "kiln"))
    assert enriched["demo_results"]


def test_assign_feature_placements_keeps_business_demo_scripts():
    features = extract_ai_features_from_blueprint(BLUEPRINT)
    routes = [
        {"path": "/faq", "title": "FAQ", "component_file": "src/pages/FaqPage.tsx", "purpose": "assistant"},
        {"path": "/owner/dashboard", "title": "Dashboard", "component_file": "src/pages/owner/DashboardPage.tsx"},
    ]
    placed = assign_feature_placements(features, routes, context=POTTERY_CONTEXT)
    faq = next(f for f in placed if f["id"] == "studio-faq-assistant")
    joined = " ".join(faq["demo_prompts"]).lower()
    assert "what are your hours" not in joined
    assert faq["demo_results"]


def test_inject_ai_panel_into_page_is_idempotent():
    source = """import { PublicShell, PublicNav } from '@/ui';

export default function FaqPage() {
  return (
    <PublicShell brandName=\"Studio\" nav={<PublicNav items={[]} />}>
      <div>FAQ</div>
    </PublicShell>
  );
}
"""
    once = inject_ai_panel_into_page(source, feature_id="studio-faq-assistant", brand_name="Studio")
    twice = inject_ai_panel_into_page(once, feature_id="studio-faq-assistant", brand_name="Studio")
    assert once.count("<AiFeaturePanel") == 1
    assert 'data-ai-feature-panel="studio-faq-assistant"' in once
    assert "aiFeatures" in once
    assert twice == once
