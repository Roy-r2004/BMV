from unittest.mock import patch

from app.pipeline import prompt_builder
from app.ui_spec import UIDemoSpec


def test_dashboard_prompt_includes_business_content(dental_spec):
    prompt = prompt_builder.build_dashboard_image_prompt(dental_spec)
    assert "SmileBright Dental" in prompt
    assert "SmileBright Operations" in prompt
    assert "Good morning, Dr. Carter" in prompt
    assert "Appointments Today" in prompt
    assert "$4,850" in prompt
    assert "Sarah Mitchell" in prompt
    assert "Dental Cleaning" in prompt
    assert "Appointments This Week" in prompt
    assert "#0e9594" in prompt


def test_dashboard_prompt_includes_design_constraints(dental_spec):
    """The anti-slop guards are the point of building prompts in code, and
    they must survive the register change — the cinematic register moved the
    ground, it did not licence the cliché."""
    prompt = prompt_builder.build_dashboard_image_prompt(dental_spec)
    assert "DESIGN CONSTRAINTS" in prompt
    assert "production software" in prompt
    for banned in ("glassmorphism", "mockup frames", "concept art", "lorem ipsum", "neon glow"):
        assert banned in prompt, f"anti-slop guard lost: {banned}"
    assert "full-bleed" in prompt.lower()


def test_light_register_is_preserved_verbatim(dental_spec):
    """Kept reachable so the funded A/B has something to compare against.
    If this drifts, the comparison stops measuring the register change."""
    with patch.object(prompt_builder.settings, "IMAGE_REGISTER", "light"):
        prompt = prompt_builder.build_dashboard_image_prompt(dental_spec)
    assert "production SaaS application" in prompt
    for banned in ("futuristic", "glassmorphism", "mockup frames", "marketing landing-page"):
        assert banned in prompt
    assert "#FFFFFF content on #F8F9FB canvas" in prompt


def test_unknown_register_falls_back_to_cinematic_rather_than_raising(dental_spec):
    """A typo in an env var must not take the image stage down."""
    with patch.object(prompt_builder.settings, "IMAGE_REGISTER", "chartreuse"):
        assert prompt_builder.register_id() == "cinematic"
        assert "deep, single-hue ground" in prompt_builder.build_dashboard_image_prompt(dental_spec)


def test_dashboard_prompt_handles_missing_optionals():
    spec = UIDemoSpec.model_validate(
        {
            "business": {"name": "Bare Minimum LLC", "industry": "Retail"},
            "product": {"name": "BM OS", "purpose": "ops", "screen_type": "dashboard"},
        }
    )
    prompt = prompt_builder.build_dashboard_image_prompt(spec)
    assert "Bare Minimum LLC" in prompt
    # No chart DATA block, and no art-pack chart instruction either — a
    # chartless screen must not be invited to invent one.
    assert "CHART — this is the screen's HERO element" not in prompt
    assert "CHART TREATMENT" not in prompt
    assert "SECONDARY PANEL" not in prompt
    assert "ACTIVITY" not in prompt
    assert "None" not in prompt  # no leaked nulls


def test_continuation_prompt_preserves_design_and_changes_screen(dental_spec):
    schedule = dental_spec.model_copy(deep=True)
    schedule.product.screen_type = "schedule"
    prompt = prompt_builder.build_continuation_prompt(schedule, "Dashboard")
    assert "SAME application" in prompt
    assert "Preserve the navigation" in prompt
    assert "Preserve the typography" in prompt
    assert "Schedule" in prompt
    assert "DESIGN CONSTRAINTS" in prompt


def test_continuation_does_not_ask_for_a_light_look_in_the_cinematic_register(dental_spec):
    """The follow-up prompt used to say "preserve the overall light look"
    unconditionally — a contradiction with the register in the same prompt,
    which the model resolves by splitting the difference."""
    cinematic = prompt_builder.build_continuation_prompt(dental_spec, "Dashboard")
    assert "overall light, restrained" not in cinematic
    assert "deep single-hue ground" in cinematic
    with patch.object(prompt_builder.settings, "IMAGE_REGISTER", "light"):
        assert "overall light, restrained" in prompt_builder.build_continuation_prompt(dental_spec, "Dashboard")


def test_prompt_versions_are_stable_identifiers():
    assert prompt_builder.DASHBOARD_IMAGE_PROMPT_VERSION == "dashboard-image-v2"
    assert prompt_builder.SCREEN_CONTINUATION_PROMPT_VERSION == "screen-continuation-v2"
