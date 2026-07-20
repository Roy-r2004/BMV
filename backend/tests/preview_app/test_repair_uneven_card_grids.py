"""md:grid-cols-2 with 3 Cards must become a 3-column layout."""
from __future__ import annotations

from pathlib import Path

from app.application.preview_app.safety.source_sanitize import repair_uneven_card_grids


def test_repair_uneven_card_grids_promotes_three_card_two_col(tmp_path: Path):
    pages = tmp_path / "src/pages"
    pages.mkdir(parents=True)
    src = """
export default function Page() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>One</Card>
      <Card>Two</Card>
      <Card>Three</Card>
    </div>
  );
}
"""
    (pages / "WaitlistConfirmationPage.tsx").write_text(src, encoding="utf-8")
    fixed = repair_uneven_card_grids(tmp_path)
    assert fixed
    out = (pages / "WaitlistConfirmationPage.tsx").read_text(encoding="utf-8")
    assert "lg:grid-cols-3" in out
    assert "md:grid-cols-2" not in out
