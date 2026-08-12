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

import json
import os
import pathlib
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


def _version_number(version: str) -> int:
    return int(version.rsplit("-v", 1)[1])


def test_the_spec_stage_version_carries_the_field():
    """The frozen-brief bundles record the prompt version they were built
    with; v3 is what says a brief HAS the field.

    Written as "v3 or later" rather than "== v3" because the template keeps
    moving for unrelated reasons — v4 made the navigation length a default
    that yields to a list the customer named — and an equality pin turns
    every later change into a spurious failure here. What the field
    actually needs is that no frozen bundle predates it and the live stage
    never falls behind them.
    """
    assert _version_number(UI_SPEC_PROMPT_VERSION) >= 3

    briefs = pathlib.Path(__file__).resolve().parents[1] / "golden" / "briefs-v3"
    bundles = sorted(briefs.glob("*.json"))
    assert bundles, "golden/briefs-v3 is empty — rebuild with scripts/build_golden.py"
    for path in bundles:
        frozen_at = json.loads(path.read_text())["frozen_by"]["ui_spec_prompt_version"]
        assert _version_number(frozen_at) >= 3, f"{path.name} predates the ai.title field"
        assert _version_number(frozen_at) <= _version_number(UI_SPEC_PROMPT_VERSION), (
            f"{path.name} was frozen at {frozen_at}, ahead of the live stage"
        )


def test_the_title_survives_spec_validation():
    from app.ui_spec import AiLayer

    ai = AiLayer.model_validate({"title": "Smart Forecast", "headline": "Book Tuesday fuller"})
    assert ai.title == "Smart Forecast"
    assert AiLayer.model_validate({"headline": "x"}).title == ""
