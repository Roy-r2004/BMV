"""How many routes does alias minting add, before and after?

    docker run --rm -v "$REPO:/repo" -w /repo/backend \
      -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api \
      -c 'python3 scripts/measure/route_alias_census.py --routes ../docs/evidence/preview-routes.json'

Drives the real `write_app_tsx` over every stored route table and counts the
`<Route path=...>` entries it emits.

**The "before" column loads the previous `assemble.py` out of git and executes
it.** The first version of this script reconstructed "before" by appending a
`:slug` twin to every path ending in `/:id`, which is a paraphrase and was
wrong in a way that inflated the result: the old code skipped any path already
ending in `/:id` (`assemble.py:1017`), so seven runs were credited with
`/owner/paintings/edit/:slug` routes no run ever shipped. A census that
re-implements the rule measures its own copy of it.

Each run needs a workspace whose `src/pages` holds a file per component, because
`_resolve_page` reads the workspace and silently drops a route whose file is
missing; the tables are rendered into a temporary directory that is discarded.
"""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.application.preview_app import assemble as assemble_mod  # noqa: E402
from app.infrastructure.templating.renderer import get_template_renderer  # noqa: E402

_PATH_RE = re.compile(r'<Route\s+path="([^"]+)"')


def _component_for(route: dict, index: int) -> str:
    raw = str(route.get("component_file") or route.get("component") or "")
    stem = Path(raw.replace("\\", "/")).stem
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", stem):
        stem = f"Page{index}"
    return stem


def _load_previous_assemble(ref: str, before_file: str | None):
    """Import the `assemble` module as it stood before this change, and return it.

    Not a copy of the old rules — the old file, executed. Its own imports
    resolve against the installed package exactly as they do at runtime.

    The test image has no `git`, so the usual invocation hands the old source in
    with `--before-file`; extract it on the host with

        git show <ref>:backend/app/application/preview_app/assemble.py > <path>
    """
    import importlib.util
    import subprocess

    if before_file:
        source = Path(before_file).read_text(encoding="utf-8")
    else:
        repo = Path(__file__).resolve().parents[3]
        source = subprocess.run(
            ["git", "show", f"{ref}:backend/app/application/preview_app/assemble.py"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    target = Path(tempfile.gettempdir()) / "_assemble_previous.py"
    target.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("_assemble_previous", target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _render(architect: dict, module=assemble_mod) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        pages = workspace / "src" / "pages"
        pages.mkdir(parents=True)
        # Each page is written at the path the run declared, subdirectories and
        # all. Flattening `src/pages/owner/LoginPage.tsx` into `src/pages/` made
        # `_resolve_page` drop nine of request 69's fifteen routes before
        # anything could be counted — a fixture too small to reach the rule.
        for route in architect["routes"]:
            comp = route["component"]
            rel = route.get("component_file") or f"src/pages/{comp}.tsx"
            target = workspace / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                f"export default function {comp}() {{ return <div />; }}\n",
                encoding="utf-8",
            )
        module.write_app_tsx(workspace, architect, get_template_renderer())
        return _PATH_RE.findall((workspace / "src" / "App.tsx").read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--routes",
        default=str(Path(__file__).resolve().parents[3] / "docs/evidence/preview-routes.json"),
    )
    parser.add_argument(
        "--before-ref",
        default="HEAD",
        help="git ref whose assemble.py is the 'before' column (default HEAD)",
    )
    parser.add_argument(
        "--before-file",
        default=None,
        help="path to the previous assemble.py, for images without git",
    )
    args = parser.parse_args()

    payload = json.loads(Path(args.routes).read_text(encoding="utf-8"))
    # `preview-routes.json` is keyed by request id, each value carrying
    # `business_name`, `industry`, `kind_context` and `routes`.
    if isinstance(payload, dict) and "runs" in payload:
        runs = payload["runs"]
    elif isinstance(payload, dict):
        runs = [{**value, "request_id": key} for key, value in payload.items()]
    else:
        runs = payload

    previous = _load_previous_assemble(args.before_ref, args.before_file)

    changed = 0
    regressions: list = []
    total_before = 0
    total_after = 0
    rows = []
    for run in runs:
        routes = [r for r in (run.get("routes") or []) if isinstance(r, dict) and r.get("path")]
        if not routes:
            continue
        architect = {
            "routes": [
                {
                    "path": r["path"],
                    "component": _component_for(r, i),
                    "component_file": r.get("component_file"),
                    "layout": r.get("layout") or r.get("surface") or "public",
                    "skeleton_id": r.get("skeleton_id"),
                    "surface": r.get("surface"),
                }
                for i, r in enumerate(routes)
            ]
        }
        after = _render(json.loads(json.dumps(architect)))
        before = _render(json.loads(json.dumps(architect)), module=previous)

        # The safety property: an alias may vanish, a DECLARED route may not.
        declared_paths = {r["path"].rstrip("/") or "/" for r in routes}
        lost = declared_paths - {p.rstrip("/") or "/" for p in after}
        if lost:
            regressions.append((run.get("request_id"), sorted(lost)))

        total_before += len(before)
        total_after += len(after)
        if len(before) != len(after):
            changed += 1
            rows.append(
                {
                    "request": run.get("request_id") or run.get("id"),
                    "declared": len(routes),
                    "before": len(before),
                    "after": len(after),
                    "dropped": sorted(set(before) - set(after)),
                }
            )

    if regressions:
        print("!! DECLARED ROUTES LOST — the change is not safe:")
        for request_id, lost in regressions:
            print(f"   request {request_id}: {lost}")
        print()
    else:
        print("no declared route is lost on any run")
    print(f"runs measured:            {sum(1 for r in runs if r.get('routes'))}")
    print(f"runs whose route count changes: {changed}")
    print(f"total routes before:      {total_before}")
    print(f"total routes after:       {total_after}")
    print(f"routes removed:           {total_before - total_after}")
    print()
    for row in sorted(rows, key=lambda r: r["before"] - r["after"], reverse=True)[:15]:
        print(
            f"  request {row['request']}: declared {row['declared']}, "
            f"{row['before']} -> {row['after']}  dropped {row['dropped'][:4]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
