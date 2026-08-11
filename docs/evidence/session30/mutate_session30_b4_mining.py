#!/usr/bin/env python3
"""Mutation sweep for Stage B / batch 4 — the last Lenis-free primitives.

Same harness as the batch-3 sweep: anchors verbatim, occurrence-counted,
every mutation aimed at a specific pin.

Run inside the test container:
  docker run --rm -v "$PWD:/repo" -w /repo/backend \
    -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template \
    --entrypoint sh bmv-local-api -c \
    'pip install -q pytest; python /repo/docs/evidence/session30/mutate_session30_b4_mining.py'
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path("/repo")
MANIFEST = REPO / "backend/preview-template/PROVENANCE.json"
REGISTRY = REPO / "backend/preview-template/src/ui/registry.ts"
BARREL = REPO / "backend/preview-template/src/ui/index.ts"
SHIMMER = REPO / "backend/preview-template/src/ui/effects/ShimmerButton.tsx"
GRID = REPO / "backend/preview-template/src/ui/effects/AnimatedGridPattern.tsx"
PROGRESS = REPO / "backend/preview-template/src/ui/effects/ScrollProgress.tsx"

T_FOUNDRY = ["tests/preview_app/test_foundry_components.py"]

SHIMMER_ROW = """  {
    "path": "src/ui/effects/ShimmerButton.tsx",
    "source_repo": "https://github.com/magicuidesign/magicui",
    "source_path": "apps/www/registry/magicui/shimmer-button.tsx",
    "source_commit": "5543371f99eaa6d1549a8dec864e78ee0b4515f2",
    "license": "MIT",
    "license_url": "https://github.com/magicuidesign/magicui/blob/5543371f99eaa6d1549a8dec864e78ee0b4515f2/LICENSE.md",
    "retrieved": "2026-08-09",
    "rewritten": true,
    "rewrite_notes": "NOT grafted into core/Button — ops surfaces keep a chrome-free Button by the restraint rule; upstream config keyframes (shimmer-slide + spin-around) and container queries became one motion-driven sweep; black/white hardcodes became brand/card tokens; radius rides --radius-ui; reduced motion renders the resting button",
    "recipe_personalities": ["bold-retail", "warm-service", "nocturne"]
  },
"""

GRID_ENTRY = """  {
    name: 'AnimatedGridPattern',
    surface: 'public',
    path: 'effects/AnimatedGridPattern.tsx',
    requiredProps: [],
    optionalProps: ['width', 'height', 'numSquares', 'maxOpacity', 'duration', 'className'],
  },
"""

MUT: list[tuple[str, Path, list[str], int, str, str]] = [
    ("B4-1 ShimmerButton loses its provenance row", MANIFEST, T_FOUNDRY, 1,
     SHIMMER_ROW,
     ""),
    ("B4-2 grid scatter re-randomized", GRID, T_FOUNDRY, 1,
     "const squareX = Math.floor(hash01(index, cycle) * cols);",
     "const squareX = Math.floor(Math.random() * cols);"),
    ("B4-3 ScrollProgress hardcodes upstream's violet gradient", PROGRESS, T_FOUNDRY, 1,
     "'linear-gradient(to right, var(--color-brand), var(--color-accent))'",
     "'linear-gradient(to right, #A97CF8, #FDCC92)'"),
    ("B4-4 ShimmerButton animates but drops the reduced-motion guard", SHIMMER, T_FOUNDRY, 2,
     "useMotionSafe",
     "motionGuard"),
    ("B4-5 AnimatedGridPattern manifested but unregistered", REGISTRY, T_FOUNDRY, 1,
     GRID_ENTRY,
     ""),
    ("B4-6 ScrollProgress registered but not barrel-exported", BARREL, T_FOUNDRY, 1,
     "  ScrollProgress,\n",
     ""),
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
