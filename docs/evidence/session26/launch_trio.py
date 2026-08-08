#!/usr/bin/env python3
"""Launch one Phase 1 verification trio — three runs, SIMULTANEOUS start.

Twelve prior runs used a 60 s stagger and recorded `contention: 0.0` every time,
so the concurrency half of the <=600 s DoD row has never actually been tested.
`POST /api/requests` returns immediately and runs the pipeline on a background
thread, so three POSTs fired from three threads at once is a genuinely
simultaneous start — which is the point of this trio.

Each trio carries one `reference_url` run, one `reference_file` run and one plain
run on three different industries, per the DoD row's own wording. Businesses are
deliberately NEW: the database holds 131 requests across 16 business names, nine
of them art galleries, so re-running the archive would add samples without adding
coverage — and these six count toward the placeholder row's 20-business
denominator.

    python3 launch_trio.py 1|2
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import requests

import os

BASE = os.environ.get("TRIO_BASE", "http://127.0.0.1:8001")
REFDIR = Path(os.environ.get("TRIO_REFDIR", str(Path(__file__).parent / "refimg")))
STAMP = int(time.time())

TRIOS: dict[str, list[dict]] = {
    # Trio 1 — storefront-with-catalogue, booking_service, storefront+service.
    "1": [
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
            "_mode": "url",
            "reference_url": "https://www.squarespace.com",
            "business_name": "Meridian Physiotherapy",
            "industry": "Physiotherapy clinic and rehabilitation",
            "business_description": (
                "A three-therapist physiotherapy clinic treating sports injuries, "
                "post-operative rehabilitation and chronic back pain. Patients book "
                "assessments and follow-up blocks, and each therapist keeps their own "
                "schedule."
            ),
            "target_customers": "Injured amateur athletes, post-surgical patients, office workers with back pain",
            "main_problem": "Booking assessments and follow-up blocks across three therapists' calendars",
            "desired_outcome": "A calm clinical site where patients book the right therapist without calling",
            "what_you_like": "Clean typography, generous white space, an obvious booking path",
            "needs_ai": "no",
        },
        {
            "_mode": "file",
            "_file": "bakery-ref.jpg",
            "business_name": "Ridgeline Bike Works",
            "industry": "Bicycle retail, service and workshop",
            "business_description": (
                "A bike shop selling around twenty models across gravel, commuter and "
                "kids ranges, alongside a workshop that takes in repairs and annual "
                "services. Customers browse the range and book a mechanic slot."
            ),
            "target_customers": "Commuters, weekend gravel riders, parents buying a first bike",
            "main_problem": "Showing the current range and booking workshop slots in one place",
            "desired_outcome": "A site that sells the range and fills the workshop diary",
            "what_you_like": "Bold photography, a clear range grid, easy service booking",
            "needs_ai": "no",
        },
    ],
    # Trio 2 — booking_service, storefront-with-deep-catalogue, internal_ops.
    "2": [
        {
            "_mode": "url",
            "reference_url": "https://www.notion.com",
            "business_name": "Halcyon Sound Studio",
            "industry": "Recording studio and audio production",
            "business_description": (
                "A two-room recording studio hiring by the day and half-day, with "
                "engineers attached to each room. Bands and voice artists book "
                "sessions, and the studio publishes rates and room specifications."
            ),
            "target_customers": "Independent bands, voice-over artists, podcast producers",
            "main_problem": "Publishing room availability and taking session bookings",
            "desired_outcome": "A site where a band can see the rooms and book a day without emailing",
            "what_you_like": "Dark, confident, image-led, with rates stated plainly",
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
        {
            "_mode": "file",
            "_file": "office-ref.jpg",
            "business_name": "Vantage Freight Desk",
            "industry": "Freight dispatch operations console",
            "business_description": (
                "An internal dispatch console for a freight brokerage. Staff-only — "
                "this is not a public website and no customer ever sees it. "
                "Dispatchers work a queue of loads, assign carriers, track exceptions "
                "and reconcile paperwork at the back office."
            ),
            "target_customers": "Our own dispatch team and back-office staff",
            "main_problem": "Working the load queue and tracking exceptions across shifts",
            "desired_outcome": "A dense operations console the dispatch desk lives in all day",
            "what_you_like": "Dense tables, keyboard-first, no marketing anything",
            "needs_ai": "no",
        },
    ],
}


def submit(spec: dict, results: list, idx: int) -> None:
    data = {
        k: v for k, v in spec.items()
        if not k.startswith("_") and v not in (None, "")
    }
    data.setdefault("budget_range", "Standard scope")
    data.setdefault("timeline", "1-2 months")
    data["email"] = f"trio.{STAMP}.{idx}@example.com"

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
    key = sys.argv[1] if len(sys.argv) > 1 else "1"
    specs = TRIOS[key]
    results: list = [None] * len(specs)

    # Threads, not a loop: a serial loop would reintroduce the stagger this
    # trio exists to remove.
    threads = [
        threading.Thread(target=submit, args=(spec, results, i))
        for i, spec in enumerate(specs)
    ]
    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    posted = [r for r in results if r and "id" in r]
    if posted:
        spread = max(r["posted_at"] for r in posted) - min(r["posted_at"] for r in posted)
    else:
        spread = 0.0

    out = {
        "trio": key,
        "launched_at": t0,
        "post_spread_s": round(spread, 3),
        "runs": results,
    }
    print(json.dumps(out, indent=1))
    return 0 if len(posted) == len(specs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
