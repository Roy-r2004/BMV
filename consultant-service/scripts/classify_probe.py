"""What archetype does an intake actually land on? — text stages only.

    python scripts/classify_probe.py                     # the standing set
    python scripts/classify_probe.py --only chatbot

Runs analyze -> consult -> plan -> ui_spec on a real Request row, through
the same functions the customer path calls, and stops before the image
stage. That is the whole point: the archetype decision is made by the
ui_spec LLM reading the consulting analysis, so the only honest way to ask
"where does this class of request land today?" is to run the stages that
decide it. Roughly $0.005 a brief, against ~$0.63 for a full generation —
cheap enough to ask before building a new shape, and far more informative
than reading a frozen golden bundle, which pins the day it was frozen
rather than what the classifier does now.

Rows land in the real database so their cost is in the real ledger and
readable at /api/requests/<id>/admin like any other spend. They carry no
images on purpose; a probe id opened at /studio/<id> will honestly say so.

Results: scripts/out/classify/results.json, appended one row per run.
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, init_db
from app.models import AiUsageEvent, Request
from app import archetypes
from app.pipeline import analyze, consult, plan, ui_spec

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "classify")

# One intake per request CLASS the session-38 brief asks about, written the
# way a customer writes it rather than the way a golden fixture does —
# short, lower-case, no consulting vocabulary. `salon` is the control: it
# is the class the catalogue was built for, and if it ever moves, the probe
# is measuring the weather rather than the classifier.
PROBES: dict[str, dict] = {
    "investment": {
        "business_name": "Ridgeline Capital",
        "business_description": (
            "I run a small investment firm. I need an investment system to manage client "
            "portfolios, track performance against benchmarks and see risk in one place."
        ),
        "industry": "Investment Management",
    },
    "chatbot": {
        "business_name": "Halden & Co",
        "business_description": (
            "I want an AI chatbot for my business that answers customer questions and books "
            "appointments, and I want to see the conversations it handled."
        ),
        "industry": "Professional Services",
    },
    "portfolio": {
        "business_name": "Jeanne Art",
        "business_description": (
            "I wanna showcase my paitings, with a dashboard that contains home, gallery, "
            "about, contact"
        ),
        "industry": "Art - Artists - paintings",
    },
    "courses": {
        "business_name": "Northlight Studio School",
        "business_description": (
            "We run evening art courses. I want an AI assistant on the site that answers "
            "questions about the courses, handles enrolment and passes the tricky ones to me. "
            "I want to read every conversation it had."
        ),
        "industry": "Adult Education",
    },
    "salon": {
        "business_name": "Lumière Hair Studio",
        "business_description": (
            "Hair salon with five stylists. Colour, cuts, treatments and extensions. "
            "The phone rings all day and we lose bookings we never hear about."
        ),
        "industry": "Hair Salon",
    },
}


def _cost(db, request_id: int) -> float:
    rows = db.query(AiUsageEvent).filter(AiUsageEvent.request_id == request_id).all()
    return round(sum(e.cost_usd or 0 for e in rows), 5)


def probe(name: str) -> dict:
    intake = PROBES[name]
    db = SessionLocal()
    try:
        req = Request(
            **intake,
            email="probe@buildmyversion.local",
            status="new",
            # Never true: is_generating is what the capacity gate counts and
            # what the startup sweep fails as stranded.
            is_generating=False,
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        request_id = req.id

        analysis = analyze.analyze_business(db, request_id)
        consult_result = consult.consult(db, request_id, analysis)
        plan_result = plan.plan_integration(db, request_id, consult_result)
        archetype_id, specs = ui_spec.build_ui_specs(db, request_id, consult_result, plan_result)

        req = db.get(Request, request_id)
        req.status = "done"
        db.commit()

        return {
            "probe": name,
            "request_id": request_id,
            # Which shapes existed when this was measured. Without it, a
            # row saying "chatbot -> operations-dashboard" is unreadable
            # later: was the console missing, or was it there and not
            # chosen? Those are opposite findings.
            "catalog": sorted(archetypes.ARCHETYPES),
            "business_name": intake["business_name"],
            "archetype": archetype_id,
            "screens": [s.product.screen_type for s in specs],
            "navigation": specs[0].navigation,
            "concept_name": specs[0].product.name,
            "anchor_kind": specs[0].concept.kind or "none",
            "anchor_choice": specs[0].concept.steps[0].label if specs[0].concept.steps else None,
            "consulting_summary": consult_result.get("consulting_summary", "")[:200],
            "cost_usd": _cost(db, request_id),
            "ran_at": datetime.utcnow().isoformat(timespec="seconds"),
        }
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append", choices=sorted(PROBES), default=None)
    args = parser.parse_args()

    init_db()
    os.makedirs(OUT_DIR, exist_ok=True)
    results_path = os.path.join(OUT_DIR, "results.json")
    existing = json.load(open(results_path)) if os.path.exists(results_path) else []

    total = 0.0
    for name in (args.only or list(PROBES)):
        row = probe(name)
        existing.append(row)
        total += row["cost_usd"]
        print(
            f'{row["probe"]:11s} req={row["request_id"]:<4} {row["archetype"]:22s} '
            f'{"->".join(row["screens"]):28s} ${row["cost_usd"]:.5f}'
        )
        print(f'{"":11s} nav={row["navigation"]}')
        print(f'{"":11s} anchor={row["anchor_kind"]}: {row["anchor_choice"]}')

    json.dump(existing, open(results_path, "w"), indent=2)
    print(f"\ntotal ${total:.5f} -> {results_path}")


if __name__ == "__main__":
    main()
