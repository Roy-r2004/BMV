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
    """An existing key survives untouched; a missing one is still filled.

    The old version returned early whenever `hero` was present, which meant a seed
    carrying `hero` but no `cta` kept crashing pages that read `seed.cta.heading`.
    It also injected the whole block when `hero` was absent, re-declaring every key
    the model had written — six TS1117 duplicate-property errors on request 43.
    """
    mock = """
export const seed = {
  hero: { headline: 'Keep me', subcopy: 'x' },
  process: [],
};
"""
    out = ensure_seed_scaffold_fields(mock, brand_name="Other")
    assert out.count("hero:") == 1, "the authored hero must not be re-declared"
    assert "Keep me" in out
    assert out.count("cta:") == 1, "a genuinely missing scaffold key is still filled"


def test_ensure_seed_scaffold_fields_never_duplicates_a_key():
    """Request 43's mock carried six duplicated keys, stub first and content second."""
    mock = """
export const seed = {
  credentialsHeading: 'Trusted by collectors',
  credentials: [{ title: 'Featured Artist', detail: 'Saatchi Art Spotlight' }],
  featuresHeading: 'About the Art',
  features: [{ title: 'Abstract Landscapes', description: 'Oils.' }],
  items: [{ id: 'a', title: 'A' }],
  footer: { title: 'Brand', description: 'Explore.' },
};
"""
    out = ensure_seed_scaffold_fields(mock, brand_name="Jeanne Kassab Art")

    for key in ("credentialsHeading", "credentials", "featuresHeading", "features", "items", "footer"):
        assert out.count(f"{key}:") == 1, f"{key} was re-declared"
    assert "Saatchi Art Spotlight" in out, "authored content must survive"
    assert out.count("hero:") == 1, "and the genuinely missing key is added"
