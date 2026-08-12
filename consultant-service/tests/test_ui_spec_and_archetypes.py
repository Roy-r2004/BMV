import json

from app import archetypes
from app.ui_spec import UIDemoSpec


def test_ui_demo_spec_tolerates_partial_llm_output():
    spec = UIDemoSpec.model_validate(
        {
            "business": {"name": "Acme", "industry": "HVAC", "unexpected_key": "ignored"},
            "product": {"name": "Acme Ops"},
            "kpis": [{"label": "Jobs Today", "value": "12"}],
        }
    )
    assert spec.business.name == "Acme"
    assert spec.product.screen_type == "dashboard"
    assert spec.kpis[0].delta is None
    assert spec.chart is None
    assert spec.navigation == []


def test_ui_demo_spec_screen_slug_and_title():
    spec = UIDemoSpec.model_validate({"product": {"screen_type": "Schedule"}})
    assert spec.screen_slug == "schedule"
    assert spec.screen_title == "Schedule"


def test_archetype_selection_falls_back_on_unknown():
    aid, arch = archetypes.get_archetype("nonsense-from-llm")
    assert aid == archetypes.DEFAULT_ARCHETYPE
    assert arch["screens"]
    aid2, _ = archetypes.get_archetype(None)
    assert aid2 == archetypes.DEFAULT_ARCHETYPE


def test_every_archetype_defines_two_plus_screens_anchor_first():
    for aid, arch in archetypes.ARCHETYPES.items():
        assert len(arch["screens"]) >= 2, aid
        for screen in arch["screens"]:
            assert screen["screen_type"], aid
            assert screen["layout"], aid


def test_catalog_for_prompt_lists_all_archetypes():
    catalog = archetypes.catalog_for_prompt()
    for aid in archetypes.ARCHETYPES:
        assert aid in catalog


def test_spec_roundtrips_through_json():
    spec = UIDemoSpec.model_validate({"business": {"name": "Café Río"}})
    again = UIDemoSpec.model_validate(json.loads(spec.model_dump_json()))
    assert again.business.name == "Café Río"


# ── brand strings carry the exact name the gate demands (session 36) ─────
# Every recorded shipped text-truth failure was the ui_spec stage inventing
# a brand variant the gate then rejected: "by hartwell & grey" for
# "Hartwell & Grey LLP" (request 93), "northgate roastery" (95),
# "lumière studio os" (22). The deterministic half — restoring a truncated
# legal suffix — is pinned here; the paraphrase half is a template
# constraint measured by the gate itself.

from app.pipeline.ui_spec import _apply_brand_string_invariant, _widen_truncated_brand


def test_a_truncated_legal_suffix_is_widened_to_the_exact_name():
    assert _widen_truncated_brand(
        "LexStream by Hartwell & Grey", "Hartwell & Grey LLP"
    ) == "LexStream by Hartwell & Grey LLP"


def test_widening_is_the_only_rewrite_that_fires():
    # A paraphrase is not a truncation — rewriting it would need a rule
    # loose enough to also mangle legitimate coinages, so it must pass
    # through untouched (the template constraint owns this class).
    assert _widen_truncated_brand(
        "Northgate Roastery", "Northgate Coffee Roasters") == "Northgate Roastery"
    # A real product coinage sharing the brand's first token stays intact.
    assert _widen_truncated_brand(
        "Northgate RoasterFlow AI", "Northgate Coffee Roasters") == "Northgate RoasterFlow AI"
    # Already exact: untouched.
    assert _widen_truncated_brand(
        "LexStream by Hartwell & Grey LLP", "Hartwell & Grey LLP"
    ) == "LexStream by Hartwell & Grey LLP"
    # Brand without a legal suffix: nothing to widen.
    assert _widen_truncated_brand(
        "Lumière Studio OS", "Lumière Hair Studio") == "Lumière Studio OS"


def test_the_invariant_reaches_both_renderable_brand_strings():
    spec = UIDemoSpec.model_validate({
        "business": {"name": "Hartwell & Grey LLP", "industry": "Law"},
        "product": {"name": "LexStream by Hartwell & Grey"},
        "hero": {"caption": "Hartwell & Grey"},
    })
    _apply_brand_string_invariant([spec])
    assert spec.product.name == "LexStream by Hartwell & Grey LLP"
    assert spec.hero.caption == "Hartwell & Grey LLP"


# ── the customer's navigation wins (session 38) ──────────────────────────
# Request 107 asked for a four-item header and got five. The template's
# "5-7 short one-word items" rule padded the list with "Settings", and the
# text-truth gate passed the screen 7/7 because the gate's ground truth IS
# the padded spec. The extraction below is the deterministic half of the
# fix; the template instruction is the other half, and it is what catches
# the phrasings this regex is deliberately too careful to read.

from app.pipeline.ui_spec import (
    _apply_explicit_navigation,
    _fallback_specs,
    extract_explicit_navigation,
)

# Request 107's intake, verbatim. Typos included on purpose: real intakes
# look like this, and a fixture cleaned up into good English would pin a
# sentence no customer ever sent us.
REQUEST_107_INTAKE = (
    "I wanna showcase my paitings, with a dashboard that contains home, gallery, about, contact"
)


def test_request_107s_own_sentence_yields_its_four_items():
    assert extract_explicit_navigation(REQUEST_107_INTAKE) == ["Home", "Gallery", "About", "Contact"]


def test_the_customers_wording_survives_except_for_case():
    assert extract_explicit_navigation("a header with Home, My Work, About Us and Contact") == [
        "Home", "My Work", "About Us", "Contact",
    ]
    # An item the customer capitalised themselves is left exactly as typed.
    assert extract_explicit_navigation("nav: home, FAQ, pricing, contact") == [
        "Home", "FAQ", "Pricing", "Contact",
    ]
    # Order is the customer's, and a repeat is not a fifth item.
    assert extract_explicit_navigation("menu: shop, about, shop, contact") == [
        "Shop", "About", "Contact",
    ]


def test_it_reads_a_list_introduced_at_arms_length():
    assert extract_explicit_navigation(
        "I'd like a site that contains the following pages: home, studio, prints, contact."
    ) == ["Home", "Studio", "Prints", "Contact"]


def test_it_stops_at_the_end_of_the_list_and_at_the_end_of_the_sentence():
    assert extract_explicit_navigation(
        "with tabs home, gallery, about and I want it to feel calm"
    ) == ["Home", "Gallery", "About"]
    assert extract_explicit_navigation(
        "menu: home, gallery, about. We also sell prints, canvases, frames"
    ) == ["Home", "Gallery", "About"]


def test_ordinary_business_prose_is_not_a_navigation_list():
    """Every one of these is a real golden-brief intake sentence or close to
    it. A false positive here would hard-override a whole request's
    navigation with the customer's SERVICES."""
    for prose in (
        "Family dental clinic with 3 dentists and 2 hygienists. Cleanings, crowns, "
        "implants, Invisalign. Struggles with no-shows and slow recall of lapsed patients.",
        "Residential HVAC company with 6 technicians. Installs, repairs, seasonal maintenance plans.",
        "Boutique family-law firm, 4 attorneys. Consultations, mediation, litigation.",
        "Specialty coffee roastery selling beans wholesale and direct.",
        "I want an app that contains everything I need to run my studio",
    ):
        assert extract_explicit_navigation(prose) is None, prose


def test_two_items_is_prose_and_a_ninth_item_is_a_promise_we_cannot_keep():
    # Under three, a comma run is far more often prose than a header — and
    # early sessions found a sparse nav renders as an empty-looking bar.
    assert extract_explicit_navigation("a menu with home and contact") is None
    # Over eight, prompt_builder and text_truth both already slice, so
    # honouring a ninth would be a promise neither could keep.
    long_list = "nav: one, two, three, four, five, six, seven, eight, nine"
    assert extract_explicit_navigation(long_list) == [
        "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
    ]


def test_empty_and_missing_intake_fields_are_simply_no_list():
    assert extract_explicit_navigation(None, "", "   ") is None
    assert extract_explicit_navigation() is None


def test_the_list_is_applied_to_every_screen_over_whatever_the_model_returned():
    specs = [
        UIDemoSpec.model_validate({"navigation": ["Home", "Gallery", "About", "Contact", "Settings"]}),
        UIDemoSpec.model_validate({"navigation": ["Dashboard", "Reports"]}),
    ]
    _apply_explicit_navigation(specs, ["Home", "Gallery", "About", "Contact"])
    for spec in specs:
        assert spec.navigation == ["Home", "Gallery", "About", "Contact"]


def test_no_explicit_list_leaves_the_models_navigation_untouched():
    spec = UIDemoSpec.model_validate({"navigation": ["Dashboard", "Schedule", "Settings"]})
    _apply_explicit_navigation([spec], None)
    assert spec.navigation == ["Dashboard", "Schedule", "Settings"]


def test_the_honoured_list_becomes_exactly_what_the_text_truth_gate_checks():
    """The point of doing this in code rather than only in the prompt: the
    gate's ground truth is spec.navigation, so an item the customer named
    and the image dropped is now a measured failure — and the invented item
    the gate used to check is gone."""
    from app.pipeline import text_truth

    spec = UIDemoSpec.model_validate({
        "business": {"name": "Jeanne Art"},
        "product": {"name": "Jeanne Artistry Gateway"},
        "navigation": ["Home", "Gallery", "About", "Contact", "Settings"],
    })
    _apply_explicit_navigation([spec], extract_explicit_navigation(REQUEST_107_INTAKE))
    assert text_truth.required_strings(spec)["navigation"] == ["Home", "Gallery", "About", "Contact"]

    rendered_without_contact = ["Jeanne Artistry Gateway", "Home", "Gallery", "About"]
    result = text_truth.check(spec, rendered_without_contact)
    assert result["passed"] is False
    assert [f["expected"] for f in result["failures"]] == ["Contact"]


def test_the_fallback_specs_honour_the_customers_list_too():
    """The fallback runs when the MODEL failed, which is no reason to stop
    honouring something read out of the brief in code."""
    class _Req:
        business_name = "Jeanne Art"
        industry = "Art"

    nav = ["Home", "Gallery", "About", "Contact"]
    _, specs = _fallback_specs(_Req(), {}, 3, nav)
    assert specs and all(spec.navigation == nav for spec in specs)
    _, generic = _fallback_specs(_Req(), {}, 3, None)
    assert generic[0].navigation == ["Dashboard", "Schedule", "Customers", "Billing", "Analytics", "Settings"]


# ── the assistant console (session 38) ───────────────────────────────────
# Measured live before it was built (docs/evidence/session38/
# classification-probe.json, request 110): "I want an AI chatbot for my
# business that answers customer questions and books appointments" landed
# on operations-dashboard with an anchor of "Select Service" and the word
# "Chatbot" as the fourth item in the navigation. The product the customer
# came to see was rendered as a menu entry. This is the shape that was
# missing — and the pairing rule below is what stops it becoming the shape
# every brief reaches for, since nearly all of them are sold an AI
# front-desk in their consulting summary.

from app.archetypes import ASSISTANT_ARCHETYPE
from app.pipeline.ui_spec import _apply_anchor_tool

CONVERSATION = {
    "kind": "assistant",
    "turns": [
        {"speaker": "customer", "text": "Do you have anything Thursday afternoon?"},
        {"speaker": "assistant", "text": "3:15pm with Elara, or 4:00pm with Lena."},
        {"speaker": "customer", "text": "3:15 works."},
        {"speaker": "assistant", "text": "Booked. Balayage with Elara, Thursday 3:15pm."},
    ],
    "primary_action": "Reply to Sarah",
}


def test_the_console_is_in_the_catalogue_and_leads_with_the_conversation():
    arch = archetypes.ARCHETYPES[ASSISTANT_ARCHETYPE]
    assert [s["screen_type"] for s in arch["screens"]] == ["conversations", "analytics", "knowledge"]
    # The anchor is the conversation, and it carries no chart — the volume
    # story belongs on the analytics screen.
    assert arch["screens"][0]["chart"] is None
    assert ASSISTANT_ARCHETYPE in archetypes.catalog_for_prompt()


def test_a_conversation_anchor_lands_on_the_console():
    specs = [UIDemoSpec.model_validate({"product": {"screen_type": "conversations"}})]
    _apply_anchor_tool(specs, CONVERSATION, ASSISTANT_ARCHETYPE)
    assert specs[0].concept.is_conversation
    assert len(specs[0].concept.turns) == 4
    assert specs[0].concept.turns[1].speaker == "assistant"


def test_a_conversation_anchor_anywhere_else_degrades_to_a_dashboard():
    """Every brief this pipeline sees is sold an AI front-desk, so
    "assistant" is a kind any of them could reach for. A salon whose anchor
    became a chat window instead of its booking flow would be a worse demo,
    not a more honest one — so the pairing is enforced here rather than
    trusted to the prompt."""
    for archetype_id in ("operations-dashboard", "crm-dashboard", "analytics-dashboard", ""):
        specs = [UIDemoSpec.model_validate({})]
        _apply_anchor_tool(specs, CONVERSATION, archetype_id)
        assert not specs[0].concept.is_conversation, archetype_id
        assert specs[0].concept.kind == "dashboard", archetype_id


def test_a_conversation_too_short_to_be_one_degrades_to_a_dashboard():
    """One bubble is a claim, not a conversation — and an empty thread
    would render as a blank panel, which is on the inspector's list."""
    for turns in ([], [{"speaker": "customer", "text": "hello"}], [{"speaker": "customer", "text": "  "}]):
        specs = [UIDemoSpec.model_validate({})]
        _apply_anchor_tool(specs, {**CONVERSATION, "turns": turns}, ASSISTANT_ARCHETYPE)
        assert not specs[0].concept.is_conversation


def test_a_conversation_is_not_a_tool_screen():
    """They are different layouts with different prompt blocks. Sharing the
    tool flag would send a thread through _steps_block, which is exactly
    how it would have rendered before it had a shape of its own."""
    from app.ui_spec import TOOL_CONCEPT_KINDS

    assert "assistant" not in TOOL_CONCEPT_KINDS
    specs = [UIDemoSpec.model_validate({})]
    _apply_anchor_tool(specs, CONVERSATION, ASSISTANT_ARCHETYPE)
    assert not specs[0].concept.is_tool


def test_a_selection_flow_still_works_exactly_as_before():
    """The whole point of the pairing rule is that nothing else moved."""
    specs = [UIDemoSpec.model_validate({})]
    _apply_anchor_tool(
        specs,
        {"kind": "selector", "steps": [{"label": "Select Stylist", "options": ["Elara"], "selected": "Elara"}]},
        "operations-dashboard",
    )
    assert specs[0].concept.is_tool
    assert specs[0].concept.kind == "selector"


# ── a bad chart costs its screen a chart, not the request its spec ───────
# Found live on the session-38 investment classification probe (request
# 113): ui_spec returned a multi-series chart whose seventh value was
# {"series1": 1.4, "series2": 6.9}. list[float] rejected it, the whole
# screens array is validated in one pass, and build_ui_specs fell back to
# the generic deterministic specs — turning a personalised demo into one
# specific to nobody, for the entire request, over one data point.


def test_a_multi_series_chart_no_longer_takes_the_whole_spec_down():
    spec = UIDemoSpec.model_validate({
        "business": {"name": "Ridgeline Capital"},
        "product": {"name": "RidgeVault"},
        "kpis": [{"label": "AUM", "value": "$48M"}],
        "chart": {
            "title": "Performance",
            "labels": ["Jan", "Feb", "Mar"],
            "values": [1.2, 3.4, {"series1": 1.4, "series2": 6.9}],
            "metric_label": "return %",
        },
    })
    # The business data survived — that is the whole point.
    assert spec.business.name == "Ridgeline Capital"
    assert spec.kpis[0].label == "AUM"
    # ...and the series it could not plot is gone rather than half-plotted.
    assert spec.chart.values == []
    assert spec.chart.title == "Performance"


def test_a_plottable_series_is_untouched_including_numeric_strings():
    chart = UIDemoSpec.model_validate(
        {"chart": {"labels": ["Mon"], "values": [22, 28.5, "30"]}}
    ).chart
    assert chart.values == [22.0, 28.5, 30.0]


def test_a_series_that_cannot_be_plotted_asks_for_no_chart_at_all():
    """Labels with no numbers would send the image model a chart section
    with nothing to draw, which is how a screen invents its own data."""
    from app.pipeline import prompt_builder

    spec = UIDemoSpec.model_validate({
        "business": {"name": "Ridgeline Capital"},
        "product": {"name": "RidgeVault"},
        "chart": {"title": "Performance", "labels": ["Jan", "Feb"], "values": [None, None]},
    })
    assert spec.chart.values == []
    assert "Performance" not in prompt_builder.build_dashboard_image_prompt(spec)
