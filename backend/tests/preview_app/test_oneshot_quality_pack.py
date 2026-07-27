"""One-shot quality pack: utility compose + recipe pick + mock floor + critics."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.application.preview_app.codegen.generate import generate_file
from app.application.preview_app.design_recipes import pick_recipe_id
from app.application.preview_app.safety.mock_data import assert_brand_content_floor
from app.application.preview_app.utility_compositor import should_compose_utility_page
from app.infrastructure.templating.renderer import JinjaTemplateRenderer


class _JsonAI:
    """Returns utility content JSON, then ignores further calls."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def ask_chat(self, _model, messages, **_kwargs):
        self.prompts.append(messages[0]["content"])
        return json.dumps(self.payload)


def test_should_compose_utility_even_with_appspec_and_wrong_skeleton() -> None:
    route = {
        "path": "/waitlist-confirmation",
        "title": "Waitlist Confirmed",
        "skeleton_id": "public-service",  # AppSpec / architect mistake
        "page_type": "confirmation",
    }
    assert should_compose_utility_page(route, "public-service", {"app_spec_contract": {"page": {"id": "P1"}}})
    assert should_compose_utility_page(
        {"path": "/cart", "skeleton_id": "public-utility"},
        "public-utility",
        {"app_spec_contract": {"page": {"id": "P-CART"}}},
    )


def test_generate_file_composes_utility_when_appspec_contract_present() -> None:
    renderer = JinjaTemplateRenderer()
    file_path = "src/pages/WaitlistConfirmationPage.tsx"
    architect = {
        "routes": [
            {
                "path": "/waitlist-confirmation",
                "title": "Waitlist Confirmed",
                "skeleton_id": "public-utility",
                "component_file": file_path,
                "section_slots": ["header", "workspace", "summary", "footer"],
                "app_spec_page_id": "PAGE-WAITLIST",
                "action_ids": ["ACTION-DONE"],
                "evidence_ids": ["EV-CONFIRM"],
            }
        ],
        "files_to_generate": [{"path": file_path, "kind": "page", "instructions": "confirm"}],
    }
    plan = {
        "pages": [
            {
                "path": "/waitlist-confirmation",
                "title": "Waitlist Confirmed",
                "component_file": file_path,
                "skeleton_id": "public-utility",
                "app_spec_contract": {
                    "page": {"id": "PAGE-WAITLIST"},
                    "actions": [{"id": "ACTION-DONE"}],
                    "evidence": [{"id": "EV-CONFIRM"}],
                },
            }
        ]
    }
    ai = _JsonAI(
        {
            "header": {"eyebrow": "Confirmed", "title": "You're on the list", "subtitle": "We'll email you."},
            "workspace": {"kind": "confirmation", "headline": "You're on the Waitlist", "body": "See you soon."},
            "summary": {"title": "Next", "rows": [{"label": "Status", "value": "Joined"}]},
        }
    )
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        (workspace / "src" / "pages").mkdir(parents=True)
        generated = generate_file(
            workspace,
            {"path": file_path, "kind": "page", "instructions": "confirm"},
            "Clay & Kiln pottery studio waitlist",
            architect,
            plan,
            {"brand": {"name": "Clay & Kiln"}},
            {},
            ai,
            renderer,
        )
    assert "ConfirmStage" in generated
    assert "composed confirmation page" in generated or "composed public-utility page" in generated
    assert "data-appspec-page" in generated
    assert "PAGE-WAITLIST" in generated
    # Must not fall through to freeform / scaffold-first marketing shell.
    assert "MarketingHero" not in generated


def test_pottery_keywords_pick_craft_recipe() -> None:
    assert (
        pick_recipe_id(
            industry="pottery studio",
            business_description="Clay wheel throwing kiln firings handmade ceramics",
            concept_name="Clay & Kiln Studio",
        )
        == "craft"
    )


def test_art_gallery_does_not_pick_ledger_ops_recipe() -> None:
    """Short tokens like ``ar`` must not match inside ``art`` / ``gallery``."""
    recipe = pick_recipe_id(
        industry="Fine art gallery · original oil paintings · artist portfolio",
        business_description=(
            "Personal fine art gallery for original paintings — abstract landscapes "
            "and layered oils. Living gallery of latest works — not a booking SaaS "
            "or ops dashboard."
        ),
        concept_name="Jeanne Kassab Art",
        seed=19,
    )
    assert recipe not in {"dense-ops-ledger", "dense-ops", "dense-ops-floor"}
    assert recipe in {"editorial", "craft", "warm-service", "bold-retail", "nocturne"}


def test_brand_content_floor_repairs_empty_manifest_services() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        mock = workspace / "src" / "data" / "mock.ts"
        mock.parent.mkdir(parents=True)
        mock.write_text(
            'export const BRAND_MANIFEST = {\n'
            '  brand_name: "Clay",\n'
            "  services: [],\n"
            "  products: [],\n"
            "};\n"
            "export const classes = [];\n",
            encoding="utf-8",
        )
        fixed = assert_brand_content_floor(workspace, "Clay")
        assert fixed
        text = mock.read_text(encoding="utf-8")
        assert "services: []" not in text.replace(" ", "")
        assert "Wheel" in text or "Studio" in text or "Class" in text


def test_prod_quality_defaults_keep_critics_on() -> None:
    """Settings defaults (no env) must keep design + visual critics enabled."""
    import os

    from app.core import config as config_mod

    keys = (
        "PREVIEW_SKIP_CRITIC",
        "PREVIEW_SKIP_VISUAL_CRITIC",
        "PREVIEW_SCAFFOLD_FIRST",
    )
    saved = {k: os.environ.pop(k) for k in keys if k in os.environ}
    try:
        fresh = config_mod.Settings()
        assert fresh.PREVIEW_SKIP_CRITIC is False
        assert fresh.PREVIEW_SKIP_VISUAL_CRITIC is False
        assert fresh.PREVIEW_SCAFFOLD_FIRST is True
    finally:
        os.environ.update(saved)
