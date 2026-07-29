"""The visual loop's verdict must actually reach the quality gate.

`visual_critique_gate_issues` existed and was documented as "triples a quality
gate can fail on directly", but nothing called it — the loop rendered pixels,
persisted a report, and the report was never read. That is the same shape as
every other blind spot in this pipeline: a check that records and disappears.
"""
from __future__ import annotations

from pathlib import Path

from app.application.preview_app.pipeline.visual_critic import (
    BLOCK,
    WARN,
    VisualCritiqueReport,
    VisualFinding,
    write_visual_critique_report,
)
from app.application.preview_app.quality_gate import evaluate_quality_gate

_PAGE = """\
export default function HomePage() {
  return <div>Home</div>;
}
"""


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    (workspace / "src" / "pages").mkdir(parents=True)
    (workspace / "src" / "data").mkdir(parents=True)
    (workspace / "dist").mkdir(parents=True)
    (workspace / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
    (workspace / "src" / "data" / "mock.ts").write_text(
        'export const images = { "hero": "https://images.pexels.com/photos/1/x.jpeg" };\n',
        encoding="utf-8",
    )
    (workspace / "src" / "pages" / "HomePage.tsx").write_text(_PAGE, encoding="utf-8")
    return workspace


def _architect() -> dict:
    return {
        "routes": [
            {
                "path": "/",
                "component_file": "src/pages/HomePage.tsx",
                "surface": "public",
                "skeleton_id": "public-home",
            }
        ],
        "files_to_generate": [],
    }


def _codes(workspace: Path) -> set[str]:
    report = evaluate_quality_gate(workspace, _architect(), require_ai_hub=False)
    return {issue.code for issue in report.issues}


def test_blocking_imagery_mismatch_fails_the_gate(tmp_path: Path) -> None:
    """The dental-photos-in-an-art-gallery case must withhold the preview."""
    workspace = _workspace(tmp_path)
    write_visual_critique_report(
        workspace,
        VisualCritiqueReport(
            findings=[
                VisualFinding(
                    code="imagery_industry_mismatch",
                    message="Imagery sourced for a 'health' business but the brief reads as 'art'.",
                    path="src/data/mock.ts",
                    severity=BLOCK,
                )
            ],
            reviewed=["src/pages/HomePage.tsx"],
        ),
    )
    assert "imagery_industry_mismatch" in _codes(workspace)


def test_warn_severity_findings_do_not_fail_the_gate(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    write_visual_critique_report(
        workspace,
        VisualCritiqueReport(
            findings=[
                VisualFinding(
                    code="visual_defect",
                    message="Spacing is a little tight above the fold.",
                    path="src/pages/HomePage.tsx",
                    severity=WARN,
                )
            ],
            reviewed=["src/pages/HomePage.tsx"],
        ),
    )
    assert "visual_defect" not in _codes(workspace)


def test_missing_image_asset_finding_defers_to_the_surface_aware_check(
    tmp_path: Path,
) -> None:
    """An owner-page thumbnail must never withhold the whole preview.

    `imagery_findings` emits `missing_image_asset` at BLOCK on every surface,
    duplicating `asset_integrity` which deliberately blocks only on public
    imagery. The gate must not adopt the surface-blind copy.
    """
    workspace = _workspace(tmp_path)
    write_visual_critique_report(
        workspace,
        VisualCritiqueReport(
            findings=[
                VisualFinding(
                    code="missing_image_asset",
                    message="Image reference '/images/mock-artwork-1.jpg' has no file.",
                    path="src/pages/admin/ManageArtworksPage.tsx",
                    severity=BLOCK,
                )
            ],
            reviewed=["src/pages/HomePage.tsx"],
        ),
    )
    assert "missing_image_asset" not in _codes(workspace)


def test_absent_report_is_not_a_gate_failure(tmp_path: Path) -> None:
    """No visual run (e.g. critic disabled) must not manufacture issues."""
    workspace = _workspace(tmp_path)
    assert not _codes(workspace) & {
        "imagery_industry_mismatch",
        "visual_defect",
        "visual_defect_severe",
        "visual_critique_unavailable",
    }


def test_corrupt_report_does_not_break_the_gate(tmp_path: Path) -> None:
    from app.application.preview_app.pipeline.visual_critic import report_path

    workspace = _workspace(tmp_path)
    path = report_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    evaluate_quality_gate(workspace, _architect(), require_ai_hub=False)
