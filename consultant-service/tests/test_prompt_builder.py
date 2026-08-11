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
    prompt = prompt_builder.build_dashboard_image_prompt(dental_spec)
    assert "DESIGN CONSTRAINTS" in prompt
    assert "production SaaS application" in prompt
    # The anti-AI-slop constraints that define the whole approach.
    for banned in ("futuristic", "glassmorphism", "mockup frames", "marketing landing-page"):
        assert banned in prompt
    assert "light" in prompt.lower()
    assert "full-bleed" in prompt.lower()


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
    assert "Preserve the sidebar" in prompt
    assert "Preserve the typography" in prompt
    assert "Schedule" in prompt
    assert "DESIGN CONSTRAINTS" in prompt


def test_prompt_versions_are_stable_identifiers():
    assert prompt_builder.DASHBOARD_IMAGE_PROMPT_VERSION == "dashboard-image-v1"
    assert prompt_builder.SCREEN_CONTINUATION_PROMPT_VERSION == "screen-continuation-v1"
