"""Freezes the golden brief set — runs the REAL ui_spec stage on the intake
fixtures and writes the resulting UIDemoSpecs to golden/briefs/<id>.json.

    python scripts/build_golden.py                 # rebuild every brief
    python scripts/build_golden.py --only dental law retail
    python scripts/build_golden.py --dry-run       # show what exists, call nothing

Costs one cheap text call per brief (ANALYSIS_MODEL, ~$0.001 each) and
prints the ledger delta it caused. Images are NEVER generated here.

Re-running overwrites the frozen briefs, which silently invalidates every
past evaluation that cited them — so it refuses unless --force is passed
for briefs that already exist. This is a fixture builder, not a pipeline
stage; nothing in the service imports it.
"""

import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from golden import BRIEFS_DIR
from golden.intake import INTAKE_FIXTURES


def _ledger_total(db) -> float:
    from app.models import AiUsageEvent

    return sum(e.cost_usd or 0 for e in db.query(AiUsageEvent).all())


def _ui_spec_call_succeeded(db, request_id: int) -> bool:
    """build_ui_specs never raises — on any failure it silently returns its
    generic deterministic specs ("Alex", "Bookings Today"). Freezing those as
    a golden brief would mean measuring every future model against a demo
    that is business-specific for nobody. The stage's own ledger row is the
    honest signal, so ask it rather than sniffing the returned text.
    """
    from app.models import AiUsageEvent

    row = (
        db.query(AiUsageEvent)
        .filter(AiUsageEvent.request_id == request_id, AiUsageEvent.purpose == "ui_spec")
        .order_by(AiUsageEvent.id.desc())
        .first()
    )
    return bool(row and row.success)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", choices=sorted(INTAKE_FIXTURES), help="rebuild just these briefs")
    parser.add_argument("--force", action="store_true", help="overwrite briefs that already exist")
    parser.add_argument("--dry-run", action="store_true", help="list what would happen; make no calls")
    args = parser.parse_args()

    from app.config import settings
    from app.database import SessionLocal, init_db
    from app.models import Request
    from app.pipeline import ui_spec

    os.makedirs(BRIEFS_DIR, exist_ok=True)
    wanted = args.only or sorted(INTAKE_FIXTURES)

    todo = []
    for bid in wanted:
        path = os.path.join(BRIEFS_DIR, f"{bid}.json")
        if os.path.exists(path) and not args.force:
            print(f"  {bid}: already frozen -> {path} (pass --force to rebuild)")
            continue
        todo.append(bid)

    if not todo:
        print("nothing to build.")
        return
    print(f"to build: {', '.join(todo)}  (model={settings.ANALYSIS_MODEL})")
    if args.dry_run:
        print("(dry run — no calls made)")
        return

    init_db()
    db = SessionLocal()
    before = _ledger_total(db)

    failed: list[str] = []
    for bid in todo:
        fixture = INTAKE_FIXTURES[bid]
        archetype_id = specs = None
        for attempt in range(3):
            req = Request(
                business_name=fixture["business_name"],
                business_description=fixture["business_description"],
                industry=fixture["industry"],
                email=fixture["email"],
                status="golden-build",
                is_generating=False,
            )
            db.add(req)
            db.commit()
            archetype_id, specs = ui_spec.build_ui_specs(
                db, req.id, fixture["consult_result"], fixture["plan_result"]
            )
            if _ui_spec_call_succeeded(db, req.id):
                break
            print(f"  {bid}: ui_spec fell back to generic specs (attempt {attempt + 1}/3) — not freezing that")
        else:
            failed.append(bid)
            continue

        bundle = {
            "id": bid,
            "label": f"{fixture['business_name']} — {fixture['industry']}",
            "archetype": archetype_id,
            "intake": {k: v for k, v in fixture.items() if k != "email"},
            "frozen_on": date.today().isoformat(),
            "frozen_by": {
                "analysis_model": settings.ANALYSIS_MODEL,
                "ui_spec_prompt_version": ui_spec.UI_SPEC_PROMPT_VERSION,
            },
            "screens": [json.loads(s.model_dump_json()) for s in specs],
        }
        path = os.path.join(BRIEFS_DIR, f"{bid}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(
            f"  {bid}: archetype={archetype_id} screens={[s.product.screen_type for s in specs]} -> {path}"
        )

    after = _ledger_total(db)
    print(f"\nledger delta for this build: ${after - before:.4f}")
    if failed:
        print(f"NOT FROZEN (ui_spec fell back every attempt): {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
