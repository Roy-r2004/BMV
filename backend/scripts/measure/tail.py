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

#: Trio keys, mirroring `analyse.py`. This list used to be nine hardcoded run
#: ids with no way to pass others, so it silently reported nothing for trio 7 —
#: the runs it skips are exactly the ones that stored no `elapsed_seconds`, and
#: it prints one line about that and moves on. Q10 went unanswered in the first
#: write-up for no better reason than this. Trio 6 is absent deliberately: it is
#: void on credits and giving it a key here would invite a citation.
_TRIOS: dict[str, list[int] | None] = {
    "1": [74, 75, 76],
    "2": [77, 78, 79],
    "3": [80, 81, 82],
    "4": [83, 84, 85],
    "5": [86, 87, 88],
    #: Void on credits, and present rather than absent on purpose. Left out of
    #: the table, `tail.py 6` would fall through to "explicit run ids" and
    #: happily decompose request **6** — an unrelated run from another week,
    #: reported without a word about the substitution.
    "6": None,
    "7": [92, 93, 94],
    #: The nine-run corpus the 33 %-AI / 67 %-non-AI decomposition came from.
    "baseline": [74, 75, 76, 77, 78, 79, 80, 81, 82],
}


def _runs(argv: list[str]) -> list[int]:
    """Trio key, explicit run ids, or the historical default."""

    if not argv:
        runs = _TRIOS["baseline"]
        assert runs is not None
        return runs
    if argv[0] in _TRIOS:
        runs = _TRIOS[argv[0]]
        if runs is None:
            raise ValueError(
                f"trio {argv[0]} is void — its numbers must not be cited. "
                "Pass explicit run ids if you really mean those requests."
            )
        return runs
    return [int(value) for value in argv]


TOTAL = 540.0


def main() -> None:
    RUNS = _runs(sys.argv[1:])
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
            # Said out loud. A run that finished inside its deadline and a run
            # this tool could not read are different facts, and skipping both in
            # silence is how the nine-run corpus read as "every run has a tail".
            print(f"{rid:>4}  (finished {-tail:.1f}s inside the deadline — no tail)")
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
