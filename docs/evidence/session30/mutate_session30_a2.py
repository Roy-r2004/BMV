#!/usr/bin/env python3
"""Mutation sweep for Stage A / A2 — enum broken, props honoured, 'split' deleted.

The template's behavior is pinned by text-level pytests (no TS test runner in
this suite), so every mutation anchors on a pinned load-bearing string; the
kill proves the pin actually guards it. Anchors verbatim, occurrence-counted.

One equivalent-mutant class is recorded rather than forced: swapping the
Python emitter's ds-vs-recipe variant SOURCE (e.g. `ds.get("hero_variant")` ->
`ds.get("footer_variant")`) is unkillable today because the sealed
design_system's variants and the recipe's are value-identical on every chain
until Stage D varies them — the A1 pin (variants == recipe.ts maps) holds
either way. Data: 8/8 recipes emit identical variants from both sources.

Run inside the test container:
  docker run --rm -v "$PWD:/repo" -w /repo/backend \
    -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template \
    --entrypoint sh bmv-local-api -c \
    'pip install -q pytest; python /repo/docs/evidence/session30/mutate_session30_a2.py'
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path("/repo")
RECIPE = REPO / "backend/preview-template/src/lib/recipe.ts"
HERO = REPO / "backend/preview-template/src/ui/public/MarketingHero.tsx"
BENTO = REPO / "backend/preview-template/src/ui/public/FeatureBento.tsx"
REGISTRY = REPO / "backend/preview-template/src/ui/registry.ts"
CATALOGUE = REPO / "backend/preview-template/src/ui/catalogue.json"

T_CONSUME = ["tests/preview_app/test_recipe_variant_consumption.py"]
T_CONSUME_DRIFT = [
    "tests/preview_app/test_recipe_variant_consumption.py",
    "tests/preview_app/test_ui_catalogue_drift.py",
]
T_SITE = ["tests/preview_app/test_site_design.py"]

MUT: list[tuple[str, Path, list[str], int, str, str]] = [
    ("T1 hero accessor bypasses SITE_DESIGN", RECIPE, T_CONSUME, 1,
     "  return designVariant(SITE_DESIGN.variants.hero, HERO_VARIANTS, recipeId) ?? HERO_BY_RECIPE[recipeId];",
     "  return HERO_BY_RECIPE[recipeId];"),
    ("T2 design answers for other sites' recipes", RECIPE, T_CONSUME, 1,
     "  if (normalizeRecipeId(SITE_DESIGN.recipe_id) !== recipeId) return null;",
     "  if (false) return null;"),
    ("T3 validity guard dropped, any string renders", RECIPE, T_CONSUME, 1,
     "  return value != null && (valid as readonly string[]).includes(value) ? (value as T) : null;",
     "  return (value ?? null) as T | null;"),
    ("T4 hero honours only 'item' again", HERO, T_CONSUME, 1,
     "    variantProp && (variantProp === 'item' || (HERO_VARIANTS as readonly string[]).includes(variantProp))",
     "    variantProp && variantProp === 'item'"),
    ("T5 bento guard removed, discard returns", BENTO, T_CONSUME, 1,
     "    variantProp && (FEATURE_VARIANTS as readonly string[]).includes(variantProp)",
     "    false"),
    ("T6 registry resurrects 'split' on the component", REGISTRY, T_CONSUME_DRIFT, 1,
     "    variants: { variant: ['cinematic', 'service', 'compact', 'product', 'editorial', 'atelier', 'item'] },",
     "    variants: { variant: ['cinematic', 'service', 'compact', 'product', 'editorial', 'atelier', 'split', 'item'] },"),
    ("T7 catalogue.json hand-edited behind the registry", CATALOGUE, T_CONSUME, 1,
     '"MarketingHero": [\n          "editorial"\n        ]',
     '"MarketingHero": [\n          "editorial",\n          "split"\n        ]'),
    ("T8 footer map loses a family", RECIPE, T_CONSUME, 1,
     "  craft: 'columns',",
     ""),
    ("T9 emitted hero variant leaves the valid set", REPO / "backend/app/application/preview_app/site_design.py", T_CONSUME + T_SITE, 1,
     '            "hero": ds.get("hero_variant") or resolved.get("hero_variant") or None,',
     '            "hero": "sideways",'),
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
