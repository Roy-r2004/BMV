"""is_request_generating must stay true through codegen/build, not stop at blueprint."""
from __future__ import annotations

import json
from types import SimpleNamespace

from app.application.services.progress import (
    is_request_generating,
    progress_payload,
)


def _req(**kwargs):
    defaults = {
        "status": "new",
        "generation_log": None,
        "mvp_blueprint": None,
        "generated_pages": None,
        "visual_demo_json": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_just_created_is_generating():
    assert is_request_generating(_req()) is True


def test_blueprint_only_still_generating_when_progress_says_codegen():
    snap = {
        "stage": "codegen",
        "label": "Writing pages...",
        "pct": 45,
        "updated_at": "2026-07-17T10:00:00+00:00",
    }
    req = _req(
        mvp_blueprint="# Blueprint",
        concept_name="Jane Art",
        generation_log=json.dumps(snap),
    )
    assert is_request_generating(req) is True


def test_done_stage_stops_generating_even_if_status_new():
    snap = {"stage": "done", "label": "Generation complete!", "pct": 100}
    req = _req(
        mvp_blueprint="# Blueprint",
        generated_pages='{"preview_app":{"url":"/x"}}',
        generation_log=json.dumps(snap),
    )
    assert is_request_generating(req) is False


def test_failed_status_stops_generating():
    req = _req(status="failed", generation_log=json.dumps({"stage": "codegen", "pct": 40}))
    assert is_request_generating(req) is False


def test_legacy_complete_without_log_not_generating():
    req = _req(
        mvp_blueprint="# Blueprint",
        generated_pages='{"roles":[]}',
        visual_demo_json="{}",
    )
    assert is_request_generating(req) is False


def test_progress_payload_flags():
    snap = {"stage": "build", "label": "Compiling...", "pct": 86, "log": []}
    req = _req(generation_log=json.dumps(snap))
    payload = progress_payload(req)
    assert payload["is_generating"] is True
    assert payload["is_failed"] is False
    assert payload["stage"] == "build"


def test_failed_payload():
    snap = {"stage": "failed", "label": "Generation failed", "pct": 0, "log": []}
    req = _req(status="failed", generation_log=json.dumps(snap))
    payload = progress_payload(req)
    assert payload["is_generating"] is False
    assert payload["is_failed"] is True


def test_emit_does_not_rewind_stage_or_pct():
    """Preview retry must not send the customer UI back to UX/UI after Architecture."""
    from app.application.services import progress as progress_mod

    class _FakeQuery:
        def __init__(self, req):
            self._req = req

        def filter(self, *_a, **_k):
            return self

        def first(self):
            return self._req

    class _FakeDb:
        def __init__(self, req):
            self.req = req
            self.commits = 0

        def query(self, *_a, **_k):
            return _FakeQuery(self.req)

        def commit(self):
            self.commits += 1

    req = _req(
        id=14,
        generation_log=json.dumps(
            {
                "stage": "build",
                "label": "Compiling...",
                "pct": 86,
                "files_done": 8,
                "files_total": 8,
                "log": [],
            }
        ),
    )
    db = _FakeDb(req)
    progress_mod.emit(db, 14, "codegen", "Retrying preview generation...", 28)
    snap = json.loads(req.generation_log)
    assert snap["stage"] == "build"
    assert snap["pct"] == 86
    assert snap["label"] == "Retrying preview generation..."


def test_emit_resets_after_terminal_failed():
    """Customer/pipeline retry after failure must leave stage=failed."""
    from app.application.services import progress as progress_mod

    class _FakeQuery:
        def __init__(self, req):
            self._req = req

        def filter(self, *_a, **_k):
            return self

        def first(self):
            return self._req

    class _FakeDb:
        def __init__(self, req):
            self.req = req

        def query(self, *_a, **_k):
            return _FakeQuery(self.req)

        def commit(self):
            pass

    req = _req(
        id=16,
        status="new",
        generation_log=json.dumps(
            {
                "stage": "failed",
                "label": "Generation failed",
                "pct": 100,
                "files_done": 0,
                "files_total": 0,
                "log": [],
            }
        ),
    )
    db = _FakeDb(req)
    progress_mod.emit(db, 16, "build", "Retrying preview generation...", 86)
    snap = json.loads(req.generation_log)
    assert snap["stage"] == "build"
    assert snap["pct"] == 86
    assert progress_mod.is_request_generating(req) is True
