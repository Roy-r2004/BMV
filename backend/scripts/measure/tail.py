#!/usr/bin/env python3
"""What is the 33-80 s post-deadline tail actually made of?

Every one of the nine runs finished past its deadline by 33-80 s regardless of
what changed between trios, which reads as structural. Nobody has decomposed
it. `RESERVE_SECONDS = 60` was fitted to the render-smoke + capture pass on two
single runs (41-42 s); if the tail is mostly something else, that number is
fitted to the wrong thing and 1.11 has been aimed at the wrong target twice.

`created_at` on `ai_usage_events` is stamped at INSERT, so it marks the call's
END. Start is `created_at - latency_ms`. A call straddling the deadline is
split, so "post-deadline AI seconds" means seconds actually spent after it.
"""
from __future__ import annotations

import json
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

from sqlalchemy import text  # noqa: E402

from app.infrastructure.db.session import engine  # noqa: E402

RUNS = [74, 75, 76, 77, 78, 79, 80, 81, 82]
TOTAL = 540.0


def main() -> None:
    with engine.connect() as conn:
        meta = {
            r["id"]: r
            for r in conn.execute(
                text(
                    "SELECT id, extract(epoch from created_at) AS created, "
                    "((generated_pages::jsonb)->'preview_app'->>'elapsed_seconds')::float "
                    "AS elapsed "
                    "FROM requests WHERE id = ANY(:ids)"
                ),
                {"ids": RUNS},
            ).mappings()
        }
        rows = conn.execute(
            text(
                "SELECT request_id, stage, latency_ms, "
                "extract(epoch from created_at) AS ended "
                "FROM ai_usage_events WHERE request_id = ANY(:ids)"
            ),
            {"ids": RUNS},
        ).mappings().all()

    per_run: dict[int, list[dict]] = {r: [] for r in RUNS}
    for row in rows:
        per_run[row["request_id"]].append(dict(row))

    print(f"{'run':>4} {'tail_s':>7} {'ai_in_tail':>11} {'non_ai':>8} {'ai%':>5}  top stages in tail")
    print("-" * 92)
    totals = {"tail": 0.0, "ai": 0.0}
    for rid in RUNS:
        info = meta.get(rid)
        if not info or info["elapsed"] is None:
            print(f"{rid:>4}  (no stored elapsed — run stored nothing)")
            continue
        # The deadline is armed within ~1 s of row creation.
        deadline_at = float(info["created"]) + TOTAL
        tail = float(info["elapsed"]) - TOTAL
        if tail <= 0:
            continue

        by_stage: dict[str, float] = {}
        for row in per_run[rid]:
            dur = (row["latency_ms"] or 0) / 1000.0
            end = float(row["ended"])
            start = end - dur
            overlap = max(0.0, min(end, deadline_at + tail) - max(start, deadline_at))
            if overlap > 0.0:
                by_stage[row["stage"] or "(none)"] = (
                    by_stage.get(row["stage"] or "(none)", 0.0) + overlap
                )
        ai = sum(by_stage.values())
        totals["tail"] += tail
        totals["ai"] += ai
        top = ", ".join(
            f"{s}={v:.0f}s"
            for s, v in sorted(by_stage.items(), key=lambda kv: -kv[1])[:4]
        )
        print(
            f"{rid:>4} {tail:>7.1f} {ai:>11.1f} {tail - ai:>8.1f} "
            f"{100 * ai / tail:>4.0f}%  {top or '(no AI calls in the tail)'}"
        )

    if totals["tail"]:
        print("-" * 92)
        print(
            f"     {totals['tail']:>7.1f} {totals['ai']:>11.1f} "
            f"{totals['tail'] - totals['ai']:>8.1f} "
            f"{100 * totals['ai'] / totals['tail']:>4.0f}%  <-- all runs"
        )


if __name__ == "__main__":
    main()
