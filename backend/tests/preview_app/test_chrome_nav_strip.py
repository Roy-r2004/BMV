"""Local PublicNav definitions must be stripped when importing from @/ui."""
from __future__ import annotations

from app.application.preview_app.chrome_nav import _ensure_named_ui_import


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
