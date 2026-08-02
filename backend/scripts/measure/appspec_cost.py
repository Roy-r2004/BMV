#!/usr/bin/env python3
"""Where does the AppSpec stage's 264-288 s actually go?

The roadmap's p50 row is failing at 569-590 s against a <= 500 s DoD, and
`appspec` alone spans 264.5 s and 288.8 s on requests 83 and 84 — roughly half
the budget before anything is built. The owner decision pending is whether to
add a Phase 1 item for bounding it. That decision needs the stage decomposed,
and nothing had decomposed it.

Three things this separates, which a stage total cannot:

* **Authoring vs everything else.** One 28k-token authoring call is not the
  same problem as ten small validation calls, and they have opposite fixes.
* **First attempts vs re-asks.** A re-ask is spend the pipeline chose after
  reading its own output as unusable. Until session 6 the authoring parser
  could not read a structurally-complete-but-under-escaped response, so some of
  these re-asks bought nothing that was not already in hand
  (`tests/test_json_extractor_parity.py`).
* **Successful spend vs discarded spend.** `usable = false` is time bought and
  thrown away.

Read-only. Run inside the api container:

    docker compose exec api python /app/backend/scripts/measure/appspec_cost.py
    docker compose exec api python /app/backend/scripts/measure/appspec_cost.py 83 84 85
"""
from __future__ import annotations

import sys
from collections import defaultdict
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

from sqlalchemy import text  # noqa: E402

from app.infrastructure.db.session import engine  # noqa: E402

# Trios 2-5. Trio 6 (89-91) is void — the account ran out of credits mid-run.
DEFAULT_RUNS = [77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88]


def main() -> None:
    runs = [int(a) for a in sys.argv[1:]] or DEFAULT_RUNS

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT request_id, stage, writer, model, attempt, latency_ms, "
                "success, usable, extract(epoch from created_at) AS ts "
                "FROM ai_usage_events WHERE request_id = ANY(:ids) "
                "ORDER BY request_id, created_at, id"
            ),
            {"ids": runs},
        ).mappings().all()

    if not rows:
        raise SystemExit(f"no ai_usage_events for runs {runs}")

    appspec = [dict(r) for r in rows if (r["stage"] or "").startswith("appspec")]
    if not appspec:
        stages = sorted({(r["stage"] or "(none)") for r in rows})
        raise SystemExit(f"no appspec rows. stages present: {stages}")

    # --- per writer ---------------------------------------------------------
    per_writer: dict[str, dict[str, float]] = defaultdict(
        lambda: {"calls": 0, "seconds": 0.0, "retries": 0, "retry_seconds": 0.0,
                 "unusable": 0, "unusable_seconds": 0.0}
    )
    for row in appspec:
        writer = row["writer"] or "(none)"
        seconds = (row["latency_ms"] or 0) / 1000.0
        bucket = per_writer[writer]
        bucket["calls"] += 1
        bucket["seconds"] += seconds
        if (row["attempt"] or 1) > 1:
            bucket["retries"] += 1
            bucket["retry_seconds"] += seconds
        if row["usable"] is False:
            bucket["unusable"] += 1
            bucket["unusable_seconds"] += seconds

    total = sum(b["seconds"] for b in per_writer.values())
    retry_total = sum(b["retry_seconds"] for b in per_writer.values())
    unusable_total = sum(b["unusable_seconds"] for b in per_writer.values())
    n = len({row["request_id"] for row in appspec})

    print(f"appspec AI spend over {n} runs: {total:.1f} s total, {total / n:.1f} s per run\n")
    header = f"{'writer':<28}{'calls':>7}{'sec':>9}{'sec/run':>9}{'re-asks':>9}{'re-ask s':>10}{'wasted s':>10}"
    print(header)
    print("-" * len(header))
    for writer, b in sorted(per_writer.items(), key=lambda kv: -kv[1]["seconds"]):
        print(
            f"{writer:<28}{int(b['calls']):>7}{b['seconds']:>9.1f}{b['seconds'] / n:>9.1f}"
            f"{int(b['retries']):>9}{b['retry_seconds']:>10.1f}{b['unusable_seconds']:>10.1f}"
        )
    print("-" * len(header))
    print(
        f"{'ALL':<28}{len(appspec):>7}{total:>9.1f}{total / n:>9.1f}"
        f"{sum(int(b['retries']) for b in per_writer.values()):>9}"
        f"{retry_total:>10.1f}{unusable_total:>10.1f}"
    )

    print(
        f"\nre-asks are {retry_total / total * 100:.0f} % of appspec AI time "
        f"({retry_total / n:.1f} s per run); "
        f"discarded (usable=false) is {unusable_total / total * 100:.0f} % "
        f"({unusable_total / n:.1f} s per run)."
    )

    # --- per run, wall span vs AI seconds -----------------------------------
    print(f"\n{'run':>5}{'calls':>7}{'AI s':>8}{'span s':>9}{'idle s':>8}  slowest single call")
    for rid in sorted({row["request_id"] for row in appspec}):
        mine = [row for row in appspec if row["request_id"] == rid]
        ai = sum((row["latency_ms"] or 0) / 1000.0 for row in mine)
        # `ts` arrives as Decimal from postgres; mixing it with float latency
        # raises rather than coercing.
        ends = [float(row["ts"]) for row in mine]
        starts = [end - (row["latency_ms"] or 0) / 1000.0 for end, row in zip(ends, mine)]
        span = max(ends) - min(starts)
        slowest = max(mine, key=lambda row: row["latency_ms"] or 0)
        print(
            f"{rid:>5}{len(mine):>7}{ai:>8.1f}{span:>9.1f}{span - ai:>8.1f}"
            f"  {(slowest['latency_ms'] or 0) / 1000.0:.1f} s {slowest['writer']}"
            f" ({slowest['model']})"
        )

    print(
        "\n`span` is first-call-start to last-call-end, so `idle` is appspec wall clock "
        "that is not an AI call in this stage: validation, sanitize, repair, persistence "
        "— and any wait on a lock another run holds."
    )


if __name__ == "__main__":
    main()
