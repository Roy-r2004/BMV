#!/usr/bin/env python3
"""DoD 6, the measurement half: fitted pipeline p50/p95 by convolution.

QUESTION. The parked DoD row says "p50 <= 500 s". What p50/p95 does the stored
latency evidence actually imply, stage by stage, when the per-stage
distributions are convolved rather than a mean scaled? (The measured per-call
p95/p50 ratio is ~2.4x — scaling a mean by anything is exactly the mistake this
script exists to not make.)

METHOD. Monte Carlo convolution over REAL per-run stage totals from
`ai_usage_events`, one independent draw per stage per iteration, summed;
p50/p95 read off the sorted draw distribution. Two metrics are convolved
separately because the corpus proves they are different things:

* **ai_total** — sum of `latency_ms` over a run's calls in a stage: model
  seconds bought. NOT comparable to wall clock: calls inside a stage run in
  parallel (run 141: 1136 s of AI inside a 532 s event span).
* **wall_span** — max(call end) - min(call start) per (run, stage), where a
  call's start is `created_at - latency_ms` (`created_at` is logged at call
  END; verified against request 141's timeline, whose first call's start
  coincides with the request row's `created_at`). This is the stage's
  occupancy on the run's clock and is the metric the <= 500 s row is about.
  For the wall convolution a pseudo-stage "(remainder)" — the run's measured
  wall clock minus the sum of its stage spans — carries the non-AI time
  (build, validate, gaps), resampled from real runs like any stage.

JUDGMENT CALLS, stated rather than buried:

1. **Window: complete runs with request_id >= 129 only.** R6 landed
   writer/attempt on every ask row and full per-stage scoping starts at 129;
   before that, unscoped calls fell back to the run purpose (see
   `codegen_cost.py`: everything unscoped lands in `codegen`), so pre-129
   per-stage totals systematically misattribute. The 853 rows with
   `request_id IS NULL` cannot be grouped into runs at all. Both are excluded,
   which is a small-corpus trade made on purpose: 8 clean runs beat 3,900
   misattributed rows.
2. **"Complete run"** = `requests.status != 'failed'` AND the run has at least
   one `codegen` row and one `demo` row. The failed 2-stage runs (130, 131,
   133, ...) died in appspec/blueprint and contain no pipeline to convolve.
3. **Real per-run stage totals are resampled, not synthesized** from per-call
   draws x a call-count distribution. The stored totals already carry the
   within-stage structure (parallel bursts, retries, the call-count/latency
   correlation) that a synthetic independence model would erase. Per-call
   independence was the fallback only if per-run totals were unavailable;
   they are available for every windowed run.
4. **A stage absent from a run contributes 0 for that run** (refine ran in 6
   of 8 runs, analyze in 2). Absence is a real outcome of a real run, so it
   stays in the empirical set rather than being imputed away.
5. **Failed calls count.** Time bought and discarded is still pipeline time
   (run 141 spent 52 s on five refine calls that all failed).
6. **What independence cannot represent, said out loud:** the pipeline has a
   ~540 s deadline that CUTS late stages (141's refine calls all end at
   +540.0 s exactly). Long early stages eat late stages' budget — the joint
   distribution is negatively correlated by construction, so independent
   convolution OVERSTATES spread (p95 especially). The sanity anchors below
   (the 8 real joint sums, and `requests.updated_at - created_at` as measured
   wall clock) are printed next to the convolved numbers so the reader sees
   the gap, not a blended lie.
7. **Percentiles** are linear interpolation on the sorted sample (type-7).
   Per-stage p95 over 8 runs interpolates near the max — reported anyway,
   labeled with n, because a small corpus reported small beats a padded one.

RED-EXITS (a rerun can never silently measure the wrong thing): required
columns missing; total row count below the 3,933 known at writing (growth is
fine, shrinkage is data loss); no complete runs in the window; a windowed row
with NULL `latency_ms` or NULL `stage`; a request row missing timestamps.

Read-only. Run inside the api container:

    docker exec -w /app/backend bmv-api python3 scripts/measure/latency_convolution.py
    docker exec -w /app/backend bmv-api python3 scripts/measure/latency_convolution.py --json-out /tmp/latency_convolution.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Runs inside the api container (`/app/backend`) or from a repo checkout.
for _candidate in ("/app/backend", str(Path(__file__).resolve().parents[2])):
    if (Path(_candidate) / "app").is_dir():
        if _candidate not in sys.path:
            sys.path.insert(0, _candidate)
        break
else:  # pragma: no cover - misplaced checkout
    raise SystemExit("cannot locate the `app` package from either /app/backend or the repo")

import sqlalchemy as sa  # noqa: E402

#: First request with full per-stage `ai_call` scoping (R6). Judgment call 1.
WINDOW_START = 129
#: Rows known to exist when this was written. Fewer means data loss: RED-EXIT.
KNOWN_ROWS = 3933
#: Reproducibility: today's date as the seed, >= 100k draws per the task.
SEED = 20260807
DRAWS = 200_000
#: The pseudo-stage carrying wall clock not inside any stage span (call 6).
REMAINDER = "(remainder)"

_REQUIRED_COLUMNS = {
    "request_id", "stage", "writer", "attempt", "latency_ms", "created_at", "success",
}


def _red_exit(msg: str) -> None:
    sys.exit(f"\nRED-EXIT: {msg}\n         A baked assumption drifted; fix the assumption, "
             "do not trust any number this run printed.")


def pct(sorted_vals: list[float], q: float) -> float:
    """Type-7 (linear interpolation) percentile of an ascending list."""
    n = len(sorted_vals)
    if n == 0:
        raise ValueError("percentile of an empty list")
    if n == 1:
        return sorted_vals[0]
    pos = q * (n - 1)
    lo = int(pos)
    frac = pos - lo
    if lo + 1 >= n:
        return sorted_vals[-1]
    return sorted_vals[lo] * (1 - frac) + sorted_vals[lo + 1] * frac


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default=None,
                    help="also write the machine-readable result to this path")
    args = ap.parse_args()

    from app.core.config import settings  # live config, never backend/.env

    eng = sa.create_engine(settings.DATABASE_URL)
    with eng.connect() as c:
        cols = {r[0] for r in c.execute(sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='ai_usage_events'"))}
        missing = _REQUIRED_COLUMNS - cols
        if missing:
            _red_exit(f"ai_usage_events is missing expected columns {sorted(missing)} "
                      f"— schema drifted since session 25")
        total_rows = c.execute(sa.text("SELECT COUNT(*) FROM ai_usage_events")).scalar()
        if total_rows < KNOWN_ROWS:
            _red_exit(f"ai_usage_events has {total_rows} rows, fewer than the {KNOWN_ROWS} "
                      "known at writing — rows were deleted, the corpus is not the one measured")

        req_rows = c.execute(sa.text(
            "SELECT id, status, created_at, updated_at FROM requests WHERE id >= :w"),
            {"w": WINDOW_START}).fetchall()
        req_meta = {r[0]: r for r in req_rows}

        ev = c.execute(sa.text(
            "SELECT request_id, stage, created_at, latency_ms FROM ai_usage_events "
            "WHERE request_id >= :w ORDER BY created_at"), {"w": WINDOW_START}).fetchall()

    if not ev:
        _red_exit(f"no ai_usage_events rows with request_id >= {WINDOW_START} — "
                  "the window is empty")

    by_run: dict[int, list] = defaultdict(list)
    for rid, stage, created, lat in ev:
        if stage is None:
            _red_exit(f"request {rid} has a row with NULL stage inside the >= {WINDOW_START} "
                      "window — full per-stage scoping was the window's premise")
        if lat is None:
            _red_exit(f"request {rid} has a row with NULL latency_ms — the known NULL-latency "
                      "issue was believed confined to old rows")
        by_run[rid].append((stage, created, lat))

    complete: list[int] = []
    for rid, rows in sorted(by_run.items()):
        meta = req_meta.get(rid)
        stages_here = {s for s, _c, _l in rows}
        if meta and meta[1] != "failed" and "codegen" in stages_here and "demo" in stages_here:
            if meta[2] is None or meta[3] is None:
                _red_exit(f"request {rid} lacks created_at/updated_at — no wall clock anchor")
            complete.append(rid)
    if not complete:
        _red_exit("zero complete runs in the window — nothing to convolve")

    # ---- per (run, stage) totals -----------------------------------------
    ai_total: dict[int, dict[str, float]] = {}
    wall_span: dict[int, dict[str, float]] = {}
    calls: dict[int, dict[str, int]] = {}
    stage_first_start: dict[str, list[float]] = defaultdict(list)
    run_wall: dict[int, float] = {}
    run_ai_sum: dict[int, float] = {}
    run_span_sum: dict[int, float] = {}
    run_remainder: dict[int, float] = {}
    all_lat: list[float] = []

    for rid in complete:
        rows = by_run[rid]
        meta = req_meta[rid]
        run_wall[rid] = (meta[3] - meta[2]).total_seconds()
        t0: datetime | None = None
        per_stage: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)
        for stage, created, lat in rows:
            start = created - timedelta(milliseconds=lat)
            t0 = start if t0 is None or start < t0 else t0
            per_stage[stage].append((start, created))
            all_lat.append(lat / 1000.0)
        ai_total[rid], wall_span[rid], calls[rid] = {}, {}, {}
        for stage, iv in per_stage.items():
            ai_total[rid][stage] = sum((e - s).total_seconds() for s, e in iv)
            wall_span[rid][stage] = (max(e for _s, e in iv)
                                     - min(s for s, _e in iv)).total_seconds()
            calls[rid][stage] = len(iv)
            stage_first_start[stage].append((min(s for s, _e in iv) - t0).total_seconds())
        run_ai_sum[rid] = sum(ai_total[rid].values())
        run_span_sum[rid] = sum(wall_span[rid].values())
        run_remainder[rid] = run_wall[rid] - run_span_sum[rid]

    stages = sorted(stage_first_start,
                    key=lambda s: pct(sorted(stage_first_start[s]), 0.5))

    #: Judgment call 4: absent stage -> 0 for that run.
    ai_sets = {s: [ai_total[r].get(s, 0.0) for r in complete] for s in stages}
    wall_sets = {s: [wall_span[r].get(s, 0.0) for r in complete] for s in stages}
    wall_sets[REMAINDER] = [run_remainder[r] for r in complete]

    # ---- Monte Carlo convolution -----------------------------------------
    rng = random.Random(SEED)

    def convolve(sets: dict[str, list[float]]) -> list[float]:
        keys = list(sets.values())
        out = []
        for _ in range(DRAWS):
            out.append(sum(vals[rng.randrange(len(vals))] for vals in keys))
        out.sort()
        return out

    mc_ai = convolve(ai_sets)
    mc_wall = convolve(wall_sets)

    # ---- report ----------------------------------------------------------
    n = len(complete)
    lat_sorted = sorted(all_lat)
    call_p50, call_p95 = pct(lat_sorted, 0.5), pct(lat_sorted, 0.95)
    print("DoD 6 (measurement half) — pipeline p50/p95 by convolution, never a scaled mean")
    print(f"  window     : complete runs with request_id >= {WINDOW_START} "
          f"(full per-stage scoping)")
    print(f"  runs       : {n} — {complete}  (small corpus, reported small)")
    nz = sorted(v for v in all_lat if v > 0)
    nz_p50, nz_p95 = pct(nz, 0.5), pct(nz, 0.95)
    print(f"  calls      : {len(lat_sorted)} ask rows; per-call p50 {call_p50:.1f} s, "
          f"p95 {call_p95:.1f} s, ratio {call_p95 / call_p50:.1f}x "
          f"(the ratio that forbids scaling a mean)")
    print(f"               excluding the {len(lat_sorted) - len(nz)} instant (0 ms) refusal "
          f"rows: p50 {nz_p50:.1f} s, p95 {nz_p95:.1f} s, ratio {nz_p95 / nz_p50:.1f}x "
          f"(the historical 2.4x was a per-call ratio of this kind)")
    print(f"  seed/draws : {SEED} / {DRAWS:,}")
    print()

    def stage_table(title: str, sets: dict[str, list[float]], mc: list[float]) -> dict:
        p50_pipe, p95_pipe = pct(mc, 0.5), pct(mc, 0.95)
        mean_pipe = sum(mc) / len(mc)
        print(title)
        print(f"  {'stage':<16} {'runs':>4} {'calls':>9} {'p50 s':>8} {'p95 s':>8} "
              f"{'mean s':>8} {'share of mean':>14}")
        out = {}
        for s in sets:
            vals = sorted(sets[s])
            present = sum(1 for v in sets[s] if v > 0)
            cs = sorted(calls[r].get(s, 0) for r in complete) if s != REMAINDER else []
            call_str = (f"{cs[0]}-{cs[-1]}" if cs else "-")
            mean = sum(vals) / len(vals)
            out[s] = {"runs_present": present, "n_runs": len(vals),
                      "calls_min": cs[0] if cs else None, "calls_max": cs[-1] if cs else None,
                      "p50_s": round(pct(vals, 0.5), 1), "p95_s": round(pct(vals, 0.95), 1),
                      "mean_s": round(mean, 1),
                      "share_of_mean": round(mean / (sum(mc) / len(mc)), 4)}
            print(f"  {s:<16} {present:>3}/{len(vals)} {call_str:>9} "
                  f"{pct(vals, 0.5):>8.1f} {pct(vals, 0.95):>8.1f} {mean:>8.1f} "
                  f"{mean / mean_pipe:>13.1%}")
        print(f"  {'PIPELINE (MC)':<16} {'':>4} {'':>9} {p50_pipe:>8.1f} {p95_pipe:>8.1f} "
              f"{mean_pipe:>8.1f} {'100.0%':>14}")
        print()
        return {"stages": out, "mc_p50_s": round(p50_pipe, 1),
                "mc_p95_s": round(p95_pipe, 1), "mc_mean_s": round(mean_pipe, 1)}

    wall_block = stage_table(
        "WALL-SPAN convolution — stage occupancy on the run clock; the <= 500 s row's metric",
        wall_sets, mc_wall)
    ai_block = stage_table(
        "AI-TOTAL convolution — model seconds bought (calls overlap; NOT wall clock)",
        ai_sets, mc_ai)

    real_wall = sorted(run_wall.values())
    real_span_sum = sorted(run_span_sum.values())
    real_ai = sorted(run_ai_sum.values())
    print("SANITY ANCHORS — the real joint distribution vs the independence assumption")
    print(f"  measured wall clock (requests.updated_at - created_at), n={n}:")
    print(f"    p50 {pct(real_wall, 0.5):.1f} s   p95 {pct(real_wall, 0.95):.1f} s   "
          f"min-max {real_wall[0]:.1f}-{real_wall[-1]:.1f} s")
    print(f"  real per-run sum of stage spans + remainder == wall by construction; "
          f"real sum of spans alone: p50 {pct(real_span_sum, 0.5):.1f} s")
    print("  (a negative remainder is real: the critique->refine loop INTERLEAVES its two"
          " stages at the tail, so per-stage spans double-count that window and the signed"
          " remainder absorbs it.)")
    print(f"  real per-run AI totals, n={n}: p50 {pct(real_ai, 0.5):.1f} s   "
          f"min-max {real_ai[0]:.1f}-{real_ai[-1]:.1f} s")
    gap50 = wall_block["mc_p50_s"] - pct(real_wall, 0.5)
    gap95 = wall_block["mc_p95_s"] - pct(real_wall, 0.95)
    print(f"  convolved wall p50 - measured wall p50 : {gap50:+.1f} s")
    print(f"  convolved wall p95 - measured wall p95 : {gap95:+.1f} s")
    print("  reading: the ~540 s deadline cuts late stages (141's refine dies at +540.0 s"
          " exactly), so real stage durations are negatively correlated; independent"
          " convolution therefore overstates spread — expected and observed at p95.")
    print()
    print("VERDICT next to the parked row: DoD asks p50 <= 500 s; "
          f"convolved wall p50 is {wall_block['mc_p50_s']:.1f} s and measured wall p50 is "
          f"{pct(real_wall, 0.5):.1f} s.")

    if args.json_out:
        payload = {
            "meta": {
                "script": "latency_convolution.py", "session": 25,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "window_start_request": WINDOW_START, "seed": SEED, "draws": DRAWS,
                "table_rows_total": total_rows, "complete_runs": complete,
                "n_complete_runs": n, "ask_rows_in_window": len(lat_sorted),
            },
            "per_call": {"p50_s": round(call_p50, 1), "p95_s": round(call_p95, 1),
                         "p95_over_p50": round(call_p95 / call_p50, 2),
                         "nonzero_p50_s": round(nz_p50, 1), "nonzero_p95_s": round(nz_p95, 1),
                         "nonzero_p95_over_p50": round(nz_p95 / nz_p50, 2),
                         "zero_ms_refusal_rows": len(lat_sorted) - len(nz)},
            "wall_span_convolution": wall_block,
            "ai_total_convolution": ai_block,
            "anchors": {
                "measured_wall_p50_s": round(pct(real_wall, 0.5), 1),
                "measured_wall_p95_s": round(pct(real_wall, 0.95), 1),
                "measured_wall_min_s": round(real_wall[0], 1),
                "measured_wall_max_s": round(real_wall[-1], 1),
                "real_ai_total_p50_s": round(pct(real_ai, 0.5), 1),
                "gap_convolved_minus_measured_p50_s": round(gap50, 1),
                "gap_convolved_minus_measured_p95_s": round(gap95, 1),
            },
            "per_run": {str(r): {
                "wall_s": round(run_wall[r], 1),
                "sum_stage_spans_s": round(run_span_sum[r], 1),
                "remainder_s": round(run_remainder[r], 1),
                "ai_total_s": round(run_ai_sum[r], 1),
                "stages": {s: {"calls": calls[r][s],
                               "ai_total_s": round(ai_total[r][s], 1),
                               "wall_span_s": round(wall_span[r][s], 1)}
                           for s in ai_total[r]},
            } for r in complete},
        }
        Path(args.json_out).write_text(json.dumps(payload, indent=2) + "\n")
        print(f"\n[json written to {args.json_out}]")


if __name__ == "__main__":
    main()
