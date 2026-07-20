"""seed.hero must survive AI mock rewrites for catalogue home scaffolds."""
from __future__ import annotations

from app.application.preview_app.safety.mock_data import ensure_seed_scaffold_fields


def test_ensure_seed_scaffold_fields_adds_hero_when_missing():
    mock = """
export const seed = {
  processHeading: 'How it works',
  process: [{ title: 'One', description: 'Step' }],
};
"""
    out = ensure_seed_scaffold_fields(mock, brand_name="Clay & Kiln")
    assert "hero:" in out
    assert "Clay & Kiln" in out
    assert "items:" in out
    assert "cta:" in out
    assert "footer:" in out


def test_ensure_seed_scaffold_fields_keeps_existing_hero():
    mock = """
export const seed = {
  hero: { headline: 'Keep me', subcopy: 'x' },
  process: [],
};
"""
    out = ensure_seed_scaffold_fields(mock, brand_name="Other")
    assert out.count("hero:") == 1
    assert "Keep me" in out
    assert "Other" not in out
