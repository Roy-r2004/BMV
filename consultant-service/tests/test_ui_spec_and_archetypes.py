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
