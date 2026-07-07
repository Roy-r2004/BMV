import sys
import time

import requests

req_id = int(sys.argv[1]) if len(sys.argv) > 1 else 4
purl = f"http://127.0.0.1:8000/api/requests/{req_id}/progress"
pvurl = f"http://127.0.0.1:8000/api/requests/{req_id}/preview"

last = None
for i in range(180):
    try:
        p = requests.get(purl, timeout=15).json()
        stage = p.get("stage", "")
        pct = p.get("pct", 0)
        label = "{:3d}% | {:14s} | {}".format(pct, stage, p.get("label", ""))
        if label != last:
            print(f"[{i*10:4d}s] {label}", flush=True)
            last = label
        # Only trust terminal stages emitted by *this* run — pct must reach the
        # actual end-of-pipeline markers, not a stale preview_app.status field
        # left over from a previous generation.
        if stage in ("done", "build_failed") and pct >= 89:
            prev = requests.get(pvurl, timeout=15).json()
            pa = (prev.get("generated_pages") or {}).get("preview_app") or {}
            print("FINAL STATUS:", pa.get("status"), pa.get("url"))
            break
    except Exception as e:
        print(f"poll err: {e}", flush=True)
    time.sleep(10)
