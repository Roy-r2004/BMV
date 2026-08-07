"""The two haiku-starved planning writers must ask TEXT_MODEL first.

Session 18, both baseline runs: `design_manifest` burned exactly its 1,500
completion tokens with 0 output chars (finish_reason=length) on every run, and
`plan_validation` did the same at 14,000 until gemini-3's tighter plans made it
fit — reasoning-burn, 100% reproducible, ~12-95 s + real cost wasted per run
before a fallback did the work. ARCHITECT_MODEL stays haiku for the architect
call itself; these two writers route to TEXT_MODEL, with the architect slot as
plan_validation's fallback only.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.services.page_experience import (
    build_design_manifest,
    validate_and_expand_plan,
)
from app.core.config import settings
from app.infrastructure.templating.renderer import JinjaTemplateRenderer

TEMPLATES_DIR = REPO_ROOT / "backend" / "app" / "templates"

_PLAN = {
    "concept_name": "Test",
    "design_system": {"primary_color": "#123456"},
    "roles": [{"id": "customer", "pages": []}],
}

_VALID_PLAN_JSON = (
    '{"concept_name": "Test", "design_system": {"primary_color": "#123456"},'
    ' "roles": [{"id": "customer", "pages": []}]}'
)


class _ModelRecorder:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.models: list[str] = []

    def ask_chat(self, model, _messages, **_kwargs):
        self.models.append(model)
        return self.responses.pop(0) if self.responses else ""

    def ask_vision(self, model, prompt, _image_path):  # pragma: no cover
        self.models.append(model)
        return ""


def _req() -> types.SimpleNamespace:
    return types.SimpleNamespace(preview_features=None, mvp_blueprint="")


def test_design_manifest_asks_text_model_not_architect() -> None:
    ai = _ModelRecorder(['{"brand_name": "Osteria", "accent": "#123456"}'])
    manifest = build_design_manifest(
        "ctx", _PLAN, ai, JinjaTemplateRenderer(TEMPLATES_DIR)
    )
    assert ai.models == [settings.TEXT_MODEL]
    assert manifest["brand_name"] == "Osteria"  # the AI answer, not the fallback dict


def test_plan_validation_asks_text_model_first() -> None:
    ai = _ModelRecorder([_VALID_PLAN_JSON])
    result = validate_and_expand_plan(
        _req(), dict(_PLAN), ai, JinjaTemplateRenderer(TEMPLATES_DIR)
    )
    assert ai.models == [settings.TEXT_MODEL]
    assert result.get("roles")


def test_plan_validation_falls_back_to_architect_model() -> None:
    ai = _ModelRecorder(["not json at all", _VALID_PLAN_JSON])
    validate_and_expand_plan(
        _req(), dict(_PLAN), ai, JinjaTemplateRenderer(TEMPLATES_DIR)
    )
    assert ai.models == [settings.TEXT_MODEL, settings.ARCHITECT_MODEL]
