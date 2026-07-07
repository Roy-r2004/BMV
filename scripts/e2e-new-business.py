"""Submit a fresh business, wait for preview, test refine chat."""
from __future__ import annotations

import json
import sys
import time

import requests

BASE = "http://127.0.0.1:8001"
STAMP = int(time.time())


def main() -> int:
    data = {
        "business_name": "Paws & Polish Mobile Grooming",
        "industry": "Pet services",
        "business_description": (
            "Mobile dog grooming for busy pet owners in Austin. "
            "We come to your home with professional equipment and eco-friendly products."
        ),
        "target_customers": "Dog owners who want convenient, stress-free grooming at home",
        "main_problem": "Booking visits, managing mobile routes, and keeping pet profiles organized",
        "reference_url": "https://calendly.com",
        "what_you_like": "Clean booking flow, simple calendar picker, and instant confirmations",
        "desired_outcome": "A branded app where customers book grooming slots and we manage our schedule",
        "needs_ai": "yes",
        "budget_range": "Standard scope",
        "timeline": "1–2 months",
        "email": f"test.paws.{STAMP}@example.com",
    }

    print("Submitting new business (AI pipeline may take several minutes)...", flush=True)
    try:
        resp = requests.post(f"{BASE}/api/requests", data=data, timeout=600)
        resp.raise_for_status()
    except Exception as exc:
        print(f"CREATE FAILED: {exc}", flush=True)
        return 1

    req_id = resp.json()["id"]
    print(f"Created request #{req_id}", flush=True)

    preview: dict = {}
    for attempt in range(1, 121):
        try:
            preview = requests.get(f"{BASE}/api/requests/{req_id}/preview", timeout=60).json()
        except Exception as exc:
            print(f"  poll {attempt}: {exc}", flush=True)
            time.sleep(5)
            continue

        concept = preview.get("concept_name")
        generating = preview.get("is_generating")
        print(
            f"  poll {attempt}: concept={concept or '—'} generating={generating} status={preview.get('status')}",
            flush=True,
        )
        if concept and not generating:
            break
        time.sleep(5)

    visual = preview.get("visual_demo") or {}
    hero = visual.get("hero") or {}
    app_config = visual.get("app_config") or {}
    tabs = app_config.get("tabs") or []

    print("\n=== PREVIEW ===", flush=True)
    print(f"concept_name: {preview.get('concept_name')}", flush=True)
    print(f"industry: {preview.get('industry')}", flush=True)
    print(f"hero: {hero.get('headline')}", flush=True)
    print(f"tabs: {[t.get('label') for t in tabs]}", flush=True)
    print(f"features: {preview.get('preview_features', [])[:5]}", flush=True)

    print("\nTesting refine chatbot...", flush=True)
    try:
        chat = requests.post(
            f"{BASE}/api/requests/{req_id}/chat",
            json={
                "message": (
                    "Make the header darker with warm gold accents, rename the home tab to "
                    "'Grooming bookings', and add a pet profile feature card."
                )
            },
            timeout=600,
        )
        chat.raise_for_status()
        chat_data = chat.json()
    except Exception as exc:
        print(f"CHAT FAILED: {exc}", flush=True)
        chat_data = {}

    if chat_data:
        print(f"reply: {(chat_data.get('reply') or '')[:280]}", flush=True)
        print(f"preview_updated: {chat_data.get('preview_updated')}", flush=True)
        print(f"changes_made: {chat_data.get('changes_made')}", flush=True)
        if chat_data.get("visual_demo"):
            updated = chat_data["visual_demo"]
            print(
                f"updated hero: {(updated.get('hero') or {}).get('headline')}",
                flush=True,
            )

    print(f"\nVIEW: http://localhost:5175/result/{req_id}", flush=True)
    print(
        json.dumps(
            {
                "id": req_id,
                "concept_name": preview.get("concept_name"),
                "chat_ok": bool(chat_data.get("reply")),
            }
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
