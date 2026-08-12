"""Summarises the cells of one label into the table an evidence doc quotes.

    python scripts/aggregate_run.py <label>

Replaces docs/evidence/session34/aggregate_fullset.py, which globbed
`scripts/out/bakeoff/*/*__<label>/images/*/*_0.json`. That path only exists
for a FROZEN replay: since session 35 a cell is a customer run, so its
screens and their per-screen metadata live under UPLOADS_DIR/images/<id>/
like everyone else's. The session-34 script is left alone as the record of
how that table was produced; this one reads both layouts.

Cost is taken from the `ledger` block bakeoff already wrote into
results.json, NOT by opening consultant.db. Those numbers were summed by
the same process that made the calls, inside its own session — whereas a
reader opening the SQLite file over a bind mount while the service is
running can miss everything still sitting in the WAL and report a run as
free. The ledger in results.json cannot lie that way.
"""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_PATH = os.path.join(SERVICE_DIR, "scripts", "out", "bakeoff", "results.json")


def _meta_paths(row: dict) -> list[str]:
    """Where this cell's per-screen metadata landed, which depends on the
    path it took."""
    if row.get("pipeline", "frozen") == "frozen":
        out_dir = os.path.join(SERVICE_DIR, row["out_dir"])
        return sorted(glob.glob(os.path.join(out_dir, "images", "*", "*_0.json")))
    from app.config import settings

    return sorted(glob.glob(
        os.path.join(settings.UPLOADS_DIR, "images", str(row["request_id"]), "*_0.json"),
    ))


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else ""
    if not label:
        sys.exit("usage: aggregate_run.py <label>")
    with open(RESULTS_PATH, encoding="utf-8") as f:
        rows = [r for r in json.load(f) if r.get("label") == label]
    if not rows:
        sys.exit(f"no cells with label {label!r} in {RESULTS_PATH}")

    modes = {r.get("pipeline", "frozen") for r in rows}
    if len(modes) > 1:
        print(f"WARNING: label {label!r} mixes {sorted(modes)} cells — they share no spec, "
              f"screen count or cost base. Split the label before quoting a mean.\n")

    screens: list[dict] = []
    for row in rows:
        for meta_path in _meta_paths(row):
            m = json.load(open(meta_path, encoding="utf-8"))
            defects = m.get("defects") or {}
            confirmed = defects.get("confirmed") or []
            cands = m.get("candidates") or []
            screens.append({
                "brief": row["brief"], "request": row["request_id"], "screen": m["screen"],
                "score": m.get("qa_score"),
                "text_truth": (m.get("text_truth") or {}).get("passed"),
                "claims": defects.get("claims"),
                "confirmed": len(confirmed),
                "kinds": ",".join(c["kind"] for c in confirmed),
                "best_effort": not any(c.get("approved") and c.get("selected") for c in cands),
            })

    print(f"{'brief':10} {'screen':22} {'score':>5} {'text':>5} {'claims':>6} {'conf':>4} "
          f"{'shipped-clean':>13} {'best-effort':>11}")
    for s in screens:
        clean = "YES" if not s["confirmed"] else "NO:" + s["kinds"]
        print(f"{s['brief']:10} {s['screen']:22} {s['score']!s:>5} {s['text_truth']!s:>5} "
              f"{s['claims']!s:>6} {s['confirmed']!s:>4} {clean:>13} {str(s['best_effort']):>11}")

    print()
    for row in rows:
        led = row["ledger"]
        note = "" if not row.get("is_failed") else f"  RUN FAILED ({row.get('status')})"
        print(f"{row['brief']:10} request {row['request_id']}: ${led['cost_total']:.4f} "
              f"({led['image_calls_ok']} image calls, {led['image_calls_failed']} failed) "
              f"{row['wall_s']:.0f}s  /studio/{row['request_id']}{note}")

    total = sum(r["ledger"]["cost_total"] for r in rows)
    below_8 = sum(1 for s in screens if (s["score"] or 0) < 8)
    with_defect = sum(1 for s in screens if s["confirmed"])
    text_fail = sum(1 for s in screens if s["text_truth"] is not True)
    # "Cost per brief" means cost per brief that DELIVERED. A brief that
    # produced nothing (a dead key, a failed stage) spent ~$0 and would drag
    # the mean down while making the product look cheaper than it is.
    delivered = [r for r in rows if any(s["request"] == r["request_id"] for s in screens)]
    empty = [r for r in rows if r not in delivered]
    print(f"\npipeline: {'/'.join(sorted(modes))}   briefs: {len(rows)}   screens: {len(screens)}")
    print(f"below 8: {below_8}   shipped-with-confirmed-defect: {with_defect}   "
          f"text-truth failures: {text_fail}")
    print(f"total: ${total:.4f}   mean/brief: "
          f"${sum(r['ledger']['cost_total'] for r in delivered) / max(1, len(delivered)):.4f} "
          f"over {len(delivered)} brief(s) that delivered")
    if empty:
        print(f"NOT counted in the mean — produced no screens: "
              + ", ".join(f"{r['brief']} (${r['ledger']['cost_total']:.4f})" for r in empty))


if __name__ == "__main__":
    main()
