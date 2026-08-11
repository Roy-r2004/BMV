"""Aggregates the s34-full golden-set run into the re-measure table.

Per screen: QA score of what shipped, text-truth, defect claims vs
confirmed on the SELECTED candidate, whether a regeneration fired, and
per-brief ledger cost. Compares shipped scores against the s33 baseline
table hard-coded from docs/evidence/session33/dod-assessment.md.

Run: docker run --rm -v "$PWD:/repo" -w /repo/consultant-service \
  --entrypoint sh bmv-consultant-py -c \
  'python /repo/docs/evidence/session34/aggregate_fullset.py <label>'
"""

import glob
import json
import sqlite3
import sys

LABEL = sys.argv[1] if len(sys.argv) > 1 else "s34-full"

S33_SCORES = {  # brief/screen -> shipped QA score, session 33
    ("dental", "dashboard"): 8.1, ("dental", "schedule"): 8.7, ("dental", "analytics"): 8.1,
    ("law", "dashboard"): 7.5, ("law", "pipeline"): 8.7, ("law", "analytics"): 7.5,
    ("retail", "analytics"): 9.2, ("retail", "dashboard"): 8.7, ("retail", "customers"): 9.2,
    ("salon", "dashboard"): 7.9, ("salon", "schedule"): 9.1, ("salon", "analytics"): 8.4,
    ("hedgefund", "analytics"): 8.7, ("hedgefund", "dashboard"): 7.9, ("hedgefund", "customers"): 8.5,
}

rows = []
for meta_path in sorted(glob.glob(f"scripts/out/bakeoff/*/*__{LABEL}/images/*/*_0.json")):
    brief = meta_path.split("bakeoff/")[1].split("/")[0]
    m = json.load(open(meta_path))
    screen = m["screen"]
    cands = m["candidates"]
    request_id = m["business_id"]
    defects = m.get("defects") or {}
    rows.append({
        "brief": brief, "screen": screen, "request": request_id,
        "score": m["qa_score"],
        "text_truth": (m.get("text_truth") or {}).get("passed"),
        "claims": defects.get("claims"),
        "confirmed": len(defects.get("confirmed") or []),
        "confirmed_kinds": [c["kind"] for c in (defects.get("confirmed") or [])],
        "candidates": len(cands),
        "rejected_by_defect": sum(1 for c in cands if (c.get("defects_confirmed") or 0) > 0),
        "best_effort": not any(c["approved"] and c["selected"] for c in cands),
    })

request_ids = sorted({r["request"] for r in rows})
conn = sqlite3.connect("/repo/consultant-service/consultant.db")
costs = {}
for rid in request_ids:
    total, images = conn.execute(
        "SELECT COALESCE(SUM(cost_usd),0),"
        " COALESCE(SUM(CASE WHEN purpose='image' THEN cost_usd END),0)"
        " FROM ai_usage_events WHERE request_id=?", (rid,),
    ).fetchone()
    n_images = conn.execute(
        "SELECT COUNT(*) FROM ai_usage_events WHERE request_id=? AND purpose='image' AND success=1", (rid,),
    ).fetchone()[0]
    costs[rid] = {"total": round(total, 4), "images": round(images, 4), "image_calls": n_images}

print(f"{'brief':10} {'screen':22} {'s33':>5} {'s34':>5} {'text':>5} {'claims':>6} {'conf':>4} {'shipped-clean':>13} {'best-effort':>11}")
shipped_confirmed = 0
below_8 = 0
for r in rows:
    s33 = S33_SCORES.get((r["brief"], r["screen"].replace("_dashboard", "").replace("_overview", "")), "-")
    clean = "YES" if r["confirmed"] == 0 else "NO:" + ",".join(r["confirmed_kinds"])
    if r["confirmed"]:
        shipped_confirmed += 1
    if (r["score"] or 0) < 8:
        below_8 += 1
    print(f"{r['brief']:10} {r['screen']:22} {s33!s:>5} {r['score']!s:>5} {r['text_truth']!s:>5} {r['claims']!s:>6} {r['confirmed']!s:>4} {clean:>13} {str(r['best_effort']):>11}")

print()
total = sum(c["total"] for c in costs.values())
for rid in request_ids:
    print(f"request {rid}: ${costs[rid]['total']:.4f} ({costs[rid]['image_calls']} image calls)")
print(f"\nscreens: {len(rows)}  below 8: {below_8}  shipped-with-confirmed-defect: {shipped_confirmed}")
print(f"total: ${total:.4f}  mean/brief: ${total / max(1, len(request_ids)):.4f}")
