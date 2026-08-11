"""3.10 consumption half — both motion engines are wired to the identity.

B2 authored the temperaments and pinned the data (distinct families, ops
restraint). This file pins the CONSUMPTION: presets.tsx (motion/react) and
anime.ts (anime.js) derive every timing constant from `motionIdentity()` as
ratios off the legacy base, so bare/unknown recipes render exactly the
pre-3.10 motion while authored recipes move at their own temperament. If a
constant gets re-hardcoded, the identity dies silently — these pins are the
alarm.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.core.config import settings

TEMPLATE = Path(settings.PREVIEW_TEMPLATE_DIR)
IDENTITY = TEMPLATE / "src" / "lib" / "motion-identity.ts"
PRESETS = TEMPLATE / "src" / "ui" / "motion" / "presets.tsx"
ANIME = TEMPLATE / "src" / "ui" / "motion" / "AnimeChrome.tsx"
ANIME_DRIVER = TEMPLATE / "src" / "ui" / "motion" / "anime.ts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_both_engines_read_the_one_identity() -> None:
    """One source of truth: motion/react and anime.js both consume the same
    resolved identity — two engines, one temperament."""
    for path in (PRESETS, ANIME_DRIVER):
        assert "from '../../lib/motion-identity'" in _read(path), (
            f"{path.name} no longer imports the motion identity — "
            "its constants have gone back to being hardcoded"
        )


def test_presets_derive_from_identity_not_literals() -> None:
    source = _read(PRESETS)
    assert "const easeOut: Transition['ease'] = identity.ease;" in source
    assert "staggerChildren: identity.staggerMs / 1000" in source
    assert "delay: 0.05 + i * (identity.staggerMs / 750)" in source
    assert "y: 18 * travel" in source
    # The legacy ease literal may live ONLY in the accessor's fallback — a
    # copy here means presets stopped following the recipe.
    assert "[0.22, 1, 0.36, 1]" not in source, (
        "presets.tsx re-hardcodes the legacy ease — the identity is unwired"
    )


def test_anime_driver_scales_by_rhythm_and_gates_the_ease() -> None:
    source = _read(ANIME_DRIVER)
    assert "export const motionRhythm" in source
    for anchor in (
        "duration = 1100 * motionRhythm.tempo",
        "y = 42 * motionRhythm.travel",
        "staggerMs = 110 * motionRhythm.pace",
        "duration = 920 * motionRhythm.tempo",
        "y = 56 * motionRhythm.travel",
    ):
        assert anchor in source, f"anime.ts default re-hardcoded: {anchor}"
    # The anime voice 'out(3)' belongs to un-authored pages only; authored
    # recipes speak their own cubic-bezier.
    assert re.search(
        r"motionIsAuthored\(\)\s*\?\s*`cubicBezier\(\$\{identity\.ease\.join\(','\)\}\)`\s*:\s*'out\(3\)'",
        source,
    ), "anime ease is no longer gated on motionIsAuthored()"


def test_anime_chrome_call_sites_follow_the_rhythm() -> None:
    source = _read(ANIME)
    for anchor in (
        "const delayStep = 160 * motionRhythm.pace;",
        "y: 48 * motionRhythm.travel",
        "duration: 1200 * motionRhythm.tempo",
        "staggerMs: 120 * motionRhythm.pace, y: 40 * motionRhythm.travel",
    ):
        assert anchor in source, f"AnimeChrome call-site re-hardcoded: {anchor}"


def test_the_ratio_base_is_the_accessor_default() -> None:
    """Every ratio divides by the legacy base (18px travel, 90ms stagger),
    which must equal DEFAULT_IDENTITY — drift here silently changes every
    bare-recipe page."""
    source = _read(IDENTITY)
    default = source.split("const DEFAULT_IDENTITY", 1)[1].split("};", 1)[0]
    assert "ease: [0.22, 1, 0.36, 1]" in default
    assert "staggerMs: 90" in default
    assert "travel: '18px'" in default
    assert "export function motionIsAuthored()" in source
    assert "raw.identity !== 'entrance-only'" in source


def test_extreme_staggers_cannot_stretch_durations_unbounded() -> None:
    """tempo is clamped in both engines: a 130ms nocturne drift may run 1.4x,
    never longer — jank protection until 3.11 measures for real."""
    clamp = "Math.min(1.4, Math.max(0.45, identity.staggerMs / 90))"
    assert clamp in _read(PRESETS)
    assert clamp in _read(ANIME_DRIVER)


if __name__ == "__main__":
    test_both_engines_read_the_one_identity()
    test_presets_derive_from_identity_not_literals()
    test_anime_driver_scales_by_rhythm_and_gates_the_ease()
    test_anime_chrome_call_sites_follow_the_rhythm()
    test_the_ratio_base_is_the_accessor_default()
    test_extreme_staggers_cannot_stretch_durations_unbounded()
    print("Motion wiring tests passed (6 tests)")
