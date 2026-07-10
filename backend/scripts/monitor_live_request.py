"""Submit a live BMV request and monitor until done; print duration."""
from __future__ import annotations

import json
import os
import time
import uuid
import urllib.request
from datetime import datetime, timezone

BASE = os.environ.get("BMV_API_BASE", "https://bmv-api.onrender.com").rstrip("/")


def get(url: str, timeout: int = 60) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def post_form(url: str, fields: dict) -> dict:
    boundary = "----BMV" + uuid.uuid4().hex
    parts: list[str] = []
    for k, v in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n"
        )
    body = ("".join(parts) + f"--{boundary}--\r\n").encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def main() -> None:
    import os
    import sys

    rid_env = (os.getenv("MONITOR_REQUEST_ID") or "").strip()
    if len(sys.argv) > 1:
        rid_env = sys.argv[1]

    if rid_env:
        rid = int(rid_env)
        print("monitor existing", rid, datetime.now(timezone.utc).isoformat(), flush=True)
    else:
        print("submit", datetime.now(timezone.utc).isoformat(), flush=True)
        created = post_form(
            f"{BASE}/api/requests",
            {
                "business_name": "Cafe Nova",
                "business_description": (
                    "Neighborhood specialty coffee shop with online ordering, "
                    "loyalty, and table reservations."
                ),
                "email": "monitor@buildmyversion.test",
                "industry": "Restaurants & Cafes",
                "target_customers": "Local coffee drinkers and remote workers",
                "main_problem": "Too many phone orders and no-shows",
                "desired_outcome": "Live MVP with menu, ordering, reservations, owner dashboard",
                "project_type": "new",
                "needs_ai": "yes",
                "budget_range": "under_5k",
                "timeline": "asap",
                "what_you_like": "Clean menu UX and AI allergen answers",
            },
        )
        rid = created["id"]
        print("created", created, flush=True)
    print(f"watch https://bmv-web.onrender.com/result/{rid}", flush=True)

    last = None
    last_change = time.time()
    t0 = time.time()
    prog: dict = {}
    prev: dict = {}
    pa: dict = {}
    outcome = "TIMEOUT"

    # Full live codegen (plan + architect + ~20 files + npm build) can take 30–45+ min on free Render.
    while time.time() - t0 < 3600:
        try:
            prog = get(f"{BASE}/api/requests/{rid}/progress")
            prev = get(f"{BASE}/api/requests/{rid}/preview")
        except Exception as e:
            print(f"poll err: {e}", flush=True)
            time.sleep(12)
            continue

        gp = prev.get("generated_pages") or {}
        pa = (gp.get("preview_app") if isinstance(gp, dict) else {}) or {}
        snap = (prog.get("stage"), prog.get("pct"), prog.get("label"), pa.get("status"))
        if snap != last:
            print(
                f"[{int(time.time() - t0)}s] {prog.get('pct')}% | {prog.get('stage')} | "
                f"{prog.get('label')} | app={pa.get('status')}",
                flush=True,
            )
            last = snap
            last_change = time.time()

        if prog.get("stage") == "failed" or prev.get("status") == "failed":
            outcome = "FAILED"
            break
        if prog.get("stage") == "done" or prog.get("pct") == 100:
            outcome = "SUCCESS"
            break
        # Worker likely dead on free Render if no progress for 25+ minutes
        if time.time() - last_change > 1500:
            outcome = "STUCK"
            print(
                f"No progress for {int(time.time() - last_change)}s — treating as stuck",
                flush=True,
            )
            break
        time.sleep(15)

    print("OUTCOME", outcome, flush=True)
    log = prog.get("log") or []
    ts = [e.get("t") for e in log if isinstance(e.get("t"), (int, float))]
    if len(ts) >= 2:
        dur = ts[-1] - ts[0]
        print(f"duration_sec {int(dur)}", flush=True)
        print(f"duration_min {dur / 60:.1f}", flush=True)
        print("start", datetime.fromtimestamp(ts[0], tz=timezone.utc).isoformat(), flush=True)
        print("end", datetime.fromtimestamp(ts[-1], tz=timezone.utc).isoformat(), flush=True)
        print("TIMELINE", flush=True)
        for e in log:
            print(f"  +{int(e['t'] - ts[0]):4d}s  {e.get('msg')}", flush=True)

    print("concept", prev.get("concept_name"), "fit", prev.get("business_fit_score"), flush=True)
    print("preview_app", pa, flush=True)
    print("wall_sec", int(time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
