"""Phase 0 tests for the default-off preview-generator boundary."""
from __future__ import annotations

import json
from types import SimpleNamespace

from app.application.preview_app.pipeline import orchestrator
from app.application.preview_app.pipeline.versioning import (
    GENERATOR_V1,
    GENERATOR_V2,
    GeneratorSelection,
    apply_generator_version_marker,
    dispatch_preview_generator,
    select_preview_generator,
)
from app.core.config import Settings


class _FakeRequestQuery:
    def __init__(self, request: object):
        self.request = request

    def query(self, _model):
        return self

    def filter(self, _expression):
        return self

    def first(self):
        return self.request


def _request(generated_pages=None):
    return SimpleNamespace(
        id=41,
        mvp_blueprint="frozen blueprint",
        generated_pages=generated_pages,
    )


def test_preview_generator_v2_defaults_false(monkeypatch) -> None:
    monkeypatch.delenv("PREVIEW_GENERATOR_V2", raising=False)
    assert Settings().PREVIEW_GENERATOR_V2 is False


def test_false_flag_dispatches_the_unchanged_v1_path(monkeypatch) -> None:
    request = _request()
    db = _FakeRequestQuery(request)
    expected = {"preview_app": {"status": "ready"}, "experience_plan": {"id": "same"}}
    calls: list[tuple[str, str]] = []

    def run_v1(*_args, **kwargs):
        calls.append(("v1", kwargs["generator_version"]))
        return expected

    def run_v2(*_args, **_kwargs):
        calls.append(("v2", "v2"))
        return {"unexpected": True}

    monkeypatch.setattr(orchestrator.settings, "PREVIEW_GENERATOR_V2", False)
    monkeypatch.setattr(orchestrator, "_run_v1_pipeline", run_v1)
    monkeypatch.setattr(orchestrator, "_run_v2_boundary", run_v2)

    actual = orchestrator._generate_preview_app_inner(db, 41, object(), object())

    assert actual is expected
    assert calls == [("v1", GENERATOR_V1)]


def test_enabling_v2_does_not_move_an_existing_unmarked_preview(monkeypatch) -> None:
    existing = {
        "preview_app": {"status": "ready", "routes": [{"path": "/"}]},
        "experience_plan": {"recipe_id": "legacy"},
    }
    request = _request(json.dumps(existing))
    db = _FakeRequestQuery(request)
    calls: list[str] = []

    monkeypatch.setattr(orchestrator.settings, "PREVIEW_GENERATOR_V2", True)
    monkeypatch.setattr(
        orchestrator,
        "_run_v1_pipeline",
        lambda *_args, **_kwargs: calls.append("v1") or existing,
    )
    monkeypatch.setattr(
        orchestrator,
        "_run_v2_boundary",
        lambda *_args, **_kwargs: calls.append("v2") or {"unexpected": True},
    )

    actual = orchestrator._generate_preview_app_inner(db, 41, object(), object())

    assert actual is existing
    assert calls == ["v1"]
    assert json.loads(request.generated_pages) == existing


def test_new_preview_can_select_v2_and_phase0_delegates_to_v1_engine(monkeypatch) -> None:
    selection = select_preview_generator(_request(), v2_enabled=True)
    assert selection == GeneratorSelection(GENERATOR_V2, "flag_enabled_new_preview")

    seen: dict[str, object] = {}

    def frozen_v1(*_args, **kwargs):
        seen.update(kwargs)
        return {"delegated": True}

    monkeypatch.setattr(orchestrator, "_run_v1_pipeline", frozen_v1)
    actual = orchestrator._run_v2_boundary(
        object(),
        41,
        object(),
        object(),
        app_spec_revision_id=None,
        req=_request(),
    )

    assert actual == {"delegated": True}
    assert seen["generator_version"] == GENERATOR_V2


def test_enabled_flag_dispatches_a_new_preview_through_v2(monkeypatch) -> None:
    request = _request()
    db = _FakeRequestQuery(request)
    expected = {"preview_app": {"generator_version": "v2"}}
    calls: list[str] = []

    monkeypatch.setattr(orchestrator.settings, "PREVIEW_GENERATOR_V2", True)
    monkeypatch.setattr(
        orchestrator,
        "_run_v1_pipeline",
        lambda *_args, **_kwargs: calls.append("v1") or {"unexpected": True},
    )
    monkeypatch.setattr(
        orchestrator,
        "_run_v2_boundary",
        lambda *_args, **_kwargs: calls.append("v2") or expected,
    )

    actual = orchestrator._generate_preview_app_inner(db, 41, object(), object())

    assert actual is expected
    assert calls == ["v2"]


def test_v2_marker_is_sticky_only_while_flag_is_enabled() -> None:
    marked = _request(json.dumps({"preview_app": {"generator_version": "v2"}}))
    assert select_preview_generator(marked, v2_enabled=True).version == GENERATOR_V2
    assert select_preview_generator(marked, v2_enabled=False).version == GENERATOR_V1

    malformed_legacy = _request("{not-json")
    assert (
        select_preview_generator(malformed_legacy, v2_enabled=True).reason
        == "existing_v1_preview"
    )


def test_v1_payload_is_not_modified_by_version_marker() -> None:
    baseline = {"status": "ready", "routes": [{"path": "/"}]}
    before = json.loads(json.dumps(baseline))
    returned = apply_generator_version_marker(baseline, version=GENERATOR_V1)

    assert returned is baseline
    assert baseline == before
    assert "generator_version" not in baseline

    apply_generator_version_marker(baseline, version=GENERATOR_V2)
    assert baseline["generator_version"] == GENERATOR_V2


def test_dispatch_evaluates_only_the_selected_generator() -> None:
    calls: list[str] = []
    actual = dispatch_preview_generator(
        GeneratorSelection(GENERATOR_V1, "test"),
        run_v1=lambda: calls.append("v1") or "legacy-result",
        run_v2=lambda: calls.append("v2") or "new-result",
    )
    assert actual == "legacy-result"
    assert calls == ["v1"]
