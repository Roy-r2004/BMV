"""The slot_fill prompt must teach the listing-face contract it is graded on.

Session 18: "catalogue-contract: missing directory face component:PageHeader,
missing BRAND_MANIFEST services binding" caused 5 of 6 contract rejections and
request 107's retry repeated it byte-identically — the prompt never named the
components or the binding. These tests drive the real generate path with a
fake provider and read the prompt off it (variable-audit style): the wording
must reach the model for the exact scaffolds the validator grades as faces,
and must stay out of slot-composed pages where it would be wrong.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app import codegen
from app.application.preview_app.catalogue_contract import (
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.catalogue_contract.face_prompt import (
    listing_face_contract_block,
)
from app.application.preview_app.catalogue_contract.validate import (
    _DIRECTORY_FACE_MARKER,
    _DIRECTORY_FACE_REQUIRED,
    _SCHEDULE_FACE_MARKER,
    _SCHEDULE_FACE_REQUIRED,
)
from app.application.preview_app.codegen.generate import (
    CONTRACT_REJECTION,
    _slot_fill_retry_prompt,
)
from app.infrastructure.templating.renderer import JinjaTemplateRenderer

TEMPLATES_DIR = REPO_ROOT / "backend" / "app" / "templates"

MENU_PAGE = "src/pages/MenuPage.tsx"
CLASSES_PAGE = "src/pages/ClassesPage.tsx"
HOME_PAGE = "src/pages/HomePage.tsx"


class _PromptRecorder:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def ask_chat(self, _model, messages, **_kwargs):
        self.prompts.append(messages[-1]["content"])
        return ""  # empty fill: scaffold ships, no retry loop

    def ask_vision(self, _model, prompt, _image_path):  # pragma: no cover
        self.prompts.append(prompt)
        return ""


def _menu_route() -> dict:
    # Request 107's rejection class: a catalogue listing (public-catalog, no
    # param) — `minimal_catalogue_page_scaffold` gives it the directory face.
    return {
        "path": "/menu",
        "page_id": "menu",
        "role_id": "customer",
        "component_file": MENU_PAGE,
        "surface": "public",
        "skeleton_id": "public-catalog",
        "title": "Menu",
    }


def _classes_route() -> dict:
    return {
        "path": "/classes",
        "page_id": "classes",
        "role_id": "customer",
        "component_file": CLASSES_PAGE,
        "surface": "public",
        "skeleton_id": "public-service",
        "title": "Classes",
    }


def _home_route() -> dict:
    return {
        "path": "/",
        "page_id": "home",
        "role_id": "customer",
        "component_file": HOME_PAGE,
        "surface": "public",
        "skeleton_id": "public-home",
        "section_slots": ["hero", "features", "cta", "footer"],
        "title": "Home",
    }


def _generate(route: dict, page: str) -> _PromptRecorder:
    ai = _PromptRecorder()
    with tempfile.TemporaryDirectory() as tmp:
        codegen.generate_file(
            Path(tmp),
            {"path": page, "kind": "page", "instructions": "fill"},
            "business context",
            {"routes": [route]},
            {"roles": []},
            {},
            {},
            ai,
            JinjaTemplateRenderer(TEMPLATES_DIR),
        )
    return ai


def test_directory_face_prompt_names_the_graded_contract() -> None:
    scaffold = minimal_catalogue_page_scaffold(MENU_PAGE, _menu_route(), brand_name="Osteria")
    assert _DIRECTORY_FACE_MARKER in scaffold  # the fixture reaches the face branch

    ai = _generate(_menu_route(), MENU_PAGE)
    assert ai.prompts, "slot_fill made no call"
    prompt = ai.prompts[0]
    assert "LOCKED LISTING FACE" in prompt
    # The component names all appear in the embedded scaffold source too, so
    # asserting them one by one would pass with the block's list gutted — the
    # first sweep proved it. Assert the block's own joined requirements line.
    assert ", ".join(_DIRECTORY_FACE_REQUIRED) in prompt
    assert "BRAND_MANIFEST" in prompt
    assert "missing directory face component:PageHeader" in prompt
    assert "no `slots` object" in prompt


def test_schedule_face_prompt_names_its_components() -> None:
    scaffold = minimal_catalogue_page_scaffold(
        CLASSES_PAGE, _classes_route(), brand_name="Studio"
    )
    assert _SCHEDULE_FACE_MARKER in scaffold

    ai = _generate(_classes_route(), CLASSES_PAGE)
    assert ai.prompts, "slot_fill made no call"
    prompt = ai.prompts[0]
    assert "LOCKED LISTING FACE" in prompt
    assert ", ".join(_SCHEDULE_FACE_REQUIRED) in prompt
    assert "BRAND_MANIFEST.services" in prompt


def test_slot_composed_page_gets_no_face_block() -> None:
    scaffold = minimal_catalogue_page_scaffold(HOME_PAGE, _home_route(), brand_name="Osteria")
    assert "SkeletonComposer" in scaffold  # composed page, not a face
    assert listing_face_contract_block(scaffold) == ""

    ai = _generate(_home_route(), HOME_PAGE)
    assert ai.prompts, "slot_fill made no call"
    assert "LOCKED LISTING FACE" not in ai.prompts[0]


def test_contract_retry_translates_the_validator_vocabulary() -> None:
    retry = _slot_fill_retry_prompt(
        "BASE",
        reason=CONTRACT_REJECTION,
        detail="missing directory face component:PageHeader",
    )
    assert "BRAND_MANIFEST" in retry
    assert "restore" in retry.lower()
