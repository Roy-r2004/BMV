#!/usr/bin/env python3
"""Board-design emitter — the silhouette harness's chain, all three files.

The frozen gate script (`silhouette_snapshot.py`) copies only the two files
it hashes. The motion boards also need `site-design.ts` (the temperament
rides in it), so this emitter IMPORTS the frozen module — same brief, same
production chain, zero duplicated resolution logic — and copies the full
write_index_css output per recipe. The gate script itself stays untouched.

Run inside the api image (see build_motion_boards.py).
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/repo/backend")

_spec = importlib.util.spec_from_file_location(
    "silhouette_snapshot", "/repo/docs/evidence/session30/silhouette_snapshot.py"
)
assert _spec and _spec.loader
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)

from app.application.preview_app.assemble import write_index_css  # noqa: E402
from app.application.preview_app.design_recipes import RECIPES, get_recipe  # noqa: E402
from app.infrastructure.templating.renderer import JinjaTemplateRenderer  # noqa: E402

BOARD_FILES = ("src/index.css", "src/lib/site-design.ts", "src/lib/recipe-id.ts")


def main() -> int:
    out_root = Path(sys.argv[1])
    out_root.mkdir(parents=True, exist_ok=True)
    for recipe_id in sorted(RECIPES):
        plan = harness._production_design_system(recipe_id)
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "src").mkdir(parents=True, exist_ok=True)
            write_index_css(
                ws,
                harness.PRIMARY,
                harness.SECONDARY,
                harness.FONT,
                JinjaTemplateRenderer(),
                recipe=get_recipe(recipe_id),
                design_system=plan.get("design_system") or {},
            )
            case_dir = out_root / f"prod-{recipe_id}"
            case_dir.mkdir(parents=True, exist_ok=True)
            for rel in BOARD_FILES:
                (case_dir / Path(rel).name).write_bytes((ws / rel).read_bytes())
    print(f"emitted {len(RECIPES)} board designs -> {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
