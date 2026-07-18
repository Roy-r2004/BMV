"""Local PublicNav definitions must be stripped when importing from @/ui."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.chrome_nav import _ensure_named_ui_import  # noqa: E402


def test_strips_local_function_public_nav_before_ui_import():
    src = """
import { Button } from '@/ui';

function PublicNav({ items, cta }) {
  return <nav>{items.length}</nav>;
}

export default function HomePage() {
  return <PublicNav items={[]} cta={null} />;
}
"""
    out = _ensure_named_ui_import(src, "PublicNav")
    assert "function PublicNav" not in out
    assert "PublicNav" in out
    assert "from '@/ui'" in out
    assert "<PublicNav items={[]} cta={null} />" in out


def test_strips_const_arrow_public_nav():
    src = """
import { PublicShell } from '@/ui';

const PublicNav = ({ items }) => {
  return <div>{items.length}</div>;
};

export default function Page() {
  return <PublicNav items={[]} />;
}
"""
    out = _ensure_named_ui_import(src, "PublicNav")
    assert "const PublicNav" not in out
    assert "PublicNav" in out
    assert "from '@/ui'" in out


def test_strips_typed_public_nav_without_leaving_props_fragment():
    """Regression: props destructuring `{ items }` must not be treated as the body.

    A naive brace strip left `: PublicNavProps) {` and broke Vite (req 17).
    """
    src = """
import { Button } from '@/ui';

type PublicNavProps = { items: unknown[]; cta?: unknown };

function PublicNav({ items, cta }: PublicNavProps) {
  return <nav className="local">{items.length}</nav>;
}

export default function AboutPage() {
  return (
    <main>
      <PublicNav items={[]} cta={null} />
      <Button>Go</Button>
    </main>
  );
}
"""
    out = _ensure_named_ui_import(src, "PublicNav")
    assert "function PublicNav" not in out
    assert "PublicNavProps" not in out
    assert ": PublicNavProps)" not in out
    assert 'className="local"' not in out
    assert "PublicNav" in out and "from '@/ui'" in out
    assert "<PublicNav items={[]} cta={null} />" in out


def main() -> None:
    test_strips_local_function_public_nav_before_ui_import()
    test_strips_const_arrow_public_nav()
    test_strips_typed_public_nav_without_leaving_props_fragment()
    print("OK: chrome_nav PublicNav strip tests passed")


if __name__ == "__main__":
    main()
