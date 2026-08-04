#!/usr/bin/env python3
"""Where does the `codegen` stage's 315-437 s of AI actually go?

Duo 1 measured `codegen` at **315.0 s / 24 calls** (request 95) and **436.9 s /
33 calls** (request 96) — three to four times `appspec`, and the term that
decides p50. Nobody had ever broken it down by writer the way
`appspec_cost.py` broke down appspec, and the `ai_call` scopes to do it
already exist. This is that decomposition.

Two things this separates that a stage total cannot, and one it exposes by
refusing to guess:

* **Which writer.** `slot_fill` (one catalogue slot per call, retried once),
  `utility_content`, `freeform` / `freeform-retry` (the non-catalogue page
  path) have different fixes; a stage total says nothing about which is live.
* **Spend the pipeline threw away.** `usable = false` is time bought and
  discarded, and on `slot_fill` it is the majority of the calls.
* **Spend nothing claimed.** `stage` falls back to the run *purpose* when a
  call is made outside any `ai_call` scope (`admin_ops.py:330`), and
  `generate_preview_app` runs the **whole** preview pipeline under
  `purpose="codegen"` (`pipeline/orchestrator.py:39`). So every unscoped AI
  call anywhere in that pipeline lands in `codegen` with `writer = NULL`.
  Those rows are reported as `(unattributed)` and never folded into a writer.

`(unattributed)` rows are split by whether they precede this run's `architect`
call, which is the one scoped landmark between the plan phase and code
generation:

* `(unattributed) pre-architect` — plan phase: `build_experience_plan`,
  `validate_and_expand_plan`, `build_design_manifest`
  (`services/page_experience.py`), none of which has a scope.
* `(unattributed) post-architect` — anything unscoped after it.

A run with no `architect` row at all reports its unattributed rows as
`(unattributed) no-architect-row`, because the split is not derivable.

Read-only. Run inside the api container:

    docker compose exec api python /app/backend/scripts/measure/codegen_cost.py
    docker compose exec api python /app/backend/scripts/measure/codegen_cost.py 95 96
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

# Runs inside the api container (`/app/backend`) or from a repo checkout.
# Whichever actually holds the `app` package wins.
for _candidate in ("/app/backend", str(Path(__file__).resolve().parents[2])):
    if (Path(_candidate) / "app").is_dir():
        if _candidate not in sys.path:
            sys.path.insert(0, _candidate)
        break
else:  # pragma: no cover - misplaced checkout
    raise SystemExit("cannot locate the `app` package from either /app/backend or the repo")

#: Duo 1. Trio 7 (92-94) is not a useful codegen baseline: two of its three
#: runs never reached codegen at all.
DEFAULT_RUNS = [95, 96]

UNATTRIBUTED_PRE = "(unattributed) pre-architect"
UNATTRIBUTED_POST = "(unattributed) post-architect"
UNATTRIBUTED_UNKNOWN = "(unattributed) no-architect-row"


def _seconds(row: Mapping[str, Any]) -> float:
    return (row.get("latency_ms") or 0) / 1000.0


def architect_boundaries(rows: Iterable[Mapping[str, Any]]) -> dict[int, float | None]:
    """When each run's `architect` call *started*, per request id.

    `None` for a run with no architect row — that run's unscoped codegen rows
    cannot be placed on either side of a boundary that was never recorded, and
    guessing is how the appspec write-up got its mechanism wrong.
    """

    starts: dict[int, float | None] = {}
    for row in rows:
        rid = row["request_id"]
        starts.setdefault(rid, None)
        if (row.get("stage") or "") != "architect":
            continue
        began = float(row["ts"]) - _seconds(row)
        current = starts[rid]
        starts[rid] = began if current is None else min(current, began)
    return starts


def writer_of(row: Mapping[str, Any], architect_start: float | None) -> str:
    """The writer to bill this row to, naming the unscoped ones rather than
    merging them into a bucket that reads like a real writer."""

    writer = row.get("writer")
    if writer:
        return str(writer)
    if architect_start is None:
        return UNATTRIBUTED_UNKNOWN
    began = float(row["ts"]) - _seconds(row)
    return UNATTRIBUTED_PRE if began < architect_start else UNATTRIBUTED_POST


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Decompose `codegen` rows by writer. Pure — no database, so it is testable."""

    codegen = [dict(r) for r in rows if (r.get("stage") or "") == "codegen"]
    starts = architect_boundaries(rows)

    per_writer: dict[str, dict[str, float]] = defaultdict(
        lambda: {"calls": 0, "seconds": 0.0, "retries": 0, "retry_seconds": 0.0,
                 "unusable": 0, "unusable_seconds": 0.0}
    )
    per_run: dict[int, dict[str, float]] = defaultdict(
        lambda: {"calls": 0, "seconds": 0.0, "unattributed_seconds": 0.0}
    )
    for row in codegen:
        rid = row["request_id"]
        writer = writer_of(row, starts.get(rid))
        seconds = _seconds(row)
        bucket = per_writer[writer]
        bucket["calls"] += 1
        bucket["seconds"] += seconds
        if (row.get("attempt") or 1) > 1:
            bucket["retries"] += 1
            bucket["retry_seconds"] += seconds
        if row.get("usable") is False:
            bucket["unusable"] += 1
            bucket["unusable_seconds"] += seconds
        run = per_run[rid]
        run["calls"] += 1
        run["seconds"] += seconds
        if writer.startswith("(unattributed)"):
            run["unattributed_seconds"] += seconds

    total = sum(b["seconds"] for b in per_writer.values())
    unattributed = sum(
        b["seconds"] for w, b in per_writer.items() if w.startswith("(unattributed)")
    )
    return {
        "runs": sorted(per_run),
        "per_writer": {k: dict(v) for k, v in per_writer.items()},
        "per_run": {k: dict(v) for k, v in per_run.items()},
        "calls": len(codegen),
        "seconds": total,
        "unattributed_seconds": unattributed,
    }


def fetch(runs: Sequence[int]) -> list[dict[str, Any]]:  # pragma: no cover - needs a db
    from sqlalchemy import text

    from app.infrastructure.db.session import engine

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT request_id, stage, writer, model, attempt, latency_ms, "
                "success, usable, output_chars, extract(epoch from created_at) AS ts "
                "FROM ai_usage_events WHERE request_id = ANY(:ids) "
                "ORDER BY request_id, created_at, id"
            ),
            {"ids": list(runs)},
        ).mappings().all()
    return [dict(r) for r in rows]


def render(report: Mapping[str, Any]) -> str:
    runs = report["runs"]
    n = len(runs) or 1
    total = report["seconds"]
    lines: list[str] = []
    lines.append(
        f"codegen AI spend over {len(runs)} runs: {total:.1f} s total, {total / n:.1f} s per run\n"
    )
    header = (
        f"{'writer':<32}{'calls':>7}{'sec':>9}{'sec/run':>9}"
        f"{'re-asks':>9}{'re-ask s':>10}{'wasted s':>10}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for writer, b in sorted(report["per_writer"].items(), key=lambda kv: -kv[1]["seconds"]):
        lines.append(
            f"{writer:<32}{int(b['calls']):>7}{b['seconds']:>9.1f}{b['seconds'] / n:>9.1f}"
            f"{int(b['retries']):>9}{b['retry_seconds']:>10.1f}{b['unusable_seconds']:>10.1f}"
        )
    lines.append("-" * len(header))
    lines.append(
        f"{'ALL':<32}{report['calls']:>7}{total:>9.1f}{total / n:>9.1f}"
        f"{sum(int(b['retries']) for b in report['per_writer'].values()):>9}"
        f"{sum(b['retry_seconds'] for b in report['per_writer'].values()):>10.1f}"
        f"{sum(b['unusable_seconds'] for b in report['per_writer'].values()):>10.1f}"
    )
    share = report["unattributed_seconds"] / total * 100 if total else 0.0
    lines.append(
        f"\n{report['unattributed_seconds']:.1f} s ({share:.0f} %) of the `codegen` stage total is "
        "NOT codegen: it is AI called outside any `ai_call` scope while the whole preview\n"
        "pipeline runs under purpose=\"codegen\", so the stage fallback claims it. Naming those "
        "writers is a prerequisite to bounding anything here."
    )
    lines.append(f"\n{'run':>5}{'calls':>7}{'AI s':>8}{'unattributed s':>16}")
    for rid in runs:
        b = report["per_run"][rid]
        lines.append(
            f"{rid:>5}{int(b['calls']):>7}{b['seconds']:>8.1f}{b['unattributed_seconds']:>16.1f}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    runs = [int(a) for a in args] or DEFAULT_RUNS
    rows = fetch(runs)
    if not rows:
        raise SystemExit(f"no ai_usage_events for runs {runs}")
    report = summarize(rows)
    if not report["calls"]:
        stages = sorted({(r.get("stage") or "(none)") for r in rows})
        raise SystemExit(f"no codegen rows. stages present: {stages}")
    print(render(report))


if __name__ == "__main__":  # pragma: no cover - shell entry point
    main()
