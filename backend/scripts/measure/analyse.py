#!/usr/bin/env python3
"""Phase 1 DoD evidence for the three concurrent runs (74, 75, 76).

Two questions this has to answer that a wall-clock number cannot:

* Was a degradation CORRECT (the run genuinely had no time left) or an
  ARTIFACT (the run spent its budget blocked on a lock another run held)?
  `blocked_seconds` / `contention` come from the instrumentation added this
  session; without them the two are the same list.
* Is any *logical ask* over 120 s inclusive of failovers? One row of
  `ai_usage_events` is one attempt against one model. A logical ask is the
  group of rows a single `ai_call` scope produced — same (request_id, stage,
  writer), contiguous in time, with `attempt` not resetting to 1.
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

_TRIOS = {
    "1": ([74, 75, 76], {74: 1785651700, 75: 1785651761, 76: 1785651821}),
    "2": ([77, 78, 79], {77: 1785653172, 78: 1785653233, 79: 1785653293}),
    "3": ([80, 81, 82], {80: 1785690348, 81: 1785690409, 82: 1785690469}),
    # Trio 4 is the proof run for the elective guards (visual_critic,
    # quality_repair). Compare against trio 3 on two axes and no others:
    # wall clock, and how many pages actually got a visual verdict. Trio 3
    # reviewed 0 of 18 *with the critic running*, because every vision call
    # was refused — so "the critic no longer runs" is only a regression if
    # the reviewed count drops below that.
    "4": ([83, 84, 85], {83: 1785693563, 84: 1785693624, 85: 1785693684}),
    # Trio 5 is the proof run for the deterministic dead-link guard.
    "5": ([86, 87, 88], {86: 1785697222, 87: 1785697283, 88: 1785697343}),
}
IDS, LAUNCH = _TRIOS[sys.argv[1] if len(sys.argv) > 1 else "1"]


def _p(values, q):
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def main() -> None:
    out: dict = {"runs": {}, "asks": {}}
    with engine.connect() as conn:
        for rid in IDS:
            row = conn.execute(
                text(
                    "SELECT status, generated_pages, "
                    "extract(epoch from created_at) AS created, "
                    "extract(epoch from updated_at) AS updated "
                    "FROM requests WHERE id = :i"
                ),
                {"i": rid},
            ).mappings().first()
            if row is None:
                out["runs"][rid] = {"error": "no such request"}
                continue
            gp = json.loads(row["generated_pages"] or "{}")
            pa = gp.get("preview_app") or {}
            out["runs"][rid] = {
                "request_status": row["status"],
                "preview_status": pa.get("status"),
                "viewable": pa.get("viewable"),
                "withheld_reason": pa.get("withheld_reason"),
                "degraded": pa.get("degraded"),
                "degradations": pa.get("degradations"),
                "deadline_seconds": pa.get("deadline_seconds"),
                "elapsed_seconds": pa.get("elapsed_seconds"),
                "deadline_exceeded": pa.get("deadline_exceeded"),
                "blocked_seconds": pa.get("blocked_seconds"),
                "contention": pa.get("contention"),
                "gate_issues": len(pa.get("gate_issues") or []),
                "visual_review_status": pa.get("visual_review_status"),
                "visual_pages_reviewed": len(
                    [
                        p
                        for p in (pa.get("visual_review") or {}).get("pages", [])
                        if (p or {}).get("verdict")
                    ]
                )
                if isinstance(pa.get("visual_review"), dict)
                else None,
                "pages": len(pa.get("pages") or gp.get("pages") or []),
                "db_created_epoch": row["created"],
                "db_updated_epoch": row["updated"],
                "launch_epoch": LAUNCH.get(rid),
            }

        # --- logical asks -------------------------------------------------
        rows = conn.execute(
            text(
                "SELECT request_id, stage, writer, model, attempt, latency_ms, "
                "success, usable, extract(epoch from created_at) AS ts "
                "FROM ai_usage_events WHERE request_id = ANY(:ids) "
                "ORDER BY request_id, created_at, id"
            ),
            {"ids": IDS},
        ).mappings().all()

    per_run_rows: dict[int, list[dict]] = {r: [] for r in IDS}
    for r in rows:
        per_run_rows[r["request_id"]].append(dict(r))

    for rid, rs in per_run_rows.items():
        asks: list[dict] = []
        current: list[dict] = []

        def _flush() -> None:
            if not current:
                return
            total = sum((c["latency_ms"] or 0) for c in current) / 1000.0
            asks.append(
                {
                    "stage": current[0]["stage"],
                    "writer": current[0]["writer"],
                    "seconds": round(total, 1),
                    "rows": len(current),
                    "models": sorted({c["model"] for c in current}),
                    "start_ts": current[0]["ts"],
                }
            )
            current.clear()

        for r in rs:
            same_scope = bool(
                current
                and r["stage"] == current[-1]["stage"]
                and r["writer"] == current[-1]["writer"]
            )
            # attempt resetting to 1 starts a new logical ask; a rising attempt
            # (retry) or a different model at the same attempt (failover) does
            # not — that is exactly the "inclusive of failovers" the DoD means.
            continues = same_scope and int(r["attempt"] or 1) > 1
            if not continues:
                _flush()
            current.append(r)
        _flush()

        # Stage spans. The `WatchBmv` log lines ("build+fix-loop finished in
        # Ns") carry no request id, so with three runs interleaved they cannot
        # be attributed. `ai_usage_events` can: span = first call start to last
        # call end, per (request, stage).
        spans: dict[str, dict] = {}
        for r in rs:
            stage = r["stage"] or "(none)"
            start = float(r["ts"])
            end = start + (r["latency_ms"] or 0) / 1000.0
            s = spans.setdefault(
                stage, {"start": start, "end": end, "calls": 0, "ai_seconds": 0.0}
            )
            s["start"] = min(s["start"], start)
            s["end"] = max(s["end"], end)
            s["calls"] += 1
            s["ai_seconds"] += (r["latency_ms"] or 0) / 1000.0
        out.setdefault("stage_spans", {})[rid] = {
            stage: {
                "span_s": round(v["end"] - v["start"], 1),
                "ai_s": round(v["ai_seconds"], 1),
                "calls": v["calls"],
            }
            for stage, v in sorted(spans.items(), key=lambda kv: -kv[1]["ai_seconds"])
        }

        durations = [a["seconds"] for a in asks]
        out["asks"][rid] = {
            "logical_asks": len(asks),
            "rows": len(rs),
            "p50_ask_s": round(_p(durations, 0.5), 1),
            "max_ask_s": round(max(durations) if durations else 0.0, 1),
            "over_120s": [a for a in asks if a["seconds"] > 120.0],
            "ai_seconds_total": round(sum(durations), 1),
        }

    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
