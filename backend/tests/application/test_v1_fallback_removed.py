"""The v1 role-pages path is gone, and failure is honest.

Session 17: the legacy HTML fallback (`role_pages` + `page_qa`) fired exactly
once in the telemetry window — request 59, 2026-07-31 — spent eight gpt-4o
calls, and still left the request `failed` with no pages stored. The owner
ruled it out: no lesser mode below the preview app. A generation that fails
twice must raise so the background runner marks the request `failed` and the
customer keeps the retry button, instead of emitting `done` over nothing.

Mutation driver: scripts/cli/mutate_v1_removal.py.
"""
from __future__ import annotations

import importlib.util

import pytest

import app.application.pipelines.orchestrator as orch
import app.application.services.request_deadline as rd


DELETED_MODULES = (
    "app.application.pipelines.role_pages",
    "app.application.services.page_qa",
    "app.application.services.page_bundle",
    "app.application.services.page_inject",
)


def test_the_v1_modules_routes_and_prompts_are_gone() -> None:
    for module in DELETED_MODULES:
        assert importlib.util.find_spec(module) is None, (
            f"{module} is back — the v1 role-pages path was removed by owner ruling"
        )

    from app.application.prompts import PromptTemplate

    for template in ("HTML_PAGE", "PAGE_QA", "PAGE_FIX"):
        assert not hasattr(PromptTemplate, template), (
            f"PromptTemplate.{template} is back without a caller"
        )

    from app.api.v1.routers.requests import router

    legacy = [r.path for r in router.routes if r.path.endswith("/generate-pages")]
    assert not legacy, f"the legacy generate-pages endpoint is back: {legacy}"


class _FakeRequest:
    id = 424242
    business_name = "Jeanne Kassab Art"
    concept_name = "Atelier"
    generation_cancel = False
    reference_url = None
    reference_metadata = None
    reference_file_path = None
    screenshot_analysis = None
    generated_pages = None
    visual_demo_json = None
    visual_demo_generated_at = None


class _FakeDB:
    def commit(self) -> None:  # pragma: no cover - bookkeeping only
        pass


def _pipeline_with_all_stages_stubbed(monkeypatch, boom_counter: list[int]):
    """A `GenerationPipeline` whose every stage is inert except codegen, which
    always raises. What is under test is only the failure path after it."""

    pipeline = orch.GenerationPipeline.__new__(orch.GenerationPipeline)
    pipeline.ai_provider = None
    pipeline.template_renderer = None
    from app.infrastructure.logging import get_logger

    pipeline.log = get_logger(orch.GenerationPipeline)

    req = _FakeRequest()
    monkeypatch.setattr(orch, "get_request", lambda _db, _rid: req)
    monkeypatch.setattr(orch, "_emit", lambda *a, **k: None)
    monkeypatch.setattr(orch, "app_spec_mode", lambda: "off")
    monkeypatch.setattr(
        orch.blueprint, "generate_mvp_blueprint", lambda *a, **k: None
    )
    monkeypatch.setattr(
        orch.visual_demo, "generate_visual_demo", lambda *a, **k: None
    )
    monkeypatch.setattr(rd, "publish_degradations", lambda _db, _rid: [])

    def _boom(*_a, **_k):
        boom_counter.append(1)
        raise RuntimeError("preview generation failed")

    monkeypatch.setattr(orch, "generate_preview_app", _boom)
    return pipeline


def test_a_failure_with_no_retry_runway_raises_instead_of_degrading(
    monkeypatch,
) -> None:
    calls: list[int] = []
    pipeline = _pipeline_with_all_stages_stubbed(monkeypatch, calls)
    monkeypatch.setattr(rd, "has_retry_runway", lambda: False)

    with pytest.raises(RuntimeError, match="preview generation failed"):
        pipeline.run(_FakeDB(), _FakeRequest.id)

    assert len(calls) == 1, "no runway means no second attempt — and no lesser mode"


def test_a_twice_failed_generation_raises_instead_of_degrading(monkeypatch) -> None:
    calls: list[int] = []
    pipeline = _pipeline_with_all_stages_stubbed(monkeypatch, calls)
    monkeypatch.setattr(rd, "has_retry_runway", lambda: True)

    with pytest.raises(RuntimeError, match="preview generation failed"):
        pipeline.run(_FakeDB(), _FakeRequest.id)

    assert len(calls) == 2, (
        "the single retry stays; what is gone is the role-pages parachute after it"
    )
