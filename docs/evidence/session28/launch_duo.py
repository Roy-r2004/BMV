#!/usr/bin/env python3
"""Session 28's verification DUO — the two runs the 162-164 trio lost — the three briefs that exercise every fix.

Same launcher as `session26/launch_trio.py` (simultaneous POSTs from three
threads, no stagger) with one trio instead of two. The three businesses are
**re-runs of session 26's**, deliberately: this trio is a controlled comparison
against the six runs that found the defects, not a coverage sweep.

    146 Kestrel & Fern Bakehouse   plain   href mask
    148 Ridgeline Bike Works       file    href mask, schedule face, booking route,
                                           catalogue base, journey hop resolution
    150 Copperline Hardware        plain   schedule face, booking route, next hop

Halcyon Sound Studio (149) is deliberately not here: it fails on the AppSpec
`state_ids` backfill, which none of this work touched.

The `file` run uses **the exact image request 148 was given** — copied out of
`bmv-api:/app/data/uploads/` by `reference_file_path` — so the only variable
between the two runs is the pipeline.

    TRIO_REFDIR=/path/to/refimg python3 launch_trio.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import requests

BASE = os.environ.get("TRIO_BASE", "http://127.0.0.1:8001")
REFDIR = Path(os.environ.get("TRIO_REFDIR", str(Path(__file__).parent / "refimg")))
STAMP = int(time.time())

TRIO: list[dict] = [
    {
        "_mode": "plain",
        "business_name": "Kestrel & Fern Bakehouse",
        "industry": "Artisan bakery and neighbourhood cafe",
        "business_description": (
            "A neighbourhood bakehouse milling its own flour, with a rotating "
            "counter of at least fourteen breads, pastries and cakes on any "
            "given morning. Customers browse the full range, see what is baking "
            "today, and pre-order whole loaves and celebration cakes for "
            "collection."
        ),
        "target_customers": "Local residents, weekend regulars, people ordering celebration cakes",
        "main_problem": "Showing what is actually available today and taking pre-orders without phone tag",
        "desired_outcome": "A warm site where the counter is browsable and pre-orders are simple",
        "what_you_like": "",
        "needs_ai": "no",
    },
    {
        "_mode": "plain",
        "business_name": "Copperline Hardware",
        "industry": "Independent hardware store and tool hire",
        "business_description": (
            "A family hardware store carrying a deep catalogue — at least sixteen "
            "tool and garden lines on show — plus a tool-hire counter. Customers "
            "browse the catalogue, check what is in stock, and reserve hire items."
        ),
        "target_customers": "Homeowners, tradespeople, allotment gardeners",
        "main_problem": "Showing a deep catalogue and taking tool-hire reservations",
        "desired_outcome": "A practical site where the catalogue is browsable and hire is bookable",
        "what_you_like": "",
        "needs_ai": "no",
    },
]


def submit(spec: dict, results: list, idx: int) -> None:
    data = {
        k: v for k, v in spec.items()
        if not k.startswith("_") and v not in (None, "")
    }
    data.setdefault("budget_range", "Standard scope")
    data.setdefault("timeline", "1-2 months")
    data["email"] = f"duo28.{STAMP}.{idx}@example.com"

    files = None
    if spec["_mode"] == "file":
        path = REFDIR / spec["_file"]
        files = {"reference_file": (path.name, path.open("rb"), "image/jpeg")}

    t0 = time.time()
    try:
        resp = requests.post(f"{BASE}/api/requests", data=data, files=files, timeout=120)
        resp.raise_for_status()
        body = resp.json()
        results[idx] = {
            "mode": spec["_mode"],
            "business": spec["business_name"],
            "id": body["id"],
            "posted_at": t0,
            "post_latency_s": round(time.time() - t0, 2),
        }
    except Exception as exc:  # pragma: no cover - operational script
        results[idx] = {"mode": spec["_mode"], "business": spec["business_name"],
                        "error": str(exc)}


def main() -> int:
    results: list = [None] * len(TRIO)

    # Threads, not a loop: a serial loop would reintroduce the stagger session 26
    # removed, and contention is part of what the ≤ 600 s row measures.
    threads = [
        threading.Thread(target=submit, args=(spec, results, i))
        for i, spec in enumerate(TRIO)
    ]
    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    posted = [r for r in results if r and "id" in r]
    spread = (
        max(r["posted_at"] for r in posted) - min(r["posted_at"] for r in posted)
        if posted
        else 0.0
    )
    print(json.dumps({
        "trio": "session27",
        "launched_at": t0,
        "post_spread_s": round(spread, 3),
        "runs": results,
    }, indent=1))
    return 0 if len(posted) == len(TRIO) else 1


if __name__ == "__main__":
    raise SystemExit(main())
