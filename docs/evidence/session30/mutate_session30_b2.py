#!/usr/bin/env python3
"""Mutation sweep for Stage B batch 2 + motion identity (3.10 data half).

Anchors verbatim, occurrence-counted. TS behavior is pinned by text-level
pytests (no TS runner in the suite), so TS mutations anchor on pinned lines.

Run inside the test container:
  docker run --rm -v "$PWD:/repo" -w /repo/backend \
    -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template \
    --entrypoint sh bmv-local-api -c \
    'pip install -q pytest; python /repo/docs/evidence/session30/mutate_session30_b2.py'
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path("/repo")
RECIPES_PY = REPO / "backend/app/application/preview_app/design_recipes.py"
SITE = REPO / "backend/app/application/preview_app/site_design.py"
MOTION_TS = REPO / "backend/preview-template/src/lib/motion-identity.ts"
DOTS = REPO / "backend/preview-template/src/ui/effects/DotPattern.tsx"
MANIFEST = REPO / "backend/preview-template/PROVENANCE.json"

T_SITE = ["tests/preview_app/test_site_design.py"]
T_FOUNDRY = ["tests/preview_app/test_foundry_components.py"]
T_GUARDS = [
    "tests/preview_app/test_foundry_components.py",
    "tests/preview_app/test_provenance_guards.py",
]

MUT: list[tuple[str, Path, list[str], int, str, str]] = [
    ("B1 two families share a motion identity", RECIPES_PY, T_SITE, 1,
     '            "identity": "nocturne-drift",',
     '            "identity": "editorial-calm",'),
    ("B2 ops restraint broken (floor staggers like marketing)", RECIPES_PY, T_SITE, 1,
     '            "identity": "ops-floor-instant",\n            "ease": [0.4, 0.0, 0.2, 1.0],\n            "stagger_ms": 35,',
     '            "identity": "ops-floor-instant",\n            "ease": [0.4, 0.0, 0.2, 1.0],\n            "stagger_ms": 135,'),
    ("B3 resolution ignores authored motion", SITE, T_SITE, 1,
     "    if isinstance(recipe_motion, dict):",
     "    if False:"),
    ("B4 accessor stops validating ease", MOTION_TS, T_FOUNDRY, 1,
     "    ease: isEase(raw.ease) ? raw.ease : DEFAULT_IDENTITY.ease,",
     "    ease: (raw.ease ?? DEFAULT_IDENTITY.ease) as [number, number, number, number],"),
    ("B5 randomness sneaks into a mined effect", DOTS, T_FOUNDRY, 1,
     "        const delay = ((i * 37) % 50) / 10;",
     "        const delay = Math.random() * 5;"),
    ("B6 a mined file loses its provenance row", MANIFEST, T_GUARDS, 1,
     '    "path": "src/ui/effects/NumberTicker.tsx",',
     '    "path": "src/ui/effects/NumberTickerRenamed.tsx",'),
    ("B7 an effect goes unregistered behind the manifest", MANIFEST, T_GUARDS, 1,
     '    "path": "src/ui/effects/VelocityScroll.tsx",',
     '    "path": "src/ui/lib/cn.ts",'),
]


def run(tests: list[str]) -> bool:
    return (
        subprocess.run(
            [sys.executable, "-m", "pytest", *tests, "-q", "-x", "--no-header"],
            cwd=str(REPO / "backend"),
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def main() -> None:
    all_tests = sorted({t for _, _, tests, _, _, _ in MUT for t in tests})
    if not run(all_tests):
        print("baseline RED — fix the tests before sweeping")
        raise SystemExit(2)
    print(f"baseline green; {len(MUT)} mutations\n")

    originals = {p: p.read_text(encoding="utf-8") for p in {m[1] for m in MUT}}
    survivors: list[str] = []
    try:
        for label, target, tests, count, old, new in MUT:
            source = originals[target]
            found = source.count(old)
            if found != count:
                print(f"  MISCOUNT  {label} — anchor x{found}, expected x{count}")
                survivors.append(label)
                continue
            target.write_text(source.replace(old, new), encoding="utf-8")
            killed = not run(tests)
            print(f"  {'kill' if killed else 'SURVIVED'}  {label}")
            if not killed:
                survivors.append(label)
            target.write_text(source, encoding="utf-8")
    finally:
        for path, text in originals.items():
            path.write_text(text, encoding="utf-8")

    print(f"\n{len(MUT) - len(survivors)} killed / {len(survivors)} survived")
    for label in survivors:
        print("  survivor:", label)
    raise SystemExit(1 if survivors else 0)


if __name__ == "__main__":
    main()
