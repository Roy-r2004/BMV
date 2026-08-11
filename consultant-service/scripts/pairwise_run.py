"""Runs the bake-off's pairwise pass: for each golden brief, the anchor from
one model against the anchor from another, judged in both orders by the
FIXED judge.

    python scripts/pairwise_run.py --a google/gemini-3-pro-image --b google/gemini-3.1-flash-image
    python scripts/pairwise_run.py ... --briefs dental law

Reads the images the bake-off already produced (scripts/out/bakeoff), so it
costs only judge calls — a few cents — and never regenerates anything.
Results append to scripts/out/bakeoff/pairwise.json.
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import golden

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "bakeoff")
RESULTS_PATH = os.path.join(OUT_DIR, "results.json")
PAIRWISE_PATH = os.path.join(OUT_DIR, "pairwise.json")


def _cells() -> list[dict]:
    with open(RESULTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _anchor_image(cell: dict) -> str | None:
    """The cell's anchor screenshot on disk. Cells are keyed by anchor model
    but several may share a directory (the tiering run reuses the pro anchor
    dir), so the request id in the path is what disambiguates."""
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), cell["out_dir"])
    screen = cell["screens"][0]
    path = os.path.join(root, "images", str(cell["request_id"]), f"{screen['role_id']}_0.png")
    return path if os.path.exists(path) else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a", required=True, help="anchor model A")
    parser.add_argument("--b", required=True, help="anchor model B")
    parser.add_argument("--briefs", nargs="+", default=list(golden.BAKEOFF_BRIEF_IDS))
    # For A/B comparisons where both sides used the SAME model and differ
    # only by condition (W2's pack vs no-pack), the condition label is what
    # separates the two cells.
    parser.add_argument("--a-label", default="", help="condition label of side A (e.g. nopack)")
    parser.add_argument("--b-label", default="", help="condition label of side B")
    args = parser.parse_args()

    from app.database import SessionLocal, init_db
    from app.pipeline import pairwise

    cells = _cells()
    init_db()
    db = SessionLocal()

    existing = []
    if os.path.exists(PAIRWISE_PATH):
        with open(PAIRWISE_PATH, encoding="utf-8") as f:
            existing = json.load(f)

    for brief_id in args.briefs:
        bundle = golden.load_brief(brief_id)
        spec = bundle["screens"][0]

        def pick(model: str, label: str) -> dict | None:
            matches = [
                c for c in cells
                if c["brief"] == brief_id and c["anchor_model"] == model
                and c["followup_model"] == model and c.get("label", "") == label
            ]
            return matches[-1] if matches else None

        cell_a, cell_b = pick(args.a, args.a_label), pick(args.b, args.b_label)
        if not cell_a or not cell_b:
            missing = f"{args.a}/{args.a_label}" if not cell_a else f"{args.b}/{args.b_label}"
            print(f"  {brief_id}: missing a cell for {missing} — skipped")
            continue
        path_a, path_b = _anchor_image(cell_a), _anchor_image(cell_b)
        if not path_a or not path_b:
            print(f"  {brief_id}: anchor image missing on disk — skipped ({path_a} / {path_b})")
            continue

        with open(path_a, "rb") as f:
            bytes_a = f.read()
        with open(path_b, "rb") as f:
            bytes_b = f.read()

        label_a = f"{args.a}[{args.a_label}]" if args.a_label else args.a
        label_b = f"{args.b}[{args.b_label}]" if args.b_label else args.b
        result = pairwise.compare(
            db, None, bytes_a, bytes_b, spec, left_label=label_a, right_label=label_b,
        )
        record = {
            "brief": brief_id,
            "archetype": bundle["archetype"],
            "screen": spec.product.screen_type,
            "a": label_a, "b": label_b,
            "a_image": os.path.relpath(path_a, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "b_image": os.path.relpath(path_b, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "ran_at": datetime.now().isoformat(timespec="seconds"),
            **result,
        }
        existing.append(record)
        verdict = result["winner"] if result["consistent"] else f"tie ({result['forward_pick']} / {result['reverse_pick']})"
        print(f"  {brief_id:8s} [{bundle['archetype']}] -> {verdict}")
        for run in result["runs"]:
            print(f"      {run['order']:38s} {run['winner']} ({run['margin']}): {run['why']}")

    with open(PAIRWISE_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
        f.write("\n")
    print(f"\nwrote {PAIRWISE_PATH}")


if __name__ == "__main__":
    main()
