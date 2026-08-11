"""Builds the owner's sign-off sheet: today's default output beside the new
pipeline's, one image per brief, no scores and no commentary.

    python scripts/side_by_side.py --old-label "" --new-label golden

The DoD's pairwise criterion is the owner's call, so this deliberately
shows only the artifacts. Labels name the condition, not the verdict; the
judge's opinion lives in the evidence doc, where it can be disagreed with.

Costs nothing — reads images both runs already produced.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw

import golden

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "bakeoff")
RESULTS_PATH = os.path.join(OUT_DIR, "results.json")
SHEET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "sign-off")

_PANEL_W = 1500
_GAP = 40
_HEADER = 90
_LABEL = 46


def _cell(rows: list[dict], brief: str, label: str) -> dict | None:
    matches = [r for r in rows if r["brief"] == brief and r.get("label", "") == label]
    return matches[-1] if matches else None


def _image_for(cell: dict, variant: str, index: int = 0) -> str | None:
    """The composited hero if the run produced one, else the raw screenshot —
    an old-default run predates compositing and has only the screenshot,
    which is exactly the comparison being shown."""
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), cell["out_dir"])
    if index >= len(cell["screens"]):
        return None
    screen = cell["screens"][index]
    base = os.path.join(root, "images", str(cell["request_id"]))
    for name in (f"{screen['role_id']}_{variant}.png", f"{screen['role_id']}_0.png"):
        path = os.path.join(base, name)
        if os.path.exists(path):
            return path
    return None


def _fit(path: str, width: int) -> Image.Image:
    image = Image.open(path).convert("RGB")
    height = round(image.height * width / image.width)
    return image.resize((width, height), Image.LANCZOS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-label", default="", help="condition label of the current default run")
    parser.add_argument("--new-label", default="golden", help="condition label of the new pipeline run")
    parser.add_argument("--briefs", nargs="+", default=None)
    parser.add_argument(
        "--full-set", action="store_true",
        help="every screen of the new cell on one sheet, instead of one screen beside the old default",
    )
    args = parser.parse_args()

    with open(RESULTS_PATH, encoding="utf-8") as f:
        rows = json.load(f)

    os.makedirs(SHEET_DIR, exist_ok=True)
    briefs = args.briefs or sorted({r["brief"] for r in rows if r.get("label", "") == args.new_label})

    written = []
    for brief in briefs:
        new_cell = _cell(rows, brief, args.new_label)
        old_cell = _cell(rows, brief, args.old_label)
        if new_cell is None:
            print(f"  {brief}: no run labelled {args.new_label!r} — skipped")
            continue

        new_path = _image_for(new_cell, "hero")
        old_path = _image_for(old_cell, "hero") if old_cell else None
        if new_path is None:
            print(f"  {brief}: new image missing on disk — skipped")
            continue

        bundle = golden.load_brief(brief)

        if args.full_set:
            # Every screen of the deliverable, stacked. Every sheet the owner
            # has judged so far showed ONE screen per business; what a client
            # actually receives is the set, and consistency ACROSS the set is
            # the thing a single-screen sheet cannot show.
            panels = []
            for index, screen in enumerate(new_cell["screens"]):
                path = _image_for(new_cell, "hero", index)
                if path is None:
                    print(f"  {brief}: screen {screen['role_id']} missing on disk — skipped")
                    continue
                title = screen["role_id"].replace("_", " ").title()
                panels.append((f"{index + 1}. {title}", path))
            if not panels:
                continue
            images = [(label, _fit(path, _PANEL_W)) for label, path in panels]
            sheet_w = _PANEL_W + 2 * _GAP
            sheet_h = _HEADER + sum(_LABEL + img.height + _GAP for _, img in images)
            sheet = Image.new("RGB", (sheet_w, sheet_h), "#FFFFFF")
            draw = ImageDraw.Draw(sheet)
            draw.text((_GAP, 30), f"{bundle['intake']['business_name']}  —  {bundle['archetype']}", fill="#111827")
            draw.text((_GAP, 52), f"the complete {len(images)}-screen deliverable", fill="#6B7280")
            y = _HEADER
            for label, image in images:
                draw.text((_GAP, y), label, fill="#6B7280")
                sheet.paste(image, (_GAP, y + _LABEL))
                y += _LABEL + image.height + _GAP
        else:
            panels = [("NEW PIPELINE", new_path)]
            if old_path:
                panels.insert(0, ("CURRENT DEFAULT", old_path))
            else:
                print(f"  {brief}: no current-default run to compare against — showing the new one alone")

            images = [(label, _fit(path, _PANEL_W)) for label, path in panels]
            sheet_w = len(images) * _PANEL_W + (len(images) + 1) * _GAP
            sheet_h = _HEADER + _LABEL + max(img.height for _, img in images) + _GAP
            sheet = Image.new("RGB", (sheet_w, sheet_h), "#FFFFFF")
            draw = ImageDraw.Draw(sheet)

            draw.text((_GAP, 30), f"{bundle['intake']['business_name']}  —  {bundle['archetype']}", fill="#111827")
            draw.text((_GAP, 52), f"{bundle['screens'][0].screen_title} screen", fill="#6B7280")

            x = _GAP
            for label, image in images:
                draw.text((x, _HEADER), label, fill="#6B7280")
                sheet.paste(image, (x, _HEADER + _LABEL))
                x += _PANEL_W + _GAP

        out_path = os.path.join(SHEET_DIR, f"{brief}.png")
        sheet.save(out_path)
        written.append(out_path)
        print(f"  {brief}: {' vs '.join(l for l, _ in images)} -> {out_path}")

    print(f"\n{len(written)} sheet(s) in {SHEET_DIR}")


if __name__ == "__main__":
    main()
