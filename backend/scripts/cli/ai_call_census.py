#!/usr/bin/env python3
"""Fit p50 / p95 per model and per stage, and derive a whole-run p95.

Phase 0.6 of `docs/PREVIEW_ROADMAP.md`. The deadline in Phase 1.1 has to be
sized from the distribution of the *sum* of per-call latencies, not from a mean
and not from p95 × call-count. This reads `ai_usage_events`, fits the per-stage
empirical distributions, convolves them over the measured call census, and
prints the run-level percentiles alongside the mandatory logical-call floor.

Usage::

    cd backend
    python scripts/cli/ai_call_census.py                       # attributed rows
    python scripts/cli/ai_call_census.py --requests 66,67,68,70,71
    python scripts/cli/ai_call_census.py --attribute-by-window # + reconstructed
    python scripts/cli/ai_call_census.py --overhead 154 --json

    docker compose exec -T -w /app/backend api \
        python scripts/cli/ai_call_census.py --requests 66,67,68,70,71

`--overhead` is the wall clock a run spends outside model calls — screenshot
capture, vite, deterministic repair. It shifts the fitted distribution so the
printed p95 is comparable to a request-accepted-to-ready number.

`--attribute-by-window` folds in rows whose `request_id` never propagated, by
the request window they fall inside. That is **reconstruction, not
measurement** — it is how the first report has to be produced, because the
context-propagation fix cannot retroactively label rows already written. The
output states how many rows were inferred.

Rows written before the census landed carry `usable = NULL`. They are reported
as unadjudicated rather than counted as successes; a blind spot must not
flatter the numbers.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy import inspect, text  # noqa: E402

from app.application.services.ai_call_census import (  # noqa: E402
    ELECTIVE_STAGES,
    MANDATORY_STAGES,
    CallRecord,
    census_report,
)
from app.infrastructure.db.session import engine  # noqa: E402

_OPTIONAL_COLUMNS = (
    "stage",
    "usable",
    "writer",
    "attempt",
    "ops_applied",
    "finish_reason",
)

#: A run's last recorded call can land slightly after `requests.updated_at`.
_WINDOW_SLACK = timedelta(minutes=3)


def _available_columns(conn) -> set[str]:
    """Which census columns this database actually has.

    The script has to run against a database the migration has not reached yet —
    that is the normal case for the first report, whose whole job is to describe
    rows written before the instrumentation existed.
    """

    return {column["name"] for column in inspect(conn).get_columns("ai_usage_events")}


def _request_windows(request_ids: list[int] | None) -> list[tuple[int, datetime, datetime]]:
    clause = "WHERE id IN :ids" if request_ids else ""
    statement = text(f"SELECT id, created_at, updated_at FROM requests {clause} ORDER BY id")
    if request_ids:
        statement = statement.bindparams(ids=tuple(request_ids))
    with engine.connect() as conn:
        rows = conn.execute(statement).mappings().all()
    return [
        (row["id"], row["created_at"], (row["updated_at"] or row["created_at"]) + _WINDOW_SLACK)
        for row in rows
        if row["created_at"] is not None
    ]


def load_records(
    *,
    request_ids: list[int] | None,
    since: datetime | None,
    attribute_by_window: bool,
) -> tuple[list[CallRecord], int]:
    """Return the census rows and how many of them were *inferred*."""

    with engine.connect() as conn:
        present = _available_columns(conn)
        selected = ["request_id", "purpose", "model", "latency_ms", "success", "created_at"]
        selected += [name for name in _OPTIONAL_COLUMNS if name in present]
        where = ["latency_ms IS NOT NULL"]
        if since is not None:
            where.append("created_at >= :since")
        sql = (
            f"SELECT {', '.join(selected)} FROM ai_usage_events "
            f"WHERE {' AND '.join(where)} ORDER BY id"
        )
        rows = conn.execute(
            text(sql), {"since": since} if since is not None else {}
        ).mappings().all()

    windows = _request_windows(request_ids) if attribute_by_window else []
    wanted = set(request_ids) if request_ids else None

    records: list[CallRecord] = []
    reconstructed = 0
    for row in rows:
        request_id = row["request_id"]
        inferred = False
        if request_id is None and windows:
            for candidate, start, end in windows:
                if start <= row["created_at"] <= end:
                    request_id, inferred = candidate, True
                    break
        if wanted is not None and request_id not in wanted:
            continue
        if request_id is None and not attribute_by_window:
            continue
        reconstructed += 1 if inferred else 0
        # `stage` falls back to `purpose` for every row written before the
        # column existed — purpose was already stage-shaped for the calls that
        # ran on the main thread.
        records.append(
            CallRecord(
                request_id=request_id,
                stage=str(row.get("stage") or row.get("purpose") or "unknown"),
                model=str(row.get("model") or "unknown"),
                latency_ms=int(row.get("latency_ms") or 0),
                success=bool(row.get("success")),
                usable=row.get("usable"),
                writer=row.get("writer"),
                attempt=row.get("attempt"),
                ops_applied=row.get("ops_applied"),
                finish_reason=row.get("finish_reason"),
            )
        )
    return records, reconstructed


def _print_table(title: str, summaries: dict[str, dict]) -> None:
    print(f"\n{title}")
    print(f"  {'key':<34}{'n':>5}{'p50 s':>9}{'p95 s':>9}{'mean s':>9}{'total s':>10}")
    for name, stats in sorted(
        summaries.items(), key=lambda item: -float(item[1]["total_s"])
    ):
        print(
            f"  {name[:33]:<34}{stats['n']:>5}{stats['p50_s']:>9.1f}"
            f"{stats['p95_s']:>9.1f}{stats['mean_s']:>9.1f}{stats['total_s']:>10.1f}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--requests", help="Comma-separated request ids")
    parser.add_argument("--since", help="ISO date/timestamp lower bound")
    parser.add_argument(
        "--attribute-by-window",
        action="store_true",
        help="Infer request_id for un-attributed rows from the request window "
        "(reconstruction, not measurement)",
    )
    parser.add_argument(
        "--overhead",
        type=float,
        default=0.0,
        help="Seconds of non-model wall clock to add to the fitted run total",
    )
    parser.add_argument("--bin-ms", type=int, default=1000, help="Convolution bin width")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    request_ids = (
        [int(part) for part in args.requests.split(",") if part.strip()]
        if args.requests
        else None
    )
    since = datetime.fromisoformat(args.since) if args.since else None

    records, reconstructed = load_records(
        request_ids=request_ids,
        since=since,
        attribute_by_window=args.attribute_by_window,
    )
    if not records:
        print("no ai_usage_events rows matched", file=sys.stderr)
        return 1

    report = census_report(records, fixed_overhead_s=args.overhead, bin_ms=args.bin_ms)
    report["rows_reconstructed"] = reconstructed

    if args.json:
        print(json.dumps(report, indent=2, default=float))
        return 0

    print(
        f"rows={report['rows']}  "
        f"reconstructed_request_id={reconstructed}  "
        f"unadjudicated_usable={report['rows_unadjudicated']}"
    )
    _print_table("per stage", report["by_stage"])
    _print_table("per model", report["by_model"])

    print("\ncall census (per run)")
    print(f"  {'stage':<24}{'min':>7}{'median':>8}{'max':>7}{'runs':>7}  class")
    for stage, stats in sorted(
        report["calls_per_run"].items(), key=lambda item: -item[1]["median"]
    ):
        kind = (
            "MANDATORY"
            if stage in MANDATORY_STAGES
            else "elective"
            if stage in ELECTIVE_STAGES
            else "UNCLASSIFIED"
        )
        print(
            f"  {stage[:23]:<24}{stats['min']:>7.0f}{stats['median']:>8.1f}"
            f"{stats['max']:>7.0f}{stats['runs']:>7.0f}  {kind}"
        )

    if report["unclassified_stages"]:
        print(
            "\n  UNCLASSIFIED stages (excluded from the mandatory floor): "
            + ", ".join(report["unclassified_stages"])
        )

    print(
        f"\nmandatory logical-call floor : {report['mandatory_floor']}"
        f"\ncalls that produced nothing   : {report['unusable_calls']}"
        f" ({report['unusable_seconds']:.0f} s of wall clock)"
        f"\n\nderived by convolution (overhead {report['fixed_overhead_s']:.0f} s):"
        f"\n  whole run      p50 {report['run_p50_s']:.0f} s   p95 {report['run_p95_s']:.0f} s"
        f"\n  mandatory only p50 {report['mandatory_p50_s']:.0f} s"
        f"   p95 {report['mandatory_p95_s']:.0f} s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
