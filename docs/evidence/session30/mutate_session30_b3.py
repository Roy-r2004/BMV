#!/usr/bin/env python3
"""Mutation sweep for Stage B / batch 3 — six more mined primitives.

Every mutation anchors on a pinned load-bearing string; the kill proves the
pin actually guards it. Anchors verbatim, occurrence-counted (`replace` swaps
every occurrence, so the count is asserted first; MISCOUNT != SKIP).

New pin under test this batch: effects may never smuggle CSS keyframes
(`@keyframes` / `animation-name:` / `animation-play-state:`) — mined
animation is motion-driven. Marquee is the precedent: upstream's
Tailwind-config `animate-marquee` became a frame loop.

Run inside the test container:
  docker run --rm -v "$PWD:/repo" -w /repo/backend \
    -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template \
    --entrypoint sh bmv-local-api -c \
    'pip install -q pytest; python /repo/docs/evidence/session30/mutate_session30_b3.py'
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path("/repo")
MANIFEST = REPO / "backend/preview-template/PROVENANCE.json"
REGISTRY = REPO / "backend/preview-template/src/ui/registry.ts"
BARREL = REPO / "backend/preview-template/src/ui/index.ts"
MARQUEE = REPO / "backend/preview-template/src/ui/effects/Marquee.tsx"
FLICKER = REPO / "backend/preview-template/src/ui/effects/FlickeringGrid.tsx"
MAGIC = REPO / "backend/preview-template/src/ui/effects/MagicCard.tsx"
LENS = REPO / "backend/preview-template/src/ui/effects/Lens.tsx"

T_FOUNDRY = ["tests/preview_app/test_foundry_components.py"]
T_PROV = ["tests/preview_app/test_provenance_guards.py"]

MARQUEE_ROW = """  {
    "path": "src/ui/effects/Marquee.tsx",
    "source_repo": "https://github.com/magicuidesign/magicui",
    "source_path": "apps/www/registry/magicui/marquee.tsx",
    "source_commit": "5543371f99eaa6d1549a8dec864e78ee0b4515f2",
    "license": "MIT",
    "license_url": "https://github.com/magicuidesign/magicui/blob/5543371f99eaa6d1549a8dec864e78ee0b4515f2/LICENSE.md",
    "retrieved": "2026-08-09",
    "rewritten": true,
    "rewrite_notes": "upstream Tailwind-config animate-marquee keyframes became a motion-driven frame loop (no new CSS), sharing VelocityScroll's wrap math; pause-on-hover is a ref the loop reads instead of animation-play-state; vertical mode dropped (no kit consumer); reduced motion renders one static row",
    "recipe_personalities": ["bold-retail", "craft", "warm-service"]
  },
"""

LENS_ENTRY = """  {
    name: 'Lens',
    surface: 'public',
    path: 'effects/Lens.tsx',
    requiredProps: ['children'],
    optionalProps: ['zoomFactor', 'lensSize', 'ariaLabel', 'className'],
  },
"""

MUT: list[tuple[str, Path, list[str], int, str, str]] = [
    ("B3-1 mined file loses its provenance row", MANIFEST, T_FOUNDRY, 1,
     MARQUEE_ROW,
     ""),
    ("B3-2 FlickeringGrid re-rolls with Math.random", FLICKER, T_FOUNDRY, 1,
     "squares[i] = hash01(i ^ 0x517cc1b7, t) * maxOpacity;",
     "squares[i] = Math.random() * maxOpacity;"),
    ("B3-3 MagicCard hardcodes upstream's violet", MAGIC, T_FOUNDRY, 1,
     "color-mix(in srgb, var(--color-brand) 70%, transparent),",
     "#9E7AFF,"),
    ("B3-4 Marquee smuggles CSS keyframes back in", MARQUEE, T_FOUNDRY, 1,
     '"flex w-max items-center will-change-transform"',
     '"flex w-max items-center will-change-transform [animation-name:marquee]"'),
    ("B3-5 Lens animates but drops the reduced-motion guard", LENS, T_FOUNDRY, 2,
     "useMotionSafe",
     "motionGuard"),
    ("B3-6 Lens manifested but unregistered", REGISTRY, T_FOUNDRY, 1,
     LENS_ENTRY,
     ""),
    ("B3-7 Lens registered but not barrel-exported", BARREL, T_FOUNDRY, 1,
     "  Lens,\n",
     ""),
    ("B3-8 provenance pin truncated to a short sha", MANIFEST, T_PROV, 1,
     '"source_path": "apps/www/registry/magicui/marquee.tsx",\n    "source_commit": "5543371f99eaa6d1549a8dec864e78ee0b4515f2",',
     '"source_path": "apps/www/registry/magicui/marquee.tsx",\n    "source_commit": "5543371f",'),
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
