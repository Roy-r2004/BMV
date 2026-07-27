"""Regression: truncation heuristic must catch mid-component cuts ending on `>`."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.source_quality import looks_truncated_source  # noqa: E402


def test_complete_page_not_truncated() -> None:
    src = """
export default function Page() {
  // note: objects use { braces }
  return (
    <main className="ok">
      <h1>Hello</h1>
    </main>
  );
}
"""
    assert looks_truncated_source(src) is False


def test_cut_after_jsx_tag_with_open_braces_is_truncated() -> None:
    """Prior bug: ending on `>` skipped truncation even with unclosed `{`."""
    src = """
export default function Page() {
  return (
    <PublicShell brandName="Acme">
      <h1>Hello</h1>
"""
    assert looks_truncated_source(src) is True


def test_comment_braces_do_not_false_positive() -> None:
    src = """
export default function Page() {
  /* leftover { from edit */
  return <main>Hi</main>;
}
"""
    assert looks_truncated_source(src) is False


def main() -> None:
    test_complete_page_not_truncated()
    test_cut_after_jsx_tag_with_open_braces_is_truncated()
    test_comment_braces_do_not_false_positive()
    print("OK: source_quality truncation tests passed (3)")


if __name__ == "__main__":
    main()
