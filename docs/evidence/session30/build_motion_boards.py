#!/usr/bin/env python3
"""Motion boards — one template build per recipe, viewable in a browser.

Stage C's sign-off needs the owner to SEE the eight temperaments, and
screenshots cannot show a 35ms ops tick against a 130ms nocturne drift.
This script builds the living version, with zero AI calls and zero new
dependencies: the silhouette harness emits every recipe's resolved design
(index.css + site-design.ts + recipe-id.ts) on the frozen Stage-A brief —
same brand, eight temperaments — and the template builds once per recipe.

Output: <repo>/boards/ (gitignored). View with:
    cd boards && python3 -m http.server 8930
    open http://localhost:8930/

Run from the repo root on the host (needs docker + the template's
node_modules, both already present):
    python3 docs/evidence/session30/build_motion_boards.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TEMPLATE = REPO / "backend" / "preview-template"
BOARDS = REPO / "boards"
DESIGNS = BOARDS / ".designs"

# The three files write_index_css owns, template-relative.
DESIGN_FILES = {
    "index.css": "src/index.css",
    "site-design.ts": "src/lib/site-design.ts",
    "recipe-id.ts": "src/lib/recipe-id.ts",
}


def run(cmd: list[str], cwd: Path | None = None) -> None:
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None)
    if result.returncode != 0:
        raise SystemExit(f"command failed ({result.returncode}): {' '.join(cmd)}")


def restore_template() -> None:
    run(
        ["git", "-C", str(REPO), "checkout", "--"]
        + [f"backend/preview-template/{rel}" for rel in DESIGN_FILES.values()]
    )


def main() -> None:
    if BOARDS.exists():
        shutil.rmtree(BOARDS)
    BOARDS.mkdir()

    print("emitting per-recipe designs (silhouette chain, no AI) ...")
    run([
        "docker", "run", "--rm",
        "-v", f"{REPO}:/repo",
        "-w", "/repo/backend",
        "-e", "PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template",
        "--entrypoint", "python",
        "bmv-local-api",
        "/repo/docs/evidence/session30/emit_board_designs.py",
        "/repo/boards/.designs",
    ])

    prod_cases = sorted(p for p in DESIGNS.iterdir() if p.name.startswith("prod-"))
    if not prod_cases:
        raise SystemExit("no prod-* cases emitted — silhouette harness changed shape?")

    identities: dict[str, dict] = {}
    try:
        for case_dir in prod_cases:
            recipe_id = case_dir.name.removeprefix("prod-")
            for name, rel in DESIGN_FILES.items():
                shutil.copyfile(case_dir / name, TEMPLATE / rel)
            design = json.loads(
                (case_dir / "site-design.ts").read_text(encoding="utf-8").split("= ", 1)[1].rstrip().rstrip(";")
            )
            identities[recipe_id] = design.get("motion") or {}
            print(f"building board: {recipe_id} ...")
            run(
                [
                    "npm", "run", "build", "--",
                    "--base", f"/{recipe_id}/",
                    "--outDir", str(BOARDS / recipe_id),
                    "--emptyOutDir",
                ],
                cwd=TEMPLATE,
            )
    finally:
        restore_template()

    rows = "\n".join(
        f"      <tr><td><a href='/{rid}/'>{rid}</a></td>"
        f"<td>{m.get('identity', '')}</td><td>{m.get('stagger_ms', '')} ms</td>"
        f"<td>{m.get('travel', '')}</td><td>{m.get('reveal', '')}</td></tr>"
        for rid, m in identities.items()
    )
    (BOARDS / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>BMV motion boards</title>\n"
        "<style>body{font:16px/1.6 system-ui;max-width:56rem;margin:3rem auto;padding:0 1rem}"
        "table{border-collapse:collapse;width:100%}td,th{padding:.4rem .8rem;border-bottom:1px solid #ddd;text-align:left}"
        "a{font-weight:600}</style>\n"
        "<h1>Motion boards — eight recipes, one frozen brand</h1>\n"
        "<p>Same Stage-A gate brief (teal bakery) on every board; only the recipe differs. "
        "What differs TODAY: bones (hero/nav/footer variants) and temperament (motion — "
        "scroll each page and watch entrance pacing, stagger, travel). What does NOT differ "
        "yet: the six marketing recipes still share one stylesheet — that sameness is the "
        "Stage-D target, kept honest here on purpose. The ops boards already carry their own "
        "CSS. Reduced-motion OS setting shows the complete static page everywhere.</p>\n"
        f"<table><tr><th>board</th><th>identity</th><th>stagger</th><th>travel</th><th>reveal</th></tr>\n{rows}\n</table>\n"
        "<p>Serve: <code>cd boards && python3 -m http.server 8930</code></p>\n",
        encoding="utf-8",
    )
    print(f"\n{len(prod_cases)} boards -> {BOARDS}")
    print("view: cd boards && python3 -m http.server 8930  ->  http://localhost:8930/")


if __name__ == "__main__":
    main()
