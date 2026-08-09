"""Stage B foundry — mined components stay coherent with the kit's contracts.

The drift test's own history note: CatalogGrid/InquiryPanel were once added
to catalogue.json and index.ts but not the registry. The inverse hole is a
component registered but never exported from `src/ui` — advertised to
codegen, unimportable by pages. Batch 1 closes both directions for every
registry component, and pins the two house rules every mined file must obey:
reduced-motion parity and tokens-not-hex.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.provenance import load_manifest
from app.application.ui_registry import build_catalogue_from_registry
from app.core.config import settings

TEMPLATE = Path(settings.PREVIEW_TEMPLATE_DIR)
EFFECTS_DIR = TEMPLATE / "src" / "ui" / "effects"


def _barrel_exported_names() -> set[str]:
    source = (TEMPLATE / "src" / "ui" / "index.ts").read_text(encoding="utf-8")
    names: set[str] = set()
    for block in re.findall(r"export \{(.*?)\} from", source, re.S):
        for token in block.split(","):
            token = token.strip()
            if not token or token.startswith("type "):
                continue
            names.add(token)
    return names


def test_every_registry_component_is_importable_from_the_barrel() -> None:
    exported = _barrel_exported_names()
    missing = [
        c["name"]
        for c in build_catalogue_from_registry()["components"]
        if c["name"] not in exported
    ]
    assert missing == [], (
        f"registered but not exported from src/ui: {missing} — "
        "advertised to codegen, unimportable by pages"
    )


def test_every_registry_component_file_exists() -> None:
    missing = [
        c["name"]
        for c in build_catalogue_from_registry()["components"]
        if not (TEMPLATE / "src" / "ui" / c["path"]).is_file()
    ]
    assert missing == []


def test_every_mined_effect_is_manifested_and_motion_safe() -> None:
    """Foundry rules per file: a provenance row exists, reduced motion is
    honoured (useMotionSafe), and no hardcoded hex colors — mined code rides
    the token pipe or it re-imports the sameness it was mined to break."""
    manifested = {str(r.get("path") or "") for r in load_manifest()}
    files = sorted(EFFECTS_DIR.glob("*.tsx"))
    assert files, "batch 1 landed effects — the directory cannot be empty"
    for path in files:
        rel = f"src/ui/effects/{path.name}"
        assert rel in manifested, f"{rel} has no provenance row"
        source = path.read_text(encoding="utf-8")
        # Reduced-motion parity is required exactly where motion exists —
        # a static component (no motion/react import) has nothing to guard.
        if "motion/react" in source:
            assert "useMotionSafe" in source, f"{rel} animates but ignores reduced motion"
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", source), (
            f"{rel} hardcodes a hex color — rewrite onto tokens"
        )
        assert "Math.random" not in source, (
            f"{rel} uses Math.random — the screenshot critic must see the "
            "same frame twice; seed by index instead"
        )
        assert not re.search(r"@keyframes|animation(?:-name|-play-state)?\s*:", source), (
            f"{rel} smuggles CSS keyframes — mined animation is motion-driven "
            "(batch 3's Marquee is the precedent: upstream animate-marquee "
            "became a frame loop)"
        )


def test_motion_identity_accessor_guards_and_falls_back() -> None:
    """`motionIdentity()` reads emitted data, so it must validate every field
    and fall back to the kit's entrance constants — same discipline as the
    variant axes. And it must have real consumers, not be a dead lane."""
    lib = (TEMPLATE / "src" / "lib" / "motion-identity.ts").read_text(encoding="utf-8")
    assert "function isEase(value: unknown)" in lib
    assert "value.length === 4" in lib
    assert "const DEFAULT_IDENTITY: MotionIdentity" in lib
    assert "isEase(raw.ease) ? raw.ease : DEFAULT_IDENTITY.ease" in lib
    consumers = [
        p.name
        for p in EFFECTS_DIR.glob("*.tsx")
        if "motionIdentity()" in p.read_text(encoding="utf-8")
    ]
    assert len(consumers) >= 2, f"motion identity has too few consumers: {consumers}"


def test_every_manifested_component_row_is_registered() -> None:
    """The other direction: a mined file that skips the registry is invisible
    to codegen — manifest rows and registry entries move together."""
    registered_paths = {
        c["path"] for c in build_catalogue_from_registry()["components"]
    }
    for row in load_manifest():
        if str(row.get("kind") or "component") != "component":
            continue
        rel = str(row.get("path") or "")
        assert rel.removeprefix("src/ui/") in registered_paths, (
            f"{rel} is manifested but not registered in registry.ts"
        )


if __name__ == "__main__":
    test_every_registry_component_is_importable_from_the_barrel()
    test_every_registry_component_file_exists()
    test_every_mined_effect_is_manifested_and_motion_safe()
    test_motion_identity_accessor_guards_and_falls_back()
    test_every_manifested_component_row_is_registered()
    print("Foundry component tests passed (5 tests)")
