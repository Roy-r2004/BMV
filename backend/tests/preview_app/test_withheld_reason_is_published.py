"""`viewable` was never a key, and `withheld_reason` never had a writer.

`scripts/measure/analyse.py` has read `preview_app["viewable"]` and
`preview_app["withheld_reason"]` since it was written. `finalize` computes
`viewable` as a **local** and publishes only its consequences — `status` and
`url` — so both reads have always returned `None`. Duo 1 reported `viewable:
None` on requests 95 and 96, *both of which shipped `ready`*, and the finding
was filed as an unexplained pipeline defect. It was the instrument.

Sixth entry in the running list of *the instrument was the defect*, after
`gate_issues` (read for four trios, never written), `tail.py`'s hardcoded run
list, the stale typecheck count, `visual_review_status`, and appspec's
`writer = NULL` census rows.

The fix is deliberately asymmetric, and that is the interesting part:

* **`viewable` is not published.** It is exactly `status == "ready"`. A second
  stored key free to disagree with the first is the same defect one layer down;
  `analyse.py` derives it instead.
* **`withheld_reason` is published**, because it is not derivable from anything
  stored. `status: "failed"` cannot tell an operator whether vite failed, the
  quality gate blocked, or a page still renders a stack trace behind a passing
  gate — three different next actions.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.application.preview_app.pipeline.finalize import withheld_reason


@pytest.mark.parametrize(
    "dist_ok, gate_ok, crash, expected",
    [
        (True, True, False, None),
        (True, True, True, "render_crash_unresolved"),
        (True, False, False, "quality_gate_failed"),
        (False, True, False, "build_failed"),
        # Order is load-bearing: a run that never built has no gate verdict
        # worth reporting, and a crash behind a failing gate is the gate's.
        (False, False, True, "build_failed"),
        (True, False, True, "quality_gate_failed"),
    ],
)
def test_the_reason_names_which_refusal_fired(dist_ok, gate_ok, crash, expected) -> None:
    assert withheld_reason(dist_ok=dist_ok, gate_ok=gate_ok, crash_unresolved=crash) == expected


def _finalize(
    tmp_path: Path,
    *,
    gate_ok: bool = True,
    build: bool = True,
    unresolved: list[str] | None = None,
) -> dict:
    """Run the real `run_finalize` and return its `preview_app` result.

    Asserting on `withheld_reason` as computed by the helper proves the helper
    works and proves nothing about whether the record carries it — which is
    precisely the defect being fixed, so it has to go through `run_finalize`.
    """

    from app.application.preview_app.pipeline import finalize as finalize_module
    from app.application.preview_app.pipeline.context import PipelineContext
    from app.application.preview_app.quality_gate import GateIssue, GateReport

    if build:
        (tmp_path / "dist").mkdir(parents=True, exist_ok=True)
        (tmp_path / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")

    ctx = PipelineContext(
        db=SimpleNamespace(commit=lambda: None),
        request_id=95,
        ai_provider=None,
        template_renderer=None,
        app_spec_revision_id=None,
        req=SimpleNamespace(
            generated_pages=None,
            business_name="Osteria Vinci",
            concept_name="Osteria Vinci",
            updated_at=None,
        ),
    )
    ctx.workspace = tmp_path
    ctx.architect = {"routes": [], "roles": []}
    ctx.plan = {"roles": []}
    ctx.manifest = {}
    ctx.design_system = {}
    ctx.enforce_app_spec = False
    ctx.ok = True
    ctx.base_path = "/api/preview-apps/95"

    # The real report, not a `SimpleNamespace` shaped like one: a fake that is
    # not the real type is a test that stops tracking the thing it tests.
    report = GateReport()
    if not gate_ok:
        report.issues.append(
            GateIssue(
                code="placeholder_content_shipped",
                message="lorem ipsum",
                path="src/pages/HomePage.tsx",
            )
        )

    originals = {
        name: getattr(finalize_module, name)
        for name in (
            "_emit",
            "run_quality_gate_with_heal",
            "ai_features_from_request",
            "_render_smoke_check",
        )
    }
    try:
        finalize_module._emit = lambda *args, **kwargs: None
        finalize_module.run_quality_gate_with_heal = lambda *a, **k: report
        finalize_module.ai_features_from_request = lambda *a, **k: []
        if unresolved is not None:
            finalize_module._render_smoke_check = lambda *a, **k: {
                "checked": len(unresolved),
                "eligible": len(unresolved),
                "skipped": 0,
                "crashed": list(unresolved),
                "stubbed": [],
                "unresolved": list(unresolved),
            }
        return finalize_module.run_finalize(ctx)["preview_app"]
    finally:
        for name, value in originals.items():
            setattr(finalize_module, name, value)


def test_a_served_preview_records_the_reason_as_none_rather_than_omitting_it(
    tmp_path: Path,
) -> None:
    """Absent and "not withheld" have to be different readings.

    Requests 95 and 96 shipped `ready` and their record said nothing at all, so
    every reader had to guess whether the pipeline had decided or not recorded.
    """

    preview_app = _finalize(tmp_path)

    assert preview_app["status"] == "ready"
    assert "withheld_reason" in preview_app
    assert preview_app["withheld_reason"] is None


def test_a_blocked_gate_says_so_in_the_record_not_only_in_the_log(tmp_path: Path) -> None:
    preview_app = _finalize(tmp_path, gate_ok=False)

    assert preview_app["status"] == "failed"
    assert preview_app["url"] is None
    assert preview_app["withheld_reason"] == "quality_gate_failed"


def test_a_run_that_never_built_is_distinguishable_from_one_the_gate_blocked(
    tmp_path: Path,
) -> None:
    """`status: "failed"` covers both, and they point at different tools."""

    preview_app = _finalize(tmp_path, build=False)

    assert preview_app["status"] == "failed"
    assert preview_app["withheld_reason"] == "build_failed"


def test_a_passing_gate_does_not_serve_a_page_that_still_renders_a_stack_trace(
    tmp_path: Path,
) -> None:
    """The third refusal, and the one a `dist_ok and gate.ok` reading loses.

    A mutation that dropped the crash term survived a first sweep: every other
    test here has `unresolved` empty, so removing it changed nothing any of
    them could see. Fourth time this repo has caught *asserting against the
    case that does not bind*.
    """

    preview_app = _finalize(tmp_path, unresolved=["/gallery"])

    assert preview_app["status"] == "failed"
    assert preview_app["url"] is None
    assert preview_app["withheld_reason"] == "render_crash_unresolved"


def test_viewable_is_derived_by_the_reader_and_never_stored(tmp_path: Path) -> None:
    """The key `analyse.py` spent four trios reading stays unwritten on purpose."""

    preview_app = _finalize(tmp_path)

    assert "viewable" not in preview_app
    assert (preview_app["status"] == "ready") is True
