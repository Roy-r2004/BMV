#!/usr/bin/env python3
"""Phase 2 DoD 7, measured: is the route/page mapping a bijection today?

DoD 7 is two claims:

  1. `len(_smoke_routes(architect))` equals the count of non-wildcard routes
     with a page file.
  2. `catalogue_route_for_file` is injective.

Both are measurable offline, and this is the baseline they are measured against.
It calls the *real* functions rather than reimplementing them — a reimplemented
check is how three "pinned" rows turned out to be false in production.

Corpus: `docs/evidence/architect-routes.json` (the architect route list of every
stored run, lifted out of `requests.generated_pages -> preview_app -> routes`,
which `finalize` persists verbatim) plus the workspaces in
`docs/evidence/preview-workspaces.tar.gz`. Both are archived because the
database and the docker volume are ephemeral infrastructure and a number that
cannot be re-derived is a claim, not a measurement.

    python3 backend/scripts/measure/route_bijection.py [--workspaces DIR]

Read-only. Nothing is written to a workspace.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# The script's own checkout wins over the image's baked `/app/backend`. The other
# tools here prefer `/app/backend`, which is right when they run inside the live api
# container and wrong here: this one is run against a *mounted* repo, and the baked
# copy silently shadowed the function under test on the first attempt.
for _candidate in (str(Path(__file__).resolve().parents[2]), "/app/backend"):
    if (Path(_candidate) / "app").is_dir():
        if _candidate not in sys.path:
            sys.path.insert(0, _candidate)
        break
else:  # pragma: no cover - misplaced checkout
    raise SystemExit("cannot locate the `app` package from either the repo or /app/backend")

from app.application.preview_app.catalogue_contract.slots import (  # noqa: E402
    catalogue_route_for_file,
)
from app.application.preview_app.pipeline.finalize import (  # noqa: E402
    _SMOKE_MAX_ROUTES,
    _smoke_routes,
    smoke_eligible_routes,
)
from app.application.preview_app.protected_paths import (  # noqa: E402
    canonical_workspace_path,
)

REPO = Path(__file__).resolve().parents[3]
CORPUS = REPO / "docs" / "evidence" / "architect-routes.json"

#: Pages the template ships in every workspace. They are not `is_template_owned_path`
#: (the generator may overwrite them), but an unrouted one is a template seed the
#: architect renamed past, not a page a writer produced and nothing serves. Counted
#: separately because conflating the two turns a 5-run finding into a 35-run one.
TEMPLATE_SEED_PAGES = frozenset(
    p.relative_to(REPO / "backend" / "preview-template").as_posix().lower()
    for p in (REPO / "backend" / "preview-template" / "src" / "pages").rglob("*.tsx")
)


def _norm(path: str) -> str:
    return canonical_workspace_path(path).lower()


def page_files(workspace: Path) -> set[str]:
    root = workspace / "src" / "pages"
    if not root.is_dir():
        return set()
    return {
        _norm(p.relative_to(workspace).as_posix())
        for p in root.rglob("*.tsx")
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--workspaces",
        default="/app/data/preview-apps",
        help="root holding <request_id>/src/... (default: the container volume)",
    )
    args = ap.parse_args()
    corpus = json.loads(CORPUS.read_text())
    ws_root = Path(args.workspaces)

    smoke_short = 0
    capped = 0
    aliased = 0
    lost_urls = 0
    unloaded = 0
    non_injective = 0
    orphan_runs = 0
    orphan_files = 0
    seed_orphan_runs = 0
    dangling_runs = 0

    print(f"{'req':>4} {'routes':>6} {'files':>5} {'smoke':>5} {'unloaded':>8}  notes")
    for rid, routes in sorted(corpus.items(), key=lambda kv: int(kv[0])):
        architect = {"routes": routes}
        eligible = smoke_eligible_routes(architect)
        smoke = _smoke_routes(architect)
        components = Counter(_norm(r["component_file"]) for r in eligible)
        dup = {c: n for c, n in components.items() if n > 1}

        notes = []
        if len(smoke) != len(eligible):
            smoke_short += 1
            unloaded += len(eligible) - len(smoke)
        if len(eligible) > len(smoke) and len(smoke) == _SMOKE_MAX_ROUTES:
            capped += 1
            notes.append(f"cap dropped {len(eligible) - _SMOKE_MAX_ROUTES}")
        if dup:
            aliased += 1
            lost_urls += sum(n - 1 for n in dup.values())
            notes.append("dup " + ",".join(sorted(c.rsplit("/", 1)[-1] for c in dup)))

        # Injectivity, asked of the real function: for every route naming a page,
        # does the lookup hand that route back? Where two routes share a file it
        # cannot, and the loser's contract is silently unenforceable.
        shadowed = [
            r
            for r in eligible
            if catalogue_route_for_file(r["component_file"], architect) is not r
        ]
        if shadowed:
            non_injective += 1
            notes.append(f"{len(shadowed)} shadowed route(s)")

        ws = ws_root / rid
        pages = page_files(ws) if ws.is_dir() else set()
        if pages:
            declared = set(components)
            orphans = sorted(pages - declared)
            generated = [p for p in orphans if p not in TEMPLATE_SEED_PAGES]
            seeds = [p for p in orphans if p in TEMPLATE_SEED_PAGES]
            dangling = sorted(declared - pages)
            if generated:
                orphan_runs += 1
                orphan_files += len(generated)
                notes.append("orphan " + ",".join(p.rsplit("/", 1)[-1] for p in generated))
            if seeds:
                seed_orphan_runs += 1
            if dangling:
                dangling_runs += 1
                notes.append("dangling " + ",".join(p.rsplit("/", 1)[-1] for p in dangling))

        print(
            f"{rid:>4} {len(eligible):>6} {len(components):>5} {len(smoke):>5} "
            f"{len(eligible) - len(smoke):>8}  " + "; ".join(notes)
        )

    n = len(corpus)
    print()
    print(f"corpus: {n} runs, {sum(len(v) for v in corpus.values())} routes")
    print(f"DoD 7a  len(_smoke_routes) != eligible routes : {smoke_short}/{n} runs, "
          f"{unloaded} routes never smoke-loaded")
    print(f"          of which the {_SMOKE_MAX_ROUTES}-route cap binds      : {capped}/{n} runs")
    print(f"          one page file under two+ URLs        : {aliased}/{n} runs, "
          f"{lost_urls} alias URLs")
    print(f"DoD 7b  catalogue_route_for_file not injective : {non_injective}/{n} runs")
    print(f"extra   generated page with no route           : {orphan_runs}/{n} runs, "
          f"{orphan_files} files")
    print(f"extra   template seed page with no route       : {seed_orphan_runs}/{n} runs")
    print(f"extra   route naming a file that does not exist: {dangling_runs}/{n} runs")


if __name__ == "__main__":
    main()
