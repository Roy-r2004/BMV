"""Golden-brief runner — one cell (brief x image model) per call, through
the pipeline a customer actually gets.

    python scripts/bakeoff.py --brief dental --model google/gemini-3-pro-image
    python scripts/bakeoff.py --brief retail --anchor-model X --followup-model Y
    python scripts/bakeoff.py --report            # matrix so far, no calls

EVERY RUN IS A CUSTOMER RUN (owner's rule, session 35). A cell submits the
brief's INTAKE — the same three fields the /studio form collects — and runs
`orchestrator.run`, the identical entry point the public route hands to its
background thread. All six text stages execute, the spec is derived rather
than replayed, progress is emitted, and the screens land under the real
UPLOADS_DIR. The consequence that matters: **every cell is viewable at
/studio/<request_id> exactly as the customer would see it**, and a number
measured here is a number about the product.

What that costs, stated up front rather than discovered later:

  - ~$0.018/brief more than the frozen path, for the text stages.
  - The ui_spec stage runs live, so KPI labels, panels and screen count
    differ run to run. Two cells that vary only by image model are no
    longer a clean A/B — the spec moved underneath them too. That is the
    exact property `golden/` was frozen to preserve, and it is the price of
    measuring the real thing.
  - Screen count comes from the plan stage, not from the brief's frozen
    screen list, so a cell may produce a different number of screens than
    the same brief did in session 34.

`--frozen-specs` restores the old behaviour for ONE job only: reproducing a
historical cell (sessions 31-34 were all measured that way) so a past
comparison stays checkable. It is not what a customer gets, it writes
outside /uploads, and it is never the default.

REAL COST either way. Cost comes from the service's own usage rows for that
request_id — never from the key balance, which is shared.

One cell at a time and resumable on purpose: an image matrix is the most
expensive thing this repo does, so it is spent in visible increments with
`--report` between them rather than in one unattended sweep. Cells already
present in the results file are skipped unless --force.

Results: scripts/out/bakeoff/results.json (one row per cell). Full-pipeline
images live under uploads/images/<request_id>/ like any other run; frozen
cells still get their own directory under scripts/out/bakeoff/<brief>/…,
because their request ids are not unique across throwaway databases and one
cell overwriting another's screenshots has already cost this project a
$0.353 result.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import golden

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "bakeoff")
RESULTS_PATH = os.path.join(OUT_DIR, "results.json")


def _load_results() -> list[dict]:
    if not os.path.exists(RESULTS_PATH):
        return []
    with open(RESULTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_results(rows: list[dict]) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
        f.write("\n")


def _cell_key(brief_id: str, anchor_model: str, followup_model: str, label: str = "") -> str:
    """`label` names a non-default CONDITION (e.g. "nopack"), so an A/B pair
    can share a brief and a model without colliding. Empty label keeps the
    key identical to the pre-A/B format, so earlier cells stay addressable."""
    key = f"{brief_id}|{anchor_model}|{followup_model}"
    return f"{key}|{label}" if label else key


def _ledger_for_request(db, request_id: int) -> dict:
    from app.models import AiUsageEvent

    events = db.query(AiUsageEvent).filter(AiUsageEvent.request_id == request_id).all()
    image_events = [e for e in events if e.purpose == "image"]
    return {
        "cost_total": round(sum(e.cost_usd or 0 for e in events), 5),
        "cost_images": round(sum(e.cost_usd or 0 for e in image_events), 5),
        "cost_qa": round(sum(e.cost_usd or 0 for e in events if e.purpose == "image_qa"), 5),
        "image_calls_ok": sum(1 for e in image_events if e.success),
        "image_calls_failed": sum(1 for e in image_events if not e.success),
        "per_model_image_cost": {
            model: round(sum(e.cost_usd or 0 for e in image_events if e.model == model and e.success), 5)
            for model in sorted({e.model for e in image_events})
        },
        "per_model_image_calls": {
            model: sum(1 for e in image_events if e.model == model and e.success)
            for model in sorted({e.model for e in image_events})
        },
    }


def report(rows: list[dict]) -> None:
    if not rows:
        print("no cells run yet.")
        return
    print(f"{'brief':9s} {'pipe':6s} {'archetype':22s} {'anchor model':30s} {'follow-up model':30s} "
          f"{'anchor QA':>9s} {'mean QA':>8s} {'imgs':>5s} {'$cell':>7s} {'wall':>6s}")
    for r in sorted(rows, key=lambda r: (r["brief"], r["anchor_model"])):
        scores = [s["qa_score"] for s in r["screens"] if s["qa_score"] is not None]
        mean = f"{sum(scores) / len(scores):.2f}" if scores else "-"
        anchor_qa = r["screens"][0]["qa_score"] if r["screens"] else None
        # Rows from before session 35 carry no "pipeline" key and were all
        # frozen replays. Printed as such rather than blank, so the two are
        # never silently averaged together.
        pipe = r.get("pipeline", "frozen")
        print(f"{r['brief']:9s} {pipe:6s} {r['archetype']:22s} {r['anchor_model']:30s} {r['followup_model']:30s} "
              f"{str(anchor_qa):>9s} {mean:>8s} {len(r['screens']):>5d} "
              f"{r['ledger']['cost_total']:>7.3f} {r['wall_s']:>5.0f}s")
    kinds = {r.get("pipeline", "frozen") for r in rows}
    print(f"\ncells: {len(rows)}   total ledger: ${sum(r['ledger']['cost_total'] for r in rows):.3f}")
    if kinds == {"frozen", "full"}:
        print("NOTE: this table mixes frozen-spec replays with full customer runs. "
              "They do not share a spec, a screen count or a cost base — compare within a mode.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", choices=golden.brief_ids())
    parser.add_argument("--model", help="same model for anchor and follow-ups")
    parser.add_argument("--anchor-model")
    parser.add_argument("--followup-model")
    parser.add_argument("--screens", type=int, help="limit to the first N screens (cheap probes)")
    parser.add_argument("--candidates", type=int, help="override DASHBOARD_CANDIDATES for this cell")
    parser.add_argument("--secondary", type=int, help="override SECONDARY_CANDIDATES for this cell")
    parser.add_argument("--label", default="", help="name this condition (e.g. nopack) so an A/B pair does not collide")
    parser.add_argument("--no-art-packs", action="store_true", help="W2 A/B control: run with ENABLE_ART_PACKS off")
    parser.add_argument("--design-sheet", action="store_true", help="W5: generate a style board first and condition every screen on it")
    parser.add_argument("--register", choices=("cinematic", "light"), help="design register for this cell (session 32 A/B)")
    parser.add_argument("--watermark", choices=("footer", "corner"), help="where the BMV mark goes; 'corner' also re-adds the corner reservation to the prompt")
    parser.add_argument("--force", action="store_true", help="re-run a cell that already has a result")
    parser.add_argument("--report", action="store_true", help="print the matrix so far and exit")
    parser.add_argument(
        "--frozen-specs", action="store_true",
        help="replay the brief's frozen UIDemoSpecs instead of running the text stages. "
             "For reproducing a session 31-34 cell ONLY — this is not what a customer gets, "
             "and its screens do not appear at /studio/<id>.",
    )
    args = parser.parse_args()

    rows = _load_results()
    if args.report:
        report(rows)
        return

    if not args.brief:
        parser.error("--brief is required (or use --report)")
    anchor_model = args.anchor_model or args.model
    followup_model = args.followup_model or args.model or anchor_model
    if not anchor_model:
        parser.error("pass --model, or --anchor-model and --followup-model")

    # The register belongs in the cell key. Two cells that differ only by
    # register would otherwise share a key AND an output directory, and the
    # second would silently overwrite the first's screenshots — which has
    # already cost this project one lost cell (session 31, $0.353).
    label = args.label or ("nopack" if args.no_art_packs else "")
    if args.register:
        label = f"{label}-{args.register}" if label else args.register
    key = _cell_key(args.brief, anchor_model, followup_model, label)
    if not args.force and any(r["key"] == key for r in rows):
        print(f"cell already run: {key} (pass --force to re-run)")
        return

    from app.config import settings
    from app.database import SessionLocal, init_db
    from app.models import GeneratedImage, Request
    from app.pipeline import images as images_stage
    from app.pipeline import orchestrator

    bundle = golden.load_brief(args.brief)

    # Model choice reaches the full pipeline through settings, because
    # orchestrator.run takes no model arguments — the customer path has no
    # way to pass one, and giving it one here would be a second code path.
    settings.IMAGE_MODEL_ANCHOR = anchor_model
    settings.IMAGE_MODEL_FOLLOWUP = followup_model
    if args.no_art_packs:
        settings.ENABLE_ART_PACKS = False
    if args.register:
        settings.IMAGE_REGISTER = args.register
    if args.watermark:
        settings.WATERMARK_STYLE = args.watermark
    if args.candidates:
        settings.DASHBOARD_CANDIDATES = args.candidates
    if args.secondary:
        settings.SECONDARY_CANDIDATES = args.secondary
    if args.design_sheet:
        settings.USE_DESIGN_SHEET = True
    if args.screens:
        settings.DEMO_SCREEN_COUNT = args.screens

    # Only a frozen replay gets its own uploads dir. A full run is a real
    # run: its images belong under UPLOADS_DIR, addressed by a request id
    # the shared database made unique, which is what makes the cell
    # viewable at /studio/<id>.
    cell_dir = os.path.join(
        OUT_DIR, args.brief, anchor_model.replace("/", "_") + (f"__{label}" if label else ""),
    )
    if args.frozen_specs:
        settings.UPLOADS_DIR = cell_dir

    init_db()
    db = SessionLocal()
    req = Request(
        business_name=bundle["intake"]["business_name"],
        business_description=bundle["intake"]["business_description"],
        industry=bundle["intake"]["industry"],
        email="bakeoff@example.com",
        # A full run moves through the same states the route drives, so the
        # progress endpoint and the studio page behave identically to a
        # customer's. A frozen replay never enters that ladder.
        status="bakeoff" if args.frozen_specs else "new",
        is_generating=not args.frozen_specs,
    )
    db.add(req)
    db.commit()

    mode = "FROZEN SPECS (historical replay)" if args.frozen_specs else "FULL PIPELINE (customer path)"
    print(f"cell: brief={args.brief} archetype={bundle['archetype']} request={req.id}")
    print(f"      mode={mode}")
    print(f"      anchor={anchor_model}  follow-ups={followup_model}")
    print(f"      db={settings.DATABASE_URL}")
    print(f"      out={cell_dir if args.frozen_specs else os.path.join(settings.UPLOADS_DIR, 'images', str(req.id))}")
    print(f"      candidates={settings.DASHBOARD_CANDIDATES}/{settings.SECONDARY_CANDIDATES} "
          f"judge={settings.QA_MODEL} (FIXED)")
    print(f"      register={settings.IMAGE_REGISTER} watermark={settings.WATERMARK_STYLE} "
          f"hero={settings.ENABLE_HERO_ASSET} tool_screens={settings.ENABLE_TOOL_SCREENS} "
          f"ai_layer={settings.ENABLE_AI_LAYER}")

    started = time.monotonic()
    if args.frozen_specs:
        specs = bundle["screens"][: args.screens] if args.screens else bundle["screens"]
        print(f"      screens={[s.product.screen_type for s in specs]} (replayed, text stages SKIPPED)")
        saved = images_stage.generate_demo_screens(
            db, req.id, bundle["archetype"], specs,
            anchor_model=anchor_model, followup_model=followup_model,
            use_design_sheet=args.design_sheet or None,
        )
    else:
        print(f"      screens=decided by the plan stage (max {settings.DEMO_SCREEN_COUNT})")
        # The same call the public route hands to its background thread.
        # It owns its own session and never raises: a failure lands on the
        # request row, which is read back below.
        orchestrator.run(req.id)
        db.expire_all()
        saved = (
            db.query(GeneratedImage)
            .filter(GeneratedImage.request_id == req.id)
            .order_by(GeneratedImage.role_id, GeneratedImage.variant)
            .all()
        )
    wall = time.monotonic() - started

    req = db.get(Request, req.id)
    screens = [
        {
            "role_id": row.role_id,
            "screen_type": row.screen_type,
            "model": row.model,
            "composition_variant": row.composition_variant,
            "qa_score": row.qa_score,
            "qa_issues": json.loads(row.qa_issues or "[]"),
            "file_path": row.file_path,
        }
        for row in saved
    ]
    ledger = _ledger_for_request(db, req.id)
    row = {
        "key": key,
        "label": label,
        # Which path produced this cell. Rows written before session 35 have
        # no such field and were all frozen replays — absent must never be
        # read as "full", or a s34 number gets compared to a s35 one as
        # though the pipeline under them were the same.
        "pipeline": "frozen" if args.frozen_specs else "full",
        "status": req.status,
        "is_failed": bool(req.is_failed),
        "concept_name": req.concept_name,
        "art_packs": settings.ENABLE_ART_PACKS,
        "design_sheet": bool(args.design_sheet),
        "register": settings.IMAGE_REGISTER,
        "watermark": settings.WATERMARK_STYLE,
        "hero_asset": settings.ENABLE_HERO_ASSET,
        "tool_screens": settings.ENABLE_TOOL_SCREENS,
        "ai_layer": settings.ENABLE_AI_LAYER,
        "briefs_dir": os.path.relpath(golden.briefs_dir(), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "brief": args.brief,
        "archetype": bundle["archetype"],
        "anchor_model": anchor_model,
        "followup_model": followup_model,
        "request_id": req.id,
        "out_dir": os.path.relpath(cell_dir, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "database_url": settings.DATABASE_URL,
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "wall_s": round(wall, 1),
        "judge_model": settings.QA_MODEL,
        "candidates": [settings.DASHBOARD_CANDIDATES, settings.SECONDARY_CANDIDATES],
        "screens": screens,
        "ledger": ledger,
    }
    rows = [r for r in rows if r["key"] != key] + [row]
    _save_results(rows)

    if req.is_failed:
        print(f"\n  RUN FAILED at stage '{req.stage}': {req.stage_label}")
        if req.progress_detail:
            print(f"    {req.progress_detail}")

    print(f"\n  screens produced: {len(screens)}")
    for s in screens:
        print(f"    {s['role_id']:12s} qa={s['qa_score']} variant={s['composition_variant']} -> {s['file_path']}")
    if not args.frozen_specs:
        print(f"  view it as the customer would: /studio/{req.id}")
    print(f"  wall: {wall:.0f}s   ledger: ${ledger['cost_total']:.4f} "
          f"(images ${ledger['cost_images']:.4f}, qa ${ledger['cost_qa']:.4f})")
    print(f"  per-image cost by model: "
          + ", ".join(
              f"{m}: ${c / max(1, ledger['per_model_image_calls'][m]):.4f} x{ledger['per_model_image_calls'][m]}"
              for m, c in ledger["per_model_image_cost"].items()
          ))
    if ledger["image_calls_failed"]:
        print(f"  NOTE: {ledger['image_calls_failed']} image call(s) failed and were retried/regenerated")


if __name__ == "__main__":
    main()
