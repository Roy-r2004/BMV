"""Pins for session 32 — the cinematic register and what it unblocks.

The through-line: session 31 measured three separate prompt improvements
losing their pairwise (W2 art packs, W5 design sheet, one W1 cell) and every
losing run named the same cause — content clipped in the bottom-right corner
the prompt reserves for the composited logo. These tests pin the four changes
that follow from that finding:

1. the mark moves to a footer strip, so no canvas is reserved at all;
2. the prompt's corner reservation is emitted ONLY when the mark is
   actually going in the corner — the two must never drift apart again;
3. the design register can be dark without being the AI-slop cliché;
4. a screen can be a TOOL, carry a rendered HERO, and state an AI OPINION —
   none of which the spec could previously express.
"""

import io
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

from app.pipeline import images as images_mod
from app.pipeline import prompt_builder
from app.ui_spec import UIDemoSpec


def _png(w: int = 640, h: int = 360, color: str = "white") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _logo() -> Image.Image:
    return Image.new("RGBA", (64, 64), (255, 0, 0, 255))


def _tool_spec() -> UIDemoSpec:
    return UIDemoSpec.model_validate(
        {
            "business": {"name": "Garden View", "industry": "Property development", "primary_color": "#0B3B2E"},
            "product": {"name": "Garden View Explorer", "purpose": "unit selection", "screen_type": "block-selection"},
            "navigation": ["Residences", "Amenities", "Gallery", "Location", "About"],
            "kpis": [
                {"label": "Blocks", "value": "3"},
                {"label": "Floors", "value": "61"},
                {"label": "Residences", "value": "180+"},
            ],
            "hero": {
                "subject": "a 30-storey glass residential tower at dusk",
                "treatment": "photoreal render",
                "caption": "Block A",
                "placement": "center",
            },
            "concept": {
                "kind": "selector",
                "steps": [
                    {"label": "Select Block", "options": ["Block A", "Block B", "Block C"], "selected": "Block A"},
                    {"label": "Select Floor", "options": ["18", "17", "16"], "selected": "18"},
                ],
                "detail": {
                    "title": "Block A · Level 18",
                    "rows": [{"unit": "A-1801", "beds": "2 Bedrooms", "size": "124.5 SQM"}],
                },
                "primary_action": "View Floor Plan",
                "secondary_action": "Explore Units",
            },
            "ai": {
                "headline": "Recommended: A-1803",
                "rationale": "Best light, under budget",
                "confidence": "94% match",
                "chips": ["Corner unit", "Ready March"],
            },
        }
    )


# ── 1. The footer strip ───────────────────────────────────────────────────


def test_footer_watermark_never_covers_the_interface(monkeypatch):
    """The entire reason for the change: the mark must not land on rendered
    UI. Verified structurally — the original pixels survive untouched and the
    canvas grew — not by trusting the placement arithmetic."""
    monkeypatch.setattr(images_mod, "_bmv_logo", lambda: _logo())
    monkeypatch.setattr(images_mod.settings, "WATERMARK_STYLE", "footer")

    original = _png(640, 360, "white")
    out = Image.open(io.BytesIO(images_mod._apply_bmv_watermark(original)))

    assert out.width == 640
    assert out.height > 360, "the strip must grow the canvas, not eat into it"
    assert out.height - 360 == max(28, round(360 * 0.06))
    # Every pixel of the original interface is still white: nothing was
    # pasted over it. The hairline sits on the first row of the strip.
    interface = out.convert("RGB").crop((0, 0, 640, 360))
    assert interface.getcolors() == [(640 * 360, (255, 255, 255))]


def test_footer_strip_carries_the_mark(monkeypatch):
    """A strip with no logo on it would pass the "never covers UI" test while
    shipping an unbranded image — DoD line 5 is the one that must not bend."""
    monkeypatch.setattr(images_mod, "_bmv_logo", lambda: _logo())
    monkeypatch.setattr(images_mod.settings, "WATERMARK_STYLE", "footer")

    out = Image.open(io.BytesIO(images_mod._apply_bmv_watermark(_png(640, 360)))).convert("RGB")
    strip = out.crop((0, 360, 640, out.height))
    reds = [c for count, c in strip.getcolors(maxcolors=100000) if c[0] > 150 and c[1] < 90 and c[2] < 90]
    assert reds, "the logo is not on the strip"


def test_footer_strip_is_tinted_from_the_interface_edge(monkeypatch):
    """A black bar under a dark screen and the same black bar under a light
    one reads as stapled on. The strip takes its hue from the bottom edge."""
    monkeypatch.setattr(images_mod, "_bmv_logo", lambda: _logo())
    monkeypatch.setattr(images_mod.settings, "WATERMARK_STYLE", "footer")

    out = Image.open(io.BytesIO(images_mod._apply_bmv_watermark(_png(200, 100, "#3060C0")))).convert("RGB")
    r, g, b = out.getpixel((5, out.height - 2))
    assert b > r and b > g, "the strip lost the interface's hue"
    assert b < 0xC0, "the strip must be darker than the interface it sits under"


def test_corner_watermark_still_available_for_rollback(monkeypatch):
    """Kept so the footer change can be compared and reverted from one env
    var — the corner path is not dead code, it is the control arm."""
    monkeypatch.setattr(images_mod, "_bmv_logo", lambda: _logo())
    monkeypatch.setattr(images_mod.settings, "WATERMARK_STYLE", "corner")

    out = Image.open(io.BytesIO(images_mod._apply_bmv_watermark(_png(640, 360))))
    assert (out.width, out.height) == (640, 360), "the corner variant must not grow the canvas"


def test_watermark_still_a_noop_without_a_logo_file(monkeypatch):
    monkeypatch.setattr(images_mod, "_bmv_logo", lambda: None)
    original = _png()
    assert images_mod._apply_bmv_watermark(original) is original


def test_tiny_images_do_not_crash_the_footer(monkeypatch):
    """The hardening suite watermarks 8x8 fixtures; arithmetic that assumes a
    real screenshot would make those tests fail for the wrong reason."""
    monkeypatch.setattr(images_mod, "_bmv_logo", lambda: _logo())
    monkeypatch.setattr(images_mod.settings, "WATERMARK_STYLE", "footer")
    out = Image.open(io.BytesIO(images_mod._apply_bmv_watermark(_png(8, 8))))
    assert out.height > 8


# ── 2. Prompt and watermark must agree about the corner ───────────────────


def test_corner_reservation_is_emitted_only_when_the_mark_goes_there(dental_spec):
    """These two settings drifted apart once already, and the cost was ~12%x17%
    of every canvas reserved for a mark that had moved."""
    with patch.object(prompt_builder.settings, "WATERMARK_STYLE", "corner"):
        assert "Reserve only the immediate bottom-right corner" in prompt_builder.build_dashboard_image_prompt(
            dental_spec
        )
    with patch.object(prompt_builder.settings, "WATERMARK_STYLE", "footer"):
        prompt = prompt_builder.build_dashboard_image_prompt(dental_spec)
    assert "Reserve only the immediate bottom-right corner" not in prompt
    assert "bottom-right" not in prompt


def test_continuation_prompt_agrees_with_the_anchor_about_the_corner(dental_spec):
    with patch.object(prompt_builder.settings, "WATERMARK_STYLE", "footer"):
        assert "bottom-right" not in prompt_builder.build_continuation_prompt(dental_spec, "Dashboard")


# ── 3. Dark, but not the cliché ───────────────────────────────────────────


def test_cinematic_register_keeps_every_anti_slop_guard(dental_spec):
    """The light register earned these bans by producing the fake look
    without them. Moving the ground does not licence any of them back."""
    prompt = prompt_builder.build_dashboard_image_prompt(dental_spec)
    for banned in (
        "neon glow",
        "lens flare",
        "circuit-board patterns",
        "hexagon grids",
        "scan lines",
        "floating 3D geometry",
        "particle fields",
        "glassmorphism",
        "concept art",
        "mockup frames",
        "lorem ipsum",
    ):
        assert banned in prompt, f"cinematic register dropped the guard against: {banned}"


def test_cinematic_register_asks_for_one_accent_only(dental_spec):
    prompt = prompt_builder.build_dashboard_image_prompt(dental_spec)
    assert "exactly ONE luminous accent" in prompt
    assert "a second accent colour" in prompt


def test_cinematic_branding_does_not_contradict_itself(dental_spec):
    """style.palette_description comes from the spec stage and says things
    like "light interface, teal accents". Emitting it inside a prompt that
    asks for a deep dark ground is a contradiction in one prompt."""
    spec = dental_spec.model_copy(deep=True)
    spec.style.palette_description = "light interface, teal accents"
    assert "light interface, teal accents" not in prompt_builder.build_dashboard_image_prompt(spec)
    with patch.object(prompt_builder.settings, "IMAGE_REGISTER", "light"):
        assert "light interface, teal accents" in prompt_builder.build_dashboard_image_prompt(spec)


# ── 4. Tool screens, hero assets, the AI module ───────────────────────────


def test_tool_screen_renders_the_selection_flow_not_a_dashboard():
    prompt = prompt_builder.build_dashboard_image_prompt(_tool_spec())
    assert "The selection flow this screen is built around" in prompt
    assert "1. Select Block" in prompt
    assert "Block A · Block B · Block C" in prompt
    assert "Selected: Block A" in prompt
    assert "View Floor Plan" in prompt
    # The dashboard furniture must be gone, not merely deprioritised.
    assert "Metric cards:\n" not in prompt
    assert "Main list panel:" not in prompt


def test_tool_screen_demotes_kpis_to_a_header_strip():
    prompt = prompt_builder.build_dashboard_image_prompt(_tool_spec())
    assert "Statistics for the page header" in prompt
    assert "3 Blocks" in prompt
    assert "NOT cards" in prompt


def test_tool_screen_moves_navigation_to_the_top():
    """A selection flow wants its full width; the reclaimed left edge is
    where the hero goes."""
    prompt = prompt_builder.build_dashboard_image_prompt(_tool_spec())
    assert "horizontal bar across the very top" in prompt
    assert "far left of the top navigation bar" in prompt
    assert "left sidebar" not in prompt


def test_dashboard_screens_keep_the_sidebar(dental_spec):
    """The tool path must not change screens that did not ask for it."""
    prompt = prompt_builder.build_dashboard_image_prompt(dental_spec)
    assert "left sidebar" in prompt
    assert "The selection flow this screen is built around" not in prompt


def test_tool_screens_can_be_switched_off_wholesale():
    with patch.object(prompt_builder.settings, "ENABLE_TOOL_SCREENS", False):
        prompt = prompt_builder.build_dashboard_image_prompt(_tool_spec())
    assert "The selection flow this screen is built around" not in prompt
    assert "left sidebar" in prompt


def test_hero_asset_is_asked_for_as_a_photograph_not_an_illustration():
    prompt = prompt_builder.build_dashboard_image_prompt(_tool_spec())
    assert "The visual centerpiece of this screen" in prompt
    assert "a 30-storey glass residential tower at dusk" in prompt
    assert "photoreal render" in prompt
    assert "It is an IMAGE, not an illustration" in prompt
    assert "no wireframe" in prompt


def test_hero_asset_absent_when_the_spec_has_none(dental_spec):
    """A spec stage that returns nothing usable must degrade to a thinner
    screen, never to an invented stock scene."""
    assert "The visual centerpiece of this screen" not in prompt_builder.build_dashboard_image_prompt(dental_spec)


def test_hero_asset_can_be_switched_off_wholesale():
    with patch.object(prompt_builder.settings, "ENABLE_HERO_ASSET", False):
        assert "The visual centerpiece of this screen" not in prompt_builder.build_dashboard_image_prompt(_tool_spec())


def test_ai_module_replaces_the_activity_log_rather_than_joining_it(dental_spec):
    """Two AI-activity modules in one prompt is the exact failure
    `_merged_ai_entries` exists to prevent — the model renders both, even
    when told not to. So the AI module must SUPPRESS the workstream log."""
    spec = dental_spec.model_copy(deep=True)
    spec.ai.headline = "Recommended: Tuesday"
    spec.ai.rationale = "Two cancellations, hygienist free"
    prompt = prompt_builder.build_dashboard_image_prompt(spec)
    # Marker chosen for what it pins, not for its wording: the AI block
    # exists and it declares the headline to be the module's top line.
    # Session 33 rewrote the opening sentence because the model was
    # drawing it as the panel's title (tests/test_end_to_end_defects.py).
    assert "Its topmost line is the headline below" in prompt
    assert "AI WORKSTREAM" not in prompt
    assert "Recommended: Tuesday" in prompt


def test_activity_log_survives_when_there_is_no_ai_module(dental_spec):
    assert "AI WORKSTREAM" in prompt_builder.build_dashboard_image_prompt(dental_spec)


def test_ai_module_can_be_switched_off_wholesale(dental_spec):
    spec = dental_spec.model_copy(deep=True)
    spec.ai.headline = "Recommended: Tuesday"
    with patch.object(prompt_builder.settings, "ENABLE_AI_LAYER", False):
        prompt = prompt_builder.build_dashboard_image_prompt(spec)
    assert "Its topmost line is the headline below" not in prompt
    assert "AI WORKSTREAM" in prompt


# ── 5. Provenance ─────────────────────────────────────────────────────────


def test_prompt_version_names_every_axis_that_changed_the_prompt():
    """A screenshot on disk is attributed months later from this string
    alone. An axis missing from it is an unattributable image."""
    version = prompt_builder.prompt_version("dashboard-image-v2", _tool_spec(), "operations-dashboard")
    assert version == "dashboard-image-v2-cinematic+tool+hero+ai"


def test_prompt_version_records_what_was_sent_not_what_was_configured(dental_spec):
    """dental_spec has no hero and no AI layer; the flags are on. Provenance
    must describe the prompt, not the settings."""
    version = prompt_builder.prompt_version("dashboard-image-v2", dental_spec, "operations-dashboard")
    assert version == "dashboard-image-v2-cinematic"


# ── 6. anchor_tool: a decision, not a default ─────────────────────────────


def test_anchor_tool_promotes_the_anchor_to_a_selection_flow(dental_spec):
    """Asked for as a per-screen `concept` field, the spec stage returned
    "dashboard" for 6 of 6 businesses across two prompt revisions — the
    archetype catalogue above it names a sequence of dashboards, so a
    per-screen field reads as "which kind of dashboard". Hoisting it to a
    required top-level key answered BEFORE the screens array took it to 6 of
    6 tool anchors. This pins the mapping that makes that possible."""
    from app.pipeline.ui_spec import _apply_anchor_tool

    specs = [dental_spec.model_copy(deep=True), dental_spec.model_copy(deep=True)]
    _apply_anchor_tool(specs, {
        "kind": "selector",
        "steps": [{"label": "Select Treatment", "options": ["Cleaning", "Crown"], "selected": "Cleaning"}],
        "detail": {"title": "9:00 AM Slot", "rows": [{"Patient": "Maya Sharma"}]},
        "primary_action": "Book Appointment",
    })
    assert specs[0].concept.is_tool
    assert specs[0].concept.primary_action == "Book Appointment"
    # Follow-ups inherit the anchor's look from a reference image; a second
    # selection flow would describe a different screen, not the same one.
    assert not specs[1].concept.is_tool


def test_anchor_tool_without_steps_stays_a_dashboard(dental_spec):
    """A kind with no steps is a claim, not a tool screen — and a SELECTION
    FLOW section with no stages in it is worse than none."""
    from app.pipeline.ui_spec import _apply_anchor_tool

    specs = [dental_spec.model_copy(deep=True)]
    _apply_anchor_tool(specs, {"kind": "selector", "steps": []})
    assert not specs[0].concept.is_tool


def test_anchor_tool_ignores_none_and_junk(dental_spec):
    from app.pipeline.ui_spec import _apply_anchor_tool

    step = [{"label": "Pick", "options": ["a"], "selected": "a"}]
    for payload in (None, {}, "selector", {"kind": "none", "steps": step}, {"kind": "dashboard", "steps": step}):
        specs = [dental_spec.model_copy(deep=True)]
        _apply_anchor_tool(specs, payload)
        assert not specs[0].concept.is_tool, f"junk accepted: {payload!r}"


def test_section_headings_are_marked_as_instructions_not_text(dental_spec):
    """The model renders ALL-CAPS prompt scaffolding as UI labels when it is
    not told otherwise: a retail anchor came back with a panel literally
    titled "RESULT PANEL", and an earlier corner-reserve instruction produced
    a screen with the word "Logo" drawn in the corner."""
    for prompt in (
        prompt_builder.build_dashboard_image_prompt(_tool_spec()),
        prompt_builder.build_continuation_prompt(dental_spec, "Dashboard"),
    ):
        assert "are instructions to you, not labels" in prompt
        assert "never draw a heading above an element" in prompt


def test_result_panel_heading_does_not_look_like_a_ui_label():
    """It leaked once. The panel already carries its own title from the spec."""
    prompt = prompt_builder.build_dashboard_image_prompt(_tool_spec())
    assert "RESULT PANEL" not in prompt
    assert "Block A · Level 18" in prompt
