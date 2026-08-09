#!/usr/bin/env python3
"""Mutation sweep for the 3.10 consumption half — motion engines wired.

Each mutation re-hardcodes one wired constant or breaks one parity guard;
the kill proves the wiring pins actually hold the temperament in place.
Anchors verbatim, occurrence-counted (`replace` swaps every occurrence).

Run inside the test container:
  docker run --rm -v "$PWD:/repo" -w /repo/backend \
    -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template \
    --entrypoint sh bmv-local-api -c \
    'pip install -q pytest; python /repo/docs/evidence/session30/mutate_session30_b4_wiring.py'
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path("/repo")
IDENTITY = REPO / "backend/preview-template/src/lib/motion-identity.ts"
PRESETS = REPO / "backend/preview-template/src/ui/motion/presets.tsx"
CHROME = REPO / "backend/preview-template/src/ui/motion/AnimeChrome.tsx"
DRIVER = REPO / "backend/preview-template/src/ui/motion/anime.ts"

T_WIRING = ["tests/preview_app/test_motion_wiring.py"]

MUT: list[tuple[str, Path, list[str], int, str, str]] = [
    ("W1 presets stagger re-hardcoded to 0.09", PRESETS, T_WIRING, 1,
     "staggerChildren: identity.staggerMs / 1000",
     "staggerChildren: 0.09"),
    ("W2 presets ease reverts to the legacy literal", PRESETS, T_WIRING, 1,
     "const easeOut: Transition['ease'] = identity.ease;",
     "const easeOut: Transition['ease'] = [0.22, 1, 0.36, 1];"),
    ("W3 anime ease gate dropped — bare pages change voice", DRIVER, T_WIRING, 1,
     "const easeOut = motionIsAuthored()\n  ? `cubicBezier(${identity.ease.join(',')})`\n  : 'out(3)';",
     "const easeOut = `cubicBezier(${identity.ease.join(',')})`;"),
    ("W4 AnimeChrome stagger descaled", CHROME, T_WIRING, 1,
     "staggerMs: 120 * motionRhythm.pace, y: 40 * motionRhythm.travel",
     "staggerMs: 120, y: 40"),
    ("W5 ratio base drifts from the accessor default", IDENTITY, T_WIRING, 1,
     "staggerMs: 90,",
     "staggerMs: 80,"),
    ("W6 tempo clamp dropped in the driver", DRIVER, T_WIRING, 1,
     "tempo: Math.min(1.4, Math.max(0.45, identity.staggerMs / 90)),",
     "tempo: identity.staggerMs / 90,"),
    ("W7 hero delay step re-hardcoded", PRESETS, T_WIRING, 1,
     "delay: 0.05 + i * (identity.staggerMs / 750),",
     "delay: 0.05 + i * 0.12,"),
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
