#!/usr/bin/env python3
"""How much of the real dead-link population can a deterministic rule retarget?

Dead links are 37 of the 49 blocking gate issues across trios 2-4. Before
writing a resolver, measure which rules actually fire on the hrefs the pipeline
really produced, rather than on the ones that are easy to imagine.

Rule 1 (parent): /patient/messages/new -> /patient/messages
Rule 2 (dash):   /book-canoe-trip -> /book-canoe -> /book
Rule 3 (home):   nothing matched; the link goes to / rather than nowhere.
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

RUNS = [77, 78, 79, 80, 81, 82, 83, 84, 85]


def _parents(path: str):
    parts = path.strip("/").split("/")
    for cut in range(len(parts) - 1, 0, -1):
        yield "/" + "/".join(parts[:cut])


def _dash_shortenings(path: str):
    parts = path.strip("/").split("/")
    last = parts[-1]
    while "-" in last:
        last = last.rsplit("-", 1)[0]
        yield "/" + "/".join(parts[:-1] + [last])


def resolve(href: str, served: set[str]) -> tuple[str, str]:
    for candidate in _parents(href):
        if _route_matches(candidate, served):
            return candidate, "parent"
    for candidate in _dash_shortenings(href):
        if _route_matches(candidate, served):
            return candidate, "dash"
    return "/", "home"


def main() -> None:
    tally = {"parent": 0, "dash": 0, "home": 0}
    for rid in RUNS:
        ws = Path(f"/app/data/preview-apps/{rid}")
        if not ws.exists():
            continue
        served = rendered_route_paths(ws)
        dead: set[str] = set()
        for f in sorted((ws / "src").rglob("*.ts*")):
            src = f.read_text(errors="replace")
            for href in set(internal_hrefs(src)) | set(internal_href_templates(src)):
                if not _route_matches(href, served):
                    dead.add(_norm(href))
        dead.discard("/owner/...")
        if not dead:
            continue
        print(f"--- {rid}")
        for href in sorted(dead):
            target, rule = resolve(href, served)
            tally[rule] += 1
            print(f"    {href:<48} -> {target:<28} [{rule}]")
    total = sum(tally.values())
    print(f"\n{total} dead hrefs: ", end="")
    print(", ".join(f"{k}={v} ({100*v/total:.0f} %)" for k, v in tally.items()))


if __name__ == "__main__":
    main()
