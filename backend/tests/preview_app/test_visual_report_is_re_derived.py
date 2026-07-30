"""P0-3 and P0-2: the visual report must be re-derived, and its coverage visible.

Two failures of the same kind — a measurement that is taken once and then either
never retaken or never read:

* **P0-3** `_bmv_visual_critique.json` was written pre-refine and persisted
  *unchanged* on the refine success path. It is the only BLOCK source the quality
  gate reads that was never re-derived, so a page the pipeline had just repaired
  kept failing the gate forever: `viewable=False`, `url=None`,
  `status="failed"` — with a good `dist/` sitting on disk.

* **P0-2** A total vision outage puts every page in `unmeasured` at WARN, which
  leaves `report.blocking == []`, which passes the gate, which reports
  `status: "ready"`. Zero pages were judged, and the progress feed said
  `Visually reviewed 6/6` because the emit ran before the exception check.
  `measurement_failed` existed to say so and had no production reader.
"""
from __future__ import annotations

import inspect
import re
import sys
import threading
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

from app.application.preview_app.pipeline import visual_critic as vc  # noqa: E402
from app.application.preview_app.screenshot import RouteCapture  # noqa: E402

GALLERY = "src/pages/GalleryPage.tsx"
HOME = "src/pages/HomePage.tsx"


def _architect() -> dict:
    return {
        "routes": [
            {"path": "/", "component_file": HOME, "surface": "public", "title": "Home"},
            {
                "path": "/gallery",
                "component_file": GALLERY,
                "surface": "public",
                "title": "Gallery",
            },
        ],
        "design_direction": "Gallery-quiet, image-led",
    }


def _workspace(tmp_path: Path) -> Path:
    for rel in (HOME, GALLERY):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("export default function P() { return null }\n", encoding="utf-8")
    return tmp_path


class _Harness:
    """Scripted stand-in for the browser, the vision model, and the builder.

    `verdicts` is read per (component_file, visit number), so a page can score
    badly on the first look and well on the second — which is the whole point of
    a refine pass and the thing the report could not represent.
    """

    def __init__(
        self,
        verdicts: dict[tuple[str, int], dict],
        *,
        capture_ok=lambda component_file, visit: True,
        build_ok: bool = True,
    ) -> None:
        self.verdicts = verdicts
        self.capture_ok = capture_ok
        self.build_ok = build_ok
        self.visits: dict[str, int] = {}
        self.refined: list[str] = []
        self.builds = 0
        self.emitted: list[tuple[str, str]] = []
        self.route_for_shot: dict[str, str] = {}
        # Routes are reviewed on a thread pool, so the visit counter needs a lock
        # and each critique must read the visit number belonging to *its own*
        # capture rather than whatever the shared counter reached.
        self._lock = threading.Lock()
        self._visit_for_shot: dict[str, int] = {}

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(vc, "capture_route_visual", self._capture)
        monkeypatch.setattr(vc, "critique_file_visual", self._critique)
        monkeypatch.setattr(vc, "refine_file", self._refine)
        monkeypatch.setattr(vc, "apply_workspace_guards", lambda *a, **k: None)
        monkeypatch.setattr(vc, "run_build", self._build)
        monkeypatch.setattr(vc, "_emit", self._emit)

    # -- seams ------------------------------------------------------------
    def _capture(self, base_url, route_path, shot_path, **_kw) -> RouteCapture:
        component_file = HOME if route_path in ("/", "") else GALLERY
        with self._lock:
            visit = self.visits.get(component_file, 0) + 1
            self.visits[component_file] = visit
        if not self.capture_ok(component_file, visit):
            return RouteCapture(ok=False)
        shot_path = Path(shot_path)
        shot_path.parent.mkdir(parents=True, exist_ok=True)
        shot_path.write_bytes(b"png")
        with self._lock:
            self.route_for_shot[str(shot_path)] = component_file
            self._visit_for_shot[str(shot_path)] = visit
        return RouteCapture(ok=True, path=shot_path, broken_images=[])

    def _critique(self, _workspace, component_file, shot_path, *_a, **_kw) -> dict:
        with self._lock:
            visit = self._visit_for_shot.get(str(shot_path), 1)
        verdict = self.verdicts.get((component_file, visit))
        if verdict is None:
            # `(file, "*")` is the any-visit fallback: when several routes share a
            # page the pool decides which visit number each one gets.
            verdict = self.verdicts[(component_file, "*")]
        return dict(verdict)

    def _refine(self, workspace, component_file, *_a, **_kw) -> None:
        (Path(workspace) / component_file).write_text(
            "export default function P() { return <main>refined</main> }\n",
            encoding="utf-8",
        )
        self.refined.append(component_file)

    def _build(self, *_a, **_kw) -> tuple[bool, str]:
        self.builds += 1
        return (self.build_ok, "")

    def _emit(self, _db, _rid, stage, label, _pct, detail="", **_kw) -> None:
        self.emitted.append((stage, label))

    # -- assertions helpers ----------------------------------------------
    def labels(self) -> list[str]:
        return [label for _stage, label in self.emitted]


def _run(tmp_path: Path, harness: _Harness) -> vc.VisualCritiqueReport:
    return vc._run_visual_critique(
        None,
        36,
        _workspace(tmp_path),
        _architect(),
        {},
        {},
        "Jeanne Kassab Art sells original oil paintings.",
        {},
        {},
        "Jeanne Kassab Art",
        "#111111",
        "#222222",
        "Inter",
        "/api/preview-apps/36",
        None,
        None,
    )


_PASS = {"score": 88, "verdict": "pass", "issues": [], "revision_instructions": ""}


def _revise(score: int, issue: str) -> dict:
    return {
        "score": score,
        "verdict": "revise",
        "issues": [issue],
        "revision_instructions": issue,
    }


# ---------------------------------------------------------------------------
# P0-3 — a repaired page must clear its own BLOCK
# ---------------------------------------------------------------------------

def test_a_refined_page_clears_its_own_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact P0-3 trap: score 30 → rewrite → rebuild clean → still failed.

    Proven before this fix by running `run_quality_gate_with_heal` on a workspace
    whose only defect was the persisted BLOCK: `ok=False` after deterministic
    heal, 3 AI repair attempts, and 4 successful rebuilds, with the report
    byte-identical on disk.
    """
    harness = _Harness(
        {
            (HOME, 1): _PASS,
            (GALLERY, 1): _revise(30, "SEVERE: the grid renders three of nine works"),
            (GALLERY, 2): _PASS,
        }
    )
    harness.install(monkeypatch)

    report = _run(tmp_path, harness)

    assert harness.refined == [GALLERY]
    assert report.refined == [GALLERY]
    assert report.blocking == [], f"stale BLOCK survived: {report.blocking}"
    assert report.ok is True
    assert report.scores[GALLERY] == 88, "the fresh score never replaced the old one"
    # And the gate — the actual victim — sees a clean report on disk.
    assert vc.visual_critique_gate_issues(tmp_path) == []


def test_a_refined_page_that_is_still_bad_gets_a_fresh_block_not_the_old_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-derivation is not the same as forgiveness.

    Distinguishes "the BLOCK was cleared" from "the BLOCK was re-measured": the
    surviving finding must quote the *second* review.
    """
    harness = _Harness(
        {
            (HOME, 1): _PASS,
            (GALLERY, 1): _revise(30, "SEVERE: first look — grid renders three of nine"),
            (GALLERY, 2): _revise(21, "SEVERE: second look — grid still renders three"),
        }
    )
    harness.install(monkeypatch)

    report = _run(tmp_path, harness)

    blocking = report.blocking
    assert [f.code for f in blocking] == ["visual_defect_severe"]
    assert "second look" in blocking[0].message
    assert "first look" not in blocking[0].message
    assert report.scores[GALLERY] == 21
    # Exactly one finding for the page, not one per pass.
    assert len([f for f in report.findings if f.path == GALLERY]) == 1


def test_a_refined_page_that_cannot_be_re_reviewed_reads_as_unmeasured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a rewrite we no longer know. That is not a pass and not the old BLOCK.

    The cheap version of the P0-3 fix — "ignore BLOCKs for paths in
    `report.refined`" — would report this page as fine.
    """
    harness = _Harness(
        {
            (HOME, 1): _PASS,
            (GALLERY, 1): _revise(30, "SEVERE: the grid renders three of nine works"),
        },
        capture_ok=lambda component_file, visit: not (component_file == GALLERY and visit == 2),
    )
    harness.install(monkeypatch)

    report = _run(tmp_path, harness)

    assert GALLERY in report.unmeasured
    assert GALLERY not in report.reviewed
    codes = [f.code for f in report.findings if f.path == GALLERY]
    assert codes == ["visual_critique_unavailable"]
    assert report.review_status == "partial"
    # WARN by default: our measurement failed, the app did not.
    assert report.blocking == []


def test_a_rollback_keeps_the_pre_refine_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the rebuild fails the source goes back, so the old verdict is current again."""
    harness = _Harness(
        {
            (HOME, 1): _PASS,
            (GALLERY, 1): _revise(30, "SEVERE: the grid renders three of nine works"),
        },
        build_ok=False,
    )
    harness.install(monkeypatch)

    report = _run(tmp_path, harness)

    assert report.refined == [], "a rolled-back refine must not be claimed"
    assert [f.code for f in report.blocking] == ["visual_defect_severe"]
    assert "three of nine" in report.blocking[0].message
    assert harness.visits[GALLERY] == 1, "no re-review on the rollback path"


def test_refining_a_file_with_no_screenshot_route_still_drops_its_stale_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_forget_pages` is the guarantee; the re-shoot is the best effort."""
    report = vc.VisualCritiqueReport(
        findings=[
            vc.VisualFinding("visual_defect_severe", "scored 30", GALLERY, vc.BLOCK),
            vc.VisualFinding("visual_defect", "spacing", HOME, vc.WARN),
        ],
        reviewed=[GALLERY, HOME],
        scores={GALLERY: 30, HOME: 88},
        refined=[GALLERY],
        routes_selected=2,
    )
    vc._remeasure_refined_pages(None, 36, report, [], lambda _i: None, None, 1)

    assert report.blocking == []
    assert report.reviewed == [HOME]
    assert GALLERY not in report.scores
    assert [f.path for f in report.findings] == [HOME]


def test_a_page_behind_several_routes_is_re_measured_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-measurement costs a screenshot and a vision call, so pay it per page.

    Declared routes routinely share a component: app 37 shipped `/artworks/:id`,
    `/artworks/:slug` and `/artworks/:artworkSlug` on one page.
    """
    architect = _architect()
    architect["routes"].append(
        {"path": "/gallery/:slug", "component_file": GALLERY, "surface": "public", "title": "Piece"}
    )
    harness = _Harness(
        {
            (HOME, "*"): _PASS,
            (GALLERY, 1): _revise(30, "SEVERE: the grid renders three of nine works"),
            (GALLERY, 2): _revise(30, "SEVERE: the grid renders three of nine works"),
            (GALLERY, 3): _PASS,
        }
    )
    harness.install(monkeypatch)

    report = vc._run_visual_critique(
        None, 36, _workspace(tmp_path), architect, {}, {}, "", {}, {},
        "Alder & Ash", "#111", "#222", "Inter", "/api/preview-apps/36", None, None,
    )

    # Two routes visit the page on the first pass, exactly one on the re-measure.
    assert harness.visits[GALLERY] == 3
    assert report.reviewed.count(GALLERY) == 1
    assert report.blocking == []


def test_forget_pages_is_exact_and_survives_windows_separators() -> None:
    report = vc.VisualCritiqueReport(
        findings=[
            vc.VisualFinding("visual_defect_severe", "bad", GALLERY, vc.BLOCK),
            vc.VisualFinding("visual_defect_severe", "bad", HOME, vc.BLOCK),
        ],
        reviewed=[GALLERY, HOME],
        unmeasured=[GALLERY],
        scores={GALLERY: 30, HOME: 20},
    )
    vc._forget_pages(report, [GALLERY.replace("/", "\\")])

    assert [f.path for f in report.findings] == [HOME]
    assert report.reviewed == [HOME]
    assert report.unmeasured == []
    assert report.scores == {HOME: 20}


def test_forget_pages_with_nothing_to_forget_is_a_no_op() -> None:
    report = vc.VisualCritiqueReport(
        findings=[vc.VisualFinding("visual_defect_severe", "bad", GALLERY, vc.BLOCK)],
        reviewed=[GALLERY],
    )
    vc._forget_pages(report, [])
    vc._forget_pages(report, [""])
    assert len(report.findings) == 1
    assert report.reviewed == [GALLERY]


def test_imagery_findings_are_recomputed_after_a_successful_refine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rewritten page can break a local image reference the first pass never saw."""
    workspace = _workspace(tmp_path)
    (workspace / "public").mkdir(exist_ok=True)

    harness = _Harness(
        {
            (HOME, 1): _PASS,
            (GALLERY, 1): _revise(30, "SEVERE: the grid renders three of nine works"),
            (GALLERY, 2): _PASS,
        }
    )
    harness.install(monkeypatch)

    def _refine_introducing_a_broken_image(ws, component_file, *_a, **_kw):
        (Path(ws) / component_file).write_text(
            'export default function P() { return <img src="/never-installed.jpg" /> }\n',
            encoding="utf-8",
        )
        harness.refined.append(component_file)

    monkeypatch.setattr(vc, "refine_file", _refine_introducing_a_broken_image)

    report = vc._run_visual_critique(
        None, 36, workspace, _architect(), {}, {}, "", {}, {},
        "Jeanne Kassab Art", "#111", "#222", "Inter", "/api/preview-apps/36", None, None,
    )

    missing = [f for f in report.findings if f.code == "missing_image_asset"]
    assert len(missing) == 1, "the post-refine imagery recompute never ran"
    assert "/never-installed.jpg" in missing[0].message


def test_imagery_finding_codes_are_complete() -> None:
    """`_IMAGERY_FINDING_CODES` drives the post-refine recompute in P0-3.

    A new code in `imagery_findings` that is missing here would be dropped from
    the report on the refine path and never restored.
    """
    import inspect

    source = inspect.getsource(vc.imagery_findings) + inspect.getsource(
        vc.check_imagery_industry_consistency
    )
    emitted = set(re.findall(r'code="([a-z_]+)"', source))
    assert emitted, "no codes found — the regex or the source shape changed"
    assert emitted == set(vc._IMAGERY_FINDING_CODES), (
        f"imagery_findings emits {sorted(emitted)} but _IMAGERY_FINDING_CODES is "
        f"{sorted(vc._IMAGERY_FINDING_CODES)}"
    )


# ---------------------------------------------------------------------------
# P0-2 — a vision outage must not report full coverage
# ---------------------------------------------------------------------------

def test_a_total_vision_outage_never_claims_a_page_was_reviewed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Visually reviewed 6/6` was emitted before the exception check."""
    harness = _Harness({}, capture_ok=lambda _cf, _v: False)
    harness.install(monkeypatch)

    report = _run(tmp_path, harness)

    assert report.reviewed == []
    assert len(report.unmeasured) == 2
    assert report.measurement_failed is True
    assert report.review_status == "unmeasured"
    assert report.routes_selected == 2

    claims = [label for label in harness.labels() if "Visually reviewed" in label]
    assert claims == [], f"progress feed claimed coverage it did not have: {claims}"
    assert any("measured 0 of 2" in label for label in harness.labels()), harness.labels()


def test_a_partial_outage_counts_only_what_was_judged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _Harness(
        {(HOME, 1): _PASS},
        capture_ok=lambda component_file, _v: component_file == HOME,
    )
    harness.install(monkeypatch)

    report = _run(tmp_path, harness)

    assert report.reviewed == [HOME]
    assert report.unmeasured == [GALLERY]
    assert report.review_status == "partial"
    assert "Visually reviewed 1/2: Home" in harness.labels()
    assert not any("2/2" in label for label in harness.labels())


def test_an_outage_still_does_not_withhold_the_preview_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Our vision vendor failing is not the generated app's defect.

    Blocking here is available, but off by default — withholding a working
    preview because OpenRouter 429'd is the same pathology as P0-3.
    """
    harness = _Harness({}, capture_ok=lambda _cf, _v: False)
    harness.install(monkeypatch)
    report = _run(tmp_path, harness)
    assert report.blocking == []
    assert vc.visual_critique_gate_issues(tmp_path) == []


def test_block_on_unmeasured_is_a_real_setting_an_operator_can_turn_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flag used to appear exactly once in the repo: at the line reading it."""
    from app.core.config import Settings

    assert hasattr(vc.settings, "PREVIEW_VISUAL_CRITIC_BLOCK_ON_UNMEASURED")
    assert vc.settings.PREVIEW_VISUAL_CRITIC_BLOCK_ON_UNMEASURED is False
    assert vc._unmeasured_severity() == vc.WARN

    monkeypatch.setenv("PREVIEW_VISUAL_CRITIC_BLOCK_ON_UNMEASURED", "true")
    assert Settings().PREVIEW_VISUAL_CRITIC_BLOCK_ON_UNMEASURED is True

    monkeypatch.setattr(
        vc.settings, "PREVIEW_VISUAL_CRITIC_BLOCK_ON_UNMEASURED", True, raising=False
    )
    assert vc._unmeasured_severity() == vc.BLOCK

    harness = _Harness({}, capture_ok=lambda _cf, _v: False)
    harness.install(monkeypatch)
    report = _run(tmp_path, harness)
    assert len(report.blocking) == 2
    assert {f.code for f in report.blocking} == {"visual_critique_unavailable"}


def test_review_status_tells_no_routes_apart_from_measured_nothing() -> None:
    assert vc.VisualCritiqueReport().review_status == "no_routes"
    assert vc.VisualCritiqueReport(routes_selected=3).review_status == "unmeasured"
    assert (
        vc.VisualCritiqueReport(routes_selected=1, unmeasured=[HOME]).review_status
        == "unmeasured"
    )
    assert (
        vc.VisualCritiqueReport(routes_selected=2, reviewed=[HOME], unmeasured=[GALLERY]).review_status
        == "partial"
    )
    assert (
        vc.VisualCritiqueReport(routes_selected=1, reviewed=[HOME]).review_status
        == "reviewed"
    )


def test_a_report_written_before_routes_selected_existed_still_classifies(
    tmp_path: Path,
) -> None:
    """An outage in an old report must not read as `no_routes`."""
    vc.report_path(tmp_path).write_text(
        '{"findings": [], "reviewed": [], "unmeasured": ["a.tsx", "b.tsx"]}',
        encoding="utf-8",
    )
    report = vc.load_visual_critique_report(tmp_path)
    assert report.routes_selected == 2
    assert report.review_status == "unmeasured"


def test_visual_review_summary_is_what_reaches_the_api_result(tmp_path: Path) -> None:
    vc.write_visual_critique_report(
        tmp_path,
        vc.VisualCritiqueReport(reviewed=[HOME], unmeasured=[GALLERY], routes_selected=2),
    )
    assert vc.visual_review_summary(tmp_path) == {
        "visual_review_status": "partial",
        "visual_pages_reviewed": 1,
        "visual_pages_unmeasured": 1,
        "visual_pages_selected": 2,
    }


def test_no_visual_run_contributes_no_fields(tmp_path: Path) -> None:
    """`PREVIEW_SKIP_VISUAL_CRITIC` is a configuration, not a measurement failure."""
    assert vc.visual_review_summary(tmp_path) == {}


def test_a_corrupt_report_summarises_instead_of_raising(tmp_path: Path) -> None:
    vc.report_path(tmp_path).write_text("{not json", encoding="utf-8")
    assert vc.visual_review_summary(tmp_path)["visual_review_status"] == "no_routes"


def _finalize(tmp_path: Path) -> tuple[dict, list[tuple]]:
    """Run the real `run_finalize` and return its `preview_app` result.

    A test that calls `_visual_review_summary` directly proves the helper works
    and proves nothing about whether anything calls it — which is the exact shape
    of defect being fixed here, so it has to go through `run_finalize`.
    """
    from types import SimpleNamespace

    from app.application.preview_app.pipeline import finalize as finalize_module
    from app.application.preview_app.pipeline.context import PipelineContext

    (tmp_path / "dist").mkdir(parents=True, exist_ok=True)
    (tmp_path / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")

    events: list[tuple] = []
    ctx = PipelineContext(
        db=SimpleNamespace(commit=lambda: None),
        request_id=36,
        ai_provider=None,
        template_renderer=None,
        app_spec_revision_id=None,
        req=SimpleNamespace(
            generated_pages=None,
            business_name="Jeanne Kassab Art",
            concept_name="Jeanne Kassab Art",
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
    ctx.base_path = "/api/preview-apps/36"

    originals = {
        name: getattr(finalize_module, name)
        for name in ("_emit", "run_quality_gate_with_heal", "ai_features_from_request")
    }
    try:
        finalize_module._emit = lambda *args, **kwargs: events.append(
            (args[2], args[3], kwargs.get("detail", ""))
        )
        finalize_module.run_quality_gate_with_heal = lambda *a, **k: SimpleNamespace(
            ok=True, healed=[], issues=[]
        )
        finalize_module.ai_features_from_request = lambda *a, **k: []
        result = finalize_module.run_finalize(ctx)
    finally:
        for name, value in originals.items():
            setattr(finalize_module, name, value)
    return result["preview_app"], events


def test_run_finalize_carries_the_measurement_into_the_api_result(tmp_path: Path) -> None:
    """`status: "ready"` must never again be the only thing a caller can see."""
    vc.write_visual_critique_report(
        tmp_path,
        vc.VisualCritiqueReport(unmeasured=[HOME, GALLERY], routes_selected=2),
    )
    preview_app, events = _finalize(tmp_path)

    assert preview_app["status"] == "ready"
    assert preview_app["visual_review_status"] == "unmeasured"
    assert preview_app["visual_pages_reviewed"] == 0
    assert preview_app["visual_pages_unmeasured"] == 2
    assert preview_app["visual_pages_selected"] == 2
    # And it is said out loud, not only recorded.
    assert any(
        "not visually reviewed" in label for _stage, label, _detail in events
    ), [label for _s, label, _d in events]


def test_run_finalize_reports_a_real_review_without_the_warning(tmp_path: Path) -> None:
    vc.write_visual_critique_report(
        tmp_path,
        vc.VisualCritiqueReport(reviewed=[HOME, GALLERY], routes_selected=2),
    )
    preview_app, events = _finalize(tmp_path)

    assert preview_app["visual_review_status"] == "reviewed"
    assert preview_app["visual_pages_reviewed"] == 2
    assert not any("not visually reviewed" in label for _s, label, _d in events)


def test_run_finalize_adds_no_visual_fields_when_the_critic_was_skipped(
    tmp_path: Path,
) -> None:
    preview_app, _events = _finalize(tmp_path)
    assert "visual_review_status" not in preview_app
    assert preview_app["status"] == "ready"
