#!/usr/bin/env python3
"""Stage-A silhouette gate — CSS custom-property output per recipe, hashed.

Renders index.css through the REAL production chain (brand brief -> recipe ->
overlay -> sealed brief -> write_index_css) for every recipe on one fixed
brief, plus the bare-design_system fallback path both write_index_css callers
can reach. Byte-identical output before/after Stage A is the no-regression
proof (the plan's gate: Stage A is plumbing; if it changes what any recipe
looks like today, that is a Stage A defect).

Run inside the api image (imports app.*):

    docker run --rm -v "$PWD:/repo" -v <outdir>:/out -w /repo/backend \
      -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template \
      --entrypoint python bmv-local-api \
      /repo/docs/evidence/session30/silhouette_snapshot.py /out/before

Compare runs with: diff -r <out>/before <out>/after  (manifest.json carries
sha256 per case; the css files themselves are kept for byte diffs).
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/repo/backend")

from app.application.preview_app.brand_brief import (  # noqa: E402
    apply_brief_to_plan,
    build_brand_brief,
)
from app.application.preview_app.design_brief import (  # noqa: E402
    apply_sealed_brief_to_plan,
    seal_design_brief,
)
from app.application.preview_app.design_overlay import (  # noqa: E402
    apply_design_overlay_to_plan,
)
from app.application.preview_app.design_recipes import (  # noqa: E402
    RECIPES,
    apply_recipe_to_plan,
    get_recipe,
)
from app.application.preview_app.assemble import write_index_css  # noqa: E402
from app.infrastructure.templating.renderer import (  # noqa: E402
    JinjaTemplateRenderer,
)

# One fixed brief. Values are arbitrary but FROZEN — the gate compares
# before/after under identical inputs, so never edit these mid-stage.
BRIEF = {
    "business_name": "Stage A Gate Bakery",
    "industry": "bakery",
    "business_description": (
        "Neighbourhood sourdough bakery with a small pastry case, "
        "morning coffee counter, and weekend baking workshops."
    ),
    "seed": 30,
}
PRIMARY = "#0f766e"
SECONDARY = "#134e4a"
FONT = "Source Sans 3"


def _production_design_system(recipe_id: str) -> dict:
    """The plan_phase layer order for the CSS-relevant lanes, recipe forced."""
    brief = build_brand_brief(
        {},
        business_name=BRIEF["business_name"],
        industry=BRIEF["industry"],
        business_description=BRIEF["business_description"],
        seed=BRIEF["seed"],
    )
    plan: dict = {"design_system": {}}
    plan = apply_brief_to_plan(plan, brief)
    plan = apply_recipe_to_plan(
        plan,
        industry=BRIEF["industry"],
        business_description=BRIEF["business_description"],
        concept_name=BRIEF["business_name"],
        seed=BRIEF["seed"],
        recipe_id=recipe_id,
    )
    plan = apply_design_overlay_to_plan(
        plan,
        seed=BRIEF["seed"],
        context=BRIEF["business_description"],
        industry=BRIEF["industry"],
        business_name=BRIEF["business_name"],
    )
    sealed = seal_design_brief(plan, brand_brief=brief)
    plan = apply_sealed_brief_to_plan(plan, sealed)
    return plan


def _render_case(case: str, recipe: dict | None, design_system: dict, out_root: Path) -> dict:
    renderer = JinjaTemplateRenderer()
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "src").mkdir(parents=True, exist_ok=True)
        write_index_css(
            ws,
            PRIMARY,
            SECONDARY,
            FONT,
            renderer,
            recipe=recipe,
            design_system=design_system,
        )
        hashes: dict[str, str] = {}
        case_dir = out_root / case
        case_dir.mkdir(parents=True, exist_ok=True)
        for rel in ("src/index.css", "src/lib/recipe-id.ts"):
            path = ws / rel
            if not path.is_file():
                hashes[rel] = "MISSING"
                continue
            data = path.read_bytes()
            hashes[rel] = hashlib.sha256(data).hexdigest()
            (case_dir / Path(rel).name).write_bytes(data)
        return hashes


def main() -> int:
    out_root = Path(sys.argv[1] if len(sys.argv) > 1 else "silhouettes/out")
    out_root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}

    for recipe_id in sorted(RECIPES):
        recipe = get_recipe(recipe_id)
        # Production path: full layer chain, sealed design_system.
        plan = _production_design_system(recipe_id)
        manifest[f"prod-{recipe_id}"] = _render_case(
            f"prod-{recipe_id}", recipe, plan.get("design_system") or {}, out_root
        )
        # Fallback path both callers can reach: recipe only, empty design_system.
        manifest[f"bare-{recipe_id}"] = _render_case(
            f"bare-{recipe_id}", recipe, {}, out_root
        )

    # No-recipe default (write_index_css(recipe=None) -> warm-service).
    manifest["default-none"] = _render_case("default-none", None, {}, out_root)

    (out_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"cases: {len(manifest)} -> {out_root}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
