"""Builds a sample branded deck from an existing run's images, so the pptx
can be OPENED and looked at without paying for a new generation.

    python scripts/deck_sample.py --brief dental --run-dir scripts/out/bakeoff/dental/google_gemini-3-pro-image__deck --request 16

The pptx has a history of distortion and overlap bugs (dd181b8, d6e8959)
that no unit test caught, because "the picture is squashed" and "the text
runs into the summary" are things you have to see. This exists so looking
is one command, and so a rendered sample can be committed as evidence.

Costs nothing: reads screenshots and composites already on disk.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import golden


class _Row:
    """Enough of a GeneratedImage for build_presentation — this script does
    not touch the DB, so the deck can be rebuilt from any run directory."""

    def __init__(self, role_id: str, role_label: str, variant: int, file_path: str):
        self.role_id = role_id
        self.role_label = role_label
        self.variant = variant
        self.file_path = file_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", default="dental", choices=golden.brief_ids())
    parser.add_argument("--run-dir", required=True, help="a bake-off cell directory (contains images/<id>/)")
    parser.add_argument("--request", type=int, required=True, help="the request id inside that run dir")
    parser.add_argument("--out", default="scripts/out/deck_sample.pptx")
    args = parser.parse_args()

    from app.config import settings
    from app.pipeline import export_pptx

    root = os.path.abspath(args.run_dir)
    settings.UPLOADS_DIR = root  # _abs_image_path resolves /uploads/... against this

    bundle = golden.load_brief(args.brief)
    intake = bundle["intake"]

    images_dir = os.path.join(root, "images", str(args.request))
    rows = []
    for spec in bundle["screens"]:
        candidate = os.path.join(images_dir, f"{spec.screen_slug}_0.png")
        if os.path.isfile(candidate):
            rows.append(_Row(spec.screen_slug, spec.screen_title, 0, f"/uploads/images/{args.request}/{spec.screen_slug}_0.png"))
    if not rows:
        raise SystemExit(f"no screenshots found under {images_dir}")

    class _Req:
        business_name = intake["business_name"]
        business_description = intake["business_description"]
        industry = intake["industry"]

    # The prose below is PLACEHOLDER, and derived from this brief so it is at
    # least about the right business. Golden briefs are frozen at the ui_spec
    # stage and carry no business analysis and no AI-employee list, so a
    # sample deck has to invent that text.
    #
    # It used to be hardcoded dental copy — "no-shows go unnoticed until the
    # chair sits empty", "lapsed patients are recalled by hand" — which the
    # retail sample duly printed underneath the name of a coffee roastery.
    # What this script exists to check is the deck's LAYOUT: distortion,
    # overlap, proportion, dead space. Nobody should read its sentences and
    # think the pipeline wrote them.
    industry = intake["industry"]
    concept = intake["plan_result"]["concept_name"]
    summary = intake["consult_result"].get("consulting_summary", "")
    analysis = {
        "pain_points": [
            f"[sample] The day is reconstructed by hand from several systems at {intake['business_name']}.",
            f"[sample] Nobody sees a problem in {industry.lower()} until it has already cost something.",
            "[sample] The work that would grow the business is the work that gets postponed.",
        ],
        "growth_opportunity": f"[sample] {summary}" if summary else "[sample] Automate the daily work and act on it sooner.",
    }
    consult_result = {
        **intake["consult_result"],
        "recommended_features": [f"[sample] {concept} daily operations", "[sample] Automated follow-up"],
        "recommended_ai_employees": [
            {"title": "AI Operations Lead", "why": f"[sample] Runs the daily {industry.lower()} workflow and escalates only what needs a person."},
            {"title": "AI Demand Analyst", "why": "[sample] Watches the numbers every day and says what to do about them."},
        ],
    }

    prs = export_pptx.build_presentation(_Req(), analysis, consult_result, intake["plan_result"], rows)
    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    prs.save(out_path)

    composites = sum(1 for f in os.listdir(images_dir) if f.endswith(("_hero.png", "_detail_1.png", "_detail_2.png")))
    print(f"screens: {[r.role_id for r in rows]}")
    print(f"composites on disk: {composites}")
    print(f"slides: {len(prs.slides._sldIdLst)}")
    print(f"wrote {out_path}")
    print(json.dumps({"deck": out_path, "screens": [r.role_id for r in rows]}, indent=2))


if __name__ == "__main__":
    main()
