"""AI feature hub must stay AiFeatureDeck — never a public-utility checkout stub."""
from __future__ import annotations

from app.application.preview_app.catalogue_contract.repair import (
    enforce_catalogue_page_contract,
)
from app.application.preview_app.catalogue_contract.validate import (
    validate_catalogue_page_content,
)
from app.application.preview_app.utility_compositor import should_compose_utility_page
from app.application.services.ai_features import ai_feature_hub_page_source


def test_ai_hub_page_passes_catalogue_contract() -> None:
    route = {
        "path": "/ai-features",
        "title": "AI features",
        "skeleton_id": "public-utility",
        "section_slots": ["header", "workspace", "footer"],
        "page_id": "PAGE-AI-FEATURES",
        "component_file": "src/pages/AiFeaturesPage.tsx",
    }
    tsx = ai_feature_hub_page_source(
        brand_name="Northwheel Pottery",
        features=[{"id": "ai-class-advisor", "name": "AI Class Advisor"}],
    )
    assert "AiFeatureDeck" in tsx
    assert validate_catalogue_page_content(tsx, route) == []


def test_enforce_replaces_utility_stub_with_ai_hub() -> None:
    architect = {
        "routes": [
            {
                "path": "/ai-features",
                "title": "AI features",
                "skeleton_id": "public-utility",
                "section_slots": ["header", "workspace", "footer"],
                "page_id": "PAGE-AI-FEATURES",
                "component_file": "src/pages/AiFeaturesPage.tsx",
            }
        ]
    }
    stub = """
import { PublicShell, PublicNav, PageHeader, Card, BrandFooter, SkeletonComposer, getSkeleton } from '@/ui';
const SKELETON_ID = "public-utility" as const;
export default function AiFeaturesPage() {
  return (
    <PublicShell brandName="Brand" nav={<PublicNav items={[]} />}>
      <PageHeader title="AI features" description="A current view of the work that needs your attention." />
      <Card title="Your details" description="Everything for this step in one place." />
    </PublicShell>
  );
}
"""
    updated, replaced = enforce_catalogue_page_contract(
        "src/pages/AiFeaturesPage.tsx",
        stub,
        architect,
        brand_name="Northwheel Pottery",
    )
    assert replaced is True
    assert "AiFeatureDeck" in updated
    assert "Signature package" not in updated
    assert "Your details" not in updated


def test_ai_hub_never_uses_utility_compositor() -> None:
    route = {
        "path": "/ai-features",
        "title": "AI features",
        "skeleton_id": "public-utility",
        "component_file": "src/pages/AiFeaturesPage.tsx",
        "page_id": "PAGE-AI-FEATURES",
    }
    assert should_compose_utility_page(route, "public-utility", route) is False
