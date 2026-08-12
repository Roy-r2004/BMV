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


# ── the active item has to exist (session 38, request 107) ───────────────
# "Only the active item changes, to Schedule" was sent for a screen whose
# navigation was the customer's own Home / Gallery / About / Contact. The
# model added a sixth item to have something to activate, and the
# text-truth gate passed the screen because the spec never ordered the
# string it invented.


def _nav_spec(nav: list[str], screen_type: str) -> UIDemoSpec:
    return UIDemoSpec.model_validate(
        {
            "business": {"name": "Jeanne Art", "industry": "Art"},
            "product": {"name": "Jeanne Artistry Gateway", "screen_type": screen_type},
            "navigation": nav,
        }
    )


JEANNE_NAV = ["Home", "Gallery", "About", "Contact"]


def test_the_active_item_is_named_only_when_the_navigation_has_one():
    assert prompt_builder.active_nav_item(_nav_spec(JEANNE_NAV, "gallery")) == "Gallery"
    # Case and spacing are styling, not identity — the same rule the
    # text-truth gate applies to these labels.
    assert prompt_builder.active_nav_item(_nav_spec(["HOME", "Gallery"], "home")) == "HOME"
    assert prompt_builder.active_nav_item(_nav_spec(JEANNE_NAV, "schedule")) is None


def test_a_follow_up_screen_absent_from_the_navigation_is_not_asked_to_activate_one():
    prompt = prompt_builder.build_continuation_prompt(_nav_spec(JEANNE_NAV, "schedule"), "Home")
    assert "Only the active item changes" not in prompt
    assert "same items in the same order" in prompt, "the navigation contract itself must survive"
    # ...and the sentence comes back the moment it is true.
    named = prompt_builder.build_continuation_prompt(_nav_spec(JEANNE_NAV, "gallery"), "Home")
    assert "Only the active item changes, to Gallery." in named


def test_an_anchor_screen_absent_from_the_navigation_is_not_asked_to_activate_one(dental_spec):
    off_nav = dental_spec.model_copy(deep=True)
    off_nav.navigation = list(JEANNE_NAV)
    assert "active" not in prompt_builder._nav_block(off_nav)
    on_nav = dental_spec.model_copy(deep=True)
    on_nav.navigation = ["Dashboard", "Schedule", "Reports"]
    assert "mark Dashboard active" in prompt_builder._nav_block(on_nav)


def test_the_navigation_block_still_lists_exactly_the_specs_items(dental_spec):
    """Whatever happens to the active marker, the list itself is the
    contract — this is the string the text-truth gate then measures."""
    off_nav = dental_spec.model_copy(deep=True)
    off_nav.navigation = list(JEANNE_NAV)
    block = prompt_builder._nav_block(off_nav)
    assert block.splitlines()[-4:] == JEANNE_NAV


# ── the conversation block (session 38) ──────────────────────────────────


def _console_spec() -> UIDemoSpec:
    return UIDemoSpec.model_validate({
        "business": {"name": "Lumière Hair Studio", "industry": "Hair Salon"},
        "product": {"name": "Lumière Front Desk", "screen_type": "conversations"},
        "navigation": ["Conversations", "Analytics", "Knowledge", "Settings"],
        "kpis": [{"label": "Chats Today", "value": "34"}],
        "chart": {"title": "Volume", "labels": ["Mon"], "values": [3]},
        "primary_panel": {"title": "Threads", "rows": [{"name": "Sarah Chen"}]},
        "concept": {
            "kind": "assistant",
            "turns": [
                {"speaker": "customer", "text": "Do you have anything Thursday afternoon?"},
                {"speaker": "assistant", "text": "3:15pm with Elara, or 4:00pm with Lena."},
            ],
            "detail": {"title": "About Sarah", "rows": [{"visits": "4", "last": "Balayage"}]},
            "primary_action": "Reply to Sarah",
            "secondary_action": "Offer 4:00pm",
        },
    })


def test_the_thread_is_the_screen_and_the_dashboard_layout_stands_down():
    prompt = prompt_builder.build_dashboard_image_prompt(_console_spec(), archetype_id="assistant-console")
    assert "Customer: Do you have anything Thursday afternoon?" in prompt
    assert "Assistant: 3:15pm with Elara, or 4:00pm with Lena." in prompt
    # A conversation screen is not a metrics screen: no chart, no main list
    # panel, no photographic hero competing with the one thing it exists to
    # show. KPIs survive only as the header strip.
    assert "CHART" not in prompt
    assert "Main list panel:" not in prompt
    # "The visual centerpiece" appears in the tail that names the prompt's
    # own scaffolding as non-labels, so the hero is detected by its data.
    assert "Subject:" not in prompt
    assert "Chats Today" in prompt


def test_the_composer_carries_a_real_string_or_is_not_asked_for():
    """An unlabelled input is a blank control — on the defect inspector's
    list — and an invented placeholder is worse."""
    spec = _console_spec()
    assert 'placeholder "Reply to Sarah"' in prompt_builder.build_dashboard_image_prompt(spec)
    spec.concept.primary_action = ""
    # Not a bare "placeholder" — the anti-slop block bans "placeholder data"
    # in every prompt, and matching that would pass for the wrong reason.
    assert 'placeholder "' not in prompt_builder.build_dashboard_image_prompt(spec)


def test_a_console_screen_still_gets_its_navigation_and_no_invented_active_item():
    spec = _console_spec()
    prompt = prompt_builder.build_dashboard_image_prompt(spec)
    assert "Conversations" in prompt
    assert "mark Conversations active" in prompt


def test_the_conversation_shape_is_switchable_off_like_every_other_concept():
    with patch.object(prompt_builder.settings, "ENABLE_TOOL_SCREENS", False):
        prompt = prompt_builder.build_dashboard_image_prompt(_console_spec())
    assert "Do you have anything Thursday afternoon?" not in prompt
    assert "Main list panel:" in prompt, "it must fall all the way back to the dashboard layout"
