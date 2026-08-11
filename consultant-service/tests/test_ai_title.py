"""Pins for the AI module's own title (JOB 5, session 34).

Six screens across the session-33 run drew a heading on the intelligence
module that nobody asked for — "HERO INTELLIGENCE", "ONLY AI
INTELLIGENCE", "PREMIUM AI INTELLIGENCE", "INTELLIGENCE MODULE",
"SOFTWARE-FORMED OPINION", "OPINION" — every one lifted from the prose
nearest the panel. Removing the phrases moved which prose it reached for;
the cause is structural: an untitled panel is a VACANCY, and the model
fills vacancies from context. ui-spec-v3 fills it with a real product
label instead.

Two directions pinned, because briefs-v2 is the control arm for every
comparison session 34 runs: WITH a title the exact string is in the
prompt above the headline; WITHOUT one the block renders the exact
session-33 wording, so a v2 brief's prompt is unchanged by this feature.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline import prompt_builder
from app.pipeline.ui_spec import UI_SPEC_PROMPT_VERSION


def _with_ai(dental_spec, **ai_fields):
    spec = dental_spec.model_copy(deep=True)
    for k, v in ai_fields.items():
        setattr(spec.ai, k, v)
    return spec


def test_a_titled_module_renders_the_exact_string_above_the_headline(dental_spec):
    spec = _with_ai(
        dental_spec,
        title="AI Insights",
        headline="Fill the 11 AM slot",
        rationale="Two cancellations, high-value patient waiting",
    )
    prompt = prompt_builder.build_dashboard_image_prompt(spec, archetype_id="operations-dashboard")
    assert "AI Insights" in prompt
    assert prompt.index("AI Insights") < prompt.index("Fill the 11 AM slot"), (
        "the label is the module's topmost line — above the headline"
    )
    assert "the module has no separate title" not in prompt


def test_an_untitled_module_renders_the_session_33_wording_unchanged(dental_spec):
    """briefs-v2 has no ai.title; its prompts must not change under this
    feature or the control arm stops being a control."""
    spec = _with_ai(dental_spec, title="", headline="Fill the 11 AM slot")
    prompt = prompt_builder.build_dashboard_image_prompt(spec, archetype_id="operations-dashboard")
    assert (
        "the module has no separate title, and nothing whatever is written above that headline" in prompt
    )
    assert "quiet kicker" not in prompt


def test_the_spec_stage_version_carries_the_field():
    """The frozen-brief bundles record the prompt version they were built
    with; v3 is what says a brief HAS the field."""
    assert UI_SPEC_PROMPT_VERSION == "ui-spec-v3"


def test_the_title_survives_spec_validation():
    from app.ui_spec import AiLayer

    ai = AiLayer.model_validate({"title": "Smart Forecast", "headline": "Book Tuesday fuller"})
    assert ai.title == "Smart Forecast"
    assert AiLayer.model_validate({"headline": "x"}).title == ""
