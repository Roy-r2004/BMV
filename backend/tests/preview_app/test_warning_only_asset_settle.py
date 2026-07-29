"""Warning-only defects must still be repaired and reported.

`GateReport.ok` ignores warnings, so `run_quality_gate_with_heal` returns before
`heal_quality_gate` when the only defect is owner-surface breakage. Preview 36
shipped exactly that shape: seven invented `/images/mock-artwork-*.jpg` and
`/placeholder-*.jpg` references, all on admin pages, every one rendering a
broken-image icon while the gate reported a clean pass.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.application.preview_app.asset_integrity import scan_asset_integrity
from app.application.preview_app.quality_gate import run_quality_gate_with_heal

_ADMIN_PAGE = """\
const rows = [
  { id: '1', title: 'Winter Solstice', thumbnail: '/images/mock-artwork-1.jpg' },
  { id: '2', title: 'Morning Mist', thumbnail: '/images/mock-artwork-2.jpg' },
];

export default function ManageArtworksPage() {
  return (
    <div>
      {rows.map((row) => (
        <img key={row.id} src={row.thumbnail} alt={row.title} />
      ))}
    </div>
  );
}
"""

_MOCK_TS = """\
export const images = {
  "hero": "https://images.pexels.com/photos/16432481/pexels-photo-16432481.jpeg",
  "card1": "https://images.pexels.com/photos/16397760/pexels-photo-16397760.jpeg"
};
"""


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    (workspace / "src" / "pages" / "admin").mkdir(parents=True)
    (workspace / "src" / "data").mkdir(parents=True)
    (workspace / "dist").mkdir(parents=True)
    (workspace / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
    (workspace / "src" / "data" / "mock.ts").write_text(_MOCK_TS, encoding="utf-8")
    (workspace / "src" / "pages" / "admin" / "ManageArtworksPage.tsx").write_text(
        _ADMIN_PAGE, encoding="utf-8"
    )
    return workspace


def _architect() -> dict:
    return {
        "routes": [
            {
                "path": "/admin/artworks",
                "component_file": "src/pages/admin/ManageArtworksPage.tsx",
                "surface": "ops",
                "skeleton_id": "ops-list",
            }
        ],
        "files_to_generate": [],
    }


def test_admin_only_missing_assets_are_detected_as_warnings(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    report = scan_asset_integrity(workspace)
    missing = {ref.path for ref in report.missing}
    assert "/images/mock-artwork-1.jpg" in missing
    assert "/images/mock-artwork-2.jpg" in missing
    assert all(not ref.public_surface for ref in report.missing), (
        "admin-page references must not be classified as public-surface, or they "
        "would withhold the whole preview"
    )


def test_warning_only_run_repairs_the_broken_references(tmp_path: Path) -> None:
    """The regression: gate passes, so the heal path is skipped and nothing repairs."""
    workspace = _workspace(tmp_path)

    report = run_quality_gate_with_heal(
        workspace,
        _architect(),
        brand_name="Jeanne Kassab Art",
        require_ai_hub=False,
        allow_ai_repair=False,
    )

    assert report.ok, "admin-only breakage must never withhold the preview"

    source = (workspace / "src" / "pages" / "admin" / "ManageArtworksPage.tsx").read_text(
        encoding="utf-8"
    )
    assert "/images/mock-artwork-1.jpg" not in source, (
        "warning-only run returned before heal_quality_gate, so the deterministic "
        "asset repair never fired and the broken reference still ships"
    )
    assert "pexels.com" in source, "broken refs should be repointed at imagery that loads"

    after = scan_asset_integrity(workspace)
    assert not after.missing, f"still unresolved: {[r.path for r in after.missing]}"


def test_repair_is_recorded_as_healed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    report = run_quality_gate_with_heal(
        workspace,
        _architect(),
        brand_name="Jeanne Kassab Art",
        require_ai_hub=False,
        allow_ai_repair=False,
    )
    assert any("ManageArtworksPage" in path for path in report.healed), (
        f"repair must be attributed in report.healed, got {report.healed}"
    )


def test_clean_workspace_is_untouched(tmp_path: Path) -> None:
    """No warnings → no rescan, no repair, no log noise."""
    workspace = _workspace(tmp_path)
    page = workspace / "src" / "pages" / "admin" / "ManageArtworksPage.tsx"
    page.write_text(
        _ADMIN_PAGE.replace("/images/mock-artwork-1.jpg", "https://example.com/a.jpg")
        .replace("/images/mock-artwork-2.jpg", "https://example.com/b.jpg"),
        encoding="utf-8",
    )
    before = page.read_text(encoding="utf-8")

    report = run_quality_gate_with_heal(
        workspace,
        _architect(),
        brand_name="Jeanne Kassab Art",
        require_ai_hub=False,
        allow_ai_repair=False,
    )

    assert report.ok
    assert not report.warnings
    assert page.read_text(encoding="utf-8") == before
