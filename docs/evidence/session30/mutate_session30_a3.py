#!/usr/bin/env python3
"""Mutation sweep for Stage A / A3 — compatible_recipes consumption.

Anchors verbatim, occurrence-counted. One equivalent class recorded, not
forced: `data["compatible_recipes"] = …` -> `setdefault(…)` cannot be killed
because zero packs author the field (the never-author pin guards that half),
and `compatible_recipes_for`'s unknown-id default cannot fire while the
map-corpus pin holds set equality over pack ids.

Run inside the test container:
  docker run --rm -v "$PWD:/repo" -w /repo/backend \
    -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template \
    --entrypoint sh bmv-local-api -c \
    'pip install -q pytest; python /repo/docs/evidence/session30/mutate_session30_a3.py'
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path("/repo")
RECIPES_PY = REPO / "backend/app/application/preview_app/design_recipes.py"
LOADER = REPO / "backend/app/application/preview_app/industry_templates/loader.py"
MAP = REPO / "backend/app/application/preview_app/industry_templates/compatible_recipes.py"

T_CONSUME = ["tests/preview_app/test_compatible_recipes_consumption.py"]
T_ALL = [
    "tests/preview_app/test_compatible_recipes_consumption.py",
    "tests/preview_app/test_compatible_recipes_map.py",
    "tests/preview_app/test_oneshot_quality_pack.py",
]

MUT: list[tuple[str, Path, list[str], int, str, str]] = [
    ("R1 fallback rotates all eight again", RECIPES_PY, T_CONSUME, 1,
     "        return MARKETING_RECIPE_IDS[(seed or 0) % len(MARKETING_RECIPE_IDS)]",
     "        order = list(RECIPES.keys())\n        return order[(seed or 0) % len(order)]"),
    ("R2 rotation freezes on one recipe", RECIPES_PY, T_CONSUME, 1,
     "        return MARKETING_RECIPE_IDS[(seed or 0) % len(MARKETING_RECIPE_IDS)]",
     "        return MARKETING_RECIPE_IDS[0]"),
    ("R3 loader stops stamping packs", LOADER, T_CONSUME, 1,
     '        data["compatible_recipes"] = list(compatible_recipes_for(tid))',
     "        pass"),
    ("R4 marketing set loses craft", MAP, T_ALL, 1,
     '    "nocturne",\n    "craft",\n)',
     '    "nocturne",\n)'),
    ("R5 keyword path bypassed, everything falls back", RECIPES_PY, T_ALL, 1,
     "    best = max(scores.values())\n    if best <= 0:",
     "    best = max(scores.values())\n    if True:"),
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
