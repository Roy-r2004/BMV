"""AI advisor card CTAs must not navigate to invented missing sub-routes."""
from __future__ import annotations

from app.application.preview_app.ai_feature_surfaces import (
    inject_ai_panel_into_page,
    rewrite_invented_ai_step_links,
)


def test_rewrite_ai_advisor_subpath_to_panel_hash() -> None:
    source = '''
export default function AiAdvisorChatPage() {
  return (
    <PublicShell>
      <Button href={"/ai-advisor/skill-assessment"}>Start Skill Assessment</Button>
      <Button href={"/ai-advisor/class-interests"}>Explore Class Types</Button>
      <div data-ai-feature-panel="skill-level-assessor">
        <AiFeaturePanel />
      </div>
    </PublicShell>
  );
}
'''
    fixed = rewrite_invented_ai_step_links(source)
    assert "/ai-advisor/skill-assessment" not in fixed
    assert 'href="#skill-level-assessor"' in fixed
    assert fixed.count('href="#skill-level-assessor"') == 2


def test_inject_panel_adds_hash_target_id() -> None:
    source = """
export default function Page() {
  return (
    <PublicShell brandName="Brand">
      <div>content</div>
    </PublicShell>
  );
}
"""
    updated = inject_ai_panel_into_page(
        source, feature_id="skill-level-assessor", brand_name="Brand"
    )
    assert 'id="skill-level-assessor"' in updated
    assert 'data-ai-feature-panel="skill-level-assessor"' in updated
