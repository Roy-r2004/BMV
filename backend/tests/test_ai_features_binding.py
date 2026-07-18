"""Plan AI features → structured inventory → AppSpec / preview coverage."""
from __future__ import annotations

import json
from pathlib import Path

from app.application.services.ai_features import (
    PAGE_AI_HUB_ID,
    bind_ai_features_to_app_spec,
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
