"""W1 bake-off runner — one matrix cell (golden brief x image model) per call.

    python scripts/bakeoff.py --brief dental --model google/gemini-3-pro-image
    python scripts/bakeoff.py --brief retail --anchor-model X --followup-model Y
    python scripts/bakeoff.py --report            # matrix so far, no calls

REAL COST. Every run goes through the real pipeline (generate_demo_screens
on frozen golden specs), so what is measured is the product, not a lab rig:
same composition variants, same fixed QA judge, same regeneration rule,
same ledger. Cost comes from the service's own usage rows for that
request_id — never from the key balance, which is shared.

One cell at a time and resumable on purpose: an image matrix is the most
expensive thing this repo does, so it is spent in visible increments with
`--report` between them rather than in one unattended sweep. Cells already
present in the results file are skipped unless --force.

Results: scripts/out/bakeoff/results.json (one row per cell); images under
scripts/out/bakeoff/<brief>/<anchor-model>/.

Each cell gets its OWN uploads dir. Not cosmetic: image paths are keyed by
request id, and this rig runs in throwaway containers whose baked-in
DATABASE_URL beat the service's .env — so every cell opened a fresh DB,
was handed request id 1, and wrote over the previous cell's screenshots.
Cost and QA rows survived in results.json; two images did not. Pinning the
output directory to the cell key removes the coupling entirely, and the
run records the DB it actually resolved so the ledger can be traced.
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
    print(f"{'brief':9s} {'archetype':22s} {'anchor model':30s} {'follow-up model':30s} "
          f"{'anchor QA':>9s} {'mean QA':>8s} {'imgs':>5s} {'$cell':>7s} {'wall':>6s}")
    for r in sorted(rows, key=lambda r: (r["brief"], r["anchor_model"])):
        scores = [s["qa_score"] for s in r["screens"] if s["qa_score"] is not None]
        mean = f"{sum(scores) / len(scores):.2f}" if scores else "-"
        anchor_qa = r["screens"][0]["qa_score"] if r["screens"] else None
        print(f"{r['brief']:9s} {r['archetype']:22s} {r['anchor_model']:30s} {r['followup_model']:30s} "
              f"{str(anchor_qa):>9s} {mean:>8s} {len(r['screens']):>5d} "
              f"{r['ledger']['cost_total']:>7.3f} {r['wall_s']:>5.0f}s")
    print(f"\ncells: {len(rows)}   total ledger: ${sum(r['ledger']['cost_total'] for r in rows):.3f}")


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
    from app.models import Request
    from app.pipeline import images as images_stage

    bundle = golden.load_brief(args.brief)
    specs = bundle["screens"][: args.screens] if args.screens else bundle["screens"]

    cell_dir = os.path.join(
        OUT_DIR, args.brief, anchor_model.replace("/", "_") + (f"__{label}" if label else ""),
    )
    settings.UPLOADS_DIR = cell_dir
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

    init_db()
    db = SessionLocal()
    req = Request(
        business_name=bundle["intake"]["business_name"],
        business_description=bundle["intake"]["business_description"],
        industry=bundle["intake"]["industry"],
        email="bakeoff@example.com",
        status="bakeoff",
        is_generating=False,
    )
    db.add(req)
    db.commit()

    print(f"cell: brief={args.brief} archetype={bundle['archetype']} request={req.id}")
    print(f"      anchor={anchor_model}  follow-ups={followup_model}")
    print(f"      db={settings.DATABASE_URL}  out={cell_dir}")
    print(f"      screens={[s.product.screen_type for s in specs]} "
          f"candidates={settings.DASHBOARD_CANDIDATES}/{settings.SECONDARY_CANDIDATES} "
          f"judge={settings.QA_MODEL} (FIXED)")
    print(f"      register={settings.IMAGE_REGISTER} watermark={settings.WATERMARK_STYLE} "
          f"hero={settings.ENABLE_HERO_ASSET} tool_screens={settings.ENABLE_TOOL_SCREENS} "
          f"ai_layer={settings.ENABLE_AI_LAYER}")

    started = time.monotonic()
    saved = images_stage.generate_demo_screens(
        db, req.id, bundle["archetype"], specs,
        anchor_model=anchor_model, followup_model=followup_model,
        use_design_sheet=args.design_sheet or None,
    )
    wall = time.monotonic() - started

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

    print(f"\n  screens produced: {len(screens)}")
    for s in screens:
        print(f"    {s['role_id']:12s} qa={s['qa_score']} variant={s['composition_variant']} -> {s['file_path']}")
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
