#!/usr/bin/env python3
"""Replay the dead-link guard over the nine real workspaces, in memory.

Reads the shipped sources, applies `repair_file_dead_links` to a copy, and
re-runs the same deadness test the quality gate runs. Nothing is written — the
standing rule is that a generated preview is never edited to make a defect go
away, and these are the audit trail for requests 77-85.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Runs inside the api container (`/app/backend`) or from a repo checkout.
# Whichever actually holds the `app` package wins.
for _candidate in ("/app/backend", str(Path(__file__).resolve().parents[2])):
    if (Path(_candidate) / "app").is_dir():
        if _candidate not in sys.path:
            sys.path.insert(0, _candidate)
        break
else:  # pragma: no cover - misplaced checkout
    raise SystemExit("cannot locate the `app` package from either /app/backend or the repo")

from app.application.preview_app.capabilities.journey import (  # noqa: E402
    _norm,
    _route_matches,
    internal_href_templates,
    internal_hrefs,
    rendered_route_paths,
)
from app.application.preview_app.safety.dead_links import (  # noqa: E402
    repair_file_dead_links,
)

RUNS = [77, 78, 79, 80, 81, 82, 83, 84, 85]


def _dead(src: str, served: set[str]) -> set[str]:
    found = set(internal_hrefs(src)) | set(internal_href_templates(src))
    return {
        _norm(h) for h in found if not _route_matches(h, served) and "..." not in h
    }


def main() -> None:
    grand = {"before": 0, "after": 0}
    totals = {"retargeted": 0, "unlinked": 0, "homed": 0}
    for rid in RUNS:
        ws = Path(f"/app/data/preview-apps/{rid}")
        if not ws.exists():
            continue
        served = rendered_route_paths(ws)
        before: set[str] = set()
        after: set[str] = set()
        run_counts = {"retargeted": 0, "unlinked": 0, "homed": 0}
        for f in sorted((ws / "src").rglob("*.ts*")):
            src = f.read_text(errors="replace")
            before |= _dead(src, served)
            repaired, counts = repair_file_dead_links(src, served)
            for k in run_counts:
                run_counts[k] += counts[k]
            after |= _dead(repaired, served)
        for k in totals:
            totals[k] += run_counts[k]
        grand["before"] += len(before)
        grand["after"] += len(after)
        flag = "" if not after else f"  LEFT: {sorted(after)}"
        print(
            f"{rid}: dead {len(before):>2} -> {len(after):>2}   "
            + ", ".join(f"{k}={v}" for k, v in run_counts.items() if v)
            + flag
        )
    print(
        f"\ntotal distinct dead hrefs {grand['before']} -> {grand['after']}   "
        + ", ".join(f"{k}={v}" for k, v in totals.items())
    )


if __name__ == "__main__":
    main()
