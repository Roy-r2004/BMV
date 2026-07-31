"""The prop shapes fed to codegen must match the real component sources.

Doubles as a drift alarm: change a catalogue component's exported interface and
the assertions below fail with the old member names.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.prompts import PromptTemplate
from app.application import ui_catalogue
from app.application.ui_catalogue import (
    catalogue_prop_shape_block,
    compact_skeleton_contract,
    component_prop_shape,
    load_catalogue,
    load_ui_type_declarations,
    prop_shape_entries,
    ui_type_shape,
)
from app.application.preview_app.text_utils import _bounded_json
from app.core.config import settings
from app.infrastructure.templating.renderer import JinjaTemplateRenderer


TEMPLATES_DIR = REPO_ROOT / "backend" / "app" / "templates"
UI_DIR = settings.PREVIEW_TEMPLATE_DIR / "src" / "ui"
_CACHED = (
    load_ui_type_declarations,
    ui_type_shape,
    component_prop_shape,
    catalogue_prop_shape_block,
    load_catalogue,
)


def _clear_caches() -> None:
    for func in _CACHED:
        func.cache_clear()


def _declared_members(source_path: Path, type_name: str) -> list[str]:
    """Member names read straight out of the .tsx with an independent parser."""
    source = source_path.read_text(encoding="utf-8")
    start = source.index(f"export interface {type_name} ")
    body = source[source.index("{", start) + 1 : source.index("}", start)]
    return re.findall(r"^\s*'?([A-Za-z_$][\w$-]*)'?\??\s*:", body, re.MULTILINE)


def test_item_shapes_match_component_sources():
    assert ui_type_shape("CredentialStripItem")["members"] == {
        "title": "string",
        "detail": "string",
    }
    assert ui_type_shape("TestimonialRailItem")["members"] == {
        "quote": "string",
        "author": "string",
        "role": "string",
    }
    expected = {
        "CredentialStripItem": UI_DIR / "public" / "CredentialStrip.tsx",
        "TestimonialRailItem": UI_DIR / "public" / "TestimonialRail.tsx",
        "MarketingHeroProps": UI_DIR / "public" / "MarketingHero.tsx",
        "FeatureBentoItem": UI_DIR / "public" / "FeatureBento.tsx",
        "ButtonProps": UI_DIR / "core" / "Button.tsx",
        "ActivityFeedItem": UI_DIR / "ops" / "ActivityFeed.tsx",
    }
    for type_name, source_path in expected.items():
        shape = ui_type_shape(type_name)
        assert shape, type_name
        assert list(shape["members"]) == _declared_members(source_path, type_name), type_name


def test_component_prop_shape_resolves_one_hop_of_indirection():
    credential = component_prop_shape("CredentialStrip")
    assert credential["props"] == (
        "heading?: string; items: CredentialStripItem[]; className?: string"
    )
    assert credential["types"]["CredentialStripItem"] == "{ title: string; detail: string }"

    hero = component_prop_shape("MarketingHero")
    assert "imageSrc: string" in hero["props"]
    assert hero["types"]["MarketingCta"] == (
        "{ label: string; href: string; onClick?: () => void }"
    )

    assert "target" not in component_prop_shape("Button")["props"]
    assert "badge" not in component_prop_shape("MarketingHero")["props"]
    # The hero does take overlay children — a detail page composes a
    # "Back to the collection" chip into it — and the shape must say so.
    assert "children?: React.ReactNode" in hero["props"]
    assert "name" not in component_prop_shape("TestimonialRail")["types"]["TestimonialRailItem"]


def test_optionality_and_literal_unions_are_captured():
    testimonial = ui_type_shape("TestimonialRailItem")
    # All three are optional since the rail accepts the aliases its own callers
    # write (`brand.testimonials` carries `name`/`text`); a row with no quote is
    # dropped by the component rather than rendered blank.
    assert testimonial["optional"] == ("quote", "author", "role")
    assert component_prop_shape("TestimonialRail")["props"].endswith("className?: string")

    button = ui_type_shape("ButtonProps")
    assert button["members"]["type"] == "'button' | 'submit' | 'reset'"
    assert "type" in button["optional"]

    assert ui_type_shape("FeatureBentoVariant")["alias"] == "'bento' | 'grid' | 'alternating'"
    # The full union is parsed…
    assert ui_type_shape("PageHeaderAction")["members"]["variant"] == (
        "'primary' | 'secondary' | 'default' | 'outline' | 'ghost' | 'destructive'"
    )
    # …and the compact prompt line drops it rather than showing a clipped one, which
    # would read as the complete list of allowed values. `variant` widened to the
    # Button vocabulary when generated ops pages kept writing `variant: "outline"`
    # and earning a TS2322, so there is nothing left for the prompt to prevent.
    assert dict(prop_shape_entries("PageHeader"))["PageHeader.actions[]"] == (
        "label, href?, onClick?:fn, variant?"
    )


def test_every_catalogue_component_but_icons_resolves_a_shape():
    unresolved = [
        component["name"]
        for component in load_catalogue()["components"]
        if not component_prop_shape(component["name"])
    ]
    assert unresolved == ["UiIcon"]


def test_extractor_degrades_to_names_only_on_unparseable_sources():
    original = settings.PREVIEW_TEMPLATE_DIR
    with tempfile.TemporaryDirectory() as tmp:
        ui_dir = Path(tmp) / "src" / "ui"
        (ui_dir / "public").mkdir(parents=True)
        (ui_dir / "catalogue.json").write_text(
            (UI_DIR / "catalogue.json").read_text(encoding="utf-8"), encoding="utf-8"
        )
        (ui_dir / "public" / "CredentialStrip.tsx").write_text(
            "export interface CredentialStripProps { items: `unterminated\n", encoding="utf-8"
        )
        (ui_dir / "public" / "Broken.tsx").write_bytes(b"\xff\xfe export interface X {")
        try:
            settings.PREVIEW_TEMPLATE_DIR = Path(tmp)
            _clear_caches()
            assert component_prop_shape("CredentialStrip") is None
            assert catalogue_prop_shape_block() == ""
            contract = compact_skeleton_contract("public-home")
            assert "prop_shapes" not in contract
            assert [item["name"] for item in contract["components"]]
        finally:
            settings.PREVIEW_TEMPLATE_DIR = original
            _clear_caches()


def test_contract_carries_slot_component_shapes_within_the_caller_budget():
    starved: set[str] = set()
    for skeleton in load_catalogue()["skeletons"]:
        slots = [
            slot
            for slot in (
                *(skeleton.get("requiredSections") or []),
                *(skeleton.get("optionalSections") or []),
            )
            if slot != "shell"
        ]
        contract = compact_skeleton_contract(skeleton["id"], slots)
        # Callers bound this JSON at 5000 chars; overshooting replaces the whole
        # contract with a truncated preview.
        assert "truncated" not in _bounded_json(contract, 5000)[:32], skeleton["id"]
        shapes = contract.get("prop_shapes", {})
        for component in contract["slot_components"].values():
            for key, _ in prop_shape_entries(component):
                if key.endswith("[]") and key not in shapes:
                    starved.add(skeleton["id"])
    # These two skeletons list so many allowed components that the contract fills
    # the callers' 5000-char budget on its own. Raise that budget and this set
    # must shrink to empty.
    assert starved == {"public-catalog", "public-booking"}


def test_rendered_prompts_expose_item_member_names():
    renderer = JinjaTemplateRenderer(TEMPLATES_DIR)
    slots = ["hero", "features", "credentials", "testimonials", "cta", "footer"]
    contract_json = _bounded_json(compact_skeleton_contract("public-home", slots), 5000)

    slot_fill = renderer.render(
        PromptTemplate.PREVIEW_APP_SLOT_FILL,
        full_context="ctx",
        file_path="src/pages/HomePage.tsx",
        file_instructions="",
        page_plan_json="{}",
        app_spec_contract_json="{}",
        skeleton_id="public-home",
        skeleton_contract_json=contract_json,
        shell_component="PublicShell",
        scaffold_source="// scaffold",
        design_brief_block="",
    )
    for expected in (
        '"CredentialStrip.items[]":"title, detail"',
        '"TestimonialRail.items[]":"quote?, author?, role?"',
        "PROP CONTRACT",
        "never omit",
        "after:bg-blend-multiply",
    ):
        assert expected in slot_fill, expected

    mock_context = {
        "full_context": "ctx",
        "plan_json": "{}",
        "routes_json": "[]",
        "manifest_json": "{}",
        "images_json": "{}",
        "required_exports": "seed",
        "import_context": "",
        "current_content": "",
    }
    # codegen/mock.py does not pass the block yet: rendering must not raise on
    # the undefined variable (the environment uses StrictUndefined).
    without_shapes = renderer.render(PromptTemplate.PREVIEW_APP_MOCK_SYNTHESIZE, **mock_context)
    assert "CATALOGUE ITEM SHAPES" not in without_shapes

    mock_prompt = renderer.render(
        PromptTemplate.PREVIEW_APP_MOCK_SYNTHESIZE,
        catalogue_prop_shapes=catalogue_prop_shape_block(),
        **mock_context,
    )
    for expected in (
        "CredentialStrip.items[] = { title, detail }",
        "TestimonialRail.items[] = { quote?, author?, role? }",
        "`{ title, detail }` — NOT `{ label, value }`",
        "seed.features",
        "TS1117",
        "`hero`, `hero2`, `card1`, `card2`, `card3`, `ambient`",
    ):
        assert expected in mock_prompt, expected

    file_prompt = renderer.render(
        PromptTemplate.PREVIEW_APP_FILE,
        full_context="ctx",
        architect_json="{}",
        design_system_json="{}",
        manifest_json="{}",
        images_json="{}",
        file_path="src/pages/HomePage.tsx",
        file_kind="page",
        file_instructions="",
        page_plan_json="{}",
        app_spec_contract_json="{}",
        catalogue_page=True,
        skeleton_id="public-home",
        skeleton_contract_json=contract_json,
        shell_component="PublicShell",
        existing_files_summary="",
    )
    assert '"CredentialStrip.items[]":"title, detail"' in file_prompt
    assert "PROP CONTRACT" in file_prompt
    assert "LEGIBILITY" in file_prompt


def test_prop_shape_block_is_a_small_prompt_addition():
    block = catalogue_prop_shape_block()
    assert "CredentialStrip.items[] = { title, detail }" in block
    assert len(block) < 4000
    added = [
        len(json.dumps(compact_skeleton_contract(skeleton["id"]).get("prop_shapes", {})))
        for skeleton in load_catalogue()["skeletons"]
    ]
    assert max(added) < 1400
