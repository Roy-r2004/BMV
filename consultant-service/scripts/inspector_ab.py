"""Before/after for a defect-inspector prompt change, on a labelled set.

    python scripts/inspector_ab.py --labels ../docs/evidence/session38/duplication-labels.json

An instrument change needs a measurement, and this is the cheap way to
take one: instruments RE-JUDGE existing screenshots, so a real before/after
costs inspector+verifier calls over images already on disk (~$0.0025 a
screen a side) instead of regenerating anything. Nothing here writes to the
pipeline or the request ledger; it reads PNGs and reports.

Both arms run in this process against the same bytes and the same specs,
through defect_check's own inspect_call/verify_call — not a
reimplementation, because a measurement of a reimplementation measures the
reimplementation. The arms differ only in which template file
image_defect_inspector.j2 resolves to.

The labels are eye-labels: which screens a person opened and judged to
carry a duplicate, and of which sort. That is the ground truth an
instrument is scored against; a second model's opinion is not.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.pipeline import defect_check
from app.ui_spec import UIDemoSpec

SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(SERVICE_ROOT, "app", "prompts", "image_defect_inspector.j2")


def _cost(usage: dict | None) -> float:
    if not usage:
        return 0.0
    return float(usage.get("cost") or 0.0)


def screens_from_db(request_ids: list[int]) -> list[dict]:
    """Every shipped screen for these requests, with its stored spec."""
    from app.database import SessionLocal
    from app.models import GeneratedImage

    db = SessionLocal()
    try:
        rows = (
            db.query(GeneratedImage)
            .filter(GeneratedImage.request_id.in_(request_ids))
            .order_by(GeneratedImage.request_id, GeneratedImage.role_id)
            .all()
        )
        out = []
        for row in rows:
            path = os.path.join(SERVICE_ROOT, row.file_path.lstrip("/"))
            if not os.path.exists(path):
                continue
            out.append({
                "key": f"{row.request_id}/{row.role_label}",
                "path": path,
                "spec": UIDemoSpec.model_validate(json.loads(row.spec_json)) if row.spec_json
                else UIDemoSpec.model_validate({"product": {"screen_type": row.screen_type or ""}}),
            })
        return out
    finally:
        db.close()


def run_arm(screens: list[dict], label: str) -> tuple[dict, float]:
    """Inspector + adversarial verifier over every screen. Only CONFIRMED
    claims count: an unrefuted claim is the instrument's actual output, and
    scoring the inspector's raw claims would credit it for guesses the
    verifier throws away."""
    results, spend = {}, 0.0
    for i, screen in enumerate(screens, start=1):
        with open(screen["path"], "rb") as f:
            image_bytes = f.read()
        inspected = defect_check.inspect_call(image_bytes, screen["spec"])
        spend += _cost(inspected["usage"])
        confirmed = []
        for claim in inspected["claims"]:
            verdict = defect_check.verify_call(image_bytes, claim, screen["spec"])
            spend += _cost(verdict["usage"])
            if verdict["confirmed"]:
                confirmed.append(claim)
        results[screen["key"]] = confirmed
        dups = [c for c in confirmed if c["kind"] == "duplicated_panel"]
        print(
            f'  [{label}] {i:>2}/{len(screens)} {screen["key"]:<22} '
            f'confirmed={len(confirmed)} dup={len(dups)}  ${spend:.4f}'
        )
    return results, spend


def score(results: dict, labels: dict) -> dict:
    """Against the eye-labels, on the duplication class only."""
    tally = Counter()
    misses, false_alarms = [], []
    for key, expected in labels.items():
        found = any(c["kind"] == "duplicated_panel" for c in results.get(key, []))
        truth = bool(expected.get("duplicate"))
        if truth and found:
            tally["caught"] += 1
        elif truth and not found:
            tally["missed"] += 1
            misses.append(f'{key} ({expected.get("what", "")})')
        elif not truth and found:
            tally["false_alarm"] += 1
            false_alarms.append(key)
        else:
            tally["clean"] += 1
    return {"tally": dict(tally), "misses": misses, "false_alarms": false_alarms}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--baseline-template", required=True,
                        help="the OLD template file, kept outside app/prompts")
    args = parser.parse_args()

    labels = json.load(open(args.labels))
    request_ids = sorted({int(k.split("/")[0]) for k in labels})
    screens = [s for s in screens_from_db(request_ids) if s["key"] in labels]
    missing = set(labels) - {s["key"] for s in screens}
    if missing:
        print(f"WARNING: {len(missing)} labelled screens have no image on disk: {sorted(missing)}")
    print(f"{len(screens)} screens, both arms, model={settings.DEFECT_MODEL}\n")

    live = open(TEMPLATE, encoding="utf-8").read()
    baseline = open(args.baseline_template, encoding="utf-8").read()
    backup = tempfile.mktemp(suffix=".j2")
    shutil.copy(TEMPLATE, backup)
    try:
        # Arm A: the shipped v1 rubric, swapped in over the live file so
        # both arms go through exactly the same code.
        open(TEMPLATE, "w", encoding="utf-8").write(baseline)
        before, spend_before = run_arm(screens, "v1")
        open(TEMPLATE, "w", encoding="utf-8").write(live)
        after, spend_after = run_arm(screens, "v2")
    finally:
        shutil.copy(backup, TEMPLATE)
        os.unlink(backup)

    report = {
        "screens": len(screens),
        "model": settings.DEFECT_MODEL,
        "v1": {"score": score(before, labels), "cost_usd": round(spend_before, 5),
               "confirmed": {k: v for k, v in before.items()}},
        "v2": {"score": score(after, labels), "cost_usd": round(spend_after, 5),
               "confirmed": {k: v for k, v in after.items()}},
    }
    print("\nv1:", report["v1"]["score"]["tally"], f'${report["v1"]["cost_usd"]:.4f}')
    print("    misses:", report["v1"]["score"]["misses"])
    print("    false alarms:", report["v1"]["score"]["false_alarms"])
    print("v2:", report["v2"]["score"]["tally"], f'${report["v2"]["cost_usd"]:.4f}')
    print("    misses:", report["v2"]["score"]["misses"])
    print("    false alarms:", report["v2"]["score"]["false_alarms"])

    if args.out:
        json.dump(report, open(args.out, "w"), indent=2)
        print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
